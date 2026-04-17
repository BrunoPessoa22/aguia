#!/usr/bin/env python3
"""
FALCAO Video Generator — fal.ai powered text-to-video pipeline.

Generates short-form video (7-90s) for X, LinkedIn, and Instagram Reels via
fal.ai. Default model: Seedance 1.0 Pro. Fallbacks: Veo 3, Kling 2.1, Runway Gen-3.

Output: MP4 file at --out path. Appends cost + metadata to the video ledger for
monthly budget enforcement.

Usage:
    python3 falcao-video-gen.py \\
        --prompt "Rapid cuts of a Brazilian stadium at dusk..." \\
        --channel x \\
        --duration 8 \\
        --style documentary \\
        --out /tmp/out.mp4

Env:
    FAL_KEY               — required, from fal.ai dashboard
    VIDEO_BUDGET_USD      — monthly spend cap (default 50.0)
    FALCAO_MOCK           — if set to "1", produce a tiny ffmpeg-generated MP4
                             instead of calling fal.ai. For local testing.

Design notes:
    * Seedance 2.0 is NOT publicly released (Apr 2026). When it lands, add the
      model ID to MODELS and bump DEFAULT_MODEL.
    * Captions are burned separately by falcao-video-caption.py — keep this
      script focused on generation.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

AGUIA_ROOT = Path("$AGUIA_HOME")
ENV_FILE = AGUIA_ROOT / ".env"
LEDGER_PATH = AGUIA_ROOT / "agents/falcao/data/video-ledger.jsonl"

# Model routing. Cost is USD per second of generated video.
# Source: fal.ai pricing page + model card defaults (Apr 2026).
MODELS: dict[str, dict] = {
    "seedance-pro": {
        "id": "fal-ai/bytedance/seedance/v1/pro/text-to-video",
        "cost_per_sec": 0.25,
        "max_duration": 10,
        "aspects": ["9:16", "16:9", "1:1"],
    },
    "veo3": {
        "id": "fal-ai/veo3",
        "cost_per_sec": 0.75,
        "max_duration": 8,
        "aspects": ["9:16", "16:9"],
    },
    "kling-21": {
        "id": "fal-ai/kling-video/v2.1/pro/text-to-video",
        "cost_per_sec": 0.15,
        "max_duration": 10,
        "aspects": ["9:16", "16:9", "1:1"],
    },
    "runway-gen3": {
        "id": "fal-ai/runway-gen3/turbo/text-to-video",
        "cost_per_sec": 0.20,
        "max_duration": 10,
        "aspects": ["16:9", "9:16"],
    },
}
DEFAULT_MODEL = "seedance-pro"

CHANNEL_RULES = {
    "x": {"min": 15, "max": 45, "default_aspect": "9:16"},
    "linkedin": {"min": 30, "max": 90, "default_aspect": "16:9"},
    "instagram": {"min": 7, "max": 15, "default_aspect": "9:16"},
}

STYLE_HINTS = {
    "documentary": ("Documentary style, 35mm film grain, natural lighting, "
                    "handheld realism, no text overlays on final cut, "
                    "subtle ambient audio."),
    "typographic": ("Bold kinetic typography over minimalist B-roll, clean "
                    "sans-serif type, high contrast, rhythmic cuts timed to a "
                    "beat, single stat per shot."),
    "cinematic": ("Cinematic anamorphic look, shallow depth of field, moody "
                   "color grade, slow pushes, atmospheric score, single strong "
                   "visual punctuating the thesis."),
}


def _log(msg: str) -> None:
    print(f"[falcao-video-gen] {msg}", file=sys.stderr)


def load_env() -> None:
    """Parse KEY=VALUE pairs from $AGUIA_HOME/.env into os.environ."""
    if not ENV_FILE.exists():
        return
    for raw in ENV_FILE.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        key, val = key.strip(), val.strip().strip('"').strip("'")
        os.environ.setdefault(key, val)


def resolve_model(name: str | None) -> tuple[str, dict]:
    key = (name or DEFAULT_MODEL).lower().strip()
    # Support exact fal model IDs too, so callers can paste directly.
    if "/" in key:
        return key, {"id": key, "cost_per_sec": 0.25, "max_duration": 10,
                     "aspects": ["9:16", "16:9"]}
    if key not in MODELS:
        _log(f"Unknown model '{name}'. Known: {', '.join(MODELS)}")
        sys.exit(2)
    return key, MODELS[key]


def clamp_duration(duration: int, channel: str, model_cfg: dict) -> int:
    rules = CHANNEL_RULES[channel]
    max_dur = min(rules["max"], model_cfg.get("max_duration", rules["max"]))
    min_dur = rules["min"]
    # Channel minimum may exceed model cap (LinkedIn wants 30s, Veo 3 caps at 8s).
    # In that case fall back to model cap and warn.
    if max_dur < min_dur:
        _log(f"WARNING: model cap {max_dur}s < channel min {min_dur}s — using {max_dur}s.")
        return max_dur
    clamped = max(min_dur, min(max_dur, int(duration)))
    if clamped != duration:
        _log(f"Duration {duration}s snapped to {clamped}s for channel={channel}.")
    return clamped


def resolve_aspect(aspect: str | None, channel: str, model_cfg: dict) -> str:
    a = aspect or CHANNEL_RULES[channel]["default_aspect"]
    if a not in model_cfg.get("aspects", [a]):
        _log(f"WARNING: aspect {a} not listed for this model; passing through anyway.")
    return a


def month_spend_usd(ledger: Path) -> float:
    if not ledger.exists():
        return 0.0
    now = datetime.now(timezone.utc)
    prefix = now.strftime("%Y-%m")
    total = 0.0
    try:
        for line in ledger.read_text().splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            ts = rec.get("ts", "")
            if ts.startswith(prefix):
                total += float(rec.get("cost_estimate", 0.0))
    except OSError as exc:
        _log(f"WARNING: could not read ledger ({exc}); assuming $0 spent.")
    return total


def append_ledger(ledger: Path, record: dict) -> None:
    ledger.parent.mkdir(parents=True, exist_ok=True)
    with ledger.open("a") as fh:
        fh.write(json.dumps(record, separators=(",", ":")) + "\n")


def build_prompt(prompt: str, style: str, duration: int) -> str:
    hint = STYLE_HINTS.get(style, "")
    return f"{prompt.strip()}\n\nStyle: {hint}\nTarget duration: {duration} seconds."


def download(url: str, out: Path) -> None:
    out.parent.mkdir(parents=True, exist_ok=True)
    with urllib.request.urlopen(url, timeout=300) as resp, out.open("wb") as fh:
        while True:
            chunk = resp.read(1 << 20)
            if not chunk:
                break
            fh.write(chunk)


def mock_generate(out: Path, duration: int, aspect: str) -> None:
    """Produce a tiny placeholder MP4 via ffmpeg testsrc so we can exercise
    the full pipeline without a FAL_KEY.
    """
    size = "1080x1920" if aspect == "9:16" else "1920x1080" if aspect == "16:9" else "1080x1080"
    cmd = [
        "ffmpeg", "-y", "-loglevel", "error",
        "-f", "lavfi", "-i", f"testsrc=duration={duration}:size={size}:rate=30",
        "-pix_fmt", "yuv420p",
        "-c:v", "libx264", "-preset", "ultrafast", "-t", str(duration),
        str(out),
    ]
    subprocess.run(cmd, check=True)


def fal_generate(prompt: str, model_id: str, duration: int, aspect: str,
                  out: Path) -> dict:
    """Call fal.ai queue API, wait for completion, download video."""
    import fal_client  # local import so --help works without fal-client

    payload = {
        "prompt": prompt,
        "aspect_ratio": aspect,
        "duration": duration,
    }

    _log(f"submitting to fal.ai model={model_id} duration={duration}s aspect={aspect}")
    handler = fal_client.submit(model_id, arguments=payload)
    request_id = handler.request_id
    _log(f"fal request_id={request_id} — polling until complete")

    result = handler.get()
    # fal outputs vary slightly across models; find a usable URL.
    video = result.get("video") or result.get("output") or {}
    if isinstance(video, dict):
        video_url = video.get("url") or video.get("video_url")
    elif isinstance(video, list) and video:
        first = video[0]
        video_url = first.get("url") if isinstance(first, dict) else first
    else:
        video_url = video if isinstance(video, str) else None

    if not video_url:
        _log(f"ERROR: could not locate video URL in fal response: {json.dumps(result)[:400]}")
        sys.exit(3)

    _log(f"downloading {video_url} -> {out}")
    download(video_url, out)
    return {"request_id": request_id, "video_url": video_url, "raw": result}


def main() -> int:
    parser = argparse.ArgumentParser(
        description="FALCAO text-to-video generator (fal.ai).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=("Models: " + ", ".join(MODELS) +
                "\nChannels: " + ", ".join(CHANNEL_RULES)),
    )
    parser.add_argument("--prompt", required=True, help="Scene description prompt.")
    parser.add_argument("--channel", required=True, choices=sorted(CHANNEL_RULES),
                        help="Target publishing channel (controls duration + aspect).")
    parser.add_argument("--duration", type=int, default=8,
                        help="Target duration in seconds (clamped per channel).")
    parser.add_argument("--style", default="documentary",
                        choices=sorted(STYLE_HINTS),
                        help="Style hint appended to the prompt.")
    parser.add_argument("--aspect", default=None,
                        help="Aspect override, e.g. 9:16. Default per channel.")
    parser.add_argument("--model", default=DEFAULT_MODEL,
                        help=f"Model short name or full fal ID. Default: {DEFAULT_MODEL}.")
    parser.add_argument("--out", required=True, help="Output MP4 path.")
    parser.add_argument("--skip-budget", action="store_true",
                        help="Skip monthly budget enforcement (use with care).")
    args = parser.parse_args()

    load_env()

    # Mock path — used for local tests before Bruno provides FAL_KEY.
    mock = os.environ.get("FALCAO_MOCK") == "1"

    if not mock:
        if not os.environ.get("FAL_KEY"):
            _log("ERROR: FAL_KEY not set. Set FAL_KEY in $AGUIA_HOME/.env "
                 "— get key at https://fal.ai/dashboard/keys")
            return 2
        # fal_client looks for FAL_KEY, FAL_KEY_ID/SECRET, or config.
        os.environ["FAL_KEY"] = os.environ["FAL_KEY"]

    model_key, model_cfg = resolve_model(args.model)
    duration = clamp_duration(args.duration, args.channel, model_cfg)
    aspect = resolve_aspect(args.aspect, args.channel, model_cfg)
    cost_est = round(duration * model_cfg["cost_per_sec"], 4)

    # Budget guard.
    budget = float(os.environ.get("VIDEO_BUDGET_USD", "50"))
    spent = month_spend_usd(LEDGER_PATH)
    if not args.skip_budget and (spent + cost_est) > budget:
        _log(f"ERROR: Budget exceeded — {spent:.2f} + {cost_est:.2f} > {budget:.2f}. "
             "Bruno must raise VIDEO_BUDGET_USD.")
        return 4

    full_prompt = build_prompt(args.prompt, args.style, duration)
    out = Path(args.out).expanduser().resolve()

    started = datetime.now(timezone.utc)
    meta: dict = {}
    if mock:
        _log("FALCAO_MOCK=1 — generating placeholder MP4 via ffmpeg testsrc.")
        mock_generate(out, duration, aspect)
        meta = {"mock": True}
    else:
        meta = fal_generate(full_prompt, model_cfg["id"], duration, aspect, out)

    record = {
        "ts": started.isoformat(timespec="seconds"),
        "channel": args.channel,
        "duration": duration,
        "aspect": aspect,
        "model": model_cfg["id"],
        "model_key": model_key,
        "cost_estimate": cost_est,
        "prompt_preview": args.prompt[:160],
        "style": args.style,
        "output_path": str(out),
        "mock": bool(mock),
        "fal_request_id": meta.get("request_id"),
    }
    append_ledger(LEDGER_PATH, record)

    print(json.dumps({
        "ok": True,
        "path": str(out),
        "duration": duration,
        "cost": cost_est,
        "model": model_cfg["id"],
        "aspect": aspect,
        "mock": bool(mock),
    }))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        _log("interrupted")
        sys.exit(130)

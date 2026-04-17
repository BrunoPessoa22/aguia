#!/usr/bin/env python3
"""
FALCAO caption burner — burns word-level or phrase-level captions into a video
via ffmpeg's drawtext filter.

Timeline format (JSON array):
    [
      {"start": 0.0, "end": 2.0, "text": "R$ 160M league"},
      {"start": 2.0, "end": 4.2, "text": "fan tokens pay"},
      ...
    ]

Style: white bold sans-serif, 3-4px black stroke, bottom-center mobile-safe.

Usage:
    python3 falcao-video-caption.py \\
        --video /tmp/in.mp4 \\
        --timeline /tmp/captions.json \\
        --out /tmp/out.mp4

Deps: ffmpeg (apt-get install ffmpeg), fonts-dejavu (DejaVuSans-Bold.ttf).
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path


FONT_PATH = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"


def _log(msg: str) -> None:
    print(f"[falcao-video-caption] {msg}", file=sys.stderr)


def ensure_deps() -> None:
    """Verify ffmpeg + bold font are available. Attempt apt install if missing."""
    missing = []
    if shutil.which("ffmpeg") is None:
        missing.append("ffmpeg")
    if not Path(FONT_PATH).exists():
        missing.append("fonts-dejavu")
    if missing:
        _log(f"missing deps: {missing}; attempting sudo apt-get install")
        try:
            subprocess.run(
                ["sudo", "apt-get", "install", "-y", "ffmpeg", "fonts-dejavu"],
                check=False,
            )
        except Exception as exc:
            _log(f"apt install failed: {exc}")
    if shutil.which("ffmpeg") is None:
        _log("ERROR: ffmpeg still missing; install manually.")
        sys.exit(2)
    if not Path(FONT_PATH).exists():
        _log(f"ERROR: {FONT_PATH} still missing; install fonts-dejavu.")
        sys.exit(2)


def ffmpeg_escape(text: str) -> str:
    """Escape a string for ffmpeg drawtext's text= option.

    Order matters: backslashes first, then colon, single-quote, comma, percent,
    square brackets.
    """
    replacements = [
        ("\\", "\\\\"),
        (":", "\\:"),
        ("'", "\\'"),
        (",", "\\,"),
        ("%", "\\%"),
        ("[", "\\["),
        ("]", "\\]"),
    ]
    for old, new in replacements:
        text = text.replace(old, new)
    return text


def build_filter(timeline: list[dict]) -> str:
    """Build a single drawtext filter chain, one per caption cue."""
    parts = []
    for cue in timeline:
        start = float(cue["start"])
        end = float(cue["end"])
        if end <= start:
            continue
        text = ffmpeg_escape(str(cue["text"]).strip())
        # mobile-safe bottom-center, generous border width
        draw = (
            "drawtext="
            f"fontfile='{FONT_PATH}':"
            f"text='{text}':"
            "fontcolor=white:"
            "fontsize=h/18:"
            "bordercolor=black@1:"
            "borderw=4:"
            "box=0:"
            "x=(w-text_w)/2:"
            "y=h-text_h-h*0.08:"
            f"enable='between(t,{start:.3f},{end:.3f})'"
        )
        parts.append(draw)
    if not parts:
        return "null"
    return ",".join(parts)


def main() -> int:
    parser = argparse.ArgumentParser(description="Burn captions into a video.")
    parser.add_argument("--video", required=True, help="Input MP4 path.")
    parser.add_argument("--timeline", required=True,
                        help="JSON timeline file with start/end/text cues.")
    parser.add_argument("--out", required=True, help="Output MP4 path.")
    parser.add_argument("--preset", default="medium",
                        help="x264 preset (ultrafast..veryslow).")
    parser.add_argument("--crf", default="20", help="x264 CRF quality (lower = better).")
    args = parser.parse_args()

    ensure_deps()

    video = Path(args.video)
    timeline_path = Path(args.timeline)
    out = Path(args.out).expanduser().resolve()

    if not video.exists():
        _log(f"ERROR: input video not found: {video}")
        return 2
    if not timeline_path.exists():
        _log(f"ERROR: timeline not found: {timeline_path}")
        return 2

    try:
        timeline = json.loads(timeline_path.read_text())
    except json.JSONDecodeError as exc:
        _log(f"ERROR: timeline JSON invalid: {exc}")
        return 2
    if not isinstance(timeline, list):
        _log("ERROR: timeline must be a JSON array.")
        return 2

    vf = build_filter(timeline)
    out.parent.mkdir(parents=True, exist_ok=True)

    cmd = [
        "ffmpeg", "-y", "-loglevel", "error",
        "-i", str(video),
        "-vf", vf,
        "-c:v", "libx264", "-preset", args.preset, "-crf", args.crf,
        "-pix_fmt", "yuv420p",
        "-c:a", "copy",
        str(out),
    ]
    _log(f"burning {len(timeline)} cues into {out.name}")
    try:
        subprocess.run(cmd, check=True)
    except subprocess.CalledProcessError as exc:
        # Retry without copying audio in case input is silent / has no audio
        # track.
        _log(f"ffmpeg failed ({exc.returncode}); retrying without audio copy.")
        cmd_noaudio = [a for a in cmd if a not in ("-c:a", "copy")]
        cmd_noaudio = cmd_noaudio[:-1] + ["-an", cmd_noaudio[-1]]
        subprocess.run(cmd_noaudio, check=True)

    print(json.dumps({"ok": True, "path": str(out), "cues": len(timeline)}))
    return 0


if __name__ == "__main__":
    sys.exit(main())

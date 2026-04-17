#!/usr/bin/env python3
"""FALCAO Clip Pipeline v2 — speaker-tracked 9:16 reframe + diacritic-clean PT captions.

Changes from v1 (addresses Apr 17 Bruno feedback):
  - Speaker detection via OpenCV Haar face cascade (sample 24 frames,
    take median of largest-face center-x, clamp to crop bounds).
  - Diacritic-correct PT-BR captions (reading from external JSON, NOT hardcoded).
  - Noto Sans Bold explicit font family (verified ASS rendering).
  - Standalone CLI: accepts --source, --highlights, --pt-captions, --out.

Usage:
  python3 build_clips_v2.py \\
      --source /path/to/source.mp4 \\
      --highlights /path/to/highlights.json \\
      --pt-captions /path/to/pt-captions.json \\
      --out-dir /path/to/out/ \\
      [--aspect 9x16]

highlights.json schema:
  [{"id": 1, "start_sec": 0, "end_sec": 32, "duration": 32, "hook_pt": "..."}]

pt-captions.json schema:
  {"1": [[0.0, 4.6, "Tem o conceito de cargo,"], ...], "2": [...]}
"""
from __future__ import annotations
import argparse
import json
import statistics
import subprocess
import sys
from pathlib import Path

# -----------------------------------------------------------------------------
# Face detection (speaker tracking)
# -----------------------------------------------------------------------------



# -----------------------------------------------------------------------------
# ASS subtitle builder
# -----------------------------------------------------------------------------

def detect_speaker_timeline(video_path, sample_interval_sec=0.5):
    """Sample faces at sample_interval (default 0.5s). Returns (timeline, (src_w,src_h))
    where timeline = list of (t_sec, cx_or_None) using the LARGEST face per frame.
    """
    try:
        import cv2
    except ImportError:
        return None, None
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        return None, None
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    src_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    src_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    if total < 2:
        cap.release()
        return None, None
    cascade = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
    if cascade.empty():
        cap.release()
        return None, None
    step_frames = max(1, int(fps * sample_interval_sec))
    timeline = []
    for i in range(0, total, step_frames):
        cap.set(cv2.CAP_PROP_POS_FRAMES, i)
        ok, frame = cap.read()
        if not ok:
            continue
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        faces = cascade.detectMultiScale(gray, scaleFactor=1.15, minNeighbors=6, minSize=(140, 140))
        t = i / fps
        if len(faces) == 0:
            timeline.append((t, None))
        else:
            x, y, w, h = max(faces, key=lambda r: r[2] * r[3])
            timeline.append((t, x + w / 2))
    cap.release()
    return timeline, (src_w, src_h)


def build_dynamic_crop_expr(timeline, src_w, crop_w, smoothing_window=3):
    """Timeline -> (ffmpeg_x_expr_or_None, static_x_or_None).
    If dynamic crop is needed, returns (expr, None). If static is fine, returns (None, x).
    """
    # Fill forward-None with last detected cx
    filled = []
    last_cx = None
    for t, cx in timeline:
        if cx is not None:
            last_cx = cx
        filled.append((t, cx if cx is not None else last_cx))
    # Backfill leading Nones
    first_cx = next((cx for _, cx in filled if cx is not None), src_w / 2)
    filled = [(t, cx if cx is not None else first_cx) for t, cx in filled]

    # Smooth with moving average to avoid jitter
    smoothed = []
    for i in range(len(filled)):
        a = max(0, i - smoothing_window // 2)
        b = min(len(filled), i + smoothing_window // 2 + 1)
        window = [filled[j][1] for j in range(a, b)]
        smoothed.append((filled[i][0], sum(window) / len(window)))

    points = []
    for t, cx in smoothed:
        x_off = int(cx - crop_w / 2)
        x_off = max(0, min(src_w - crop_w, x_off))
        points.append((t, x_off))

    # Collapse into segments where x_off changes by more than 30px (avoid micro-jitter)
    segments = []
    prev_x = None
    for t, x in points:
        if prev_x is None or abs(x - prev_x) > 30:
            segments.append((t, x))
            prev_x = x

    if not segments:
        return None, 0
    if len(segments) == 1:
        return None, segments[0][1]

    # Build nested ffmpeg expression: if(lt(t,T1),X1, if(lt(t,T2),X2, ... Xlast))
    # Escape commas with backslash for ffmpeg filter syntax
    expr = str(segments[-1][1])
    for idx in range(len(segments) - 2, -1, -1):
        next_t = segments[idx + 1][0]
        x = segments[idx][1]
        expr = f"if(lt(t\\,{next_t:.2f})\\,{x}\\,{expr})"
    return expr, None



ASS_HEADER = """[Script Info]
ScriptType: v4.00+
PlayResX: {w}
PlayResY: {h}
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Hook,Noto Sans Bold,72,&H00FFFFFF,&H00FFFFFF,&H00000000,&H88000000,1,0,0,0,100,100,0,0,1,5,2,8,60,60,180,1
Style: Caption,Noto Sans Bold,64,&H00FFFFFF,&H00FFFFFF,&H00000000,&H88000000,1,0,0,0,100,100,0,0,1,6,3,2,60,60,260,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""


def _fmt_ts(t: float) -> str:
    h = int(t // 3600); m = int((t % 3600) // 60); s = t % 60
    return f"{h:d}:{m:02d}:{s:05.2f}"


def build_ass(hook_pt: str, duration: float, translations: list, out_path: Path, w: int, h: int):
    lines = [ASS_HEADER.format(w=w, h=h)]
    lines.append(f"Dialogue: 0,{_fmt_ts(0)},{_fmt_ts(duration)},Hook,,0,0,0,,{hook_pt}")
    for a, b, txt in translations:
        a = max(0, min(duration, a))
        b = max(a + 0.05, min(duration, b))
        lines.append(f"Dialogue: 0,{_fmt_ts(a)},{_fmt_ts(b)},Caption,,0,0,0,,{txt}")
    out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


# -----------------------------------------------------------------------------
# ffmpeg helpers
# -----------------------------------------------------------------------------

def run(cmd, **kw):
    print(">>", " ".join(cmd), file=sys.stderr)
    r = subprocess.run(cmd, capture_output=True, text=True, **kw)
    if r.returncode != 0:
        print("STDERR:", r.stderr[-1000:], file=sys.stderr)
        raise RuntimeError(f"cmd failed rc={r.returncode}")
    return r


def probe_size(path: Path) -> tuple[int, int]:
    r = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0",
         "-show_entries", "stream=width,height", "-of", "csv=p=0", str(path)],
        capture_output=True, text=True, check=True,
    )
    w, h = map(int, r.stdout.strip().split(","))
    return w, h


def cut_and_reframe(src: Path, highlight: dict, translations: list, aspect: str,
                    out_dir: Path) -> Path:
    hid = highlight["id"]
    start = highlight["start_sec"]
    end = highlight["end_sec"]
    duration = highlight["duration"]

    clips_dir = out_dir / "clips"; clips_dir.mkdir(parents=True, exist_ok=True)
    final_dir = out_dir / "final"; final_dir.mkdir(parents=True, exist_ok=True)

    raw = clips_dir / f"h{hid}_raw.mp4"
    if not raw.exists():
        run([
            "ffmpeg", "-y", "-loglevel", "error",
            "-ss", f"{start:.3f}", "-to", f"{end:.3f}",
            "-i", str(src),
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
            "-c:a", "aac", "-b:a", "128k",
            str(raw),
        ])

    # Dynamic speaker-tracked crop (handles 2-shot interviews)
    timeline, dims = detect_speaker_timeline(raw, sample_interval_sec=0.5)
    src_w, src_h = probe_size(raw)
    if aspect == "9x16":
        crop_w = int(src_h * 9 / 16); crop_h = src_h
        out_w, out_h = 1080, 1920
    else:
        crop_w = src_h; crop_h = src_h
        out_w, out_h = 1080, 1080

    if timeline and dims:
        expr, static_x = build_dynamic_crop_expr(timeline, src_w, crop_w)
        if expr:
            vf_crop = f"crop={crop_w}:{crop_h}:{expr}:0,scale={out_w}:{out_h}"
            n_segments = expr.count("if(")
            print(f"[v2] h{hid} {aspect} DYNAMIC crop — {n_segments+1} segments", file=sys.stderr)
        elif static_x is not None:
            vf_crop = f"crop={crop_w}:{crop_h}:{static_x}:0,scale={out_w}:{out_h}"
            print(f"[v2] h{hid} {aspect} static crop x={static_x}", file=sys.stderr)
        else:
            x_off = (src_w - crop_w) // 2
            vf_crop = f"crop={crop_w}:{crop_h}:{x_off}:0,scale={out_w}:{out_h}"
    else:
        x_off = (src_w - crop_w) // 2
        vf_crop = f"crop={crop_w}:{crop_h}:{x_off}:0,scale={out_w}:{out_h}"
        print(f"[v2] h{hid} {aspect} fallback center crop (no timeline)", file=sys.stderr)

    out_no_subs = clips_dir / f"h{hid}_{aspect}_nosub.mp4"
    if out_no_subs.exists():
        out_no_subs.unlink()  # always rebuild — crop may have changed
    run([
        "ffmpeg", "-y", "-loglevel", "error",
        "-i", str(raw), "-vf", vf_crop,
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
        "-c:a", "copy", str(out_no_subs),
    ])

    ass_path = clips_dir / f"h{hid}_{aspect}.ass"
    build_ass(highlight["hook_pt"], duration, translations, ass_path, out_w, out_h)

    final_path = final_dir / f"h{hid}_{aspect}_pt.mp4"
    if final_path.exists(): final_path.unlink()
    ass_escaped = str(ass_path).replace(":", r"\:").replace("'", r"\'")
    run([
        "ffmpeg", "-y", "-loglevel", "error",
        "-i", str(out_no_subs), "-vf", f"ass={ass_escaped}",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
        "-c:a", "copy", str(final_path),
    ])
    return final_path


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", required=True)
    ap.add_argument("--highlights", required=True)
    ap.add_argument("--pt-captions", required=True)
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--aspect", default="9x16", choices=["9x16", "1x1", "both"])
    args = ap.parse_args()

    src = Path(args.source)
    highlights = json.loads(Path(args.highlights).read_text())
    captions = json.loads(Path(args.pt_captions).read_text())
    out_dir = Path(args.out_dir)

    aspects = ["9x16", "1x1"] if args.aspect == "both" else [args.aspect]

    results = []
    for h in highlights:
        hid = str(h["id"])
        translations = [tuple(t) for t in captions.get(hid, [])]
        if not translations:
            print(f"[v2] no translations for h{hid}, skipping", file=sys.stderr)
            continue
        for aspect in aspects:
            out = cut_and_reframe(src, h, translations, aspect, out_dir)
            print(f"h{hid} {aspect} -> {out}")
            results.append(str(out))

    print(json.dumps({"ok": True, "outputs": results}))


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Transcribe audio with faster-whisper large-v3 + word-level timestamps.

Accuracy-first transcription for FALCAO podcast clip pipeline.

Changes from v1:
  - Model: large-v3 (was base, ~15% WER -> ~3% WER)
  - compute_type: int8 (CPU) keeps memory <4GB but large-v3 is slow on CPU
    (~5-10x realtime for 166s audio = 13-27min). Acceptable for daily automation.
  - beam_size: 5 (was 1) — better accuracy, minor speed hit
  - vad_filter: True — still skips silence
  - word_timestamps: True — word-level for precise caption chunking

Usage:
  python3 transcribe.py <input_audio> <output_json> [--language en] [--model large-v3]
"""
from __future__ import annotations
import argparse
import json
import os
import sys
import time
from pathlib import Path

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("audio", nargs="?", default="$AGUIA_HOME/agents/falcao/data/video-prototype/v2/source/audio.mp3")
    ap.add_argument("out", nargs="?", default="$AGUIA_HOME/agents/falcao/data/video-prototype/v2/transcripts/transcript.json")
    ap.add_argument("--language", default="en", help="source language (ISO code)")
    ap.add_argument("--model", default="large-v3", help="whisper model size")
    ap.add_argument("--compute", default="int8", help="compute type: int8, int8_float16, float16, float32")
    ap.add_argument("--device", default="cpu", help="cpu or cuda")
    ap.add_argument("--beam-size", type=int, default=5)
    args = ap.parse_args()

    try:
        from faster_whisper import WhisperModel
    except ImportError:
        print("pip install --user --break-system-packages faster-whisper", file=sys.stderr)
        sys.exit(2)

    if not Path(args.audio).exists():
        print(f"ERROR: audio file not found: {args.audio}", file=sys.stderr)
        sys.exit(1)

    t0 = time.time()
    print(f"[{time.strftime('%H:%M:%S')}] Loading {args.model} ({args.compute} on {args.device})...", flush=True)
    model = WhisperModel(args.model, device=args.device, compute_type=args.compute)
    print(f"[{time.strftime('%H:%M:%S')}] Transcribing {args.audio}...", flush=True)

    segments, info = model.transcribe(
        args.audio,
        language=args.language,
        word_timestamps=True,
        beam_size=args.beam_size,
        vad_filter=True,
        condition_on_previous_text=True,  # better coherence
        temperature=[0.0, 0.2, 0.4],      # fallback if no-speech prob high
    )

    out = {
        "language": info.language,
        "duration": info.duration,
        "model": args.model,
        "compute": args.compute,
        "beam_size": args.beam_size,
        "transcribed_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "segments": [],
    }
    total_words = 0
    for seg in segments:
        s = {
            "id": seg.id,
            "start": seg.start,
            "end": seg.end,
            "text": seg.text,
            "words": [
                {"start": w.start, "end": w.end, "word": w.word, "probability": round(w.probability, 3)}
                for w in (seg.words or [])
            ],
        }
        out["segments"].append(s)
        total_words += len(s["words"])
        if seg.id % 5 == 0:
            print(f"[{time.strftime('%H:%M:%S')}] seg {seg.id} t={seg.end:.1f}s", flush=True)

    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(out, indent=2, ensure_ascii=False))
    elapsed = time.time() - t0
    print(f"[{time.strftime('%H:%M:%S')}] Done in {elapsed:.1f}s. {total_words} words across {len(out['segments'])} segments.", flush=True)
    print(f"[{time.strftime('%H:%M:%S')}] Output: {args.out}", flush=True)

if __name__ == "__main__":
    main()

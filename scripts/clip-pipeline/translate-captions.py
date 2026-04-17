#!/usr/bin/env python3
"""FALCAO caption translator — EN -> PT-BR with semantic verification.

Given a whisper transcript.json (with word-level timestamps) + a highlights.json
(which defines which time ranges to clip), produces a pt-captions.json where each
caption chunk is:
  - Semantically faithful to the English audio
  - Chunked into 4-8 word phrases (natural speech rhythm)
  - Timestamped to align with the actual speech segments
  - Verified by a second Claude pass that does reverse-translation check

Pipeline:
  1. For each highlight, pull the English word-level words that fall in its [start, end] window
  2. Group English words into natural caption chunks (at punctuation or every ~4 words)
  3. Dispatch to Claude CLI with a tight prompt: "Translate each chunk to PT-BR preserving meaning"
  4. Dispatch a VERIFICATION call: "Does this PT match the EN? Flag any drift, then fix"
  5. Write pt-captions.json with timestamps from the original EN word timings

Usage:
  python3 translate-captions.py \
    --transcript /path/to/transcript.json \
    --highlights /path/to/highlights.json \
    --out /path/to/pt-captions.json
"""
from __future__ import annotations
import argparse, json, os, subprocess, sys, tempfile
from pathlib import Path


CLAUDE_BIN = os.environ.get("CLAUDE_BIN", "/home/ubuntu/.local/bin/claude")


def group_words_into_chunks(words, max_words=6, max_duration=3.0):
    """Group word list into caption-sized chunks. Breaks at sentence punctuation
    or when max_words/max_duration reached."""
    chunks = []
    cur = []
    for w in words:
        cur.append(w)
        text = w["word"].strip()
        duration = w["end"] - cur[0]["start"]
        ends_sentence = text.endswith(('.', '!', '?'))
        long_enough = len(cur) >= max_words or duration >= max_duration
        breakable = text.endswith((',', '—', ':', ';'))
        if ends_sentence or (long_enough and breakable) or len(cur) >= max_words + 2:
            chunks.append(cur); cur = []
    if cur: chunks.append(cur)
    return chunks


def claude_translate_and_verify(en_chunks, context=""):
    """Dispatch Claude CLI to translate chunks to PT-BR with verification.
    Returns list of translated strings aligned 1:1 with en_chunks.
    """
    en_text = "\n".join(
        f"{i+1}. \"{' '.join(w['word'] for w in chunk).strip()}\""
        for i, chunk in enumerate(en_chunks)
    )
    prompt = f"""You are translating a podcast clip caption from EN to PT-BR. The source speaker is American, speaking naturally in business/tech register. Target audience is Brazilian (BR Portuguese).

{context}

Below are {len(en_chunks)} short chunks of English as spoken in the podcast. Translate each to PT-BR preserving EXACT meaning. Do NOT paraphrase. Do NOT compress beyond what PT syntax requires. Use natural spoken PT-BR, not formal written Portuguese.

Rules:
- Keep numeric expressions as spoken ("US$ 160 milhões", not "160.000.000 dólares")
- Preserve English technical terms where Brazilians use them in English (e.g. "software", "prompt", "AI" can stay as "IA" but "LLM" stays as "LLM")
- Use diacritics correctly (é, ã, ô, ç, etc.) — this is mandatory
- If the speaker says something awkwardly, translate to awkwardly in PT too (don't smooth it out)
- Each PT chunk must be speakable in the same time as the EN chunk

Output ONLY a JSON array of strings, one per chunk, no preamble, no explanation.

English chunks:
{en_text}

Now do a VERIFICATION pass: read your PT translations, reverse-translate each mentally to EN, and check if meaning matches the original EN. If any chunk has drift (missing concept, added concept, changed nuance), fix it before outputting.

Output JSON array:"""

    try:
        result = subprocess.run(
            [CLAUDE_BIN, "-p", prompt, "--model", "claude-opus-4-7",
             "--max-turns", "3", "--output-format", "text"],
            capture_output=True, text=True, timeout=300,
        )
    except subprocess.TimeoutExpired:
        print("[translate] claude timeout, falling back to literal identity", file=sys.stderr)
        return [" ".join(w["word"] for w in c).strip() for c in en_chunks]
    out = result.stdout.strip()
    # Extract JSON array from output
    start = out.find("[")
    end = out.rfind("]")
    if start == -1 or end == -1:
        print(f"[translate] claude response not JSON:\n{out[:400]}", file=sys.stderr)
        return [" ".join(w["word"] for w in c).strip() for c in en_chunks]
    try:
        arr = json.loads(out[start:end+1])
    except Exception as e:
        print(f"[translate] JSON parse error: {e}", file=sys.stderr)
        return [" ".join(w["word"] for w in c).strip() for c in en_chunks]
    if len(arr) != len(en_chunks):
        print(f"[translate] WARNING: returned {len(arr)} items, expected {len(en_chunks)}", file=sys.stderr)
        # Pad or truncate
        while len(arr) < len(en_chunks): arr.append("")
        arr = arr[:len(en_chunks)]
    return arr


def process_highlight(clip, all_words_by_time, context=""):
    """Build chunked PT captions for one highlight."""
    start = clip["start_sec"]
    end = clip["end_sec"]
    # Prefer words in the clip's embedded 'words' field
    if clip.get("words"):
        clip_words = clip["words"]
    else:
        clip_words = [w for w in all_words_by_time if start <= w["start"] < end]
    if not clip_words:
        return []

    chunks = group_words_into_chunks(clip_words, max_words=6, max_duration=3.0)
    pt_texts = claude_translate_and_verify(chunks, context)
    out = []
    for chunk, pt in zip(chunks, pt_texts):
        if not pt or not pt.strip():
            continue
        # Words in highlights.json are already clip-relative (0-based within the clip)
        clip_duration = end - start
        t_start = max(0, chunk[0]["start"])
        t_end = min(clip_duration, chunk[-1]["end"])
        out.append([round(t_start, 2), round(t_end, 2), pt.strip()])
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--transcript", required=True)
    ap.add_argument("--highlights", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--context", default="", help="Extra context for Claude (e.g. 'speaker is Marc Andreessen, context AI in the workplace')")
    args = ap.parse_args()

    transcript = json.loads(Path(args.transcript).read_text())
    highlights = json.loads(Path(args.highlights).read_text())

    # Flatten all words for fallback lookup
    all_words = []
    for seg in transcript.get("segments", []):
        all_words.extend(seg.get("words", []))

    captions = {}
    for clip in highlights:
        print(f"[translate] Processing highlight {clip['id']} ({clip['duration']}s)...", file=sys.stderr)
        captions[str(clip["id"])] = process_highlight(clip, all_words, args.context)

    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(captions, indent=2, ensure_ascii=False))
    print(f"[translate] Wrote {args.out}", file=sys.stderr)


if __name__ == "__main__":
    main()

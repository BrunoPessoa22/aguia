# FALCAO Caption Accuracy Protocol (Apr 17 2026)

**you rule:** captions MUST be accurate — both semantically (what the speaker actually said) and positionally (when they said it). Inaccurate captions make the clip worthless.

## The 3-stage pipeline

### Stage 1 — Transcribe with Whisper large-v3

`transcribe_v2.py` (path: `/home/ubuntu/aguia/agents/falcao/data/video-prototype/v2/transcribe_v2.py`)

| Property | v1 (deprecated) | v2 (mandatory) |
|---|---|---|
| Model | `base` (~74M params) | **`large-v3`** (~1.55B params) |
| WER on tech/business content | ~10-15% | ~3-5% |
| Beam size | 1 | 5 |
| Compute | int8 CPU | int8 CPU (still, but ~5-10x realtime) |
| Word probability included? | No | **Yes** (caller can gate on min prob) |

For a 166s podcast clip, large-v3 int8 on CPU takes ~15-25 min. Acceptable for daily automation.

CLI:
```
python3 transcribe_v2.py audio.mp3 transcript.json --language en --model large-v3
```

### Stage 2 — Translate with verification (Claude Opus 4.7)

`translate-captions.py` (path: `/home/ubuntu/aguia/scripts/translate-captions.py`)

For each highlight, the script:

1. Groups English word-level timestamps into natural caption chunks (4-8 words, break at punctuation or every ~3s)
2. Dispatches to `claude` CLI with an opinionated translation prompt:
   - "Translate preserving EXACT meaning. Do NOT paraphrase. Do NOT compress beyond what PT syntax requires."
   - "Use diacritics correctly. This is mandatory."
   - "Then VERIFY by reverse-translating mentally to EN — if any drift, fix before output."
3. Parses Claude's JSON response, aligns 1:1 with input chunks
4. Outputs `pt-captions.json` with `[t_start, t_end, text]` tuples

### Stage 3 — Burn with Noto Sans Bold (diacritic-safe)

`build_clips_v2.py` uses Noto Sans Bold (not DejaVu) in ASS style. Noto Sans has full Latin Extended coverage so `é ã ô ç í ñ` render correctly.

## Accuracy audit of Apr 17 Andreessen clips

### BEFORE (my hand-paraphrased PT, posted to IG)

| EN (Andreessen verbatim) | My PT | Verdict |
|---|---|---|
| "There's the concept of the job" | "Tem o conceito de cargo" | acceptable |
| "but the job is not actually the atomic unit of what happens in the workplace" | "mas cargo não é a unidade atômica do trabalho" | **compressed — loses "of what happens in the workplace"** |
| "what you want to look at is task loss" | "O que importa é a perda de tarefa" | **drifted — "what matters" vs "what you want to look at"** |

### AFTER (Claude-verified translation)

| EN | PT (verified) | Verdict |
|---|---|---|
| "There's the concept of the job" | "Existe o conceito do trabalho" | literal + natural |
| "but the job is not actually the atomic unit of what happens in the workplace" | "mas o trabalho não é de fato a unidade atômica do que acontece no ambiente de trabalho" | **faithful** — "de fato" preserves "actually" |
| "what you want to look at is task loss" | "o que você quer olhar é perda de tarefas" | **faithful** |

## Pre-publish gate (brain rule)

Before any Reel posts to IG/X/LI, the agent runs this checklist:

- [ ] Whisper model used = `large-v3` (not `base`/`tiny`/`small`)
- [ ] Per-word `probability` >= 0.5 for all visible caption chunks (flag low-confidence words to Bruno)
- [ ] PT captions generated via `translate-captions.py` (not hand-written)
- [ ] Diacritic test: at least one `é`, `ã`, `ô`, `ç` rendered correctly in a preview frame (use ffmpeg to extract, read JPEG)
- [ ] Caption timestamps verified: no negative values, no chunks outside clip duration
- [ ] Spot-check: read 3 random caption chunks out loud at the clip's corresponding timestamp — meaning matches audio?

If any of the above fails, the clip is **quarantined** to `data/clip-quarantine/` and you is notified via Telegram.

## Hard rules locked in `brain/rules.yaml`

```yaml
video:
  captions:
    whisper_model_required: large-v3
    translation_method: llm_verified  # never hand-paraphrase going forward
    min_word_probability: 0.5
    diacritic_check_required: true
    pre_publish_gate: true
    font_family: "Noto Sans Bold"
```

## Known limits

1. **Whisper large-v3 on CPU is slow** — 15-25 min per 3-min audio. Acceptable for daily Reel, not for real-time. If we need faster, switch to GPU (fal.ai Whisper serverless) or use `distil-large-v3` (60% faster, ~1% worse WER).
2. **Claude translation cost** — ~$0.05 per 3-min audio (1 LLM call per highlight, 3 highlights = ~$0.15). Negligible at our volume.
3. **Speaker identity mismatches** — Whisper doesn't know who spoke what line. For 2-speaker interviews, captions don't attribute. Consider pyannote speaker diarization if you wants "MARC: xxx / INTERVIEWER: xxx" labels.
4. **Cultural untranslatables** — some American idioms don't translate well ("fast forward to today"). Claude's verification pass catches most but not all. Review recommended for celebrity-level clips.

## Sync to Obsidian

This article syncs to `~/aguia-wiki/raw/falcao-caption-accuracy.md` and compiles to `~/clawd/wiki/compiled/agents/falcao-caption-accuracy.md` via Second Brain.

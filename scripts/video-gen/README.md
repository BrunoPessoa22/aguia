# Video Generation — fal.ai Seedance / Veo / Kling / Runway

Autonomous short-form video from a text prompt. Lives alongside the podcast clip pipeline — use this when you DON'T have a source video (pure synthesis).

## Scripts

| File | What |
|---|---|
| `falcao-video-gen.py` | Submit prompt to fal.ai, poll, download MP4. Model routing (Seedance Pro default, Veo 3 / Kling 2.1 / Runway Gen-3 fallbacks). Per-channel duration/aspect clamps. Monthly budget guard. |
| `falcao-video-caption.py` | Burn text captions via ffmpeg `drawtext`. DejaVu / Noto Sans Bold, white + 3-4px black stroke, mobile-safe bottom-center. |

## Costs (rough — confirm on fal.ai dashboard)

| Model | Cost/sec | Notes |
|---|---|---|
| Seedance 1.0 Pro | ~$0.25 | Best realism, 10s max, 9:16/16:9/1:1 |
| Kling 2.1 Pro | ~$0.15 | Cheaper, good quality |
| Veo 3 | ~$0.75 | Highest quality, expensive |
| Runway Gen-3 Turbo | ~$0.20 | Fast, 10s max |

Budget: `VIDEO_BUDGET_USD=50` env var (monthly cap). Ledger at `data/video-ledger.jsonl`.

## Setup

```bash
# Get fal.ai key: https://fal.ai/dashboard/keys
echo "FAL_KEY=fal-xxx" >> $AGUIA_HOME/.env

pip install --user --break-system-packages fal-client
sudo apt-get install -y ffmpeg fonts-dejavu-core fonts-noto
```

## Usage

```bash
# Generate pure footage (NO TEXT in prompt — critical rule, see docs/LESSONS.md #6)
python3 falcao-video-gen.py \
  --prompt "Empty tunnel of a football stadium at dusk, single security guard walking through, 35mm photojournalism grain, no text, no logos, no watermarks" \
  --channel instagram \
  --duration 8 \
  --aspect 9:16 \
  --out /tmp/raw.mp4

# Output: {"ok": true, "path": "/tmp/raw.mp4", "duration": 8, "cost": 2.0, "model": "fal-ai/bytedance/seedance/v1/pro/text-to-video"}

# Burn overlay via ffmpeg (separate step — ALWAYS)
cat > /tmp/timeline.json <<EOF
[
  {"start": 4.5, "end": 7.5, "text": "US\$ 160 MILHÕES"}
]
EOF
python3 falcao-video-caption.py --video /tmp/raw.mp4 --timeline /tmp/timeline.json --out /tmp/final.mp4
```

## Per-channel specs enforced

| Channel | Duration clamp | Aspect default | Use case |
|---|---|---|---|
| `x` | 15-45s | 9:16 (vertical preferred in 2026) | Hook + data overlay, silent-viewable |
| `linkedin` | 30-90s | 16:9 or 4:5 | Explainer, selfie-style OK |
| `instagram` | 7-15s | 9:16 | Viral sweet spot, hook in 1.5s |

## Mock mode (no API key needed)

```bash
FALCAO_MOCK=1 python3 falcao-video-gen.py --prompt "..." --channel instagram --duration 8 --aspect 9:16 --out /tmp/test.mp4
```

Generates a test-pattern MP4 matching the requested spec. Useful for CI / testing the rest of the pipeline without burning fal.ai credits.

## The hard-learned rule

**NEVER include readable text in a generative video prompt.** Seedance, Veo, Kling, Runway — all of them render text as garbled letter-soup. See [docs/LESSONS.md #6](../../docs/LESSONS.md) for the full story (we shipped a bad Reel that said "US$ 160 MILHÕES" in the prompt; result read "USF1160S MIUHO'ES").

Always two-stage:
1. Prompt generates pure footage
2. ffmpeg `drawtext` burns the overlay in post

`falcao-video-caption.py` is that second stage. DejaVu Bold and Noto Sans Bold both render diacritics correctly if the input is UTF-8 NFC.

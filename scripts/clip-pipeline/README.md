# Podcast Clip Pipeline — Speaker-Tracked 9:16 Reels

Convert long-form podcast/stream video into short-form Reels with accurate captions and proper speaker framing.

## The problem this solves

You have a 60-minute podcast with 2-4 speakers on camera (alternating shots). You want 30-60s vertical clips for Instagram Reels / X shorts / LinkedIn, with:

1. **Speaker always in frame** (not a bookshelf behind them)
2. **Captions accurate** (what they actually said, not a bad transcription)
3. **Diacritics correct** (é, ã, ô, ç — not stripped)
4. **Time-aligned** to the speech rhythm

Off-the-shelf tools (Opus Clip, Riverside, Submagic) do some of this but often miss #1 on multi-speaker interviews and #2 on non-English content.

## Pipeline

```
 source.mp4                   transcript.json             pt-captions.json
 +----------+                 +-----+-----+-----+        +------+------+------+
 |          |                 |     |     |     |        | 0-4s | Text |time|
 |  video   | -> transcribe_v2| EN  | ts  | prob| ->     +------+------+------+
 |  (1h+)   |  (Whisper       +-----+-----+-----+ translate-captions.py
 |          |   large-v3)                                (Claude verified)
 +----------+                                                     |
      |                                                           v
      |          build_clips_v2.py                          +------------+
      +----------------------------+-------------------->   | Reel 9:16  |
                                   |                        | 7-60s      |
                             YuNet+SFace                    | captions   |
                             face tracking                  | speaker    |
                             (dynamic crop)                 | centered   |
                                                            +------------+
```

## Scripts

| File | What it does | Notes |
|---|---|---|
| `transcribe_v2.py` | Whisper large-v3 int8 CPU, word-level timestamps, word probability | ~0.3x realtime on CPU |
| `translate-captions.py` | Chunk EN word stream, send to Claude Opus 4.7 with "translate, verify by reverse-translating, flag drift" prompt | ~$0.15 per 3-min audio |
| `build_clips_v2.py` | Dynamic speaker-tracked crop via face detection + face matching | Handles 2-shot interviews correctly |

## Setup

```bash
# Whisper
pip install --user --break-system-packages faster-whisper

# OpenCV + face detection deps
pip install --user --break-system-packages opencv-python-headless

# Download face detector + recognizer models
mkdir -p $AGUIA_HOME/agents/your-agent/data/face-models
cd $AGUIA_HOME/agents/your-agent/data/face-models
wget -O yunet.onnx https://github.com/opencv/opencv_zoo/raw/main/models/face_detection_yunet/face_detection_yunet_2023mar.onnx
wget -O sface.onnx https://github.com/opencv/opencv_zoo/raw/main/models/face_recognition_sface/face_recognition_sface_2021dec.onnx

# PT caption font (diacritic-safe)
sudo apt-get install -y fonts-noto fonts-noto-ui-core

# ffmpeg
sudo apt-get install -y ffmpeg
```

## End-to-end example

```bash
# 1. Download source (YouTube — needs cookies, see docs/LESSONS.md #12)
yt-dlp --cookies $HOME/.youtube_cookies.txt -f bestvideo+bestaudio -o source.mp4 <URL>

# 2. Extract audio
ffmpeg -i source.mp4 -q:a 0 -map a source.mp3

# 3. Transcribe
python3 transcribe_v2.py source.mp3 transcript.json --language pt --model large-v3

# 4. Select highlights (manually or via Claude — see example prompt in evolve.py)
# Write highlights.json with: id, start_sec, end_sec, hook_pt, words (filtered)

# 5. Translate & verify (if source is EN and you want PT captions)
python3 translate-captions.py \
  --transcript transcript.json \
  --highlights highlights.json \
  --out pt-captions.json \
  --context "Speaker: X. Topic: Y. Audience: Brazilian executives."

# 6. Build clips
python3 build_clips_v2.py \
  --source source.mp4 \
  --highlights highlights.json \
  --pt-captions pt-captions.json \
  --out-dir ./clips \
  --aspect 9x16
```

Output: `./clips/final/h1_9x16_pt.mp4`, `h2_9x16_pt.mp4`, ...

## Speaker matching (track YOUR face specifically)

For YouTube live streams where you're one of N panelists, you can tell the pipeline to always crop on you:

```bash
# One-time: create reference embedding from a clean face photo
python3 -c "
import cv2, numpy as np
img = cv2.imread('your-face.jpg')
h, w = img.shape[:2]
det = cv2.FaceDetectorYN.create('yunet.onnx', '', (w,h), 0.7, 0.3, 5000)
det.setInputSize((w, h))
_, faces = det.detect(img)
recog = cv2.FaceRecognizerSF.create('sface.onnx', '')
emb = recog.feature(recog.alignCrop(img, faces[0]))
np.save('your-embedding.npy', emb)
"

# Then pass --face-reference when building clips (pending feature — PR welcome)
```

See [docs/LESSONS.md entry #9](../../docs/LESSONS.md) for why the naive Haar approach fails and what the dominant-bucket-mode + dynamic crop expression fix looks like.

## Cost estimate (for automated daily runs)

For a 60-min source processed into 3 Reels:

- Whisper large-v3 CPU: ~20min compute, $0 (local)
- Translation: 3 highlights × 1 Claude call ≈ $0.15
- Clip render: ~2 min ffmpeg, $0 (local)
- Face detection: ~30s, $0 (local)

**Total: ~$0.15 per batch, ~25min wall time.**

If you use GPU (fal.ai Whisper serverless) you cut Whisper to ~1 min at ~$0.10.

# Changelog

## 2026-04-17 — Brain, caption accuracy, video pipeline, media bypass

Major additions distilled from one week of production debugging. 22 non-obvious lessons documented.

### Added

- **`agents/brain/`** — Self-evolving rules subsystem. YAML config + daily collector + weekly analyzer + evolver with git commit trail. Auto-applies safe parameter changes, queues risky ones for Telegram approval. [README](agents/brain/README.md)

- **`scripts/clip-pipeline/`** — Podcast→Reel pipeline with speaker-tracked crop and Claude-verified captions.
  - `transcribe_v2.py` — Whisper `large-v3` (was `base`, ~5x accuracy improvement). Word-level timestamps with probability scores.
  - `translate-captions.py` — Claude Opus 4.7 translation with reverse-verification prompt (catches paraphrase drift).
  - `build_clips_v2.py` — Dynamic crop expression (`crop=w:h:if(lt(t,T1),X1,if(lt(t,T2),X2,...)):0`) that moves the crop window as the camera cuts between speakers. YuNet face detection + SFace embedding matching for known-speaker tracking.

- **`scripts/video-gen/`** — fal.ai text-to-video with budget guard.
  - `falcao-video-gen.py` — Seedance Pro default + Veo 3 / Kling 2.1 / Runway Gen-3 fallbacks, per-channel duration clamp, monthly `VIDEO_BUDGET_USD` cap, ledger at `data/video-ledger.jsonl`.
  - `falcao-video-caption.py` — ffmpeg `drawtext` post-burn (DejaVu/Noto Sans Bold, white + black stroke, mobile-safe).

- **`scripts/publishing/`** — Direct social posting via Playwright (Typefully v2 media bypass).
  - `falcao-x-media-post.py` — X with images/video, cookie session + password fallback.
  - `falcao-linkedin-post.py` — LinkedIn feed post, cascading cookie/token/password auth.

- **`docs/LESSONS.md`** — 22 non-obvious production gotchas with symptom / root cause / fix. The ones that cost us days:
  - Typefully v2 has no media upload — every image posted silently drops (−50% engagement)
  - Never ask text-to-video models to render on-screen text (always ffmpeg post-burn)
  - Haar face detector fails catastrophically on 2-shot interviews — use dominant-bucket mode + dynamic crop
  - YouTube n-challenge breaks yt-dlp — fix with deno + yt-dlp-ejs
  - Cloudflare 403 on Resend API from Python urllib — set a real User-Agent
  - `docker restart` doesn't pick up new image — must stop+rm+run
  - SQLite `CREATE TABLE IF NOT EXISTS` doesn't add columns — always write migrations
  - Agents lie about success — require pre-publish visual gate via Read tool on rendered frame
  - ...and 14 more.

- **`docs/wiki/`** — Channel virality playbooks for 2026 algorithms:
  - `channel-virality-x.md` — X Grok-transformer update, self-reply velocity (150x like), posting windows US+EU+BR overlap
  - `channel-virality-linkedin.md` — Document carousel ER 6.60% (highest format), dwell time as #1 signal, comment 5-7x weight from peers
  - `channel-virality-instagram.md` — Mosseri April 2026 update, Reels 7-15s sweet spot, anti-AI-generic visual rules, Broadcast Channel + Threads amplification
  - `falcao-caption-accuracy.md` — Full 3-stage protocol (Whisper large-v3 → Claude verified translation → Noto Sans Bold ASS render)

### Changed

- **`orchestrator/dispatch.sh`** — v6.1: Opus 4.7 default model (was `sonnet`). Bumped max-turns and timeouts across heavy outreach/research agents (jaguar, cb-sales, gaviao, harpia, carcara, falcao). Added wiki injection paths for brain rules + channel playbooks + caption-accuracy doc. Per-agent model override via `--model claude-opus-4-7` (pinned full ID — avoids alias drift, see [LESSONS #1](docs/LESSONS.md)).

- **`README.md`** — Updated architecture diagram with new integrations and brain subsystem. Expanded Project Structure and What Makes This Different sections.

### Principles reinforced in code

- **Pin model IDs** — never use `opus` / `sonnet` / `haiku` aliases in production cron. Full IDs only.
- **Pre-publish visual gate** — agents must Read the rendered frame before claiming success.
- **Two-stage video** — synthesize footage + burn overlay separately. Never trust a text-to-video model with text.
- **Queue, then send** — outreach drafts go to a queue file first, a rate-limited sender picks them up. Bruno stays in the loop without per-email friction.

---

## 2026-04-11 — Initial open-source release

- Dispatch.sh v6 with memory injection
- Keepalive + responsiveness watchdog + session-health
- 10 agent templates (example, clawfix, second-brain, content-creator, outreach-hunter, health-coach, job-hunter, newsletter, family-ops)
- Telegram + WhatsApp + LinkedIn integrations
- Full install.sh + systemd unit files

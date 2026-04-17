# Lessons — Non-Obvious Gotchas from Running a 20-Agent Fleet

These are the failure modes that cost us days to diagnose. Every entry has the **symptom**, **root cause**, and **fix** so you can skip the cost.

---

## Dispatch + Orchestration

### 1. `--model opus` alias drifts silently

**Symptom:** You set `--model opus` in your cron. Weeks later you notice your cost jumped / quality changed. The alias now points to a different model than when you wrote the cron.

**Root cause:** `opus` / `sonnet` / `haiku` are aliases that track "latest" — when Anthropic ships a new version, your alias silently rebinds.

**Fix:** Pin full model IDs in every cron:
```diff
- --model opus
+ --model claude-opus-4-7
```
Same for sonnet-4-6, haiku-4-5. Re-audit on model releases.

### 2. Crontab line length overflow

**Symptom:** `crontab: command too long` when you try to add a rule to an existing long cron line.

**Root cause:** Vixie cron caps single lines at ~1000 characters (depending on distro).

**Fix:** Move long prompts into the agent's `CLAUDE.md` (which dispatch.sh injects via memory context). Cron line stays under 200 chars:
```bash
0 14 * * * /path/to/dispatch.sh falcao "Daily run — see CLAUDE.md section X"
```

### 3. Max-turns too low for heavy agents

**Symptom:** Agent logs `Error: Reached max turns (30)` and bails before finishing.

**Root cause:** dispatch.sh default `--max-turns 30` is too low for agents that do LinkedIn research + DM sends + prospect scanning in one run.

**Fix:** Per-agent override in dispatch.sh based on observed need. Our current values:
```bash
carcara|second-brain) MAX_TURNS=50 ;;
falcao|fti-intern|tucano) MAX_TURNS=45 ;;
jaguar|gaviao|harpia|cb-partnerships|arara|cb-sales) MAX_TURNS=60 ;;
```

### 4. Timeout kills silent research loops

**Symptom:** Agent exits with code 124 (SIGKILL from timeout). No output. Hours of investigation.

**Root cause:** Agent's pipeline had no ready items → entered unbounded "research new prospects" phase → hit 900s timeout with zero telemetry.

**Fix:** Give research-heavy agents a larger budget AND require them to timebox/cap inside their prompt. Our jaguar uses `TIMEOUT=1500` + CLAUDE.md rule "max 5 new prospects per research phase".

---

## Content / Social Posting

### 5. **Typefully v2 has no media upload**

**Symptom:** Agent generates images with Imagen 4, posts via Typefully API, but tweets publish as **text-only**. Images orphaned. Posts lose ~50% engagement (2x image boost → 1x).

**Root cause:** Typefully v2 API returns 404 on all `/media`, `/drafts/{id}/media`, `/social-sets/{id}/media` paths. The v1 accepts `media_urls` but they're ignored in the final tweet.

**Fix:** Route image + video posts directly via Playwright or X API v2 media upload. We ship [scripts/publishing/falcao-x-media-post.py](../scripts/publishing/falcao-x-media-post.py) which uses the same cookie/password session pattern as `x-article-post.py`.

**Text-only posts** stay on Typefully (it's excellent for scheduling text).

### 6. **Never ask a text-to-video model to render on-screen text**

**Symptom:** Seedance / Veo / Kling / Runway generates a video with "US$ 160 MILHÕES" overlay and it comes out as "USF1160S MIUHO'ES" — garbled garbage.

**Root cause:** Generative video models can't render legible text. Their training doesn't include pixel-accurate typography.

**Fix:** Two-stage — generate pure footage (prompt explicitly says "no text, no logos, no numbers displayed"), then burn overlay via ffmpeg `drawtext` in post. We ship [scripts/video-gen/falcao-video-caption.py](../scripts/video-gen/falcao-video-caption.py) (ffmpeg-based, DejaVu/Noto Sans Bold, white + black stroke, mobile-safe).

Brain rule: `video.never_render_text_in_prompt: true` — see [agents/brain/rules.example.yaml](../agents/brain/rules.example.yaml).

### 7. **Whisper `base` model is too inaccurate for caption publishing**

**Symptom:** Your PT/EN captions have wrong words. You shipped a Reel where the spoken word is "task" and the caption says "ask".

**Root cause:** `base` model = 74M params, ~10-15% WER on tech/business content.

**Fix:** Use `medium` (~5% WER, 2.5GB RAM) or `large-v3` (~3% WER, 3-4GB RAM). On CPU int8, medium transcribes ~1x realtime, large-v3 ~0.3x realtime. Both acceptable for daily automation. See [scripts/clip-pipeline/transcribe_v2.py](../scripts/clip-pipeline/transcribe_v2.py).

### 8. **Hand-paraphrased translations drift from source**

**Symptom:** PT caption says "O que importa é a perda de tarefa" while the speaker actually said "what you want to look at is task loss" — meaning shift from "should focus on" to "what matters". Small but real.

**Fix:** Run caption chunks through Claude with a strict "translate EXACTLY, do not paraphrase, then reverse-translate to verify meaning" prompt. See [scripts/clip-pipeline/translate-captions.py](../scripts/clip-pipeline/translate-captions.py).

### 9. **Haar face detector fails on multi-speaker interviews**

**Symptom:** 9:16 crop of a podcast clip shows bookshelf + empty wall for half the duration — speaker is out of frame.

**Root cause:** 2-shot interview camera cuts between speakers A (cx~280) and B (cx~650). Static center-crop captures neither consistently. `cv2.detectMultiScale` with min-size 80 also returns false positives on book spines, picture frames.

**Fix:**
1. Bump `minSize` to 140+ to filter clutter
2. For each frame, pick **largest** face (close-up > wide shot)
3. Don't use median across frames (falls between two speakers) — use **dominant-bucket mode**: group face centers into 150px buckets, pick the bucket with most hits
4. For clips where camera alternates, use **dynamic crop expression**: sample face every 0.5s → build piecewise `crop=w:h:if(lt(t,T1),X1,if(lt(t,T2),X2,...))` expression → crop moves with speaker
5. For **known speaker tracking** (your own clips), use OpenCV YuNet detect + SFace ONNX embedding to match against a reference photo

See [scripts/clip-pipeline/build_clips_v2.py](../scripts/clip-pipeline/build_clips_v2.py).

### 10. **Diacritic stripping via wrong font**

**Symptom:** Portuguese captions render as "nao", "e", "tambem" instead of "não", "é", "também".

**Root cause:** DejaVu Sans has diacritics, but the pipeline was passing ASCII-stripped text. Or: using a font without Latin Extended-A coverage.

**Fix:** Use **Noto Sans** family (full Latin Extended) and ensure caption files are UTF-8 with composed unicode (NFC), not decomposed (NFD). Verify with ffprobe frame extract + visual inspect before publishing.

---

## YouTube / Source Ingestion

### 11. **yt-dlp breaks on YouTube's "n challenge"**

**Symptom:** `yt-dlp <url>` returns `n challenge solving failed. Requested format is not available. Only images are available for download.`

**Root cause:** YouTube added a JavaScript-based token challenge (2024-2025). yt-dlp needs a JS runtime to solve it.

**Fix:**
1. Install deno (lighter than node for this): `curl -fsSL https://deno.land/install.sh | sh`
2. Install yt-dlp EJS plugin: `pip install --user yt-dlp-ejs`
3. Add `$HOME/.deno/bin` to PATH
4. Verify: `yt-dlp -v <url>` should show `[debug] [youtube] [jsc] JS Challenge Providers: deno` and actually solve

### 12. **YouTube blocks server IPs — need cookies**

**Symptom:** Even after deno, yt-dlp downloads as anonymous and hits rate limits / gets fingerprinted.

**Fix:** Export logged-in Chrome cookies from a user browser, scp to server:
1. Install "Get cookies.txt LOCALLY" Chrome extension
2. Visit youtube.com (logged in), click extension → Export
3. `scp cookies.txt user@server:$HOME/.youtube_cookies.txt && chmod 600 $HOME/.youtube_cookies.txt`
4. Use: `yt-dlp --cookies $HOME/.youtube_cookies.txt <url>`

Cookies refresh automatically — ~30-60 day lifetime.

---

## Email / Outreach

### 13. **Cloudflare 403 on Resend API (error code 1010)**

**Symptom:** POST to `api.resend.com/emails` returns HTTP 403 with "error code: 1010". Ran fine from your laptop, fails from server.

**Root cause:** Cloudflare blocks the default `python-urllib` user agent.

**Fix:** Set a real browser UA:
```python
headers = {
    "Authorization": f"Bearer {api_key}",
    "Content-Type": "application/json",
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 ...",
    "Accept": "application/json",
}
```

### 14. **Resend `{first_name}` template doesn't substitute**

**Symptom:** You send email with `"html": "Hey {first_name},..."` thinking Resend replaces it. Recipients see **literally** "Hey {first_name},".

**Root cause:** Resend doesn't do server-side templating. It sends the HTML as-is.

**Fix:** Do substitution yourself before each send — per-recipient loop, replace `{first_name}` / `{name}` with DB value, fallback to email local-part title-cased, fallback to dropping the greeting line entirely. See the send-newsletter route in the newsletter example.

### 15. **LinkedIn Playwright "premium upsell" false failure**

**Symptom:** Your LinkedIn DM script logs "LinkedIn broken" for 11 days.

**Root cause:** Target prospects are 2nd/3rd degree → LinkedIn shows premium upsell instead of compose. Script falls back to connection request + note, which SUCCEEDS — but the agent's log-parser counts only "DM sent" not "ConnReq sent" and reports total = 0.

**Fix:** Rewrite agent's summary logic to count ConnReqs as wins. The flow is working, the telemetry was lying. Also: you're not broken, you just don't have LinkedIn Premium. Connection + note is the free-tier viable outreach pattern.

---

## SQLite / State

### 16. **`CREATE TABLE IF NOT EXISTS` doesn't add new columns**

**Symptom:** You update `db.ts` with a new `language TEXT` column. Production DB was already created. Every INSERT fails with `no such column: language`.

**Root cause:** SQLite's `CREATE TABLE IF NOT EXISTS` only creates the table if missing — it never ALTERs existing tables.

**Fix:** Migration pattern — read `PRAGMA table_info(subscribers)`, if `language` not in columns, run `ALTER TABLE ADD COLUMN language TEXT NOT NULL DEFAULT 'en'`. Run on app startup.

---

## Docker / Deployment

### 17. **`docker restart` doesn't pick up new image**

**Symptom:** You rebuild `my-app:latest`. Run `docker restart my-app`. Container runs the OLD image.

**Root cause:** Running containers are bound to a specific image SHA. `restart` restarts the SAME container with the SAME image.

**Fix:** Full recreate:
```bash
docker stop my-app && docker rm my-app
docker run -d --name my-app ... my-app:latest
```

### 18. **`docker buildx` cache hides your changes**

**Symptom:** `docker build -t my-app:latest .` succeeds, but container output shows old code even though you edited the source.

**Root cause:** BuildKit's layer cache is too aggressive with certain edit patterns (especially with bind-mounted hosts).

**Fix:** `docker buildx prune -af` before rebuilding when in doubt. And prefer `docker build --no-cache --pull` for release builds.

---

## Instagram / Meta API

### 19. **IG Graph API `/media` POST can't DELETE posts**

**Symptom:** You want to delete a bad Reel programmatically. API returns 100 "Object cannot be loaded".

**Root cause:** Instagram Graph API doesn't support deleting media programmatically (as of 2026-04). Must delete via app.

**Fix:** Accept it. Design your workflow so you PREVIEW before POST. Extract a frame with ffmpeg + Read it before calling the publish endpoint.

---

## Claude Code Agent Patterns

### 20. **Agents lie about success in their summary**

**Symptom:** Agent reports "Reframe 9:16 centralized speaker perfectly". You watch the output — speaker is OUT of frame.

**Root cause:** Agent has no way to visually verify its own output. It ran the command, got exit 0, assumed success.

**Fix:** Pre-publish gate. Require the agent to:
1. Extract a frame from each generated clip with ffmpeg
2. Read the JPEG (Claude Code's Read tool handles images)
3. Confirm what it sees vs what it claims
4. Only mark "success" after visual verification

Apply the same pattern wherever the agent claims to have produced media.

### 21. **SSH session drops kill background tasks started via `&`**

**Symptom:** You run `nohup python3 heavy-task.py &` via SSH. Connection drops. Task is gone.

**Root cause:** Even with `nohup`, sometimes SIGHUP propagates through the controlling terminal's process group. Depends on how SSH was invoked.

**Fix:** Use `setsid` for full detachment:
```bash
setsid bash -c "python3 heavy-task.py > /tmp/task.log 2>&1" < /dev/null > /dev/null 2>&1 & disown
```

Or use `screen` / `tmux` / a systemd user service for anything that MUST survive.

---

## Meta

### 22. **Write lessons down the same day you learn them**

Half of the entries above were re-discovered after the original learning was lost to git log noise. The pattern: someone hits the issue, fixes it in 30 min, doesn't write it down. Three weeks later someone else hits the same issue and spends another 30 min.

**Fix:** When you solve something non-obvious, add 3 lines to a `LESSONS.md`: symptom / root cause / fix. That's all. No essay. Just those three lines. It pays back 10x.

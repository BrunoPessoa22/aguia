# Publishing — Direct Social Post Scripts (Typefully Bypass)

**Why this exists:** Typefully v2 has no media upload endpoint (see [docs/LESSONS.md #5](../../docs/LESSONS.md)). If you try to post images/video via Typefully, they silently drop. Every image goes out as text-only. You lose ~50% of engagement.

These scripts post directly to X and LinkedIn via Playwright using cookies from a logged-in Chrome session — bypass Typefully entirely for media posts. Text-only scheduling can stay on Typefully.

## Scripts

| File | Channel | Auth |
|---|---|---|
| `falcao-x-media-post.py` | X (Twitter) | `$HOME/.aguia_cookies/x/cookies.json` → fallback `$HOME/.aguia_creds/x` (X_EMAIL / X_USER / X_PASS) auto-login |
| `falcao-linkedin-post.py` | LinkedIn | `$HOME/.aguia_cookies/linkedin*.json` cascade → `$HOME/.aguia_cookies/li_at` token → `$HOME/.aguia_creds/linkedin` (LI_EMAIL / LI_PASS) |

## Setup

```bash
pip install --user --break-system-packages playwright
python3 -m playwright install chromium

# Create credentials files
mkdir -p $HOME/.aguia_creds $HOME/.aguia_cookies
chmod 700 $HOME/.aguia_creds

cat > $HOME/.aguia_creds/x <<EOF
X_EMAIL=your@email.com
X_USER=yourhandle
X_PASS=your-password
EOF
chmod 600 $HOME/.aguia_creds/x

cat > $HOME/.aguia_creds/linkedin <<EOF
LI_EMAIL=your@email.com
LI_PASS=your-password
EOF
chmod 600 $HOME/.aguia_creds/linkedin
```

**Credential caveat:** 2FA on either account breaks auto-login. Best path is to manually log in once via the Chrome extension "Get cookies.txt LOCALLY" + scp the cookies to server, then the script uses them.

## Usage

```bash
# X post with image
python3 falcao-x-media-post.py \
  --text "$(cat tweet.txt)" \
  --media /path/to/image.jpg

# X post with video
python3 falcao-x-media-post.py \
  --text "Video hook, self-reply planned" \
  --media /path/to/clip.mp4

# LinkedIn post with image
python3 falcao-linkedin-post.py \
  --text "$(cat li-post.txt)" \
  --media /path/to/image.jpg

# LinkedIn post with video
python3 falcao-linkedin-post.py \
  --text "Founder story, Portuguese audience" \
  --video /path/to/selfie.mp4

# Preview without posting
python3 falcao-x-media-post.py --text "..." --media ... --dry-run
# Screenshots saved to /tmp/x-preview.png or /tmp/li-preview.png
```

## Failure modes + queueing

All scripts fail gracefully. If session expired / login blocked / 2FA hit:

1. Post is saved to `$AGUIA_HOME/agents/<agent>/data/<channel>-media-queue.jsonl`
2. Telegram notify Bruno with reason
3. Exit code 3 (auth failed) or 1 (playwright error)
4. Caller can retry manually via `--force-id` pattern

Typical failure causes:
- LinkedIn: periodic challenge/checkpoint prompts (~once a month). Fix by logging in via browser, re-exporting cookies.
- X: session rotation (~every 2-3 weeks if active). Same fix.

## Instagram

Instagram has its own script in the `aguia-hub` repo: `instagram_client.py` — uses the **official Instagram Business/Creator Graph API** (not Playwright). More reliable if you have a Business or Creator IG account. Long-lived tokens last 60 days and auto-refresh.

Setup: https://developers.facebook.com/docs/instagram-api/getting-started

## X API v2 alternative (paid)

If you want DMs or higher reliability, X API v2 with OAuth 1.0a works:
- `POST statuses/update` with media_ids (from v1.1 /media/upload)
- Scripts: see [`falcao-x-video-post.py`](../../examples/x-api-video/) (placeholder — PR welcome)

Cost: $100/mo Basic tier for ~1500 posts/mo.

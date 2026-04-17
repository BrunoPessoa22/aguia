#!/usr/bin/env python3
"""
FALCAO LinkedIn Poster — Playwright feed post with images/videos.

Uses existing credentials / cookies already managed by aguia v2:
  - $AGUIA_HOME/.linkedin_cookies.json       (primary cookie file)
  - $AGUIA_HOME/.linkedin_cookies_v2         (secondary)
  - $AGUIA_HOME/.linkedin_li_at              (li_at token only)
  - $AGUIA_HOME/.linkedin_creds              (LI_EMAIL, LI_PASS fallback)
  - $AGUIA_HOME/.linkedin_browser_profile    (Chromium persistent profile)

Usage:
  python3 falcao-linkedin-post.py --text "post body" --media /path/img.jpg [/path/img2.jpg] [--video /path/v.mp4]
  python3 falcao-linkedin-post.py --text "text-only post" [--dry-run]
"""
import argparse, asyncio, json, os, sys
from datetime import datetime, timezone
from pathlib import Path

BASE = Path("$AGUIA_HOME")
PROFILE_DIR = BASE / ".linkedin_browser_profile"
COOKIE_FILES = [BASE / ".linkedin_cookies.json", BASE / ".linkedin_cookies_v2", BASE / ".linkedin_cookies_full.json", BASE / ".linkedin_cookies_new"]
LI_AT_FILE = BASE / ".linkedin_li_at"
CREDS_FILE = BASE / ".linkedin_creds"
QUEUE = BASE / "agents/falcao/data/linkedin-queue.jsonl"
LOG = BASE / "shared/logs/falcao-linkedin-post.log"

def log(msg):
    ts = datetime.now(timezone.utc).isoformat()
    line = f"[{ts}] {msg}"
    print(line, flush=True)
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with open(LOG, "a") as f: f.write(line + "\n")

def load_creds():
    if not CREDS_FILE.exists(): return None
    c = {}
    for line in CREDS_FILE.read_text().splitlines():
        if "=" in line and not line.strip().startswith("#"):
            k,v = line.split("=",1); c[k.strip()] = v.strip()
    return c

def queue(text, media, reason):
    QUEUE.parent.mkdir(parents=True, exist_ok=True)
    row = {"ts": datetime.now(timezone.utc).isoformat(), "text": text, "media": [str(m) for m in media], "reason": reason}
    with open(QUEUE, "a") as f: f.write(json.dumps(row, ensure_ascii=False) + "\n")
    log(f"Queued: {reason}")
    try:
        import urllib.request, urllib.parse
        bot = os.environ.get("AGUIA_V2_BOT")
        chat = os.environ.get("BRUNO_DM", "YOUR_TELEGRAM_CHAT_ID")
        if bot:
            msg = f"[FALCAO] LinkedIn post queued\nReason: {reason}\nText: {text[:200]}"
            body = urllib.parse.urlencode({"chat_id": chat, "text": msg}).encode()
            urllib.request.urlopen(urllib.request.Request(f"https://api.telegram.org/bot{bot}/sendMessage", data=body), timeout=8).read()
    except Exception as e: log(f"TG notify failed: {e}")

async def load_any_cookies(ctx):
    # Try JSON cookie files first
    for f in COOKIE_FILES:
        if f.exists():
            try:
                raw = f.read_text().strip()
                if not raw: continue
                data = json.loads(raw)
                if isinstance(data, dict) and "cookies" in data: data = data["cookies"]
                if isinstance(data, list) and len(data) > 0:
                    # Normalize: ensure domain starts with . for linkedin.com
                    for c in data:
                        if "domain" not in c: c["domain"] = ".linkedin.com"
                        if "path" not in c: c["path"] = "/"
                        if c.get("sameSite") not in ("Strict", "Lax", "None"): c["sameSite"] = "Lax"
                    await ctx.add_cookies(data)
                    log(f"Loaded {len(data)} cookies from {f.name}")
                    return True
            except Exception as e:
                log(f"Failed parsing {f.name}: {e}")
    # Fall back to li_at token only
    if LI_AT_FILE.exists():
        li_at = LI_AT_FILE.read_text().strip()
        if li_at:
            await ctx.add_cookies([{
                "name": "li_at", "value": li_at,
                "domain": ".linkedin.com", "path": "/", "sameSite": "Lax",
                "secure": True, "httpOnly": True,
            }])
            log(f"Loaded li_at token")
            return True
    return False

async def login_with_password(page, email, password):
    log("Navigating to LinkedIn login...")
    await page.goto("https://www.linkedin.com/login", wait_until="domcontentloaded", timeout=45000)
    await page.wait_for_timeout(3000)
    em = page.locator('input#username').first
    if await em.count() == 0:
        log("ERROR: LI username field not found"); return False
    await em.fill(email); await page.wait_for_timeout(300)
    pw = page.locator('input#password').first
    await pw.fill(password); await page.wait_for_timeout(300)
    btn = page.locator('button[type="submit"]').first
    await btn.click()
    await page.wait_for_timeout(6000)
    # Check for challenge / captcha / OTP
    if "checkpoint" in page.url or "challenge" in page.url:
        log(f"LI LOGIN BLOCKED: {page.url} (challenge/OTP). Bruno must refresh session.")
        return False
    return "feed" in page.url or "linkedin.com/in" in page.url or page.locator('div.scaffold-layout').count() > 0

async def save_cookies(ctx):
    try:
        cookies = await ctx.cookies()
        (BASE / ".linkedin_cookies.json").write_text(json.dumps(cookies, indent=2))
        log(f"Saved {len(cookies)} cookies -> .linkedin_cookies.json")
    except Exception as e: log(f"Cookie save failed: {e}")

async def do_post(text, media_paths, dry_run):
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        log("playwright missing"); return 4

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, args=["--disable-blink-features=AutomationControlled","--no-sandbox"])
        ctx = await browser.new_context(
            viewport={"width": 1366, "height": 900},
            user_agent="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0 Safari/537.36",
        )
        cookies_ok = await load_any_cookies(ctx)
        page = await ctx.new_page()
        try:
            await page.goto("https://www.linkedin.com/feed/", wait_until="domcontentloaded", timeout=30000)
            await page.wait_for_timeout(3500)

            if "login" in page.url or "authwall" in page.url:
                log("Session invalid — attempting password login")
                creds = load_creds()
                if not creds or not creds.get("LI_PASS"):
                    queue(text, media_paths, "no .linkedin_creds found"); await browser.close(); return 3
                ok = await login_with_password(page, creds.get("LI_EMAIL"), creds["LI_PASS"])
                if not ok:
                    queue(text, media_paths, "LI login failed/checkpoint"); await browser.close(); return 3
                await save_cookies(ctx)
                await page.goto("https://www.linkedin.com/feed/", wait_until="domcontentloaded", timeout=30000)
                await page.wait_for_timeout(3500)

            # Click "Start a post"
            start = page.locator('button:has-text("Start a post"), button:has-text("Começar a publicação"), button.share-box-feed-entry__trigger').first
            await start.wait_for(timeout=10000)
            await start.click()
            await page.wait_for_timeout(2000)

            # Fill text in composer editor
            editor = page.locator('div.ql-editor, div[role="textbox"][contenteditable="true"]').first
            await editor.wait_for(timeout=10000)
            await editor.click()
            await page.keyboard.type(text, delay=6)
            await page.wait_for_timeout(800)

            # Attach media
            if media_paths:
                # Click "Add a photo/video" button — opens OS file picker
                # We intercept via setInputFiles on hidden input
                for m in media_paths:
                    is_vid = str(m).lower().endswith(('.mp4','.mov','.webm'))
                    # Open the media menu
                    media_btn = page.locator('button[aria-label*="photo"], button[aria-label*="foto"], button[aria-label*="video"], button[aria-label*="vídeo"]').first
                    if await media_btn.count() > 0:
                        try: await media_btn.click()
                        except Exception: pass
                        await page.wait_for_timeout(800)
                    fi = page.locator('input[type="file"]').first
                    try:
                        await fi.set_input_files(str(m))
                    except Exception as e:
                        log(f"file input error: {e}")
                        queue(text, media_paths, f"file input error: {e}")
                        await browser.close(); return 1
                    await page.wait_for_timeout(8000 if is_vid else 4000)
                    # If LI opens editor dialog, click "Done"/"Concluir"
                    done = page.locator('button:has-text("Done"), button:has-text("Concluir"), button:has-text("Próximo"), button:has-text("Next")').first
                    if await done.count() > 0:
                        try: await done.click()
                        except Exception: pass
                        await page.wait_for_timeout(1500)

            if dry_run:
                await page.screenshot(path="/tmp/li-preview.png")
                log("DRY RUN — preview at /tmp/li-preview.png"); await browser.close(); return 0

            # Post button: "Post" / "Publicar"
            pb = page.locator('button:has-text("Post"):not([aria-disabled="true"]), button:has-text("Publicar"):not([aria-disabled="true"])').first
            for _ in range(15):
                if await pb.count() > 0:
                    disabled = await pb.get_attribute("aria-disabled")
                    if disabled != "true": break
                await page.wait_for_timeout(1000)
            await pb.click()
            await page.wait_for_timeout(6000)
            await save_cookies(ctx)
            log(f"LI posted: {text[:80]}")
            await browser.close(); return 0
        except Exception as e:
            try: await page.screenshot(path="/tmp/li-error.png")
            except Exception: pass
            await browser.close()
            log(f"LI error: {e}")
            queue(text, media_paths, f"playwright error: {e}")
            return 1

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--text", required=True)
    ap.add_argument("--media", nargs="*", default=[])
    ap.add_argument("--video", default=None, help="alias for --media with single video")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    media = [Path(m) for m in args.media]
    if args.video: media.append(Path(args.video))
    for m in media:
        if not m.exists(): log(f"Media not found: {m}"); sys.exit(2)
    sys.exit(asyncio.run(do_post(args.text, media, args.dry_run)))

if __name__ == "__main__":
    main()

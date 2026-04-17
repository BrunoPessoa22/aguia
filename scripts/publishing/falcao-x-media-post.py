#!/usr/bin/env python3
"""
FALCAO X Media Poster v2 — Playwright X post with images/videos, full auth flow.

Uses same credential/cookie pattern as x-article-post.py:
  - $AGUIA_HOME/.x_cookies/cookies.json   (session cookies, auto-created)
  - $AGUIA_HOME/.x_creds                  (X_EMAIL, X_USER, X_PASS for fallback login)

Usage:
  python3 falcao-x-media-post.py --text "tweet body" --media /path/img1.jpg [/path/img2.jpg]
  python3 falcao-x-media-post.py --text "tweet" --media /path/video.mp4 [--dry-run]

Exit codes: 0 success | 1 playwright error (queued) | 2 bad args | 3 auth failed (queued) | 4 playwright not installed
"""
import argparse, asyncio, json, os, sys
from datetime import datetime, timezone
from pathlib import Path

BASE = Path("$AGUIA_HOME")
COOKIES_DIR = BASE / ".x_cookies"
COOKIE_FILE = COOKIES_DIR / "cookies.json"
CREDS_FILE = BASE / ".x_creds"
QUEUE = BASE / "agents/falcao/data/x-media-queue.jsonl"
LOG = BASE / "shared/logs/falcao-x-media.log"

def log(msg):
    ts = datetime.now(timezone.utc).isoformat()
    line = f"[{ts}] {msg}"
    print(line, flush=True)
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with open(LOG, "a") as f: f.write(line + "\n")

def load_creds():
    if not CREDS_FILE.exists(): return None
    creds = {}
    for line in CREDS_FILE.read_text().splitlines():
        if "=" in line and not line.strip().startswith("#"):
            k, v = line.split("=", 1); creds[k.strip()] = v.strip()
    return creds

def queue_for_manual(text, media, reason):
    QUEUE.parent.mkdir(parents=True, exist_ok=True)
    row = {"ts": datetime.now(timezone.utc).isoformat(), "text": text,
           "media": [str(m) for m in media], "reason": reason}
    with open(QUEUE, "a") as f: f.write(json.dumps(row, ensure_ascii=False) + "\n")
    log(f"Queued for manual post: {reason}")
    try:
        import urllib.request, urllib.parse
        bot = os.environ.get("AGUIA_V2_BOT")
        chat = os.environ.get("BRUNO_DM", "YOUR_TELEGRAM_CHAT_ID")
        if bot:
            msg = f"[FALCAO] X media post queued\nReason: {reason}\nText: {text[:200]}\nMedia: {len(media)} file(s)"
            body = urllib.parse.urlencode({"chat_id": chat, "text": msg}).encode()
            urllib.request.urlopen(urllib.request.Request(
                f"https://api.telegram.org/bot{bot}/sendMessage", data=body), timeout=8).read()
    except Exception as e: log(f"Telegram notify failed: {e}")

async def login_with_password(page, email, password, username=None):
    log("Navigating to X login...")
    await page.goto("https://x.com/i/flow/login", wait_until="domcontentloaded", timeout=45000)
    await page.wait_for_timeout(4000)
    try:
        await page.wait_for_selector('input[name="text"], input[autocomplete="username"]', timeout=15000)
    except Exception: pass
    em = page.locator('input[name="text"], input[autocomplete="username"]').first
    if await em.count() == 0:
        log("ERROR: username field not found"); return False
    await em.fill(email); await page.wait_for_timeout(500)
    nb = page.locator('button:has-text("Next"), [data-testid="LoginForm_Login_Button"]').first
    if await nb.count() > 0: await nb.click()
    else: await page.keyboard.press("Enter")
    await page.wait_for_timeout(3000)
    unusual = page.locator('input[data-testid="ocfEnterTextTextInput"]').first
    if await unusual.count() > 0:
        log("Unusual login prompt — entering username")
        await unusual.fill(username or email.split("@")[0])
        nb2 = page.locator('button:has-text("Next")').first
        if await nb2.count() > 0: await nb2.click()
        else: await page.keyboard.press("Enter")
        await page.wait_for_timeout(3000)
    try: await page.wait_for_selector('input[name="password"], input[type="password"]', timeout=10000)
    except Exception: pass
    pw = page.locator('input[name="password"], input[type="password"]').first
    if await pw.count() == 0:
        log("ERROR: password field not found"); return False
    await pw.fill(password); await page.wait_for_timeout(500)
    lb = page.locator('button[data-testid="LoginForm_Login_Button"], button:has-text("Log in")').first
    if await lb.count() > 0: await lb.click()
    else: await page.keyboard.press("Enter")
    await page.wait_for_timeout(6000)
    try:
        await page.wait_for_selector('[data-testid="SideNav_AccountSwitcher_Button"], [data-testid="AppTabBar_Home_Link"], [aria-label="Home"]', timeout=10000)
        log("Login successful"); return True
    except Exception:
        return "login" not in page.url

async def save_cookies(ctx):
    COOKIES_DIR.mkdir(parents=True, exist_ok=True)
    cookies = await ctx.cookies()
    COOKIE_FILE.write_text(json.dumps(cookies, indent=2))
    log(f"Saved {len(cookies)} cookies -> {COOKIE_FILE}")

async def load_cookies(ctx):
    if not COOKIE_FILE.exists(): return False
    try:
        cookies = json.loads(COOKIE_FILE.read_text())
        await ctx.add_cookies(cookies)
        log(f"Loaded {len(cookies)} cookies from {COOKIE_FILE}")
        return True
    except Exception as e:
        log(f"Cookie load failed: {e}"); return False

async def do_post(text, media_paths, dry_run):
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        log("playwright missing. Install: pip install --user --break-system-packages playwright && python3 -m playwright install chromium")
        return 4

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, args=["--disable-blink-features=AutomationControlled", "--no-sandbox"])
        ctx = await browser.new_context(
            viewport={"width": 1280, "height": 900},
            user_agent="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0 Safari/537.36",
        )
        cookies_ok = await load_cookies(ctx)
        page = await ctx.new_page()
        try:
            await page.goto("https://x.com/compose/post", wait_until="domcontentloaded", timeout=30000)
            await page.wait_for_timeout(2500)

            # If redirected to login, fall back to password
            if "login" in page.url or "flow/login" in page.url:
                log("Session invalid — logging in with password")
                creds = load_creds()
                if not creds or not creds.get("X_PASS"):
                    queue_for_manual(text, media_paths, "no .x_creds found")
                    await browser.close(); return 3
                login_ok = await login_with_password(
                    page, creds.get("X_EMAIL") or creds.get("X_USER"),
                    creds["X_PASS"], creds.get("X_USER"))
                if not login_ok:
                    queue_for_manual(text, media_paths, "login failed (check 2FA or creds)")
                    await browser.close(); return 3
                await save_cookies(ctx)
                await page.goto("https://x.com/compose/post", wait_until="domcontentloaded", timeout=30000)
                await page.wait_for_timeout(3000)

            composer = page.locator('div[role="textbox"][data-testid="tweetTextarea_0"]').first
            await composer.wait_for(timeout=10000)
            await composer.click()
            await page.keyboard.type(text, delay=8)
            await page.wait_for_timeout(800)

            if media_paths:
                file_input = page.locator('input[data-testid="fileInput"]').first
                await file_input.set_input_files([str(m) for m in media_paths])
                # wait for upload: videos take longer
                wait_ms = 4000 + (12000 if any(str(m).lower().endswith(('.mp4','.mov','.webm')) for m in media_paths) else 1500 * len(media_paths))
                await page.wait_for_timeout(wait_ms)

            if dry_run:
                await page.screenshot(path="/tmp/x-preview.png")
                log("DRY RUN — preview at /tmp/x-preview.png"); await browser.close(); return 0

            btn = page.locator('button[data-testid="tweetButton"], button[data-testid="tweetButtonInline"]').first
            # Wait until not disabled
            for _ in range(15):
                disabled = await btn.get_attribute("aria-disabled") or await btn.get_attribute("disabled")
                if disabled not in ("true", ""): break
                await page.wait_for_timeout(1000)
            await btn.click()
            await page.wait_for_timeout(6000)
            # Save cookies after successful action
            await save_cookies(ctx)
            log(f"Posted: {text[:80]}")
            await browser.close(); return 0
        except Exception as e:
            try: await page.screenshot(path="/tmp/x-error.png")
            except Exception: pass
            await browser.close()
            log(f"Playwright error: {e}")
            queue_for_manual(text, media_paths, f"playwright error: {e}")
            return 1

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--text", required=True)
    ap.add_argument("--media", nargs="*", default=[])
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    media = [Path(m) for m in args.media]
    for m in media:
        if not m.exists(): log(f"Media not found: {m}"); sys.exit(2)
    sys.exit(asyncio.run(do_post(args.text, media, args.dry_run)))

if __name__ == "__main__":
    main()

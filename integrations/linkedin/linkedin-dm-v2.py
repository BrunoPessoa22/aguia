#!/usr/bin/env python3
"""
LinkedIn DM Sender v2 -- Cookie-based ephemeral contexts.

NO persistent Chrome profile. Uses saved cookies injected into fresh contexts.
NO URN extraction. Uses LinkedIn's messaging search (like a human).

Cookie lifecycle:
  1. login_and_save_cookies() -- Playwright login, saves 24+ cookies to JSON
  2. Each DM run injects cookies into a fresh ephemeral context
  3. Daily cron refreshes cookies via linkedin-session-check.sh

Usage:
  python3 linkedin-dm-v2.py --to "First Last" --message "Hello!" [--dry-run]
  python3 linkedin-dm-v2.py --to "linkedin.com/in/slug" --message "Hello!"
  python3 linkedin-dm-v2.py --batch /path/to/leads.json [--dry-run]
  python3 linkedin-dm-v2.py --login  # Force re-login and save cookies
  python3 linkedin-dm-v2.py --check  # Verify session health

Requires:
  pip install playwright
  playwright install chromium
"""
import argparse, asyncio, json, random, sys, time, re
from datetime import datetime
from pathlib import Path

# ============================================================================
# Config -- paths and credentials from environment / config files
# ============================================================================
COOKIE_FILE = Path(os.path.expanduser("~/aguia/.linkedin_cookies.json")) if 'os' in dir() else Path("~/.linkedin_cookies.json").expanduser()
CREDS_FILE = Path(os.path.expanduser("~/aguia/.linkedin_creds")) if 'os' in dir() else Path("~/.linkedin_creds").expanduser()
LOG_FILE = Path(os.path.expanduser("~/aguia/shared/logs/linkedin-dm-send.log")) if 'os' in dir() else Path("~/aguia/shared/logs/linkedin-dm-send.log").expanduser()
MAX_DMS_PER_RUN = 5

import os
COOKIE_FILE = Path(os.environ.get("LI_COOKIE_FILE", os.path.expanduser("~/aguia/.linkedin_cookies.json")))
CREDS_FILE = Path(os.environ.get("LI_CREDS_FILE", os.path.expanduser("~/aguia/.linkedin_creds")))
CHROME_BIN = os.environ.get("CHROME_BIN", "/usr/bin/google-chrome-stable")
LOG_FILE = Path(os.path.expanduser("~/aguia/shared/logs/linkedin-dm-send.log"))


def log(msg):
    ts = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line, flush=True)
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(LOG_FILE, "a") as f:
        f.write(line + "\n")


def load_creds():
    """Load credentials from file. Format: KEY=VALUE per line.
    Or use environment variables LI_EMAIL and LI_PASS."""
    creds = {
        "LI_EMAIL": os.environ.get("LI_EMAIL", ""),
        "LI_PASS": os.environ.get("LI_PASS", ""),
    }
    try:
        for line in CREDS_FILE.read_text().splitlines():
            if "=" in line:
                k, v = line.strip().split("=", 1)
                creds[k] = v
    except Exception:
        pass
    return creds


async def _launch_browser(playwright):
    return await playwright.chromium.launch(
        headless=True,
        args=["--no-sandbox", "--disable-setuid-sandbox", "--disable-gpu",
              "--disable-blink-features=AutomationControlled"],
        executable_path=CHROME_BIN if Path(CHROME_BIN).exists() else None,
    )


async def _new_context(browser, cookies=None):
    ctx = await browser.new_context(
        user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                   "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
        viewport={"width": 1280, "height": 900},
        locale="en-US",
    )
    if cookies:
        await ctx.add_cookies(cookies)
    return ctx


async def login_and_save_cookies():
    """Fresh login, save all cookies. Called by --login or when cookies expire."""
    from playwright.async_api import async_playwright
    creds = load_creds()

    async with async_playwright() as p:
        browser = await _launch_browser(p)
        ctx = await _new_context(browser)
        page = await ctx.new_page()

        await page.goto("https://www.linkedin.com/login", wait_until="networkidle", timeout=30000)
        await page.wait_for_timeout(3000)

        # Dismiss cookie consent
        for sel in ["button:has-text('Accept')", "button:has-text('Reject')"]:
            try:
                await page.locator(sel).first.click(timeout=3000)
                await page.wait_for_timeout(1000)
                break
            except Exception:
                continue

        await page.fill("#username", creds.get("LI_EMAIL", ""))
        await page.fill("#password", creds.get("LI_PASS", ""))
        await page.click("button[type=submit]")
        await page.wait_for_timeout(10000)

        url = page.url
        if "feed" in url or "messaging" in url:
            cookies = await ctx.cookies()
            COOKIE_FILE.write_text(json.dumps(cookies))
            log(f"Login OK. Saved {len(cookies)} cookies.")
            await browser.close()
            return True
        elif "checkpoint" in url or "challenge" in url:
            log("CHALLENGE -- need manual intervention")
            await page.screenshot(path="/tmp/li-challenge.png")
            await browser.close()
            return False
        else:
            log(f"Login failed: {url}")
            await browser.close()
            return False


async def ensure_session(page):
    """Navigate to messaging. If cookies expired, re-login automatically."""
    await page.goto("https://www.linkedin.com/messaging/",
                    wait_until="domcontentloaded", timeout=30000)
    await page.wait_for_timeout(3000)

    if "/messaging" in page.url and "/login" not in page.url:
        log("  Session OK")
        return True

    log("  Cookies expired -- re-logging in")
    ok = await login_and_save_cookies()
    if not ok:
        return False

    # Reload with fresh cookies
    fresh = json.loads(COOKIE_FILE.read_text())
    await page.context.add_cookies(fresh)
    await page.goto("https://www.linkedin.com/messaging/",
                    wait_until="domcontentloaded", timeout=30000)
    await page.wait_for_timeout(3000)
    return "/messaging" in page.url and "/login" not in page.url


async def send_dm(page, recipient_name, message, profile_url=None, dry_run=False):
    """Send DM via profile page Message button + overlay.

    Flow: profile page -> click Message -> type in overlay -> send.
    Accepts profile_url (linkedin.com/in/slug) or searches by name.
    """
    log(f"  Target: {recipient_name}")

    # Step 1: Navigate to the profile page
    if profile_url and "/in/" in profile_url:
        url = profile_url if profile_url.startswith("http") else "https://www.linkedin.com" + profile_url
        await page.goto(url, wait_until="domcontentloaded", timeout=30000)
    else:
        search_url = f"https://www.linkedin.com/search/results/people/?keywords={recipient_name.replace(' ', '%20')}"
        await page.goto(search_url, wait_until="domcontentloaded", timeout=30000)
        await page.wait_for_timeout(4000)

        first_result = page.locator("a.app-aware-link[href*='/in/'] span[dir='ltr']").first
        try:
            await first_result.click(timeout=8000)
            await page.wait_for_timeout(4000)
            log(f"  Found profile via search: {page.url[:60]}")
        except Exception:
            log(f"  ERROR: Could not find profile for '{recipient_name}'")
            return False

    await page.wait_for_timeout(3000)

    # Step 2: Click the Message button
    msg_btn = page.locator("button:visible:has-text('Message')").first
    try:
        await msg_btn.click(timeout=8000)
        log("  Clicked Message button")
    except Exception:
        log("  ERROR: Message button not found/clickable")
        return False

    await page.wait_for_timeout(4000)

    # Step 3: Find the message textbox in the overlay
    textbox = None
    for attempt in range(3):
        for sel in [
            "div[role='textbox'][contenteditable='true']",
            "[contenteditable='true'][role='textbox']",
            ".msg-form__contenteditable[contenteditable='true']",
            "div[aria-label*='Write a message' i][contenteditable='true']",
            "div[aria-label*='message' i][contenteditable='true']",
        ]:
            try:
                el = page.locator(sel).first
                if await el.count() > 0 and await el.is_visible():
                    textbox = el
                    break
            except Exception:
                continue
        if textbox:
            break
        log(f"  Textbox not found yet (attempt {attempt+1}/3), waiting...")
        await page.wait_for_timeout(3000)

    if not textbox:
        log("  ERROR: Message textbox not found after retries")
        return False

    if dry_run:
        log(f"  DRY-RUN: Would send {len(message)} chars")
        return True

    # Step 4: Type the message
    await textbox.click()
    await page.wait_for_timeout(300)
    await page.keyboard.type(message, delay=random.randint(15, 40))
    await page.wait_for_timeout(1500)

    # Step 5: Send
    send_btn = page.locator("button.msg-form__send-button, button[aria-label='Send' i], button[type='submit']").first
    try:
        await send_btn.wait_for(timeout=5000)
        disabled = await send_btn.get_attribute("disabled")
        if disabled is None:
            await send_btn.click()
            log("  Clicked send button")
        else:
            await page.keyboard.press("Enter")
            log("  Pressed Enter (button disabled)")
    except Exception:
        await page.keyboard.press("Enter")
        log("  Pressed Enter (no send button)")

    await page.wait_for_timeout(3000)

    # Verify: textbox should be empty
    try:
        content = await textbox.inner_text()
        if not content.strip():
            log("  SUCCESS: DM sent")
        else:
            log("  WARNING: Textbox not cleared -- may not have sent")
    except Exception:
        log("  SUCCESS: DM likely sent")
    return True


def parse_recipient(to_value):
    m = re.search(r"/in/([^/?#]+)", to_value)
    if m:
        slug = m.group(1)
        slug = re.sub(r'-[a-f0-9]{6,}$', '', slug)
        return slug.replace("-", " ").title()
    return to_value


async def main():
    parser = argparse.ArgumentParser(description="LinkedIn DM Sender v2")
    parser.add_argument("--to", help="Recipient name or LinkedIn URL")
    parser.add_argument("--message", help="Message text")
    parser.add_argument("--batch", help="JSON leads file")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--login", action="store_true", help="Force re-login")
    parser.add_argument("--check", action="store_true", help="Check session")
    parser.add_argument("--max", type=int, default=MAX_DMS_PER_RUN)
    args = parser.parse_args()

    if args.login:
        ok = await login_and_save_cookies()
        return 0 if ok else 1

    from playwright.async_api import async_playwright

    if not COOKIE_FILE.exists():
        log("No saved cookies -- doing initial login")
        ok = await login_and_save_cookies()
        if not ok:
            return 1

    cookies = json.loads(COOKIE_FILE.read_text())

    async with async_playwright() as p:
        browser = await _launch_browser(p)
        ctx = await _new_context(browser, cookies)
        page = await ctx.new_page()

        ok = await ensure_session(page)
        if not ok:
            log("ERROR: Could not establish session")
            await browser.close()
            return 1

        if args.check:
            log("Session check: OK")
            fresh = await ctx.cookies()
            COOKIE_FILE.write_text(json.dumps(fresh))
            await browser.close()
            return 0

        # Build queue
        queue = []
        if args.batch:
            leads = json.loads(Path(args.batch).read_text())
            queue = [l for l in leads if l.get("status") == "pending_dm" and l.get("name")][:args.max]
        elif args.to and args.message:
            name = parse_recipient(args.to)
            url = args.to if "/in/" in args.to else None
            queue = [{"name": name, "dm_message": args.message, "profile_url": url}]

        if not queue:
            log("No pending DMs")
            await browser.close()
            return 0

        results = []
        for i, lead in enumerate(queue):
            name = lead.get("name", "Unknown")
            message = lead.get("dm_message", "")
            if not message:
                continue

            log(f"\n[{i+1}/{len(queue)}] DM to: {name}")
            url = lead.get("profile_url")
            ok = await send_dm(page, name, message, profile_url=url, dry_run=args.dry_run)
            results.append({"name": name, "success": ok})

            if i < len(queue) - 1 and not args.dry_run:
                delay = random.randint(45, 90)
                log(f"  Waiting {delay}s...")
                await asyncio.sleep(delay)

        # Save refreshed cookies after the run
        fresh = await ctx.cookies()
        COOKIE_FILE.write_text(json.dumps(fresh))

        await browser.close()

        sent = sum(1 for r in results if r["success"])
        failed = sum(1 for r in results if not r["success"])
        log(f"\n=== SUMMARY: Sent={sent} Failed={failed} ===")
        return 0 if sent > 0 or args.dry_run else 1

if __name__ == "__main__":
    sys.exit(asyncio.run(main()))

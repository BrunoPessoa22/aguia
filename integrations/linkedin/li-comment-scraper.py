#!/usr/bin/env python3
"""
LinkedIn Comment Scraper -- Playwright-based, bypasses API blocks.

Scrapes comments on monitored posts, identifies trigger words,
and auto-sends DMs via the linkedin-dm-v2.py flow.

Runs hourly via cron.

Requires:
  pip install playwright requests
  playwright install chromium
"""
import asyncio
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from playwright.async_api import async_playwright

# ============================================================================
# Config -- customize these for your setup
# ============================================================================
COOKIE_FILE = os.environ.get("LI_COOKIE_FILE", os.path.expanduser("~/aguia/.linkedin_cookies.json"))
CREDS_FILE = os.environ.get("LI_CREDS_FILE", os.path.expanduser("~/aguia/.linkedin_creds"))
CHROME_BIN = os.environ.get("CHROME_BIN", "/usr/bin/google-chrome-stable")
LEADS_FILE = Path(os.environ.get("LEADS_FILE", os.path.expanduser("~/aguia/agents/sales/data/linkedin-leads.json")))
LOG_FILE = Path(os.path.expanduser("~/aguia/shared/logs/li-comment-scraper.log"))
DM_SENDER = os.path.expanduser("~/aguia/integrations/linkedin/linkedin-dm-v2.py")

# Posts to monitor -- add your LinkedIn post URLs here
MONITORED_POSTS = [
    # "https://www.linkedin.com/feed/update/urn:li:share:YOUR_POST_ID",
]

# Trigger words that indicate interest (customize for your use case)
FALLBACK_TRIGGERS = [
    "interested", "yes", "send me", "want", "I want",
    "sign me up", "count me in", "how", "tell me more",
]

MAX_DMS_PER_RUN = 5

# Telegram notification (optional)
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("OWNER_DM", "")


def log(msg):
    ts = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line)
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(LOG_FILE, "a") as f:
        f.write(line + "\n")


def load_creds():
    creds = {
        "LI_EMAIL": os.environ.get("LI_EMAIL", ""),
        "LI_PASS": os.environ.get("LI_PASS", ""),
    }
    creds_path = Path(CREDS_FILE)
    if creds_path.exists():
        for line in creds_path.read_text().splitlines():
            line = line.strip()
            if "=" in line:
                k, v = line.split("=", 1)
                creds[k] = v
    return creds


def load_leads():
    if LEADS_FILE.exists():
        return json.loads(LEADS_FILE.read_text())
    return []


def save_leads(leads):
    LEADS_FILE.parent.mkdir(parents=True, exist_ok=True)
    LEADS_FILE.write_text(json.dumps(leads, indent=2, ensure_ascii=False))


def is_trigger(text: str) -> bool:
    t = text.lower().strip()
    for trigger in FALLBACK_TRIGGERS:
        if re.search(rf'\b{re.escape(trigger)}\b', t):
            return True
    return False


def build_dm(name: str, post_url: str) -> str:
    """Build a personalized DM based on the post they commented on.
    Customize this for your use case."""
    first = name.split()[0] if name else "Hi"
    return (
        f"Hi {first}! Thanks for your comment on my post.\n\n"
        "As promised, here's the resource I mentioned. "
        "Let me know if you have any questions!\n\n"
        "Best regards"
    )


def normalize_li_url(url: str) -> str:
    """Normalize regional LinkedIn subdomains to www."""
    return re.sub(r'https://[a-z]{2}\.linkedin\.com/', 'https://www.linkedin.com/', url)


async def scrape_post_comments(page, post_url: str) -> list:
    """Scrape all visible comments on a LinkedIn post.

    Uses text-based extraction: gets full page text, finds trigger words,
    and pairs them with nearby profile links. Resilient to DOM changes.
    """
    log(f"Scraping: {post_url}")
    await page.goto(post_url, wait_until="domcontentloaded", timeout=30000)
    await page.wait_for_timeout(5000)

    # Scroll to load comments
    for _ in range(3):
        await page.evaluate("window.scrollBy(0, 500)")
        await page.wait_for_timeout(1000)

    # Expand "Load more comments" buttons
    for _ in range(5):
        for sel in [
            "button.comments-comments-list__load-more-comments-button",
            "button:has-text('more comments')",
            "button:has-text('Load')",
        ]:
            try:
                btn = page.locator(sel).first
                if await btn.count() > 0:
                    await btn.click(timeout=3000)
                    await page.wait_for_timeout(1500)
            except Exception:
                continue

    # Get all profile links on the page
    links = await page.evaluate("""() => {
        return Array.from(document.querySelectorAll('a[href*="/in/"]')).map(a => ({
            text: a.innerText.trim(),
            href: a.href
        }));
    }""")

    # Build a name -> URL map
    name_to_url = {}
    for l in links:
        name = l.get("text", "").strip()
        url = l.get("href", "")
        if name and url and len(name) > 2 and len(name) < 60:
            if name not in name_to_url:
                name_to_url[name] = url

    # Get full page text and find trigger words with context
    body = await page.evaluate("document.body.innerText")
    lines = [l.strip() for l in body.split("\n") if l.strip()]

    triggers = set(t.lower() for t in FALLBACK_TRIGGERS)
    results = []
    seen_urls = set()

    for i, line in enumerate(lines):
        if line.lower().strip() not in triggers:
            continue

        # Found a trigger word -- look backwards for the commenter name
        for j in range(i - 1, max(0, i - 6), -1):
            candidate = lines[j].strip()
            if candidate.startswith("\u2022") or candidate in ("1st", "2nd", "3rd"):
                continue
            if candidate.lower() in ("reply", "like", "comment", "repost"):
                continue
            if len(candidate) < 3 or len(candidate) > 60:
                continue

            for known_name, url in name_to_url.items():
                if candidate in known_name or known_name.startswith(candidate):
                    if url not in seen_urls:
                        seen_urls.add(url)
                        results.append({
                            "name": known_name,
                            "profileUrl": url,
                            "text": line.strip(),
                        })
                    break
            else:
                continue
            break

    log(f"  Found {len(results)} comments with triggers")
    return results


def send_telegram(msg: str):
    """Send notification via Telegram."""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return
    import requests
    try:
        requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
            json={"chat_id": TELEGRAM_CHAT_ID, "text": msg},
            timeout=10,
        )
    except Exception as e:
        log(f"Telegram error: {e}")


async def main():
    log("=== LinkedIn Comment Scraper starting ===")

    if not MONITORED_POSTS:
        log("No posts configured in MONITORED_POSTS. Add your LinkedIn post URLs.")
        return 0

    existing_leads = load_leads()
    sent_profiles = {normalize_li_url(l.get("profile_url", "")) for l in existing_leads if l.get("status") == "dm_sent"}

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            executable_path=CHROME_BIN if Path(CHROME_BIN).exists() else None,
            args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-blink-features=AutomationControlled"],
        )

        # Load saved cookies
        cookies = []
        try:
            cookies = json.loads(open(COOKIE_FILE).read())
        except Exception as e:
            log(f"Cannot load cookies: {e}")
            await browser.close()
            return 1

        ctx = await browser.new_context(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
            viewport={"width": 1280, "height": 900},
            locale="en-US",
        )
        await ctx.add_cookies(cookies)
        page = await ctx.new_page()

        # Verify session
        await page.goto("https://www.linkedin.com/feed/", wait_until="domcontentloaded", timeout=30000)
        await page.wait_for_timeout(3000)
        if "/login" in page.url or "authwall" in page.url:
            log("Session expired -- run linkedin-dm-v2.py --login to refresh")
            await browser.close()
            return 1
        log("Session OK")

        new_leads = []
        dms_sent = 0

        for post_url in MONITORED_POSTS:
            comments = await scrape_post_comments(page, post_url)

            for c in comments:
                name = c.get("name", "")
                profile_url = normalize_li_url(c.get("profileUrl", ""))
                text = c.get("text", "")

                if not name or not profile_url:
                    continue

                if not is_trigger(text):
                    continue

                if profile_url in sent_profiles:
                    log(f"  Already messaged: {name}")
                    continue

                log(f"  NEW trigger comment: {name} -- '{text[:50]}'")

                dm = build_dm(name, post_url)
                lead = {
                    "profile_url": profile_url,
                    "name": name,
                    "post_url": post_url,
                    "comment_text": text,
                    "dm_message": dm,
                    "detected_at": datetime.now(timezone.utc).isoformat(),
                    "status": "pending_dm",
                }
                new_leads.append(lead)

                # Auto-send DM
                if dms_sent < MAX_DMS_PER_RUN:
                    log(f"  Sending DM to {name}...")
                    result = subprocess.run(
                        ["python3", DM_SENDER, "--to", profile_url, "--message", dm],
                        capture_output=True, text=True, timeout=120
                    )
                    if result.returncode == 0:
                        lead["status"] = "dm_sent"
                        lead["dm_sent_at"] = datetime.now(timezone.utc).isoformat()
                        dms_sent += 1
                        log(f"  DM sent to {name}")
                    else:
                        log(f"  DM failed for {name}")
                    await page.wait_for_timeout(3000)

        await browser.close()

    if new_leads:
        for lead in new_leads:
            existing_leads.append(lead)
        save_leads(existing_leads)

        sent_count = sum(1 for l in new_leads if l.get("status") == "dm_sent")
        fail_count = len(new_leads) - sent_count

        summary = f"Leads: {len(new_leads)} new comment(s), DMs: {sent_count} sent"
        if fail_count:
            summary += f", {fail_count} failed"
        send_telegram(summary)
        log(f"\nSummary: {sent_count} DMs sent, {fail_count} failed")
    else:
        log("No new trigger comments found")

    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))

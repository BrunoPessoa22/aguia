#!/usr/bin/env python3
"""
FALCAO Brain — Metrics Collector (daily)

Pulls engagement metrics for every post FALCAO has published in the last 24h.
Appends one row per post to performance.jsonl (append-only ledger).

Sources:
  - Typefully v2 /drafts?published=true  (X + LinkedIn metadata we scheduled)
  - X API v2 /tweets/:id (impressions, likes, retweets, replies, bookmarks) [needs X_BEARER]
  - Instagram Graph API /media (reach, saves, likes, comments) [needs IG_ACCESS_TOKEN]
  - LinkedIn — no API for personal post insights; fall back to Typefully's own tracker if available

Writes to $AGUIA_HOME/agents/falcao/brain/performance.jsonl
Format: one JSON object per line with:
  { ts_collected, channel, post_id, published_at, preview, pillar_guess, format,
    metrics: { impressions, engagements, rate, viral }, url }

Run from cron daily at 23:00 UTC.
"""
import os
import sys
import json
import time
import urllib.request
import urllib.parse
import urllib.error
from datetime import datetime, timedelta, timezone
from pathlib import Path

BASE = Path("$AGUIA_HOME")
BRAIN = BASE / "agents" / "falcao" / "brain"
LEDGER = BRAIN / "performance.jsonl"
LOG = BASE / "shared" / "logs" / "falcao-brain-collect.log"

# Load env
for line in (BASE / ".env").read_text().splitlines() if (BASE / ".env").exists() else []:
    if "=" in line and not line.strip().startswith("#"):
        k, _, v = line.partition("=")
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))

TYPEFULLY_KEY = os.environ.get("TYPEFULLY_KEY") or "YOUR_TYPEFULLY_API_KEY"
SOCIAL_SET_ID = os.environ.get("TYPEFULLY_SOCIAL_SET_ID") or "291443"
X_BEARER = os.environ.get("X_BEARER_TOKEN")  # optional
IG_ACCESS = os.environ.get("IG_ACCESS_TOKEN")  # optional
IG_USER_ID = os.environ.get("IG_USER_ID")  # optional

def log(msg):
    ts = datetime.now(timezone.utc).isoformat()
    line = f"[{ts}] {msg}"
    print(line)
    try:
        LOG.parent.mkdir(parents=True, exist_ok=True)
        with open(LOG, "a") as f:
            f.write(line + "\n")
    except Exception:
        pass

def http_json(url, headers=None, timeout=15):
    req = urllib.request.Request(url, headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        log(f"HTTP {e.code} on {url[:80]}: {e.read().decode('utf-8', errors='ignore')[:200]}")
        return None
    except Exception as e:
        log(f"Error on {url[:80]}: {e}")
        return None

def pillar_guess(text):
    """Rough classifier based on CLAUDE.md pillar keywords."""
    t = (text or "").lower()
    scores = {
        "sports_blockchain": sum(k in t for k in ["fan token", "tokeniza", "blockchain", "onchain", "web3 sport"]),
        "sports_tech_ai": sum(k in t for k in ["ai ", "agent", "llm", "automation", "data", "ml", "model"]),
        "sports_business": sum(k in t for k in ["league", "sponsor", "franchise", "revenue", "ipo", "deal", "acquisition", "club", "fund", "investi"]),
        "regulation": sum(k in t for k in ["regulat", "compliance", "cvm", "sec ", "law", "polic"]),
    }
    if max(scores.values(), default=0) == 0:
        return "unclassified"
    return max(scores, key=scores.get)

def collect_typefully():
    """Get last 30 published drafts; we filter to last 24h."""
    url = f"https://api.typefully.com/v2/social-sets/{SOCIAL_SET_ID}/drafts?published=true&limit=30"
    data = http_json(url, headers={"Authorization": f"Bearer {TYPEFULLY_KEY}"})
    if not data:
        return []
    posts = data.get("results", []) or []
    cutoff = datetime.now(timezone.utc) - timedelta(hours=26)
    recent = []
    for p in posts:
        pub = p.get("published_at") or ""
        try:
            pub_dt = datetime.fromisoformat(pub.replace("Z", "+00:00")) if pub else None
        except Exception:
            pub_dt = None
        if not pub_dt or pub_dt < cutoff:
            continue
        preview = p.get("preview", "") or ""
        platforms = []
        if p.get("x_post_enabled"): platforms.append("x")
        if p.get("linkedin_post_enabled"): platforms.append("linkedin")
        x_id = None
        x_url = p.get("x_published_url") or ""
        if "/status/" in x_url:
            try: x_id = x_url.rstrip("/").split("/status/")[-1].split("?")[0]
            except Exception: pass
        for channel in platforms:
            recent.append({
                "source": "typefully",
                "channel": channel,
                "post_id": str(p.get("id")),
                "platform_post_id": x_id if channel == "x" else None,
                "published_at": pub,
                "preview": preview[:500],
                "pillar_guess": pillar_guess(preview),
                "format": "video" if p.get("media_ids") else "text",
                "url": x_url if channel == "x" else (p.get("linkedin_published_url") or ""),
            })
    return recent

def enrich_x_metrics(entries):
    """If X_BEARER set, pull engagement for X posts."""
    if not X_BEARER:
        for e in entries:
            if e["channel"] == "x":
                e["metrics"] = {"note": "X_BEARER_TOKEN not set, metrics pending"}
        return entries
    ids = [e["platform_post_id"] for e in entries if e["channel"] == "x" and e.get("platform_post_id")]
    if not ids:
        return entries
    url = (
        "https://api.twitter.com/2/tweets?"
        + urllib.parse.urlencode({
            "ids": ",".join(ids[:100]),
            "tweet.fields": "public_metrics,non_public_metrics,organic_metrics,created_at",
        })
    )
    data = http_json(url, headers={"Authorization": f"Bearer {X_BEARER}"})
    if not data:
        return entries
    by_id = {t["id"]: t for t in (data.get("data") or [])}
    for e in entries:
        if e["channel"] != "x": continue
        t = by_id.get(e.get("platform_post_id"))
        if not t: continue
        pm = t.get("public_metrics", {}) or {}
        org = t.get("non_public_metrics", {}) or {}
        imp = org.get("impression_count") or pm.get("impression_count") or 0
        eng = pm.get("like_count", 0) + pm.get("retweet_count", 0) * 20 + pm.get("reply_count", 0) * 13.5 + pm.get("bookmark_count", 0) * 10
        rate = eng / imp if imp else 0.0
        e["metrics"] = {
            "impressions": imp,
            "likes": pm.get("like_count", 0),
            "retweets": pm.get("retweet_count", 0),
            "replies": pm.get("reply_count", 0),
            "bookmarks": pm.get("bookmark_count", 0),
            "weighted_engagement": round(eng, 1),
            "rate": round(rate, 4),
            "viral": rate > 0.05,
        }
    return entries

def enrich_instagram():
    """Pull last 24h IG posts + insights."""
    if not (IG_ACCESS and IG_USER_ID):
        return []
    # /me/media?fields=id,caption,media_type,permalink,timestamp + /<id>/insights
    url = f"https://graph.instagram.com/v19.0/{IG_USER_ID}/media?access_token={IG_ACCESS}&fields=id,caption,media_type,permalink,timestamp&limit=10"
    data = http_json(url)
    if not data: return []
    out = []
    cutoff = datetime.now(timezone.utc) - timedelta(hours=26)
    for m in data.get("data", []):
        try:
            mt = datetime.fromisoformat(m["timestamp"].replace("Z", "+00:00"))
        except Exception:
            continue
        if mt < cutoff: continue
        insights = http_json(
            f"https://graph.instagram.com/v19.0/{m['id']}/insights?metric=reach,likes,comments,saves,shares&access_token={IG_ACCESS}"
        ) or {}
        metric_map = {x["name"]: x["values"][0]["value"] for x in insights.get("data", [])}
        reach = metric_map.get("reach", 0)
        eng = metric_map.get("likes", 0) + metric_map.get("comments", 0) * 5 + metric_map.get("saves", 0) * 10 + metric_map.get("shares", 0) * 15
        rate = eng / reach if reach else 0.0
        out.append({
            "source": "instagram_graph",
            "channel": "instagram",
            "post_id": m["id"],
            "platform_post_id": m["id"],
            "published_at": m["timestamp"],
            "preview": (m.get("caption") or "")[:500],
            "pillar_guess": pillar_guess(m.get("caption") or ""),
            "format": m.get("media_type", "").lower(),
            "url": m.get("permalink"),
            "metrics": {
                "reach": reach,
                "likes": metric_map.get("likes", 0),
                "comments": metric_map.get("comments", 0),
                "saves": metric_map.get("saves", 0),
                "shares": metric_map.get("shares", 0),
                "weighted_engagement": eng,
                "rate": round(rate, 4),
                "viral": rate > 0.08,
            },
        })
    return out

def main():
    entries = []
    entries.extend(collect_typefully())
    entries = enrich_x_metrics(entries)
    entries.extend(enrich_instagram())

    if not entries:
        log("No new posts in last 24h")
        return 0

    LEDGER.parent.mkdir(parents=True, exist_ok=True)
    collected_ts = datetime.now(timezone.utc).isoformat()
    with open(LEDGER, "a") as f:
        for e in entries:
            e["ts_collected"] = collected_ts
            f.write(json.dumps(e, ensure_ascii=False) + "\n")

    log(f"Collected {len(entries)} posts. Ledger: {LEDGER}")
    return 0

if __name__ == "__main__":
    sys.exit(main())

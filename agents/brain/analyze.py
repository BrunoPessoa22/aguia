#!/usr/bin/env python3
"""
FALCAO Brain — Weekly Analyzer

Reads performance.jsonl for the last 30 days.
Extracts:
  - Top 10% and bottom 20% by engagement rate per channel
  - Hook patterns that correlate with the top (first 8 words clustered)
  - Format × performance (text / image / carousel / video / reel / document)
  - Pillar × performance
  - Time-of-day × performance
  - Anti-patterns (common substrings in bottom 20%)

Writes Markdown report to:
  - brain/insights-YYYY-MM-DD.md (full analysis)
  - brain/insights-latest.md (symlink)
  - memory/YYYY-MM-DD.md (appended, so FALCAO sees it next run)
  - $WIKI_ROOT/raw/falcao-insights-YYYY-MM-DD.md (Second Brain picks up)

Usage:
  python3 analyze.py              # analyze last 7 days
  python3 analyze.py --days 30
"""
import argparse
import json
import re
import statistics
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

BASE = Path("$AGUIA_HOME")
BRAIN = BASE / "agents" / "falcao" / "brain"
MEMORY = BASE / "agents" / "falcao" / "memory"
WIKI_RAW = Path("$WIKI_ROOT/raw")
LEDGER = BRAIN / "performance.jsonl"

def load_entries(days):
    if not LEDGER.exists():
        return []
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    out = []
    with open(LEDGER) as f:
        for line in f:
            try:
                e = json.loads(line)
            except Exception:
                continue
            pub = e.get("published_at") or e.get("ts_collected") or ""
            try:
                pub_dt = datetime.fromisoformat(pub.replace("Z", "+00:00"))
            except Exception:
                continue
            if pub_dt >= cutoff:
                out.append(e)
    return out

def er(e):
    m = e.get("metrics") or {}
    return m.get("rate") if isinstance(m.get("rate"), (int, float)) else None

def first_n_words(text, n=8):
    words = re.findall(r"\S+", text or "")
    return " ".join(words[:n]).lower()

def detect_hook_type(text):
    t = (text or "").lower()
    if re.search(r"[\$r][\$ ]?[\d,\.]+[kmb]?\s*(?:→|->|vs|\s+to\s+)", t):
        return "number_contrast"
    if re.search(r"\b(i was wrong|i thought|pensava|achei que)\b", t):
        return "contrarian_confessional"
    if re.search(r"\b(who owns|why does|what if|quem é dono)\b", t):
        return "reframe_question"
    if re.search(r"\b(i just|today i|acabei de|hoje eu)\b", t):
        return "behind_scenes"
    if re.search(r"\b(here'?s what|eis o que|a verdade é)\b", t):
        return "authoritative_list"
    return "other"

def bucket(rate, channel):
    # thresholds per channel from rules.yaml — hardcoded here for zero-dep
    viral = {"x": 0.05, "linkedin": 0.06, "instagram": 0.08}.get(channel, 0.05)
    floor = {"x": 0.015, "linkedin": 0.02, "instagram": 0.025}.get(channel, 0.015)
    if rate is None: return "unknown"
    if rate >= viral: return "viral"
    if rate >= floor: return "ok"
    return "underperform"

def analyze(entries):
    by_channel = defaultdict(list)
    for e in entries:
        by_channel[e.get("channel", "unknown")].append(e)

    report = ["# FALCAO Brain — Insights Report", ""]
    report.append(f"**Window:** last {days} days | **Posts analyzed:** {len(entries)} | **Generated:** {datetime.now(timezone.utc).isoformat()}")
    report.append("")

    for ch in ("x", "linkedin", "instagram"):
        posts = by_channel.get(ch, [])
        rates = [er(e) for e in posts if er(e) is not None]
        if not posts:
            report += [f"## {ch.upper()}", "_no data_", ""]
            continue
        report.append(f"## {ch.upper()} — {len(posts)} posts")
        if rates:
            report.append(f"- Median engagement rate: **{statistics.median(rates):.3%}**")
            report.append(f"- Mean: {statistics.mean(rates):.3%} | p90: {sorted(rates)[int(len(rates)*0.9)-1] if len(rates)>=10 else 'n/a'}")
        else:
            report.append("- No rate data yet (likely missing X_BEARER_TOKEN / IG_ACCESS_TOKEN)")

        # buckets
        buckets = Counter(bucket(er(e), ch) for e in posts)
        report.append(f"- Viral: {buckets['viral']} | OK: {buckets['ok']} | Underperform: {buckets['underperform']} | Unknown: {buckets['unknown']}")

        # top 10%
        scored = [(e, er(e)) for e in posts if er(e) is not None]
        scored.sort(key=lambda x: -x[1])
        top_n = max(1, len(scored) // 10)
        bot_n = max(1, len(scored) // 5)
        top = scored[:top_n]
        bot = scored[-bot_n:] if len(scored) >= bot_n else []

        if top:
            report.append(f"\n### Top {len(top)} — winners")
            for e, r in top[:5]:
                report.append(f"- **{r:.2%}** · pillar:{e.get('pillar_guess')} · fmt:{e.get('format')} · {e.get('preview','')[:140]}... <{e.get('url','')}>")

        # hook pattern analysis
        top_hooks = Counter(detect_hook_type(e.get("preview","")) for e, _ in top)
        bot_hooks = Counter(detect_hook_type(e.get("preview","")) for e, _ in bot)
        if top_hooks:
            report.append(f"\n### Hook patterns in top vs bottom")
            for pattern in set(list(top_hooks.keys()) + list(bot_hooks.keys())):
                t, b = top_hooks.get(pattern, 0), bot_hooks.get(pattern, 0)
                report.append(f"- `{pattern}`: top={t}, bottom={b}")

        # pillar × rate
        report.append(f"\n### Pillar performance")
        pillar_rates = defaultdict(list)
        for e in posts:
            if er(e) is not None:
                pillar_rates[e.get("pillar_guess","unclassified")].append(er(e))
        for pillar, rs in sorted(pillar_rates.items(), key=lambda x: -statistics.mean(x[1]) if x[1] else 0):
            if rs:
                report.append(f"- `{pillar}`: n={len(rs)}, mean={statistics.mean(rs):.2%}")

        # format × rate
        fmt_rates = defaultdict(list)
        for e in posts:
            if er(e) is not None:
                fmt_rates[e.get("format","text")].append(er(e))
        if fmt_rates:
            report.append(f"\n### Format performance")
            for fmt, rs in sorted(fmt_rates.items(), key=lambda x: -statistics.mean(x[1]) if x[1] else 0):
                report.append(f"- `{fmt}`: n={len(rs)}, mean={statistics.mean(rs):.2%}")

        # time of day heatmap
        hour_rates = defaultdict(list)
        for e in posts:
            if er(e) is None: continue
            try:
                h = datetime.fromisoformat(e["published_at"].replace("Z","+00:00")).hour
                hour_rates[h].append(er(e))
            except Exception: pass
        if hour_rates:
            report.append(f"\n### Best hours (UTC)")
            ranked = sorted(hour_rates.items(), key=lambda x: -statistics.mean(x[1]))
            for h, rs in ranked[:5]:
                report.append(f"- `{h:02d}:00`: n={len(rs)}, mean={statistics.mean(rs):.2%}")

        report.append("")

    # cross-channel anti-patterns
    report.append("## Anti-patterns (shared across bottom 20%)")
    all_bottom_text = []
    for ch, posts in by_channel.items():
        scored = [(e, er(e)) for e in posts if er(e) is not None]
        scored.sort(key=lambda x: x[1])
        bot = scored[:max(1, len(scored)//5)]
        all_bottom_text.extend(e.get("preview","")[:200] for e, _ in bot)
    # simple bigram extraction
    words = " ".join(all_bottom_text).lower()
    bigrams = Counter(re.findall(r"\b(\w+\s+\w+)\b", words))
    common_bigrams = [b for b, c in bigrams.most_common(30) if c >= 3 and not any(w in b for w in ["the","and","to","in","of","is","a","que","para","uma","de","do"])]
    for b in common_bigrams[:10]:
        report.append(f"- `{b}`")

    return "\n".join(report)

def main():
    global days
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=7)
    args = ap.parse_args()
    days = args.days

    entries = load_entries(days)
    report = analyze(entries)

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    out_brain = BRAIN / f"insights-{today}.md"
    out_latest = BRAIN / "insights-latest.md"
    out_wiki = WIKI_RAW / f"falcao-insights-{today}.md"
    out_memory = MEMORY / f"{today}.md"

    BRAIN.mkdir(parents=True, exist_ok=True)
    WIKI_RAW.mkdir(parents=True, exist_ok=True)

    out_brain.write_text(report)
    if out_latest.exists() or out_latest.is_symlink():
        out_latest.unlink()
    out_latest.symlink_to(out_brain.name)
    out_wiki.write_text(report)

    # Append to memory (non-destructive)
    with open(out_memory, "a") as f:
        f.write("\n\n## Brain insights (auto-generated)\n\n")
        f.write(report)

    print(f"Written: {out_brain}, {out_wiki}, appended to {out_memory}")

if __name__ == "__main__":
    main()

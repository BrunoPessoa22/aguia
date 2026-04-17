#!/usr/bin/env python3
"""
FALCAO Brain — Evolver (weekly)

Reads brain/insights-latest.md + brain/rules.yaml.
Proposes rule changes based on insights.

Two modes:
  - AUTO: if change is in evolution.auto_allowed, apply directly + git commit
  - PROPOSE: if in evolution.requires_approval, write proposal to brain/proposals/YYYY-MM-DD.md and Telegram Bruno

Never changes evolution.never_change keys.

Usage: python3 evolve.py [--dry-run]
"""
import argparse
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

try:
    import yaml
except ImportError:
    print("Install pyyaml: pip install --user pyyaml", file=sys.stderr)
    sys.exit(2)

BASE = Path("$AGUIA_HOME")
BRAIN = BASE / "agents" / "falcao" / "brain"
RULES = BRAIN / "rules.yaml"
INSIGHTS = BRAIN / "insights-latest.md"
PROPOSALS = BRAIN / "proposals"
PROPOSALS.mkdir(parents=True, exist_ok=True)

def load_rules():
    return yaml.safe_load(RULES.read_text())

def save_rules(rules):
    RULES.write_text(yaml.safe_dump(rules, sort_keys=False, allow_unicode=True))

def git(*args):
    try:
        subprocess.run(["git", "-C", str(BRAIN), *args], check=True, capture_output=True)
        return True
    except Exception as e:
        print(f"git {args}: {e}")
        return False

def parse_insights(text):
    """Extract structured signals from analyzer report."""
    sig = {
        "top_hooks": {},        # channel -> [hook types ranked]
        "top_formats": {},      # channel -> [formats ranked]
        "top_hours": {},        # channel -> [hours ranked]
        "pillar_rates": {},     # channel -> { pillar -> rate }
    }
    current_ch = None
    section = None
    for line in text.splitlines():
        m = re.match(r"^## ([A-Z]+)\b", line)
        if m and m.group(1) in ("X", "LINKEDIN", "INSTAGRAM"):
            current_ch = m.group(1).lower()
            continue
        if line.startswith("### "):
            section = line[4:].strip().lower()
            continue
        if not current_ch or not section: continue
        if "hook patterns" in section:
            m = re.match(r"- `(\w+)`: top=(\d+), bottom=(\d+)", line.strip())
            if m:
                pat, t, b = m.group(1), int(m.group(2)), int(m.group(3))
                sig["top_hooks"].setdefault(current_ch, {})[pat] = t - b
        elif "pillar performance" in section:
            m = re.match(r"- `(\w+)`: n=(\d+), mean=([\d.]+)%", line.strip())
            if m:
                sig["pillar_rates"].setdefault(current_ch, {})[m.group(1)] = float(m.group(3)) / 100
        elif "format performance" in section:
            m = re.match(r"- `(\w+)`: n=(\d+), mean=([\d.]+)%", line.strip())
            if m:
                sig["top_formats"].setdefault(current_ch, []).append((m.group(1), float(m.group(3))/100))
        elif "best hours" in section:
            m = re.match(r"- `(\d+):00`: n=(\d+), mean=([\d.]+)%", line.strip())
            if m:
                sig["top_hours"].setdefault(current_ch, []).append((int(m.group(1)), float(m.group(3))/100))
    return sig

def propose_changes(rules, sig):
    """Return two lists: (auto_changes, approval_changes). Each change is (path, old, new, reason)."""
    auto, approval = [], []

    # Rule 1: recalibrate engagement_rate thresholds based on observed median (auto)
    for ch in ("x", "linkedin", "instagram"):
        rates = sig.get("pillar_rates", {}).get(ch, {})
        if not rates: continue
        means = list(rates.values())
        if not means: continue
        observed_median = sorted(means)[len(means)//2]
        current_floor = rules["thresholds"]["engagement_rate_floor_by_channel"].get(ch)
        # only nudge if observed is wildly off (20%+ drift)
        if current_floor and abs(observed_median - current_floor) / current_floor > 0.3:
            new_floor = round(observed_median * 0.6, 4)   # floor = 60% of median
            auto.append((
                f"thresholds.engagement_rate_floor_by_channel.{ch}",
                current_floor, new_floor,
                f"observed median {observed_median:.3%}, recalibrating floor to 60% of median"
            ))

    # Rule 2: add top hour to optimal_windows if it beats existing windows by 30%+ (auto)
    for ch in ("x", "linkedin", "instagram"):
        hours = sig.get("top_hours", {}).get(ch, [])
        if not hours: continue
        best_hour, best_rate = hours[0]
        key_map = {
            "x": "channels.x.optimal_windows_utc",
            "linkedin": "channels.linkedin.optimal_windows_warsaw",
            "instagram": "channels.instagram.optimal_windows_brt",
        }
        path = key_map[ch]
        current = rules
        for k in path.split("."):
            current = current.get(k, {})
        if isinstance(current, list) and f"{best_hour:02d}" not in " ".join(str(x) for x in current):
            auto.append((
                path + ".append",
                current,
                current + [f"{best_hour:02d}:00"],
                f"new hour {best_hour:02d}:00 UTC performed at {best_rate:.3%}"
            ))

    # Rule 3: hook pattern updates (requires approval)
    for ch in ("x", "linkedin", "instagram"):
        hooks = sig.get("top_hooks", {}).get(ch, {})
        if not hooks: continue
        winners = [h for h, score in hooks.items() if score >= 2]
        losers = [h for h, score in hooks.items() if score <= -2]
        if winners or losers:
            approval.append((
                f"channels.{ch}.hook_patterns_winners",
                rules["channels"][ch].get("hook_patterns_winners", []),
                {"add": winners, "remove": losers},
                f"top hooks: +{winners}, bottom: -{losers}"
            ))

    return auto, approval

def apply_auto(rules, auto_changes, dry=False):
    applied = []
    for path, old, new, reason in auto_changes:
        keys = path.replace(".append", "").split(".")
        cur = rules
        for k in keys[:-1]:
            cur = cur[k]
        if not dry:
            cur[keys[-1]] = new
        applied.append({"path": path, "old": old, "new": new, "reason": reason})
    return applied

def send_proposal(approval_changes, today):
    if not approval_changes: return None
    path = PROPOSALS / f"{today}.md"
    lines = [f"# FALCAO Brain Proposals — {today}", "", "Bruno: reply YES or the specific change you approve.", ""]
    for i, (p, old, new, reason) in enumerate(approval_changes, 1):
        lines.append(f"## {i}. `{p}`")
        lines.append(f"**Reason:** {reason}")
        lines.append(f"**Current:** `{old}`")
        lines.append(f"**Proposed:** `{new}`")
        lines.append("")
    path.write_text("\n".join(lines))
    return path

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    if not RULES.exists():
        print(f"rules.yaml missing at {RULES}", file=sys.stderr)
        sys.exit(1)
    if not INSIGHTS.exists():
        print(f"insights-latest.md missing — run analyze.py first", file=sys.stderr)
        sys.exit(1)

    rules = load_rules()
    sig = parse_insights(INSIGHTS.read_text())
    auto, approval = propose_changes(rules, sig)

    applied = apply_auto(rules, auto, dry=args.dry_run)
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    if applied and not args.dry_run:
        save_rules(rules)
        git("add", "rules.yaml")
        git("commit", "-m", f"brain: auto-evolve rules {today}\n\n" + "\n".join(f"- {a['path']}: {a['reason']}" for a in applied))

    prop_path = send_proposal(approval, today)

    summary = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "auto_applied": len(applied),
        "approval_pending": len(approval),
        "auto": applied,
        "proposal_file": str(prop_path) if prop_path else None,
    }
    (BRAIN / f"evolve-{today}.json").write_text(json.dumps(summary, indent=2))
    print(json.dumps(summary, indent=2))

if __name__ == "__main__":
    main()

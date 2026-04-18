#!/bin/bash
# Aguia v2 — promote-live
#
# Moves live/ entries older than N hours (default 24h) into raw/ as
# self-contained markdown files, where the existing second-brain cron can
# pick them up and compile into wiki articles.
#
# Per-entry promotion (one .md per entry), not per-day-file. Keeps the
# raw/ folder clean and matches the second-brain's expected shape.
#
# Usage:
#   promote-live.sh [HOURS_OLD]
#     HOURS_OLD   minimum age in hours (default 24)
#
# Idempotent — once an entry is promoted, it's stripped from the live file.
# Leaves a `<!-- promoted:TIMESTAMP -->` marker so double-runs are safe.

set -euo pipefail

MIN_AGE_HOURS="${1:-24}"
LIVE_DIR="${WIKI_LIVE_DIR:-/home/ubuntu/clawd/wiki/live}"
RAW_DIR="${WIKI_RAW_DIR:-/home/ubuntu/clawd/wiki/raw}"
LOG=/home/ubuntu/aguia/shared/logs/wiki-remember.log

mkdir -p "$RAW_DIR"
mkdir -p "$(dirname "$LOG")"

[ -d "$LIVE_DIR" ] || { echo "[$(date -u +%FT%TZ)] live dir missing, skip" >> "$LOG"; exit 0; }

NOW=$(date +%s)
THRESHOLD=$((MIN_AGE_HOURS * 3600))
PROMOTED=0

for F in "$LIVE_DIR"/*.md; do
    [ -f "$F" ] || continue
    FILE_MTIME=$(stat -c %Y "$F")
    AGE=$((NOW - FILE_MTIME))
    # If the whole file is newer than threshold, skip (its entries may not all be ready)
    [ "$AGE" -lt "$THRESHOLD" ] && continue

    FILE_DATE=$(basename "$F" .md)
    python3 <<PYEOF
import re
import sys
from pathlib import Path

src = Path("$F")
raw_dir = Path("$RAW_DIR")
file_date = "$FILE_DATE"
content = src.read_text()

# Split by "## HH:MM UTC — TITLE" headers
entries = re.split(r'(?=^## \d\d:\d\d UTC — )', content, flags=re.MULTILINE)

kept = [entries[0]] if entries and not entries[0].startswith("## ") else []
promoted_count = 0

for entry in entries:
    if not entry.startswith("## "):
        continue
    if "<!-- promoted:" in entry:
        kept.append(entry)
        continue
    # Parse title
    m = re.match(r'^## (\d\d:\d\d) UTC — (.+?)\n', entry)
    if not m:
        kept.append(entry)
        continue
    hm, title = m.group(1), m.group(2).strip()
    slug = re.sub(r'[^a-z0-9]+', '-', title.lower()).strip('-')[:60]
    out_path = raw_dir / f"{file_date}-live-{slug}.md"
    if out_path.exists():
        # Already promoted earlier, mark
        kept.append(entry.rstrip() + "\n<!-- promoted:already -->\n")
        continue
    out_path.write_text(f"# {title}\n\n_Promoted from live/{file_date}.md at {hm} UTC._\n\n" + entry[m.end():].strip() + "\n")
    kept.append(entry.rstrip() + f"\n<!-- promoted:{out_path.name} -->\n")
    promoted_count += 1
    # Emit signal — agents see WIKI_PROMOTED in their SIGNALS_CONTEXT
    src_match = re.search(r"_Source:\s+(\S+?)_", entry)
    source = src_match.group(1) if src_match else "unknown"
    import datetime as dt
    now = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    signal = f"[{now}] WIKI_PROMOTED agent={source} title=\"{title[:80]}\" path=wiki/raw/{out_path.name}\n"
    with open("/home/ubuntu/aguia/shared/signals.md", "a") as sf:
        sf.write(signal)

src.write_text(''.join(kept))
print(promoted_count)
PYEOF
    COUNT=$(python3 <<PYEOF
import re
from pathlib import Path
c = Path("$F").read_text().count("<!-- promoted:")
print(c)
PYEOF
)
    :
done

# Count promotions this run by tallying new raw files matching today's pattern
NEW_RAW=$(find "$RAW_DIR" -name "*-live-*.md" -newer "$LOG" -type f 2>/dev/null | wc -l)
echo "[$(date -u +%FT%TZ)] promoted $NEW_RAW live entries to raw/" >> "$LOG"
exit 0

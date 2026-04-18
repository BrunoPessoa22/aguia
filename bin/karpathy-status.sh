#!/bin/bash
# Karpathy-loop status dashboard — runs every 30 min via cron.
# Writes a human-readable status.md that agents + Bruno can read.
#
# Output: /home/ubuntu/aguia/shared/karpathy-status.md
# Also writes a machine-readable JSON: /home/ubuntu/aguia/shared/karpathy-status.json

set -u
export TZ=UTC

LIVE_DIR=/home/ubuntu/clawd/wiki/live
RAW_DIR=/home/ubuntu/clawd/wiki/raw
COMPILED_DIR=/home/ubuntu/clawd/wiki/compiled
WIKI_LOG=/home/ubuntu/aguia/shared/logs/wiki-remember.log
SIGNALS=/home/ubuntu/aguia/shared/signals.md
OUT_MD=/home/ubuntu/aguia/shared/karpathy-status.md
OUT_JSON=/home/ubuntu/aguia/shared/karpathy-status.json

NOW=$(date -u +%Y-%m-%dT%H:%M:%SZ)
TODAY=$(date -u +%Y-%m-%d)

# Counts
LIVE_COUNT=$(find "$LIVE_DIR" -maxdepth 1 -name '*.md' 2>/dev/null | wc -l)
LIVE_ENTRIES=$(find "$LIVE_DIR" -maxdepth 1 -name '*.md' 2>/dev/null | xargs grep -Hc '^## ' 2>/dev/null | awk -F: '{s+=$2} END {print s+0}')
LIVE_PROMOTED=$(find "$LIVE_DIR" -maxdepth 1 -name '*.md' 2>/dev/null | xargs grep -Hc '<!-- promoted:' 2>/dev/null | awk -F: '{s+=$2} END {print s+0}')
LIVE_PENDING=$((LIVE_ENTRIES - LIVE_PROMOTED))
RAW_COUNT=$(find "$RAW_DIR" -maxdepth 1 -name '*.md' 2>/dev/null | wc -l)
COMPILED_COUNT=$(find "$COMPILED_DIR" -name '*.md' 2>/dev/null | wc -l)

# Today's wiki-remember activity — by agent
WIKI_TODAY_COUNT=0
if [ -f "$WIKI_LOG" ]; then
    WIKI_TODAY_COUNT=$(grep -c "^\[${TODAY}" "$WIKI_LOG" 2>/dev/null || echo 0)
fi

# Per-agent activity today (parse src:AGENT_NAME from log lines)
BY_AGENT=$(grep "^\[${TODAY}" "$WIKI_LOG" 2>/dev/null | grep -oE 'src:[a-z-]+' | sort | uniq -c | sort -rn | head -10)

# Recent signals (last 5 WIKI_PROMOTED)
RECENT_PROMOTIONS=$(grep 'WIKI_PROMOTED' "$SIGNALS" 2>/dev/null | tail -5)

# Raw backlog age buckets
RAW_LT_24H=$(find "$RAW_DIR" -maxdepth 1 -name '*.md' -mtime -1 2>/dev/null | wc -l)
RAW_1D_7D=$(find "$RAW_DIR" -maxdepth 1 -name '*.md' -mtime +1 -mtime -7 2>/dev/null | wc -l)
RAW_GT_7D=$(find "$RAW_DIR" -maxdepth 1 -name '*.md' -mtime +7 2>/dev/null | wc -l)

# Last compile timestamp (mtime of the newest compiled file)
LAST_COMPILE=$(find "$COMPILED_DIR" -name '*.md' -type f -printf '%TY-%Tm-%Td %TH:%TM  %p\n' 2>/dev/null | sort -r | head -1 | awk '{print $1, $2}')

# === MARKDOWN DASHBOARD ===
cat > "$OUT_MD" <<EOF
# Karpathy Loop — Status ($NOW)

## Pipeline counts

| Stage | Count | Notes |
|---|---|---|
| **Live brain** (wiki/live/) | ${LIVE_ENTRIES} entries in ${LIVE_COUNT} day-files | ${LIVE_PENDING} pending promotion, ${LIVE_PROMOTED} already promoted |
| **Raw backlog** (wiki/raw/) | ${RAW_COUNT} files | <24h: ${RAW_LT_24H} / 1-7d: ${RAW_1D_7D} / >7d: ${RAW_GT_7D} |
| **Compiled articles** (wiki/compiled/) | ${COMPILED_COUNT} articles | Last compile: ${LAST_COMPILE:-none} |

## Today's wiki-remember activity

Total writes today (UTC): **${WIKI_TODAY_COUNT}**

By agent:
\`\`\`
${BY_AGENT:-(none yet)}
\`\`\`

## Recent promotions (live → raw)

\`\`\`
${RECENT_PROMOTIONS:-(none yet — promote-live runs daily at 05:30 UTC)}
\`\`\`

## Hot links

- Wiki index: \`/home/ubuntu/clawd/wiki/index.md\`
- Today's live brain: \`${LIVE_DIR}/${TODAY}.md\`
- Wiki-remember log: \`${WIKI_LOG}\`
- Signals: \`${SIGNALS}\` (grep WIKI_PROMOTED)

_Regenerated every 30 min by \`/home/ubuntu/aguia/bin/karpathy-status.sh\`._
EOF

# === JSON (for programmatic consumers) ===
python3 <<PYEOF > "$OUT_JSON"
import json
print(json.dumps({
    "ts": "$NOW",
    "pipeline": {
        "live": {"day_files": $LIVE_COUNT, "entries": $LIVE_ENTRIES, "pending_promotion": $LIVE_PENDING, "already_promoted": $LIVE_PROMOTED},
        "raw": {"total": $RAW_COUNT, "lt_24h": $RAW_LT_24H, "1d_7d": $RAW_1D_7D, "gt_7d": $RAW_GT_7D},
        "compiled": {"total": $COMPILED_COUNT, "last_compile": "${LAST_COMPILE:-none}"}
    },
    "today_wiki_writes": $WIKI_TODAY_COUNT,
}, indent=2))
PYEOF

exit 0

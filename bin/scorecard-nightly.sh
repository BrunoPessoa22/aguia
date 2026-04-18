#!/bin/bash
# Nightly scorecards per agent — runs at 23:50 UTC via cron.
#
# Counts for each agent:
#   - wiki-remember writes today (from wiki-remember.log)
#   - rate-limit skips today
#   - insights that landed in today's live/<date>.md
#   - promotions today (from signals.md WIKI_PROMOTED lines)
#
# Writes per-agent scorecards to /home/ubuntu/aguia/shared/scorecards/<agent>.md
# Also writes a fleet-wide rollup to shared/scorecards/_fleet.md

set -u
export TZ=UTC

LOG=/home/ubuntu/aguia/shared/logs/wiki-remember.log
SIGNALS=/home/ubuntu/aguia/shared/signals.md
LIVE_DIR=/home/ubuntu/clawd/wiki/live
SCORECARD_DIR=/home/ubuntu/aguia/shared/scorecards
mkdir -p "$SCORECARD_DIR"

TODAY=$(date -u +%Y-%m-%d)
NOW=$(date -u +%Y-%m-%dT%H:%M:%SZ)

# Aggregate fleet rollup data
declare -A WRITES
declare -A SKIPS
declare -A PROMOTIONS

# Parse wiki-remember.log today lines — extract src:<agent>
if [ -f "$LOG" ]; then
    while IFS= read -r line; do
        agent=$(echo "$line" | grep -oE 'src:[a-z0-9_-]+' | head -1 | cut -d: -f2)
        [ -z "$agent" ] && continue
        if echo "$line" | grep -q "rate-limit:"; then
            SKIPS[$agent]=$((${SKIPS[$agent]:-0} + 1))
        elif echo "$line" | grep -q "^\[${TODAY}.*wrote"; then
            WRITES[$agent]=$((${WRITES[$agent]:-0} + 1))
        fi
    done < <(grep "^\[${TODAY}" "$LOG" 2>/dev/null)
fi

# Parse signals.md today — WIKI_PROMOTED lines
if [ -f "$SIGNALS" ]; then
    while IFS= read -r line; do
        agent=$(echo "$line" | grep -oE 'agent=[a-z0-9_-]+' | cut -d= -f2)
        [ -z "$agent" ] && continue
        PROMOTIONS[$agent]=$((${PROMOTIONS[$agent]:-0} + 1))
    done < <(grep "WIKI_PROMOTED" "$SIGNALS" 2>/dev/null | grep "$TODAY")
fi

# Union of agent names seen today
ALL_AGENTS=$({ for a in "${!WRITES[@]}" "${!SKIPS[@]}" "${!PROMOTIONS[@]}"; do echo "$a"; done } | sort -u)

# Per-agent scorecard write
for agent in $ALL_AGENTS; do
    w=${WRITES[$agent]:-0}
    s=${SKIPS[$agent]:-0}
    p=${PROMOTIONS[$agent]:-0}
    attempt_total=$((w + s))
    cat > "$SCORECARD_DIR/$agent.md" <<EOF
# Scorecard — $agent

_Generated: $NOW (UTC day: $TODAY)_

## Today's Karpathy-loop activity

| Metric | Count |
|---|---|
| wiki-remember writes (accepted) | **$w** |
| wiki-remember skipped (rate-limit or dedup) | $s |
| Total wiki-remember attempts | $attempt_total |
| Promotions (live → raw) | $p |

## Signal quality hint

$(
if [ "$w" -eq 0 ] && [ "$s" -eq 0 ]; then
    echo "No wiki-remember activity today. If this agent ran crons, it did not capture any insights worth persisting. Either legitimately nothing new OR agent is not invoking wiki-remember on discoveries."
elif [ "$w" -gt 10 ]; then
    echo "High write volume ($w). Check signal/noise ratio — are these genuinely reusable insights, or is the agent writing everything?"
elif [ "$p" -gt 0 ]; then
    echo "$p insight(s) matured 24h and promoted to raw/. Next cron of second-brain ($(date -u -d 'tomorrow 06:00' +%Y-%m-%d) 06:00 UTC) will consider compiling them."
else
    echo "$w insight(s) captured, awaiting promotion window (24h). Expected promote-live run: 05:30 UTC tomorrow."
fi
)

## Last few entries from live brain

\`\`\`
$(grep -B 1 -A 2 "_Source: ${agent}_" "$LIVE_DIR/$TODAY.md" 2>/dev/null | tail -12 || echo '(none today)')
\`\`\`

_Agents read this at dispatch time if INJECT_SCORECARD=1 is set. Scorecard
helps you self-assess quality and know what made it to the durable brain._
EOF
done

# Fleet rollup
cat > "$SCORECARD_DIR/_fleet.md" <<EOF
# Fleet scorecard — $TODAY

_Generated: ${NOW}_

| Agent | Writes | Skips | Promotions |
|---|---:|---:|---:|
$(
for agent in $ALL_AGENTS; do
    printf "| %s | %d | %d | %d |\n" "$agent" "${WRITES[$agent]:-0}" "${SKIPS[$agent]:-0}" "${PROMOTIONS[$agent]:-0}"
done
)
| **TOTAL** | $({ total=0; for a in "${!WRITES[@]}"; do total=$((total + WRITES[$a])); done; echo $total; }) | $({ total=0; for a in "${!SKIPS[@]}"; do total=$((total + SKIPS[$a])); done; echo $total; }) | $({ total=0; for a in "${!PROMOTIONS[@]}"; do total=$((total + PROMOTIONS[$a])); done; echo $total; }) |

## Activity heat check

$(
if [ ${#WRITES[@]} -eq 0 ]; then
    echo "**⚠️  Zero wiki-remember activity across the fleet today.** Karpathy loop is not engaging. Check agent prompts + trigger patterns."
else
    echo "${#WRITES[@]} agents contributed to the live brain today."
fi
)

## Per-agent cards

$(for agent in $ALL_AGENTS; do echo "- [$agent]($agent.md)"; done)
EOF

echo "[$NOW] scorecards generated — ${#WRITES[@]} agents active, $(echo $ALL_AGENTS | wc -w) total entries"

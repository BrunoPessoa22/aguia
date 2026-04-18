#!/bin/bash
# investigate.sh — append a hypothesis to the shared investigation queue.
#
# Usage:
#   investigate.sh "HYPOTHESIS text — what to investigate or test"
#
# Any agent can call this when it notices something worth looking into but
# doesnt have the budget to investigate now. Aguia (interactive) or a future
# investigator cron can pick up entries during idle cycles.
#
# Format per line: [ISO_TS] agent=<src> QUESTION: <text>

set -euo pipefail
QUEUE=/home/ubuntu/aguia/shared/investigation-queue.md
SOURCE="${WIKI_REMEMBER_SOURCE:-unknown}"
HYPOTHESIS="${1:-}"

if [ -z "$HYPOTHESIS" ]; then
    echo "usage: investigate.sh \"hypothesis / question to investigate\"" >&2
    exit 2
fi

mkdir -p "$(dirname "$QUEUE")"
if [ ! -f "$QUEUE" ]; then
    cat > "$QUEUE" <<HDR
# Investigation Queue

Agents add hypotheses here when they notice something worth investigating
later but dont have budget now. Aguia or a future investigator cron picks
them up. Format: \`[ISO_TS] agent=<src> QUESTION: <text>\`

Resolved entries get prefixed \`[RESOLVED <date>]\` — do NOT delete (audit trail).

---

HDR
fi

TS=$(date -u +%Y-%m-%dT%H:%M:%SZ)
echo "[$TS] agent=$SOURCE QUESTION: $HYPOTHESIS" >> "$QUEUE"
echo "[$TS] queued: $HYPOTHESIS"

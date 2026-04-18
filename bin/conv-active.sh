#!/bin/bash
# Returns 0 (active -> defer) if Bruno has inbound Telegram msg in last $1 seconds.
# Returns 1 (quiet -> send) otherwise.
# Usage: conv-active.sh [window_seconds=120]
WINDOW=${1:-120}
INBOX=/home/ubuntu/.claude/channels/telegram/inbox
[ -d "$INBOX" ] || exit 1
LATEST=$(find "$INBOX" -type f -name '*.json' -printf '%T@\n' 2>/dev/null | sort -n | tail -1 | cut -d. -f1)
[ -z "$LATEST" ] && exit 1
NOW=$(date +%s)
AGE=$((NOW - LATEST))
if [ "$AGE" -lt "$WINDOW" ]; then
    exit 0
fi
exit 1

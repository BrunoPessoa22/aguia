#!/bin/bash
# Session health check (context auto-compact).
#
# KILL branch removed 2026-04-18 after audit showed 15 kill/respawn cycles/day
# were fighting the live Telegram session and dropping user messages.
# /compact auto-action retained for context-size control.
#
# To restore the KILL branch, see session-health.sh.bak.p0.<timestamp>
# or .bak.1776450601 (pre-Apr-17 version).

export PATH="$HOME/.local/bin:$HOME/.bun/bin:$PATH"

LOG=/home/ubuntu/aguia/shared/logs/session-health.log

if tmux has-session -t aguia 2>/dev/null; then
    CONTEXT=$(tmux capture-pane -t aguia -p -S -50 2>&1)

    if echo "$CONTEXT" | grep -qE 'save [0-9]+'; then
        TOKENS=$(echo "$CONTEXT" | grep -oE '[0-9]+\.[0-9]+k' | tail -1 | sed 's/k//')
        if [ -n "$TOKENS" ]; then
            OVER=$(echo "$TOKENS > 80" | bc -l 2>/dev/null || echo "0")
            if [ "$OVER" = "1" ]; then
                tmux send-keys -t aguia "/compact" Enter
                echo "$(date): Compacted session at ${TOKENS}k tokens" >> "$LOG"
            fi
        fi
    fi
fi

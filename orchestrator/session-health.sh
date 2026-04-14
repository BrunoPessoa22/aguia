#!/bin/bash
# Session Health -- Auto-compact when context gets too large
# Called by keepalive.sh, can also run standalone via cron.
export PATH="$HOME/.local/bin:$HOME/.bun/bin:$PATH"

if tmux has-session -t aguia 2>/dev/null; then
    CONTEXT=$(tmux capture-pane -t aguia -p 2>&1)
    # Check for "save NNNk" pattern indicating high context usage
    if echo "$CONTEXT" | grep -qE 'save [0-9]+'; then
        TOKENS=$(echo "$CONTEXT" | grep -oE '[0-9]+\.[0-9]+k' | tail -1 | sed 's/k//')
        if [ -n "$TOKENS" ]; then
            OVER=$(echo "$TOKENS > 80" | bc -l 2>/dev/null || echo "0")
            if [ "$OVER" = "1" ]; then
                tmux send-keys -t aguia "/compact" Enter
                echo "$(date): Compacted session at ${TOKENS}k tokens" >> "$HOME/aguia/shared/logs/session-health.log"
            fi
        fi
    fi
fi

#!/bin/bash
# Responsiveness Watchdog -- runs every minute via cron
# Detects stuck sessions and interrupts them to process queued Telegram messages
#
# Problem: When Claude is thinking/running a long tool call, incoming Telegram
# messages queue up indefinitely. Users get no response for minutes.
#
# Solution: If the session has been processing (not at idle prompt) for >90s,
# send Escape to interrupt and let it process queued messages.

export PATH="$HOME/.local/bin:$HOME/.bun/bin:$PATH"
LOG="$HOME/aguia/shared/logs/responsiveness.log"
STATE_FILE="/tmp/aguia-processing-since"

if ! tmux has-session -t aguia 2>/dev/null; then
    exit 0
fi

# Capture current pane content
PANE=$(tmux capture-pane -t aguia -p 2>/dev/null)

# Check if session is at idle prompt (ready for input)
IS_IDLE=false
if echo "$PANE" | tail -5 | grep -qE '^> $|^>$'; then
    IS_IDLE=true
fi

# Check if session is actively thinking/processing
IS_PROCESSING=false
if echo "$PANE" | tail -5 | grep -qE 'Thinking|tokens\)|still running'; then
    IS_PROCESSING=true
fi

# Check for context size -- compact earlier at 50k
TOKENS=$(echo "$PANE" | grep -oE '[0-9]+\.[0-9]+k' | tail -1 | sed 's/k//')
if [ -n "$TOKENS" ]; then
    OVER=$(echo "$TOKENS > 50" | bc -l 2>/dev/null || echo "0")
    if [ "$OVER" = "1" ]; then
        # Don't interrupt if actively processing, just log
        if [ "$IS_IDLE" = "true" ]; then
            tmux send-keys -t aguia "/compact" Enter
            echo "$(date +%H:%M:%S): Compacted at ${TOKENS}k tokens" >> "$LOG"
        fi
    fi
fi

if [ "$IS_IDLE" = "true" ]; then
    # Session is idle -- clear state file
    rm -f "$STATE_FILE"
    exit 0
fi

if [ "$IS_PROCESSING" = "true" ]; then
    if [ ! -f "$STATE_FILE" ]; then
        # First detection of processing -- record timestamp
        date +%s > "$STATE_FILE"
        exit 0
    fi

    # Check how long it's been processing
    STARTED=$(cat "$STATE_FILE")
    NOW=$(date +%s)
    ELAPSED=$(( NOW - STARTED ))

    if [ "$ELAPSED" -gt 90 ]; then
        # Been processing for >90 seconds -- interrupt!
        echo "$(date +%H:%M:%S): Session stuck for ${ELAPSED}s -- sending Escape to interrupt" >> "$LOG"
        tmux send-keys -t aguia Escape
        sleep 2

        # Check if it responded to the interrupt
        NEW_PANE=$(tmux capture-pane -t aguia -p 2>/dev/null)
        if echo "$NEW_PANE" | tail -5 | grep -qE '^> $|^>$'; then
            echo "$(date +%H:%M:%S): Session interrupted successfully -- now at idle prompt" >> "$LOG"
            rm -f "$STATE_FILE"
        else
            # Still processing after interrupt -- log but don't kill
            echo "$(date +%H:%M:%S): Interrupt sent but session still busy (will retry next minute)" >> "$LOG"
            # Reset timer so it doesn't interrupt every minute forever
            date +%s > "$STATE_FILE"
        fi
    fi
else
    # Not clearly processing or idle -- might be in a tool call
    # If state file exists and it's been >120s, soft interrupt
    if [ -f "$STATE_FILE" ]; then
        STARTED=$(cat "$STATE_FILE")
        NOW=$(date +%s)
        ELAPSED=$(( NOW - STARTED ))
        if [ "$ELAPSED" -gt 120 ]; then
            echo "$(date +%H:%M:%S): Ambiguous state for ${ELAPSED}s -- sending Escape" >> "$LOG"
            tmux send-keys -t aguia Escape
            rm -f "$STATE_FILE"
        fi
    else
        # Start tracking
        date +%s > "$STATE_FILE"
    fi
fi

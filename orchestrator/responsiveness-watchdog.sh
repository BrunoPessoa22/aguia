#!/bin/bash
# Responsiveness Watchdog v3 — runs every minute via cron
# Detects TRULY stuck sessions and interrupts them.
#
# v2 changes: fixed false-positive "ambiguous state" detection that was
# sending Escape every 3 minutes (139 false interrupts logged).
# Now checks for actual Telegram message queue before interrupting.
#
# v3 changes (2026-04-18):
# - Raised IS_WORKING interrupt threshold 300s -> 900s (Opus 4.7 tool chains
#   legitimately take >5 min; 5 min was still too aggressive).
# - Disabled RESUME branch (the "resume: continue o que..." nudge). It was
#   prompt-injection-risky and never actually fired in production.

if [ -f /tmp/watchdog_paused ]; then exit 0; fi
export PATH="$HOME/.local/bin:$HOME/.bun/bin:$PATH"
LOG="$HOME/aguia/shared/logs/responsiveness.log"
STATE_FILE="/tmp/aguia-processing-since"
INTERRUPT_COUNT_FILE="/tmp/aguia-interrupt-count"

if ! tmux has-session -t aguia 2>/dev/null; then
    rm -f "$STATE_FILE" "$INTERRUPT_COUNT_FILE"
    exit 0
fi

# Capture current pane content (last 30 lines for better detection)
PANE=$(tmux capture-pane -t aguia -p -S -30 2>/dev/null)

# Check if session is at idle prompt (ready for input)
IS_IDLE=false
if echo "$PANE" | tail -5 | grep -qE '^❯ $|^❯$'; then
    IS_IDLE=true
fi

# Check if session is actively working (thinking, tool calls, streaming)
IS_WORKING=false
if echo "$PANE" | tail -30 | grep -qiE 'esc to interrupt|Bloviating|Brewing|Brewed|Thinking|Razzle|Dazzling|Ruminating|Percolating|Pondering|Simmering|Cogitating|Noodling|Mulling|tokens|still running|Reading|Editing|Writing|Searching|Bash|Glob|Grep|Agent|WebFetch|mcp__|⠋|⠙|⠹|⠸|⠼|⠴|⠦|⠧|⠇|⠏|✶|✴|✳'; then
    IS_WORKING=true
fi

# Check for context size — compact at 60k (raised from 50k)
TOKENS=$(echo "$PANE" | grep -oE '[0-9]+\.[0-9]+k' | tail -1 | sed 's/k//')
if [ -n "$TOKENS" ]; then
    OVER=$(echo "$TOKENS > 60" | bc -l 2>/dev/null || echo "0")
    if [ "$OVER" = "1" ]; then
        if [ "$IS_IDLE" = "true" ]; then
            tmux send-keys -t aguia "/compact" Enter
            echo "$(date +%H:%M:%S): Compacted at ${TOKENS}k tokens" >> "$LOG"
        fi
    fi
fi

if [ "$IS_IDLE" = "true" ]; then
    rm -f "$STATE_FILE" "$INTERRUPT_COUNT_FILE"
    exit 0
fi

if [ "$IS_WORKING" = "true" ]; then
    # Session is actively working — this is NORMAL. Don't interrupt.
    # Only track time, interrupt after 15 MINUTES (v3: raised from 5min).
    if [ ! -f "$STATE_FILE" ]; then
        date +%s > "$STATE_FILE"
        exit 0
    fi

    STARTED=$(cat "$STATE_FILE")
    NOW=$(date +%s)
    ELAPSED=$(( NOW - STARTED ))

    # Only interrupt after 15 minutes of continuous processing
    if [ "$ELAPSED" -gt 900 ]; then
        # Check interrupt count — max 2 interrupts before backing off
        COUNT=$(cat "$INTERRUPT_COUNT_FILE" 2>/dev/null || echo "0")
        if [ "$COUNT" -ge 2 ]; then
            # Already interrupted twice — back off, let it work
            exit 0
        fi

        echo "$(date +%H:%M:%S): Session processing for ${ELAPSED}s — sending Escape (interrupt #$((COUNT+1)))" >> "$LOG"
        tmux send-keys -t aguia Escape
        echo $((COUNT+1)) > "$INTERRUPT_COUNT_FILE"
        date +%s > "$STATE_FILE"
    fi
    exit 0
fi

# Ambiguous state — NOT idle, NOT clearly working.
# This happens during tool output rendering, streaming, etc.
# DO NOT interrupt unless it's been 10+ minutes (was 120s — way too aggressive)
if [ -f "$STATE_FILE" ]; then
    STARTED=$(cat "$STATE_FILE")
    NOW=$(date +%s)
    ELAPSED=$(( NOW - STARTED ))

    # RESUME branch DISABLED 2026-04-18 (v3): was never actually triggered in
    # production (0 fires since Apr 17) and carries a prompt-injection risk —
    # the typed text becomes part of Aguia's pending input. If you need to
    # nudge a stuck session, do it manually via Telegram.
    if false && [ "$ELAPSED" -gt 120 ] \
        && echo "$PANE" | grep -q 'Interrupted · What should Claude do instead?' \
        && echo "$PANE" | tail -3 | grep -qE '^❯ *$'; then
        echo "$(date +%H:%M:%S): RESUME — Interrupted+empty prompt for ${ELAPSED}s, nudging session" >> "$LOG"
        tmux send-keys -t aguia "resume: continue o que estava fazendo, ou lista pending telegram messages" Enter
        date +%s > "$STATE_FILE"
        exit 0
    fi

    if [ "$ELAPSED" -gt 600 ]; then
        echo "$(date +%H:%M:%S): Ambiguous state for ${ELAPSED}s (10m+) — sending Escape" >> "$LOG"
        tmux send-keys -t aguia Escape
        rm -f "$STATE_FILE"
    fi
else
    date +%s > "$STATE_FILE"
fi

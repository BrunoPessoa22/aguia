#!/bin/bash
# LinkedIn Session Health Check v2 -- Cookie-based, no Chrome profile dependency
# Run daily via cron to keep cookies fresh.
export PATH="$HOME/.local/bin:/usr/local/bin:/usr/bin:/bin:$PATH"
LOG="$HOME/aguia/shared/logs/linkedin-session.log"
TS=$(date +%Y-%m-%dT%H:%M:%S)
echo "[$TS] LinkedIn session check v2 starting..." >> "$LOG"

python3 "$HOME/aguia/integrations/linkedin/linkedin-dm-v2.py" --check >> "$LOG" 2>&1
EXIT=$?

if [ $EXIT -ne 0 ]; then
    echo "[$(date +%Y-%m-%dT%H:%M:%S)] Session expired -- running --login" >> "$LOG"
    python3 "$HOME/aguia/integrations/linkedin/linkedin-dm-v2.py" --login >> "$LOG" 2>&1
fi

echo "[$(date +%Y-%m-%dT%H:%M:%S)] Check complete (exit: $EXIT)" >> "$LOG"

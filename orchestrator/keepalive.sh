#!/bin/bash
# AGUIA Keepalive v2 -- Hardened
# Runs every 5 min via cron/systemd timer.
# Ensures the interactive agent session is alive, responsive, and patched.

set -o pipefail
export PATH="$HOME/.local/bin:$HOME/.bun/bin:$PATH"

LOG="$HOME/aguia/shared/logs/keepalive.log"
PATCH_SRC="$HOME/aguia/patches/telegram-server.ts.patched"
TOKEN_FILE="$HOME/.claude_token"

# -- 1. TOKEN VALIDATION -------------------------------------------------
if [ ! -f "$TOKEN_FILE" ]; then
    echo "$(date): CRITICAL -- token file missing at $TOKEN_FILE" >> "$LOG"
    exit 1
fi
source "$TOKEN_FILE"
export CLAUDE_CODE_OAUTH_TOKEN
if [ -z "$CLAUDE_CODE_OAUTH_TOKEN" ]; then
    echo "$(date): CRITICAL -- CLAUDE_CODE_OAUTH_TOKEN is empty after sourcing" >> "$LOG"
    exit 1
fi

# -- 2. TELEGRAM PLUGIN PATCH --------------------------------------------
# Apply error filter to ALL plugin versions (handles auto-updates).
# If you have a patched version of the Telegram plugin server.ts that
# filters noisy errors, this ensures it stays applied across updates.
if [ -f "$PATCH_SRC" ]; then
    for PLUGIN_DIR in \
        "$HOME/.claude/plugins/cache/claude-plugins-official/telegram/"*/ \
        "$HOME/.claude/plugins/marketplaces/claude-plugins-official/external_plugins/telegram/"; do
        PLUGIN_SRC="${PLUGIN_DIR}server.ts"
        if [ -f "$PLUGIN_SRC" ] && ! grep -q 'ERROR_PATTERNS' "$PLUGIN_SRC"; then
            cp "$PATCH_SRC" "$PLUGIN_SRC"
            echo "$(date): Patched $PLUGIN_SRC" >> "$LOG"
        fi
    done
fi

# -- 3. SESSION HEALTH CHECK ---------------------------------------------
SESSION_ALIVE=false
NEEDS_RESTART=false

# The interactive session runs in a tmux session named "aguia"
if tmux has-session -t aguia 2>/dev/null; then
    SESSION_ALIVE=true

    # Check if claude process is actually running inside the session
    CLAUDE_PID=$(pgrep -f "claude --channels" 2>/dev/null | head -1)
    if [ -z "$CLAUDE_PID" ]; then
        echo "$(date): Session exists but claude process DEAD -- restarting" >> "$LOG"
        tmux kill-session -t aguia 2>/dev/null
        NEEDS_RESTART=true
    fi

    # Check if telegram bot (bun) is running
    BUN_PID=$(pgrep -f "bun.*server.ts" 2>/dev/null | head -1)
    if [ -z "$BUN_PID" ] && [ -n "$CLAUDE_PID" ]; then
        echo "$(date): Telegram plugin process not running -- restarting session" >> "$LOG"
        tmux kill-session -t aguia 2>/dev/null
        NEEDS_RESTART=true
    fi

    # Check if session is stuck (no activity for 2+ hours during work hours)
    # Skip this check between 22:00-06:00 UTC (low activity expected)
    HOUR=$(date -u +%H)
    if [ "$HOUR" -ge 6 ] && [ "$HOUR" -le 22 ]; then
        if [ -n "$CLAUDE_PID" ]; then
            CPU=$(ps -p "$CLAUDE_PID" -o %cpu= 2>/dev/null | tr -d ' ' | cut -d. -f1)
            if [ "${CPU:-0}" -eq 0 ]; then
                STATE=$(ps -p "$CLAUDE_PID" -o stat= 2>/dev/null | head -c1)
                # S = sleeping (normal when waiting for messages), T = stopped (bad)
                if [ "$STATE" = "T" ]; then
                    echo "$(date): Claude process is STOPPED (T state) -- restarting" >> "$LOG"
                    tmux kill-session -t aguia 2>/dev/null
                    NEEDS_RESTART=true
                fi
            fi
        fi
    fi
else
    NEEDS_RESTART=true
fi

# -- 3.5. TELEGRAM ACCESS GUARD ------------------------------------------
# Ensure critical users are always on the Telegram allowlist.
# Prevents lockouts when the session restarts.
ACCESS_FILE="$HOME/.claude/channels/telegram/access.json"
if [ -f "$ACCESS_FILE" ]; then
    python3 -c "
import json
# Add your Telegram user IDs here
REQUIRED_USERS = ['YOUR_TELEGRAM_USER_ID']
with open('$ACCESS_FILE') as f:
    cfg = json.load(f)
changed = False
for uid in REQUIRED_USERS:
    if uid not in cfg.get('allowFrom', []):
        cfg.setdefault('allowFrom', []).append(uid)
        changed = True
if changed:
    with open('$ACCESS_FILE', 'w') as f:
        json.dump(cfg, f, indent=2)
    print('Keepalive: restored missing users to Telegram allowlist')
" 2>/dev/null
fi

# -- 4. RESTART IF NEEDED ------------------------------------------------
if [ "$NEEDS_RESTART" = true ]; then
    sleep 2

    tmux new-session -d -s aguia "\
        export PATH=\$HOME/.local/bin:\$HOME/.bun/bin:\$PATH && \
        source $TOKEN_FILE && \
        export CLAUDE_CODE_OAUTH_TOKEN && \
        cd $HOME/aguia && \
        claude --channels plugin:telegram@claude-plugins-official --dangerously-skip-permissions --model opus"

    # Wait for Claude to initialize
    sleep 12

    # Accept the permissions prompt
    tmux send-keys -t aguia Down
    sleep 0.5
    tmux send-keys -t aguia Enter

    echo "$(date): Restarted AGUIA session (v2 keepalive)" >> "$LOG"
fi

# -- 5. AUTO-COMPACT (prevent context overflow) ---------------------------
"$HOME/aguia/orchestrator/session-health.sh" 2>/dev/null

# -- 6. DISPATCH HEALTH (ensure cron dispatches can run) ------------------
[ -x "$HOME/aguia/orchestrator/dispatch.sh" ] || chmod 700 "$HOME/aguia/orchestrator/dispatch.sh"

# -- 7. WIKI SERVER HEALTH -----------------------------------------------
# Ensure wiki API is running (serves semantic search for dispatch.sh)
if ! pgrep -f "uvicorn serve:app" > /dev/null 2>&1; then
    cd "$HOME/aguia/agents/second-brain/wiki" && \
    nohup python3 -m uvicorn serve:app --host 0.0.0.0 --port 3200 \
        >> "$HOME/aguia/shared/logs/wiki-server.log" 2>&1 &
    echo "$(date): Restarted wiki server" >> "$LOG"
fi

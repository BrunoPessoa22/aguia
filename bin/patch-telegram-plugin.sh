#!/bin/bash
# Re-apply Aguia v2 Telegram plugin patches after a Claude Code update.
#
# Background: the upstream plugin at
#   ~/.claude/plugins/cache/claude-plugins-official/telegram/<version>/
# gets overwritten on every Claude Code auto-update. Our custom patches
# (inbound debouncer, etc.) live in /home/ubuntu/aguia/bin/patches/*.py.
# This script replays them idempotently.
#
# Usage: /home/ubuntu/aguia/bin/patch-telegram-plugin.sh
#
# After running, kill the aguia tmux session so the plugin reloads:
#   tmux kill-session -t aguia   # keepalive will respawn within 60s

set -euo pipefail

PLUGIN_ROOT=/home/ubuntu/.claude/plugins/cache/claude-plugins-official/telegram
PATCHES_DIR=/home/ubuntu/aguia/bin/patches
LOG=/home/ubuntu/aguia/shared/logs/plugin-patcher.log

mkdir -p "$PATCHES_DIR"

# Find the latest installed plugin version
VERSION_DIR=$(find "$PLUGIN_ROOT" -maxdepth 1 -mindepth 1 -type d | sort -V | tail -1)
if [ -z "$VERSION_DIR" ] || [ ! -f "$VERSION_DIR/server.ts" ]; then
    echo "[$(date -u +%FT%TZ)] FATAL: no telegram plugin found under $PLUGIN_ROOT" | tee -a "$LOG"
    exit 1
fi

SERVER_TS="$VERSION_DIR/server.ts"
echo "[$(date -u +%FT%TZ)] target: $SERVER_TS" | tee -a "$LOG"

# Backup current state before patching
TS=$(date +%s)
cp "$SERVER_TS" "$SERVER_TS.bak.patcher.${TS}"
echo "[$(date -u +%FT%TZ)] backup: server.ts.bak.patcher.${TS}" | tee -a "$LOG"

# Apply every patch script in order. Each script is idempotent (re-runs as noop).
applied=0
skipped=0
for patch in "$PATCHES_DIR"/*.py; do
    [ -f "$patch" ] || continue
    name=$(basename "$patch")
    output=$(python3 "$patch" "$SERVER_TS" 2>&1 || true)
    if echo "$output" | grep -q 'already patched'; then
        skipped=$((skipped + 1))
        echo "[$(date -u +%FT%TZ)] $name: already applied" | tee -a "$LOG"
    elif echo "$output" | grep -qE 'patched|added'; then
        applied=$((applied + 1))
        echo "[$(date -u +%FT%TZ)] $name: applied — $output" | tee -a "$LOG"
    else
        echo "[$(date -u +%FT%TZ)] $name: ERROR — $output" | tee -a "$LOG"
        echo "[$(date -u +%FT%TZ)] restoring from backup" | tee -a "$LOG"
        cp "$SERVER_TS.bak.patcher.${TS}" "$SERVER_TS"
        exit 2
    fi
done

echo "[$(date -u +%FT%TZ)] summary: $applied applied, $skipped skipped" | tee -a "$LOG"

# Sanity: TS compile check via bun
if command -v bun >/dev/null 2>&1; then
    cd "$VERSION_DIR"
    if bun build --target=bun server.ts --outfile=/tmp/server.compile-check.js >/dev/null 2>&1; then
        rm -f /tmp/server.compile-check.js
        echo "[$(date -u +%FT%TZ)] bun build: OK" | tee -a "$LOG"
    else
        echo "[$(date -u +%FT%TZ)] bun build: FAILED — rolling back" | tee -a "$LOG"
        cp "$SERVER_TS.bak.patcher.${TS}" "$SERVER_TS"
        exit 3
    fi
else
    echo "[$(date -u +%FT%TZ)] bun not on PATH, skipping compile check" | tee -a "$LOG"
fi

echo "[$(date -u +%FT%TZ)] done. To activate: tmux kill-session -t aguia" | tee -a "$LOG"

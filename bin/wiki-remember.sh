#!/bin/bash
# Aguia v2 — wiki-remember
#
# Writes a "live brain" entry to /home/ubuntu/clawd/wiki/live/<date>.md.
# Entries are visible to the next SessionStart hook via <live_brain> and
# get promoted to raw/ after 24h by promote-live.sh.
#
# Usage:
#   wiki-remember.sh "TITLE" "CONTENT (markdown)" ["tag1,tag2,..."]
#
# Example:
#   wiki-remember.sh \
#     "FALCAO CB Live — tile crop 9:16 math" \
#     "h1 uses 100x80 top-left tile. h2/h3 use 320x180 top-right tile. \
#      Screen-share compression softens h1 — use HD source whenever possible." \
#     "falcao,cb-live,video,ffmpeg"
#
# Dedup: skips writes whose (title+content) hash already exists in any
# live/*.md file (cross-day dedup). Same pattern surfacing twice is noise.
#
# Env overrides:
#   WIKI_REMEMBER_SOURCE — agent name to credit (default: aguia)
#   WIKI_LIVE_DIR        — override live dir (default: /home/ubuntu/clawd/wiki/live)

set -euo pipefail

TITLE="${1:-}"
CONTENT="${2:-}"
TAGS="${3:-}"
SOURCE="${WIKI_REMEMBER_SOURCE:-aguia}"
LIVE_DIR="${WIKI_LIVE_DIR:-/home/ubuntu/clawd/wiki/live}"
LOG=/home/ubuntu/aguia/shared/logs/wiki-remember.log

if [ -z "$TITLE" ] || [ -z "$CONTENT" ]; then
    cat >&2 <<USAGE
usage: wiki-remember.sh "TITLE" "CONTENT" ["tag1,tag2,..."]

  TITLE    short, specific (e.g. "FALCAO tile crop 9:16 math")
  CONTENT  1-3 paragraphs of markdown with exact numbers/commands/paths
  TAGS     optional comma-separated
USAGE
    exit 2
fi

mkdir -p "$LIVE_DIR"
mkdir -p "$(dirname "$LOG")"

# Rate-limit: max WRITES_PER_DAY entries per source per UTC day.
# Runaway agent cannot flood live/. Bruno override: WIKI_REMEMBER_RATE_LIMIT=N
RATE_LIMIT="${WIKI_REMEMBER_RATE_LIMIT:-25}"
TODAY_UTC="$(date -u +%Y-%m-%d)"
if [ -f "$LOG" ]; then
    WRITES_TODAY=$(grep -c "^\[${TODAY_UTC}.*src:${SOURCE}[[:space:]]*)" "$LOG" 2>/dev/null || echo 0)
    if [ "${WRITES_TODAY:-0}" -ge "$RATE_LIMIT" ]; then
        echo "[$(date -u +%FT%TZ)] rate-limit: $SOURCE at ${WRITES_TODAY}/${RATE_LIMIT} today, skip \"$TITLE\"" >> "$LOG"
        exit 0
    fi
fi

TODAY=$(date -u +%Y-%m-%d)
HM=$(date -u +%H:%M)
TARGET="$LIVE_DIR/$TODAY.md"
HASH=$(printf '%s\n%s' "$TITLE" "$CONTENT" | sha256sum | cut -c1-12)

# Dedup — skip if same hash present in any live file
for F in "$LIVE_DIR"/*.md; do
    [ -f "$F" ] || continue
    if grep -q "hash:$HASH" "$F" 2>/dev/null; then
        echo "[$(date -u +%FT%TZ)] skip '$TITLE' — duplicate of hash $HASH in $(basename "$F")" >> "$LOG"
        exit 0
    fi
done

# Append entry
{
    echo
    echo "## $HM UTC — $TITLE"
    echo
    echo "$CONTENT"
    echo
    if [ -n "$TAGS" ]; then
        echo "_Tags: ${TAGS}_"
    fi
    echo "_Source: ${SOURCE}_ <!-- hash:$HASH -->"
} >> "$TARGET"

echo "[$(date -u +%FT%TZ)] wrote '$TITLE' to $TARGET (hash:$HASH, src:$SOURCE)" >> "$LOG"

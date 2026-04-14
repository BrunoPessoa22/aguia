#!/bin/bash
# AGUIA Agent Dispatcher v6
# Memory injection + Wiki context + shared context + per-agent Telegram routing
# Usage: dispatch.sh <agent-name> [--model <model>] "<task prompt>"

AGENT=$1
shift

MODEL="sonnet"
if [ "$1" = "--model" ]; then
    MODEL=$2
    shift 2
fi
TASK=$1

TIMESTAMP=$(date +%Y-%m-%dT%H:%M:%S)
TODAY=$(date +%Y-%m-%d)
BASE_DIR="$(cd "$(dirname "$0")/.." && pwd)"
LOG_DIR="$BASE_DIR/shared/logs"
AGENT_DIR="$BASE_DIR/agents/$AGENT"
MEMORY_DIR="$AGENT_DIR/memory"
WIKI_ROOT="$BASE_DIR/wiki"
WIKI_API="http://localhost:3200"

export PATH="$HOME/.local/bin:$HOME/.bun/bin:$PATH"
source "$HOME/.claude_token" && export CLAUDE_CODE_OAUTH_TOKEN

# ============================================================================
# Per-agent Telegram routing
# Configure your bot tokens and chat IDs in .env or .claude_token
# ============================================================================

OWNER_DM="${OWNER_DM:-YOUR_CHAT_ID}"
TEAM_GROUP_A="${TEAM_GROUP_A:-YOUR_TEAM_A_CHAT_ID}"
TEAM_GROUP_B="${TEAM_GROUP_B:-YOUR_TEAM_B_CHAT_ID}"

case "$AGENT" in
    # Route specific agents to specific bots/groups
    # Customize this mapping for your setup
    example-agent)
        TG_BOT="$TEAM_BOT_TOKEN"
        TG_CHAT="$TEAM_GROUP_A"
        ;;
    *)
        TG_BOT="$TELEGRAM_BOT_TOKEN"
        TG_CHAT="$OWNER_DM"
        ;;
esac

mkdir -p "$LOG_DIR" "$MEMORY_DIR"

if [ ! -d "$AGENT_DIR" ]; then
    echo "[$TIMESTAMP] ERROR: Agent $AGENT not found at $AGENT_DIR" >> "$LOG_DIR/dispatch.log"
    exit 1
fi

# ============================================================================
# SEMANTIC WIKI CONTEXT INJECTION
# Each agent gets deterministic wiki articles + semantic search augmentation
# ============================================================================
get_wiki_context() {
    local agent="$1"
    local task="$2"
    local ctx=""

    # --- Per-agent deterministic wiki injection ---
    # Map each agent to its relevant wiki articles.
    # Articles live in $WIKI_ROOT/compiled/agents/<agent-name>-*.md
    case "$agent" in
        example-agent)
            for f in "$WIKI_ROOT"/compiled/agents/example-agent-*.md; do
                [ -f "$f" ] && ctx="${ctx}\n\n$(cat "$f")"
            done
            ;;
        clawfix)
            for f in "$WIKI_ROOT"/compiled/agents/clawfix-*.md; do
                [ -f "$f" ] && ctx="${ctx}\n\n$(cat "$f")"
            done
            ;;
        second-brain)
            for f in "$WIKI_ROOT"/compiled/agents/wiki-maintenance.md \
                     "$WIKI_ROOT"/compiled/agents/karpathy-kb-pattern.md \
                     "$WIKI_ROOT"/compiled/agents/second-brain-*.md; do
                [ -f "$f" ] && ctx="${ctx}\n\n$(cat "$f")"
            done
            ;;
        # Add more agents here following the same pattern:
        # your-agent)
        #     for f in "$WIKI_ROOT"/compiled/agents/your-agent-*.md; do
        #         [ -f "$f" ] && ctx="${ctx}\n\n$(cat "$f")"
        #     done
        #     ;;
    esac

    # --- Semantic search augmentation (appends to deterministic context) ---
    # If you have a wiki API with semantic search, this queries it
    local query="${agent} ${task:0:200}"

    local semantic_result
    semantic_result=$(curl -sf --max-time 10 \
        "${WIKI_API}/wiki/semantic?$(python3 -c "import urllib.parse,sys; print('q='+urllib.parse.quote(sys.argv[1])+'&n=5&source=wiki')" "$query" 2>/dev/null)" 2>/dev/null)

    if [ -n "$semantic_result" ]; then
        local paths
        paths=$(echo "$semantic_result" | python3 -c "
import sys, json
try:
    d = json.load(sys.stdin)
    for r in d.get('results', []):
        p = r.get('metadata', {}).get('path', '')
        if p:
            print(p)
except: pass
" 2>/dev/null)

        if [ -n "$paths" ]; then
            ctx="${ctx}\n\n## Knowledge Base -- Semantically Relevant Articles (query: ${agent})"
            while IFS= read -r path; do
                [ -f "$path" ] && ctx="${ctx}\n\n$(cat "$path")"
            done <<< "$paths"
        fi
    fi

    # Fallback: inject wiki index if no context gathered at all
    if [ -z "$ctx" ] && [ -f "$WIKI_ROOT/index.md" ]; then
        ctx="$(head -50 "$WIKI_ROOT/index.md" 2>/dev/null)"
    fi

    # Safety: cap wiki context at ~400 lines
    echo "$ctx" | head -400
}

WIKI_CONTEXT="$(get_wiki_context "$AGENT" "$TASK")"

# ============================================================================
# MEMORY INJECTION
# Last 3 daily logs (50 lines each) give the agent short-term memory
# ============================================================================
MEMORY_CONTEXT=""
for f in $(ls -t "$MEMORY_DIR"/*.md 2>/dev/null | head -3); do
    MEMORY_CONTEXT="$MEMORY_CONTEXT
--- $(basename "$f") ---
$(head -50 "$f")
"
done

# ============================================================================
# SHARED CONTEXT -- cross-agent signals
# Today's briefing (written by other agents) provides fleet-wide awareness
# ============================================================================
SHARED_CONTEXT=""
if [ -f "$BASE_DIR/shared/today-briefing.md" ]; then
    SHARED_CONTEXT="$(cat "$BASE_DIR/shared/today-briefing.md")"
fi

# ============================================================================
# ASSEMBLE PROMPT
# ============================================================================
FULL_PROMPT="$TASK"
if [ -n "$WIKI_CONTEXT" ] || [ -n "$MEMORY_CONTEXT" ] || [ -n "$SHARED_CONTEXT" ]; then
    FULL_PROMPT=""
    if [ -n "$WIKI_CONTEXT" ]; then
        FULL_PROMPT="## Wiki Context (from knowledge base)
$WIKI_CONTEXT
---
"
    fi
    if [ -n "$MEMORY_CONTEXT" ]; then
        FULL_PROMPT="${FULL_PROMPT}## Recent Memory (last 3 logs)
$MEMORY_CONTEXT
---
"
    fi
    if [ -n "$SHARED_CONTEXT" ]; then
        FULL_PROMPT="${FULL_PROMPT}## Cross-Agent Briefing (today's signals from other agents)
$SHARED_CONTEXT
---
"
    fi
    FULL_PROMPT="${FULL_PROMPT}## Current Task
$TASK

IMPORTANT: After completing your task, write a brief log entry to memory/${TODAY}.md with what you found/did. If you discover reusable knowledge (API quirks, patterns, fixes, data insights), also write a raw article to the wiki raw/ directory for the wiki compiler."
fi

echo "[$TIMESTAMP] Dispatching $AGENT (model=$MODEL): ${TASK:0:100}..." >> "$LOG_DIR/dispatch.log"

cd "$AGENT_DIR"

# Timeout configuration
# Heavy agents (wiki, research, content) get more time
# Opus model needs ~5x more time than Sonnet
TIMEOUT=600
case "$AGENT" in
    second-brain|clawfix) TIMEOUT=900 ;;
esac
if [ "$MODEL" = "opus" ]; then TIMEOUT=1800; fi

OUTPUT=$(timeout $TIMEOUT claude -p "$FULL_PROMPT" \
    --model "$MODEL" \
    --permission-mode bypassPermissions \
    --max-turns 40 \
    --output-format text \
    2>&1)

EXIT_CODE=$?
echo "[$TIMESTAMP] $AGENT completed (exit: $EXIT_CODE)" >> "$LOG_DIR/dispatch.log"
echo "$OUTPUT" >> "$LOG_DIR/${AGENT}_${TODAY}.log"

# ============================================================================
# TELEGRAM REPORTING
# Each agent reports its output to the configured chat
# ============================================================================
if [ -n "$OUTPUT" ] && [ ${#OUTPUT} -gt 10 ]; then
    SUMMARY=$(echo "$OUTPUT" | head -60 | cut -c1-3800)
    TAG=$(echo "$AGENT" | tr '[:lower:]' '[:upper:]' | tr '-' ' ')

    MSG="[$TAG] $(date +%H:%M)

$SUMMARY"

    curl -sf -X POST "https://api.telegram.org/bot${TG_BOT}/sendMessage" \
        -d chat_id="$TG_CHAT" \
        --data-urlencode "text=$(echo "$MSG" | head -c 4000)" \
        --max-time 10 \
        > /dev/null 2>&1 &
fi

if [ $EXIT_CODE -ne 0 ]; then
    echo "[$TIMESTAMP] FAILED: $AGENT (exit $EXIT_CODE)" >> "$LOG_DIR/failures.log"
    curl -sf -X POST "https://api.telegram.org/bot${TG_BOT}/sendMessage" \
        -d chat_id="$TG_CHAT" \
        --data-urlencode "text=[FAIL] $AGENT failed (exit $EXIT_CODE) at $TIMESTAMP" \
        --max-time 10 \
        > /dev/null 2>&1 &
fi

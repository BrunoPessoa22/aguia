#!/bin/bash
# ÁGUIA Agent Dispatcher v6
# Memory injection + Wiki context + shared context + per-agent Telegram routing
# Usage: dispatch.sh <agent-name> [--model <model>] "<task prompt>"

AGENT=$1
shift

MODEL="claude-opus-4-7"
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
WIKI_ROOT="/home/ubuntu/clawd/wiki"
WIKI_API="http://localhost:3200"

export PATH="$HOME/.local/bin:$HOME/.bun/bin:$PATH"
source /home/ubuntu/.claude_token && export CLAUDE_CODE_OAUTH_TOKEN

# Inject project-level secrets (FAL_KEY, X_API_*, VIDEO_BUDGET_USD, ...)
# into every agent's environment. Keeps secrets out of .claude_token.
if [ -f /home/ubuntu/aguia/.env ]; then
    set -a
    # shellcheck disable=SC1091
    source /home/ubuntu/aguia/.env
    set +a
fi

# Per-agent Telegram routing

BRUNO_DM="5138814159"
FTI_GROUP="-5110457157"
CB_GROUP="-5027507793"

case "$AGENT" in
    fti-intern)
        TG_BOT="$FTI_BOT"
        TG_CHAT="$FTI_GROUP"
        ;;
    receitas)
        TG_BOT="$AGUIA_V2_BOT"
        TG_CHAT="${ANGELIKA_CHAT:-$BRUNO_DM}"
        ;;
    cbuilder|gaviao)
        TG_BOT="$CB_BOT"
        TG_CHAT="$CB_GROUP"
        ;;
    *)
        TG_BOT="$AGUIA_V2_BOT"
        TG_CHAT="$BRUNO_DM"
        ;;
esac

mkdir -p "$LOG_DIR" "$MEMORY_DIR"

if [ ! -d "$AGENT_DIR" ]; then
    echo "[$TIMESTAMP] ERROR: Agent $AGENT not found at $AGENT_DIR" >> "$LOG_DIR/dispatch.log"
    exit 1
fi

# === SEMANTIC WIKI CONTEXT INJECTION ===
get_wiki_context() {
    local agent="$1"
    local task="$2"
    local ctx=""

    # --- Per-agent deterministic wiki injection ---
    case "$agent" in
        fti-intern)
            for f in "$WIKI_ROOT"/compiled/agents/fti-intern-*.md "$WIKI_ROOT"/compiled/agents/fti-trading-*.md; do
                [ -f "$f" ] && ctx="${ctx}\n\n$(cat "$f")"
            done
            ;;
        falcao)
            for f in "$WIKI_ROOT"/compiled/agents/falcao-*.md "$WIKI_ROOT"/raw/falcao-design-system-v3.md "$WIKI_ROOT"/raw/falcao-video-pipeline.md "$WIKI_ROOT"/raw/channel-virality-x.md "$WIKI_ROOT"/raw/channel-virality-linkedin.md "$WIKI_ROOT"/raw/channel-virality-instagram.md /home/ubuntu/aguia/agents/falcao/brain/rules.yaml /home/ubuntu/aguia/agents/falcao/brain/insights-latest.md "\$WIKI_ROOT"/raw/falcao-podcast-clip-pipeline.md "$WIKI_ROOT"/raw/falcao-structure-v3.md; do
                [ -f "$f" ] && ctx="${ctx}\n\n$(cat "$f")"
            done
            ;;
        arara)
            for f in "$WIKI_ROOT"/compiled/agents/arara-*.md; do
                [ -f "$f" ] && ctx="${ctx}\n\n$(cat "$f")"
            done
            ;;
        health-coach)
            for f in "$WIKI_ROOT"/compiled/agents/health-coach-*.md; do
                [ -f "$f" ] && ctx="${ctx}\n\n$(cat "$f")"
            done
            ;;
        clawfix)
            for f in "$WIKI_ROOT"/compiled/agents/clawfix-*.md; do
                [ -f "$f" ] && ctx="${ctx}\n\n$(cat "$f")"
            done
            ;;
        aguia-core)
            for f in "$WIKI_ROOT"/compiled/agents/aguia-*.md "$WIKI_ROOT"/compiled/agents/workspace-structure.md "$WIKI_ROOT"/compiled/agents/system-blockers*.md; do
                [ -f "$f" ] && ctx="${ctx}\n\n$(cat "$f")"
            done
            ;;
        jaguar)
            for f in "$WIKI_ROOT"/compiled/agents/jaguar-*.md; do
                [ -f "$f" ] && ctx="${ctx}\n\n$(cat "$f")"
            done
            ;;
        harpia)
            for f in "$WIKI_ROOT"/compiled/agents/harpia-*.md; do
                [ -f "$f" ] && ctx="${ctx}\n\n$(cat "$f")"
            done
            ;;
        tucano)
            for f in "$WIKI_ROOT"/compiled/agents/tucano-*.md; do
                [ -f "$f" ] && ctx="${ctx}\n\n$(cat "$f")"
            done
            if [ -d "$WIKI_ROOT/compiled/podcasts" ]; then
                for f in "$WIKI_ROOT"/compiled/podcasts/*.md; do
                    [ -f "$f" ] && ctx="${ctx}\n\n$(cat "$f")"
                done
            fi
            ;;
        coruja)
            for f in "$WIKI_ROOT"/compiled/agents/coruja-*.md; do
                [ -f "$f" ] && ctx="${ctx}\n\n$(cat "$f")"
            done
            ;;
        papagaio)
            for f in "$WIKI_ROOT"/compiled/agents/papagaio-*.md; do
                [ -f "$f" ] && ctx="${ctx}\n\n$(cat "$f")"
            done
            ;;
        urubu)
            for f in "$WIKI_ROOT"/compiled/agents/urubu-*.md; do
                [ -f "$f" ] && ctx="${ctx}\n\n$(cat "$f")"
            done
            for f in "$WIKI_ROOT"/compiled/business/*.md; do
                [ -f "$f" ] && ctx="${ctx}\n\n$(cat "$f")"
            done
            ;;
        beija-flor)
            for f in "$WIKI_ROOT"/compiled/agents/beija-flor-*.md; do
                [ -f "$f" ] && ctx="${ctx}\n\n$(cat "$f")"
            done
            ;;
        cb-partnerships)
            for f in "$WIKI_ROOT"/compiled/agents/cb-partnerships-*.md; do
                [ -f "$f" ] && ctx="${ctx}\n\n$(cat "$f")"
            done
            ;;
        cb-sales)
            for f in "$WIKI_ROOT"/compiled/agents/cb-sales-*.md; do
                [ -f "$f" ] && ctx="${ctx}\n\n$(cat "$f")"
            done
            ;;
        cbuilder)
            for f in "$WIKI_ROOT"/compiled/agents/cbuilder-*.md; do
                [ -f "$f" ] && ctx="${ctx}\n\n$(cat "$f")"
            done
            ;;
        canario)
            for f in "$WIKI_ROOT"/compiled/agents/canario-*.md; do
                [ -f "$f" ] && ctx="${ctx}\n\n$(cat "$f")"
            done
            ;;
        gaviao)
            for f in "$WIKI_ROOT"/compiled/agents/gaviao-*.md; do
                [ -f "$f" ] && ctx="${ctx}\n\n$(cat "$f")"
            done
            ;;
        second-brain)
            for f in "$WIKI_ROOT"/compiled/agents/wiki-maintenance.md "$WIKI_ROOT"/compiled/agents/karpathy-kb-pattern.md "$WIKI_ROOT"/compiled/agents/second-brain-*.md; do
                [ -f "$f" ] && ctx="${ctx}\n\n$(cat "$f")"
            done
            ;;
    esac

    # --- Semantic search augmentation (appends to deterministic context) ---
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
            ctx="${ctx}\n\n## Knowledge Base — Semantically Relevant Articles (query: ${agent})"
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

# === MEMORY INJECTION ===
MEMORY_CONTEXT=""
for f in $(ls -t "$MEMORY_DIR"/*.md 2>/dev/null | head -3); do
    MEMORY_CONTEXT="$MEMORY_CONTEXT
--- $(basename "$f") ---
$(head -50 "$f")
"
done

# === SHARED CONTEXT — cross-agent signals ===
SHARED_CONTEXT=""
if [ -f "$BASE_DIR/shared/today-briefing.md" ]; then
    SHARED_CONTEXT="$(cat "$BASE_DIR/shared/today-briefing.md")"
fi

# === BRUNO VOICE DNA ===
VOICE_CONTEXT=""
if [ -f "$BASE_DIR/shared/bruno-voice.md" ]; then
    VOICE_CONTEXT="$(cat "$BASE_DIR/shared/bruno-voice.md")"
fi

# === CROSS-AGENT SIGNALS ===
SIGNALS_CONTEXT=""
if [ -f "$BASE_DIR/shared/signals.md" ]; then
    SIGNALS_CONTEXT="$(tail -30 "$BASE_DIR/shared/signals.md")"
fi

# === LIVE BRAIN — fresh unpromoted wiki-remember entries (last 48h) ===
LIVE_BRAIN_CONTEXT=""
if [ -d /home/ubuntu/clawd/wiki/live ]; then
    # Last 2 day-files, cap ~100 lines total, filter promoted entries
    LIVE_BRAIN_CONTEXT=$(find /home/ubuntu/clawd/wiki/live -maxdepth 1 -name '*.md' -mtime -2 -type f 2>/dev/null | sort -r | head -2 | xargs cat 2>/dev/null | grep -v '<!-- promoted:' | head -100)
fi

# === INSIGHT PATTERNS — per-agent guidance for what is worth writing to the wiki ===
INSIGHT_PATTERNS_CONTEXT=""
PATTERNS_FILE="/home/ubuntu/aguia/shared/insight-patterns/${AGENT}.md"
if [ -f "$PATTERNS_FILE" ]; then
    INSIGHT_PATTERNS_CONTEXT="$(cat "$PATTERNS_FILE")"
fi

# === ASSEMBLE PROMPT ===
FULL_PROMPT="$TASK"
if [ -n "$WIKI_CONTEXT" ] || [ -n "$MEMORY_CONTEXT" ] || [ -n "$SHARED_CONTEXT" ] || [ -n "$VOICE_CONTEXT" ] || [ -n "$SIGNALS_CONTEXT" ] || [ -n "$LIVE_BRAIN_CONTEXT" ] || [ -n "$INSIGHT_PATTERNS_CONTEXT" ]; then
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
    if [ -n "$VOICE_CONTEXT" ]; then
        FULL_PROMPT="${FULL_PROMPT}## Bruno Voice Guide (match this tone in ALL external comms)
$VOICE_CONTEXT
---
"
    fi
    if [ -n "$SIGNALS_CONTEXT" ]; then
        FULL_PROMPT="${FULL_PROMPT}## Cross-Agent Signals (read and act on relevant ones)
$SIGNALS_CONTEXT
---
"
    fi
    if [ -n "$LIVE_BRAIN_CONTEXT" ]; then
        FULL_PROMPT="${FULL_PROMPT}## Live Brain — fresh agent insights from last 48h (unpromoted wiki-remember entries — trust these, build on them)
$LIVE_BRAIN_CONTEXT
---
"
    fi
    if [ -n "$INSIGHT_PATTERNS_CONTEXT" ]; then
        FULL_PROMPT="${FULL_PROMPT}## Insight Patterns (what this agent should capture via wiki-remember)
$INSIGHT_PATTERNS_CONTEXT
---
"
    fi
    FULL_PROMPT="${FULL_PROMPT}## Current Task
$TASK

IMPORTANT: After completing your task:
1. Write a brief log entry to memory/${TODAY}.md with what you found/did.
2. For each reusable insight discovered during this run (API quirks, patterns, fixes, data insights, \"never do X\" rules), call:
   bash -c '/home/ubuntu/aguia/bin/wiki-remember.sh \"TITLE\" \"CONTENT\" \"'${AGENT}',topic,tag\"'
   - TITLE must be specific and searchable (e.g. \"Typefully .com substring blocks direct publish\", NOT \"bug found\").
   - CONTENT must be actionable in 1-3 paragraphs with exact commands/numbers/paths.
   - The entry lands in /home/ubuntu/clawd/wiki/live/<today>.md and becomes visible to the next agent dispatch within minutes. Dedup by content hash is automatic.
   - Self-check: \"If a sibling agent reads this 3 weeks from now, would it help them act faster?\" Yes = write. No = skip.
3. DO NOT call wiki-remember for routine task completion, heartbeats, or status updates — only for non-obvious reusable knowledge."
fi

echo "[$TIMESTAMP] Dispatching $AGENT (model=$MODEL): ${TASK:0:100}..." >> "$LOG_DIR/dispatch.log"
/home/ubuntu/aguia/bin/acp-hook.sh start "$AGENT" "$TASK" 2>/dev/null || true

cd "$AGENT_DIR"

# Opus needs more time (~5x slower than sonnet)
TIMEOUT=600
# Heavy agents get more time
case "$AGENT" in
    gaviao|harpia) TIMEOUT=1200 ;;  # Outreach agents: web research + LinkedIn DMs
    jaguar) TIMEOUT=2400 ;;  # Jaguar: LinkedIn DM flow + pipeline can take >25min when sends chain
    carcara) TIMEOUT=900 ;;  # Prediction market: heavy analysis + API calls
    second-brain|falcao|aguia-core|tucano) TIMEOUT=900 ;;
    tucano) TIMEOUT=900 ;;  # Podcast scanning: multiple web fetches
    cb-partnerships|arara|fti-intern) TIMEOUT=900 ;;
    cb-sales) TIMEOUT=1500 ;;  # 10 LinkedIn DMs sequential + research = heavy
esac
if [ "$MODEL" = "opus" ] || [[ "$MODEL" == claude-opus* ]]; then TIMEOUT=1800; fi

MAX_TURNS=40
case "$AGENT" in
    carcara) MAX_TURNS=50 ;;  # Heavy analysis: price checks + research + execution
    second-brain) MAX_TURNS=50 ;;  # Wiki processing: 150+ articles, lint, compile
    falcao) MAX_TURNS=45 ;;  # Content creation: carousel gen + publishing + engagement check
    fti-intern) MAX_TURNS=45 ;;  # Signal scan: API pulls + analysis + trade execution
    cb-sales) MAX_TURNS=60 ;;  # LinkedIn research + DM sending
    jaguar|gaviao|harpia|cb-partnerships) MAX_TURNS=60 ;;  # Outreach: web research + LinkedIn DMs
    arara) MAX_TURNS=60 ;;  # Job search: web scraping + application drafting
    tucano) MAX_TURNS=45 ;;  # Podcast scanning: web search + content extraction
esac

export WIKI_REMEMBER_SOURCE="$AGENT"
OUTPUT=$(timeout $TIMEOUT claude -p "$FULL_PROMPT" \
    --model "$MODEL" \
    --permission-mode bypassPermissions \
    --max-turns $MAX_TURNS \
    --output-format text \
    2>&1)

EXIT_CODE=$?
/home/ubuntu/aguia/bin/acp-hook.sh end "$AGENT" "$EXIT_CODE" 2>/dev/null || true
COMPLETED_TS=$(date +%Y-%m-%dT%H:%M:%S)
echo "[$COMPLETED_TS] $AGENT completed (exit: $EXIT_CODE) [${TIMEOUT}s timeout]" >> "$LOG_DIR/dispatch.log"
echo "$OUTPUT" >> "$LOG_DIR/${AGENT}_${TODAY}.log"

# === TELEGRAM REPORTING ===
if [ -n "$OUTPUT" ] && [ ${#OUTPUT} -gt 10 ]; then
    SUMMARY=$(echo "$OUTPUT" | head -60 | cut -c1-3800)
    TAG=$(echo "$AGENT" | tr '[:lower:]' '[:upper:]' | tr '-' ' ')

    MSG="[$TAG] $(date +%H:%M)

$SUMMARY"

    # Conversation-active gate (added 2026-04-18) — defer Bruno DM cron posts
    # when a user msg hit the inbox in the last 120s. Groups (FTI, CB) bypass
    # the gate. Held posts are logged to shared/held-heartbeats/ (not auto-sent).
    if [ "$TG_CHAT" = "$BRUNO_DM" ] && /home/ubuntu/aguia/bin/conv-active.sh 120; then
        HELD_DIR=/home/ubuntu/aguia/shared/held-heartbeats
        mkdir -p "$HELD_DIR"
        {
            echo "=== $COMPLETED_TS ==="
            echo "$MSG"
            echo
        } >> "$HELD_DIR/$(date +%Y-%m-%d).log"
        echo "[$COMPLETED_TS] $AGENT: held (conversation active)" >> "$LOG_DIR/dispatch.log"
    else
        curl -sf -X POST "https://api.telegram.org/bot${TG_BOT}/sendMessage" \
            -d chat_id="$TG_CHAT" \
            --data-urlencode "text=$(echo "$MSG" | head -c 4000)" \
            --max-time 10 \
            > /dev/null 2>&1 &
    fi
fi

if [ $EXIT_CODE -ne 0 ]; then
    echo "[$TIMESTAMP] FAILED: $AGENT (exit $EXIT_CODE)" >> "$LOG_DIR/failures.log"
    curl -sf -X POST "https://api.telegram.org/bot${TG_BOT}/sendMessage" \
        -d chat_id="$TG_CHAT" \
        --data-urlencode "text=[FAIL] $AGENT failed (exit $EXIT_CODE) at $TIMESTAMP" \
        --max-time 10 \
        > /dev/null 2>&1 &
fi

# NOTE: Receitas agent Telegram routing is handled via ANGELIKA_CHAT variable
# Set ANGELIKA_CHAT after she messages @aguia2_bot for the first time

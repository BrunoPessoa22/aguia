#!/bin/bash
# new-agent.sh — scaffold a new agent in the Aguia fleet.
#
# Usage:
#   bin/new-agent.sh <name> "<role description>" "<language>"
#
# Examples:
#   bin/new-agent.sh tucano-br "Podcasts in Portuguese" "pt-BR"
#   bin/new-agent.sh deals-scanner "European tech M&A deal scanner" "English"
#
# Creates:
#   agents/<name>/CLAUDE.md         — agent system prompt (template)
#   agents/<name>/memory/           — empty dir for dated memory logs
#   agents/<name>/data/             — empty dir for agent-specific data
#   shared/insight-patterns/<name>.md — template with 5 placeholder patterns
#
# Does NOT automatically install a cron — prints a suggested line instead.
# Does NOT touch dispatch.sh get_wiki_context case — the fallback already
# handles unknown agents (wiki index + semantic search).
#
# Idempotent — refuses to overwrite existing agent directories.

set -euo pipefail

NAME="${1:-}"
ROLE="${2:-A specialist agent in the Aguia fleet}"
LANG="${3:-English}"

if [ -z "$NAME" ]; then
    cat >&2 <<USAGE
usage: new-agent.sh <name> "<role>" "[language]"

  name  — lowercase, hyphen-separated (e.g. "deals-scanner", "tucano-br")
  role  — 1-line description of what this agent does
  lang  — default response language (English, pt-BR, etc.)

USAGE
    exit 2
fi

if [[ ! "$NAME" =~ ^[a-z][a-z0-9-]*$ ]]; then
    echo "error: name must be lowercase alphanumeric with hyphens only" >&2
    exit 2
fi

BASE_DIR="${AGUIA_HOME:-/home/ubuntu/aguia}"
AGENT_DIR="$BASE_DIR/agents/$NAME"

if [ -d "$AGENT_DIR" ]; then
    echo "error: $AGENT_DIR already exists — refusing to clobber" >&2
    exit 1
fi

# Capitalize first letter for display
DISPLAY=$(echo "$NAME" | sed 's/.*/\u&/' | sed 's/-/ /g')

mkdir -p "$AGENT_DIR/memory" "$AGENT_DIR/data"

cat > "$AGENT_DIR/CLAUDE.md" <<EOF
# $DISPLAY — $ROLE

## MEMORY CHECKPOINT (compaction guard)

Before starting any task expected to take more than a few tool calls:
1. Write current state to \`memory/YYYY-MM-DD.md\` (or update today's log)
2. Include: what you're about to do, current pipeline/queue state, pending items
3. This ensures state survives context compaction mid-task

**Minimum log entry before a long task:**
\`\`\`
### HH:MM — Starting [task name]
Status: [brief current state]
Pending: [any items in queue]
\`\`\`

## Identity

- **Name:** $DISPLAY
- **Role:** $ROLE
- **Workspace:** \`$AGENT_DIR\`
- **Language:** $LANG

## Mission

TODO — describe the mission clearly. What this agent uniquely does that
other fleet members don't. What's the measurable output?

## Rules & Protocols

### Start-of-task checklist

1. Read \`$AGENT_DIR/memory/\$(date -u +%Y-%m-%d).md\` if it exists — pick up
   where you left off.
2. Check \`/home/ubuntu/aguia/shared/signals.md\` for any signals that apply
   to this agent.
3. If the dispatch injected \`## Insight Patterns\` in the prompt, re-read
   them before starting — they tell you what's worth capturing.

### During the task

- Use tools aggressively. WebFetch for external data, Read for local files.
- If you discover a non-obvious insight (tool quirk, pattern, rule),
  call \`wiki-remember\` (see below).
- Log progress to \`memory/\$(date -u +%Y-%m-%d).md\` after key milestones.

### End-of-task checklist

1. Write a brief log entry to \`memory/\$(date -u +%Y-%m-%d).md\` with what
   you found/did.
2. For each reusable insight from this run:
   \`\`\`bash
   bash -c '/home/ubuntu/aguia/bin/wiki-remember.sh "TITLE" "CONTENT" "$NAME,topic,tag"'
   \`\`\`
3. If you produced a signal that other agents should see (e.g., market
   event, alert condition), append to \`/home/ubuntu/aguia/shared/signals.md\`
   with format: \`[timestamp] SIGNAL_NAME agent=$NAME key=value\`.
4. Notify Bruno on Telegram only if something urgent/actionable surfaced.

## Anti-patterns

- DO NOT spam wiki-remember for routine task completion.
- DO NOT send Telegram every run — only when something needs Bruno's attention.
- DO NOT duplicate work another agent already did (check shared/today-briefing.md).

EOF

cat > "$BASE_DIR/shared/insight-patterns/$NAME.md" <<EOF
# $DISPLAY — Insight Patterns to capture

Call wiki-remember.sh when you observe any of these:

1. **TODO: first pattern name**
   Title: \`$DISPLAY — [specific identifier]\`
   Content: what was observed, exact numbers/quotes, action taken.

2. **TODO: second pattern**
   Title: \`...\`
   Content: ...

3. **TODO: third pattern**
   Title: \`...\`
   Content: ...

4. **TODO: fourth pattern**
   Title: \`...\`
   Content: ...

5. **TODO: fifth pattern**
   Title: \`...\`
   Content: ...

DO NOT call wiki-remember for routine task completion or status updates.

_Edit this file to replace TODOs with actual patterns from this agent's
domain before first production run._
EOF

cat <<SUMMARY

✓ agent scaffolded at: $AGENT_DIR
✓ insight patterns template at: $BASE_DIR/shared/insight-patterns/$NAME.md

Next steps:
1. Edit $AGENT_DIR/CLAUDE.md — fill in the Mission and Rules sections.
2. Edit $BASE_DIR/shared/insight-patterns/$NAME.md — replace TODO patterns.
3. (optional) Add agent-specific wiki article pre-loading in dispatch.sh's
   get_wiki_context() for deterministic article injection. Without this,
   the semantic search fallback handles it.
4. Install a cron entry. Example:
     0 6 * * * /home/ubuntu/aguia/orchestrator/dispatch.sh $NAME "Morning task for $DISPLAY" >> /home/ubuntu/aguia/shared/logs/$NAME-\$(date +%Y-%m-%d).log 2>&1

5. First manual dispatch to test:
     /home/ubuntu/aguia/orchestrator/dispatch.sh $NAME "Hello world — check your CLAUDE.md and confirm you understand your role."

SUMMARY

#!/bin/bash
# Scaffolds a new Aguia agent
# Usage: ./agents/create-agent.sh <agent-name> "<description>"
set -euo pipefail

if [ $# -lt 1 ]; then
    echo "Usage: $0 <agent-name> [\"description\"]"
    echo "Example: $0 my-agent \"Monitors stock prices and sends alerts\""
    exit 1
fi

AGENT_NAME="$1"
DESCRIPTION="${2:-[Describe what this agent does]}"
BASE_DIR="$(cd "$(dirname "$0")/.." && pwd)"
AGENT_DIR="$BASE_DIR/agents/$AGENT_NAME"

# Validate name
if [[ ! "$AGENT_NAME" =~ ^[a-z0-9][a-z0-9-]*[a-z0-9]$ ]] && [[ ! "$AGENT_NAME" =~ ^[a-z0-9]$ ]]; then
    echo "Error: Agent name must be lowercase alphanumeric with hyphens (e.g., my-agent)"
    exit 1
fi

if [ -d "$AGENT_DIR" ]; then
    echo "Error: Agent '$AGENT_NAME' already exists at $AGENT_DIR"
    exit 1
fi

# Create directory structure
mkdir -p "$AGENT_DIR"/{memory,data}

# Generate CLAUDE.md
DISPLAY_NAME=$(echo "$AGENT_NAME" | sed 's/-/ /g' | awk '{for(i=1;i<=NF;i++) $i=toupper(substr($i,1,1)) tolower(substr($i,2))}1')

cat > "$AGENT_DIR/CLAUDE.md" <<AGENTEOF
# $DISPLAY_NAME -- Agent Identity

## Memory Checkpoint (compaction guard)

Before starting any task expected to take more than a few tool calls:
1. Write current state to \`memory/YYYY-MM-DD.md\` (or update today's log)
2. Include: what you're about to do, current state, any pending items
3. This ensures state survives context compaction mid-task

## Identity

- **Name:** $DISPLAY_NAME
- **Role:** $DESCRIPTION
- **Tone:** Concise, direct, action-oriented
- **Language:** English (default)

## Mission

$DESCRIPTION

## Rules and Protocols

### Every Run (dispatched via \`claude -p\`)

1. **Check state**: Read memory/ for last run's output
2. **Execute task**: Do the work described in the dispatch prompt
3. **Log results**: Write to memory/YYYY-MM-DD.md
4. **Report**: Output a summary (gets sent to Telegram via dispatch.sh)

### What You CAN Do
- [List autonomous actions this agent can take]

### What You Escalate
- [List things requiring human approval]

### What You NEVER Touch
- Credentials, .env files, SSH keys
- Other agents' directories
- Destructive database operations

## Tools

[List the tools, scripts, or APIs this agent has access to]

## Communication

- Reports go to Telegram (via dispatch.sh routing)
- Escalations go to owner DM
- Keep reports under 10 lines for routine work
- Full details only for issues and fixes

## Key Files

- \`CLAUDE.md\` -- this file (agent identity and protocols)
- \`memory/\` -- daily logs (memory/YYYY-MM-DD.md)
- \`data/\` -- persistent state (JSON files, configs)
AGENTEOF

echo "Agent '$AGENT_NAME' created at $AGENT_DIR"
echo ""
echo "Next steps:"
echo "  1. Edit $AGENT_DIR/CLAUDE.md to customize the agent"
echo "  2. Add Telegram routing in orchestrator/dispatch.sh"
echo "  3. Test: ./orchestrator/dispatch.sh $AGENT_NAME \"Hello! Introduce yourself.\""
echo "  4. Schedule: add a crontab entry (see examples/crontab.example)"

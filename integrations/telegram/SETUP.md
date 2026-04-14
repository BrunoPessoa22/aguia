# Telegram Integration

The interactive Aguia session uses Claude Code's official Telegram channel plugin.
This gives you a persistent AI agent accessible via Telegram DMs or groups.

## Prerequisites

1. Create a Telegram bot via [@BotFather](https://t.me/BotFather)
2. Save the bot token
3. Install Claude Code CLI: `npm install -g @anthropic-ai/claude-code`

## Setup

### 1. Configure the Telegram plugin

The Telegram plugin ships with Claude Code. Start the interactive session:

```bash
claude --channels plugin:telegram@claude-plugins-official \
       --dangerously-skip-permissions \
       --model opus
```

### 2. First-time setup

On first run, Claude Code will ask for your Telegram bot token.
After that, message your bot from Telegram to start interacting.

### 3. Access control

Only approved Telegram user IDs can message the bot. The keepalive script
(see `orchestrator/keepalive.sh`) ensures your user IDs stay on the allowlist.

Configure allowed users in the keepalive script's `REQUIRED_USERS` array.

## Running as a persistent session

Use tmux to keep the session alive:

```bash
tmux new-session -d -s aguia "\
    cd ~/aguia && \
    claude --channels plugin:telegram@claude-plugins-official \
           --dangerously-skip-permissions \
           --model opus"
```

The keepalive script monitors this tmux session and restarts it if it dies.

## Architecture

```
User (Telegram) -> Bot API -> Claude Code Telegram Plugin -> Claude LLM
                                                          -> Tools (Bash, Read, Write, etc.)
                                                          -> MCP servers
```

The interactive session has full tool access: it can run shell commands,
read/write files, dispatch other agents, and interact with any configured
MCP server.

## Model selection

- Use `opus` for the interactive session (highest quality for real-time conversations)
- Cron-dispatched agents use `sonnet` by default (faster, good enough for automated tasks)
- The WhatsApp handler uses `haiku` for classification and `sonnet` for responses

## Tips

- The responsiveness watchdog (`orchestrator/responsiveness-watchdog.sh`) prevents
  the session from getting stuck on long operations
- Session health (`orchestrator/session-health.sh`) auto-compacts context at 80k tokens
- The keepalive checks every 5 minutes that both claude and the telegram plugin are running

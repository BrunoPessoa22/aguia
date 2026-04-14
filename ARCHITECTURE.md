# Aguia Architecture

## System Overview

Aguia is a multi-agent system that runs entirely on Anthropic's Claude Code CLI.
It consists of:

1. **Interactive session**: A persistent Claude Code instance in a tmux session,
   connected to Telegram via the official channel plugin. This is the "brain" --
   it handles real-time conversations and can dispatch work to other agents.

2. **Cron-dispatched agents**: Specialized agents that run on schedule via
   `dispatch.sh`. Each gets its own CLAUDE.md identity, memory, and wiki context.

3. **Integration layer**: WhatsApp (WAsenderAPI webhooks), LinkedIn (Playwright),
   and Telegram (native Claude Code plugin).

4. **Knowledge base**: A Karpathy-pattern wiki where agents contribute raw knowledge
   and a curator agent compiles it into structured articles.

5. **Self-healing infrastructure**: Keepalive, watchdog, and auto-compact scripts
   that ensure the system stays responsive 24/7.

## Agent Lifecycle

```
                  CRON TRIGGER
                      |
                      v
              +---------------+
              | dispatch.sh   |
              |               |
              | 1. Find agent |
              | 2. Load memory|
              | 3. Load wiki  |
              | 4. Load shared|
              | 5. Assemble   |
              |    prompt     |
              +-------+-------+
                      |
                      v
              +---------------+
              | claude -p     |
              | --model X     |
              | --max-turns N |
              +-------+-------+
                      |
                      v
              +---------------+
              | Agent runs    |
              | - Reads files |
              | - Runs tools  |
              | - Writes logs |
              | - Calls APIs  |
              +-------+-------+
                      |
                      v
              +---------------+
              | dispatch.sh   |
              | post-exec     |
              |               |
              | 1. Log output |
              | 2. Send TG    |
              | 3. Log errors |
              +---------------+
```

### Dispatch flow in detail

1. **Agent lookup**: Verify `agents/{name}/` exists, has CLAUDE.md
2. **Memory injection**: Read last 3 files from `agents/{name}/memory/` (50 lines each)
3. **Wiki context**: Load deterministic articles for the agent + semantic search results
4. **Shared context**: Load `shared/today-briefing.md` (cross-agent signals)
5. **Prompt assembly**: Concatenate wiki + memory + shared + task prompt
6. **Execution**: `claude -p` with model, timeout, and permission bypass
7. **Reporting**: Truncate output to 4000 chars, send to agent's Telegram destination
8. **Error handling**: Log failures, send failure notification to Telegram

## Memory System

### Per-agent memory (short-term)

Each agent has a `memory/` directory. Every run, the agent writes a log entry
to `memory/YYYY-MM-DD.md`. On the next dispatch, the last 3 log files are
injected into the prompt, giving the agent awareness of recent activity.

```
agents/clawfix/memory/
  2026-04-11.md   <- injected (newest)
  2026-04-10.md   <- injected
  2026-04-09.md   <- injected
  2026-04-08.md   <- not injected (too old)
```

### Wiki context (long-term)

The wiki stores compiled knowledge articles that get injected based on agent type.
Each agent has deterministic wiki mappings (always-inject) plus semantic search
augmentation (query-based, top 5 results).

```
wiki/
  raw/              <- Source material (agent logs, web research, notes)
  compiled/
    agents/         <- Agent-specific knowledge
      clawfix-health-check.md
      clawfix-common-fixes.md
    tools/          <- Tool and API references
    domain/         <- Domain-specific knowledge
  index.md          <- Auto-generated catalog
  log.md            <- Append-only changelog
```

### Shared context (fleet-wide)

`shared/today-briefing.md` is a daily file that any agent can write to.
It provides fleet-wide awareness -- for example, if a content agent discovers
a trending topic, it writes a signal that the sales agent picks up on its next run.

### Memory compaction guard

Each agent CLAUDE.md includes a "Memory Checkpoint" section that instructs the
agent to save state to its memory file before starting long tasks. This ensures
that if Claude Code runs `/compact` mid-task (triggered by auto-compact), the
agent can recover its progress.

## Session Management

### Interactive session (tmux)

The main Aguia instance runs in a tmux session with the Telegram channel plugin:

```bash
tmux new-session -d -s aguia "claude --channels plugin:telegram@claude-plugins-official \
    --dangerously-skip-permissions --model opus"
```

### Keepalive (every 5 minutes)

1. **Token validation**: Verify OAuth token file exists and is non-empty
2. **Plugin patch**: Apply error filter patches to Telegram plugin (survives auto-updates)
3. **Session health**:
   - tmux session exists?
   - Claude process running inside it?
   - Telegram plugin (bun) process running?
   - Process not in stopped (T) state?
4. **Access guard**: Ensure required Telegram user IDs are on the allowlist
5. **Restart if needed**: Kill dead session, start fresh, accept permissions prompt
6. **Auto-compact**: Trigger session-health.sh to compact if context > 80k tokens
7. **Dispatch health**: Verify dispatch.sh is executable
8. **Wiki server health**: Ensure the semantic search API is running

### Responsiveness watchdog (every minute)

Solves a critical problem: when Claude is thinking or running a long tool call,
incoming Telegram messages queue up. Users get no response for minutes.

The watchdog:
1. Captures tmux pane content
2. Checks if session is idle (at prompt) or processing
3. If processing for >90 seconds, sends Escape to interrupt
4. Checks if interrupt worked, resets timer if not
5. Also triggers /compact at 50k tokens when idle

### Auto-compact

Two layers:
- **session-health.sh**: Compacts at 80k tokens (called by keepalive)
- **responsiveness-watchdog.sh**: Compacts at 50k tokens (runs every minute)

This prevents the interactive session from hitting context limits and degrading.

## Integration Layer

### Telegram (native)

Uses Claude Code's official Telegram channel plugin. The interactive session
IS the Telegram bot -- messages come in, Claude processes them, responses go out.

Access control via allowlist (Telegram user IDs).

### WhatsApp (WAsenderAPI)

A FastAPI webhook handler receives WhatsApp messages from WAsenderAPI:

1. **Mention detection**: Only responds when @aguia or the bot emoji is in the message
2. **Security**: Prompt injection patterns are blocked
3. **Rate limiting**: 3 messages/min per sender, 5s cooldown per group
4. **Model routing**: Haiku classifies complexity, then routes to Haiku/Sonnet
5. **Tier system**: Groups mapped to tiers (public/team/off) with different knowledge bases
6. **Response**: Claude generates response, sent back via WAsenderAPI

### LinkedIn (Playwright)

Browser automation for LinkedIn interactions:

- **DM sender**: Navigate to profile -> click Message -> type -> send
- **Comment scraper**: Monitor posts -> detect trigger words -> auto-DM responders
- **Session management**: Cookie-based auth, daily refresh, auto re-login

All scripts use ephemeral browser contexts with injected cookies. No persistent
Chrome profiles (which are fragile on headless servers).

## Security Model

### Plugin allowlist

The interactive session runs with `--dangerously-skip-permissions` to avoid
blocking on permission prompts. This is necessary for autonomous operation but
means the CLAUDE.md is the primary security boundary.

### Prompt injection detection

The WhatsApp handler scans incoming messages for injection patterns:
- "ignore previous instructions"
- "repeat your system prompt"
- "you are now DAN"
- etc.

Detected injections are silently blocked and logged.

### Rate limiting

- WhatsApp: 3 messages/min per sender, 5s cooldown per group
- LinkedIn: 45-90s delay between DMs, max 5 per run
- Cron dispatches: Fixed schedules with appropriate timeouts

### Access control

- Telegram: User ID allowlist, maintained by keepalive
- WhatsApp: Group tier system (off by default)
- LinkedIn: Cookie-based, daily session verification

### Agent sandboxing

Each agent runs as a separate `claude -p` process with:
- Its own working directory (`agents/{name}/`)
- Its own CLAUDE.md defining boundaries
- Explicit lists of what it can and cannot touch
- Timeout enforcement via `timeout` command

## Performance Considerations

### Model selection

| Task | Model | Timeout | Reason |
|------|-------|---------|--------|
| Interactive chat | Opus | N/A (persistent) | Highest quality for real-time |
| Routine cron tasks | Sonnet | 600s | Good balance of speed/quality |
| Heavy agents (wiki, research) | Sonnet | 900s | More turns needed |
| Complex cron tasks | Opus | 1800s | ~5x slower than Sonnet |
| Classification | Haiku | 15s | Speed is all that matters |

### Resource usage

On a t3.small (2 vCPU, 2 GB RAM):
- Interactive session: ~200-400 MB RSS
- Each cron dispatch: ~150-300 MB (process exits after completion)
- Peak: Interactive + 1-2 concurrent dispatches = ~1 GB
- The tmux session is lightweight (~5 MB)

### Context management

- Interactive session: Compact at 50k tokens (watchdog) or 80k tokens (session-health)
- Cron agents: Fresh context every run (no accumulation)
- Wiki articles: Capped at 400 lines per agent per dispatch
- Memory injection: Last 3 logs, 50 lines each = ~150 lines max

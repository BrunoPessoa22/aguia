# Aguia -- Multi-Agent System for Claude Code CLI

A production multi-agent system built natively on [Anthropic's Claude Code CLI](https://docs.anthropic.com/en/docs/claude-code). 20+ autonomous agents running on a single EC2 instance with Telegram, WhatsApp, and LinkedIn integration. **Zero API cost** -- uses OAuth authentication (free tier).

This is not a framework or a library. It's a battle-tested production system that has been running 24/7 since early 2026, processing 24+ automated dispatches per day across 20 specialized agents.

## Architecture

```
                          +------------------+
                          |   Telegram Bot   |
                          | (Claude Code     |
                          |  Channel Plugin) |
                          +--------+---------+
                                   |
                          +--------v---------+
                          |  AGUIA (Opus)    |
                          |  Interactive     |
                          |  tmux session    |
                          +--------+---------+
                                   |
              +--------------------+--------------------+
              |                    |                    |
     +--------v-------+  +--------v-------+  +--------v-------+
     | Keepalive      |  | Responsiveness |  | Session Health |
     | (every 5 min)  |  | Watchdog       |  | Auto-compact   |
     |                |  | (every 1 min)  |  | at 50-80k tok  |
     +----------------+  +----------------+  +----------------+

     +-----------------------------------------------------------+
     |                    dispatch.sh v6                          |
     |  Memory Injection + Wiki Context + Model Routing          |
     +----+------+------+------+------+------+------+------+----+
          |      |      |      |      |      |      |      |
        +-v-+  +-v-+  +-v-+  +-v-+  +-v-+  +-v-+  +-v-+  +-v-+
        |A1 |  |A2 |  |A3 |  |A4 |  |A5 |  |A6 |  |A7 |  |...|
        +---+  +---+  +---+  +---+  +---+  +---+  +---+  +---+
        Each agent: own CLAUDE.md, memory/, data/, wiki context

     +-----------------------------------------------------------+
     |                   Integrations                            |
     |  Telegram | WhatsApp (WAsenderAPI) | LinkedIn (Playwright)|
     +-----------------------------------------------------------+

     +-----------------------------------------------------------+
     |              Wiki / Second Brain                          |
     |  raw/ -> compiled/ -> index.md (Karpathy KB pattern)     |
     |  Semantic search API on port 3200                        |
     +-----------------------------------------------------------+
```

## What Makes This Different

- **Native Claude Code**: No wrappers, no SDKs, no API calls. Just `claude -p` for cron agents and `claude --channels` for interactive sessions
- **Zero API cost**: Uses Claude Code OAuth (free). The only costs are your VPS (~$5-20/mo) and optional WAsenderAPI (~$6/mo)
- **Memory injection**: Each agent gets its last 3 daily logs + relevant wiki articles injected into every prompt
- **Model load balancing**: Haiku for classification, Sonnet for routine tasks, Opus for complex/interactive work
- **Self-healing**: Keepalive restarts dead sessions, watchdog interrupts stuck ones, auto-compact prevents context overflow
- **Wiki knowledge base**: Karpathy pattern -- agents discover knowledge, write raw articles, the wiki compiler distills them, all agents benefit

## Prerequisites

- **Claude Code CLI**: `npm install -g @anthropic-ai/claude-code` then `claude auth login`
- **VPS/EC2**: Any Linux server with 2+ GB RAM (tested on t3.small)
- **tmux**: For persistent interactive sessions
- **Python 3.10+**: For WhatsApp/LinkedIn integrations
- **Bun**: For the Telegram plugin runtime
- **Optional**: Telegram bot token (via @BotFather), WAsenderAPI account, Chrome/Chromium (for LinkedIn)

## Quick Start

### 1. Clone and configure

```bash
git clone https://github.com/BrunoPessoa22/aguia.git ~/aguia
cd ~/aguia
cp .env.example .env
# Edit .env with your tokens and chat IDs
```

### 2. Set up Claude Code OAuth

```bash
claude auth login
# This opens a browser for OAuth -- after auth, your token is saved locally
# Export it for cron jobs:
echo "export CLAUDE_CODE_OAUTH_TOKEN=$(claude auth token)" > ~/.claude_token
```

### 3. Create your first agent

```bash
mkdir -p agents/my-agent/memory
cp agents/example-agent/CLAUDE.md agents/my-agent/CLAUDE.md
# Edit CLAUDE.md to define your agent's identity and rules
```

### 4. Test a dispatch

```bash
./orchestrator/dispatch.sh my-agent "Hello! Introduce yourself and write a log entry."
# Check output:
cat shared/logs/my-agent_$(date +%Y-%m-%d).log
```

### 5. Start the interactive session

```bash
# Source your token
source ~/.claude_token && export CLAUDE_CODE_OAUTH_TOKEN

# Start in tmux
tmux new-session -d -s aguia "\
    cd ~/aguia && \
    claude --channels plugin:telegram@claude-plugins-official \
           --dangerously-skip-permissions --model opus"
```

### 6. Set up keepalive

```bash
chmod +x orchestrator/*.sh
# Add to crontab:
crontab -e
# */5 * * * * ~/aguia/orchestrator/keepalive.sh
# * * * * * ~/aguia/orchestrator/responsiveness-watchdog.sh
```

## How dispatch.sh Works

The dispatcher is the core of the system. When a cron job fires:

1. **Agent lookup**: Finds the agent directory with its CLAUDE.md
2. **Memory injection**: Reads the agent's last 3 daily log files (50 lines each)
3. **Wiki context**: Loads deterministic wiki articles for the agent + semantic search results
4. **Shared context**: Injects today's cross-agent briefing (written by other agents)
5. **Telegram routing**: Maps the agent to the correct bot token and chat ID
6. **Model selection**: Uses the specified model (default: sonnet, override with `--model opus`)
7. **Execution**: Runs `claude -p` with the assembled prompt, with appropriate timeout
8. **Reporting**: Sends output summary to Telegram, logs failures

```bash
# Basic dispatch
./orchestrator/dispatch.sh my-agent "Check the API health"

# With model override
./orchestrator/dispatch.sh my-agent --model opus "Write a detailed analysis"

# Typical cron entry
0 8 * * * ~/aguia/orchestrator/dispatch.sh clawfix "Run health check"
```

## How to Create a New Agent

1. Create the agent directory:
   ```bash
   mkdir -p agents/my-agent/{memory,data}
   ```

2. Write the CLAUDE.md (see `agents/example-agent/CLAUDE.md` for template):
   - Identity (name, role, tone)
   - Mission (one paragraph)
   - Rules and protocols (what to do each run)
   - Autonomous actions vs. escalation boundaries
   - Communication preferences

3. Add Telegram routing in `orchestrator/dispatch.sh`:
   ```bash
   my-agent)
       TG_BOT="$MY_BOT_TOKEN"
       TG_CHAT="$MY_CHAT_ID"
       ;;
   ```

4. Add wiki context mapping (optional):
   ```bash
   my-agent)
       for f in "$WIKI_ROOT"/compiled/agents/my-agent-*.md; do
           [ -f "$f" ] && ctx="${ctx}\n\n$(cat "$f")"
       done
       ;;
   ```

5. Schedule it:
   ```crontab
   0 */6 * * * ~/aguia/orchestrator/dispatch.sh my-agent "Do your thing"
   ```

## Telegram Integration

The interactive session uses Claude Code's official Telegram channel plugin.
See `integrations/telegram/SETUP.md` for detailed setup instructions.

Key features:
- Persistent AI agent accessible via Telegram DMs
- User allowlist for access control
- Auto-restart via keepalive if the session dies
- Responsiveness watchdog prevents stuck sessions

## WhatsApp Integration

Uses [WAsenderAPI](https://wasenderapi.com) (~$6/month) for WhatsApp messaging.
See `integrations/whatsapp/README.md` for setup.

Key features:
- Mention detection (@aguia, bot emoji, case-insensitive)
- Model load balancing (Haiku for simple, Sonnet for complex)
- Per-group tier system with custom knowledge bases
- Prompt injection detection
- Rate limiting and cooldown

## LinkedIn Integration

Playwright-based automation for LinkedIn DMs and comment scraping.
See `integrations/linkedin/` for scripts.

Key features:
- Cookie-based authentication (no persistent Chrome profile)
- Auto-login and session refresh
- Comment scraping with trigger word detection
- Batch DM sending with human-like delays
- Daily session health check

## Model Load Balancing

Different tasks need different models. The system uses three tiers:

| Model | Use Case | Speed | Cost |
|-------|----------|-------|------|
| Haiku | Classification, simple Q&A, routing | Fast | Free (OAuth) |
| Sonnet | Routine agent tasks, code generation, analysis | Medium | Free (OAuth) |
| Opus | Interactive session, complex reasoning, content | Slow | Free (OAuth) |

The WhatsApp handler auto-classifies incoming questions and routes to the cheapest
adequate model. Cron dispatches default to Sonnet but can override with `--model opus`.

## Cost Breakdown

| Component | Cost | Notes |
|-----------|------|-------|
| Claude Code CLI | **Free** | OAuth authentication, no API charges |
| VPS (EC2 t3.small) | ~$15/mo | 2 vCPU, 2 GB RAM. A $5/mo VPS works too |
| WAsenderAPI | ~$6/mo | Optional -- only if you want WhatsApp |
| Telegram Bot | **Free** | Via @BotFather |
| LinkedIn | **Free** | Uses your existing account |
| **Total** | **$5-21/mo** | For 20+ autonomous agents |

## Project Structure

```
aguia/
  orchestrator/
    dispatch.sh              # Agent dispatcher with memory/wiki injection
    keepalive.sh             # Session health monitor and auto-restart
    session-health.sh        # Auto-compact at high context usage
    responsiveness-watchdog.sh  # Interrupt stuck sessions
  agents/
    CLAUDE.md                # Main orchestrator identity
    example-agent/CLAUDE.md  # Agent template
    clawfix/CLAUDE.md        # Health check agent template
    second-brain/CLAUDE.md   # Wiki curator template
  integrations/
    telegram/SETUP.md        # Telegram setup guide
    whatsapp/                # WhatsApp webhook handler
    linkedin/                # LinkedIn DM and scraping scripts
  systemd/                   # Systemd service/timer files
  scripts/                   # Utility scripts
  shared/
    logs/                    # Shared log directory
    memory/                  # Cross-agent shared state
```

## FAQ

**Q: Does this really cost nothing for the AI?**
A: Yes. Claude Code CLI uses OAuth authentication which is free. You only pay for
your server and optional integrations.

**Q: How many agents can I run?**
A: We run 20+ on a single t3.small (2 GB RAM). Each cron dispatch is a separate
`claude -p` process that runs and exits. The only persistent process is the
interactive Telegram session.

**Q: What if the interactive session crashes?**
A: The keepalive script checks every 5 minutes and restarts it automatically.
It also re-applies any plugin patches and verifies the Telegram access allowlist.

**Q: How do agents share knowledge?**
A: Three mechanisms: (1) Memory injection -- each agent reads its own daily logs,
(2) Wiki context -- compiled articles get injected based on agent type,
(3) Shared briefing -- agents write to `shared/today-briefing.md` for fleet-wide signals.

**Q: Can I use this with GPT-4 / other models?**
A: This system is built specifically for Claude Code CLI. The dispatch, keepalive,
and session management all depend on Claude Code's CLI interface and plugin system.

## License

MIT -- see [LICENSE](LICENSE).

## Credits

Built by [Bruno Pessoa](https://github.com/BrunoPessoa22). Powered by
[Anthropic's Claude Code CLI](https://docs.anthropic.com/en/docs/claude-code).

Inspired by Andrej Karpathy's [LLM Knowledge Base pattern](https://karpathy.ai/)
for the wiki/second-brain system.

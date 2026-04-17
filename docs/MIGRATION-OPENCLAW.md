# Migrating from OpenClaw to Aguia (Claude Code CLI + Second Brain)

If you're running an agent fleet on OpenClaw and considering the move to native Claude Code CLI, this is the porting guide. **Takes ~4 hours of focused work for a fleet of ~5 agents, ~1 day for 20+.**

## Why migrate

OpenClaw is a fine orchestration layer on top of an API-call abstraction. It works. What you gain going native:

- **Zero API cost** — Claude Code OAuth is free (Pro/Max subscription covers it). OpenClaw-via-API runs you $200-2000/month depending on volume.
- **Native Claude Code features**: sub-agents, MCP servers, skills, hooks, `/compact`, checkpoints. None of these exist in OpenClaw's abstraction.
- **No vendor lock-in**: dispatch.sh is 236 lines of bash. If you leave Aguia, you read the code. Nothing proprietary.
- **Single process model**: one interactive `claude --channels` session + cron-based `claude -p` dispatches. OpenClaw's worker/server/agent split becomes one conceptual unit.
- **The Second Brain pattern** (this repo): agents write raw articles, compiler distills, fleet-wide semantic search. OpenClaw doesn't ship this.

What you lose:
- OpenClaw's web UI (Aguia is terminal + Telegram)
- Their managed cron (you run system cron + systemd timers)
- Their message router (replaced by Claude Code Telegram plugin)

## Concept mapping

| OpenClaw concept | Aguia equivalent | Notes |
|---|---|---|
| **Agent** | Directory in `agents/<name>/` with `CLAUDE.md`, `memory/`, `data/` | Identity lives in CLAUDE.md (rules, persona, tools). State lives in memory/ (daily logs). |
| **Workflow / Flow** | A cron entry that calls `dispatch.sh <agent> "task prompt"` | Multi-step flows become sequential dispatches or a single long-task prompt. Claude handles the step orchestration inside. |
| **Skill** | Either (a) a Claude Code skill in `~/.claude/skills/` or (b) an inline section in the agent's CLAUDE.md | Built-in Claude Code skills (hooks, MCP) are more powerful. |
| **Cron job (payload.model)** | System crontab entry with `--model claude-opus-4-7` | Pin full IDs — see [LESSONS.md #1](LESSONS.md). |
| **Message channel** | Claude Code Telegram plugin (`claude --channels plugin:telegram@...`) | Plus WhatsApp bridge via `scripts/wa-webhook-handler.py` if needed. |
| **Memory store** | `agents/<name>/memory/YYYY-MM-DD.md` + wiki injection | `dispatch.sh` auto-injects last 3 daily logs + relevant wiki articles. |
| **Health check** | `agents/clawfix/CLAUDE.md` + cron every 4-6h | Template included. |
| **Scheduled agent** | Standard cron entry calling `dispatch.sh` | No custom scheduler needed. |
| **Global config / env** | `~/.env` file sourced by `dispatch.sh` | Plain dotenv. |
| **Rate limits** | Inline in CLAUDE.md + rate-limiting wrapper scripts | Example: `scripts/publishing/falcao-x-media-post.py` has retry + queue. |
| **Workflow variables** | Agent's `data/` directory (JSON files) | Agents read/write their own JSON state. |
| **Tool definitions** | Claude Code built-ins (Bash, Read, Write, Edit, Grep, WebFetch, WebSearch) + MCP servers | Nothing to port — Claude Code has them. |
| **API cost management** | N/A — uses OAuth, free under Pro/Max | Monitor via Claude Code's `/usage` command. |

## Step-by-step port

### 1. Export your OpenClaw state

```bash
openclaw agent list --json > openclaw-agents.json
openclaw cron list --json > openclaw-crons.json
openclaw memory dump --all > openclaw-memory-backup/
```

### 2. Install Aguia

```bash
git clone https://github.com/BrunoPessoa22/aguia.git ~/aguia
cd ~/aguia
./install.sh
```

`install.sh` creates directories, installs Claude Code CLI if missing, runs `claude auth login`, sets up the Telegram plugin, and drops example agents in place.

### 3. Port your first agent (example)

Say you had an OpenClaw agent `research-agent` with:
- Model: `claude-opus-4-7`
- Workflow: "every day at 09:00, search arxiv for RL papers, summarize top 3, post to Slack"
- Memory: a JSON file tracking what was already posted

Port it:

```bash
cd ~/aguia
cp -r agents/example-agent agents/research-agent
```

Edit `agents/research-agent/CLAUDE.md`:

```markdown
# Research Agent

## Identity
You scan arxiv cs.LG daily for RL papers and post top 3 to Slack.

## Memory
`memory/YYYY-MM-DD.md` with papers you've summarized (so you don't repeat).

## Task (what cron dispatches you to do)
1. WebFetch arxiv.org/list/cs.LG/new
2. Read memory/YYYY-MM-DD-1.md to see what was posted yesterday
3. Pick 3 new papers (RL-relevant, not already posted)
4. Draft 3-sentence summary per paper
5. POST to Slack via webhook (see $SLACK_WEBHOOK in .env)
6. Write memory/YYYY-MM-DD.md with IDs of posted papers

## Compliance
- Never claim a paper proves X without hedging
- Always include arxiv ID
```

Add cron entry:

```cron
0 9 * * * $HOME/aguia/orchestrator/dispatch.sh research-agent --model claude-opus-4-7 "Daily arxiv RL scan — see CLAUDE.md" >> $HOME/aguia/shared/logs/research-agent.log 2>&1
```

That's it. The agent runs daily via cron, loads its CLAUDE.md + last 3 daily memory logs + any wiki articles about "research-agent" + the task prompt, and does the work.

### 4. Turn on Second Brain (optional but recommended)

```bash
cd ~/aguia/agents/second-brain
pip install --user --break-system-packages fastapi uvicorn sentence-transformers faiss-cpu
nohup python3 -m uvicorn serve:app --host 0.0.0.0 --port 3200 > ../../shared/logs/wiki-server.log 2>&1 &
```

Now when your research agent discovers something reusable ("arxiv API rate-limits at 3 requests/sec after 100 requests in 1min"), it writes it to `$WIKI_ROOT/raw/research-agent/arxiv-rate-limit-pattern.md`. Tonight's `second-brain` cron compiles it into `$WIKI_ROOT/compiled/agents/research-agent-arxiv-patterns.md`. Tomorrow's dispatch auto-injects that compiled article into the research-agent's context.

Compound learning, zero manual work.

### 5. Port the rest

For each OpenClaw agent:
1. Read its workflow definition
2. Translate the goal + constraints into a CLAUDE.md
3. Drop relevant skills/hooks/MCP servers
4. Add cron entry with pinned model ID
5. Move its historical memory into `agents/<name>/memory/` as markdown logs
6. Test: `./orchestrator/dispatch.sh <name> "test run"` — watch the output, fix issues

Typical porting takes 15-30 min per agent after you've done 2-3.

### 6. Kill OpenClaw

When every agent has been verified working for 1 week on Aguia:

```bash
openclaw stop --all
systemctl disable openclaw
```

Don't uninstall immediately — keep it for 2-3 more weeks as a rollback. Then delete.

## Gotchas specific to the migration

### 1. OpenClaw agents ran in isolation; Aguia agents CAN share state

OpenClaw enforces agent sandboxing via `tools.fs.workspaceOnly`. Aguia doesn't. That's intentional (shared wiki, shared signals), but if you DEPENDED on sandboxing for safety, re-introduce it via:

```bash
# In agent's CLAUDE.md Compliance section:
## File system scope
You MAY only write to:
- agents/<name>/memory/
- agents/<name>/data/
- shared/logs/<name>-*.log
- clawd/wiki/raw/<name>/

You MUST NOT write to any other path.
```

Claude Code respects these constraints when given clear rules.

### 2. OpenClaw message routing → Claude Code Telegram plugin

If your OpenClaw setup used its native message bus, migrate to:

```bash
# Install the Telegram plugin (via marketplace)
claude plugin install telegram@claude-plugins-official

# Configure
cat > ~/.claude/channels/telegram/access.json <<EOF
{
  "dmPolicy": "allowlist",
  "allowFrom": ["<your-telegram-chat-id>"],
  "groups": {}
}
EOF

# Start an interactive session
tmux new-session -d -s aguia "claude --channels plugin:telegram@claude-plugins-official --dangerously-skip-permissions --model claude-opus-4-7"
```

Now messages to your Telegram bot land in the running Claude session. It can respond, dispatch agents, read files, etc.

**Allowlist gotcha**: if your chat ID isn't in `allowFrom`, the plugin SILENTLY drops messages. Took us a week to find that bug.

### 3. OpenClaw cron jobs ran in a clean workdir; Aguia cron inherits `$HOME`

`dispatch.sh` doesn't set `cd` explicitly. Make sure each agent's CLAUDE.md tells the agent what its working directory is:

```markdown
## Working directory
Your cwd when dispatched is `$AGUIA_HOME/agents/<name>/`. Paths in this CLAUDE.md are relative to there.
```

### 4. OpenClaw's skill catalog → Claude Code skills

OpenClaw skills are (mostly) prompt templates. Claude Code skills are more powerful (can define tools, hooks, MCP bindings). Port your skills to `~/.claude/skills/<skill-name>/SKILL.md`. They become slash-commands (`/skill-name`) inside any Claude session.

### 5. `--model` alias drift

OpenClaw abstracted model choice. Now you manage it. Never use `opus` / `sonnet` / `haiku` aliases in production cron — pin full IDs like `claude-opus-4-7`. The aliases rebind when Anthropic ships new versions; you want explicit control. See [LESSONS.md #1](LESSONS.md).

## Verification checklist

Before killing OpenClaw:

- [ ] All agents running 1+ week on Aguia without errors
- [ ] Memory logs being written (`ls agents/*/memory/*.md` shows recent files)
- [ ] Telegram bot responds to you in interactive session
- [ ] Cron triggers actually fire (`grep $AGENT /var/log/syslog` or check `shared/logs/dispatch.log`)
- [ ] Second Brain compile cycles producing new `compiled/` articles
- [ ] `serve.py` responds on :3200 (`curl http://localhost:3200/wiki/search?q=test`)
- [ ] No Claude Code quota overruns — `/usage` shows comfortable headroom

## Rollback plan

If something breaks mid-migration and you need OpenClaw back:

```bash
# Stop Aguia crons
crontab -r  # or manually remove Aguia entries

# Kill interactive session
tmux kill-session -t aguia

# Restart OpenClaw
systemctl enable openclaw && systemctl start openclaw
```

Agent memory is portable (just markdown files). You can move back if needed. No lock-in on either side.

## Questions?

- [LESSONS.md](LESSONS.md) — 22 production gotchas, many are OpenClaw migrants' first walls
- [Open an issue](https://github.com/BrunoPessoa22/aguia/issues) — tag with `migration`
- Architecture questions → the README + `dispatch.sh` itself (236 lines, readable)

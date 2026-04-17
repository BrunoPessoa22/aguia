# Second Brain — Karpathy KB Pattern for Agent Fleets

A personal knowledge base that your agents **build**, **query**, and **get smarter from** — with no external service required.

Inspired by Karpathy's "writing to build your own mental model" pattern, adapted for multi-agent systems: agents discover knowledge during work, dump raw articles, a weekly compiler distills them, and semantic search makes everything queryable by every other agent in the fleet.

## The shape

```
$WIKI_ROOT/
  raw/            <- agents append raw articles here as they discover things
  compiled/       <- weekly compile distills raw/ into canonical articles
    agents/       <- per-agent knowledge (auto-injected into that agent's dispatches)
    business/
    health/
    sports/
    tools/
  index.md        <- top-level index with links
  lint.md         <- quality issues the compiler flagged
  log.md          <- compile run history
```

## Components

| File | What it does |
|---|---|
| `CLAUDE.md` | Agent rules — how to lint, compile, which raw → which compiled folder, link hygiene |
| `serve.py` | FastAPI server on port 3200. Endpoints: `/wiki/search?q=...`, `/wiki/semantic?q=...&n=5`. Used by `dispatch.sh` for per-agent context injection |
| `knowledge_index.py` | Rebuilds the embedding index (FAISS or SQLite-VSS depending on deps). Re-run after compile cycles. |
| `mcp_knowledge.py` | MCP server exposing the wiki as a tool to Claude Code sessions (so you can `/search` the wiki directly in an interactive session) |

## Setup

```bash
# Install
pip install --user --break-system-packages fastapi uvicorn sentence-transformers faiss-cpu

# Directory structure
mkdir -p $AGUIA_HOME/clawd/wiki/{raw,compiled/{agents,business,health,sports,tools}}
# $WIKI_ROOT in scripts = $AGUIA_HOME/clawd/wiki (set in your .env)

# Run the search server (port 3200, used by dispatch.sh wiki context injection)
cd $AGUIA_HOME/agents/second-brain
nohup python3 -m uvicorn serve:app --host 0.0.0.0 --port 3200 > $AGUIA_HOME/shared/logs/wiki-server.log 2>&1 &

# Build initial index
python3 knowledge_index.py
```

Or via systemd unit (create `/etc/systemd/system/aguia-wiki.service`):

```ini
[Unit]
Description=Aguia Wiki Server
After=network.target

[Service]
Type=simple
User=ubuntu
WorkingDirectory=/home/ubuntu/aguia/agents/second-brain
ExecStart=/usr/bin/python3 -m uvicorn serve:app --host 0.0.0.0 --port 3200
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

## How agents USE it

1. **Write to raw/**: Agents that discover reusable knowledge during work (a pattern, a fix, an API quirk) append a markdown article to `$WIKI_ROOT/raw/{category}/{slug}.md`.

2. **Dispatch context injection**: `dispatch.sh` for each agent:
   - Cat-concatenates `$WIKI_ROOT/compiled/agents/{agent-name}-*.md` into the agent's prompt
   - Queries `serve.py` for semantically-related articles: `GET /wiki/semantic?q={agent}+{task}&n=5`
   - Result: each agent run starts with the fleet's distilled knowledge relevant to this specific task.

3. **Daily compile**: The `second-brain` agent runs 2x/day (cron), reads `raw/`, applies lint rules (no duplicate slugs, required frontmatter, link hygiene), merges related articles, writes to `compiled/`, updates `index.md`.

4. **Weekly re-index**: `knowledge_index.py` regenerates embeddings so semantic search stays fresh.

## Cron (recommended)

```cron
# Daily harvest (agent reads last day's memory, extracts patterns, writes to raw/)
0 6 * * * /home/ubuntu/aguia/orchestrator/dispatch.sh second-brain "Morning knowledge harvest..."

# Daily compile (reads raw/, distills to compiled/)
0 20 * * * /home/ubuntu/aguia/orchestrator/dispatch.sh second-brain "Evening wiki maintenance..."

# Re-index after compile
30 20 * * * cd $AGUIA_HOME/agents/second-brain && python3 knowledge_index.py >> $AGUIA_HOME/shared/logs/knowledge-index.log 2>&1
```

## Obsidian sync (optional)

If you keep a local Obsidian vault, bidirectional rsync every 15 min keeps both sides in sync:

```cron
*/15 * * * * rsync -avz --delete /path/to/ObsidianVault/ user@server:$WIKI_ROOT/ 2>&1
*/15 * * * * rsync -avz user@server:$WIKI_ROOT/compiled/ /path/to/ObsidianVault/compiled/ 2>&1
```

Agents write to `raw/`, you read/edit in Obsidian's visual graph view.

## Why this matters for an agent fleet

Without a shared knowledge store, each agent starts every run cold. They rediscover the same LinkedIn selector, the same rate-limit, the same fact — every single time. Compute waste + quality inconsistency.

With Second Brain:
- Falcão discovers the brandsdecoded typography style → writes it to wiki raw → next Monday all content agents see it in context
- ARARA finds a new job board with good API → writes it → Jaguar + CB-Sales inherit the hit
- A new model release (Opus 4.7) gets documented once → every agent's context now includes the migration pattern

It's compound interest on agent learning.

## What "Karpathy pattern" means

Andrej Karpathy wrote about using a personal wiki as a durable second brain for engineers. The pattern:

1. **Everything interesting gets written down** — even if sloppy, even as bullet points
2. **Write for your future self first** — you'll come back to these articles in 6 months
3. **The act of writing distills the idea** — if you can't write it, you don't really know it
4. **Compound over years** — after 500+ articles you have an irreplaceable moat

We adapted it for agents: the writer is the fleet. The reader is the fleet + you. The result is the same — compounding knowledge.

## See also

- [docs/MIGRATION-OPENCLAW.md](../../docs/MIGRATION-OPENCLAW.md) — if you're coming from OpenClaw, this is the porting guide
- [orchestrator/dispatch.sh](../../orchestrator/dispatch.sh) — see `get_wiki_context()` for how agents get wiki articles injected

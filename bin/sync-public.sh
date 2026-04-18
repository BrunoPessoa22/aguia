#!/bin/bash
# sync-public.sh — push infra-only subset of aguia-private to BrunoPessoa22/aguia (public)
#
# Whitelist-driven: copies only paths listed below. Any agent memory,
# conversation logs, Bruno-specific data, contacts, tokens, etc. stay
# in aguia-private and never touch the public mirror.
#
# Usage:
#   /home/ubuntu/aguia/bin/sync-public.sh              # normal sync
#   /home/ubuntu/aguia/bin/sync-public.sh --dry-run    # preview without commit

set -euo pipefail
export TZ=UTC

SRC=/home/ubuntu/aguia
PUBLIC_DIR=/tmp/aguia-public
REMOTE_URL="$(cd "$SRC" && git remote get-url origin | sed 's|aguia-private|aguia|')"
DRY=${1:-}

# Whitelist — infra-only. Add here as more gets productionized.
WHITELIST=(
    ".gitignore"
    ".env.example"
    ".claude/settings.json"
    "orchestrator/dispatch.sh"
    "keepalive.sh"
    "orchestrator/session-health.sh"
    "orchestrator/responsiveness-watchdog.sh"
    "bin/aguia-session-start.py"
    "bin/conv-active.sh"
    "bin/karpathy-status.sh"
    "bin/patch-telegram-plugin.sh"
    "bin/promote-live.sh"
    "bin/wiki-remember.sh"
    "bin/sync-public.sh"
    "bin/patches/"
    "mcp/wiki-search/server.ts"
    "mcp/wiki-search/package.json"
    "shared/insight-patterns/"
)

echo "[$(date -u +%FT%TZ)] sync-public starting..."
echo "  src: $SRC"
echo "  remote: $REMOTE_URL"
echo "  local working copy: $PUBLIC_DIR"

# Clone or update public clone
if [ -d "$PUBLIC_DIR/.git" ]; then
    echo "[sync] pulling latest public"
    (cd "$PUBLIC_DIR" && git remote set-url origin "$REMOTE_URL" && git fetch origin && git reset --hard origin/main)
else
    echo "[sync] fresh clone"
    rm -rf "$PUBLIC_DIR"
    git clone --depth 1 "$REMOTE_URL" "$PUBLIC_DIR"
fi

# Identity
(cd "$PUBLIC_DIR" && git config user.name "Bruno Pessoa" && git config user.email "bmpessoa22@gmail.com")

# Copy whitelisted paths
echo "[sync] copying whitelisted paths"
for p in "${WHITELIST[@]}"; do
    if [ -e "$SRC/$p" ]; then
        mkdir -p "$PUBLIC_DIR/$(dirname "$p")"
        if [ -d "$SRC/$p" ]; then
            rsync -a --delete "$SRC/$p/" "$PUBLIC_DIR/$p/"
        else
            cp "$SRC/$p" "$PUBLIC_DIR/$p"
        fi
        echo "  + $p"
    else
        echo "  - $p (missing in source, skipped)"
    fi
done

# README — regenerated on every sync (placed in public only, never synced back)
cat > "$PUBLIC_DIR/README.md" <<'README_EOF'
# Águia — Multi-Agent Fleet on Claude Code CLI

Infrastructure for running a personal fleet of Claude Code-based agents
with durable memory, semantic wiki retrieval, and responsive Telegram
interaction — costing you zero API dollars (OAuth-only via Claude subscription).

This is the **public/reference** mirror. Build your own fleet on top of this.

## What you get

### Core loop
- **`orchestrator/dispatch.sh`** — cron dispatcher. Builds a rich prompt with
  wiki context (semantic + agent-specific), memory, cross-agent signals, voice
  DNA, live-brain, insight patterns. Invokes `claude -p` with the right model,
  timeout, turn budget.
- **`orchestrator/keepalive.sh`** — 5-min cron. Keeps the long-running
  interactive Claude Code session alive in tmux. Re-patches the Telegram
  plugin across Claude Code auto-updates.
- **`orchestrator/session-health.sh`** / **`responsiveness-watchdog.sh`** —
  measured watchdogs that `/compact` when context grows, interrupt truly stuck
  sessions, but **don't** thrash-kill on every ambiguous state (v3 safe
  thresholds).

### Durable memory (Karpathy loop)
- **`bin/wiki-remember.sh`** — CLI tool any agent can call to capture a
  non-obvious insight. Deduped by content hash. Lands in
  `/home/ubuntu/clawd/wiki/live/<today>.md`.
- **`bin/promote-live.sh`** — nightly cron. Moves 24h+ live entries to
  `wiki/raw/`, where the `second-brain` agent's 06:00/20:00 UTC cron compiles
  them into structured articles under `wiki/compiled/` with an auto-generated
  `index.md`.
- **`bin/aguia-session-start.py`** — Claude Code `SessionStart` hook.
  Injects three blocks into every fresh session (startup/resume/clear/compact):
  - `<recalled_context>` — last ~10 real user↔assistant turns, heartbeat-filtered
  - `<wiki_touchpoints>` — top-5 wiki articles matching recent topics
  - `<live_brain>` — recent unpromoted wiki-remember entries
- **`shared/insight-patterns/*.md`** — per-agent "what's worth capturing"
  guidance that dispatch.sh loads for the dispatching agent.

### Telegram plugin patches (`bin/patches/`)
- **`01_debouncer.py`** — coalesces rapid back-to-back messages per
  (chat_id, user_id) into a single MCP notification. 600ms batch / 2500ms
  absolute max hold. Media bypasses. Fixes "3 messages → only first answered".
- **`02_abort_fence.py`** — every inbound bumps a per-chat generation
  counter. The `reply` tool snapshots at start and checks between chunks;
  if superseded, edits the last-sent chunk with `[interrompido]` and stops.
  Fixes "monologues while I type".
- **`bin/patch-telegram-plugin.sh`** — idempotent wrapper that re-applies
  patches after Claude Code auto-updates the plugin.

### Semantic wiki search (MCP)
- **`mcp/wiki-search/server.ts`** — stdio MCP server exposing
  `wiki_search(query, limit)`. Wraps a FastAPI semantic-search service over
  the compiled wiki. Registered in `.claude/settings.json`.

### Monitoring
- **`bin/karpathy-status.sh`** — */30m cron. Writes a human-readable
  `karpathy-status.md` (+ machine JSON) with pipeline counts, today's
  wiki-remember activity per agent, recent promotions, and raw backlog.

## Getting started

This isn't a one-click install — it assumes Claude Code CLI with OAuth, a
Linux box, tmux, Python 3, Bun, and FastAPI for the wiki service. See
`orchestrator/keepalive.sh` for the full runtime requirements.

1. Clone this repo somewhere (e.g. `~/aguia`).
2. Copy `.env.example` → `.env` and fill in your values (Telegram bot
   token, wiki bearer, etc.).
3. Authenticate Claude Code: `claude auth login` (OAuth, no API key).
4. Install the Claude Code Telegram plugin (`/plugin install telegram`)
   and run `bin/patch-telegram-plugin.sh` to apply the debouncer + abort-fence.
5. Write a `CLAUDE.md` for your orchestrator — identity, tone, rules.
6. Add agent directories under `agents/<name>/` with their own `CLAUDE.md`.
7. Install crons: keepalive every 5 min, dispatch per agent per schedule.
8. Register the SessionStart hook + MCP server in `.claude/settings.json`
   (template included).

## Architecture

```
CONVERSAS (interactive)          CRONS (agent fleet)
    │                                │
    │  CLAUDE.md rules               │  dispatch.sh injects:
    │  "lembra / anota"              │    wiki ctx + memory +
    │                                │    signals + live-brain +
    │                                │    insight-patterns
    ▼                                ▼
      wiki-remember.sh (dedup)
            │
            ▼
    clawd/wiki/live/<today>.md (instant, visible to next session)
            │ 24h+
            ▼
    clawd/wiki/raw/<slug>.md   (via promote-live.sh at 05:30 UTC)
            │
            ▼
    clawd/wiki/compiled/*.md   (via second-brain cron at 06:00/20:00)
            │
            ▼
    index.md refresh + knowledge_index.py embedding refresh
            │
            ▼
    next SessionStart hook / dispatch semantic search picks it up
```

## License

MIT. Use, fork, share. If you build something cool on top of this, ping
[@brunompessoa](https://twitter.com/brunompessoa).

---

This mirror is auto-synced from the private working repo by
`bin/sync-public.sh`. Infra only — no conversations, memories, or
personal data.
README_EOF

# Commit if dirty
cd "$PUBLIC_DIR"
if [ -z "$(git status --short)" ]; then
    echo "[sync] public is already up-to-date, nothing to commit"
    exit 0
fi

if [ "$DRY" = "--dry-run" ]; then
    echo "[sync] DRY-RUN — would commit:"
    git status --short
    exit 0
fi

git add -A
MSG="sync: infra update from aguia-private"
git commit -m "$MSG" 2>&1 | tail -3
echo "[sync] pushing to public..."
git push origin main 2>&1 | tail -5

echo "[$(date -u +%FT%TZ)] sync-public complete."

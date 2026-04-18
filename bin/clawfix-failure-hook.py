#!/usr/bin/env python3
"""ClawFix v2 failure hook — read-only wiki-aware remediation suggestion.

Called by dispatch.sh when an agent cron exits non-zero. We:
  1. Read the last N lines of the agent's log for error context.
  2. Call the wiki semantic API with the error text.
  3. If top match score > THRESHOLD, write a suggestion markdown file
     and append a CLAWFIX_SUGGESTION signal.
  4. Exit silently otherwise — no noise on novel failures.

READ-ONLY. Never applies the fix — just surfaces the relevant prior article
so Bruno (or a future ClawFix v3 with apply logic) can act.

Usage (called from dispatch.sh):
  clawfix-failure-hook.py <agent_name> <log_path> <exit_code>
"""
from __future__ import annotations
import datetime as _dt
import json
import os
import re
import sys
import urllib.parse
import urllib.request
from pathlib import Path

WIKI_API = os.environ.get("WIKI_API", "http://localhost:3200")
ENV_FILE = Path("/home/ubuntu/aguia/.env")
SUGGESTIONS_FILE = Path("/home/ubuntu/aguia/shared/clawfix-suggestions.md")
SIGNALS_FILE = Path("/home/ubuntu/aguia/shared/signals.md")
THRESHOLD = 0.35
N_LOG_LINES = 30
N_RESULTS = 3


def _load_bearer() -> str | None:
    try:
        for line in ENV_FILE.read_text().splitlines():
            if line.startswith("WIKI_BEARER="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    except Exception:
        pass
    return None


def _extract_error(log_path: Path) -> str:
    """Pull the last N lines and try to surface error-ish content."""
    try:
        lines = log_path.read_text(errors="replace").splitlines()[-N_LOG_LINES:]
    except Exception:
        return ""
    # Join and lightly compress whitespace for semantic query
    return re.sub(r"\s+", " ", " ".join(lines))[:800]


def _semantic_search(query: str, bearer: str) -> list[dict]:
    url = f"{WIKI_API}/wiki/semantic?q={urllib.parse.quote(query)}&n={N_RESULTS}&source=wiki"
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {bearer}"})
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return data.get("results") or []
    except Exception as exc:
        sys.stderr.write(f"clawfix-failure-hook: semantic search failed: {exc}\n")
        return []


def _write_suggestion(agent: str, exit_code: int, query: str, top: dict) -> None:
    meta = top.get("metadata") or {}
    title = meta.get("title") or meta.get("rel_path") or "(untitled)"
    path = meta.get("path") or ""
    score = top.get("score", 0)
    excerpt = (top.get("excerpt") or "").replace("\n", " ").strip()[:400]

    now = _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")

    entry = (
        f"\n## {now} — {agent} failed (exit {exit_code})\n\n"
        f"**Error context (last log lines, compressed):**\n"
        f"```\n{query[:500]}\n```\n\n"
        f"**Top wiki match (score {score:.2f}):** [{title}]({path})\n\n"
        f"_Excerpt:_ {excerpt}\n\n"
        f"---\n"
    )
    try:
        SUGGESTIONS_FILE.parent.mkdir(parents=True, exist_ok=True)
        with SUGGESTIONS_FILE.open("a") as f:
            f.write(entry)
    except Exception as exc:
        sys.stderr.write(f"clawfix-failure-hook: suggestion write failed: {exc}\n")
        return

    # Emit signal
    try:
        signal = (
            f'[{now}] CLAWFIX_SUGGESTION agent={agent} exit={exit_code} '
            f'score={score:.2f} title="{title[:80]}" path={path}\n'
        )
        with SIGNALS_FILE.open("a") as f:
            f.write(signal)
    except Exception:
        pass


def main() -> int:
    if len(sys.argv) < 4:
        return 0
    agent = sys.argv[1]
    log_path = Path(sys.argv[2])
    try:
        exit_code = int(sys.argv[3])
    except ValueError:
        exit_code = -1

    if not log_path.exists():
        return 0

    query = _extract_error(log_path)
    if not query.strip() or len(query) < 20:
        return 0

    bearer = _load_bearer()
    if not bearer:
        return 0

    results = _semantic_search(f"failure: {query}", bearer)
    if not results:
        return 0

    top = results[0]
    score = float(top.get("score") or 0)
    if score < THRESHOLD:
        return 0

    _write_suggestion(agent, exit_code, query, top)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:
        sys.stderr.write(f"clawfix-failure-hook: unexpected error: {exc}\n")
        sys.exit(0)

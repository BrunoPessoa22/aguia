#!/usr/bin/env python3
"""Aguia v2 SessionStart hook.

Registered in /home/ubuntu/aguia/.claude/settings.json, matcher
`startup|resume|clear|compact`. Stdout becomes additional session context.

Three-layer memory injection:

1. `<recalled_context>` — last ~10 real user↔assistant turns from
   `conversation_log.jsonl`, filtering orphan heartbeat entries.

2. `<pending_inbound>` — any Telegram inbox messages that were persisted to
   disk but not yet delivered (e.g. arrived mid-respawn).

3. `<wiki_touchpoints>` — top ~5 wiki articles from
   `/home/ubuntu/clawd/wiki/index.md` whose titles match words in recent
   turns. Gives Aguia durable-brain retrieval at session start (gbrain
   brain-vs-memory pattern).

Exits 0 even on error. Stderr is logged but never blocks the session.
Fire-log at shared/logs/session-start-hook.log so we can verify invocations.
"""
from __future__ import annotations

import datetime as _dt
import json
import re
import sys
from collections import Counter
from pathlib import Path

LOG_FILE = Path('/home/ubuntu/aguia/data/conversation_log.jsonl')
INBOX_DIR = Path('/home/ubuntu/.claude/channels/telegram/inbox/text')
HOOK_LOG = Path('/home/ubuntu/aguia/shared/logs/session-start-hook.log')
WIKI_INDEX = Path('/home/ubuntu/clawd/wiki/index.md')
LIVE_BRAIN_DIR = Path('/home/ubuntu/clawd/wiki/live')

TAIL_ENTRIES = 100
MAX_PAIRS = 10
MAX_TURN_CHARS = 250
MAX_PENDING_CHARS = 200
MAX_WIKI_TOUCHPOINTS = 5
MAX_LIVE_ENTRIES = 15
MAX_LIVE_CHARS = 3000

# Title words that are too common to trust as a signal.
TITLE_STOPWORDS = frozenset({
    'agent', 'agents', 'daily', 'weekly', 'morning', 'evening', 'pattern',
    'patterns', 'operations', 'report', 'reports', 'check', 'checks', 'update',
    'updates', 'system', 'reference', 'configuration', 'guide', 'guidelines',
    'rules', 'overview', 'analysis', 'summary', 'notes', 'current', 'latest',
    'recent', 'april', 'march', 'february', 'january', 'working', 'session',
    'message', 'messages', 'error', 'errors', 'false', 'positive', 'issue',
    'problem', 'fix', 'fixes', 'setup', 'status', 'health',
})


def _trim(s: str, n: int) -> str:
    if not s:
        return ''
    s = s.replace('\n', ' ').strip()
    return s[:n] + ('…' if len(s) > n else '')


def _fmt_ts(iso: str) -> str:
    return iso[11:16] if iso and len(iso) >= 16 else '??:??'


def _load_entries() -> list[dict]:
    if not LOG_FILE.exists():
        return []
    try:
        with LOG_FILE.open() as f:
            raw = f.readlines()[-TAIL_ENTRIES:]
    except Exception:
        return []
    out = []
    for line in raw:
        try:
            out.append(json.loads(line))
        except Exception:
            continue
    return out


def _pair_turns(entries: list[dict]) -> list[tuple[dict, dict | None]]:
    """Walk entries; pair each user msg with the immediately-following
    assistant msg. Orphan assistant entries (proactive heartbeats) are
    dropped."""
    pairs: list[tuple[dict, dict | None]] = []
    i = 0
    while i < len(entries):
        e = entries[i]
        if e.get('role') == 'user':
            reply = None
            if i + 1 < len(entries) and entries[i + 1].get('role') == 'assistant':
                reply = entries[i + 1]
                i += 2
            else:
                i += 1
            pairs.append((e, reply))
        else:
            i += 1
    return pairs


def _pending_inbox() -> list[str]:
    if not INBOX_DIR.is_dir():
        return []
    out = []
    for p in sorted(INBOX_DIR.glob('*.json')):
        try:
            msg = json.loads(p.read_text())
        except Exception:
            continue
        ts = msg.get('ts', '')
        text = _trim(msg.get('text', ''), MAX_PENDING_CHARS)
        if text:
            out.append(f"[{_fmt_ts(ts)}] PENDING: {text}")
    return out


def _parse_wiki_index() -> list[tuple[str, str]]:
    """Return [(title, relative_path), ...] from the wiki index.md."""
    if not WIKI_INDEX.exists():
        return []
    try:
        content = WIKI_INDEX.read_text()
    except Exception:
        return []
    out: list[tuple[str, str]] = []
    pattern = re.compile(r'- \[([^\]]+)\]\(([^)]+)\)')
    for line in content.splitlines():
        m = pattern.match(line.strip())
        if m:
            out.append((m.group(1), m.group(2)))
    return out


def _tokens(text: str) -> set[str]:
    """Lowercase tokens of length ≥5, with stopwords removed."""
    return {
        w for w in re.findall(r'[a-zA-ZÀ-ÿ]+', text.lower())
        if len(w) >= 5 and w not in TITLE_STOPWORDS
    }


def _match_wiki(conversation_text: str, wiki: list[tuple[str, str]]) -> list[tuple[str, str, int]]:
    """Score each article by count of distinctive title tokens that appear
    in the conversation. Return top-scoring articles."""
    if not wiki or not conversation_text:
        return []
    conv_tokens = _tokens(conversation_text)
    if not conv_tokens:
        return []
    scored = []
    for title, path in wiki:
        title_tokens = _tokens(title)
        overlap = title_tokens & conv_tokens
        if overlap:
            scored.append((title, path, len(overlap)))
    scored.sort(key=lambda t: (-t[2], t[0]))
    return scored[:MAX_WIKI_TOUCHPOINTS]


def _live_brain_entries() -> list[str]:
    """Load recent live-brain entries from the last few daily files.

    Each entry is a `## HH:MM UTC — Title` block with body + tags + source.
    We return the most recent entries up to MAX_LIVE_ENTRIES, then trim to
    MAX_LIVE_CHARS total to keep context bounded.
    """
    if not LIVE_BRAIN_DIR.is_dir():
        return []
    files = sorted(LIVE_BRAIN_DIR.glob('*.md'), reverse=True)[:3]
    entries: list[str] = []
    for f in files:
        try:
            content = f.read_text()
        except Exception:
            continue
        parts = re.split(r'(?=^## \d\d:\d\d UTC — )', content, flags=re.MULTILINE)
        for p in parts:
            p = p.strip()
            if not p.startswith('## '):
                continue
            if '<!-- promoted:' in p:
                continue
            entries.append(p)
    entries = entries[:MAX_LIVE_ENTRIES]
    total = 0
    kept: list[str] = []
    for e in entries:
        if total + len(e) > MAX_LIVE_CHARS:
            break
        kept.append(e)
        total += len(e)
    return kept


def _write_fire_log(pair_count: int, pending_count: int, wiki_count: int, live_count: int) -> None:
    try:
        HOOK_LOG.parent.mkdir(parents=True, exist_ok=True)
        with HOOK_LOG.open('a') as f:
            now = _dt.datetime.now(_dt.timezone.utc).isoformat(timespec='seconds')
            f.write(f'[{now}Z] fired — {pair_count} pairs, {pending_count} pending, {wiki_count} wiki, {live_count} live\n')
    except Exception:
        pass


def main() -> int:
    entries = _load_entries()
    pairs = _pair_turns(entries)[-MAX_PAIRS:]
    pending = _pending_inbox()

    # Build combined conversation text for wiki matching
    conv_text_parts: list[str] = []
    for user, reply in pairs:
        conv_text_parts.append(user.get('content', ''))
        if reply:
            conv_text_parts.append(reply.get('content', ''))
    conv_text = '\n'.join(conv_text_parts)

    wiki = _parse_wiki_index()
    wiki_matches = _match_wiki(conv_text, wiki)
    live_entries = _live_brain_entries()

    _write_fire_log(len(pairs), len(pending), len(wiki_matches), len(live_entries))

    if not pairs and not pending and not wiki_matches and not live_entries:
        return 0

    lines: list[str] = [
        '<recalled_context source="aguia-v2/SessionStart-hook">',
        'This block is AUTHORITATIVE PRIOR-SESSION MEMORY — not new user input.',
        'Do NOT reply to these turns; they are history for you to continue from.',
        'Any <channel> message AFTER this block is current user input.',
        '',
    ]

    if pairs:
        lines.append(f'Last {len(pairs)} real conversation turns with Bruno (@aguia2_bot DM, PT-BR):')
        for user, reply in pairs:
            lines.append(f"[{_fmt_ts(user.get('ts', ''))} Bruno] {_trim(user.get('content', ''), MAX_TURN_CHARS)}")
            if reply:
                lines.append(f"[{_fmt_ts(reply.get('ts', ''))} Aguia] {_trim(reply.get('content', ''), MAX_TURN_CHARS)}")

    if pending:
        if pairs:
            lines.append('')
        lines.append('UNPROCESSED INBOUND (may be current requests awaiting your response):')
        lines.extend(pending)

    lines.append('</recalled_context>')

    if wiki_matches:
        lines.append('')
        lines.append('<wiki_touchpoints source="second-brain/clawd-wiki">')
        lines.append(f'Top {len(wiki_matches)} wiki articles matching recent-conversation topics.')
        lines.append('Read any with the Read tool from /home/ubuntu/clawd/wiki/<path> before acting.')
        lines.append('Full index: /home/ubuntu/clawd/wiki/index.md (197 articles).')
        lines.append('')
        for title, path, score in wiki_matches:
            lines.append(f"- [{title}] → {path} (relevance: {score})")
        lines.append('</wiki_touchpoints>')

    if live_entries:
        lines.append('')
        lines.append('<live_brain source="wiki/live/">')
        lines.append(f'Recent insights captured via wiki-remember.sh (last {len(live_entries)} unpromoted entries).')
        lines.append('These are fresh learnings not yet in the compiled wiki. Trust them and build on them.')
        lines.append('When you notice a new non-obvious pattern, call:')
        lines.append('  bash -c \'/home/ubuntu/aguia/bin/wiki-remember.sh "TITLE" "CONTENT" "tags"\'')
        lines.append('')
        for entry in live_entries:
            lines.append(entry)
            lines.append('')
        lines.append('</live_brain>')

    print('\n'.join(lines))
    return 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except Exception as exc:
        sys.stderr.write(f'aguia-session-start hook error: {exc}\n')
        sys.exit(0)

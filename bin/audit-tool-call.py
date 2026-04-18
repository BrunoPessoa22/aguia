#!/usr/bin/env python3
"""PostToolUse hook — append one JSONL row per tool call to audit log.

Registered in /home/ubuntu/aguia/.claude/settings.json under PostToolUse.
Claude Code sends JSON on stdin:
  {session_id, transcript_path, tool_name, tool_input, tool_response, ...}

We write a condensed record with timestamp, tool, input summary, success flag.
Fails closed (exit 0 on any error) — audit should NEVER block a tool call.
"""
from __future__ import annotations
import datetime as _dt
import json
import sys
from pathlib import Path

LOG = Path("/home/ubuntu/aguia/shared/logs/tool-audit.jsonl")

def main():
    try:
        raw = sys.stdin.read()
        data = json.loads(raw) if raw.strip() else {}
    except Exception:
        data = {"parse_error": True}

    tool_name = data.get("tool_name", "unknown")
    tool_input = data.get("tool_input") or {}
    tool_response = data.get("tool_response") or {}
    is_error = bool(tool_response.get("is_error")) if isinstance(tool_response, dict) else False

    # Summarize input (first 200 chars per key)
    summary = {}
    if isinstance(tool_input, dict):
        for k, v in tool_input.items():
            sv = str(v) if not isinstance(v, (list, dict)) else json.dumps(v)[:200]
            summary[k] = sv[:200]

    row = {
        "ts": _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "session_id": data.get("session_id", "")[:16],
        "tool": tool_name,
        "input": summary,
        "error": is_error,
    }

    try:
        LOG.parent.mkdir(parents=True, exist_ok=True)
        with LOG.open("a") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    except Exception:
        pass
    return 0

if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        sys.exit(0)

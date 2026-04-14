#!/usr/bin/env python3
"""
WhatsApp Webhook Handler for Aguia -- WAsenderAPI Edition

Receives group messages, detects @aguia mentions, routes to Claude
with model load balancing (Haiku/Sonnet), responds via API.

Requires:
  pip install fastapi uvicorn requests

Environment variables:
  WASENDER_SESSION_KEY   -- WAsenderAPI session key
  WASENDER_WEBHOOK_SECRET -- Webhook signature for verification

Run:
  uvicorn wa-webhook-handler:app --host 0.0.0.0 --port 8086
"""
import json
import os
import re
import subprocess
import time
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, Request, Response
import uvicorn

app = FastAPI()

# ============================================================================
# Config -- all secrets from environment variables
# ============================================================================
API_KEY = os.environ.get("WASENDER_SESSION_KEY", "")
WEBHOOK_SECRET = os.environ.get("WASENDER_WEBHOOK_SECRET", "")
API_URL = "https://api.wasenderapi.com/api"
CLAUDE_BIN = os.path.expanduser("~/.local/bin/claude")
AGENT_DIR = Path(os.path.expanduser("~/aguia/agents/whatsapp-bridge"))
LOG_FILE = Path(os.path.expanduser("~/aguia/shared/logs/wa-webhook.log"))
MAX_RESPONSE_LENGTH = 4000

# ============================================================================
# Mention patterns -- customize for your bot name
# ============================================================================
MENTION_PATTERNS = [
    re.compile(r"\baguia\b", re.IGNORECASE),
    re.compile(r"@aguia\b", re.IGNORECASE),
]
BOT_EMOJI = "\U0001F985"  # Eagle emoji as alternative trigger

# ============================================================================
# Model routing -- classify question complexity, pick cheapest adequate model
# ============================================================================
MODEL_MAP = {"SIMPLE": "haiku", "MEDIUM": "sonnet", "COMPLEX": "sonnet"}

# Tier config for group-specific knowledge bases
tier_config = {"groups": {}, "defaultTier": "off", "tiers": {}}
knowledge_cache = {}

# ============================================================================
# Security -- prompt injection detection
# ============================================================================
INJECTION_PATTERNS = [
    re.compile(r"ignore\s+(previous|above|all)\s+(instructions|prompts|rules)", re.I),
    re.compile(r"repeat\s+(your|the)\s+(system|initial)\s+(prompt|instructions)", re.I),
    re.compile(r"disregard\s+(all|any|previous)\s+(instructions|rules)", re.I),
    re.compile(r"you\s+are\s+now\s+(a|an|DAN|jailbreak)", re.I),
]

# ============================================================================
# Rate limiting
# ============================================================================
last_response = {}
COOLDOWN_SECONDS = 5
RATE_LIMIT_PER_MIN = 3
rate_counter = {}
processed = set()

# Conversation context: track active conversations (group+sender -> last mention time)
active_conversations = {}
FOLLOWUP_WINDOW = 300  # 5 minutes


def log(msg):
    ts = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line, flush=True)
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(LOG_FILE, "a") as f:
        f.write(line + "\n")


def load_config():
    global tier_config
    try:
        tier_config = json.loads((AGENT_DIR / "data" / "config.json").read_text())
        log(f"Config loaded: {len(tier_config.get('groups', {}))} group mappings")
    except Exception as e:
        log(f"Config load error: {e}")


def get_group_tier(group_name):
    if not group_name:
        return "public"
    lower = group_name.lower()
    for pattern, tier in tier_config.get("groups", {}).items():
        if pattern.lower() in lower:
            return tier
    return tier_config.get("defaultTier", "off")


def load_knowledge(tier):
    if tier in knowledge_cache:
        return knowledge_cache[tier]
    tier_def = tier_config.get("tiers", {}).get(tier, {})
    kb_file = tier_def.get("knowledge")
    if not kb_file:
        knowledge_cache[tier] = ""
        return ""
    try:
        content = (AGENT_DIR / kb_file).read_text()
        knowledge_cache[tier] = content
        return content
    except Exception:
        knowledge_cache[tier] = ""
        return ""


def is_mention(text):
    if not text:
        return False
    if BOT_EMOJI in text:
        return True
    return any(p.search(text) for p in MENTION_PATTERNS)


def detect_injection(text):
    return any(p.search(text) for p in INJECTION_PATTERNS)


def is_rate_limited(sender_id):
    now = time.time()
    times = rate_counter.get(sender_id, [])
    recent = [t for t in times if now - t < 60]
    if len(recent) >= RATE_LIMIT_PER_MIN:
        return True
    recent.append(now)
    rate_counter[sender_id] = recent
    return False


def classify_complexity(question):
    """Use a cheap model (Haiku) to classify question complexity."""
    prompt = (
        'Classify this question complexity. Reply with one word: SIMPLE, MEDIUM, or COMPLEX.\n'
        'SIMPLE: greetings, yes/no, access issues.\n'
        'MEDIUM: technical how-to, debugging, explanations.\n'
        'COMPLEX: architecture, multi-step analysis.\n\n'
        f'Question: "{question[:500]}"'
    )
    try:
        result = subprocess.run(
            [CLAUDE_BIN, "-p", prompt, "--model", "haiku", "--max-turns", "1", "--output-format", "text"],
            capture_output=True, text=True, timeout=15,
            env={**os.environ, "PATH": f"{os.path.expanduser('~/.local/bin')}:{os.environ.get('PATH', '')}"},
        )
        out = result.stdout.strip().upper()
        if "COMPLEX" in out:
            return "COMPLEX"
        if "MEDIUM" in out:
            return "MEDIUM"
        return "SIMPLE"
    except Exception:
        return "SIMPLE"


def ask_claude(question, sender_name, group_name="", knowledge=""):
    """Route question to Claude with appropriate model based on complexity."""
    complexity = classify_complexity(question)
    model = MODEL_MAP[complexity]
    log(f"  Router: {complexity} -> {model}")

    system_parts = [
        "You are an AI assistant for a community group.",
        "Be concise - max 3-4 short paragraphs.",
        "Be helpful, warm, practical.",
        "Do NOT use markdown. WhatsApp does not render it.",
        "Use plain text: dashes for lists, line breaks for sections.",
        "If asked about code, write it plain without code fences.",
    ]
    if knowledge:
        system_parts.append(f"\nKnowledge base:\n{knowledge}")

    system_prompt = "\n".join(system_parts)
    full_prompt = f'{system_prompt}\n\nMember "{sender_name}" asks:\n{question}'

    try:
        result = subprocess.run(
            [CLAUDE_BIN, "-p", full_prompt, "--model", model, "--max-turns", "3", "--output-format", "text"],
            capture_output=True, text=True, timeout=90,
            cwd=str(AGENT_DIR),
            env={**os.environ, "PATH": f"{os.path.expanduser('~/.local/bin')}:{os.environ.get('PATH', '')}"},
        )
        response = result.stdout.strip()
        if len(response) > MAX_RESPONSE_LENGTH:
            response = response[:MAX_RESPONSE_LENGTH] + "..."
        return response
    except subprocess.TimeoutExpired:
        return "Sorry, I took too long thinking. Try again?"
    except Exception as e:
        log(f"  Claude error: {e}")
        return "Oops, had a problem. Try again in a minute."


def send_wa_message(to, text):
    """Send a WhatsApp message via WAsenderAPI."""
    import requests
    try:
        resp = requests.post(
            f"{API_URL}/send-message",
            headers={"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"},
            json={"to": to, "text": text},
            timeout=30,
        )
        return resp.json()
    except Exception as e:
        log(f"  Send error: {e}")
        return {"error": str(e)}


@app.on_event("startup")
async def startup():
    load_config()
    load_knowledge("public")
    load_knowledge("team")
    log(f"WhatsApp webhook handler started (API_KEY={'set' if API_KEY else 'MISSING'})")


@app.post("/wa-webhook")
async def webhook(request: Request):
    body = await request.body()

    # Verify signature
    if WEBHOOK_SECRET:
        sig = request.headers.get("x-webhook-signature", "")
        if sig and sig != WEBHOOK_SECRET:
            log("Signature mismatch - rejecting")
            return Response(status_code=401)

    try:
        data = json.loads(body)
    except Exception:
        return Response(status_code=400)

    event_type = data.get("event", "")
    log(f"EVENT: {event_type}")

    # WAsenderAPI payload structure
    msg = data.get("data", {}).get("messages", {})
    if not msg or not isinstance(msg, dict):
        return {"ok": True}

    # Extract fields from WAsenderAPI format
    key = msg.get("key", {})
    msg_id = key.get("id", "")
    from_me = key.get("fromMe", False)
    remote_jid = key.get("remoteJid", "") or msg.get("remoteJid", "")
    participant = key.get("participant", "") or key.get("participantPn", "")
    sender_name = msg.get("pushName", "Unknown")
    text = msg.get("messageBody", "") or ""
    is_group = "@g.us" in remote_jid

    # Fallback text extraction
    if not text:
        inner_msg = msg.get("message", {})
        text = inner_msg.get("conversation", "") or ""
        if not text:
            ext = inner_msg.get("extendedTextMessage", {})
            text = ext.get("text", "") or ""

    # Dedup
    if msg_id in processed:
        return {"ok": True}
    processed.add(msg_id)
    if len(processed) > 5000:
        processed.clear()

    # Skip own messages in DMs only
    if from_me and not is_group:
        return {"ok": True}

    # Skip empty or reaction-only messages
    if not text or len(text.strip()) < 2:
        return {"ok": True}

    log(f"{'GRP' if is_group else 'DM'} from {sender_name}: {text[:80]}")

    # Check mention
    if not is_mention(text):
        return {"ok": True}

    # Security
    if detect_injection(text):
        log(f"  INJECTION BLOCKED from {sender_name}")
        return {"ok": True}

    # Rate limit
    if is_rate_limited(participant or remote_jid):
        log(f"  Rate limited: {sender_name}")
        return {"ok": True}

    # Cooldown
    now = time.time()
    if remote_jid in last_response and (now - last_response[remote_jid]) < COOLDOWN_SECONDS:
        return {"ok": True}
    last_response[remote_jid] = now

    # Tier check
    tier = "public"
    if is_group:
        group_name = msg.get("groupName", "") or msg.get("subject", "")
        if group_name:
            tier = get_group_tier(group_name)

    if tier == "off":
        log(f"  Tier OFF - ignoring")
        return {"ok": True}

    log(f"  MENTION from {sender_name} | tier={tier} | group={remote_jid[:30]}")

    knowledge = load_knowledge(tier)

    # Clean mention from text
    clean_text = text
    for p in MENTION_PATTERNS:
        clean_text = p.sub("", clean_text).strip()
    clean_text = clean_text.replace(BOT_EMOJI, "").strip()
    if not clean_text:
        clean_text = "hello"

    # Respond
    response = ask_claude(clean_text, sender_name, remote_jid, knowledge)

    if response:
        result = send_wa_message(remote_jid, response)
        log(f"  Reply sent ({len(response)} chars): {str(result)[:100]}")

    return {"ok": True}


@app.get("/wa-webhook")
async def health():
    return {"status": "ok", "service": "aguia-wa-webhook", "api_key_set": bool(API_KEY)}


if __name__ == "__main__":
    log("Starting WhatsApp webhook handler on port 8086")
    uvicorn.run(app, host="0.0.0.0", port=8086)

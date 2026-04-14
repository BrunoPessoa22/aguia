# WhatsApp Integration (WAsenderAPI)

Receives WhatsApp group messages via webhook, detects @aguia mentions,
routes questions to Claude with model load balancing, and responds via API.

## Setup

1. Sign up at [WAsenderAPI](https://wasenderapi.com) (~$6/month)
2. Scan the QR code with your WhatsApp to link your number
3. Set environment variables:
   ```bash
   export WASENDER_SESSION_KEY=your_key
   export WASENDER_WEBHOOK_SECRET=your_secret
   ```
4. Configure the webhook URL in WAsenderAPI dashboard:
   `https://your-server.com/wa-webhook`

## Features

- Mention detection (@aguia, eagle emoji, case-insensitive)
- Model load balancing (Haiku for simple, Sonnet for complex)
- Per-group tier system (public/team/off)
- Prompt injection detection
- Rate limiting (3 messages/min per sender)
- Cooldown (5s between responses per group)
- Message deduplication

## Running

```bash
# Direct
pip install fastapi uvicorn requests
python wa-webhook-handler.py

# Docker
docker compose up -d
```

## Tier Configuration

Create `agents/whatsapp-bridge/data/config.json`:
```json
{
  "groups": {
    "team-chat": "team",
    "public-group": "public"
  },
  "defaultTier": "off",
  "tiers": {
    "team": { "knowledge": "data/team-kb.md" },
    "public": { "knowledge": "data/public-kb.md" }
  }
}
```

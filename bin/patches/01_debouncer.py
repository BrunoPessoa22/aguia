#!/usr/bin/env python3
"""Patch server.ts to add an inbound debouncer for rapid back-to-back messages.

Design (ported from Hermes + OpenClaw):
- Per-(chat_id, user_id) buffer; 600ms batch delay (wait after last msg);
  2500ms absolute max hold.
- Media/attachments bypass buffer (flush + emit unbuffered).
- Coalesced payload: contents joined with \\n\\n; meta = last msg's meta +
  {batched_count, batched_first_ts}.
- Env TELEGRAM_DEBOUNCE_DISABLE=1 short-circuits to current behavior.

Idempotent: re-running is a no-op (anchors won't match after first apply).
"""
import sys

P = sys.argv[1] if len(sys.argv) > 1 else '/home/ubuntu/.claude/plugins/cache/claude-plugins-official/telegram/0.0.6/server.ts'
s = open(P).read()

ANCHOR_STATE = 'const fallbackTimeouts = new Map<string, ReturnType<typeof setTimeout>>()'
HELPERS = '''const fallbackTimeouts = new Map<string, ReturnType<typeof setTimeout>>()

// === INBOUND DEBOUNCER (added 2026-04-18, P1 port from Hermes/OpenClaw) ===
// Coalesces rapid back-to-back messages per (chat_id, user_id) into a single
// MCP notification. 600ms batch delay, 2500ms absolute max hold. Media
// messages bypass. Set TELEGRAM_DEBOUNCE_DISABLE=1 to short-circuit.
// See /home/ubuntu/aguia/bin/patch-telegram-plugin.sh for re-apply.
const DEBOUNCE_DISABLED = process.env.TELEGRAM_DEBOUNCE_DISABLE === '1'
const DEBOUNCE_BATCH_MS = 600
const DEBOUNCE_MAX_HOLD_MS = 2500

interface PendingInboundBatch {
  payloads: Array<{ content: string; meta: Record<string, string> }>
  batchTimer?: ReturnType<typeof setTimeout>
  maxHoldTimer?: ReturnType<typeof setTimeout>
}
const pendingInboundBatches = new Map<string, PendingInboundBatch>()

function emitInboundNotification(payload: { content: string; meta: Record<string, string> }): void {
  mcp.notification({
    method: 'notifications/claude/channel',
    params: payload,
  }).catch(err => {
    process.stderr.write(`telegram channel: failed to deliver inbound to Claude: ${err}\\n`)
  })
}

function flushInboundBatch(key: string): void {
  const batch = pendingInboundBatches.get(key)
  if (!batch || batch.payloads.length === 0) return
  if (batch.batchTimer) clearTimeout(batch.batchTimer)
  if (batch.maxHoldTimer) clearTimeout(batch.maxHoldTimer)
  pendingInboundBatches.delete(key)

  if (batch.payloads.length === 1) {
    emitInboundNotification(batch.payloads[0]!)
    return
  }

  const combined = {
    content: batch.payloads.map(p => p.content).join('\\n\\n'),
    meta: {
      ...batch.payloads[batch.payloads.length - 1]!.meta,
      batched_count: String(batch.payloads.length),
      batched_first_ts: batch.payloads[0]!.meta.ts,
    },
  }
  emitInboundNotification(combined)
}

function enqueueInbound(payload: { content: string; meta: Record<string, string> }): void {
  const hasMedia = payload.meta.image_path != null || payload.meta.attachment_kind != null
  const key = `${payload.meta.chat_id}:${payload.meta.user_id}`

  if (DEBOUNCE_DISABLED || hasMedia) {
    if (pendingInboundBatches.has(key)) flushInboundBatch(key)
    emitInboundNotification(payload)
    return
  }

  let batch = pendingInboundBatches.get(key)
  if (!batch) {
    batch = { payloads: [] }
    pendingInboundBatches.set(key, batch)
    batch.maxHoldTimer = setTimeout(() => flushInboundBatch(key), DEBOUNCE_MAX_HOLD_MS)
  }
  batch.payloads.push(payload)
  if (batch.batchTimer) clearTimeout(batch.batchTimer)
  batch.batchTimer = setTimeout(() => flushInboundBatch(key), DEBOUNCE_BATCH_MS)
}
// === END DEBOUNCER ==='''

ANCHOR_CALL = '''  mcp.notification({
    method: 'notifications/claude/channel',
    params: {
      content: text,
      meta: {
        chat_id,
        ...(msgId != null ? { message_id: String(msgId) } : {}),
        user: from.username ?? String(from.id),
        user_id: String(from.id),
        ts: tsIso,
        ...(imagePath ? { image_path: imagePath } : {}),
        ...(attachment ? {
          attachment_kind: attachment.kind,
          attachment_file_id: attachment.file_id,
          ...(attachment.size != null ? { attachment_size: String(attachment.size) } : {}),
          ...(attachment.mime ? { attachment_mime: attachment.mime } : {}),
          ...(attachment.name ? { attachment_name: attachment.name } : {}),
        } : {}),
      },
    },
  }).catch(err => {
    process.stderr.write(`telegram channel: failed to deliver inbound to Claude: ${err}\\n`)
  })
}'''

NEW_CALL = '''  enqueueInbound({
    content: text,
    meta: {
      chat_id,
      ...(msgId != null ? { message_id: String(msgId) } : {}),
      user: from.username ?? String(from.id),
      user_id: String(from.id),
      ts: tsIso,
      ...(imagePath ? { image_path: imagePath } : {}),
      ...(attachment ? {
        attachment_kind: attachment.kind,
        attachment_file_id: attachment.file_id,
        ...(attachment.size != null ? { attachment_size: String(attachment.size) } : {}),
        ...(attachment.mime ? { attachment_mime: attachment.mime } : {}),
        ...(attachment.name ? { attachment_name: attachment.name } : {}),
      } : {}),
    },
  })
}'''

if 'enqueueInbound' in s:
    print('already patched — noop', file=sys.stderr)
    sys.exit(0)

if ANCHOR_STATE not in s:
    print(f'ERROR: state anchor not found', file=sys.stderr)
    sys.exit(1)
if s.count(ANCHOR_STATE) != 1:
    print(f'ERROR: state anchor has {s.count(ANCHOR_STATE)} matches, need 1', file=sys.stderr)
    sys.exit(1)
if ANCHOR_CALL not in s:
    print(f'ERROR: call anchor not found', file=sys.stderr)
    sys.exit(1)
if s.count(ANCHOR_CALL) != 1:
    print(f'ERROR: call anchor has {s.count(ANCHOR_CALL)} matches, need 1', file=sys.stderr)
    sys.exit(1)

s = s.replace(ANCHOR_STATE, HELPERS, 1)
s = s.replace(ANCHOR_CALL, NEW_CALL, 1)
open(P, 'w').write(s)
print(f'patched: added {HELPERS.count(chr(10))+1} lines of debouncer + rewired inbound notification')

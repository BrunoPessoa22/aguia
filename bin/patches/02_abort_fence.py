#!/usr/bin/env python3
"""Add abort-fence to Telegram plugin server.ts.

Every inbound bumps currentGeneration[chat_id]. The `reply` tool snapshots
the generation at the start of its handler and checks before each
bot.api.sendMessage / sendPhoto / sendDocument whether the generation has
advanced (= a newer inbound arrived). On supersede, the last-sent message
is edited to append "\\n\\n_[interrompido]_" and remaining chunks/files are
dropped. The tool returns an aborted status to Claude so the agent can
respond fresh to the new input.

Safety: env TELEGRAM_ABORT_FENCE_DISABLE=1 short-circuits the check.

Idempotent: re-running is a noop after first apply.
"""
from __future__ import annotations

import sys
from pathlib import Path

P = Path(sys.argv[1]) if len(sys.argv) > 1 else Path('/home/ubuntu/.claude/plugins/cache/claude-plugins-official/telegram/0.0.6/server.ts')
s = P.read_text()

if 'currentGeneration' in s and 'ABORT_FENCE' in s:
    print('already patched — noop')
    sys.exit(0)

# --- 1. Add generation map + helpers right after the debouncer block --------
ANCHOR_1 = '''function enqueueInbound(payload: { content: string; meta: Record<string, string> }): void {
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

HELPERS_2 = '''function enqueueInbound(payload: { content: string; meta: Record<string, string> }): void {
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
// === END DEBOUNCER ===

// === ABORT FENCE (added 2026-04-18, P2.2) ===
// Every inbound bumps currentGeneration[chat_id]. The reply tool captures a
// snapshot at start and checks between chunk sends whether the generation
// advanced. On supersede, the last-sent message is edited to append an
// "[interrompido]" marker and remaining chunks are dropped.
// Safety: TELEGRAM_ABORT_FENCE_DISABLE=1 short-circuits.
const ABORT_FENCE_DISABLED = process.env.TELEGRAM_ABORT_FENCE_DISABLE === '1'
const currentGeneration = new Map<string, number>()

function bumpGeneration(chat_id: string): number {
  const next = (currentGeneration.get(chat_id) ?? 0) + 1
  currentGeneration.set(chat_id, next)
  return next
}

function isSuperseded(chat_id: string, startGen: number): boolean {
  if (ABORT_FENCE_DISABLED) return false
  return (currentGeneration.get(chat_id) ?? 0) > startGen
}
// === END ABORT FENCE ==='''

# --- 2. Bump generation in handleInbound BEFORE enqueueInbound -----------------
ANCHOR_2 = '''  // image_path goes in meta only — an in-content "[image attached — read: PATH]"
  // annotation is forgeable by any allowlisted sender typing that string.
  enqueueInbound({'''

REPLACE_2 = '''  // Abort-fence: bump generation so any in-flight reply for this chat is
  // superseded. The reply tool checks this between chunks.
  bumpGeneration(chat_id)

  // image_path goes in meta only — an in-content "[image attached — read: PATH]"
  // annotation is forgeable by any allowlisted sender typing that string.
  enqueueInbound({'''

# --- 3. Snapshot startGen + per-chunk abort check + files abort check ---------
ANCHOR_3 = '''      case 'reply': {
        const chat_id = args.chat_id as string
        const text = args.text as string'''

REPLACE_3 = '''      case 'reply': {
        const chat_id = args.chat_id as string
        const text = args.text as string
        // Snapshot generation at reply start — if a newer inbound arrives
        // during the multi-chunk send, we'll abort the remaining sends.
        const abortFenceStartGen = currentGeneration.get(chat_id) ?? 0'''

# --- 4. Wrap chunk-send loop with abort check --------------------------------
ANCHOR_4 = '''        try {
          for (let i = 0; i < chunks.length; i++) {
            const shouldReplyTo =
              reply_to != null &&
              replyMode !== 'off' &&
              (replyMode === 'all' || i === 0)
            const sent = await bot.api.sendMessage(chat_id, chunks[i], {
              ...(shouldReplyTo ? { reply_parameters: { message_id: reply_to } } : {}),
              ...(parseMode ? { parse_mode: parseMode } : {}),
            })
            sentIds.push(sent.message_id)
          }
        } catch (err) {'''

REPLACE_4 = '''        let abortedBySupersede = false
        try {
          for (let i = 0; i < chunks.length; i++) {
            if (isSuperseded(chat_id, abortFenceStartGen)) {
              abortedBySupersede = true
              // Edit last-sent chunk with interruption marker so the user
              // sees where we stopped. Fire-and-forget — don't block on edit.
              if (sentIds.length > 0) {
                const lastId = sentIds[sentIds.length - 1]
                const prevChunk = chunks[i - 1] ?? ''
                void bot.api.editMessageText(
                  chat_id,
                  lastId,
                  `${prevChunk}\\n\\n_[interrompido — respondendo à sua nova mensagem]_`,
                  parseMode ? { parse_mode: parseMode } : undefined,
                ).catch(() => {})
              }
              break
            }
            const shouldReplyTo =
              reply_to != null &&
              replyMode !== 'off' &&
              (replyMode === 'all' || i === 0)
            const sent = await bot.api.sendMessage(chat_id, chunks[i], {
              ...(shouldReplyTo ? { reply_parameters: { message_id: reply_to } } : {}),
              ...(parseMode ? { parse_mode: parseMode } : {}),
            })
            sentIds.push(sent.message_id)
          }
        } catch (err) {'''

# --- 5. Wrap files loop with abort check --------------------------------------
ANCHOR_5 = '''        // Files go as separate messages (Telegram doesn't mix text+file in one
        // sendMessage call). Thread under reply_to if present.
        for (const f of files) {
          const ext = extname(f).toLowerCase()
          const input = new InputFile(f)
          const opts = reply_to != null && replyMode !== 'off'
            ? { reply_parameters: { message_id: reply_to } }
            : undefined
          if (PHOTO_EXTS.has(ext)) {
            const sent = await bot.api.sendPhoto(chat_id, input, opts)
            sentIds.push(sent.message_id)
          } else {
            const sent = await bot.api.sendDocument(chat_id, input, opts)
            sentIds.push(sent.message_id)
          }
        }'''

REPLACE_5 = '''        // Files go as separate messages (Telegram doesn't mix text+file in one
        // sendMessage call). Thread under reply_to if present. Skip remaining
        // files if abort-fence triggered during chunks loop (or trips here).
        for (const f of files) {
          if (abortedBySupersede || isSuperseded(chat_id, abortFenceStartGen)) {
            abortedBySupersede = true
            break
          }
          const ext = extname(f).toLowerCase()
          const input = new InputFile(f)
          const opts = reply_to != null && replyMode !== 'off'
            ? { reply_parameters: { message_id: reply_to } }
            : undefined
          if (PHOTO_EXTS.has(ext)) {
            const sent = await bot.api.sendPhoto(chat_id, input, opts)
            sentIds.push(sent.message_id)
          } else {
            const sent = await bot.api.sendDocument(chat_id, input, opts)
            sentIds.push(sent.message_id)
          }
        }'''

# --- 6. Update return status to signal abort when superseded ------------------
ANCHOR_6 = '''        const result =
          sentIds.length === 1
            ? `sent (id: ${sentIds[0]})`
            : `sent ${sentIds.length} parts (ids: ${sentIds.join(', ')})`
        return { content: [{ type: 'text', text: result }] }
      }
      case 'react': {'''

REPLACE_6 = '''        const result = abortedBySupersede
          ? `aborted after ${sentIds.length}/${chunks.length} chunks — superseded by newer inbound; respond to the new message fresh`
          : sentIds.length === 1
            ? `sent (id: ${sentIds[0]})`
            : `sent ${sentIds.length} parts (ids: ${sentIds.join(', ')})`
        return { content: [{ type: 'text', text: result }] }
      }
      case 'react': {'''


def apply(src: str, anchor: str, new: str, label: str) -> str:
    if anchor not in src:
        print(f'[{label}] anchor NOT FOUND', file=sys.stderr)
        sys.exit(1)
    if src.count(anchor) != 1:
        print(f'[{label}] anchor matched {src.count(anchor)} times, need 1', file=sys.stderr)
        sys.exit(1)
    return src.replace(anchor, new, 1)


orig_len = len(s)
s = apply(s, ANCHOR_1, HELPERS_2, 'generation-helpers')
s = apply(s, ANCHOR_2, REPLACE_2, 'bump-generation-on-inbound')
s = apply(s, ANCHOR_3, REPLACE_3, 'snapshot-start-generation')
s = apply(s, ANCHOR_4, REPLACE_4, 'chunks-abort-check')
s = apply(s, ANCHOR_5, REPLACE_5, 'files-abort-check')
s = apply(s, ANCHOR_6, REPLACE_6, 'abort-return-status')

P.write_text(s)
print(f'patched: {orig_len} -> {len(s)} bytes (+{len(s) - orig_len})')

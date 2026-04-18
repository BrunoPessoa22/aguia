#!/usr/bin/env bun
/**
 * MCP server — wiki_search tool for Aguia.
 *
 * Exposes a single `wiki_search(query, limit?)` tool backed by the
 * second-brain semantic search API at `${WIKI_API}/wiki/semantic` (a
 * FastAPI/uvicorn service on localhost:3200 that wraps knowledge_index.py).
 *
 * Loads WIKI_BEARER from /home/ubuntu/aguia/.env so Aguia's MCP host
 * doesn't need the token in its own environment.
 *
 * Registered in /home/ubuntu/aguia/.claude/settings.json under mcpServers.
 */

import { Server } from '@modelcontextprotocol/sdk/server/index.js'
import { StdioServerTransport } from '@modelcontextprotocol/sdk/server/stdio.js'
import {
  ListToolsRequestSchema,
  CallToolRequestSchema,
} from '@modelcontextprotocol/sdk/types.js'
import { readFileSync } from 'fs'
import { homedir } from 'os'
import { join } from 'path'

const ENV_FILE = join(homedir(), 'aguia', '.env')
try {
  for (const line of readFileSync(ENV_FILE, 'utf8').split('\n')) {
    const m = line.match(/^(\w+)=(.*)$/)
    if (m && process.env[m[1]] === undefined) process.env[m[1]] = m[2]
  }
} catch {}

const WIKI_API = process.env.WIKI_API ?? 'http://localhost:3200'
const WIKI_BEARER = process.env.WIKI_BEARER

if (!WIKI_BEARER) {
  process.stderr.write(`wiki-search MCP: WIKI_BEARER not set in ${ENV_FILE}; refusing to start\n`)
  process.exit(1)
}

const server = new Server(
  { name: 'wiki-search', version: '1.0.0' },
  { capabilities: { tools: {} } },
)

server.setRequestHandler(ListToolsRequestSchema, async () => ({
  tools: [
    {
      name: 'wiki_search',
      description:
        'Semantic search across the second-brain wiki (~200 compiled articles, refreshed 2x/day by the second-brain agent). Use when you need historical context, prior solutions, patterns, or pitfalls for a task. Complements the <wiki_touchpoints> block that SessionStart injected — use wiki_search mid-conversation when the touchpoints block does not cover the specific topic you care about. Returns ranked articles with title, absolute path, relevance score, and a short excerpt. Read the full article with the Read tool on the path returned.',
      inputSchema: {
        type: 'object',
        properties: {
          query: {
            type: 'string',
            description:
              'Natural language query. Examples: "Typefully URL rejection pattern", "ARARA rejection recovery", "FTI A5 threshold", "Falcão carousel template".',
          },
          limit: {
            type: 'number',
            description: 'Max results (1-15, default 5).',
            default: 5,
          },
        },
        required: ['query'],
      },
    },
  ],
}))

server.setRequestHandler(CallToolRequestSchema, async req => {
  if (req.params.name !== 'wiki_search') {
    throw new Error(`wiki-search MCP: unknown tool ${req.params.name}`)
  }
  const args = (req.params.arguments ?? {}) as { query?: string; limit?: number }
  if (!args.query) {
    throw new Error('wiki_search: query is required')
  }
  const limit = Math.max(1, Math.min(args.limit ?? 5, 15))
  const url = `${WIKI_API}/wiki/semantic?q=${encodeURIComponent(args.query)}&n=${limit}&source=wiki`

  let data: any
  try {
    const res = await fetch(url, {
      headers: { Authorization: `Bearer ${WIKI_BEARER}` },
      signal: AbortSignal.timeout(10_000),
    })
    if (!res.ok) {
      const body = await res.text().catch(() => '')
      return {
        content: [
          { type: 'text', text: `wiki API HTTP ${res.status}: ${body.slice(0, 200)}` },
        ],
        isError: true,
      }
    }
    data = await res.json()
  } catch (err) {
    const msg = err instanceof Error ? err.message : String(err)
    return {
      content: [{ type: 'text', text: `wiki search request failed: ${msg}` }],
      isError: true,
    }
  }

  const results = Array.isArray(data?.results) ? data.results : []
  if (results.length === 0) {
    return {
      content: [{ type: 'text', text: `No wiki matches for "${args.query}".` }],
    }
  }

  const lines = results.map((r: any, i: number) => {
    const meta = r.metadata ?? {}
    const title = meta.title ?? meta.rel_path ?? 'untitled'
    const path = meta.path ?? ''
    const score = typeof r.score === 'number' ? r.score.toFixed(2) : '?'
    const excerpt = String(r.excerpt ?? '')
      .replace(/\s+/g, ' ')
      .trim()
      .slice(0, 250)
    return `${i + 1}. **${title}** (score ${score})\n   \`${path}\`\n   _${excerpt}…_`
  })

  const text = [
    `Top ${results.length} wiki matches for "${args.query}":`,
    '',
    ...lines,
    '',
    `Read any with the Read tool on the absolute path.`,
  ].join('\n')

  return { content: [{ type: 'text', text }] }
})

const transport = new StdioServerTransport()
await server.connect(transport)

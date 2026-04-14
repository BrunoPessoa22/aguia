# Agent Fleet -- Ideas and Inspiration

A showcase of agent archetypes you can build with Aguia. Each can be scaffolded with `./agents/create-agent.sh <name> "<description>"` and customized via CLAUDE.md.

---

## Included Templates

These are ready-to-use templates in the `agents/` directory:

| # | Agent | Role | Schedule |
|---|-------|------|----------|
| 1 | **ClawFix** | System health monitor and auto-repair | Every 4-6h |
| 2 | **Second Brain** | Wiki curator (Karpathy Knowledge Base pattern) | 2x/day |
| 3 | **Content Creator** | Social media content for X/LinkedIn/Instagram | 3-4x/day |
| 4 | **Outreach Hunter** | BD/sales outreach via LinkedIn | Weekdays |
| 5 | **Health Coach** | Personal wellness from wearable data | Daily AM |
| 6 | **Job Hunter** | Autonomous job search and application pipeline | Weekdays |
| 7 | **Newsletter** | Newsletter curation and weekly writing | Mon + Wed |
| 8 | **Family Ops** | Family calendar, birthdays, work-life balance | Daily AM |

---

## More Ideas

### Revenue and Business

| Agent | What It Does |
|-------|-------------|
| **Deal Scanner** | Scans AngelList, ProductHunt, YC for investment and freelance opportunities. Scores and alerts on high matches. |
| **Freelance Hunter** | Monitors Upwork, Toptal, and niche job boards for high-rate contracts matching your skills. |
| **Enterprise Sales** | Researches and scores enterprise targets, sends outreach via LinkedIn, tracks pipeline. |
| **Partnership BD** | Identifies potential partners, tracks conversations, manages follow-up cadence. |
| **Revenue Tracker** | Aggregates income across freelance, investments, products. Weekly P&L report. |

### Content and Brand

| Agent | What It Does |
|-------|-------------|
| **Podcast Miner** | Scans podcast RSS feeds for new episodes, extracts hot takes and data points, drafts content. |
| **Thread Writer** | Takes raw ideas and crafts X/Twitter threads with hooks, data, and CTAs. |
| **LinkedIn Ghost** | Writes and schedules LinkedIn posts in your voice. Engagement optimization loop. |
| **Blog Publisher** | Writes long-form blog posts from agent discoveries. SEO optimization. |
| **Community Manager** | Monitors Discord/Telegram communities. Welcomes new members, flags unanswered questions. |

### Knowledge and Research

| Agent | What It Does |
|-------|-------------|
| **Paper Reader** | Reads arXiv papers in your field, writes 200-word summaries, flags breakthroughs. |
| **Competitor Watch** | Monitors competitors' websites, social, and product launches. Weekly digest. |
| **Patent Scanner** | Searches patent databases for prior art or interesting innovations. |
| **News Curator** | Aggregates and summarizes industry news from 20+ sources daily. |
| **Trend Spotter** | Analyzes social media trends, search volumes, and market data for emerging opportunities. |

### Operations and DevOps

| Agent | What It Does |
|-------|-------------|
| **Deploy Guardian** | Monitors deployments, runs smoke tests, auto-rollbacks on failure. |
| **Cost Optimizer** | Analyzes cloud bills, suggests right-sizing, flags unused resources. |
| **Security Scanner** | Runs dependency audits, checks SSL certs, monitors for exposed credentials. |
| **Backup Verifier** | Tests backup restoration, verifies data integrity, reports gaps. |
| **Log Analyst** | Mines application logs for patterns, anomalies, and recurring errors. |

### Personal Life

| Agent | What It Does |
|-------|-------------|
| **Meal Planner** | Weekly meal plans with shopping lists. Considers dietary preferences and seasonal produce. |
| **Finance Tracker** | Categorizes expenses, tracks budgets, alerts on unusual spending. |
| **Reading List** | Curates books and articles based on your interests. Sends daily reading suggestion. |
| **Travel Planner** | Monitors flight prices, suggests trip itineraries, manages packing lists. |
| **Gift Finder** | Tracks upcoming birthdays/holidays, suggests personalized gift ideas with purchase links. |

### Domain-Specific

| Agent | What It Does |
|-------|-------------|
| **Trading Analyst** | Monitors crypto/stock markets, runs signal analysis, paper-trades strategies. |
| **Real Estate Scout** | Scans listings matching your criteria, calculates ROI, alerts on new matches. |
| **Legal Monitor** | Tracks regulatory changes in your industry. Summarizes new laws and compliance requirements. |
| **Sports Intel** | Monitors sports data, match results, and market correlations for your domain. |
| **Academic Tracker** | Follows researchers and labs in your field, tracks citations, alerts on new publications. |

---

## Building Your Fleet

Start small. A good first fleet:

1. **ClawFix** -- keeps everything running
2. **Second Brain** -- builds knowledge over time
3. **One domain agent** -- your core use case (content, sales, research, etc.)

Add more agents as you identify repetitive tasks that can be automated. The wiki system means each new agent benefits from the knowledge all previous agents have accumulated.

### Agent Communication Patterns

Agents communicate through shared state, not direct messages:

```
Content Creator writes a great post
  -> logs to memory/
    -> Second Brain harvests the insight
      -> compiles wiki article
        -> ALL agents get smarter via wiki injection

Outreach Hunter finds a hot lead
  -> writes to shared/today-briefing.md
    -> Orchestrator sees it in fleet briefing
      -> mentions it to you in Telegram
```

This is emergent intelligence -- agents that were never designed to work together still benefit from each other's discoveries through the wiki and shared context layers.

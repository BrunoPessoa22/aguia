# Brain — Self-Evolving Agent Rules

A lightweight self-evolution loop for any Aguia agent. The brain:

1. **Collects** metrics daily (what was posted, how it performed)
2. **Analyzes** weekly to find patterns in top/bottom performers
3. **Evolves** rules in a git-tracked YAML config, with a safe/approval split

## Why

Agents can't get smarter if their rules never change. The brain is the feedback loop that turns yesterday's real-world performance into tomorrow's decisions — without dumping everything into the main CLAUDE.md (which would bloat context).

## Files

| File | Purpose |
|---|---|
| `rules.example.yaml` | Starter config — pillars, cadence, thresholds, evolution policy, banned words, compliance |
| `collect.py` | Daily cron — pulls engagement from platform APIs, appends to `performance.jsonl` |
| `analyze.py` | Weekly cron — extracts patterns from top 10% / bottom 20%, writes `insights-latest.md` |
| `evolve.py` | Weekly cron — proposes rule changes; auto-applies safe ones with git commit, queues approval for bigger changes |

## Setup

```bash
cp agents/brain/rules.example.yaml agents/brain/rules.yaml
# edit rules.yaml — pillars, thresholds, compliance. See comments inline.
cd agents/brain && git init -q
pip install --user --break-system-packages pyyaml
```

Credentials needed in `.env` for collect.py (all optional — script degrades gracefully):

```
TYPEFULLY_KEY=...
TYPEFULLY_SOCIAL_SET_ID=...
X_BEARER_TOKEN=...   # X API v2 read-only
IG_ACCESS_TOKEN=...  # Instagram Graph API long-lived
IG_USER_ID=...
```

## Cron schedule

```cron
# Daily 23:00 UTC — pull yesterday's post engagement
0 23 * * * cd $AGUIA_HOME/agents/<your-agent>/brain && python3 collect.py >> $AGUIA_HOME/shared/logs/brain.log 2>&1

# Weekly Sunday 16:30 UTC — analyze + evolve
30 16 * * 0 cd $AGUIA_HOME/agents/<your-agent>/brain && python3 analyze.py --days 7 && python3 evolve.py >> $AGUIA_HOME/shared/logs/brain.log 2>&1
```

## Evolution policy (what the brain can auto-change vs what needs you)

Defined in `rules.yaml` under `evolution`:

```yaml
evolution:
  auto_allowed:       # brain auto-applies with git commit for rollback
    - "pillars.*.target_pct"
    - "channels.*.posts_per_day"  # within ±1 of current
    - "channels.*.optimal_windows*"
    - "thresholds.engagement_rate_*"
  requires_approval:  # brain proposes -> Telegram you, you reply YES
    - "channels.*.hook_patterns_winners"
    - "channels.*.anti_patterns"
    - "channels.*.video_spec.*"
  never_change:       # hard rules, brain never touches
    - "channels.linkedin.language_rule"
    - "compliance"
```

## Example: pillar balance

Say your rules say 35% AI / 35% Business / 20% Blockchain / 10% Regulation. Brain notices last 7 posts were 50% Business, 10% Blockchain. It:

1. Flags Blockchain as **under-represented** (<15% floor)
2. Next time agent runs, injects a note: "PREFER Blockchain topics this run (under-represented)"
3. Candidate topics from Blockchain get +50% score bonus
4. Business candidates get −40% until rebalanced

Zero agent retraining. Pure config feedback loop.

## The rule it locked today

Apr 17 Kings League Reel generated with overlay text in the prompt → Seedance rendered gibberish text. Brain now has:

```yaml
video:
  never_render_text_in_prompt: true
  reason: "Text-to-video models garble on-screen text. Always post-burn via ffmpeg."
```

That rule is auto-injected into every Falcão dispatch now. Won't repeat.

See [docs/LESSONS.md](../../docs/LESSONS.md) entry 6 for the full story.

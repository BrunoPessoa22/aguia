# Channel Virality Playbook — X (2026)

**Audience:** YOUR_NAME @your_x_handle, Sports × AI × Blockchain thought-leadership voice. Mixed US+EU+Brazil follower base. Target: 10K followers EOY 2026.

**Source:** audit of Apr 3–16 2026 posts + 2026 algo research (Grok-transformer update Jan 2026, public algo code). Last verified 2026-04-16.

## Algorithm reality (Jan 2026 Grok update)

- **Engagement velocity in the first 30–60 minutes is the single strongest ranking factor.** A post that gets zero engagement in the first hour is dead. The scoring formula from the leaked-then-refactored algo:
  - Likes ×1
  - Retweets ×20
  - Replies ×13.5
  - Profile clicks ×12
  - Link clicks ×11
  - Bookmarks ×10
- **Premium subscription gives 4× in-network visibility and 2× out-of-network.** Non-Premium posts with external links have near-zero median reach post-March 2026.
- **Grok now reads the full post text AND watches every attached video**, so production quality of the first 3 seconds matters for algo grading, not just the first hook line.

## Hook structure that works in 2026

The hook is the **entire first line**, not the thread. 8 words or less in most cases. Patterns that validated in your audit (top 10% of posts Apr 3–16):

1. **Specific number + contrast** — `$400K → $0`, `R$ 5B vs R$ 0`, `US $8B vs Brazil $50M`. Works because concrete numbers cut through timeline noise AND the contrast creates cognitive tension.
2. **Contrarian-confessional opener** — "I was wrong about X.", "Pensava que um founder brasileiro demoraria 10 anos." Triggers reply-instinct; replies count 13.5× in the algo.
3. **Infrastructure reframe** — "Who owns the data?" outperforms "AI replaces X." Elevates the conversation from hype to stakes, attracting thoughtful QRTs.
4. **Authoritative list** — "Here's what nobody is saying about [X]:" + thread. Works only if payoff is real.

Patterns that failed (bottom 20%):
- Generic "AI will replace [job]" without ownership/incentive angle
- "VR stadium" framings without a specific team or deal
- Athlete-fractional-ownership without a named protocol or cap table

## Optimal format

**Short-form native video dominates.** ~10× text engagement when properly formatted.

Video spec for X in 2026:
- **Duration**: 15–45 seconds sweet spot
- **Aspect**: 9:16 vertical preferred (mobile-first in 2026) or 16:9 for desktop-heavy moments
- **Captions**: burned in, bold sans-serif white + 3–4px black stroke, 2–3 words per page. Most X video is watched muted.
- **Hook**: must land in first 2–3 seconds or viewers swipe.
- **Length cap**: never exceed 45s; engagement falls off a cliff past ~50s.

Long-form text (up to 4000 chars for Premium): rewards depth. Threads still work if every tweet has a self-contained payoff.

## Posting windows — UTC overlap for US+EU+Brazil

| UTC | ET | CET | BRT | Priority |
|---|---|---|---|---|
| 12:00 | 08:00 | 14:00 | 09:00 | **Peak** (US morning ramp + EU afternoon + BR breakfast) |
| 15:00 | 11:00 | 17:00 | 12:00 | Strong |
| 17:00 | 13:00 | 19:00 | 14:00 | Strong |
| 20:00 | 16:00 | 22:00 | 17:00 | Moderate (US afternoon) |

Avoid: 02:00–10:00 UTC (US asleep). Current FALCAO 06:00 UTC slot is dead air for Americans and should be moved to 13:00 UTC.

**Tue / Wed / Thu outperform weekends by ~40% for B2B thought leadership.**

## Viral mechanic unique to X

**Reply-to-your-own-post within 2 minutes is worth ~150× a like in the algo velocity signal.**

Tactic the agent must execute after every post:
1. Post the main hook
2. Within 2 minutes, self-reply with one of:
   - Additional data point that extends the argument
   - A short question that invites responses
   - A visual (chart/screenshot) that wasn't in main
3. Reply to every comment in the first 60 minutes. Reply length 2–4 lines, not one-liners. Reply velocity signals the algo that the post is generating conversation.

## Distinct content types, weekly cadence

| Type | Frequency | Format |
|---|---|---|
| Hook post (short, data-driven) | 4–5/day | Text + 1 image (carousel-v3 typographic) or 7–12s video |
| Thread (3–7 tweets) | 3/week | Text, optional 1 image in Tweet #1 |
| X Essay (long-form, up to 4000 chars) | 3/week Tue/Thu/Sat 14:00 UTC | Text only, Opus-generated, one distinctive visual |
| Reply / quote-tweet engagement | throughout day | Target @AlexDreyfus, @MarioNawfal, @levelsio, @alibarati, @balajis |
| Video | 1/day minimum | 15–45s, vertical, captions burned |

## Anti-pattern checklist (auto-reject before post)

- Contains banned AI-speak: leverage, synergy, ecosystem, unlock, empower, cutting-edge, paradigm shift, game-changing, disruptive, holistic, best-in-class, seamless, landscape
- External link in body (kills reach unless Premium-boosted)
- Starts with a question (low reply trigger vs claim-based hook)
- Duplicates a topic posted within last 72h
- Mentions (your employer or topic) / (token) / (brand) directly (compliance)

## Metrics to track (Falcão Brain)

- **Engagement rate**: weighted_engagement / impressions. Floor 1.5%, viral ≥5.0%.
- **Reply ratio**: replies / impressions. Reply-heavy posts compound in the algo.
- **Click-through**: link clicks / impressions (when Premium).
- **Profile clicks per post**: growth signal.

Record to `brain/performance.jsonl` daily via `brain/collect.py`.

## Compliance (hard rules)

- Never reveal (your employer or topic) employer identity in posts
- Never promote (token) price targets
- Fan tokens: comment as "industry observation", never "buy/sell" advice
- Attribute sources when quoting stats; link to source in a self-reply, not main post

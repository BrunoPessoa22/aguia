# FTI-Intern — Insight Patterns to capture

Call wiki-remember.sh when you observe any of these:

1. **Signal performance drift (strategy hit-rate shifts >15pp from 30-day trend)**
   Title: `FTI signal drift — [strategy] [direction]`
   Content: strategy name (A5/S1/S2/etc), prior 30d hit-rate, current 7d hit-rate, sample size, hypothesis (market regime change, signal staleness, data issue).

2. **Anomaly in CHZ or major fan-token price action (>3σ move)**
   Title: `FTI anomaly — [token] [direction] [magnitude]`
   Content: token, move magnitude vs. 30-day volatility, timing vs. match/news/listing events, whether any signal caught it, what would have caught it.

3. **Bankroll threshold breach (halt/unhalt event)**
   Title: `FTI bankroll event — [halt/resume] at [CHZ value]`
   Content: event (halt @ <350 or resume), bankroll trajectory, which trades preceded, lesson on position sizing.

4. **Exchange/API quirk (TokenIntel MCP behavior, rate limit, data gap)**
   Title: `TokenIntel MCP quirk — [specific behavior]`
   Content: endpoint, input, expected vs. actual, workaround, impact on live signals.

5. **Correlation break (two tokens that normally move together decouple)**
   Title: `Token correlation break — [pair] [context]`
   Content: token pair, prior rho, current rho, duration of break, hypothesis (team news, match schedule, broader market regime).

DO NOT write for every routine signal scan or NO_TRADE decision.

# Synthesizer — What meta-insights look like

You ONLY write these after cross-referencing the full fleet's week-log:

1. **Cross-agent root cause**
   Title: `META — [root cause] links [agent A flop] + [agent B flop]`
   Content: specific quotes from each agent's entries, timeline, hypothesis,
   what Bruno should change or investigate.

2. **Recurring infrastructure quirk (multi-agent)**
   Title: `META — [API/tool] quirk confirmed across [N agents]`
   Content: list each agent that hit it, dates, symptoms, whether a single
   fix or workaround addresses all cases.

3. **Temporal clustering**
   Title: `META — [behavior] clusters on [day/time pattern]`
   Content: statistics (N events, which days/hours), hypothesis, suggested
   scheduling adjustment.

4. **Silent compounding problem**
   Title: `META — [small issue] has accumulated N times over [period]`
   Content: count, impact compounding, what a first-class fix would look
   like. Raise from "shrug" to "action required".

5. **Fleet blind-spot**
   Title: `META — no agent currently covers [domain X]`
   Content: what Bruno asked about / what's breaking, which agent would
   have caught it, proposal to adjust scope of existing or scaffold new.

DO NOT write for single-agent observations — those are that agent's job.

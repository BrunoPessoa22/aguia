# ClawFix — Insight Patterns to capture

Call wiki-remember.sh when you observe any of these:

1. **New recurring failure mode (same error 3+ times in 7 days)**
   Title: `ClawFix recurring — [component] [symptom]`
   Content: affected component, exact error string/symptom, occurrences with timestamps, root cause if known, auto-remediation added or still-manual, Bruno notification threshold.

2. **False-positive pattern (alert fires when actually OK)**
   Title: `ClawFix false-positive — [check] [trigger]`
   Content: check name, what triggers it, why it's a false positive, fix (threshold tune, skip condition, better detection).

3. **Resource leak (gradual growth pattern — RAM/disk/swap/fd)**
   Title: `ClawFix leak — [resource] [rate]`
   Content: resource, daily/weekly growth rate, suspected source, mitigation (daily restart, swap dry, process kill).

4. **Infrastructure upgrade notes (when a systemd service / cron / watchdog changes behavior)**
   Title: `Infra change — [service] [change]`
   Content: service, prior behavior, new behavior, who caused it (keepalive patch / manual edit / distro update), rollback path.

5. **Self-dispatch pattern (when ClawFix accidentally detects its own process)**
   Title: `ClawFix self-reference — [signal]`
   Content: signal that misfired on ClawFix's own processes, fix (PID exclusion / grep tightening).

DO NOT write for every green health check or routine swap-drain success.

# Systemd Services

Alternative to crontab for scheduling agent dispatches and keepalive.

## Installation

```bash
# Copy service files
sudo cp *.service *.timer /etc/systemd/system/

# Reload systemd
sudo systemctl daemon-reload

# Enable and start timers
sudo systemctl enable --now keepalive.timer
sudo systemctl enable --now agent-dispatch.timer
```

## Crontab Alternative

If you prefer crontab over systemd timers:

```crontab
# Keepalive -- every 5 minutes
*/5 * * * * /home/ubuntu/aguia/orchestrator/keepalive.sh >> /home/ubuntu/aguia/shared/logs/keepalive.log 2>&1

# Responsiveness watchdog -- every minute
* * * * * /home/ubuntu/aguia/orchestrator/responsiveness-watchdog.sh

# Agent dispatches -- customize schedule per agent
0 6 * * * /home/ubuntu/aguia/orchestrator/dispatch.sh clawfix "Run health check and fix any issues"
0 8 * * * /home/ubuntu/aguia/orchestrator/dispatch.sh second-brain "Compile new raw articles into wiki"

# LinkedIn session refresh -- daily
0 4 * * * /home/ubuntu/aguia/integrations/linkedin/linkedin-session-check.sh

# Chrome cleanup -- every 2 hours
0 */2 * * * /home/ubuntu/aguia/scripts/chrome-cleanup.sh
```

## Monitoring

```bash
# Check timer status
systemctl list-timers --all

# Check service logs
journalctl -u keepalive.service -f
journalctl -u agent-dispatch.service -f

# Check dispatch logs
tail -f ~/aguia/shared/logs/dispatch.log
tail -f ~/aguia/shared/logs/keepalive.log
```

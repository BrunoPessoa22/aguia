#!/bin/bash
# Kill orphaned headless Chrome processes (from Playwright runs)
# Run periodically via cron to prevent memory leaks.
pkill -f "chrome.*--headless" 2>/dev/null || true
pkill -f "chromium.*--headless" 2>/dev/null || true

#!/bin/bash
# Aguia Installer -- Idempotent setup script
# Safe to run multiple times. Skips steps that are already complete.
set -euo pipefail

AGUIA_HOME="${AGUIA_HOME:-$HOME/aguia}"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log()   { echo -e "${GREEN}[OK]${NC} $1"; }
warn()  { echo -e "${YELLOW}[WARN]${NC} $1"; }
fail()  { echo -e "${RED}[FAIL]${NC} $1"; }
info()  { echo -e "${BLUE}[INFO]${NC} $1"; }

echo ""
echo "======================================"
echo "  Aguia Multi-Agent System Installer"
echo "======================================"
echo ""

# ============================================================================
# PREREQUISITES CHECK
# ============================================================================
info "Checking prerequisites..."

MISSING=0

check_cmd() {
    local cmd="$1"
    local install_hint="$2"
    if command -v "$cmd" &>/dev/null; then
        log "$cmd found: $(command -v "$cmd")"
    else
        fail "$cmd not found. Install: $install_hint"
        MISSING=$((MISSING + 1))
    fi
}

check_cmd "claude" "npm install -g @anthropic-ai/claude-code"
check_cmd "node"   "https://nodejs.org/ or: curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash - && sudo apt install -y nodejs"
check_cmd "python3" "sudo apt install -y python3 python3-pip"
check_cmd "tmux"   "sudo apt install -y tmux"
check_cmd "jq"     "sudo apt install -y jq"
check_cmd "curl"   "sudo apt install -y curl"

# Chrome is optional (only needed for LinkedIn integration)
if command -v google-chrome &>/dev/null || command -v chromium-browser &>/dev/null; then
    log "Chrome/Chromium found (needed for LinkedIn integration)"
else
    warn "Chrome/Chromium not found. Optional -- only needed for LinkedIn integration."
    warn "  Install: sudo apt install -y chromium-browser"
fi

# Bun is optional (only needed for Telegram plugin)
if command -v bun &>/dev/null; then
    log "Bun found (needed for Telegram plugin runtime)"
else
    warn "Bun not found. Optional -- only needed for Telegram channel plugin."
    warn "  Install: curl -fsSL https://bun.sh/install | bash"
fi

if [ "$MISSING" -gt 0 ]; then
    fail "$MISSING required tool(s) missing. Install them and re-run this script."
    exit 1
fi

echo ""
log "All required prerequisites found."
echo ""

# ============================================================================
# DIRECTORY STRUCTURE
# ============================================================================
info "Setting up directory structure..."

# If running from a cloned repo, use it as AGUIA_HOME
if [ -f "$SCRIPT_DIR/orchestrator/dispatch.sh" ]; then
    AGUIA_HOME="$SCRIPT_DIR"
    log "Using cloned repo at $AGUIA_HOME"
fi

mkdir -p "$AGUIA_HOME"/{shared/logs,shared/memory,wiki/raw,wiki/compiled}
log "Directory structure ready at $AGUIA_HOME"

# ============================================================================
# ENVIRONMENT FILE
# ============================================================================
info "Setting up environment..."

ENV_FILE="$AGUIA_HOME/.env"
ENV_EXAMPLE="$AGUIA_HOME/.env.example"

if [ -f "$ENV_FILE" ]; then
    log ".env already exists -- skipping (edit manually if needed)"
else
    if [ -f "$ENV_EXAMPLE" ]; then
        cp "$ENV_EXAMPLE" "$ENV_FILE"
        log "Created .env from .env.example"
    else
        cat > "$ENV_FILE" <<'ENVEOF'
# Aguia Environment Configuration
# Fill in your values below.

# Telegram Bot (create via @BotFather on Telegram)
TELEGRAM_BOT_TOKEN=
OWNER_DM=

# Optional: Team bot for agent groups
TEAM_BOT_TOKEN=
TEAM_GROUP_A=
TEAM_GROUP_B=

# Optional: WAsenderAPI for WhatsApp integration (~$6/mo)
WASENDER_API_KEY=
WASENDER_DEVICE_ID=

# Claude Code OAuth token (populated by: claude auth token)
# Normally sourced from ~/.claude_token at runtime
ENVEOF
        log "Created .env template"
    fi

    echo ""
    read -rp "Enter your Telegram bot token (or press Enter to skip): " TG_TOKEN
    if [ -n "$TG_TOKEN" ]; then
        sed -i.bak "s/^TELEGRAM_BOT_TOKEN=.*/TELEGRAM_BOT_TOKEN=$TG_TOKEN/" "$ENV_FILE" && rm -f "${ENV_FILE}.bak"
        log "Telegram bot token saved to .env"
    else
        warn "Skipped Telegram token. Edit .env later to add it."
    fi

    read -rp "Enter your Telegram chat ID (or press Enter to skip): " TG_CHAT
    if [ -n "$TG_CHAT" ]; then
        sed -i.bak "s/^OWNER_DM=.*/OWNER_DM=$TG_CHAT/" "$ENV_FILE" && rm -f "${ENV_FILE}.bak"
        log "Telegram chat ID saved to .env"
    else
        warn "Skipped Telegram chat ID. Edit .env later to add it."
    fi
fi

# ============================================================================
# CLAUDE CODE OAUTH TOKEN
# ============================================================================
info "Setting up Claude Code authentication..."

TOKEN_FILE="$HOME/.claude_token"
if [ -f "$TOKEN_FILE" ]; then
    log "~/.claude_token already exists"
else
    if command -v claude &>/dev/null; then
        TOKEN=$(claude auth token 2>/dev/null || true)
        if [ -n "$TOKEN" ]; then
            echo "export CLAUDE_CODE_OAUTH_TOKEN=\"$TOKEN\"" > "$TOKEN_FILE"
            log "Saved OAuth token to ~/.claude_token"
        else
            warn "Could not get Claude auth token. Run 'claude auth login' first, then re-run this script."
            echo 'export CLAUDE_CODE_OAUTH_TOKEN=""' > "$TOKEN_FILE"
        fi
    fi
fi

# ============================================================================
# MAKE SCRIPTS EXECUTABLE
# ============================================================================
info "Setting script permissions..."

chmod +x "$AGUIA_HOME"/orchestrator/*.sh 2>/dev/null || true
chmod +x "$AGUIA_HOME"/scripts/*.sh 2>/dev/null || true
chmod +x "$AGUIA_HOME"/agents/create-agent.sh 2>/dev/null || true
chmod +x "$AGUIA_HOME"/install.sh 2>/dev/null || true
log "All scripts marked executable"

# ============================================================================
# CRONTAB SETUP
# ============================================================================
info "Setting up cron jobs..."

CRON_MARKER="# AGUIA-MANAGED"
EXISTING_CRON=$(crontab -l 2>/dev/null || true)

if echo "$EXISTING_CRON" | grep -q "$CRON_MARKER"; then
    log "Aguia cron entries already present -- skipping"
else
    echo ""
    info "The following cron entries will be added:"
    echo "  - Keepalive (every 5 min)"
    echo "  - Responsiveness watchdog (every 1 min)"
    echo "  - Session health (every 15 min)"
    echo ""
    read -rp "Add cron entries? [y/N]: " ADD_CRON
    if [[ "$ADD_CRON" =~ ^[Yy]$ ]]; then
        CRON_BLOCK="
$CRON_MARKER -- START (do not edit this block manually)
SHELL=/bin/bash
PATH=/usr/local/bin:/usr/bin:/bin:$HOME/.local/bin
AGUIA_HOME=$AGUIA_HOME

# Keepalive: restart interactive session if it dies
*/5 * * * * $AGUIA_HOME/orchestrator/keepalive.sh >> $AGUIA_HOME/shared/logs/keepalive.log 2>&1

# Responsiveness watchdog: interrupt stuck sessions
* * * * * $AGUIA_HOME/orchestrator/responsiveness-watchdog.sh 2>/dev/null

# Session health: auto-compact at high context usage
*/15 * * * * $AGUIA_HOME/orchestrator/session-health.sh >> $AGUIA_HOME/shared/logs/session-health.log 2>&1

# Reboot resilience: restart after server reboot
@reboot sleep 30 && $AGUIA_HOME/orchestrator/keepalive.sh >> $AGUIA_HOME/shared/logs/keepalive.log 2>&1
$CRON_MARKER -- END"

        (echo "$EXISTING_CRON"; echo "$CRON_BLOCK") | crontab -
        log "Cron entries added. Run 'crontab -l' to verify."
    else
        warn "Skipped cron setup. See examples/crontab.example for reference."
    fi
fi

# ============================================================================
# SYSTEMD TIMERS (optional, if systemd is available)
# ============================================================================
if command -v systemctl &>/dev/null && [ -d /etc/systemd/system ]; then
    info "Systemd detected. Timer units available in systemd/ directory."
    info "To install: sudo cp systemd/*.service systemd/*.timer /etc/systemd/system/"
    info "Then: sudo systemctl enable --now keepalive.timer agent-dispatch.timer"
else
    info "Systemd not detected -- using cron for scheduling (this is fine)."
fi

# ============================================================================
# CREATE EXAMPLE AGENT (if none exist besides templates)
# ============================================================================
AGENT_COUNT=$(find "$AGUIA_HOME/agents" -maxdepth 1 -mindepth 1 -type d 2>/dev/null | wc -l)
if [ "$AGENT_COUNT" -le 3 ]; then
    info "Tip: Create your first custom agent with:"
    info "  $AGUIA_HOME/agents/create-agent.sh my-first-agent \"My first autonomous agent\""
fi

# ============================================================================
# KEEPALIVE START (optional)
# ============================================================================
echo ""
read -rp "Start the keepalive now? (requires tmux + Telegram token) [y/N]: " START_KA
if [[ "$START_KA" =~ ^[Yy]$ ]]; then
    source "$TOKEN_FILE" 2>/dev/null && export CLAUDE_CODE_OAUTH_TOKEN
    if [ -n "${CLAUDE_CODE_OAUTH_TOKEN:-}" ] && [ -n "$(grep -oP 'TELEGRAM_BOT_TOKEN=\K.+' "$ENV_FILE" 2>/dev/null)" ]; then
        "$AGUIA_HOME/orchestrator/keepalive.sh" &
        log "Keepalive started in background"
    else
        warn "Missing CLAUDE_CODE_OAUTH_TOKEN or TELEGRAM_BOT_TOKEN. Fix .env and ~/.claude_token first."
    fi
else
    info "Skipped keepalive start."
fi

# ============================================================================
# SUCCESS
# ============================================================================
echo ""
echo "======================================"
echo "  Aguia installation complete!"
echo "======================================"
echo ""
info "Next steps:"
echo "  1. Edit $AGUIA_HOME/.env with your bot tokens and chat IDs"
echo "  2. Run 'claude auth login' if you haven't already"
echo "  3. Create agents: ./agents/create-agent.sh <name> \"<description>\""
echo "  4. Test a dispatch: ./orchestrator/dispatch.sh example-agent \"Hello!\""
echo "  5. Start interactive session:"
echo "     tmux new-session -d -s aguia \\"
echo "       \"cd $AGUIA_HOME && claude --channels plugin:telegram@claude-plugins-official \\"
echo "        --dangerously-skip-permissions --model opus\""
echo ""
info "Full crontab example: examples/crontab.example"
info "Agent ideas and templates: examples/agent-fleet.md"
info "Documentation: README.md"
echo ""
log "Happy automating!"

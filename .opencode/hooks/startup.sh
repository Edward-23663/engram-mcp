#!/bin/bash
# OpenCode Startup Hook for Engram MCP Auto-Healer
# This script runs when opencode starts

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
HEALER_SCRIPT="$SCRIPT_DIR/start_mcp_healer.sh"
LOG_FILE="/tmp/opencode_startup_hook.log"

# Colors
GREEN='\033[0;32m'
BLUE='\033[0;34m'
NC='\033[0m'

log() {
    echo -e "${BLUE}[opencode-startup]${NC} $(date '+%Y-%m-%d %H:%M:%S') - $1" | tee -a "$LOG_FILE"
}

success() {
    echo -e "${GREEN}✓${NC} $1" | tee -a "$LOG_FILE"
}

# Check if healer script exists
if [ ! -f "$HEALER_SCRIPT" ]; then
    log "MCP auto-healer script not found at $HEALER_SCRIPT"
    exit 0
fi

# Make sure it's executable
chmod +x "$HEALER_SCRIPT" 2>/dev/null || true

log "Starting Engram MCP Auto-Healer on opencode startup..."
log "Script: $HEALER_SCRIPT"

# Start the healer
if "$HEALER_SCRIPT" start; then
    success "Engram MCP Auto-Healer started successfully"
    
    # Wait a moment and test
    sleep 3
    if "$HEALER_SCRIPT" test; then
        success "MCP server test passed"
    else
        log "MCP server test failed (may need more time to start)"
    fi
else
    log "Failed to start Engram MCP Auto-Healer"
fi

log "OpenCode startup hook completed"
log "========================================"
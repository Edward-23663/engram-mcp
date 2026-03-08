#!/bin/bash
# Engram MCP Auto-Healer Startup Script
# This script should be configured to run when opencode starts

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOG_FILE="/tmp/engram_mcp_startup.log"
PID_FILE="/tmp/engram_mcp_healer.pid"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

log() {
    echo -e "${BLUE}[$(date '+%Y-%m-%d %H:%M:%S')]${NC} $1" | tee -a "$LOG_FILE"
}

success() {
    echo -e "${GREEN}✓${NC} $1" | tee -a "$LOG_FILE"
}

warning() {
    echo -e "${YELLOW}⚠${NC} $1" | tee -a "$LOG_FILE"
}

error() {
    echo -e "${RED}✗${NC} $1" | tee -a "$LOG_FILE"
}

check_dependencies() {
    log "Checking dependencies..."
    
    # Check Python
    if command -v python3 &> /dev/null; then
        success "Python3 is available"
    else
        error "Python3 is not installed"
        return 1
    fi
    
    # Check Docker
    if command -v docker &> /dev/null; then
        success "Docker is available"
    else
        warning "Docker is not available (some checks may fail)"
    fi
    
    # Check MCP script
    if [ -f "$SCRIPT_DIR/engram-mcp/mcp_auto_healer.py" ]; then
        success "MCP auto-healer script found"
    else
        error "MCP auto-healer script not found"
        return 1
    fi
    
    return 0
}

check_if_running() {
    if [ -f "$PID_FILE" ]; then
        PID=$(cat "$PID_FILE")
        if ps -p "$PID" > /dev/null 2>&1; then
            log "MCP auto-healer is already running (PID: $PID)"
            return 0
        else
            warning "Stale PID file found, removing..."
            rm -f "$PID_FILE"
        fi
    fi
    return 1
}

start_healer() {
    log "Starting Engram MCP Auto-Healer..."
    
    # Check if already running
    if check_if_running; then
        warning "Auto-healer is already running"
        return 0
    fi
    
    # Start in background
    cd "$SCRIPT_DIR"
    nohup python3 engram-mcp/mcp_auto_healer.py >> "$LOG_FILE" 2>&1 &
    
    HEALER_PID=$!
    echo "$HEALER_PID" > "$PID_FILE"
    
    # Wait a moment to check if it started
    sleep 2
    
    if ps -p "$HEALER_PID" > /dev/null 2>&1; then
        success "Engram MCP Auto-Healer started (PID: $HEALER_PID)"
        log "Logs: $LOG_FILE"
        log "PID file: $PID_FILE"
        return 0
    else
        error "Failed to start Engram MCP Auto-Healer"
        rm -f "$PID_FILE"
        return 1
    fi
}

stop_healer() {
    log "Stopping Engram MCP Auto-Healer..."
    
    if [ -f "$PID_FILE" ]; then
        PID=$(cat "$PID_FILE")
        
        if ps -p "$PID" > /dev/null 2>&1; then
            kill "$PID" 2>/dev/null
            sleep 1
            
            if ps -p "$PID" > /dev/null 2>&1; then
                warning "Process did not terminate, forcing..."
                kill -9 "$PID" 2>/dev/null
            fi
            
            success "Engram MCP Auto-Healer stopped"
        else
            warning "Process not found (may have already stopped)"
        fi
        
        rm -f "$PID_FILE"
    else
        warning "PID file not found"
    fi
}

status_healer() {
    log "Engram MCP Auto-Healer Status"
    echo "========================================"
    
    if check_if_running; then
        PID=$(cat "$PID_FILE")
        success "Status: RUNNING (PID: $PID)"
        
        # Check recent logs
        if [ -f "$LOG_FILE" ]; then
            echo ""
            log "Recent logs (last 10 lines):"
            tail -10 "$LOG_FILE"
        fi
    else
        error "Status: STOPPED"
    fi
    
    echo "========================================"
}

test_mcp() {
    log "Testing MCP server..."
    
    cd "$SCRIPT_DIR"
    echo '{"jsonrpc":"2.0","method":"tools/list","id":1}' | python3 engram-mcp/mcp_direct.py 2>/dev/null | grep -q '"tools"'
    
    if [ $? -eq 0 ]; then
        success "MCP server test passed"
        return 0
    else
        error "MCP server test failed"
        return 1
    fi
}

case "$1" in
    start)
        check_dependencies
        start_healer
        ;;
    stop)
        stop_healer
        ;;
    restart)
        stop_healer
        sleep 2
        start_healer
        ;;
    status)
        status_healer
        ;;
    test)
        test_mcp
        ;;
    *)
        echo "Usage: $0 {start|stop|restart|status|test}"
        echo ""
        echo "Commands:"
        echo "  start   - Start the MCP auto-healer"
        echo "  stop    - Stop the MCP auto-healer"
        echo "  restart - Restart the MCP auto-healer"
        echo "  status  - Check status of the auto-healer"
        echo "  test    - Test MCP server functionality"
        exit 1
        ;;
esac
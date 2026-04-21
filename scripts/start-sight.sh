#!/bin/bash
# G-Codex: Sight Socket Launcher (Phase 22c Handshake Reset)
# Launches Chrome for Testing and attaches the MCP vision socket.

LOG_FILE=".sight_mcp.log"
USER_DATA_DIR="/tmp/g-codex-sight"
PORT=9222

echo "✦ [1/3] Initializing G-Codex Sight..." | tee "$LOG_FILE"

# 1. Locate Chrome for Testing
CHROME_BIN=$(find ~/chrome -name "chrome" -type f -executable 2>/dev/null | grep "chrome-linux64" | head -n 1)

if [ -z "$CHROME_BIN" ]; then
    echo "⚠ Error: Chrome for Testing not found in ~/chrome." | tee -a "$LOG_FILE"
    exit 1
fi

# 2. Launch Chrome if not running
if ss -tuln | grep -q ":$PORT "; then
    echo "✦ Port $PORT is already active." | tee -a "$LOG_FILE"
else
    echo "✦ Launching Chrome for Testing on port $PORT..." | tee -a "$LOG_FILE"
    nohup "$CHROME_BIN" \
        --remote-debugging-port=$PORT \
        --user-data-dir="$USER_DATA_DIR" \
        --no-first-run \
        --no-sandbox \
        --disable-dev-shm-usage \
        &> /dev/null &
    
    # Wait for port
    for i in {1..10}; do
        if ss -tuln | grep -q ":$PORT "; then break; fi
        sleep 1
    done
fi

# 3. Attach MCP Vision Socket (One stable attempt with logs)
echo "✦ [2/3] Attaching chrome-devtools-mcp..." | tee -a "$LOG_FILE"
# We use --browser-url to ensure it targets the correct local instance
nohup npx -y chrome-devtools-mcp@latest --browser-url=http://127.0.0.1:$PORT --no-usage-statistics >> "$LOG_FILE" 2>&1 &
MCP_PID=$!

echo "✦ [3/3] Sight Handshake initiated (MCP PID: $MCP_PID)." | tee -a "$LOG_FILE"
echo "✦ Check Dashboard for ✦ Sight: Verified (Green) or Partial (Amber)."

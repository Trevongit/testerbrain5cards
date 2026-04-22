#!/bin/bash
# G-Codex: Hardened Sight Socket Launcher (Phase 22d/23 Stability Patch)
# Purpose: Ensure reliable Chrome for Testing -> MCP connection and Dashboard visibility.

LOG_FILE=".sight_hardened.log"
USER_DATA_DIR="/tmp/g-codex-sight"
PORT=9222
DASHBOARD_URL="file:///home/trev/PROJECTS/workspace2/g-code-brain-template/scripts/named_agent_dashboard.html"

echo "✦ [1/6] Aggressive Cleanup..." | tee "$LOG_FILE"
# Kill anything on 9222 and any lingering MCP processes
fuser -k $PORT/tcp &> /dev/null
pkill -f "chrome-devtools-mcp" &> /dev/null
pkill -f "chrome-linux64/chrome" &> /dev/null
sleep 2

echo "✦ [2/6] Locating Chrome for Testing..." | tee -a "$LOG_FILE"
CHROME_BIN=$(find ~/chrome -name "chrome" -type f -executable 2>/dev/null | grep "chrome-linux64" | head -n 1)

if [ -z "$CHROME_BIN" ]; then
    echo "⚠ Error: Chrome for Testing binary not found in ~/chrome." | tee -a "$LOG_FILE"
    exit 1
fi
echo "✦ Found: $CHROME_BIN" | tee -a "$LOG_FILE"

echo "✦ [3/6] Launching Clean Chrome for Testing..." | tee -a "$LOG_FILE"
# Standard stable flags + Clean Room profile
nohup "$CHROME_BIN" \
    --remote-debugging-port=$PORT \
    --user-data-dir="$USER_DATA_DIR" \
    --no-sandbox \
    --disable-dev-shm-usage \
    --no-first-run \
    --no-default-browser-check \
    --remote-allow-origins="*" \
    "$DASHBOARD_URL" &> /dev/null &

echo "✦ [4/6] Waiting 15s for Chrome to stabilize..." | tee -a "$LOG_FILE"
for i in {15..1}; do
    echo -n "$i... "
    sleep 1
done
echo ""

if ss -tuln | grep -q ":$PORT "; then
    echo "✦ Port $PORT is active." | tee -a "$LOG_FILE"
else
    echo "⚠ Error: Port $PORT failed to open. Check .sight_hardened.log" | tee -a "$LOG_FILE"
    exit 1
fi

echo "✦ [5/6] Attaching MCP Vision Socket (Keep-Alive)..." | tee -a "$LOG_FILE"
attach_mcp() {
    while true; do
        echo "[$(date +'%T')] ✦ Launching chrome-devtools-mcp..." >> "$LOG_FILE"
        # --browser-url specifies the target; --no-usage-statistics prevents interactive prompts
        npx -y chrome-devtools-mcp@latest --browser-url=http://127.0.0.1:$PORT --no-usage-statistics >> "$LOG_FILE" 2>&1
        EXIT_CODE=$?
        echo "[$(date +'%T')] ⚠ MCP exited with code $EXIT_CODE. Restarting in 5s..." >> "$LOG_FILE"
        sleep 5
    done
}

# Run the attach loop in the background
attach_mcp &
ATTACH_PID=$!

echo "✦ [6/6] Sight Protocol Active (Keep-Alive PID: $ATTACH_PID)" | tee -a "$LOG_FILE"
echo "--------------------------------------------------------"
echo "✦ SUCCESS: Dashboard should be open in the Testing Browser."
echo "✦ Check your Dashboard header for the green ✦ Sight pill."
echo "--------------------------------------------------------"
echo "✦ Diagnostic commands to run if the pill stays amber/offline:"
echo "  1. ss -tuln | grep :$PORT"
echo "  2. ps aux | grep -E 'chrome|devtools-mcp'"
echo "  3. tail -f $LOG_FILE"

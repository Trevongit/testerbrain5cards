#!/bin/bash
echo "🔧 G-Codex Sight Hardened Gentle v2"

LOG_FILE=".sight_hardened.log"
USER_DATA_DIR="/tmp/g-codex-sight"
PORT=9222
DASHBOARD_URL="file:///home/trev/PROJECTS/workspace2/g-code-brain-template/scripts/named_agent_dashboard.html"

echo "✦ [1/6] Gentle Cleanup..." | tee "$LOG_FILE"
fuser -k $PORT/tcp &> /dev/null || true
pkill -f chrome-devtools-mcp &> /dev/null || true
sleep 2

echo "✦ [2/6] Locating Chrome..." | tee -a "$LOG_FILE"
CHROME_BIN=$(find ~/chrome -name "chrome" -type f -executable 2>/dev/null | grep "chrome-linux64" | head -n 1)

echo "✦ [3/6] Launching Clean Chrome..." | tee -a "$LOG_FILE"
nohup "$CHROME_BIN" \
  --remote-debugging-port=$PORT \
  --user-data-dir="$USER_DATA_DIR" \
  --no-sandbox \
  --disable-dev-shm-usage \
  --no-first-run \
  --no-default-browser-check \
  --remote-allow-origins="*" \
  "$DASHBOARD_URL" &> /dev/null &

echo "✦ [4/6] Waiting 15s for stabilization..." | tee -a "$LOG_FILE"
for i in {15..1}; do echo -n "$i... "; sleep 1; done
echo ""

echo "✦ [5/6] Starting MCP with --browser-url..." | tee -a "$LOG_FILE"
nohup npx -y chrome-devtools-mcp@latest \
  --browser-url=http://127.0.0.1:$PORT \
  --no-usage-statistics -y \
  >> "$LOG_FILE" 2>&1 &

echo "✦ [6/6] Dashboard opened in clean Chrome. MCP keep-alive started." | tee -a "$LOG_FILE"
echo "--------------------------------------------------------"
echo "✦ Check the clean Chrome window for the Sight pill."
echo "--------------------------------------------------------"

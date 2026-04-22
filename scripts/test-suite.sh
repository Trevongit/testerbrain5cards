#!/usr/bin/env bash
# G-Codex Testing & Validation Suite (P9)
# Validates core system scripts for deterministic, local-first operation.

set -euo pipefail

# --- 🧪 CONFIGURATION ---
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
TEST_RUNTIME="${ROOT_DIR}/test_runtime"
PORT=8765

# --- 🎨 COLORS ---
GREEN='\033[0;32m'
RED='\033[0;31m'
NC='\033[0m' # No Color

log_step() { echo -e "\n🔍 ${GREEN}STEP: $1${NC}"; }
log_fail() { echo -e "\n❌ ${RED}FAIL: $1${NC}"; exit 1; }
log_pass() { echo -e "✅ $1"; }

cleanup() {
  log_step "Cleaning up test runtime..."
  # Kill any process on our test port
  fuser -k ${PORT}/tcp 2>/dev/null || true
  # Remove temp directory
  rm -rf "${TEST_RUNTIME}"
  log_pass "Cleanup complete."
}

trap cleanup EXIT

# --- 🚀 EXECUTION ---

# 0. Setup
log_step "Initializing Test Runtime..."
[[ -d "${TEST_RUNTIME}" ]] && rm -rf "${TEST_RUNTIME}"
mkdir -p "${TEST_RUNTIME}"
cd "${TEST_RUNTIME}"
git init -q
log_pass "Temporary repo initialized at ${TEST_RUNTIME}"

# 1. Test: Bootstrap
log_step "Test 1: Bootstrap Validation"
# Provide Repository Name, Description, and Answer "n" to starting server now.
printf "TestRepo\nTesting validation suite description\nn\n" | bash "${SCRIPT_DIR}/bootstrap-brain.sh" . > /dev/null

required_files=(
  "AGENTS.md"
  "G-Codex-brain/00_BOOTSTRAP_GUIDE.md"
  "G-Codex-brain/00_INDEX.md"
  "G-Codex-brain/03_ACTIVE_NOW.md"
  "scripts/conductor.sh"
  "scripts/brain_server.py"
)

for f in "${required_files[@]}"; do
  [[ -f "$f" ]] || log_fail "Missing $f after bootstrap."
done

grep -q "TestRepo" AGENTS.md || log_fail "Bootstrap failed to localize AGENTS.md"
log_pass "Bootstrap successful. Files present and localized."

# 2. Test: Dashboard & Server
log_step "Test 2: Control Room / Brain Server connectivity"
# Kill existing port just in case
fuser -k ${PORT}/tcp 2>/dev/null || true

# Start server in background (manual start since we skipped it in bootstrap)
python3 "${TEST_RUNTIME}/scripts/brain_server.py" > /dev/null 2>&1 &
SERVER_PID=$!
sleep 2 # Give it a second to bind

if ! curl -s "http://127.0.0.1:${PORT}/context" > /dev/null; then
  log_fail "Brain Server failed to start on port ${PORT}"
fi
log_pass "Brain Server is alive and responding (PID: $SERVER_PID)"

# 3. Test: Auto-Approval Gate
log_step "Test 3: Auto-Approval Gate (Logic & Logging)"
echo "Surgical typo fix for validation." > test.txt
git add test.txt
# Must be >= 8 words and contain no forbidden keywords
bash "${TEST_RUNTIME}/scripts/conductor.sh" auto-approve "Correcting this should pass as it is a valid surgical typo fix"

if ! git log -1 --pretty=oneline | grep -q "auto:"; then
  log_fail "Auto-approve commit not found."
fi

if ! grep -q "Auto-Approval Gate" G-Codex-brain/DYNAMIC_MEMORY.md; then
  log_fail "Auto-approve action not logged to DYNAMIC_MEMORY.md"
fi
log_pass "Auto-Approval Gate successfully committed and logged changes."

# 4. Test: Hand-off Context Validation
log_step "Test 4: Hand-off Context Validation"
CONTEXT_JSON=$(curl -s "http://127.0.0.1:${PORT}/context")

# Verify Repo name is correct in the JSON
if ! echo "$CONTEXT_JSON" | grep -q "\"name\": \"test_runtime\""; then
  log_fail "Hand-off context: Incorrect repo name in JSON"
fi

# Verify 03_ACTIVE_NOW.md context is present
if ! echo "$CONTEXT_JSON" | grep -q "03_ACTIVE_NOW.md"; then
  log_fail "Hand-off context: Missing 03_ACTIVE_NOW.md in payload"
fi
log_pass "Hand-off Context JSON contains all required data for P8 features."

# --- ✨ SUMMARY ---
echo -e "\n---------------------------------------------------"
echo -e "🎉 ${GREEN}ALL TESTS PASSED SUCCESSFULLY${NC}"
echo -e "---------------------------------------------------"
echo "G-Codex Control Room is mission-ready."

# 09 AUTOMATED AGENT SWARM


## Purpose
Turn low-risk coding slices into one-button operations while preserving determinism, local-first, anti-drift, and human consent on anything non-trivial.



## Priority 1: Antigravity Mission Control (Recommended Starting Point)


### Why this is first
Antigravity Mission Control gives immediate leverage with the least implementation effort: one saved mission, stable role assignments, explicit approval gate, and automatic logging discipline.


### Create a saved mission: `G-Codex Low-Risk Swarm`

1. Create a new mission in Antigravity named `G-Codex Low-Risk Swarm`.
2. Add three fixed agent roles:
   - `OAC@mint-laptop` (executor): writes code/docs and runs checks.
   - `GEMINI3` (reviewer): validates correctness and edge cases.
   - `GROK` (alignment checker): validates ethos alignment (determinism, local-first, anti-drift).
3. Set mission mode to low-risk slices only.
4. Require final human confirm for any filesystem-wide refactor, secrets, infra, or dependency upgrades.


### Copy-paste mission prompt template


```text
Mission: G-Codex Low-Risk Swarm

Context:
- Read AGENTS.md
- Read G-Codex-brain/00_BOOTSTRAP_GUIDE.md
- Read G-Codex-brain/03_ACTIVE_NOW.md
- Read G-Codex-brain/MERGE_LOG.md
- Read G-Codex-brain/DYNAMIC_MEMORY.md

Slice Input:
{{SLICE_DESCRIPTION}}

Role Contract:
1) OAC@mint-laptop (Executor)
- Implement smallest deterministic slice.
- Run local verification commands.
- Produce patch + command log.

2) GEMINI3 (Reviewer)
- Check behavior regressions, edge cases, and missing tests.
- Approve or request exact changes.

3) GROK (Alignment Checker)
- Confirm anti-drift: no unverified claims.
- Confirm local-first and deterministic constraints are preserved.
- Confirm no high-risk action bypassed consent gate.

Approval Gate:
- If risk class is LOW and all three roles agree: proceed.
- If risk is MEDIUM/HIGH or disagreement exists: stop and request human approval.

Required Outputs:
- Files changed list.
- Verification results.
- MERGE_LOG entry text draft.
- DYNAMIC_MEMORY session log entry text draft.

```


### Low-risk classifier (mission input)


```text
LOW RISK if all are true:
- <= 5 files changed
- no secrets/auth/infra/dependencies touched
- no data migration
- no production config changes
- easy rollback

```


### Auto-update protocol for memory files

At mission completion, append:

1. `G-Codex-brain/MERGE_LOG.md`
   - one canonical row with date, slice, commit, author.
2. `G-Codex-brain/DYNAMIC_MEMORY.md`
   - one `SESSION_LOG_ENTRY` block with actions, verification, blockers, next step.


### Next Step
Create this mission first and run one trivial slice (for example: docs typo fix) to validate end-to-end swarm behavior.


## Priority 2: Local G-Codex Conductor Script


### Goal
Add a local dispatcher script that converts a plain-language slice into consistent multi-agent work packets.


### File target
`scripts/conductor.sh`


### Functional spec
1. Accept one required argument: slice description.
2. Load canonical context files.
3. Generate a structured task packet.
4. Dispatch packet to available agents (current shell integrations first).
5. Print a deterministic execution summary.


### Starter code (drop-in)


```bash
#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 1 ]]; then
  echo "Usage: $(basename "$0") \"<slice description>\"" >&2
  exit 1
fi

SLICE_DESC="$1"
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BRAIN_DIR="${ROOT_DIR}/G-Codex-brain"

required=(
  "${ROOT_DIR}/AGENTS.md"
  "${BRAIN_DIR}/00_BOOTSTRAP_GUIDE.md"
  "${BRAIN_DIR}/03_ACTIVE_NOW.md"
  "${BRAIN_DIR}/MERGE_LOG.md"
  "${BRAIN_DIR}/DYNAMIC_MEMORY.md"
)

for f in "${required[@]}"; do
  [[ -f "${f}" ]] || { echo "Missing required context: ${f}" >&2; exit 1; }
done

PACKET_FILE="${ROOT_DIR}/.swarm_packet.txt"
cat > "${PACKET_FILE}" <<PACKET
SLICE: ${SLICE_DESC}
ROLE_EXECUTOR: OAC@mint-laptop
ROLE_REVIEWER: GEMINI3
ROLE_ALIGNMENT: GROK
RISK_CLASSIFIER: LOW_ONLY
CONTEXT_FILES:
- AGENTS.md
- G-Codex-brain/00_BOOTSTRAP_GUIDE.md
- G-Codex-brain/03_ACTIVE_NOW.md
- G-Codex-brain/MERGE_LOG.md
- G-Codex-brain/DYNAMIC_MEMORY.md
PACKET

echo "Created packet: ${PACKET_FILE}"
echo "Next: send packet to executor/reviewer/alignment agents via your local tooling."

```


### Next Step
Create `scripts/conductor.sh`, make it executable, and test with one low-risk slice text.


## Priority 3: Browser-First Grok Mode


### Goal
Make Grok browser sessions zero-friction while still grounded in brain context.


### Option A: Bookmarklet (quickest)

Save as browser bookmark URL:


```javascript
javascript:(async()=>{const txt=`Read AGENTS.md + G-Codex-brain/00_BOOTSTRAP_GUIDE.md + 03_ACTIVE_NOW.md + MERGE_LOG.md. Then assist only with deterministic, local-first, anti-drift slices.`;try{await navigator.clipboard.writeText(txt);}catch(e){}window.open('https://grok.com/','_blank');alert('Swarm context copied to clipboard. Paste into Grok.');})();

```


### Option B: Userscript (auto-paste helper)

Use Tampermonkey/Greasemonkey to inject a reusable context snippet button on Grok chat pages.


### Option C: MCP handoff

Expose a local endpoint returning latest brain context and instruct Grok sessions to consume it before planning.


### Next Step
Start with the bookmarklet. It is the fastest path and keeps onboarding under 2 minutes.


## Priority 4: MCP-Powered Shared Brain


### Goal
Replace manual copy-paste with a local shared-brain service for all agents.


### High-level architecture
1. Local server reads canonical brain files.
2. Agents request context payload by role.
3. Agents post append-only memory updates.
4. Human approval gate remains external and explicit.


### Minimal Python server starter (single-file)


```python
#!/usr/bin/env python3
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
import json

ROOT = Path(__file__).resolve().parents[1]
BRAIN = ROOT / "G-Codex-brain"

CONTEXT_FILES = [
    ROOT / "AGENTS.md",
    BRAIN / "00_BOOTSTRAP_GUIDE.md",
    BRAIN / "03_ACTIVE_NOW.md",
    BRAIN / "MERGE_LOG.md",
    BRAIN / "DYNAMIC_MEMORY.md",
]

class Handler(BaseHTTPRequestHandler):
    def _json(self, payload, status=200):
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path != "/context":
            self._json({"error": "not found"}, 404)
            return
        data = {}
        for path in CONTEXT_FILES:
            if path.exists():
                data[str(path.relative_to(ROOT))] = path.read_text(encoding="utf-8")
        self._json({"context": data})

if __name__ == "__main__":
    HTTPServer(("127.0.0.1", 8765), Handler).serve_forever()

```


### Next Step
Run this locally and validate one agent can fetch `/context` before executing a slice.


## Priority 5: Named-Agent Dashboard (OPERATIONAL)


### Goal
Provide a local control room for operator visibility, deterministic dispatch, and live team telemetry.


### Operational Features
1. **Dispatch Swarm button is functional** in `scripts/named_agent_dashboard.html`.
2. **Risk capture is wired** (`LOW ADVENTURE`, `MEDIUM ADVENTURE`, `HIGH ADVENTURE`).
3. **Live brain context is fetched** from `/context` before dispatch.
4. **Packet generation is local** via `POST /dispatch`, writing root `.swarm_packet.txt`.
5. **Realtime injections feed is live** via `GET /activity` polling every 8 seconds.
6. **Visual roadmap mindmap is live** in the control room via Mermaid CDN.


### Packet Contract (Current)

```text
# G-Codex Swarm Packet
Timestamp: <ISO timestamp>
Repo: <repo.name>
Risk Level: <LOW|MEDIUM|HIGH ADVENTURE>
Slice: <operator input>
Context Summary: <excerpt from 03_ACTIVE_NOW.md>
---
Ready for Triad of Truth execution.
```


### Current Local Endpoints
1. `GET /context`: canonical brain context + repo metadata.
2. `POST /dispatch`: validates payload and writes `.swarm_packet.txt`.
3. `GET /activity`: combines latest `DYNAMIC_MEMORY.md` entries plus swarm packet activity.
4. `POST /activity`: refresh signal endpoint for bridge-driven immediate feed updates.


## Priority 11: G-Codex Bridge Protocol (OPERATIONAL)


### Goal
Create a local-first bridge from browser LLM chats to deterministic brain memory injections.


### Components
1. `scripts/bridge.user.js`: userscript button (`⚡ G-Codex`) on supported LLM domains.
2. `scripts/watcher.py`: clipboard watcher polling every 2 seconds via `xclip`.
3. `./scripts/conductor.sh watch`: background watcher process management with `.watcher.pid`.


### Bridge Protocol
1. User clicks `⚡ G-Codex` beside a model response.
2. Userscript copies a standardized injection block.
3. Watcher detects header `### 🧠 G-CODEX INJECTION:`.
4. Watcher appends deterministic memory entry into `G-Codex-brain/DYNAMIC_MEMORY.md`.
5. Watcher sends local `POST /activity` to refresh dashboard feed immediately.


### Injection Block Example

```text
### 🧠 G-CODEX INJECTION:
Source: Gemini 3
Timestamp: 2026-04-01T12:00:00+11:00
Content:
We validated the low-risk patch and propose a minimal follow-up test.
```


### Deterministic Safety Controls
1. De-duplicates by content hash (`md5`) against last 5 bridge injections.
2. Never writes unless canonical header is present.
3. Stores source and timestamp with each appended block.


## Priority 6: Risk-Aware Auto-Approval Gate (OPERATIONAL)


### Goal

Enable true one-button execution for genuinely low-risk slices while strictly preserving human consent for core memory and architectural changes.


### Usage


```bash
./scripts/conductor.sh auto-approve "your descriptive slice message (min 8 words)"

```


### Auto-Approval Safety Gate Logic

Implementation: `scripts/conductor.sh auto_approve` function.

1. **Staged Changes Only**: The gate only acts on changes explicitly added via `git add`.
2. **"Brain" Lockdown**: Any file in `G-Codex-brain/` or high-risk keywords like `refactor` or `secret` trigger a rejection.
3. **Small-Slice Constraint**: Limited to $\le$ 5 modified files.
4. **Clean Baseline**: Rejects if unstaged changes exist.


### The Triad of Truth Consensus (Surgical Implementation)

Every auto-approval is signed off by a deterministic consensus of three core roles:

- **GROK (Alignment)**: Validates against `forbidden` keyword drift (`refactor|delete|remove|secret|brain|G-Codex-brain`).
- **GEMINI 3 (Logic)**: Validates git state (clean) and file count ($\le$ 5).
- **CHATGPT (Clarity)**: Enforces a minimum description length (8 words) for audit consistency.


---



## Adventure Mode: Risk-Tier Model

| Tier | Autonomy | Scope | Approval |
| :--- | :--- | :--- | :--- |
| **LOW** | Full | Typo fixes, minor docs, unit tests | Auto-Approval Gate |
| **MEDIUM** | Guided | Core logic, feature extensions | Human Review Required |
| **HIGH** | Strategic | Architecture, infra, brain-memory | Operator Only |


## Priority 7: Swarm Mode Built Into Every Template


### Goal
Every repo bootstrapped from this template immediately supports swarm operations.


### Template integration plan
1. Include `09_AUTOMATED_AGENT_SWARM.md` by default.
2. Include `scripts/conductor.sh` skeleton by default.
3. Add `.github/pull_request_template.md` swarm reminder.
4. Add bootstrap flag: `--enable-swarm` for optional setup helpers.


### Definition of ready
1. New repo can run one low-risk swarm slice in under 10 minutes.
2. `MERGE_LOG` and `DYNAMIC_MEMORY` receive append-only updates automatically.
3. Human gate is enforced for non-trivial changes.


### Next Step
Ship Priority 1 + Priority 2 first; defer dashboard and MCP enhancements until baseline workflow is stable.


## Priority 9: Testing & Validation Suite (OPERATIONAL)


### Goal
Establish a deterministic validation layer for the G-Codex system to ensure core scripts (bootstrap, conductor, dashboard) remain operational and "safe."


### Usage

```bash
./scripts/test-suite.sh

```


### Tests Performed
1. **Bootstrap Validation**: Ensures a target repo is correctly equipped with all `G-Codex-brain/` files and localized `AGENTS.md`.
2. **Brain Server Connectivity**: Confirms `scripts/brain_server.py` starts correctly and delivers the necessary JSON context.
3. **Auto-Approval Gate**: Validates the **Triad of Truth** logic by performing a safe mock commit and checking memory logs.
4. **Hand-off Integrity**: Verifies that the server payload contains all the metadata required for rich cross-model hand-offs.


---



## Current Capabilities Summary (v1.0 Ready)

| Feature | Status | Value |
| :--- | :--- | :--- |
| **Bootstrap Brain** | `OPERATIONAL` | One-script integration for any repository. |
| **Control Room** | `OPERATIONAL` | Premium, local dashboard for agent orchestration. |
| **Auto-Approval Gate** | `OPERATIONAL` | Safe, one-button commits for surgical slices. |
| **Hand-off Links** | `OPERATIONAL` | Deep-context LLM onboarding in one click. |
| **Shared Brain Server** | `OPERATIONAL` | Local context provider for cross-model sync. |
| **Validation Suite** | `OPERATIONAL` | Deterministic local tests for system health. |

*G-Codex: The engineering system that never forgets.*

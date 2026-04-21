#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<USAGE
Usage: $(basename "$0") <target-repo-path> [--repo-name <name>] [--repo-desc <desc>] [--status-hint <text>] [--next-slice-hint <text>] [--yes]

Bootstraps G-Codex into an existing repository by copying:
- AGENTS.md
- G-Codex-brain/
- scripts/ (including ingress, dashboard, conductor, watcher, bridge userscript)
- examples/ (reference case studies)

Options:
  --repo-name <name>   Explicit repository name for localization metadata.
  --repo-desc <desc>   Short repository description for localization metadata.
  --status-hint <text> Optional current-status hint for initial 03_ACTIVE_NOW generation.
  --next-slice-hint <text> Optional next-slice hint for initial 03_ACTIVE_NOW generation.
  --yes                Non-interactive mode (uses defaults when values are omitted).
USAGE
}

SCRIPT_PATH="${BASH_SOURCE[0]}"
SCRIPT_DIR="$(cd -- "$(dirname -- "${SCRIPT_PATH}")" >/dev/null 2>&1 && pwd -P)"
SOURCE_ROOT="$(cd -- "${SCRIPT_DIR}/.." >/dev/null 2>&1 && pwd -P)"

if [[ -z "${SCRIPT_DIR}" || ! -d "${SCRIPT_DIR}" ]]; then
  echo "Error: could not resolve bootstrap script directory." >&2
  exit 1
fi

if [[ ! -f "${SOURCE_ROOT}/AGENTS.md" || ! -d "${SOURCE_ROOT}/G-Codex-brain" || ! -d "${SOURCE_ROOT}/scripts" ]]; then
  echo "Error: template source root is incomplete: ${SOURCE_ROOT}" >&2
  echo "Expected AGENTS.md, G-Codex-brain/, and scripts/ in the template root." >&2
  exit 1
fi

TARGET_REPO=""
REPO_NAME=""
REPO_DESC=""
STATUS_HINT=""
NEXT_SLICE_HINT=""
ASSUME_YES="0"

if [[ $# -lt 1 ]]; then
  usage
  exit 1
fi

while [[ $# -gt 0 ]]; do
  case "$1" in
    --repo-name)
      [[ $# -ge 2 ]] || { echo "Missing value for --repo-name" >&2; exit 1; }
      REPO_NAME="$2"
      shift 2
      ;;
    --repo-desc)
      [[ $# -ge 2 ]] || { echo "Missing value for --repo-desc" >&2; exit 1; }
      REPO_DESC="$2"
      shift 2
      ;;
    --status-hint)
      [[ $# -ge 2 ]] || { echo "Missing value for --status-hint" >&2; exit 1; }
      STATUS_HINT="$2"
      shift 2
      ;;
    --next-slice-hint)
      [[ $# -ge 2 ]] || { echo "Missing value for --next-slice-hint" >&2; exit 1; }
      NEXT_SLICE_HINT="$2"
      shift 2
      ;;
    --yes)
      ASSUME_YES="1"
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      if [[ -z "${TARGET_REPO}" ]]; then
        TARGET_REPO="$1"
        shift
      else
        echo "Unknown argument: $1" >&2
        usage
        exit 1
      fi
      ;;
  esac
done

if [[ -z "${TARGET_REPO}" ]]; then
  echo "Error: target repo path is required." >&2
  usage
  exit 1
fi

if [[ ! -d "${TARGET_REPO}" ]]; then
  echo "Error: target repo path does not exist: ${TARGET_REPO}" >&2
  exit 1
fi

if ! cd "${TARGET_REPO}" >/dev/null 2>&1; then
  echo "Error: target repo path is not accessible: ${TARGET_REPO}" >&2
  exit 1
fi
TARGET_REPO="$(pwd -P)"
DEFAULT_REPO_NAME="$(basename "${TARGET_REPO}")"

if [[ -z "${REPO_NAME}" ]]; then
  if [[ "${ASSUME_YES}" == "1" ]]; then
    REPO_NAME="${DEFAULT_REPO_NAME}"
  else
    read -r -p "Repository name [${DEFAULT_REPO_NAME}]: " INPUT_REPO_NAME
    REPO_NAME="${INPUT_REPO_NAME:-${DEFAULT_REPO_NAME}}"
  fi
fi

if [[ -z "${REPO_DESC}" ]]; then
  if [[ "${ASSUME_YES}" == "1" ]]; then
    REPO_DESC="Repository bootstrapped with G-Codex context overlay."
  else
    read -r -p "Short repository description: " INPUT_REPO_DESC
    REPO_DESC="${INPUT_REPO_DESC:-Repository bootstrapped with G-Codex context overlay.}"
  fi
fi

mkdir -p "${TARGET_REPO}/G-Codex-brain"
mkdir -p "${TARGET_REPO}/scripts"

cp -f "${SOURCE_ROOT}/AGENTS.md" "${TARGET_REPO}/AGENTS.md"
cp -a "${SOURCE_ROOT}/G-Codex-brain/." "${TARGET_REPO}/G-Codex-brain/"
cp -a "${SOURCE_ROOT}/scripts/." "${TARGET_REPO}/scripts/"
if [[ -d "${SOURCE_ROOT}/examples" ]]; then
  mkdir -p "${TARGET_REPO}/examples"
  cp -a "${SOURCE_ROOT}/examples/." "${TARGET_REPO}/examples/"
fi

chmod +x "${TARGET_REPO}/scripts/"*.sh 2>/dev/null || true
chmod +x "${TARGET_REPO}/scripts/"*.py 2>/dev/null || true

apply_context_block() {
  local file_path="$1"
  local tmp_file
  tmp_file="$(mktemp)"

  awk '
    /<!-- BRAIN_BOOTSTRAP_CONTEXT_START -->/ { skip=1; next }
    /<!-- BRAIN_BOOTSTRAP_CONTEXT_END -->/   { skip=0; next }
    !skip { print }
  ' "${file_path}" > "${tmp_file}"

  {
    echo "<!-- BRAIN_BOOTSTRAP_CONTEXT_START -->"
    echo "## Repository Context"
    echo "- Repository Name: ${REPO_NAME}"
    echo "- Repository Description: ${REPO_DESC}"
    echo "- Localized By: scripts/bootstrap-brain.sh"
    echo "<!-- BRAIN_BOOTSTRAP_CONTEXT_END -->"
    echo
    cat "${tmp_file}"
  } > "${file_path}"

  rm -f "${tmp_file}"
}

apply_context_block "${TARGET_REPO}/AGENTS.md"
apply_context_block "${TARGET_REPO}/G-Codex-brain/00_INDEX.md"

write_initial_brain_state() {
  local target_repo="$1"
  local repo_name="$2"
  local repo_desc="$3"
  local reason="${4:-Bootstrap initialization}"
  local status_hint="${5:-}"
  local next_slice_hint="${6:-}"
  local timestamp
  timestamp="$(date -u +"%Y-%m-%dT%H:%M:%SZ")"
  local short_date="${timestamp%%T*}"
  local roadmap_path="${target_repo}/G-Codex-brain/ROADMAP.md"
  local truth_anchor_line="- Truth Anchor: \`G-Codex-brain/ROADMAP.md\` is canonical and present."
  local status_line="- Status: G-Codex surfaces injected; align this file to current repo reality before feature expansion."
  local next_slice_line="4. Dispatch the next low-adventure slice from Control Room."
  local merge_reason="${reason}"
  if [[ ! -f "${roadmap_path}" ]]; then
    truth_anchor_line="- Missing Truth Anchor: \`G-Codex-brain/ROADMAP.md\` not found. Regenerate ingress/roadmap before relying on generated summaries."
    echo "Missing Truth Anchor: ${roadmap_path} not found during bootstrap state generation." >&2
  fi
  if [[ -n "${status_hint}" ]]; then
    status_line="- Status: ${status_hint}"
    merge_reason="${reason} (status hint: ${status_hint//|//})"
  fi
  if [[ -n "${next_slice_hint}" ]]; then
    next_slice_line="4. Dispatch the next low-adventure slice: ${next_slice_hint}"
  fi

  cat > "${target_repo}/G-Codex-brain/03_ACTIVE_NOW.md" <<EOF
# 03 ACTIVE NOW

## Active State: Bootstrap Alignment Pending Localization

- Repository: ${repo_name}
- Description: ${repo_desc}
- Current Phase: Bootstrap Reality Alignment
${status_line}
${truth_anchor_line}

## Immediate Next Steps

1. Launch \`./scripts/conductor.sh dashboard\`.
2. Start bridge watcher with \`./scripts/conductor.sh watch start\`.
3. Localize \`03_ACTIVE_NOW.md\` and review \`G-Codex-brain/ROADMAP.md\` against real repo state.
${next_slice_line}
EOF

  cat > "${target_repo}/G-Codex-brain/MERGE_LOG.md" <<EOF
# MERGE LOG

| Date | Description | Commit | Author |
|---|---|---|---|
| ${short_date} | ${merge_reason} for ${repo_name} | local-bootstrap | scripts/bootstrap-brain.sh |
EOF

  cat > "${target_repo}/G-Codex-brain/DYNAMIC_MEMORY.md" <<EOF
# DYNAMIC MEMORY

## SESSION_LOG_ENTRY
- timestamp: ${timestamp}
- agent: scripts/bootstrap-brain.sh
- repo: ${repo_name}
- branch: main
- objective: Initialize baseline G-Codex memory surfaces for this repository injection.
- actions:
  - Generated baseline \`03_ACTIVE_NOW.md\`, \`MERGE_LOG.md\`, and \`DYNAMIC_MEMORY.md\`.
  - Reset inherited template-local activity history in injected brain surfaces.
- outputs:
  - G-Codex-brain/03_ACTIVE_NOW.md
  - G-Codex-brain/ROADMAP.md
  - G-Codex-brain/MERGE_LOG.md
  - G-Codex-brain/DYNAMIC_MEMORY.md
  - G-Codex-brain/PROPOSAL_OUTCOMES.md
  - G-Codex-brain/AGENT_ROLES.md
- verification:
  - Baseline brain files were regenerated during bootstrap.
- status: DONE
- blockers: none
- next_step: Open Control Room and align active state/roadmap with current repo reality.
EOF

  cat > "${target_repo}/G-Codex-brain/PROPOSAL_OUTCOMES.md" <<EOF
# PROPOSAL OUTCOMES

Accepted Managing Director proposals are logged here for pattern reuse.

| Timestamp | Proposal ID | Managing Director | Feature Slice | Outcome | Reviewer | Notes |
|---|---|---|---|---|---|---|
EOF

  cat > "${target_repo}/G-Codex-brain/AGENT_ROLES.md" <<EOF
# AGENT ROLES

# Preferred CLI co-leads: OAC and GGC.
# MD_BRAIN_ENGINE defaults to GGC for synthesis/supportive guidance; OAC remains execution lead.
# AGa remains troubleshooter/visual auditor (manual use; not default lead).
# Managing Directors: any listed agent can be assigned a sub-lead slice.
# Proposal flow: submit MD_PROPOSAL entries in DYNAMIC_MEMORY.md for Lead review.
LEAD_EXECUTOR: OAC
MD_BRAIN_ENGINE: GGC
AGENTS:
  OAC:
    display: OAC
    description: Surgical code & deterministic execution (preferred CLI co-lead)
  GGC:
    display: GGC
    description: Google Gemini Codex CLI - strong reasoning & execution (preferred CLI co-lead)
  AGa:
    display: AGa
    description: Troubleshooter & Visual Auditor (manual use only; not default lead)
  Gemini 3:
    display: Gemini 3
    description: Deep reasoning & architecture
  Grok:
    display: Grok
    description: Alignment, truth-seeking & anti-drift
  ChatGPT:
    display: ChatGPT
    description: Polish, UX clarity & creative refinement
EOF
}

write_initial_brain_state "${TARGET_REPO}" "${REPO_NAME}" "${REPO_DESC}" "Bootstrap baseline initialization" "${STATUS_HINT}" "${NEXT_SLICE_HINT}"

README_PATH="${TARGET_REPO}/README.md"
BOOTSTRAP_MARKER_START="<!-- GCODEX_BOOTSTRAP_START -->"
BOOTSTRAP_MARKER_END="<!-- GCODEX_BOOTSTRAP_END -->"

if [[ ! -f "${README_PATH}" ]]; then
  cat > "${README_PATH}" <<README_NEW
# ${REPO_NAME}

${REPO_DESC}

README_NEW
fi

tmp_readme="$(mktemp)"
awk -v start="${BOOTSTRAP_MARKER_START}" -v end="${BOOTSTRAP_MARKER_END}" '
  $0 == start { skip=1; next }
  $0 == end   { skip=0; next }
  !skip { print }
' "${README_PATH}" > "${tmp_readme}"

cat >> "${tmp_readme}" <<README_BLOCK

${BOOTSTRAP_MARKER_START}
## G-Codex Bootstrap

This repository has been bootstrapped with the full G-Codex template stack.

- Primary entry point: \`./scripts/conductor.sh dashboard\`
- Ingress helper (for future clone/bootstrap workflows): \`./scripts/ingress.sh\`
- Clipboard bridge watcher: \`./scripts/conductor.sh watch\`
- Shared brain directory: \`G-Codex-brain/\`
- Guiding manifesto: \`G-Codex-brain/ENLIGHTENMENT_MANIFESTO.md\`
- Browser bridge userscript: \`scripts/bridge.user.js\`
- Pure repo exit: \`./scripts/remove-gcodex.sh\`
- For the clipboard bridge: \`sudo apt install xclip\` (Linux Mint / Ubuntu)

### Local Python Environment

If \`.venv/\` exists, activate it before running extended Python tooling:

\`\`\`bash
source .venv/bin/activate
\`\`\`

### First Run

\`\`\`bash
./scripts/conductor.sh dashboard
\`\`\`

This launches the G-Codex Control Room and starts the local brain server.
${BOOTSTRAP_MARKER_END}
README_BLOCK

mv "${tmp_readme}" "${README_PATH}"

if command -v python3 >/dev/null 2>&1; then
  if [[ ! -d "${TARGET_REPO}/.venv" ]]; then
    if python3 -m venv "${TARGET_REPO}/.venv"; then
      echo "Created local Python virtual environment: ${TARGET_REPO}/.venv"
    else
      echo "Warning: failed to create ${TARGET_REPO}/.venv (python3 -m venv)." >&2
    fi
  else
    echo "Python virtual environment already exists: ${TARGET_REPO}/.venv"
  fi
else
  echo "Warning: python3 not found; skipped .venv setup." >&2
fi

required_files=(
  "AGENTS.md"
  "README.md"
  "G-Codex-brain/00_BOOTSTRAP_GUIDE.md"
  "G-Codex-brain/00_INDEX.md"
  "G-Codex-brain/03_ACTIVE_NOW.md"
  "G-Codex-brain/06_INTELLIGENT_DEV_METHOD.md"
  "G-Codex-brain/09_AUTOMATED_AGENT_SWARM.md"
  "G-Codex-brain/ROADMAP.md"
  "G-Codex-brain/ENLIGHTENMENT_MANIFESTO.md"
  "G-Codex-brain/AGENT_RULES.md"
  "G-Codex-brain/AGENT_ROLES.md"
  "G-Codex-brain/PROPOSAL_OUTCOMES.md"
  "G-Codex-brain/user_domain_nodes.json"
  "G-Codex-brain/MERGE_LOG.md"
  "scripts/bootstrap-brain.sh"
  "scripts/ingress.sh"
  "scripts/conductor.sh"
  "scripts/brain_server.py"
  "scripts/named_agent_dashboard.html"
  "scripts/watcher.py"
  "scripts/bridge.user.js"
  "scripts/remove-gcodex.sh"
  "examples/openclaw-enlightenment.md"
)

missing_count=0
for relative_path in "${required_files[@]}"; do
  if [[ ! -f "${TARGET_REPO}/${relative_path}" ]]; then
    echo "Missing required file: ${relative_path}" >&2
    missing_count=$((missing_count + 1))
  fi
done

if [[ ${missing_count} -ne 0 ]]; then
  echo "Anti-drift check: FAIL (${missing_count} missing file(s))." >&2
  exit 1
fi

echo "Anti-drift check: PASS"
echo "✨ Bootstrap complete for: ${TARGET_REPO}"
echo
echo "----------------------------------------------------------------"
echo "🚀 G-CODEX TEMPLATE BOOTSTRAP SUCCESSFUL"
echo "----------------------------------------------------------------"
echo "Repository Name: ${REPO_NAME}"
echo "Description:     ${REPO_DESC}"
echo
echo "Recommended entry point:"
echo "  ./scripts/conductor.sh dashboard"
echo
echo "Optional bridge watcher:"
echo "  ./scripts/conductor.sh watch"
echo
echo "Next commands:"
echo "  cd \"${TARGET_REPO}\""
echo
echo "Next steps:"
echo "  1) ./scripts/conductor.sh dashboard"
echo "  2) ./scripts/conductor.sh watch start   (for the bridge)"
echo "----------------------------------------------------------------"

#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ASSUME_YES="0"
BRAIN_SERVER_PORT="8765"
WATCHER_PID_FILE="${ROOT_DIR}/.watcher.pid"
AMBIENT_INGRESS_PID_FILE="${ROOT_DIR}/.ambient_ingress.pid"

info() {
  echo "[purity] $*"
}

usage() {
  cat <<USAGE
Usage: $(basename "$0") [--yes]

Safely removes G-Codex integration from this repository using shutdown-first purity discipline:
- Identifies active runtime/watcher processes
- Stops runtime writers before purge
- Removes G-Codex-brain/
- Removes managed scripts from scripts/
- Removes injected G-Codex README block markers
- Preserves non-G-Codex files where possible
USAGE
}

append_pid_if_numeric() {
  local candidate="${1:-}"
  if [[ "${candidate}" =~ ^[0-9]+$ ]]; then
    echo "${candidate}"
  fi
}

append_live_pid_from_file() {
  local pid_file="${1:-}"
  if [[ -z "${pid_file}" || ! -f "${pid_file}" ]]; then
    return 0
  fi
  local pid
  pid="$(append_pid_if_numeric "$(cat "${pid_file}" 2>/dev/null || true)")"
  if [[ -n "${pid}" ]] && pid_alive "${pid}"; then
    echo "${pid}"
    return 0
  fi
  # Stale pid files are non-blocking; purge still removes the file later.
  rm -f "${pid_file}"
  return 0
}

list_brain_server_pids() {
  local pids=""
  if command -v lsof > /dev/null 2>&1; then
    pids="$(lsof -ti "tcp:${BRAIN_SERVER_PORT}" -sTCP:LISTEN 2>/dev/null || true)"
  elif command -v fuser > /dev/null 2>&1; then
    pids="$(fuser -n tcp "${BRAIN_SERVER_PORT}" 2>/dev/null || true)"
  fi
  echo "${pids}" | tr ' ' '\n' | awk -v port="${BRAIN_SERVER_PORT}" '/^[0-9]+$/ && $1 != port {print $1}' | sort -u
}

list_runtime_writer_pids() {
  local all_pids=""
  local brain_port_pids=""
  brain_port_pids="$(list_brain_server_pids || true)"
  if [[ -n "${brain_port_pids}" ]]; then
    all_pids+=$'\n'"${brain_port_pids}"
  fi

  if command -v pgrep > /dev/null 2>&1; then
    local patterns=(
      "${ROOT_DIR}/scripts/brain_server.py"
      "${ROOT_DIR}/scripts/watcher.py"
      "${ROOT_DIR}/scripts/ingress.sh --watch-folder"
    )
    local pattern
    local matches
    for pattern in "${patterns[@]}"; do
      matches="$(pgrep -f "${pattern}" 2>/dev/null || true)"
      if [[ -n "${matches}" ]]; then
        all_pids+=$'\n'"${matches}"
      fi
    done
  fi

  all_pids+=$'\n'"$(append_live_pid_from_file "${WATCHER_PID_FILE}")"
  all_pids+=$'\n'"$(append_live_pid_from_file "${AMBIENT_INGRESS_PID_FILE}")"

  echo "${all_pids}" | awk '/^[0-9]+$/{print $1}' | sort -u
}

pid_alive() {
  local pid="${1:-0}"
  [[ "${pid}" =~ ^[0-9]+$ ]] || return 1
  kill -0 "${pid}" 2>/dev/null
}

stop_pid_group() {
  local label="${1:-runtime}"
  shift || true
  local requested=("$@")
  local pids=()
  local pid
  for pid in "${requested[@]}"; do
    if [[ "${pid}" =~ ^[0-9]+$ ]] && pid_alive "${pid}"; then
      pids+=("${pid}")
    fi
  done

  if (( ${#pids[@]} == 0 )); then
    info "No active ${label} process detected."
    return 0
  fi

  info "Stopping ${label} PID(s): ${pids[*]}"
  kill "${pids[@]}" 2>/dev/null || true

  local survivors=("${pids[@]}")
  local still=()
  local _i
  for _i in {1..20}; do
    still=()
    for pid in "${survivors[@]}"; do
      if pid_alive "${pid}"; then
        still+=("${pid}")
      fi
    done
    if (( ${#still[@]} == 0 )); then
      info "${label} stopped cleanly."
      return 0
    fi
    survivors=("${still[@]}")
    sleep 0.2
  done

  info "${label} did not exit in time; forcing PID(s): ${survivors[*]}"
  kill -9 "${survivors[@]}" 2>/dev/null || true
  sleep 0.2

  still=()
  for pid in "${survivors[@]}"; do
    if pid_alive "${pid}"; then
      still+=("${pid}")
    fi
  done
  if (( ${#still[@]} > 0 )); then
    echo "[purity] Failed to stop ${label} PID(s): ${still[*]}" >&2
    return 1
  fi

  info "${label} force-stopped."
  return 0
}

stop_pid_file_process() {
  local label="${1:-runtime}"
  local pid_file="${2:-}"
  if [[ -z "${pid_file}" || ! -f "${pid_file}" ]]; then
    return 0
  fi
  local pid
  pid="$(cat "${pid_file}" 2>/dev/null || true)"
  if [[ "${pid}" =~ ^[0-9]+$ ]]; then
    stop_pid_group "${label}" "${pid}" || return 1
  fi
  return 0
}

verify_no_runtime_writers() {
  local remaining=()
  mapfile -t remaining < <(list_runtime_writer_pids)
  if (( ${#remaining[@]} > 0 )); then
    echo "[purity] Runtime writer process(es) still active: ${remaining[*]}" >&2
    return 1
  fi
  info "Verified no active G-Codex runtime writers remain."
}

enforce_shutdown_first() {
  info "Purity protocol: identifying active runtime processes..."
  local initial=()
  mapfile -t initial < <(list_runtime_writer_pids)
  if (( ${#initial[@]} > 0 )); then
    info "Detected active runtime PID(s): ${initial[*]}"
  else
    info "No active runtime PID detected."
  fi

  info "Step 1/4: stop brain_server.py"
  local brain_pids=()
  mapfile -t brain_pids < <(
    {
      list_brain_server_pids || true
      if command -v pgrep > /dev/null 2>&1; then
        pgrep -f "${ROOT_DIR}/scripts/brain_server.py" 2>/dev/null || true
      fi
    } | awk '/^[0-9]+$/{print $1}' | sort -u
  )
  stop_pid_group "brain_server.py" "${brain_pids[@]}"

  info "Step 2/4: stop watcher/background bridge processes"
  stop_pid_file_process "watcher (pid file)" "${WATCHER_PID_FILE}"
  local watcher_pids=()
  mapfile -t watcher_pids < <(
    if command -v pgrep > /dev/null 2>&1; then
      pgrep -f "${ROOT_DIR}/scripts/watcher.py" 2>/dev/null || true
    fi
  )
  stop_pid_group "watcher.py" "${watcher_pids[@]}"

  stop_pid_file_process "ambient ingress (pid file)" "${AMBIENT_INGRESS_PID_FILE}"
  local ambient_pids=()
  mapfile -t ambient_pids < <(
    if command -v pgrep > /dev/null 2>&1; then
      pgrep -f "${ROOT_DIR}/scripts/ingress.sh --watch-folder" 2>/dev/null || true
    fi
  )
  stop_pid_group "ambient watch-folder ingress" "${ambient_pids[@]}"

  info "Step 3/4: stop any remaining repo-writing G-Codex runtime"
  local remaining_pids=()
  mapfile -t remaining_pids < <(list_runtime_writer_pids)
  stop_pid_group "remaining runtime writers" "${remaining_pids[@]}"

  info "Step 4/4: verify shutdown complete before purge"
  verify_no_runtime_writers
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --yes)
      ASSUME_YES="1"
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown argument: $1" >&2
      usage
      exit 1
      ;;
  esac
done

cd "${ROOT_DIR}"
info "Starting shutdown-first pure-repo cleanup in ${ROOT_DIR}"

if [[ "${ASSUME_YES}" != "1" ]]; then
  echo "This will remove G-Codex files from:"
  echo "  ${ROOT_DIR}"
  read -r -p "Continue with pure-repo cleanup? [y/N]: " REPLY
  REPLY="${REPLY:-N}"
  if [[ ! "${REPLY,,}" =~ ^y ]]; then
    echo "Cancelled."
    exit 0
  fi
fi

enforce_shutdown_first

README_PATH="${ROOT_DIR}/README.md"
BOOTSTRAP_MARKER_START="<!-- GCODEX_BOOTSTRAP_START -->"
BOOTSTRAP_MARKER_END="<!-- GCODEX_BOOTSTRAP_END -->"

if [[ -f "${README_PATH}" ]]; then
  tmp_readme="$(mktemp)"
  awk -v start="${BOOTSTRAP_MARKER_START}" -v end="${BOOTSTRAP_MARKER_END}" '
    $0 == start { skip=1; next }
    $0 == end   { skip=0; next }
    !skip { print }
  ' "${README_PATH}" > "${tmp_readme}"
  mv "${tmp_readme}" "${README_PATH}"
fi

if [[ -d "${ROOT_DIR}/G-Codex-brain" ]]; then
  rm -rf "${ROOT_DIR}/G-Codex-brain"
fi

managed_script_paths=(
  "scripts/bootstrap-brain.sh"
  "scripts/ingress.sh"
  "scripts/conductor.sh"
  "scripts/brain_server.py"
  "scripts/named_agent_dashboard.html"
  "scripts/watcher.py"
  "scripts/bridge.user.js"
  "scripts/remove-gcodex.sh"
  "scripts/vendor/README.md"
  "scripts/vendor/mermaid.min.js"
)

for rel in "${managed_script_paths[@]}"; do
  if [[ -e "${ROOT_DIR}/${rel}" ]]; then
    rm -rf "${ROOT_DIR}/${rel}"
  fi
done

state_files=(
  ".brain_server.pid"
  ".watcher.pid"
  ".ambient_ingress.pid"
  ".ambient_ingress.parent"
  ".ambient_ingress.auto_start"
  ".brain_server.log"
  ".watcher.log"
  ".ambient_ingress.log"
  ".notify_enabled"
  ".md_core_state.json"
  ".gcodex_oac_prompt.txt"
  ".gcodex_ggc_helper.txt"
  ".gcodex_ggc_prompt.txt"
  ".swarm_packet.txt"
  ".backups"
)

for rel in "${state_files[@]}"; do
  rm -rf "${ROOT_DIR}/${rel}"
done

if [[ -d "${ROOT_DIR}/scripts/vendor" ]]; then
  rmdir "${ROOT_DIR}/scripts/vendor" 2>/dev/null || true
fi

if [[ -d "${ROOT_DIR}/scripts" ]]; then
  if find "${ROOT_DIR}/scripts" -mindepth 1 -print -quit 2>/dev/null | grep -q .; then
    echo "Preserved user files in scripts/:"
    find "${ROOT_DIR}/scripts" -mindepth 1 -maxdepth 3 -print | sed "s#^${ROOT_DIR}/##"
  else
    rmdir "${ROOT_DIR}/scripts" 2>/dev/null || true
  fi
fi

verify_no_runtime_writers

post_purge_expected_absent=(
  "G-Codex-brain"
  "scripts/bootstrap-brain.sh"
  "scripts/ingress.sh"
  "scripts/conductor.sh"
  "scripts/brain_server.py"
  "scripts/named_agent_dashboard.html"
  "scripts/watcher.py"
  "scripts/bridge.user.js"
)

still_present=()
for rel in "${post_purge_expected_absent[@]}"; do
  if [[ -e "${ROOT_DIR}/${rel}" ]]; then
    still_present+=("${rel}")
  fi
done

if (( ${#still_present[@]} > 0 )); then
  echo "[purity] Purity verification failed; expected removed surfaces still present:" >&2
  printf '%s\n' "${still_present[@]}" >&2
  exit 1
fi

info "Purity verification passed: template-owned runtime surfaces removed, project-owned files preserved."
echo "Pure repo cleanup complete."

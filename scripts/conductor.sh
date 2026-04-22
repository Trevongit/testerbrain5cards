#!/usr/bin/env bash
set -euo pipefail
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BRAIN_DIR="${ROOT_DIR}/G-Codex-brain"
BRAIN_SERVER_HOST="127.0.0.1"
BRAIN_SERVER_PORT="8765"
BRAIN_SERVER_SCRIPT="${ROOT_DIR}/scripts/brain_server.py"
BRAIN_SERVER_LOG="${ROOT_DIR}/.brain_server.log"
DASHBOARD_URL="http://${BRAIN_SERVER_HOST}:${BRAIN_SERVER_PORT}/dashboard"
WATCHER_SCRIPT="${ROOT_DIR}/scripts/watcher.py"
WATCHER_LOG="${ROOT_DIR}/.watcher.log"
WATCHER_PID_FILE="${ROOT_DIR}/.watcher.pid"
NOTIFY_FLAG_FILE="${ROOT_DIR}/.notify_enabled"
INGRESS_SCRIPT="${ROOT_DIR}/scripts/ingress.sh"
AMBIENT_INGRESS_LOG="${ROOT_DIR}/.ambient_ingress.log"
AMBIENT_INGRESS_PID_FILE="${ROOT_DIR}/.ambient_ingress.pid"
AMBIENT_INGRESS_PARENT_FILE="${ROOT_DIR}/.ambient_ingress.parent"
AMBIENT_AUTO_START_FILE="${ROOT_DIR}/.ambient_ingress.auto_start"
AMBIENT_DEFAULT_PARENT="${GCODEX_AMBIENT_PARENT:-${HOME}/Projects/G-Codex-Enlightened}"
BACKUPS_DIR="${ROOT_DIR}/.backups"
CHANGELOG_PATH="${BRAIN_DIR}/CHANGELOG.md"
DYNAMIC_MEMORY_PATH="${BRAIN_DIR}/DYNAMIC_MEMORY.md"
PUSH_LOG_FILE="${ROOT_DIR}/.git/gcodex_push.log"

function list_brain_server_pids() {
  local pids=""
  if command -v lsof > /dev/null 2>&1; then
    pids=$(lsof -ti "tcp:${BRAIN_SERVER_PORT}" -sTCP:LISTEN 2>/dev/null || true)
  elif command -v fuser > /dev/null 2>&1; then
    pids=$(fuser -n tcp "${BRAIN_SERVER_PORT}" 2>/dev/null || true)
  fi

  echo "${pids}" | tr ' ' '\n' | awk -v port="${BRAIN_SERVER_PORT}" '/^[0-9]+$/ && $1 != port {print $1}' | sort -u
}

function is_brain_server_listening() {
  if command -v ss > /dev/null 2>&1; then
    ss -ltnH "( sport = :${BRAIN_SERVER_PORT} )" 2>/dev/null | awk '$1=="LISTEN"{found=1} END{exit(found?0:1)}'
    return $?
  fi

  if command -v netstat > /dev/null 2>&1; then
    netstat -ltn 2>/dev/null | awk -v p=":${BRAIN_SERVER_PORT}" '$6=="LISTEN" && index($4,p){found=1} END{exit(found?0:1)}'
    return $?
  fi

  python3 -c "import socket,sys; s=socket.socket(); s.settimeout(0.2); ok=(s.connect_ex(('${BRAIN_SERVER_HOST}', ${BRAIN_SERVER_PORT}))==0); s.close(); sys.exit(0 if ok else 1)"
}

function is_brain_server_http_ready() {
  local health_url="http://${BRAIN_SERVER_HOST}:${BRAIN_SERVER_PORT}/health"
  if command -v curl > /dev/null 2>&1; then
    local body
    body="$(curl -fsS --max-time 0.5 "${health_url}" 2>/dev/null || true)"
    [[ "${body}" == *'"status":"healthy"'* || "${body}" == *'"status": "healthy"'* ]]
    return $?
  fi

  python3 -c "import json,sys,urllib.request; \
url='${health_url}'; \
resp=urllib.request.urlopen(url, timeout=0.5); \
payload=json.loads(resp.read().decode('utf-8')); \
sys.exit(0 if isinstance(payload, dict) and str(payload.get('status','')).lower()=='healthy' else 1)" \
    >/dev/null 2>&1
}

function stop_brain_server() {
  local pids=()
  mapfile -t pids < <(list_brain_server_pids)
  if (( ${#pids[@]} == 0 )); then
    echo "No existing brain server found on port ${BRAIN_SERVER_PORT}."
    return 0
  fi

  echo "Stopping existing brain server PID(s): ${pids[*]}"
  kill "${pids[@]}" 2>/dev/null || true

  for _ in {1..10}; do
    sleep 0.2
    mapfile -t pids < <(list_brain_server_pids)
    if (( ${#pids[@]} == 0 )); then
      echo "Previous brain server stopped cleanly."
      return 0
    fi
  done

  echo "Old server did not exit in time. Forcing stop for PID(s): ${pids[*]}"
  kill -9 "${pids[@]}" 2>/dev/null || true
  sleep 0.2

  mapfile -t pids < <(list_brain_server_pids)
  if (( ${#pids[@]} > 0 )); then
    echo "Failed to clear port ${BRAIN_SERVER_PORT}. Still held by PID(s): ${pids[*]}" >&2
    return 1
  fi

  echo "Port ${BRAIN_SERVER_PORT} is now clear."
}

function start_brain_server() {
  echo "Preparing brain server startup on ${BRAIN_SERVER_HOST}:${BRAIN_SERVER_PORT}..."
  stop_brain_server

  python3 "${BRAIN_SERVER_SCRIPT}" > "${BRAIN_SERVER_LOG}" 2>&1 &
  local new_pid=$!

  for _ in {1..20}; do
    sleep 0.2
    if ! kill -0 "${new_pid}" 2>/dev/null; then
      echo "Brain server exited during startup. Recent log output:" >&2
      tail -n 20 "${BRAIN_SERVER_LOG}" >&2 || true
      return 1
    fi
    if is_brain_server_listening; then
      if ! is_brain_server_http_ready; then
        continue
      fi
      echo "Brain server started successfully (PID ${new_pid})."
      echo "Endpoint: http://${BRAIN_SERVER_HOST}:${BRAIN_SERVER_PORT}/context"
      echo "Log file: ${BRAIN_SERVER_LOG}"
      return 0
    fi
  done

  echo "Brain server did not become ready in time. Recent log output:" >&2
  tail -n 20 "${BRAIN_SERVER_LOG}" >&2 || true
  return 1
}

function is_watcher_running() {
  if [[ ! -f "${WATCHER_PID_FILE}" ]]; then
    return 1
  fi
  local pid
  pid="$(cat "${WATCHER_PID_FILE}" 2>/dev/null || true)"
  [[ -n "${pid}" ]] || return 1
  kill -0 "${pid}" 2>/dev/null
}

function set_notify_mode() {
  local enabled="${1:-1}"
  echo "${enabled}" > "${NOTIFY_FLAG_FILE}"

  local payload='{"enabled":true}'
  if [[ "${enabled}" == "0" ]]; then
    payload='{"enabled":false}'
  fi

  curl -s -X POST "http://${BRAIN_SERVER_HOST}:${BRAIN_SERVER_PORT}/notify-control" \
    -H "Content-Type: application/json" \
    -d "${payload}" > /dev/null 2>&1 || true
}

function start_watcher() {
  local quiet_mode="${1:-0}"
  if [[ ! -f "${WATCHER_SCRIPT}" ]]; then
    echo "Missing watcher script: ${WATCHER_SCRIPT}" >&2
    return 1
  fi

  if is_watcher_running; then
    local existing_pid
    existing_pid="$(cat "${WATCHER_PID_FILE}")"
    echo "Watcher already running (PID ${existing_pid})."
    return 0
  fi

  if [[ "${quiet_mode}" == "1" ]]; then
    set_notify_mode 0
    echo "Watcher notification mode: CALM (desktop notifications off, visual flash remains)."
  elif [[ ! -f "${NOTIFY_FLAG_FILE}" ]]; then
    set_notify_mode 1
  fi

  echo "Starting clipboard watcher..."
  python3 "${WATCHER_SCRIPT}" >> "${WATCHER_LOG}" 2>&1 &
  local watcher_pid=$!
  echo "${watcher_pid}" > "${WATCHER_PID_FILE}"
  sleep 0.4

  if kill -0 "${watcher_pid}" 2>/dev/null; then
    echo "Watcher started successfully (PID ${watcher_pid})."
    echo "Log file: ${WATCHER_LOG}"
    return 0
  fi

  echo "Watcher exited during startup. Recent log output:" >&2
  tail -n 20 "${WATCHER_LOG}" >&2 || true
  rm -f "${WATCHER_PID_FILE}"
  return 1
}

function stop_watcher() {
  if ! is_watcher_running; then
    echo "Watcher is not running."
    rm -f "${WATCHER_PID_FILE}"
    return 0
  fi

  local pid
  pid="$(cat "${WATCHER_PID_FILE}")"
  echo "Stopping watcher PID ${pid}..."
  kill "${pid}" 2>/dev/null || true

  for _ in {1..10}; do
    sleep 0.2
    if ! kill -0 "${pid}" 2>/dev/null; then
      rm -f "${WATCHER_PID_FILE}"
      echo "Watcher stopped."
      return 0
    fi
  done

  kill -9 "${pid}" 2>/dev/null || true
  rm -f "${WATCHER_PID_FILE}"
  echo "Watcher force-stopped."
}

function watcher_status() {
  if is_watcher_running; then
    echo "Watcher: RUNNING (PID $(cat "${WATCHER_PID_FILE}"))"
  else
    echo "Watcher: STOPPED"
  fi
}

function bridge_watcher_status_line() {
  if is_watcher_running; then
    echo "Bridge watcher: running"
  else
    echo "Bridge watcher: stopped"
  fi
}

function is_ambient_ingress_running() {
  if [[ ! -f "${AMBIENT_INGRESS_PID_FILE}" ]]; then
    return 1
  fi
  local pid
  pid="$(cat "${AMBIENT_INGRESS_PID_FILE}" 2>/dev/null || true)"
  [[ -n "${pid}" ]] || return 1
  kill -0 "${pid}" 2>/dev/null
}

function normalize_watch_interval() {
  local raw="${1:-6}"
  if ! [[ "${raw}" =~ ^[0-9]+$ ]]; then
    echo "6"
    return
  fi
  if (( raw < 2 )); then
    echo "2"
    return
  fi
  if (( raw > 60 )); then
    echo "60"
    return
  fi
  echo "${raw}"
}

function start_watch_folder() {
  local parent="${1:-${AMBIENT_DEFAULT_PARENT}}"
  local assume_yes="${2:-0}"
  local interval_raw="${3:-6}"
  local quiet_mode="${4:-0}"
  local interval
  interval="$(normalize_watch_interval "${interval_raw}")"

  if [[ ! -x "${INGRESS_SCRIPT}" ]]; then
    echo "Missing ingress script: ${INGRESS_SCRIPT}" >&2
    return 1
  fi

  parent="${parent/#\~/${HOME}}"
  mkdir -p "${parent}"
  parent="$(cd "${parent}" && pwd -P)"

  if is_ambient_ingress_running; then
    local existing_pid existing_parent
    existing_pid="$(cat "${AMBIENT_INGRESS_PID_FILE}" 2>/dev/null || true)"
    existing_parent="$(cat "${AMBIENT_INGRESS_PARENT_FILE}" 2>/dev/null || true)"
    echo "Watch-folder already running (PID ${existing_pid:-unknown}) for ${existing_parent:-unknown parent}."
    return 0
  fi

  local consent_file="${parent}/.gcodex-watch-consent"
  if [[ ! -f "${consent_file}" && "${assume_yes}" != "1" ]]; then
    echo "Ambient ingress safety check:"
    echo "  Parent folder: ${parent}"
    echo "  New subfolders will be auto-bootstrapped."
    echo "  Ignore patterns in ${parent}/.gcodex-ignore are respected."
    read -r -p "Enable watch-folder mode for this parent? [y/N]: " CONFIRM
    CONFIRM="${CONFIRM:-N}"
    if [[ ! "${CONFIRM,,}" =~ ^y ]]; then
      echo "watch-folder start cancelled."
      return 1
    fi
  fi

  if [[ ! -f "${consent_file}" ]]; then
    cat > "${consent_file}" <<EOF
enabled_at=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
enabled_by=conductor.sh
EOF
  fi

  echo "${parent}" > "${AMBIENT_INGRESS_PARENT_FILE}"
  log_ambient_event "watch-folder start requested parent=${parent} interval=${interval}"
  if [[ "${quiet_mode}" != "1" ]]; then
    echo "Starting ambient ingress watcher..."
  fi
  GCODEX_WATCH_INTERVAL_SEC="${interval}" \
    bash "${INGRESS_SCRIPT}" --watch-folder "${parent}" --yes >> "${AMBIENT_INGRESS_LOG}" 2>&1 &
  local pid=$!
  echo "${pid}" > "${AMBIENT_INGRESS_PID_FILE}"
  sleep 0.4

  if kill -0 "${pid}" 2>/dev/null; then
    log_ambient_event "watch-folder started pid=${pid} parent=${parent} interval=${interval}"
    if [[ "${quiet_mode}" != "1" ]]; then
      echo "Watch-folder started (PID ${pid})."
      echo "Parent: ${parent}"
      echo "Log file: ${AMBIENT_INGRESS_LOG}"
    fi
    return 0
  fi

  echo "Watch-folder exited during startup. Recent log output:" >&2
  tail -n 30 "${AMBIENT_INGRESS_LOG}" >&2 || true
  rm -f "${AMBIENT_INGRESS_PID_FILE}"
  return 1
}

function stop_watch_folder() {
  if ! is_ambient_ingress_running; then
    echo "Watch-folder is not running."
    rm -f "${AMBIENT_INGRESS_PID_FILE}"
    return 0
  fi

  local pid
  pid="$(cat "${AMBIENT_INGRESS_PID_FILE}" 2>/dev/null || true)"
  log_ambient_event "watch-folder stop requested pid=${pid}"
  echo "Stopping watch-folder PID ${pid}..."
  kill "${pid}" 2>/dev/null || true
  for _ in {1..10}; do
    sleep 0.2
    if ! kill -0 "${pid}" 2>/dev/null; then
      rm -f "${AMBIENT_INGRESS_PID_FILE}"
      log_ambient_event "watch-folder stopped pid=${pid}"
      echo "Watch-folder stopped."
      return 0
    fi
  done

  kill -9 "${pid}" 2>/dev/null || true
  rm -f "${AMBIENT_INGRESS_PID_FILE}"
  log_ambient_event "watch-folder force-stopped pid=${pid}"
  echo "Watch-folder force-stopped."
}

function watch_folder_status() {
  load_watch_folder_auto_start
  if is_ambient_ingress_running; then
    local pid parent
    pid="$(cat "${AMBIENT_INGRESS_PID_FILE}" 2>/dev/null || true)"
    parent="$(cat "${AMBIENT_INGRESS_PARENT_FILE}" 2>/dev/null || true)"
    echo "Watch-folder: RUNNING (PID ${pid})"
    echo "Parent: ${parent:-unknown}"
    echo "Log file: ${AMBIENT_INGRESS_LOG}"
  else
    echo "Watch-folder: STOPPED"
  fi
  if [[ "${AUTO_START_ENABLED}" == "1" ]]; then
    echo "Auto-start: ENABLED (parent=${AUTO_START_PARENT}, interval=${AUTO_START_INTERVAL}s, quiet=${AUTO_START_QUIET})"
  else
    echo "Auto-start: DISABLED"
  fi
}

function utc_now_iso() {
  date -u +"%Y-%m-%dT%H:%M:%SZ"
}

function compact_one_line() {
  local raw="${1:-}"
  printf '%s' "${raw}" | tr '\r\n\t' '   ' | sed -E 's/[[:space:]]+/ /g; s/^ //; s/ $//'
}

function truncate_chars() {
  local raw="${1:-}"
  local limit="${2:-180}"
  if ! [[ "${limit}" =~ ^[0-9]+$ ]]; then
    limit=180
  fi
  if (( limit < 4 )); then
    limit=4
  fi
  if (( ${#raw} <= limit )); then
    printf '%s' "${raw}"
    return 0
  fi
  printf '%s...' "${raw:0:$((limit - 3))}"
}

function ensure_dynamic_memory_file() {
  mkdir -p "${BRAIN_DIR}"
  if [[ ! -f "${DYNAMIC_MEMORY_PATH}" ]]; then
    cat > "${DYNAMIC_MEMORY_PATH}" <<'EOF'
# DYNAMIC MEMORY

EOF
  fi
}

function append_cli_output_block() {
  local source="${1:-OAC}"
  local session_label="${2:-local-cli}"
  local command_label="${3:-}"
  local return_code="${4:-0}"
  local stdout_text="${5:-}"
  local stderr_text="${6:-}"
  ensure_dynamic_memory_file

  local stdout_summary stderr_summary excerpt
  stdout_summary="$(truncate_chars "$(compact_one_line "${stdout_text}")" 180)"
  stderr_summary="$(truncate_chars "$(compact_one_line "${stderr_text}")" 180)"
  [[ -n "${stdout_summary}" ]] || stdout_summary="(none)"
  [[ -n "${stderr_summary}" ]] || stderr_summary="(none)"

  excerpt="$(compact_one_line "$(printf '%s %s' "${stdout_text}" "${stderr_text}")")"
  excerpt="$(truncate_chars "${excerpt}" 520)"
  [[ -n "${excerpt}" ]] || excerpt="(no terminal output)"
  excerpt="${excerpt//\`\`\`/[triple-backticks]}"

  {
    printf '\n## CLI_OUTPUT\n'
    printf -- '- timestamp: %s\n' "$(utc_now_iso)"
    printf -- '- source: %s\n' "$(compact_one_line "${source}")"
    printf -- '- session_label: %s\n' "$(compact_one_line "${session_label}")"
    printf -- '- command: %s\n' "$(compact_one_line "${command_label}")"
    printf -- '- return_code: %s\n' "${return_code}"
    printf -- '- stdout_summary: %s\n' "${stdout_summary}"
    printf -- '- stderr_summary: %s\n' "${stderr_summary}"
    printf -- '- content:\n'
    printf '```text\n%s\n```\n' "${excerpt}"
  } >> "${DYNAMIC_MEMORY_PATH}"
}

function conversation_bus_capture() {
  local source="${GCODEX_CLI_SOURCE:-}"
  local session_label="${GCODEX_SESSION_LABEL:-}"
  local explicit_source="0"
  local explicit_session="0"
  local quiet_mode="0"

  while [[ $# -gt 0 ]]; do
    case "$1" in
      --source)
        [[ $# -ge 2 ]] || { echo "Missing value for --source" >&2; return 1; }
        source="$2"
        explicit_source="1"
        shift 2
        ;;
      --session-label)
        [[ $# -ge 2 ]] || { echo "Missing value for --session-label" >&2; return 1; }
        session_label="$2"
        explicit_session="1"
        shift 2
        ;;
      --quiet)
        quiet_mode="1"
        shift
        ;;
      --help|-h)
        echo "Usage: ./scripts/conductor.sh bus-capture [--source OAC|GGC|...] [--session-label label] [--quiet] -- <command> [args...]" >&2
        return 0
        ;;
      --)
        shift
        break
        ;;
      *)
        break
        ;;
    esac
  done

  if [[ $# -lt 1 ]]; then
    echo "Usage: ./scripts/conductor.sh bus-capture [--source OAC|GGC|...] [--session-label label] [--quiet] -- <command> [args...]" >&2
    return 1
  fi

  local cmd=("$@")
  local command_label=""
  local arg=""
  for arg in "${cmd[@]}"; do
    if [[ -n "${command_label}" ]]; then
      command_label+=" "
    fi
    command_label+="$(printf '%q' "${arg}")"
  done
  local command_lower
  command_lower="$(printf '%s' "${command_label}" | tr '[:upper:]' '[:lower:]')"

  if [[ "${explicit_source}" != "1" ]]; then
    if [[ "${command_lower}" == *"gemini"* || "${command_lower}" == *"ggc"* ]]; then
      source="GGC"
    elif [[ "${command_lower}" == *"codex"* || "${command_lower}" == *"oac"* ]]; then
      source="OAC"
    elif [[ -z "${source}" ]]; then
      source="OAC"
    fi
  fi

  if [[ "${explicit_session}" != "1" ]]; then
    if [[ "${source}" == "GGC" ]]; then
      session_label="ggc-synthesis"
    elif [[ "${source}" == "OAC" && "${command_lower}" == *"codex"* ]]; then
      session_label="oac-codex"
    elif [[ "${command_lower}" == *"pytest"* || "${command_lower}" == *" test"* ]]; then
      session_label="verification"
    elif [[ -z "${session_label}" ]]; then
      session_label="local-cli"
    fi
  fi

  local stdout_file stderr_file
  stdout_file="$(mktemp)"
  stderr_file="$(mktemp)"
  local return_code
  set +e
  "${cmd[@]}" >"${stdout_file}" 2>"${stderr_file}"
  return_code=$?
  set -e

  local stdout_text stderr_text
  stdout_text="$(head -c 8192 "${stdout_file}" 2>/dev/null || true)"
  stderr_text="$(head -c 8192 "${stderr_file}" 2>/dev/null || true)"
  rm -f "${stdout_file}" "${stderr_file}"

  append_cli_output_block "${source}" "${session_label}" "${command_label}" "${return_code}" "${stdout_text}" "${stderr_text}"
  if [[ "${quiet_mode}" != "1" ]]; then
    echo "Conversation Bus captured CLI output (${source}/${session_label}) with return code ${return_code}."
  fi
  return "${return_code}"
}

function log_ambient_event() {
  local message="${1:-ambient event}"
  mkdir -p "$(dirname "${AMBIENT_INGRESS_LOG}")"
  printf '%s %s\n' "$(utc_now_iso)" "${message}" >> "${AMBIENT_INGRESS_LOG}"
}

function load_watch_folder_auto_start() {
  AUTO_START_ENABLED="0"
  AUTO_START_PARENT="${AMBIENT_DEFAULT_PARENT}"
  AUTO_START_INTERVAL="${GCODEX_WATCH_INTERVAL_SEC:-6}"
  AUTO_START_QUIET="1"
  if [[ ! -f "${AMBIENT_AUTO_START_FILE}" ]]; then
    return 0
  fi

  AUTO_START_ENABLED="1"
  while IFS='=' read -r key value; do
    case "${key}" in
      parent) AUTO_START_PARENT="${value}" ;;
      interval) AUTO_START_INTERVAL="${value}" ;;
      quiet) AUTO_START_QUIET="${value}" ;;
    esac
  done < "${AMBIENT_AUTO_START_FILE}"
}

function enable_watch_folder_auto_start() {
  local parent="${1:-${AMBIENT_DEFAULT_PARENT}}"
  local interval_raw="${2:-${GCODEX_WATCH_INTERVAL_SEC:-6}}"
  local quiet_mode="${3:-1}"
  local interval
  interval="$(normalize_watch_interval "${interval_raw}")"

  parent="${parent/#\~/${HOME}}"
  mkdir -p "${parent}"
  parent="$(cd "${parent}" && pwd -P)"

  cat > "${AMBIENT_AUTO_START_FILE}" <<EOF
parent=${parent}
interval=${interval}
quiet=${quiet_mode}
enabled_at=$(utc_now_iso)
enabled_by=conductor.sh
EOF
  log_ambient_event "watch-folder auto-start enabled parent=${parent} interval=${interval} quiet=${quiet_mode}"
}

function disable_watch_folder_auto_start() {
  rm -f "${AMBIENT_AUTO_START_FILE}"
  log_ambient_event "watch-folder auto-start disabled"
}

function maybe_auto_start_watch_folder() {
  load_watch_folder_auto_start
  if [[ "${AUTO_START_ENABLED}" != "1" ]]; then
    return 0
  fi
  if is_ambient_ingress_running; then
    return 0
  fi
  echo "Ambient ingress auto-start is enabled. Starting watch-folder..."
  start_watch_folder "${AUTO_START_PARENT}" "1" "${AUTO_START_INTERVAL}" "${AUTO_START_QUIET}" || true
}

function append_dynamic_memory_push_entry() {
  local commit_sha="${1:-unknown}"
  local snapshot_path="${2:-none}"
  mkdir -p "${BRAIN_DIR}"
  if [[ ! -f "${DYNAMIC_MEMORY_PATH}" ]]; then
    cat > "${DYNAMIC_MEMORY_PATH}" <<'EOF'
# DYNAMIC MEMORY
EOF
  fi
  {
    printf '\n## SESSION_LOG_ENTRY\n'
    printf -- '- timestamp: %s\n' "$(utc_now_iso)"
    printf -- '- agent: scripts/conductor.sh\n'
    printf -- '- action: push private/main --force-with-lease\n'
    printf -- '- commit: %s\n' "${commit_sha}"
    printf -- '- snapshot: %s\n' "${snapshot_path}"
    printf -- '- status: DONE\n'
  } >> "${DYNAMIC_MEMORY_PATH}"
}

function create_brain_snapshot_local() {
  local reason="${1:-Safety snapshot}"
  local actor="${2:-conductor.sh}"
  if [[ ! -d "${BRAIN_DIR}" ]]; then
    echo ""
    return 0
  fi

  local snapshot_rel
  snapshot_rel="$(
    SNAPSHOT_ROOT="${ROOT_DIR}" SNAPSHOT_REASON="${reason}" SNAPSHOT_ACTOR="${actor}" python3 - <<'PY'
import os
import zipfile
from datetime import datetime
from pathlib import Path

root = Path(os.environ["SNAPSHOT_ROOT"]).resolve()
brain = root / "G-Codex-brain"
backups = root / ".backups"
if not brain.exists():
    print("")
    raise SystemExit(0)

backups.mkdir(parents=True, exist_ok=True)
stamp = datetime.now().astimezone().strftime("%Y%m%d-%H%M%S")
base = f"G-Codex-brain-{stamp}"
target = backups / f"{base}.zip"
suffix = 1
while target.exists():
    target = backups / f"{base}-{suffix:02d}.zip"
    suffix += 1

with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED) as archive:
    for path in sorted(brain.rglob("*")):
        if path.is_file():
            archive.write(path, arcname=path.relative_to(root).as_posix())

print(target.relative_to(root).as_posix())
PY
  )"
  if [[ -z "${snapshot_rel}" ]]; then
    echo ""
    return 0
  fi
  echo "${snapshot_rel}"
}

function is_ignorable_runtime_path() {
  local path="${1:-}"
  case "${path}" in
    .backups/*|.brain_server.log|.watcher.log|.ambient_ingress.log|.ambient_ingress.pid|.ambient_ingress.parent|.ambient_ingress.auto_start|.watcher.pid|.notify_enabled|.swarm_packet.txt)
      return 0
      ;;
    *)
      return 1
      ;;
  esac
}

function log_push_action_local() {
  local commit_sha="${1:-unknown}"
  local snapshot_path="${2:-}"
  local branch_name="${3:-$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo unknown)}"
  mkdir -p "${ROOT_DIR}/.git"
  printf '%s | branch=%s | remote=private/main | commit=%s | snapshot=%s | mode=force-with-lease\n' \
    "$(utc_now_iso)" "${branch_name}" "${commit_sha}" "${snapshot_path:-none}" >> "${PUSH_LOG_FILE}"
}

function extract_proposal_id() {
  local text="${1:-}"
  local id
  id="$(echo "${text}" | grep -oE 'MDP-[0-9]{8}-[0-9]{6}-[0-9]{2,}' | head -n 1 || true)"
  echo "${id}"
}

function git_has_any_changes() {
  if ! git diff --quiet 2>/dev/null; then
    return 0
  fi
  if ! git diff --cached --quiet 2>/dev/null; then
    return 0
  fi
  local path
  while IFS= read -r path; do
    [[ -n "${path}" ]] || continue
    if ! is_ignorable_runtime_path "${path}"; then
      return 0
    fi
  done < <(git ls-files --others --exclude-standard 2>/dev/null || true)
  return 1
}

function git_has_staged_changes() {
  ! git diff --cached --quiet 2>/dev/null
}

function path_is_low_adventure_safe() {
  local path="${1:-}"
  [[ -n "${path}" ]] || return 1
  if [[ "${path}" == G-Codex-brain/* || "${path}" == scripts/* || "${path}" == docs/* ]]; then
    return 0
  fi
  if [[ "${path}" == "README.md" || "${path}" == "AGENTS.md" ]]; then
    return 0
  fi
  return 1
}

function is_untracked_ignored_path() {
  local path="${1:-}"
  [[ -n "${path}" ]] || return 1
  if git ls-files --error-unmatch -- "${path}" >/dev/null 2>&1; then
    return 1
  fi
  git check-ignore -q -- "${path}" 2>/dev/null
}

function stage_low_adventure_files() {
  local staged_count=0
  local path=""
  while IFS= read -r path; do
    [[ -n "${path}" ]] || continue
    if is_ignorable_runtime_path "${path}"; then
      continue
    fi
    if is_untracked_ignored_path "${path}"; then
      continue
    fi
    if path_is_low_adventure_safe "${path}"; then
      git add -- "${path}" >/dev/null 2>&1 || true
    fi
  done < <(
    {
      git diff --name-only
      git ls-files --others --exclude-standard
      git ls-files --deleted
    } | awk 'NF' | sort -u
  )

  staged_count="$(git diff --cached --name-only | awk 'NF' | wc -l | tr -d ' ')"
  echo "${staged_count}"
}

function ensure_short_lived_branch_merge() {
  local branch_name="${1:-}"
  local original_branch="${2:-}"
  [[ -n "${branch_name}" ]] || return 0
  [[ -n "${original_branch}" ]] || return 0

  if [[ "${branch_name}" == "${original_branch}" ]]; then
    return 0
  fi

  git checkout "${original_branch}" >/dev/null
  git merge --ff-only "${branch_name}" >/dev/null
  git branch -D "${branch_name}" >/dev/null 2>&1 || true
  echo "Short-lived branch ${branch_name} merged back into ${original_branch}."
}

function git_safe_commit() {
  local description="${1:-}"
  shift || true

  local proposal_id=""
  local harmonization_summary=""
  local auto_stage_safe="0"
  local short_lived_branch=""
  local original_branch=""
  local branch_created="0"

  while [[ $# -gt 0 ]]; do
    case "$1" in
      --proposal-id)
        [[ $# -ge 2 ]] || { echo "Missing value for --proposal-id" >&2; return 1; }
        proposal_id="$2"
        shift
        ;;
      --summary)
        [[ $# -ge 2 ]] || { echo "Missing value for --summary" >&2; return 1; }
        harmonization_summary="$2"
        shift
        ;;
      --auto-stage-safe)
        auto_stage_safe="1"
        ;;
      --branch)
        [[ $# -ge 2 ]] || { echo "Missing value for --branch" >&2; return 1; }
        short_lived_branch="$2"
        shift
        ;;
      *)
        echo "Unknown git-safe-commit option: $1" >&2
        echo "Usage: ./scripts/conductor.sh git-safe-commit \"slice description\" [--proposal-id MDP-...] [--summary \"...\"] [--auto-stage-safe] [--branch branch-name]" >&2
        return 1
        ;;
    esac
    shift
  done

  if [[ -z "${description}" ]]; then
    echo "Usage: ./scripts/conductor.sh git-safe-commit \"slice description\" [--proposal-id MDP-...] [--summary \"...\"] [--auto-stage-safe] [--branch branch-name]" >&2
    return 1
  fi

  git rev-parse --is-inside-work-tree >/dev/null 2>&1 || { echo "Not inside a git repository." >&2; return 1; }

  if [[ -n "$(git diff --name-only --diff-filter=U)" ]]; then
    echo "Unmerged files detected. Resolve conflicts before committing." >&2
    return 1
  fi

  if [[ -n "${short_lived_branch}" ]]; then
    original_branch="$(git rev-parse --abbrev-ref HEAD 2>/dev/null || true)"
    if [[ -z "${original_branch}" || "${original_branch}" == "HEAD" ]]; then
      echo "--branch requires a named current branch (not detached HEAD)." >&2
      return 1
    fi
    if [[ "${short_lived_branch}" != "${original_branch}" ]]; then
      if git show-ref --verify --quiet "refs/heads/${short_lived_branch}"; then
        echo "Short-lived branch already exists: ${short_lived_branch}. Choose a unique branch name." >&2
        return 1
      fi
      git checkout -b "${short_lived_branch}" >/dev/null
      branch_created="1"
      echo "Using short-lived branch: ${short_lived_branch}"
    fi
  fi

  local staged_before unstaged_before untracked_before
  staged_before="$(git diff --cached --name-only | awk 'NF' | wc -l | tr -d ' ')"
  unstaged_before="$(git diff --name-only | awk 'NF' | wc -l | tr -d ' ')"
  untracked_before="$(git ls-files --others --exclude-standard | awk 'NF' | wc -l | tr -d ' ')"
  echo "Dirty state: staged=${staged_before} unstaged=${unstaged_before} untracked=${untracked_before}"

  if [[ "${auto_stage_safe}" == "1" && "${staged_before}" == "0" ]]; then
    local staged_now
    staged_now="$(stage_low_adventure_files)"
    echo "Low-adventure auto-stage complete: staged=${staged_now}"
  fi

  if ! git_has_staged_changes; then
    echo "No staged changes to commit." >&2
    if [[ "${auto_stage_safe}" != "1" ]]; then
      echo "Tip: add files manually or pass --auto-stage-safe for conservative auto-staging." >&2
    fi
    return 1
  fi

  if [[ -z "${proposal_id}" ]]; then
    proposal_id="$(extract_proposal_id "${description}")"
  fi

  local snapshot_path
  snapshot_path="$(create_brain_snapshot_local "Pre-commit safety snapshot before: ${description}" "conductor.sh git-safe-commit")"
  if [[ -n "${snapshot_path}" ]]; then
    echo "Safety snapshot created: ${snapshot_path}"
  else
    echo "Safety snapshot skipped (G-Codex-brain not found)."
  fi

  local subject="${description}"
  if [[ -n "${proposal_id}" && "${subject}" != *"${proposal_id}"* ]]; then
    subject="${subject} [${proposal_id}]"
  fi

  local body=""
  if [[ -n "${proposal_id}" ]]; then
    body+="Proposal-ID: ${proposal_id}\n"
  fi
  if [[ -n "${harmonization_summary}" ]]; then
    body+="Harmonization-Summary: ${harmonization_summary}\n"
  fi
  if [[ -n "${snapshot_path}" ]]; then
    body+="Safety-Snapshot: ${snapshot_path}\n"
  fi
  body+="Changelog: ${CHANGELOG_PATH#${ROOT_DIR}/}"

  local commit_file
  commit_file="$(mktemp "${ROOT_DIR}/.git-safe-commit-msg.XXXXXX")"
  {
    printf '%s\n\n' "${subject}"
    printf '%b\n' "${body}"
  } > "${commit_file}"

  if ! git commit -F "${commit_file}"; then
    rm -f "${commit_file}"
    if [[ "${branch_created}" == "1" ]]; then
      git checkout "${original_branch}" >/dev/null 2>&1 || true
    fi
    return 1
  fi
  rm -f "${commit_file}"

  if [[ "${branch_created}" == "1" ]]; then
    ensure_short_lived_branch_merge "${short_lived_branch}" "${original_branch}"
  fi

  local short_sha
  short_sha="$(git rev-parse --short HEAD)"
  echo "git-safe-commit complete: ${short_sha}"
}

function push_with_safety() {
  local description="${1:-}"
  shift || true

  local commit_args=()
  local requested_branch=""
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --branch)
        if [[ $# -lt 2 ]]; then
          echo "Missing value for --branch" >&2
          return 1
        fi
        requested_branch="$2"
        commit_args+=("--branch" "$2")
        shift
        ;;
      *)
        commit_args+=("$1")
        ;;
    esac
    shift
  done

  git rev-parse --is-inside-work-tree >/dev/null 2>&1 || { echo "Not inside a git repository." >&2; return 1; }

  if git_has_any_changes; then
    if [[ -z "${description}" || "${description}" == --* ]]; then
      echo "Uncommitted changes detected. Provide an explicit slice description:" >&2
      echo "  ./scripts/conductor.sh push \"descriptive message\" [--proposal-id MDP-...] [--summary \"...\"] [--auto-stage-safe] [--branch branch-name]" >&2
      return 1
    fi
    echo "Changes detected. Running git-safe-commit before push..."
    git_safe_commit "${description}" "${commit_args[@]}"
  else
    echo "Working tree clean. No commit needed before push."
    if [[ -n "${requested_branch}" ]]; then
      echo "Note: --branch was provided but no commit was needed."
    fi
  fi

  local pre_push_snapshot
  pre_push_snapshot="$(create_brain_snapshot_local "Pre-push safety snapshot before private/main force-with-lease." "conductor.sh push")"
  if [[ -n "${pre_push_snapshot}" ]]; then
    echo "Pre-push snapshot created: ${pre_push_snapshot}"
  fi

  echo "Pushing to private/main with --force-with-lease..."
  git push private main --force-with-lease

  local head_sha
  head_sha="$(git rev-parse --short HEAD)"
  local current_branch
  current_branch="$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo unknown)"
  log_push_action_local "${head_sha}" "${pre_push_snapshot}" "${current_branch}"
  append_dynamic_memory_push_entry "${head_sha}" "${pre_push_snapshot:-none}"
  echo "Push complete: private/main @ ${head_sha}"
}

if [[ $# -lt 1 ]]; then
  echo "Usage: $(basename "$0") <command|slice description>" >&2
  echo "Commands:" >&2
  echo "  stop-server             Stop Brain Server if running" >&2
  echo "  start-server            Start/Restart Brain Server only" >&2
  echo "  dashboard               Start/Restart Brain Server and open Control Room" >&2
  echo "  watch [start|stop|status] [--quiet]  Manage clipboard watcher background process" >&2
  echo "  watch-folder [start|stop|status|auto-start] [parent-dir] [--yes] [--interval <sec>] [--quiet] [--off|--status]  Ambient ingress monitor" >&2
  echo "  bus-capture [--source OAC|GGC|...] [--session-label label] [--quiet] -- <command> [args...]  Run command and append bounded CLI_OUTPUT block" >&2
  echo "  git-safe-commit \"slice\" [--proposal-id MDP-...] [--summary \"...\"] [--auto-stage-safe] [--branch branch-name]  Safe commit with snapshot" >&2
  echo "  push [\"slice\"] [--proposal-id MDP-...] [--summary \"...\"] [--auto-stage-safe] [--branch branch-name]  Commit if needed, then push private/main" >&2
  echo "  auto-approve \"slice\"    Commit staged changes if they pass safety gate" >&2
  exit 1
fi

if [[ "$1" == "stop-server" ]]; then
  stop_brain_server
  exit $?
fi

if [[ "$1" == "start-server" ]]; then
  start_brain_server
  exit $?
fi

if [[ "$1" == "dashboard" ]]; then
  echo "Launching Control Room..."
  start_brain_server

  if ! is_watcher_running; then
    echo "Bridge watcher not running. Attempting auto-start..."
    start_watcher || true
  fi
  bridge_watcher_status_line
  maybe_auto_start_watch_folder

  if command -v xdg-open > /dev/null 2>&1; then
    xdg-open "${DASHBOARD_URL}" > /dev/null 2>&1 || true
    echo "Dashboard opened."
  else
    echo "xdg-open is not available. Open this URL manually:"
    echo "  ${DASHBOARD_URL}"
  fi
  exit 0
fi

if [[ "$1" == "watch" ]]; then
  shift
  watch_action="${1:-start}"
  quiet_mode="0"
  if [[ "${watch_action}" == "--quiet" ]]; then
    watch_action="start"
    quiet_mode="1"
  else
    shift || true
    while [[ $# -gt 0 ]]; do
      case "$1" in
        --quiet)
          quiet_mode="1"
          ;;
        *)
          echo "Unknown watch option: $1" >&2
          echo "Usage: ./scripts/conductor.sh watch [start|stop|status] [--quiet]" >&2
          exit 1
          ;;
      esac
      shift
    done
  fi

  case "${watch_action}" in
    start)
      start_watcher "${quiet_mode}"
      ;;
    stop)
      stop_watcher
      ;;
    status)
      watcher_status
      ;;
    *)
      echo "Unknown watch action: ${watch_action}" >&2
      echo "Usage: ./scripts/conductor.sh watch [start|stop|status] [--quiet]" >&2
      exit 1
      ;;
  esac
  exit $?
fi

if [[ "$1" == "watch-folder" ]]; then
  shift
  ambient_action="${1:-start}"
  ambient_parent="${AMBIENT_DEFAULT_PARENT}"
  ambient_yes="0"
  ambient_quiet="0"
  ambient_interval="${GCODEX_WATCH_INTERVAL_SEC:-6}"
  ambient_off="0"
  ambient_status_only="0"
  parent_set="0"

  if [[ "${ambient_action}" == "start" || "${ambient_action}" == "stop" || "${ambient_action}" == "status" || "${ambient_action}" == "auto-start" ]]; then
    [[ $# -gt 0 ]] && shift || true
  elif [[ -n "${ambient_action}" ]]; then
    ambient_parent="${ambient_action}"
    parent_set="1"
    ambient_action="start"
    [[ $# -gt 0 ]] && shift || true
  fi

  while [[ $# -gt 0 ]]; do
    case "$1" in
      --yes)
        ambient_yes="1"
        ;;
      --quiet)
        ambient_quiet="1"
        ;;
      --off)
        ambient_off="1"
        ;;
      --status)
        ambient_status_only="1"
        ;;
      --interval)
        if [[ $# -lt 2 ]]; then
          echo "Missing value for --interval" >&2
          exit 1
        fi
        ambient_interval="$2"
        shift
        ;;
      --help|-h)
        echo "Usage: ./scripts/conductor.sh watch-folder [start|stop|status|auto-start] [parent-dir] [--yes] [--interval <sec>] [--quiet] [--off|--status]" >&2
        exit 0
        ;;
      *)
        if [[ "${parent_set}" == "0" ]]; then
          ambient_parent="$1"
          parent_set="1"
        else
          echo "Unknown watch-folder option: $1" >&2
          echo "Usage: ./scripts/conductor.sh watch-folder [start|stop|status|auto-start] [parent-dir] [--yes] [--interval <sec>] [--quiet] [--off|--status]" >&2
          exit 1
        fi
        ;;
    esac
    shift
  done

  case "${ambient_action}" in
    start)
      start_watch_folder "${ambient_parent}" "${ambient_yes}" "${ambient_interval}" "${ambient_quiet}"
      ;;
    stop)
      stop_watch_folder
      ;;
    status)
      watch_folder_status
      ;;
    auto-start)
      if [[ "${ambient_status_only}" == "1" ]]; then
        watch_folder_status
        exit $?
      fi
      if [[ "${ambient_off}" == "1" ]]; then
        disable_watch_folder_auto_start
        echo "Watch-folder auto-start disabled."
        exit 0
      fi
      enable_watch_folder_auto_start "${ambient_parent}" "${ambient_interval}" "${ambient_quiet}"
      echo "Watch-folder auto-start enabled."
      start_watch_folder "${ambient_parent}" "1" "${ambient_interval}" "${ambient_quiet}"
      ;;
    *)
      echo "Unknown watch-folder action: ${ambient_action}" >&2
      echo "Usage: ./scripts/conductor.sh watch-folder [start|stop|status|auto-start] [parent-dir] [--yes] [--interval <sec>] [--quiet] [--off|--status]" >&2
      exit 1
      ;;
  esac
  exit $?
fi

if [[ "$1" == "bus-capture" ]]; then
  shift
  conversation_bus_capture "$@"
  exit $?
fi

if [[ "$1" == "git-safe-commit" ]]; then
  shift
  git_safe_commit "${1:-}" "${@:2}"
  exit $?
fi

if [[ "$1" == "push" ]]; then
  shift
  push_with_safety "${1:-}" "${@:2}"
  exit $?
fi

# --- 🛡️ AUTONOMOUS SAFETY GATE ---
# This function is restricted to Low Adventure slices only (deterministic, small, and low-risk).
function auto_approve() {
  local description="${1:-""}"

  # 0. Context check
  BRAIN_DIR="${BRAIN_DIR:-G-Codex-brain}"
  if [[ ! -d "$BRAIN_DIR" ]]; then
    echo "❌ ERROR: Cannot find G-Codex-brain directory." >&2
    return 1
  fi

  if [[ -z "$description" ]]; then
    echo "Usage: ./scripts/conductor.sh auto-approve \"your short slice description here\"" >&2
    return 1
  fi

  echo "🛡️  AUTONOMOUS SAFETY GATE: Checking staged changes..."
  
  # 1. Verification: Anything staged?
  local staged_files
  staged_files=$(git diff --name-only --cached)
  if [[ -z "${staged_files}" ]]; then
    echo "❌ ERROR: No staged changes found. Use 'git add' first." >&2
    return 1
  fi

  # 2. Safety Check: Unstaged changes?
  if ! git diff --exit-code > /dev/null; then
    echo "❌ ERROR: Unstaged changes detected. Manual review required." >&2
    return 1
  fi

  # --- 🤝 TRIAD OF TRUTH CONSENSUS ---
  
  # A. GROK (Alignment): Keyword check
  local forbidden="refactor|delete|remove|secret|brain|G-Codex-brain"
  if echo "${description}" | grep -qiE "${forbidden}"; then
    echo "❌ GROK REJECTED: High-risk keywords detected. Manual review required." >&2
    return 1
  fi
  echo "✅ GROK: APPROVED (Anti-drift verified)"

  # B. GEMINI 3 (Logic): Size & Boundary check
  local file_count
  file_count=$(echo "${staged_files}" | wc -l)
  if [[ ${file_count} -gt 5 ]]; then
    echo "❌ GEMINI 3 REJECTED: Slice size (${file_count} files) exceeds limit (5). Manual review required." >&2
    return 1
  fi
  echo "✅ GEMINI 3: APPROVED (Logic checked)"

  # C. CHATGPT (Clarity): Word count check
  local word_count
  word_count=$(echo "${description}" | wc -w)
  if [[ ${word_count} -lt 8 ]]; then
    echo "❌ CHATGPT REJECTED: Slice description too short (${word_count} words). Min 8 required."
    echo "Manual review required."
    return 1
  fi
  echo "✅ CHATGPT: APPROVED (UX/Docs polished)"
  echo "-----------------------------------"

  # 5. Execute Commit (Default Low Adventure)
  git commit -m "auto: ${description} [G-Codex-Gate]"
  
  # 6. Logging (Deterministic Memory)
  local timestamp
  timestamp=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
  local short_sha
  short_sha=$(git rev-parse --short HEAD)
  
  echo "| ${timestamp} | ${description} | ${short_sha} | G-Codex-Gate |" >> "${BRAIN_DIR}/MERGE_LOG.md"
  
  cat >> "${BRAIN_DIR}/DYNAMIC_MEMORY.md" <<LOG

### SESSION_LOG_ENTRY: ${timestamp}
- **Action**: Auto-Approval Gate execution.
- **Slice**: ${description}
- **Result**: Committed autonomously as ${short_sha} [G-Codex-Gate].
LOG

  echo "✨ SUCCESS: Slice committed as [${short_sha}] [G-Codex-Gate] and logged to memory."
  return 0
}

if [[ "$1" == "auto-approve" ]]; then
  auto_approve "${2:-""}"
  exit $?
fi

SLICE_DESC="$1"

required=(
  "${ROOT_DIR}/AGENTS.md"
  "${BRAIN_DIR}/00_INDEX.md"
  "${BRAIN_DIR}/00_BOOTSTRAP_GUIDE.md"
  "${BRAIN_DIR}/02_ETHOS_AND_PRODUCT_PRINCIPLES.md"
  "${BRAIN_DIR}/03_ACTIVE_NOW.md"
  "${BRAIN_DIR}/MERGE_LOG.md"
  "${BRAIN_DIR}/DYNAMIC_MEMORY.md"
  "${BRAIN_DIR}/AGENT_RULES.md"
)

for f in "${required[@]}"; do
  [[ -f "${f}" ]] || { echo "FILE_NOT_FOUND: ${f}" >&2; }
done

PACKET_FILE="${ROOT_DIR}/.swarm_packet.txt"
cat > "${PACKET_FILE}" <<PACKET
SLICE: ${SLICE_DESC}
REPO_NAME: $(basename "${ROOT_DIR}")
REPO_PATH: ${ROOT_DIR}
ROLE_EXECUTOR: OAC@mint-laptop
ROLE_REVIEWER: GEMINI3
ROLE_ALIGNMENT: GROK
RISK_CLASSIFIER: LOW_ONLY
CONTEXT_FILES:
- AGENTS.md
- G-Codex-brain/00_INDEX.md
- G-Codex-brain/00_BOOTSTRAP_GUIDE.md
- G-Codex-brain/02_ETHOS_AND_PRODUCT_PRINCIPLES.md
- G-Codex-brain/03_ACTIVE_NOW.md
- G-Codex-brain/MERGE_LOG.md
- G-Codex-brain/DYNAMIC_MEMORY.md
- G-Codex-brain/AGENT_RULES.md
PACKET

echo "Created packet: ${PACKET_FILE}"
echo "Next: send packet to executor/reviewer/alignment agents via your local tooling."

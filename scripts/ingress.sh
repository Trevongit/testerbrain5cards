#!/usr/bin/env bash
set -euo pipefail

SCRIPT_PATH="${BASH_SOURCE[0]}"
SCRIPT_DIR="$(cd -- "$(dirname -- "${SCRIPT_PATH}")" >/dev/null 2>&1 && pwd -P)"
TEMPLATE_ROOT="$(cd -- "${SCRIPT_DIR}/.." >/dev/null 2>&1 && pwd -P)"
BOOTSTRAP_SCRIPT="${SCRIPT_DIR}/bootstrap-brain.sh"

if [[ -z "${SCRIPT_DIR}" || ! -d "${SCRIPT_DIR}" ]]; then
  echo "Error: could not resolve ingress script directory." >&2
  exit 1
fi

if [[ ! -f "${BOOTSTRAP_SCRIPT}" ]]; then
  echo "Error: bootstrap script not found at expected path: ${BOOTSTRAP_SCRIPT}" >&2
  echo "Tip: ensure the full template folder was copied intact (scripts/bootstrap-brain.sh required)." >&2
  exit 1
fi

if [[ ! -f "${TEMPLATE_ROOT}/AGENTS.md" || ! -d "${TEMPLATE_ROOT}/G-Codex-brain" || ! -d "${TEMPLATE_ROOT}/scripts" ]]; then
  echo "Error: template root appears incomplete: ${TEMPLATE_ROOT}" >&2
  echo "Missing AGENTS.md, G-Codex-brain/, or scripts/. Copy the full template folder and retry." >&2
  exit 1
fi

usage() {
  cat <<USAGE
Usage: $(basename "$0") [target-repo-path] [--yes]
       $(basename "$0") --watch-folder <parent-dir> [--watch-interval <seconds>] [--watch-once] [--yes]

Interactive one-step ingress for G-Codex.
- If target path is omitted, current directory is used by default.
- Runs bootstrap automatically in deterministic non-interactive mode.
- Watch mode monitors a parent directory and bootstraps newly created subfolders.
USAGE
}

resolve_target_repo() {
  local raw_path="$1"
  raw_path="${raw_path/#\~/${HOME}}"

  if [[ ! -d "${raw_path}" ]]; then
    if ! mkdir -p "${raw_path}" 2>/dev/null; then
      echo "Error: cannot create target directory: ${raw_path}" >&2
      exit 1
    fi
    echo "Created target directory:" >&2
    echo "  ${raw_path}" >&2
  fi

  if ! cd "${raw_path}" >/dev/null 2>&1; then
    echo "Error: target directory is not accessible: ${raw_path}" >&2
    exit 1
  fi

  pwd -P
}

TARGET_REPO=""
ASSUME_YES="0"
WATCH_FOLDER_PARENT=""
WATCH_FOLDER_MODE="0"
WATCH_ONCE="0"
WATCH_INTERVAL_SEC="${GCODEX_WATCH_INTERVAL_SEC:-6}"
PROJECT_DESC_INPUT=""
LEAD_EXECUTOR_INPUT=""
FOCUS_AREA_INPUT=""
BOOTSTRAP_STATUS_HINT_INPUT=""
BOOTSTRAP_NEXT_SLICE_HINT_INPUT=""
ROADMAP_SCAN_ENABLED="${GCODEX_ROADMAP_SCAN_ENABLED:-1}"
ROADMAP_MAX_DEPTH="${GCODEX_ROADMAP_MAX_DEPTH:-4}"
ROADMAP_MAX_DIRS="${GCODEX_ROADMAP_MAX_DIRS:-7}"
ROADMAP_MAX_FILES_PER_DIR="${GCODEX_ROADMAP_MAX_FILES_PER_DIR:-2}"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --yes)
      ASSUME_YES="1"
      shift
      ;;
    --watch-folder)
      if [[ $# -lt 2 ]]; then
        echo "Error: --watch-folder requires a parent directory path." >&2
        usage
        exit 1
      fi
      WATCH_FOLDER_PARENT="$2"
      WATCH_FOLDER_MODE="1"
      shift 2
      ;;
    --watch-interval)
      if [[ $# -lt 2 ]]; then
        echo "Error: --watch-interval requires a numeric value in seconds." >&2
        usage
        exit 1
      fi
      WATCH_INTERVAL_SEC="$2"
      shift 2
      ;;
    --watch-once)
      WATCH_ONCE="1"
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

normalize_watch_interval() {
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

watch_folder_is_ignored() {
  local parent="$1"
  local child_name="$2"
  local ignore_file="${parent}/.gcodex-ignore"
  [[ -f "${ignore_file}" ]] || return 1
  while IFS= read -r raw || [[ -n "${raw}" ]]; do
    local line
    line="${raw%%#*}"
    line="$(echo "${line}" | xargs)"
    [[ -z "${line}" ]] && continue
    if [[ "${child_name}" == ${line} ]]; then
      return 0
    fi
  done < "${ignore_file}"
  return 1
}

run_watch_folder_mode() {
  local parent="${WATCH_FOLDER_PARENT}"
  if [[ -z "${parent}" ]]; then
    echo "Error: watch-folder mode requires --watch-folder <parent-dir>." >&2
    exit 1
  fi

  parent="$(resolve_target_repo "${parent}")"
  local interval
  interval="$(normalize_watch_interval "${WATCH_INTERVAL_SEC}")"
  local consent_file="${parent}/.gcodex-watch-consent"
  local state_file="${parent}/.gcodex-watch-state"

  if [[ ! -f "${consent_file}" ]]; then
    if [[ "${ASSUME_YES}" != "1" ]]; then
      echo
      echo "Ambient Ingress safety check:"
      echo "  Parent folder: ${parent}"
      echo "  New subfolders will be bootstrapped automatically."
      echo "  Ignored names/patterns in ${parent}/.gcodex-ignore are always respected."
      read -r -p "Enable watch-folder mode for this parent? [y/N]: " WATCH_CONFIRM
      WATCH_CONFIRM="${WATCH_CONFIRM:-N}"
      if [[ ! "${WATCH_CONFIRM,,}" =~ ^y ]]; then
        echo "Watch-folder mode cancelled."
        exit 1
      fi
    fi
    cat > "${consent_file}" <<EOF
enabled_at=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
enabled_by=ingress.sh
EOF
  fi

  declare -A known=()
  if [[ -f "${state_file}" ]]; then
    while IFS= read -r name || [[ -n "${name}" ]]; do
      [[ -n "${name}" ]] && known["${name}"]=1
    done < "${state_file}"
  else
    : > "${state_file}"
    while IFS= read -r existing; do
      local existing_name
      existing_name="$(basename "${existing}")"
      known["${existing_name}"]=1
      echo "${existing_name}" >> "${state_file}"
    done < <(find "${parent}" -mindepth 1 -maxdepth 1 -type d | sort)
  fi

  echo "Ambient ingress watch-folder active."
  echo "  Parent: ${parent}"
  echo "  Poll interval: ${interval}s"
  [[ "${WATCH_ONCE}" == "1" ]] && echo "  Mode: scan once"
  echo "  Ignore file: ${parent}/.gcodex-ignore"

  while true; do
    while IFS= read -r child; do
      local child_name
      child_name="$(basename "${child}")"
      [[ -z "${child_name}" ]] && continue
      [[ "${child_name}" == .* ]] && continue

      if watch_folder_is_ignored "${parent}" "${child_name}"; then
        continue
      fi

      if [[ -n "${known[${child_name}]:-}" ]]; then
        continue
      fi

      known["${child_name}"]=1
      echo "${child_name}" >> "${state_file}"

      if [[ -d "${child}/G-Codex-brain" && -f "${child}/scripts/conductor.sh" ]]; then
        echo "[watch-folder] ${child_name}: already bootstrapped, tracking only."
        continue
      fi

      local should_bootstrap="1"
      if [[ "${ASSUME_YES}" != "1" ]]; then
        read -r -p "[watch-folder] Bootstrap new folder '${child_name}' now? [Y/n]: " CHILD_CONFIRM
        CHILD_CONFIRM="${CHILD_CONFIRM:-Y}"
        if [[ "${CHILD_CONFIRM,,}" =~ ^n ]]; then
          should_bootstrap="0"
        fi
      fi

      if [[ "${should_bootstrap}" == "1" ]]; then
        echo "[watch-folder] Bootstrapping: ${child}"
        if ! bash "${SCRIPT_PATH}" "${child}" --yes; then
          echo "[watch-folder] Bootstrap failed for ${child_name}. Check logs and rerun manually." >&2
        fi
      else
        echo "[watch-folder] Skipped: ${child_name}"
      fi
    done < <(find "${parent}" -mindepth 1 -maxdepth 1 -type d | sort)

    [[ "${WATCH_ONCE}" == "1" ]] && break
    sleep "${interval}"
  done
}

if [[ "${WATCH_FOLDER_MODE}" == "1" ]]; then
  run_watch_folder_mode
  exit 0
fi

is_directory_empty() {
  local dir="$1"
  [[ -z "$(find "${dir}" -mindepth 1 -maxdepth 1 -print -quit 2>/dev/null)" ]]
}

has_git_anchor() {
  local dir="$1"
  [[ -e "${dir}/.git" ]]
}

is_ignored_rel_path() {
  local rel="$1"
  case "${rel}" in
    .git/*|.git|.venv/*|.venv|node_modules/*|node_modules|dist/*|dist|build/*|build|target/*|target|__pycache__/*|__pycache__|.idea/*|.idea|.vscode/*|.vscode|.next/*|.next|.nuxt/*|.nuxt|.cache/*|.cache|.pytest_cache/*|.pytest_cache|.mypy_cache/*|.mypy_cache|coverage/*|coverage|out/*|out|vendor/*|vendor|.terraform/*|.terraform|.gradle/*|.gradle|G-Codex-brain/*|G-Codex-brain|G-Codex-brain-archive/*|G-Codex-brain-archive|.backups/*|.backups)
      return 0
      ;;
    *)
      return 1
      ;;
  esac
}

is_key_file() {
  local rel="$1"
  local base
  base="$(basename "${rel}")"
  case "${base}" in
    README|README.*|Makefile|Dockerfile|docker-compose*.yml|docker-compose*.yaml|package.json|pyproject.toml|requirements*.txt|go.mod|Cargo.toml|pom.xml|build.gradle|build.gradle.kts|setup.py|setup.cfg|main.*|app.*|index.*|server.*|client.*|api.*|routes.*|config.*|settings.*|schema.*|models.*|controller.*|handler.*|cli.*)
      return 0
      ;;
  esac
  return 1
}

mermaid_label_escape() {
  local value="$1"
  value="${value//\"/\'}"
  printf '%s' "${value}"
}

truncate_text() {
  local value="$1"
  local limit="${2:-96}"
  value="$(echo "${value}" | tr '\n' ' ' | tr -s ' ' ' ')"
  if (( ${#value} <= limit )); then
    printf '%s' "${value}"
    return
  fi
  printf '%s...' "${value:0:$((limit - 3))}"
}

generate_dynamic_roadmap() {
  local repo_root="$1"
  local repo_name="$2"
  local roadmap_path="${repo_root}/G-Codex-brain/ROADMAP.md"
  local generated_at
  generated_at="$(date -u +"%Y-%m-%dT%H:%M:%SZ")"
  local max_depth="${ROADMAP_MAX_DEPTH}"
  local max_dirs="${ROADMAP_MAX_DIRS}"
  local max_files_per_dir="${ROADMAP_MAX_FILES_PER_DIR}"
  local max_root_files="${GCODEX_ROADMAP_MAX_ROOT_FILES:-6}"
  local max_total_modules="${GCODEX_ROADMAP_MAX_TOTAL_MODULES:-14}"
  local root_rel_files=()
  local key_root_files=()
  local top_dirs=()
  local candidate_files=()
  local picked_modules=()
  local milestones=()
  local module_summary_lines=()
  local node_action_lines=()
  local roadmap_summary=""

  if ! [[ "${max_depth}" =~ ^[0-9]+$ ]]; then
    max_depth=4
  fi
  if (( max_depth > 4 )); then
    max_depth=4
  fi
  if (( max_depth < 2 )); then
    max_depth=2
  fi

  if [[ "${ROADMAP_SCAN_ENABLED}" != "1" ]]; then
    cat > "${roadmap_path}" <<EOF
# ROADMAP

Generated: ${generated_at}

## Repo Structure Summary
- Roadmap scan disabled via \`GCODEX_ROADMAP_SCAN_ENABLED=0\`.

## Suggested Milestones
1. Confirm repository goals and current delivery baseline.
2. Launch Control Room and dispatch a low-adventure alignment slice.
3. Establish baseline tests and documentation as needed.

## Mermaid
\`\`\`mermaid
flowchart TB
    R["${repo_name}"] --> A["Define next implementation milestone"]
    A --> B["Dispatch next low-adventure slice"]
    B --> C["Validate and log progress"]
\`\`\`

## Roadmap Node Actions
- M1 | milestone | Define next implementation milestone
EOF
    ROADMAP_SUMMARY="Roadmap scan is disabled. Focus on next milestone definition and alignment execution."
    return 0
  fi

  declare -A allowed_dirs=()
  while IFS= read -r dir_path; do
    local rel
    rel="${dir_path#${repo_root}/}"
    is_ignored_rel_path "${rel}" && continue
    top_dirs+=("${rel}")
    allowed_dirs["${rel}"]=1
    [[ ${#top_dirs[@]} -ge ${max_dirs} ]] && break
  done < <(find "${repo_root}" -mindepth 1 -maxdepth 1 -type d | sort)

  while IFS= read -r file_path; do
    local rel
    rel="${file_path#${repo_root}/}"
    is_ignored_rel_path "${rel}" && continue
    if [[ "${rel}" != */* ]] && is_key_file "${rel}"; then
      root_rel_files+=("${rel}")
    fi
  done < <(find "${repo_root}" -mindepth 1 -maxdepth 1 -type f | sort)

  while IFS= read -r file_path; do
    local rel
    rel="${file_path#${repo_root}/}"
    is_ignored_rel_path "${rel}" && continue
    if is_key_file "${rel}"; then
      candidate_files+=("${rel}")
    fi
  done < <(find "${repo_root}" -mindepth 1 -maxdepth "${max_depth}" -type f | sort)

  for rf in "${root_rel_files[@]}"; do
    [[ ${#key_root_files[@]} -ge ${max_root_files} ]] && break
    case "$(basename "${rf}")" in
      README|README.*|package.json|pyproject.toml|Cargo.toml|go.mod|pom.xml|build.gradle|build.gradle.kts|Dockerfile|docker-compose*.yml|docker-compose*.yaml|Makefile)
        key_root_files+=("${rf}")
        ;;
    esac
  done

  declare -A per_dir_count=()
  declare -A dir_has_pick=()
  local total_module_nodes=0
  for rel in "${candidate_files[@]}"; do
    local top_dir
    top_dir="${rel%%/*}"
    if [[ "${rel}" != */* ]]; then
      continue
    fi

    [[ "${allowed_dirs[${top_dir}]:-0}" == "1" ]] || continue

    local count="${per_dir_count[${top_dir}]:-0}"
    if (( count >= max_files_per_dir )); then
      continue
    fi
    if (( total_module_nodes >= max_total_modules )); then
      break
    fi
    per_dir_count["${top_dir}"]=$((count + 1))
    total_module_nodes=$((total_module_nodes + 1))
    picked_modules+=("${rel}")
    dir_has_pick["${top_dir}"]=1
  done

  local milestone_candidates=()
  declare -A milestone_seen=()
  add_milestone() {
    local text="$1"
    [[ -z "${text}" ]] && return 0
    if [[ -n "${milestone_seen[${text}]:-}" ]]; then
      return 0
    fi
    milestone_seen["${text}"]=1
    milestone_candidates+=("${text}")
  }

  if [[ ! -f "${repo_root}/README.md" ]]; then
    add_milestone "Write README runbook and local launch instructions"
  fi
  if [[ ! -d "${repo_root}/tests" ]] && [[ ! -d "${repo_root}/test" ]] && [[ ! -d "${repo_root}/__tests__" ]]; then
    add_milestone "Add baseline tests for the core project flow"
  fi
  if [[ ! -d "${repo_root}/.github/workflows" ]]; then
    add_milestone "Create CI guardrail for lint and test checks"
  fi
  if [[ -d "${repo_root}/src" ]] || [[ -d "${repo_root}/app" ]]; then
    add_milestone "Map entrypoints and assign module ownership"
  fi
  if [[ -d "${repo_root}/dashboard-ui" ]] || [[ -d "${repo_root}/ui" ]]; then
    add_milestone "Run AGa visual verification pass on dashboard and UX flow"
  fi
  if [[ -f "${repo_root}/package.json" ]] && [[ ! -f "${repo_root}/tsconfig.json" ]] && [[ ! -f "${repo_root}/jsconfig.json" ]]; then
    add_milestone "Define JS/TS project config for deterministic builds"
  fi
  if [[ -f "${repo_root}/pyproject.toml" ]] && [[ ! -f "${repo_root}/ruff.toml" ]] && [[ ! -f "${repo_root}/.ruff.toml" ]]; then
    add_milestone "Add Python lint defaults for deterministic style checks"
  fi
  add_milestone "Dispatch next low-adventure slice from Control Room"
  add_milestone "Review roadmap and update handoff after each merge"
  if (( ${#milestone_candidates[@]} < 3 )); then
    add_milestone "Confirm branch state and current objective with lead executor"
  fi
  if (( ${#milestone_candidates[@]} < 3 )); then
    add_milestone "Align handoff with immediate repo priorities"
  fi
  milestones=("${milestone_candidates[@]:0:5}")
  if (( ${#milestones[@]} == 0 )); then
    milestones=("Dispatch next low-adventure slice")
  fi

  local mermaid="%%{init: {'theme':'dark','securityLevel':'loose','flowchart': {'curve':'basis','nodeSpacing': 78,'rankSpacing': 110,'padding': 24,'htmlLabels': true},'themeVariables': {'fontSize': '20px'}}}%%"$'\n'
  mermaid+="flowchart TB"$'\n'
  mermaid+="    R[\"$(mermaid_label_escape "${repo_name}")\"]"$'\n'
  mermaid+="    classDef repo fill:#1a1c24,stroke:#7b61ff,stroke-width:2.2px,color:#e0e0e6,font-size:22px,font-weight:700"$'\n'
  mermaid+="    classDef folder fill:#151a24,stroke:#3d4860,stroke-width:1.2px,color:#d5d9e3,font-size:19px"$'\n'
  mermaid+="    classDef keyfile fill:#122632,stroke:#00d9ff,stroke-width:1.8px,color:#c4f7ff,font-size:18px"$'\n'
  mermaid+="    classDef module fill:#171821,stroke:#57607a,stroke-width:1.2px,color:#e0e0e6,font-size:17px"$'\n'
  mermaid+="    classDef milestone fill:#1f1b2a,stroke:#a98bff,stroke-width:1.4px,color:#efe9ff,font-size:18px"$'\n'
  mermaid+=$'\n'
  mermaid+="    subgraph STRUCTURE[\"Repository Structure\"]"$'\n'
  mermaid+="        direction TB"$'\n'
  mermaid+="        subgraph MAIN[\"Main Folders\"]"$'\n'

  local dir_index=0
  local folder_ids=()
  for d in "${top_dirs[@]}"; do
    dir_index=$((dir_index + 1))
    local dir_id="D${dir_index}"
    folder_ids+=("${dir_id}")
    mermaid+="        ${dir_id}[\"$(mermaid_label_escape "${d}/")\"]"$'\n'
    node_action_lines+=("- ${dir_id} | folder | ${d}")
  done
  mermaid+="        end"$'\n'
  mermaid+=$'\n'

  local module_ids=()
  for i in "${!top_dirs[@]}"; do
    local d="${top_dirs[i]}"
    local dir_id="D$((i + 1))"
    if [[ "${dir_has_pick[${d}]:-0}" == "1" ]]; then
      mermaid+="        subgraph S$((i + 1))[\"${d}/ key modules\"]"$'\n'
      mermaid+="            direction TB"$'\n'
    fi
    local file_index=0
    local module_lines=()
    for rel in "${picked_modules[@]}"; do
      if [[ "${rel}" == "${d}/"* ]]; then
        file_index=$((file_index + 1))
        local file_id="F$((i + 1))_${file_index}"
        module_ids+=("${file_id}")
        mermaid+="            ${file_id}[\"$(mermaid_label_escape "${rel}")\"]"$'\n'
        mermaid+="            ${dir_id} --> ${file_id}"$'\n'
        module_lines+=("${rel}")
      fi
    done
    if [[ "${dir_has_pick[${d}]:-0}" == "1" ]]; then
      mermaid+="        end"$'\n'
      local module_summary
      module_summary="$(printf '%s; ' "${module_lines[@]}")"
      module_summary="${module_summary%; }"
      module_summary_lines+=("- ${d}/: ${module_summary}")
    fi
    mermaid+=$'\n'
  done

  local root_file_ids=()
  if (( ${#key_root_files[@]} > 0 )); then
    mermaid+="        subgraph ROOTFILES[\"Key Root Files\"]"$'\n'
    mermaid+="            direction TB"$'\n'
  fi
  local root_file_index=0
  for rf in "${key_root_files[@]}"; do
    root_file_index=$((root_file_index + 1))
    local root_file_id="RF${root_file_index}"
    root_file_ids+=("${root_file_id}")
    mermaid+="            ${root_file_id}[\"$(mermaid_label_escape "${rf}")\"]"$'\n'
  done
  if (( ${#key_root_files[@]} > 0 )); then
    mermaid+="        end"$'\n'
  fi
  mermaid+="    end"$'\n'
  mermaid+=$'\n'

  for i in "${!top_dirs[@]}"; do
    mermaid+="    R --> D$((i + 1))"$'\n'
  done
  for i in "${!key_root_files[@]}"; do
    mermaid+="    R --> RF$((i + 1))"$'\n'
  done
  mermaid+=$'\n'

  mermaid+="    subgraph NEXT[\"Suggested Next Milestones\"]"$'\n'
  local milestone_nodes=()
  for i in "${!milestones[@]}"; do
    local milestone_id="M$((i + 1))"
    local milestone_text
    milestone_text="$(truncate_text "${milestones[i]}" 56)"
    mermaid+="        ${milestone_id}[\"$((i + 1)). $(mermaid_label_escape "${milestone_text}")\"]"$'\n'
    milestone_nodes+=("${milestone_id}")
  done
  mermaid+="    end"$'\n'
  if (( ${#milestone_nodes[@]} > 0 )); then
    mermaid+="    R --> ${milestone_nodes[0]}"$'\n'
    for i in "${!milestone_nodes[@]}"; do
      if (( i == 0 )); then
        continue
      fi
      mermaid+="    ${milestone_nodes[i-1]} --> ${milestone_nodes[i]}"$'\n'
    done
  fi
  mermaid+=$'\n'

  mermaid+="    class R repo"$'\n'
  if (( ${#folder_ids[@]} > 0 )); then
    mermaid+="    class $(IFS=,; echo "${folder_ids[*]}") folder"$'\n'
  fi
  if (( ${#root_file_ids[@]} > 0 )); then
    mermaid+="    class $(IFS=,; echo "${root_file_ids[*]}") keyfile"$'\n'
  fi
  if (( ${#module_ids[@]} > 0 )); then
    mermaid+="    class $(IFS=,; echo "${module_ids[*]}") module"$'\n'
  fi
  if (( ${#milestone_nodes[@]} > 0 )); then
    mermaid+="    class $(IFS=,; echo "${milestone_nodes[*]}") milestone"$'\n'
  fi

  for i in "${!top_dirs[@]}"; do
    local dir_id="D$((i + 1))"
    local tooltip
    tooltip="$(truncate_text "Open folder: ${top_dirs[i]}/" 58)"
    mermaid+="    click ${dir_id} roadmapNodeClick \"$(mermaid_label_escape "${tooltip}")\""$'\n'
  done
  for i in "${!milestones[@]}"; do
    local milestone_id="M$((i + 1))"
    local milestone_tooltip
    milestone_tooltip="$(truncate_text "Queue mission: ${milestones[i]}" 64)"
    mermaid+="    click ${milestone_id} roadmapNodeClick \"$(mermaid_label_escape "${milestone_tooltip}")\""$'\n'
    node_action_lines+=("- ${milestone_id} | milestone | ${milestones[i]}")
  done

  local top_dirs_summary="(none detected)"
  if (( ${#top_dirs[@]} > 0 )); then
    top_dirs_summary="$(printf '%s, ' "${top_dirs[@]}")"
    top_dirs_summary="${top_dirs_summary%, }"
  fi

  local highlighted_count="${#picked_modules[@]}"
  local key_root_summary="(none detected)"
  if (( ${#key_root_files[@]} > 0 )); then
    key_root_summary="$(printf '%s, ' "${key_root_files[@]}")"
    key_root_summary="${key_root_summary%, }"
  fi
  roadmap_summary="Top folders: ${top_dirs_summary}. Key root files: ${key_root_summary}. Next milestone: ${milestones[0]}"

  {
    echo "# ROADMAP"
    echo
    echo "Generated: ${generated_at}"
    echo "Scan Settings: depth=${max_depth}, max_dirs=${max_dirs}, max_files_per_dir=${max_files_per_dir}, max_total_modules=${max_total_modules}"
    echo
    echo "## Repo Structure Summary"
    echo "- Top folders: ${top_dirs_summary}"
    echo "- Highlighted key modules: ${highlighted_count}"
    echo "- Key root files: ${key_root_summary}"
    echo
    echo "## Actionable Module Highlights"
    if (( ${#module_summary_lines[@]} == 0 )); then
      echo "- No deep module highlights detected within scan depth."
    else
      for line in "${module_summary_lines[@]}"; do
        echo "${line}"
      done
    fi
    echo
    echo "## Suggested Milestones"
    local milestone_index=0
    for milestone in "${milestones[@]}"; do
      milestone_index=$((milestone_index + 1))
      echo "${milestone_index}. ${milestone}"
    done
    echo
    echo "## Mermaid"
    echo '```mermaid'
    printf '%s\n' "${mermaid}"
    echo '```'
    echo
    echo "## Roadmap Node Actions"
    if (( ${#node_action_lines[@]} == 0 )); then
      echo "- M1 | milestone | Dispatch next low-adventure slice from Control Room"
    else
      for action in "${node_action_lines[@]}"; do
        echo "${action}"
      done
    fi
  } > "${roadmap_path}"

  ROADMAP_SUMMARY="${roadmap_summary}"
}

choose_brain_renew_mode() {
  local existing_brain="$1"
  local selected="clean"
  if [[ "${existing_brain}" != "1" ]]; then
    echo "clean"
    return 0
  fi

  if [[ "${ASSUME_YES}" == "1" ]]; then
    # Deterministic safe default in non-interactive mode for existing repos.
    echo "keep"
    return 0
  fi

  echo >&2
  echo "Existing G-Codex brain detected in target repo." >&2
  echo "Choose renewal mode:" >&2
  echo "  1) Clean Slate      (replace brain files with fresh state)" >&2
  echo "  2) Archive & Renew  (backup old brain, then fresh state)" >&2
  echo "  3) Keep as-is       (preserve existing brain files)" >&2
  read -r -p "Select [1/2/3] (default: 2): " RENEW_REPLY >&2
  RENEW_REPLY="${RENEW_REPLY:-2}"
  case "${RENEW_REPLY}" in
    1|clean|C|c)
      selected="clean"
      ;;
    2|archive|A|a)
      selected="archive"
      ;;
    3|keep|K|k)
      selected="keep"
      ;;
    *)
      selected="archive"
      ;;
  esac
  echo "${selected}"
}

archive_existing_brain() {
  local repo_root="$1"
  local stamp
  stamp="$(date -u +"%Y%m%dT%H%M%SZ")"
  local archive_root="${repo_root}/G-Codex-brain-archive"
  local archive_path="${archive_root}/brain-${stamp}"
  mkdir -p "${archive_root}"
  if [[ -d "${archive_path}" ]]; then
    archive_path="${archive_path}-$$"
  fi
  cp -a "${repo_root}/G-Codex-brain" "${archive_path}"
  printf '%s' "${archive_path}"
}

DEFAULT_TARGET="$(pwd)"
if [[ -z "${TARGET_REPO}" ]]; then
  TARGET_REPO="${DEFAULT_TARGET}"
  echo "No target path supplied. Using current directory:"
  echo "  ${TARGET_REPO}"
fi

TARGET_REPO="$(resolve_target_repo "${TARGET_REPO}")"

if [[ "${TARGET_REPO}" == "${TEMPLATE_ROOT}" ]]; then
  echo "Error: target repo cannot be the template root itself: ${TEMPLATE_ROOT}" >&2
  echo "Choose a different repository path (for example /tmp/my-project)." >&2
  exit 1
fi

if [[ ! -r "${BOOTSTRAP_SCRIPT}" ]]; then
  echo "Error: bootstrap script is not readable: ${BOOTSTRAP_SCRIPT}" >&2
  exit 1
fi

needs_confirmation="0"
confirm_reasons=()
if is_directory_empty "${TARGET_REPO}"; then
  needs_confirmation="1"
  confirm_reasons+=("directory is empty")
fi
if ! has_git_anchor "${TARGET_REPO}"; then
  needs_confirmation="1"
  confirm_reasons+=("no .git anchor detected")
fi

if [[ "${needs_confirmation}" == "1" && "${ASSUME_YES}" != "1" ]]; then
  echo
  echo "Quick safety check before ingress:"
  for reason in "${confirm_reasons[@]}"; do
    echo "  - ${reason}"
  done
  read -r -p "Continue bootstrapping here? [Y/n]: " CONFIRM_REPLY
  CONFIRM_REPLY="${CONFIRM_REPLY:-Y}"
  if [[ "${CONFIRM_REPLY,,}" =~ ^n ]]; then
    echo "Ingress cancelled. No changes made."
    exit 1
  fi
fi

echo
echo "Initializing G-Codex ingress into:"
echo "  ${TARGET_REPO}"
EXISTING_BRAIN="0"
if [[ -d "${TARGET_REPO}/G-Codex-brain" ]]; then
  EXISTING_BRAIN="1"
fi

BRAIN_RENEW_MODE="$(choose_brain_renew_mode "${EXISTING_BRAIN}")"
PRESERVE_BRAIN_BACKUP=""
ARCHIVE_PATH=""

if [[ "${EXISTING_BRAIN}" == "1" ]]; then
  case "${BRAIN_RENEW_MODE}" in
    archive)
      ARCHIVE_PATH="$(archive_existing_brain "${TARGET_REPO}")"
      echo "Archived existing brain to: ${ARCHIVE_PATH}"
      ;;
    keep)
      PRESERVE_BRAIN_BACKUP="$(mktemp -d)"
      cp -a "${TARGET_REPO}/G-Codex-brain" "${PRESERVE_BRAIN_BACKUP}/G-Codex-brain"
      echo "Preserving existing brain state (keep-as-is mode)."
      ;;
  esac
fi

if [[ "${ASSUME_YES}" != "1" && ! ( "${EXISTING_BRAIN}" == "1" && "${BRAIN_RENEW_MODE}" == "keep" ) ]]; then
  echo
  echo "Bootstrap localization assist (optional, press Enter to skip):"
  read -r -p "Current status hint for initial 03_ACTIVE_NOW.md [optional]: " BOOTSTRAP_STATUS_HINT_INPUT
  read -r -p "Next slice hint for initial 03_ACTIVE_NOW.md [optional]: " BOOTSTRAP_NEXT_SLICE_HINT_INPUT
fi

BOOTSTRAP_CMD=(bash "${BOOTSTRAP_SCRIPT}" "${TARGET_REPO}" --yes)
if [[ -n "${BOOTSTRAP_STATUS_HINT_INPUT}" ]]; then
  BOOTSTRAP_CMD+=(--status-hint "${BOOTSTRAP_STATUS_HINT_INPUT}")
fi
if [[ -n "${BOOTSTRAP_NEXT_SLICE_HINT_INPUT}" ]]; then
  BOOTSTRAP_CMD+=(--next-slice-hint "${BOOTSTRAP_NEXT_SLICE_HINT_INPUT}")
fi
"${BOOTSTRAP_CMD[@]}"

if [[ "${EXISTING_BRAIN}" == "1" && "${BRAIN_RENEW_MODE}" == "keep" && -d "${PRESERVE_BRAIN_BACKUP}/G-Codex-brain" ]]; then
  rm -rf "${TARGET_REPO}/G-Codex-brain"
  cp -a "${PRESERVE_BRAIN_BACKUP}/G-Codex-brain" "${TARGET_REPO}/G-Codex-brain"
  rm -rf "${PRESERVE_BRAIN_BACKUP}"
fi

REPO_NAME="$(basename "${TARGET_REPO}")"
GUIDE_PATH="${TARGET_REPO}/G-Codex-brain/01_FIRST_RUN_GUIDE.md"
HANDOFF_PATH="${TARGET_REPO}/G-Codex-brain/02_FIRST_HANDOFF.md"
ROLES_PATH="${TARGET_REPO}/G-Codex-brain/AGENT_ROLES.md"
TIMESTAMP="$(date -u +"%Y-%m-%dT%H:%M:%SZ")"
DEFAULT_PROJECT_DESC="Repository bootstrapped with G-Codex context overlay."
DEFAULT_LEAD_EXECUTOR="OAC"
DEFAULT_FOCUS_AREA="Stabilize repository context and prepare the next low-adventure implementation slice."

normalize_lead_executor() {
  local raw="${1:-}"
  raw="$(echo "${raw}" | tr '[:lower:]' '[:upper:]' | xargs)"
  case "${raw}" in
    ""|"OAC")
      echo "OAC"
      ;;
    "GGC")
      echo "GGC"
      ;;
    "AGA")
      echo "AGa"
      ;;
    "GROK")
      echo "Grok"
      ;;
    "GEMINI"|"GEMINI 3")
      echo "Gemini 3"
      ;;
    "CHATGPT")
      echo "ChatGPT"
      ;;
    *)
      echo "OAC"
      ;;
  esac
}

set_handoff_template_profile() {
  local destination="${1:-}"
  HANDOFF_TEMPLATE_NAME="Remote Advisory Handoff"
  HANDOFF_EXPECTED_ROLE="Advisory analysis and scoped recommendations."
  HANDOFF_TRUTH_ANCHOR='Use provided `G-Codex-brain/ROADMAP.md` excerpt + supplied repo evidence.'
  HANDOFF_PREFLIGHT_STEP='Do not assume local shell access. If repo status is missing or stale, request a fresh `git status --short --branch` report from a local executor.'
  HANDOFF_CAN_ASSUME_LINES=$'- Prompt context and explicit mission scope.\n- Coordination overlay excerpts from `G-Codex-brain/`.'
  HANDOFF_NOT_ASSUME_LINES=$'- Local filesystem write access.\n- Local shell or deterministic test execution in this environment.'

  case "${destination}" in
    OAC|GGC)
      HANDOFF_TEMPLATE_NAME="Local Executor Handoff"
      HANDOFF_EXPECTED_ROLE="Direct repository execution: implement, verify, and document deterministic slices."
      HANDOFF_TRUTH_ANCHOR='Run `git status --short --branch` and use `G-Codex-brain/ROADMAP.md` as coordination truth anchor.'
      HANDOFF_PREFLIGHT_STEP='Run `git status --short --branch` before planning. If dirty, treat as continuation work.'
      HANDOFF_CAN_ASSUME_LINES=$'- Local filesystem access in this repository.\n- Local shell + git availability for deterministic checks.'
      HANDOFF_NOT_ASSUME_LINES=$'- Remote-only advisory constraints.\n- Unverified cloud environment parity.'
      ;;
    AGa|Gemini\ 3|Grok|ChatGPT)
      ;;
    GitHub*|GH*)
      HANDOFF_TEMPLATE_NAME="GitHub-Connected Advisory Handoff"
      HANDOFF_EXPECTED_ROLE="Repository advisory via GitHub artifacts (issues/PRs/refs), not local execution."
      HANDOFF_TRUTH_ANCHOR='Use linked GitHub refs plus `G-Codex-brain/ROADMAP.md` excerpt from the source repo.'
      HANDOFF_PREFLIGHT_STEP='Use supplied branch/status evidence from GitHub or request a local executor refresh when missing.'
      HANDOFF_CAN_ASSUME_LINES=$'- GitHub repository/PR/issue context provided by links or refs.\n- Structured mission and acceptance criteria in handoff.'
      HANDOFF_NOT_ASSUME_LINES=$'- Direct local shell execution.\n- Guaranteed writable local repository access.'
      ;;
    Cloud*|*Cloud\ Coding*)
      HANDOFF_TEMPLATE_NAME="Cloud Coding Handoff"
      HANDOFF_EXPECTED_ROLE="Bounded implementation in an alternate execution environment with explicit verification notes."
      HANDOFF_TRUTH_ANCHOR='Use pinned branch/ref + `G-Codex-brain/ROADMAP.md` intent + required acceptance checks.'
      HANDOFF_PREFLIGHT_STEP='Confirm branch/ref and workspace state first; call out any environment differences before execution.'
      HANDOFF_CAN_ASSUME_LINES=$'- Isolated cloud workspace execution capability.\n- Ability to implement scoped code changes in that workspace.'
      HANDOFF_NOT_ASSUME_LINES=$'- Perfect parity with local developer environment.\n- Implicit access to local machine processes or unpublished state.'
      ;;
  esac
}

if [[ "${ASSUME_YES}" != "1" && ! ( "${EXISTING_BRAIN}" == "1" && "${BRAIN_RENEW_MODE}" == "keep" ) ]]; then
  echo
  echo "Smart first handoff setup (optional, press Enter to accept defaults):"
  read -r -p "Short project description [${DEFAULT_PROJECT_DESC}]: " PROJECT_DESC_INPUT
  read -r -p "Preferred Lead Executor (OAC/GGC/AGa/Grok/Gemini/ChatGPT) [${DEFAULT_LEAD_EXECUTOR}] (tip: OAC/GGC as CLI co-leads; AGa manual visual troubleshooter): " LEAD_EXECUTOR_INPUT
  read -r -p "Initial focus area [${DEFAULT_FOCUS_AREA}]: " FOCUS_AREA_INPUT
fi

PROJECT_DESC="${PROJECT_DESC_INPUT:-${DEFAULT_PROJECT_DESC}}"
LEAD_EXECUTOR="$(normalize_lead_executor "${LEAD_EXECUTOR_INPUT:-${DEFAULT_LEAD_EXECUTOR}}")"
FOCUS_AREA="${FOCUS_AREA_INPUT:-${DEFAULT_FOCUS_AREA}}"
set_handoff_template_profile "${LEAD_EXECUTOR}"

ROADMAP_SUMMARY="Roadmap summary unavailable."
ROADMAP_PATH="${TARGET_REPO}/G-Codex-brain/ROADMAP.md"
TRUTH_ANCHOR_NOTE=""
SKIP_BRAIN_REGEN="0"
if [[ "${EXISTING_BRAIN}" == "1" && "${BRAIN_RENEW_MODE}" == "keep" ]]; then
  SKIP_BRAIN_REGEN="1"
fi

# ROADMAP.md is always regenerated during ingress to keep navigator context current.
generate_dynamic_roadmap "${TARGET_REPO}" "${REPO_NAME}"
if [[ -f "${ROADMAP_PATH}" ]]; then
  TRUTH_ANCHOR_NOTE="Truth Anchor: \`G-Codex-brain/ROADMAP.md\` is the canonical source-of-truth for shipped workflows, lifecycle states, and open items."
else
  TRUTH_ANCHOR_NOTE="Missing Truth Anchor: \`G-Codex-brain/ROADMAP.md\` was not found. Regenerate ingress/roadmap before relying on generated handoff guidance."
  echo "Missing Truth Anchor: ${ROADMAP_PATH} was not found after roadmap generation." >&2
fi

if [[ "${SKIP_BRAIN_REGEN}" != "1" ]]; then
cat > "${ROLES_PATH}" <<EOF
# AGENT ROLES

# Preferred CLI co-leads: OAC and GGC.
# MD_BRAIN_ENGINE defaults to GGC for synthesis/supportive guidance; OAC remains execution lead.
# AGa remains troubleshooter/visual auditor (manual use; not default lead).
# CLI install/usage reference: see G-Codex-brain/CLI_TOOLS_REFERENCE.md (update weekly).
# Managing Directors: any listed agent can be assigned a sub-lead slice.
# Proposal flow: submit MD_PROPOSAL entries in DYNAMIC_MEMORY.md for Lead review.
LEAD_EXECUTOR: ${LEAD_EXECUTOR}
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

cat > "${HANDOFF_PATH}" <<EOF
# G-Codex First Handoff

Generated: ${TIMESTAMP}

## Repository Snapshot
- Repository Name: ${REPO_NAME}
- Repository Path: ${TARGET_REPO}
- Project Description: ${PROJECT_DESC}

## Lead Executor
- Agent: ${LEAD_EXECUTOR}
- Preferred CLI co-leads: OAC and GGC.
- AGa remains visual troubleshooter/auditor unless explicitly chosen by human.

## System Truth Anchor
${TRUTH_ANCHOR_NOTE}

## Dynamic Roadmap Snapshot
${ROADMAP_SUMMARY}

## Destination Capability Template
- Template: ${HANDOFF_TEMPLATE_NAME}
- Expected Role: ${HANDOFF_EXPECTED_ROLE}
- Truth Anchor: ${HANDOFF_TRUTH_ANCHOR}

### Can Assume Access
${HANDOFF_CAN_ASSUME_LINES}

### Do Not Assume
${HANDOFF_NOT_ASSUME_LINES}

## Continue From Here
Please take over as **${LEAD_EXECUTOR}** and start with this mission:

1. ${HANDOFF_PREFLIGHT_STEP}
2. If the reported working tree is not clean, treat this session as continuation work and override inherited clean-slate/bootstrap assumptions when repo reality disagrees.
3. Treat the repository as primary; use \`G-Codex-brain/\` as coordination overlay that reflects and serves repo reality.
4. Validate canonical overlay files (\`ROADMAP.md\`, \`03_ACTIVE_NOW.md\`, \`DYNAMIC_MEMORY.md\`, \`PROPOSAL_OUTCOMES.md\`) against real repo state.
5. Begin execution with focus on: **${FOCUS_AREA}**.
6. Prefer durable repo improvements over behavior that is unnecessarily coupled to ongoing overlay presence.
7. Keep proposal flow deterministic: \`HARMONIZATION_PENDING -> ASSESSED/READY_FOR_OAC/REJECTED -> explicit harmonized execution\`.
8. Keep persona alignment user-agnostic: read domains from \`G-Codex-brain/user_domain_nodes.json\` only.

## Ready-To-Paste Prompt
You are ${LEAD_EXECUTOR} continuing after G-Codex bootstrap alignment in \`${REPO_NAME}\`.
Destination template: ${HANDOFF_TEMPLATE_NAME}. ${HANDOFF_PREFLIGHT_STEP} Treat the repository as primary and \`G-Codex-brain/\` as a coordination overlay. Follow role expectations: ${HANDOFF_EXPECTED_ROLE} Use \`G-Codex-brain/ROADMAP.md\` as the truth anchor for current coordination state, and execute the next smallest high-confidence slice focused on: ${FOCUS_AREA}

This handoff was prepared automatically so you can continue immediately with clear context.
EOF

cat > "${GUIDE_PATH}" <<EOF
# Welcome to G-Codex

Generated: ${TIMESTAMP}

## Your Repository
- Name: ${REPO_NAME}
- Path: ${TARGET_REPO}

You now have a calm, local-first Control Room with deterministic proposal flow and sovereign orchestration.

## Quick Actions
1. Launch Control Room:
   \`\`\`bash
   ./scripts/conductor.sh dashboard
   \`\`\`
2. Enable Bridge watcher:
   \`\`\`bash
   ./scripts/conductor.sh watch start
   \`\`\`
3. Copy First Handoff:
   \`\`\`bash
   cat G-Codex-brain/02_FIRST_HANDOFF.md
   \`\`\`
4. Review CLI tools guidance:
   \`\`\`bash
   cat G-Codex-brain/CLI_TOOLS_REFERENCE.md
   \`\`\`
5. Read the guiding vision:
   \`\`\`bash
   cat G-Codex-brain/ENLIGHTENMENT_MANIFESTO.md
   \`\`\`
6. Review source-of-truth roadmap:
   \`\`\`bash
   cat G-Codex-brain/ROADMAP.md
   \`\`\`
7. Review a real-world case study:
   \`\`\`bash
   cat examples/openclaw-enlightenment.md
   \`\`\`
8. Explore Roadmap:
   - Folder nodes can open file explorer or terminal.
   - Milestone nodes can prefill a low-adventure dispatch mission.
9. Talk to the Managing Director in the Proposals panel (\`Talk to MD\`) for health, friction, and next-mission guidance.
10. Assign a Managing Director in the Proposals panel for an isolated slice.

## Leadership Defaults
- Preferred CLI co-leads: \`OAC\` and \`GGC\`.
- \`AGa\` remains manual-use troubleshooter/visual auditor (not default lead).
- Use \`⭐ Promote to Lead\` when you intentionally want to swap leadership.
- Keep CLI install/upgrade and non-interactive flag patterns current in \`G-Codex-brain/CLI_TOOLS_REFERENCE.md\`.

## Truth Anchor
${TRUTH_ANCHOR_NOTE}

## External Design Review Flow (MCP)

1. In MD Guidance, click \`Connect to External Tool (MCP)\`.
2. When MD shows request-pending (amber), click \`Authorize Design Interview\`.
3. External proposals are queued in \`G-Codex-brain/PROPOSAL_OUTCOMES.md\` as \`## DESIGN_PROPOSAL\`.
4. Use \`Review with MD\` to generate \`ASSESSMENT_REPORT\` updates.
5. Lifecycle stays deterministic and visible:
   - \`HARMONIZATION_PENDING\`
   - \`ASSESSED\` / \`READY_FOR_OAC\` / \`REJECTED\`
   - explicit harmonized execution only after human review
6. For assessed proposals, use \`Harmonize via OAC\` to generate a deterministic handoff directive.

## Persona Alignment (Person as Prime)
- Edit \`G-Codex-brain/user_domain_nodes.json\` with your active domain nodes.
- Keep domain data in user files only; do not hardcode personal interests into generator scripts.
- MD assessment and OAC handoff remain agnostic and data-driven.

## Managing Directors & Proposals

- Use \`Talk to MD\` for health checks, next steps, and calm strategy.
- The Managing Director learns your style over time and offers attuned, low-adventure suggestions. Watch for the subtle ✦ attuned marker when personality influences a response.
- Review and refine proposals before implementation.
- No automatic code mutation: harmonization remains explicit and human-led.

## Durable Logging and Recall

- Proposal state: \`G-Codex-brain/PROPOSAL_OUTCOMES.md\`
- Event log: \`G-Codex-brain/DYNAMIC_MEMORY.md\` (\`## EXTERNAL_TOOL_INJECTION\`, \`## CLI_OUTPUT\`)
- Merge-level history: \`G-Codex-brain/CHANGELOG.md\`

## You Are Now Ready
Run these commands in this order for the smoothest start:

\`\`\`bash
cd "${TARGET_REPO}"
./scripts/conductor.sh dashboard
./scripts/conductor.sh watch start
\`\`\`

You now have a coherent local-first control loop aligned with current repo reality and guarded by the ROADMAP truth anchor.
EOF
fi

echo
echo "Ingress complete. Nice start."
if [[ "${SKIP_BRAIN_REGEN}" == "1" ]]; then
  echo "Existing brain kept as-is (no brain file replacement performed)."
else
  echo "Personal first-run guide created:"
  echo "  ${GUIDE_PATH}"
  echo "Smart first handoff generated:"
  echo "  ${HANDOFF_PATH}"
  if [[ -n "${ARCHIVE_PATH}" ]]; then
    echo "Previous brain archived at:"
    echo "  ${ARCHIVE_PATH}"
  fi
  echo "Brain renewal mode: ${BRAIN_RENEW_MODE}"
fi
echo
echo "Recommended next steps:"
echo "  cd \"${TARGET_REPO}\""
echo "  ./scripts/conductor.sh dashboard"
echo "  ./scripts/conductor.sh watch start"
echo "  cat G-Codex-brain/02_FIRST_HANDOFF.md"
echo "  cat G-Codex-brain/ROADMAP.md"

if [[ "${ASSUME_YES}" != "1" ]]; then
  echo
  read -r -p "Launch the Control Room dashboard now? [Y/n]: " LAUNCH_REPLY
  LAUNCH_REPLY="${LAUNCH_REPLY:-Y}"
  if [[ ! "${LAUNCH_REPLY,,}" =~ ^n ]]; then
    (
      cd "${TARGET_REPO}"
      ./scripts/conductor.sh dashboard
    ) || {
      echo "Could not launch dashboard automatically."
      echo "Run manually:"
      echo "  cd \"${TARGET_REPO}\" && ./scripts/conductor.sh dashboard"
    }
  fi
fi

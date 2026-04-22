# OpenClaw Enlightenment

## From Generic Task Assistant to an Enlightened Engineering Matrix

OpenClaw can feel half-baked when it only reacts to tasks without system memory, strategic purpose, or maker-aware guidance.  
This case study shows how to upgrade it with a practical G-Codex pattern:

- **Prefrontal Cortex:** the Managing Director (MD) for synthesis, prioritization, and calm direction.
- **Central Nervous System:** the Conversation Bus for shared context, continuity, and handoff clarity.

The goal is not complexity for its own sake. The goal is a safer, more human-aligned engineering flow that stays local-first, deterministic, and non-destructive.

Guiding principle: **First, Do No Harm.**

## The Enlightenment Script (Ready to Run)

This script bootstraps G-Codex into an existing repo (for example, OpenClaw) with explicit safety checks and a reversible checkpoint.
It is designed to fail fast with clear messages and includes a dry-run mode for zero-write planning.

Safety note:
- This script is intended for a local clone you control.
- Default mode blocks dirty working trees to reduce accidental overlap.
- Use `--dry-run` first to preview actions before any write operation.

```bash
#!/usr/bin/env bash
set -euo pipefail
IFS=$'\n\t'

usage() {
  cat <<'USAGE'
Usage:
  ./enlighten-repo.sh --target-repo /path/to/openclaw [--template-root /path/to/g-code-brain-template] [--repo-name NAME] [--repo-desc DESC] [--allow-dirty] [--dry-run]

Purpose:
  Safely install the G-Codex brain + control-room stack into an existing repository.
  Default behavior is conservative and non-destructive.

Options:
  --target-repo   Required. Existing repository path to enlighten.
  --template-root Optional. Path to g-code-brain-template. Defaults to current working directory.
  --repo-name     Optional. Override localized repository name.
  --repo-desc     Optional. Override localized repository description.
  --allow-dirty   Optional. Allow bootstrap with uncommitted changes (not recommended).
  --dry-run       Optional. Print planned actions without changing files or tags.
  -h, --help      Show help.
USAGE
}

log() { printf '%s\n' "$*"; }
warn() { printf 'Warning: %s\n' "$*" >&2; }
fail() {
  local msg="$1"
  local hint="${2:-}"
  printf 'Error: %s\n' "$msg" >&2
  if [[ -n "$hint" ]]; then
    printf 'Hint: %s\n' "$hint" >&2
  fi
  exit 1
}

require_cmd() {
  command -v "$1" >/dev/null 2>&1 || fail "Missing required command: $1" "Install it and rerun."
}

canonical_path() {
  local input="$1"
  if [[ -d "$input" ]]; then
    (cd "$input" && pwd -P)
  else
    fail "Path does not exist or is not a directory: $input" "Check the path and rerun."
  fi
}

run_cmd() {
  if [[ "${DRY_RUN}" == "1" ]]; then
    printf '[dry-run]'
    printf ' %q' "$@"
    printf '\n'
    return 0
  fi
  "$@"
}

TARGET_REPO=""
TEMPLATE_ROOT="$(pwd -P)"
REPO_NAME=""
REPO_DESC="OpenClaw enlightened with G-Codex: MD brain + Conversation Bus, local-first and deterministic."
ALLOW_DIRTY="0"
DRY_RUN="0"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --target-repo)
      [[ $# -ge 2 ]] || fail "Missing value for --target-repo"
      TARGET_REPO="$2"
      shift 2
      ;;
    --template-root)
      [[ $# -ge 2 ]] || fail "Missing value for --template-root"
      TEMPLATE_ROOT="$2"
      shift 2
      ;;
    --repo-name)
      [[ $# -ge 2 ]] || fail "Missing value for --repo-name"
      REPO_NAME="$2"
      shift 2
      ;;
    --repo-desc)
      [[ $# -ge 2 ]] || fail "Missing value for --repo-desc"
      REPO_DESC="$2"
      shift 2
      ;;
    --allow-dirty)
      ALLOW_DIRTY="1"
      shift
      ;;
    --dry-run)
      DRY_RUN="1"
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      fail "Unknown argument: $1" "Use --help to see supported flags."
      ;;
  esac
done

[[ -n "$TARGET_REPO" ]] || { usage; fail "--target-repo is required" "Example: --target-repo /path/to/openclaw"; }

require_cmd bash
require_cmd git
require_cmd date

TARGET_REPO="$(canonical_path "$TARGET_REPO")"
TEMPLATE_ROOT="$(canonical_path "$TEMPLATE_ROOT")"
BOOTSTRAP_SCRIPT="${TEMPLATE_ROOT}/scripts/bootstrap-brain.sh"

[[ -f "$BOOTSTRAP_SCRIPT" ]] || fail "Bootstrap script not found: $BOOTSTRAP_SCRIPT" "Point --template-root at g-code-brain-template."
[[ -r "$BOOTSTRAP_SCRIPT" ]] || fail "Bootstrap script is not readable: $BOOTSTRAP_SCRIPT" "Fix file permissions and rerun."

if [[ -z "$REPO_NAME" ]]; then
  REPO_NAME="$(basename "$TARGET_REPO")"
fi

if [[ ! -d "${TARGET_REPO}/.git" ]]; then
  fail "Target is not a Git repository: ${TARGET_REPO}" "Initialize it first (git init or clone)."
fi

if [[ "$ALLOW_DIRTY" != "1" ]]; then
  if [[ -n "$(git -C "$TARGET_REPO" status --porcelain)" ]]; then
    fail "Target repo has uncommitted changes." "Commit/stash first, or rerun with --allow-dirty."
  fi
fi

if [[ "$TARGET_REPO" == "/" ]]; then
  fail "Refusing to operate on filesystem root (/)." "Use a specific repository path."
fi

if [[ "$TARGET_REPO" == "$TEMPLATE_ROOT" ]]; then
  fail "Target repo and template root are the same path." "Use a separate target clone to avoid self-mutation."
fi

timestamp="$(date -u +%Y%m%dT%H%M%SZ)"
checkpoint_tag="pre-gcodex-enlightenment-${timestamp}"

if [[ "$DRY_RUN" == "1" ]]; then
  warn "Dry-run mode enabled. No tags or files will be changed."
fi

# Safety checkpoint: lightweight, local, and reversible.
if git -C "$TARGET_REPO" rev-parse --verify HEAD >/dev/null 2>&1; then
  run_cmd git -C "$TARGET_REPO" tag -a "$checkpoint_tag" -m "Pre-G-Codex enlightenment checkpoint (${timestamp})"
  log "Created safety checkpoint tag: ${checkpoint_tag}"
else
  log "No commit history yet; skipping checkpoint tag creation."
fi

log "Bootstrapping G-Codex into: ${TARGET_REPO}"
run_cmd bash "$BOOTSTRAP_SCRIPT" "$TARGET_REPO" --repo-name "$REPO_NAME" --repo-desc "$REPO_DESC" --yes

if [[ "$DRY_RUN" == "1" ]]; then
  log
  log "Dry run complete. Review the planned commands above, then rerun without --dry-run."
  exit 0
fi

required_paths=(
  "AGENTS.md"
  "G-Codex-brain/00_INDEX.md"
  "G-Codex-brain/03_ACTIVE_NOW.md"
  "G-Codex-brain/ENLIGHTENMENT_MANIFESTO.md"
  "scripts/conductor.sh"
  "scripts/brain_server.py"
  "examples/openclaw-enlightenment.md"
)

for p in "${required_paths[@]}"; do
  [[ -e "${TARGET_REPO}/${p}" ]] || fail "Expected path missing after bootstrap: ${p}"
done

log
log "OpenClaw Enlightenment bootstrap complete."
log "Next steps:"
log "  1) cd \"${TARGET_REPO}\""
log "  2) ./scripts/conductor.sh dashboard"
log "  3) In dashboard: Talk to MD -> request next low-adventure slice -> execute with OAC."
```

### Script Validation (Before First Real Run)

Use this sequence for a deterministic, low-risk first pass:

```bash
chmod +x ./enlighten-repo.sh
bash -n ./enlighten-repo.sh
./enlighten-repo.sh --target-repo /path/to/openclaw --template-root /path/to/g-code-brain-template --dry-run
```

## Strategic Distillation

### 1) Repo Interview (Discovery)
Start with repo truth, not assumptions: architecture, branch state, risks, and friction points.
This turns vague intent into a concrete baseline for safe change.

### 2) Second Heart (MD-Led Management)
Install the Managing Director as the prefrontal layer.
The MD converts raw events into purposeful sequencing, calm guidance, and maker-aligned priorities.

### 3) Dynamic Muscles & Portability
Keep execution local-first and deterministic.
Favor surgical scripts, clear entry points, and portable flows that run across real developer environments.

### 4) Non-API Enlightenment
The biggest upgrade is not another API call.
It is the Conversation Bus: shared memory, harmonized proposals, and clear handoffs across sessions.

## What the MD Will Do After Enlightenment

- Anticipate useful next slices from roadmap and live context, not just react to prompts.
- Remember your working style and focus patterns, then shape guidance around how you actually build.
- Translate noisy activity into calm, low-adventure mission steps.
- Keep the project aligned to safety, truth, and maker delight when momentum gets messy.

## How the MD Brings Soul and Anticipation

Before enlightenment, a task assistant often executes atomized instructions without narrative memory or human alignment.  
The MD changes that by adding:

- maker-aware synthesis from terminal output, human notes, and shared memory.
- low-adventure anticipation that protects momentum and reduces context thrash.
- personal, supportive phrasing that stays practical while lowering friction.
- explicit guardrails for local-first safety and anti-drift truth.

Result: OpenClaw stops feeling half-baked and starts acting like a calm engineering partner with purpose.

## Next Steps (Fork, Run, Lead)

1. Fork or clone your OpenClaw repository locally.
2. Clone this G-Codex template locally.
3. Save the script above as `enlighten-repo.sh` in a safe local folder.
4. Run:
   ```bash
   chmod +x ./enlighten-repo.sh
   ./enlighten-repo.sh --target-repo /path/to/openclaw --template-root /path/to/g-code-brain-template
   ```
5. Open the Control Room:
   ```bash
   cd /path/to/openclaw
   ./scripts/conductor.sh dashboard
   ```
6. Ask the MD for a first low-adventure mission and execute it surgically with OAC.
7. Keep every slice aligned to: **First, Do No Harm**.

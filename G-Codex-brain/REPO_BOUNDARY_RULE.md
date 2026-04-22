# Repo Boundary Rule + Field Learning Ledger

## Purpose

Keep core G-Codex evolution deterministic and auditable while allowing safe learning from real project work.
Current operating center is Layer 1: one prime user, with focus/continuity/execution utility prioritized over early multi-user expansion.

## Repository Modes

### SOURCE_MODE
- Pure source repo where G-Codex itself evolves.
- Canonical place for core policy, runtime, dashboard, and template behavior changes.

### VALIDATION_MODE
- Disposable repos used to test core changes safely.
- Used to validate behavior before promoting changes into SOURCE_MODE.
- Use `G-Codex-brain/VALIDATION_OUTCOME.md` for concise evidence capture.
- Some scenarios require a minimal runtime file set (for example: `scripts/conductor.sh`, `scripts/brain_server.py`, `scripts/named_agent_dashboard.html`).

### PROJECT_MODE
- Real project repos with injected brain where the project remains primary.
- `G-Codex-brain/` acts as a coordination overlay currently present in the repo, not a replacement for project-owned truth.
- Project delivery is first priority; core brain evolution is not the default activity here.
- Prefer durable repo improvements over mechanisms that become unnecessarily dependent on continued overlay presence.
- Use `G-Codex-brain/PURITY_PROTOCOL.md` when deliberately returning an injected repo to pure project-only state.

## Repo Posture Declaration Standard

Declare repository posture in:
- `G-Codex-brain/REPO_POSTURE.json`

Minimum required fields:
- `posture_mode`
- `role`
- `source_ref`
- `project_id`
- `purity_status`

Current SOURCE_MODE declaration in this repo:
- `posture_mode`: `SOURCE_MODE`
- `role`: `g_codex_core_source`
- `source_ref`: `self`
- `project_id`: `g-code-brain-template`
- `purity_status`: `pure`

Expected declarations for later repos:
- VALIDATION_MODE repos should set `posture_mode: VALIDATION_MODE`, keep `source_ref` pointing to the SOURCE_MODE baseline under test, and mark `purity_status` as disposable validation.
- PROJECT_MODE repos should set `posture_mode: PROJECT_MODE`, keep `source_ref` pointing to the SOURCE_MODE baseline that was injected, and set `project_id` to the real project identity.

## Boundary Rules

1. Core changes are authored and finalized in SOURCE_MODE.
2. Core changes are tested in VALIDATION_MODE before SOURCE_MODE promotion when feasible.
3. PROJECT_MODE remains project-first; avoid turning project repos into the main core lab.
4. If a core issue is discovered in PROJECT_MODE, capture it locally, then return it to SOURCE_MODE intentionally.
5. Do not let ad-hoc project fixes become uncontrolled architecture drift.

## Field Learning Ledger (PROJECT_MODE)

Use a lightweight local ledger in injected project repos to capture core-brain observations for later return-home work.

Recommended local file path in project repos:
- `G-Codex-brain/FIELD_LEARNING_LEDGER.md`
- Use the SOURCE_MODE starter template for consistency.

Each entry should stay brief and operational:
- `date`
- `context` (what real project scenario exposed the issue)
- `observation` (bug/drift/friction)
- `impact`
- `send_home_candidate` (what should change in SOURCE_MODE)
- `status` (`captured`, `sent_home`, or `closed`)

## Send-Home Rule

When a ledger item is core-relevant:

1. Capture it in PROJECT_MODE ledger first (no rushed architecture edits).
2. Move to SOURCE_MODE deliberately.
3. Implement and validate in SOURCE_MODE/VALIDATION_MODE.
4. Re-ingress updated template behavior into project repos as needed.

See `G-Codex-brain/SEND_HOME_PROTOCOL.md` for the operational step sequence and status handling.

This keeps git history clearer, testing safer, and core evolution intentional.

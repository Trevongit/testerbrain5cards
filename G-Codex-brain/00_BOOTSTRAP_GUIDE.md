# 00 BOOTSTRAP GUIDE

## Purpose

This guide defines how to bootstrap and maintain the **G-Codex brain system** inside any repository while preserving:

1. **Determinism**
2. **Local-first operation**
3. **Anti-drift documentation discipline**
4. **Intelligent development method**

The brain is not optional metadata. It is the operational memory and coordination plane for G-Codex work.
In PROJECT_MODE injected repos, the repository remains primary and `G-Codex-brain/` is a coordination overlay describing and serving repo reality.

## Template Note

This repository is a reusable template. Some files may start as generic or reference examples. After bootstrap, localize them to target-repo truth before feature development.
Bootstrap defaults are intentionally neutral (not Phase-0 clean-slate assertions) so mature repos are not falsely reset in wording.

## Canonical Structure

Minimum expected layout:

```text
/
├── AGENTS.md
├── G-Codex-brain/
│   ├── 00_BOOTSTRAP_GUIDE.md
│   ├── 00_INDEX.md
│   ├── 01_FIRST_RUN_GUIDE.md
│   ├── 01_REPO_UNDERSTANDING.md
│   ├── 02_ETHOS_AND_PRODUCT_PRINCIPLES.md
│   ├── 03_ACTIVE_NOW.md
│   ├── 04_ACTION_PLAN_AND_ROADMAP.md
│   ├── 05_MULTI_ENGINEER_EXECUTION_MODEL.md
│   ├── 06_INTELLIGENT_DEV_METHOD.md
│   ├── 07_TEAM_DISCUSSION_AND_ASSESSMENT.md
│   ├── 08_BRAINSTORM_IDEAS.md
│   ├── AGENT_RULES.md
│   ├── CAPABILITIES.md
│   ├── DYNAMIC_MEMORY.md
│   ├── KNOWN_RISKS.md
│   ├── MERGE_LOG.md
│   ├── MULTI_AGENT_COORDINATION.md
│   ├── ROADMAP.md
│   ├── REPO_BOUNDARY_RULE.md
│   ├── REPO_POSTURE.json
│   ├── FIELD_LEARNING_LEDGER.md
│   ├── SEND_HOME_PROTOCOL.md
│   ├── VALIDATION_OUTCOME.md
│   └── PURITY_PROTOCOL.md
├── .cursor/
│   └── rules/            # optional, recommended
└── scripts/              # bootstrap and maintenance utilities
```

Mode-aware operating spine:

1. `REPO_BOUNDARY_RULE.md`: SOURCE/VALIDATION/PROJECT discipline.
2. `REPO_POSTURE.json`: posture declaration for this repo.
3. `FIELD_LEARNING_LEDGER.md`: local PROJECT_MODE field capture.
4. `SEND_HOME_PROTOCOL.md`: deliberate promotion flow into SOURCE_MODE.
5. `VALIDATION_OUTCOME.md`: disposable validation evidence record.
6. `PURITY_PROTOCOL.md`: shutdown-first return to true project-only state.

## Bootstrap Procedure (Per Target Repo)

1. **Establish repo truth first**
   - Confirm current branch and working tree state.
   - Confirm there is no unresolved or hidden change set.

2. **Inject brain structure**
   - Copy/adapt the full `G-Codex-brain/` set.
   - Add root `AGENTS.md` pointing to the brain.

3. **Localize identity without changing method**
   - Update repo-specific identity and product context.
   - In interactive ingress, provide optional localization assist hints (current status / next slice) when useful.
   - Update `00_INDEX.md` and `03_ACTIVE_NOW.md` to match target repo truth.
   - Preserve deterministic/local-first/anti-drift rules verbatim in spirit.

4. **Run anti-drift validation pass**
   - Ensure no document claims unimplemented behavior.
   - Ensure active state and roadmap reflect real, present repo status.
   - Ensure first lead handoff starts with repo-reality preflight (`git status --short --branch`) and continuation override when tree is dirty.
   - In PROJECT_MODE, prefer durable repo improvements over behavior that only works while overlay files remain present.

5. **Commit as a single bootstrap slice**
   - Keep bootstrap commit isolated and auditable.
   - Record major bootstrap action in `G-Codex-brain/MERGE_LOG.md`.

## Anti-Drift Rules

1. If it is not implemented and verifiable, it is not documented as done.
2. If behavior changes, brain docs are updated in the same slice.
3. If scope changes, roadmap and active-now are updated before next feature work.
4. Discovery summaries stay concise; technical truth remains in code and concrete artifacts.

## Determinism and Local-First Guardrails

1. Prefer deterministic defaults over creative variability.
2. Avoid cloud-only critical paths for core functionality.
3. Keep execution possible in an offline/local environment whenever practical.
4. Make verification steps explicit and repeatable.

## Intelligent Dev Method (Required)

1. **Research:** understand existing patterns and constraints.
2. **Strategy:** define the smallest viable slice.
3. **Execute:** implement surgically and verify.
4. **Log:** write down decisions, risks, and merge history.

## Session Handshake for Any Agent

At session start, do this in order:

1. Read `AGENTS.md`.
2. Read `G-Codex-brain/00_BOOTSTRAP_GUIDE.md` and `00_INDEX.md`.
3. Read `03_ACTIVE_NOW.md` for current reality.
4. Read `AGENT_RULES.md` and `06_INTELLIGENT_DEV_METHOD.md` before coding.

## What Success Looks Like

Bootstrap is successful when:

1. The brain is present and complete.
2. Agent behavior is constrained by local-first deterministic rules.
3. Docs and implementation remain synchronized over time.
4. New contributors can continue work without re-discovery overhead.

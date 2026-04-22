# Send-Home Protocol

## Purpose

Define the deliberate path for moving PROJECT_MODE field learning into canonical SOURCE_MODE improvement work.

## Core Rules

1. Not every field observation is source-worthy.
2. `send_home_candidate: yes` means intentional review, not auto-promotion.
3. SOURCE_MODE is the only canonical place for core evolution.
4. VALIDATION_MODE is used when isolated testing materially reduces risk.

## Workflow

1. `captured` (PROJECT_MODE)
   - Record the observation in `FIELD_LEARNING_LEDGER.md` with context, impact, and candidate flag.
2. Review / triage
   - Decide: `no`, `maybe`, or `yes` for send-home candidacy.
   - If `no`, close locally.
   - If `maybe`, keep captured until clarified.
   - If `yes`, proceed intentionally to SOURCE_MODE intake.
3. `sent_home`
   - Mark ledger entry as `sent_home`.
   - Create explicit SOURCE_MODE work item (issue/slice) with clear scope.
4. SOURCE_MODE implementation
   - Implement core change only in SOURCE_MODE, not ad-hoc in project repos.
5. VALIDATION_MODE check (when needed)
   - Run isolated validation in disposable repo when change benefits from risk-contained testing.
   - Capture outcomes using `G-Codex-brain/VALIDATION_OUTCOME.md`.
6. `closed`
   - Close when SOURCE_MODE change is merged (and validation completed when used).
   - Keep ledger entry as traceable history.

## Minimal Status Semantics

- `captured`: observed in PROJECT_MODE, not yet sent home.
- `sent_home`: accepted for deliberate SOURCE_MODE improvement.
- `closed`: no further action needed (rejected, superseded, or completed and merged).

# Purity Protocol

## Purpose

Define the safe sequence for returning an injected PROJECT_MODE repo to true project-only state without partial-purge drift.

## Core Constraints

1. Do not attempt purity while runtime processes are active.
2. Partial removal during active runtime can recreate minimal brain files and create false-clean confusion.
3. PROJECT_MODE repos can return to pure project state only through deliberate shutdown-first discipline.
4. Stale PID files are non-authoritative; live process checks determine blocking status.

## Ordered Sequence

1. Identify active runtime processes
   - Check for `brain_server.py`, watcher processes, and any active G-Codex runtime writing into the repo.
   - Validate PID-file references against live process existence; treat stale PID files as non-blocking.
2. Stop `brain_server.py`
   - Confirm the server process is no longer running.
3. Stop watcher processes
   - Confirm watcher/background bridge processes are no longer running.
4. Stop any remaining repo-writing G-Codex runtime
   - Ensure no active process can recreate brain/runtime files during purge.
5. Purge template-owned surfaces
   - Remove injected G-Codex runtime/brain/template surfaces intended to be purged.
6. Preserve project-owned assets
   - Do not remove project domain code, project docs, or project runtime assets.
7. Verify purity after removal
   - Confirm no active G-Codex runtime processes remain.
   - Confirm template-owned injected surfaces are removed as intended.
   - Confirm project-owned assets are intact.

## Posture Note

When a posture declaration exists, update `G-Codex-brain/REPO_POSTURE.json` `purity_status` only after shutdown + purge verification is complete.

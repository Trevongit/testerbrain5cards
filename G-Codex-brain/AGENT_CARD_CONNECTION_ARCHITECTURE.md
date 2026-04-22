# Agent Card Connection Architecture

## Purpose

Define a practical destination-aware handoff model so agent cards route context through pathways that match real access capabilities.

## Audited Surfaces

Current launch/handoff behavior was audited in:
- `scripts/ingress.sh` (`02_FIRST_HANDOFF.md` generation)
- `scripts/brain_server.py` (`_regenerate_first_handoff`, `/agent-launch`, local terminal launch helpers)
- `scripts/named_agent_dashboard.html` (`launchAgent`, `buildAgentPrompt`, `buildFallbackHandoff`)

These paths show mixed destination models today (local executor, MCP-gated advisory, browser advisory), so uniform handoff assumptions create friction.

## Capability Classes

| Class | Typical agents | Access assumptions | Best/safest connection pathway | Recommended handoff style | Likely context packet shape | Suitable work types |
|---|---|---|---|---|---|---|
| Local Executor | OAC, GGC | Local filesystem + local git + local runtime available | Dashboard `/agent-launch` -> local terminal helper (`codex`/`gemini`) | Execution-directive handoff with repo-reality preflight first | Full handoff + local file pointers + current branch/tree state + exact next slice | Deterministic implementation, verification, commits, runtime fixes |
| MCP-Gated Advisory | AGa (current model) | No automatic write path; read-only MCP resources only after MD authorization | MCP handshake via MD gatekeeper (`REQUEST_PENDING` -> `AUTHORIZED`) | Short advisory brief with explicit gated-state note and allowed resource scope | MD-approved read-only context set + current objective + requested visual/audit output format | Visual audit, design interview, troubleshooting insights |
| Remote Advisory | Gemini 3, Grok, ChatGPT (browser launch path) | Usually no local repo filesystem access; prompt-only + optional clipboard context | Browser URL launch + copy handoff fallback | Question-led advisory handoff with explicit access limits and requested output artifact | Compact brief: objective, constraints, posture summary, key excerpts, expected deliverable | Reasoning, architecture critique, alignment checks, wording/polish |
| GitHub-Connected Advisory | Any advisory agent with GitHub app/repo visibility but no local fs | Remote can inspect repo via GitHub links/PRs/issues but may not run local scripts | GitHub pointer handoff (repo URL, branch/PR/issue refs) + bounded ask | Evidence-seeking review handoff referencing exact GitHub artifacts | Objective + GitHub refs + constraints + acceptance criteria + requested diff/review format | PR review, issue triage, cross-repo advisory analysis |
| Cloud Coding Executor | Remote coding executor with isolated cloud workspace | Has execution ability, but environment differs from local source runtime | Explicit workspace handoff + branch/ref pin + validation checklist | Execution handoff with strict scope, reproducibility checks, and merge-back expectations | Branch/ref, target files, required commands/tests, expected outputs, risk guardrails | Bounded implementation, test execution, parallelizable coding slices |

## Context Inclusion Policy by Class

| Class | Include `posture_mode` / posture context | Include prime-user/core-purpose context | Include GitHub context pointer when local access unavailable |
|---|---|---|---|
| Local Executor | Yes (always) | Yes (brief, operational) | Optional |
| MCP-Gated Advisory | Yes (always) | Yes (brief, decision-shaping only) | Optional |
| Remote Advisory | Yes (always) | Yes (short summary to reduce semantic drift) | Yes (when no local repo access) |
| GitHub-Connected Advisory | Yes (always) | Yes (short summary) | Yes (always primary pointer) |
| Cloud Coding Executor | Yes (always) | Yes (brief, execution-relevant) | Yes (for canonical review/merge surfaces) |

## Shared Handoff Discipline

1. Start with repo-reality preflight (`git status --short --branch`) for lead/execution paths.
2. If repo reality disagrees with inherited bootstrap framing, continuation reality wins.
3. Declare access model in the handoff header (local, MCP-gated, remote advisory, GitHub-connected, or cloud executor).
4. Match requested output to class capability (advice vs executable change).
5. Keep packet minimal but sufficient: objective, constraints, acceptance criteria, and evidence pointers.

## Smallest Next Implementation Steps

1. Add a compact `access_class` field to agent-card metadata in dashboard runtime payload.
2. Teach fallback handoff generation to inject class-specific connection notes.
3. Add optional GitHub pointer block in browser-advisory handoff prompts when local access is absent.
4. Keep all changes additive and small; do not redesign card UI or launch architecture.

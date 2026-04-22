# G-Codex Capabilities & Maturity Matrix

This document tracks the current functional state of G-Codex features and their maturity levels.

| Feature | Current Status | Maturity | Next Slice | Notes |
| :--- | :--- | :--- | :--- | :--- |
| **MD Gatekeeper** | Active | High | Governance | Authorizes all external tool access. |
| **MCP Bridge** | Active | High | Automation | Local-first context exposure (Triad of Truth). |
| **Dashboard Runtime Surface** | Active | High | Coherence | Canonical UI path is served `/dashboard` via `brain_server.py` (not legacy `file://` launch). |
| **Easy-Start Launcher Flow** | Active | Medium | UX Clarity | Root `gcodex-easy-start.sh` + clickable `.desktop` launcher support click-first bootstrap/startup with terminal-visible fallback. |
| **Bootstrap Localization Assist** | Active | Medium | Operator Guidance | Interactive ingress can capture optional current-status and next-slice hints to reduce generic initial `03_ACTIVE_NOW.md` drift. |
| **Lead Handoff Reality Preflight** | Active | High | Consistency | First lead handoffs enforce `git status --short --branch` and continuation-mode override on dirty trees across generation/fallback paths. |
| **Runtime Posture Awareness** | Active | High | Coherence | `posture_mode`, `role`, and `purity_status` from `REPO_POSTURE.json` are surfaced in runtime status. |
| **Purity Execution Hardening** | Active | High | Safety | Purity flow enforces shutdown-first sequencing and tolerates stale PID files without weakening live-process detection. |
| **Snapshot/Restore Surface** | Active | Medium | Retention Policy | Backup artifact creation is verified; dashboard restore flow remains explicit and safety-first. |
| **MCP Failure Path Hygiene** | Active | High | Stability | Dependency/init failures are emitted to `stderr` to keep MCP `stdout` protocol-safe. |
| **Antigravity MCP Client Path** | Active | Medium | Setup Clarity | Validated path uses a dependency-complete interpreter (commonly repo-local `.venv`) configured on the client side. |
| **GitHub Integration** | Active | Medium | Write Actions | Read-only PR/Issue visibility + basic comments. |
| **Mission Logging** | Active | Medium | Automation | Logs assessed missions to GitHub Issues. |
| **PR Intelligence** | Active | Medium | Diff Analysis | Personality-attuned assessment prompts. |
| **Domain Nodes** | Active | High | Dynamic Swap | JSON-first manifest + automated hygiene audit. |
| **Readiness Pulse** | Active | High | Visualization | Score-driven health indicator (0-100). |
| **Sight Socket** | Active | Medium | Client Logic | Presence awareness + Direct CDP Screenshot (Phase 23 Lite). |
| **Visual Heartbeat** | Research | Research | Implementation | Reserved for future native MCP client-driven DOM checks. |
| **Browser Bridge** | Planned | Research | Implementation | Direct authorized Web LLM interaction (Phase 23). |

## Maturity Levels
- **High**: Stable, verified, and integrated into daily workflows.
- **Medium**: Functional but limited scope or requires manual triggers.
- **Low**: Experimental, initial detection, or basic connectivity only.
- **Research**: Architectural design only; no implementation yet.

## Context Surfaces (Current Truth)
G-Codex uses these concrete, auditable context surfaces:
- **Durable Memory**: `G-Codex-brain/DYNAMIC_MEMORY.md` for append-only event/state logs.
- **Proposal Lifecycle**: `G-Codex-brain/PROPOSAL_OUTCOMES.md` for non-destructive proposal and assessment state.
- **Persona/Domain Alignment**: `G-Codex-brain/user_domain_nodes.json` for deterministic domain-node guidance.

## Current Constraints
- MD gatekeeper semantics remain mandatory for external context release (`REQUEST_PENDING` -> `AUTHORIZED`/`REVOKED`).
- Sight maturity remains limited to presence awareness and direct CDP screenshots; no generalized browser-control client is shipped yet.

✦ **Provenance Guaranteed via Sovereign Signature.**

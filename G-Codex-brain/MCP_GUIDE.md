# MCP Guide (Sovereign External Tool Bridge)

This guide explains how G-Codex safely accepts external context and design proposals.

## Why This Exists

The MCP bridge lets external tools (for example Google Stitch) collaborate without bypassing project safety.
The Managing Director (MD) remains the gatekeeper.

## Core Safety Rules

- First, Do No Harm.
- No automatic code mutation from external tools.
- External design input is intake-only until reviewed.
- Authorization is explicit and session-scoped.

## End-to-End Flow

1. In MD Guidance, click `Connect to External Tool (MCP)`.
2. If a request is pending, click `Authorize Design Interview`.
3. External tool submits a design proposal via MCP.
4. Proposal is saved as a `## DESIGN_PROPOSAL` block in `G-Codex-brain/PROPOSAL_OUTCOMES.md`.
5. In dashboard `Review Design`, click `Review with MD`.
6. MD records structured assessment (`WORTH_ASSESSMENT`, `VALUE_SCORE`) and updates proposal status.
7. OAC/human decides harmonization path.

## Proposal Status Lifecycle

- `HARMONIZATION_PENDING`: newly ingested and waiting for MD review.
- `ASSESSED`: MD reviewed and added worth/value guidance.
- `READY_FOR_OAC`: MD assessment indicates this is ready for execution planning.

## What Gets Logged

All MCP and assessment actions are logged under:
- `## EXTERNAL_TOOL_INJECTION` in `G-Codex-brain/DYNAMIC_MEMORY.md`

This keeps the collaboration auditable and local-first.

## Operational Notes

- Primary MCP transport is stdio.
- Authorization resets on server restart.
- Gatekeeper scope in v1 is a single global authorize/revoke state.
- Deep Sea Mode and local-first behavior remain intact during MCP workflows.

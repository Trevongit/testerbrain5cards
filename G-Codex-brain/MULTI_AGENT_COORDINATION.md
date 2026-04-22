# MULTI AGENT COORDINATION

## Purpose

Define deterministic collaboration between human operators and multiple LLM/software agents using a single shared brain.

## Agent Naming Convention

1. Start with temporary names during bootstrap (for example: `AGENT_A`, `AGENT_B`).
2. Promote to stable names once scope hardens.
3. Suggested permanent pattern:
   - `OAC` = OpenAI Codex CLI on Linux Mint laptop.
   - `GEMINI3` = Gemini 3 primary reasoning agent.
   - `GEMINI_CLI` = Gemini CLI execution agent.
   - `CHATGPT` = ChatGPT strategic/review surface.
   - `GROK` = Grok auxiliary analysis surface.
4. Child agents use parent-qualified names: `OAC_CHILD_01`, `GEMINI3_CHILD_02`.

## Machine-Specific Naming

Use host-qualified IDs for the same agent type on different machines:

- `OAC@mint-laptop`
- `OAC@workstation`
- `GEMINI_CLI@cloud-vm-01`

This avoids memory collisions and preserves traceability.

## Hand-Off Protocol

Every hand-off must include these fields:

1. `from_agent`
2. `to_agent`
3. `timestamp`
4. `objective`
5. `state_summary`
6. `files_touched`
7. `commands_run`
8. `open_risks`
9. `next_expected_action`

Hand-off template:

```md
## HANDOFF
- from_agent: OAC@mint-laptop
- to_agent: GEMINI3
- timestamp: 2026-03-30T14:00:00+11:00
- objective: <target outcome>
- state_summary:
  - <fact 1>
  - <fact 2>
- files_touched:
  - <path>
- commands_run:
  - <command>
- open_risks:
  - <risk>
- next_expected_action: <single action>
```

For web/GitHub/cloud external destinations, use `EXTERNAL_AGENT_EXCHANGE_PACKET_STANDARD.md` and log outcomes in `EXTERNAL_AGENT_EXCHANGE_LOG.md`.

## Parallel Execution Rules

1. One writer at a time for code changes.
2. Multiple readers/verifiers can run in parallel.
3. Shared state is written to `G-Codex-brain/` as canonical memory.
4. If parallel branches are used, merge only after deterministic verification.

## Conflict Resolution

1. Record conflicting decisions and evidence in `G-Codex-brain/MERGE_LOG.md`.
2. Escalate major architecture or product-direction conflicts for human approval.
3. Resolve by append-only decision entry; do not erase previous rationale.
4. If unresolved, default to the most conservative deterministic/local-first path.

## Minimum Governance

1. No agent may claim unverified completion.
2. No agent may bypass anti-drift documentation updates.
3. No agent may perform major repo-shaping actions without human approval.

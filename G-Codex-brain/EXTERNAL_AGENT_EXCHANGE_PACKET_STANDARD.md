# External Agent Exchange Packet Standard

## Purpose

Provide one small, consistent packet shape for external advisory/cloud exchanges so different agents can contribute without access-model confusion.

This standard is documentation-first and manual-use friendly. It does not imply automation.

## Destination Types

- `remote_advisory_web` (for example: web ChatGPT/Gemini/Grok)
- `github_connected_advisory` (GitHub-visible, no local shell assumption)
- `cloud_coding_executor` (Codex cloud or similar remote coding workspace)

## Packet Template

```md
## EXTERNAL_AGENT_PACKET
- packet_id: EAP-YYYYMMDD-HHMMSS
- timestamp_utc: <ISO-8601>
- from_agent: <OAC/GGC/MD/Human>
- destination_type: <remote_advisory_web|github_connected_advisory|cloud_coding_executor>
- destination_label: <ChatGPT Web / GitHub Advisory / Codex Cloud>

### Repo Identity
- repo_name: <name>
- repo_path_or_url: <local path or canonical repo URL>
- posture_mode: <SOURCE_MODE|VALIDATION_MODE|PROJECT_MODE>

### Repo Reality Snapshot
- branch: <branch>
- git_status_short_branch: <paste output or summary>
- dirty_tree: <yes|no|unknown>

### Truth Anchor
- roadmap_path: G-Codex-brain/ROADMAP.md
- roadmap_excerpt: <2-6 lines relevant to current mission>

### Active Mission
- active_question_or_mission: <single concrete ask>
- why_now: <short practical reason>

### Access Assumptions
- can_assume:
  - <access fact 1>
  - <access fact 2>
- do_not_assume:
  - <non-access assumption 1>
  - <non-access assumption 2>

### Scope + Acceptance
- scope_boundaries:
  - <in-scope item>
  - <out-of-scope item>
- acceptance_criteria:
  - <criterion 1>
  - <criterion 2>

### Expected Response Shape
- requested_output_type: <advisory|plan|patch_suggestion|execution_report>
- response_format_hint: <bullets / diff notes / risk list>
```

## Practical Notes by Destination

- `remote_advisory_web`: keep packets concise; include explicit non-assumption of local shell/filesystem access.
- `github_connected_advisory`: include repo/PR/issue links and branch evidence; avoid assuming local execution.
- `cloud_coding_executor`: pin branch/ref and acceptance checks; require explicit environment-difference notes.

## Minimum Discipline

1. Repo-reality snapshot must be included (or marked `unknown`).
2. Access assumptions must be explicit.
3. Truth anchor excerpt must be concrete, not generic.
4. Keep packet scope bounded to one mission whenever possible.

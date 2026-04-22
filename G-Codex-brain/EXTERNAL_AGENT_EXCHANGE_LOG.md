# External Agent Exchange Log (Skeleton)

## Purpose

Record external-agent packet exchanges and resulting decisions so later agents can follow what happened without re-discovery.

Use this as a lightweight append-only log. Keep entries short and factual.

## Outcome Types

- `advisory_only`
- `proposal_input`
- `implementation_input`
- `rejected`

## Entry Template

```md
## EXTERNAL_EXCHANGE_ENTRY
- timestamp_utc: <ISO-8601>
- destination_type: <remote_advisory_web|github_connected_advisory|cloud_coding_executor>
- destination_label: <ChatGPT Web / GitHub Advisory / Codex Cloud>
- packet_id: <EAP-...>

### Packet Summary
- mission: <one-line mission>
- truth_anchor_used: <ROADMAP excerpt reference>
- access_assumptions: <one-line summary>

### Response Summary
- key_points:
  - <point 1>
  - <point 2>
- risks_or_unknowns:
  - <risk 1>

### Decision + Action
- outcome_type: <advisory_only|proposal_input|implementation_input|rejected>
- resulting_action: <what we did next>
- decision_owner: <OAC/GGC/MD/Human>
- follow_up_ref: <PR/issue/commit/path or n/a>
```

## Log Starts

(No entries yet in this source template.)

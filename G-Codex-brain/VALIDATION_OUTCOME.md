# Validation Outcome (VALIDATION_MODE)

Use this template in VALIDATION_MODE repos only.

- VALIDATION_MODE repos are disposable and evidence-focused.
- Validation notes support SOURCE_MODE decisions and the send-home flow.
- Validation repos must not become semi-permanent shadow projects.

## Entry Template

```text
## YYYY-MM-DD — <short validation title>
- date: YYYY-MM-DD
- validation_scenario: <what validation environment/path is being exercised>
- objective: <what this validation is trying to prove or falsify>
- change_under_test: <specific source change, behavior, or slice>
- result: pass|fail|partial — <short outcome description>
- evidence: <commands, outputs, artifacts, links, or notes supporting the result>
- runtime_pid_observed: yes|no (optional)
- recommended_next_step: send_home|no_action|further_validation
- status: open|closed
- source_commit_ref: <optional SOURCE_MODE commit SHA or PR ref>
```

## Validation Runs

Append new validation runs below this section (newest first).

### Example Entry

```text
## 2026-04-18 — Dashboard launcher served URL validation
- date: 2026-04-18
- validation_scenario: fresh VALIDATION_MODE ingress repo on Linux with xdg-open available
- objective: verify dashboard launch path uses served /dashboard endpoint
- change_under_test: conductor dashboard launch behavior
- result: pass — launcher opened http://127.0.0.1:8765/dashboard and server returned 200
- evidence: captured xdg-open target plus curl probe to /dashboard
- runtime_pid_observed: yes
- recommended_next_step: send_home
- status: closed
- source_commit_ref: 2fb1cca
```

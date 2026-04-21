# Field Learning Ledger (PROJECT_MODE)

Use this lightweight ledger in injected project repos to capture core-brain observations during real delivery work.

- Project repos are project-first.
- Capture field learning locally.
- Send source-worthy improvements home to SOURCE_MODE deliberately.
- Do not use this ledger as a place for uncontrolled architecture drift.

## Entry Template

```text
## YYYY-MM-DD — <short title>
- date: YYYY-MM-DD
- context: <real project scenario where this surfaced>
- observation: <bug/drift/friction observed>
- impact: <why it matters in project execution>
- send_home_candidate: no|maybe|yes
- status: captured|sent_home|closed
```

## Example Entry

```text
## 2026-04-18 — Dashboard launcher mismatch
- date: 2026-04-18
- context: PROJECT_MODE repo launch via ./scripts/conductor.sh dashboard
- observation: launcher opened file:// dashboard instead of served /dashboard URL
- impact: runtime behavior differed from SOURCE_MODE truth and caused operator confusion
- send_home_candidate: yes
- status: sent_home
```

## Operating Notes

1. Keep entries concise and factual.
2. Mark `send_home_candidate: yes` only when the change is core/template relevant.
3. When a `yes` item is sent home, update status to `sent_home` and link the SOURCE_MODE commit/PR in the entry body.
4. Use `closed` when no further SOURCE_MODE action is needed.
5. Follow `G-Codex-brain/SEND_HOME_PROTOCOL.md` for the intentional `captured -> sent_home -> closed` path.

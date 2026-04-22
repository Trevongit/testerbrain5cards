# CLI TOOLS REFERENCE

Last Updated: 2026-04-13 (Australia/Sydney)

Purpose:
- Keep OAC and GGC usage practical, current, and deterministic.
- Reduce drift between dashboard behavior and CLI reality.

## Baseline

- OpenAI Codex CLI package: `@openai/codex`
- Google Gemini CLI package: `@google/gemini-cli`
- Leadership default: OAC + GGC are preferred CLI co-leads.
- MD synthesis default: `GGC`; execution lead: `OAC`.

## Install and Upgrade

```bash
# Install
npm install -g @openai/codex @google/gemini-cli

# Upgrade
npm install -g @openai/codex@latest @google/gemini-cli@latest

# Verify
codex --version
gemini --version
```

Optional version lookup:

```bash
npm view @openai/codex version
npm view @google/gemini-cli version
```

## Choose OAC vs GGC

- Choose OAC for surgical deterministic implementation and verification.
- Choose GGC for deeper synthesis, architecture framing, and strategic tradeoffs.
- Use both when helpful: GGC frames, OAC executes.

## Recommended Patterns

### OAC (Codex CLI)

```bash
codex exec "Implement the smallest deterministic fix, run one verification, and summarize the diff."
```

Example with explicit controls:

```bash
codex exec \
  --sandbox workspace-write \
  --ask-for-approval never \
  "Apply one low-adventure patch and run one local check."
```

### GGC (Gemini CLI)

Persistent interactive session with startup context:

```bash
gemini -i "Review current state and suggest one calm low-adventure next step."
```

Alternative documented interactive startup:

```bash
gemini "Review current state and suggest one calm low-adventure next step."
```

Session resume:

```bash
gemini -r latest
```

Non-interactive one-shot (for scripts only):

```bash
gemini --prompt "Summarize current risks and propose one deterministic next slice."
```

## Dashboard Continuity Notes

- `Open Full GGC Terminal` should open a terminal and start Gemini in interactive mode.
- `Continue this conversation` keeps MD-to-GGC handoff continuity for the next message.
- If auto-launch is unavailable, use the copied helper packet and follow the 3-step instructions.

## Weekly Anti-Drift Checklist

1. Run `codex --help` and `gemini --help`.
2. Confirm package versions with `npm view`.
3. Update this file's `Last Updated` date if behavior changed.
4. Keep these files aligned:
   - `README.md`
   - `G-Codex-brain/01_FIRST_RUN_GUIDE.md`
   - `G-Codex-brain/AGENT_ROLES.md`

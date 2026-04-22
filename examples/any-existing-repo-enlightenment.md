# Any Existing Repo Enlightenment

## 99% Hands-Off Path

This guide shows how to enlighten almost any existing repository with minimal manual overhead.

Flow:
1. Clone target repo.
2. Run `enlighten-repo.sh` once.
3. Open Control Room and let MD take the helm for low-adventure sequencing.

## Preconditions (Safe and Practical)

- You have a full local clone of the target repository.
- You have a local clone of this G-Codex template.
- You want a non-destructive, local-first bootstrap.

## Step-by-Step

1. Clone any existing repo:
```bash
git clone https://github.com/<owner>/<repo>.git
cd <repo>
```

2. Use the existing Enlightenment script pattern:
- If you already have `enlighten-repo.sh`, reuse it.
- Otherwise, copy the script from `examples/openclaw-enlightenment.md`.

3. Run enlightenment:
```bash
./enlighten-repo.sh \
  --target-repo /absolute/path/to/<repo> \
  --template-root /absolute/path/to/g-code-brain-template
```

4. Start the Thinking Machine:
```bash
cd /absolute/path/to/<repo>
./scripts/conductor.sh dashboard
```

5. Let MD take the helm:
- Ask: `What should I focus on next?`
- Accept one low-adventure slice.
- Execute surgically with OAC.

## What Happens Automatically

After bootstrap, the repo receives:
- `G-Codex-brain/` persistent memory and operating context.
- Control Room dashboard and local brain server.
- MD guidance, complexity filter, and matched intelligence routing.
- Safety-first local workflow with deterministic defaults.

## Non-Destructive Safety Notes

- Default mode blocks dirty working trees.
- A reversible pre-enlightenment checkpoint tag is created when possible.
- High-adventure or unclear asks trigger clarification before execution.
- Core path remains local-first with graceful fallback behavior.

## First Productive Loop (Recommended)

1. Tell MD your style hints:
- `I prefer calm low-adventure slices and visual polish.`

2. Request next step:
- `What should I focus on next?`

3. Execute one slice only:
- Keep scope narrow.
- Verify locally.
- Log the outcome in brain memory.

This is how any existing repo transitions into an enlightened engineering matrix with minimal ceremony and maximum clarity.

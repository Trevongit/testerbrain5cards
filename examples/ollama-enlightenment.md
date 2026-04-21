# Ollama Enlightenment: Deep Sea Mode

## Sovereign Thinking Machine (Local-First)

Deep Sea Mode is the local sovereign lane of the G-Codex Thinking Machine.
It lets the Managing Director (MD) prefer fast local reasoning with Ollama for crisp status and next-step requests, while gracefully falling back to heavier reasoning when needed.

The goal is calm performance without fragility:
- Prefer local Ollama when available and ready.
- Warm the preferred local model so responses stay snappy.
- Fall back cleanly to GGC/OAC when local conditions are not ready.
- Never guess on high-adventure or unclear asks.

## Deep Sea Mode Behavior

MD now uses matched routing with a light complexity check:

1. Simple status or next-mission prompts:
- Prefer `OLLAMA_FAST_LOCAL` when local runtime and preferred model are ready.

2. Surgical implementation prompts:
- Route to `OAC_SURGICAL_EXECUTION` for deterministic execution.

3. Deep strategic prompts:
- Route to `HEAVY_LOCAL_OR_GGC` (or `GGC_DEEP_REASONING` fallback) for higher-caliber planning.

4. High-adventure or unclear prompts:
- Route to `PERSONAL_TRAINER_CLARIFY` and ask for a short intent-clarification meeting first.

## Active Preference, Warm-Up, and Fallback

Deep Sea Mode is controlled by lightweight environment toggles:

- `GCODEX_OLLAMA_DEEP_SEA_MODE=auto` (default)
  - Enables local preference when available.
- `GCODEX_OLLAMA_MODEL=llama3.2:3b` (default)
  - Preferred local model for fast synthesis.
- `GCODEX_OLLAMA_WARMUP=1` (default)
  - Attempts a soft warm-up check so first responses stay smooth.

Graceful fallback behavior:
- If `ollama` is missing, slow, or preferred model is not ready, MD falls back to GGC/OAC routing safely.
- No destructive actions are taken during fallback.
- Guidance remains explicit and human-aligned.

## Quick Local Validation

Run this in a bootstrapped repo:

```bash
python3 - <<'PY'
import importlib.util
from pathlib import Path

repo = Path('.')
module_path = repo / 'scripts' / 'brain_server.py'
spec = importlib.util.spec_from_file_location('brain_server_local', module_path)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

status = mod._ollama_runtime_status(force=True)
print('Deep Sea status:', status)

route_simple = mod._assess_complexity_and_route(
    latest_human='How is project health right now?',
    focus='health',
    next_mission='Dispatch one small deterministic slice.',
    ollama_status=status,
)
print('Simple route:', route_simple)
PY
```

## Why This Matters

Deep Sea Mode keeps the organization sovereign and graceful:
- Local when possible.
- Heavy when necessary.
- Clarifying before risky ambiguity.

That is matched intelligence in practice: respectful, high-fidelity reasoning that serves maker delight without dumbing down the mission.

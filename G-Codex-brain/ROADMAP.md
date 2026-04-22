# ROADMAP

Generated: 2026-04-22T09:39:00Z
Truth posture: Repository reality validated locally on 2026-04-22.

## Repo Structure Summary
- Top folders: `examples`, `scripts`, `src`, `tests`, `G-Codex-brain`
- Key root files: `package.json`, `README.md`, `index.html`, `eslint.config.js`
- Runtime profile: browser game UI in `src/game.js` with deterministic core logic in `src/game-core.js`
- Verification profile: `npm run check` (lint + test) passes locally
- VCS reality: `.git` is absent in repo root, so branch/status/commit flows are currently unavailable

## Canonical Workflows (Shipped)
1. Run game locally by opening `index.html` in a browser.
2. Run deterministic checks:
   - `npm run check`
3. Run Control Room and watcher when needed:
   - `./scripts/conductor.sh dashboard`
   - `./scripts/conductor.sh watch start`

## Suggested Milestones
1. Map entrypoints and assign module ownership notes for `src/`, `tests/`, and `scripts/`.
2. Add explicit handling guidance for missing `.git` metadata during handoff preflight.
3. Confirm remote CI execution on the intended default branch once git metadata is restored.
4. Review roadmap and update handoff after each meaningful slice.

## Mermaid
```mermaid
flowchart TB
    R["testerbrain5cards"]
    D1["examples/"]
    D2["scripts/"]
    D3["src/"]
    D4["tests/"]
    RF1["package.json"]
    RF2["README.md"]
    M1["1. Map entrypoints and ownership"]
    M2["2. Handle missing .git preflight explicitly"]
    M3["3. Confirm remote CI branch execution"]
    M4["4. Refresh roadmap/handoff after each slice"]

    R --> D1
    R --> D2
    R --> D3
    R --> D4
    R --> RF1
    R --> RF2
    R --> M1
    M1 --> M2
    M2 --> M3
    M3 --> M4

    click D1 roadmapNodeClick "Open folder: examples/"
    click D2 roadmapNodeClick "Open folder: scripts/"
    click D3 roadmapNodeClick "Open folder: src/"
    click D4 roadmapNodeClick "Open folder: tests/"
    click M1 roadmapNodeClick "Queue mission: Map entrypoints and assign module ownership"
    click M2 roadmapNodeClick "Queue mission: Add missing .git preflight handling guidance"
    click M3 roadmapNodeClick "Queue mission: Confirm remote CI branch execution"
    click M4 roadmapNodeClick "Queue mission: Refresh roadmap and handoff after each slice"
```

## Roadmap Node Actions
- D1 | folder | examples
- D2 | folder | scripts
- D3 | folder | src
- D4 | folder | tests
- M1 | milestone | Map entrypoints and assign module ownership
- M2 | milestone | Add missing .git preflight handling guidance
- M3 | milestone | Confirm remote CI branch execution
- M4 | milestone | Review roadmap and update handoff after each meaningful slice

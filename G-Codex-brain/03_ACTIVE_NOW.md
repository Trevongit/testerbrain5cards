# 03 ACTIVE NOW

## Active State: Reality Alignment Complete

- Repository: testerbrain5cards
- Description: 5 Cards Brain Tester - A memory game for G-Codex testing.
- Current Phase: Bootstrap Reality Alignment
- Status: G-Codex surfaces localized to project reality. Initial commit pushed to GitHub.
- Truth Anchor: `README.md` and `src/game.js`.

## Immediate Next Steps

1.  **Low-risk determinism slice:** Extract pure helpers from `src/game.js` (shuffle + click validation), then add a tiny local Node test script for deterministic logic checks.
2.  **Baseline Testing:** Implement automated tests for the core game logic (shuffle, sequence validation).
3.  **Linting:** Add a basic linter (e.g., ESLint) to maintain code quality.
4.  **CI/CD:** Set up a GitHub Action to run tests and linting on push.
5.  **UX Polish:** Consider adding a level/score counter or a timer.

## Main Entry Points (Current Repo Reality)

- Browser game runtime: `index.html` loading `src/style.css` and `src/game.js`.
- Game behavior source of truth: `src/game.js`.
- Optional G-Codex control runtime: `./scripts/conductor.sh dashboard`.

## Known Structure/Docs Mismatch To Resolve

- `G-Codex-brain/00_INDEX.md` references `../docs/proposals/PHASE_25_SEQUENTIAL_THINKING.md`, but this repository currently has no `docs/` directory.

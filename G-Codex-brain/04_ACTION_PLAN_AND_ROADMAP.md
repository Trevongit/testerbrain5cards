# 04 ACTION PLAN AND ROADMAP

## 1) Completed Foundations
The core game engine is functional and the repository is bootstrapped.

* [x] **Core Logic:** Functional memory game with shuffle and validation in `src/game.js`.
* [x] **Modular Structure:** Separated HTML, CSS, and JS.
* [x] **G-Codex Bootstrap:** Full context overlay and script suite injected.
* [x] **Source Control:** Git initialized and pushed to GitHub.

## 2) Phase 1: Quality & Testing (Active)
Focus on making the codebase robust and verifiable.

* [ ] **Baseline Tests:** Implement Vitest or Jest for game logic.
* [ ] **Linting & Formatting:** Integrate ESLint and Prettier.
* [ ] **CI Integration:** GitHub Actions for automated validation.

## 3) Suggested Next 5 Development Moves

1.  **Vitest Setup:** Add unit tests for the `shuffle` function and sequence matching logic.
2.  **Score Persistence:** Use LocalStorage to save the player's best time or streak.
3.  **Difficulty Levels:** Add options for more cards (e.g., 7 or 9 cards).
4.  **Visual Feedback:** Improve "error" and "success" animations for better user experience.
5.  **Documentation:** Update `AGENTS.md` with specific developer workflows for this game.

## 4) Rules For Future Contributors

1.  **Pure Logic:** Keep DOM manipulation separate from core game logic whenever possible.
2.  **Deterministic Tests:** Ensure the shuffle function can be mocked or tested for predictability.
3.  **Visual Consistency:** Follow the existing CSS variable patterns for colors and timing.
4.  **Brain Sync:** Always update `03_ACTIVE_NOW.md` after completing a milestone.

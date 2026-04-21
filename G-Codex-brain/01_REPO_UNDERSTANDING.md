# 01 REPO UNDERSTANDING

## Technical Summary
*   **Project:** **5 Cards Brain Tester**
*   **Type:** Modular HTML/CSS/JS memory game.
*   **Objective:** Memorize a sequence of 5 cards and click them in the correct numerical order (1-5).
*   **Stack:** 
    *   **Frontend:** Vanilla JavaScript, CSS3 (Flexbox/Grid), HTML5.
    *   **Logic:** Shuffle-based randomization and sequence validation.

## Current State Assessment
*   **Game Engine:** Functional memory game logic in `src/game.js`.
*   **UI/UX:** Responsive card layout with CSS transitions for flipping.
*   **Structure:** Clean separation of concerns between structure (`index.html`), style (`src/style.css`), and logic (`src/game.js`).

## Architecture Layers
1.  **UI Layer:** `index.html` with card containers and control buttons.
2.  **Presentation Layer:** `src/style.css` handling card animations and states (correct, error, flipped).
3.  **Logic Layer:** `src/game.js` managing game state, sequence generation, and user input validation.

# KNOWN RISKS

## Technical Risks
- **Browser Compatibility:** Some advanced CSS animations (3D transforms) may perform differently across browsers.
- **State Management:** As the game grows (e.g., adding levels), simple global variables may lead to race conditions if not refactored into a state manager.
- **Test Coverage:** Currently zero automated tests for the core logic.

## Project Risks
- **Scope Creep:** Adding too many features (leaderboards, multiplayer) before the core game is hardened with tests.
- **Asset Integrity:** Replacing CSS cards with external images may increase load times and break the "static-first" design.

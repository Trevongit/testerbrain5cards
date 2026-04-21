# testerbrain5cards



## 5 Cards Brain Tester

This repository contains a simple modular HTML/CSS/JS game used to test G-Codex agent capabilities.

- **Objective**: Memorize the sequence of 5 cards and click them in order.
- **Testing Surface**: Modular structure (index.html, src/style.css, src/game.js) for auditing multi-file reasoning.

### Run Game

Simply open `index.html` in your browser.



<!-- GCODEX_BOOTSTRAP_START -->
## G-Codex Bootstrap

This repository has been bootstrapped with the full G-Codex template stack.

- Primary entry point: `./scripts/conductor.sh dashboard`
- Ingress helper (for future clone/bootstrap workflows): `./scripts/ingress.sh`
- Clipboard bridge watcher: `./scripts/conductor.sh watch`
- Shared brain directory: `G-Codex-brain/`
- Guiding manifesto: `G-Codex-brain/ENLIGHTENMENT_MANIFESTO.md`
- Browser bridge userscript: `scripts/bridge.user.js`
- Pure repo exit: `./scripts/remove-gcodex.sh`
- For the clipboard bridge: `sudo apt install xclip` (Linux Mint / Ubuntu)

### Local Python Environment

If `.venv/` exists, activate it before running extended Python tooling:

```bash
source .venv/bin/activate
```

### First Run

```bash
./scripts/conductor.sh dashboard
```

This launches the G-Codex Control Room and starts the local brain server.
<!-- GCODEX_BOOTSTRAP_END -->

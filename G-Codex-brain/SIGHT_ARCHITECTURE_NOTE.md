# Sight Architecture & MCP Truth Capture

This note documents the hard-won architectural truth established during the Phase 21-22 Sight/MCP development loop.

## The Reality of `chrome-devtools-mcp`

Through a series of bounded CLI audits, we have established the following:

1.  **Server-Only Mode**: The `chrome-devtools-mcp` tool functions strictly as a long-running MCP server. It does **not** support a one-shot CLI model for browser actions (e.g., it has no `evaluate` or `screenshot` subcommands that run and exit).
2.  **Hanging Behavior**: Attempts to invoke it as a subprocess for discrete actions resulted in "hanging" because the tool was actually starting a new, unlinked server instance and waiting for a client connection.
3.  **Process Exit**: In many configurations, the tool exits with code 0 almost immediately after printing its banner, requiring robust keep-alive logic even for simple presence.
4.  **Operational Boundary**: G-Codex currently supports **Sight Presence Awareness** (detecting the browser on port 9222 and the active MCP server process). While the `chrome-devtools-mcp` tool remains server-only, a direct one-shot screenshot path has been verified.
5.  **Phase 23 Lite (Direct CDP)**: A surgical WebSocket implementation (`scripts/screenshot_helper.py`) enables functional screenshots by bypassing the MCP server layer and communicating directly with the browser's DevTools protocol.

## Future Path: "Real Browser Control"

To achieve the full "Visual Handshake" envisioned in the Blueprint, the next architectural layer must include:

-   **Dedicated MCP Client**: A native G-Codex client (likely in `brain_server.py` or a specialized helper) that connects to the `chrome-devtools-mcp` server as a persistent consumer.
-   **Capability Handshake**: A real-time verification step (e.g., fetching `document.title`) that proves the client-server-browser link is operationally active.
-   **Safe Write Model**: An MD-gated permission model for browser actions beyond simple read-only DOM inspection.

## Summary of Current Capability

-   **Browser Launcher**: Reliable (port 9222 + clean room profile).
-   **Presence Detection**: High-fidelity (identifies browser + MCP processes).
-   **Visual Handshake**: Architecturally aligned. Presence is high-fidelity; one-shot screenshots are functional via Phase 23 Lite direct path.

✦ **Visible Honesty: Aligned with audited CLI behavior.**

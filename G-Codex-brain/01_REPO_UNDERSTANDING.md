# 01 REPO UNDERSTANDING

## Technical Summary
*   **Original Project:** LL3M (cloud-based multi-agent 3D generation).
*   **Pivot:** **MStorm Asset Forge** (Standalone local static prop generator).
*   **Core Engine:** Blender 4.0.2 (Local).
*   **Export Status:** 
    *   **OBJ/MTL:** Verified and functional as the primary baseline.
    *   **GLB/glTF:** **BLOCKED** by system-level `_ctypes` issue in the Python environment used by Blender.

## Current State Assessment
*   **Headless Automation:** Successfully proven via `blender --background --python <script>`.
*   **Format Pivot:** The One-Day MVP now assumes an **OBJ-baseline** packaging strategy.
*   **Environment:** Linux Mint (local), Blender 4.0.2.

## Architecture Layers (MVP)
1.  **Orchestrator:** Simple CLI (upcoming).
2.  **Generator:** Maps requests to `bpy` script strings.
3.  **Bridge:** Executes headless Blender for OBJ/MTL export.
4.  **Packager:** Bundles OBJ, MTL, and `manifest.json` into timestamped folders.

# 04 ACTION PLAN AND ROADMAP

## 1) Completed Foundations (Phases 1–5)
The core engine of the MStorm Asset Forge is complete and hardened.

* [x] **Blender Orchestration:** Headless OBJ/GLB generation pipeline.
* [x] **Validated Packaging:** Artifact integrity gates and PBR manifest writing.
* [x] **Library Core:** Enriched `registry.json` discovery layer.
* [x] **Explorer UX:** Sorting, JSON output, and trait filtering.
* [x] **Material Contract:** Alpha, Emission, and PBR property support.
* [x] **Handoff:** Project sync utility and library pruning.

## 2) Phase 6: Archetypes & Production Scaling (Active)
Current focus is on making the library genuinely usable at scale.

* [x] **Asset Presets v2:** 10+ deterministic recipes implemented.
* [x] **Validation Profiles:** mobile/standard/high_fidelity gates.
* [x] **Registry Enrichment:** Enriched discovery layer with dimensions, materials, and profiles.
* [x] **Guidance & Integration:** (Current) refined documentation for Studio and Agents.

## 3) Suggested Next 5 Development Moves
These are the most impactful technical slices to implement next:

1.  **Rich Explorer UI Refinement:** Add filtering by validation status (OK vs WARN) and specific material traits (e.g., show only emissive).
2.  **Asset Presets v3 (Environment Detail):** Expand the recipe library with more environment-focused props (e.g., `bookshelf_large`, `pillar_round`).
3.  **Validation Profile Hardening:** Add stricter mesh checks (e.g., non-manifold geometry detection) to the `high_fidelity` profile.
4.  **Sync Improvement:** Support "exclude" patterns or "sync-by-tag" logic for more surgical handoffs.
5.  **Launcher Wrapper (Phase 7):** Begin the local-first GUI wrapper concept (docs in Phase 6 Slice 7).

## 4) Rules For Future Contributors And Agents
Follow these rules to maintain the integrity of the forge:

1.  **Repo Truth Pass:** Always verify the current committed hashes and tree state before writing code.
2.  **Surgical Slices:** Prefer narrow, verifiable logical slices over broad speculative rewrites.
3.  **Discovery vs Truth:** Keep `registry.json` lean (discovery) and `manifest.json` detailed (per-asset truth).
4.  **Documentation Handoff:** Update the Brain and `docs/` whenever a slice changes a contract or adds a capability.
5.  **No Speculation:** Do not imply that unbuilt GUI or plugin features exist in production-facing docs.
6.  **Deterministic Priority:** Maintain the stability of the deterministic generation path as the primary feature.

---

## 5) Usability / Integration Follow-Through
Ensure all future integration work (bridges, plugins) respects the **Discovery-First** pattern defined in `docs/mstorm-integration.md`.

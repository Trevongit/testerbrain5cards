# KNOWN RISKS

- **GLB Blocker:** `ModuleNotFoundError: No module named '_ctypes'` in the Blender Python environment blocks glTF/GLB export.
- **OBJ Materiality:** OBJ format does not support advanced PBR materials as natively as GLB; MStorm rendering results may vary.
- **Unit Scale:** Units must be verified for MStorm Studio 2026 (assumed metric/meters for now).
- **Environment Variance:** Differences in Python environments on different machines can affect headless execution.

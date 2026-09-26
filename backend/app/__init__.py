"""CreativeForge backend (Phase 11+).

Real, extensible FastAPI service: API -> Agent Planner -> Tool Router ->
CreativeAsset pipeline -> PostgreSQL persistence.
"""

import os
import sys

# The deterministic character-art renderer is a shared repo-level package
# (`artgen/`), also used by the Studio backend. Make it importable when the
# service is launched from `backend/` (python -m uvicorn app.main:app).
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

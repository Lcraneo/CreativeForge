"""CreativeForge backend entry (Phase 11.12).

    uvicorn app.main:app --reload     # http://127.0.0.1:8000/docs
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.adapters.registry import setup_adapters
from app.api.asset import router as asset_router
from app.api.benchmark import router as benchmark_router
from app.api.collab import router as collab_router
from app.api.dna import router as dna_router
from app.api.knowledge import router as knowledge_router
from app.api.mcp import router as mcp_router
from app.api.models import router as models_router
from app.api.task import router as task_router
from app.core.database import init_models


@asynccontextmanager
async def lifespan(_: FastAPI):
    await init_models()
    setup_adapters()
    yield


app = FastAPI(
    title="CreativeForge API",
    version="0.1.0",
    description="Phase 11-23: agent runtime -> engines -> foundation training -> game creation intelligence",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(asset_router, prefix="/api/v1/assets", tags=["assets"])
app.include_router(task_router, prefix="/api/v1/tasks", tags=["tasks"])
app.include_router(dna_router, prefix="/api/v1/dna", tags=["dna"])
app.include_router(models_router, prefix="/api/v1/models", tags=["models"])
app.include_router(mcp_router, prefix="/api/v1/mcp", tags=["mcp"])
app.include_router(collab_router, prefix="/api/v1/projects", tags=["projects"])
app.include_router(knowledge_router, prefix="/api/v1/knowledge", tags=["knowledge"])
app.include_router(benchmark_router, prefix="/api/v1/benchmark", tags=["benchmark"])


@app.get("/health")
async def health():
    return {"status": "ok"}

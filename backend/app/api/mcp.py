"""MCP Tool Ecosystem (Phase 22.3): machine-readable tools + invocation.

`GET /api/v1/mcp/tools` is the manifest external MCP clients (and the
Planner's capability selector) read:

    pipeline tools   used by the Planner inside the Agent Runtime DAG
    standalone tools invocable through `POST /api/v1/mcp/invoke`:
                     export_cocos / export_unity / export_godot,
                     dna_embed, asset_quality, motion_analyze,
                     train_dna_encoder

New engines or model services register here by adding an `EngineExporter`
or extending the model service — the manifest follows automatically.
"""

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.engines.foundation.training.registry import get_production
from app.engines.gimport.exporter.registry import engine_names
from app.models import Asset
from app.runtime.registry import describe_tools
from app.schemas.mcp import McpInvokeRequest, McpInvokeResponse
from app.services.export_service import run_export
from app.services.model_service import get_model_service

router = APIRouter()

STANDALONE_TOOLS: dict[str, dict[str, Any]] = {
    "export_cocos": {
        "description": "Export an asset to a Cocos Creator resource tree (Phase 15.4)",
        "input": {"asset_id": "str"},
        "output": {"engine": "str", "files": "list"},
    },
    "export_unity": {
        "description": "Export an asset to a Unity project tree (Phase 15.4)",
        "input": {"asset_id": "str"},
        "output": {"engine": "str", "files": "list"},
    },
    "export_godot": {
        "description": "Export an asset to a Godot project tree (Phase 15.4)",
        "input": {"asset_id": "str"},
        "output": {"engine": "str", "files": "list"},
    },
    "dna_embed": {
        "description": "Embed an image into a DNA vector via the production encoder (Phase 20)",
        "input": {"image": "str"},
        "output": {"vector": "list", "model": "str"},
    },
    "asset_quality": {
        "description": "Consistency / game-ready quality scores for an asset (Phase 19)",
        "input": {"asset_id": "str"},
        "output": {"scores": "dict", "game_ready": "float"},
    },
    "motion_analyze": {
        "description": "Per-clip motion semantics from the animation library (Phase 19)",
        "input": {"asset_id": "str"},
        "output": {"clips": "list"},
    },
    "train_dna_encoder": {
        "description": "Run the DNA contrastive training pipeline over the asset library (Phase 20)",
        "input": {"name": "str?"},
        "output": {"report": "dict"},
    },
}


def _manifest() -> list[dict[str, Any]]:
    tools = [
        {**schema, "invocable": False, "used_by": "planner"}
        for schema in describe_tools()
    ]
    tools.extend(
        {**schema, "name": name, "invocable": True, "used_by": "mcp"}
        for name, schema in STANDALONE_TOOLS.items()
    )
    return tools


@router.get("/tools")
async def tools() -> dict[str, Any]:
    return {
        "tools": _manifest(),
        "engines": engine_names(),
    }


@router.post("/invoke", response_model=McpInvokeResponse)
async def invoke(data: McpInvokeRequest, db: AsyncSession = Depends(get_db)):
    tool = data.tool
    if tool not in STANDALONE_TOOLS:
        raise HTTPException(
            status_code=404,
            detail=f"unknown or non-invocable tool: {tool}",
        )
    payload = data.input or {}
    service = get_model_service()

    if tool.startswith("export_"):
        row = await db.get(Asset, payload.get("asset_id") or "")
        if row is None:
            raise HTTPException(status_code=404, detail="asset not found")
        exported, engine_target = await run_export(row, tool.removeprefix("export_"))
        await db.commit()
        resources = exported["engine"]["resources"]
        result: dict[str, Any] = {
            "asset_id": exported["id"],
            "engine": resources["engine"],
            "root": resources["root"],
            "files": sorted(resources["files"]),
            "quality": resources["quality"],
        }
    elif tool == "dna_embed":
        artifact = await get_production(db, "dna_encoder")
        result = await service.embed(payload.get("image") or "", artifact)
    elif tool == "asset_quality":
        row = await db.get(Asset, payload.get("asset_id") or "")
        if row is None:
            raise HTTPException(status_code=404, detail="asset not found")
        result = await service.quality_check(row.metadata_json or {})
        result["asset_id"] = payload.get("asset_id")
    elif tool == "motion_analyze":
        row = await db.get(Asset, payload.get("asset_id") or "")
        if row is None:
            raise HTTPException(status_code=404, detail="asset not found")
        result = await service.motion_analyze(row.metadata_json or {})
        result["asset_id"] = payload.get("asset_id")
    else:  # train_dna_encoder
        report = await service.train(db, name=payload.get("name") or "dna_encoder")
        result = {"report": report}

    return McpInvokeResponse(tool=tool, result=result)

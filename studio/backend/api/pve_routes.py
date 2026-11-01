"""REST API for the isolated PVE enemy forge."""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from studio.backend.pve_service.service import PveEnemyService


class GeneratePveEnemyRequest(BaseModel):
    prompt: str
    role: str = "minion"
    difficulty: str = "normal"


def build_pve_router(service: PveEnemyService) -> APIRouter:
    router = APIRouter(prefix="/api")

    @router.post("/pve/enemies/{enemy_id}/actions/{action}/rebuild", status_code=202)
    def rebuild_enemy_action(enemy_id: str, action: str):
        try:
            return service.rebuild_action(enemy_id, action)
        except KeyError:
            raise HTTPException(status_code=404, detail="unknown enemy")
        except ValueError as error:
            raise HTTPException(status_code=409, detail=str(error))

    @router.get("/pve/enemies")
    def list_pve_enemies():
        return {"enemies": service.store.list()}

    @router.get("/pve/enemies/{enemy_id}")
    def get_pve_enemy(enemy_id: str):
        record = service.store.get(enemy_id)
        if record is None:
            raise HTTPException(status_code=404, detail="unknown enemy")
        return record

    @router.delete("/pve/enemies/{enemy_id}")
    def delete_pve_enemy(enemy_id: str):
        record = service.store.get(enemy_id)
        if record is None:
            raise HTTPException(status_code=404, detail="unknown enemy")
        if record.get("builtin"):
            raise HTTPException(status_code=409, detail="builtin enemies cannot be deleted")
        if record.get("status") in {
            "analyzing",
            "generating_model",
            "generating_actions",
        }:
            raise HTTPException(status_code=409, detail="enemy is still generating")
        if not service.store.delete(enemy_id):
            raise HTTPException(status_code=404, detail="unknown enemy")
        return {"status": "deleted", "removed": enemy_id}

    @router.post("/pve/enemies/generate", status_code=202)
    def generate_pve_enemy(request: GeneratePveEnemyRequest):
        prompt = request.prompt.strip()
        if not prompt:
            raise HTTPException(status_code=422, detail="prompt is required")
        if len(prompt) > 1200:
            raise HTTPException(status_code=422, detail="prompt must be <= 1200 characters")
        if request.role not in ("minion", "boss"):
            raise HTTPException(status_code=422, detail="role must be minion or boss")
        if request.difficulty not in ("easy", "normal", "hard"):
            raise HTTPException(status_code=422, detail="difficulty must be easy/normal/hard")
        return service.start_generation(prompt, request.role, request.difficulty)

    return router

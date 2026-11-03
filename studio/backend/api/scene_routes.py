"""REST API for prompt-driven playable scenes."""

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

from studio.backend.scene_service import SceneService
from studio.backend.scene_service.compiler import DIFFICULTIES


class CreateSceneRequest(BaseModel):
    prompt: str
    gameplay: str = "parkour"
    difficulty: str = "normal"


class UpdatePveSequenceRequest(BaseModel):
    profile_ids: list[str]
    stage_id: str | None = None


def build_scene_router(service: SceneService) -> APIRouter:
    router = APIRouter(prefix="/api")

    @router.post("/scenes", status_code=202)
    def create_scene(request: CreateSceneRequest):
        prompt = request.prompt.strip()
        if not prompt:
            raise HTTPException(status_code=422, detail="prompt is required")
        if len(prompt) > 2000:
            raise HTTPException(status_code=422, detail="prompt must be <= 2000 characters")
        if request.gameplay not in ("parkour", "pve"):
            raise HTTPException(status_code=422, detail="gameplay must be parkour or pve")
        if request.difficulty not in DIFFICULTIES:
            raise HTTPException(status_code=422, detail="difficulty must be easy/normal/hard")
        return service.start(prompt, request.difficulty, request.gameplay)

    @router.get("/scenes")
    def list_scenes(limit: int = 20):
        return {"scenes": service.store.list(max(1, min(limit, 50)))}

    @router.get("/scenes/{scene_id}")
    def get_scene(scene_id: str):
        scene = service.store.get(scene_id)
        if scene is None:
            raise HTTPException(status_code=404, detail="unknown scene")
        return scene

    @router.delete("/scenes/{scene_id}")
    def delete_scene(scene_id: str):
        scene = service.store.get(scene_id)
        if scene is None:
            raise HTTPException(status_code=404, detail="unknown scene")
        if scene.get("status") == "generating":
            raise HTTPException(status_code=409, detail="scene is still generating")
        if not service.store.delete(scene_id):
            raise HTTPException(status_code=404, detail="unknown scene")
        return {"status": "deleted", "removed": scene_id}

    @router.put("/scenes/{scene_id}/pve/enemy-sequence")
    def update_pve_enemy_sequence(scene_id: str, request: UpdatePveSequenceRequest):
        try:
            scene = service.update_pve_enemy_sequence(
                scene_id, request.profile_ids, request.stage_id
            )
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        if scene is None:
            raise HTTPException(status_code=404, detail="unknown scene")
        return scene

    @router.get("/scenes/{scene_id}/background.png")
    def scene_background(scene_id: str):
        from studio.backend import artifact_store

        path = service.store.background_path(scene_id, 0)
        if path is None:
            path = artifact_store.ensure_local("data/scenes/{}_{}.png".format(scene_id, 0)) or (
                artifact_store.ensure_local("data/scenes/{}.png".format(scene_id))
            )
        if path is None:
            raise HTTPException(status_code=404, detail="background not found")
        return FileResponse(
            path,
            media_type="image/png",
            headers={"Cache-Control": "public, max-age=86400"},
        )

    @router.get("/scenes/{scene_id}/backgrounds/{index}.png")
    def sequenced_scene_background(scene_id: str, index: int):
        from studio.backend import artifact_store

        path = service.store.background_path(scene_id, index)
        if path is None and index >= 0:
            path = artifact_store.ensure_local(
                "data/scenes/{}_{}.png".format(scene_id, index)
            )
        if path is None:
            raise HTTPException(status_code=404, detail="background not found")
        return FileResponse(
            path,
            media_type="image/png",
            headers={"Cache-Control": "public, max-age=86400"},
        )

    @router.post("/scenes/{scene_id}/background", status_code=202)
    def retry_scene_background(scene_id: str):
        try:
            scene = service.retry_background(scene_id)
        except RuntimeError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        if scene is None:
            raise HTTPException(status_code=404, detail="unknown scene")
        return {
            "scene_id": scene_id,
            "status": scene["status"],
            "stage": (scene.get("generation") or {}).get("stage"),
        }

    return router

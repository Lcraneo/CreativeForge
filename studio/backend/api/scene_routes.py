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


def build_scene_router(service: SceneService) -> APIRouter:
    router = APIRouter(prefix="/api")

    @router.post("/scenes", status_code=202)
    def create_scene(request: CreateSceneRequest):
        prompt = request.prompt.strip()
        if not prompt:
            raise HTTPException(status_code=422, detail="prompt is required")
        if len(prompt) > 2000:
            raise HTTPException(status_code=422, detail="prompt must be <= 2000 characters")
        if request.gameplay != "parkour":
            raise HTTPException(status_code=422, detail="当前仅支持 parkour")
        if request.difficulty not in DIFFICULTIES:
            raise HTTPException(status_code=422, detail="difficulty must be easy/normal/hard")
        return service.start(prompt, request.difficulty)

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
        if not service.store.delete(scene_id):
            raise HTTPException(status_code=404, detail="unknown scene")
        return {"status": "deleted", "removed": scene_id}

    @router.get("/scenes/{scene_id}/background.png")
    def scene_background(scene_id: str):
        path = service.store.background_path(scene_id, 0)
        if path is None:
            raise HTTPException(status_code=404, detail="background not found")
        return FileResponse(
            path,
            media_type="image/png",
            headers={"Cache-Control": "public, max-age=86400"},
        )

    @router.get("/scenes/{scene_id}/backgrounds/{index}.png")
    def sequenced_scene_background(scene_id: str, index: int):
        path = service.store.background_path(scene_id, index)
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

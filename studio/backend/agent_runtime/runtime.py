"""Agent Runtime: drives the Multi-Agent Supervisor in background threads
and streams its lifecycle events into the TaskStore for WebSocket fans.

Every finished task is also written to the persistent HistoryStore so past
generations (prompt + character + asset snapshot) survive restarts.

When a third-party image API is configured (and enabled), the runtime asks it
for the character artwork first; any failure transparently falls back to the
built-in deterministic pipeline (``MODEL_FALLBACK`` event).
"""

import threading
import time

from agent.generation.external import build_image_prompt
from agent.generation.spec import apply_overrides, parse_prompt
from agents.supervisor.supervisor import SupervisorAgent
from studio.backend.asset_service.service import AssetStore, TaskStore
from studio.backend.history_service.service import DEFAULT_HISTORY_PATH, HistoryStore
from studio.backend.model_service.service import (
    ChatProvider,
    ImageProvider,
    ModelSettingsStore,
)


class AgentRuntime:
    """POST /api/tasks -> runtime.start_task(goal) -> live event stream."""

    def __init__(self, supervisor=None, history=None, model_settings=None):
        self.tasks = TaskStore()
        self.assets = AssetStore()
        self.history = history or HistoryStore(DEFAULT_HISTORY_PATH)
        self.model_settings = model_settings or ModelSettingsStore()
        self._supervisor = supervisor or SupervisorAgent()

    def start_task(self, goal, overrides=None):
        task_id = self.tasks.create(goal)
        thread = threading.Thread(
            target=self._run,
            args=(task_id, goal, overrides),
            name="creativeforge-task-{}".format(task_id),
            daemon=True
        )
        thread.start()
        return task_id

    def _run(self, task_id, goal, overrides=None):
        started = time.time()
        enhanced, image = self._call_external(task_id, goal, overrides)

        def on_event(event):
            self.tasks.append_event(task_id, event)

        try:
            result = self._supervisor.run(goal, on_event=on_event, overrides=overrides)
        except Exception as error:  # keep the task visible on failure
            self.tasks.fail(task_id, error)
            self._record(task_id, goal, None, error, started)
            return

        asset = result.get("asset")
        if asset and (enhanced or image):
            if enhanced:
                asset["prompt_enhance"] = enhanced
            if image:
                asset["image"] = image
            self.tasks.append_event(task_id, {
                "type": "ASSET_UPDATE",
                "id": asset.get("id"),
                "name": asset.get("name"),
                "engine": asset.get("engine", {}).get("target"),
                "image": (image or {}).get("url"),
            })

        self.tasks.finish(task_id, result)
        if asset:
            self.assets.save(asset)
        self._record(task_id, goal, result, None, started)

    def _call_external(self, task_id, goal, overrides):
        """Runs the configured model API: chat prompt enhancement first, then
        optional image generation. Every failure degrades gracefully."""
        settings = self.model_settings.effective()
        if not (settings.get("enabled") and settings.get("base_url") and settings.get("api_key")):
            return None, None

        enhanced = None
        if settings.get("use_chat") and settings.get("chat_model"):
            self.tasks.append_event(task_id, {
                "type": "MODEL_START",
                "stage": "enhance",
                "provider": settings.get("provider"),
                "model": settings.get("chat_model"),
            })
            try:
                spec = apply_overrides(parse_prompt(goal), overrides)
                enhanced = ChatProvider(settings).enhance(goal, spec, overrides)
                self.tasks.append_event(task_id, {
                    "type": "MODEL_ENHANCE",
                    "model": enhanced.get("model"),
                    "prompt": enhanced.get("prompt"),
                })
            except Exception as error:
                self.tasks.append_event(task_id, {
                    "type": "MODEL_FALLBACK",
                    "stage": "enhance",
                    "detail": str(error),
                })
                enhanced = None

        image = None
        if settings.get("use_image") and settings.get("model"):
            self.tasks.append_event(task_id, {
                "type": "MODEL_START",
                "stage": "image",
                "provider": settings.get("provider"),
                "model": settings.get("model"),
            })
            try:
                prompt = build_image_prompt(
                    goal, overrides, enhanced.get("prompt") if enhanced else None
                )
                image = ImageProvider(settings).generate(prompt)
                self.tasks.append_event(task_id, {
                    "type": "MODEL_IMAGE",
                    "id": image.get("file"),
                    "url": image.get("url"),
                    "model": image.get("model"),
                })
            except Exception as error:
                self.tasks.append_event(task_id, {
                    "type": "MODEL_FALLBACK",
                    "stage": "image",
                    "detail": str(error),
                })
                image = None

        return enhanced, image

    def _record(self, task_id, goal, result, error, started):
        """Appends one history record (prompt + character + asset snapshot)."""
        asset = (result or {}).get("asset") if result else None
        character = (asset or {}).get("character") or {}
        report = ((asset or {}).get("quality") or {}).get("report") or {}
        engine = ((asset or {}).get("engine") or {}).get("target")
        supervisor = (result or {}).get("supervisor") or {}
        palette = ((asset or {}).get("pixel") or {}).get("palette") or {}
        animation = (asset or {}).get("animation") or {}
        task = self.tasks.get(task_id) or {}

        status = "failed" if error is not None else str(supervisor.get("status", "unknown")).lower()

        self.history.add({
            "task_id": task_id,
            "created_at": task.get("created_at", started),
            "finished_at": time.time(),
            "goal": goal,
            "engine": engine,
            "status": status,
            "report_status": report.get("status"),
            "error": str(error) if error is not None else None,
            "asset_id": (asset or {}).get("id"),
            "name": (asset or {}).get("name"),
            "type": (asset or {}).get("type"),
            "role": (asset or {}).get("role"),
            "action": animation.get("action"),
            "frames": None if character.get("static") else (len(animation.get("frames") or []) or None),
            "fps": animation.get("fps"),
            "scores": report.get("scores") or {},
            "qa_rounds": supervisor.get("qa_rounds", 0),
            "elapsed_seconds": round(time.time() - started, 3),
            "character": character,
            "palette": palette.get("colors") or [],
            "image": (asset or {}).get("image"),
            "enhanced_prompt": ((asset or {}).get("prompt_enhance") or {}).get("prompt"),
            "asset": asset,
        })

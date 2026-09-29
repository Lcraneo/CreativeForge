"""Agent Runtime: drives the Multi-Agent Supervisor in background threads
and streams its lifecycle events into the TaskStore for WebSocket fans.

Every finished task is also written to the persistent HistoryStore so past
generations (prompt + character + asset snapshot) survive restarts.

When a third-party image API is configured (and enabled), the runtime asks it
for the character artwork first; any failure transparently falls back to the
built-in deterministic pipeline (``MODEL_FALLBACK`` event).
"""

import random
import threading
import time
import uuid

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
        self.batches = {}

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

    # -- batch production line (P1-B) --------------------------------------

    def start_batch(self, goal, count=4, mode="seed", overrides=None):
        """批量生成：一个后台线程串行跑 count 个任务（避免并发打爆图像
        API 限流），每个任务通过 overrides 注入不同 seed（多变体）或不同
        action（多姿势）。批次状态聚合在 self.batches 供前端轮询。"""

        count = max(2, min(12, int(count)))
        mode = "pose" if mode == "pose" else "seed"
        batch_id = uuid.uuid4().hex[:8]
        self.batches[batch_id] = {
            "id": batch_id,
            "goal": goal,
            "count": count,
            "mode": mode,
            "status": "running",
            "created_at": time.time(),
            "tasks": [],
        }
        thread = threading.Thread(
            target=self._run_batch,
            args=(batch_id, goal, count, mode, overrides),
            name="creativeforge-batch-{}".format(batch_id),
            daemon=True,
        )
        thread.start()
        return batch_id

    def _run_batch(self, batch_id, goal, count, mode, overrides):
        batch = self.batches.get(batch_id) or {}
        actions = ["idle", "walk", "run", "attack", "jump"]
        base_seed = random.randint(10**8, 10**9 - 1)
        for index in range(count):
            task_overrides = dict(overrides or {})
            if mode == "seed":
                task_overrides["seed"] = (base_seed + index * 7919) % (10**9)
            else:
                task_overrides["action"] = actions[index % len(actions)]
            task_id = self.tasks.create(goal)
            entry = {
                "task_id": task_id,
                "index": index + 1,
                "overrides": {
                    key: task_overrides.get(key)
                    for key in ("seed", "action")
                    if task_overrides.get(key)
                },
            }
            batch.setdefault("tasks", []).append(entry)
            try:
                self._run(task_id, goal, task_overrides)
                task = self.tasks.get(task_id) or {}
                result = task.get("result") or {}
                asset = result.get("asset") or {}
                entry["asset_id"] = asset.get("id")
                entry["name"] = asset.get("name")
                entry["status"] = task.get("status", "done")
                entry["image_url"] = (asset.get("image") or {}).get("url")
                entry["scores"] = ((asset.get("quality") or {}).get("report") or {}).get("scores") or {}
            except Exception as error:  # noqa: BLE001 - one failure must not kill the batch
                entry["status"] = "failed"
                entry["error"] = str(error)
        batch["status"] = "done"

    def batch_snapshot(self, batch_id):
        batch = self.batches.get(batch_id)
        if not batch:
            return None
        view = dict(batch)
        view["tasks"] = [
            dict(entry, status=entry.get("status") or (
                (self.tasks.get(entry.get("task_id")) or {}).get("status") or "running"
            ))
            for entry in batch.get("tasks", [])
        ]
        return view

    def _run(self, task_id, goal, overrides=None):
        started = time.time()
        spec = apply_overrides(parse_prompt(goal), overrides)
        enhanced, image = self._call_external(task_id, goal, overrides, spec)

        if image:
            # hand the AI artwork to the pipeline: PReCon reconstructs from it
            from studio.backend.model_service.service import safe_generated_path

            local = safe_generated_path(image.get("file"))
            if local:
                image["path"] = local
                try:
                    from PIL import Image

                    with Image.open(local) as handle:
                        image["width"], image["height"] = handle.size
                except Exception:
                    pass
            overrides = dict(overrides or {})
            overrides["_model_image"] = image

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

        if asset:
            self._generate_design_views(task_id, asset)

        self.tasks.finish(task_id, result)
        if asset:
            self.assets.save(asset)
        self._record(task_id, goal, result, None, started)

    def _call_external(self, task_id, goal, overrides, spec=None):
        """Runs the configured model API: chat prompt enhancement first, then
        optional image generation. Every failure degrades gracefully."""
        spec = spec or {}
        settings = self.model_settings.effective()
        if not (settings.get("enabled") and settings.get("base_url") and settings.get("api_key")):
            if settings.get("enabled"):
                # switch is on but the configuration is incomplete — surface why
                self.tasks.append_event(task_id, {
                    "type": "MODEL_FALLBACK",
                    "stage": "configure",
                    "detail": "自定义模型未配置完整：需要 Base URL 与 API Key（设置 → 模型设置）",
                })
            return None, None

        # 提示词增强改为「用户手动触发」：对话框上的「增强提示词」按钮会调用
        # POST /api/prompt/enhance，用户在发送前自行确认增强后的提示词。
        # 因此这里不再自动增强，直接把用户当前文本作为生成提示词。
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
                    goal, overrides, enhanced.get("prompt") if enhanced else None,
                    style=spec.get("style"),
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

    def _generate_design_views(self, task_id, asset):
        """Auto AI turnaround: derives side/back views from the fresh artwork
        (qwen-image-edit with a self-check + wanx fallback), so an enabled
        custom model never leaves the design center on deterministic
        placeholder views. Best-effort: failures keep the placeholders and
        surface as MODEL_FALLBACK."""

        try:
            image = asset.get("image") or {}
            base_url = image.get("url")
            settings = self.model_settings.effective()
            if not base_url or not settings.get("enabled") or not settings.get("api_key"):
                return

            from studio.backend.model_service.service import (
                ImageEditProvider,
                generate_turnaround,
            )

            self.tasks.append_event(task_id, {
                "type": "MODEL_START",
                "stage": "views",
                "provider": settings.get("provider"),
                "model": ImageEditProvider.EDIT_MODEL,
            })

            def on_result(view, result):
                self.tasks.append_event(task_id, {
                    "type": "MODEL_IMAGE",
                    "stage": "views",
                    "view": view,
                    "id": result.get("file"),
                    "url": result.get("url"),
                    "model": result.get("model"),
                })

            deadline = time.time() + 180.0
            views, failures = generate_turnaround(
                settings, base_url, front_image=image,
                deadline=deadline, on_result=on_result,
            )

            if failures:
                self.tasks.append_event(task_id, {
                    "type": "MODEL_FALLBACK",
                    "stage": "views",
                    "detail": "侧/背视图生成失败（{}），对应视角保留确定性示意；可在设计中心重试".format(
                        "；".join(failures)
                    ),
                })

            asset["design_views"] = views
            self.tasks.append_event(task_id, {
                "type": "ASSET_UPDATE",
                "id": asset.get("id"),
                "name": asset.get("name"),
                "engine": asset.get("engine", {}).get("target"),
                "image": base_url,
            })
        except Exception as error:  # views are best-effort, never fail the task
            self.tasks.append_event(task_id, {
                "type": "MODEL_FALLBACK",
                "stage": "views",
                "detail": str(error),
            })

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

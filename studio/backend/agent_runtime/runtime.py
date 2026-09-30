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

    def start_task(self, goal, overrides=None, turbo=False, asset=None):
        task_id = self.tasks.create(goal)
        thread = threading.Thread(
            target=self._run,
            args=(task_id, goal, overrides, turbo, asset),
            name="creativeforge-task-{}".format(task_id),
            daemon=True,
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
        """批量执行：有界并发（默认 3 工位）——吞吐约为串行的 3 倍，同时
        不打爆图像 API 限流；结果按提交顺序写回，前端展示顺序稳定。"""

        from concurrent.futures import ThreadPoolExecutor

        batch = self.batches.get(batch_id) or {}
        actions = ["idle", "walk", "run", "attack", "jump"]
        base_seed = random.randint(10**8, 10**9 - 1)

        jobs = []
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
            jobs.append((task_id, task_overrides, entry))

        def execute(job):
            task_id, task_overrides, entry = job
            try:
                self._run(task_id, goal, task_overrides)
                task = self.tasks.get(task_id) or {}
                result = task.get("result") or {}
                asset = result.get("asset") or {}
                entry["asset_id"] = asset.get("id")
                entry["name"] = asset.get("name")
                entry["status"] = task.get("status", "done")
                entry["image_url"] = (asset.get("image") or {}).get("url")
                entry["scores"] = ((asset.get("quality") or {}).get("report") or {}).get(
                    "scores"
                ) or {}
            except Exception as error:  # noqa: BLE001 - one failure must not kill the batch
                entry["status"] = "failed"
                entry["error"] = str(error)

        workers = min(3, max(1, count))
        with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="cf-batch") as pool:
            list(pool.map(execute, jobs))
        batch["status"] = "done"

    def batch_snapshot(self, batch_id):
        batch = self.batches.get(batch_id)
        if not batch:
            return None
        view = dict(batch)
        view["tasks"] = [
            dict(
                entry,
                status=entry.get("status")
                or ((self.tasks.get(entry.get("task_id")) or {}).get("status") or "running"),
            )
            for entry in batch.get("tasks", [])
        ]
        return view

    def _run(self, task_id, goal, overrides=None, turbo=False, asset=None):
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

        # 三视图 worker 与主管线并行：视图生成（约 20-60s）不再串行压在
        # 管线之后；极速档（turbo）直接跳过以压缩等待时间
        views_thread, views_getter = (None, None)
        if image and not turbo:
            views_thread, views_getter = self._start_views_worker(task_id, image)

        def on_event(event):
            self.tasks.append_event(task_id, event)

        try:
            result = self._supervisor.run(goal, asset=asset, on_event=on_event, overrides=overrides)
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
            self.tasks.append_event(
                task_id,
                {
                    "type": "ASSET_UPDATE",
                    "id": asset.get("id"),
                    "name": asset.get("name"),
                    "engine": asset.get("engine", {}).get("target"),
                    "image": (image or {}).get("url"),
                },
            )

        if asset and views_thread is not None:
            views, failures = views_getter()
            if views:
                asset["design_views"] = views
            if failures:
                self.tasks.append_event(
                    task_id,
                    {
                        "type": "MODEL_FALLBACK",
                        "stage": "views",
                        "detail": "侧/背视图生成失败（{}），对应视角保留确定性示意；可在设计中心重试".format(
                            "；".join(failures)
                        ),
                    },
                )
            if views or failures:
                self.tasks.append_event(
                    task_id,
                    {
                        "type": "ASSET_UPDATE",
                        "id": asset.get("id"),
                        "name": asset.get("name"),
                        "engine": asset.get("engine", {}).get("target"),
                        "image": (image or {}).get("url"),
                    },
                )

        self.tasks.finish(task_id, result)
        if asset:
            self.assets.save(asset)
        self._record(task_id, goal, result, None, started)

    def _start_views_worker(self, task_id, image):
        """在后台线程预生成三视图（与主管线并行）。返回 (thread, getter)，
        getter() 阻塞至 worker 结束并返回 (views|None, failures|None)。"""

        settings = self.model_settings.effective()
        base_url = (image or {}).get("url")
        if not base_url or not settings.get("enabled") or not settings.get("api_key"):
            return None, (lambda: (None, None))

        from studio.backend.model_service.service import (
            ImageEditProvider,
            generate_turnaround,
        )

        self.tasks.append_event(
            task_id,
            {
                "type": "MODEL_START",
                "stage": "views",
                "provider": settings.get("provider"),
                "model": ImageEditProvider.EDIT_MODEL,
            },
        )

        def on_result(view, result):
            self.tasks.append_event(
                task_id,
                {
                    "type": "MODEL_IMAGE",
                    "stage": "views",
                    "view": view,
                    "id": result.get("file"),
                    "url": result.get("url"),
                    "model": result.get("model"),
                },
            )

        outcome = {}

        def worker():
            try:
                views, failures = generate_turnaround(
                    settings,
                    base_url,
                    front_image=image,
                    deadline=time.time() + 180.0,
                    on_result=on_result,
                )
                outcome["views"] = views
                outcome["failures"] = failures
            except Exception as error:  # noqa: BLE001 - views are best-effort
                outcome["views"] = None
                outcome["failures"] = [str(error)]

        thread = threading.Thread(
            target=worker,
            name="creativeforge-views-{}".format(task_id),
            daemon=True,
        )
        thread.start()

        def getter():
            thread.join(timeout=200.0)
            if thread.is_alive():
                return None, ["视图生成超时，已跳过"]
            if "views" not in outcome:
                return None, ["视图生成异常"]
            return outcome.get("views"), outcome.get("failures")

        return thread, getter

    def _call_external(self, task_id, goal, overrides, spec=None):
        """Runs the configured model API: chat prompt enhancement first, then
        optional image generation. Every failure degrades gracefully."""
        spec = spec or {}
        settings = self.model_settings.effective()
        if not (settings.get("enabled") and settings.get("base_url") and settings.get("api_key")):
            if settings.get("enabled"):
                # switch is on but the configuration is incomplete — surface why
                self.tasks.append_event(
                    task_id,
                    {
                        "type": "MODEL_FALLBACK",
                        "stage": "configure",
                        "detail": "自定义模型未配置完整：需要 Base URL 与 API Key（设置 → 模型设置）",
                    },
                )
            return None, None

        # 提示词增强改为「用户手动触发」：对话框上的「增强提示词」按钮会调用
        # POST /api/prompt/enhance，用户在发送前自行确认增强后的提示词。
        # 因此这里不再自动增强，直接把用户当前文本作为生成提示词。
        enhanced = None

        image = None
        if settings.get("use_image") and settings.get("model"):
            self.tasks.append_event(
                task_id,
                {
                    "type": "MODEL_START",
                    "stage": "image",
                    "provider": settings.get("provider"),
                    "model": settings.get("model"),
                },
            )
            try:
                prompt = build_image_prompt(
                    goal,
                    overrides,
                    enhanced.get("prompt") if enhanced else None,
                    style=spec.get("style"),
                )
                image = ImageProvider(settings).generate(prompt)
                self.tasks.append_event(
                    task_id,
                    {
                        "type": "MODEL_IMAGE",
                        "id": image.get("file"),
                        "url": image.get("url"),
                        "model": image.get("model"),
                    },
                )
            except Exception as error:
                self.tasks.append_event(
                    task_id,
                    {
                        "type": "MODEL_FALLBACK",
                        "stage": "image",
                        "detail": str(error),
                    },
                )
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

        self.history.add(
            {
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
                "frames": (
                    None
                    if character.get("static")
                    else (len(animation.get("frames") or []) or None)
                ),
                "fps": animation.get("fps"),
                "scores": report.get("scores") or {},
                "qa_rounds": supervisor.get("qa_rounds", 0),
                "elapsed_seconds": round(time.time() - started, 3),
                "character": character,
                "palette": palette.get("colors") or [],
                "image": (asset or {}).get("image"),
                "enhanced_prompt": ((asset or {}).get("prompt_enhance") or {}).get("prompt"),
                "asset": asset,
            }
        )

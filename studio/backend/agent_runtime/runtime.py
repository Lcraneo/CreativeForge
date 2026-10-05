"""Agent Runtime: drives the Multi-Agent Supervisor in background threads
and streams its lifecycle events into the TaskStore for WebSocket fans.

Every finished task is also written to the persistent HistoryStore so past
generations (prompt + character + asset snapshot) survive restarts.

When a third-party image API is configured (and enabled), the runtime asks it
for the character artwork first; any failure transparently falls back to the
built-in deterministic pipeline (``MODEL_FALLBACK`` event).
"""

import logging
import random
import threading
import time
import uuid

from agent.generation.external import build_image_prompt
from agent.generation.spec import apply_overrides, parse_prompt
from agents.supervisor.supervisor import SupervisorAgent

logger = logging.getLogger("creativeforge.agent_runtime")
if not logger.handlers:
    # uvicorn 默认日志配置不接管自定义 logger（INFO 会被 lastResort 吞掉），
    # 自带 handler 保证 IP 改写/降级决策/失败原因完整落 stdout 日志
    _handler = logging.StreamHandler()
    _handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s :: %(message)s"))
    logger.addHandler(_handler)
    logger.setLevel(logging.INFO)
    logger.propagate = False
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
        enhanced, image, image_error = self._call_external(task_id, goal, overrides, spec)

        # 生图失败策略（image_fallback_policy）：
        #   strict（默认）——自救轮（IP 预替换 + 审核安全改写）之后仍失败，
        #     任务立即失败并返回「原因 + 已尝试动作 + 下一步建议」，绝不静默
        #     产出与主题无关的离线示意；
        #   degrade——仅在用户于「模型设置」显式开启自动降级时，才继续离线
        #     管线（产物带 model_fallback 标记，前端三处徽章可见）。
        if image_error:
            policy = self.model_settings.effective().get("image_fallback_policy") or "strict"
            logger.warning(
                "image generation failed task=%s kind=%s detail=%s policy=%s goal=%r",
                task_id,
                image_error.get("kind"),
                image_error.get("detail"),
                policy,
                goal,
            )
            if policy != "degrade":
                from studio.backend.model_service.service import image_failure_guidance

                message = image_failure_guidance(image_error)
                error = RuntimeError(message)
                self.tasks.fail(task_id, error)
                self._record(task_id, goal, None, error, started, image_error)
                return

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
        if asset and image_error:
            # A 失败透明化：生图失败原因随资产落库，前端据此刻
            # 「AI 生图失败，已用离线示意替代」徽章（含一键重试）
            asset["model_fallback"] = image_error

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

        # 先落库再发事件（P0 修复）：此前 ASSET_UPDATE 先于 assets.save 发出，
        # 前端收到事件立即 GET /api/assets/{id} 会 404（"unknown asset"），
        # 表现为"生成请求失败"。任何 ASSET_UPDATE 发出前，资产必须已在
        # AssetStore 中可取。
        if asset:
            self.assets.save(asset)
        if asset and (enhanced or image):
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
        self._record(task_id, goal, result, None, started, image_error)

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
        """Runs the configured model API: optional image generation. Every
        failure degrades gracefully — and the REASON travels with the task
        (event stream + return value) instead of being swallowed, so the
        product can show「AI 生图失败，已用离线示意替代」instead of silently
        shipping an unrelated seeded sprite."""
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
            return None, None, None

        # 提示词增强改为「用户手动触发」：对话框上的「增强提示词」按钮会调用
        # POST /api/prompt/enhance，用户在发送前自行确认增强后的提示词。
        # 因此这里不再自动增强，直接把用户当前文本作为生成提示词。
        enhanced = None

        image = None
        image_error = None
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
                # D 主动 IP 中性化：现代版权角色名（哆啦A梦/皮卡丘等）平台基本
                # 必拦，送模型前直接替换为视觉特征——不浪费一轮拦截，主题不丢。
                # 古典人物（孙悟空等）保留原文，审核拦截后由安全改写轮兜底。
                from studio.backend.model_service.service import neutralize_hard_ip

                neutralized = neutralize_hard_ip(prompt)
                if neutralized != prompt:
                    prompt = neutralized
                    logger.info(
                        "image prompt pre-translated (hard IP) task=%s prompt=%r",
                        task_id,
                        prompt,
                    )
                    self.tasks.append_event(
                        task_id,
                        {
                            "type": "MODEL_FALLBACK",
                            "stage": "image",
                            "kind": "ip-pretranslated",
                            "detail": "提示词含知名 IP 角色名，已预先替换为视觉特征描述（避免内容审核拦截）",
                            "prompt_used": prompt,
                        },
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
                if image.get("softened"):
                    # 审核拦截后的安全改写轮成功——告知用户提示词被改写过，
                    # 改写结果可在事件流追溯（prompt_used）
                    logger.info(
                        "image prompt soften retry succeeded task=%s prompt=%r",
                        task_id,
                        image.get("prompt_used"),
                    )
                    self.tasks.append_event(
                        task_id,
                        {
                            "type": "MODEL_FALLBACK",
                            "stage": "image",
                            "kind": "moderation-softened",
                            "detail": "原始提示词触发内容审核，已自动中性化改写后生成成功",
                            "prompt_used": image.get("prompt_used"),
                        },
                    )
            except Exception as error:
                from studio.backend.model_service.service import classify_error, describe_error

                image_error = {
                    "kind": classify_error(error),
                    "detail": describe_error(error),
                }
                logger.warning(
                    "image generation error task=%s kind=%s raw=%s",
                    task_id,
                    image_error["kind"],
                    str(error)[:200],
                )
                self.tasks.append_event(
                    task_id,
                    {
                        "type": "MODEL_FALLBACK",
                        "stage": "image",
                        "kind": image_error["kind"],
                        "detail": image_error["detail"],
                    },
                )
                image = None

        return enhanced, image, image_error

    def _record(self, task_id, goal, result, error, started, image_error=None):
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
                "model_image_error": image_error,
                "asset": asset,
            }
        )

"""Agent Runtime: drives the Multi-Agent Supervisor in background threads
and streams its lifecycle events into the TaskStore for WebSocket fans.

Every finished task is also written to the persistent HistoryStore so past
generations (prompt + character + asset snapshot) survive restarts.

When a third-party image API is configured (and enabled), the runtime asks it
for the character artwork first; any failure transparently falls back to the
built-in deterministic pipeline (``MODEL_FALLBACK`` event).
"""

import logging
import threading
import time

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

                error = RuntimeError(image_failure_guidance(image_error))
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

        # 角色生成只负责原画；三视图改为用户在设计中心手动触发
        # （POST /api/design/views），任务不再等待 side/back，也不写 design_views。

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

        if isinstance(asset, dict):
            # 重新生成的角色原画已更新，旧三视图与新原画不匹配，随本次任务
            # 失效；新三视图只能由用户在设计中心手动点击生成。
            asset.pop("design_views", None)

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
        self.tasks.finish(task_id, result)
        self._record(task_id, goal, result, None, started, image_error)

    def _call_external(self, task_id, goal, overrides, spec=None):
        """Runs the configured model API: optional image generation. Every
        failure degrades gracefully — and the REASON travels with the task
        (event stream + return value) instead of being swallowed, so the
        product can show「AI 生图失败，已用离线示意替代」instead of silently
        shipping an unrelated seeded sprite."""
        spec = spec or {}
        settings = self.model_settings.effective()
        configured = bool(
            settings.get("enabled") and settings.get("base_url") and settings.get("api_key")
        )
        if not configured:
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
        self._persist_history_now()

    def _persist_history_now(self) -> None:
        """资产入库后立即把 history.json 推进对象存储。

        后台增量扫描是 8s 一轮，容器若在这个窗口内重启（Render 自动
        部署/休眠唤醒），刚生成的资产快照还没上传就会永久丢失——前端
        动作补生成会因此拿到 404 unknown asset。这里同步上传（单文件
        一次 PUT，几十 KB），失败仍由后台 worker 下一轮兜底。"""
        try:
            from studio.backend import artifact_store

            if not artifact_store.configured():
                return
            artifact_store.upload_file(self.history.path)
        except Exception:  # noqa: BLE001 - 上传失败不影响任务交付
            pass

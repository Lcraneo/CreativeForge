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

from agent.generation.external import build_image_prompt, build_reference_image_prompt
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

    def start_task(self, goal, overrides=None, turbo=False, asset=None, reference_image=None):
        task_id = self.tasks.create(goal)
        thread = threading.Thread(
            target=self._run,
            args=(task_id, goal, overrides, turbo, asset, reference_image),
            name="creativeforge-task-{}".format(task_id),
            daemon=True,
        )
        thread.start()
        return task_id

    def _run(self, task_id, goal, overrides=None, turbo=False, asset=None, reference_image=None):
        started = time.time()
        spec = apply_overrides(parse_prompt(goal), overrides)
        enhanced, image, image_error = self._call_external(
            task_id, goal, overrides, spec, reference_image=reference_image
        )

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
            if policy != "degrade" or image_error.get("kind") == "reference-model-missing":
                from studio.backend.model_service.service import image_failure_guidance

                message = (
                    image_error.get("detail") or "已上传人物正面图，但图片模型不可用"
                    if image_error.get("kind") == "reference-model-missing"
                    else image_failure_guidance(image_error)
                )
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

        views_event = None
        if isinstance(asset, dict):
            if reference_image:
                # 用户上传的正面图与角色绑定持久化，后续流程/编辑页仍可取用。
                # 即使生图降级失败也必须保留原图，否则无法重试。
                asset["reference_image"] = reference_image
            if reference_image and isinstance(image, dict):
                # 参考图驱动的角色在生成阶段直接产出三视图；失败只记录原因，
                # 原画与原始正面图都保留，用户可在设计中心重试。
                views_event = self._design_views(task_id, asset, image)
            else:
                # 纯文本流程：重新生成的角色原画已更新，旧三视图与新原画不匹配，
                # 随本次任务失效；新三视图只能由用户在设计中心手动点击生成。
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
        if views_event:
            status, payload = views_event
            if status == "views":
                self.tasks.append_event(
                    task_id, {"type": "MODEL_VIEWS", "design_views": payload}
                )
            else:
                self.tasks.append_event(
                    task_id,
                    {
                        "type": "MODEL_FALLBACK",
                        "stage": "views",
                        "kind": payload.get("kind"),
                        "detail": payload.get("detail"),
                    },
                )
        self.tasks.finish(task_id, result)
        self._record(task_id, goal, result, None, started, image_error)

    def _design_views(self, task_id, asset, image):
        """Derive side / back views from the reference-driven front artwork.

        Returns ``("views", views)`` on success or ``("failed", failure)`` when
        the turnaround model fails. The caller still saves the asset, so a
        failure never loses the original artwork or the uploaded photo.
        """

        from studio.backend.model_service.service import (
            TURNAROUND_EDIT_MODEL,
            classify_error,
            describe_error,
            generate_turnaround,
        )

        self.tasks.append_event(
            task_id,
            {
                "type": "MODEL_START",
                "stage": "views",
                "model": TURNAROUND_EDIT_MODEL,
                "detail": "正在基于正面图生成侧面与背面",
            },
        )
        try:
            views, _failures = generate_turnaround(
                self.model_settings.effective(),
                image.get("url"),
                front_image=image,
                deadline=time.time() + 240.0,
            )
        except Exception as error:  # noqa: BLE001 - 失败原因随资产持久化
            failure = {"kind": classify_error(error), "detail": describe_error(error)}
            asset["design_views_error"] = failure
            logger.warning(
                "design views failed task=%s kind=%s detail=%s",
                task_id,
                failure["kind"],
                failure["detail"],
            )
            return "failed", failure

        asset["design_views"] = views
        asset.pop("design_views_error", None)
        return "views", views

    def _call_external(self, task_id, goal, overrides, spec=None, reference_image=None):
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
        can_generate = bool(settings.get("use_image") and settings.get("model"))
        if reference_image and not (configured and can_generate):
            # 上传了正面图却不能用模型 → 绝不静默退回纯文本，否则参考图没被
            # 实际使用，与用户预期不符。
            detail = (
                "已上传人物正面图，但图片模型未启用或配置不完整："
                "请在「模型设置」启用并填写 Base URL、API Key 与图像模型后重试"
            )
            self.tasks.append_event(
                task_id,
                {
                    "type": "MODEL_FALLBACK",
                    "stage": "reference",
                    "kind": "reference-model-missing",
                    "detail": detail,
                },
            )
            return None, None, {"kind": "reference-model-missing", "detail": detail}
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
                if reference_image:
                    # 正面图是身份唯一来源：锁定身份后再拼现有构图/风格约束。
                    prompt = build_reference_image_prompt(
                        goal,
                        overrides,
                        enhanced.get("prompt") if enhanced else None,
                        style=spec.get("style"),
                    )
                else:
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
                if reference_image:
                    from studio.backend.model_service.service import generate_from_reference

                    image = generate_from_reference(
                        settings,
                        reference_image.get("url"),
                        prompt,
                        deadline=time.time() + 240.0,
                    )
                else:
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

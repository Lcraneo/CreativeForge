"""Animation service (Studio): source image -> style-consistent animation.

Bridges the workbench asset/upload to the shared ``artgen`` animation pipeline
(style analysis + character extraction + pose frames + consistency check +
GIF/sheet encoding) and persists the artefacts for the console to display.
"""

import base64
import io
import json
import os
import time
import uuid
from typing import Any

from artgen import ACTIONS, STYLE_LABELS, create_animation
from artgen.character2d import asset_params
from artgen.gif import decode_image
from artgen.style import analyze_rgba, dominant_palette, extract_character

# 构图约束（借鉴 Windup _framing.py：代码统一追加、只写正向句——该类接口没有
# negative_prompt，否定句里的名词会被 latch 进画面）
FRAMING_CLAUSE = (
    "Preserve the reference character's exact face, hairstyle, clothing, accessories, "
    "color palette, linework, silhouette, textures, and local details throughout every frame. "
    "Use a locked camera with unchanged projection, framing, character scale, and canvas "
    "occupancy throughout the video. Exactly one character is in the frame, and the whole "
    "body from head to feet stays inside the frame at all times."
)

# 动作提示词（i2v 模板）：**视角无关**——旧版硬编码 "seen from the side"，
# 而用户原画多为正面站姿，模型被迫把角色扭成侧面，是肢体缺失的主要诱因之一。
# 现在要求保持输入图的朝向不变，只描述肢体动作本身。
MOTION_PROMPTS = {
    "walk": (
        "The character walks in place, keeping exactly the same facing direction, "
        "viewpoint and pose orientation as the input image: the legs alternate lifting "
        "and stepping naturally, the arms swing gently in counter-phase, the hips and "
        "torso sway subtly with each step, the upper body stays upright and calm, "
        "the character's design, outfit, colors and proportions stay exactly the same "
        "as the input image, the camera stays locked, the motion loops seamlessly."
    ),
    "run": (
        "The character runs in place, keeping exactly the same facing direction and "
        "viewpoint as the input image: quick energetic strides, the arms pumping in "
        "counter-phase, hair and clothes bouncing with the motion, "
        "the character's design, outfit, colors and proportions stay exactly the same "
        "as the input image, the camera stays locked, the motion loops seamlessly."
    ),
    "attack": (
        "The character performs one single committed attack in place, keeping exactly "
        "the same facing direction and viewpoint as the input image: a brief coil back, "
        "then a decisive strike with the leading arm extending naturally, then settle "
        "back into the original stance, "
        "the character's design, outfit, colors and proportions stay exactly the same "
        "as the input image, the camera stays locked."
    ),
    "jump": (
        "The character jumps straight up in place, keeping exactly the same facing "
        "direction and viewpoint as the input image: a small crouch, a vertical hop "
        "with the legs tucking slightly, then landing back into the starting stance, "
        "the character's design, outfit, colors and proportions stay exactly the same "
        "as the input image, the camera stays locked."
    ),
    "idle": (
        "The character breathes gently in place, keeping exactly the same facing "
        "direction and viewpoint as the input image: the torso slowly rises and falls, "
        "subtle head and shoulder movement, everything else stays still, "
        "the character's design, outfit, colors and proportions stay exactly the same "
        "as the input image, the camera stays locked, the motion loops seamlessly."
    ),
}


# AI 主体分割指令：背景替换为纯白（白底可被经典洪泛可靠分离）。
# 实测"移除背景放置角色"的表述会让编辑模型丢细节（肩甲/脚部），
# "背景替换纯白 + 明确列出不得缺失的部位"能保住全部装备细节。
SEGMENT_PROMPT = (
    "把这张图中角色周围的全部背景替换为纯白色(#FFFFFF)。角色本体保持完全原样："
    "包括所有装备、护甲、武器、脚部、尾巴、饰物等每一个细节，不缺失、不变色、"
    "不位移、不缩放。只允许背景像素变成纯白。"
)

# 动作描述 AI 增强的系统提示：只润色、不改动作身份，输出英文 i2v 提示词。
MOTION_ENHANCE_SYSTEM = (
    "You are a game animation director writing prompts for an image-to-video (i2v) model. "
    "Rewrite the given motion description into ONE richer English paragraph (<=90 words). "
    "Preserve exactly: the action's identity (a walk stays walking, an attack stays ONE "
    "committed attack), in-place motion, the character keeping the input image's facing "
    "direction, a locked camera, and the character's design/outfit/colors unchanged. "
    "Enrich with plausible secondary motion implied by the character context "
    "(e.g. armor plates shifting, cloth and hair settling, weapon weight affecting "
    "posture and rhythm) plus pacing, weight shift and easing details. "
    "Never introduce new characters, camera moves, scene changes, violence or blood. "
    "Output only the prompt text — no markdown, no explanation."
)

# 润色结果持久缓存：同一（模型/动作/上下文/模板）命中同一润色输出。
# 这不是省钱——是保正确：最终提示词参与视频缓存 key，若每次润色结果都
# 不同，视频缓存将永远无法命中，重跑同一动作会重复烧视频额度。
_MOTION_PROMPT_CACHE_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "data",
    "motion_prompt_cache.json",
)
_motion_prompt_cache: dict = {}


def _load_motion_prompt_cache() -> None:
    global _motion_prompt_cache
    try:
        with open(_MOTION_PROMPT_CACHE_PATH, "r", encoding="utf-8") as handle:
            data = json.load(handle)
        _motion_prompt_cache = data if isinstance(data, dict) else {}
    except (ValueError, OSError):
        _motion_prompt_cache = {}


def _save_motion_prompt_cache() -> None:
    try:
        os.makedirs(os.path.dirname(_MOTION_PROMPT_CACHE_PATH), exist_ok=True)
        with open(_MOTION_PROMPT_CACHE_PATH, "w", encoding="utf-8") as handle:
            json.dump(_motion_prompt_cache, handle, ensure_ascii=False)
    except OSError:
        pass


_load_motion_prompt_cache()


def ai_enhance_motion_prompt(settings, action, base_prompt, context=None):
    """对话模型润色动作描述（video_ai_enhance，默认开）。

    未配置 / 开关关闭 / 任何失败：一律原样返回 base_prompt（绝不中断生成）。
    成功结果持久缓存，保证同一动作重复生成拿到同一润色文本。
    FRAMING_CLAUSE 等代码级约束由调用方另行追加，不交给模型发挥。"""

    if not isinstance(settings, dict) or not settings.get("video_ai_enhance", True):
        return base_prompt
    if not (
        settings.get("enabled")
        and settings.get("api_key")
        and settings.get("use_chat", True)
        and (settings.get("chat_model") or settings.get("model"))
    ):
        return base_prompt

    import hashlib as _hashlib

    cache_key = _hashlib.sha1(
        "|".join(
            [
                settings.get("chat_model") or settings.get("model") or "",
                str(action),
                str(context or ""),
                base_prompt,
            ]
        ).encode("utf-8")
    ).hexdigest()[:20]
    cached = _motion_prompt_cache.get(cache_key)
    if isinstance(cached, str) and cached:
        return cached

    user = "Action type: {}\nBase motion description:\n{}\n{}Rewrite it into one richer English i2v motion prompt now.".format(
        action,
        base_prompt,
        (
            "Character context (outfit/gear/identity hints only): {}\n".format(
                str(context)[:160]
            )
            if context
            else ""
        ),
    )
    try:
        from studio.backend.model_service.service import ChatProvider

        result = ChatProvider(settings).chat(MOTION_ENHANCE_SYSTEM, user, temperature=0.5)
        enhanced = " ".join((result.get("content") or "").split())
        # 产出质量门：过短/过长/疑似模型解释文本一律弃用
        if not (40 <= len(enhanced) <= 900) or enhanced.count("```"):
            return base_prompt
    except Exception:  # noqa: BLE001 - 润色是增益项，失败绝不阻塞
        return base_prompt

    _motion_prompt_cache[cache_key] = enhanced
    _save_motion_prompt_cache()
    return enhanced

MIN_SEGMENT_COVERAGE = 0.02  # mask 面积下限（低于此说明分割失败/人物丢失）
MAX_SEGMENT_COVERAGE = 0.85  # mask 面积上限（高于此说明背景没抠掉）


# 批次状态模块级共享：路由处理函数每次请求构造 AnimationService 实例，
# 批次状态若挂在实例上会跨请求丢失（轮询永远 404）。
_ACTION_BATCHES: dict[str, dict] = {}


def _generate_video_cached(settings, prompt, source_bytes, timeout_seconds=420.0):
    """视频驱动生成的稳定入口（自动走 mp4 缓存）。"""

    from studio.backend.model_service.service import generate_video

    return generate_video(settings, prompt, source_bytes, timeout_seconds=timeout_seconds)


class VideoGenerationError(RuntimeError):
    """带分类的视频生成失败（kind: quota/auth/moderation/network/fatal）。"""

    def __init__(self, message: str, kind: str = "fatal"):
        super().__init__(message)
        self.kind = kind


def generate_video_with_policy(settings, prompt, source_bytes, timeout_seconds=420.0):
    """视频驱动生成入口：mp4 缓存 + 网络类失败自动退避重试 + 错误分类。

    成功返回 ``(video_bytes, model)``；最终失败抛 VideoGenerationError，
    message 为面向用户的中文描述，kind 供批次徽章/前端提示分类展示。
    审核拦截与 Key 池切换由 generate_video 内部处理（安全改写重试轮）。"""

    from studio.backend.model_service.service import (
        classify_error,
        describe_error,
        generate_video,
    )

    last_exc = None
    for attempt in range(2):
        try:
            return generate_video(
                settings, prompt, source_bytes, timeout_seconds=timeout_seconds
            )
        except Exception as exc:  # noqa: BLE001 - 分类后决定重试或上抛
            last_exc = exc
            if classify_error(exc) == "network" and attempt == 0:
                time.sleep(3.0)
                continue
            break
    raise VideoGenerationError(describe_error(last_exc), classify_error(last_exc)) from last_exc


class AnimationService:
    def __init__(self, directory: str):
        self.directory = directory
        os.makedirs(self.directory, exist_ok=True)
        self.action_batches = _ACTION_BATCHES

    # -- 一键补齐全套动作（串行队列，跳过已生成） --------------------------

    def existing_ai_actions(self, asset_id: str | None) -> set:
        """该资产已生成过 AI 动画的动作集合（扫描动画 meta）。"""

        import glob as _glob

        done = set()
        if not asset_id:
            return done
        for meta_path in _glob.glob(os.path.join(self.directory, "*.json")):
            try:
                with open(meta_path, "r", encoding="utf-8") as handle:
                    meta = json.load(handle)
            except (ValueError, OSError):
                continue
            if meta.get("asset_id") != asset_id:
                continue
            if len(meta.get("frame_urls") or []) >= 2:
                action = meta.get("requested_action") or meta.get("action")
                if action:
                    done.add(action)
        return done

    def start_action_batch(
        self,
        asset_id: str,
        source_bytes: bytes,
        settings: dict[str, Any],
        actions: list[str] | None = None,
        enhance_context: str | None = None,
    ) -> str:
        """为资产串行补齐缺失动作的 AI 动画（视频驱动）。已生成的动作自动
        跳过；批次状态存内存供前端轮询。``enhance_context`` 传给动作描述
        AI 增强（角色名/简介上下文）。"""

        import threading
        import uuid as _uuid

        wanted = [a for a in (actions or ["idle", "walk", "run", "attack", "jump"]) if a in ACTIONS]
        done = self.existing_ai_actions(asset_id)
        pending = [a for a in wanted if a not in done]

        batch_id = _uuid.uuid4().hex[:8]
        self.action_batches[batch_id] = {
            "id": batch_id,
            "asset_id": asset_id,
            "status": "running" if pending else "done",
            "total": len(pending),
            "created_at": time.time(),
            "tasks": [
                {"action": a, "status": "skipped", "note": "已有 AI 动画"}
                for a in wanted
                if a not in pending
            ] + [
                {"action": a, "status": "pending"}
                for a in pending
            ],
        }
        if pending:
            thread = threading.Thread(
                target=self._run_action_batch,
                args=(batch_id, asset_id, source_bytes, settings, pending, enhance_context),
                name="cf-action-batch-{}".format(batch_id),
                daemon=True,
            )
            thread.start()
        return batch_id

    def _run_action_batch(self, batch_id, asset_id, source_bytes, settings, pending, enhance_context=None):
        import random as _random

        batch = self.action_batches.get(batch_id) or {}
        for action in pending:
            entry = next((t for t in batch.get("tasks", []) if t.get("action") == action), None)
            if entry:
                entry["status"] = "generating"
            try:
                base_prompt = MOTION_PROMPTS.get(action, MOTION_PROMPTS["walk"])
                enhanced_prompt = ai_enhance_motion_prompt(
                    settings, action, base_prompt, context=enhance_context
                )
                prompt = enhanced_prompt + " " + FRAMING_CLAUSE
                video_bytes, video_model = generate_video_with_policy(
                    settings, prompt, source_bytes, timeout_seconds=420.0
                )
                frames_rgba = self._slice_video(video_bytes, source_bytes, 12, 1.0, 384, min_count=20)
                from artgen import compose_animation

                result = compose_animation(frames_rgba=frames_rgba, fps=12, size=384)
                animation_id = _uuid.uuid4().hex[:12]
                meta = self._persist(result, animation_id, "video")
                meta["video_model"] = video_model
                meta["asset_id"] = asset_id
                meta["requested_action"] = action
                if enhanced_prompt != base_prompt:
                    meta["prompt_enhanced"] = True
                    meta["motion_prompt"] = prompt[:400]
                self._write(f"{animation_id}.json", json.dumps(meta, ensure_ascii=False).encode("utf-8"))
                if entry:
                    entry["status"] = "done"
                    entry["animation_id"] = animation_id
            except VideoGenerationError as error:
                # 分类失败：审核拦截/额度不足/Key 无效…前端按 error_kind 出徽章
                if entry:
                    entry["status"] = "failed"
                    entry["error"] = str(error)[:160]
                    entry["error_kind"] = error.kind
            except Exception as error:  # noqa: BLE001 - 单动作失败不拖垮批次
                if entry:
                    entry["status"] = "failed"
                    entry["error"] = str(error)[:160]
        batch["status"] = "done"

    def action_batch_snapshot(self, batch_id: str) -> dict | None:
        batch = self.action_batches.get(batch_id)
        return dict(batch) if batch else None

    # -- public API -----------------------------------------------------

    def animations_for_asset(self, asset_id: str | None) -> list[dict]:
        """该资产关联的全部动画 meta（骨骼/序列帧/视频驱动），新→旧排序。

        资产包导出与队列中心都按「资产 + meta」收集产物。"""

        import glob as _glob

        metas: list[dict] = []
        if not asset_id:
            return metas
        for meta_path in _glob.glob(os.path.join(self.directory, "*.json")):
            try:
                with open(meta_path, "r", encoding="utf-8") as handle:
                    meta = json.load(handle)
            except (ValueError, OSError):
                continue
            if meta.get("asset_id") != asset_id:
                continue
            meta["_meta_file"] = os.path.basename(meta_path)
            metas.append(meta)
        metas.sort(key=lambda m: m.get("created_at", 0), reverse=True)
        return metas

    def create(
        self,
        asset: dict[str, Any] | None = None,
        image_bytes: bytes | None = None,
        action: str = "walk",
        fps: int = 12,
        duration: float = 1.0,
        size: int = 512,
        consistency_floor: float = 0.6,
        skeletal: bool = False,
        view: str = "front",
        pose_config: dict[str, Any] | None = None,
        model_settings: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        action = action if action in ACTIONS else "walk"

        params = None
        source_bytes = None
        source_kind = "builtin"

        if skeletal:
            # 全身骨骼模式：绑定「当前角色的真实源图」做角色专属骨骼动画。
            # 没有真实源图时直接报错，绝不回退到固定模板角色（修复"任何角色
            # 都生成同一个橙色角色"的根因）。
            source_kind = "skeletal"
            params = (
                asset_params(asset)
                if asset is not None
                else {"palette": None, "seed": f"{action}-{fps}"}
            )
            if image_bytes:
                source_bytes = image_bytes
            elif asset is not None:
                source_bytes = self._asset_render(asset)
                if source_bytes is None:
                    from artgen import render_asset_view

                    source_bytes = render_asset_view(asset, "front", max(384, min(1024, int(size))))
            if source_bytes is None:
                raise ValueError("骨骼动画需要真实角色源图（资产原画或上传图片），当前没有可用源图")
        elif image_bytes:
            source_kind = "upload"
            source_bytes = image_bytes
        elif asset is not None:
            source_kind = "asset"
            params = asset_params(asset)
            source_bytes = self._asset_render(asset)
            if source_bytes is None:
                # 无 AI 原画/本地文件（如重启后的历史资产）：退回资产正面立绘
                # （与前端展示的 /api/assets/{id}/image.png 同一渲染），保证关键帧
                # 从资产图本身派生，而不是落到程序化像素小人
                try:
                    from artgen import render_asset_view

                    source_bytes = render_asset_view(asset, "front", max(384, min(1024, int(size))))
                except Exception:
                    source_bytes = None

        # 原图驱动的主体分离：AI 原画是复杂场景背景，经典洪泛抠图会把背景
        # 连同人一起判定为主体（整图一起动）。启用自定义模型时先用
        # qwen-image-edit 把角色抠到纯白底再分离；失败回退经典洪泛。
        segment_mask = None
        if source_bytes is not None:
            settings = model_settings or {}
            if settings.get("enabled") and settings.get("api_key"):
                segment_mask = ai_segment_subject(
                    source_bytes, size, settings, deadline=time.time() + 150.0
                )

        result = create_animation(
            params=params,
            action=action,
            fps=fps,
            duration=duration,
            size=size,
            reference=source_bytes,
            source_bytes=source_bytes,
            consistency_floor=consistency_floor,
            view=view,
            pose_config=pose_config,
            segment_mask=segment_mask,
            rigged=(source_kind == "skeletal"),
        )

        animation_id = uuid.uuid4().hex[:12]
        meta = self._persist(result, animation_id, source_kind)
        meta["skeletal"] = source_kind == "skeletal"
        # 记录归属资产（资产包导出/队列中心按 asset_id 收集动画）。
        # _persist 内部已写盘，追加字段后必须重写一次，否则磁盘上没有。
        if asset is not None and asset.get("id"):
            meta["asset_id"] = asset.get("id")
            self._write(
                f"{animation_id}.json", json.dumps(meta, ensure_ascii=False).encode("utf-8")
            )
        if result.get("rig"):
            from artgen.rig import rig_summary

            meta["rig"] = rig_summary(result["rig"])
        if result.get("falign"):
            meta["falign"] = result["falign"]
        if segment_mask is not None:
            meta["subject_segmentation"] = "ai"
        return meta

    def create_sequence(
        self,
        frames: list[bytes],
        fps: int = 12,
        size: int = 384,
        consistency_floor: float = 0.6,
    ) -> dict[str, Any]:
        """Compose an animation from user-imported sequence frames (标准序列帧
        工作流): frames are fitted to a shared canvas and packed as-is into a
        looping GIF — no re-drawing, no pose synthesis, imported order kept."""
        from artgen import compose_animation

        result = compose_animation(
            frame_bytes=frames,
            fps=fps,
            size=size,
            consistency_floor=consistency_floor,
        )
        animation_id = uuid.uuid4().hex[:12]
        return self._persist(result, animation_id, "sequence")

    def _persist(
        self, result: dict[str, Any], animation_id: str, source_kind: str
    ) -> dict[str, Any]:
        gif_name = f"{animation_id}.gif"
        sheet_name = f"{animation_id}_sheet.png"
        thumb_name = f"{animation_id}_thumb.png"
        self._write(gif_name, result["gif"])
        self._write(sheet_name, result["sheet"])
        self._write(thumb_name, result["frames"][0])
        # 每一帧单独落盘，交付完整的图像序列
        frame_urls = []
        for index, png in enumerate(result["frames"]):
            name = f"{animation_id}_f{index:02d}.png"
            self._write(name, png)
            frame_urls.append(f"/api/animation/{name}")

        meta = {
            "id": animation_id,
            "source": source_kind,
            "action": result["action"],
            "fps": result["fps"],
            "duration": result["duration"],
            "frame_count": result["frame_count"],
            "size": result["size"],
            "loop": result["loop"],
            "style": result["style"],
            "style_label": STYLE_LABELS.get(result["style"]["style"], result["style"]["style"]),
            "character": result["character"],
            "consistency": result["consistency"],
            "per_frame": result["per_frame"],
            "sheet_size": result["sheet_size"],
            "frames": len(result["frames"]),
            "frame_urls": frame_urls,
            "urls": {
                "gif": f"/api/animation/{gif_name}",
                "sheet": f"/api/animation/{sheet_name}",
                "thumb": f"/api/animation/{thumb_name}",
            },
            "created_at": time.time(),
        }
        self._write(f"{animation_id}.json", json.dumps(meta, ensure_ascii=False).encode("utf-8"))
        return meta

    # -- helpers --------------------------------------------------------

    def create_video(
        self,
        source_bytes: bytes,
        settings: dict[str, Any],
        action: str = "walk",
        fps: int = 12,
        duration: float = 1.0,
        size: int = 384,
        asset_id: str | None = None,
        enhance_context: str | None = None,
    ) -> dict[str, Any]:
        """Windup 式 AI 视频驱动：源图（自动裁白边）+ 动作提示词 → 图生视频
        → 均匀抽帧 →（仅 idle）弱背景稳定 → 序列合成。失败抛
        VideoGenerationError（带分类与中文描述），路由原样透传给前端。

        ``enhance_context``：角色名/简介等上下文，供动作描述 AI 增强参考
        （video_ai_enhance 开启时）。"""

        action = action if action in ACTIONS else "walk"

        # 送 i2v 前自动裁掉白边/留白：主体占比从 ~60% 提到 ~90%，
        # 对齐官方 demo 的输入形态（主体小+平面白底会显著拉低 i2v 质量）
        work_bytes = source_bytes
        crop_info = None
        try:
            work_bytes, crop_info = self._crop_to_subject(source_bytes, settings)
        except Exception:  # noqa: BLE001 - crop is best-effort
            work_bytes = source_bytes

        # 动作描述 AI 增强（可配置，失败回退原模板）；代码级构图约束
        # FRAMING_CLAUSE 始终由代码追加，不交给模型发挥
        base_prompt = MOTION_PROMPTS.get(action, MOTION_PROMPTS["walk"])
        enhanced_prompt = ai_enhance_motion_prompt(
            settings, action, base_prompt, context=enhance_context
        )
        prompt = enhanced_prompt + " " + FRAMING_CLAUSE
        video_bytes, video_model = generate_video_with_policy(
            settings, prompt, work_bytes, timeout_seconds=420.0
        )
        frames_rgba = self._slice_video(
            video_bytes, source_bytes, fps, duration, size, min_count=20
        )

        # 弱背景稳定（仅 idle）：i2v 背景会随生成轻微漂移。用 AI 分割 mask
        # 的**大幅膨胀区**之外贴回第 0 帧背景——只锁远处背景，绝不裁切肢体
        # （旧实现用静立 mask 硬抠角色，肢体一动就被切掉 → "少胳膊"）。
        # 步态/攻击/跳跃的肢体位移大，一律不做合成，保肢体完整优先。
        subject_locked = False
        if action == "idle" and len(frames_rgba) >= 2:
            try:
                mask = ai_segment_subject(work_bytes, size, settings, deadline=time.time() + 150.0)
            except Exception:  # noqa: BLE001
                mask = None
            if mask is not None:
                try:
                    frames_rgba = self._stabilize_background(frames_rgba, mask, size)
                    subject_locked = True
                except Exception:  # noqa: BLE001
                    subject_locked = False

        from artgen import compose_animation

        result = compose_animation(frames_rgba=frames_rgba, fps=fps, size=size)
        animation_id = uuid.uuid4().hex[:12]
        meta = self._persist(result, animation_id, "video")
        meta["video_model"] = video_model
        # 记录归属资产与真实动作（compose 会把 action 覆盖为 "sequence"），
        # 试玩舞台按「资产 + 动作」匹配 AI 动画帧。
        # 注意：_persist 内部已写盘，此处追加字段后必须重写一次，否则丢失。
        if asset_id:
            meta["asset_id"] = asset_id
        meta["requested_action"] = action
        if enhanced_prompt != base_prompt:
            meta["prompt_enhanced"] = True
            meta["motion_prompt"] = prompt[:400]
        self._write(f"{animation_id}.json", json.dumps(meta, ensure_ascii=False).encode("utf-8"))
        if crop_info:
            meta["source_cropped"] = crop_info
        if subject_locked:
            meta["subject_locked"] = True
        return meta

    def _crop_to_subject(self, source_bytes: bytes, settings: dict[str, Any]):
        """自动裁掉源图四周的留白/白边，让主体占满画面再送 i2v。
        分割不可用时回退洪泛 mask；再失败返回原图。"""

        import io

        from PIL import Image

        from artgen.sourceanim import _subject_mask

        original = Image.open(io.BytesIO(source_bytes)).convert("RGB")
        mask = ai_segment_subject(source_bytes, 384, settings, deadline=time.time() + 90.0)
        if mask is None:
            fitted = original.resize((384, 384))
            mask, _, _ = _subject_mask(fitted)
        bbox = mask.getbbox()
        if not bbox:
            return source_bytes, None

        # bbox 映射回原图坐标 + 6% 余量
        fw, fh = original.size
        x0 = max(0, int(bbox[0] / 384 * fw) - int(fw * 0.03))
        y0 = max(0, int(bbox[1] / 384 * fh) - int(fh * 0.03))
        x1 = min(fw, int(bbox[2] / 384 * fw) + int(fw * 0.03))
        y1 = min(fh, int(bbox[3] / 384 * fh) + int(fh * 0.03))
        if (x1 - x0) < fw * 0.3 or (y1 - y0) < fh * 0.3:
            return source_bytes, None  # 裁得太狠说明 mask 不可信，放弃
        cropped = original.crop((x0, y0, x1, y1))

        buffer = io.BytesIO()
        cropped.save(buffer, "PNG")
        info = {"box": [x0, y0, x1, y1], "original": [fw, fh]}
        return buffer.getvalue(), info

    @staticmethod
    def _stabilize_background(frames_rgba, mask, size):
        """弱背景稳定：把「第 0 帧挖掉角色后的背景」贴回每帧的**mask 膨胀区
        之外**——远处背景锁定为静止，角色及其近邻区域保持原视频帧，
        肢体无论如何运动都不会被裁切。"""

        from PIL import Image, ImageFilter

        images = [Image.frombytes("RGBA", (w, h), bytes(data)) for w, h, data in frames_rgba]
        # 大幅膨胀（31px）+ 羽化：角色 ±40px 内的一切原样保留
        zone = mask.filter(ImageFilter.MaxFilter(31)).filter(ImageFilter.GaussianBlur(6))
        outside = zone.point(lambda v: 255 - v)

        first = images[0]
        static_bg = first.copy()
        rgb = first.convert("RGB")
        step = max(1, first.width // 64)
        samples = [rgb.getpixel((x, 0)) for x in range(0, first.width, step)]
        samples += [rgb.getpixel((x, first.height - 1)) for x in range(0, first.width, step)]
        bg = tuple(sorted(c[i] for c in samples)[len(samples) // 2] for i in range(3))
        # 第 0 帧挖掉角色（膨胀区）补底色 → 得到"无人的静态背景"
        hole = mask.filter(ImageFilter.MaxFilter(15))
        static_bg.paste(
            Image.new("RGBA", first.size, (bg[0], bg[1], bg[2], 255)),
            (0, 0),
            hole,
        )

        stabilized = []
        for frame in images:
            canvas = frame.copy()
            # 膨胀区之外 → 贴回第 0 帧的静态背景（背景漂移归零）
            canvas.paste(static_bg, (0, 0), outside)
            stabilized.append((size, size, bytearray(canvas.tobytes())))
        return stabilized

    def _slice_video(
        self,
        video_bytes: bytes,
        source_bytes: bytes,
        fps: int,
        duration: float,
        size: int,
        min_count: int | None = None,
    ):
        """mp4 bytes -> evenly sampled, stabilized (w,h,RGBA) frames.

        流式解码：逐帧读取、即时缩略、只保留采样目标帧——避免旧实现把
        全部帧解码进内存（161 帧 960×960 ≈ 425MB）的内存峰值。"""

        import imageio.v2 as imageio
        from PIL import Image

        from artgen.sourceanim import _fit

        tmp = os.path.join(self.directory, "tmp_{}.mp4".format(uuid.uuid4().hex[:8]))
        with open(tmp, "wb") as handle:
            handle.write(video_bytes)
        try:
            reader = imageio.get_reader(tmp)
            try:
                total = int(reader.count_frames())
            except Exception:  # noqa: BLE001 - metadata unavailable
                total = 0
            count = max(2, min(60, round(fps * duration)))
            if min_count:
                # i2v 的 5 秒视频压到 12 帧会丢掉大部分动作信息；至少抽
                # min_count 帧让动作周期完整、播放更顺滑
                count = max(count, min(int(min_count), 60))

            if total >= 4:
                lo = max(1, int(total * 0.02))
                hi = total - max(1, int(total * 0.04))
                if hi - lo < 4:
                    lo, hi = 0, total - 1
                wanted = {round(lo + (hi - lo) * i / max(1, count - 1)) for i in range(count)}
            else:
                wanted = None  # 元数据缺失：逐帧保留后本地重采样

            def small(gray_prev, frame):
                small = Image.fromarray(frame).resize((48, 48)).convert("L")
                data = list(small.getdata())
                if gray_prev is None:
                    return 0.0, data
                diff = sum(abs(a - b) for a, b in zip(gray_prev, data)) / len(data)
                return diff, data

            # 流式扫描：在线帧差定位动作起点（开头是静态原图），即时缩略落盘
            kept: dict[int, Image.Image] = {}
            consecutive: list[float] = []
            gray_prev = None
            index = 0
            for frame in reader:
                diff, gray_prev = small(gray_prev, frame)
                if index > 0:
                    consecutive.append(diff)
                if wanted is None or index in wanted:
                    canvas = _fit(Image.fromarray(frame), max(64, min(1024, int(size))))
                    kept[index] = canvas
                index += 1
            reader.close()
        finally:
            try:
                os.remove(tmp)
            except OSError:
                pass

        total = max(total, index)
        if index < 4:
            raise RuntimeError("生成的视频过短，无法抽帧")

        start = 0
        for offset, diff in enumerate(consecutive):
            if diff > 3.0 and offset + 1 < len(consecutive) and consecutive[offset + 1] > 3.0:
                start = offset + 1
                break

        if wanted is not None:
            indices = sorted(kept.keys())[:count]
        else:
            lo = min(start + max(1, int(total * 0.02)), max(0, total - 4))
            hi = total - max(1, int(total * 0.04))
            if hi - lo < 4:
                lo, hi = 0, total - 1
            indices = sorted(
                set(round(lo + (hi - lo) * i / max(1, count - 1)) for i in range(count))
            )[:count]

        frames_rgba = []
        for frame_index in indices:
            canvas = kept.get(frame_index)
            if canvas is None:
                continue
            frames_rgba.append((canvas.width, canvas.height, bytearray(canvas.tobytes())))
        if len(frames_rgba) < 2:
            raise RuntimeError("生成的视频有效帧不足，无法抽帧")

        # 循环接缝优化：GIF 首尾相接，把相邻帧差最大的那一对切到循环边界，
        # 循环回跳感最小。O(n) 的 48×48 灰度差，代价可忽略。
        if len(frames_rgba) > 2:
            from PIL import Image as PILImage

            def gray_small(item):
                return (
                    PILImage.frombytes("RGBA", (item[0], item[1]), bytes(item[2]))
                    .convert("L")
                    .resize((48, 48))
                )

            def pair_diff(a, b):
                da, db = list(gray_small(a).getdata()), list(gray_small(b).getdata())
                return sum(abs(x - y) for x, y in zip(da, db)) / len(da)

            pairs = [
                pair_diff(frames_rgba[i], frames_rgba[(i + 1) % len(frames_rgba)])
                for i in range(len(frames_rgba))
            ]
            cut = pairs.index(max(pairs)) + 1
            if 0 < cut < len(frames_rgba):
                frames_rgba = frames_rgba[cut:] + frames_rgba[:cut]
        return frames_rgba

    def _asset_render(self, asset: dict[str, Any]):
        """Local source image bytes for the asset (generated dir / AI 原画), or None."""
        from studio.backend.model_service.service import GENERATED_DIR

        base = GENERATED_DIR
        candidates: list[str] = []
        metas = [asset.get("image")]
        source = asset.get("source")
        if isinstance(source, dict):
            metas.append(source.get("ai_image"))
        for meta in metas:
            if not isinstance(meta, dict):
                continue
            if meta.get("path"):
                candidates.append(str(meta["path"]))
            if meta.get("file"):
                candidates.append(os.path.join(base, os.path.basename(str(meta["file"]))))
            if meta.get("url"):
                candidates.append(str(meta["url"]))
        content = asset.get("content") or {}
        if isinstance(content, dict) and content.get("image_render"):
            candidates.append(os.path.join(base, os.path.basename(str(content["image_render"]))))

        remote = None
        for candidate in candidates:
            if candidate.startswith(("http://", "https://")):
                remote = remote or candidate
                continue
            # "/api/generated/<name>" 形式的本地 URL → generated 目录
            name = os.path.basename(candidate.split("?")[0])
            for path in (candidate, os.path.join(base, name)):
                if name and path and os.path.isfile(path):
                    with open(path, "rb") as handle:
                        return handle.read()
        if remote:
            # 远端 AI 原画仅存 URL：先按文件名找本地缓存，未命中再拉取
            name = os.path.basename(remote.split("?")[0])
            local = os.path.join(base, name)
            if name and os.path.isfile(local):
                with open(local, "rb") as handle:
                    return handle.read()
            try:
                import urllib.request

                with urllib.request.urlopen(remote, timeout=20) as response:
                    return response.read()
            except Exception:
                return None
        return None

    def _write(self, name: str, payload: bytes) -> None:
        with open(os.path.join(self.directory, name), "wb") as handle:
            handle.write(payload)

    def path(self, name: str) -> str | None:
        # 允许一级子目录（play_cache/…），但拒绝任何目录穿越
        candidate = os.path.normpath(os.path.join(self.directory, name))
        if not candidate.startswith(os.path.abspath(self.directory)):
            return None
        return candidate if os.path.isfile(candidate) else None


def analyze_only(image_bytes: bytes) -> dict[str, Any]:
    """Style + character report for an image without animating it."""
    width, height, rgba = decode_image(image_bytes)
    return {
        "style": analyze_rgba(width, height, rgba),
        "character": extract_character(width, height, rgba),
        "palette": dominant_palette(width, height, rgba, count=8),
    }


def ai_segment_subject(
    source_bytes: bytes,
    size: int,
    settings: dict[str, Any],
    deadline: float | None = None,
):
    """AI 主体分割：qwen-image-edit 把角色原样抠到纯白底，再用白底洪泛
    提取主体 mask。对 AI 原画的复杂场景背景远比经典洪泛可靠。

    返回 PIL "L" mask（size×size，255=主体，已膨胀羽化对齐误差），任何
    失败返回 None（调用方回退经典洪泛），因此永远不会让任务中断。
    """
    if deadline is not None and time.time() >= deadline:
        return None
    try:
        from PIL import Image, ImageFilter

        from artgen.sourceanim import _border_bg, _fit, _flood_subject
        from studio.backend.model_service.service import (
            ImageEditProvider,
            safe_generated_path,
        )

        editor = ImageEditProvider(settings)
        encoded = base64.b64encode(source_bytes).decode()
        result = editor.edit("data:image/png;base64," + encoded, SEGMENT_PROMPT)

        path = safe_generated_path(result.get("file"))
        if not path:
            return None
        with open(path, "rb") as handle:
            edited = Image.open(io.BytesIO(handle.read())).convert("RGB")

        fitted = _fit(edited, max(64, min(1024, int(size)))).convert("RGB")
        # 白底化失败快速识别：四边中值色必须接近纯白
        border = _border_bg(fitted)
        if not all(channel > 230 for channel in border):
            return None

        mask = _flood_subject(fitted)
        hist = mask.histogram()
        total = mask.width * mask.height
        coverage = sum(hist[128:]) / total
        if not (MIN_SEGMENT_COVERAGE <= coverage <= MAX_SEGMENT_COVERAGE):
            return None
        bbox = mask.getbbox()
        if bbox is None or (bbox[2] - bbox[0]) * (bbox[3] - bbox[1]) < 0.01 * total:
            return None

        # 编辑模型输出与源图构图存在毫米级偏差：膨胀 + 羽化吸收边缘误差
        return mask.filter(ImageFilter.MaxFilter(7)).filter(ImageFilter.GaussianBlur(1.2))
    except Exception:  # noqa: BLE001 - segmentation is best-effort
        return None

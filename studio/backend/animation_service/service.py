"""Animation service (Studio): source image -> style-consistent animation.

Bridges the workbench asset/upload to the shared ``artgen`` animation pipeline
(style analysis + character extraction + pose frames + consistency check +
GIF/sheet encoding) and persists the artefacts for the console to display.
"""

import base64
import hashlib
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
# 帧粘连修复（正向句版）：i2v 模型在关节快速运动时常见"上一帧姿态残影叠加
# 到下一帧、肢体分裂成双重轮廓"伪影（试玩区/动画工作台实测的拖影粘连）。
# 主提示词不能写"no ghosting/no motion blur"（否定句名词会被 latch），只能
# 用正向句要求"每帧只有一份清晰轮廓、每个肢体只有一个明确位置"；残影类
# 伪影的否定交给 generate_video 的 negative_prompt 参数（见 model_service）。
FRAMING_CLAUSE = (
    "Preserve the reference character's exact face, hairstyle, clothing, accessories, "
    "color palette, linework, silhouette, textures, and local details throughout every frame. "
    "Use a locked camera with unchanged projection, framing, character scale, and canvas "
    "occupancy throughout the video. Exactly one character is in the frame, and the whole "
    "body from head to feet stays inside the frame at all times. Every frame shows exactly "
    "one single crisp copy of the character: each limb, joint and held item keeps a clean "
    "sharp outline and one well-defined position, staying just as sharply drawn at the "
    "fastest point of the motion as in a held pose."
)

# 动作提示词（i2v 模板 v2，词表工程）：**视角无关**原则不变。v2 相比 v1
# 的升级点（V2 词表 A/B 实测驱动）：①关节级编排（足跟触地/体重滚动/膝屈曲
# /对侧摆臂/髋肩反向旋转）给 i2v 明确的运动学目标，减少"整体漂移式"假动作；
# ②明确节奏与次数（"two full stride cycles"/"exactly one strike"）压住模型
# 自由发挥导致的倍速漂移与重复挥击；③次级运动显式化（发/布料/饰品迟一拍
# 跟随）补剪纸感的"无物理"短板；④循环收尾句（首尾同姿态）配合抽帧循环
# 接缝优化，降低回跳感。身份/构图/相机约束仍由 FRAMING_CLAUSE 代码级追加，
# 这里不重复，把词预算花在运动本身。
MOTION_PROMPTS = {
    "walk": (
        "The character walks in place, facing exactly the same direction as in the "
        "input image. Two full stride cycles: each leg lifts with a soft knee bend, "
        "the heel reaches forward and plants, weight rolls over the foot, then pushes "
        "off. The arms swing relaxed in counter-phase to the legs; hips and shoulders "
        "counter-rotate slightly; the torso dips at weight acceptance and rises at "
        "push-off. Hair, cloth and loose accessories settle naturally a beat after "
        "each step. The motion starts and ends in the same neutral standing pose."
    ),
    "run": (
        "The character runs in place, facing exactly the same direction as in the "
        "input image. Three quick stride cycles with brief airborne moments: knees "
        "drive up, heels kick back toward the hips, feet land under the body. The "
        "arms pump bent at the elbow in counter-phase; the torso leans slightly "
        "forward and bounces with each stride; hair and cloth bounce and trail with "
        "the impacts. The motion starts and ends in the same ready stance."
    ),
    "attack": (
        # MOS 盲评（benchmark/mos_kit，n=1，2026-10-04）：v2 攻击句（强调
        # "fast committed strike"+髋肩旋转）让 attack 一致性/真实感全线崩盘
        # （flash_v2/plus/1080p 三组整体均 2 分），而 v1 旧措辞拿 4 分——
        # 攻击性描述诱发 i2v 大幅运动伪影。attack 回滚 v1 措辞，其余四个
        # 动作保留 v2（v2 walk 是全场唯一 5 分）。
        "The character performs one single committed attack in place, keeping exactly "
        "the same facing direction and viewpoint as the input image: a brief coil back, "
        "then a decisive strike with the leading arm extending naturally, then settle "
        "back into the original stance, "
        "the character's design, outfit, colors and proportions stay exactly the same "
        "as the input image, the camera stays locked."
    ),
    "jump": (
        "The character performs one vertical jump in place, facing exactly the same "
        "direction as in the input image. A quick counter-movement crouch with the "
        "arms swinging back, an explosive vertical take-off with the legs extending "
        "and tucking slightly mid-air, hair and cloth rising with the ascent, then a "
        "soft bent-knee landing recovering into the original standing pose. Exactly "
        "one jump, starting and ending in the same stance."
    ),
    "idle": (
        "The character stands relaxed and breathes in place, facing exactly the same "
        "direction as in the input image. Slow breathing cycles: the chest and "
        "shoulders rise gently on the inhale and settle on the exhale; subtle weight "
        "shifts and micro-adjustments of the head and arms; hair and cloth sway very "
        "slightly. No steps, no large motion. The motion loops seamlessly between "
        "the first and the last frame."
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
    "direction, a locked camera, the character's design/outfit/colors unchanged, and one "
    "single crisp silhouette in every frame (each limb drawn once with sharp edges, never "
    "blended between two poses). "
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

# 分割结果缓存：每次调用都是真实计费请求，同一张源图会被重复分割
# （create_video 裁边 + idle 稳定分支、骨骼预览路由）。mask 对调用方
# 只读使用（filter 生成新图），共享安全。
_SEGMENT_CACHE: dict[str, tuple[float, Any]] = {}
_SEGMENT_CACHE_TTL = 600.0


# 批次状态模块级共享：路由处理函数每次请求构造 AnimationService 实例，
# 批次状态若挂在实例上会跨请求丢失（轮询永远 404）。
_ACTION_BATCHES: dict[str, dict] = {}
_ACTION_BATCHES_TTL = 3600.0  # 批次最长约 5×90 秒，1 小时 TTL 不会误删运行中批次

# ── 视频采样配置指纹（benchmark/video_quality.py 依赖；改动需重录基线）──
# R1 基线：min_count=20 / duration=1.0（20 帧 @12fps ≈ 1.67s 循环）。
# R2 优化：i2v 源视频 5s/24fps≈120 帧里只取 20 帧，时间采样率仅 17%；
# 提升到 30 帧（2.5s 循环，+50%）——每帧间源素材跨度从 0.21s 降到
# 0.14s，动作周期更完整、播放更顺滑；质量七项指标由基准 --check 把关。
VIDEO_SAMPLE_MIN_COUNT = 30
VIDEO_SAMPLE_DURATION = 1.25


def _prune_action_batches() -> None:
    """清理超过 TTL 的历史批次（内存态只增不删会缓慢泄漏）。"""

    now = time.time()
    for batch_id in list(_ACTION_BATCHES):
        created = (_ACTION_BATCHES.get(batch_id) or {}).get("created_at", 0)
        if now - created > _ACTION_BATCHES_TTL:
            _ACTION_BATCHES.pop(batch_id, None)


def _generate_video_cached(settings, prompt, source_bytes, timeout_seconds=420.0):
    """视频驱动生成的稳定入口（自动走 mp4 缓存）。"""

    from studio.backend.model_service.service import generate_video

    return generate_video(settings, prompt, source_bytes, timeout_seconds=timeout_seconds)


class VideoGenerationError(RuntimeError):
    """带分类的视频生成失败（kind: quota/auth/moderation/network/fatal）。"""

    def __init__(self, message: str, kind: str = "fatal"):
        super().__init__(message)
        self.kind = kind


def generate_video_with_policy(
    settings, prompt, source_bytes, timeout_seconds=420.0, model_override=None
):
    """视频驱动生成入口：mp4 缓存 + 网络类失败自动退避重试 + 错误分类。

    成功返回 ``(video_bytes, model)``；最终失败抛 VideoGenerationError，
    message 为面向用户的中文描述，kind 供批次徽章/前端提示分类展示。
    审核拦截与 Key 池切换由 generate_video 内部处理（安全改写重试轮）。
    ``model_override``：定稿档模型（V2 双档策略），直通 generate_video。"""

    from studio.backend.model_service.service import (
        classify_error,
        describe_error,
        generate_video,
    )

    last_exc = None
    for attempt in range(2):
        try:
            return generate_video(
                settings,
                prompt,
                source_bytes,
                timeout_seconds=timeout_seconds,
                model_override=model_override,
            )
        except Exception as exc:  # noqa: BLE001 - 分类后决定重试或上抛
            last_exc = exc
            if classify_error(exc) == "network" and attempt == 0:
                time.sleep(3.0)
                continue
            break
    raise VideoGenerationError(describe_error(last_exc), classify_error(last_exc)) from last_exc


def _select_by_motion(candidates, consecutive, count):
    """动作感知选帧：按「累计运动量」等分取帧（R3）。

    均匀时间采样在非匀速运动（i2v 常态：起手蓄力慢、发力快）下会把帧
    预算浪费在慢段、又跳过快段的中间帧——帧间运动能量忽大忽小（CV 高），
    观感卡顿。改为在候选帧的累计运动曲线上等分取点：运动快的段自动多
    取帧、静止段自动跳过，帧间能量均匀 = 视觉匀速。
    候选数 ≤ count 时退化为顺序截取（行为同旧版）。"""

    if len(candidates) <= count:
        return list(candidates)
    import bisect

    cum = [0.0]
    for a, b in zip(candidates, candidates[1:]):
        hi = min(b, len(consecutive))
        cum.append(cum[-1] + (sum(consecutive[a:hi]) if hi > a else 0.0))
    total_motion = cum[-1]
    if total_motion <= 1e-6:
        return candidates[:count]

    positions = []
    last = -1
    for k in range(count):
        desired = total_motion * k / (count - 1)
        pos = bisect.bisect_left(cum, desired)
        pos = max(pos, last + 1)
        # 右侧留足剩余名额，保证严格递增且恰好 count 个
        pos = min(pos, len(candidates) - 1 - (count - 1 - k))
        positions.append(pos)
        last = pos
    return [candidates[p] for p in positions]


def _reap_file(path, timeout=30.0):
    """后台收割临时文件（Windows 专属竞态的兜底）。

    reader.close() 返回时 ffmpeg 子进程可能尚未完全退出，读句柄仍在，
    立刻 os.remove 会 PermissionError（浸泡实测命中约 1/30）。主线程
    只做一次快删，失败交给本守护线程退避重试——磁盘清理最终一致，
    绝不阻塞生成主流程。"""

    deadline = time.time() + timeout
    delay = 0.1
    while time.time() < deadline:
        try:
            os.remove(path)
            return
        except FileNotFoundError:
            return
        except PermissionError:
            time.sleep(delay)
            delay = min(0.5, delay * 1.5)
        except OSError:
            return


# 发/裙次级运动：让编辑模型把头发变纯白，再与原图差分提取发层
# （「隔离头发到白底」单提示实测不可靠——模型不执行；「变白」有
# SEGMENT_PROMPT 同族先例，差分可靠，2026-10-04 骑士实测覆盖率 8.12%）
HAIR_WHITE_PROMPT = (
    "把这张图中角色的头发全部变成纯白色(#FFFFFF)。其余部分（脸、身体、"
    "衣服、武器、背景）保持完全原样：不缺失、不变色、不位移。只允许头发"
    "像素变成纯白。"
)


class AnimationService:
    def __init__(self, directory: str):
        self.directory = directory
        os.makedirs(self.directory, exist_ok=True)
        self.action_batches = _ACTION_BATCHES

    # -- 一键补齐全套动作（串行队列，跳过已生成） --------------------------

    def existing_ai_actions(self, asset_id: str | None) -> set:
        """该资产已生成过 **AI 视频驱动** 动画的动作集合（扫描动画 meta）。

        判定三条件（缺一不可，修复"补齐 0 个/永远不完成"的双口径 bug）：
        1. ``source == "video"`` —— 源图摆动（asset）等确定性动画不算 AI 动画，
           否则旧动画会永久阻塞同类动作的 AI 生成；
        2. 本地帧文件实存 ≥ 4 —— 坏 meta/文件被清理的记录不算，避免永久跳过；
        3. 动作名可识别。
        """

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
            if meta.get("source") != "video" or meta.get("asset_id") != asset_id:
                continue
            frame_urls = meta.get("frame_urls") or []
            local = sum(
                1
                for url in frame_urls
                if os.path.isfile(os.path.join(self.directory, os.path.basename(url)))
            )
            if local < 4:
                continue
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

        _prune_action_batches()

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

        from studio.backend.animation_service.equipment import (
            context_line as _equipment_context_line,
        )
        from studio.backend.animation_service.equipment import (
            motion_clauses as _equipment_motion_clauses,
        )
        from studio.backend.animation_service.equipment import (
            recognize as _equipment_recognize,
        )

        batch = self.action_batches.get(batch_id) or {}
        # V3.5 装备识别（批次共享一次调用，之后走源图哈希缓存）：
        # 上下文并入润色，attack+持械追加武器保持子句（与单条链路同语义）
        equipment = None
        if settings.get("equipment_aware", True):
            equipment = _equipment_recognize(source_bytes, settings)
        batch_context = enhance_context
        equipment_line = _equipment_context_line(equipment) if equipment else None
        if equipment_line:
            batch_context = (
                "{}；{}".format(enhance_context, equipment_line)[:200]
                if enhance_context
                else equipment_line
            )
        for action in pending:
            entry = next((t for t in batch.get("tasks", []) if t.get("action") == action), None)
            if entry:
                entry["status"] = "generating"
                entry["stage"] = "prompt"
                entry["started_at"] = time.time()
            try:
                base_prompt = MOTION_PROMPTS.get(action, MOTION_PROMPTS["walk"])
                enhanced_prompt = ai_enhance_motion_prompt(
                    settings, action, base_prompt, context=batch_context
                )
                extra_clauses = _equipment_motion_clauses(equipment, action) if equipment else []
                clause_text = (" " + " ".join(extra_clauses)) if extra_clauses else ""
                prompt = enhanced_prompt + clause_text + " " + FRAMING_CLAUSE
                if entry:
                    entry["stage"] = "video"  # i2v 生成是 60~90s 的大头
                video_bytes, video_model = generate_video_with_policy(
                    settings, prompt, source_bytes, timeout_seconds=420.0
                )
                if entry:
                    entry["stage"] = "sampling"
                frames_rgba = self._slice_video(
                    video_bytes,
                    source_bytes,
                    12,
                    VIDEO_SAMPLE_DURATION,
                    384,
                    min_count=VIDEO_SAMPLE_MIN_COUNT,
                )
                if entry:
                    entry["stage"] = "composing"
                from artgen import compose_animation

                # 批次补齐走试玩条带，无需 mp4 出口（省每条 1~3s 编码）
                result = compose_animation(
                    frames_rgba=frames_rgba, fps=12, size=384, with_mp4=False
                )
                animation_id = uuid.uuid4().hex[:12]  # 模块级已导入；修复批次作用域引用未导入别名导致的 NameError
                meta = self._persist(result, animation_id, "video")
                meta["video_model"] = video_model
                meta["asset_id"] = asset_id
                meta["requested_action"] = action
                # V3.5 生成后自动质检（批次链）：同单条链路语义
                try:
                    from studio.backend.animation_service.motion_qa import post_validate

                    _qa = post_validate(
                        frames_rgba, source_bytes=source_bytes, action=action, chain="video"
                    )
                    if _qa:
                        meta["qa"] = _qa
                except Exception:  # noqa: BLE001
                    pass
                if equipment:
                    meta["equipment"] = equipment
                    if extra_clauses:
                        meta["equipment_prompt_clauses"] = True
                if enhanced_prompt != base_prompt:
                    meta["prompt_enhanced"] = True
                    meta["motion_prompt"] = prompt[:400]
                self._write(f"{animation_id}.json", json.dumps(meta, ensure_ascii=False).encode("utf-8"))
                if entry:
                    entry["status"] = "done"
                    entry["stage"] = "done"
                    entry["progress"] = 100
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
        # 收尾分级：全部动作失败标 failed（前端可提示异常），部分失败仍算 done
        failed = sum(1 for t in batch.get("tasks", []) if t.get("status") == "failed")
        batch["failed_count"] = failed
        batch["status"] = "failed" if failed and failed == len(pending) else "done"

    def action_batch_snapshot(self, batch_id: str) -> dict | None:
        _prune_action_batches()
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

    def _hair_overlay(
        self,
        source_bytes: bytes,
        settings: dict[str, Any],
        size: int,
        pose_config: dict[str, Any] | None,
    ):
        """发层 overlay（V3 次级运动）：按动画源图哈希落盘缓存——首期调用
        一次"头发变白"编辑（~0.3 元）差分提取，之后同源图永久免费。返回
        riganim overlays dict 或 None（模型不可用/提取不可信/用户关幅度）。

        幅度/滞后可由 pose_config 的 ``hair_amp``（度，默认 7）/``hair_lag``
        （0..1，默认 0.12）覆盖；hair_amp=0 即关闭摆动（仍跟随头部）。"""

        import base64 as _b64

        from artgen.sourceanim import extract_hair_layer
        from studio.backend.model_service.service import GENERATED_DIR

        if not source_bytes:
            return None
        amp = float((pose_config or {}).get("hair_amp", 7.0))
        lag = float((pose_config or {}).get("hair_lag", 0.12))
        if amp <= 0:
            return None

        source_hash = hashlib.sha1(source_bytes).hexdigest()[:12]
        layer_path = os.path.join(GENERATED_DIR, "hair_{}.png".format(source_hash))
        meta_path = os.path.join(GENERATED_DIR, "hair_{}.json".format(source_hash))
        try:
            if os.path.isfile(layer_path) and os.path.isfile(meta_path):
                with open(meta_path, encoding="utf-8") as handle:
                    info = json.load(handle)
                with open(layer_path, "rb") as handle:
                    from PIL import Image

                    layer = Image.open(io.BytesIO(handle.read())).convert("RGBA")
            else:
                if not ((settings or {}).get("enabled") and (settings or {}).get("api_key")):
                    return None
                from PIL import Image

                from studio.backend.model_service.service import ImageEditProvider

                editor = ImageEditProvider(settings)
                result = editor.edit(
                    "data:image/png;base64," + _b64.b64encode(source_bytes).decode(),
                    HAIR_WHITE_PROMPT,
                )
                edited_path = safe_generated_path(result.get("file"))
                if not edited_path:
                    return None
                with open(edited_path, "rb") as handle:
                    edited = Image.open(io.BytesIO(handle.read())).convert("RGB")
                front = Image.open(io.BytesIO(source_bytes)).convert("RGB")
                layer, root, coverage = extract_hair_layer(front, edited)
                if not (0.005 <= coverage <= 0.35):
                    return None  # 提取不可信：宁可不加发层也不糊脸
                buffer = io.BytesIO()
                layer.save(buffer, "PNG")
                layer_bytes = buffer.getvalue()
                with open(layer_path, "wb") as handle:
                    handle.write(layer_bytes)
                info = {"root": list(root), "coverage": coverage, "size": list(layer.size)}
                with open(meta_path, "w", encoding="utf-8") as handle:
                    json.dump(info, handle, ensure_ascii=False)
            root = info.get("root") or [0.5, 0.5]
            return {
                "layer": layer,
                "root": (float(root[0]), float(root[1])),
                "amp": amp,
                "lag": lag,
            }
        except Exception:  # noqa: BLE001 - 次级运动是增益项，永不阻塞生成
            return None

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
        secondary_motion: bool = False,
        equipment_aware: bool = True,
    ) -> dict[str, Any]:
        action = action if action in ACTIONS else "walk"

        params = None
        source_bytes = None
        source_kind = "builtin"
        side_bound = False  # V3-②：侧视动画是否绑定到了真三视图 side 源图

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
                if view == "side":
                    # V3-②：侧视动画优先用三视图 side 真源图（本地存在时），
                    # 替代"正视原画凑侧视"的旧做法
                    side_bytes = self._asset_view_render(asset, "side")
                    if side_bytes:
                        source_bytes = side_bytes
                        side_bound = True
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
            if view == "side":
                # V3-②：同骨骼分支——侧视动画用三视图 side 真源图
                side_bytes = self._asset_view_render(asset, "side")
                if side_bytes:
                    source_bytes = side_bytes
                    side_bound = True
            if source_bytes is None:
                # 无 AI 原画/本地文件（如重启后的历史资产）：退回资产正面立绘
                # （与前端展示的 /api/assets/{id}/image.png 同一渲染），保证关键帧
                # 从资产图本身派生，而不是落到程序化像素小人
                try:
                    from artgen import render_asset_view

                    source_bytes = render_asset_view(asset, "front", max(384, min(1024, int(size))))
                except Exception:
                    source_bytes = None

        # V3.5 装备/服装识别：按源图哈希持久缓存（首次一次视觉对话
        # ~0.002 元，之后终身免费）。骨骼链用它做姿态贴合（持械 attack
        # 摆臂加大 / 重甲 run 起伏收敛 / 长裙 walk 步幅微收），用户滑杆
        # 参数永远优先（覆盖只填用户未给的键）。识别失败一律返回 None，
        # 绝不阻塞生成。
        equipment = None
        if source_bytes is not None and equipment_aware:
            from studio.backend.animation_service.equipment import (
                pose_overrides as _equipment_pose_overrides,
            )
            from studio.backend.animation_service.equipment import (
                recognize as _equipment_recognize,
            )

            equipment = _equipment_recognize(source_bytes, model_settings or {})
            if equipment and skeletal:
                overrides = _equipment_pose_overrides(equipment, action)
                if overrides:
                    pose_config = {**overrides, **(pose_config or {})}

        # V3 次级运动（发/裙摆动）：secondary_motion 开启时构建发层 overlay。
        # 首次生成调用一次图像编辑（~0.3 元），按源图哈希落盘缓存后永久免费。
        overlays = None
        if secondary_motion and source_bytes is not None:
            overlay = self._hair_overlay(
                source_bytes, model_settings or {}, size, pose_config
            )
            if overlay:
                overlays = [overlay]

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
            overlays=overlays,
        )

        animation_id = uuid.uuid4().hex[:12]
        meta = self._persist(result, animation_id, source_kind)
        meta["skeletal"] = source_kind == "skeletal"
        # V3.5 生成后自动质检：对交付帧算三维量化指标（流畅/时序/细节还原），
        # grade ∈ pass/warn/fail 落 meta 供前端徽章；best-effort 绝不阻塞
        try:
            from artgen.gif import decode_png as _decode_png

            from studio.backend.animation_service.motion_qa import post_validate

            _qa_frames = [_decode_png(png) for png in result["frames"]]
            _qa = post_validate(
                _qa_frames,
                source_bytes=source_bytes,
                action=action,
                chain="skeletal" if source_kind == "skeletal" else "source",
            )
            if _qa:
                meta["qa"] = _qa
        except Exception:  # noqa: BLE001 - 质检永不阻塞生成
            pass
        if side_bound:
            # V3-②：本次侧视动画绑定的是三视图 side 真源图（供前端徽标/测试断言）
            meta["view_bound"] = "side"
        if overlays:
            # V3 次级运动：本次动画携带发层摆动（meta 落盘供前端徽标）
            meta["hair_overlay"] = True
        # V3 网格变形：记录实际生效的皮肤模式（A/B 开关的落盘证据）
        if source_kind == "skeletal":
            from artgen.riganim import RIGANIM_SKIN_DEFAULT

            meta["skin_mode"] = (pose_config or {}).get("skin") or RIGANIM_SKIN_DEFAULT
        # V3.5 装备识别：本次生成使用的装备/服装信息（前端标签徽章数据源）。
        # 放在资产归属重写之前，保证落盘的 meta 里也有。
        if equipment:
            meta["equipment"] = equipment
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

    def _asset_view_render(self, asset: dict[str, Any], view: str):
        """三视图源图（design_views.<view>）的本地 bytes；无记录或本地文件
        缺失返回 None（调用方回退正面原画）。

        V3-②：side 视图真绑定——AI 三视图的 side.png 此前只用于展示与
        导出（export_service），侧视动画一直在用正视原画凑数；本方法把它
        接进动画管线。仅认本地文件，远端签名失效一律回退，绝不阻塞生成。"""

        if not isinstance(asset, dict):
            return None
        views = asset.get("design_views")
        if not isinstance(views, dict):
            return None
        meta = views.get(view)
        if not isinstance(meta, dict):
            return None
        from studio.backend.model_service.service import safe_generated_path

        path = safe_generated_path(meta.get("file"))
        if not path or not os.path.isfile(path):
            return None
        try:
            with open(path, "rb") as handle:
                return handle.read()
        except OSError:
            return None

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

        urls = {
            "gif": f"/api/animation/{gif_name}",
            "sheet": f"/api/animation/{sheet_name}",
            "thumb": f"/api/animation/{thumb_name}",
        }
        # mp4 出口（V3 后期链）：程序化链与 i2v 链同规格交付；缺省无此键
        video_spec = None
        if result.get("mp4"):
            self._write(f"{animation_id}.mp4", result["mp4"])
            urls["video"] = f"/api/animation/{animation_id}.mp4"
            video_spec = {
                "width": result["size"],
                "height": result["size"],
                "fps": result.get("mp4_fps") or result["fps"],
                "duration": round(
                    result["frame_count"] / max(1, result.get("mp4_fps") or result["fps"]), 3
                ),
                "bytes": len(result["mp4"]),
            }

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
            "urls": urls,
            "created_at": time.time(),
        }
        if video_spec:
            meta["video_spec"] = video_spec
        # V3.5 流畅度：walk/run 帧混合（伪运动模糊）已应用到本次产物
        if result.get("motion_blend"):
            meta["motion_blend"] = True
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
        final_quality: bool = False,
        equipment_aware: bool = True,
    ) -> dict[str, Any]:
        """Windup 式 AI 视频驱动：源图（自动裁白边）+ 动作提示词 → 图生视频
        → 均匀抽帧 →（仅 idle）弱背景稳定 → 序列合成。失败抛
        VideoGenerationError（带分类与中文描述），路由原样透传给前端。

        ``enhance_context``：角色名/简介等上下文，供动作描述 AI 增强参考
        （video_ai_enhance 开启时）。

        ``final_quality``：V2 双档策略的定稿档——用 settings
        ``video_model_final``（默认 wan2.2-i2v-plus）出片；草稿档走
        ``video_model``（默认 flash），成本 1/2.8。meta 记 quality_tier。

        ``equipment_aware``：V3.5 装备/服装识别——看图认出武器/服装后
        并入润色上下文；attack+持械时代码级追加「武器保持在手」子句
        （快速挥击中武器被挥丢/换手是实测失败模式）。按源图哈希持久
        缓存，同一张原画终身只识别一次。"""

        action = action if action in ACTIONS else "walk"

        # V3.5 装备/服装识别（持久缓存，失败静默跳过）
        equipment = None
        if equipment_aware:
            from studio.backend.animation_service.equipment import (
                context_line as _equipment_context_line,
            )
            from studio.backend.animation_service.equipment import (
                motion_clauses as _equipment_motion_clauses,
            )
            from studio.backend.animation_service.equipment import (
                recognize as _equipment_recognize,
            )

            equipment = _equipment_recognize(source_bytes, settings)

        # 送 i2v 前自动裁掉白边/留白：主体占比从 ~60% 提到 ~90%，
        # 对齐官方 demo 的输入形态（主体小+平面白底会显著拉低 i2v 质量）
        work_bytes = source_bytes
        crop_info = None
        try:
            work_bytes, crop_info = self._crop_to_subject(source_bytes, settings)
        except Exception:  # noqa: BLE001 - crop is best-effort
            work_bytes = source_bytes

        # 动作描述 AI 增强（可配置，失败回退原模板）；代码级构图约束
        # FRAMING_CLAUSE 始终由代码追加，不交给模型发挥。
        # 装备/服装识别结果并入润色上下文——润色系统提示本就要求
        # "Character context (outfit/gear/identity hints only)"，现在给它
        # 真实的看图结论（标签+款式描述）而不是只有角色名。
        context = enhance_context
        equipment_line = _equipment_context_line(equipment) if equipment else None
        if equipment_line:
            context = (
                "{}；{}".format(enhance_context, equipment_line)[:200]
                if enhance_context
                else equipment_line
            )
        base_prompt = MOTION_PROMPTS.get(action, MOTION_PROMPTS["walk"])
        enhanced_prompt = ai_enhance_motion_prompt(
            settings, action, base_prompt, context=context
        )
        extra_clauses = _equipment_motion_clauses(equipment, action) if equipment else []
        clause_text = (" " + " ".join(extra_clauses)) if extra_clauses else ""
        prompt = enhanced_prompt + clause_text + " " + FRAMING_CLAUSE
        # 双档策略：定稿档强制走 video_model_final（缓存 key 含实际模型，
        # 与草稿档互不命中）；草稿档保持现有回退链
        model_override = None
        if final_quality:
            model_override = (settings or {}).get("video_model_final") or None
        video_bytes, video_model = generate_video_with_policy(
            settings, prompt, work_bytes, timeout_seconds=420.0, model_override=model_override
        )
        frames_rgba, slice_info = self._slice_video(
            video_bytes,
            source_bytes,
            fps,
            max(float(duration or 1.0), VIDEO_SAMPLE_DURATION),
            size,
            min_count=VIDEO_SAMPLE_MIN_COUNT,
            with_info=True,
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

        # with_mp4=False：i2v 链的 mp4 由 _deliver_video_mp4 直通裁剪源视频
        # （960²~1440² 原画质），384px 帧重编码没有意义
        result = compose_animation(frames_rgba=frames_rgba, fps=fps, size=size, with_mp4=False)
        animation_id = uuid.uuid4().hex[:12]
        meta = self._persist(result, animation_id, "video")
        meta["video_model"] = video_model
        meta["quality_tier"] = "final" if final_quality else "draft"
        # V3.5 生成后自动质检（i2v 链）：对抽帧后的交付序列算量化指标；
        # best-effort 绝不阻塞交付
        try:
            from studio.backend.animation_service.motion_qa import post_validate

            _qa = post_validate(
                frames_rgba, source_bytes=source_bytes, action=action, chain="video"
            )
            if _qa:
                meta["qa"] = _qa
        except Exception:  # noqa: BLE001
            pass
        # V3.5 装备识别：本次视频使用的装备/服装信息（含是否注入了武器子句）
        if equipment:
            meta["equipment"] = equipment
            if extra_clauses:
                meta["equipment_prompt_clauses"] = True
        # mp4 直通交付（V1）：与 GIF 同窗的原速、原分辨率 H.264。失败只
        # 降级（无 urls.video），不影响已落盘的 GIF 产物。
        video_spec = self._deliver_video_mp4(video_bytes, slice_info, animation_id)
        if video_spec:
            meta["urls"]["video"] = f"/api/animation/{animation_id}.mp4"
            meta["video_spec"] = video_spec
        # 记录归属资产与真实动作（compose 会把 action 覆盖为 "sequence"），
        # 试玩舞台按「资产 + 动作」匹配 AI 动画帧。
        if asset_id:
            meta["asset_id"] = asset_id
        meta["requested_action"] = action
        if enhanced_prompt != base_prompt:
            meta["prompt_enhanced"] = True
            meta["motion_prompt"] = prompt[:400]
        if crop_info:
            meta["source_cropped"] = crop_info
        if subject_locked:
            meta["subject_locked"] = True
        # 所有追加字段就位后统一落盘一次。旧代码在写入之后才追加
        # source_cropped/subject_locked，这两个字段从未落过盘。
        self._write(f"{animation_id}.json", json.dumps(meta, ensure_ascii=False).encode("utf-8"))
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
        with_info: bool = False,
    ):
        """mp4 bytes -> evenly sampled, stabilized (w,h,RGBA) frames.

        流式解码：逐帧读取、即时缩略、只保留采样目标帧——避免旧实现把
        全部帧解码进内存（161 帧 960×960 ≈ 425MB）的内存峰值。

        选帧策略（R3）：元数据可用时先保留 ~3× 预算的候选帧（封顶 64），
        再按累计运动量等分精选（_select_by_motion）；元数据缺失时退回
        均匀重采样。

        ``with_info=True`` 时返回 ``(frames, info)``：info 携带源视频帧率、
        选中帧的源索引与循环接缝偏移——mp4 直通交付（_deliver_video_mp4）
        靠它把 GIF 同窗的片段从源视频精确裁出来。默认 False，返回值与
        既有调用方/测试兼容。"""

        import imageio.v2 as imageio
        from PIL import Image

        from artgen.sourceanim import _fit

        if not video_bytes or len(video_bytes) < 1024:
            # 模块衔接边界校验：上游（生成/缓存/下载）给到空/截断数据时
            # 立即给可读错误，而不是等 imageio 抛解析异常
            raise RuntimeError("视频数据为空或已损坏（<1KB），无法抽帧")

        tmp = os.path.join(self.directory, "tmp_{}.mp4".format(uuid.uuid4().hex[:8]))
        with open(tmp, "wb") as handle:
            handle.write(video_bytes)
        try:
            try:
                reader = imageio.get_reader(tmp)
            except Exception as error:  # noqa: BLE001 - 上游给到垃圾/截断数据
                raise RuntimeError(
                    "视频数据无法解码：{}".format(str(error)[:120])
                ) from error
            source_fps = 0.0
            try:
                # 源帧率供 mp4 直通换算时间窗；元数据缺失时由调用方兜底
                source_fps = float(reader.get_meta_data().get("fps") or 0.0)
            except Exception:  # noqa: BLE001 - metadata unavailable
                source_fps = 0.0
            try:
                total = int(reader.count_frames())
            except Exception:  # noqa: BLE001 - metadata unavailable
                total = 0
            count = max(2, min(90, round(fps * duration)))
            if min_count:
                # i2v 的 5 秒视频压到 12 帧会丢掉大部分动作信息；至少抽
                # min_count 帧让动作周期完整、播放更顺滑。上限 90 放行
                # 24fps 整循环（原 60 封顶会把 24fps×>2.5s 挡在门外）
                count = max(count, min(int(min_count), 90))

            if total >= 4:
                lo = max(1, int(total * 0.02))
                hi = total - max(1, int(total * 0.04))
                if hi - lo < 4:
                    lo, hi = 0, total - 1
                candidate_n = min(3 * count, 64, hi - lo + 1)
                wanted = {
                    round(lo + (hi - lo) * i / max(1, candidate_n - 1))
                    for i in range(candidate_n)
                }
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
            try:
                for frame in reader:
                    diff, gray_prev = small(gray_prev, frame)
                    if index > 0:
                        consecutive.append(diff)
                    if wanted is None or index in wanted:
                        canvas = _fit(Image.fromarray(frame), max(64, min(1024, int(size))))
                        kept[index] = canvas
                    index += 1
            finally:
                # 任何路径（含中途异常）都必须关掉 reader：ffmpeg 子进程
                # 不退出，tmp 文件句柄就永远不释放
                reader.close()
        finally:
            try:
                os.remove(tmp)
            except PermissionError:
                # Windows 竞态：ffmpeg 子进程尚未完全退出 → 交给后台收割线程
                import threading

                threading.Thread(
                    target=_reap_file, args=(tmp,), daemon=True, name="cf-tmp-reaper"
                ).start()
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
            indices = _select_by_motion(sorted(kept.keys()), consecutive, count)
        else:
            lo = min(start + max(1, int(total * 0.02)), max(0, total - 4))
            hi = total - max(1, int(total * 0.04))
            if hi - lo < 4:
                lo, hi = 0, total - 1
            indices = sorted(
                set(round(lo + (hi - lo) * i / max(1, count - 1)) for i in range(count))
            )[:count]

        frames_rgba = []
        found_indices = []
        for frame_index in indices:
            canvas = kept.get(frame_index)
            if canvas is None:
                continue
            found_indices.append(frame_index)
            frames_rgba.append((canvas.width, canvas.height, bytearray(canvas.tobytes())))
        if len(frames_rgba) < 2:
            raise RuntimeError("生成的视频有效帧不足，无法抽帧")

        # 循环接缝优化：GIF 首尾相接，把相邻帧差最大的那一对切到循环边界，
        # 循环回跳感最小。O(n) 的 48×48 灰度差，代价可忽略。
        cut = 0
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
        if with_info:
            info = {
                "source_fps": source_fps or None,
                "total": total,
                "indices": found_indices,
                "cut": cut,
            }
            return self._loop_blend(frames_rgba), info
        return self._loop_blend(frames_rgba)

    @staticmethod
    def _blend_rgba(frame_a, frame_b, alpha):
        """两帧 RGBA 线性混合（循环交叉溶解的过渡帧）。"""

        import numpy as np
        from PIL import Image

        a = np.asarray(Image.frombytes("RGBA", (frame_a[0], frame_a[1]), bytes(frame_a[2])), dtype=np.float32)
        b = np.asarray(Image.frombytes("RGBA", (frame_b[0], frame_b[1]), bytes(frame_b[2])), dtype=np.float32)
        mixed = a * (1.0 - alpha) + b * alpha
        return (frame_a[0], frame_a[1], bytearray(np.clip(mixed, 0, 255).astype(np.uint8).tobytes()))

    @staticmethod
    def _loop_blend(frames_rgba, blend_k=2):
        """循环交叉溶解（V4 功能体检发现的共性缺陷·统一修复）：i2v 源视频
        首尾状态天然差异大（开头=静止原图、结尾=运动后状态），接缝重排只能
        把最大跳变**藏**到循环边界、不能消除它——全模型配置产出接缝残留
        实测 2.5~3× 平均帧差（matrix B 六组全部命中）。在循环边界追加 K 帧
        首尾交叉混合（12fps 下 ~160ms 渐变），硬回跳变肉眼顺滑过渡。
        帧数 +K，循环时长略增；对程序化链不适用（其首尾本就 C0 连续）。"""

        if not frames_rgba or len(frames_rgba) < 6 or blend_k <= 0:
            return frames_rgba
        first, last = frames_rgba[0], frames_rgba[-1]
        if first[0] != last[0] or first[1] != last[1]:
            return frames_rgba
        blended = [
            AnimationService._blend_rgba(last, first, k / (blend_k + 1.0))
            for k in range(1, blend_k + 1)
        ]
        return frames_rgba + blended

    def _deliver_video_mp4(self, video_bytes: bytes, info: dict, animation_id: str):
        """i2v 源 mp4 直通交付：按抽帧选中的时间窗从**源视频**精确裁出
        原速、原分辨率的 mp4（GIF 只保留了 384px/12fps 的子采样）。裁剪窗
        与 GIF 同源（同一批选中索引），编码对齐 onetake 渲染规范
        （H.264 CRF16 high profile +faststart）。

        纯增益路径：任何失败只降级返回 None（GIF 产物不受影响），绝不
        让整次动画生成失败。返回 spec dict（分辨率/帧率/时长/码率）或
        None。"""

        if not info or len(info.get("indices") or []) < 2 or not video_bytes:
            return None
        fps_src = float(info.get("source_fps") or 0.0)
        if fps_src <= 0:
            fps_src = 24.0  # DashScope wan 系 i2v 标称帧率；元数据缺失时兜底
        indices = info["indices"]
        t0 = indices[0] / fps_src
        duration = (indices[-1] + 1) / fps_src - t0
        if duration < 0.3:
            return None

        import subprocess

        try:
            import imageio_ffmpeg

            ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
        except Exception:  # noqa: BLE001 - 无 ffmpeg 环境直接降级
            return None

        tmp = os.path.join(self.directory, "tmp_src_{}.mp4".format(animation_id))
        out_path = os.path.join(self.directory, "{}.mp4".format(animation_id))
        with open(tmp, "wb") as handle:
            handle.write(video_bytes)
        try:
            command = [
                ffmpeg,
                "-v", "error",
                "-y",
                # -ss 在 -i 前（输入定位）+ 重编码 = 帧级精确裁剪
                "-ss", "{:.3f}".format(t0),
                "-t", "{:.3f}".format(duration),
                "-i", tmp,
                "-an",  # i2v 无音轨；显式去除避免容器诡异物
                "-c:v", "libx264",
                "-preset", "medium",
                "-crf", "16",
                "-pix_fmt", "yuv420p",
                "-profile:v", "high",
                "-movflags", "+faststart",
                out_path,
            ]
            creationflags = (
                getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0
            )
            proc = subprocess.run(
                command,
                timeout=180,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                creationflags=creationflags,
            )
            if (
                proc.returncode != 0
                or not os.path.isfile(out_path)
                or os.path.getsize(out_path) < 1024
            ):
                try:
                    os.remove(out_path)
                except OSError:
                    pass
                return None
        except Exception:  # noqa: BLE001 - 降级路径：GIF 已交付，mp4 失败不致命
            try:
                os.remove(out_path)
            except OSError:
                pass
            return None
        finally:
            try:
                os.remove(tmp)
            except PermissionError:
                # Windows 竞态：子进程句柄未释放 → 后台收割（同 _slice_video）
                import threading

                threading.Thread(
                    target=_reap_file, args=(tmp,), daemon=True, name="cf-tmp-reaper"
                ).start()
            except OSError:
                pass

        spec = {"duration": round(duration, 3), "bytes": os.path.getsize(out_path)}
        try:
            import imageio.v2 as imageio

            reader = imageio.get_reader(out_path)
            try:
                meta = reader.get_meta_data()
                spec["fps"] = round(float(meta.get("fps") or fps_src), 3)
                size = meta.get("size")
                if size:
                    spec["width"], spec["height"] = int(size[0]), int(size[1])
            finally:
                reader.close()
        except Exception:  # noqa: BLE001 - 规格探测失败不影响交付
            spec["fps"] = round(fps_src, 3)
        if spec.get("width"):
            spec["bitrate_kbps"] = int(
                spec["bytes"] * 8 / max(0.001, spec["duration"]) / 1000
            )
        return spec

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

        # 远端图落地时优先用资产记录的 file 名：与 file/path 候选同链路，
        # 落盘一次后整条解析链（含 /api/generated/<file>）都本地可达
        remote_file = None
        for meta in metas:
            if isinstance(meta, dict) and meta.get("url"):
                remote_file = remote_file or (
                    os.path.basename(str(meta["file"])) if meta.get("file") else None
                )

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
            name = remote_file or os.path.basename(remote.split("?")[0])
            local = os.path.join(base, name)
            if name and os.path.isfile(local):
                with open(local, "rb") as handle:
                    return handle.read()
            try:
                import urllib.request

                with urllib.request.urlopen(remote, timeout=20) as response:
                    data = response.read()
                # 立即落盘：OSS/签名 URL 会过期，过期后原图永久丢失。
                # 访问过一次就本地化，之后该资产与经典工作台同源同图。
                if name and data:
                    try:
                        with open(local, "wb") as handle:
                            handle.write(data)
                    except OSError:
                        pass
                return data
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
    cache_key = hashlib.sha1(source_bytes).hexdigest()[:16] + ":{}".format(size)
    cached = _SEGMENT_CACHE.get(cache_key)
    if cached and time.time() - cached[0] < _SEGMENT_CACHE_TTL:
        return cached[1]
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
        # 分体修复 R1：白底分割同样有"封闭背景洞"问题（两腿之间的白底
        # 被腿围住、洪泛不可达 → 误判主体），编辑后的图就在手边，按白底
        # 色回收；回收失败静默回退原 mask
        from artgen.riganim import _absorb_enclosed_background

        mask = _absorb_enclosed_background(mask, fitted, bg_color=border)
        hist = mask.histogram()
        total = mask.width * mask.height
        coverage = sum(hist[128:]) / total
        if not (MIN_SEGMENT_COVERAGE <= coverage <= MAX_SEGMENT_COVERAGE):
            return None
        bbox = mask.getbbox()
        if bbox is None or (bbox[2] - bbox[0]) * (bbox[3] - bbox[1]) < 0.01 * total:
            return None

        # 编辑模型输出与源图构图存在毫米级偏差：膨胀 + 羽化吸收边缘误差
        result = mask.filter(ImageFilter.MaxFilter(7)).filter(ImageFilter.GaussianBlur(1.2))
        _SEGMENT_CACHE[cache_key] = (time.time(), result)
        return result
    except Exception:  # noqa: BLE001 - segmentation is best-effort
        return None

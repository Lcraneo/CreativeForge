"""Third-party image-model integration for the Studio.

These providers are only invoked when the user configures an external model
API (``enabled`` + ``base_url`` + ``api_key``). With no configuration the
runtime degrades to the built-in deterministic pipeline, so every call here is
best-effort and wrapped by the caller's ``MODEL_FALLBACK`` path.

The chat / image calls speak the OpenAI-compatible ``/chat/completions`` and
``/images/generations`` contracts, which most hosted providers mirror.
"""

import base64
import hashlib
import io
import json
import os
import threading
import time

import httpx

from studio.backend.persistence import atomic_write_json, read_json_recover

DEFAULT_SETTINGS_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "model_settings.json"
)

GENERATED_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "generated"
)

# ── 凭证 .env 兜底（与 storage_service 同源纪律：密钥仅读取环境变量） ──────────
_BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_ENV_FILE_CANDIDATES = (
    os.path.join(_BACKEND_DIR, ".env"),  # studio/backend/.env（推荐）
    os.path.join(os.path.dirname(_BACKEND_DIR), ".env"),  # studio/.env
    os.path.join(os.path.dirname(os.path.dirname(_BACKEND_DIR)), ".env"),  # 仓库根 .env
)


def _load_env_file(path):
    """极简 .env 解析（KEY=VALUE，支持引号与 # 注释）。"""
    values = {}
    try:
        with open(path, "r", encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, value = line.split("=", 1)
                values[key.strip()] = value.strip().strip("\"'")
    except OSError:
        pass
    return values


def _env_credentials():
    """合并进程环境与 .env 文件（进程环境优先）。"""
    env = dict(os.environ)
    for candidate in _ENV_FILE_CANDIDATES:
        for key, value in _load_env_file(candidate).items():
            env.setdefault(key, value)
    return env


def _dashscope_env_override():
    """.env 里有百炼 key 时构造一份启用配置（兜底默认，用户显式配置优先）。"""
    env = _env_credentials()
    key = env.get("DASHSCOPE_API_KEY") or env.get("AI_API_KEY")
    if not key:
        return None
    preset = PROVIDER_PRESETS["dashscope"]
    return {
        "enabled": True,
        "provider": "dashscope",
        "base_url": preset["base_url"],
        "model": env.get("DASHSCOPE_MODEL", preset["model"]),
        "chat_model": env.get("DASHSCOPE_CHAT_MODEL", preset["chat_model"]),
        "api_key": key,
        "use_chat": True,
        "use_image": True,
        "size": env.get("DASHSCOPE_SIZE", "1024*1024"),
        "timeout": int(env.get("DASHSCOPE_TIMEOUT", "60")),
    }


# ── 提示词缓存（省额度）：相同 prompt+模型+参数 直接复用已生成的本地产物 ──
_IMAGE_CACHE_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "generated", "image_cache.json"
)
_VIDEO_CACHE_DIR = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "generated", "video_cache"
)
_image_cache: dict = {}


def _load_image_cache() -> None:
    global _image_cache
    try:
        with open(_IMAGE_CACHE_PATH, "r", encoding="utf-8") as handle:
            data = json.load(handle)
        _image_cache = data if isinstance(data, dict) else {}
    except (ValueError, OSError):
        _image_cache = {}


def _save_image_cache() -> None:
    try:
        os.makedirs(os.path.dirname(_IMAGE_CACHE_PATH), exist_ok=True)
        with open(_IMAGE_CACHE_PATH, "w", encoding="utf-8") as handle:
            json.dump(_image_cache, handle, ensure_ascii=False)
    except OSError:
        pass


_load_image_cache()


def _cache_key(*parts) -> str:
    return hashlib.sha1("|".join(str(p) for p in parts).encode("utf-8")).hexdigest()[:20]


def _keys_for(settings) -> list[str]:
    """主 Key + 备用 Key 池（去重保序）。"""

    keys = [settings.get("api_key")]
    keys += [k for k in (settings.get("api_key_pool") or []) if k]
    out, seen = [], set()
    for key in keys:
        if key and key not in seen:
            seen.add(key)
            out.append(key)
    return out


# Key 健康状态（本次运行内，重启清零）：完整 Key 作内部索引，对外只按
# 池内序号暴露状态。ok=可用 / quota=额度耗尽 / auth=无效 / 未调用=unknown
_KEY_HEALTH: dict[str, dict] = {}
_KEY_HEALTH_TTL = 6 * 3600.0


def note_key_outcome(key, ok, kind=None):
    """记录一把 Key 的最近一次调用结果（统计行为，永不抛错）。"""

    try:
        if not key:
            return
        if ok:
            _KEY_HEALTH[key] = {"status": "ok", "at": time.time()}
            return
        status = kind if kind in ("quota", "auth") else "error"
        prev = _KEY_HEALTH.get(key)
        # 暂时的网络/服务端错误不覆盖已有的额度/鉴权结论
        if status == "error" and prev and prev.get("status") in ("quota", "auth"):
            return
        _KEY_HEALTH[key] = {"status": status, "at": time.time()}
    except Exception:  # noqa: BLE001
        pass


def key_health_view(settings):
    """按「主 Key + 池序号」输出健康状态（永不回显 Key 本身）。"""

    keys = _keys_for(settings)
    now = time.time()
    statuses = []
    for key in keys:
        state = _KEY_HEALTH.get(key)
        if not state or now - state.get("at", 0) > _KEY_HEALTH_TTL:
            statuses.append("unknown")
        else:
            statuses.append(state.get("status", "unknown"))
    if not statuses:
        return {"primary": "unknown", "pool": []}
    return {"primary": statuses[0], "pool": statuses[1:]}


def _is_quota_error(exc) -> bool:
    """额度类错误判定：命中则自动切换 Key 池中的下一把重试。"""

    return classify_error(exc) == "quota"


# ── 错误分类：quota 额度/限流 / auth 鉴权 / moderation 内容审核 / network 网络 / fatal 其他 ──
_MODERATION_MARKERS = (
    "datainspectionfailed",
    "data inspection",
    "ipinfringement",
    "infringement",
    "sensitive",
    "moderation",
    "contentpolicy",
    "content policy",
    "inappropriate",
    "内容审核",
    "敏感",
    "风控",
    "审核未通过",
)
_AUTH_MARKERS = (
    "invalid_api_key",
    "invalidapikey",
    "invalid api key",
    "unauthorized",
    "authentication",
    "accessdenied",
    "access denied",
    "forbidden",
    "鉴权",
)
_QUOTA_MARKERS = (
    "arrearage",
    "arrears",
    "allocationquota",
    "quotaexceeded",
    "exceeded quota",
    "throttl",
    "ratelimit",
    "rate limit",
    "欠费",
    "额度",
)


def _error_text(exc) -> str:
    text = str(exc).lower()
    response = getattr(exc, "response", None)
    body = ""
    try:
        body = (response.text or "").lower()
    except Exception:  # noqa: BLE001
        pass
    return text + " " + body


def classify_error(exc) -> str:
    """把第三方模型调用异常归为五类之一，驱动重试与 Key 切换策略：

    * ``quota``      额度耗尽/限流/欠费（→ 切换 Key 池下一把）
    * ``auth``       Key 无效/鉴权失败（→ 切换下一把，本 Key 重试无意义）
    * ``moderation`` 内容审核拦截（→ 换 Key/换模型无意义，走安全改写重试）
    * ``network``    超时/连接失败/5xx（→ 幂等重试有望恢复）
    * ``fatal``      其余（模型不存在、参数错误等，原样上抛）
    """

    if exc is None:
        return "fatal"
    response = getattr(exc, "response", None)
    status = getattr(response, "status_code", 0)
    if isinstance(exc, httpx.TimeoutException) or isinstance(exc, httpx.TransportError):
        return "network"
    text = _error_text(exc)
    if status == 429 or any(m in text for m in _QUOTA_MARKERS):
        return "quota"
    if status == 401 or any(m in text for m in _AUTH_MARKERS):
        return "auth"
    if any(m in text for m in _MODERATION_MARKERS):
        return "moderation"
    if status >= 500:
        return "network"
    if status in (400, 403, 404, 422):
        # 403 若带审核语义上面已归类 moderation；其余 4xx 视为确定性失败
        return "fatal"
    return "fatal"


ERROR_LABELS = {
    "quota": "额度不足或触发限流（可在模型设置追加备用 Key）",
    "auth": "API Key 鉴权失败",
    "moderation": "内容审核未通过（源图或提示词触发平台风控）",
    "network": "网络超时或连接失败",
    "fatal": "",
}


def describe_error(exc) -> str:
    """把原始异常翻译成面向用户的中文一句话（fatal 保留原始信息）。"""

    kind = classify_error(exc)
    label = ERROR_LABELS.get(kind) or ""
    raw = str(exc).strip()
    if not label:
        return raw[:200] or "生成失败"
    if kind == "moderation":
        return label  # 审核响应体是一坨 JSON，对用户没有信息量
    return "{}：{}".format(label, raw[:140])


def image_failure_guidance(image_error) -> str:
    """strict 策略下生图失败的任务失败信息：具体原因 + 已尝试的自救动作
    + 下一步建议（按错误分类给出可操作指引）。"""

    kind = (image_error or {}).get("kind", "fatal")
    detail = (image_error or {}).get("detail") or "未知原因"
    if kind == "moderation":
        tried = "系统已自动把知名 IP 角色名/敏感词改写为视觉特征后重试，仍未通过平台审核"
        steps = (
            "建议：① 调整目标描述——去掉品牌/IP 名称或敏感表述，改用外观特征词"
            "（例：「哆啦A梦」→「蓝白色圆滚滚机器猫，脖子挂铃铛」）；"
            "② 生成记录可在「历史记录」一键重试；"
            "③ 如希望失败时仍产出离线示意资产，请在「模型设置 → 图像」开启「失败自动降级」。"
        )
    elif kind == "quota":
        tried = "已用尽 Key 池内全部备用 Key，额度/限流仍未恢复"
        steps = (
            "建议：① 在「模型设置」追加备用 API Key 或等待限流窗口过去；"
            "② 稍后在「历史记录」一键重试。"
        )
    elif kind == "auth":
        tried = "Key 池内所有 Key 鉴权均失败"
        steps = "建议：到「模型设置」检查 API Key 是否有效/过期，重新保存后再重试。"
    elif kind == "network":
        tried = "已尝试 Key 池内全部 Key，网络仍不可达"
        steps = "建议：检查本机网络与服务商地址可达性，恢复后在「历史记录」一键重试。"
    else:
        tried = "生图请求未成功"
        steps = "建议：到「智能体」事件流查看详细错误，调整目标后在「历史记录」一键重试。"
    return "AI 生图失败（{}）：{}。{}".format(detail, tried, steps)


# 安全改写：审核轮用的词表替换（正则词边界，大小写不敏感）+ 合规尾缀。
# i2v 提示词里的攻击性词汇（attack/strike/punch…）是审核拦截的常见诱因。
_SOFTEN_REPLACEMENTS = (
    (r"\battacks?\b", "practice form"),
    (r"\battacking\b", "performing a practice form"),
    (r"\bstrikes?\b", "controlled swing"),
    (r"\bstriking\b", "swinging in a controlled way"),
    (r"\bpunch(?:es|ing)?\b", "arm extension"),
    (r"\bkick(?:s|ing)?\b", "leg extension"),
    (r"\bslash(?:es|ing)?\b", "sweeping motion"),
    (r"\bstab(?:s|bing)?\b", "forward reach"),
    (r"\bsword\b|\bblade\b|\bblades\b", "prop"),
    (r"\bguns?\b|\bfirearms?\b", "prop"),
    (r"\bblood\w*\b|\bgore\b", "dramatic shading"),
    (r"\bweapon\w*\b", "prop"),
)

# 知名 IP 角色名 → 视觉特征描述（版权名是平台审核拦截的头号诱因，如
# 「哆啦A梦」直接命中 DashScope 风控）。改写原则：去掉 IP 名字、保留
# 视觉特征——过审的同时主题不丢。CJK 无词边界，用普通交替模式。
# 两档语义：
#   HARD——现代版权角色，平台基本必拦，送模型前**主动**替换（不浪费一轮
#          拦截，见 neutralize_hard_ip）；
#   SOFT ——古典/民间人物（孙悟空等），通常可过审，保留原文；只在审核
#          拦截后的安全改写轮一并替换。
_HARD_IP_REPLACEMENTS = (
    (r"哆啦A梦|多啦A梦|哆啦哆啦|叮当猫|[Dd]oraemon", "蓝白色圆滚滚机器猫，大圆眼睛，脖子挂铃铛"),
    (r"皮卡丘|[Pp]ikachu", "黄色电气鼠，闪电形尾巴，红色脸颊"),
    (r"樱桃小丸子", "红色贝雷帽的圆脸小学生女孩"),
    (r"蜡笔小新", "粗眉毛的调皮小男孩"),
    (r"Hello ?Kitty|凯蒂猫", "白色圆脸小猫，红色蝴蝶结，没有嘴巴"),
    (r"米老鼠|米奇|[Mm]ickey ?[Mm]ouse", "黑色大耳朵的小老鼠，红色短裤白手套"),
    (r"海绵宝宝|[Ss]ponge[Bb]ob", "黄色方形海绵，棕色短裤，红领带"),
)
_SOFT_IP_REPLACEMENTS = (
    (r"孙悟空", "金色毛发猴王，虎皮裙，金箍棒"),
)
_IP_REPLACEMENTS = _HARD_IP_REPLACEMENTS + _SOFT_IP_REPLACEMENTS
_SOFTEN_SUFFIX = (
    " Family-friendly stylized cartoon performance, purely athletic and non-violent, "
    "no blood, no gore, no realistic harm."
)


def neutralize_hard_ip(prompt: str) -> str:
    """送模型前的主动 IP 中性化：只替换 HARD 档现代版权角色名，不追加
    合规尾缀（保持用户提示词干净）。返回改写后的文本；调用方对比原文
    判断是否命中并透出事件。"""

    import re as _re

    softened = prompt
    for pattern, replacement in _HARD_IP_REPLACEMENTS:
        softened = _re.sub(pattern, replacement, softened)
    return softened


def _soften_prompt(prompt: str) -> str:
    """把提示词里的高风险词替换成中性表达并追加合规尾缀（审核重试轮）。

    攻击性词汇与知名 IP 角色名（HARD+SOFT 全档）都替换为中性/视觉化
    表达；尾缀总是追加，因此有拦截词时结果必然有变化。"""

    import re as _re

    softened = prompt
    for pattern, replacement in _SOFTEN_REPLACEMENTS:
        softened = _re.sub(pattern, replacement, softened, flags=_re.IGNORECASE)
    for pattern, replacement in _IP_REPLACEMENTS:
        softened = _re.sub(pattern, replacement, softened)
    if _SOFTEN_SUFFIX.strip() not in softened:
        softened = softened.rstrip() + _SOFTEN_SUFFIX
    return softened


PROVIDER_PRESETS = {
    "openai": {
        "label": "OpenAI",
        "base_url": "https://api.openai.com/v1",
        "chat_model": "gpt-4o-mini",
        "model": "gpt-image-1",
        "note": "官方 API，密钥以 sk- 开头；图像模型为 gpt-image-1。",
    },
    "dashscope": {
        "label": "阿里云百炼 DashScope",
        "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "chat_model": "qwen3-omni-flash",
        "model": "wanx2.1-t2i-turbo",
        "note": "兼容模式；密钥在百炼控制台「API-KEY」创建（sk- 开头）。新账号免费额度以控制台模型列表为准（常用：qwen3-omni-flash 对话 + wanx2.1-t2i-turbo 生图）。",
    },
    "volcengine": {
        "label": "豆包 · 火山方舟",
        "base_url": "https://ark.cn-beijing.volces.com/api/v3",
        "chat_model": "doubao-1-5-pro-32k",
        "model": "doubao-seedream-3-0-t2i",
        "note": "模型 ID 以方舟开通页为准（也可填推理接入点 ep-xxx）；图像为 Seedream 文生图。",
    },
    "zhipu": {
        "label": "智谱 GLM",
        "base_url": "https://open.bigmodel.cn/api/paas/v4",
        "chat_model": "glm-4-flash",
        "model": "cogview-3-flash",
        "note": "glm-4-flash 与 cogview-3-flash 均有免费额度；密钥在智谱开放平台「API 密钥」获取。",
    },
    "siliconflow": {
        "label": "硅基流动 SiliconFlow",
        "base_url": "https://api.siliconflow.cn/v1",
        "chat_model": "deepseek-ai/DeepSeek-V3",
        "model": "Kwai-Kolors/Kolors",
        "note": "聚合平台；图像为 Kolors，聊天可选 DeepSeek / Qwen 系列。",
    },
    "windup": {
        "label": "Windup",
        "base_url": "",
        "chat_model": "",
        "model": "",
        "style": "anime",
        "note": "自定义 / 手动填写兼容 OpenAI 协议的服务地址。",
    },
}


def safe_generated_path(name):
    """Resolve a generated-image filename to an absolute path inside
    ``GENERATED_DIR`` (never outside it), or ``None`` if unavailable."""

    if not name:
        return None
    name = os.path.basename(str(name))
    if not name or name in (".", ".."):
        return None
    if not name.lower().endswith((".png", ".jpg", ".jpeg", ".webp")):
        return None
    path = os.path.join(GENERATED_DIR, name)
    if not os.path.isfile(path):
        return None
    return path


class ModelSettingsStore:
    _DEFAULTS = {
        "enabled": False,
        "provider": "openai",
        "base_url": "",
        "api_key": "",
        # 能力 → 模型：文本 / 图像 / 图像编辑 / 视频共用同一套 base_url + api_key
        "model": "",  # 图像生成（原画）
        "chat_model": "",  # 文本 / 对话（提示词增强）
        "vl_model": "qwen-vl-plus",  # 视觉对话（装备/服装识别）：看图输出结构化 JSON
        "edit_model": "",  # 图像编辑（抠图 / 风格迁移 / 发层）；留空用服务商默认
        # 三视图是固定模型 TURNAROUND_EDIT_MODEL（qwen-image-2.1-turbo），不受此项控制
        "video_model": "",  # 视频 / 图生视频（当前仅 DashScope）
        # 历史双档字段：视频模型已固定为 VIDEO_MODEL（flash 档），
        # 本项仅为兼容旧配置保留，不参与实际请求
        "video_model_final": "wan2.2-i2v-flash",
        "use_chat": True,
        "use_image": True,
        "use_video": True,
        "size": "1024x1024",
        "negative_prompt": (
            "lowres, bad anatomy, bad hands, extra fingers, missing fingers, "
            "fused fingers, worst quality, low quality, jpeg artifacts, watermark, "
            "signature, blurry, deformed, bad proportions"
        ),
        "seed": "",
        "prompt_extend": False,
        "watermark": False,
        "video_size": "1280*720",
        "video_prompt_extend": False,
        "video_ai_enhance": True,  # 动作描述 AI 增强：对话模型润色 i2v 动作提示词（失败自动回退原模板）
        "timeout": 60,
        "style": "pixel",
        "api_key_pool": [],  # 备用 Key 池：额度类错误自动切换下一把
        # 生图失败策略（IP/审核拦截等，自救轮之后仍失败时生效）：
        #   strict  = 任务失败并返回原因与建议（默认——不静默产出无关的离线示意）
        #   degrade = 自动降级为离线示意资产（带 model_fallback 标记与徽章）
        "image_fallback_policy": "strict",
    }

    def __init__(self, path=None):
        self.path = path or DEFAULT_SETTINGS_PATH
        self._lock = threading.Lock()
        self._data = dict(self._DEFAULTS)
        self._load()

    def _load(self):
        data = read_json_recover(self.path)
        if isinstance(data, dict):
            self._data.update({k: v for k, v in data.items() if k in self._DEFAULTS})

    def _save(self):
        try:
            atomic_write_json(self.path, self._data)
        except OSError:
            pass

    def effective(self):
        """生效配置：用户显式保存的优先；未配 api_key 时回落 .env（百炼兜底）。"""
        with self._lock:
            data = dict(self._data)
        if not data.get("api_key"):
            override = _dashscope_env_override()
            if override:
                data.update(override)
        return data

    def public(self):
        """脱敏视图（不回显 api_key）；.env 兜底启用时也反映启用状态。"""
        with self._lock:
            data = dict(self._data)
            pool = data.get("api_key_pool") or []
            data["api_key_pool"] = [
                (k[:8] + "…" + k[-4:]) if len(k) > 14 else "…" for k in pool
            ]
            data["api_key_pool_size"] = len(pool)
        if not data.get("api_key"):
            override = _dashscope_env_override()
            if override:
                data.update(override)
        key = data.get("api_key") or ""
        hint = ""
        if key:
            hint = "{}****{}".format(key[:3], key[-4:]) if len(key) > 8 else "****"
        data["key_health"] = key_health_view(data)
        data.pop("api_key", None)
        data["has_key"] = bool(key)
        data["key_hint"] = hint
        return data

    def update(self, changes):
        with self._lock:
            append_keys = (
                changes.pop("api_key_pool_add")
                if isinstance(changes, dict) and isinstance(changes.get("api_key_pool_add"), list)
                else None
            )
            remove_indexes = (
                changes.pop("api_key_pool_remove")
                if isinstance(changes, dict) and isinstance(changes.get("api_key_pool_remove"), list)
                else None
            )
            for key, value in (changes or {}).items():
                if key in self._DEFAULTS:
                    self._data[key] = value
            if append_keys:
                pool = [k for k in (self._data.get("api_key_pool") or []) if k]
                primary = self._data.get("api_key")
                for key in append_keys:
                    key = str(key).strip()
                    if key and key != primary and key not in pool:
                        pool.append(key)
                self._data["api_key_pool"] = pool
            if remove_indexes:
                # 按池内序号移除（UI 只拿到脱敏回显，无法按明文匹配）
                pool = [k for k in (self._data.get("api_key_pool") or []) if k]
                drop = set()
                for index in remove_indexes:
                    try:
                        drop.add(int(index))
                    except (TypeError, ValueError):
                        continue
                self._data["api_key_pool"] = [
                    k for i, k in enumerate(pool) if i not in drop
                ]
            self._save()
        return self.public()

    def clear_key(self):
        with self._lock:
            self._data["api_key"] = ""
            self._save()
        return self.public()


def _http_error(exc):
    """Unwrap an httpx status error into a message that carries the
    provider's own response body (so 403/404 show the real reason)."""

    response = getattr(exc, "response", None)
    if response is not None:
        detail = response.text[:220]
        return RuntimeError("HTTP {} {}: {}".format(response.status_code, exc.request.url, detail))
    return exc


def poll_video_task(api_key, task_id, timeout_seconds):
    """Poll a DashScope i2v task without discarding an accepted job on a blip.

    The video task has already been accepted by DashScope when this function is
    entered.  A transient timeout while *asking for its status* must therefore
    not be treated as a failed generation (nor cause the caller to submit an
    expensive duplicate task).  Keep polling until the end-to-end budget is
    spent; authentication and terminal provider states still fail immediately.
    """

    deadline = time.time() + timeout_seconds
    last_transport_error = None
    while time.time() < deadline:
        try:
            poll = httpx.get(
                DASHSCOPE_HOST + "/api/v1/tasks/" + task_id,
                headers={"Authorization": "Bearer " + api_key},
                timeout=30,
            )
        except (httpx.TimeoutException, httpx.TransportError) as exc:
            last_transport_error = exc
            # Do not re-submit a task that may already be rendering remotely.
            time.sleep(min(5, max(0.2, deadline - time.time())))
            continue
        if poll.status_code in (401, 403):
            raise RuntimeError(
                "dashscope task poll unauthorized: HTTP {}".format(poll.status_code)
            )
        if poll.status_code == 404:
            raise RuntimeError("dashscope task not found: " + task_id)
        body = poll.json() if poll.status_code < 500 else {}
        output = body.get("output") or {}
        status = output.get("task_status")
        if status == "SUCCEEDED":
            url = output.get("video_url") or ((output.get("results") or [{}])[0].get("url"))
            if not url:
                raise RuntimeError("dashscope video task succeeded without video_url")
            return url
        if status in ("FAILED", "CANCELED", "UNKNOWN"):
            message = output.get("message") or status
            raise RuntimeError("dashscope video task {}: {}".format(task_id, message))
        time.sleep(min(5, max(0.2, deadline - time.time())))
    if last_transport_error is not None:
        raise RuntimeError(
            "dashscope video task timeout after transient network errors: {} ({})".format(
                task_id, str(last_transport_error)[:120]
            )
        )
    raise RuntimeError("dashscope video task timeout: " + str(task_id))


# 帧粘连抑制的代码级默认项（wan 系模型中文负面提示词生效最好）：覆盖
# 残影叠加（重影/残影/拖影/双重曝光/鬼影）、肢体分裂（肢体分裂/多余肢体）、
# 形变与闪烁（形变破碎/画面闪烁）三大类实测伪影。
DEFAULT_VIDEO_NEGATIVE_PROMPT = (
    "重影, 残影, 拖影, 双重曝光, 鬼影, 肢体分裂, 多余肢体, 形变破碎, 画面闪烁"
)

# 动画工作台 / 试玩舞台（单动作 / 批量补齐）统一固定的视频模型。
# video_model、video_model_final 与 model_override 一律不参与实际请求，
# 也不做 plus / turbo 自动回退：保证请求、缓存 key、任务元数据与用量账单
# 口径一致。
VIDEO_MODEL = "wan2.2-i2v-flash"


def _video_negative_prompt(settings) -> str:
    """最终负面提示词：用户配置优先，代码默认项去重后追加。"""

    user = str((settings or {}).get("negative_prompt") or "").strip()
    if not user:
        return DEFAULT_VIDEO_NEGATIVE_PROMPT
    extras = [t.strip() for t in DEFAULT_VIDEO_NEGATIVE_PROMPT.split(",") if t.strip() not in user]
    return ", ".join([user] + extras)


def generate_video(settings, prompt, image_bytes, timeout_seconds=420.0, model_override=None):
    """图生视频 (Windup 式 i2v 路线): source image + motion prompt -> mp4 bytes.

    视频模型固定为 ``VIDEO_MODEL``（wan2.2-i2v-flash）：``model_override``、
    ``settings['video_model']`` 与 ``settings['video_model_final']`` 均不再
    影响实际请求，也不会自动回退到 plus / turbo。返回 ``(video_bytes,
    model_name)``，model_name 恒为固定模型。

    ``model_override``：仅为旧调用方兼容保留，已忽略。"""
    api_key = settings.get("api_key")
    if not api_key:
        raise RuntimeError("自定义模型未启用，无法使用 AI 视频驱动")

    # 帧粘连抑制（代码级默认负面提示词）：i2v 在关节快速运动时常见"上一帧
    # 姿态残影叠加到下一帧、肢体分裂成双重轮廓"伪影。主提示词只写正向句
    # （Windup _framing 纪律），残影类伪影统一交给 negative_prompt 参数抑制
    # ——这正是该参数的用途。用户配置的 negative_prompt 优先、默认项去重后
    # 追加；最终串必须参与视频缓存 key（见下）。
    negative_prompt = _video_negative_prompt(settings)

    # 视频缓存：相同 提示词+模型+源图+负面词+生成参数 直接复用已生成的 mp4
    # （视频是额度大头）。负面提示词必须参与 key：同 prompt 不同 negative
    # 共用旧 key 会让新加的伪影抑制静默失效（命中未抑制的旧缓存），不同
    # 配置间还会互相覆盖缓存。同理 size 与 prompt_extend 也必须入 key。
    # 模型分量取固定的 VIDEO_MODEL——配置怎么写都只有同一档缓存。
    requested_model = VIDEO_MODEL
    video_key = _cache_key(
        prompt,
        requested_model,
        hashlib.sha1(image_bytes).hexdigest(),
        hashlib.sha1(negative_prompt.encode("utf-8")).hexdigest(),
        "size={}|ext={}".format(
            settings.get("video_size") or "1280*720",
            bool(settings.get("video_prompt_extend", False)),
        ),
    )
    cached_path = os.path.join(_VIDEO_CACHE_DIR, video_key + ".mp4")
    if os.path.isfile(cached_path):
        with open(cached_path, "rb") as handle:
            return handle.read(), requested_model
    # 单一模型链：不再按 video_model / video_model_final 回退到 plus / turbo，
    # 额度或鉴权错误只换 Key（见下方 Key 池循环），不换模型。
    models = [VIDEO_MODEL]
    encoded = base64.b64encode(image_bytes).decode()
    parameters = {
        "size": settings.get("video_size") or "1280*720",
        "prompt_extend": bool(settings.get("video_prompt_extend", False)),
        "watermark": False,
        "negative_prompt": negative_prompt,
    }

    def _create(key, model, prompt_now):
        # Async-task creation has no idempotency token. Retry transport blips a
        # bounded number of times here instead of letting one DNS/reset error
        # abort the whole model fallback chain.
        delays = (1.0, 2.0, 4.0)
        for attempt in range(len(delays) + 1):
            try:
                return httpx.post(
                    DASHSCOPE_HOST + "/api/v1/services/aigc/video-generation/video-synthesis",
                    headers={
                        "Authorization": "Bearer " + key,
                        "Content-Type": "application/json",
                        "X-DashScope-Async": "enable",
                    },
                    json={
                        "model": model,
                        "input": {
                            "prompt": prompt_now,
                            "img_url": "data:image/png;base64," + encoded,
                        },
                        "parameters": parameters,
                    },
                    # Creating an async task should be quick, but gateways sometimes
                    # queue the acknowledgement. Honour the configured network budget
                    # and never use a shorter-than-one-minute connect/read window.
                    timeout=max(60.0, float(settings.get("timeout", 60))),
                )
            except (httpx.TimeoutException, httpx.TransportError):
                if attempt == len(delays):
                    raise
                time.sleep(delays[attempt])

    # 两轮策略：第 1 轮原始提示词；若被内容审核拦截，第 2 轮用安全改写
    # （高风险词中性化 + 合规尾缀）整体重试一遍——审核失败换 Key/换模型
    # 都无意义，只浪费调用次数。
    last_error = None
    moderation_error = None
    for safe_round in (False, True):
        if safe_round:
            if moderation_error is None:
                break
            prompt_now = _soften_prompt(prompt)
        else:
            prompt_now = prompt
        hit_moderation = False
        for attempt_key in _keys_for(settings):
            # Key 池：额度/鉴权类错误自动切换下一把（模型候选链对每把 Key 完整重试）
            for model in models:
                create = _create(attempt_key, model, prompt_now)
                if create.status_code >= 400:
                    err = RuntimeError(
                        "HTTP {} ({}): {}".format(create.status_code, model, create.text[:220])
                    )
                    kind = classify_error(err)
                    if kind in ("quota", "auth"):
                        note_key_outcome(attempt_key, False, kind)
                    if kind == "moderation":
                        if not safe_round:
                            moderation_error = moderation_error or err
                        hit_moderation = True
                        break
                    if kind in ("quota", "auth"):
                        last_error = err
                        # Auth failure applies to every model for this Key. Quota
                        # is model-scoped on DashScope free tiers, so keep walking
                        # the fallback chain before moving to another Key.
                        if kind == "auth":
                            break
                        continue
                    last_error = err
                    continue
                task_id = (create.json().get("output") or {}).get("task_id")
                if not task_id:
                    last_error = RuntimeError("dashscope: no task_id in response")
                    continue
                url = poll_video_task(attempt_key, task_id, timeout_seconds)
                video = httpx.get(url, timeout=120)
                video.raise_for_status()
                from studio.backend.model_service.usage import record_usage

                record_usage("video", model)
                note_key_outcome(attempt_key, True)
                try:
                    os.makedirs(_VIDEO_CACHE_DIR, exist_ok=True)
                    with open(cached_path, "wb") as handle:
                        handle.write(video.content)
                except OSError:
                    pass
                return video.content, model
            if hit_moderation:
                break
    # 审核拦截优先呈现（安全改写轮失败时它是真正的根因）；其余取最后一次错误
    raise moderation_error or last_error or RuntimeError("video generation failed")


def poll_dashscope_task(api_key, task_id, timeout_seconds):
    """Poll a DashScope async task until it finishes; returns the result URL."""

    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        poll = httpx.get(
            DASHSCOPE_HOST + "/api/v1/tasks/" + task_id,
            headers={"Authorization": "Bearer " + api_key},
            timeout=30,
        )
        if poll.status_code in (401, 403):
            raise RuntimeError(
                "dashscope task poll unauthorized: HTTP {}".format(poll.status_code)
            )
        if poll.status_code == 404:
            raise RuntimeError("dashscope task not found: " + task_id)
        body = poll.json() if poll.status_code < 500 else {}
        status = (body.get("output") or {}).get("task_status")
        if status == "SUCCEEDED":
            results = (body.get("output") or {}).get("results") or []
            url = (results[0] or {}).get("url")
            if not url:
                raise RuntimeError("dashscope task succeeded without result url")
            return url
        if status in ("FAILED", "CANCELED", "UNKNOWN"):
            message = (body.get("output") or {}).get("message") or status
            raise RuntimeError("dashscope task {}: {}".format(task_id, message))
        time.sleep(2)
    raise RuntimeError("dashscope task timeout: " + str(task_id))


class ChatProvider:
    """OpenAI-compatible chat completion (prompt enhancement / motion rewrite)."""

    def __init__(self, settings):
        self.settings = settings or {}

    def chat(self, system, user, temperature=0.6):
        """Single-round chat completion (key-pool aware). Returns
        ``{"model", "content"}``. 额度/鉴权/网络类错误切下一把 Key，
        确定性失败原样上抛。"""

        base_url = (self.settings.get("base_url") or "").rstrip("/")
        model = self.settings.get("chat_model") or self.settings.get("model")
        if not base_url or not self.settings.get("api_key") or not model:
            raise RuntimeError("chat provider not configured")
        last_error = None
        for key in _keys_for(self.settings):
            # 第一段：请求本身。额度/鉴权/网络类错误才换下一把 Key，
            # 确定性失败（参数、模型名错误等）原样上抛
            try:
                response = httpx.post(
                    base_url + "/chat/completions",
                    headers={
                        "Authorization": "Bearer " + key,
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": model,
                        "messages": [
                            {"role": "system", "content": system},
                            {"role": "user", "content": str(user)},
                        ],
                        "temperature": temperature,
                    },
                    timeout=float(self.settings.get("timeout", 60)),
                )
                response.raise_for_status()
            except httpx.HTTPStatusError as exc:
                note_key_outcome(key, False, classify_error(exc))
                if classify_error(exc) in ("quota", "auth", "network"):
                    last_error = exc
                    continue
                raise _http_error(exc)
            except httpx.HTTPError as exc:  # 连接/超时等网络类
                note_key_outcome(key, False, classify_error(exc))
                last_error = exc
                continue
            # 第二段：解析。响应结构异常与 Key 无关，直接上抛不烧 Key 池
            try:
                content = response.json()["choices"][0]["message"]["content"]
            except (KeyError, IndexError, ValueError, TypeError) as exc:
                raise RuntimeError(
                    "chat 响应结构异常：{}".format(str(exc)[:120])
                ) from exc
            from studio.backend.model_service.usage import record_usage

            record_usage("chat", model)
            note_key_outcome(key, True)
            return {"model": model, "content": content.strip()}
        raise last_error or RuntimeError("chat completion failed")

    def enhance(self, goal, spec, overrides=None):
        system = (
            "You rewrite a game-asset request into ONE concise image-generation prompt. "
            "IMPORTANT: reply in the SAME language as the user's request "
            "(if the user writes Chinese, output Chinese; if English, output English). "
            "Rules: strictly follow the style the user asks for "
            "(anime / pixel / 3d / realistic ...); if unspecified, use the natural default. "
            "Do NOT impose a fixed style; do NOT mention artist names, studios or copyrighted IP. "
            "Keep concrete attributes (gender, age, hair, outfit, accessories, pose, colors). "
            "Keep it short (<=120 words / ~120 汉字). "
            "Output only the prompt text — no markdown, no explanation."
        )
        result = self.chat(system, goal, temperature=0.6)
        return {"model": result["model"], "prompt": result["content"]}


class VisionChatProvider:
    """OpenAI-compatible multimodal chat（视觉语言模型，看图 → 结构化文本）.

    装备/服装识别走这里：请求体 content 为多段列表（image_url data URL +
    text），与 ChatProvider 共用同一套 Key 池与错误分级。系统提示合入
    user 文本段发送——部分视觉模型（qwen-vl 原生）不支持 system 角色，
    合入后两种网关都能稳定工作。
    """

    def __init__(self, settings):
        self.settings = settings or {}

    def chat(self, system, user, image_b64, temperature=0.2):
        """单轮图文对话。``image_b64`` 为纯 base64（不带 data: 前缀）或完整
        data URL。返回 ``{"model", "content"}``；额度/鉴权/网络类错误切下一
        把 Key，确定性失败原样上抛。"""

        base_url = (self.settings.get("base_url") or "").rstrip("/")
        model = self.settings.get("vl_model") or "qwen-vl-plus"
        if not base_url or not _keys_for(self.settings) or not model:
            raise RuntimeError("vision chat provider not configured")
        if image_b64.startswith("data:"):
            data_url = image_b64
        else:
            data_url = "data:image/png;base64," + image_b64
        last_error = None
        for key in _keys_for(self.settings):
            try:
                response = httpx.post(
                    base_url + "/chat/completions",
                    headers={
                        "Authorization": "Bearer " + key,
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": model,
                        "messages": [
                            {
                                "role": "user",
                                "content": [
                                    {"type": "image_url", "image_url": {"url": data_url}},
                                    {"type": "text", "text": str(system) + "\n\n" + str(user)},
                                ],
                            }
                        ],
                        "temperature": temperature,
                    },
                    timeout=float(self.settings.get("timeout", 60)),
                )
                response.raise_for_status()
            except httpx.HTTPStatusError as exc:
                note_key_outcome(key, False, classify_error(exc))
                if classify_error(exc) in ("quota", "auth", "network"):
                    last_error = exc
                    continue
                raise _http_error(exc)
            except httpx.HTTPError as exc:  # 连接/超时等网络类
                note_key_outcome(key, False, classify_error(exc))
                last_error = exc
                continue
            try:
                content = response.json()["choices"][0]["message"]["content"]
            except (KeyError, IndexError, ValueError, TypeError) as exc:
                raise RuntimeError(
                    "vision chat 响应结构异常：{}".format(str(exc)[:120])
                ) from exc
            from studio.backend.model_service.usage import record_usage

            record_usage("chat", model)
            note_key_outcome(key, True)
            return {"model": model, "content": content.strip()}
        raise last_error or RuntimeError("vision chat completion failed")


DASHSCOPE_HOST = "https://dashscope.aliyuncs.com"


class ImageProvider:
    """Image generation + connectivity test.

    Speaks the OpenAI-compatible ``/images/generations`` contract, with a
    native DashScope branch: wanx image models are asynchronous there
    (create task -> poll -> fetch result URL) and have no compatible route.
    """

    def __init__(self, settings):
        self.settings = settings or {}

    def _is_dashscope(self):
        return "dashscope.aliyuncs.com" in (self.settings.get("base_url") or "")

    def _headers(self):
        return {
            "Authorization": "Bearer " + (self.settings.get("api_key") or ""),
            "Content-Type": "application/json",
        }

    def _generate_dashscope(self, prompt):
        """Native DashScope flow for wanx models: async task create -> poll
        -> download the result image."""

        api_key = self.settings.get("api_key")
        timeout = float(self.settings.get("timeout", 60))
        size = (self.settings.get("size") or "1024*1024").replace("x", "*").replace("X", "*")
        parameters = {
            "size": size,
            "n": 1,
            "watermark": bool(self.settings.get("watermark", False)),
        }
        if self.settings.get("negative_prompt"):
            parameters["negative_prompt"] = self.settings["negative_prompt"]
        if self.settings.get("prompt_extend") is not None:
            parameters["prompt_extend"] = bool(self.settings.get("prompt_extend"))
        seed = str(self.settings.get("seed", "")).strip()
        if seed not in ("", "None"):
            try:
                parameters["seed"] = int(seed)
            except ValueError:
                pass
        create = httpx.post(
            DASHSCOPE_HOST + "/api/v1/services/aigc/text2image/image-synthesis",
            headers={
                "Authorization": "Bearer " + api_key,
                "X-DashScope-Async": "enable",
                "Content-Type": "application/json",
            },
            json={
                "model": self.settings.get("model"),
                "input": {"prompt": prompt},
                "parameters": parameters,
            },
            timeout=timeout,
        )
        try:
            create.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise _http_error(exc)
        task_id = (create.json().get("output") or {}).get("task_id")
        if not task_id:
            raise RuntimeError("dashscope: no task_id in response")

        url = poll_dashscope_task(api_key, task_id, max(120.0, timeout * 3))
        os.makedirs(GENERATED_DIR, exist_ok=True)
        file_name = "img_{}.png".format(int(time.time() * 1000))
        image_response = httpx.get(url, timeout=60)
        with open(os.path.join(GENERATED_DIR, file_name), "wb") as handle:
            handle.write(image_response.content)
        return {"file": file_name, "url": url, "model": self.settings.get("model")}

    def generate(self, prompt):
        if (
            not (self.settings.get("base_url") or "").rstrip("/")
            or not self.settings.get("api_key")
            or not self.settings.get("model")
        ):
            raise RuntimeError("image provider not configured")

        # 提示词缓存：相同 prompt+模型+尺寸 直接复用本地产物（省额度）
        cache_key = _cache_key(
            prompt, self.settings.get("model"), self.settings.get("size"),
            self.settings.get("negative_prompt", ""), self.settings.get("seed", ""),
        )
        cached = _image_cache.get(cache_key)
        if cached and os.path.isfile(cached.get("path", "")):
            name = os.path.basename(cached["path"])
            return {
                "file": name,
                "url": "/api/generated/" + name,
                "model": cached.get("model") or self.settings.get("model"),
                "cached": True,
            }

        from studio.backend.model_service.usage import record_usage

        # 两轮策略（与视频链路 generate_video 同款）：第 1 轮原始提示词；
        # 若被内容审核拦截（版权 IP/敏感词是常见诱因，如「哆啦A梦」），
        # 第 2 轮用 _soften_prompt 中性化改写（IP 名→视觉特征 + 合规尾缀）
        # 整体重试——审核失败换 Key/换模型无意义，改写重试才是正解。
        moderation_error = None
        last_error = None
        prompt_now = prompt
        for safe_round in (False, True):
            if safe_round:
                if moderation_error is None:
                    break
                prompt_now = _soften_prompt(prompt)
            else:
                prompt_now = prompt
            for key in _keys_for(self.settings):
                scoped = {**self.settings, "api_key": key}
                try:
                    if ImageProvider(scoped)._is_dashscope():
                        result = ImageProvider(scoped)._generate_dashscope(prompt_now)
                    else:
                        result = ImageProvider(scoped)._generate_openai_compat(prompt_now)
                except Exception as exc:  # noqa: BLE001
                    note_key_outcome(key, False, classify_error(exc))
                    kind = classify_error(exc)
                    if kind == "moderation":
                        # 记录根因并跳出 Key 池，进入安全改写轮
                        if not safe_round:
                            moderation_error = moderation_error or exc
                        break
                    if kind in ("quota", "auth", "network"):
                        last_error = exc
                        continue
                    raise
                record_usage("image", result.get("model") or scoped.get("model"))
                note_key_outcome(key, True)
                if result.get("file"):
                    path = os.path.join(GENERATED_DIR, os.path.basename(result["file"]))
                    if os.path.isfile(path):
                        _image_cache[cache_key] = {"path": path, "model": result.get("model")}
                        _save_image_cache()
                if prompt_now != prompt:
                    # 供上层透出「已自动改写提示词」事件，避免用户察觉不到改写
                    result["softened"] = True
                    result["prompt_used"] = prompt_now
                return result
        # 审核拦截优先呈现（安全改写轮仍失败时它是真正的根因）
        raise moderation_error or last_error or RuntimeError("image generation failed")

    def _generate_openai_compat(self, prompt):
        base_url = (self.settings.get("base_url") or "").rstrip("/")
        model = self.settings.get("model")
        os.makedirs(GENERATED_DIR, exist_ok=True)
        response = httpx.post(
            base_url + "/images/generations",
            headers=self._headers(),
            json={
                "model": model,
                "prompt": prompt,
                "n": 1,
                "size": self.settings.get("size", "512x512"),
            },
            timeout=float(self.settings.get("timeout", 60)),
        )
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise _http_error(exc)
        data = response.json()
        item = (data.get("data") or [{}])[0]
        url = item.get("url")
        encoded = item.get("b64_json")
        file_name = None
        if encoded:
            file_name = "img_{}.png".format(int(time.time() * 1000))
            with open(os.path.join(GENERATED_DIR, file_name), "wb") as handle:
                handle.write(base64.b64decode(encoded))
        elif url:
            # URL-based providers: pull the image locally so PReCon can read it
            file_name = "img_{}.png".format(int(time.time() * 1000))
            image_response = httpx.get(url, timeout=float(self.settings.get("timeout", 60)))
            image_response.raise_for_status()
            with open(os.path.join(GENERATED_DIR, file_name), "wb") as handle:
                handle.write(image_response.content)
        return {
            "file": file_name,
            "url": url or ("/api/generated/" + file_name if file_name else None),
            "model": model,
        }

    def test(self):
        base_url = (self.settings.get("base_url") or "").rstrip("/")
        if not base_url or not self.settings.get("api_key"):
            return {"ok": False, "detail": "not configured"}
        try:
            response = httpx.get(
                base_url + "/models",
                headers=self._headers(),
                timeout=float(self.settings.get("timeout", 60)),
            )
            if response.status_code < 400:
                return {"ok": True, "status": response.status_code}
            if response.status_code in (404, 405, 501):
                # 部分服务商（方舟 / 智谱等）不提供 GET /models，能路由到网关即视为可达
                return {
                    "ok": True,
                    "status": response.status_code,
                    "detail": "服务可达（该服务商不支持 /models，未做鉴权深度验证）",
                }
            return {"ok": False, "status": response.status_code}
        except Exception as exc:  # noqa: BLE001 - degrade gracefully
            return {"ok": False, "detail": str(exc)}


# 一次生成 side + back：以原画为参考，输出横向双栏转面设定图，本地裁切。
TURNAROUND_SHEET_PROMPT = (
    "以参考图中的角色为唯一身份依据，生成一张双栏角色正交转面设定图。\n\n"
    "左栏：同一个角色的正右侧 90° 全身侧面像，角色面朝画面右侧，单眼、侧脸轮廓、"
    "鼻尖、下巴、身体厚度和背部轮廓清晰可见，双臂和双腿完整，双脚完整露出并朝右；"
    "鼻尖、面部和脚尖都明确指向画面右侧。\n\n"
    "右栏：同一个角色的正后方 180° 全身背面像，角色背对镜头，只可见后脑勺、发型背面、"
    "背部服装和背部结构，完全不可见眼睛、鼻子、嘴巴和面部。\n\n"
    "两栏必须是同一个角色，保持相同的发型、发色、服装、配色、武器、配饰、体型和身高比例。\n\n"
    "两栏人物均从头到脚完整入画，头顶、双手、双腿和双脚不被裁切；\n"
    "两栏人物使用相同比例和脚底基准线，各自在栏内居中；\n"
    "两栏之间保留白色间隔，人物互不重叠；\n"
    "纯白背景，无文字、无边框、无场景、无其他人物。"
)

# PVE 敌人可能是菌类、甲壳、根系等非人形生物，沿用角色的「单眼 / 双臂双腿」描述
# 会诱导模型补出原本不存在的肢体，因此单独使用一版生物向提示词。
PVE_TURNAROUND_SHEET_PROMPT = (
    "以参考图中的怪物为唯一身份依据，生成一张双栏怪物正交转面设定图。\n\n"
    "左栏：同一个怪物的正右侧 90° 全身侧面像，怪物面朝画面右侧，完整保留其原有身体结构、"
    "肢体数量、器官、菌盖、甲壳、翅膀、尾巴、根系、配色和体型比例；"
    "该怪物原本没有的肢体不得凭空增加。侧脸轮廓、肢体厚度和背部轮廓清晰可见，"
    "所有肢体完整入画。\n\n"
    "右栏：同一个怪物的正后方 180° 全身背面像，怪物背对镜头，只可见背部、背部甲壳、"
    "菌盖背面、尾巴或根系结构，完全不可见眼睛、面部和口部正面。\n\n"
    "两栏必须是同一个怪物，保持相同的体型、身高比例、配色、材质和所有识别特征。\n\n"
    "两栏怪物均从头到脚（或到最低肢体 / 根系）完整入画，头顶、菌盖、肢体、尾巴和根系不被裁切；\n"
    "两栏使用相同比例和底部基准线，各自在栏内居中；两栏之间保留白色间隔，互不重叠；\n"
    "纯白背景，无文字、无边框、无场景、无其他怪物。"
)


class TurnaroundError(RuntimeError):
    """三视图生成失败：携带可直接展示给用户的真实原因。"""


# 三视图专用编辑模型：视角变换指令跟随更强。只在 generate_turnaround 里通过
# scoped settings 显式指定，其它编辑链路（风格迁移 / 抠图 / 发层）仍沿用
# 用户配置的 edit_model 或 ImageEditProvider 默认模型。
TURNAROUND_EDIT_MODEL = "qwen-image-2.1-turbo"
TURNAROUND_VIEW_MIN_SIDE = 96  # 单侧裁切图最小宽高（px）
TURNAROUND_VIEW_BLANK_RATIO = 0.003  # 非白像素占比低于该值视为空白图

# 用户上传的人物正面图：复用生图产物目录与 /api/generated 代理。文件名前缀
# reference_ 用于区分模型产物，并让孤儿文件清理只处理本功能自己的文件。
REFERENCE_EDIT_MODEL = TURNAROUND_EDIT_MODEL
MAX_REFERENCE_BYTES = 10 * 1024 * 1024
_REFERENCE_MIMES = {
    "PNG": ("image/png", "png"),
    "JPEG": ("image/jpeg", "jpg"),
    "WEBP": ("image/webp", "webp"),
}


class ImageEditProvider:
    """Image edit for the turnaround views (side / back of the same character).

    Default model ``qwen-image-edit`` (multimodal-generation, sync): follows
    viewpoint-change instructions. Falls back to the wanx2.1 description_edit
    async flow when qwen is unavailable for the account.
    """

    QWEN_EDIT_MODEL = "qwen-image-edit"
    WANX_EDIT_MODEL = "wanx2.1-imageedit"
    EDIT_MODEL = QWEN_EDIT_MODEL

    def __init__(self, settings):
        self.settings = settings or {}

    def edit(self, base_image_url, instruction, poll_timeout=180.0, allow_wanx_fallback=True):
        """编辑图片；``allow_wanx_fallback=False`` 时仅允许 qwen，失败直接抛真实原因。

        三视图链路固定走 qwen-image-2.1-turbo，不允许静默换模型；其他编辑功能
        （风格迁移 / 抠图 / 发层）保持原有 Wanx 兜底行为。
        """

        base_image_url = _resolve_cloud_image(base_image_url)
        last_error = None
        model_hint = self.settings.get("edit_model") or self.QWEN_EDIT_MODEL
        for key in _keys_for(self.settings):
            scoped = {**self.settings, "api_key": key}
            try:
                result = ImageEditProvider(scoped)._edit_chain(
                    base_image_url, instruction, poll_timeout, allow_wanx_fallback
                )
                from studio.backend.model_service.usage import record_usage

                record_usage("edit", result.get("model") or scoped.get("edit_model") or "?")
                note_key_outcome(key, True)
                return result
            except Exception as exc:  # noqa: BLE001
                # 额度/鉴权/网络类错误换下一把 Key；确定性失败直接上抛
                note_key_outcome(key, False, classify_error(exc))
                if classify_error(exc) in ("quota", "auth", "network"):
                    last_error = exc
                    continue
                if allow_wanx_fallback:
                    raise
                raise RuntimeError(
                    "{} 调用失败：{}".format(model_hint, str(exc) or exc.__class__.__name__)
                ) from exc
        if not last_error:
            raise RuntimeError("image edit failed")
        if allow_wanx_fallback:
            raise last_error
        raise RuntimeError(
            "{} 调用失败：{}".format(
                model_hint, str(last_error) or last_error.__class__.__name__
            )
        ) from last_error

    def _edit_chain(self, base_image_url, instruction, poll_timeout, allow_wanx_fallback=True):
        try:
            return self._edit_qwen(base_image_url, instruction, poll_timeout)
        except Exception:  # noqa: BLE001 - 其他编辑链路保留 wanx 兜底
            if not allow_wanx_fallback:
                raise
            return self._edit_wanx(base_image_url, instruction, poll_timeout)

    def _download(self, url):
        os.makedirs(GENERATED_DIR, exist_ok=True)
        file_name = "edit_{}.png".format(int(time.time() * 1000))
        image_response = httpx.get(url, timeout=60)
        image_response.raise_for_status()
        with open(os.path.join(GENERATED_DIR, file_name), "wb") as handle:
            handle.write(image_response.content)
        return file_name

    def _edit_qwen(self, base_image_url, instruction, poll_timeout=180.0):
        """Sync multimodal-generation call; image URL at
        ``output.choices[0].message.content[i].image``."""

        api_key = self.settings.get("api_key")
        if not api_key:
            raise RuntimeError("image edit not configured")
        edit_model = self.settings.get("edit_model") or self.QWEN_EDIT_MODEL
        # 请求超时不超过 side / back 的统一时间预算（poll_timeout 由 deadline 折算）
        timeout = max(
            30.0,
            min(float(poll_timeout), max(120.0, float(self.settings.get("timeout", 60)) * 2)),
        )
        response = httpx.post(
            DASHSCOPE_HOST + "/api/v1/services/aigc/multimodal-generation/generation",
            headers={
                "Authorization": "Bearer " + api_key,
                "Content-Type": "application/json",
            },
            json={
                "model": edit_model,
                "input": {
                    "messages": [
                        {
                            "role": "user",
                            "content": [
                                {"image": base_image_url},
                                {"text": instruction},
                            ],
                        }
                    ]
                },
                "parameters": {"n": 1, "watermark": False},
            },
            timeout=timeout,
        )
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise _http_error(exc)
        body = response.json()
        choices = (body.get("output") or {}).get("choices") or []
        content = (choices[0].get("message") or {}).get("content") if choices else []
        url = next((item.get("image") for item in content if item.get("image")), None)
        if not url:
            raise RuntimeError(
                "{}: no image in response ({})".format(
                    edit_model,
                    str(body.get("code") or body.get("message") or "empty content")[:160]
                )
            )
        return {
            "file": self._download(url),
            "url": url,
            "model": edit_model,
        }

    def _edit_wanx(self, base_image_url, instruction, poll_timeout):
        """DashScope wanx2.1-imageedit async task flow (legacy fallback)."""

        api_key = self.settings.get("api_key")
        if not api_key:
            raise RuntimeError("image edit not configured")
        if not base_image_url:
            raise RuntimeError("base image url missing")

        create = httpx.post(
            DASHSCOPE_HOST + "/api/v1/services/aigc/image2image/image-synthesis",
            headers={
                "Authorization": "Bearer " + api_key,
                "X-DashScope-Async": "enable",
                "Content-Type": "application/json",
            },
            json={
                "model": self.WANX_EDIT_MODEL,
                "input": {
                    "function": "description_edit",
                    "prompt": instruction,
                    "base_image_url": base_image_url,
                },
                "parameters": {},
            },
            timeout=float(self.settings.get("timeout", 60)),
        )
        try:
            create.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise _http_error(exc)
        task_id = (create.json().get("output") or {}).get("task_id")
        if not task_id:
            raise RuntimeError("dashscope: no task_id in response")

        url = poll_dashscope_task(api_key, task_id, poll_timeout)
        return {
            "file": self._download(url),
            "url": url,
            "model": self.WANX_EDIT_MODEL,
        }


def _dhash(image):
    """64 位差异感知哈希（9×8 灰度邻像素比较）。"""
    pixels = image.convert("L").resize((9, 8)).tobytes()
    value = 0
    for row in range(8):
        offset = row * 9
        for col in range(8):
            value <<= 1
            if pixels[offset + col] < pixels[offset + col + 1]:
                value |= 1
    return value


def _near_identical(path_a, path_b, threshold=0.03, hash_distance=6):
    """判断编辑模型是否把输入图原样返回。

    同时用像素差异（64×64 灰度平均差）与 dHash 感知哈希（汉明距离），
    避免仅靠灰度均值把「换了构图但明暗接近」误判为重复，也避免把
    「原图原样返回」当成有效的侧/背视图。返回 ``(bool, detail)``；
    任何异常都返回 ``(False, None)``，不让校验阻断生成。
    """

    if not path_a or not path_b:
        return False, None
    try:
        from PIL import Image

        with Image.open(path_a) as handle_a, Image.open(path_b) as handle_b:
            gray_a = handle_a.convert("L").resize((64, 64))
            gray_b = handle_b.convert("L").resize((64, 64))
            data_a = gray_a.tobytes()
            data_b = gray_b.tobytes()
            distance = bin(_dhash(handle_a) ^ _dhash(handle_b)).count("1")
        score = sum(abs(a - b) for a, b in zip(data_a, data_b)) / (255.0 * 64 * 64)
        duplicate = score < threshold or distance <= hash_distance
        return duplicate, "diff={:.4f}, dHash={}".format(score, distance)
    except Exception:  # noqa: BLE001
        return False, None


def _source_meta(front_image, base_url):
    """把调用方传入的原画引用归一为 {file, url, model}。"""
    meta = front_image if isinstance(front_image, dict) else {}
    return {
        "file": meta.get("file"),
        "url": meta.get("url") or base_url,
        "model": meta.get("model"),
    }


def _resolve_cloud_image(url):
    """把本地代理 URL（/api/generated/<file>）转成可被 DashScope 访问的
    base64 data URI；已是 data URI 或公网 URL 时原样返回，避免把 localhost
    相对地址直接发到云端导致「Incorrect padding」等解码失败。"""
    prefix = "/api/generated/"
    if isinstance(url, str) and url.startswith(prefix):
        path = safe_generated_path(url[len(prefix):])
        if path:
            ext = os.path.splitext(path)[1].lower()
            mime = {
                ".jpg": "image/jpeg",
                ".jpeg": "image/jpeg",
                ".webp": "image/webp",
            }.get(ext, "image/png")
            with open(path, "rb") as handle:
                return "data:{};base64,{}".format(
                    mime, base64.b64encode(handle.read()).decode("ascii")
                )
    return url


def _sheet_split_x(image):
    """双栏设定图裁切线：优先取中央白色间隔的中点，检测不到时取宽度 50%。"""

    width, height = image.size
    if width < 2:
        return width // 2
    # 缩到 256 宽再扫描，避免大图逐像素遍历过慢
    sample_w = 256
    sample_h = max(1, int(round(height * sample_w / float(width))))
    gray = image.convert("L").resize((sample_w, sample_h))
    pixels = gray.tobytes()
    # 只在中央 50% 窗口内找白列，避免选到画布外侧留白
    lo, hi = sample_w // 4, (sample_w * 3) // 4
    blank_limit = max(1, int(sample_h * 0.01))
    runs = []
    start = None
    for x in range(lo, hi):
        ink = 0
        for y in range(sample_h):
            if pixels[y * sample_w + x] < 240:
                ink += 1
        blank = ink <= blank_limit
        if blank and start is None:
            start = x
        elif not blank and start is not None:
            runs.append((start, x))
            start = None
    if start is not None:
        runs.append((start, hi))
    if not runs:
        return width // 2
    center = sample_w / 2.0
    best = max(
        runs, key=lambda run: (run[1] - run[0], -abs((run[0] + run[1]) / 2.0 - center))
    )
    return int(round(width * (((best[0] + best[1]) / 2.0) / float(sample_w))))


def _crop_turnaround_sheet(sheet_path):
    """把双栏设定图裁成独立的 side / back PNG；返回 ``{view: {file,path,bbox}}``。"""

    from PIL import Image

    with Image.open(sheet_path) as sheet:
        sheet.load()
        width, height = sheet.size
        split = _sheet_split_x(sheet)
        if split <= 0 or split >= width:
            split = width // 2
        boxes = {"side": (0, 0, split, height), "back": (split, 0, width, height)}
        os.makedirs(GENERATED_DIR, exist_ok=True)
        stamp = int(time.time() * 1000)
        saved = {}
        for view, box in boxes.items():
            crop = sheet.crop(box)
            name = "turnaround_{}_{}.png".format(view, stamp)
            path = os.path.join(GENERATED_DIR, name)
            crop.save(path, format="PNG")
            saved[view] = {"file": name, "path": path, "bbox": list(box)}
    return saved


def _validate_view_image(path, view, front_path, other_path=None):
    """确定性质量校验；合格返回 ``None``，否则返回可读原因。"""

    from PIL import Image

    try:
        with Image.open(path) as image:
            image.load()
            width, height = image.size
            histogram = image.convert("L").histogram()
    except Exception as error:  # noqa: BLE001 - 坏图按失败处理
        return "{} 裁切图无法解码（{}）".format(view, error)
    if width < TURNAROUND_VIEW_MIN_SIDE or height < TURNAROUND_VIEW_MIN_SIDE:
        return "{} 裁切图尺寸过小（{}×{}）".format(view, width, height)
    blank_ratio = sum(histogram[:245]) / float(width * height)
    if blank_ratio < TURNAROUND_VIEW_BLANK_RATIO:
        return "{} 裁切图接近纯白/空白（非白像素 {:.2%}）".format(view, blank_ratio)
    try:
        with Image.open(path) as reopened:
            reopened.load()
    except Exception as error:  # noqa: BLE001
        return "{} 裁切图保存后无法重新打开（{}）".format(view, error)
    peers = [("原画", front_path)]
    if other_path:
        peers.append(("背面" if view == "side" else "侧面", other_path))
    for label, peer in peers:
        if not peer or not os.path.isfile(peer):
            continue
        duplicate, detail = _near_identical(path, peer)
        if duplicate:
            return "{} 与{}几乎一致（{}），未执行视角变换".format(view, label, detail or "?")
    return None


def validate_reference_image(data):
    """Validate an uploaded front-view photo; returns its normalized metadata.

    Raises ``ValueError`` with a user-actionable message for empty, oversized
    or unsupported files. The real format comes from PIL, never the filename.
    """

    if not data:
        raise ValueError("图片内容为空，请重新选择文件")
    if len(data) > MAX_REFERENCE_BYTES:
        raise ValueError("图片超过 10MB 限制，请压缩后重新上传")

    from PIL import Image

    try:
        with Image.open(io.BytesIO(data)) as image:
            image_format = (image.format or "").upper()
            image.load()
            width, height = image.size
    except Exception as error:  # noqa: BLE001 - 坏文件按格式错误处理
        raise ValueError("无法识别图片内容，请上传 JPG / PNG / WebP 图片") from error

    if image_format not in _REFERENCE_MIMES:
        raise ValueError("仅支持 JPG / PNG / WebP 图片")
    mime, ext = _REFERENCE_MIMES[image_format]
    return {
        "mime": mime,
        "ext": ext,
        "width": width,
        "height": height,
        "bytes": len(data),
    }


def save_reference_image(data, *, sha=None):
    """Persist a validated front-view photo under ``GENERATED_DIR``.

    The ``reference_`` prefix keeps these files distinguishable from model
    output so orphan cleanup can never touch unrelated generated assets.
    """

    meta = validate_reference_image(data)
    digest = (sha or hashlib.sha256(data).hexdigest())[:8]
    name = "reference_{}_{}.{}".format(int(time.time() * 1000), digest, meta.pop("ext"))
    os.makedirs(GENERATED_DIR, exist_ok=True)
    with open(os.path.join(GENERATED_DIR, name), "wb") as handle:
        handle.write(data)
    return {"file": name, "url": "/api/generated/" + name, **meta}


def generate_from_reference(settings, reference_url, prompt, deadline=None):
    """Generate the character art from the user's photo via the edit model.

    Reuses the turnaround edit model (qwen multimodal, single reference image)
    and refuses silent model fallbacks: when the reference path is chosen the
    upload must actually drive the output. The result is decoded and checked
    for blank/broken output before it is handed to the runtime.
    """

    if not reference_url:
        raise ValueError("reference image url missing")
    editor = ImageEditProvider({**(settings or {}), "edit_model": REFERENCE_EDIT_MODEL})
    remaining = None
    if deadline is not None:
        remaining = deadline - time.time()
        if remaining <= 0:
            raise TurnaroundError("参考图生图超时，请稍后重试")

    result = editor.edit(
        reference_url,
        prompt,
        poll_timeout=max(30.0, remaining) if remaining is not None else 180.0,
        allow_wanx_fallback=False,
    )
    meta = result if isinstance(result, dict) else {}
    file_name = meta.get("file")
    path = safe_generated_path(file_name)
    if not path:
        raise TurnaroundError("参考图生图未返回可读取的图片")

    reason = None
    width = height = 0
    try:
        from PIL import Image

        with Image.open(path) as image:
            image.load()
            width, height = image.size
            histogram = image.convert("L").histogram()
        if width < TURNAROUND_VIEW_MIN_SIDE or height < TURNAROUND_VIEW_MIN_SIDE:
            reason = "生成图尺寸过小（{}×{}）".format(width, height)
        else:
            blank_ratio = sum(histogram[:245]) / float(width * height)
            if blank_ratio < TURNAROUND_VIEW_BLANK_RATIO:
                reason = "生成图接近纯白/空白（非白像素 {:.2%}）".format(blank_ratio)
    except Exception as error:  # noqa: BLE001 - 坏图按失败处理
        reason = "生成图无法解码（{}）".format(error)

    if reason:
        try:
            os.remove(path)
        except OSError:
            pass
        raise TurnaroundError(reason)

    return {
        "file": file_name,
        "url": "/api/generated/" + file_name,
        "model": meta.get("model") or REFERENCE_EDIT_MODEL,
        "provider": "dashscope",
        "size": {"width": width, "height": height},
        "prompt": prompt,
        "reference_url": reference_url,
    }


def generate_turnaround(
    settings,
    base_url,
    front_image=None,
    deadline=None,
    on_result=None,
    sheet_prompt=None,
):
    """三视图生成：front 直接用原画，side/back 来自一次双栏生成。

    1. 不做正面视角识别，不调用任何 VLM / 图片理解模型；
    2. ``front`` 严格等于原画（file / url / model），不生成替换图；
    3. 以原画为参考，一次调用 qwen-image-2.1-turbo 生成 side+back 双栏设定图，
       禁止 Wanx 兜底；qwen 失败直接抛真实错误；
    4. 双栏图按白色间隔（兜底 50%）裁成两个独立 PNG，再逐项做确定性校验；
    5. side / back 任一不合格即整体失败，不返回可写入的 design_views。

    ``sheet_prompt`` 可覆盖默认的角色转面提示词（PVE 生物使用单独版本）。
    Returns ``(views, failures)``，成功时 ``failures`` 恒为空。
    """

    editor = ImageEditProvider({**(settings or {}), "edit_model": TURNAROUND_EDIT_MODEL})
    source_image = _source_meta(front_image, base_url)
    if not source_image.get("url"):
        raise ValueError("source art url missing")
    front_path = safe_generated_path(source_image.get("file"))
    if not front_path:
        raise TurnaroundError("角色原画文件不存在或不可读")

    views = {
        "front": {
            "file": source_image.get("file"),
            "url": source_image.get("url"),
            "model": source_image.get("model"),
            "view": "front",
        }
    }
    remaining = None
    if deadline is not None:
        remaining = deadline - time.time()
        if remaining <= 0:
            raise TurnaroundError("三视图生成超时，请稍后重试")

    sheet = editor.edit(
        source_image.get("url"),
        sheet_prompt or TURNAROUND_SHEET_PROMPT,
        poll_timeout=max(30.0, remaining) if remaining is not None else 180.0,
        allow_wanx_fallback=False,
    )
    sheet_meta = sheet if isinstance(sheet, dict) else {}
    sheet_name = sheet_meta.get("file")
    sheet_path = safe_generated_path(sheet_name)
    if not sheet_path:
        raise TurnaroundError("双栏设定图未生成或无法读取")

    try:
        crops = _crop_turnaround_sheet(sheet_path)
    except Exception as error:  # noqa: BLE001 - 坏图/裁切失败直接判失败
        raise TurnaroundError("双栏设定图裁切失败：{}".format(error)) from error

    failures = []
    validated = {}
    for view in ("side", "back"):
        other = validated.get("side") if view == "back" else None
        reason = _validate_view_image(crops[view]["path"], view, front_path, other)
        if reason:
            failures.append(reason)
            continue
        validated[view] = crops[view]["path"]
    if failures:
        # 整组失败：清掉已落盘的裁切文件，避免留下错误结果
        for crop in crops.values():
            try:
                os.remove(crop["path"])
            except OSError:
                pass
        raise TurnaroundError("；".join(failures))

    for view in ("side", "back"):
        meta = {
            "file": crops[view]["file"],
            "url": "/api/generated/" + crops[view]["file"],
            "model": sheet_meta.get("model") or TURNAROUND_EDIT_MODEL,
            "view": view,
            "source": "qwen-turnaround-sheet",
            "sheet_file": sheet_name,
            "bbox": crops[view]["bbox"],
        }
        if view == "side":
            # 试玩舞台的规范侧视朝向；旧记录缺少此字段时前端按历史左向兼容。
            meta["facing"] = "right"
        views[view] = meta
        if on_result:
            on_result(view, meta)

    return views, []

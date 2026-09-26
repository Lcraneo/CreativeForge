"""Third-party image-model settings + OpenAI-compatible image provider.

Security:
    * the API key is never returned by the API — responses expose only a hint
      (``sk-****abcd``) and ``has_key``;
    * the settings file is written with owner-only permissions where the OS
      supports it and lives under the git-ignored ``studio/backend/data``;
    * empty key submissions keep the stored key, ``key: null`` clears it;
    * ``CF_MODEL_API_KEY`` / ``CF_MODEL_BASE_URL`` env vars override the file
      without ever persisting a key to disk.
"""

import base64
import json
import os
import re
import threading
import time
import urllib.error
import urllib.request
import uuid

DATA_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data"
)
DEFAULT_SETTINGS_PATH = os.path.join(DATA_DIR, "model_settings.json")
GENERATED_DIR = os.path.join(DATA_DIR, "generated")

DEFAULTS = {
    "enabled": False,
    "provider": "custom",
    "base_url": "",
    "api_key": "",
    "model": "",            # image model
    "chat_model": "",       # chat model (DeepSeek enhancer)
    "use_chat": True,
    "use_image": True,
    "size": "1024x1024",
    "timeout": 60,
    "updated_at": None,
}

PROVIDER_PRESETS = [
    {
        "id": "system",
        "label": "系统默认",
        "base_url": "",
        "chat_model": "",
        "image_model": "",
        "use_chat": False,
        "use_image": False,
        "note": "确定性内置管线，无需密钥。",
    },
    {
        "id": "deepseek",
        "label": "DeepSeek 官方",
        "base_url": "https://api.deepseek.com/v1",
        "chat_model": "deepseek-chat",
        "image_model": "",
        "use_chat": True,
        "use_image": False,
        "note": "官方 API 目前是文本模型：用于角色设定与提示词增强；原画由系统管线产出。若你的网关在 DeepSeek 名称下提供图像接口，可同时勾选“用图像接口生成原画”。",
    },
    {
        "id": "openai",
        "label": "OpenAI",
        "base_url": "https://api.openai.com/v1",
        "chat_model": "gpt-4o-mini",
        "image_model": "gpt-image-1",
        "use_chat": True,
        "use_image": True,
        "note": "聊天模型增强提示词 + images 接口生成原画。",
    },
    {
        "id": "zhipu",
        "label": "智谱 BigModel",
        "base_url": "https://open.bigmodel.cn/api/paas/v4",
        "chat_model": "glm-4-flash",
        "image_model": "cogview-3-flash",
        "use_chat": True,
        "use_image": True,
        "note": "glm 对话增强 + cogview 绘图。",
    },
    {
        "id": "siliconflow",
        "label": "硅基流动",
        "base_url": "https://api.siliconflow.cn/v1",
        "chat_model": "Qwen/Qwen2.5-7B-Instruct",
        "image_model": "black-forest-labs/FLUX.1-schnell",
        "use_chat": True,
        "use_image": True,
        "note": "Qwen 增强 + FLUX 绘图。",
    },
    {
        "id": "custom",
        "label": "自定义网关",
        "base_url": "",
        "chat_model": "",
        "image_model": "",
        "use_chat": True,
        "use_image": True,
        "note": "任意 OpenAI 兼容网关，自行填写地址与模型。",
    },
]

SAFE_NAME = re.compile(r"^[A-Za-z0-9._-]{1,120}$")


class ImageProviderError(Exception):
    """Raised when the external image API cannot produce an image."""


class ModelSettingsStore:
    def __init__(self, path=DEFAULT_SETTINGS_PATH):
        self._path = path
        self._lock = threading.RLock()
        self._data = dict(DEFAULTS)
        self._load()

    # ------------------------------------------------------------------
    # persistence
    # ------------------------------------------------------------------

    def _load(self):
        try:
            with open(self._path, encoding="utf-8") as handle:
                payload = json.load(handle)
            if isinstance(payload, dict):
                for key in DEFAULTS:
                    if key in payload:
                        self._data[key] = payload[key]
        except (OSError, ValueError):
            pass

    def _persist_locked(self):
        try:
            os.makedirs(os.path.dirname(self._path), exist_ok=True)
            temporary = "{}.tmp".format(self._path)
            with open(temporary, "w", encoding="utf-8") as handle:
                json.dump(self._data, handle, ensure_ascii=False, indent=2)
            os.replace(temporary, self._path)
            try:
                os.chmod(self._path, 0o600)
            except OSError:
                pass
        except OSError:
            pass

    # ------------------------------------------------------------------
    # API
    # ------------------------------------------------------------------

    def update(self, payload):
        """Partial update; empty key keeps the current one, null clears it."""
        with self._lock:
            data = dict(self._data)
            if "enabled" in payload and payload["enabled"] is not None:
                data["enabled"] = bool(payload["enabled"])
            if "provider" in payload and payload["provider"] is not None:
                data["provider"] = str(payload["provider"]).strip() or "custom"
            if "base_url" in payload and payload["base_url"] is not None:
                data["base_url"] = str(payload["base_url"]).strip()
            if "model" in payload and payload["model"] is not None:
                data["model"] = str(payload["model"]).strip()
            if "chat_model" in payload and payload["chat_model"] is not None:
                data["chat_model"] = str(payload["chat_model"]).strip()
            if "use_chat" in payload and payload["use_chat"] is not None:
                data["use_chat"] = bool(payload["use_chat"])
            if "use_image" in payload and payload["use_image"] is not None:
                data["use_image"] = bool(payload["use_image"])
            if "size" in payload and payload["size"] is not None:
                data["size"] = str(payload["size"]).strip() or DEFAULTS["size"]
            if "timeout" in payload and payload["timeout"] is not None:
                try:
                    data["timeout"] = max(5, min(300, int(payload["timeout"])))
                except (TypeError, ValueError):
                    pass
            if "api_key" in payload:
                key = payload["api_key"]
                if key is None:
                    data["api_key"] = ""
                elif str(key).strip():
                    data["api_key"] = str(key).strip()
            data["updated_at"] = time.time()
            self._data = data
            self._persist_locked()
            return self.public()

    def clear_key(self):
        return self.update({"api_key": None})

    def raw(self):
        with self._lock:
            return dict(self._data)

    def effective(self):
        """Raw settings with environment overrides applied."""
        data = self.raw()
        if os.environ.get("CF_MODEL_BASE_URL"):
            data["base_url"] = os.environ["CF_MODEL_BASE_URL"].strip()
        if os.environ.get("CF_MODEL_API_KEY"):
            data["api_key"] = os.environ["CF_MODEL_API_KEY"].strip()
            data["enabled"] = True
        data["env_override"] = bool(
            os.environ.get("CF_MODEL_API_KEY") or os.environ.get("CF_MODEL_BASE_URL")
        )
        return data

    def public(self):
        data = self.raw()
        key = data.get("api_key") or ""
        hint = ""
        if key:
            hint = "{}****{}".format(key[:3], key[-4:]) if len(key) > 8 else "****"
        has_chat = bool(data.get("chat_model")) and bool(data.get("use_chat"))
        has_image = bool(data.get("model")) and bool(data.get("use_image"))
        return {
            "enabled": bool(data.get("enabled")) and bool(data.get("base_url")),
            "provider": data.get("provider"),
            "base_url": data.get("base_url") or "",
            "model": data.get("model") or "",
            "chat_model": data.get("chat_model") or "",
            "use_chat": bool(data.get("use_chat")),
            "use_image": bool(data.get("use_image")),
            "size": data.get("size"),
            "timeout": data.get("timeout"),
            "has_key": bool(key),
            "key_hint": hint,
            "updated_at": data.get("updated_at"),
            "env_override": bool(
                os.environ.get("CF_MODEL_API_KEY") or os.environ.get("CF_MODEL_BASE_URL")
            ),
            "capabilities": {
                "chat": bool(data.get("base_url")) and has_chat,
                "image": bool(data.get("base_url")) and has_image,
                "any": bool(data.get("base_url")) and (has_chat or has_image),
            },
        }

    def ready(self):
        data = self.effective()
        if not (data.get("enabled") and data.get("base_url") and data.get("api_key")):
            return False
        return bool(
            (data.get("use_chat") and data.get("chat_model"))
            or (data.get("use_image") and data.get("model"))
        )


def _endpoint(base_url, suffix="images/generations"):
    url = str(base_url or "").strip().rstrip("/")
    if not url:
        raise ImageProviderError("API 地址为空")
    if url.endswith("/" + suffix) or url.endswith(suffix):
        return url
    if url.endswith("/v1"):
        return "{}/{}".format(url, suffix)
    return "{}/v1/{}".format(url, suffix)


def _request_json(url, method, api_key, payload=None, timeout=30):
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    request = urllib.request.Request(url, data=data, method=method)
    request.add_header("Content-Type", "application/json")
    request.add_header("Authorization", "Bearer {}".format(api_key))
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8", "replace"))
    except urllib.error.HTTPError as error:
        detail = error.read().decode("utf-8", "replace")[:280]
        raise ImageProviderError("HTTP {}: {}".format(error.code, detail))
    except urllib.error.URLError as error:
        raise ImageProviderError("网络错误: {}".format(error.reason))
    except (ValueError, OSError) as error:
        raise ImageProviderError(str(error))


class ImageProvider:
    """OpenAI-compatible ``POST /v1/images/generations`` client."""

    def __init__(self, settings, generated_dir=GENERATED_DIR):
        self.settings = settings
        self.generated_dir = generated_dir

    def test(self):
        started = time.perf_counter()
        api_key = self.settings.get("api_key") or ""
        base_url = self.settings.get("base_url") or ""
        if not base_url:
            return {"ok": False, "message": "请先填写 API 地址"}
        if not api_key:
            return {"ok": False, "message": "请先填写 API 密钥"}
        try:
            url = _endpoint(base_url, "models")
            result = _request_json(url, "GET", api_key, timeout=min(20, int(self.settings.get("timeout", 60))))
            models = [
                str(item.get("id"))
                for item in (result.get("data") or [])
                if isinstance(item, dict) and item.get("id")
            ]
            latency = round((time.perf_counter() - started) * 1000)
            return {
                "ok": True,
                "message": "连接成功，共 {} 个模型".format(len(models)),
                "latency_ms": latency,
                "models": models[:30],
            }
        except ImageProviderError as error:
            # some gateways do not expose /models — probe with a dry payload
            try:
                url = _endpoint(base_url, "images/generations")
                _request_json(url, "POST", api_key, {
                    "model": self.settings.get("model"),
                    "prompt": "connectivity probe (will not be used)",
                    "n": 1,
                    "size": self.settings.get("size", "1024x1024"),
                    "max_tokens": 1,
                }, timeout=min(20, int(self.settings.get("timeout", 60))))
                latency = round((time.perf_counter() - started) * 1000)
                return {"ok": True, "message": "接口可达（未验证图片返回）", "latency_ms": latency}
            except ImageProviderError as nested:
                return {"ok": False, "message": str(nested), "hint": str(error)}

    def generate(self, prompt, timeout=None):
        settings = self.settings
        api_key = settings.get("api_key") or ""
        if not api_key:
            raise ImageProviderError("未配置 API 密钥")
        model = settings.get("model")
        if not model:
            raise ImageProviderError("未配置图像模型（例如 gpt-image-1 / FLUX.1-schnell）")
        url = _endpoint(settings.get("base_url"), "images/generations")
        payload = {
            "model": model,
            "prompt": str(prompt)[:4000],
            "n": 1,
            "size": settings.get("size") or "1024x1024",
            "response_format": "b64_json",
        }
        started = time.perf_counter()
        result = _request_json(
            url, "POST", api_key, payload,
            timeout=int(timeout or settings.get("timeout") or 60),
        )
        items = result.get("data") or []
        if not items:
            raise ImageProviderError("接口未返回图像数据: {}".format(str(result)[:200]))
        item = items[0]
        mime = "image/png"
        binary = None
        if item.get("b64_json"):
            binary = base64.b64decode(item["b64_json"])
        elif item.get("url"):
            with urllib.request.urlopen(item["url"], timeout=60) as response:
                binary = response.read()
                mime = response.headers.get("Content-Type", "image/png").split(";")[0]
        else:
            raise ImageProviderError("返回格式不支持（缺少 b64_json / url）")

        os.makedirs(self.generated_dir, exist_ok=True)
        extension = {"image/jpeg": ".jpg", "image/webp": ".webp"}.get(mime, ".png")
        filename = "{}{}".format(uuid.uuid4().hex[:12], extension)
        path = os.path.join(self.generated_dir, filename)
        with open(path, "wb") as handle:
            handle.write(binary)
        try:
            os.chmod(path, 0o600)
        except OSError:
            pass

        return {
            "file": filename,
            "url": "/api/generated/{}".format(filename),
            "mime": mime,
            "provider": "custom",
            "model": payload["model"],
            "size": payload["size"],
            "prompt": payload["prompt"],
            "elapsed_ms": round((time.perf_counter() - started) * 1000),
        }


def safe_generated_path(name, generated_dir=GENERATED_DIR):
    if not name or not SAFE_NAME.match(name):
        return None
    path = os.path.join(generated_dir, name)
    if not os.path.isfile(path):
        return None
    return path


CHAT_SYSTEM_PROMPT = (
    "You are the art director of a game studio. Rewrite the user's character "
    "request into ONE vivid English image-generation prompt for a character "
    "concept illustration. Preserve every explicit detail (gender, age, hair "
    "colour and style, expression, height, body type, outfit, weapon, colour "
    "palette, accessories), add tasteful art-direction words (clean line art, "
    "soft cel shading, semi-realistic anime style, full body front view, plain "
    "light background), and keep it under 220 words. Output only the prompt "
    "text — no JSON, no markdown, no explanations."
)


def _chat_user_content(goal, spec=None, overrides=None):
    lines = ["用户需求 / USER REQUEST:", str(goal).strip()]
    if spec:
        attributes = [
            "gender={}".format(spec.get("gender_label")),
            "class={}".format(spec.get("class_label")),
            "element={}".format(spec.get("element_label")),
            "height={}cm".format(spec.get("height_cm")),
            "build={}".format(spec.get("build_label")),
            "hair={}{}".format(spec.get("hair_color_label"), spec.get("hair_style_label")),
            "expression={}".format(spec.get("expression_label")),
            "weapon={}".format(spec.get("weapon_label")),
        ]
        lines.append("解析出的角色属性 / PARSED ATTRIBUTES: " + ", ".join(attributes))
    if overrides:
        pairs = ["{}={}".format(key, value) for key, value in overrides.items() if value]
        if pairs:
            lines.append("必须遵守的参数约束 / MUST FOLLOW: " + ", ".join(pairs))
    return "\n".join(lines)


class ChatProvider:
    """OpenAI-compatible ``POST /v1/chat/completions`` prompt enhancer
    (used with DeepSeek / GPT / GLM chat models)."""

    def __init__(self, settings):
        self.settings = settings

    def enhance(self, goal, spec=None, overrides=None):
        api_key = self.settings.get("api_key") or ""
        if not api_key:
            raise ImageProviderError("未配置 API 密钥")
        model = self.settings.get("chat_model")
        if not model:
            raise ImageProviderError("未配置对话模型（例如 deepseek-chat）")
        url = _endpoint(self.settings.get("base_url"), "chat/completions")
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": CHAT_SYSTEM_PROMPT},
                {"role": "user", "content": _chat_user_content(goal, spec, overrides)},
            ],
            "temperature": 0.7,
            "max_tokens": 700,
            "stream": False,
        }
        started = time.perf_counter()
        result = _request_json(
            url, "POST", api_key, payload,
            timeout=int(self.settings.get("timeout") or 60),
        )
        try:
            content = result["choices"][0]["message"]["content"].strip()
        except (KeyError, IndexError, TypeError, AttributeError):
            raise ImageProviderError("对话接口返回格式不支持: {}".format(str(result)[:200]))
        content = content.strip("` \n\"'")
        if content.startswith("```"):
            content = content.strip("`").strip()
        if not content:
            raise ImageProviderError("对话接口返回空内容")
        return {
            "prompt": content,
            "model": model,
            "provider": self.settings.get("provider") or "custom",
            "elapsed_ms": round((time.perf_counter() - started) * 1000),
        }

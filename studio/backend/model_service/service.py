"""Third-party image-model integration for the Studio.

These providers are only invoked when the user configures an external model
API (``enabled`` + ``base_url`` + ``api_key``). With no configuration the
runtime degrades to the built-in deterministic pipeline, so every call here is
best-effort and wrapped by the caller's ``MODEL_FALLBACK`` path.

The chat / image calls speak the OpenAI-compatible ``/chat/completions`` and
``/images/generations`` contracts, which most hosted providers mirror.
"""

import base64
import json
import os
import threading
import time

import httpx

DEFAULT_SETTINGS_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "model_settings.json"
)

GENERATED_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "generated"
)

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
        "model": "",
        "chat_model": "",
        "use_chat": True,
        "use_image": True,
        "size": "512x512",
        "timeout": 60,
        "style": "pixel",
    }

    def __init__(self, path=None):
        self.path = path or DEFAULT_SETTINGS_PATH
        self._lock = threading.Lock()
        self._data = dict(self._DEFAULTS)
        self._load()

    def _load(self):
        if os.path.isfile(self.path):
            try:
                with open(self.path, "r", encoding="utf-8") as handle:
                    data = json.load(handle)
                if isinstance(data, dict):
                    self._data.update(
                        {k: v for k, v in data.items() if k in self._DEFAULTS}
                    )
            except (ValueError, OSError):
                pass

    def _save(self):
        try:
            with open(self.path, "w", encoding="utf-8") as handle:
                json.dump(self._data, handle, ensure_ascii=False, indent=2)
        except OSError:
            pass

    def effective(self):
        with self._lock:
            return dict(self._data)

    def public(self):
        with self._lock:
            data = dict(self._data)
            data.pop("api_key", None)
        return data

    def update(self, changes):
        with self._lock:
            for key, value in (changes or {}).items():
                if key in self._DEFAULTS:
                    self._data[key] = value
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


def poll_dashscope_task(api_key, task_id, timeout_seconds):
    """Poll a DashScope async task until it finishes; returns the result URL."""

    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        poll = httpx.get(
            DASHSCOPE_HOST + "/api/v1/tasks/" + task_id,
            headers={"Authorization": "Bearer " + api_key},
            timeout=30,
        )
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
    """OpenAI-compatible chat completion used for prompt enhancement."""

    def __init__(self, settings):
        self.settings = settings or {}

    def enhance(self, goal, spec, overrides=None):
        base_url = (self.settings.get("base_url") or "").rstrip("/")
        model = self.settings.get("chat_model") or self.settings.get("model")
        api_key = self.settings.get("api_key")
        if not base_url or not api_key or not model:
            raise RuntimeError("chat provider not configured")
        prompt = (
            "Rewrite the following game-asset generation request as a detailed "
            "art-direction brief for a game character:\n\n" + str(goal)
        )
        response = httpx.post(
            base_url + "/chat/completions",
            headers={
                "Authorization": "Bearer " + api_key,
                "Content-Type": "application/json",
            },
            json={
                "model": model,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.7,
            },
            timeout=float(self.settings.get("timeout", 60)),
        )
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise _http_error(exc)
        content = response.json()["choices"][0]["message"]["content"]
        return {"model": model, "prompt": content.strip()}


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
                "parameters": {"size": size, "n": 1},
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
        if not (self.settings.get("base_url") or "").rstrip("/") or not self.settings.get("api_key") or not self.settings.get("model"):
            raise RuntimeError("image provider not configured")
        if self._is_dashscope():
            return self._generate_dashscope(prompt)

        base_url = (self.settings.get("base_url") or "").rstrip("/")
        model = self.settings.get("model")
        api_key = self.settings.get("api_key")
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
            "url": url
            or ("/api/generated/" + file_name if file_name else None),
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


class ImageEditProvider:
    """DashScope native image edit (wanx2.1-imageedit): derives new views of
    an existing AI artwork (turnaround side / back views) via async tasks."""

    EDIT_MODEL = "wanx2.1-imageedit"

    def __init__(self, settings):
        self.settings = settings or {}

    def edit(self, base_image_url, instruction):
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
                "model": self.EDIT_MODEL,
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

        url = poll_dashscope_task(api_key, task_id, 180.0)
        os.makedirs(GENERATED_DIR, exist_ok=True)
        file_name = "edit_{}.png".format(int(time.time() * 1000))
        image_response = httpx.get(url, timeout=60)
        with open(os.path.join(GENERATED_DIR, file_name), "wb") as handle:
            handle.write(image_response.content)
        return {"file": file_name, "url": url, "model": self.EDIT_MODEL}

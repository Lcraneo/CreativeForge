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
        "video_model": "",
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


def poll_video_task(api_key, task_id, timeout_seconds):
    """Poll a DashScope i2v (图生视频) async task; returns the video URL."""

    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        poll = httpx.get(
            DASHSCOPE_HOST + "/api/v1/tasks/" + task_id,
            headers={"Authorization": "Bearer " + api_key},
            timeout=30,
        )
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
        time.sleep(5)
    raise RuntimeError("dashscope video task timeout: " + str(task_id))


def generate_video(settings, prompt, image_bytes, timeout_seconds=420.0):
    """图生视频 (Windup 式 i2v 路线): source image + motion prompt -> mp4 bytes.

    Tries the configured ``video_model`` first, then the known DashScope
    i2v model names (naming changed across model generations). Returns
    ``(video_bytes, model_name)``."""
    api_key = settings.get("api_key")
    if not api_key:
        raise RuntimeError("自定义模型未启用，无法使用 AI 视频驱动")
    # wan2.2-i2v-flash 为当前主线（实测可用）；wanx2.1-i2v-turbo 仍在线作回退。
    # 早期候选 wan2.1-i2v-turbo / wanx-i2v 已下线（HTTP 400 Model not exist）。
    models = [m for m in (settings.get("video_model"), "wan2.2-i2v-flash", "wanx2.1-i2v-turbo") if m]
    encoded = base64.b64encode(image_bytes).decode()
    last_error = None
    for model in models:
        create = httpx.post(
            DASHSCOPE_HOST + "/api/v1/services/aigc/video-generation/video-synthesis",
            headers={
                "Authorization": "Bearer " + api_key,
                "Content-Type": "application/json",
                "X-DashScope-Async": "enable",
            },
            json={
                "model": model,
                "input": {"prompt": prompt, "img_url": "data:image/png;base64," + encoded},
                "parameters": {"size": "960*960", "prompt_extend": True},
            },
            timeout=60,
        )
        if create.status_code >= 400:
            last_error = RuntimeError(
                "HTTP {} ({}): {}".format(create.status_code, model, create.text[:220])
            )
            continue
        task_id = (create.json().get("output") or {}).get("task_id")
        if not task_id:
            last_error = RuntimeError("dashscope: no task_id in response")
            continue
        url = poll_video_task(api_key, task_id, timeout_seconds)
        video = httpx.get(url, timeout=120)
        video.raise_for_status()
        return video.content, model
    raise last_error or RuntimeError("video generation failed")


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


TURNAROUND_PROMPTS = {
    "side": (
        "把图中角色向左旋转90度，生成同一个角色的正左侧全身侧面像：面朝画面左侧站立，"
        "可见侧脸轮廓、单只眼睛、身体与手臂的侧面，保持完全相同的角色设计"
        "（相同的发型、发色、配色、服装细节、体型与比例），单人全身立绘，纯白背景"
    ),
    "back": (
        "把图中角色旋转180度，生成同一个角色的正后方全身背面像：背对镜头站立，"
        "只可见后脑勺、发型背面、背部与服装背面，完全不可见面部，"
        "保持完全相同的角色设计（相同的发型、发色、配色、服装细节、体型与比例），"
        "单人全身立绘，纯白背景"
    ),
}

# 二次尝试时的强化指令：编辑模型偶尔会原样返回输入图，必须强调视角必须改变
TURNAROUND_REINFORCE = {
    "side": TURNAROUND_PROMPTS["side"]
    + "。注意：这是一次视角变换，必须生成全新的侧面构图，正面朝向的形象不允许出现。",
    "back": TURNAROUND_PROMPTS["back"]
    + "。注意：这是一次视角变换，必须生成全新的背面构图，任何面部特征都不允许出现。",
}


class ImageEditProvider:
    """Image edit for the turnaround views (side / back of the same character).

    Primary model ``qwen-image-edit`` (multimodal-generation, sync): follows
    viewpoint-change instructions. Falls back to the wanx2.1 description_edit
    async flow when qwen is unavailable for the account.
    """

    QWEN_EDIT_MODEL = "qwen-image-edit"
    WANX_EDIT_MODEL = "wanx2.1-imageedit"
    EDIT_MODEL = QWEN_EDIT_MODEL

    def __init__(self, settings):
        self.settings = settings or {}

    def edit(self, base_image_url, instruction, poll_timeout=180.0):
        try:
            return self._edit_qwen(base_image_url, instruction)
        except Exception:  # noqa: BLE001 - fall back to the wanx flow
            return self._edit_wanx(base_image_url, instruction, poll_timeout)

    def _download(self, url):
        os.makedirs(GENERATED_DIR, exist_ok=True)
        file_name = "edit_{}.png".format(int(time.time() * 1000))
        image_response = httpx.get(url, timeout=60)
        image_response.raise_for_status()
        with open(os.path.join(GENERATED_DIR, file_name), "wb") as handle:
            handle.write(image_response.content)
        return file_name

    def _edit_qwen(self, base_image_url, instruction):
        """Sync multimodal-generation call; image URL at
        ``output.choices[0].message.content[i].image``."""

        api_key = self.settings.get("api_key")
        if not api_key:
            raise RuntimeError("image edit not configured")
        timeout = max(120.0, float(self.settings.get("timeout", 60)) * 2)
        response = httpx.post(
            DASHSCOPE_HOST + "/api/v1/services/aigc/multimodal-generation/generation",
            headers={
                "Authorization": "Bearer " + api_key,
                "Content-Type": "application/json",
            },
            json={
                "model": self.QWEN_EDIT_MODEL,
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
        url = next(
            (item.get("image") for item in content if item.get("image")), None
        )
        if not url:
            raise RuntimeError(
                "qwen-image-edit: no image in response ({})".format(
                    str(body.get("code") or body.get("message") or "empty content")[:160]
                )
            )
        return {
            "file": self._download(url),
            "url": url,
            "model": self.QWEN_EDIT_MODEL,
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


def _near_identical(path_a, path_b, threshold=0.03):
    """Mean abs diff of two downscaled grayscale images. Returns
    ``(bool, score)``; any failure yields ``(False, None)`` so the check can
    never break generation."""

    if not path_a or not path_b:
        return False, None
    try:
        from PIL import Image

        with Image.open(path_a) as handle_a, Image.open(path_b) as handle_b:
            data_a = handle_a.convert("L").resize((64, 64)).tobytes()
            data_b = handle_b.convert("L").resize((64, 64)).tobytes()
        score = sum(abs(a - b) for a, b in zip(data_a, data_b)) / (255.0 * 64 * 64)
        return score < threshold, score
    except Exception:  # noqa: BLE001
        return False, None


def generate_turnaround(settings, base_url, front_image=None, deadline=None,
                        on_result=None):
    """Derives the side / back views from the base artwork with a self-check:
    the edit models sometimes echo the input, so each result is compared with
    the front image and regenerated once with a reinforced instruction when
    it comes back near-identical.

    Returns ``(views, failures)`` — ``views`` always carries ``front``;
    a view that failed stays absent (the UI keeps its placeholder).
    """

    editor = ImageEditProvider(settings)
    front_path = safe_generated_path((front_image or {}).get("file"))
    views = {"front": {"url": base_url, "model": (front_image or {}).get("model")}}
    failures = []

    for view, instruction in TURNAROUND_PROMPTS.items():
        result = None
        reason = None
        for attempt in range(2):
            if deadline is not None and time.time() >= deadline:
                reason = reason or "time budget exhausted"
                break
            try:
                prompt = TURNAROUND_REINFORCE[view] if attempt else instruction
                result = editor.edit(base_url, prompt)
            except Exception as error:  # noqa: BLE001 - retry once on any error
                result = None
                reason = str(error)
                continue
            duplicate, score = _near_identical(
                front_path, safe_generated_path(result.get("file"))
            )
            if duplicate:
                result = None
                reason = "输出与原图几乎一致（diff={}），未执行视角变换".format(
                    round(score, 4) if score is not None else "?"
                )
                continue
            reason = None
            break

        if result:
            result["view"] = view
            views[view] = result
            if on_result:
                on_result(view, result)
        else:
            failures.append("{}: {}".format(view, (reason or "unknown")[:140]))

    return views, failures

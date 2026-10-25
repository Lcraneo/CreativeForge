"""``CreativeAsset`` 云扩展契约 v1.0：``extensions.cloud_backends`` 的读写与校验。

契约规则（与实施计划 R1–R10 一一对应）：

- **R1 只加不改**：本模块只操作 ``extensions.cloud_backends`` 子树，绝不改写其他字段。
- **R2 全可选**：子树整体缺失即合法，旧资产与旧 benchmark 不受影响。
- **R3 未知字段忽略**：``normalize()`` 静默剥离未声明字段，不抛错。
- **R4 二进制不入契约**：只存引用（``local_path``）与校验值（``sha256`` / ``bytes``）。
- **R5 路径沙箱**：``local_path`` 必须是相对路径，且规范化后落在缓存根内。
- **R6 凭据隔离**：本模块不接受、不写入任何 API Key 或鉴权头。
- **R7 失败留痕**：失败槽位只保留 ``status`` + ``provider`` + ``error_class``。
- **R8 导出净化**：``export_view()`` 剥离 ``provenance``，只留可复现的产物引用。
- **R9 幂等**：由 ``provenance.request_hash`` 承载（缓存判定在客户端层实现）。
- **R10 单产物单来源**：一个槽位同一时刻只有一个 ``provider``，不做多后端产物合并。

槽位：``mesh`` / ``image`` / ``video`` / ``audio``。

实现只用标准库：不引入校验框架，避免给主工程增加依赖。
"""

from __future__ import annotations

import os

__all__ = [
    "NAMESPACE",
    "VERSION",
    "SLOT_NAMES",
    "STATUSES",
    "PROVIDERS",
    "ERROR_CLASSES",
    "AUDIO_KINDS",
    "CloudExtensionError",
    "normalize",
    "validate",
    "read_extension",
    "write_extension",
    "export_view",
    "safe_rel_path",
    "resolve_local_path",
    "error_slot",
]

NAMESPACE = "cloud_backends"
VERSION = "1.0"
SLOT_NAMES = ("mesh", "image", "video", "audio")
STATUSES = ("pending", "running", "succeeded", "failed")
PROVIDERS = ("bailian-tripo", "tripo", "meshy", "ark", "seed-audio")
ERROR_CLASSES = (
    "auth",
    "quota",
    "rate_limit",
    "server",
    "task_failed",
    "task_timeout",
    "invalid_request",
)
AUDIO_KINDS = ("dialogue", "sfx")

# 槽位字段声明：类型标记 —— str / int / float / bool / "path" / "sha256"
_SLOT_FIELDS = {
    "mesh": {
        "task_id": str,
        "format": str,
        "local_path": "path",
        "bytes": int,
        "sha256": "sha256",
        "decimation_target": float,
        "texture_size": int,
        "rigged": bool,
    },
    "image": {
        "model": str,
        "local_path": "path",
        "width": int,
        "height": int,
        "seed": int,
        "bytes": int,
        "sha256": "sha256",
    },
    "video": {
        "model": str,
        "local_path": "path",
        "duration_s": float,
        "bytes": int,
        "sha256": "sha256",
    },
    "audio": {
        "kind": str,
        "local_path": "path",
        "duration_s": float,
        "sample_rate": int,
        "bytes": int,
        "sha256": "sha256",
    },
}
_COMMON_FIELDS = {"status": str, "provider": str}
_FAILURE_FIELDS = {"error_class": str, "error_message": str}
_PROVENANCE_FIELDS = {
    "request_hash": str,
    "created_at": str,
    "cache_hit": bool,
    "credits_estimate": int,
    "cost_actual": float,
    # GF last_call_info 口径的可选留痕（R8 导出时 provenance 整体剥离，不受影响）
    "elapsed_sec": float,
    "preview_url": str,
    "triangles": int,
}


class CloudExtensionError(ValueError):
    """扩展块读写失败（路径越界、结构非法等）。"""


# ── 基础工具 ────────────────────────────────────────────────────────────────


def safe_rel_path(value) -> str | None:
    """校验并规范化相对路径；非法（绝对路径 / 上跳 / 非字符串）返回 ``None``（R5）。

    统一输出正斜杠形式，保证跨平台一致。
    """

    if not isinstance(value, str):
        return None
    raw = value.strip().replace("\\", "/")
    if not raw or raw.startswith("/") or ":" in raw.split("/")[0]:
        return None
    segments = [seg for seg in raw.split("/") if seg not in ("", ".")]
    if not segments or any(seg == ".." for seg in segments):
        return None
    return "/".join(segments)


def resolve_local_path(rel_path: str, root: str | None = None) -> str:
    """把契约内的相对路径解析为绝对路径，越界即抛错（R5）。"""

    clean = safe_rel_path(rel_path)
    if clean is None:
        raise CloudExtensionError("local_path 必须是以缓存根为基准的相对路径")
    if root is None:
        from .. import config  # 延迟导入：避免契约层与运营配置互相牵连

        root = config.cache_dir()
    base = os.path.abspath(root)
    target = os.path.abspath(os.path.join(base, *clean.split("/")))
    if target != base and not target.startswith(base + os.sep):
        raise CloudExtensionError("local_path 越出缓存根目录")
    return target


def _coerce(value, kind):
    """按声明类型做宽松收敛；不可转换时返回 ``None``。"""

    if kind == "path":
        return safe_rel_path(value)
    if kind == "sha256":
        if not isinstance(value, str):
            return None
        digest = value.strip().lower()
        if not digest or len(digest) > 128:
            return None
        if any(ch in digest for ch in ("/", "\\", "..")):
            return None
        return digest
    if kind is bool:
        if isinstance(value, bool):
            return value
        if isinstance(value, str) and value.strip().lower() in ("true", "false"):
            return value.strip().lower() == "true"
        return None
    if kind is str:
        if not isinstance(value, str):
            return None
        text = value.strip()
        return text or None
    if kind is int:
        if isinstance(value, bool) or isinstance(value, str):
            return None
        if isinstance(value, int):
            return value
        if isinstance(value, float) and value.is_integer():
            return int(value)
        return None
    if kind is float:
        if isinstance(value, bool) or isinstance(value, str):
            return None
        if isinstance(value, (int, float)):
            return float(value)
        return None
    return None


# ── 规范化（R3 / R5 / R7）───────────────────────────────────────────────────


def _normalize_slot(slot: str, raw: dict, issues: list[str]) -> dict | None:
    fields = dict(_COMMON_FIELDS)
    fields.update(_SLOT_FIELDS[slot])

    status = _coerce(raw.get("status"), str)
    if status not in STATUSES:
        issues.append(f"{slot}.status 非法或缺失：{raw.get('status')!r}")
        return None

    clean: dict = {"status": status}
    provider = _coerce(raw.get("provider"), str)
    if provider is not None:
        if provider not in PROVIDERS:
            issues.append(f"{slot}.provider 未登记：{provider!r}")
        else:
            clean["provider"] = provider

    if status == "failed":
        # R7：失败槽位只留痕，不保留半成品产物字段
        error_class = _coerce(raw.get("error_class"), str)
        if error_class not in ERROR_CLASSES:
            issues.append(f"{slot}.error_class 非法或缺失：{raw.get('error_class')!r}")
        else:
            clean["error_class"] = error_class
        message = _coerce(raw.get("error_message"), str)
        if message is not None:
            clean["error_message"] = message
        return clean

    for name, kind in fields.items():
        if name in ("status", "provider"):
            continue
        if name not in raw:
            continue
        value = _coerce(raw[name], kind)
        if value is None:
            issues.append(f"{slot}.{name} 类型或取值非法：{raw[name]!r}")
            continue
        clean[name] = value

    if status == "succeeded":
        if "provider" not in clean:
            issues.append(f"{slot} 已成功但缺少合法 provider")
        if "local_path" not in clean:
            issues.append(f"{slot} 已成功但缺少合法 local_path")
    if slot == "audio" and "kind" in clean and clean["kind"] not in AUDIO_KINDS:
        issues.append(f"{slot}.kind 只能是 {'/'.join(AUDIO_KINDS)}：{clean['kind']!r}")
        clean.pop("kind")
    return clean


def _normalize_provenance(raw: dict, issues: list[str]) -> dict | None:
    clean: dict = {}
    for name, kind in _PROVENANCE_FIELDS.items():
        if name not in raw:
            continue
        value = _coerce(raw[name], kind)
        if value is None:
            issues.append(f"provenance.{name} 类型非法：{raw[name]!r}")
            continue
        clean[name] = value
    if "request_hash" not in clean:
        issues.append("provenance.request_hash 缺失（R9 幂等所需的缓存键）")
    return clean or None


def normalize(block) -> dict:
    """静默清洗扩展块（R3）：剥离未知字段、丢弃非法槽位，只返回合法内容。

    非法内容不抛错，仅由 ``validate()`` 负责报告。
    """

    return _normalize_with_issues(block)[0]


def validate(block) -> list[str]:
    """校验扩展块结构，返回问题清单；空清单表示合法。"""

    return _normalize_with_issues(block)[1]


def _normalize_with_issues(block) -> tuple[dict, list[str]]:
    issues: list[str] = []
    if block is None:
        return {}, issues
    if not isinstance(block, dict):
        return {}, ["扩展块必须是对象（dict）"]

    version = _coerce(block.get("version"), str) or VERSION
    if version.split(".")[0] != VERSION.split(".")[0]:
        issues.append(f"扩展块主版本不兼容：{version!r}（当前支持 {VERSION}）")
        version = VERSION

    clean: dict = {"version": version}
    for slot in SLOT_NAMES:
        raw = block.get(slot)
        if raw is None:
            continue
        if not isinstance(raw, dict):
            issues.append(f"{slot} 必须是对象（dict）")
            continue
        normalized = _normalize_slot(slot, raw, issues)
        if normalized is not None:
            clean[slot] = normalized

    raw_provenance = block.get("provenance")
    if raw_provenance is not None:
        if not isinstance(raw_provenance, dict):
            issues.append("provenance 必须是对象（dict）")
        else:
            provenance = _normalize_provenance(raw_provenance, issues)
            if provenance is not None:
                clean["provenance"] = provenance

    return clean, issues


# ── 资产读写（R1 / R2 / R8）─────────────────────────────────────────────────


def read_extension(asset) -> dict | None:
    """从资产读取扩展块；整体缺失即合法，返回 ``None``（R2）。"""

    if not isinstance(asset, dict):
        return None
    extensions = asset.get("extensions")
    if not isinstance(extensions, dict):
        return None
    block = extensions.get(NAMESPACE)
    if not isinstance(block, dict):
        return None
    return block


def write_extension(asset: dict, block) -> dict:
    """把扩展块写回资产（R1）：只动 ``extensions.cloud_backends``，其余字段原样保留。

    清洗后为空的块不写入，避免制造空壳。
    """

    if not isinstance(asset, dict):
        raise CloudExtensionError("资产必须是 dict")
    clean = normalize(block)
    if not clean or set(clean) == {"version"}:
        return asset
    extensions = asset.get("extensions")
    if not isinstance(extensions, dict):
        extensions = {}
    extensions[NAMESPACE] = clean
    asset["extensions"] = extensions
    return asset


def export_view(asset_or_block) -> dict | None:
    """导出交付视图（R8）：剥离 ``provenance``，只保留可复现的产物引用。"""

    if isinstance(asset_or_block, dict) and "extensions" in asset_or_block:
        block = read_extension(asset_or_block)
    else:
        block = asset_or_block
    if not isinstance(block, dict):
        return None
    clean = normalize(block)
    clean.pop("provenance", None)
    return clean or None


def error_slot(provider: str, error_class: str, message: str = "") -> dict:
    """构造失败槽位（R7）：只留状态与错误分类，不留半成品。"""

    if error_class not in ERROR_CLASSES:
        raise CloudExtensionError(f"未登记的错误分类：{error_class!r}")
    slot = {"status": "failed", "error_class": error_class}
    if provider in PROVIDERS:
        slot["provider"] = provider
    text = (message or "").strip()
    if text:
        slot["error_message"] = text[:500]
    return slot

"""C 部分（本地模型旁路服务）接缝 —— 本期为空实现。

最小档方案只启用云后端，本地权重（Trellis2 / WorldMirror / WorldPlay /
Puppeteer / MoMask）一律不进主环境、不占磁盘。为了让后续按需开启时不必
返工，接口形态现在先定死：

- ``enabled()``   —— 运营开关（``CF_SIDECAR_ENABLED``，默认关闭）
- ``available()`` —— 旁路是否就绪（本期恒为 ``False``）
- ``require(kind)`` —— 取用旁路能力；未就绪即抛 ``SidecarUnavailable``

契约：旁路只作为**可选增强**，其失败必须能被云后端兜住，
不得成为主链路的必需依赖。
"""

from .. import config

__all__ = ["SIDECAR_KINDS", "SidecarUnavailable", "enabled", "available", "require"]

SIDECAR_KINDS = ("local_3d_object", "local_motion", "local_3d_scene")


class SidecarUnavailable(RuntimeError):
    """旁路服务未启用或未就绪。"""


def enabled() -> bool:
    """运营开关状态（仅代表配置意图，不代表服务已部署）。"""

    return config.sidecar_enabled()


def available() -> bool:
    """旁路是否可用；最小档固定返回 ``False``。"""

    return False


def require(kind: str):
    """取用指定旁路能力；未登记或未就绪一律抛错。"""

    if kind not in SIDECAR_KINDS:
        raise SidecarUnavailable(f"未登记的旁路能力：{kind!r}")
    raise SidecarUnavailable(
        f"旁路能力 {kind!r} 未部署（最小档为纯云形态，如需启用见实施计划 C 部分）"
    )

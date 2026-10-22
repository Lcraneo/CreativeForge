"""云能力算子（S3）：能力输入 → 云 wrapper → 产物写回扩展槽位。

- ``object_3d`` → ``mesh``
- ``image``     → ``image``
- ``cg_video``  → ``video``
- ``audio``     → ``audio``

每个算子只做单次能力调用；后端选择、fallback 与编排仍在 Supervisor / 路由层。
"""

from . import audio, base, cg_video, image, object_3d

__all__ = ["base", "object_3d", "image", "cg_video", "audio"]

"""各云厂商 wrapper：只负责「请求构造 + 响应解析」。

统一继承 ``BaseCloudModel``，共享云管道的重试、缓存、错误分类与落盘。

- ``bailian_tripo`` 阿里云百炼 · Tripo 3D（3D 主通道）
- ``tripo``        Tripo3D 官方（3D 备通道，支持本地上传）
- ``meshy``        Meshy（3D 最终兜底，多格式，免费档需署名）
- ``seedream``     方舟 ARK · Seedream 图像（同步）
- ``seedance``     方舟 ARK · Seedance 视频（异步 submit → poll → download）
- ``seed_audio``   Seed Audio（单 wrapper 双槽：对白 / 音效）
"""

from . import bailian_tripo, base, meshy, seed_audio, seedance, seedream, tripo

__all__ = [
    "base",
    "bailian_tripo",
    "tripo",
    "meshy",
    "seedream",
    "seedance",
    "seed_audio",
]

"""云能力算子（S3 落地）。

S3 将在此实现：``object_3d.py`` / ``image.py`` / ``cg_video.py`` / ``audio.py``。
每个算子只做「能力输入 -> 云 wrapper 调用 -> 产物写回
``extensions.cloud_backends`` 对应槽位」，编排权仍在 Supervisor。

S1 只占位，不含实现。
"""

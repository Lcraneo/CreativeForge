"""``CreativeAsset`` 契约扩展命名空间（当前 v1.0）。

只做加法扩展：既有字段语义一律冻结，扩展内容的读写与校验全部收敛到
``extension_v1`` 一处，避免校验逻辑在算子与适配器之间重复实现。
"""

from . import extension_v1

__all__ = ["extension_v1"]

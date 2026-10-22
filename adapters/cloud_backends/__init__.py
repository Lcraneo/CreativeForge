"""A 部分：云生成后端的 vendored 内核（最小档 = 纯云，零本地权重）。

分层：

- ``config``     —— 运行开关与缓存策略
- ``contracts``  —— ``extensions.cloud_backends`` 契约读写与校验
- ``client``     —— 云管道基座（S2）
- ``models``     —— 各厂商 wrapper（S2）
- ``operators``  —— 云能力算子（S3）
- ``sidecar``    —— C 部分（本地旁路）接缝，本期为空
- ``cloud_adapter`` —— 适配器（S3）

隔离铁律：本子包自成闭环，主工程只通过 ``AssetAdapter`` 接口与
``CapabilityRegistry`` 感知它；本包不得反向依赖主工程内部模块。

S1 只导出已就绪的三块（配置、契约、接缝），S2/S3 落地后再逐个补出。
"""

from . import config, contracts, sidecar

__all__ = ["config", "contracts", "sidecar"]

"""Studio 云生成服务层：厂商目录 + 凭据配置存储（S1 骨架）。

S4 将在此补充生成路由与任务编排；本包不承载任何本地模型运行时代码。
"""

from . import catalog, provider_store

__all__ = ["catalog", "provider_store"]

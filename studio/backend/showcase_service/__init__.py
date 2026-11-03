"""Showcase service (Studio): CreativeAsset → OneTake 发布展示视频。

adapters/onetake 负责「资产 → 合成」映射，本服务负责任务编排：后台线程
完成 素材准备 → comp 生成 → 草稿渲染 → oracle 验收，产物与 meta 落盘。
批次状态仿 AnimationService._ACTION_BATCHES（内存 + TTL + 前端轮询）。
"""


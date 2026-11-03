"""OneTake adapter — CreativeAsset → 发布展示视频（External Creative Capability）。

上游 onetake（third_party/onetake，PolyForm NC）提供 f(t) 合成范式与渲染管线；
本适配层把 CreativeAsset 映射为合成素材与节拍表，并驱动离线渲染。业务只依赖
本包与 ShowcaseService 的产物（mp4/poster/预览 HTML），不直接触碰 third_party。
"""

from adapters.onetake.asset_mapper import MissingMaterialError, prepare_job_assets
from adapters.onetake.scene_mapper import build_scene
from adapters.onetake.timeline_mapper import build_timeline, render_comp, shots_list

__all__ = [
    "MissingMaterialError",
    "prepare_job_assets",
    "resolve_material",
    "build_scene",
    "build_timeline",
    "render_comp",
    "shots_list",
]

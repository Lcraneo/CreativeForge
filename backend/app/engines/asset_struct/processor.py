"""AssetStruct pipeline (Phase 13.11):

    generate image -> Vision Analyzer -> Find Parts -> SAM2 -> Masks
                    -> Extract Layers -> Build Asset Graph -> Anchors
                    -> Pixel Data -> CreativeAsset

All modules are AssetProcessor-shaped: CreativeAsset in, enriched
CreativeAsset out, so the agent pipeline just chains them.
"""

from typing import Any

from app.engines.asset_struct.analyzer.vision_analyzer import VisionAnalyzer
from app.engines.asset_struct.builder.asset_builder import AssetBuilder
from app.engines.asset_struct.graph.asset_graph import AssetGraphBuilder
from app.engines.asset_struct.layers.layer_extractor import LayerExtractor
from app.engines.asset_struct.segmentation.sam_processor import SamProcessor


class AssetStructProcessor:
    name = "asset_struct"

    def __init__(
        self,
        analyzer: VisionAnalyzer | None = None,
        segmenter: SamProcessor | None = None,
        extractor: LayerExtractor | None = None,
        graph_builder: AssetGraphBuilder | None = None,
        builder: AssetBuilder | None = None,
    ):
        self.analyzer = analyzer or VisionAnalyzer()
        self.segmenter = segmenter or SamProcessor()
        self.extractor = extractor or LayerExtractor()
        self.graph_builder = graph_builder or AssetGraphBuilder()
        self.builder = builder or AssetBuilder()

    async def process(self, asset: dict[str, Any]) -> dict[str, Any]:
        image = asset["content"]["image"]
        goal = (asset.get("identity") or {}).get("prompt")

        analysis = await self.analyzer.analyze(image, goal=goal)
        parts = analysis["parts"]

        layers = []
        for part in parts:
            segmentation = await self.segmenter.segment(image, part["name"])
            layer = self.extractor.extract(image, segmentation)
            layers.append(layer.to_dict())

        graph = self.graph_builder.build(parts).to_dict()
        score = sum(l["confidence"] for l in layers) / len(layers) if layers else 0.0

        return self.builder.build(asset, layers, graph, score)

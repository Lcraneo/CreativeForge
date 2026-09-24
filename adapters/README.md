Adapter Layer

Holonic Adapter:
- AssetMapper
- ImageProcessorMapper
- VideoProcessorMapper
- TaskMapper

Windup Adapter:
- GenerationMapper
- PixelMapper
- AnimationMapper
- CocosMapper

FAlign CreativeAsset Adapter:
- CreativeAssetAdapter (adapters/creative_asset_adapter.py)
- Runs FAlign over CreativeAsset.animation.frames
- Writes aligned animation state + quality.animation back into the asset

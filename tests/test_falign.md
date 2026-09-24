# FAlign Contract Tests

1. Frame extraction normalizes frames (id + image, upstream hints preserved).
2. Anchor detection returns root / feet / center / head per frame.
3. Phase alignment maps frames onto the 0..1 motion phase track.
4. Root motion correction flags drift (small steps) and keeps real motion (large steps).
5. Temporal analysis outputs jitter score + smooth verdict.
6. Animation evaluator writes anchor / motion / temporal / overall scores.
7. FAlignEngine returns CreativeAsset-compatible animation + quality.animation.
8. CreativeAssetAdapter writes aligned animation state back into the asset.

Future:
- real sprite sheet / video / gif decoding
- keypoint model integration for anchor detection
- benchmark dataset (drift / jitter / phase ground truth)

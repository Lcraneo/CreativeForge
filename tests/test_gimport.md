# GImport Contract Tests

1. Manifest generator emits asset_id / type / resources and passes its own contract.
2. Manifest schema validation catches missing required fields.
3. Atlas builder packs frames into one atlas image with frame layout rects.
4. Animation clip generator emits Unity clip (fps / loop) and Cocos animation (duration).
5. Prefab generator emits the character entity with full component set.
6. Engine adapters (Cocos / Unity / Godot) map resources to engine paths.
7. Runtime validator checks resource integrity, animation integrity and engine compatibility.
8. GImportEngine end-to-end returns manifest / atlas / animation / prefab / engine / validation.
9. One-click export produces the shareable game asset package.

Future:
- real Unity .unitypackage / Cocos project writing
- Godot scene generation
- engine-side import verification

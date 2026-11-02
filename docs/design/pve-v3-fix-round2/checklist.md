# 验收清单

- [x] `pve.ts` 的 `PVE_GUARD_COOLDOWN` 为 2，护盾被击中后 2 秒恢复（`stepProjectiles` 的 50 步测试断言 `pveHud(...).guardAvailable === true`）
- [x] 玩家弹丸具备追踪能力：`steerPlayerProjectile` 在 `PVE_HOMING_RANGE` 内就近锁定活敌人，超出范围保持直线（两条测试分别覆盖命中与不命中）
- [x] 竞技场可活动范围收敛为 `PVE_EDGE_MARGIN = 20`，不再有硬编码 40
- [x] 上下方向与按键一致：`projectGround` 为 `top + y * depthScale`，`stepPlayerMove` 的 `inputY = down - up`
- [x] 画面不再绘制中央擂台：`drawArenaFloor` 及其调用已删除，无地面矩形/边框/网格
- [x] 投影横纵铺满画布（`scale = width / arena.width`，`depthScale` 由高度与纵深换算），不再居中缩成一条
- [x] 立绘按纵深透视缩放（`depthPerspective`）并对脚底以上空间做高度封顶（`actorHeight`），远端角色与 Boss 不再被画布顶部裁切
- [x] 敌人血条/阴影与透视一致，血条不会跑到画布外
- [x] `matchingProfileId` 在原 profile 已删除时回退到同角色首个可用敌人，进入编辑即有可保存的默认值
- [x] 序列编辑器在敌人池无可用敌人时显示空态提示，保存失败显示后端返回的错误文案
- [x] 敌人工坊删除改为行内两步确认，代码中不再有 `window.confirm`，删除失败在行内展示
- [x] 后端三关背景提示词要求 “continuous seamless ground plane / strong perspective depth / no floating islands, no separated platforms”，PVE composition 满足单一体连续地面
- [x] `npm run test` 20 文件 156 用例全部通过
- [x] `npm run typecheck` 通过
- [x] `npm run build` 通过
- [x] 后端 `test_pve_enemy_service.py`、`test_scene_api.py`、`test_pve_validation.py` 共 20 项通过

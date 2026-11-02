# 实施任务

- [x] 任务 1：`studio/frontend/src/lib/pve.ts` 战斗参数与边界
  - [x] `PVE_GUARD_COOLDOWN = 2`
  - [x] 新增 `PVE_EDGE_MARGIN = 20`，替换 `stepPlayerMove` / `stepEnemy` / `stepProjectiles` 中的 40
  - [x] 新增 `PVE_HOMING_RANGE` / `PVE_HOMING_TURN` 并在 `stepProjectiles` 实现玩家弹丸转向
- [x] 任务 2：`studio/frontend/src/pages/PveStage.tsx` 投影与交互
  - [x] `Projection` 增加 `depthScale`；`makeProjection` 横纵铺满；`projectGround` 改为 `top + y * depthScale`
  - [x] 删除 `drawArenaFloor` 及其调用；震地椭圆用 `depthScale`
  - [x] 新增 `depthPerspective` / `actorHeight`，立绘按纵深缩放并封顶，远端角色与 Boss 不被裁切；血条与阴影同步透视
  - [x] 战斗说明中“冷却 4 秒”改为 2 秒
  - [x] `matchingProfileId` 回退到同角色首个可用 profile
  - [x] `CampaignSequenceCard` 增加空态与保存错误展示
  - [x] `PveEnemyForge` 删除改为行内两步确认
- [x] 任务 3：`studio/backend/scene_service/service.py`
  - [x] 强化 `_PVE_BACKGROUND_SHOTS` 与 PVE composition 的连续地面 / 纵深 / 禁止分裂平面约束
- [x] 任务 4：`studio/frontend/src/lib/pve.test.ts`
  - [x] 改写两条直线弹道断言为追踪弹道断言
  - [x] 新增追踪范围外不命中、护盾 2 秒恢复断言
- [x] 任务 5：验证 `npm run test`、`npm run typecheck`、`npm run build`、后端三个测试文件

# 任务依赖

- 任务 2 依赖任务 1
- 任务 4 依赖任务 1 与任务 2
- 任务 5 依赖任务 1–4

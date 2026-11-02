# PVE 2.5D 修复批次 spec（round 2）

范围：只修复用户列出的 6 项问题，不改动已验收的三关状态机、数据结构和其它页面。

## 1. 上下方向反转

根因：`PveStage.tsx` 的 `projectGround` 使用 `arenaDepth - y`，而物理上 `y` 增大表示靠近镜头、`pveSortByDepth` 按 `y` 升序绘制（远→近）。

改法：
- `projectGround` 改为 `screenY = top + y * depthScale`，即 `y` 越小越靠上。
- 深度排序保持升序，与投影方向一致。
- `stepPlayerMove` / `stepEnemy` 的 `inputY = down - up`（按下 y 增大、画面上往下走）保持不变，修复后观感与按键一致。

## 2. 中间“擂台”限制区域

根因：`drawArenaFloor` 画出深色圆角矩形 + 边框 + 网格；`makeProjection` 用 `0.94 / 0.86` 边距且把纵深按 1.6 倍铺开，导致桌面宽画布下竞技场只占中间一条。

改法：
- 删除 `drawArenaFloor` 整个函数与调用；地面完全交给生成的背景图。
- `Projection` 增加 `depthScale`（每逻辑 y 单位的屏幕像素）。
- `makeProjection`：
  - `scale = width / arena.width`（横向铺满）
  - `depthScale = height / (arena.depth * PVE_DEPTH_SCALE)`（纵向铺满）
  - `offsetX = 0`、`top = 0`
- `projectGround` 用独立的 x/y 比例，形成真实斜俯视的纵向压缩感，不再出现居中的矩形场地。
- `drawTelegraph` 中震地椭圆的 y 半径改用 `depthScale`，与地面比例一致。
- 逻辑边界收敛：`pve.ts` 新增 `PVE_EDGE_MARGIN = 20`，玩家/敌人 clamp 与击退上限改用它（替代硬编码 40），可活动范围最大化；场景生成时敌人的初始坐标仍按后端 `40..width-40` 校验，不受影响。

## 3. 场景背景分裂平面 / 缺纵深

改法（后端 `scene_service/service.py`）：
- `_PVE_BACKGROUND_SHOTS` 三关文案改为强调“one continuous seamless ground plane from foreground to horizon”“strong perspective depth”“no floating islands / no separated platforms / no split levels / no arena ring or border”。
- `_background_prompts` 的 PVE composition 增加同样的强约束，并明确“ground plane fills the entire frame”。
- 不改生成流程与校验，只规范提示词。

## 4. 敌人子弹追踪 + 护盾 CD

`lib/pve.ts`：
- `PVE_GUARD_COOLDOWN = 4` → `2`。
- 新增 `PVE_HOMING_RANGE = 520`、`PVE_HOMING_TURN = 7`（每秒最大转向权重）。
- `stepProjectiles` 对 `owner === "player"` 的弹丸：就近选择 `PVE_HOMING_RANGE` 内最近的活敌人（用 `pveGroundDistance`），把速度方向按 `PVE_HOMING_TURN * dt` 权重向目标方向插值并归一化回 `PVE_SHOT_SPEED`；z 方向同步向目标中心靠拢；超出范围保持直线。命中判定仍使用现有三维扫掠 AABB。
- HUD / 说明文案里的“冷却 4 秒”改为 2 秒。

测试：
- 删掉/改写“aimZ 向上瞄准必打空”“y 偏移必打空”两条直线弹道断言。
- 新增：近距离侧向偏移目标被追踪命中；超出 `PVE_HOMING_RANGE` 的目标不命中；护盾触发后 `2s` 恢复（`pveHud(runtime).guardAvailable`）。

## 5. 生成的敌人无法加入敌人序列

已核实后端 `update_pve_enemy_sequence` 与 PUT 路由对真实数据可用（stage_1/stage_2/stage_3 替换均成功）。真实故障在前端默认值：
- 现网场景槽位引用 `pve_05c80b00ef`，该 profile 已不在敌人池，`matchingProfileId` 返回 `""`，所有槽位都是“选择敌人”；漏选任一槽位即被前端拦截，用户表现为“加不进去”。

改法（`PveStage.tsx`）：
- `matchingProfileId` 找不到原 profile 时回退到同角色可用 profile 的第一个，保证进入编辑即有一组可保存的默认值。
- `CampaignSequenceCard` 增加空态提示：某角色没有可用 profile 时显示“敌人池暂无可用 Boss/小怪”，并显示保存失败原因（`saveSequence.error.message`）。
- 保存成功后保持现有 `setQueryData` + runtime 重建逻辑（`campaign` 变化即触发 `createPveRuntime`）。

## 6. 敌人池删除不可用

根因：删除按钮依赖 `window.confirm`，在嵌入式/禁止 modal 的环境里直接返回 false，点击无任何反应。

改法（`PveStage.tsx` 的 `PveEnemyForge`）：
- 去掉 `window.confirm`，改为行内两步确认：第一次点击把 `pendingDelete` 设为该敌人 id，行内出现“确认删除 / 取消”两个按钮；确认后调用 `remove.mutate`。
- 删除失败在行内展示 `remove.error` 文案；生成中状态仍禁用删除（后端 409 语义不变）。

## 验证

- `npm run test`（`lib/pve.test.ts` 更新后全绿）
- `npm run typecheck`
- `npm run build`
- 后端：`pytest studio/backend/tests/test_pve_enemy_service.py studio/backend/tests/test_scene_api.py studio/backend/tests/test_pve_validation.py`
- 人工：进入 `scene_9ac79172101e`，按上向上走、按上向下走消失；画面无中央矩形擂台；替换第三关 Boss 一次保存成功；敌人池删除按钮出现行内确认并删除成功。

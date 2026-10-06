# 修复：自定义动作与内置动作命名空间混淆（试玩舞台动作错播）

日期：2026-10-06。

## 缺陷与根因

**现象**（用户实测）：创建自定义动作「人物原地敲竹板」后，未选择任何基础动作时
基础动作区默认显示「行走」；在试玩舞台执行「行走」时，播放的是自定义的敲竹板
动画而非系统内置行走动画。

**根因链**（三个环节叠加）：

1. 自定义动作存储里 `action` 字段是"运动族"（解释器给出的基础动作词，缺省
   `walk`——`custom_actions.py` 的 `str(payload.get("action") or "walk")`）；
2. 前端 `resolveGeneration` 把该运动族词当作生成请求的 `action`，后端
   `create_video` 把它原样记入 `meta.requested_action`——自定义动画以
   `walk` 入账；
3. 试玩舞台 AI 条带按 `meta.requested_action` 与内置动作名做成员匹配，同
   槽位取最新——自定义敲竹板动画（更新）抢占内置 walk 条带。同一根因还
   让批次补齐把 walk 误判为已交付而跳过（`existing_ai_actions`）。

「基础动作默认显示行走」本身是既定的清晰默认选择机制（判别联合选择模型，
基础/自定义互斥高亮），它不产生数据——真正缺陷是第 2、3 环：运动族词被当
成了动作归属。

## 修复方案：命名空间隔离（后端强制）

- **身份协议**：新增 `CUSTOM_ACTION_PREFIX = "custom:"`。自定义动作的动画
  meta 记 `requested_action = "custom:<名称>"` 并附 `custom_action` 字段；
  内置动作保持无前缀动作词。两套身份永不交汇——即使自定义动作与内置动作
  同名（如自定义"walk"），`custom:walk ≠ walk`。
- **执行点过滤**（内置槽位只认 `base` 身份）：
  - `collect_ai_strips()`（新抽取的纯函数，routes 试玩条带改用它）：custom:
    记录永不参与内置动作条带；
  - `existing_ai_actions()`：自定义记录不算内置动作已交付（批次补齐恢复
    正确的跳过判定）；
  - `action_matrix()`：自定义记录不占动作×视角矩阵格（归动作库管理）。
- **请求通道**：`AnimationRequest.custom_action` 字段贯通同步端点与生成
  任务端点 → `create_video`（入口 `sanitize_custom_action` 规范化：剥误带
  前缀/限长）。`action` 参数此时仅作运动族（提示词词表回退/装备子句/idle
  稳定分支），不再代表归属。
- **前端**：`resolveGeneration` 对自定义动作返回 `custom_action: preset 名`
  并随载荷发送（`AnimationStudio.generate`）；基础动作计划不含该字段。
- **默认选择机制**：保留「初始选中内置 walk」作为清晰默认——经上述隔离后
  它与自定义动作零耦合，不再可能串数据。

## 历史数据修复

缺陷生效期间生成的自定义动画已以错误身份入账。一次性修复脚本
`studio/backend/tools/repair_custom_action_identity.py`：用
`custom_motion_prompt_cache.json` 的润色子句做确定性匹配（该子句是自定义
链路唯一产物；`motion_prompt` 以其开头 ⇒ 必出自自定义动作），把 3 条记录
迁移到 `custom:` 命名空间并留 `legacy_identity_repair` 溯源：

- `ab17d1060efa`：walk → `custom:原地敲竹板待机循环动画`
- `729cc85e109b`、`de1fe997ed9d`：idle → `custom:鞠躬致意`（两条历史版本）

## 专项测试（命名空间契约固化）

后端 `test_action_identity.py`（11 项）：身份解析/规范化往返、试玩条带
最新胜出+custom 排除+同名冲突（custom:walk）+跨资产/稀疏帧排除、批次补
齐不被自定义记录误导、矩阵格排除自定义、自定义库与内置同名互不污染。
前端 `actionSelection.test.ts`（更新+新增）：基础计划无自定义身份、自定义
计划必带身份、敲竹板场景复现断言（action=walk 仅运动族、custom_action 为
播放归属）、同名冲突两命名空间互不污染。

## 验证记录

- 后端 34/34（含新增 11 项）、契约 45/45；前端 Vitest 64/64、tsc、构建通过。
- 8600 实机验证（修复后重启）：敲竹板所在资产 ast43024 的 walk 条带由
  ai-video（被抢占）回退 `rigged`（系统默认骨骼行走）；鞠躬所在资产
  ast93505 的 idle 条带为真实内置 idle 动画；动作矩阵无自定义记录混入；
  全库审计无「带 custom_action 却非 custom: 身份」的记录。
- 归属对应关系：内置槽位（试玩/矩阵/补齐）= 内置动画；自定义动作的播放
  严格随其记录（动画工作台结果/历史按 animation id 精确回放）。试玩舞台
  当前仅陈列内置动作槽位，自定义动作不参与亦不干扰（后续如需可在舞台
  增加 custom: 条带陈列，属功能扩展不属本缺陷）。

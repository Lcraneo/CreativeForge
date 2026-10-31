# Tasks：人物正面图 → 三视图

> 执行顺序即依赖顺序。每完成一项立即勾选，并在完成后运行对应验证。

## T1 提示词：身份锁定
- [x] `agent/generation/external.py` 新增 `_IDENTITY_LOCK_ZH/_EN` 与 `build_reference_image_prompt()`。
- 验收：中文输入返回中文锁定前缀 + 原 `build_image_prompt` 内容；英文同理；不含参考图时旧函数输出逐字不变。
- 验证：`python -m pytest agent` 或现有生成测试；`ruff check agent`。

## T2 参考图存储与参考图生图
- [x] `studio/backend/model_service/service.py`：`MAX_REFERENCE_BYTES`、`validate_reference_image()`、`save_reference_image()`、`generate_from_reference()`。
- 验收：伪造扩展名被 PIL 拦下；10MB 边界前后行为正确；生成结果落在 `GENERATED_DIR` 且 `safe_generated_path` 可取；空白图被判失败。
- 验证：新测试文件中的上传/生成用例。

## T3 Runtime 支持参考图 + 任务内三视图
- [x] `runtime.py`：`start_task`/`_run`/`_call_external` 增加 `reference_image`。
- [x] 参考分支用 `build_reference_image_prompt` + `generate_from_reference`；模型不可用时任务失败并给可操作提示。
- [x] 带参考图时任务内调用 `generate_turnaround` 写 `design_views`；失败写 `design_views_error` + `MODEL_FALLBACK stage="views"`，原图保留。
- [x] 无参考图时保留 `asset.pop("design_views", None)` 且不调用 views。
- 验收：现有 `test_design_views.py` 两个契约测试仍通过；新参考图任务产出 front/side/back。
- 验证：`python -m unittest studio.backend.tests.test_design_views -v`。

## T4 上传 / 删除 / 任务参数 API
- [x] `routes.py`：`POST /api/character/reference`、`DELETE /api/character/reference/{name}`、`CreateTaskRequest.reference_image`、任务创建校验、`_localize_asset` 补 `reference_image`。
- [x] 历史删除后 `_cleanup_orphan_references`：只清未引用的 `reference_` 文件。
- 验收：413/415/400 错误码与可操作 detail；被引用文件删除返回 409；删除历史后孤儿文件消失、在用文件保留。
- 验证：新测试文件 + `python -m unittest studio.backend.tests.test_character_reference -v`。

## T5 前端类型与 API 客户端
- [x] `types.ts`：`ReferenceImage`、`CreativeAsset.reference_image/design_views_error`、`MODEL_VIEWS` 事件。
- [x] `api/client.ts`：`uploadCharacterReference`（FormData + authHeaders，不设 Content-Type）、`deleteCharacterReference`、`createTask` 增 `referenceImage`。
- 验收：TypeScript 编译通过。
- 验证：`npm run build`（含 tsc）。

## T6 创建页上传入口
- [x] `Workspace.tsx`：上传卡片、提示文案、预览/替换/删除、客户端格式与大小校验、错误 toast。
- [x] `generate()` 携带 `reference_image`；`busy || agentRunning` 防重复；失败保留参考图状态。
- 验收：未上传时与原流程一致；上传后调用 `POST /api/tasks` body 含 `reference_image`。
- 验证：`npm run lint` + `npm run test`。

## T7 设计中心展示
- [x] `DesignCenter.tsx`：原始正面图卡片、`design_views_error` 持久化提示 + 复用“重新生成三视图”。
- [x] `useTaskFeed.ts` 登记 `MODEL_VIEWS`。
- 验收：刷新后仍显示参考图与三视图；失败原因可见且可重试。
- 验证：`npm run build`。

## T8 自动化测试
- [x] 新增 `studio/backend/tests/test_character_reference.py`，覆盖：
  1. 合法上传 + 生成 + 保存 + 重读三视图；
  2. 未上传时走原流程；
  3. 非法类型 / 超限拒绝；
  4. 生图失败保留原图且可重试；
  5. 孤儿文件引用保护与清理。
- 验收：全部通过且不修改现有测试断言。

## T9 全量验证与报告
- [x] `python tests/run_tests.py`、`ruff check ...`、`black --check ...`
- [x] `npm run lint`、`npm run test`、`npm run build`
- [x] 输出报告：修改文件、接口/字段变化、执行命令与结果。
- [x] 按用户偏好提交并推送远程仓库（commit message 说明参考图三视图能力）。

## 回滚点
每个任务独立可回滚；`reference_image` / `design_views_error` 均为可选字段，旧数据无需迁移。

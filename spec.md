# Spec：人物正面图 → 角色三视图 → 后续流程

## 1. 目标与范围

用户可在角色创建页上传一张人物正面全身图；点击生成时，该图作为强身份参考送入现有图片生成模型，产出与原图一致的角色原画，并在同一次任务内生成正面 / 侧面 / 背面三视图。原始正面图与三视图都持久化到角色资产，刷新或重进编辑页仍可见，后续流程优先使用三视图。

范围内：
- 后端：参考图上传/删除接口、任务创建参数、参考图生图、任务内三视图生成、持久化与孤儿文件清理。
- 前端：创建页上传/预览/替换/删除、客户端校验、生成时携带参考图、DesignCenter 展示原始图与三视图、生成中防重复提交。
- 测试：四个必需场景的自动化测试 + 现有测试回归。

范围外（明确不做）：
- 不重构无关模块，不新增第三方依赖，不改下游 `design_views` 契约（仍为独立 `front/side/back` 三字段）。
- 不改纯文本流程的行为（无参考图时：任务不生成三视图、不保留旧 `design_views`）。
- 不新增数据库/ORM；沿用现有 JSON 存储结构。

## 2. 现有数据流（勘察结论）

1. 创建页 `studio/frontend/src/pages/Workspace.tsx` → `api.createTask(goal, overrides)` → `POST /api/tasks`。
2. `studio/backend/api/routes.py` `build_router(runtime)`：`CreateTaskRequest(goal, overrides, turbo, asset_id)` → `runtime.start_task(...)`（后台线程）。
3. `studio/backend/agent_runtime/runtime.py::_run` → `_call_external` 用 `agent/generation/external.py::build_image_prompt` 组词 → `studio/backend/model_service/service.py::ImageProvider.generate`（OpenAI 兼容 / DashScope wanx 异步）。成功后写入 `asset.image`，再 `asset.pop("design_views", None)`，存 `AssetStore` 并发 `ASSET_UPDATE`；`_record` 写历史。
4. 三视图目前只在设计中心手动触发：`DesignCenter.tsx` → `POST /api/design/views` → `model_service.service.py::generate_turnaround(settings, asset.image.url, front_image=image)`，side/back 写回 `asset.design_views`，`front = 原画`；失败抛 502 并保留旧 views。
5. 图片落盘：`GENERATED_DIR` + `safe_generated_path(name)`（仅允许 `GENERATED_DIR` 下 `.png/.jpg/.jpeg/.webp`）；浏览器访问 `/api/generated/<file>`；`_resolve_cloud_image` 将本地代理 URL 转 data URI 给 qwen 多模态模型；`_localize_asset` 负责把资产里的本地地址转云端可访问地址。
6. 测试契约（必须保留）：`studio/backend/tests/test_design_views.py`
   - `test_task_generation_never_calls_views_model`：无参考图时任务绝不调用 views 模型。
   - `test_regenerated_asset_drops_old_design_views`：重新生成后旧 `design_views` 被清除。
7. 前端请求封装 `studio/frontend/src/api/client.ts::request()` 固定 `Content-Type: application/json` 并 `response.json()`，**不能**用于 multipart；上传需独立 `fetch` + `authHeaders()` + `FormData`。
8. 事件分类表 `studio/frontend/src/hooks/useTaskFeed.ts::EVENT_META`，新事件类型必须在此登记（否则显示为原始 type 名）。

## 3. 关键决策与假设

- **D1 参考图存放位置**：复用生图产物目录 `GENERATED_DIR`，文件名前缀 `reference_`。理由：可直接复用 `safe_generated_path`、`/api/generated` 代理、`_resolve_cloud_image`（qwen 需要 data URI）与 `_localize_asset`，零新增存储设施。
- **D2 上传校验**：后端用 PIL `Image.open` 校验真实格式（PNG/JPEG/WEBP），限制 10 MB（`MAX_REFERENCE_BYTES`），并读取宽高；前端先按 MIME + 扩展名 + `size` 预校验，给出即时提示。不接受 SVG/GIF/HEIC。
- **D3 参考图生图**：复用 `ImageEditProvider` + 现有 `TURNAROUND_EDIT_MODEL = "qwen-image-2.1-turbo"`（单图 + 文本指令），新增 `generate_from_reference(settings, reference_url, prompt, deadline=None)`。不新增 provider、不改 `ImageProvider`。
- **D4 无模型时的行为**：用户上传了参考图但模型未启用/未配置时，任务**失败**并返回可操作提示（明确说明需要开启并配置模型）。不静默降级为纯文本，否则违背“上传后必须实际使用这张图”。
- **D5 三视图生成时机**：仅当本次任务带 `reference_image` 时，在任务线程内、原画成功落库后自动调用 `generate_turnaround`，写入 `design_views`（`front=新原画`, `side`, `back`）。无参考图时保持旧行为（不生成、清除旧 views）。
- **D6 三视图失败语义**：任务仍算成功（原画已产出），`asset.design_views_error = {kind, detail}` 持久化，发 `MODEL_FALLBACK` `stage="views"`；原始正面图绝不删除；用户可在 DesignCenter 用现有按钮重试（现有 `POST /api/design/views` 会覆盖错误并写新 views）。
- **D7 下游契约**：继续使用 `design_views` 的独立三字段，front 即角色原画；后续流程（DesignCenter `viewUrl` 等）优先三视图的逻辑保持不变；额外保留 `asset.reference_image` 作为身份增强参考，不改变 `design_views` 结构。
- **D8 防重复提交**：前端按钮 `loading={busy || agentRunning}`；后端上传接口无副作用幂等（同名内容按 sha 去重不影响），任务创建仍由现有机制保护。
- **D9 孤儿文件清理**：
  - 替换上传成功后，前端调用 `DELETE /api/character/reference/{old}`（尽力而为，失败不阻塞）。
  - `DELETE /api/character/reference/{name}` 若该文件仍被任何历史记录 / 当前资产引用 → `409`，避免删除在用图。
  - 删除历史记录 / 清空历史时，扫描剩余记录与资产，清理不再被引用的 `reference_` 文件。
  - 删除失败/生成失败都不删除参考图。

## 4. 后端改动（精确到文件与函数）

### 4.1 `agent/generation/external.py`
新增：

```python
_IDENTITY_LOCK_ZH = (
    "严格以参考图人物为唯一身份来源，保持脸型、五官、发型、发色、肤色、体型比例、"
    "服装款式与配色、配饰和标志性细节完全一致；禁止重新设计人物、禁止换脸、"
    "禁止改变服装；只允许按下方描述调整动作、姿态与画面呈现。"
)
_IDENTITY_LOCK_EN = (
    "Use the reference person as the sole identity source. Keep face shape, facial features, "
    "hairstyle, hair color, skin tone, body proportions, costume design and colors, accessories "
    "and signature details exactly consistent with the reference image. Do not redesign the "
    "character, do not change the face, do not change the costume; only adjust pose, gesture "
    "and presentation as described below."
)

def build_reference_image_prompt(goal, overrides=None, enhanced_prompt=None, style=None):
    """身份锁定前缀 + 现有 build_image_prompt 的完整构图/风格约束。"""
```

实现：先 `base = build_image_prompt(...)`，按 `_is_chinese(base)` 选前缀，返回 `"{lock} {base}"`。

### 4.2 `studio/backend/model_service/service.py`
新增常量与函数：

- `REFERENCE_EDIT_MODEL = TURNAROUND_EDIT_MODEL`（复用，不新增模型名）。
- `MAX_REFERENCE_BYTES = 10 * 1024 * 1024`
- `validate_reference_image(data: bytes) -> dict`：PIL 打开校验 `format in {"PNG","JPEG","WEBP"}`，超限抛 `ValueError("图片超过 10MB 限制")`，返回 `{mime,width,height,bytes,ext}`。
- `save_reference_image(data: bytes, *, sha: str | None = None) -> dict`：写入 `GENERATED_DIR/reference_<时间戳>_<sha8>.<ext>`，返回 `{file,url,mime,width,height,bytes}`（`url` 用现有 `/api/generated/<file>` 形式，复用现有 helper）。
- `generate_from_reference(settings, reference_url, prompt, deadline=None)`：`ImageEditProvider(settings).edit(reference_url, prompt, allow_wanx_fallback=False)`；校验返回文件经 `safe_generated_path` 存在且非空白（复用 `_validate_view_image` 的非空白判定或等价检查）；返回 `{file,url,model,provider,size,prompt,reference_url}`。失败抛原始异常（由 runtime 分类）。

### 4.3 `studio/backend/agent_runtime/runtime.py`
- `start_task(goal, overrides=None, turbo=False, asset=None, reference_image=None)` 透传。
- `_run(..., reference_image=None)`：
  - 把 `reference_image` 存入 `asset["reference_image"]`（在 supervisor 产物返回后合并，或在 `asset` dict 原地写入）。
  - `_call_external(..., reference_image=None)`：存在参考图时走 `build_reference_image_prompt` + `neutralize_hard_ip` + `generate_from_reference`；无参考图保持原 `ImageProvider.generate` 路径。
  - 参考图分支里模型未启用/配置不完整 → 不返回 `(None,None,None)`，而是抛/返回明确 `image_error`（`kind="reference-model-missing"`），由 `_run` 按 strict 失败，提示“已上传正面图但模型未开启，请在设置→模型设置启用并配置模型后重试”。
  - 成功后：若 `reference_image` 且原画成功 → 发 `MODEL_START stage="views"`，调用 `generate_turnaround(settings, image["url"], front_image=image, deadline=...)`：
    - 成功：`asset["design_views"] = {**旧, **views}`，清除 `asset["design_views_error"]`，发 `MODEL_VIEWS`。
    - 失败：`asset["design_views_error"] = {kind, detail}`，发 `MODEL_FALLBACK stage="views"`；**不删除** `asset["reference_image"]`，任务继续成功收尾。
  - 无参考图：保留现有 `asset.pop("design_views", None)`，不发 views 事件（兼容现有测试）。
- `_record`：历史记录资产快照自动包含 `reference_image` / `design_views` / `design_views_error`（无需改字段，因为整体 `asset` 已入库）。

### 4.4 `studio/backend/api/routes.py`
新增：

- `POST /api/character/reference`（`UploadFile`）：
  - 读全部字节，`len > MAX_REFERENCE_BYTES` → 413；`validate_reference_image` 失败 → 415（`detail` 含可操作原因）。
  - `save_reference_image` → 返回参考图 meta（200）。
- `DELETE /api/character/reference/{name}`：
  - 校验 `name.startswith("reference_")` 且 `safe_generated_path(name)` 命中，否则 404/400。
  - 引用检查：遍历 `runtime.history.list()` 的 `asset` 与 `reference_image.file`，以及 `runtime.assets`（如有 list）→ 命中则 409 `detail="该图片仍被角色引用"`。
  - 未引用才 `os.remove`。
- `CreateTaskRequest` 增加 `reference_image: str | None = None`。
- `POST /api/tasks`：若 `reference_image`：
  - `safe_generated_path(name)` 与 `startswith("reference_")` 校验 → 非法 400。
  - 构造 meta（文件存在 + PIL 读宽高 + mime），传 `runtime.start_task(..., reference_image=meta)`。
- `_localize_asset(asset, base)`：增加 `reference_image` 与 `design_views` 的本地地址本地化（保持现有 design_views 处理不变，若原本已处理则只补 `reference_image`）。
- `DELETE /api/history/{id}`、`DELETE /api/history`：删除后调用新增内部 `_cleanup_orphan_references(runtime)`，仅删除不再被任何剩余 history/asset 引用的 `reference_` 文件（异常吞掉并记录日志，不影响删除响应）。

### 4.5 API 契约汇总

| 方法 | 路径 | 请求 | 响应 |
| --- | --- | --- | --- |
| POST | `/api/character/reference` | multipart `file` | `{file,url,mime,width,height,bytes}` |
| DELETE | `/api/character/reference/{name}` | - | `204` / `409` / `404` |
| POST | `/api/tasks` | 原字段 + `reference_image?: string` | 原响应 + `reference_image` 校验 |

新增/变更数据字段：
- `CreativeAsset.reference_image?: {file,url,mime,width,height,bytes}`
- `CreativeAsset.design_views_error?: {kind, detail}`
- `CreateTaskRequest.reference_image?: string`
- 新事件 `MODEL_VIEWS`（前端 `types.ts` + `useTaskFeed.EVENT_META` 登记，`kind="generate"`, `title="三视图出图"`, `tone="success"`）。

## 5. 前端改动

### 5.1 `studio/frontend/src/types.ts`
- 新增 `ReferenceImage`；`CreativeAsset` 增加 `reference_image?`、`design_views_error?`。
- `TaskEvent` 的 `type` 联合/字符串处理补 `MODEL_VIEWS`（按现有定义方式）。

### 5.2 `studio/frontend/src/api/client.ts`
- `uploadCharacterReference(file: File, signal?)`：`fetch("/api/character/reference", {method:"POST", body: FormData, headers: authHeaders()})`（**不要**设置 Content-Type，让浏览器带 boundary），错误解析按现有 `ApiError` 风格。
- `deleteCharacterReference(name)`：`DELETE /api/character/reference/{encodeURIComponent(name)}`。
- `createTask` 增加可选 `referenceImage?: string`，放入 body `reference_image`。

### 5.3 `studio/frontend/src/pages/Workspace.tsx`
- 新增状态：`reference`、`uploading`、`referenceError`、隐藏 `<input type="file" accept="image/png,image/jpeg,image/webp">`。
- 上传入口卡片：提示文案「请上传光线均匀、人物正面站立、面部与服装无遮挡的全身图」；支持预览（`SafeImage`）、替换、删除；客户端校验格式与 10MB，错误 toast。
- 替换时上传成功后尽力 `deleteCharacterReference(旧 file)`。
- `generate()`：`api.createTask(text, cleaned, undefined, undefined, reference?.file)`；`busy || agentRunning` 防重复；失败保留 `reference` 状态与预览。
- 未上传时行为与现状完全一致。

### 5.4 `studio/frontend/src/pages/DesignCenter.tsx`
- 若 `asset.reference_image` 存在，展示“原始正面图”卡片（缩略图 + 只读）。
- 若 `asset.design_views_error` 存在，持久化展示失败原因并提供“重新生成三视图”按钮（复用现有 `generateViews`）。
- 后续流程继续优先 `design_views`（现有 `viewUrl` 逻辑不改）。

### 5.5 `studio/frontend/src/hooks/useTaskFeed.ts`
- `EVENT_META.MODEL_VIEWS = { kind: "generate", title: "三视图出图", tone: "success" }`。

## 6. 测试

新增 `studio/backend/tests/test_character_reference.py`（unittest + FastAPI TestClient + mock，风格对齐 `test_design_views.py`）：

1. `test_upload_reference_and_generate_views`：合法 PNG 上传 → 200 meta；`POST /api/tasks` 带 `reference_image` → mock `generate_from_reference` 产出原画、mock `generate_turnaround` 产出 side/back → 资产含 `reference_image` + `design_views` 四要素；`GET /api/assets/{id}` 重读一致；历史记录可再读。
2. `test_task_without_reference_keeps_text_pipeline`：不传 `reference_image` → 走 `ImageProvider.generate`，不调用 `generate_turnaround`，无 `reference_image` 字段。
3. `test_reference_rejects_bad_type_and_oversize`：GIF/SVG 或伪造扩展名 → 415；超过 `MAX_REFERENCE_BYTES` → 413；`POST /api/tasks` 传不存在/非 `reference_` 前缀 → 400。
4. `test_generation_failure_keeps_reference_and_allows_retry`：mock `generate_from_reference` 抛错（strict 策略）→ 任务 failed，参考图文件仍存在且资产/历史仍可引用；再次调用 `POST /api/design/views` 或重新上传同图后重试成功。
5. 孤儿文件：`DELETE /api/character/reference/{name}` 被引用 → 409；删除历史后未引用文件被清理。

回归：`studio/backend/tests/test_design_views.py` 全部通过（尤其两个契约测试）。

## 7. 验证命令

后端（在 `d:\pyProject\creative-forge`）：
```powershell
python -m unittest studio.backend.tests.test_character_reference -v
python -m unittest studio.backend.tests.test_design_views -v
python tests/run_tests.py
ruff check agent agents artgen adapters tests studio/backend
black --check agent agents artgen adapters studio/backend tests
```
前端（在 `studio/frontend`）：
```powershell
npm run lint
npm run test
npm run build
```
（若仓库 `package.json` 另有 typecheck 脚本，一并执行。）

## 8. 验收标准对照

- 创建页可上传/预览/替换/删除正面图，格式与大小前后端校验。
- 上传后生成：原画由参考图驱动，三视图 front/side/back 落库，刷新后仍在，可直接进入后续流程。
- 生成中明确状态且不可重复提交；格式错误/超限/生图失败均有可操作提示。
- 生图失败保留原始正面图并可重试。
- 无参考图时纯文本流程与现有测试完全不变。
- 无孤儿文件：替换/删除/删历史均有清理与引用保护。
- API Key 仍走现有 `ModelSettingsStore` 配置，无硬编码。

## 9. 风险与回滚

- 参考图分支依赖 qwen 多模态模型可用性；不可用时不静默降级（D4），用户可见失败原因。回滚：删除任务内 views 生成分支与上传入口即可，`design_views`/`reference_image` 为可选字段，不影响旧数据。
- 任务耗时增加一次 `generate_turnaround` 调用（最长受 deadline 约束）；失败不影响原画交付。

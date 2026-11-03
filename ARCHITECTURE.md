# CreativeForge 架构

CreativeForge 将自然语言需求转化为可检查、可试玩、可导出的游戏资产。产品由单一
Studio 应用承载，后端使用共享同一套资产数据流的 Python 管线。

## 运行流程

```text
用户需求
   |
   v
React Studio
   |
   v
FastAPI 路由 / WebSocket
   |
   v
AgentRuntime
   |
   +--> Creative Agent / 多智能体规划
   +--> 美术资产生成
   +--> PReCon 像素重建
   +--> FAlign 动画对齐
   +--> GImport 引擎打包
   +--> 场景 / PVE / 试玩服务
   |
   v
CreativeAsset -> 预览 -> 版本 -> 导出
```

`CreativeAsset` 是规划、生成、质量检查、预览和导出之间的统一边界。当用户意图
不需要某个处理环节时，该环节可以被跳过。

## 目录职责

```text
studio/frontend/        React 18 + TypeScript + Vite 工作台
studio/backend/         FastAPI、智能体运行时、业务服务、API 和 WebSocket

agent/                  意图分析、规划、执行和失败恢复
agents/                 多智能体专家实现
protocol/               智能体消息与状态机

precon/                 像素重建管线
falign/                 抽帧、对齐和动画质检
gimport/                引擎清单、图集、适配器和导出
artgen/                 确定性的 2D 生成与动画工具
adapters/               外部能力适配器，包括云模型服务

core/                   核心适配器契约
schemas/                CreativeAsset JSON Schema
packages/creative-core/ 参考接口与模型定义

benchmark/              质量评测与回归基线
examples/               示例载荷和比赛演示
games/                  可在浏览器中运行的演示游戏
tests/                  管线、发布与集成检查
```

生成的上传文件、导出文件、历史记录和模型输出属于运行期数据，位于
`studio/backend/data/` 与 `studio/backend/generated/`，不属于应用源码结构。

## 后端主要组件

`studio/backend/app.py` 创建 FastAPI 应用，并挂载 HTTP、WebSocket、PVE 和场景
路由。存在前端构建产物时，该入口同时提供 SPA 页面和浏览器演示游戏。

`studio/backend/agent_runtime/runtime.py` 负责一次任务的完整执行生命周期：

- 解析需求并生成执行计划；
- 执行所需的资产能力；
- 通过 WebSocket 推送任务进度；
- 持久化任务、资产和历史状态；
- 在存在回退方案时恢复失败环节。

业务服务按职责划分：

- `animation_service/`：帧生成、动作批处理和动画质检；
- `asset_service/`：资产与任务持久化；
- `export_service/`：生成可直接进入引擎的角色和工程包；
- `model_service/`：模型设置、外部图片/视频调用和用量记录；
- `pve_service/` 与 `scene_service/`：敌人档案、战役编译和可玩场景数据；
- `showcase_service/`：OneTake 渲染任务；
- `storage_service/`：可选的 S3 兼容对象存储；
- `cloud_service/`：云厂商配置与用量统计。

## 前端

前端只负责展示和交互。服务端请求统一集中在
`studio/frontend/src/api/client.ts`，实时任务更新使用
`src/websocket/taskStream.ts`。页面组合出工作台、资产检查器、动画控制、场景编辑、
PVE 试玩、版本中心、历史和导出视图。

画布和 3D 预览优先保留实际工作空间。前端测试会检查主要模块导入边界、动效令牌
和 WebSocket 行为。

## 数据与持久化

- 运行期 JSON 文件采用原子写入；主文件截断时可从有效备份恢复。
- 大型生成资产保存在磁盘，API 返回稳定的资产 ID 或 URL，不直接嵌入二进制内容。
- 可选云服务默认关闭。凭据只从本地加密配置或环境变量读取，配置 API 不会返回明文。
- 历史记录、导出文件与生成媒体都是本地运行状态，不应视为源码。

## 扩展位置

- 在 `agent/capability/capability_registry.py` 中增加资产能力。
- 在 `adapters/cloud_backends/models/` 中增加云模型。
- 在 `gimport/adapters/` 中增加目标引擎。
- 在 `studio/backend/` 中实现功能服务和路由，再注册到
  `studio/backend/app.py`。
- 在 `studio/frontend/src/` 中增加页面和路由，并复用统一 API 与 WebSocket 客户端。

## 验证

从仓库根目录运行：

```powershell
python tests/run_tests.py
python -m pytest -q
python tests/release/run_release_tests.py
npm --prefix studio/frontend run lint
npm --prefix studio/frontend run typecheck
npm --prefix studio/frontend run test
npm --prefix studio/frontend run build
```

后端与前端是两个明确的产品边界；仓库中不存在并行的遗留后端或前端。

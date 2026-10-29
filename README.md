# CreativeForge Studio

**面向游戏开发的 AI 资产生产工作台**：输入一句自然语言，由多智能体自主规划，经自研技术链（PReCon / FAlign / GImport / 3D 管线）产出可直接导入 Unity / Cocos / Godot 的游戏角色、动画与工程资产。

> CreativeForge 不是单一的模型调用工具，而是一套开放式游戏资产生成系统：统一 `CreativeAsset` 资产协议连接像素重建、动画切帧对齐、引擎自动导入与 3D 试玩，实现从创意描述到可运行资源的一体化闭环。

## 技术栈

- **前端** — `studio/frontend`：React 18 + TypeScript + Vite + Tailwind CSS
- **后端** — `studio/backend`：FastAPI（REST + WebSocket 事件流）
- **智能体** — `agent/` + `agents/`：Supervisor 规划调度
- **自研引擎** — `precon/`（像素重建）、`falign/`（动画对齐）、`gimport/`（引擎导入）、`artgen/` `sprite/`（2D 生成链路）、`three_d/`（3D 管线）
- **外部能力** — `adapters/`（云生成 / 模型服务商适配）
- **契约层** — `core/` `protocol/` `schemas/` `packages/`

## 目录结构

```text
creative-forge/
├── studio/
│   ├── frontend/            # React + Vite 前端（工作台 / 资产库 / 试玩舞台）
│   └── backend/             # FastAPI 后端（REST + WebSocket）
├── agent/  agents/          # 智能体层（单 Agent + 多 Agent 编排）
├── precon/  falign/  gimport/  # 自研引擎层
├── artgen/  sprite/         # 2D 角色 / 精灵生成链路
├── three_d/                 # 3D 资产管线
├── adapters/                # 外部能力 / 模型服务商适配层
├── core/  protocol/  schemas/  packages/  # CreativeAsset 契约层
├── benchmark/               # 质量验证与评测
├── examples/  games/        # 演示与内置小游戏
├── tests/  tests/release/   # 测试体系
└── docs/                    # 架构与设计文档
```

## 快速启动

> 环境要求：Python 3.11+、Node.js 18+（推荐 20+）。以下命令均在**仓库根目录**执行。

### 1. 安装依赖

```bash
# 虚拟环境
python -m venv .venv
.venv\Scripts\Activate.ps1        # Windows PowerShell；macOS/Linux 用: source .venv/bin/activate

# 后端依赖
pip install -r requirements.txt

# 前端依赖
npm --prefix studio/frontend install
```

### 2. 启动后端

```bash
python -m studio.backend.main      # http://127.0.0.1:8600
```

可选参数：`--host`、`--port`、`--reload`（开发热重载）。

### 3. 启动前端（开发模式）

另开一个终端：

```bash
npm --prefix studio/frontend run dev   # http://127.0.0.1:5173（自动代理 /api、/ws 到 8600）
```

### 4. 生产 / 单进程模式（后端托管前端）

```bash
npm --prefix studio/frontend run build   # 构建到 studio/frontend/dist
python -m studio.backend.main            # 后端自动托管前端，访问 http://127.0.0.1:8600
```

## 常用命令

### 测试

```bash
# 后端单元测试（示例）
python -m unittest studio.backend.tests.test_design_views -v

# 契约 / 发布测试
python tests/run_tests.py
python tests/release/run_release_tests.py
```

### 前端检查

```bash
npm --prefix studio/frontend run typecheck   # 类型检查
npm --prefix studio/frontend run lint        # ESLint
npm --prefix studio/frontend run test        # Vitest
```

### 构建

```bash
npm --prefix studio/frontend run build       # tsc -b && vite build
```

## 模型配置（可选）

后端默认以内置确定性管线运行；接入自定义大模型后可使用 AI 原画、三视图、图生视频等能力。启动后在「设置 → 模型设置」填写 Base URL 与 API Key 即可，密钥仅读取环境变量 / `.env`，不落库。

## 文档

- [架构设计](docs/architecture.md)
- 更多设计与决策记录见 [docs/](docs/)
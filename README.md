# CreativeForge Studio

CreativeForge Studio 是一个面向游戏开发的 AI 资产生产工作台。用户输入
自然语言创意，由智能体完成规划与调度，再通过像素重建、动画对齐、引擎导入、
场景编译和试玩管线，生成可进入 Unity、Cocos 或 Godot 的角色、动画和工程资产。

项目以 `CreativeAsset` 串联设计、生成、检查、动效、试玩和导出流程。目标是把
「创意描述」转化为可检查、可试玩、可导出的游戏资源。

## 技术栈

- 前端：React 18、TypeScript、Vite、Tailwind CSS
- 后端：FastAPI、REST API、WebSocket
- 智能体：Supervisor 规划与多 Agent 调度
- 资产管线：PReCon、FAlign、GImport、2D 动画、3D 管线
- 外部能力：模型服务与云生成适配层

## 环境要求

- Python 3.11+
- Node.js 20.19+、22.13+ 或 24+（推荐 22 LTS）
- npm

以下命令均从仓库根目录执行。

## 安装依赖

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
npm --prefix studio/frontend install
```

macOS / Linux 激活虚拟环境：

```bash
source .venv/bin/activate
```

## 通过 8600 端口启动

`8600` 模式由后端托管 `studio/frontend/dist` 中已构建的前端，适合本地完整运行或演示。首次启动前需要先构建前端：

```powershell
npm --prefix studio/frontend run build
python -m studio.backend.main --host 127.0.0.1 --port 8600
```

启动后访问：

- 有开屏动画：<http://127.0.0.1:8600/#opening>
- 没有开屏动画：<http://127.0.0.1:8600/#noopening>

## 通过 5173 端口启动

`5173` 是 Vite 开发服务器，支持前端热更新；后端仍需运行在 `8600`。

终端一，启动后端：

```powershell
python -m studio.backend.main --host 127.0.0.1 --port 8600
```

终端二，启动前端：

```powershell
npm --prefix studio/frontend run dev
```

启动后访问：

- 有开屏动画：<http://127.0.0.1:5173/#opening>
- 没有开屏动画：<http://127.0.0.1:5173/#noopening>

Vite 会将 `/api` 和 `/ws` 请求代理到 `http://127.0.0.1:8600`。如需连接其他
后端地址，可设置 `VITE_BACKEND`。

## Vercel + Render 分离部署

- Vercel 项目根目录设为 `studio/frontend`，Framework 选择 Vite。
- Render 使用仓库根目录的 `Dockerfile.render`（或直接同步 `render.yaml`），部署为免费 Web Service。
- Vercel 构建环境设置 `VITE_BACKEND_URL=https://<render-service>.onrender.com`。
- Render 运行环境设置 `STUDIO_CORS_ORIGINS=https://<vercel-project>.vercel.app`；如绑定自定义域名，用逗号继续追加。
- 生产前端不应写入 `VITE_STUDIO_TOKEN`：所有 `VITE_*` 值都会进入浏览器 bundle。需要鉴权时，由使用者在设置页输入令牌，后端通过 `STUDIO_AUTH_TOKEN` 校验。

REST、生成资源和 WebSocket 会使用同一个后端源站；WebSocket 不可用时，任务流会自动回退到 REST 轮询。

## 开屏动画说明

启动命令本身相同，是否显示开屏动画由访问地址中的哈希片段决定：

| 访问方式 | 行为 |
| --- | --- |
| `/#opening` | 强制显示开屏动画 |
| `/#noopening` | 强制跳过开屏动画 |
| 无上述片段 | 按本地存储记录判断，默认每天显示一次 |

开屏播放期间可按 `Esc`、`Enter` 或点击页面跳过。

## 前端构建过期

如果页面出现「前端构建已过期」提示，说明前端源码比 `studio/frontend/dist` 中的构建产物新。请从仓库根目录重新构建：

```powershell
npm --prefix studio/frontend run build
```

构建完成后，在浏览器中执行强制刷新（Windows 通常为 `Ctrl+F5`）。

仅在使用 `8600` 的单进程模式时需要处理此提示；`5173` 开发模式直接读取源码，不依赖 `dist`。

## 常用检查

```powershell
.\.venv\Scripts\python.exe tests\run_tests.py
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe tests\release\run_release_tests.py
npm --prefix studio/frontend run typecheck
npm --prefix studio/frontend run lint
npm --prefix studio/frontend run test
npm --prefix studio/frontend run build
```

## 项目结构

```text
studio/frontend/       React 工作台
studio/backend/        FastAPI、智能体运行时与业务服务
agent/  agents/        智能体规划与多 Agent 编排
precon/                像素重建
falign/                动画对齐
gimport/               引擎导入
artgen/                2D 生成与动画
adapters/              模型、云服务和 OneTake 适配
core/  protocol/       核心接口与 Agent 协议
schemas/  packages/    CreativeAsset 契约
benchmark/  tests/     质量评测与测试
examples/  games/      示例和浏览器演示
```

`studio/backend/data/`、`studio/backend/generated/`、历史记录和导出文件属于
本地运行时数据，不属于源码结构。

## 项目文档

关键文档共六份：

- [README.md](README.md)：安装、启动和日常使用
- [ARCHITECTURE.md](ARCHITECTURE.md)：运行时流程、目录职责和扩展点
- [PRODUCT.md](PRODUCT.md)：产品定位、用户和边界
- [DESIGN.md](DESIGN.md)：视觉系统与交互规范
- [PROMPT_GUIDE.md](PROMPT_GUIDE.md)：角色、场景和 PVE 敌人提示词写法
- [CONTRIBUTING.md](CONTRIBUTING.md)：开发约定和质量门

## 模型配置

后端默认可使用内置确定性管线。需要 AI 原画、图生视频等能力时，可在
「设置 → 模型设置」中填写模型服务地址与密钥；密钥通过环境变量或本地 `.env`
提供，不写入仓库。

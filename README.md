# CreativeForge Studio

CreativeForge Studio 是一个面向游戏开发的 AI 资产生产工作台。用户可以输入自然语言创意，由多智能体完成规划与调度，再通过像素重建、动画对齐、引擎导入和 3D 试玩等管线，生成可导入 Unity、Cocos 或 Godot 的游戏角色、动画及工程资产。

项目以 `CreativeAsset` 资产协议串联设计、生成、检查、动效、试玩和导出流程，目标是把「创意描述」转化为可直接进入游戏引擎的可用资源。

## 技术栈

- 前端：React 18、TypeScript、Vite、Tailwind CSS
- 后端：FastAPI、REST API、WebSocket
- 智能体：Supervisor 规划与多 Agent 调度
- 资产管线：PReCon、FAlign、GImport、2D 动画、3D 管线
- 外部能力：模型服务与云生成适配层

## 环境要求

- Python 3.11+
- Node.js 18+（推荐 20+）
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

Vite 会将 `/api` 和 `/ws` 请求代理到 `http://127.0.0.1:8600`。如需连接其他后端地址，可设置 `VITE_BACKEND`。

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
npm --prefix studio/frontend run typecheck
npm --prefix studio/frontend run lint
npm --prefix studio/frontend run test
```

## 项目结构

```text
creative-forge/
├── studio/frontend/       # React 工作台
├── studio/backend/        # FastAPI 后端
├── agent/  agents/        # 智能体与多 Agent 编排
├── precon/                # 像素重建
├── falign/                # 动画对齐
├── gimport/               # 引擎导入
├── artgen/  sprite/       # 2D 生成管线
├── three_d/               # 3D 资产管线
├── adapters/              # 模型与云服务适配
├── core/  protocol/       # CreativeAsset 协议与契约
├── benchmark/             # 质量评测
└── tests/                 # 测试
```

## 模型配置

后端默认可使用内置确定性管线。需要 AI 原画、图生视频等能力时，可在「设置 → 模型设置」中填写模型服务地址与密钥；密钥通过环境变量或本地 `.env` 提供，不写入仓库。

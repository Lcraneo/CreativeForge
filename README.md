# CreativeForge AI

**面向游戏开发的自主规划型 AI 资产生产系统**：一句自然语言目标，经多智能体自主规划与自研技术链（PReCon / FAlign / GImport）处理，产出可直接导入 Unity / Cocos / Godot 的游戏资产。

> CreativeForge 不是一个调用生成模型的工具，而是一个面向游戏开发的自主规划型 AI 资产生产系统，通过 CreativeAsset 统一协议连接自研像素重建、动画切帧对齐和引擎自动导入，实现从创意描述到可运行游戏资源的一体化生成。

## 1. Overview

```text
                自然语言目标（"创建一个像素RPG火焰法师Boss，导入Unity"）
                                  |
                                  v
                    CreativeForge Studio（Web 控制台）
                                  |
                                  v
                     Supervisor Agent 自主规划任务图
                                  |
            +---------------------+---------------------+
            |                     |                     |
        Art Agent          Animation Agent        Engine Agent
       生成 + PReCon            FAlign                GImport
            |                     |                     |
            +---------------------+---------------------+
                                  |
                          QA Agent 质量验证
                                  |
                          游戏引擎就绪资产（Unity / Cocos / Godot）
```

- **产品层** — `studio/`：React 18 + TypeScript + Vite 前端（智能体任务图 / 资产检查器 / 像素工作台 / 动画工作台 / 基准中心 / 导出中心）+ FastAPI 后端（REST + WebSocket 事件流）
- **智能层** — `agents/` + `agent/`：Supervisor 规划调度专家智能体，带 QA 修复轮、检查点与失败恢复
- **技术层** — `precon/` `falign/` `gimport/`：三项自研引擎
- **标准层** — `schemas/` + `packages/creative-core/`：CreativeAsset v1.0 统一资产协议（冻结契约）
- **验证层** — `benchmark/`：数据集 + 对比指标 + CF Score

## 2. Problem

独立游戏开发者做一个游戏角色需要：美术设计 → 手动像素化 → 手动切帧对齐 → 手动配置动画 → 手动拼 Prefab → 导入引擎，**12 步人工操作、约 45 分钟**，且 AI 生成素材直接使用时有像素错位、动画漂移、脚滑、抖动等硬伤。

## 3. Innovation

### PReCon — 像素重建引擎（`precon/`）

AI 图片 → 网格推断 → 语义化调色板重建 → 轮廓修复 → 风格一致性 → 质量评估。

### FAlign — 动画切帧对齐引擎（`falign/`）

帧抽取 → 锚点检测（root/feet/center/head）→ 运动相位对齐 → 根运动纠偏（区分真实位移与漂移）→ 时序一致性。

### GImport — 引擎一键导入管线（`gimport/`）

CreativeAsset → 资产清单 → 精灵图集 → 动画剪辑 → Prefab → 引擎适配器（Unity/Cocos/Godot）→ 运行时校验 → 一键导出真实 zip 工程包。

## 4. Architecture

见 [docs/architecture.md](docs/architecture.md)：八层架构与 phase 规格 → 合并位置映射。

## 5. Multi-Agent System

```text
Supervisor Agent（规划 + 路由 + QA/修复循环 + 记忆）
  -> Art Agent（Generation + PReCon）
  -> Animation Agent（FAlign）
  -> Engine Agent（GImport：Unity / Cocos / Godot）
  -> QA Agent（验证 -> 修复轮）
  -> Memory Agent（风格 / 版本 / 检查点）
```

入口：`agents.supervisor.supervisor.SupervisorAgent.run(goal)`；Studio 运行时以事件流（`PLAN_CREATED / AGENT_START / AGENT_DONE / QUALITY_REPORT / TASK_COMPLETE`）推送全过程。

## 6. Quick Start

```bash
# 后端 + 前端（推荐）
pip install -r studio/backend/requirements.txt
npm --prefix studio/frontend install && npm --prefix studio/frontend run build
python -m studio.backend.main            # http://127.0.0.1:8600

# 前端开发模式（热更新，代理到 8600）
npm --prefix studio/frontend run dev     # http://127.0.0.1:5173

# Docker 一键起
docker compose up -d
```

命令行直跑：

```python
from agents.supervisor.supervisor import SupervisorAgent

result = SupervisorAgent().run("生成一个像素RPG火焰法师Boss，带攻击动画，并导入Unity")
print(result["supervisor"]["status"])        # PASS
print(result["asset"]["engine"]["target"])   # unity
```

## 7. Demo

比赛固定演示（确定性，产物固化在 `examples/competition_demo/`）：

```bash
python examples/competition_demo/run_demo.py
# prompt.txt -> source/(intent+task graph) -> intermediate/(steps+messages+asset)
#            -> output/FireMageGameAsset.zip -> report/(quality+benchmark)
```

## 8. Benchmark

```bash
python -m benchmark.run_benchmark          # 写入 benchmark/results/
```

在 12 个数据集资产上实时运行真实管线（Phase 9 体系）：

| 引擎/系统 | 指标 | Baseline | CreativeForge |
| --------- | ---- | -------- | ------------- |
| PReCon | 像素一致性 | 81% | **90%** |
| PReCon | 调色板颜色数 | 37 | **16** |
| FAlign | 根漂移 px/frame | 2.25 | **0.00** |
| FAlign | 时序平滑度 | 85% | **96%** |
| GImport | 导入成功率 | — | **100%** |
| GImport | 流程 | 12 步 / 45 分钟 | **1 步 / 秒级** |
| Agent | 任务自主完成率 | — | **100%**（12/12） |

**CF Score = 96.6%**（pixel 0.30 / animation 0.30 / engine 0.25 / agent 0.15 加权）。

## 9. Roadmap

- 生成端接入真实图像/视频模型（当前为确定性管线模拟，接口已冻结）
- Benchmark 数据集扩到 1000 资产并引入人工标注
- 引擎侧：Unity Editor 插件实现进程内导入校验
- Studio 协作：多人项目空间与资产版本树

---

### 测试

```bash
python tests/run_tests.py                  # 36 项契约检查（Phase 3-7）
python tests/release/run_release_tests.py  # 12 项发布验证（四层）
python tests/dump_examples.py              # 用真实运行刷新 examples/*.json
```

### 项目结构

```text
CreativeForge/
├── core/ protocol/ schemas/ packages/    # 契约层（CreativeAsset v1.0）
├── adapters/                             # 外部能力适配层
├── precon/ falign/ gimport/              # 自研引擎层
├── agent/ agents/                        # 智能体层（单 Agent + 多 Agent）
├── studio/frontend studio/backend        # 产品层（Phase 8）
├── benchmark/                            # 验证层（Phase 9）
├── examples/competition_demo/            # 固定演示（Phase 10）
├── tests/ tests/release/                 # 测试体系
└── docs/                                 # 架构与映射文档
```

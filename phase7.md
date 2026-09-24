 **Phase 7：CreativeForge Multi-Agent System（多 Agent 协作系统）**。


# Phase 7：CreativeForge Multi-Agent System

## 阶段目标

将：

```
CreativeForge 工具链
```

升级为：

```
CreativeForge AI 游戏资产生产团队
```

即：

用户只给目标：

> 创建一个像素 RPG 火焰法师 Boss，包含待机、攻击动画，并生成 Unity 可运行资源。

系统自动：

```
理解目标

↓

规划任务

↓

分配 Agent

↓

调用 PReCon

↓

调用 FAlign

↓

调用 GImport

↓

质量检测

↓

输出项目
```

---

# 一、Phase 7 总体架构

```text
                     User Goal

                         |

                         v


              Supervisor Agent

                         |

        +----------------+----------------+

        |                |                |

        v                v                v


    Art Agent      Animation Agent    Engine Agent


        |                |                |

        v                v                v


     PReCon            FAlign          GImport


        \                |                /

         \               |               /

          +--------------+--------------+

                         |

                         v


                    QA Agent


                         |

                         v


                  Memory Agent

```

---

# 二、新增项目结构

```text
CreativeForge-Phase7-Multi-Agent

│
├── agents/
│
│   ├── supervisor/
│   │   ├── planner.py
│   │   └── task_router.py
│   │
│   ├── art_agent/
│   │   └── art_agent.py
│   │
│   ├── animation_agent/
│   │   └── animation_agent.py
│   │
│   ├── engine_agent/
│   │   └── engine_agent.py
│   │
│   ├── qa_agent/
│   │   └── qa_agent.py
│   │
│   └── memory_agent/
│       └── memory_agent.py
│
│
├── protocol/
│
│   ├── message.py
│   └── state.py
│
│
├── workflow/
│
│   ├── executor.py
│   └── checkpoint.py
│
│
├── registry/
│
│   └── capability_registry.py
│
│
├── tests/
│
│   └── agent_test.md
│
└── docs/
    └── architecture.md

```

---

# 三、核心：Supervisor Agent

这是整个系统的大脑。

职责：

1. 理解用户目标
2. 生成任务图
3. 调度 Agent

例如：

输入：

```
创建火焰法师Boss
需要攻击动画
导入Unity
```

---

Planner 输出：

```json
{
 "goal":"fire mage boss",

 "tasks":[

 {
   "id":"001",
   "agent":"ArtAgent",
   "action":"create_character"
 },


 {
   "id":"002",
   "agent":"AnimationAgent",
   "action":"create_attack_animation"
 },


 {
   "id":"003",
   "agent":"EngineAgent",
   "action":"export_unity"
 }

 ]

}
```

---

# 四、Agent 通信协议

新增统一消息：

## AgentMessage

```json
{
 "from":"ArtAgent",

 "to":"AnimationAgent",

 "type":"ASSET_READY",

 "payload":

 {
   "asset_id":"hero001"
 }
}
```

---

状态：

```text
CREATED

↓

RUNNING

↓

SUCCESS

↓

FAILED

↓

RECOVERY

```

---

# 五、Art Agent

负责：

```
视觉资产生产
```

调用：

```
Generation
    |
    v
PReCon
```

流程：

```text
Prompt

↓

角色生成

↓

像素重建

↓

CreativeAsset.pixel

```

输出：

```json
{
"type":"character",

"asset_id":"mage001",

"pixel":

{

"palette":"16",

"style":"pixel"

}

}
```

---

# 六、Animation Agent

负责：

```
动画生产
```

调用：

```
FAlign
```

流程：

```
Animation Source

↓

Frame Extraction

↓

Anchor Detection

↓

Motion Alignment

↓

Animation Asset
```

输出：

```json
{
"animation":

{

"action":"attack",

"frames":12,

"aligned":true

}

}
```

---

# 七、Engine Agent

负责：

```
游戏引擎生产
```

调用：

```
GImport
```

支持：

```
Unity

Cocos

Godot
```

输出：

```json
{
"engine":"Unity",

"package":

"FireMage.unitypackage"

}
```

---

# 八、QA Agent

这是比赛差异化重点。

很多 AI 项目：

```
生成
↓

结束
```

你的：

```
生成

↓

验证

↓

修复

↓

输出
```

QA 检测：

## Pixel Quality

```
palette

outline

style
```

## Animation Quality

```
drift

jitter

phase
```

## Engine Quality

```
missing asset

runtime error

```

输出：

```json
{
"score":0.96,

"status":"PASS"
}
```

---

# 九、Memory Agent

支持长任务。

保存：

```text
Memory

├── User Style

├── Asset Version

├── Task History

├── Error Record

└── Checkpoint

```

例如：

用户连续制作：

```
第一关角色

第二关怪物

第三关Boss
```

保持：

```
统一像素风格
```

---

# 十、Workflow Executor

负责执行任务图。

状态：

```text
Task Graph


Task1
 |
 v
Task2
 |
 v
Task3

```

支持：

## 断点续跑

例如：

```
PReCon 完成

FAlign失败
```

恢复：

```
Checkpoint

↓

继续FAlign

```

无需重新生成。

---

# 十一、最终 Demo 流程

比赛现场：

用户输入：

```
生成一个像素RPG火焰法师Boss，
带攻击动画，并导入Unity。
```

屏幕：

---

## Planner

显示：

```
任务拆解完成：

✓ 角色生成
✓ 像素优化
✓ 动画对齐
✓ Unity导入
✓ 质量检测
```

---

## Agent执行

```
Art Agent

      ↓

PReCon

      ↓

Animation Agent

      ↓

FAlign

      ↓

Engine Agent

      ↓

GImport

      ↓

QA Agent
```

---

## 输出

```
FireMageBoss/

├── texture

├── sprite atlas

├── animation

├── prefab

└── unity package

```

---

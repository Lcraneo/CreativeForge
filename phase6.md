**Phase 6：Creative Agent Planner + 自动工作流编排层设计**。

前面五个阶段已经形成了底层能力：

```text
                    Creative Agent

                         |

                         v

                CreativeAsset Contract

                         |

                         v


      ------------------------------------------------

      PReCon              FAlign             GImport

      像素重建             动画修复             引擎导入

      ------------------------------------------------


                         |

                         v

                 Game Engine Project

```

现在进入关键升级：

> 从「AI工具链」升级为「自主规划型 AI 游戏资产生产 Agent」。

---

# Phase 6 目标

用户不再操作：

* 图片处理工具
* 动画工具
* 导入工具

用户只描述最终目标：

例如：

> 创建一个像素风 RPG 火焰法师角色，包含待机、攻击动画，并导入 Cocos 项目。

Agent 自主完成：

```text
理解目标

↓

任务拆解

↓

选择能力

↓

执行流水线

↓

检查质量

↓

失败重试

↓

输出项目
```

---

# 一、整体架构

新增：

```text
CreativeForge-Agent
│
├── planner/
│
├── executor/
│
├── memory/
│
├── capability/
│
├── workflow/
│
├── monitor/
│
└── recovery/
```

---

# 二、Agent 总体架构

```text
                         User Goal

                             |

                             v


                      Intent Analyzer


                             |

                             v


                         Planner


                             |

              +--------------+--------------+

              |                             |

              v                             v


        Capability Router             Task Memory



              |

              v


        Workflow Executor


              |

              |

 ---------------------------------------------

 |                    |                       |

 v                    v                       v


PReCon              FAlign               GImport


 |                    |                       |

 ---------------------------------------------


                             |

                             v


                    Quality Validator


                             |

                             v


                    Game Project Output

```

---

# 三、Planner（核心）

这是比赛最重要展示点。

普通 Agent：

```text
用户问题

↓

LLM回答
```

---

我们的：

```text
用户目标

↓

Planner生成执行计划
```

---

例如：

输入：

```
制作一个像素RPG火焰法师
```

Planner 输出：

```json
{
 "goal":"create fire mage",

 "tasks":[

 {
   "id":"task1",
   "name":"generate_asset",
   "capability":"generation"
 },


 {
   "id":"task2",
   "name":"pixel_reconstruction",
   "capability":"PReCon"
 },


 {
   "id":"task3",
   "name":"animation_alignment",
   "capability":"FAlign"
 },


 {
   "id":"task4",
   "name":"engine_import",
   "capability":"GImport"
 }

 ]

}
```

---

# 四、Capability Registry

Agent 不直接调用代码。

维护能力注册表：

```json
{
"name":"PReCon",

"type":"processor",

"input":

"CreativeAsset",

"output":

"CreativeAsset",

"cost":

0.2,

"quality":

0.95
}
```

---

注册：

```text
Capability

├── ImageGeneration

├── PReCon

├── FAlign

├── GImport

├── CocosExport

└── UnityExport

```

---

Planner 根据需求选择：

例如：

用户：

> 制作角色并导入Unity

规划：

```text
Generation

↓

PReCon

↓

FAlign

↓

GImport(Unity)

```

---

# 五、Workflow Engine

负责执行。

类似：

LangGraph / Temporal 思想。

---

定义：

```text
Workflow


Node

↓

Edge

↓

State

```

---

例如：

```json
{

"workflow_id":"001",

"current":

"PReCon",


"state":

"running"

}

```

---

执行：

```text
Node1

Generation

完成

↓

Node2

PReCon

完成

↓

Node3

FAlign

完成

↓

Node4

GImport

完成

```

---

# 六、Executor 执行器

职责：

1. 接收任务

2. 找 Processor

3. 调用

4. 保存结果

流程：

```text
Task

↓

Capability Registry

↓

Processor

↓

CreativeAsset Update

↓

Checkpoint

```

---

# 七、Memory 系统

支持长任务。

保存：

```text
Task Memory

├── goal

├── plan

├── completed_steps

├── asset_versions

├── errors

└── checkpoints

```

---

例如：

任务做到：

```text
FAlign完成

GImport失败
```

不会重新开始：

```text
重新：

Generation

PReCon

FAlign

```

而是：

```text
读取checkpoint

↓

继续GImport
```

---

# 八、Recovery（失败恢复）

Agent 必须具备：

## 1. Retry

例如：

GImport失败：

```text
第一次

↓

重新生成manifest

↓

第二次

```

---

## 2. Fallback

例如：

Unity Adapter失败：

切换：

```text
Cocos Adapter
```

---

## 3. Human-in-loop

严重错误：

请求用户：

```
检测到角色风格冲突

是否重新生成？
```

---

# 九、Quality Gate

三个技术模块输出：

统一检查。

## PReCon

检查：

```json
{
"pixel_score":0.94
}
```

低于：

```
0.8
```

重新优化。

---

## FAlign

检查：

```
anchor_score

jitter

motion
```

---

## GImport

检查：

```
prefab

animation

runtime
```

---

# 十、最终 Demo 流程（比赛展示）

用户：

> 我要一个像素风冒险游戏角色：火焰法师，包含待机和攻击动作，并生成Cocos可运行资源。

屏幕展示：

---

## Step 1

Planner:

```
分析目标

需要：

1.角色生成
2.像素重建
3.动画修复
4.Cocos导入
```

---

## Step 2

执行：

```text
Generation

✓

PReCon

✓

FAlign

✓

GImport

✓
```

---

## Step 3

输出：

```
FireMage/

├── sprite/

├── animation/

├── prefab/

├── config/

└── cocos_project/

```

---

# 十一、Phase 6 技术亮点

比赛表达：

## 1. Goal-driven Autonomous Planning

不是工具集合。

而是：

```
用户目标

↓

Agent自主规划

↓

完成复杂生产任务
```

---

## 2. CreativeAsset as Agent Memory

资产不是文件。

而是：

```
可持续演化状态对象
```

支持：

```
Version
Checkpoint
Recovery
```

---

## 3. Self-developed AI Game Asset Pipeline

形成：

```
Planner

+

CreativeAsset

+

PReCon

+

FAlign

+

GImport
```

完整自主生产闭环。
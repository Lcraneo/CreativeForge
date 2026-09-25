基于前面前端技术栈优化，重新设计 **Phase 8：CreativeForge Studio 产品化平台（新版架构）**。
> **AI 游戏资产自主生产平台 + 多 Agent 可视化控制台 + 游戏资产编辑工作台**
核心目标：
让评委看到：

1. 这是一个真正的 AI Agent 系统；
2. Agent 不是黑盒，有完整规划过程；
3. 有自主研发技术（PReCon/FAlign/GImport）；
4. 最终产物可以进入游戏引擎。

---

# Phase 8：CreativeForge Studio v2

## 产品定位



# 一、最终前端架构

```text
CreativeForge Studio Frontend


React 18
+
TypeScript
+
Vite


        |
        |

Application Layer


        |
        +----------------+

        |                |

 Zustand             TanStack Query


        |

Realtime Layer


        |

WebSocket / Socket.IO


        |

Visualization Layer


        |

+---------------+---------------+

|               |               |

React Flow      R3F             Konva


Agent Graph     3D Preview      Pixel Editor


        |

        |

UI Layer


TailwindCSS

shadcn/ui

Framer Motion

```

---

# 二、页面重新设计

整个 Studio 分为 6 个核心页面。

---

# Page 1：Creative Workspace（主入口）

## 目标

用户提出游戏创意。

布局：

```
------------------------------------------------


CreativeForge Studio


Create your game asset


[ 输入你的创意 ]



创建一个像素风火焰法师Boss

需要：
- Idle动画
- Attack动画
- Unity导出


        [Generate]


------------------------------------------------


最近项目

FireMage

DragonBoss

ForestNPC


------------------------------------------------

```

---

## 交互

点击 Generate：

创建：

```json
{
task_id:"xxx",

goal:"FireMage Boss"

}

```

进入 Agent Pipeline。

---

# Page 2：Agent Command Center ⭐核心展示页

这是比赛最重要页面。

使用：

## React Flow

展示：

```
              Supervisor


                  |

        +---------+---------+

        |         |         |


     ArtAgent Animation Engine


        |         |         |


     PReCon     FAlign   GImport


                  |

                  v


                 QA

```

---

节点状态：

运行：

```
● Running
```

完成：

```
✓ Success
```

失败：

```
× Failed
```

---

节点点击：

打开详情。

例如：

点击 FAlign：

```
FAlign Engine


Input:

animation_raw.mp4


Process:

Frame Extraction

Anchor Detection

Motion Alignment


Output:

animation.asset


Score:

96%

```

---

# Page 3：CreativeAsset Inspector

对应你的核心协议。

CreativeAsset成为整个系统的数据中心。

结构：

```
Asset Inspector


Identity

------------------

ID

mage001


Type

Character


------------------


Pixel Data


Before


AI Image


After


Pixel Asset



------------------


Animation


Idle

Attack


Frames:

12


------------------


Engine


Unity Ready


Cocos Ready


```

---

# Page 4：Pixel Studio

新增页面。

目的：

展示 PReCon。

技术：

React Konva

功能：

```
Pixel Canvas


+----------------+

|                |

|  █ █ █         |

|    █           |

|  █ █ █         |

|                |

+----------------+



Palette


16 Colors


Grid


8x8

```

展示：

Before：

```
普通AI图片
```

After：

```
像素游戏资产
```

---

# Page 5：Animation Studio

展示 FAlign。

布局：

```
Animation Studio


Frame Timeline


|1|2|3|4|5|6|7|


       ↓


Motion Preview



       


Quality


Anchor:

98%


Jitter:

2%


Smooth:

96%


```

---

功能：

* 播放动画
* 查看关键帧
* 显示修复前后差异

---

# Page 6：Export Center

展示 GImport。

流程：

```
CreativeAsset


       |

       v


GImport


       |

+------+------+

|             |


Unity       Cocos


       |

       v


Game Project

```

输出：

```
FireMage_Unity.zip


Assets

├── Texture

├── Animation

├── Prefab

├── Config

└── Project

```

---

# 三、前端状态架构

使用 Zustand。

目录：

```
src/store/


agentStore.ts

assetStore.ts

workflowStore.ts

previewStore.ts

exportStore.ts

```

---

## agentStore

保存：

```typescript
{
agents:[
 {
 name:"PReCon",
 status:"running",
 progress:60
 }
]
}

```

---

## assetStore

保存：

```typescript
{
creativeAsset:{

id,

pixel,

animation,

engine

}

}

```

---

## workflowStore

保存：

```typescript
{
nodes:[],

edges:[],

currentNode:"FAlign"

}

```

---

# 四、实时通信架构

新版：

WebSocket + Event Bus。

结构：

```
Backend


Agent Runtime


      |

      v


Event Stream


      |

      v


WebSocket


      |

      v


Frontend Event Handler


      |

      v


Zustand


      |

      v


UI Update

```

---

事件协议：

## Agent开始

```json
{
"type":

"AGENT_START",

"agent":

"PReCon"

}

```

---

## 进度

```json
{
"type":

"PROGRESS",

"agent":

"FAlign",

"value":

80

}

```

---

## 完成

```json
{
"type":

"ASSET_UPDATE",

"id":

"mage001"

}

```

---

# 五、动画交互增强

加入：

## Framer Motion

用于：

Agent节点：

```
等待

↓

启动

↓

流动光效

↓

完成

```

例如：

```
PReCon

[========]

100%

✓

```

---

# 六、3D资产展示

使用：

React Three Fiber + Drei。

页面：

Asset Viewer。

支持：

```
Character Model


旋转

缩放

动画播放

灯光切换

```

组件：

```
Canvas

 ├── Camera

 ├── Lights

 ├── Model

 └── AnimationMixer

```

---

# 七、后端接口升级

## Task API

创建任务：

```
POST

/api/tasks

```

返回：

```json
{
taskId:

"001"
}

```

---

## Agent Stream

```
WS

/tasks/{id}/stream

```

---

## Asset

```
GET

/assets/{id}

```

---

## Export

```
POST

/export

```

---

# 八、完整项目目录

```
CreativeForge-Studio


frontend/

├── src

│

├── pages

│   ├── Workspace

│   ├── AgentDashboard

│   ├── AssetInspector

│   ├── PixelStudio

│   ├── AnimationStudio

│   └── ExportCenter


├── components

│

├── stores

│

├── websocket

│

├── three

│

├── flow

│

└── api



backend/

├── api

├── agent_runtime

├── websocket

├── asset_service

└── export_service


```


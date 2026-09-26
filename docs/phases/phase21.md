Phase 21：CreativeForge MVP Engineering Plan（工程落地版）
这一阶段开始从“完整架构设计”进入：
真正可以开发的第一版 CreativeForge MVP。
目标：
不是做一个完整商业SaaS，而是在有限时间内证明核心技术闭环：
一句话需求

↓

Agent自主规划

↓

角色资产生成

↓

Character DNA保存

↓

动画处理

↓

游戏资源导出

↓

Cocos运行


一、MVP核心目标重新定义
第一版只验证：
核心问题1：
AI生成角色是否可以长期保持一致？
对应：
Character DNA

核心问题2：
AI动画是否可以变成游戏动画？
对应：
MotionAlign

核心问题3：
AI资产是否可以进入游戏引擎？
对应：
GImport

所以MVP：
不要做：
● 自研大模型
● 完整市场平台
● 复杂社交系统
先证明：
AI → Game Ready Asset

二、MVP最终Demo
用户输入：
创建一个赛博朋克机械猫战士，拥有火焰剑攻击动画，并导入Cocos。
系统执行：
Planner Agent


↓

Generate Agent


↓

AssetStruct


↓

DNA Encoder


↓

MotionAlign


↓

Combat Generator


↓

Cocos Export


输出：
RobotCat/


├── robot_cat.png


├── DNA.json


├── attack.anim


├── fire_skill.json


├── collider.json


└── Cocos Project

打开Cocos：
出现：
RobotCat


Idle

Run

Attack



三、MVP技术架构

                  Frontend


             React / Next.js


                    |


                    ↓


              Backend API


              FastAPI


                    |


                    ↓


             Agent Runtime


             LangGraph


                    |


 ------------------------------------------------


 |            |            |            |


Asset       DNA        Motion       Export


Agent      Agent       Agent        Agent


 |            |            |            |


 ------------------------------------------------


                    |


             Storage Layer


 ------------------------------------------------


PostgreSQL


Vector DB


Object Storage



四、代码仓库结构
推荐：
Monorepo。
CreativeForge/


├── frontend/


│
├── app/


│
├── components/


│
└── pages/


│


├── backend/


│
├── api/


│
├── agent/


│
├── services/


│
├── models/


│
└── database/


│


├── engine/


│
├── asset_struct/


│
├── motion_align/


│
└── gimport/


│


├── ai/


│
├── dna/


│
├── quality/


│
└── embedding/


│


├── storage/


│
├── vector/


│
└── object/


│


└── docker/


五、后端服务拆分
1. Agent Service
负责：
任务规划。
技术：
推荐：
LangGraph。
原因：
适合：
● DAG
● 状态保存
● 多Agent
结构：
agent/


planner.py


executor.py


state.py


memory.py


核心：
class AgentState:


    task_id:str


    goal:str


    current_node:str


    asset_id:str


    status:str


六、Agent Workflow
MVP：
固定几个核心Agent。

Planner


 |

 |

GenerateAgent


 |

AssetStructAgent


 |

DNAAgent


 |

MotionAgent


 |

ExportAgent



后续再升级动态Planner。

七、Asset Service
负责：
CreativeAsset管理。
目录：
asset/


schema.py


processor.py


version.py


核心对象：
class CreativeAsset:


    id:str


    identity:dict


    visual:dict


    animation:dict


    engine:dict


    version:int


八、Character DNA模块
MVP不训练模型。
采用：
DINOv2


+

FAISS


流程：
Character Image


↓

DINOv2 Encoder


↓

Embedding


↓

FAISS


↓

Similarity Search


接口：
POST:
/api/dna/create
输入：
{
image:

"robot.png"

}

输出：
{
character_id:

"cat001",


embedding_id:

123

}


九、MotionAlign MVP
第一版不要生成动画。
重点：
把已有动画处理成游戏资产。
原因：
降低复杂度。

输入：
frame_001.png

frame_002.png

frame_003.png


处理：
Frame Detection


↓

Anchor Alignment


↓

Sprite Sheet


↓

Animation JSON



输出：
{
animation:

"attack",


fps:

12,


frames:

20

}


十、GImport MVP
先支持：
Cocos。
原因：
文件结构简单。

生成：
Cocos/


assets/


├── textures

├── spriteframes

├── animations

└── prefab


接口：
POST

/api/export/cocos


输入：
{
asset_id:

"cat001"

}

输出：
zip。

十一、数据库设计
PostgreSQL
保存业务数据。

asset表：
CREATE TABLE asset(

id UUID,

name TEXT,

type TEXT,

version INT,

status TEXT

);


task表：
CREATE TABLE task(

id UUID,

goal TEXT,

status TEXT,

current_agent TEXT

);


animation表：
CREATE TABLE animation(

id UUID,

asset_id UUID,

name TEXT,

metadata JSONB

);


十二、Vector数据库
MVP：
FAISS。
保存：
DNA。
结构：
{
id:

"cat001",


vector:

[0.1,0.5],


metadata:

{

style:

"cyberpunk"

}

}


十三、对象存储
保存：
图片和动画。
MVP：
MinIO。
结构：
bucket:


assets/


cat001/


v1/


image.png

animation/

export/


十四、Frontend设计
核心页面：
1. Creation Studio
Prompt输入


[ 创建机械猫战士 ]


参数:


Style

Engine


Generate


2. Agent Timeline
显示：
✓ Planning

✓ Generate

✓ DNA

⟳ MotionAlign

○ Export


3. Asset Viewer
显示：
RobotCat


Preview


DNA Similarity

Animation


Export


十五、MVP开发顺序
Week 1：基础框架
完成：
● Monorepo
● FastAPI
● React
● PostgreSQL
● MinIO

Week 2：Agent Runtime
完成：
● Planner
● Task State
● Agent Executor

Week 3：AssetStruct
完成：
● Asset Schema
● Layer管理
● Version系统

Week 4：DNA
完成：
● DINOv2接入
● Embedding生成
● FAISS检索

Week 5：MotionAlign
完成：
● Frame分析
● Anchor
● Sprite Sheet
● Animation JSON

Week 6：Cocos Export
完成：
● Atlas
● AnimationClip
● Prefab

Week 7：Frontend
完成：
● Prompt页面
● Agent状态
● Asset展示

Week 8：完整Demo
完成：
一句话：
创建角色

↓

自动生产

↓

Cocos运行


十六、MVP技术栈
Frontend
React

Next.js

TailwindCSS

Three.js(预览)

Backend
Python

FastAPI

LangGraph

Pydantic


AI
DINOv2

CLIP

LLM API

Stable Diffusion/Flux


Storage
PostgreSQL

FAISS

MinIO

Engine
Cocos Creator


Phase 20：CreativeForge Model Training & Deployment（模型训练与部署工程）
最终架构：
                    CreativeForge AI


                         |

              Foundation Intelligence Layer


 ------------------------------------------------------


 Character DNA      Asset Graph      Motion      Quality

 Encoder             Knowledge       Encoder     Model


 ------------------------------------------------------


                         |

                  Agent Runtime


                         |

 ------------------------------------------------------


 AssetStruct     MotionAlign     Combat     GImport


 ------------------------------------------------------


                         |

                    Game Engine


一、模型战略：哪些自研，哪些调用API
首先确定边界。
不建议自研：
1. 基础大语言模型
例如：
● GPT
● Claude
● Qwen
● Llama
原因：
训练成本巨大。
CreativeForge 的竞争点不是语言能力。
LLM负责：
理解需求

规划任务

调用工具
即可。

2. 通用图片生成模型
例如：
● Stable Diffusion
● Flux
● Midjourney
原因：
这是通用能力。
竞争激烈。
CreativeForge 不需要重新造一个。

二、真正需要自研的部分
重点：
1. Character DNA Encoder ⭐⭐⭐⭐⭐
最高优先级。
解决：
AI生成角色长期一致。

2. Asset Graph Knowledge System ⭐⭐⭐⭐⭐
解决：
AI理解游戏资产关系。

3. Motion Understanding Model ⭐⭐⭐⭐
解决：
AI理解动画。

4. Quality Evaluation Model ⭐⭐⭐⭐
解决：
自动判断生成结果是否可用。

5. Game Asset Adapter ⭐⭐⭐⭐⭐
解决：
AI结果进入游戏引擎。
这个属于工程壁垒。

二、数据集构建方案
目标：
建立：
Game Asset Intelligence Dataset。
不是图片集合。
而是：
角色

+

结构

+

动作

+

关系

+

引擎信息


三、Dataset结构设计
目录：
CreativeForge Dataset/


characters/


├── robot_cat/


│
├── images/


│   ├── idle.png

│   ├── attack.png

│   └── side.png


│
├── metadata.json


│
├── skeleton.json


│
├── animation/


│   ├── run.json

│   └── attack.json


│
└── engine/


    └── cocos.json


四、Character DNA Dataset
核心数据：
Identity Pair。
例如：
同一个角色：
RobotCat


image1:

idle


image2:

attack


image3:

side


image4:

different pose

标签：
{
character_id:

"robot_cat_001"

}


训练目标：
模型学习：
这些都是同一个角色。

五、正负样本设计
Contrastive Learning。
例如：
正样本：
RobotCat idle

RobotCat attack

label:
same=1

负样本：
RobotCat

vs

DragonKnight

label:
same=0

六、数据规模规划
MVP：
不需要百万。
第一阶段：
5000角色
每个：
10张图
约：
50000 images。

第二阶段：
50000角色
约：
50万图片。

第三阶段：
百万级资产库。

七、Character DNA模型选择
候选：

CLIP
结构：
Image

↓

Vision Encoder

↓

Embedding

优点：
成熟。
生态好。
缺点：
偏语义。
游戏细节不足。

DINOv2
更推荐。
原因：
更关注：
● 结构
● 形态
● 视觉一致性
适合：
角色身份。

SigLIP
优势：
图文对齐强。
适合：
Prompt理解。

八、推荐方案
CreativeForge：
采用：
DINOv2

+

CLIP

+

Projection Head

结构：
Character Image


      |

      ↓


DINOv2 Encoder


      |

      ↓


Character Feature


      |

      ↓


Projection Layer


      |

      ↓


DNA Vector


输出：
768维：
[
0.123,
0.442,
...
]

九、Vector Database设计
DNA需要检索。
例如：
用户：
找之前那个机械猫
查询：
图片：
↓
Embedding
↓
Vector Search。

架构：
                DNA Query


                    |

                    ↓


             Embedding Model


                    |

                    ↓


               Vector DB


                    |

                    ↓


              Similar Characters


十、Vector DB选择
MVP：
FAISS
原因：
简单。
适合：
本地。

产品：
Milvus。
结构：
Milvus


Collection:

character_dna


Fields:


id

embedding

metadata


数据：
{
id:

"cat001",


vector:

[...],


metadata:


{

style:"cyberpunk",

weapon:"sword"

}

}


十一、Asset Graph设计
数据库：
推荐：
Neo4j。

节点：
Character


Weapon


Animation


Skill


EngineAsset


关系：
Character

|

HAS

|

Weapon


Weapon

|

TRIGGERS

|

Skill


查询：
例如：
给机械猫增加攻击技能
Graph：
找到：
RobotCat

↓

Weapon Slot

↓

Attack Animation

↓

Skill Event


十二、Motion Model设计
目标：
理解动画。
输入：
帧序列：
frame1

frame2

frame3

输出：
{
action:

"attack",


speed:

"fast",


weapon:

"sword"

}


模型：
Frames


↓

Pose Estimator


↓

Temporal Encoder


↓

Motion Embedding


组件：
Pose Extractor
可以使用：
● OpenPose
● MediaPipe

Temporal Encoder
选择：
Transformer。

输出：
Motion Vector。

十三、Quality Model
这是非常重要的商业能力。
因为：
生成100个资产：
不可能人工检查。

输入：
Generated Asset

输出：
{
score:


{

identity:

0.92,


style:

0.88,


game_ready:

0.90

}

}


检测：
角色一致性
比较：
旧版本。

动画稳定性
检测：
关键点漂移。

游戏可用性
检测：
是否：
● 有透明背景
● 有碰撞
● 有完整动画

十四、LoRA/Fine-tune策略
不要训练大模型。
采用：
LoRA。

第一类：
角色风格LoRA
例如：
Cyberpunk Pixel Style

Fantasy RPG Style


第二类：
资产格式LoRA
例如：
生成：
游戏Sprite。

第三类：
角色一致性LoRA
让：
同一角色：
多动作保持。

十五、训练流程
完整Pipeline：
Dataset


↓

Preprocess


↓

Embedding Extraction


↓

Contrastive Training


↓

Evaluation


↓

Model Registry


↓

Deployment


十六、模型服务部署
架构：
Frontend


↓

API Gateway


↓

Model Service


↓

GPU Worker


↓

Model


服务：
DNA Service
接口：
POST /dna/embed
输入：
图片。
输出：
vector。

Quality Service
接口：
POST /quality/check
输入：
asset。
输出：
score。

Motion Service
接口：
POST /motion/analyze
输入：
animation。
输出：
semantic。

十七、GPU成本控制
不要所有任务GPU。
采用：
冷热分层。

GPU任务
例如：
● 图片生成
● 动画分析
● 模型推理

CPU任务
例如：
● Asset Graph查询
● Metadata处理
● Agent规划

架构：
Heavy Task

↓

GPU Queue


Light Task

↓

CPU Worker


十八、部署方案
MVP阶段
单机：
Docker


├── Agent

├── API

├── VectorDB

├── Model Service

└── Storage


产品阶段
Kubernetes：
Frontend


Backend


Agent Cluster


GPU Cluster


Storage


十九、私有化部署
面向游戏公司。
架构：
Customer Server


↓

CreativeForge Runtime


↓

Local Models


↓

Internal Asset Library


优势：
● 数据不上传
● IP安全
● 游戏公司接受度高

二十、Phase20最终技术架构
                    CreativeForge


                         |


              Intelligence Foundation


 ------------------------------------------------


 DINOv2+DNA


 Asset Graph


 Motion Encoder


 Quality Model


 LoRA Models


 ------------------------------------------------


                         |


                 Agent Runtime


                         |


 ------------------------------------------------


 AssetStruct


 MotionAlign


 Combat


 GImport


 ------------------------------------------------


                         |


                   Game Engine


二十一、最终形成的技术壁垒
和普通：
“调用GPT + 图片API”
区别：
普通：
Prompt

↓

Image API

↓

图片

CreativeForge：

二十二、推荐实际开发顺序
不要一开始训练模型。
实际路线：
MVP
先完成：
1. CreativeAsset协议
2. Agent Runtime
3. Asset Graph
4. DNA Embedding（基于DINOv2）
5. MotionAlign

V2
加入：
6. Quality Model
7. LoRA风格模型
8. 数据闭环

V3
加入：
9. 自研生成模型
10. 私有化部署
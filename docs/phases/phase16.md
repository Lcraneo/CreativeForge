Phase 16：CreativeForge Agent Orchestration Layer
这一阶段是整个项目从：
自主规划型 Game Asset Production Agen
前面 Phase 13-15.5 已经完成底层能力：
AssetStruct Engine
        ↓
Character DNA Engine
        ↓
MotionAlign Engine
        ↓
GImport Engine
但是这些还是：
用户手动调用工具
Phase 16 解决：
用户只描述目标

↓

Agent自主决定：

调用什么模块

先做什么

失败怎么办

如何迭代

↓

生成最终游戏资产

一、Phase 16 核心定位
传统 AI 游戏工具：
用户

↓

Prompt

↓

图片


CreativeForge：
用户目标

↓

Planner Agent

↓

任务拆解

↓

多个专业Agent协作

↓

验证

↓

自动修复

↓

输出游戏资产


例如：
用户输入：
创建一个赛博朋克机械猫战士，装备火焰剑，有攻击动画，导入Cocos。
Agent理解：
目标：
{
type:

"game_character_creation",


engine:

"cocos",


requirements:


[

"character",

"weapon",

"animation",

"combat"

]

}


二、整体 Agent 架构
                    User


                     |

                     ↓


              Intent Analyzer


                     |

                     ↓


              Planner Agent


                     |

                     |

     ----------------------------------


     |        |        |       |      |


Generate  Asset    DNA   Motion Combat Export

Agent     Agent    Agent Agent  Agent  Agent


     |        |        |       |      |


     ----------------------------------


                     |

                     ↓


              Quality Agent


                     |

                     ↓


             Final Game Asset


三、为什么采用 Multi-Agent
因为每个模块专业能力不同。
例如：
Generate Agent：
负责：
图片生成
不应该知道：
碰撞盒

Combat Agent：
负责：
Hitbox

Skill Event

Damage

不应该负责：
角色生成

所以：
采用：
领域Agent。

四、核心 Agent 定义
1. Planner Agent（总调度）
最高级。
职责：
● 理解用户目标
● 生成任务图
● 决定执行顺序
● 调度工具

输入：
创建机械猫战士

输出：
{
plan:


[


{

agent:

"GenerateAgent",

task:

"create_character"

},


{

agent:

"DNAAgent",

task:

"create_identity"

},


{

agent:

"MotionAgent",

task:

"create_animation"

}


]

}


五、Planner Agent 不固定流程
重点：
不是：
永远:

Generate

↓

DNA

↓

Motion


而是：
动态规划。
例如：
用户：
修改已有机械猫，让它换武器。
Planner：
发现：
已有DNA。
所以：
跳过Generate


Character DNA

↓

Motion

↓

Export


流程：
User Goal


↓

Planner


↓

Asset Memory Search


↓

决定路径


六、Generate Agent
负责：
初始资产创建。
工具：
Image Generation API

+

Style Control

+

Reference Image


输入：
{
style:

"cyberpunk",


character:

"robot cat"

}


输出：
{
asset_id:

001,


image:

cat.png

}


七、AssetStruct Agent
调用：
Phase 13。
职责：
图片：
↓
游戏资产。

执行：
Image


↓

Layer Separation


↓

Mask Generation


↓

Asset Graph


输出：
{
layers:

[

body,

armor,

weapon

]

}


八、DNA Agent
调用：
Phase 14。
职责：
建立角色身份。

输入：
Asset。
执行：
Encoder


↓

Embedding


↓

Vector DB


↓

DNA Record


输出：
{
character_id:

cat001

}


九、Motion Agent
调用：
Phase 15。
职责：
动画生产。

任务：
create attack animation

执行：
Animation Generation


↓

Pose Alignment


↓

Sprite Extraction


↓

Timeline


输出：
{

animation:

attack.anim

}


十、Combat Agent
负责：
战斗逻辑。
调用：
Phase 15.5。

任务：
add fire sword skill

执行：
Weapon Mask


↓

Hitbox


↓

Event Binding


↓

Damage


输出：
{

skill:

fire_slash,


damage:

100

}


十一、Export Agent
调用：
Phase 15.4。
职责：
引擎适配。

输入：
完整CreativeAsset。
输出：
Cocos Project


RobotCat.prefab



十二、Memory Layer（非常重要）
Agent必须记忆：
不是聊天记录。
而是：
资产生产记忆。

新增：
Agent Memory


├── Character Memory

├── Asset Memory

├── Version Memory

└── User Preference


例如：
用户：
第二次：
修改机械猫颜色
Agent知道：
cat001

当前版本:

v3


已有:

fire sword

attack animation


不用重新生成。

十三、Task Graph
不要使用简单链式。
使用 DAG。
例如：
创建角色：
              Generate


                 |

                 ↓


            AssetStruct


             /      \


          DNA      Motion


             \      /


              Combat


                 |


              Export


原因：
DNA和Motion可以并行。

十四、Agent Tool Registry
所有能力注册。
结构：
class ToolRegistry:


    tools={

    "generate":
    GenerateTool(),


    "asset_struct":
    AssetStructTool(),


    "dna":
    DNATool(),


    "motion":
    MotionTool(),


    "combat":
    CombatTool(),


    "export":
    ExportTool()

    }


Planner：
通过工具描述选择。

十五、Tool Schema
类似 MCP。
例如：
Motion Tool：
{
name:

"create_animation",


description:

"Generate game animation",


input:


{

character_id,

action

}

}


Planner：
读取：
available tools

决定：
调用。

十六、失败恢复机制
这是 Agent 和普通工作流区别。
例如：
动画失败：
原因：
Pose confidence < threshold


Quality Agent：
返回：
{
error:

"pose unstable"

}


Planner：
重新规划：
重新生成动作

降低复杂度

重新Alignment


十七、Quality Agent
最终检查。
检查：
Asset Quality
Layer完整

Mask正常


DNA Quality
Identity similarity >0.85


Motion Quality
Anchor drift < threshold


Runtime Quality
Cocos load success


十八、完整一次任务执行
用户：
创建赛博朋克机械猫战士，火焰剑攻击，导入Cocos。

Step 1
Planner：
生成任务图。

Step 2
Generate Agent：
生成角色。

Step 3
AssetStruct：
拆：
body

armor

weapon


Step 4
DNA：
建立：
cat001


Step 5
Motion：
生成：
attack animation


Step 6
Combat：
生成：
fire slash skill


Step 7
Export：
输出：
Cocos Project


Step 8
Quality：
测试。

十九、最终技术架构
                 CreativeForge Agent


                         |


                    Planner Agent


                         |


 ------------------------------------------------


 |          |          |          |          |


Generate  Struct     DNA      Motion    Combat Export


 Agent    Agent     Agent     Agent     Agent Agent


 ------------------------------------------------


                         |


                  Quality Agent


                         |


                  Game Asset Output


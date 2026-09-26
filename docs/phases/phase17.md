继续进入 Phase 17：CreativeForge Agent Runtime（生产级 Agent 系统）
Phase 17 总目标
用户输入：
创建一个赛博朋克机械猫战士，拥有火焰剑技能，并生成 Cocos 可运行角色。
系统：
不是：
Prompt
↓
API
↓
图片
而是：
User Goal

↓

Agent Runtime

↓

任务理解

↓

计划生成

↓

工具选择

↓

执行

↓

验证

↓

失败恢复

↓

版本保存

↓

最终资产


一、Agent Runtime 总架构
                    User


                     |

                     ↓


              Task Gateway


                     |

                     ↓


             Planner Runtime


                     |

        ---------------------------


        |                         |


 Task Graph Engine        Memory System


        |                         |


        ---------------------------


                     |


              Agent Executor


                     |


 ------------------------------------------------


 |          |          |          |             |


Asset    DNA      Motion    Combat       Export


Agent   Agent     Agent     Agent        Agent


 ------------------------------------------------


                     |


              Quality Agent


                     |

                     ↓


              Asset Version


二、核心模块1：Task Gateway
负责：
接收用户目标。
输入：
自然语言：
创建机械猫战士

转换：
Task。

数据结构：
{
task_id:

"task_001",


goal:

"create cyber cat warrior",


constraints:

{

engine:

"cocos",

style:

"cyberpunk"

}

}


三、Planner Runtime
这是核心。
之前 Phase16：
Planner负责：
拆任务。
Phase17：
Planner升级：
成为动态决策系统。

Planner职责
1. Goal Understanding
理解：
用户想要什么。

2. Capability Matching
查询：
当前有哪些Agent能力。
例如：
已有：
GenerateAgent

DNAAgent

MotionAgent

CombatAgent

ExportAgent


3. Plan Generation
生成：
DAG。

四、DAG Task Graph Engine
为什么不用普通流程？
因为：
真实生产不是线性。
例如：
修改角色颜色：
不需要：
重新生成动画。

任务图：
                 Character


                    |

                    ↓


              AssetStruct


              /        \


          DNA          Motion


              \        /


              Combat


                  |

                  ↓


                Export


数据模型：
class TaskNode:


    id:str


    agent:str


    input:list


    output:list


    status:str




Task Graph：
class TaskGraph:


    nodes=[]


    edges=[]



    def next_tasks():

        pass


五、Agent Executor
负责真正执行。
流程：
Planner

↓

TaskGraph

↓

Executor

↓

Agent

↓

Tool

↓

Result


例如：
任务：
{
agent:

"MotionAgent",

action:

"create_attack_animation"

}

Executor：
找到：
MotionAgent

执行。

六、Agent状态管理
生产任务可能：
几十分钟。
不能：
一次完成。
所以需要状态。

Task State：
id="agent_state"
CREATED

↓

PLANNING

↓

RUNNING

↓

WAITING

↓

FAILED

↓

RETRY

↓

COMPLETED


数据库：
agent_task


id

user_id

goal

status

created_at

updated_at


七、断点续跑系统
这是生产级Agent必须有的。
例如：
执行：
Generate

完成


AssetStruct

完成


Motion

失败


重新启动：
不能：
全部重新生成。
读取：
{
completed:


[

generate,

asset_struct

],


failed:

motion

}

继续：
Motion

↓

Combat

↓

Export


八、Agent Memory System
分三层。

1. Asset Memory
保存：
生成过的资产。
例如：
{
character_id:

cat001,


version:

3,


assets:

[

idle,

run,

attack

]

}


2. User Preference Memory
用户习惯。
例如：
喜欢：
dark cyberpunk

low poly


3. Process Memory
生产经验。
例如：
某模型：
生成机械角色稳定。

九、Version Control
CreativeAsset 已经有：
Version。

这里扩展：
Asset Git。

版本：
cat001


v1

↓

基础角色


v2

↓

增加护甲


v3

↓

增加火焰剑


v4

↓

优化攻击动画


数据：
{
asset_id:

cat001,


version:

4,


parent:

3,


changes:

[

"add_weapon"

]

}


十、Human-in-the-loop
不是所有步骤自动。
游戏生产需要审核。
加入：
Review Agent。

例如：
生成角色后：
系统：
是否接受该角色设计？

A 修改

B 继续


审核点：
1. Concept Review
角色设计。

2. Animation Review
动作质量。

3. Runtime Review
游戏运行。

十一、Retry & Self Healing
Agent区别普通Workflow：
失败后自己调整。

例如：
Motion失败：
原因：
pose confidence 0.55

Quality Agent：
返回：
{
issue:

"unstable_pose",

suggestion:

"regenerate_animation"

}


Planner：
修改计划：
重新生成动作

降低动作复杂度

重新Alignment


十二、Token优化设计
Agent容易：
上下文爆炸。
解决：

1. Context Compression
保存摘要：
不是全部历史。

2. Tool Result Cache
例如：
DNA查询：
不用重复。

3. Structured Output
Agent之间：
不用自然语言。
使用：
JSON。

十三、MCP化工具层
Phase17加入：
Tool Registry。
类似 MCP。
结构：
{
tools:


[


{

name:

"motion_align",


description:

"align animation frames"


},


{

name:

"export_cocos",


description:

"export cocos asset"

}

]

}


Planner：
动态选择工具。

十四、完整执行案例
用户：
创建一个赛博朋克机械猫战士，火焰剑攻击，导入Cocos。

Step 1
Task Gateway：
生成任务。

Step 2
Planner：
创建DAG。
Generate

↓

AssetStruct

↓

DNA

↓

Motion

↓

Combat

↓

Export


Step 3
Executor执行。

Step 4
Quality检查。
发现：
动画漂移。

Step 5
Self Healing。
重新调用：
MotionAlign。

Step 6
输出：
RobotCat.prefab

attack.anim

fire_skill.json


十五、Phase17完成后架构
最终：
                 CreativeForge


                      |


              Agent Runtime


                      |


        ----------------------------


        Planner


        Task Graph


        Memory


        Executor


        Quality


        Version


        ----------------------------


                      |


 ------------------------------------------------


AssetStruct   DNA   Motion   Combat   Export


 ------------------------------------------------


                      |


                 Game Engine



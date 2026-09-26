Phase 15 的实现优先级为：
优先级：
2. Pose / Anchor Alignment       
1. Sprite Frame Extraction       
3. Animation Timeline             
5. Cocos Animation Export         
4. Hitbox / Hurtbox Generation    


Phase 15：MotionAlign Engine（重新规划版）
目标：
把：
AI生成角色序列
转换为：
游戏可用 Animation Asset

总架构
                Character DNA


                      |

                      ↓


              MotionAlign Engine


                      |

 ------------------------------------------------

 |                    |                         |

Pose             Frame                 Timeline

Align            Extraction             Builder


 |                    |                         |


 ------------------------------------------------


                      |

                      ↓


             Game Animation Package


                      |

                      ↓


                Cocos / Unity


Phase 15.1 核心模块重新排序
目录：
motion_align/


├── alignment/                 ★核心

│
├── pose_detector.py

├── anchor_solver.py

├── transform.py



├── extraction/

│
├── frame_detector.py

├── sprite_cropper.py



├── timeline/

│
├── animation_builder.py



├── exporter/

│
├── cocos_exporter.py



├── collision/

│
├── hitbox_generator.py


第一核心：Pose / Anchor Alignment
AI生成动画最大的问题：
不是没有动作。
而是：
每一帧：
Frame 1:

脚在这里


Frame 2:

脚漂移


Frame 3:

身体缩小

进入游戏：
角色会：
● 滑步
● 抖动
● 身体跳动
所以需要：
统一坐标系统。

一、Anchor设计
游戏角色至少需要：
Root Anchor
角色中心。
        ▲

       head


        |

        |

      body


        |

        |

       feet

        ▼

       root


Body Anchor
身体中心。

Action Anchor
攻击动作：
剑的位置。

例如：
攻击：
Frame 1


     sword

       *

        \

         \

          body


           |

          root



Frame 2


        *

       /

      /

   body


    |

   root

剑的位置变化。
但是：
body/root不能漂移。

二、Pose Detection
输入：
attack_001.png

attack_002.png

attack_003.png

输出：
关键点：
{
"head":[120,40],

"shoulder":[130,90],

"hip":[130,180],

"left_foot":[110,250],

"right_foot":[150,250]
}

技术：
第一版：
MediaPipe Pose
后期：
训练游戏角色专用Pose模型。

三、Anchor Solver
核心算法。
目标：
寻找：
所有帧共同参考点
例如：
10帧：
得到：
root:

[
(100,200),
(102,201),
(98,199)
]

计算：
平均：
root=(100,200)


然后：
所有帧重新变换。
公式：
new_position

=

old_position

-

offset


效果：
修正：
Frame1

Frame2

Frame3

全部：
基于同一个root。

四、Transform Normalization
解决：
尺寸变化。
AI动画：
可能：
第一帧：
height=300
第二帧：
height=330
归一化：
scale =
target_height / current_height


最终：
所有帧：
512x512

root一致

scale一致


五、Sprite Frame Extraction
第二优先。
作用：
动画序列：
↓
Sprite Sheet。

输入：
attack.gif

或者：
frame_001.png

frame_002.png


输出：
sprite/


attack/


001.png

002.png

003.png


Frame Detector
自动检测：
有效区域。
例如：
图片：
512x512
实际角色：
300x400
裁剪：
bbox:

[100,50,400,450]


生成：
frame metadata

{
frame:1,

bbox:

[
100,
50,
400,
450
]

}

六、Sprite Sheet生成
输出：
attack.png
● 
attack.json

例如：
{
frames:[

{

name:"attack_001",

x:0,

y:0,

w:128,

h:128

}

]

}


七、Animation Timeline
第三优先。
把：
frame图片
变成：
游戏动画

结构：
{
animation:

"attack",


fps:

12,


frames:

[

"001",

"002",

"003"

]

}


生成：
Timeline：
0s

|

frame1


0.08s

|

frame2


0.16s

|

frame3


八、事件系统
游戏需要：
攻击事件。
例如：
第5帧：
触发：
Hit Active


Timeline：
增加：
{
frame:5,

event:

"attack_start"

}


以后接：
Hitbox。

九、Cocos Export
第四优先。
输出：
Cocos资源：
assets/


character/


├── sprite/

├── atlas/

├── animation/

└── prefab/


生成：
AnimationClip：
例如：
attack.anim

内容：
fps:

12


duration:

0.8


frames:

10


Prefab：
Character


├── Sprite

├── Animation

├── Collider


十、Hitbox/Hurtbox
第五。
因为：
依赖：
前面的：
● Pose
● Timeline

Hitbox生成
攻击帧：
检测：
武器区域。
例如：
sword.png


mask


↓

polygon


↓

hitbox


输出：
{
frame:5,

hitbox:

[
[120,80],

[200,100],

[220,150]

]

}


十一、完整MotionAlign Pipeline
最终：
AI Animation


       |

       ↓


Pose Detection


       |

       ↓


Anchor Alignment       ★核心


       |

       ↓


Frame Extraction


       |

       ↓


Sprite Sheet


       |

       ↓


Animation Timeline


       |

       ↓


Hitbox Generation


       |

       ↓


Cocos Export


       |

       ↓


Playable Character


十二、MVP实现顺序
按照你的优先级：
V1（必须）
完成：
Pose Detection

+

Anchor Alignment

+

Frame Normalize

价值最高。

V2
加入：
Frame Extraction

Sprite Sheet


V3
加入：
Timeline

Animation Clip


V4
加入：
Cocos Export


V5
加入：
Hitbox/Hurtbox



 Phase 15.1：Anchor Alignment 核心算法与工程实现设计
优先级：
2. Pose / Anchor Alignment ★★★★★

1. Sprite Frame Extraction ★★★★☆

3. Animation Timeline ★★★☆☆

5. Cocos Export ★★★☆☆

4. Hitbox/Hurtbox ★★☆☆☆
并且 MotionAlign 最终仍然遵循 CreativeAsset Contract：
Animation 内包含：
Animation

├── Frames
├── Anchor
├── Motion
└── Action

同时所有模块通过 AssetProcessor 统一处理：
Input CreativeAsset

↓

Processor

↓

Output CreativeAsset Version


Phase 15.1 总架构
AI Animation Frames


frame_001.png
frame_002.png
frame_003.png
...


        |

        ↓


Pose Detector


        |

        ↓


Keypoint Extraction


        |

        ↓


Anchor Solver


        |

        ↓


Transform Normalize


        |

        ↓


Aligned Frames


        |

        ↓


CreativeAsset.Animation



一、核心问题定义
AI生成动画存在五类漂移：

1. Root Drift（根节点漂移）
例如：
第一帧：
角色脚底

      |
      |
     root

x=100
y=300

第二帧：
角色脚底

      |
      |
     root


x=110
y=310

游戏表现：
角色瞬移。

2. Scale Drift（比例漂移）
第一帧：
height=300px
第二帧：
height=330px
表现：
角色忽大忽小。

3. Rotation Drift（旋转漂移）
例如攻击动作：
Frame1:
身体垂直
Frame2:
身体倾斜
Frame3:
恢复
导致：
抖动。

4. Limb Drift（四肢漂移）
手：
Frame1:
x=120
Frame2:
x=150
但实际动作不应该变化。

5. Camera Drift
AI生成：
每帧视角轻微变化。

二、Pose Keypoint 数据结构
首先定义统一关键点。
文件：
motion_align/models/pose.py

PosePoint
from dataclasses import dataclass


@dataclass
class PosePoint:

    name:str

    x:float

    y:float

    confidence:float


例如：
{
"head":
{
"x":120,
"y":40,
"confidence":0.98
},

"hip":
{
"x":130,
"y":180,
"confidence":0.95
},

"left_foot":
{
"x":110,
"y":300,
"confidence":0.97
}

}


三、角色关键 Anchor 定义
游戏角色固定：
Anchor


root

↓

hip

↓

feet


定义：
ANCHOR_POINTS = [

"hip",

"left_foot",

"right_foot",

"head"

]


为什么不用单点？
因为：
单 root：
容易错误。
多个点：
可以求：
● 平移
● 缩放
● 旋转

四、Root Anchor 求解算法
目标：
找到所有帧共同坐标。
假设：
10帧：
Frame1:

root=(100,300)


Frame2:

root=(103,302)


Frame3:

root=(98,301)


计算平均：
公式：
$R=
\frac{1}{N}
\sum_{i=1}^{N}R_i$
代码：
def calculate_root(points):


    x=sum(
        p.x for p in points
    ) / len(points)


    y=sum(
        p.y for p in points
    ) / len(points)


    return (
        x,
        y
    )


得到：
root=(100.3,301)


五、Frame Translation Alignment
计算偏移。
例如：
目标：
root=(100,300)

当前：
root=(108,310)

偏移：
dx=-8

dy=-10


公式：
$P'=P-(R_i-R)$
代码：
def translate_frame(
    points,
    target_root
):

    current_root = calculate_root(points)


    dx = target_root[0]-current_root[0]

    dy = target_root[1]-current_root[1]


    for p in points:

        p.x += dx
        p.y += dy


    return points


六、Scale Normalization
解决：
大小变化。
计算：
角色高度：
head.y - feet.y

例如：
Frame1:
height=300
Frame2:
height=340
目标：
统一：
height=300


公式：
$scale=
\frac{targetHeight}{currentHeight}$
代码：
def normalize_scale(
    points,
    target_height
):

    current_height = abs(
        points["head"].y -
        points["feet"].y
    )


    scale = (
        target_height /
        current_height
    )


    for p in points.values():

        p.x *= scale
        p.y *= scale


    return points


七、Rotation Alignment
解决：
身体倾斜。
参考：
hip → head
计算角度：
$\theta=
atan2(y2-y1,x2-x1)$
目标：
90°

代码：
import math


def calculate_angle(
    hip,
    head
):

    return math.atan2(
        head.y-hip.y,
        head.x-hip.x
    )



旋转矩阵：
$\begin{bmatrix}
cosθ&-sinθ\\
sinθ&cosθ
\end{bmatrix}$

八、完整 Anchor Solver
结构：
AnchorSolver

|
├── solve_root()

├── solve_scale()

├── solve_rotation()

└── align()


代码：
class AnchorSolver:


    def align(
        self,
        frames
    ):


        target_root = (
            256,
            400
        )


        for frame in frames:


            frame.pose = (
                self.align_root(
                    frame.pose,
                    target_root
                )
            )


            frame.pose = (
                self.normalize(
                    frame.pose
                )
            )


        return frames


九、和 Character DNA 联动
这是关键。
MotionAlign 不能只看动作。
必须知道：
这个角色是谁。
流程：
Animation Frame


↓

Character DNA


↓

Expected Skeleton


↓

Anchor Alignment


例如：
DNA保存：
{

"body_ratio":

{

"head":

0.18,


"body":

0.55

}

}


Alignment 时：
目标不是：
所有角色一样。
而是：
保持：
这个角色自己的比例。

十、CreativeAsset 输出
经过 MotionAlign：
更新：
{
"animation":

{

"frames":

[

{

"id":0,

"uri":"frame0.png",

"duration":83

}

],


"anchor":

{

"root":

{

"x":256,

"y":400

}

},


"motion":

{

"root_dx":0,

"root_dy":0

}

}

}


对应 Contract：
Animation:
● frames
● anchor
● motion
● action


十一、工程目录
最终：
motion_align/


├── models/

│
├── pose.py

├── frame.py


├── detector/

│
├── pose_detector.py


├── alignment/

│
├── anchor_solver.py

├── transform.py


├── pipeline/

│
└── processor.py


└── tests/

    ├── test_anchor.py

    └── test_scale.py


十二、MVP实现范围
第一版：
必须完成：
✅ Pose Detection接口
✅ Root Anchor计算
✅ 多帧平移修正
✅ 比例归一化
✅ CreativeAsset Animation写入
暂时不做：
❌ AI骨骼重定向
❌ 复杂IK
❌ 自动动作生成
❌ 物理动画

十三、验证Demo
输入：
attack_animation/

001.png

002.png

003.png

004.png

处理前：
角色上下跳动

处理后：
root固定

高度一致

动作连续



进入 Phase 15.2：Sprite Frame Extraction + Sprite Sheet Generator
Phase 15.2 总目标
输入：
attack/

frame_001.png

frame_002.png

frame_003.png

frame_004.png

输出：
character/


├── textures/

│
├── attack_atlas.png


├── atlas/

│
├── attack.plist


├── animation/

│
└── attack.anim


└── metadata.json

最终：
Cocos 可以直接：
拖入项目

↓

绑定 Animation Component

↓

播放攻击动画


一、整体架构
Aligned Frames


       |

       ▼


Frame Analyzer


       |

       ▼


Sprite Cropper


       |

       ▼


Padding Normalizer


       |

       ▼


Atlas Generator


       |

       ▼


Animation Builder


       |

       ▼


Cocos Export


二、为什么不能直接拼 Sprite Sheet？
流程必须：
裁剪

↓

重新定位

↓

统一Frame尺寸

↓

Atlas


三、Frame Analyzer
作用：
分析每一帧：
● 有效像素区域
● bbox
● anchor位置
输入：
frame_001.png
输出：
{
width:512,

height:512,


bbox:

[
120,
60,
390,
450
],


anchor:

{
x:256,
y:430
}

}


四、Sprite Cropper
核心逻辑
原图：
512x512


+----------------+

|                |

|     CAT        |

|                |

+----------------+

检测：
bbox:

100,50

400,450

裁剪：
+---------+

| CAT     |

|         |

+---------+


代码结构：
class SpriteCropper:


    def crop(
        self,
        image,
        bbox
    ):

        return image.crop(
            bbox
        )


五、Padding Normalizer
这是关键。
游戏动画要求：
所有帧：
相同大小。
例如：
统一：
128x128


但是角色不能居中。
必须保持：
Anchor。
例如：
攻击：
Frame1：
   sword


    cat


     |

    root

Frame2：
        sword


    cat


     |

    root

如果强行居中：
动作会错。

所以：
采用：
Anchor Based Padding。

公式：
目标：
root固定
不是：
图片中心固定

数据：
{
frame_size:

[128,128],


anchor:

[64,110]

}


六、Sprite Frame Metadata
生成：
attack.json

内容：
{

"frames":[


{

"name":
"attack_001",


"x":
0,


"y":
0,


"width":
128,


"height":
128,


"anchor":

{

"x":
64,

"y":
110

}


}

]


}


这个文件后面：
用于：
Cocos Animation。

七、Atlas Generator
作用：
多个 PNG：
合成：
一张大图。
例如：
原：
frame1.png

frame2.png

frame3.png

frame4.png

生成：
attack_atlas.png


布局：

+-------+-------+

| f1    | f2    |

+-------+-------+

| f3    | f4    |

+-------+-------+


算法：
采用：
MaxRects Bin Packing。
原因：
游戏行业常用。

流程：
输入:

N张sprite


↓

计算面积


↓

排序


↓

矩形填充


↓

输出Atlas



八、Atlas 数据结构
{

"texture":

"attack_atlas.png",


"sprites":[


{

"name":

"attack_001",


"x":

0,


"y":

0,


"w":

128,


"h":

128

}


]

}


九、Animation Builder
现在：
图片资源有了。
需要：
生成动画。

输入：
frames:

001

002

003

配置：
{
fps:

12

}


输出：
Animation Timeline：
{

"name":

"attack",


"fps":

12,


"duration":

0.33,


"frames":

[

"attack_001",

"attack_002",

"attack_003"

]

}


十、Animation Event 插入
结合之前设计：
Phase 15.1：
Anchor
这里加入：
事件。
例如：
攻击动画：
Frame:

1
准备


2
挥剑


3
命中


4
恢复


生成：
{

events:[


{

frame:

3,


type:

"hit"


}


]

}


后续 Phase 15.5：
Hitbox 自动生成会读取这个。

十一、Cocos Export
Cocos需要：
三类资源：

1. Texture
.png


2. SpriteFrame
.plist


3. Animation
.anim


目录：
assets/


character/


├── attack_atlas.png


├── attack.plist


├── attack.anim



十二、Cocos Adapter设计
不要直接生成 Cocos 文件。
增加：
Exporter。
结构：
Exporter Interface


        |


        +---- CocosExporter


        +---- UnityExporter



代码：
class AnimationExporter:


    async def export(
        self,
        asset
    ):
        pass


Cocos：
class CocosExporter(
    AnimationExporter
):


    async def export(
        self,
        animation
    ):

        return {

        "engine":

        "cocos",


        "files":

        [

        "atlas.png",

        "anim"

        ]

        }


十三、和 CreativeAsset 联动
最终写入：
{
animation:

{


frames:

[

{

uri:

"attack_001.png"

}


],



atlas:

"attack_atlas.png",



timeline:

{


fps:

12

}


}

}

对应：
CreativeAsset：
Animation

├── Frames

├── Anchor

├── Motion

└── Action



十四、Phase 15.2 核心代码结构
motion_align/


sprite/


├── analyzer.py


├── cropper.py


├── normalizer.py


├── atlas.py


├── animation.py


└── cocos_export.py


十五、MVP开发顺序
V1
完成：
✅ Frame bbox检测
✅ 自动裁剪
✅ Anchor保持
✅ PNG序列输出

V2
完成：
✅ Atlas生成
✅ Metadata生成

V3
完成：
✅ Animation Clip生成
✅ Cocos导入

V4
完成：
✅ 自动事件标记
✅ Hitbox接口口
Windup

↓

生成攻击动作


↓

MotionAlign

↓

Anchor校正


↓

Sprite Extract


↓

Atlas


↓

Animation


↓

Cocos角色Prefab

最终：
打开 Cocos：
看到：
MechanicalCat

Idle

Run

Attack

直接可播放。
Phase 15.3：Animation Timeline + Action Event System
进入这一阶段后，MotionAlign 不再只是：
图片序列处理器
而升级为：
AI生成角色行为系统

一、目标重新定义
普通 AI 动画：
Prompt

↓

生成攻击动画

↓

GIF

结束。
CreativeForge：
Prompt

↓

生成角色动作

↓

理解动作语义

↓

生成Animation State

↓

绑定游戏事件

↓

可直接进入游戏逻辑


二、整体架构
                 Character DNA


                      |

                      ↓


             Animation Timeline


                      |

        --------------------------------

        |              |              |

   State Machine   Event System   Skill System


        |              |              |


        --------------------------------


                      |

                      ↓


              Engine Runtime



三、Animation Timeline 数据模型
游戏需要：
什么时候发生什么事情。


所以设计：
Animation Timeline。

AnimationClip
{
"name":

"attack",


"duration":

0.8,


"fps":

12,


"frames":

[],


"events":[]

}


完整：
{
"name":"attack",


"fps":12,


"duration":0.8,


"frames":[


{
"id":1,

"time":0.08,

"sprite":"attack_001"

},


{
"id":2,

"time":0.16,

"sprite":"attack_002"

}


],


"events":[


{

"time":0.32,

"type":"damage"


}

]

}


四、Animation State Machine
角色不是播放单个动画。
而是：
状态切换。
例如：
          Idle


           |

           |

        Move


           |

           |

        Attack


           |

           |

        Idle


五、State定义
增加：
animation/state/
结构：
class AnimationState:


    name:str


    clip:str


    loop:bool


    transitions:list


例如：
{
"name":

"idle",


"clip":

"idle.anim",


"loop":

true

}


六、状态转换规则
例如：
Idle：
收到：
move=true
进入：
Run。

数据：
{
from:

"idle",


condition:

"move",


to:

"run"

}


Attack：
{
from:

"idle",


condition:

"attack",


to:

"attack"

}


七、Agent控制动画
这是 CreativeForge 的关键。
用户：
让机械猫战士释放火焰斩
Agent解析：
不是：
生成图片。
而是：
修改角色行为。

Agent Plan：
{
action:

"skill_attack",


character:

"cat001",


skill:

"fire_slash"

}


调用：
Animation Tool。
Agent

↓

Character DNA

↓

Animation Library

↓

Fire Slash Clip

↓

Runtime Event


八、Frame Event System
游戏动画最重要部分。
例如：
攻击动作：
10帧。
不是：
每帧都造成伤害。
只有：
第6帧。

Timeline：
Frame:


1

准备


2

抬手


3

蓄力


4

挥动


5

剑出现


6

命中 ★


7

恢复


事件：
{
frame:

6,


event:

"hit_start"

}


九、Event类型设计
基础：
AnimationEvent


├── Sound

├── VFX

├── Damage

├── Spawn

├── Camera

└── Script


Sound Event
例如：
挥剑声音。
{
frame:4,

type:

"sound",


value:

"sword.wav"

}


VFX Event
火焰效果。
{
frame:5,

type:

"effect",


value:

"fire"

}


Damage Event
攻击判定。
{
frame:6,

type:

"damage",


value:

100

}


十、Skill System
动画和技能绑定。
例如：
角色：
机械猫战士。
技能：
火焰斩。
结构：
{
skill:

"fire_slash",


animation:

"attack_fire",


events:


[


"spawn_fire",

"damage"

]

}


十一、Action Semantic Analyzer
这里连接 AI。
输入：
用户：
让角色跳起来然后挥剑

LLM分析：
{
actions:[


"jump",

"attack"


]

}


转换：
jump

↓

jump.anim


attack

↓

attack.anim


十二、Animation Graph
最终：
不是列表。
是图。
例如：
              Idle

                |

                |

              Run

                |

                |

            Attack


             /   \


        Skill1   Skill2



数据：
{
nodes:[

"idle",

"run",

"attack"

],


edges:[


{
from:"idle",

to:"run"

}

]

}


十三、与 Character DNA 联动
重点。
同一个角色：
机械猫。
拥有：
DNA

+

Animation


DNA保存：
{
body:

"small_robot",


combat_style:

"fast_attack"

}


Agent生成攻击：
不会随机：
而是：
根据DNA选择。
例如：
机械猫：
速度快。
生成：
快速连续攻击
而不是：
巨大慢动作。

十四、数据库设计
新增：
animation_clip
id

character_id

name

duration

fps

metadata


animation_event
id

animation_id

frame

event_type

payload


animation_state
id

character_id

state

clip_id

transition


十五、代码结构
新增：
motion_align/


timeline/


├── clip.py


├── event.py


├── state_machine.py


├── graph.py



runtime/


├── action_parser.py


├── animation_controller.py


十六、Animation Controller
核心运行逻辑：
class AnimationController:


    def update(
        self,
        input
    ):


        state = (
            self.state_machine
            .next(input)
        )


        self.play(
            state
        )


例如：
输入：
{
"attack":true
}

返回：
attack.anim

十七、最终 Demo
用户：
输入：
创建一个机械猫战士，让它使用火焰剑攻击
Agent：

Step 1：
找到：
Character DNA
cat001

Step 2：
生成：
Action Plan
{
action:

attack,


weapon:

fire_sword

}


Step 3：
调用：
Animation System
生成：
attack_fire.anim

Step 4：
绑定：
Events：
frame 5:

fire spawn


frame 6:

damage


frame 8:

recover


最终：
Cocos：
MechanicalCat


Idle

Run

FireAttack


可直接运行。

Phase 15.3 完成后的能力
CreativeForge 形成：
AI图片生成

↓

可编辑资产

↓

一致角色

↓

游戏动画

↓

行为事件

↓

可运行角色


继续进入 Phase 15.4：Cocos Export Adapter 工程设计
这一阶段完成后，CreativeForge 的链路：
AI生成角色

↓

AssetStruct

↓

Character DNA

↓

MotionAlign

↓

Animation Timeline

↓

Cocos Creator工程资源
闭环。
核心目标：
将 CreativeAsset 转换为 Cocos Creator 可以直接识别的项目文件。
这一层对应之前设计中的 GImport（Engine Import）。
CreativeAsset 中已经预留：
Engine

├── target
├── resources
├── prefab
├── animations
用于不同游戏引擎导入。
并且 GImport 作为独立 Processor：
CreativeAsset

↓

GImportProcessor

↓

Engine Asset


Phase 15.4 总目标
输入：
CreativeAsset

{
 identity:
 "robot_cat",

 animation:
 {
   frames,
   timeline,
   events
 }
}

输出：
完整 Cocos 工程资源：
cocos_project/


assets/


├── characters/


│
├── robot_cat/


│
├── textures/

│   └── robot_cat_atlas.png


│
├── spriteframes/

│   └── robot_cat.plist


│
├── animations/

│   ├── idle.anim

│   ├── run.anim

│   └── attack.anim


│
└── prefab/


    └── robot_cat.prefab


一、Cocos Export 架构
不要直接：
CreativeAsset

↓

生成Cocos文件

采用 Adapter。
架构：
                 CreativeAsset


                       |

                       ▼


              GImport Processor


                       |

                       ▼


             Engine Adapter Layer


                       |

        -------------------------------


        |                             |


 Cocos Adapter                 Unity Adapter


        |


        ▼


 Cocos Resources


二、Exporter 接口设计
目录：
gimport/


exporter/


├── base.py

├── cocos.py

└── unity.py


接口：
from abc import ABC,abstractmethod



class EngineExporter(ABC):


    @abstractmethod
    async def export(
        self,
        asset
    ):
        pass


未来扩展：
UnityExporter

GodotExporter

UnrealExporter

不影响核心系统。

三、Cocos Asset Mapping
CreativeAsset：
Animation

├── Frames

├── Anchor

├── Motion

└── Action

转换：

Frame
输入：
{
uri:
"frame001.png",

duration:
83
}

转换：
Cocos SpriteFrame。

Anchor
输入：
{
root:

{
x:64,
y:120
}

}

转换：
Cocos：
{
anchorX:0.5,

anchorY:0.1

}


Timeline
输入：
{
fps:

12,


frames:

[]

}

转换：
Cocos AnimationClip。

四、Texture Atlas Generator
Cocos 不推荐大量散图。
所以：
PNG Frames

↓

TexturePacker

↓

Atlas


生成：
robot_cat.png

robot_cat.plist


Atlas结构：
{
frames:

{

attack001:

{

x:0,

y:0,

width:128,

height:128

}

}

}


五、Cocos AnimationClip生成
Cocos动画：
核心：
AnimationClip

↓

Track

↓

SpriteFrame


例如：
attack.anim
{
name:

"attack",


duration:

0.8,


sample:

12,


tracks:

[

{

property:

"spriteFrame",


keys:

[

0,

1,

2

]

}

]

}


六、Prefab自动生成
目标：
用户导入Cocos：
直接出现角色。
Prefab结构：
RobotCat


├── Sprite

│
└── SpriteFrame


├── Animation


│
└── Animator


├── Collider


└── Scripts


Prefab数据：
{
node:

"RobotCat",


components:


[

"Sprite",

"Animation"


]

}


七、自动绑定组件
CreativeAsset:
{
engine:

{

target:

"cocos"

}

}

进入：
GImport。
自动：
添加：

Sprite：
角色显示

Animation：
播放动画

Collider：
Phase 15.5添加。

八、Cocos Adapter代码结构
adapters/


cocos/


├── exporter.py

├── prefab.py

├── animation.py

├── atlas.py

└── manifest.py


九、CocosExporter
核心：
class CocosExporter:


    name="cocos"



    async def export(
        self,
        asset
    ):


        atlas = (
            self.build_atlas(
                asset
            )
        )


        animations = (
            self.build_animation(
                asset
            )
        )


        prefab = (
            self.build_prefab(
                asset
            )
        )


        return {


        "atlas":atlas,


        "animations":animations,


        "prefab":prefab


        }


十、GImport Processor
统一入口。
class GImportProcessor:


    def __init__(
        self,
        exporter
    ):

        self.exporter=exporter



    async def process(
        self,
        asset
    ):


        result = await (
            self.exporter
            .export(asset)
        )


        asset.engine.resources=result


        return asset


十一、Agent调用方式
用户：
创建一个机械猫战士，并导入Cocos
Planner：
生成：
{
tasks:


[


"generate_asset",


"structure_asset",


"create_dna",


"motion_align",


"gimport"


]

}


执行：
generate

↓

AssetStruct

↓

DNA

↓

MotionAlign

↓

Cocos Export


十二、质量检测
GImport完成后：
必须验证：

1. Manifest检查
是否存在：
texture

atlas

animation

prefab


2. Animation检查
检查：
frame数量

duration

fps


3. Runtime检查
启动Cocos：
检测：
是否加载

是否播放

是否报错


十三、加入 Quality Schema
对应：
quality.import
之前设计：
{
manifest_score:1,

runtime_score:1

}



十四、Phase 15.4完成后的能力
现在：
CreativeForge：
已经具备：
输入：
一句话：
生成机械猫战士，带火焰剑攻击动画

系统：
Agent


↓

AI生成


↓

资产结构化


↓

角色身份保存


↓

动画对齐


↓

Sprite生成


↓

Cocos工程



最终输出：
打开Cocos Creator

↓

看到:

RobotCat.prefab


点击运行

↓

Idle

Run

FireAttack

正常播放


十五、Phase 15完整技术闭环
现在：
Phase 13

AssetStruct Engine

图片
↓

游戏资产结构



        ↓



Phase 14

Character DNA

资产
↓

角色身份



        ↓



Phase 15

MotionAlign


动画
↓

游戏行为



        ↓



Phase 15.4

GImport


游戏资产

↓

引擎运行

Phase 15.5：Hitbox / Hurtbox 自动生成系统
进入 MotionAlign 最后一环。
前面已经完成：
Phase 13
AssetStruct

图片
↓
可编辑游戏资产


Phase 14
Character DNA

角色
↓
身份一致性


Phase 15.1
Anchor Alignment

动画帧
↓
空间一致


Phase 15.2
Sprite Extraction

帧
↓
Sprite资源


Phase 15.3
Animation Timeline

资源
↓
游戏行为


Phase 15.4
Cocos Export

资产
↓
引擎工程
现在解决最后一个问题：
AI生成的角色虽然能播放动画，但是游戏不知道哪里可以攻击，哪里可以受伤。

一、Phase 15.5目标
输入：
attack_animation


frame_001.png

frame_002.png

frame_003.png

frame_004.png

输出：
Combat Asset


├── Hitbox

│
├── sword_attack_area


├── Hurtbox

│
├── body_area


├── Collider Config


└── Animation Events

最终：
Cocos：
RobotCat


Animation


Attack Frame 5


↓

Enable Hitbox


↓

Enemy Damage


二、核心架构
                Sprite Frame


                     |

                     ▼


              Mask Analyzer


                     |

        ----------------------------


        |                          |


    Hurtbox                     Hitbox


        |                          |


        ----------------------------


                     |

                     ▼


             Collider Generator


                     |

                     ▼


          Animation Event Binding


                     |

                     ▼


              Engine Export


三、Hitbox 和 Hurtbox 定义
Hurtbox
角色被攻击区域。
例如：
机械猫：
      head


       □


    body


       □


    legs


       □


Hitbox
攻击产生区域。
例如：
火焰剑：

      sword

        ========

            |

          body



四、数据模型设计
新增：
combat/


├── hitbox.py

├── hurtbox.py

├── collider.py


Collider Schema
{
"type":

"hitbox",


"name":

"fire_sword",


"shape":

"polygon",


"points":

[

[120,80],

[220,100],

[250,150]

]


}


五、Hurtbox 自动生成
核心思路：
利用 Phase 13 AssetStruct 的 Mask。
已有：
Character


↓

body mask


armor mask


weapon mask


所以：
不用重新识别。
流程：
AssetStruct Layer


        |

        ▼


Body Layer


        |

        ▼


Mask


        |

        ▼


Hurtbox


六、Body Mask 转 Hurtbox
输入：
body_mask.png

例如：
111111

111111

111111


生成：
轮廓点。
算法：
Contour Extraction。
流程：
Binary Mask


↓

Edge Detection


↓

Polygon Simplification


↓

Collider Polygon


输出：
{
hurtbox:


{

points:

[

[100,50],

[180,50],

[200,300],

[90,300]

]

}

}


七、Hitbox 自动生成
难点：
攻击区域不是身体。
需要：
识别：
weapon layer


Phase 13 已经有：
Layer Graph：
Character


├── Body

├── Weapon

└── Effect

所以：
直接读取：
weapon mask


流程：
Weapon Layer


↓

Mask


↓

扩张区域


↓

Hitbox Polygon


为什么需要扩张？
因为：
武器边缘不是实际攻击范围。
例如：
剑：
========

攻击：
需要：
================

增加：
margin。

八、Hitbox Expansion
算法：
Morphological Dilation。
例如：
原：
00000

00100

00100

扩张：
01110

01110

01110


参数：
expand_radius=8


效果：
攻击更稳定。

九、动画帧绑定
重点。
Hitbox不是永久存在。
例如：
挥剑：
10帧。
只有：
第4-6帧攻击。

Timeline：
{
animation:

"fire_attack",


events:

[

{

frame:

4,


type:

"hitbox_enable"

},


{

frame:

7,


type:

"hitbox_disable"

}

]

}


运行：
Frame 1

无攻击


Frame 4

开启Hitbox


Frame 7

关闭Hitbox


十、Hitbox Event System
事件类型：
AnimationEvent


├── HITBOX_ENABLE

├── HITBOX_DISABLE

├── DAMAGE

├── EFFECT

└── SOUND


例如：
{
frame:

5,


event:

"DAMAGE",


data:

{

damage:

100,


element:

"fire"

}

}


十一、Cocos Collider生成
Cocos支持：
● BoxCollider2D
● PolygonCollider2D
选择：
攻击：
PolygonCollider2D
身体：
PolygonCollider2D。

生成：
{
component:

"PolygonCollider2D",


points:

[

[10,20],

[50,80]

]

}


Prefab：
RobotCat


├── Sprite

├── Animation


├── Hurtbox


│   └── PolygonCollider2D


└── Hitbox


    └── PolygonCollider2D


十二、和 Character DNA 联动
这里非常重要。
不同角色：
身体结构不同。
不能固定：
人体模板


DNA提供：
{
body_type:

"robot_cat",


combat_style:

"melee"

}


生成策略：
猫战士：
重点：
● 爪
● 剑
● 尾巴

法师：
重点：
● 法杖
● 魔法区域

巨型机器人：
重点：
● 手臂
● 爆炸范围

所以：
Hitbox Generator：
读取：
Character DNA

+

Asset Graph

决定生成方式。

十三、Hitbox Generator接口
class HitboxGenerator:


    async def generate(
        self,
        asset
    ):


        weapon = (
            asset.layers
            .get("weapon")
        )


        mask = weapon.mask


        polygon = (
            extract_polygon(mask)
        )


        return polygon


十四、Combat Asset 数据结构
最终加入 CreativeAsset：
{
combat:


{


hitboxes:

[


{

name:

"fire_sword",


frames:

[4,5,6],


damage:

100


}


],


hurtboxes:

[


{

name:

"body",


type:

"normal"

}

]

}

}


十五、质量检测
新增：
Combat Quality。

1. Collision Coverage
检测：
Hitbox是否覆盖武器。
指标：
IoU。

2. Stability
连续帧：
Hitbox变化。
避免：
攻击区域跳动。

3. Runtime Test
Cocos运行：
检测：
● Collider存在
● Event触发
● Damage调用

十六、完整 MotionAlign Pipeline 完成版
AI Prompt


↓

Generate Character


↓

AssetStruct


↓

Character DNA


↓

Animation Generation


↓

Pose Alignment


↓

Sprite Extraction


↓

Timeline


↓

Hitbox/Hurtbox


↓

Cocos Export


↓

Playable Game Character


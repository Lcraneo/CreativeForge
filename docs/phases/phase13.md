继续进入 Phase 13：AssetStruct Engine 深度实现设计
这一阶段开始实现 CreativeForge 第一个真正的核心技术：
AI 生成图片 → 可编辑游戏资产结构（Game Asset Structure）的重建技术
这部分决定项目是否只是：
AI图片生成工具
还是：
AI游戏资产生产系统
CreativeAsset 已经冻结，因此 AssetStruct Engine 的输出必须符合统一协议。CreativeAsset Contract 本身就是为了支撑 PReCon、FAlign、GImport、Agent 和 Adapter 的统一交换。
Phase 1 中已经定义：
● Identity
● Source
● Content
● Pixel
● Animation
● Engine
● Quality
● Provenance
● Version
这些字段会成为 AssetStruct 的输出目标。

Phase 13 总目标
实现：
输入：
一张 AI 生成角色图

robot_cat.png
输出：
CreativeAsset


content:

├── layers

│
├── body

├── weapon

├── armor

├── effect


visual:

├── bounding box

├── anchor point


pixel:

├── palette

├── contour


quality:

├── segmentation_score


一、AssetStruct Engine 定位

CreativeForge：
PNG

↓

视觉理解

↓

语义拆分

↓

结构重建

↓

可编辑资产

二、整体架构
                 Image


                   |

                   ▼


          Vision Analyzer


                   |

                   ▼


          Semantic Graph


                   |

                   ▼


          Segmentation Engine


                   |

                   ▼


          Layer Extractor


                   |

                   ▼


          Asset Struct Builder


                   |

                   ▼


          CreativeAsset



三、模块划分
新增：
engines/


asset_struct/


├── analyzer/

│
├── vision_analyzer.py


├── segmentation/

│
├── sam_processor.py


├── layers/

│
├── layer_extractor.py


├── graph/

│
├── asset_graph.py


├── builder/

│
└── asset_builder.py


四、核心数据结构设计
1. Asset Layer
这是最重要的数据。
一个角色不是一张图。
而是：
Character

├── Head

├── Body

├── Weapon

├── Armor

├── Effect


定义：
class AssetLayer:


    name:str


    type:str


    image:str


    mask:str


    bbox:list


    confidence:float


例如：
{
"name":"sword",

"type":"weapon",

"image":"sword.png",

"mask":"sword_mask.png",

"bbox":[120,80,200,300],

"confidence":0.93

}

五、Vision Analyzer
作用：
理解图片。
输入：
character.png
输出：
Semantic Parts
例如：
{
parts:[

{
name:"body",
type:"character"

},

{
name:"sword",
type:"weapon"

}

]

}

技术选择
推荐：
第一版：
GPT-4.1 Vision / Claude Vision
原因：
负责：
理解
不是：
切割

调用：
class VisionAnalyzer:


    async def analyze(
        self,
        image
    ):


        return {

        "parts":[

            "body",

            "weapon"

        ]

        }


六、Segmentation Engine
这里是真正技术点。
Vision知道：
这是剑
但是不知道：
哪些像素属于剑
所以需要：
SAM2。
流程：
Vision

↓

Object Prompt

↓

SAM2

↓

Mask


例如：
输入：
weapon
SAM2：
输出：
weapon_mask.png

结构：
class Segmenter:


    async def segment(

        image,

        object_name

    ):


        mask = SAM2.predict(

            image,

            object_name

        )


        return mask


七、Layer Extractor
作用：
根据 Mask 提取独立图片。
例如：
原：
cat.png
Mask:
sword_mask
输出：
sword.png

流程：
Image

+

Mask


↓

Alpha Channel


↓

PNG Layer


代码结构：
class LayerExtractor:


    def extract(

        self,

        image,

        mask

    ):


        return layer_image


八、Asset Graph
这是区别普通分割的重要部分。
不仅拆图片。
还建立：
资产关系图
例如：
Character


 |

 ├── Body


 |

 ├── Weapon


 |       |

 |       └── Sword


 |

 └── Effect

数据：
class AssetNode:


    id:str


    type:str


    children:list



最终：
{
root:"character",

children:[

"body",

"weapon",

"effect"

]

}

九、Anchor 自动生成
游戏资产需要：
挂载点。
例如：
剑应该挂：
hand
脚：
feet
身体：
root

输出：
CreativeAsset:
{
anchor:

{

root:[128,256],

hand:[180,150],

feet:[128,300]

}

}

实现：
第一版：
Vision + Pose Estimation。
技术：
● MediaPipe Pose
● OpenPose

十、Pixel 信息提取
对应 CreativeAsset Pixel。
生成：
{
pixel:

{

grid:

{

size:8

},


palette:

{

colors:[

"#111111",

"#ffaa00"

]

}

}

}

用途：
后续：
● 像素重建
● 风格一致性
● 自动优化

十一、AssetStruct Pipeline
完整：
generate image


↓

Vision Analyzer


↓

Find Parts


↓

SAM2


↓

Generate Masks


↓

Extract Layers


↓

Build Asset Graph


↓

Generate Anchors


↓

Extract Pixel Data


↓

CreativeAsset


十二、Agent Tool 接入
新增：
structure_asset
Tool：
class AssetStructTool:


    name="structure_asset"



    async def run(
        self,
        asset
    ):


        result = await engine.process(
            asset
        )


        return result


十三、数据库变化
增加：
Asset Layer 表。
asset_layers
id

asset_id

name

type

image_url

mask_url

bbox

confidence


Asset Graph：
asset_nodes


id

asset_id

parent_id

type

metadata


十四、Benchmark设计
证明技术价值。
1. Layer Extraction Accuracy
指标：
IoU
比较：
Mask准确率。

2. Editability Score
测试：
能否单独修改：
● 武器
● 装备
● 特效

3. Reconstruction Completeness
检测：
是否生成：
body

equipment

animation anchor


十五、MVP实现范围
第一版不要做：
❌ 完美人体骨骼
❌ 自动重绘缺失区域
❌ 复杂动作理解
实现：
必须：
✅ Vision识别部件
✅ SAM2分割
✅ Layer导出
✅ Asset Graph
✅ CreativeAsset写入

十六、完成后的能力
用户：
输入：
创建一个机械猫战士
得到：
MechanicalCat


├── body.png

├── armor.png

├── sword.png

├── effect.png


metadata.json


CreativeAsset.json


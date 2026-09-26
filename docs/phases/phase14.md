Phase 14：Character DNA Engine 深度设计
进入第二个核心技术模块。
Phase 13 解决：
一张 AI 图片如何变成可编辑游戏资产。
Phase 14 解决：
一个 AI 角色如何拥有“身份”，并在持续修改、扩展、动画生成过程中保持一致。
这是 CreativeForge 区别于普通 AI 绘图工具的关键。

一、Character DNA Engine 定位
CreativeForge：
认为：
这是：
同一个角色

+
新的状态

结构：
Character Identity

        +

Modification


        ↓


New Version


二、整体架构
                 Character Image


                        |

                        ▼


              Character Encoder


                        |

                        ▼


              Identity Vector


                        |

        --------------------------------


        |                              |


 Similarity Search              DNA Memory


        |                              |


        --------------------------------


                        |

                        ▼


               Character DNA


                        |

                        ▼


              Agent Modification



三、Character DNA 数据模型
Character DNA 不保存图片。
保存：
角色的核心特征。
结构：
{
character_id:

"cat_warrior_001",


identity:

{


species:

"robot_cat",


style:

"cyberpunk",


body:

{

height_ratio:1.8,

armor_type:"metal"

},


face:

{

eye_color:"blue",

shape:"cat"

},


color:

[

"black",

"blue"

]

},


embedding:

[0.231,0.553,...],


versions:

[

"v1",

"v2"

]

}

四、DNA 三层结构
Layer 1：Semantic Identity（语义身份）
解决：
“它是谁”。
包括：
● 种族
● 风格
● 外形
● 核心装备
例如：
{
species:

"cat"


role:

"warrior"


style:

"anime cyber"

}

Layer 2：Visual Identity（视觉身份）
解决：
“长什么样”。
包括：
● 颜色
● 比例
● 五官
● 轮廓
例如：
{
palette:

[
"#000",

"#00ffff"

],


head_ratio:

0.18,


body_ratio:

0.6

}

Layer 3：Vector Identity（向量身份）
解决：
机器理解。
图片：
↓
Encoder
↓
Embedding
例如：
[0.123,
0.532,
0.876...]


五、Character Encoder
作用：
图片 → Identity Vector。
流程：
Character Image


        |

        ▼


Vision Encoder


        |

        ▼


Embedding Vector


技术选择：
MVP：
CLIP。
后期：
训练：
Character Identity Encoder。

CLIP流程
输入：
cat_warrior.png
输出：
[
0.213,
0.556,
0.921
]

这个向量代表：
视觉身份。

六、Identity Vector
核心数据：
class IdentityVector:


    character_id:str


    vector:list[float]


    model:str


    created_at:str


保存：
数据库：
character_embeddings
字段：
id

character_id

embedding

model

created_at


七、Similarity Retrieval
作用：
找到：
“是不是同一个角色”。

例如：
用户：
给机械猫战士换武器
Agent收到：
新图片：
cat_fire_sword.png
计算：
new_embedding


        VS


database embeddings


计算：
Cosine Similarity：
公式：
$similarity =
\frac{A\cdot B}
{|A||B|}$
结果：
0.92

判断：
同一个角色。

阈值：
>0.85

认为同角色


八、Vector Database
增加：
Milvus / Chroma。
结构：
Character Memory


cat_warrior_001


vector:

[0.23,0.55,...]


metadata:

{

style:

cyberpunk

}


查询：
search(
vector,
top_k=5
)

返回：
[
{
id:
"cat_warrior_001",

score:
0.94
}
]

九、角色版本系统
角色不是覆盖修改。
采用：
Version Graph。
结构：
Cat Warrior


       |

       v1


       |

       +------ v2
       |
       |
       +------ v3


例如：
v1：
基础角色。
v2：
增加火焰剑。
v3：
增加机甲。

数据库：
character_versions
id

character_id

parent_version

changes

asset_id

created_at


十、Change Tracking
每次修改：
记录：
{
change_type:

"equipment_change",


before:

"sword",


after:

"fire_sword"

}


这样 Agent 可以理解：
不是重新生成。
而是：
修改。

十一、Agent 如何调用 DNA
这是重点。
用户：
给机械猫战士增加火焰剑

Step 1
Planner分析：
modify_existing_character

不是：
create_character。

Step 2
调用：
Character Search Tool。
find_character(
"机械猫战士"
)


返回：
{
id:

"cat_warrior_001",

similarity:

0.94

}


Step 3
加载 DNA。
得到：
{
identity:

"robot cat",

style:

"cyberpunk",

color:

"black blue"

}


Step 4
传给生成模型。
Prompt 不再：
生成机械猫战士

而是：
保持 cat_warrior_001 身份，

只修改：

weapon=fire sword

保持：

颜色

脸部

比例

风格

不变。


Step 5
生成新版本。
结果：
Cat Warrior v2


十二、DNA Engine API设计
创建DNA
POST：
/api/v1/dna/create

请求：
{
asset_id:

"asset001"

}

返回：
{
character_id:

"cat001"

}


查询角色
GET：
/api/v1/dna/{character_id}

返回：
{
identity:{},

embedding:{}

}


相似搜索
POST：
/api/v1/dna/search

请求：
{
image:

"new.png"

}

返回：
{
match:

"cat001",

score:

0.93

}


十三、项目代码结构
增加：
engines/


character_dna/


├── encoder/


│
├── clip_encoder.py


├── vector/


│
├── store.py


├── retrieval/


│
├── similarity.py


├── memory/


│
├── dna_memory.py


├── version/


│
├── version_manager.py


└── service.py


十四、核心代码接口
Encoder
class CharacterEncoder:


    async def encode(
        self,
        image
    ):

        vector = model.encode(
            image
        )

        return vector


Similarity
class DNAResolver:


    async def search(
        self,
        vector
    ):


        result = vector_db.search(
            vector
        )


        return result


DNA Service
class CharacterDNAService:


    async def create(
        self,
        asset
    ):


        vector = await encoder.encode(
            asset.image
        )


        dna = {

        "identity_vector":
        vector

        }


        return dna


十五、Benchmark设计
证明角色一致性。

Benchmark 1：Identity Similarity
测试：
同角色不同动作：
Idle

Attack

Run

计算：
Embedding 相似度。

Benchmark 2：Modification Preservation
测试：
修改：
● 武器
● 装甲
保持：
● 脸
● 配色
● 身体比例

Benchmark 3：Version Stability
连续：
10次修改。
检测：
身份漂移。

十六、MVP实现范围
第一版：
必须：
✅ CLIP Encoder
✅ Vector Database
✅ DNA JSON结构
✅ Similarity Search
✅ Version记录
暂缓：
❌ 自训练Encoder
❌ 大规模角色数据库
❌ 自动角色进化模型

十七、完成后的 CreativeForge 能力
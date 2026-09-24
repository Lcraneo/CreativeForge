**Phase 5：GImport 自

这一阶段完成第三个核心技术壁垒：

> **GImport（Game Engine Import Pipeline）——AI生成资产到游戏引擎项目的一键编译导入系统**

前三阶段：

```text
PReCon
自研像素重建
        |
        v
FAlign
自研切帧对齐
        |
        v
GImport
自研引擎一键导入
```

形成完整闭环：

```text
AI资产生成

↓

标准化资产协议 CreativeAsset

↓

像素优化

↓

动画修复

↓

自动进入游戏引擎
```

---

# Phase 5 总体目标

解决当前 AI 游戏资产生产流程中的问题：

传统流程：

```text
AI生成图片

↓

人工切图

↓

人工制作Sprite Sheet

↓

人工设置Animation Clip

↓

人工拖入Unity/Cocos

↓

人工配置Prefab

↓

运行测试
```

耗时：

几十分钟~数小时。

---

GImport：

```text
CreativeAsset

        |

        v

GImport Engine

        |

        +----------------+

        |                |

      Cocos            Unity

        |                |

        v                v

   可运行游戏资产
```

---

# 一、工程目录设计

```text
CreativeForge-Phase5-GImport-Engine

│
├── README.md
│
├── gimport/
│
│
├── pipeline/
│   │
│   └── gimport_engine.py
│
│
├── manifest/
│   │
│   ├── manifest_generator.py
│   └── schema.py
│
│
├── atlas/
│   │
│   └── sprite_atlas_builder.py
│
│
├── animation/
│   │
│   └── animation_clip_generator.py
│
│
├── prefab/
│   │
│   └── prefab_generator.py
│
│
├── adapters/
│
│   ├── cocos_adapter.py
│   └── unity_adapter.py
│
│
├── validation/
│
│   └── runtime_validator.py
│
│
├── exporter/
│
│   └── one_click_export.py
│
│
├── tests/
│
│   └── test_gimport_contract.py
│
└── docs/
    └── architecture.md

```

---

# 二、核心 Pipeline

入口：

```python
GImportEngine
```

完整流程：

```text
CreativeAsset

      |

      v

Asset Manifest Generator

      |

      v

Sprite Atlas Builder

      |

      v

Animation Clip Generator

      |

      v

Prefab Generator

      |

      v

Engine Adapter

      |

      v

Runtime Validation

      |

      v

One Click Export

```

---

# 三、GImport Engine

文件：

```text
gimport/pipeline/gimport_engine.py
```

核心：

```python
from manifest.manifest_generator import ManifestGenerator
from atlas.sprite_atlas_builder import SpriteAtlasBuilder
from animation.animation_clip_generator import AnimationClipGenerator
from prefab.prefab_generator import PrefabGenerator
from validation.runtime_validator import RuntimeValidator


class GImportEngine:


    def __init__(self):

        self.manifest = ManifestGenerator()

        self.atlas = SpriteAtlasBuilder()

        self.animation = AnimationClipGenerator()

        self.prefab = PrefabGenerator()

        self.validator = RuntimeValidator()



    def process(
        self,
        asset,
        engine="cocos"
    ):


        manifest = (
            self.manifest.generate(asset)
        )


        atlas = (
            self.atlas.build(asset)
        )


        animation = (
            self.animation.generate(asset)
        )


        prefab = (
            self.prefab.generate(
                asset
            )
        )


        result = {

            "manifest":manifest,

            "atlas":atlas,

            "animation":animation,

            "prefab":prefab

        }


        validation = (
            self.validator.check(
                result
            )
        )


        result["validation"] = validation


        return result
```

---

# 四、Asset Manifest Generator

## 作用

生成资产清单。

类似：

游戏引擎资产身份证。

输入：

CreativeAsset：

```json
{
"id":"hero001",

"type":"character"
}
```

输出：

```json
{
"asset_id":"hero001",

"type":"character",

"resources":
{

"texture":
"hero.png",

"animation":
"hero.anim",

"prefab":
"hero.prefab"

}

}
```

---

# 五、Sprite Atlas Builder

解决：

AI生成：

```text
frame1.png

frame2.png

frame3.png
```

转换：

```text
hero_sprite_atlas.png
```

输出：

```json
{
"atlas":

{
"name":"hero",

"frames":

[
"idle_0",

"idle_1",

"walk_0"

]

}

}
```

---

优势：

减少：

* Draw Call
* 资源管理复杂度

---

# 六、Animation Clip Generator

读取：

Phase4 FAlign 输出：

```json
{
"animation":

{

"frames":[],

"anchor":{},

"motion":{}

}

}
```

生成：

引擎动画配置：

---

Unity:

```json
{
"clip":

{

"name":"walk",

"fps":12,

"loop":true

}

}
```

---

Cocos:

```json
{
"animation":

{

"name":"walk",

"duration":1.0

}

}
```

---

# 七、Prefab Generator

自动生成：

角色实体。

例如：

输入：

```text
Pixel Character

+

Animation

+

Collider
```

输出：

```text
Hero.prefab
```

包含：

```text
Hero

├── Sprite Renderer

├── Animator

├── Collider

├── Script

└── Animation Controller
```

---

# 八、Engine Adapter

核心设计：

不绑定单引擎。

接口：

```python
class EngineAdapter:


    def import_asset(self, asset):
        pass


    def export_project(self):
        pass
```

实现：

```text
EngineAdapter

        |

        +---- CocosAdapter

        |

        +---- UnityAdapter

        |

        +---- GodotAdapter

```

---

# 九、Cocos Adapter

输出：

```text
assets/

├── textures

├── atlas

├── animations

└── prefabs

```

---

# 十、Unity Adapter

输出：

```text
Assets/

├── Texture/

├── Animation/

├── Prefab/

└── Controller/

```

---

# 十一、Runtime Validation

这是比赛展示的重要部分。

导入后自动检测：

## 资源完整性

```text
texture exists

animation exists

prefab exists
```

---

## 动画完整性

检测：

```text
frame count

anchor drift

loop error
```

---

## 引擎兼容性

例如：

```text
Cocos:

✔ atlas

✔ prefab


Unity:

✔ animator

✔ prefab
```

---

输出：

```json
{
"status":"success",

"score":

0.96

}
```

---

# 十二、One Click Export

最终用户体验：

用户输入：

> 创建一个像素火焰法师角色

Agent 自动：

```text
Windup

↓

CreativeAsset

↓

PReCon

↓

FAlign

↓

GImport

↓

Cocos项目
```

最终：

点击：

```text
Export Game Project
```

生成：

```text
FireMageGameAsset.zip
```

包含：

```text
Assets

├── Character

├── Animation

├── Prefab

└── Config
```

---

# 十三、GImport 技术创新点

## 1. Asset Manifest 驱动

不是：

```text
文件复制
```

而是：

```text
CreativeAsset Contract

↓

自动编译
```

---

## 2. Multi Engine Adapter

同一资产：

```text
CreativeAsset

        |

        +---- Unity

        |

        +---- Cocos

        |

        +---- Godot

```

---

## 3. Runtime Validation

传统：

人工发现错误。

GImport：

自动：

```text
Generate

↓

Validate

↓

Repair

↓

Export
```

---

# 十四、三大技术最终闭环

目前：

```text
                 Creative Agent


                      |

                      v


             CreativeAsset Contract


                      |

                      v


------------------------------------------------


PReCon              FAlign             GImport


像素重建            动画修复            引擎导入


------------------------------------------------


                      |

                      v


              Game Engine Project


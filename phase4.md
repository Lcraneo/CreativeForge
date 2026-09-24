
# Phase 4 目标

## FAlign（Frame Alignment Engine）

定位：

> AI 游戏动画生成后的自动切帧、对齐、纠偏引擎。

解决：

| 问题    | 原因              | FAlign处理               |
| ----- | --------------- | ---------------------- |
| 人物漂移  | 每帧主体位置变化        | Anchor Alignment       |
| 脚底滑动  | Root Motion 不稳定 | Root Correction        |
| 动作抖动  | 帧间差异过大          | Temporal Consistency   |
| 动作不连贯 | 动作阶段错位          | Motion Phase Alignment |

---

# 一、工程结构

```text
CreativeForge-Phase4-FAlign-Engine

│
├── README.md
│
├── falign/
│
│   ├── pipeline/
│   │   └── falign_engine.py
│   │
│   ├── extraction/
│   │   └── frame_extractor.py
│   │
│   ├── anchor/
│   │   └── anchor_detector.py
│   │
│   ├── phase/
│   │   └── phase_alignment.py
│   │
│   ├── motion/
│   │   └── root_motion.py
│   │
│   ├── temporal/
│   │   └── temporal_consistency.py
│   │
│   └── quality/
│       └── animation_quality.py
│
├── adapters/
│
│   └── creative_asset_adapter.py
│
├── tests/
│
│   └── test_falign_contract.py
│
├── docs/
│
│   └── architecture.md
│
└── examples/
    └── animation_result.json

```

---

# 二、核心 Pipeline

入口：

```python
FAlignEngine
```

流程：

```text
Animation Frames

        |
        v

Frame Extraction

        |
        v

Anchor Detection

        |
        v

Motion Phase Alignment

        |
        v

Root Motion Correction

        |
        v

Temporal Consistency

        |
        v

Quality Evaluation

        |
        v

CreativeAsset.animation
```

---

# 三、FAlign Engine 主控制器

文件：

```
falign/pipeline/falign_engine.py
```

```python
from falign.extraction.frame_extractor import FrameExtractor
from falign.anchor.anchor_detector import AnchorDetector
from falign.phase.phase_alignment import PhaseAligner
from falign.motion.root_motion import RootMotionCorrector
from falign.temporal.temporal_consistency import TemporalAnalyzer
from falign.quality.animation_quality import AnimationEvaluator


class FAlignEngine:


    def __init__(self):

        self.extractor = FrameExtractor()

        self.anchor = AnchorDetector()

        self.phase = PhaseAligner()

        self.motion = RootMotionCorrector()

        self.temporal = TemporalAnalyzer()

        self.quality = AnimationEvaluator()



    def process(self, frames):

        normalized_frames = (
            self.extractor.process(frames)
        )


        anchors = (
            self.anchor.detect(
                normalized_frames
            )
        )


        phase_result = (
            self.phase.align(
                normalized_frames,
                anchors
            )
        )


        motion_result = (
            self.motion.correct(
                normalized_frames,
                anchors
            )
        )


        temporal_result = (
            self.temporal.analyze(
                normalized_frames
            )
        )


        quality = (
            self.quality.evaluate(
                anchors,
                motion_result,
                temporal_result
            )
        )


        return {

            "animation": {

                "frames":
                    normalized_frames,

                "anchor":
                    anchors,

                "phase":
                    phase_result,

                "motion":
                    motion_result

            },


            "quality":

            {

                "animation":
                    quality

            }

        }

```

---

# 四、Frame Extraction

作用：

统一动画输入。

支持：

```text
sprite sheet

video

gif

AI generated sequence
```

输出：

```json
{
 "frames":[

 {
   "id":0,
   "image":"frame0.png"
 }

 ]
}
```

---

# 五、Character Anchor Detection

核心。

定义角色稳定点：

```text
root

feet

center

head
```

例如：

```json
{
"anchor":{

"root":
{
"x":32,
"y":60
},


"feet":
{
"x":32,
"y":64
}

}

}
```

作用：

每帧：

```
Frame1

root(30,60)


Frame2

root(35,62)
```

发现：

```
+5,+2 偏移
```

进入修正。

---

# 六、Motion Phase Alignment

解决：

AI生成：

```
Frame1
站立

Frame2
半抬脚

Frame3
落脚
```

但是：

下一次生成：

```
Frame1
抬脚

Frame2
站立
```

动作阶段错乱。

---

建立：

```python
phase_id
```

例如：

walk:

```
0%
25%
50%
75%
100%
```

映射：

```json
{
"action":"walk",

"phase":

[
0,
0.25,
0.5,
0.75,
1
]

}
```

---

# 七、Root Motion Correction

解决：

## 人物漂移

输入：

```json
{
"root":

[
[30,60],
[34,61],
[39,63]

]
}
```

计算：

```text
delta movement

↓

判断是否真实移动

↓

修正
```

输出：

```json
{
"root_dx":0,

"root_dy":0,

"drift_corrected":true
}
```

---

# 八、Temporal Consistency

检测：

相邻帧：

```text
Frame1

↓

Frame2
```

差异：

```text
pixel difference

+

feature difference
```

输出：

```json
{
"jitter_score":0.04,

"smooth":true
}
```

---

# 九、Animation Quality Evaluation

写入：

CreativeAsset:

```json
{
"quality":

{

"animation":

{

"anchor_score":0.96,

"motion_score":0.94,

"temporal_score":0.95,


"overall":0.95

}

}

}
```

---

# 十、CreativeAsset 对接

输入：

Phase 3 输出：

```json
CreativeAsset

{

pixel:{},

animation:

{

frames:[...]

}

}

```

经过 FAlign：

输出：

```json
CreativeAsset

{

animation:

{

frames,

anchor,

motion,

action

},


quality:

{

animation:{}

}

}
```

---

# 十一、FAlign 技术亮点（比赛表达）

## 1. Anchor-driven Alignment

不是简单逐帧裁剪：

而是：

```
角色语义关键点
+
空间约束
```

保证：

角色稳定。

---

## 2. Motion Phase Modeling

将动画：

```
图片序列

↓

动作状态空间
```

解决 AI 动作随机性。

---

## 3. Temporal Quality Evaluation

建立：

```
Animation Quality Score
```

自动判断：

* 是否抖动
* 是否漂移
* 是否连贯

---

# 十二、当前完整技术链

现在：

```text
AI Generate

    ↓

Windup Adapter


    ↓

CreativeAsset


    ↓

PReCon

(像素重建)


    ↓

FAlign

(切帧对齐)


    ↓

GImport

(引擎导入)

    ↓

Cocos / Unity
```




# 视频质量提升路线图（2026-10-03）

状态：**分析与实施计划（未实施）**。本文基于 2026-10-03 全仓代码核查（三条视频链路逐文件取证），目标：让视频生成质量达到或接近专业 AIGC 水平，并建立可验证的评估体系。

---

## 0. 结论速览

**最大根因不是模型不行，而是交付链倒挂**：我们按 720p/24fps 生成 AI 视频（wan2.2-i2v-flash，1.25 元/条），却把 5s 源视频只取 1/4 时长、抽到 384px/12fps、再压进 255 色无抖动的 GIF 交付——生成的质量大部分死在交付环节。四阶段：**V1 交付链快赢（零额度，1 周）→ V2 模型双档与提示词工程（2 周）→ V3 素材与渲染引擎升级（4 周）→ V4 评估体系固化（持续）**。

---

## 1. 现状基线（代码事实）

三条视频链路，规格与问题各不相同：

| 链路 | 生成规格 | 交付规格 | 关键证据 |
|---|---|---|---|
| **AI i2v 动作视频**（动画工作台"AI 视频驱动"、试玩批次补齐） | DashScope `wan2.2-i2v-flash`，请求 `size=1280*720`，源视频约 5s/24fps | **384×384 GIF @12fps，30 帧（2.5s 循环）** | model_service/service.py:607-623；animation_service/service.py:221-222, 697-699, 891-895 |
| **程序化帧动画**（riganim 骨骼/源图驱动） | 参数化曲线逐帧渲染，刚体分区合成 | 256~512px GIF @12-16fps，12-16 帧 | artgen/riganim.py:270-529；api/routes.py:54-64, 1450-1455 |
| **onetake 宣传片**（/showcase 发布） | Playwright 逐帧 + ffmpeg，快门 180° | **1080p30 H.264 CRF16**（终稿 4K60） | third_party/onetake/scripts/render.py:209-213 |

成本牌价（model_service/usage.py:33-35）：`wan2.2-i2v-plus` 3.50 元/条、`wan2.2-i2v-flash` 1.25 元/条。视频是额度大头，已有 mp4 缓存（model_service/service.py:590-603）、润色提示词持久缓存（animation_service/service.py:109-139）等五层省额度机制。

onetake 宣传片链的渲染规格已达专业水准（CRF16/快门模糊/oracle 验收），其短板在素材端（24px 像素网格重建，adapters/onetake/asset_mapper.py:12-15，属风格选择）。**本方案主体针对前两条链路。**

---

## 2. 根因分析

### 2.1 分辨率：交付规格与生成规格倒挂（主因）

- i2v 源视频 1280×720，抽帧时统一缩到 384px（service.py:891-895 `size` 参数），GIF 画布 384×384——像素信息量只剩源视频的 **16%**（921,600 → 147,456），线性细节缩到 1/2~1/3。
- 抠图链把任何素材 `_fit` 缩到 ≤512/384/256（animation_service/service.py:1094-1158），全仓**没有任何超分/放大处理**（搜 upscale/esrgan/超分 零命中）。
- 试玩条带再压到 288px 宽（api/routes.py:1691-1702）。
- 抠图边缘只有 `MaxFilter(7)+GaussianBlur(1.2)` 羽化（service.py:1154），洪泛容差 48（artgen/sourceanim.py:19），放大后毛边明显。

### 2.2 帧率与时间采样（主因）

- 源视频 24fps → 抽帧 fps=12，**时间分辨率减半**；代码注释自证："120 帧里只取 30 帧，时间采样率仅 17%→25%"（service.py:216-222）。
- 12fps 是"逐帧感"的直接来源；现代专业 AIGC 视频标准是 24/30fps。
- 帧数钳制 `min(48, …)`（artgen/pipeline.py:148-149）把 24fps×2.5s=60 帧的合法需求挡在门外。
- 抽帧窗口最短 1.25s（VIDEO_SAMPLE_DURATION），5s 源视频 3/4 的时间信息被丢弃。

### 2.3 动态效果

- **程序化链**：刚体分区旋转 + 羽化搭接（riganim.py:352-450），无网格变形、无次级运动（头发/裙摆/披风零摆动）、侧视=正视镜像（character2d.py:352-357）——"剪纸感"的结构性来源。缓动曲线本身已是 C1 连续（anim.py:48-69），曲线质量不是瓶颈，帧率和刚体性才是。
- **i2v 链**：`wan2.2-i2v-flash` 是速度档；`prompt_extend=false` 关闭了官方提示词增强（service.py:618-623）；运动描述依赖模板+润色缓存，运动幅度、物理感上限受档位与提示词约束。
- **侧视资源浪费**：AI 三视图 side.png 只用于展示与导出（export_service/character_package.py:100-107），**不进入动画管线**——侧视动画仍在用镜像的正视图。

### 2.4 内容连贯性

- 单图条件 i2v 存在角色漂移与肢体伪影，目前靠负面词兜底（"重影/肢体分裂/形变破碎"，service.py:558-560）；未使用首尾帧约束（若 API 支持）来锁定循环与一致性。
- 跨动作之间各自独立生成，无统一参考；循环接缝只按帧差重排起点（service.py:979-1001），无交叉溶解/运动矢量过渡。
- 镜头语言缺失：onetake 链有 BEATS 节拍表（timeline_mapper.py:23-44），动画工作台无任何镜头/节奏概念。

### 2.5 视觉真实感

- **GIF 格式天花板**：255 色 MEDIANCUT 量化、`dither=NONE`（artgen/gif.py:228），渐变与抗锯齿边缘出现色带；且 `_quantize_frame` **逐帧独立建调色板**（gif.py:194-197）→ 帧间色彩漂移（隐性闪烁源之一）。
- 无后期链：无超分、无补帧、无锐化/降噪/调色；帧序列**没有 mp4 出口**（ffmpeg 只出现在 i2v 解码与 onetake 渲染两条旁路）。
- 试玩舞台 `imageSmoothingEnabled=false`（PlaytestStage.tsx:496）在放大 AI 动画（非像素画）时产生硬边像素感。

### 2.6 交付格式

GIF89a（1989 年格式）：256 色上限、无音轨、压缩率低、透明只支持 1 位。专业 AIGC 交付标准是 mp4（H.264/HEVC, yuv420p, 24-30fps, 1080p）。我们唯一符合标准的编码链在 onetake（CRF16 high profile +faststart，render.py:209-213），**没有复用到角色动画链**。

---

## 3. 解决方案总览

| 方向 | 内容 | 对应阶段 |
|---|---|---|
| A 交付链改造 | i2v mp4 直通交付、编码规范统一、GIF 降级为兼容预览 | V1 |
| B 模型参数与选型 | 双档策略（flash 草稿/plus 定稿）、prompt_extend、能力实测、多供应商抽象 | V2（多供应商可延至 V3） |
| C 素材处理流程 | 2K 源图/超分、matting 精修、side 视图真正入动画管线 | V3 |
| D 渲染引擎升级 | riganim 网格变形、次级运动、RIFE 补帧到 24fps | V3 |
| E 后期处理链 | 超分/补帧/锐化/编码封装统一模块 | V1 起（编码）→ V3（超分补帧） |
| F 质量评估体系 | 客观指标扩展 + MOS 人评 + 基准集 + 门禁接入 | V1 建 → V4 固化 |

---

## 4. 分阶段实施计划

### V1 交付链快赢（第 1 周，零新增额度）

> **✅ 已实施（2026-10-03 晚）**。落地明细：
> - mp4 直通：`AnimationService._deliver_video_mp4`（ffmpeg `-ss/-t` 帧级精确裁剪 + H.264 CRF16 high profile +faststart），`_slice_video` 新增 `with_info`（默认 False，既有调用方/测试零破坏）；meta 增 `urls.video` + `video_spec`（分辨率/帧率/时长/码率）；顺带修复 `create_video` 的 `source_cropped`/`subject_locked` 在写盘后才追加、从未落盘的旧 bug。routes `.mp4 → video/mp4`；前端主预览 mp4 优先（`<video>`，onError 回退 GIF）+ 「下载 MP4」+ 规格展示。
> - GIF 全局调色板：`encode_gif` 全序列 NEAREST 采样统一建板（消除逐帧独立 MEDIANCUT 的帧间色彩漂移）；`dither` 参数默认 NONE（disposal=2 下抖动噪声有闪烁风险，待视觉 A/B 后再决定是否开启）。实测对照旧基线：**质量七项全 PASS**（motion_cv 0.574× 优于门限、temporal/sharpness 1.00×），**GIF 体积 -12%**。已知良性边界：相邻"亚调色板微差"帧会坍缩合并（时长完整并入邻居 GCE，循环总时长不变，测试按 ±2 帧容差 + 总时长硬校验）。
> - 帧数钳制 48→90（pipeline/sourceanim）、60→90（抽帧上限），24fps 整循环合法化。
> - 规格入基线：`delivery_size`/`source_fps`/`mp4_width`/`mp4_fps`/`mp4_duration` 进 video_quality 报告与 TOLERANCES 硬门（mp4 码率仅记录）；基线已重录并 --check 全 PASS。
> - 回归：动画回归 **123/123**（原 112 + 新增 11：全局调色板色表逐字节一致/三色回读/透明保留/with_info 元数据/mp4 交付分辨率帧率窗口）、run_tests **39/39**、前端 typecheck 干净 + vitest **35/35**。

**目标**：不动模型、不花一分钱额度，把已付费的 720p/24fps 源视频完整送达用户眼前。

任务（按优先级）：
1. **i2v mp4 直通交付**：`create_video` 在抽帧选定循环窗口后，用 ffmpeg 按 `-ss/-t` 裁剪缓存 mp4 并重编码（`-c:v libx264 -crf 16 -pix_fmt yuv420p -profile:v high -movflags +faststart`，对齐 onetake 编码规范），落 `{id}.mp4` 到 ANIMATION_DIR；meta 增 `video_url`。前端 AnimationStudio 优先 `<video loop>` 播放 mp4，GIF 降级为兼容预览。
2. **GIF 调色板统一**：`encode_gif` 改为全序列采样建**全局调色板**（消除逐帧 MEDIANCUT 的帧间色漂），并 A/B `dither=FLOYDSTEINBERG`（注意 disposal=2 下抖动噪声是否引入帧间闪烁，实测定夺）。
3. **帧数钳制放宽**：pipeline.py:148-149 的 48 → 90，并重验内存契约（既有口径 30 帧×384px≈90MB 峰值，翻倍需实测；抽帧已是 imageio 流式，风险可控）。
4. **规格指标入基线**：ffprobe（分辨率/帧率/码率）写进 meta 与 benchmark 报告——把"规格"本身变成被测对象。

**资源**：1 人 × 3-5 天；无 GPU；额度 0（同一次 i2v 调用）。
**评估标准**：mp4 交付链全链路跑通；`benchmark/video_quality.py --check` 七项指标相对现有 video_baseline.json 不降级；sharpness（对 mp4 帧测量）显著高于旧 384px GIF 路径；GIF 色带目测消除；动画回归 112/112 通过。
**风险与回退**：mp4 裁剪窗与 GIF 循环窗不一致 → 用同一窗口参数派生两者；前端 `<video>` 循环衔接生硬 → mp4 裁剪窗口沿用现有接缝优化选出的起点。

### V2 模型双档与提示词工程（第 2-3 周，额度预算 ≈ 200-400 元）

> **✅ 已实施 + 实测完成（2026-10-03 深夜，实际花费 50.3 元 / 33 次视频调用）**。
> 实测报告：`benchmark/i2v_report.json`（逐动作明细）、能力探测：`benchmark/dashscope_capability.json`、样片：`benchmark/i2v_runs/<变体>/<动作>.mp4`。基准角色 ast61935 星辉剑士（`benchmark/i2v_bench.py` 可重跑，同参命中缓存零计费）。
>
> **能力实测结论（DashScope 现状，2026-10）**：
> - `wan2.5-i2v-*`、`wan2.2-i2v-flf2v`（首尾帧）、`wan2.2-i2v-flash-audio` 均**不存在**（400 免费探测确认）——首尾帧循环锁定与音频生成在当前平台不可用。
> - `size` 参数被**完全忽略**：请求 1920*1080 仍输出 960×960——分辨率由模型固化（flash 960×960@30fps、plus 1440×1440@30fps，均 5s），升分辨率只能换模型档。
> - 旧世代 `wanx2.1-i2v-plus` 在线但画质明显更软（公平口径 sharpness 15.2 vs flash 18.6），不采用。
> - `prompt_extend` 真实生效：色保真 0.094→0.132（+40%），运动量 +55%，时序一致性略降（0.936→0.929）。
>
> **词表 A/B（flash，5 动作 × 同图同负面词）**：v2 运动学词表 vs v1 旧词表——motion_cv **0.631→0.520（-18%，运动更均匀）**、色保真 **0.061→0.094（+55%）**；公平口径 sharpness 20.5→18.6（运动量增大带来的动态模糊，可接受）。
>
> **档位对比（v2 词表）**：plus 对 flash——**1440² vs 960²（2.25× 像素）**、motion_cv **0.520→0.387（-26%，全组最优）**、时序一致性 0.9397（最优）；公平口径 sharpness 持平（19.1 vs 18.6）。定稿档价值成立。
>
> **落地（已进代码）**：双档 `video_model_final`（默认 wan2.2-i2v-plus）+ 请求字段 `final_quality` + 前端「高清定稿（plus 档）」开关；缓存 key 修复：**size 与 prompt_extend 已入 key**（V2 基准曾因此整组命中错误缓存），含 6 项契约测试（`tests/test_video_pipeline.py` 28/28）；词表 v2 为生产默认。
> **推荐组合**：草稿 = flash + v2（1.25 元/条，41s）；定稿 = plus + v2（3.50 元/条，51s，1440²）。
> **MOS 人评**：样片已就位（i2v_runs/ 五组 × 五动作），按 §5.2 盲评表打分即可回填基线。
>
> **目标**：把"画质优先"从回退注释变成真实策略：草稿用 flash 确认动作，定稿用 plus 出片；提示词工程化。

任务：
1. **能力实测先行**（不做无依据升级）：实测 DashScope wan2.2 系 `size` 上限（1080P 是否可用）、`duration` 参数、首尾帧模型（flf2v 类）与 audio 参数，产出 `docs/dashscope-video-capability.md` 备忘。
2. **双档策略**：settings 增加 `video_model_final`（默认 wan2.2-i2v-plus）；批次补齐用 flash，工作台新增"定稿"按钮走 plus；模型回退链保持"plus→flash→turbo"画质优先语义（service.py:607-616）。
3. **prompt_extend A/B**：10 条基准集上实测开启收益，按结果更新 model_settings.json。
4. **运动提示词词表工程**：为 5 动作 × 2 视角建立运动学描述模板（速度/幅度/相机锁定/循环收尾词），负面词按伪影类型分场景扩展；所有改动自动进缓存 key（service.py:594-599 已保证）。
5. **基准集建立**：固定 1 个角色资产（如骑士 ast61935）× 5 动作 × 2 视角 = 10 条固定 prompt，作为后续所有 A/B 的公共标尺；跑通 flash 档产出 **i2v_baseline.json**。

**资源**：1 人 × 1.5-2 周；额度：基准集一轮 ≈ 40 次 flash（50 元）+ 定稿 40 次 plus（140 元），两轮调优 ≈ 400 元内；额度仪表（GET /settings/model/usage）全程监控。
**评估标准**：基准集 MOS（5 维，见 §5）≥ 3.5/5；plus 档对 flash 档 MOS ≥ +0.4；9 项客观指标 --check 通过；审核/4xx 一次通过率 ≥ 85%；记录 元/条定稿成本（预期 ≈ 4.75 元：1.25 草稿 + 3.50 定稿）。
**风险与回退**：plus 收益不显著 → 保持 flash + 提示词工程，省 2.8× 成本；首尾帧/1080P 不可用 → 记录备忘，循环锁定改由 V3 本地补帧+接缝处理承担。

### V3 素材与渲染引擎升级（第 4-7 周，本地算力为主）

> **◐ 第一批已实施（2026-10-03 深夜）**：
> - **`artgen/postfx.py` 后期链模块**：`encode_mp4`（RGBA 帧序列 → libx264 CRF16 high profile +faststart，透明帧白底合成，奇数尺寸自动补偶；imageio ffmpeg 插件不支持 BytesIO，走临时文件中转）+ `interpolate_mci`（ffmpeg minterpolate MCI/AOBMC 运动补偿补帧）。
> - **程序化链 mp4 出口**：`compose_animation`/`create_animation` 交付 GIF 之外同步产出 mp4（`_persist` 落 `{id}.mp4` + `urls.video`/`video_spec`），骨骼/源图/序列帧动画从此与 i2v 链同规格。批次条带链与 i2v 链显式 `with_mp4=False`（条带不需要、i2v 直通裁剪画质更高不重复编码）。前端零改动（V1 的 `<video>` 优先逻辑自动生效）。
> - **补帧实测后不设默认**：合成卡通内容 12→24fps 收益为负（时序一致性 0.980→0.972——minterpolate 在平坦色块上引入插值噪声），真 i2v 视频 30→60fps 需 75s/条不可用。`interpolate_mci` 保留为 opt-in，实测数据记录在案；真正的补帧升级位留给 RIFE（接口已按 mp4 in/out 设计好）。
> - **边缘质量指标**：`sourceanim.edge_smoothness`（边界过渡像素占比，硬边 0.0/羽化 1.0）与 `edge_halo_px`（外溢 halo 像素数）建立度量基线（现行 GaussianBlur：smoothness 1.0 / halo 0）。
> - **教训**：距离分级羽化（erosion 分级 ramp）实测在 band=2 时是**色带阶梯**，劣于 blur 的连续钟形——已回滚保留 blur。matting 真升级（AI matting / 分数距离变换）留待下批用指标驱动做对。
> - 回归：动画 **132/132**（+9 项 postfx/边缘契约）、run_tests 39/39、视频管线契约 28/28、video_quality 门 PASS。
>
> **下批待做（按风险排序）**：① ~~riganim 网格变形 + 发/裙次级运动~~ **✅ 已完成（2026-10-03 深夜，见下）**；② ~~side 三视图真绑定~~ **✅ 已完成**；③ AI matting 边缘精修（以 edge_smoothness/halo 指标验收）；④ ~~前端 mp4 白底视觉适配~~ **✅ 已完成**（postfx 默认底色改暖纸 #f1efe9，与预览面板同色无缝融合）。
>
> **✅ 网格变形（膝/肘皮肤化）实施明细（V3 收官）**：`artgen/riganim.py` 新增 `_mesh_canvas`/`_mesh_union`——小腿/前臂顶部过渡带（SKIN_BAND_SHIN=28px / SKIN_BAND_FOREARM=16px）内，子层世界角从**父段角**（跨关节连续）平滑插值到**完整屈曲角**（=旧刚体角，姿态端点不变），带外刚体；过渡带细分为 6 条重叠横带逐带旋转，按 **max-alpha 独占所有权**合成（v5/v6 分区哲学在子层内的复用，杜绝半透明双绘）。近/远角差 <0.5° 时逐字节退化为刚体路径（零屈曲零开销）。
> **A/B 开关（三层）**：`animate_rigged(skin=)` 显式参数 > pose_config 保留键 `skin` > 模块常量 `RIGANIM_SKIN_DEFAULT`（改回 "rigid" 一键还原 v5/v6 行为）；API 字段 `deform`、前端「网格变形（膝/肘皮肤化）」开关（骨骼模式）、meta 落 `skin_mode`。
> **测试（动画回归 135→141）**：幽灵/分体不变量在 mesh 默认下全过；新增 6 项——零屈曲退化逐字节等价、脚部区域 IoU≥0.85（姿态端点保持）、膝带 A/B 差异>1000 alpha（非空转）、config 键与显式参数等价、低屈曲 idle mesh≈rigid≥0.97、默认常量校验。
> **A/B 样片**：`studio/backend/generated/side_binding_preview/ab_walk_{mesh,rigid}.{gif,mp4}` + `ab_knee_closeup.png`（最大屈曲帧膝部 2× 特写并排，左 mesh 右 rigid）。
> **次级运动（发/裙摆动）**：需要发/裙独立图层（AI 分层）才有真物理，本轮未做——躯干剪切式近似有"假物理"风险，留待与用户在浏览器里迭代。
>
> **✅ side 真绑定实施明细（2026-10-03 深夜）**：`AnimationService._asset_view_render(asset, view)` 解析 `design_views.<view>` 本地文件（只认本地，远端失效一律回退正面原画、绝不阻塞）；`create()` 的骨骼/资产两分支在 `view=="side"` 时优先用 side 真源图，meta 打 `view_bound: "side"` 标记。侧视骨骼动画从"正视原画凑数"变成**真侧视绑定**（骨架检测、分区、步态曲线直接作用在侧视原画上）。对比样片：`studio/backend/generated/side_binding_preview/knight_walk_{SIDE,FRONT}.{gif,mp4}`。测试：动画回归 3 项新检查（绑定标记/出片/正面不误标），总 **135/135**。

**目标**：补齐素材端与程序化动画端的"专业感"来源：高分辨率素材、真侧视、网格变形、次级运动、24fps。

任务：
1. **源图 2K 化**：文生图 size 升档实测（service.py:401 现为 1024×1024）；1024 源图走 **Real-ESRGAN x2** 本地超分（BSD-3 许可，ncnn/vulkan 版可 CPU）。
2. **matting 精修**：洪泛容差 48 + MaxFilter(7) 羽化 → trimap + alpha matting（或按边缘曲率自适应羽化）；新增边缘质量指标（见 §5.1）驱动验收。
3. **side 视图入动画管线**：design_views.side（generate_turnaround 产物）注册为侧视 rig 源，侧视 walk/run 用真侧视绑定替代镜像正视（替换 character2d.py:352-357 镜像路径在 riganim 链的依赖）。
4. **riganim 网格变形**：分区刚体 → 分区网格 + 关节处共享控制点（肩/髋/膝带连续性），躯干/四肢皮肤拉伸；保留现有羽化带作为回退开关。
5. **次级运动层**：发梢/裙摆/披风按 `sin` 相位差摆动（跟随 bob/sway 派生，幅度按 `_motion_scales` 体型自适应），先做 walk/run 两个动作。
6. **RIFE 补帧**：程序化 12fps → RIFE 插帧至 24fps（rife-ncnn-vulkan；与 ffmpeg `minterpolate` 对比选优），i2v 源视频保持原生 24fps 不动。
7. **后期链模块**（`artgen/postfx.py` 或 backend 服务）：unsharp/cas 锐化 + 轻降噪 + 统一编码封装（CRF16 H.264 / dither GIF 双出口）。

**资源**：1 人 × 3-4 周；可选 NVIDIA GPU（≥6GB 加速超分/补帧；CPU 亦可，分钟级/条）；全部开源组件许可友好（Real-ESRGAN BSD-3、RIFE MIT）。
**评估标准**：动画回归 112/112 + 新增契约测试；边缘质量指标较现状提升 ≥ 30%；程序化链 24fps 输出 MOS ≥ 3.5/5；网格变形与刚体模式 A/B 盲评胜率 ≥ 70%；任一回退开关可一键切回现状。
**风险与回退**：网格变形引入新撕裂 → 分区独占所有权与立柱机制（v5/v6 修复成果）保持不变，网格仅在带内变形；超分放大毛边 → 超分前先精修 alpha；RIFE 对像素风不友好 → 像素素材跳过补帧（最近邻本来就按低帧率设计）。

### V4 评估体系固化（第 8 周起，持续）

> **◐ 首项已落地（2026-10-03 深夜）**：`tests/run_tests.py` 新增 `video-quality` 组（40 项）——合成管线跑 `video_quality.run_pipeline` 并对照 `video_baseline.json` 全量硬门（含 delivery_size / source_fps / mp4_width / mp4_fps / mp4_duration 五项交付规格门），任一回归即 FAIL；基线缺 mp4 规格字段时显式报错提示重录。MOS 月度复盘与 L4 扩展待做。
>
> **✅ MOS 盲评工具链就绪（2026-10-03 深夜）**：`benchmark/mos_kit.py`——`python benchmark/mos_kit.py` 生成盲评包（27 个随机代号样片：5 i2v 变体 × 5 动作 + mesh/rigid A/B，代号对照在 `mos_kit/key.json` 评分前勿看）；浏览器打开 `benchmark/mos_kit/评分.html` 逐条按 5 维打分 → 导出 JSON 发回；`python benchmark/mos_kit.py --decode 评分.json` 解码出对照表与均值，落 `mos_kit/mos_decoded_*.json` 归档。

**目标**：质量不靠人眼记忆，靠门禁与复盘。

---

## 附：三项收尾工作的落地记录（2026-10-03 深夜）

1. **MOS 盲评**：工具链已就绪（见 V4 状态块）。**首轮评分已完成（2026-10-04，n=1，样片 25/27——mesh/rigid 两条因页面 GIF 渲染 bug 未评成，已修复待补评）**。原始答案 `mos_kit/answers_20261004.json`，解码 `mos_kit/mos_decoded_20261004_094911.json`。

   **结果与结论**（总均值：清晰度 4.00 / 流畅度 3.88 / 一致性 3.64 / 真实感 3.60 / 整体 3.64）：
   - **attack 是唯一重灾区（动作均值 2.6 vs 非 attack ≈3.9）**：v2 运动学 attack 句（强调 "fast committed strike"+髋肩旋转）让 flash_v2 / flash_v2_1080p / plus_v2 三组的一致性+真实感全线崩盘（整体 2/2/2），而 v1 温和措辞拿 4——攻击性描述诱发 i2v 大幅运动伪影，与模型档位无关。**已行动：attack 词表回滚 v1 措辞**，其余四动作保留 v2（v2 walk 是全场唯一 5 分，确认有效）。
   - 变体整体均分：flash_v1 4.00 > flash_v2 3.80 = ext 3.80 > plus_v2 3.40 > 1080p 3.20——被 attack 崩盘拉偏；attack 修复后 plus 定稿档需复测（客观 motion_cv 最优但本轮主观未赢，n=1 且受 attack 拖累）。
   - 局限：单评分者、单角色资产；下轮起积累多人多角色样本。
2. **AI matting 精修（路线 A·白底 alpha 反解）✅ 已实施**：`sourceanim.refine_edge_alpha(image, mask, bg, band)`——边界带内按合成方程 `C = F·α + bg·(1−α)` 反解真 alpha 与前景色（前景色从 solid 内部逐格传播），同时消除旧路径"羽化 alpha 保留旧底色"的 t² 底色泄漏；`|F−bg| < 30` 的歧义像素（白衣贴白底）保留原值不解。已接入 riganim 非透明路径（失败回退旧 putalpha），试玩缓存升 **v7**。真值 fixture 实测：**边缘合成色差 63.9 → 11.6（5.5× 改善）**，内部 alpha 不侵蚀，动画回归 **144/144**（+3 项 matting 检查）。
3. **发/裙次级运动·分层试验 ✅ 打通**：qwen-image-edit "头发变纯白" + 原图差分（`|diff|>90` + 中值滤波清理）提取发层，骑士实测覆盖率 8.12% 合理；发根锚点 = 发 mask 底部 12% 行质心；摆动 = 相位滞后 0.12 的 sin 曲线（±7°，跟随 bob/sway/lean/tilt 的躯干变换后叠加），演示样片 `generated/side_binding_preview/hair_swing_demo.gif` + 分层产物 `hair_layer.png`。试验花费 0.6 元（两次编辑）。**生产接线待用户看过演示后进行**：分层产物挂 asset meta（`layers.hair.file`）、animate_rigged 接 overlays 参数、幅度/滞后暴露为 pose_config 键。

任务：
1. `video_quality --check`（含 i2v 真实基线）进 tests/run_tests.py（基线视频缺失时 SKIP，沿用 L5 惯例）。
2. release 门 L4 增加 video 维度断言（独立阈值，**不动 cf_score 权重** benchmark/score.py:15-20）。
3. MOS 人评月度复盘，结果归档 docs/quality-scores.md（沿用既有惯例）。
4. QA 复核工作台：自动检测报告 + 人工通过/重生成按钮（motion_qa 检测器随 V1-V3 指标逐步落地）。
5. 半年度模型选型评估制度：以基准集重跑外部候选（见 §5.3）。

**评估标准**：门禁在 CI/发布流程中真实拦截 ≥ 1 次回归；月度复盘连续执行 ≥ 2 期。

---

## 5. 质量检测方法与对比评估指标

### 5.1 客观指标（复用 + 新增）

已有（benchmark/video_quality.py，TOLERANCES 于 :214-221）：`sharpness`（Laplacian std）、`temporal_consistency`（similarity_rgba）、`color_fidelity`（RGB 直方图余弦）、`dynamic_range_spread`、`motion_total / motion_mean / motion_cv`、`loop_seconds`、`gif_bytes`。

新增：

| 指标 | 计算方法 | 阈值示例 | 捕捉什么 |
|---|---|---|---|
| `delivery_spec` | ffprobe 读 width/height/avg_frame_rate/bit_rate | 硬断言 ≥720p/24fps | 交付规格回归 |
| `ghost_energy` | 帧差图的 Laplacian 高频能量占比 | ≤ 基线 ×1.05 | 残影/鬼影 |
| `flicker` | 相邻帧全图相关性方差 | ≤ 0.05 | 闪烁（调色板漂移、LZW 类） |
| `edge_quality` | alpha 通道边缘梯度熵 / 锯齿度 | 较现状 +30% | 抠图毛边 |
| `identity_drift`（可选） | 首帧 vs 尾帧 CLIP 嵌入余弦 | ≥ 0.90 | i2v 角色漂移 |

### 5.2 主观评测（MOS）

- **5 维 × 5 分制**：清晰度、流畅度、一致性（角色/循环）、真实感（运动物理）、整体印象。
- **盲评协议**：基准集 10 条 × 待比方案（如 flash vs plus vs 外部标杆），文件名随机化、来源隐藏、多人打分取均值（≥2 人）。
- 基线先行：V2 第一步先测当前 flash 档 MOS 作为基线，此后所有改动对基线报告增量。

### 5.3 对标"专业 AIGC"的方法

1. **外部标杆锚点**：同 prompt + 同首帧图投递 2-3 个业界标杆模型（Kling / 海螺 / Vidu / Seedance，用其免费额度或样片），取回样片混入盲评集——我们的相对得分 ≥ 标杆的 90% 即"接近专业水平"。
2. **FVD 不引入**（算力/样本量门槛高）；时序一致性用 similarity_rgba + flicker + CLIP 组合替代，够用且免费。
3. onetake verify_promo oracle（cadence/rest/burst/continuity/framing，verify_promo.py:65-105）继续作为宣传片链的验收腿，不重复建设。

### 5.4 成本指标

- 元/条定稿（分档记录）、一次通过率（免重生成）、缓存命中率（视频/润色/分割三层）。
- 额度仪表已有（routes.py:548-554），增加按"动作定稿"维度的聚合视图。

### 5.5 门禁接入点

- **日常**：run_tests.py @check（合成视频基线，已有 39 项体系内扩展）。
- **基准变更**：改采样/编码参数必须重录基线（service.py:216-220 既有指纹约定，PLAYTEST_CACHE_VERSION 同理）。
- **发布**：release L4 video 维度断言。
- **月度**：MOS 复盘 + 指标趋势归档。

---

## 6. 总验收标准（北极星）

| 维度 | 现状 | V1 后 | V2 后 | V3 后 |
|---|---|---|---|---|
| 交付分辨率 | 384×384 GIF | **1280×720 mp4** + 384 GIF 兼容 | 同左（或 1080P，视实测） | mp4 + 2K 源素材 |
| 交付帧率 | 12fps | **24fps（mp4）** | 24fps | 24fps（程序化链也 24） |
| 有效循环时长 | 2.5s | ≥2.5s（mp4 同窗） | ≥2.5s | ≥2.5s |
| 色彩 | 255 色无抖动、逐帧板 | 全局板 + 抖动 GIF / mp4 真彩 | 同左 | 同左 |
| 客观指标 | video_baseline.json（384px 口径） | --check 不降级 + mp4 新基线 | i2v_baseline.json 成立 | 边缘指标 +30% |
| MOS（5 维均值） | 未测（V2 先建基线） | — | ≥3.5/5 | ≥4.0/5 |
| 对标外部标杆 | — | — | 首次采样 | 相对分 ≥90% |
| 成本 | 1.25 元/条 | 0 新增 | 4.75 元/条定稿（草稿+定稿） | 本地算力为主 |

---

## 7. 风险、依赖与备注

1. **DashScope 能力边界未实测**（size/duration/首尾帧/audio）——V2 第一项就是实测，绝不按猜测升级参数。
2. **内存契约**：帧数×尺寸翻倍影响条带与缓存（routes.py:1691-1702 的 288px 上限、90MB 口径）——V1 任务 3 强制重验；试玩舞台本轮**不动**（v6 缓存链刚稳定）。
3. **GIF 逐帧调色板**（gif.py:194-197）是隐性闪烁源，V1 修复但需 A/B 验证 disposal=2 + dither 组合。
4. **PolyForm NC**：onetake 渲染管线商用受限的既有结论不变（docs/onetake-integration-plan.md:268-274），本路线图不加重依赖。
5. **安全**：model_settings.json 含明文 API Key 且已入库——与既有"key 轮换"待办合并处理，建议迁 env 并轮换。
6. **记录不一致**：历史笔记中的 motion_qa.py/equipment.py 质检系统在当前工作区零命中（实测 PLAYTEST_CACHE_VERSION=6），本文按当前代码为准，QA 检测器按"新建"纳入 V4 任务 4。

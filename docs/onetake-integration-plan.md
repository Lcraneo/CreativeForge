# onetake 引入可行性评估与集成方案（Showcase / 发布动效层）

> **状态（2026-10-02）：已实施落地。** P0–P4 全部完成：`adapters/onetake/` 四模块 + `cf_showcase.html`
> 模板 + `studio/backend/showcase_service/` + 三条 `/api/showcase` 路由 + capability
> `motion_video_generation`（plan_service 目录 + legacy registry 双注册）+ 前端 ShowcaseStudio
> （lazy 路由 /showcase）+ 契约测试 `tests/test_onetake_pipeline.py`（33 项）+ 前端 vitest 27 项。
> 实机验收：骑士资产 ast61935 全链路出片，oracle `verify_promo` 五腿 **PASS**
> （cadence CV 0.81 / rest 56% 静帧+1.92s 静止 / continuity 1.00 / shutter 180° / framing 0 违规）。
> 运行前提：演示机 `pip install playwright static-ffmpeg` + `python -m playwright install chromium`。

> 评估对象：`D:\onetake-main.zip`（onetake-main，lineage `otk-7f3e1c`，作者 Patrick / github.com/feitangyuan）
> 需求来源：`前端 UI创意点.md`——把 onetake 作为「AI 生成资产后的展示/发布动效层」接入 CreativeForge，
> 定位为 External Creative Capability（与 Holonic / Windup 并列），不进入自研核心（PReCon / FAlign / GImport）。
> 评估日期：2026-10-02 · 基准：studio/frontend 与 studio/backend 当前 master。

---

## 0. 结论（TL;DR）

**可行，且与 MD 的定位高度契合——但必须先纠正一个范畴判断：onetake 不是"前端 UI 组件库/框架"。**

对 `onetake-main.zip` 的实测结论：它是一个 **AI Agent Skill 包**（`SKILL.md` 八步创作协议）+ 一套
**"一镜到底"动效短片的创作范式**（单个 HTML 合成、一切值都是时间 `t` 的纯函数、`__seek(t)` 确定性寻帧）
+ 一个 **零依赖 JS 动效库**（`lib/motion.js` → `window.OM`，39 个动效原语）+ 一条 **Python 离线渲染管线**
（Playwright 逐帧截图 → mp4，真实快门运动模糊，1080p30 草稿 / 4K60 终稿）+ 一个 **自动验收 oracle**
（`verify_promo.py`：节奏/衔接/曲线/构图/爆发五腿）。

因此本方案对需求中各节的实际回答是：

| 需求条目 | 实际答案 |
|---|---|
| UI 组件库选型与版本确认 | **不引入任何新 UI 组件库**（onetake 里不存在组件库）。Showcase Studio 页面完全复用项目现有 `components/ui.tsx` 体系与暖纸编辑风令牌；引入物是 vendored 静态资产三件套（motion.js 33KB / ui_kit.js 8KB / comp.html 模板 22KB）+ 渲染脚本，版本锁定 `lineage otk-7f3e1c` 快照 |
| 样式系统适配 | comp 内部走 onetake 的 look 八色令牌系统（`looks/`，其中 `paper` look 的 `#f8f8f6` 纸底与本项目暖纸编辑风天然同源），用 `look.py from-shot` 从骑士原画/产品截图一次性烘焙 `cf-paper` 专属 look；页面 UI 走项目令牌，两套令牌互不渗透 |
| 组件按需加载 | 路由级 lazy（项目已有模式）；`motion.js` 只在被隔离的预览 iframe 内执行，**不进主 bundle**；成片是 mp4 URL 流式播放 |
| 主题定制 | look.json 版本化资产 + `look.py apply` 产物随 comp 生成；深色场景可用 `dusk` look 或截图反色烘焙 |
| 状态管理集成 | 前端零新增 store：生成任务走 react-query 轮询（对齐 action-batch 的 2.5s refetchInterval 先例），资产选择复用 zustand `assetStore`；后端任务沿用 `AnimationService._ACTION_BATCHES` + TTL 剪枝的线程批次先例 |
| 单测与 E2E | vitest 组件 smoke + boundaries 断言（third_party 只可被 adapter/api 层触及）+ 后端 mapper 纯函数单测 + comp 契约测试（`__seek/__meta/__events` 存在、渲染路径无 `Math.random`）；**onetake 自带 verify_promo 作为视频产物的验收 E2E**；顺带用渲染所需的 Playwright 补一条最小前端冒烟（项目当前没有浏览器 E2E 框架） |

**最大风险（一票否决级）**：许可证为 **PolyForm Noncommercial 1.0.0**——非商业使用免费。比赛 / 学术演示 /
作品集属非商业，可直接用；一旦项目商业化（收费、商业客户、闭源商用发行）必须获得授权或整体替换。
替换成本已被架构隔离到最小：业务只依赖 `adapters/onetake` 的输出（mp4 + 预览 HTML），motion.js 的 f(t)
原语可由 framer-motion（项目已有 ^11.11.0）+ 自研曲线层等价重写，迁移面仅 comp 模板与 patches。

---

## 1. onetake 是什么（实测事实清单）

### 1.1 体积与构成

| 部分 | 文件 | 体积 | 说明 |
|---|---|---|---|
| 动效库 | `lib/motion.js` | 33KB | 39 个原语：curves（t80 标注的缓动族/spring/spline/rng）· enter（wordRise/letterDrop/popIn/typeOn/tick/flyThrough）· carry（morphRect/iris/zoomThrough/gather/seal/staccato）· contact（impact/press/cursor/squash + 4 个 240Hz 预仿真 sim）· camera（camera/whip/shake/drift/lattice/project）· fluid。**纯函数、不碰 DOM、无状态、渲染路径禁 Math.random（OM.rng(seed)）**——同一参数永远同一结果，这是确定性逐帧渲染的根基 |
| 重建 UI 助手 | `lib/ui_kit.js` | 8KB | 把产品 UI 在合成平面内重建（stage/domLocal/rectCache/高亮/glowRing/timeWarp 双语言对时/字幕） |
| 合成模板 | `templates/comp.html` | 22KB | 1920×1080 定长舞台骨架；契约：`window.__seek(t)→Promise`、`__ready`、`__meta{dur,fps,w,h}`，可选 `__motion(t0,t1)`（运动模糊采样量）、`__events()`（音效事件）、`__meta.inFrame`（构图守卫）；查询参数 `?play`（实时循环预览）/`?t=6.4&hud`（钉帧） |
| 渲染管线 | `scripts/*.py` ×11 | ~112KB | render.py（快门运动模糊=开角内多次 seek 线性光平均、`--workers` 并行浏览器）、stills.py、probe.py、verify_promo.py（oracle）、analyze_ref.py、record_footage.py（Playwright 实录）、look.py（八色 look 应用/从截图烘焙/字体子集内联）、sfx_palette.py、vo_tools.py（TTS+字幕）、frame_diff.py、gallery.py；另有 node 版 test_motion.js |
| 视觉主题 | `looks/looks.json` + fonts | 5KB + 字体 | 八色令牌（ground/deep/card/line/mute/ink/accent/accent2）×三字体；六套从过审影片实测的 look（paper/dusk/tabletop/ultramarine/riso/ember），OFL 许可字体 |
| 其他 | cases/gallery/references/assets | ~70MB | 案例成片、动效图鉴、方法论文档——**仅需精选入库，非集成依赖** |

### 1.2 依赖与本地环境实测（Windows，python 3.11.9 / node C:\Tool）

| 依赖 | 用途 | 本机状态 |
|---|---|---|
| playwright(chromium) | 逐帧截图渲染、实录、前端冒烟 | **未安装**（一次性 `pip install playwright` + `playwright install chromium`） |
| numpy / scipy / Pillow | 管线数值/图像 | ✅ 已装 |
| opencv-python | 仅 reference 解构的运动线分析 | 未装（可选，集成不需要） |
| fonttools + brotli | look.py 字体子集烘焙 | 未装（一次性烘焙时安装） |
| ffmpeg / ffprobe | 合成 mp4 | ✅ 经 imageio-ffmpeg 自带二进制（需把其 binary 目录注入 PATH 或软链） |
| node | motion.js 单测 | ✅ |

### 1.3 创作协议要点（决定集成形态）

SKILL.md 规定八步流程（解构参考 → 三概念 → beat sheet → 素材 → 合成 → 渲染 → 声音 → oracle 验收），
并有一组「每条都砍过一次片子」的硬规则：不默认模板叙事、beat 必须 carry 不许替换、镜长差 ≥4×、
禁粒子彩带、静帧占三分之一、手（因）必须可见、确定性寻帧……**这些是创作自由度，不是运行时 API**。
产品化集成的关键决策因此是：*把创作自由度收敛为一个受管的固定叙事模板，参数由数据注入*
（见 §3.3），运行时零人工创作。

---

## 2. 五维评估

### 2.1 技术兼容性 —— **高（唯一红灯是许可证）**

- **前端栈**：React 18.3.1 + Vite 5.4 + TS 5.6 + Tailwind 4（@tailwindcss/vite）+ zustand 5 + react-query 5.59 + Konva 9.3 + three 0.169/R3F 8.17 + framer-motion 11.11。onetake 的 JS 件零框架依赖（`<script>` → `window.OM`，node 可 require），合成是**自包含 HTML**，以 iframe 隔离承载——与主应用唯一的接触面是一个 URL。无样式泄漏、无全局污染、无依赖冲突。Konva/R3F/Framer 各司其职互不重叠（comp 在 iframe 里自成体系，不需要 React 化）。
- **后端栈**：FastAPI。三项既有设施原生贴合——① `adapters/` 端口模式（windup 已有 `map_animation` 等先例，MD 提议的 `adapters/onetake/{asset,scene,timeline}_mapper + render_client` 完全同构）；② `agent/capability/capability_registry.py` 的 `register()` 按 name 供 Planner 选择（MD 的 `motion_video_generation` 能力直接挂入）；③ `AnimationService._ACTION_BATCHES` 内存批次 + TTL 剪枝 + 前端轮询的异步任务先例（渲染一个 15s 片需要分钟级后台任务，照抄该模式即可）。
- **CreativeAsset 契约**：MD 要求新增 `presentation` 字段。落点三处同步——`backend/app/models/asset.py`（运行时 dict 语义）、`adapters/creative_asset_adapter.py`（AssetAdapter 端口 import/export 映射）、`packages/creative-core/models/creative_asset.go`（Go 侧接口注释性同步）；studio 运行时资产本就是宽松 dict，向后兼容（缺字段 = 无展示产物）。
- **渲染管线环境**：本机 python3.11 + numpy/scipy/PIL 已备，缺 playwright/chromium 与 ffmpeg PATH，均一次性解决（§4 P0）。Windows 实测可行（render.py 用多进程起 Chromium 截图，无 POSIX 专属调用；`_reap_file` 式 Windows 文件竞态兜底经验项目里已有）。
- **许可证兼容性**：PolyForm NC 1.0.0 与比赛用途兼容；与任何商业化不兼容（见 §0）。

### 2.2 性能影响 —— **前端≈0，后端为离线批任务**

- 主 bundle 增量：**0KB**（motion.js/ui_kit.js 只进 iframe 文档；页面代码 lazy 切分；成片 mp4 走静态文件流）。首屏、试玩舞台、动画工作台等现有路径零影响。
- Showcase 页运行时成本：一个 `<video>`（成片）或一个 `?play` iframe（实时预览，comp 每帧 <1ms 绘制，SKILL 实测）——挂载由用户点击触发，不做自动播放。
- 后端渲染预算：15s 草稿 1080p30 在 8 workers 下参考耗时 ~2 分钟（上游实测 103s/2480 帧）；并发上限沿用批次线程模式（`max_workers` 封顶、TTL 剪枝），与本机已有的 i2v 轮询任务错峰（渲染是纯本地 CPU，不烧额度）。
- 磁盘：mp4/look.js/comp 产物落 `generated/`（沿用 GENERATED_DIR 治理与 history 关联），4K60 终稿只在验收后按需渲染。

### 2.3 学习曲线 —— **前端 ≈0；创作成本被模板化收敛**

- 页面开发者：新页面 = 现有 AnimationStudio/PlaytestStage 同款模式（react-query 轮询 + ui.tsx 组件），无新框架。
- 合成作者（一次性）：SKILL 八步协议 + carry/rhythm 硬规则需要真实学习；本方案**不要求运行时创作**——P1 阶段把 CreativeForge 的固定叙事（AI 生成 → 像素重建 → 动作展开 → Cocos 运行 → Logo）做成受管 comp 模板，之后每次生成只是参数注入（资产名/调色板/原画帧/条带帧/导出截图），作者成本仅发生在改模板时。
- 后端集成者：adapter + capability 先例齐备，属照猫画虎。

### 2.4 开发效率提升 —— **显著，且是自研不划算的那类**

直接继承的上游沉淀：39 个过审影片打磨的动效原语（含 4 个预仿真物理 sim 与跟焦运镜）、真实快门运动模糊渲染器（自研需反复调采样）、**自动验收 oracle**（把「像不像 PPT」变成可测的五腿断言——这正是本仓库质量门文化的东西）、八色 look 主题系统、双语言 time-warp。自研等价物估算数周至数月。对比赛叙事的增益（MD 原话）：「AI 创意 → 游戏资产 → 游戏运行 → 产品宣传视频」闭环，Demo 观感提升明确。

### 2.5 长期维护成本 —— **中低，但有两条硬约束**

- 上游**没有 npm 包、没有版本发布**（GitHub 快照式 skill）→ 以 vendored 快照入库，README 记录 lineage `otk-7f3e1c` 与上游 URL；本地修改只允许走 `third_party/onetake/patches/`（升级时可重放），禁止直接改 vendored 文件。
- 许可边界：vendored LICENSE 必须随行；关于页/TechnologyCenter 标注「OneTake — External Creative Capability, PolyForm NC」；商业化触发时按 §0 替换预案执行。
- 运维面：playwright/chromium 随浏览器大版本升级需偶发更新；字体子集在改 look 时重烘焙；**CI 不跑渲染**（CI 只跑 mapper 单测 + comp 契约测试，渲染是本机/演示机的离线动作），保住现有门禁时长。

---

## 3. 集成方案

### 3.1 架构（对齐 MD 的图）

```
CreativeAgent ──> CapabilityRegistry.register(motion_video_generation)
                        │
                        ▼
             adapters/onetake/OneTakeAdapter
             ├── asset_mapper.py      CreativeAsset → 素材清单（原画/条带帧/GIF/导出截图/名字/调色板）
             ├── scene_mapper.py      presentation.storyboard → comp 场景参数（beat/入场/离开）
             ├── timeline_mapper.py   → 节拍表（镜长差≥4×、carry 边界、inFrame 清单）+ comp.html 注入
             └── render_client.py     playwright+ffmpeg 渲染 → generated/showcase/{id}.mp4 + poster
                        │
                        ▼
        POST /api/showcase {asset_id, style} → {job_id}；GET /api/showcase/{job_id} 轮询
                        │
                        ▼
   前端 ShowcaseStudio（lazy 路由）：Asset Timeline → [Generate OneTake Demo]
   → 徽章轮询 → <video> 自动播放 + ?play iframe 实时预览 + 历史列表
```

### 3.2 选型与版本锁定（对需求「UI 组件库选型与版本确认」的正式回答）

1. **不引入第三方 UI 组件库**。MD 的页面需求（标题区/时间线/按钮/徽章/空态/卡片）在 `components/ui.tsx`（Button/Card/Badge/PageHeader/EmptyState/Toast）内全部有解；引入 shadcn/radix 之类反而破坏暖纸统一性、顶到体积预算。
2. **vendored 清单**（其余 ~70MB 案例资产不入库）：
   ```
   third_party/onetake/
   ├── lib/motion.js            # 33KB → window.OM
   ├── lib/ui_kit.js            # 8KB（product-demo 路线用）
   ├── templates/comp.html      # 22KB 骨架 → adapters/onetake 的生成底版
   ├── looks/looks.json         # 八色令牌 + 字体表
   ├── looks/fonts/             # 精选 3-4 个 OFL 面（paper/dusk 所需）+ 许可
   ├── scripts/{render,stills,probe,verify_promo,look}.py   # 渲染与验收最小集
   ├── scripts/sfx_palette.py   # 草稿音效（可选）
   ├── SKILL.md + references/{composition,motion-library,rhythm}.md   # 作者文档
   ├── LICENSE                  # PolyForm NC 1.0.0 原文，随行
   └── README.md                # 上游 URL + lineage otk-7f3e1c + 快照日期 + 补丁规则
   ```
3. **版本策略**：快照即版本；升级 = 重新快照 + 重放 patches；`lineage` 字样写入 comp 头注释（模板已有该行）。

### 3.3 创作模板（功能需求的落点）

一个受管模板 `adapters/onetake/template/cf_showcase.html`（基于 comp.html 底版改写），叙事固定为 MD 的闭环：

```
beat1 一句话意图（ kinetic type，copy = asset.identity.prompt 摘要 ）
beat2 原画定格 → 像素重建（PReCon 产物原画 vs 像素帧 hard-cut 对撞，carry=同一主体缩放）
beat3 动作展开（试玩区条带帧序列 + 手指沿攻击轨迹，carry=角色从帧格中放大走出）
beat4 Cocos/导出预览窗（export 包截图置入浏览器窗卡，carry=窗卡 zoomThrough 成场景）
beat5 Logo/wordmark 收束（staccato 命中 ×3 → 黑场 wordmark）
```

参数注入契约 = `presentation`：

```json
{
  "presentation": {
    "type": "launch_video", "style": "one_take", "duration": 15,
    "camera": "continuous", "look": "cf-paper",
    "assets": { "art": "…png", "strips": "attack", "cocos_shot": "…png" },
    "copy": { "hook": "一句话", "beats": ["像素重建","动作就绪","进入 Cocos"], "wordmark": "CreativeForge" },
    "render_output": { "draft": "generated/showcase/{id}.mp4", "poster": "…png" }
  }
}
```

硬规则内建在模板里：`OM.rng(seed)` 固定种子、`__meta.inFrame` 声明主体不裁切、`__motion` 供快门采样、
镜长由 timeline_mapper 按 ≥4× 差生成、每个 beat 的 carry 边界在 scene_mapper 显式声明（无 carry 不成 beat）。

### 3.4 后端实现要点

- `adapters/onetake/` 四模块为纯函数优先（mapper 可离线单测）；`render_client.py` 封装 playwright 调用：
  `subprocess` 起 `python -m playwright`？——直接进程内 `sync_playwright()`（渲染在守护线程批次里），
  ffmpeg 调用注入 `imageio_ffmpeg.get_ffmpeg_exe()` 路径，失败分类复用 `classify_error` 五类
  （渲染失败归 fatal、环境缺失归 fatal + 中文可读提示「演示机未安装 playwright」）。
- 任务管理：`ShowcaseService`（`studio/backend/showcase_service/`）仿 `_ACTION_BATCHES`：
  内存批次 + TTL 3600s + `_prune` + 轮询快照；产物持久化进 `generated/showcase/` 并写 meta json
  （含 presentation 回填 render_output——与 `_persist` 后重写的既有纪律一致）。
- 路由：`POST /api/showcase`（202 + job_id）、`GET /api/showcase/{job_id}`（快照）、
  `GET /api/showcase/{job_id}/video.mp4|poster.png`（文件伺服，走 `path()` 同款目录穿越防护）。
- capability：`motion_video_generation` 注册进 default registry（`agent/capability/capability_registry.py`
  的 default 构造处），input_schema = asset_id + style；Agent 侧故事（MD 的「一句话 → 15 秒片」）由
  Planner 选择该能力完成编排。
- 素材缺失语义：**不做静默兜底**（沿用「宁可报错不给模板」纪律）——缺原画/缺条带帧时 409 + 可读中文
  （「该资产还没有动作条带，先在试玩区/工作台生成」）。

### 3.5 前端实现要点

- `studio/frontend/src/pages/ShowcaseStudio.tsx`（路由 lazy 注册进 App.tsx，nav 入口「Showcase」）。
  结构：PageHeader + 资产选择（复用历史资产选择器模式）+ Asset Timeline 卡（五 beat 徽章连线，
  数据来自 GET `/api/showcase/preview?asset_id`（mapper 的 dry-run 输出，不渲染））+
  Generate 按钮（loading/failed 徽章复用 `ERROR_KIND_LABEL` 模式）+ 完成后 `<video controls autoPlay loop poster>`。
- 实时预览（可选开关）：`<iframe src="{comp_url}?play" sandbox="allow-scripts">`，16:9 容器
  `aspect-ratio` + `transform: scale()` 适配容器宽（comp 固定 1920×1080）。iframe `sandbox` 无
  `allow-same-origin` 即可（comp 无网络请求，字体已内联）。
- 状态：`useQuery(["showcase-job", jobId], refetchInterval: running?2500:false)`；资产选择读现有
  `assetStore`；本页不新增 zustand store。

### 3.6 测试适配

- **vitest**（现有 24 例之上新增）：
  1. ShowcaseStudio smoke：mock api → 渲染 → 显示五 beat 时间线与按钮；job 完成后出现 video；
  2. boundaries.test.ts 增一条：业务代码不得直接 import `third_party/onetake/**`（只能经后端 API 或
     `public/showcase/` 静态产物）；
  3. presentation 契约：缺字段资产的时间线 dry-run 返回安全默认且不抛错。
- **后端 pytest**（进 tests/run_tests.py 计数）：
  1. asset_mapper：骑士形态资产 → 素材清单字段齐全（原画/条带帧数/导出截图）；
  2. timeline_mapper：给定 presentation → 节拍表满足镜长差 ≥4×、carry 边界全声明、总时长 = duration；
  3. comp 契约：生成产物含 `__seek/__ready/__meta/__events`、`OM.rng(` 存在、渲染路径无 `Math.random(`、
     lineage 注释保留；
  4. showcase API：202→轮询→404/409 语义（无 playwright 环境时分类为 fatal + 可读文案）。
- **渲染验收（E2E 级）**：`verify_promo.py draft.mp4 --comp cf_showcase.html` 五腿通过
  （rhythm CV≥0.25 / carry≥0.5 / curves / framing 0 违规 / burst 视参考）。这是 onetake 的核心赠送：
  把「像不像 PPT」变成回归门。
- **前端浏览器冒烟（新增，最小化）**：复用渲染所装的 Playwright 写一条 python 冒烟
  （dev server 起后进 /showcase → 断言时间线渲染）——项目当前没有浏览器 E2E，此处不引入重框架，
  只借依赖顺带补位；CI 暂不跑（与渲染同级，本机门禁）。

---

## 4. 实施计划（可直接执行）

| 阶段 | 内容 | 交付物 / 文件 | 工时 |
|---|---|---|---|
| **P0 环境** | pip install playwright + chromium；ffmpeg PATH（imageio_ffmpeg 二进制软链或注入）；fonttools+brotli；vendored third_party/onetake（§3.2 清单）；跑通 `render.py templates/comp.html --out draft.mp4` | 环境说明写进 docs/同文附录；draft.mp4 | 0.5d |
| **P1 契约+后端** | presentation 字段（models/asset + creative_asset_adapter + Go 接口注释）；adapters/onetake 四模块；cf_showcase.html 模板（五 beat 落版）；ShowcaseService + 三条路由；capability 注册 | 新文件 ~8 个；mapper 单测 + comp 契约测试过 | 1.5–2d |
| **P2 前端** | ShowcaseStudio.tsx（lazy 路由 + Timeline + Generate + video + iframe 预览 + 历史）；api/client.ts 三端点；nav 入口 | 新页面 + client 扩展；vitest 3 项过 | 1–1.5d |
| **P3 视觉与编排** | look.py from-shot 烘焙 cf-paper look（骑士原画取样）；CreativeStudio 加「生成发布片」入口；TechnologyCenter 定位文案（External Creative Capability） | look 资产 + 两处入口文案 | 0.5d |
| **P4 门禁收口** | verify_promo 集成进验收步（成片五腿）；全量门禁回归；文档定稿 | 验收清单全勾 | 0.5–1d |

合计 **4–5.5 个工作日**（含调试缓冲）；其中唯一的外部不确定项是 P0 的 Windows playwright 环境与渲染时长调优。

## 5. 验收标准

**功能**
- [ ] 选择有原画+有动作条带的资产 → Generate OneTake Demo → 轮询完成 → 15s±1 成片可播放可下载；
- [ ] 成片覆盖五 beat：一句话意图 / 原画→像素重建 / 动作展开 / Cocos 预览 / Logo 收束；
- [ ] Asset Timeline dry-run 展示五 beat 与素材就绪状态；素材缺失给 409 + 中文可读提示，不静默兜底；
- [ ] Agent 侧 capability 注册生效（plan_capabilities 可见 motion_video_generation）。

**视觉 / 交互 / 响应式**
- [ ] 页面 UI 全部走暖纸编辑风令牌（与 DesignCenter 对照无出戏元素）；
- [ ] comp 用 cf-paper look（纸底 + 单强调色，取样自项目资产），无上游默认叙事残留；
- [ ] Generate→生成中徽章→完成自动播放；失败按错误分类出徽章；不自动渲染、不自动播放音频；
- [ ] 1280 / 1440 / 1920 三档宽度无横向滚动；预览 iframe 16:9 等比；reduced-motion 下页面过渡瞬时完成（项目既有纪律）。

**性能 / 质量 / 合规**
- [ ] 主 bundle gzip 增量 < 20KB（页面 lazy + iframe 隔离，用 Lighthouse/产物体积门验证）；
- [ ] vitest 全绿且新增 ≥3 项；后端 mapper/契约测试 ≥6 项；主套件 39/39、动画回归 112/112、发布门 15/15 不回退；
- [ ] 一条 draft 成片通过 verify_promo 五腿（carry ≥ 0.5，framing 0 违规）；
- [ ] LICENSE 随行 + 关于页标注 PolyForm NC + lineage 记录；third_party 无本地直改（patches/ 机制）。

## 6. 风险与缓解

| 风险 | 等级 | 缓解 |
|---|---|---|
| PolyForm NC 许可 vs 商业化 | 高（一票否决级） | 比赛/演示可用；商业化触发即执行替换预案（framer-motion 11 已在依赖内，f(t) 原语可迁移，业务只耦合 mp4/预览 URL） |
| 上游无版本发布 | 中 | vendored 快照 + lineage + patches 目录；升级手工重放 |
| 渲染时长/环境（Windows） | 中 | 用户点击后渲染；1080p30 draft 先行；workers 封顶；环境缺失给可读 fatal；CI 不渲染 |
| 素材质量拖累成片 | 中 | mapper 前置校验（原画/条带帧/导出截图齐全才可生成）；dry-run 时间线暴露缺口 |
| 创作模板「像上游案例」 | 低 | SKILL 硬规则内建：cf_showcase 是 CreativeForge 专属叙事，look 取样自本项目资产，不复制模板故事 |
| 双语言/配音范围蔓延 | 低 | P1–P4 不含 vo_tools/kokoro（演示用 sfx_palette 草稿音效即可）；多语言列为后续可选 |

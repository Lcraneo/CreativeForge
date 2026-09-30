# CreativeForge × Windup 系统性质量提升方案

> 基准日期：2026-09-30。竞品样本：windup.xin 线上站（深色改版）+ Windup-main 源码（GitHub main，浅色版）。
> 我方基线：studio/ 子系统（排除遗留 backend/ 与 frontend/）。本方案基于线上实测数据、竞品源码研读与我方仓库工程探查（证据随表格标注）。

---

## 一、质量评估指标体系与双方量化评分

### 1.1 指标体系（7 维度加权，0-5 分制）

| 维度 | 权重 | 评估内容 | 数据来源 |
|---|---|---|---|
| 功能完整性 | 20% | 核心链路覆盖度、深度、边界处理 | 源码 + 页面走查 |
| 体验流畅度 | 15% | 动效系统纪律、帧率、滚动/切换行为、可访问性降级 | 浏览器实测（165Hz 屏采样） |
| 界面设计 | 15% | 设计语言一致性、排版纪律、信息层级 | 截图走查 |
| 性能表现 | 15% | 加载指标、资源策略、运行时开销 | Performance API + 响应头实测 |
| 稳定性 | 15% | 错误合同、失败恢复、输入鲁棒性 | 源码 + 实测 |
| 安全性 | 10% | 鉴权、密钥管理、传输/响应头、输入面 | 响应头实测 + 仓库扫描 |
| 工程质量 | 10% | 测试文化、CI、lint、债务 | 仓库探查 |

### 1.2 量化评分

| 维度 | Windup | CreativeForge(studio) | 差距 | 关键证据 |
|---|---|---|---|---|
| 功能完整性 | **4.0** | 3.5 | −0.5 | 竞品资产层级 Project⊃Character⊃Outfit⊃Action + 试玩台键位重绑/八向/持久化；我方 15 页覆盖面更广（含批量/版本/基准/导出中心）但试玩深度刚补齐、展示区多处占位 |
| 体验流畅度 | **5.0** | 2.5 | **−2.5** | 竞品实测 165fps、长帧 0、maxΔ 7ms；全站统一动效令牌（cubic-bezier(0.16,1,0.3,1) + 90-280ms 阶梯）；reduced-motion 全覆盖。我方无统一动效系统，页面各自为政（PlaytestStage 四补丁后局部达 4 分） |
| 界面设计 | **4.5** | 3.5 | −1.0 | 竞品暖纸编辑风 + 衬线/等宽字纪律 + 深色改版一致性；我方已统一暖纸令牌但无动效语言规范、视觉丰富度受占位素材拖累 |
| 性能表现 | **4.5** | 3.0 | −1.5 | 竞品 DCL 1.54s / load 1.70s / 61 资源 / 路由级分包（index+entities+ui+workflow chunks）/ 39 图全 lazy / 视频 poster+metadata 预载+视口播放 / shader 像素上限。我方后端有性能门（规划<50ms、导出<1s、内存<128MB）但前端零度量、无分包审计 |
| 稳定性 | **4.0** | 2.5 | −1.5 | 竞品错误合同清晰（业务码 404 vs 传输错误分开认）、帧失败可重试、blur 清键、禁止占位数据兜底；我方无 ErrorBoundary、JSON 持久化无原子写、quality_gate 仅 3 维 |
| 安全性 | 3.0 | **1.0** | **−2.0** | 竞品有登录墙但零安全响应头（无 CSP/HSTS/XFO/XCTO/Referrer-Policy，实测）；我方更糟：**无鉴权、CORS `*`、无限流，且 model_settings.json 明文真实 DashScope key 被 git 跟踪（已确认，最高危）** |
| 工程质量 | **4.5** | 2.5 | **−2.0** | 竞品每模块带测试（runtime/stage/bindings/preferences/boundaries）+ 5 条 CI 工作流 + coverage + openapi.json；我方本地测试文化其实很强（契约 md + 35 项断言 + 4 层发布门含性能阈值）但 **CI 零、lint 零、前端测试零、遗留双系统占一半体量（179 py）** |
| **加权总分** | **4.25** | **2.78** | **−1.47** | |

### 1.3 竞品优势清单（按量化证据）

1. **动效系统纪律**（165fps/0 长帧实测）：所有滚动驱动一律 rAF 合并 scroll 事件 + CSS 变量下发；切换瞬时、观感过渡交给 120-280ms 短 CSS 动画。
2. **播放引擎正确性**：时间步进累加器 + Δ封顶 50ms + 状态不变返回原对象（零渲染预算）；全动作预载 + decode() 门控。
3. **测试即架构**：`playtest-boundaries.test.ts` 用测试固化模块边界（页面禁 import features/generation），比文档更硬。
4. **诚实的错误合同**：业务 404 与传输错误分开认；"读不到就报错，不回退内置数据"写进 README。
5. **资源策略**：路由分包、lazy 图、视频 poster+视口播放（IO 阈值 0.35 实测）、shader maxPixelCount 封顶 GPU 成本。

### 1.4 竞品不足清单（= 我方超越点）

1. **行走预览首过尖峰 466ms**：帧图未预载完成即开始播放（实测 maxΔ），二次通过才降到 10ms → 我方可用 `link rel=preload` + decode 完成门做到零尖峰。
2. **落地页大面积占位**：4 个悬浮卡、4 个风格展示位、3 个能力场景全是"素材待接入"白卡 → 我方用真实产品录屏/可交互 demo 直接碾压。
3. **试玩台登录墙**：/playtest 未登录 302 到 login（实测）→ 我方做 guest 试玩公开嵌入。
4. **零安全响应头**（实测五头全缺）+ 键位仅 localStorage 明确不做服务端同步 → 我方补齐头 + 做偏好同步/导入导出。
5. **无运行时性能监控**（源码未见 RUM 之外的 FPS 采样）→ 我方把帧率/长帧纳入发布门。

---

## 二、分阶段目标与实施计划

> 时间按单人开发折算（周）。"责任分工"按工作流（WS）切分，每项给出验收判据——判据不达成不算完成。

### Phase Q1（第 1-2 周）止血与地基 —— 安全+工程，清零两个 −2 项

| # | 事项 | WS | 时间 | 验收判据 |
|---|---|---|---|---|
| 1.1 | **立即吊销并轮换 DashScope key**；`git rm --cached model_settings.json` + .gitignore + 改为 env 优先 | WS1 | D1 | 旧 key 失效；`git ls-files` 不再包含该文件；gitleaks 扫描清零 |
| 1.2 | CORS 白名单化（开发域+生产域），WebSocket 加 origin 校验，绑定 127.0.0.1 默认值 | WS1 | 第 1 周 | 非白名单 Origin 请求被拒（curl 验证） |
| 1.3 | 最小鉴权：本地单用户 Bearer token（env 配置），routes.py 全局依赖；限流 slowapi | WS1 | 第 2 周 | 无 token 401；前端 client.ts 带 token |
| 1.4 | 安全响应头中间件：CSP（script-src self+nonce）、HSTS、XFO=DENY、XCTO=nosniff、Referrer-Policy=strict-origin-when-cross-origin | WS1 | 第 1 周 | securityheaders.com ≥ B |
| 1.5 | GitHub Actions：backend（pytest + run_tests + release L1-L2）/ frontend（tsc -b + build + vitest）双工作流 | WS2 | 第 2 周 | CI 双绿；PR 必跑 |
| 1.6 | ruff+black+eslint+prettier 一次配齐并全量修复 | WS2 | 第 2 周 | 仓库零告警 |
| 1.7 | ErrorBoundary 组件 + 路由级 lazy 分包 + api client 统一 toast 错误捕获 | WS2 | 第 2 周 | 手动抛错验证兜底 UI；路由 chunks ≥ 5 |

### Phase Q2（第 3-5 周）体验追平 —— 流畅度 −2.5 与稳定性 −1.5 ✅ 2026-09-30 完成

> 完成备注：7 项全部落地；2.6 额外含 boundaries 架构测试（24 用例全绿）；vitest 锁定 v3（vite 5 兼容性）；2.3 的 CommandPalette/Layout 属按键覆盖层（合法拥有按键），不适用 typing 守卫。eslint 遗留 warn（React Compiler 系新规 11 处 + 未用符号），Q3 清零后升 error。

| # | 事项 | WS | 时间 | 验收判据 |
|---|---|---|---|---|
| 2.1 | 动效令牌系统 `motion.css`：统一缓动 cubic-bezier(0.16,1,0.3,1) + 时长阶梯（90/120/180/260/280ms），全页面替换裸 transition/animation | WS3 | 第 3-4 周 | `grep 裸 ms 常量` 仅剩令牌文件；reduced-motion 全覆盖 |
| 2.2 | PlaytestStage 四补丁（已落地）纳入回归 + 预载门控推广到 PixelStudio/AnimationStudio 帧播放 | WS3 | 第 3 周 | 切动作零网络请求；首帧零等待 |
| 2.3 | 键盘/焦点管理统一：blur 清键、typing-target 守卫、物理键码，抽成 `useKeyboardBindings` 复用 | WS3 | 第 4 周 | 试玩/像素台/动画台共用一套 |
| 2.4 | quality_gate 3 维 → 6 维（+结构完整性、时间轴一致性、性能预算），阈值与 release L4 对齐 | WS1 | 第 4 周 | 新维度有单测且低于阈值触发 RETRY |
| 2.5 | JSON 持久化原子写（tmp+rename）+ 损坏自动恢复（备份回退） | WS1 | 第 5 周 | kill -9 注入测试通过 |
| 2.6 | 前端测试基建：vitest + testing-library；PlaytestStage/api client/5 个 store 各 3-5 用例；boundaries 式架构测试 | WS4 | 第 4-5 周 | vitest ≥ 15 用例绿，进 CI |
| 2.7 | 前端性能基线测量（165Hz Profiler + Performance API 采样脚本，本会话已验证方法） | WS4 | 第 5 周 | 建立基线数字进看板 |

### Phase Q3（第 6-8 周）超越点 —— 攻击竞品的占位符 ✅ 2026-09-30 完成

> 完成备注：3.1 演示模式经 API 测试固化（test_playtest_demo_api.py：5 动作程序化条带、只读、跨调用稳定；本工具无登录墙，"未登录可玩"由架构保证）；3.2 全仓唯一真占位（AssetInspector 3D 替身）已真实化——AssetViewer 新增 textureUrl，像素重建图作为 NearestFilter 贴图上 3D 舞台，失败回落体素；3.3 rel=preload 首选条带提示 + 条带未就绪时 rAF 循环零 setState；3.4 lighthouserc.json + CI Lighthouse job（性能≥90 / LCP<2.5s / CLS<0.1 / TBT<200ms / 脚本体积门，CI 首跑后按实际分数校准）；3.5 偏好 JSON 导入导出（SettingsCenter 偏好迁移卡，studio_token 刻意排除；服务端同步留待账号体系）。首过零尖峰的最终数字待 app 运行时按 docs/perf-baseline.md 方法采样回填。

| # | 事项 | WS | 时间 | 验收判据 |
|---|---|---|---|---|
| 3.1 | **Guest 试玩**：公开嵌入试玩舞台（演示资产只读），无需登录——竞品是登录墙 | WS5 | 第 6-7 周 | 未登录可玩；只读不写资产 |
| 3.2 | 展示区真实化：能力场景/风格展示全部替换为真实产品录屏与可交互 demo（竞品全是"待接入"白卡） | WS5 | 第 6-8 周 | 零占位文案 |
| 3.3 | 帧预载零尖峰：`link rel=preload` + decode 完成门（竞品首过 466ms 尖峰 → 我方 0） | WS3 | 第 6 周 | 首过 maxΔ < 16ms |
| 3.4 | Lighthouse CI + 预算门：LCP<2.5s、CLS<0.1、TBT<200ms、bundle 预算 | WS4 | 第 7-8 周 | 四项 ≥90 进 CI |
| 3.5 | 偏好同步：键位/工作区设置服务端存储（登录后），无账号则导入导出 JSON | WS1+WS5 | 第 8 周 | 跨浏览器恢复配置 |

### Phase Q4（第 9-10 周 + 常态）可持续质量保障体系 ✅ 2026-09-30 完成

> 完成备注：4.1 发布门扩至 **L1-L5**（新增 L5 前端层：体积预算入口 gzip≤130KB/单 chunk≤900KB + vitest + eslint + tsc；node/dist 缺失自动 SKIP；`python run_release_tests.py L5` 支持分层过滤——首跑 15 checks 全绿）；4.2 遗留冻结（architecture 冻结测试 + docs/legacy-inventory.md 三里程碑，删除留给显式决定）；4.3 双工作流 Gate summary 步骤输出测试计数/L4 耗时/L5 体积到 job summary；4.4 CONTRIBUTING.md 落笔约定 + docs/quality-scores.md 评分历史档案（月度复盘模板就位）。

| # | 事项 | WS | 验收判据 |
|---|---|---|---|
| 4.1 | 发布门 L5（前端）：tsc/build/vitest/lighthouse/browser-use 冒烟（FPS 采样+交互走查，工具链本会话已验证可自动化） | WS4 | `run_release_tests.py` L1-L5 全绿才可发布 |
| 4.2 | 遗留系统处置：backend/(179 py)+frontend/ 冻结→迁移→删除的三个里程碑 | WS6 | 体量减半；CI 不再跑遗留 |
| 4.3 | 度量看板：CI artifact 输出测试通过率/阈值达成/bundle 趋势/四门耗时 | WS6 | 每次发布可对比 |
| 4.4 | 文化机制：功能 PR 必附测试（竞品每模块带测试的文化）；README/代码注释写决策理由（竞品做法）；月度重跑本方案 1.2 评分表 | WS6 | 评分表有历史记录 |

---

## 三、质量监控与测试机制（贯穿全程）

**指标阈值表（门禁用，全部门槛来自实测或竞品水平）：**

| 指标 | 门禁阈值 | 竞品实测参照 |
|---|---|---|
| 运行时长帧 | 静置 0 个（>25ms）；交互 maxΔ p95 < 8ms | 0 个 / 7ms |
| LCP / CLS / TBT | <2.5s / <0.1 / <200ms | DCL 1.54s（含 1s TTFB 网络项） |
| 帧预载首过尖峰 | maxΔ < 16ms | 466ms |
| 后端规划/导出/内存 | 沿用 release L4（<50ms/<1s/<128MB） | 已有 |
| 质量门维度 | 6 维全过（pixel 0.8 / animation 0.85 / engine 0.9 / +3 新） | 竞品未见等价物 |
| 密钥扫描 | gitleaks 零命中 | 竞品未公开 |
| 测试 | pytest 35 项 + vitest ≥15 + L1-L5 全绿 | 每模块测试 |

**三层门禁：**
1. 本地 pre-push：tsc -b + ruff + vitest 相关用例（<2 分钟）。
2. CI 必绿：双工作流 + gitleaks + lighthouse（PR 阻断）。
3. 发布前：`run_release_tests.py` L1-L5 + browser-use 自动化冒烟（headless cdp 模式跑首页 FPS/试玩交互走查）。

---

## 四、目标与里程碑

- **Q1 末**：安全项清零 + CI 双绿 → 工程质量 2.5→3.5，安全 1→3.5，总分 2.78→3.3。
- **Q2 末**：流畅度与稳定性追平竞品 → 2.5→4.5 与 2.5→4.0，总分→3.9。
- **Q3 末**：三个超越点落地两个 + Lighthouse ≥90 → 功能 4.0、性能 4.5，**总分 ≥4.4 ≥ 竞品 4.25**。
- **Q4 起**：体系常态化，月度评分表复盘防止回退。

**关键依赖与风险**：① key 轮换依赖云厂商控制台（D1 即办，其余不阻塞）；② guest 试玩需要演示资产只读快照，若后端鉴权方案变化需同步调整；③ 遗留系统删除前确认无独占功能。

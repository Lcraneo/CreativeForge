---
name: CreativeForge Studio
description: 以雾蓝色工坊为视觉世界，将自然语言创意转化为可直接用于游戏的资产。
colors:
  canvas: "#F3F6FA"
  paper: "#FBF9F4"
  surface-1: "#EAF0F6"
  surface-2: "#E1E8F1"
  line: "#CBD5E3"
  ink-blue: "#25345A"
  ink-blue-2: "#394968"
  ink-blue-3: "#4E5D7B"
  ink-blue-4: "#526079"
  mist-blue: "#AEBFD7"
  ember: "#93A9C4"
  ember-ink: "#4A627E"
  wax-red: "#8E4657"
  success: "#3E6553"
  warning: "#765A2C"
  danger: "#8E4657"
typography:
  display:
    fontFamily: "Cormorant Garamond, Noto Serif SC, serif"
    fontSize: "clamp(2.75rem, 5vw, 5rem)"
    fontWeight: 600
    lineHeight: 0.98
    letterSpacing: "-0.02em"
  title:
    fontFamily: "Noto Serif SC, Cormorant Garamond, serif"
    fontSize: "2.125rem"
    fontWeight: 900
    lineHeight: 1.05
    letterSpacing: "-0.02em"
  body:
    fontFamily: "Outfit, Noto Sans SC, sans-serif"
    fontSize: "0.875rem"
    fontWeight: 400
    lineHeight: 1.55
    letterSpacing: "normal"
  label:
    fontFamily: "Outfit, Noto Sans SC, sans-serif"
    fontSize: "0.75rem"
    fontWeight: 600
    lineHeight: 1.25
    letterSpacing: "0.06em"
  code:
    fontFamily: "IBM Plex Mono, ui-monospace, monospace"
    fontSize: "0.75rem"
    fontWeight: 400
    lineHeight: 1.45
    letterSpacing: "normal"
rounded:
  xs: "4px"
  sm: "6px"
  md: "10px"
  lg: "14px"
  xl: "18px"
  pill: "999px"
spacing:
  xs: "4px"
  sm: "8px"
  md: "16px"
  lg: "24px"
  xl: "32px"
  2xl: "48px"
components:
  button-primary:
    backgroundColor: "{colors.ink-blue}"
    textColor: "{colors.paper}"
    rounded: "{rounded.sm}"
    padding: "10px 16px"
  button-primary-hover:
    backgroundColor: "{colors.ink-blue-2}"
    textColor: "{colors.paper}"
    rounded: "{rounded.sm}"
    padding: "10px 16px"
  button-secondary:
    backgroundColor: "{colors.paper}"
    textColor: "{colors.ink-blue}"
    rounded: "{rounded.sm}"
    padding: "10px 16px"
  input:
    backgroundColor: "{colors.paper}"
    textColor: "{colors.ink-blue}"
    rounded: "{rounded.md}"
    padding: "10px 12px"
  letter-card:
    backgroundColor: "{colors.paper}"
    textColor: "{colors.ink-blue}"
    rounded: "{rounded.lg}"
    padding: "24px"
  dossier-panel:
    backgroundColor: "{colors.surface-1}"
    textColor: "{colors.ink-blue}"
    rounded: "{rounded.lg}"
    padding: "20px"

---

# 设计系统：CreativeForge Studio

## 概述

**创意北极星：“雾蓝工坊”**

CreativeForge 应当像一个正在工作的工坊，而不是传统控制面板：象牙色工作台面、
雾蓝空气、墨蓝文字、银蓝分隔线，以及只用于重要结果的少量蜡红色时刻。视觉世界
借用洛可可沙龙的从容与仪式感，但最终服务于生产工具，让资产、智能体推理和下一步
操作始终清晰可读。

**关键特征：**

- 纸张与羊皮纸质感表面，搭配精确的银蓝分隔线。
- 暖象牙底色上的墨蓝文字，雾蓝主要用于氛围，而非装饰。
- 开屏是唯一强表现时刻，日常产品动效保持克制。
- 二级面板像档案页，控制项像票签，元数据像邮戳。
- 使用清晰的 SVG 卷草纹、缎带、纹章和拱形线条建立沙龙氛围。
- 高密度区域保持安静、规整、便于扫读。
- 中文排版经过专门设计，不依赖系统兜底效果。

## 色彩

### 主色

- **墨蓝 `#25345A`**：主要文字、主要操作和权威标签。
- **雾蓝 `#AEBFD7`**：氛围背景、选中表面和低调的品牌存在感。
- **蜡红 `#8E4657`**：破坏性操作、不可逆确认和少量表示结果的重要印记。

### 中性色

- **纸张 / 象牙白 `#FBF9F4`**：主要工作纸张。
- **画布 `#F3F6FA`**：应用背景与大气层。
- **表面 `#EAF0F6`**：二级面板、工具栏和档案内容区。
- **雾银 `#93A9C4`**：线条、图标、弱化元数据和禁用文字。
- **分隔线 `#CBD5E3`**：一像素边框和分隔线。

成功、警告和危险状态分别使用 `#3E6553`、`#765A2C` 和 `#8E4657`，
并且必须同时搭配文字或形状提示。

### 命名规则

**结果规则。** 蜡红不装饰非活动内容，只用于决策、中断或不可逆操作。

**纸上墨色规则。** 正文和控件在象牙白或画布上使用墨蓝，不使用浅灰配蓝色；
次级文字从墨蓝派生，而不是改成中性灰。

## 排版

### 层级

- **展示标题**：Cormorant Garamond，中文回退到 Noto Serif SC；用于开屏、空状态
  核心句和每个界面的唯一焦点标题。
- **页面标题**：Noto Serif SC，28–34px；用于页面和区块标题。
- **正文**：Outfit，中文回退到无衬线字体；用于标签、控件、描述和数据。
- **标签**：Outfit 12px、字重 600、适度字距；用于导航和元数据。
- **代码**：IBM Plex Mono；用于路径、任务 ID、JSON、日志和数值测量。

### 命名规则

**中文语气规则。** 拉丁展示字体可以承担英文和法文视觉重音，但中文展示文字始终
使用 Noto Serif SC，并单独调整字重与行高。

**标签规则。** 展示字体和手写风格字体不得出现在按钮、表单标签、表头或高密度操作
文本中。

## 布局

桌面端采用三段式结构：左侧导航书页、中间工作信纸、右侧可选档案面板。中栏承担
主要任务，两侧区域是辅助内容并可以收起。视口小于等于 1280px 时，左侧导航可以
收窄；小于等于 1024px 时，档案面板变为抽屉；小于 768px 时，界面切换为单列，
并使用紧凑的底部导航。

页面间距采用 4px 节奏，并以 16/24/32/48px 递进。密集表格和日志可以使用紧凑行，
但页面级区块之间保持充足留白。阅读文本宽度控制在 65–75 个字符。3D、试玩和动画
画布占用全部剩余空间，只保留轻量边框。

## 抬升与纵深感

结构主要由边框承担。阴影只用于浮动菜单、抽屉和开屏遮罩。抬升效果使用偏移和柔和
模糊，不使用零偏移的彩色光晕。纸张表面可以有轻微内高光，但不能同时叠加粗边框和
重阴影。

## 形状

圆角保持在 6–18px。主要容器使用 14px 圆角的稳定矩形。洛可可表达使用专门绘制的
SVG 几何：身份区域使用纹章，工作区使用双线拱门，页面标题使用卷草角，卡片标题
使用小花饰。缎带和椭圆印章承载元数据或状态。装饰是布局之上的图层，绝不能替代
点击区域、文本流或画布空间。

## 组件

### 按钮

主按钮使用墨蓝底和纸张白文字，保持紧凑矩形。次按钮使用纸张白底和银蓝边框。悬停
时向上移动一像素并强化边框，不强化阴影。按下状态缩放到 98%。焦点使用象牙白与
墨蓝双层轮廓。破坏性操作使用蜡红色和明确动词。

### 标签片

标签片像小型印章：象牙白填充、银蓝边框、墨蓝文字。选中项使用雾蓝底和墨蓝文字。
除非表示破坏性筛选，否则不使用蜡红。

### 卡片与容器

信件式卡片使用象牙白、14px 圆角、一像素边框和宽松内边距。避免卡片嵌套。通过标题
分隔线和正文节奏建立层级，不要连续堆叠装饰盒子。

### 输入框

输入框使用象牙白内嵌表面、银蓝边框和墨蓝光标与文字。占位文字对比度至少达到
4.5:1。错误信息应使用产品语言说明问题和恢复方式。

### 导航

左侧书页在安静的墨蓝标题和银色分隔线下组织目的地。当前项使用雾蓝底色和一个小
蜡红书签，不使用大面积高饱和高亮。移动端导航保留同一套视觉语言，但采用紧凑形式。

### 标志性组件

档案面板是标志性的二级表面：冷纸张底色、缎带标签、紧凑标题和纵向事实序列。配套
装饰语法包括：身份区使用 `RococoCrest`，区块过渡使用 `RococoDivider`，页面边框
使用 `RococoCorner`，工作区拱门使用 `RococoFrame`，标签使用 `RococoRibbon`。
装饰元素必须设置 `aria-hidden`、允许指针穿透，并且不能替代文字含义。

### 装饰预算

每个页面最多使用一个页眉角饰、一个区块分隔线，以及一个重要位置的纹章或缎带。
卡片只在标题处使用小花饰。密集表格、日志、画布控件和 3D 视口不增加卷草装饰。

### 动效

常规过渡时长 120–320ms，使用稳定的 ease-out。开屏是唯一专门编排的视觉演出：
桌面端每天运行一次，持续 4.5 秒，经过字形画框和最终印章，再用 240ms 收回已加载
的工作台。移动端版本为 1.6 秒；减少动态效果模式下，最终标记以 1.15 秒淡入。点击、
Enter、空格或 Escape 均可跳过。页面加载编排不会在产品内部重复播放。

## 应做与不应做

### 应做

- 使用真实产品内容和实际状态词汇。
- 每种语义色都必须搭配文字或形状。
- 保持中央工作区安静，并把装饰预算集中使用。
- 在每个断点测试中文、英文、混合字符串、长路径和大数字。
- 所有专门编排的动画都支持 `prefers-reduced-motion`。
- 洛可可装饰使用清晰的 SVG 线条，并保持指针穿透。

### 不应做

- 复制 Kimi Code 的品牌、文案或页面内容。
- 在操作标签中使用展示字体。
- 嵌套卡片，或给每个面板都增加装饰。
- 使用 emoji、位图涂鸦或装饰性字形代替纹样。
- 用模糊、渐变或纹理替代信息层级。
- 当资源或路由失败时，让开屏动画阻止用户进入。

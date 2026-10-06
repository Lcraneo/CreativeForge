import type { IconName } from "../components/icons";

export interface NavItem {
  to: string;
  label: string;
  icon: IconName;
  kbd?: string;
  /** 子级导航：侧栏可展开/收起（历史记录从属于智能体） */
  children?: NavItem[];
}

export interface NavGroup {
  label: string;
  /** 章序号（宋体），侧栏展开态显示 */
  numeral?: string;
  /** 一句话副题，悬停组头时提示 */
  hint?: string;
  items: NavItem[];
}

/**
 * 信息架构按创作旅程分章：
 * 壹·创作（从一句话到一条管线）→ 贰·资产库（每件作品都有档案）
 * → 叁·舞台（让角色登台演出）→ 肆·手记（度量、资料与调校）
 */
export const NAV_GROUPS: NavGroup[] = [
  {
    label: "创作",
    numeral: "壹",
    hint: "从一句话到一条管线",
    items: [
      { to: "/", label: "工作台", icon: "panel", kbd: "1" },
      {
        to: "/agents",
        label: "智能体",
        icon: "layers",
        kbd: "2",
        children: [{ to: "/history", label: "历史记录", icon: "clock" }],
      },
      { to: "/batch", label: "批量生产线", icon: "package" },
    ],
  },
  {
    label: "资产库",
    numeral: "贰",
    hint: "每件作品都有档案",
    items: [
      { to: "/asset", label: "资产检查", icon: "cube", kbd: "3" },
      { to: "/design", label: "设计三视图", icon: "brush" },
      { to: "/animation", label: "动画工作台", icon: "film" },
      { to: "/versions", label: "版本控制", icon: "clock" },
    ],
  },
  {
    label: "舞台",
    numeral: "叁",
    hint: "让角色登台演出",
    items: [
      { to: "/playtest", label: "试玩舞台", icon: "play" },
      { to: "/showcase", label: "发布展示间", icon: "spark" },
      { to: "/export", label: "导出中心", icon: "package" },
    ],
  },
  {
    label: "手记",
    numeral: "肆",
    hint: "度量、资料与调校",
    items: [
      { to: "/benchmark", label: "基准中心", icon: "gauge" },
      { to: "/technology", label: "技术中心", icon: "book" },
      { to: "/settings", label: "模型设置", icon: "terminal" },
    ],
  },
];

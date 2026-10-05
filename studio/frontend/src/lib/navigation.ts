import type { IconName } from "../components/icons";

export interface NavItem {
  to: string;
  label: string;
  icon: IconName;
  kbd?: string;
  /** 子级导航：侧栏可展开/收起（历史记录从属于智能体指挥中心） */
  children?: NavItem[];
}

export const NAV_GROUPS: Array<{ label: string; items: NavItem[] }> = [
  {
    label: "生产",
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
      { to: "/playtest", label: "试玩舞台", icon: "film" },
      { to: "/showcase", label: "发布展示间", icon: "spark" },
    ],
  },
  {
    label: "资产",
    items: [
      { to: "/asset", label: "资产检查", icon: "cube", kbd: "3" },
      { to: "/design", label: "设计三视图", icon: "layers" },
      { to: "/versions", label: "版本控制", icon: "clock" },
      { to: "/animation", label: "动画工作台", icon: "film" },
    ],
  },
  {
    label: "交付 · 洞察",
    items: [
      { to: "/export", label: "导出中心", icon: "package" },
      { to: "/benchmark", label: "基准中心", icon: "gauge" },
      { to: "/technology", label: "技术中心", icon: "book" },
      { to: "/settings", label: "模型设置", icon: "terminal" },
    ],
  },
];

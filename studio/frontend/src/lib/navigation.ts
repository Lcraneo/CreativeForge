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
 * 信息架构按三条核心产品线分章：
 * 壹·生成（从一句话到一条管线）→ 贰·资产库（每件作品都有档案）
 * → 叁·试玩（让角色登台演出）
 */
export const NAV_GROUPS: NavGroup[] = [
  {
    label: "总览",
    numeral: "序",
    hint: "从一个想法开始",
    items: [{ to: "/", label: "首页", icon: "spark" }],
  },
  {
    label: "生成",
    numeral: "壹",
    hint: "从一句话到一条管线",
    items: [
      { to: "/workspace", label: "工作台", icon: "panel", kbd: "1" },
      { to: "/scenes", label: "场景工坊", icon: "grid" },
      {
        to: "/agents",
        label: "智能体",
        icon: "layers",
        kbd: "2",
        children: [{ to: "/history", label: "历史记录", icon: "clock" }],
      },
      { to: "/settings", label: "模型设置", icon: "key" },
    ],
  },
  {
    label: "资产库",
    numeral: "贰",
    hint: "每件作品都有档案",
    items: [
      { to: "/asset", label: "资产检查", icon: "cube", kbd: "3" },
      { to: "/design", label: "设计三视图", icon: "brush" },
      { to: "/versions", label: "版本控制", icon: "clock" },
    ],
  },
  {
    label: "试玩",
    numeral: "叁",
    hint: "让角色登台演出",
    items: [
      { to: "/playtest", label: "试玩舞台", icon: "play" },
      { to: "/arcade", label: "关卡试玩场", icon: "zap" },
    ],
  },
];

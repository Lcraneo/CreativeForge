import { useEffect, useState } from "react";
import { NavLink, Outlet, useLocation, useNavigate } from "react-router-dom";
import { AnimatePresence, motion } from "framer-motion";
import { EASE_STANDARD, MOTION } from "../lib/motion";
import { api } from "../api/client";
import { useAgentStore } from "../stores/agentStore";
import { useAssetStore } from "../stores/assetStore";
import { CommandPalette } from "./CommandPalette";
import { Toaster } from "./Toaster";
import { Icon, type IconName } from "./icons";
import { Badge, StatusDot, cx } from "./ui";

interface NavItem {
  to: string;
  label: string;
  icon: IconName;
  kbd?: string;
  /** 子级导航：侧栏可展开/收起（历史记录从属于智能体指挥中心） */
  children?: NavItem[];
}

const AGENTS_NAV_KEY = "cf-nav-agents-open";

const NAV_GROUPS: Array<{ label: string; items: NavItem[] }> = [
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

const MOBILE_TABS: NavItem[] = [
  { to: "/", label: "工作台", icon: "spark" },
  { to: "/agents", label: "智能体", icon: "layers" },
  { to: "/asset", label: "资产", icon: "cube" },
  { to: "/history", label: "历史", icon: "clock" },
  { to: "/export", label: "导出", icon: "package" },
];

const BREADCRUMBS: Record<string, { group: string; label: string }> = {
  "/": { group: "生产", label: "工作台" },
  "/workspace": { group: "生产", label: "工作台" },
  "/agents": { group: "生产", label: "智能体指挥中心" },
  "/history": { group: "智能体指挥中心", label: "历史记录" },
  "/batch": { group: "生产", label: "批量生产线" },
  "/playtest": { group: "生产", label: "试玩舞台" },
  "/versions": { group: "资产", label: "版本控制中心" },
  "/asset": { group: "资产", label: "资产检查器" },
  "/design": { group: "资产", label: "角色设计三视图" },
  "/animation": { group: "资产", label: "动画工作台" },
  "/export": { group: "交付", label: "导出中心" },
  "/benchmark": { group: "洞察", label: "基准中心" },
  "/technology": { group: "洞察", label: "技术中心" },
  "/settings": { group: "洞察", label: "模型设置" },
};

export default function Layout() {
  const [rail, setRail] = useState(
    () => localStorage.getItem("cf-rail") === "1" || window.innerWidth < 1024,
  );
  const [paletteOpen, setPaletteOpen] = useState(false);
  const location = useLocation();
  const navigate = useNavigate();

  const taskId = useAgentStore((state) => state.taskId);
  const status = useAgentStore((state) => state.status);
  const progress = useAgentStore((state) => state.progress);
  const goal = useAgentStore((state) => state.goal);
  const asset = useAssetStore((state) => state.asset);

  // 智能体子导航展开态（跨会话保留）；深链到子级页面时派生为展开，
  // 不经 effect 写 state（避免级联渲染）
  const [agentsOpen, setAgentsOpen] = useState(
    () => localStorage.getItem(AGENTS_NAV_KEY) !== "0",
  );
  const agentsExpanded = agentsOpen || location.pathname === "/history";

  function toggleAgentsOpen() {
    setAgentsOpen((value) => {
      localStorage.setItem(AGENTS_NAV_KEY, value ? "0" : "1");
      return !value;
    });
  }

  useEffect(() => localStorage.setItem("cf-rail", rail ? "1" : "0"), [rail]);

  // 侧栏 kbd 数字 = 真实快捷键（1/2/3 跳转），输入时忽略
  useEffect(() => {
    const shortcuts = new Map(
      NAV_GROUPS.flatMap((group) => group.items)
        .filter((item) => item.kbd)
        .map((item) => [item.kbd as string, item.to]),
    );
    function onKey(event: KeyboardEvent) {
      if (event.metaKey || event.ctrlKey || event.altKey) return;
      const target = event.target as HTMLElement | null;
      if (
        target &&
        (target.tagName === "INPUT" ||
          target.tagName === "TEXTAREA" ||
          target.tagName === "SELECT" ||
          target.isContentEditable)
      ) {
        return;
      }
      const to = shortcuts.get(event.key);
      if (to) navigate(to);
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [navigate]);

  const crumb = BREADCRUMBS[location.pathname] ?? { group: "CreativeForge", label: "工作台" };

  // 构建过期自检：后端 /health 报 dist 落后于 src 时页脚角标提示强刷
  // （dev server 5173 下 dist 不参与渲染，角标无意义故跳过）
  const [buildStale, setBuildStale] = useState(false);
  useEffect(() => {
    if (window.location.port === "5173") return;
    let alive = true;
    api
      .health()
      .then((d) => {
        if (alive) setBuildStale(Boolean(d.frontend_stale));
      })
      .catch(() => {});
    return () => {
      alive = false;
    };
  }, []);

  return (
    <div className="flex h-screen overflow-hidden bg-canvas text-ink">
      {/* Sidebar (desktop) */}
      <aside
        className={cx(
          "hidden shrink-0 flex-col border-r border-line-subtle bg-gradient-to-b from-[#f0ede6] to-[#ebe8e0] transition-[width] duration-(--motion-slow) ease-standard md:flex",
          rail ? "w-16 px-2 py-3" : "w-60 p-3",
        )}
      >
        <div
          className={cx(
            "mb-2 flex items-center gap-2.5 border-b border-line-subtle pb-4",
            rail ? "justify-center px-0" : "px-2",
          )}
        >
          <span className="grid h-[30px] w-[30px] shrink-0 place-items-center rounded-[9px] bg-ink font-display text-[13px] font-black tracking-[-0.04em] text-canvas shadow-[0_6px_14px_-6px_rgba(26,24,20,.5)]">
            CF
          </span>
          {!rail && (
            <div className="min-w-0">
              <div className="truncate font-display text-[14.5px] font-black">CreativeForge</div>
              <div className="text-[9.5px] font-semibold uppercase tracking-[0.1em] text-ink-3">
                AI Asset Factory
              </div>
            </div>
          )}
        </div>

        <nav className="cf-scroll flex-1 overflow-y-auto">
          {NAV_GROUPS.map((group) => (
            <div key={group.label}>
              {!rail && (
                <div className="px-2.5 pb-1.5 pt-3.5 text-[10.5px] font-semibold uppercase tracking-[0.1em] text-ink-4">
                  {group.label}
                </div>
              )}
              {group.items.map((item) =>
                item.children ? (
                  <div key={item.to} className="relative">
                    <NavLink
                      to={item.to}
                      title={rail ? item.label : undefined}
                      className={({ isActive }) =>
                        cx(
                          "relative flex items-center gap-2.5 rounded-md py-2 text-[13.5px] transition-colors duration-(--motion-fast) ease-standard",
                          rail ? "justify-center px-0" : "px-2.5 pr-7",
                          isActive
                            ? "bg-primary-tint font-semibold text-ink"
                            : "text-ink-2 hover:bg-surface-2 hover:text-ink",
                        )
                      }
                    >
                      {({ isActive }) => (
                        <>
                          {isActive && (
                            <span className="absolute -left-3 top-2 bottom-2 w-0.5 rounded-sm bg-primary" />
                          )}
                          <Icon
                            name={item.icon}
                            className={cx("h-4 w-4 shrink-0", isActive && "text-primary")}
                          />
                          {!rail && (
                            <>
                              <span className="truncate">{item.label}</span>
                              {item.kbd && (
                                <kbd className="ml-auto rounded-xs border border-line-subtle px-1.5 font-mono text-[10px] text-ink-4">
                                  {item.kbd}
                                </kbd>
                              )}
                            </>
                          )}
                        </>
                      )}
                    </NavLink>
                    {rail ? (
                      /* 折叠态：子级以图标链接常驻（缩进半格，tooltip 提示），
                         保证窄窗口/折叠侧栏下层级仍然可见可点 */
                      <div className="mt-1 flex flex-col items-center gap-1">
                        {item.children.map((child) => (
                          <NavLink
                            key={child.to}
                            to={child.to}
                            title={child.label}
                            className={({ isActive }) =>
                              cx(
                                "grid h-8 w-8 place-items-center rounded-md transition-colors duration-(--motion-fast) ease-standard",
                                isActive
                                  ? "bg-primary-tint text-primary"
                                  : "text-ink-4 hover:bg-surface-2 hover:text-ink",
                              )
                            }
                          >
                            <Icon name={child.icon} className="h-4 w-4" />
                          </NavLink>
                        ))}
                      </div>
                    ) : (
                      <>
                        <button
                          type="button"
                          aria-label={agentsExpanded ? "收起智能体子导航" : "展开智能体子导航"}
                          aria-expanded={agentsExpanded}
                          onClick={toggleAgentsOpen}
                          className="absolute right-1.5 top-[13px] grid h-6 w-6 place-items-center rounded-md text-ink-4 transition-colors hover:bg-surface-2 hover:text-ink"
                        >
                          <Icon
                            name="chevron"
                            className={cx(
                              "h-3.5 w-3.5 transition-transform duration-(--motion-fast) ease-standard",
                              agentsExpanded && "rotate-90",
                            )}
                          />
                        </button>
                        <AnimatePresence initial={false}>
                          {agentsExpanded && (
                          <motion.div
                            initial={{ height: 0, opacity: 0 }}
                            animate={{ height: "auto", opacity: 1 }}
                            exit={{ height: 0, opacity: 0 }}
                            transition={{ duration: MOTION.fast, ease: EASE_STANDARD }}
                            className="overflow-hidden"
                          >
                            <div className="relative mt-0.5 pb-0.5">
                              <span
                                className="absolute bottom-2 left-[15px] top-0 w-px bg-line-subtle"
                                aria-hidden="true"
                              />
                              {item.children.map((child) => (
                                <NavLink
                                  key={child.to}
                                  to={child.to}
                                  className={({ isActive }) =>
                                    cx(
                                      "relative ml-[15px] flex items-center gap-2 rounded-md py-1.5 pl-6 pr-2 text-[12.5px] transition-colors duration-(--motion-fast) ease-standard",
                                      isActive
                                        ? "bg-primary-tint font-semibold text-ink"
                                        : "text-ink-2 hover:bg-surface-2 hover:text-ink",
                                    )
                                  }
                                >
                                  {({ isActive }) => (
                                    <>
                                      <span
                                        className={cx(
                                          "absolute top-1 bottom-1 w-0.5 rounded-sm",
                                          isActive ? "-left-px bg-primary" : "bg-transparent",
                                        )}
                                      />
                                      <Icon
                                        name={child.icon}
                                        className={cx(
                                          "h-3.5 w-3.5 shrink-0",
                                          isActive ? "text-primary" : "text-ink-3",
                                        )}
                                      />
                                      <span className="truncate">{child.label}</span>
                                    </>
                                  )}
                                </NavLink>
                              ))}
                            </div>
                          </motion.div>
                        )}
                        </AnimatePresence>
                      </>
                    )}
                  </div>
                ) : (
                  <NavLink
                    key={item.to}
                    to={item.to}
                    end={item.to === "/"}
                    title={rail ? item.label : undefined}
                    className={({ isActive }) =>
                      cx(
                        "relative flex items-center gap-2.5 rounded-md py-2 text-[13.5px] transition-colors duration-(--motion-fast) ease-standard",
                        rail ? "justify-center px-0" : "px-2.5",
                        isActive
                          ? "bg-primary-tint font-semibold text-ink"
                          : "text-ink-2 hover:bg-surface-2 hover:text-ink",
                      )
                    }
                  >
                    {({ isActive }) => (
                      <>
                        {isActive && (
                          <span className="absolute -left-3 top-2 bottom-2 w-0.5 rounded-sm bg-primary" />
                        )}
                        <Icon
                          name={item.icon}
                          className={cx("h-4 w-4 shrink-0", isActive && "text-primary")}
                        />
                        {!rail && (
                          <>
                            <span className="truncate">{item.label}</span>
                            {item.kbd && (
                              <kbd className="ml-auto rounded-xs border border-line-subtle px-1.5 font-mono text-[10px] text-ink-4">
                                {item.kbd}
                              </kbd>
                            )}
                          </>
                        )}
                      </>
                    )}
                  </NavLink>
                ),
              )}
            </div>
          ))}
        </nav>

        <div
          className={cx(
            "mt-auto flex items-center border-t border-line-subtle pt-3.5",
            rail ? "justify-center" : "justify-between px-2.5",
          )}
        >
          {!rail && <span className="text-[11px] text-ink-3">v1.0 · Studio</span>}
          <span className="flex gap-1.5">
            <span
              className="h-2 w-2 rounded-full bg-success shadow-[0_0_0_3px_rgba(52,211,153,.15)]"
              title="Unity"
            />
            <span
              className="h-2 w-2 rounded-full bg-success shadow-[0_0_0_3px_rgba(52,211,153,.15)]"
              title="Cocos"
            />
            <span
              className="h-2 w-2 rounded-full bg-success shadow-[0_0_0_3px_rgba(52,211,153,.15)]"
              title="Godot"
            />
          </span>
        </div>
      </aside>

      {/* Main column */}
      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex h-14 shrink-0 items-center gap-4 border-b border-line-subtle bg-[rgba(245,243,239,.86)] px-4 backdrop-blur-md md:px-6">
          <span className="flex items-center gap-2 md:hidden">
            <span className="grid h-6 w-6 place-items-center rounded-md bg-ink font-display text-[10px] font-black text-canvas">
              CF
            </span>
            <b className="text-[13px]">{crumb.label}</b>
          </span>

          <div className="hidden items-center gap-2 text-[13px] text-ink-3 md:flex">
            <span>{crumb.group}</span>
            <span className="text-ink-4">/</span>
            <b className="font-semibold text-ink">{crumb.label}</b>
          </div>

          <NavLink
            to={taskId ? "/agents" : "/"}
            className="mx-auto hidden max-w-md items-center gap-2 rounded-full border border-line-subtle bg-surface-1 px-3 py-1 text-xs text-ink-2 transition-colors hover:border-line hover:text-ink sm:flex"
          >
            <StatusDot
              tone={
                status === "idle"
                  ? "idle"
                  : status === "failed"
                    ? "failed"
                    : status === "pass"
                      ? "success"
                      : "running"
              }
            />
            {taskId ? (
              <>
                <span className="truncate">
                  {taskId} · {goal || "资产生产"}
                </span>
                <span className="font-mono text-[11px] text-ink-3">
                  {status === "pass" ? "PASS" : status === "failed" ? "FAILED" : `${progress}%`}
                </span>
              </>
            ) : (
              <span>系统就绪 · 等待任务</span>
            )}
          </NavLink>

          {asset && (
            <NavLink to="/asset" className="hidden lg:block">
              <Badge tone="primary" icon="cube">
                {asset.id}
              </Badge>
            </NavLink>
          )}

          <button
            onClick={() => setPaletteOpen(true)}
            className="ml-auto flex h-8 items-center gap-2 rounded-md border border-line-subtle bg-surface-1 px-2.5 text-xs text-ink-3 transition-colors hover:border-line hover:text-ink-2 md:ml-0"
          >
            <Icon name="search" className="h-3.5 w-3.5" />
            <span className="hidden sm:inline">命令</span>
            <kbd className="rounded-xs border border-line px-1.5 font-mono text-[10px] text-ink-2">
              ⌘K
            </kbd>
          </button>

          <button
            aria-label={rail ? "展开侧栏" : "折叠侧栏"}
            title={rail ? "展开侧栏" : "折叠侧栏"}
            onClick={() => setRail((value) => !value)}
            className="hidden h-8 w-8 place-items-center rounded-md border border-line-subtle bg-surface-1 text-ink-2 transition-colors hover:border-line hover:text-ink md:grid"
          >
            <Icon name="panel" className="h-4 w-4" />
          </button>
        </header>

        <main className="cf-scroll flex-1 overflow-y-auto pb-20 md:pb-0">
          <Outlet />
        </main>

        {/* Bottom tabs (mobile) */}
        <nav className="fixed inset-x-0 bottom-0 z-40 grid grid-cols-5 border-t border-line-subtle bg-[rgba(245,243,239,.95)] backdrop-blur-md md:hidden">
          {MOBILE_TABS.map((tab) => (
            <NavLink
              key={tab.to}
              to={tab.to}
              end={tab.to === "/"}
              className={({ isActive }) =>
                cx(
                  "flex flex-col items-center gap-1 pb-3 pt-2 text-[10px] transition-colors",
                  isActive ? "text-primary" : "text-ink-4",
                )
              }
            >
              <Icon name={tab.icon} className="h-4 w-4" />
              {tab.label}
            </NavLink>
          ))}
        </nav>
      </div>

      <CommandPalette open={paletteOpen} onOpenChange={setPaletteOpen} />
      <Toaster />
      {buildStale && (
        <div className="fixed bottom-4 right-4 z-50 max-w-xs rounded-lg border border-warning/50 bg-surface-1 px-3.5 py-2.5 text-[11.5px] leading-relaxed text-ink shadow-lg">
          <span className="font-medium text-warning">前端构建已过期</span>
          —— 源码比 dist 新，当前页面可能不是最新版本。请重新构建后强刷（Ctrl+F5）。
        </div>
      )}
    </div>
  );
}

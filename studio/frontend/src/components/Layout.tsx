import { useEffect, useState } from "react";
import { NavLink, Outlet, useLocation, useNavigate } from "react-router-dom";
import { AnimatePresence, motion } from "framer-motion";
import { EASE_STANDARD, MOTION } from "../lib/motion";
import { api } from "../api/client";
import { useAgentStore } from "../stores/agentStore";
import { useAssetStore } from "../stores/assetStore";
import { NAV_GROUPS, type NavItem } from "../lib/navigation";
import { useAssetNavigation } from "../lib/assetNavigation";
import { MobileNavigation } from "./MobileNavigation";
import { CommandPalette } from "./CommandPalette";
import { Toaster } from "./Toaster";
import { Icon } from "./icons";
import { Badge, Stamp, StatusDot, cx } from "./ui";
import { RococoCorner, RococoCrest, RococoDivider, RococoFleuron } from "./rococo/RococoOrnaments";
import { RococoBackdrop, RococoJournal, RococoLetterMark } from "./rococo/RococoBackdrop";

const AGENTS_NAV_KEY = "cf-nav-agents-open";

const MOBILE_TABS: NavItem[] = [
  { to: "/", label: "首页", icon: "spark" },
  { to: "/workspace", label: "工作台", icon: "panel" },
  { to: "/agents", label: "智能体", icon: "layers" },
  { to: "/asset", label: "资产", icon: "cube" },
  { to: "/playtest", label: "试玩", icon: "play" },
];

const BREADCRUMBS: Record<string, { group: string; label: string }> = {
  "/": { group: "CreativeForge", label: "首页" },
  "/workspace": { group: "生成", label: "工作台" },
  "/scenes": { group: "生成", label: "场景工坊" },
  "/agents": { group: "生成", label: "智能体" },
  "/history": { group: "生成 · 智能体", label: "历史记录" },
  "/playtest": { group: "试玩", label: "试玩舞台" },
  "/arcade": { group: "试玩", label: "关卡试玩场" },
  "/versions": { group: "资产库", label: "版本控制" },
  "/asset": { group: "资产库", label: "资产检查" },
  "/design": { group: "资产库", label: "设计三视图" },
  "/animation": { group: "资产库", label: "动画工作台" },
  "/export": { group: "资产库", label: "导出中心" },
  "/settings": { group: "生成", label: "模型设置" },
};

export default function Layout() {
  const [rail, setRail] = useState(
    () => localStorage.getItem("cf-rail") === "1" || window.innerWidth < 1024,
  );
  const [paletteOpen, setPaletteOpen] = useState(false);
  const [mobileOpen, setMobileOpen] = useState(false);
  const href = useAssetNavigation();
  const location = useLocation();
  const navigate = useNavigate();

  const taskId = useAgentStore((state) => state.taskId);
  const status = useAgentStore((state) => state.status);
  const progress = useAgentStore((state) => state.progress);
  const goal = useAgentStore((state) => state.goal);
  const asset = useAssetStore((state) => state.asset);
  const contextId = new URLSearchParams(location.search).get("asset") || asset?.id;

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
      if (event.metaKey || event.ctrlKey || event.altKey || paletteOpen || mobileOpen) return;
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
      if (to) navigate(href(to));
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [navigate, href, paletteOpen, mobileOpen]);

  const crumb = BREADCRUMBS[location.pathname] ?? { group: "CreativeForge", label: "首页" };

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
    <div className="flex h-dvh overflow-hidden text-ink">
      {/* 键盘用户跳过导航直达主内容 */}
      <a
        href="#cf-main"
        className="sr-only focus:not-sr-only focus:absolute focus:left-3 focus:top-3 focus:z-50 focus:rounded-md focus:border focus:border-line focus:bg-canvas focus:px-3 focus:py-2 focus:text-sm"
      >
        跳到主内容
      </a>
      {/* Sidebar (desktop) */}
      <aside
        className={cx(
          "cf-folio relative hidden shrink-0 flex-col border-r border-line transition-[width] duration-(--motion-slow) ease-standard md:flex",
          rail ? "w-16 px-2 py-3" : "w-60 p-3",
        )}
      >
        <div
          className={cx(
            "mb-2 flex items-center gap-2.5 border-b border-line-subtle pb-4",
            rail ? "justify-center px-0" : "px-2",
          )}
        >
          <span className="grid h-10 w-9 shrink-0 place-items-center">
            <RococoCrest className="h-10 w-9" />
          </span>
          {!rail && (
            <div className="min-w-0 flex-1">
              <div className="truncate font-display text-[17px] font-semibold leading-5">CreativeForge</div>
              <div className="font-mono text-[8.5px] font-medium uppercase tracking-[0.16em] text-ink-4">
                Atelier des Assets
              </div>
            </div>
          )}
          {!rail && <Stamp char="造" tone="ember" size={22} title="CreativeForge 蓝雾工坊" />}
        </div>

        <RococoDivider className="mx-auto mb-1 h-4 w-[78%] text-line-strong/65" />
        <nav className="cf-scroll relative z-10 flex-1 overflow-y-auto">
          {NAV_GROUPS.map((group) => (
            <div key={group.label} title={group.hint}>
              {!rail && (
                <div className="flex items-baseline gap-1.5 px-2.5 pb-1.5 pt-4">
                  <span className="cf-display-num text-[14px] leading-none text-ember-ink-ink">
                    {group.numeral}
                  </span>
                  <span className="font-mono text-[9px] font-medium uppercase tracking-[0.14em] text-ink-4">
                    {group.label}
                  </span>
                  <RococoFleuron className="ml-0.5 h-3 w-6 shrink-0 text-line-strong/80" />
                  <span className="ml-1 h-px flex-1 bg-line" aria-hidden="true" />
                </div>
              )}
              {group.items.map((item) =>
                item.children ? (
                  <div key={item.to} className="relative">
                    <NavLink
                      to={href(item.to)}
                      title={rail ? item.label : undefined}
                      className={({ isActive }) =>
                        cx(
                          "relative flex items-center gap-2.5 rounded-md py-2 text-[13.5px] transition-colors duration-(--motion-fast) ease-standard",
                          rail ? "justify-center px-0" : "px-2.5 pr-7",
                          isActive
                            ? "bg-ember-tint font-semibold text-ink"
                            : "text-ink-2 hover:bg-paper/70 hover:text-ink",
                        )
                      }
                    >
                      {({ isActive }) => (
                        <>
                          {isActive && (
                            <span className="absolute left-1 top-1/2 h-1.5 w-1.5 -translate-y-1/2 rotate-45 bg-danger" />
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
                            to={href(child.to)}
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
                                  to={href(child.to)}
                                  className={({ isActive }) =>
                                    cx(
                                      "relative ml-[15px] flex items-center gap-2 rounded-md py-1.5 pl-6 pr-2 text-[12.5px] transition-colors duration-(--motion-fast) ease-standard",
                                      isActive
                                        ? "bg-ember-tint font-semibold text-ink"
                                        : "text-ink-2 hover:bg-paper/70 hover:text-ink",
                                    )
                                  }
                                >
                                  {({ isActive }) => (
                                    <>
                                      <span
                                        className={cx(
                                          "absolute left-2 top-1/2 h-1 w-1 -translate-y-1/2 rotate-45",
                                          isActive ? "bg-danger" : "bg-transparent",
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
                    to={href(item.to)}
                    end={item.to === "/"}
                    title={rail ? item.label : undefined}
                    className={({ isActive }) =>
                      cx(
                        "relative flex items-center gap-2.5 rounded-md py-2 text-[13.5px] transition-colors duration-(--motion-fast) ease-standard",
                        rail ? "justify-center px-0" : "px-2.5",
                        isActive
                          ? "bg-ember-tint font-semibold text-ink"
                          : "text-ink-2 hover:bg-paper/70 hover:text-ink",
                      )
                    }
                  >
                    {({ isActive }) => (
                      <>
                        {isActive && (
                          <span className="absolute left-1 top-1/2 h-1.5 w-1.5 -translate-y-1/2 rotate-45 bg-danger" />
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

        {/* 纸面角饰：手账信笺与旧书（仅展开态、纯装饰） */}
        {!rail && <RococoLetterMark />}
        {!rail && (
          <div className="pointer-events-none absolute bottom-0 left-0 z-0 h-[168px] w-[132px] overflow-hidden" aria-hidden="true">
            <RococoJournal />
          </div>
        )}

        <RococoDivider className="mx-auto mt-3 h-4 w-[78%] text-line-strong/65" />
        <div
          className={cx(
            "relative z-10 flex items-center border-t border-line-subtle pt-3.5",
            rail ? "justify-center" : "justify-between px-2.5",
          )}
        >
          {!rail && <span className="font-mono text-[9px] uppercase tracking-[0.1em] text-ink-4">MMXXVI · Salon Bleu</span>}
          <span className="flex items-center gap-2" title="Unity · Cocos · Godot 引擎通道就绪">
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
            {!rail && (
              <span className="font-mono text-[9.5px] uppercase tracking-[0.08em] text-ink-4">
                引擎就绪
              </span>
            )}
          </span>
        </div>
      </aside>

      {/* Main column */}
      <div className="relative flex min-w-0 flex-1 flex-col">
        {/* 纸面背景层：城堡 / 首字母水印 / 四角花饰（不随内容滚动） */}
        <div className="pointer-events-none absolute inset-0 z-0 overflow-hidden" aria-hidden="true">
          <RococoBackdrop />
          <RococoCorner className="absolute right-3 top-14 hidden h-36 w-36 rotate-90 text-line/35 lg:block" />
          <RococoCorner className="absolute bottom-3 left-3 hidden h-32 w-32 rotate-180 text-line/25 lg:block" />
        </div>
        <header className="flex h-14 shrink-0 items-center gap-4 border-b border-line bg-paper/95 px-4 md:px-6">
          <span className="flex items-center gap-2 md:hidden">
            <RococoCrest className="h-7 w-6 shrink-0" />
            <b className="text-[13px]">{crumb.label}</b>
          </span>

          <div className="hidden items-center gap-2 text-[13px] text-ink-3 md:flex">
            <RococoFleuron className="h-4 w-7 shrink-0 text-ember-ink/70" />
            <span>{crumb.group}</span>
            <span className="text-ink-4">/</span>
            <b className="font-semibold text-ink">{crumb.label}</b>
          </div>

          <NavLink
            to={href(taskId ? "/agents" : "/workspace")}
            className="mx-auto hidden max-w-md items-center gap-2 rounded-sm border border-line bg-canvas px-3 py-1.5 text-xs text-ink-2 transition-colors hover:border-line-strong hover:bg-surface-1 hover:text-ink sm:flex"
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

          {contextId && (
            <NavLink to={href("/asset")} className="hidden lg:block">
              <Badge tone="primary" icon="cube">
                {contextId}
              </Badge>
            </NavLink>
          )}

          <button
            onClick={() => setPaletteOpen(true)}
            className="ml-auto flex h-8 items-center gap-2 rounded-sm border border-line bg-paper px-2.5 text-xs text-ink-3 transition-colors hover:border-line-strong hover:bg-surface-1 hover:text-ink md:ml-0"
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
            className="hidden h-8 w-8 place-items-center rounded-sm border border-line bg-paper text-ink-2 transition-colors hover:border-line-strong hover:bg-surface-1 hover:text-ink md:grid"
          >
            <Icon name="panel" className="h-4 w-4" />
          </button>
        </header>

        <main
          id="cf-main"
          tabIndex={-1}
          className="cf-scroll relative min-h-0 flex-1 overflow-y-auto pb-[calc(5rem+env(safe-area-inset-bottom))] outline-none md:pb-0"
        >
          {/* 路由进入过渡：CSS 动画（key 变化触发重放，query 变化不重挂载） */}
          <div key={location.pathname} className="relative z-10 cf-page-enter">
            <Outlet />
          </div>
        </main>

        {/* Bottom tabs (mobile) */}
        <nav aria-label="移动端主导航" className="fixed inset-x-0 bottom-0 z-40 grid grid-cols-6 border-t border-line bg-paper/95 md:hidden" style={{ paddingBottom: "env(safe-area-inset-bottom)" }}>
          {MOBILE_TABS.map((tab) => (
            <NavLink
              key={tab.to}
              to={href(tab.to)}
              end={tab.to === "/"}
              className={({ isActive }) =>
                cx(
                  "relative flex min-h-11 flex-col items-center gap-1 pb-3 pt-2 text-[10px] transition-colors duration-(--motion-fast) ease-standard",
                  isActive ? "text-ink" : "text-ink-4",
                )
              }
            >
              {({ isActive }) => (
                <>
                  {/* 激活指示器：色觉之外的冗余状态线索 */}
                  <span
                    className={cx(
                      "absolute top-0 h-0.5 w-7 rounded-full bg-danger transition-opacity duration-(--motion-fast) ease-standard",
                      isActive ? "opacity-100" : "opacity-0",
                    )}
                    aria-hidden="true"
                  />
                  <Icon name={tab.icon} className="h-4 w-4" />
                  {tab.label}
                </>
              )}
            </NavLink>
          ))}
          <button type="button" aria-label="更多功能" aria-haspopup="dialog" aria-expanded={mobileOpen}
            onClick={() => setMobileOpen(true)} className="flex min-h-11 flex-col items-center gap-1 pb-3 pt-2 text-[10px] text-ink-2">
            <Icon name="panel" className="h-4 w-4" />更多
          </button>
        </nav>
      </div>
      <MobileNavigation open={mobileOpen} onClose={() => setMobileOpen(false)} />

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

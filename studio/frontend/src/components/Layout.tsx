import { useEffect, useState } from "react";
import { NavLink, Outlet, useLocation, useNavigate } from "react-router-dom";
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
}

const NAV_GROUPS: Array<{ label: string; items: NavItem[] }> = [
  {
    label: "生产",
    items: [
      { to: "/", label: "创作工作台", icon: "spark", kbd: "1" },
      { to: "/workspace", label: "经典工作台", icon: "panel" },
      { to: "/agents", label: "智能体", icon: "layers", kbd: "2" },
      { to: "/history", label: "历史记录", icon: "clock" },
      { to: "/batch", label: "批量生产线", icon: "package" },
      { to: "/playtest", label: "试玩舞台", icon: "film" },
    ],
  },
  {
    label: "资产",
    items: [
      { to: "/asset", label: "资产检查", icon: "cube", kbd: "3" },
      { to: "/design", label: "设计三视图", icon: "layers" },
      { to: "/pixel", label: "像素工作台", icon: "grid" },
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
  "/": { group: "生产", label: "创作工作台" },
  "/creative": { group: "生产", label: "创作工作台" },
  "/workspace": { group: "生产", label: "经典工作台" },
  "/agents": { group: "生产", label: "智能体指挥中心" },
  "/history": { group: "生产", label: "历史记录" },
  "/batch": { group: "生产", label: "批量生产线" },
  "/playtest": { group: "生产", label: "试玩舞台" },
  "/versions": { group: "资产", label: "版本控制中心" },
  "/asset": { group: "资产", label: "资产检查器" },
  "/design": { group: "资产", label: "角色设计三视图" },
  "/pixel": { group: "资产", label: "像素工作台" },
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

  const taskTone = status === "failed" ? "danger" : status === "pass" ? "success" : "primary";

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
              {group.items.map((item) => (
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
              ))}
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
    </div>
  );
}

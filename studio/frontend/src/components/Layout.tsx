import { NavLink, Outlet } from "react-router-dom";

const NAV = [
  { to: "/", label: "工作台", sub: "Workspace" },
  { to: "/agents", label: "智能体", sub: "Agent Graph" },
  { to: "/asset", label: "资产", sub: "Inspector" },
  { to: "/pixel", label: "像素", sub: "Pixel Studio" },
  { to: "/animation", label: "动画", sub: "Animation" },
  { to: "/benchmark", label: "基准", sub: "Benchmark" },
  { to: "/export", label: "导出", sub: "Export" },
];

export default function Layout() {
  return (
    <div className="flex h-screen overflow-hidden bg-zinc-950 text-zinc-100">
      <aside className="flex w-56 shrink-0 flex-col border-r border-zinc-800 bg-zinc-900/60">
        <div className="border-b border-zinc-800 px-5 py-5">
          <div className="pixel-title text-sm font-bold text-sky-400">
            CreativeForge
          </div>
          <div className="mt-1 text-xs text-zinc-400">AI Game Asset Factory</div>
        </div>
        <nav className="flex-1 space-y-1 px-3 py-4">
          {NAV.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.to === "/"}
              className={({ isActive }) =>
                `block rounded-lg px-3 py-2 text-sm transition-colors ${
                  isActive
                    ? "bg-white/10 font-semibold text-white"
                    : "text-zinc-400 hover:bg-zinc-800/70 hover:text-zinc-200"
                }`
              }
            >
              <span className="font-medium">{item.label}</span>
              <span className="ml-2 text-[10px] uppercase tracking-wider opacity-60">
                {item.sub}
              </span>
            </NavLink>
          ))}
        </nav>
        <div className="border-t border-zinc-800 px-5 py-3 text-[10px] text-zinc-500">
          v1.0 · Phase 8 Studio
        </div>
      </aside>
      <main className="flex-1 overflow-y-auto">
        <Outlet />
      </main>
    </div>
  );
}

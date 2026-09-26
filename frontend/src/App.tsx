import { useEffect, useRef, useState } from "react";
import gsap from "gsap";
import AgentTimeline from "./components/AgentTimeline";
import AssetViewer from "./components/AssetViewer";
import CreationStudio from "./components/CreationStudio";
import Home from "./components/Home";

export type View = "home" | "studio" | "timeline" | "viewer";

function stored(key: string): string | undefined {
  return window.localStorage.getItem(key) ?? undefined;
}

const NAV: { key: View; label: string }[] = [
  { key: "home", label: "工作台" },
  { key: "studio", label: "创作" },
  { key: "timeline", label: "时间线" },
  { key: "viewer", label: "资产" },
];

export default function App() {
  const [view, setView] = useState<View>("home");
  const [lastTaskId, setLastTaskId] = useState<string | undefined>(
    stored("cf.lastTaskId"),
  );
  const [lastAssetId, setLastAssetId] = useState<string | undefined>(
    stored("cf.lastAssetId"),
  );
  const main = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (lastTaskId) window.localStorage.setItem("cf.lastTaskId", lastTaskId);
    if (lastAssetId) window.localStorage.setItem("cf.lastAssetId", lastAssetId);
  }, [lastTaskId, lastAssetId]);

  useEffect(() => {
    if (!main.current) return;
    gsap.fromTo(
      main.current,
      { y: 14, opacity: 0 },
      { y: 0, opacity: 1, duration: 0.5, ease: "power2.out" },
    );
  }, [view]);

  const openTask = (taskId: string) => {
    setLastTaskId(taskId);
    setView("timeline");
  };
  const openAsset = (assetId: string) => {
    setLastAssetId(assetId);
    setView("viewer");
  };

  return (
    <div className="min-h-screen bg-paper">
      <header className="sticky top-0 z-10 border-b border-line bg-paper/90 backdrop-blur">
        <div className="mx-auto flex h-14 max-w-6xl items-center px-6">
          <button
            onClick={() => setView("home")}
            className="flex items-center gap-2 text-ink"
          >
            <svg viewBox="0 0 24 24" className="h-5 w-5" aria-hidden>
              <path
                d="M4 18 L10 18 L9 21 L3 21 Z M6 16 L12 6 L15 6 L20 12 L16 16 Z"
                fill="currentColor"
              />
            </svg>
            <span className="text-[15px] font-semibold tracking-wide">
              CreativeForge
            </span>
          </button>

          <nav className="absolute left-1/2 flex -translate-x-1/2 items-center gap-8">
            {NAV.map((item) => {
              const active = view === item.key;
              return (
                <button
                  key={item.key}
                  onClick={() => setView(item.key)}
                  className={`relative py-1 text-sm transition-colors ${
                    active
                      ? "font-medium text-ink"
                      : "text-mute hover:text-ink"
                  }`}
                >
                  {item.label}
                  <span
                    className={`absolute -bottom-1 left-1/2 h-[2px] w-6 -translate-x-1/2 bg-ink transition-opacity ${
                      active ? "opacity-100" : "opacity-0"
                    }`}
                  />
                </button>
              );
            })}
          </nav>

          <div className="ml-auto flex items-center gap-2">
            <span className="grid h-7 w-7 place-items-center rounded-full bg-ink text-[11px] font-medium text-paper">
              CF
            </span>
            <span className="text-sm text-ink-2">forge</span>
          </div>
        </div>
      </header>

      <main ref={main} className="mx-auto max-w-6xl px-6 pb-24 pt-8">
        {view === "home" && <Home onOpen={setView} />}
        {view === "studio" && (
          <CreationStudio
            onCreated={(taskId, assetId) => {
              if (assetId) setLastAssetId(assetId);
              openTask(taskId);
            }}
            onOpenAsset={openAsset}
          />
        )}
        {view === "timeline" && (
          <AgentTimeline
            taskId={lastTaskId}
            onOpenAsset={openAsset}
            onOpenStudio={() => setView("studio")}
          />
        )}
        {view === "viewer" && (
          <AssetViewer assetId={lastAssetId} onOpenAsset={openAsset} />
        )}
      </main>
    </div>
  );
}

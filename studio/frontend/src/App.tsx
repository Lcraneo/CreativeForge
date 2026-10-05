import { Suspense, lazy } from "react";
import { Route, Routes } from "react-router-dom";
import ErrorBoundary from "./components/ErrorBoundary";
import Layout from "./components/Layout";

// 路由级代码分割：每个页面独立 chunk，首屏只加载当前路由
const AgentDashboard = lazy(() => import("./pages/AgentDashboard"));
const AnimationStudio = lazy(() => import("./pages/AnimationStudio"));
const AssetInspector = lazy(() => import("./pages/AssetInspector"));
const BenchmarkCenter = lazy(() => import("./pages/BenchmarkCenter"));
const ExportCenter = lazy(() => import("./pages/ExportCenter"));
const HistoryCenter = lazy(() => import("./pages/HistoryCenter"));
const DesignCenter = lazy(() => import("./pages/DesignCenter"));
const SettingsCenter = lazy(() => import("./pages/SettingsCenter"));
const BatchCenter = lazy(() => import("./pages/BatchCenter"));
const PlaytestStage = lazy(() => import("./pages/PlaytestStage"));
const ShowcaseStudio = lazy(() => import("./pages/ShowcaseStudio"));
const VersionCenter = lazy(() => import("./pages/VersionCenter"));
const Workspace = lazy(() => import("./pages/Workspace"));
const TechnologyCenter = lazy(() => import("./pages/TechnologyCenter"));

function PageFallback() {
  return (
    <div className="grid min-h-[60vh] place-items-center text-xs tracking-[0.16em] text-ink-4">
      加载中…
    </div>
  );
}

export default function App() {
  return (
    <ErrorBoundary>
      <Suspense fallback={<PageFallback />}>
        <Routes>
          <Route element={<Layout />}>
            <Route index element={<Workspace />} />
            <Route path="workspace" element={<Workspace />} />
            <Route path="agents" element={<AgentDashboard />} />
            <Route path="history" element={<HistoryCenter />} />
            <Route path="batch" element={<BatchCenter />} />
            <Route path="versions" element={<VersionCenter />} />
            <Route path="asset" element={<AssetInspector />} />
            <Route path="design" element={<DesignCenter />} />
            <Route path="settings" element={<SettingsCenter />} />
            <Route path="animation" element={<AnimationStudio />} />
            <Route path="playtest" element={<PlaytestStage />} />
            <Route path="showcase" element={<ShowcaseStudio />} />
            <Route path="benchmark" element={<BenchmarkCenter />} />
            <Route path="export" element={<ExportCenter />} />
            <Route path="technology" element={<TechnologyCenter />} />
          </Route>
        </Routes>
      </Suspense>
    </ErrorBoundary>
  );
}

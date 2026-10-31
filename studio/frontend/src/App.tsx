import { Suspense, lazy } from "react";
import { Navigate, Route, Routes } from "react-router-dom";
import ErrorBoundary from "./components/ErrorBoundary";
import Layout from "./components/Layout";
import { OpeningSequence } from "./components/opening/OpeningSequence";

// 路由级代码分割：每个页面独立 chunk，首屏只加载当前路由
const Home = lazy(() => import("./pages/Home"));
const AgentDashboard = lazy(() => import("./pages/AgentDashboard"));
const AnimationStudio = lazy(() => import("./pages/AnimationStudio"));
const AssetInspector = lazy(() => import("./pages/AssetInspector"));
const ExportCenter = lazy(() => import("./pages/ExportCenter"));
const HistoryCenter = lazy(() => import("./pages/HistoryCenter"));
const DesignCenter = lazy(() => import("./pages/DesignCenter"));
const SettingsCenter = lazy(() => import("./pages/SettingsCenter"));
const SceneStudio = lazy(() => import("./pages/SceneStudio"));
const PlaytestStage = lazy(() => import("./pages/PlaytestStage"));
const Playtest3DPage = lazy(() => import("./pages/playtest3d/Playtest3DPage"));
const ArcadeStage = lazy(() => import("./pages/ArcadeStage"));
const VersionCenter = lazy(() => import("./pages/VersionCenter"));
const Workspace = lazy(() => import("./pages/Workspace"));

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
      <OpeningSequence />
      <Suspense fallback={<PageFallback />}>
        <Routes>
          <Route element={<Layout />}>
            <Route index element={<Home />} />
            <Route path="workspace" element={<Workspace />} />
            <Route path="agents" element={<AgentDashboard />} />
            <Route path="history" element={<HistoryCenter />} />
            <Route path="versions" element={<VersionCenter />} />
            <Route path="asset" element={<AssetInspector />} />
            <Route path="design" element={<DesignCenter />} />
            <Route path="settings" element={<SettingsCenter />} />
            <Route path="animation" element={<AnimationStudio />} />
            <Route path="scenes" element={<SceneStudio />} />
            <Route path="playtest" element={<PlaytestStage />} />
            <Route path="playtest-3d" element={<Playtest3DPage />} />
            <Route path="arcade" element={<ArcadeStage />} />
            <Route path="export" element={<ExportCenter />} />
            {/* 旧书签兼容重定向 */}
            <Route path="batch" element={<Navigate to="/" replace />} />
            <Route path="benchmark" element={<Navigate to="/" replace />} />
            <Route path="technology" element={<Navigate to="/" replace />} />
            <Route path="showcase" element={<Navigate to="/playtest" replace />} />
          </Route>
        </Routes>
      </Suspense>
    </ErrorBoundary>
  );
}

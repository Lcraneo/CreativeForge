import { Route, Routes } from "react-router-dom";
import Layout from "./components/Layout";
import AgentDashboard from "./pages/AgentDashboard";
import AnimationStudio from "./pages/AnimationStudio";
import AssetInspector from "./pages/AssetInspector";
import BenchmarkCenter from "./pages/BenchmarkCenter";
import ExportCenter from "./pages/ExportCenter";
import HistoryCenter from "./pages/HistoryCenter";
import DesignCenter from "./pages/DesignCenter";
import SettingsCenter from "./pages/SettingsCenter";
import PixelStudio from "./pages/PixelStudio";
import Workspace from "./pages/Workspace";
import TechnologyCenter from "./pages/TechnologyCenter";

export default function App() {
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route index element={<Workspace />} />
        <Route path="agents" element={<AgentDashboard />} />
        <Route path="history" element={<HistoryCenter />} />
        <Route path="asset" element={<AssetInspector />} />
        <Route path="design" element={<DesignCenter />} />
        <Route path="settings" element={<SettingsCenter />} />
        <Route path="pixel" element={<PixelStudio />} />
        <Route path="animation" element={<AnimationStudio />} />
        <Route path="benchmark" element={<BenchmarkCenter />} />
        <Route path="export" element={<ExportCenter />} />
        <Route path="technology" element={<TechnologyCenter />} />
      </Route>
    </Routes>
  );
}

import { useEffect, useMemo, useState } from "react";
import { motion } from "framer-motion";
import { useAssetLoader } from "../stores/assetStore";
import { Badge, Card, ScoreBar } from "../components/ui";

/** Frame card: stick figure posed by phase (FAlign 对齐结果的可视化). */
function FrameFigure({ phase, active }: { phase: number; active: boolean }) {
  const swing = Math.sin(phase * Math.PI * 2) * 10;
  const arm = Math.cos(phase * Math.PI * 2) * 22;
  return (
    <svg viewBox="0 0 64 80" className={`h-20 w-16 ${active ? "opacity-100" : "opacity-60"}`}>
      {/* staff */}
      <line x1={46 + swing / 2} y1={14} x2={50 + swing} y2={66} stroke="#a16207" strokeWidth="2.5" />
      <circle cx={46 + swing / 2} cy={12} r={3.5} fill="#fb923c" />
      {/* head */}
      <circle cx={32} cy={16} r={9} fill="#f4d58d" />
      <path d={`M23 14 L32 4 L41 14 Z`} fill="#38bdf8" />
      {/* body */}
      <line x1="32" y1="25" x2="32" y2="50" stroke="#38bdf8" strokeWidth="7" strokeLinecap="round" />
      {/* arms */}
      <line x1="32" y1="32" x2="44" y2={34 + arm / 2} stroke="#f4d58d" strokeWidth="3.4" strokeLinecap="round" />
      <line x1="32" y1="32" x2="20" y2={34 - arm / 2} stroke="#f4d58d" strokeWidth="3.4" strokeLinecap="round" />
      {/* legs */}
      <line x1="32" y1="50" x2={26 - swing / 3} y2="70" stroke="#3f3f46" strokeWidth="4" strokeLinecap="round" />
      <line x1="32" y1="50" x2={38 + swing / 3} y2="70" stroke="#3f3f46" strokeWidth="4" strokeLinecap="round" />
      {/* anchor point (root) — stable after FAlign */}
      {active && <circle cx="32" cy="72" r="2.4" fill="#34d399" />}
    </svg>
  );
}

export default function AnimationStudio() {
  const asset = useAssetLoader();
  const frames = asset?.animation?.frames ?? [];
  const phases = asset?.animation?.phase?.phase;
  const [current, setCurrent] = useState(0);
  const [playing, setPlaying] = useState(true);

  useEffect(() => {
    if (!playing || frames.length === 0) return;
    const fps = asset?.animation?.fps ?? 12;
    const timer = setInterval(
      () => setCurrent((index) => (index + 1) % frames.length),
      Math.max(60, 1000 / fps / 2),
    );
    return () => clearInterval(timer);
  }, [playing, frames.length, asset?.animation?.fps]);

  const rootTrack = asset?.animation?.motion?.root_track ?? [];
  const corrections = asset?.animation?.motion?.corrections ?? [];
  const trackPath = useMemo(() => {
    if (rootTrack.length === 0) return "";
    const width = 260;
    const height = 70;
    return rootTrack
      .map((point, index) => {
        const x = (index / Math.max(1, rootTrack.length - 1)) * width;
        const y = height / 2 - point.dx * 6;
        return `${index === 0 ? "M" : "L"}${x.toFixed(1)},${y.toFixed(1)}`;
      })
      .join(" ");
  }, [rootTrack]);

  if (frames.length === 0) {
    return (
      <div className="mx-auto max-w-3xl px-8 py-16 text-center text-sm text-zinc-400">
        暂无动画数据，请先生成一个带动画的资产。
      </div>
    );
  }

  const quality = asset?.quality?.animation;

  return (
    <div className="mx-auto max-w-5xl px-6 py-6">
      <header className="mb-5 flex items-center justify-between">
        <div>
          <h1 className="pixel-title text-sm font-semibold text-zinc-200">
            Animation Studio
          </h1>
          <p className="mt-1 text-xs text-zinc-500">
            FAlign 切帧对齐：锚点检测 → 运动相位对齐 → 根运动纠偏 → 时序一致性
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Badge tone="blue">{asset?.animation?.action}</Badge>
          <Badge>{frames.length} frames</Badge>
          <Badge>{asset?.animation?.fps} fps</Badge>
          {asset?.animation?.motion?.drift_corrected && (
            <Badge tone="green">drift corrected</Badge>
          )}
        </div>
      </header>

      <div className="grid grid-cols-[1fr_320px] gap-4">
        <div className="space-y-4">
          <Card
            title="动作预览 / Motion Preview"
            right={
              <button
                onClick={() => setPlaying((value) => !value)}
                className="rounded-lg bg-cyan-400 px-3 py-1 text-xs font-semibold text-zinc-950 hover:bg-cyan-300"
              >
                {playing ? "暂停" : "播放"}
              </button>
            }
          >
            <div className="flex items-center justify-center rounded-lg border border-zinc-800 bg-zinc-950 py-6">
              <motion.div key={current} initial={{ scale: 0.96 }} animate={{ scale: 1 }}>
                <FrameFigure
                  phase={phases?.[current] ?? current / Math.max(1, frames.length - 1)}
                  active
                />
              </motion.div>
            </div>
          </Card>

          <Card title="帧时间轴 / Frame Timeline">
            <div className="flex gap-2 overflow-x-auto pb-2">
              {frames.map((frame, index) => (
                <button
                  key={frame.id}
                  onClick={() => {
                    setPlaying(false);
                    setCurrent(index);
                  }}
                  className={`flex flex-col items-center rounded-lg border px-2 py-2 transition-colors ${
                    index === current
                      ? "border-cyan-400/70 bg-cyan-400/10"
                      : "border-zinc-800 hover:border-zinc-600"
                  }`}
                >
                  <FrameFigure
                    phase={phases?.[index] ?? index / Math.max(1, frames.length - 1)}
                    active={index === current}
                  />
                  <span className="mt-1 font-mono text-[10px] text-zinc-500">
                    #{frame.id}
                  </span>
                </button>
              ))}
            </div>
          </Card>

          <Card title="根运动轨迹 / Root Motion（漂移 → 纠偏）">
            <svg viewBox="0 0 260 70" className="w-full">
              <line x1="0" y1="35" x2="260" y2="35" stroke="#27272a" strokeDasharray="4 4" />
              <path d={trackPath} fill="none" stroke="#f87171" strokeWidth="2" />
              {rootTrack.map((_, index) => {
                const corrected = corrections[index];
                if (!corrected) return null;
                const x = (index / Math.max(1, rootTrack.length - 1)) * 260;
                const y = 35 - (rootTrack[index].dx + corrected.dx) * 6;
                return <circle key={index} cx={x} cy={y} r="3" fill="#34d399" />;
              })}
            </svg>
            <div className="mt-2 flex gap-4 text-[11px] text-zinc-500">
              <span><span className="text-red-400">—</span> 对齐前（漂移）</span>
              <span><span className="text-emerald-400">●</span> FAlign 纠偏后</span>
            </div>
          </Card>
        </div>

        <Card title="质量评分 / Quality">
          {quality ? (
            <div className="space-y-3">
              <ScoreBar label="Anchor 锚点稳定" value={quality.anchor_score ?? 0} />
              <ScoreBar label="Motion 根运动" value={quality.motion_score ?? 0} />
              <ScoreBar label="Temporal 时序平滑" value={quality.temporal_score ?? 0} />
              <ScoreBar label="Overall" value={quality.overall ?? 0} threshold={0.85} />
            </div>
          ) : (
            <p className="text-xs text-zinc-500">暂无评分</p>
          )}
          <div className="mt-4 space-y-2 text-xs text-zinc-400">
            <p>
              <span className="text-emerald-400">✓</span> 锚点检测：root / feet /
              center / head 四点稳定
            </p>
            <p>
              <span className="text-emerald-400">✓</span> 相位对齐：
              {asset?.animation?.phase?.phase.map((p) => p.toFixed(2)).join(" / ")}
            </p>
            <p>
              <span className="text-emerald-400">✓</span> 漂移纠偏：
              {corrections.length} 帧校正回 frame-0 根位置
            </p>
          </div>
        </Card>
      </div>
    </div>
  );
}

import { useEffect, useMemo, useState } from "react";
import { motion } from "framer-motion";
import { useAssetLoader } from "../stores/assetStore";
import { Badge, Button, Card, PageHeader, ScoreBar, cx } from "../components/ui";
import { Icon } from "../components/icons";
import { FrameFigure } from "../components/FrameFigure";

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

  useEffect(() => {
    function onKey(event: KeyboardEvent) {
      if (event.code === "Space") {
        event.preventDefault();
        setPlaying((value) => !value);
      }
      if (event.key === "ArrowLeft") {
        setPlaying(false);
        setCurrent((index) => Math.max(0, index - 1));
      }
      if (event.key === "ArrowRight") {
        setPlaying(false);
        setCurrent((index) => Math.min(frames.length - 1, index + 1));
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [frames.length]);

  const rootTrack = asset?.animation?.motion?.root_track ?? [];
  const corrections = asset?.animation?.motion?.corrections ?? [];
  const trackPath = useMemo(() => {
    if (rootTrack.length === 0) return "";
    const width = 640;
    const height = 90;
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
      <div className="mx-auto w-full max-w-[1440px] px-4 py-5 md:px-6">
        <Card>
          <PageHeader
            overline="Animation Studio"
            title="动画工作台"
            description="暂无动画数据，请先生成一个带动画的资产。"
          />
        </Card>
      </div>
    );
  }

  const quality = asset?.quality?.animation;

  return (
    <div className="mx-auto flex w-full max-w-[1440px] flex-col gap-5 px-4 py-5 md:px-6">
      <PageHeader
        overline="Animation Studio"
        title="动画工作台"
        description="FAlign 切帧对齐：锚点检测 → 运动相位对齐 → 根运动纠偏 → 时序一致性"
        actions={
          <>
            <Badge tone="falign">{asset?.animation?.action}</Badge>
            <Badge tone="neutral">{frames.length} frames</Badge>
            <Badge tone="neutral">{asset?.animation?.fps} fps</Badge>
            {asset?.animation?.motion?.drift_corrected && (
              <Badge tone="success" icon="check">
                drift corrected
              </Badge>
            )}
          </>
        }
      />

      <div className="grid grid-cols-12 gap-5">
        <div className="col-span-12 flex flex-col gap-5 xl:col-span-8">
          <Card
            title="动作预览 Motion Preview"
            icon="play"
            iconClassName="text-falign"
            right={
              <Button
                variant="secondary"
                size="sm"
                icon={playing ? "pause" : "play"}
                onClick={() => setPlaying((value) => !value)}
              >
                {playing ? "暂停" : "播放"}
              </Button>
            }
          >
            <div className="flex h-[230px] items-center justify-center rounded-[10px] border border-line-subtle bg-[radial-gradient(300px_160px_at_50%_40%,rgba(124,92,196,.10),transparent_70%),#f1efe9]">
              <motion.div
                key={current}
                initial={{ scale: 0.96, opacity: 0.7 }}
                animate={{ scale: 1, opacity: 1 }}
                transition={{ duration: 0.18 }}
              >
                <FrameFigure
                  phase={phases?.[current] ?? current / Math.max(1, frames.length - 1)}
                  active
                  className="h-44 w-36"
                />
              </motion.div>
            </div>
            <div className="mt-2.5 flex items-center gap-3 text-[11px] text-ink-3">
              <span>
                空格 播放/暂停 · ←→ 逐帧 · 当前 #{frames[current]?.id}
              </span>
            </div>
          </Card>

          <Card
            title="帧时间轴 Frame Timeline"
            icon="film"
            iconClassName="text-falign"
            right={<Badge tone="neutral">当前 #{frames[current]?.id}</Badge>}
          >
            <div className="cf-scroll flex gap-2.5 overflow-x-auto pb-1">
              {frames.map((frame, index) => (
                <button
                  key={frame.id}
                  onClick={() => {
                    setPlaying(false);
                    setCurrent(index);
                  }}
                  className={cx(
                    "flex w-[92px] shrink-0 flex-col items-center rounded-[10px] border p-2 transition-all duration-150 ease-standard",
                    index === current
                      ? "-translate-y-0.5 border-falign/60 bg-falign/[.08]"
                      : "border-line-subtle bg-surface-1 hover:border-line",
                  )}
                >
                  <FrameFigure
                    phase={phases?.[index] ?? index / Math.max(1, frames.length - 1)}
                    active={index === current}
                    className="h-16 w-14"
                  />
                  <span className="mt-1 font-mono text-[10px] text-ink-4">
                    #{frame.id} · {(phases?.[index] ?? index / Math.max(1, frames.length - 1)).toFixed(2)}
                  </span>
                </button>
              ))}
            </div>
          </Card>

          <Card
            title="根运动轨迹 Root Motion（漂移 → 纠偏）"
            icon="activity"
            iconClassName="text-falign"
            right={<Badge tone="success">0.00 px/frame</Badge>}
          >
            <svg viewBox="0 0 640 90" className="h-[90px] w-full">
              <line x1="0" y1="45" x2="640" y2="45" stroke="#b9b3a5" strokeDasharray="5 5" />
              <path d={trackPath} fill="none" stroke="#a94f3d" strokeWidth="2" />
              {rootTrack.map((point, index) => {
                const corrected = corrections[index];
                const x = (index / Math.max(1, rootTrack.length - 1)) * 640;
                const y = 45 - (point.dx + (corrected?.dx ?? 0)) * 6;
                return (
                  <circle key={index} cx={x} cy={y} r="3.5" fill="#3e7d5a">
                    <title>{`frame ${index} · dx ${point.dx.toFixed(2)}`}</title>
                  </circle>
                );
              })}
            </svg>
            <div className="mt-1.5 flex gap-4 text-[11px] text-ink-3">
              <span>
                <span className="text-danger">—</span> 对齐前（漂移）
              </span>
              <span>
                <span className="text-success">●</span> FAlign 纠偏后（根位置稳定）
              </span>
            </div>
          </Card>
        </div>

        <div className="col-span-12 flex flex-col gap-5 xl:col-span-4">
          <Card
            title="质量评分 Quality"
            icon="gauge"
            iconClassName="text-falign"
            right={<Badge tone={(quality?.overall ?? 0) >= 0.85 ? "success" : "warning"}>{(quality?.overall ?? 0) >= 0.85 ? "PASS" : "RETRY"}</Badge>}
          >
            <div className="space-y-3.5">
              <ScoreBar label="Anchor 锚点稳定" value={quality?.anchor_score ?? 0} tone="falign" />
              <ScoreBar label="Motion 根运动" value={quality?.motion_score ?? 0} tone="gimport" />
              <ScoreBar label="Temporal 时序平滑" value={quality?.temporal_score ?? 0} tone="falign" />
              <ScoreBar
                label="Overall · 阈值 0.85"
                value={quality?.overall ?? 0}
                threshold={0.85}
              />
            </div>
          </Card>

          <Card title="对齐详情" icon="check">
            <ul className="space-y-2.5 text-[12.5px] text-ink-2">
              <li className="flex items-start gap-2.5">
                <Icon name="check" className="mt-0.5 h-4 w-4 shrink-0 text-success" />
                锚点检测：root / feet / center / head 四点稳定
              </li>
              <li className="flex items-start gap-2.5">
                <Icon name="check" className="mt-0.5 h-4 w-4 shrink-0 text-success" />
                相位对齐：{(phases ?? []).map((p) => p.toFixed(2)).join(" / ") || "—"}
              </li>
              <li className="flex items-start gap-2.5">
                <Icon name="check" className="mt-0.5 h-4 w-4 shrink-0 text-success" />
                漂移纠偏：{corrections.length} 帧校正回 frame-0 根位置
              </li>
            </ul>
          </Card>
        </div>
      </div>
    </div>
  );
}

import { useCallback, useRef, useState } from "react";
import { useAssetLoader } from "../stores/assetStore";
import { api, type AnimationResult } from "../api/client";
import { Badge, Button, Card, PageHeader, ScoreBar, cx } from "../components/ui";

const ACTIONS = ["idle", "walk", "run", "attack", "jump"];
const ACTION_LABELS: Record<string, string> = {
  idle: "待机",
  walk: "行走",
  run: "奔跑",
  attack: "攻击",
  jump: "跳跃",
  sequence: "序列帧",
};
const SIZES = [256, 384, 512, 768];

interface SeqFrame {
  name: string;
  dataUrl: string;
}

export default function AnimationStudio() {
  const asset = useAssetLoader();
  const [mode, setMode] = useState<"smart" | "sequence">("smart");
  const [skeletal, setSkeletal] = useState(true);
  const [action, setAction] = useState("walk");
  const [fps, setFps] = useState(12);
  const [duration, setDuration] = useState(1.0);
  const [size, setSize] = useState(384);
  const [result, setResult] = useState<AnimationResult | null>(null);
  const [upload, setUpload] = useState<{ name: string; dataUrl: string } | null>(null);
  const [seqFrames, setSeqFrames] = useState<SeqFrame[]>([]);
  const seqFileRef = useRef<HTMLInputElement>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [preview, setPreview] = useState(false);
  const [previewLoading, setPreviewLoading] = useState(false);
  const [previewError, setPreviewError] = useState(false);
  const [mainError, setMainError] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);

  const assetImage =
    (asset as { image?: { url?: string } } | null)?.image?.url ||
    (asset?.source as { ai_image?: { url?: string } } | undefined)?.ai_image?.url ||
    (asset?.id ? `/api/assets/${asset.id}/image.png?view=front&size=512` : undefined);

  const generate = useCallback(async () => {
    setBusy(true);
    setError(null);
    setMainError(false);
    try {
      const payload: Parameters<typeof api.createAnimation>[0] = {
        action,
        fps,
        duration,
        size,
        skeletal,
      };
      if (upload) {
        payload.image = upload.dataUrl.split(",")[1];
      } else if (asset?.id) {
        payload.asset_id = asset.id;
      }
      // otherwise the backend resolves the latest workbench / history asset
      setResult(await api.createAnimation(payload));
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }, [action, fps, duration, size, upload, asset?.id, skeletal]);

  const openPreview = () => {
    if (!result) return;
    setPreviewError(false);
    setPreviewLoading(true);
    setPreview(true);
  };

  const onSeqFiles = (files: FileList | null) => {
    if (!files || files.length === 0) return;
    const collator = new Intl.Collator(undefined, { numeric: true, sensitivity: "base" });
    const incoming = Array.from(files)
      .sort((a, b) => collator.compare(a.name, b.name))
      .map(
        (file) =>
          new Promise<SeqFrame>((resolve, reject) => {
            const reader = new FileReader();
            reader.onload = () => resolve({ name: file.name, dataUrl: String(reader.result) });
            reader.onerror = () => reject(reader.error);
            reader.readAsDataURL(file);
          }),
      );
    Promise.all(incoming)
      .then((frames) => setSeqFrames((prev) => [...prev, ...frames].slice(0, 60)))
      .catch(() => setError("读取序列帧图片失败，请重试"));
  };

  const composeSequence = useCallback(async () => {
    if (seqFrames.length < 2 || busy) return;
    setBusy(true);
    setError(null);
    setMainError(false);
    try {
      setResult(
        await api.createAnimationSequence({
          frames: seqFrames.map((frame) => frame.dataUrl),
          fps,
          size,
        }),
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }, [seqFrames, fps, size, busy]);

  const onFile = (file?: File) => {
    if (!file) return;
    const reader = new FileReader();
    reader.onload = () => setUpload({ name: file.name, dataUrl: String(reader.result) });
    reader.readAsDataURL(file);
  };

  const quality = asset?.quality?.animation;
  const rootTrack = asset?.animation?.motion?.root_track ?? [];
  const corrections = asset?.animation?.motion?.corrections ?? [];
  const trackPath = rootTrack
    .map((point, index) => {
      const x = (index / Math.max(1, rootTrack.length - 1)) * 640;
      const y = 45 - point.dx * 6;
      return `${index === 0 ? "M" : "L"}${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .join(" ");

  return (
    <div className="mx-auto flex w-full max-w-[1440px] flex-col gap-5 px-4 py-5 md:px-6">
      <PageHeader
        overline="Animation Studio"
        title="动画工作台"
        description="智能生成：读取源图风格 → 提取人物特征 → 生成风格一致帧序列 → 一致性校验 → 输出动画；序列帧导入：按顺序导入帧图直接合成循环动画"
        actions={
          <>
            {result && <Badge tone="falign">{ACTION_LABELS[result.action] ?? result.action}</Badge>}
            {result && <Badge tone="neutral">{result.frame_count} frames</Badge>}
            {result && <Badge tone="neutral">{result.fps} fps</Badge>}
            {result && (
              <Badge tone={result.consistency.passed ? "success" : "warning"}>
                一致性 {(result.consistency.overall * 100).toFixed(0)}%
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
              result ? (
                <div className="flex items-center gap-3">
                  <button
                    onClick={openPreview}
                    className="rounded-md border border-line-subtle px-2.5 py-1 text-[12px] text-ink-2 hover:bg-surface-2"
                  >
                    在线预览
                  </button>
                  <a className="text-[12px] text-ink-3 underline decoration-line" href={result.urls.gif} download>
                    下载 GIF
                  </a>
                </div>
              ) : undefined
            }
          >
            <div className="flex h-[320px] items-center justify-center rounded-[10px] border border-line-subtle bg-[radial-gradient(300px_160px_at_50%_40%,rgba(124,92,196,.10),transparent_70%),#f1efe9]">
              {result ? (
                mainError ? (
                  <div className="px-6 text-center text-sm text-danger">
                    动画预览加载失败。可点击「在线预览」或「下载 GIF」查看。
                  </div>
                ) : (
                  <img
                    src={result.urls.gif}
                    alt="animation preview"
                    onError={() => setMainError(true)}
                    className="max-h-[300px] max-w-full object-contain"
                  />
                )
              ) : upload ? (
                <img src={upload.dataUrl} alt="source" className="max-h-[300px] max-w-full object-contain" />
              ) : assetImage ? (
                <img src={assetImage} alt="source" className="max-h-[300px] max-w-full object-contain" />
              ) : (
                <div className="text-sm text-ink-3">生成资产，或上传一张图片作为动画源。</div>
              )}
            </div>
            <div className="mt-2.5 flex flex-wrap items-center gap-3 text-[11px] text-ink-3">
              <span>
                源：
                {mode === "sequence"
                  ? `序列帧 · ${seqFrames.length} 张`
                  : upload
                    ? `上传 · ${upload.name}`
                    : asset
                      ? `资产 · ${asset.name ?? asset.id}`
                      : "—"}
              </span>
              {result && <span>输出 {result.size}px · {result.duration}s · 循环</span>}
            </div>
          </Card>

          <Card title="生成参数 Animation Settings" icon="panel" iconClassName="text-falign">
            <div className="mb-4 flex items-center gap-3">
              <div className="flex overflow-hidden rounded-lg border border-line-subtle">
                <button
                  onClick={() => setMode("smart")}
                  className={cx(
                    "px-3 py-1.5 text-[12px] transition-colors",
                    mode === "smart" ? "bg-primary text-white" : "text-ink-2 hover:bg-surface-2",
                  )}
                >
                  智能生成
                </button>
                <button
                  onClick={() => setMode("sequence")}
                  className={cx(
                    "px-3 py-1.5 text-[12px] transition-colors",
                    mode === "sequence" ? "bg-primary text-white" : "text-ink-2 hover:bg-surface-2",
                  )}
                >
                  序列帧导入
                </button>
              </div>
              <span className="text-[11px] text-ink-4">
                {mode === "smart"
                  ? "由 AI 原画 / 资产立绘驱动生成风格一致的动作帧"
                  : "标准序列帧工作流：按文件名顺序导入帧图，直接合成为循环动画"}
              </span>
            </div>
            {mode === "smart" ? (
              <div className="flex flex-wrap items-end gap-6">
              <div className="flex flex-wrap items-center gap-6">
                <div>
                  <div className="mb-2 text-[11px] uppercase tracking-widest text-ink-4">生成方式</div>
                  <div className="flex overflow-hidden rounded-lg border border-line-subtle">
                    <button
                      onClick={() => setSkeletal(true)}
                      title="姿态引擎驱动的全身关节动画，含预备/跟随/重叠动作"
                      className={cx(
                        "px-3 py-1.5 text-[12px] transition-colors",
                        skeletal ? "bg-primary text-white" : "text-ink-2 hover:bg-surface-2",
                      )}
                    >
                      全身骨骼
                    </button>
                    <button
                      onClick={() => setSkeletal(false)}
                      title="对源图做变形动画，最大程度保留原画外观"
                      className={cx(
                        "px-3 py-1.5 text-[12px] transition-colors",
                        !skeletal ? "bg-primary text-white" : "text-ink-2 hover:bg-surface-2",
                      )}
                    >
                      源图驱动
                    </button>
                  </div>
                </div>
                <div>
                  <div className="mb-2 text-[11px] uppercase tracking-widest text-ink-4">动作</div>
                  <div className="flex overflow-hidden rounded-lg border border-line-subtle">
                    {ACTIONS.map((item) => (
                      <button
                        key={item}
                        onClick={() => setAction(item)}
                        className={cx(
                          "px-3 py-1.5 text-[12px] transition-colors",
                          action === item ? "bg-primary text-white" : "text-ink-2 hover:bg-surface-2",
                        )}
                      >
                        {ACTION_LABELS[item]}
                      </button>
                    ))}
                  </div>
                </div>
              </div>
                <label className="text-[11px] text-ink-4">
                  <span className="mb-2 block uppercase tracking-widest">帧率 {fps} fps</span>
                  <input type="range" min={4} max={30} value={fps} onChange={(e) => setFps(Number(e.target.value))} />
                </label>
                <label className="text-[11px] text-ink-4">
                  <span className="mb-2 block uppercase tracking-widest">时长 {duration.toFixed(1)}s</span>
                  <input
                    type="range"
                    min={0.3}
                    max={4}
                    step={0.1}
                    value={duration}
                    onChange={(e) => setDuration(Number(e.target.value))}
                  />
                </label>
                <label className="text-[11px] text-ink-4">
                  <span className="mb-2 block uppercase tracking-widest">分辨率</span>
                  <select
                    value={size}
                    onChange={(e) => setSize(Number(e.target.value))}
                    className="rounded-lg border border-line-subtle bg-surface-1 px-2 py-1.5 text-[12px]"
                  >
                    {SIZES.map((option) => (
                      <option key={option} value={option}>
                        {option} x {option}
                      </option>
                    ))}
                  </select>
                </label>
                <div className="ml-auto flex items-center gap-3">
                  <input
                    ref={fileRef}
                    type="file"
                    accept="image/*"
                    className="hidden"
                    onChange={(e) => onFile(e.target.files?.[0])}
                  />
                  <Button variant="secondary" size="sm" icon="image" onClick={() => fileRef.current?.click()}>
                    上传源图
                  </Button>
                  <Button variant="primary" size="sm" icon="spark" onClick={generate} disabled={busy}>
                    {busy ? "生成中…" : "生成动画"}
                  </Button>
                </div>
              </div>
            ) : (
              <div className="flex flex-col gap-4">
                <div className="flex flex-wrap items-end gap-6">
                  <label className="text-[11px] text-ink-4">
                    <span className="mb-2 block uppercase tracking-widest">帧率 {fps} fps</span>
                    <input type="range" min={2} max={30} value={fps} onChange={(e) => setFps(Number(e.target.value))} />
                  </label>
                  <label className="text-[11px] text-ink-4">
                    <span className="mb-2 block uppercase tracking-widest">分辨率</span>
                    <select
                      value={size}
                      onChange={(e) => setSize(Number(e.target.value))}
                      className="rounded-lg border border-line-subtle bg-surface-1 px-2 py-1.5 text-[12px]"
                    >
                      {SIZES.map((option) => (
                        <option key={option} value={option}>
                          {option} x {option}
                        </option>
                      ))}
                    </select>
                  </label>
                  <div className="ml-auto flex items-center gap-3">
                    <input
                      ref={seqFileRef}
                      type="file"
                      accept="image/*"
                      multiple
                      className="hidden"
                      onChange={(e) => {
                        onSeqFiles(e.target.files);
                        e.target.value = "";
                      }}
                    />
                    <Button variant="secondary" size="sm" icon="image" onClick={() => seqFileRef.current?.click()}>
                      导入序列帧
                    </Button>
                    <Button
                      variant="primary"
                      size="sm"
                      icon="film"
                      onClick={composeSequence}
                      disabled={busy || seqFrames.length < 2}
                    >
                      {busy ? "合成中…" : `合成动画（${seqFrames.length} 帧）`}
                    </Button>
                  </div>
                </div>
                {seqFrames.length > 0 && (
                  <div>
                    <div className="mb-2 flex items-center justify-between text-[11px] text-ink-4">
                      <span>已导入 {seqFrames.length} 帧 · 按文件名顺序播放（时长约 {(seqFrames.length / fps).toFixed(2)}s）</span>
                      <button className="underline hover:text-ink-2" onClick={() => setSeqFrames([])}>
                        清空全部
                      </button>
                    </div>
                    <div className="cf-scroll flex max-h-[120px] flex-wrap gap-2 overflow-y-auto rounded-[10px] border border-line-subtle bg-surface-1 p-2">
                      {seqFrames.map((frame, index) => (
                        <div
                          key={`${frame.name}-${index}`}
                          className="group relative h-14 w-14 shrink-0 overflow-hidden rounded-md border border-line-subtle bg-[#f1efe9]"
                          title={`${frame.name} · 第 ${index + 1} 帧`}
                        >
                          <img src={frame.dataUrl} alt={frame.name} className="h-full w-full object-contain" />
                          <button
                            onClick={() => setSeqFrames((prev) => prev.filter((_, i) => i !== index))}
                            className="absolute right-0 top-0 hidden h-4 w-4 items-center justify-center rounded-bl-md bg-ink/80 text-[9px] text-canvas group-hover:flex"
                            aria-label={`移除 ${frame.name}`}
                          >
                            ✕
                          </button>
                          <span className="absolute bottom-0 left-0 bg-ink/70 px-1 text-[9px] text-canvas">
                            {index + 1}
                          </span>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            )}
            {(mode === "smart" && upload) && (
              <button className="mt-2 text-[11px] text-ink-3 underline" onClick={() => setUpload(null)}>
                清除上传，改用当前资产
              </button>
            )}
            {error && <p className="mt-3 border-l-2 border-danger pl-3 text-[12.5px] text-danger">{error}</p>}
          </Card>

          {result && (
            <Card
              title="帧序列 Sprite Sheet"
              icon="film"
              iconClassName="text-falign"
              right={
                <a className="text-[12px] text-ink-3 underline decoration-line" href={result.urls.sheet} download>
                  下载雪碧图
                </a>
              }
            >
              <div className="cf-scroll overflow-x-auto rounded-[10px] border border-line-subtle bg-surface-1 p-2">
                <img src={result.urls.sheet} alt="sprite sheet" className="max-h-[220px]" />
              </div>
            </Card>
          )}

          {result && result.frame_urls && result.frame_urls.length > 0 && (
            <Card
              title={`关键帧 Keyframes · ${result.frame_count} 帧`}
              icon="grid"
              iconClassName="text-falign"
              right={
                <span className="text-[12px] text-ink-3">
                  {result.action === "sequence" ? "导入序列 · 原样合成" : skeletal ? "全身骨骼 · 关节动画" : "源图驱动 · 变形动画"}
                </span>
              }
            >
              <div className="cf-scroll flex gap-3 overflow-x-auto pb-1">
                {result.frame_urls.map((url, index) => (
                  <figure key={url} className="shrink-0">
                    <div className="h-[130px] w-[130px] overflow-hidden rounded-lg border border-line-subtle bg-[#f1efe9]">
                      <img
                        src={url}
                        alt={`frame ${index + 1}`}
                        className="h-full w-full object-contain"
                        loading="lazy"
                      />
                    </div>
                    <figcaption className="mt-1 text-center font-mono text-[10.5px] text-ink-4">
                      #{index + 1}
                    </figcaption>
                  </figure>
                ))}
              </div>
            </Card>
          )}

          {rootTrack.length > 0 && (
            <Card title="根运动轨迹 Root Motion（漂移 → 纠偏）" icon="activity" iconClassName="text-falign">
              <svg viewBox="0 0 640 90" className="h-[90px] w-full">
                <line x1="0" y1="45" x2="640" y2="45" stroke="#b9b3a5" strokeDasharray="5 5" />
                <path d={trackPath} fill="none" stroke="#a94f3d" strokeWidth="2" />
                {rootTrack.map((point, index) => {
                  const x = (index / Math.max(1, rootTrack.length - 1)) * 640;
                  const y = 45 - (point.dx + (corrections[index]?.dx ?? 0)) * 6;
                  return <circle key={index} cx={x} cy={y} r="3.5" fill="#3e7d5a" />;
                })}
              </svg>
            </Card>
          )}
        </div>

        <div className="col-span-12 flex flex-col gap-5 xl:col-span-4">
          <Card title="风格识别 Style Analysis" icon="layers" iconClassName="text-falign">
            {result ? (
              <div className="space-y-3.5">
                <div className="flex items-center justify-between">
                  <span className="text-[13px] text-ink-2">识别风格</span>
                  <Badge tone="falign">{result.style_label}</Badge>
                </div>
                <ScoreBar label="置信度" value={result.style.confidence} />
                <ul className="space-y-2 text-[12px] text-ink-3">
                  <li className="flex justify-between">
                    <span>色板规模</span>
                    <span className="font-mono">{result.style.palette_size}</span>
                  </li>
                  <li className="flex justify-between">
                    <span>线条密度</span>
                    <span className="font-mono">{result.style.edge_density.toFixed(3)}</span>
                  </li>
                  <li className="flex justify-between">
                    <span>平涂占比</span>
                    <span className="font-mono">{result.style.flat_ratio.toFixed(3)}</span>
                  </li>
                  <li className="flex justify-between">
                    <span>饱和度</span>
                    <span className="font-mono">{result.style.saturation.toFixed(3)}</span>
                  </li>
                </ul>
              </div>
            ) : (
              <div className="text-[12.5px] text-ink-3">生成动画后展示源图的风格识别结果。</div>
            )}
          </Card>

          <Card
            title="一致性校验 Consistency"
            icon="check"
            iconClassName="text-falign"
            right={
              result ? (
                <Badge tone={result.consistency.passed ? "success" : "warning"}>
                  {result.consistency.passed ? "PASS" : "RETRY"}
                </Badge>
              ) : undefined
            }
          >
            {result ? (
              <div className="space-y-3.5">
                <ScoreBar label="色彩 Palette" value={result.consistency.palette} tone="falign" />
                <ScoreBar label="色调 Color" value={result.consistency.color} tone="gimport" />
                <ScoreBar label="线条 Line" value={result.consistency.line} tone="falign" />
                <ScoreBar label="感知哈希 Hash" value={result.consistency.hash} tone="gimport" />
                <ScoreBar
                  label={`综合 · 阈值 ${result.consistency.floor}`}
                  value={result.consistency.overall}
                  threshold={result.consistency.floor}
                />
                <div className="text-[11px] text-ink-4">对比 {result.consistency.frames_checked} 帧</div>
              </div>
            ) : (
              <div className="text-[12.5px] text-ink-3">
                通过视觉相似度分析（配色 / 线条 / 感知哈希）校验生成动画与源图的一致性。
              </div>
            )}
          </Card>

          {result && result.character.palette.length > 0 && (
            <Card title="人物特征 Character" icon="cube">
              <ul className="space-y-2 text-[12px] text-ink-3">
                <li className="flex justify-between">
                  <span>包围盒</span>
                  <span className="font-mono">{result.character.bbox.join(",")}</span>
                </li>
                <li className="flex justify-between">
                  <span>宽高比</span>
                  <span className="font-mono">{result.character.aspect}</span>
                </li>
                <li className="flex justify-between">
                  <span>中心</span>
                  <span className="font-mono">{result.character.center.join(",")}</span>
                </li>
              </ul>
              <div className="mt-3 flex flex-wrap gap-1.5">
                {result.character.palette.map((color) => (
                  <span
                    key={color}
                    className="h-5 w-5 rounded border border-line-subtle"
                    style={{ background: color }}
                    title={color}
                  />
                ))}
              </div>
            </Card>
          )}

          {quality && (
            <Card title="FAlign 质量 Quality" icon="gauge" iconClassName="text-falign">
              <div className="space-y-3.5">
                <ScoreBar label="Anchor 锚点稳定" value={quality.anchor_score ?? 0} tone="falign" />
                <ScoreBar label="Motion 根运动" value={quality.motion_score ?? 0} tone="gimport" />
                <ScoreBar label="Temporal 时序平滑" value={quality.temporal_score ?? 0} tone="falign" />
              </div>
            </Card>
          )}
        </div>
      </div>

      {preview && result && (
        <div
          className="fixed inset-0 z-50 grid place-items-center bg-black/60 p-6"
          onClick={() => setPreview(false)}
        >
          <div
            className="relative max-h-[90vh] max-w-[92vw] rounded-2xl border border-line-subtle bg-surface-1 p-4 shadow-2xl"
            onClick={(event) => event.stopPropagation()}
          >
            <button
              onClick={() => setPreview(false)}
              className="absolute -right-3 -top-3 grid h-8 w-8 place-items-center rounded-full border border-line-subtle bg-surface-1 text-ink-2"
            >
              ✕
            </button>
            {previewLoading && !previewError && (
              <div className="grid h-[320px] w-[320px] place-items-center text-sm text-ink-3">
                正在加载动画…
              </div>
            )}
            {previewError && (
              <div className="grid h-[320px] w-[320px] place-items-center px-6 text-center text-sm text-danger">
                在线预览加载失败，请点击「下载 GIF」查看。
              </div>
            )}
            <img
              src={result.urls.gif}
              alt="animation preview"
              className={cx("max-h-[80vh] max-w-[88vw] object-contain", (previewLoading || previewError) && "hidden")}
              onLoad={() => setPreviewLoading(false)}
              onError={() => {
                setPreviewLoading(false);
                setPreviewError(true);
              }}
            />
          </div>
        </div>
      )}
    </div>
  );
}

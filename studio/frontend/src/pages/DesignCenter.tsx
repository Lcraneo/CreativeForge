import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useAssetLoader, useAssetStore } from "../stores/assetStore";
import { Badge, Button, Card, EmptyState, KV, PageHeader, SafeImage, Segmented, cx } from "../components/ui";
import { CharacterArt } from "../components/CharacterArt";
import { Icon } from "../components/icons";
import { toast } from "../stores/toastStore";
import { api } from "../api/client";
import { AssetLoadState } from "../components/AssetLoadState";
import type { CreativeAsset } from "../types";

const VIEWS = [
  { id: "front", label: "正面 Front" },
  { id: "side", label: "侧面 Side" },
  { id: "back", label: "背面 Back" },
] as const;

type ViewId = (typeof VIEWS)[number]["id"];

const VIEW_CAPTION: Record<ViewId, string> = {
  front: "正视图 · 面部 / 服装细节",
  side: "侧视图 · 剪影 / 武器挂载",
  back: "背视图 · 发型 / 背部结构",
};

export default function DesignCenter() {
  const asset = useAssetLoader();
  if (!asset) return <AssetLoadState />;
  return <DesignEditor key={asset.id} asset={asset} />;
}

function DesignEditor({ asset }: { asset: CreativeAsset }) {
  const navigate = useNavigate();
  const [pose, setPose] = useState<ViewId>("front");
  const [generating, setGenerating] = useState(false);
  const [viewError, setViewError] = useState<string | null>(null);
  const [restyleStyle, setRestyleStyle] = useState("anime");
  const [restyleBusy, setRestyleBusy] = useState(false);
  const [cutoutBusy, setCutoutBusy] = useState(false);
  const patchAsset = useAssetStore((state) => state.patch);

  if (!asset?.character) {
    return (
      <div className="mx-auto w-full max-w-[1440px] px-4 py-5 md:px-6">
        <Card>
          <EmptyState
            icon="image"
            title={asset ? "该资产未包含角色规格" : "还没有可查看的资产"}
            description="三视图基于 AI 原画与 CharacterSpec 生成。先在工作台生成一个角色资产，这里会展示其正 / 侧 / 背设计视图。"
            action={
              <Button variant="primary" icon="spark" onClick={() => navigate("/workspace")}>
                去生成资产
              </Button>
            }
          />
        </Card>
      </div>
    );
  }

  const spec = asset.character;
  const palette = asset.pixel?.palette.colors;
  const views = asset.design_views;
  const viewsReady = Boolean(views?.side?.url && views?.back?.url);
  const viewModel = views?.side?.model ?? views?.back?.model ?? "qwen-image-2.1-turbo";
  const chips = [
    spec.gender_label,
    spec.class_label,
    spec.element !== "none" ? spec.element_label : null,
    [spec.hair_color_label, spec.hair_style_label].filter(Boolean).join("") || null,
    spec.build_label,
    spec.height_cm != null ? `${spec.height_cm}cm` : null,
  ].filter(Boolean);

  function viewUrl(view: ViewId): string | undefined {
    return views?.[view]?.url ?? (view === "front" ? asset?.image?.url : undefined);
  }

  async function generateViews() {
    if (!asset || generating) return;
    setGenerating(true);
    setViewError(null);
    try {
      const payload = await api.generateDesignViews(asset.id);
      const nextViews = payload.design_views ?? {};
      if (!nextViews.side?.url || !nextViews.back?.url) {
        // 后端只有 side / back 全部通过校验才返回成功；这里再兜一层
        throw new Error("side / back 未完整生成，已保留上一版三视图");
      }
      patchAsset(asset.id, { design_views: nextViews });
      toast({
        tone: "success",
        title: "三视图已生成",
        description: `${payload.model ?? "qwen-image-2.1-turbo"} · side / back 已通过校验`,
      });
    } catch (cause) {
      // 失败不 patchAsset：上一版三视图保持原样
      const reason = (cause instanceof Error ? cause.message : String(cause)).slice(0, 300);
      setViewError(reason);
      toast({ tone: "danger", title: "三视图生成失败", description: reason.slice(0, 200) });
    } finally {
      setGenerating(false);
    }
  }

  async function doRestyle() {
    if (!asset || restyleBusy) return;
    setRestyleBusy(true);
    try {
      const payload = await api.restyleAsset(asset.id, restyleStyle);
      patchAsset(asset.id, { restyle: payload });
      toast({
        tone: "success",
        title: "风格迁移完成",
        description: `${restyleStyle} · ${payload.model ?? ""}`,
      });
    } catch (cause) {
      toast({ tone: "danger", title: "风格迁移失败", description: String(cause).slice(0, 200) });
    } finally {
      setRestyleBusy(false);
    }
  }

  async function doCutout() {
    if (!asset || cutoutBusy) return;
    setCutoutBusy(true);
    try {
      const payload = await api.cutoutAsset(asset.id);
      patchAsset(asset.id, { cutout_png: payload.cutout_png });
      toast({
        tone: "success",
        title: "透明底立绘已生成",
        description: "可在资产检查器查看与导出",
      });
    } catch (cause) {
      toast({ tone: "danger", title: "透明底生成失败", description: String(cause).slice(0, 200) });
    } finally {
      setCutoutBusy(false);
    }
  }

  function copyPrompt() {
    const prompt = asset?.prompt_enhance?.prompt || asset?.source.prompt;
    if (!prompt) return;
    navigator.clipboard?.writeText(prompt).catch(() => undefined);
    toast({ tone: "info", title: "提示词已复制", description: "可粘贴到任意图像模型复现" });
  }

  return (
    <div className="mx-auto flex w-full max-w-[1440px] flex-col gap-5 px-4 py-5 md:px-6">
      <PageHeader
        overline="Design Turnaround"
        title="角色设计三视图"
        description="基于 AI 原画生成的多视角设计图；无原画时显示确定性示意视图"
        actions={
          <>
            <Badge tone="primary" icon="spark">
              seed {spec.seed}
            </Badge>
            {viewsReady && (
              <Badge tone="neutral" icon="spark">
                {viewModel}
              </Badge>
            )}
            {aiImageAvailable(asset) && (
              <Button
                variant="ember"
                icon="image"
                loading={generating}
                disabled={generating}
                onClick={generateViews}
              >
                {generating ? "生成中…" : viewsReady ? "重新生成三视图" : "生成三视图"}
              </Button>
            )}
          </>
        }
      />

      {chips.length > 0 && (
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-[11px] uppercase tracking-[0.08em] text-ink-4">Prompt spec</span>
          {chips.map((chip) => (
            <Badge key={String(chip)} tone="neutral">
              {chip}
            </Badge>
          ))}
        </div>
      )}

      <div className="grid grid-cols-12 gap-5">
        <div className="col-span-12 flex flex-col gap-5 lg:col-span-8">
        <Card
          title="三视图 Turnaround"
          icon="image"
          right={
            <Segmented options={VIEWS.map((v) => ({ ...v }))} value={pose} onChange={setPose} />
          }
        >
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
            {(["front", "side", "back"] as const).map((view, index) => {
              const url = viewUrl(view);
              const title = VIEWS.find((item) => item.id === view)?.label ?? view;
              return (
                <button
                  key={view}
                  onClick={() => setPose(view)}
                  className={cx(
                    "group flex flex-col overflow-hidden rounded-lg border text-left transition-[border-color,background-color,box-shadow] duration-(--motion-fast) ease-standard",
                    pose === view
                      ? "border-primary/45 bg-primary-tint/50"
                      : "border-line-subtle bg-surface-1 hover:border-line-strong",
                  )}
                >
                  <div className="flex w-full items-baseline justify-between gap-2 border-b border-line-subtle px-3 py-2">
                    <span
                      className={cx(
                        "text-[12px] font-semibold",
                        pose === view ? "text-primary" : "text-ink",
                      )}
                    >
                      {title}
                    </span>
                    <span className="cf-ref">0{index + 1}</span>
                  </div>
                  <div className="flex h-[240px] items-center justify-center bg-canvas px-3 py-3 xl:h-[300px]">
                    {url ? (
                      <SafeImage
                        src={url}
                        alt={`character ${view} view`}
                        sealChar={view === "front" ? "正" : view === "side" ? "侧" : "背"}
                        className="h-full w-full object-contain"
                      />
                    ) : (
                      <CharacterArt
                        spec={spec}
                        palette={palette}
                        view={view}
                        className="h-full w-auto"
                      />
                    )}
                  </div>
                  <div className="px-3 py-2">
                    <span
                      className={cx(
                        "block text-[11px]",
                        pose === view ? "font-semibold text-primary" : "text-ink-3",
                      )}
                    >
                      {url
                        ? VIEW_CAPTION[view]
                        : view === "front"
                          ? "未生成 AI 原画"
                          : "未生成 · 点击生成三视图"}
                    </span>
                    {!url && <span className="mt-0.5 block text-[10px] text-ink-4">示意图 · 非 AI 结果</span>}
                  </div>
                </button>
              );
            })}
          </div>
          <p
            className={cx("mt-3 text-[11px]", viewError ? "text-danger" : "text-ink-4")}
          >
            {generating
              ? `正在调用 ${viewModel} 生成 side / back 双栏图，请勿关闭页面…`
              : viewError
                ? `三视图生成失败：${viewError}（已保留上一版三视图）`
                : viewsReady
                  ? `三视图由 ${viewModel} 基于 AI 原画一次生成双栏图后本地裁切，与资产同源。`
                  : "正面为 AI 原画；侧 / 背尚未生成，示意图不是 AI 结果。点击「生成三视图」手动触发生成。"}
          </p>
        </Card>

          {palette && palette.length > 0 && (
            <Card title="语义调色板" icon="grid" iconClassName="text-precon">
              <div className="grid grid-cols-6 gap-1.5 sm:grid-cols-10 xl:grid-cols-12">
                {palette.slice(0, 16).map((color, index) => (
                  <button
                    key={`${color}-${index}`}
                    title={color}
                    onClick={() => {
                      navigator.clipboard?.writeText(color).catch(() => undefined);
                      toast({ tone: "info", title: "已复制色值", description: color });
                    }}
                    className="h-7 rounded-sm border border-ink/[.12] transition-transform duration-(--motion-fast) ease-standard hover:scale-110 pointer-coarse:h-11"
                    style={{ background: color }}
                  />
                ))}
              </div>
              {spec.palette && (
                <div className="mt-3 grid gap-x-7 md:grid-cols-2">
                  <KV label="outline" value={spec.palette.outline ?? "—"} />
                  <KV label="base / outfit" value={spec.palette.base ?? "—"} />
                  <KV label="hair" value={spec.hair_color_hex ?? "—"} />
                </div>
              )}
            </Card>
          )}
        </div>

        <div className="col-span-12 flex flex-col gap-5 lg:col-span-4">
          <Card title="角色档案 Identity" icon="cube">
            <KV
              label="性别 / 体型"
              value={[spec.gender_label, spec.build_label].filter(Boolean).join(" · ") || "—"}
            />
            <KV
              label="职业 / 元素"
              value={[spec.class_label, spec.element_label].filter(Boolean).join(" · ") || "—"}
            />
            <KV label="定位" value={spec.role_label ?? "—"} />
            <KV
              label="发型 / 发色"
              value={[spec.hair_color_label, spec.hair_style_label].filter(Boolean).join("") || "—"}
            />
            <KV
              label="瞳色 / 肤色"
              value={[spec.eyes_label, spec.skin_label].filter(Boolean).join(" · ") || "—"}
            />
            <KV label="武器" value={spec.weapon_label ?? "—"} />
            <KV label="配饰" value={spec.accessory?.length ? spec.accessory.join(" / ") : "无"} />
            <KV label="身高" value={spec.height_cm != null ? `${spec.height_cm} cm` : "—"} />
          </Card>

          <Card
            title="AI 原画 Concept"
            icon="spark"
            right={
              asset.image ? (
                <Badge tone="primary">{asset.image.provider}</Badge>
              ) : (
                <Badge tone="neutral">未生成</Badge>
              )
            }
          >
            {aiImageAvailable(asset) && (
              <div className="mb-3 flex flex-col gap-2 rounded-sm border border-line-subtle bg-surface-1/60 p-2.5">
                <Segmented
                  options={[
                    { id: "anime", label: "动漫" },
                    { id: "pixel", label: "像素" },
                    { id: "ink", label: "水墨" },
                  ]}
                  value={restyleStyle}
                  onChange={setRestyleStyle}
                  className="self-start"
                />
                <div className="flex flex-wrap gap-2">
                  <Button
                    variant="secondary"
                    size="sm"
                    icon="spark"
                    loading={restyleBusy}
                    onClick={doRestyle}
                  >
                    风格迁移
                  </Button>
                  <Button
                    variant="secondary"
                    size="sm"
                    icon="eraser"
                    loading={cutoutBusy}
                    onClick={doCutout}
                  >
                    透明底
                  </Button>
                </div>
              </div>
            )}
            {asset.restyle?.url && (
              <div className="mb-3 overflow-hidden rounded-[10px] border border-line-subtle bg-canvas">
                <p className="px-3 pt-2 text-[11px] text-ink-3">
                  风格迁移 · {asset.restyle.style}（点击放大另存）
                </p>
                <a href={asset.restyle.url} target="_blank" rel="noreferrer">
                  <SafeImage
                    src={asset.restyle.url}
                    alt={`restyle ${asset.restyle.style}`}
                    className="mx-auto h-[200px] object-contain"
                  />
                </a>
              </div>
            )}
            {asset.cutout_png && (
              <div className="mb-3 overflow-hidden rounded-[10px] border border-dashed border-primary/40 bg-white">
                <p className="px-3 pt-2 text-[11px] text-ink-3">
                  透明底立绘（棋盘格外的都是透明像素）
                </p>
                <a href={asset.cutout_png} target="_blank" rel="noreferrer">
                  <SafeImage
                    src={asset.cutout_png}
                    alt="cutout"
                    sealChar="立"
                    className="mx-auto h-[200px] object-contain"
                    style={{
                      backgroundImage:
                        "linear-gradient(45deg,#eee 25%,transparent 25%,transparent 75%,#eee 75%),linear-gradient(45deg,#eee 25%,transparent 25%,transparent 75%,#eee 75%)",
                      backgroundSize: "16px 16px",
                      backgroundPosition: "0 0, 8px 8px",
                    }}
                  />
                </a>
              </div>
            )}
            {asset.image?.url ? (
              <div className="overflow-hidden rounded-[10px] border border-line-subtle bg-paper">
                <SafeImage
                  src={asset.image.url}
                  alt={asset.name ?? "concept art"}
                  sealChar="画"
                  className="mx-auto h-[220px] object-contain"
                />
              </div>
            ) : (
              <p className="text-[12.5px] leading-[19px] text-ink-3">
                未生成 AI
                原画（离线管线或未启用自定义模型）。三视图与像素资产不依赖原图，仍可正常导出。
              </p>
            )}
            <button
              onClick={copyPrompt}
              className="mt-3 inline-flex items-center gap-1.5 text-xs font-medium text-primary transition-opacity hover:opacity-80"
            >
              <Icon name="terminal" className="h-3.5 w-3.5" />
              复制生成提示词
            </button>
            {asset.source.prompt && (
              <p className="mt-2 line-clamp-3 text-[11.5px] leading-[18px] text-ink-3">
                {asset.source.prompt}
              </p>
            )}
          </Card>
        </div>
      </div>
    </div>
  );
}

function aiImageAvailable(asset: { image?: { url?: string } | null }): boolean {
  return Boolean(asset.image?.url);
}

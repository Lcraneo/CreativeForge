import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useAssetLoader, useAssetStore } from "../stores/assetStore";
import {
  Badge,
  Button,
  Card,
  EmptyState,
  KV,
  PageHeader,
  Segmented,
  cx,
} from "../components/ui";
import { CharacterArt } from "../components/CharacterArt";
import { Icon } from "../components/icons";
import { toast } from "../stores/toastStore";
import { api } from "../api/client";
import type { DesignViewImage } from "../types";

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
  const navigate = useNavigate();
  const [pose, setPose] = useState<ViewId>("front");
  const [generating, setGenerating] = useState(false);
  const setAsset = useAssetStore((state) => state.set);

  if (!asset?.character) {
    return (
      <div className="mx-auto w-full max-w-[1440px] px-4 py-5 md:px-6">
        <Card>
          <EmptyState
            icon="image"
            title={asset ? "该资产未包含角色规格" : "还没有可查看的资产"}
            description="三视图基于 AI 原画与 CharacterSpec 生成。先在工作台生成一个角色资产，这里会展示其正 / 侧 / 背设计视图。"
            action={
              <Button variant="primary" icon="spark" onClick={() => navigate("/")}>
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
  const chips = [
    spec.gender_label,
    spec.class_label,
    spec.element !== "none" ? spec.element_label : null,
    [spec.hair_color_label, spec.hair_style_label].filter(Boolean).join("") || null,
    spec.build_label,
    spec.height_cm != null ? `${spec.height_cm}cm` : null,
  ].filter(Boolean);

  function viewUrl(view: ViewId): string | undefined {
    return views?.[view]?.url ?? (view === "front" ? asset?.image?.url ?? asset?.source?.ai_image?.url : undefined);
  }

  async function generateViews() {
    if (!asset || generating) return;
    setGenerating(true);
    try {
      const next = await api.generateDesignViews(asset.id);
      setAsset({ ...asset, design_views: next });
      toast({ tone: "success", title: "AI 三视图已生成", description: "基于阿里云图像编辑模型，与原画同源" });
    } catch (cause) {
      toast({ tone: "danger", title: "三视图生成失败", description: String(cause).slice(0, 200) });
    } finally {
      setGenerating(false);
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
            {aiImageAvailable(asset) && (
              <Button
                variant="ember"
                icon="image"
                loading={generating}
                onClick={generateViews}
              >
                {views?.side ? "重新生成三视图" : "生成 AI 三视图"}
              </Button>
            )}
            <Button variant="secondary" icon="grid" onClick={() => navigate("/pixel")}>
              像素工作台
            </Button>
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
        <Card
          className="col-span-12 lg:col-span-8"
          title="三视图 Turnaround"
          icon="image"
          right={
            <Segmented
              options={VIEWS.map((v) => ({ ...v }))}
              value={pose}
              onChange={setPose}
            />
          }
        >
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
            {(["front", "side", "back"] as const).map((view) => {
              const url = viewUrl(view);
              return (
                <button
                  key={view}
                  onClick={() => setPose(view)}
                  className={cx(
                    "group flex flex-col items-center gap-3 rounded-xl border p-4 transition-all duration-150 ease-standard",
                    pose === view
                      ? "border-primary/45 bg-primary-tint/50"
                      : "border-line-subtle bg-[#f1efe9] hover:border-line",
                  )}
                >
                  {url ? (
                    <img
                      src={url}
                      alt={`character ${view} view`}
                      className="h-[220px] w-full object-contain"
                    />
                  ) : (
                    <CharacterArt
                      spec={spec}
                      palette={palette}
                      view={view}
                      className="h-[220px] w-auto"
                    />
                  )}
                  <span
                    className={cx(
                      "text-[11px]",
                      pose === view ? "font-semibold text-primary" : "text-ink-3",
                    )}
                  >
                    {VIEW_CAPTION[view]}
                    {url ? "" : " · 示意"}
                  </span>
                </button>
              );
            })}
          </div>
          <p className="mt-3 text-[11px] text-ink-4">
            {views?.side
              ? "三视图由阿里云图像编辑模型基于 AI 原画生成，与资产同源。"
              : "正面为 AI 原画；侧 / 背为确定性示意。点「生成 AI 三视图」可基于原画生成真实多视角。"}
          </p>
        </Card>

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
            <KV
              label="配饰"
              value={spec.accessory?.length ? spec.accessory.join(" / ") : "无"}
            />
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
            {asset.image?.url ? (
              <div className="overflow-hidden rounded-[10px] border border-line-subtle bg-[#f1efe9]">
                <img
                  src={asset.image.url}
                  alt={asset.name ?? "concept art"}
                  className="mx-auto h-[220px] object-contain"
                />
              </div>
            ) : (
              <p className="text-[12.5px] leading-[19px] text-ink-3">
                未生成 AI 原画（离线管线或未启用自定义模型）。三视图与像素资产不依赖原图，仍可正常导出。
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

          {palette && palette.length > 0 && (
            <Card title="语义调色板" icon="grid" iconClassName="text-precon">
              <div className="grid grid-cols-8 gap-1.5">
                {palette.slice(0, 16).map((color, index) => (
                  <button
                    key={`${color}-${index}`}
                    title={color}
                    onClick={() => {
                      navigator.clipboard?.writeText(color).catch(() => undefined);
                      toast({ tone: "info", title: "已复制色值", description: color });
                    }}
                    className="h-7 rounded-sm border border-ink/[.12] transition-transform duration-150 ease-standard hover:scale-110"
                    style={{ background: color }}
                  />
                ))}
              </div>
              {spec.palette && (
                <div className="mt-3">
                  <KV label="outline" value={spec.palette.outline ?? "—"} />
                  <KV label="base / outfit" value={spec.palette.base ?? "—"} />
                  <KV label="hair" value={spec.hair_color_hex ?? "—"} />
                </div>
              )}
            </Card>
          )}
        </div>
      </div>
    </div>
  );
}

function aiImageAvailable(asset: { image?: { url?: string } | null; source?: { ai_image?: { url?: string } | null } | null }): boolean {
  return Boolean(asset.image?.url || asset.source?.ai_image?.url);
}

import { Suspense, lazy, type ReactNode } from "react";
import { useNavigate } from "react-router-dom";
import { assetHref, useAssetLoader } from "../stores/assetStore";
import {
  Badge,
  Button,
  Card,
  KV,
  PageHeader,
  SafeImage,
  ScoreBar,
  ScoreRing,
} from "../components/ui";
import { AssetLoadState } from "../components/AssetLoadState";
import { Icon } from "../components/icons";
import { api } from "../api/client";
import { toast } from "../stores/toastStore";
const AssetViewer = lazy(() => import("../three/AssetViewer"));

/** 档案分区：每个分区一条顶部分隔线，标题行不再叠加装饰 */
function DossierSection({
  eyebrow,
  title,
  right,
  children,
}: {
  eyebrow: string;
  title: string;
  right?: ReactNode;
  children: ReactNode;
}) {
  return (
    <section className="border-t border-line-subtle px-5 py-4 first:border-t-0">
      <header className="mb-3 flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1.5">
        <div className="flex min-w-0 flex-1 items-baseline gap-2.5">
          <span className="cf-ref shrink-0">{eyebrow}</span>
          <h2 className="shrink-0 text-[15px] font-semibold leading-6">{title}</h2>
          <span className="h-px min-w-8 flex-1 bg-line" aria-hidden="true" />
        </div>
        {right}
      </header>
      {children}
    </section>
  );
}

export default function AssetInspector() {
  const asset = useAssetLoader();
  const navigate = useNavigate();

  if (!asset) return <AssetLoadState />;

  const quality = asset.quality;
  const report = quality?.report;
  const spec = asset.character;
  const aiImage = asset.image?.url ?? asset.source?.ai_image?.url;
  const aiImageMeta = asset.image ?? asset.source?.ai_image;
  const resources = Object.entries(asset.engine?.resources ?? {});
  const checks = asset.engine?.validation.checks ?? [];
  const label = (value: string | null | undefined) => (value ? value : "—");
  const pair = (...values: Array<string | null | undefined>) =>
    values
      .map(label)
      .filter((value) => value !== "—")
      .join(" · ") || "—";
  const sourceLabel = asset.source?.ai_image?.width
    ? `${asset.source.ai_image.width} × ${asset.source.ai_image.height} · AI 原画`
    : `${asset.source.width} × ${asset.source.height}`;

  return (
    <div className="mx-auto flex w-full max-w-[1440px] flex-col gap-5 px-4 py-5 md:px-6">
      <PageHeader
        overline="CreativeAsset Inspector"
        title={`${asset.name ?? "未命名资产"} · ${asset.id}`}
        description="CreativeAsset v1.0 统一协议：Identity → Pixel → Animation → Engine → Quality"
        actions={
          <>
            <Badge tone="primary" icon="cube">
              {asset.engine?.target ?? "—"}
            </Badge>
            <Button
              variant="secondary"
              icon="refresh"
              onClick={() => {
                navigate("/");
                toast({ tone: "info", title: "回到工作台", description: "可重新描述目标生成资产" });
              }}
            >
              重新生成
            </Button>
            <Button variant="secondary" icon="layers" onClick={() => navigate(assetHref("/design", asset.id))}>
              设计三视图
            </Button>
            <Button variant="primary" icon="package" onClick={() => navigate(assetHref("/export", asset.id))}>
              导出工程包
            </Button>
          </>
        }
      />

      {/* E 来源透明化：AI 生图失败的降级资产，明确标注离线示意属性 */}
      {asset.model_fallback && (
        <div className="rounded-lg border border-warning/50 bg-warning/[.07] px-4 py-3">
          <div className="flex flex-wrap items-center gap-x-2 gap-y-1 text-[12.5px]">
            <span className="font-semibold text-warning">离线示意资产</span>
            <span className="text-ink-2">
              AI 生图失败（{asset.model_fallback.detail}），当前像素产物由离线确定性管线生成，
              可能与原始目标主题不符。
            </span>
            <Button
              variant="secondary"
              size="sm"
              icon="refresh"
              className="ml-auto"
              onClick={() => {
                navigate("/");
                toast({
                  tone: "info",
                  title: "回到工作台重新生成",
                  description: "原目标可在历史记录中一键重试",
                });
              }}
            >
              重新生成
            </Button>
          </div>
        </div>
      )}

      <div className="grid grid-cols-12 gap-5">
        {/* 左：大图预览（AI 原画优先，无原画时退回 3D 舞台） */}
        <Card
          className="col-span-12 lg:col-span-5"
          title="资产预览 Preview"
          icon="image"
          right={<Badge tone="neutral">{aiImage ? "AI 原画" : "3D 舞台"}</Badge>}
        >
          <div className="flex h-[320px] items-center justify-center overflow-hidden rounded-lg border border-line-subtle bg-canvas sm:h-[420px] lg:h-[500px]">
            {aiImage ? (
              <SafeImage
                src={aiImage}
                alt={asset.name ?? "AI 原画"}
                sealChar="画"
                className="h-full w-full object-contain"
              />
            ) : (
              <Suspense
                fallback={
                  <div className="grid h-full w-full place-items-center text-xs text-ink-3" role="status">
                    加载 3D 查看器…
                  </div>
                }
              >
                <AssetViewer textureUrl={`/api/assets/${encodeURIComponent(asset.id)}/image.png`} />
              </Suspense>
            )}
          </div>
          {aiImage ? (
            <div className="mt-3 flex flex-wrap items-center gap-x-3 gap-y-1.5 text-[11px] text-ink-3">
              {aiImageMeta?.model && <span>AI 原画 · {aiImageMeta.model}</span>}
              {asset.image?.cached && <Badge tone="neutral">来自缓存</Badge>}
              <button
                onClick={async () => {
                  try {
                    const r = await api.openFolder("generated");
                    toast({ tone: "success", title: "已打开图片文件夹", description: r.path });
                  } catch (cause) {
                    toast({ tone: "danger", title: "打开失败", description: String(cause).slice(0, 140) });
                  }
                }}
                className="font-medium text-primary underline-offset-2 hover:underline"
              >
                打开所在文件夹
              </button>
              <span className="cf-ref ml-auto">
                {asset.source?.ai_image?.width
                  ? `${asset.source.ai_image.width} × ${asset.source.ai_image.height}`
                  : `${asset.source.width} × ${asset.source.height}`}
              </span>
            </div>
          ) : (
            <div className="mt-3 flex items-center gap-1.5 text-[11px] text-ink-3">
              <Icon name="refresh" className="h-3.5 w-3.5" />
              3D 舞台 · 当前角色像素重建实时贴图（拖拽旋转）
            </div>
          )}
        </Card>

        {/* 右：档案册（基础信息 / 文件信息 / 质量评估） */}
        <Card
          className="cf-dossier col-span-12 lg:col-span-7"
          title="角色档案 Dossier"
          icon="cube"
          bodyClassName="p-0"
          right={
            <div className="flex flex-wrap items-center gap-2">
              {asset.image && (
                <Badge tone="primary" icon="spark">
                  AI 原画 · {asset.image.model}
                </Badge>
              )}
              <Badge tone="primary">{asset.character?.summary ?? "CharacterSpec"}</Badge>
            </div>
          }
        >
          <DossierSection eyebrow="01 · Identity" title="基础信息">
            <div className="grid gap-x-7 md:grid-cols-2">
              <div>
                <KV label="资产 ID" value={asset.id} />
                <KV label="名称 Name" value={asset.name ?? "—"} />
                <KV label="类型 / 定位" value={`${asset.type ?? "character"} / ${asset.role ?? "—"}`} />
                <KV label="来源 Source" value={sourceLabel} />
                {spec && (
                  <>
                    <KV label="性别 / 体型" value={pair(spec.gender_label, spec.build_label)} />
                    <KV label="职业 / 元素" value={pair(spec.class_label, spec.element_label)} />
                    <KV label="角色定位 Role" value={label(spec.role_label)} />
                  </>
                )}
              </div>
              <div>
                {spec ? (
                  <>
                    <KV label="身高 Height" value={spec.height_cm != null ? `${spec.height_cm} cm` : "—"} />
                    <KV label="发型 / 发色" value={pair(spec.hair_color_label, spec.hair_style_label)} />
                    <KV label="瞳色 / 肤色" value={pair(spec.eyes_label, spec.skin_label)} />
                    <KV label="神态 Expression" value={label(spec.expression_label)} />
                    <KV label="武器 Weapon" value={label(spec.weapon_label)} />
                    <KV
                      label="配饰 Accessory"
                      value={spec.accessory?.length ? spec.accessory.join(" / ") : "无"}
                    />
                    <KV label="Seed" value={spec.seed ?? "—"} />
                  </>
                ) : (
                  <p className="py-2 text-xs text-ink-3">该资产由旧版本生成，未包含 CharacterSpec。</p>
                )}
              </div>
            </div>
            <div className="mt-3 rounded-md border border-line-subtle bg-surface-2/50 p-3">
              <div className="mb-1 cf-ref">Source Prompt</div>
              <p className="text-[12.5px] leading-5 text-ink-2">{asset.source.prompt ?? "—"}</p>
            </div>
            {asset.prompt_enhance?.prompt && (
              <div className="mt-2 rounded-md border border-primary/30 bg-primary-tint/40 p-3">
                <div className="mb-1 flex items-center gap-1.5 text-[10.5px] font-semibold uppercase tracking-[0.08em] text-primary">
                  <Icon name="spark" className="h-3.5 w-3.5" />
                  增强提示词 · {asset.prompt_enhance.model}
                </div>
                <p className="text-[12.5px] leading-5 text-ink-2">{asset.prompt_enhance.prompt}</p>
              </div>
            )}
          </DossierSection>

          <DossierSection
            eyebrow="02 · Engine"
            title="文件信息"
            right={
              <Badge tone={asset.engine?.validation.status === "success" ? "gimport" : "danger"}>
                <Icon
                  name={asset.engine?.validation.status === "success" ? "check" : "x"}
                  className="h-3.5 w-3.5"
                />
                {asset.engine?.validation.status ?? "—"} · {asset.engine?.validation.score ?? 0}
              </Badge>
            }
          >
            {resources.length > 0 ? (
              <div className="flex flex-wrap gap-2">
                {resources.map(([key, path]) => (
                  <Badge key={key} tone="neutral">
                    {key}: {String(path).split("/").pop()}
                  </Badge>
                ))}
              </div>
            ) : (
              <p className="text-[12px] text-ink-3">未包含引擎资源</p>
            )}
            <div className="mt-2">
              {checks.length > 0 ? (
                checks.map((check) => (
                  <div
                    key={check.name}
                    className="flex items-center gap-2.5 border-b border-ink/[.08] py-1.5 text-[12.5px] text-ink-2 last:border-0"
                  >
                    <Icon
                      name={check.passed ? "check" : "x"}
                      className={check.passed ? "h-4 w-4 text-success" : "h-4 w-4 text-danger"}
                    />
                    <span className="font-mono text-[11.5px]">{check.name}</span>
                    <span className="ml-auto text-[11px] text-ink-3">
                      {check.passed ? "pass" : "fail"}
                    </span>
                  </div>
                ))
              ) : (
                <p className="text-[12px] text-ink-3">暂无校验项</p>
              )}
            </div>
          </DossierSection>

          <DossierSection
            eyebrow="03 · QA Gate"
            title="质量评估"
            right={
              <Badge tone={report?.status === "PASS" ? "success" : "warning"}>
                {report?.status ?? "待验证"}
              </Badge>
            }
          >
            <div className="flex flex-wrap items-center gap-5">
              <ScoreRing
                value={
                  report
                    ? Object.values(report.scores).reduce((a, b) => a + b, 0) /
                      Object.keys(report.scores).length
                    : (asset.quality?.pixel?.overall ?? 0)
                }
                label="QA 均值"
                size={124}
              />
              <div className="min-w-[220px] flex-1 space-y-3">
                {report ? (
                  Object.entries(report.scores).map(([section, score]) => (
                    <ScoreBar
                      key={section}
                      label={`${section} · 阈值 ${report.thresholds[section] ?? "—"}`}
                      value={score}
                      threshold={report.thresholds[section]}
                      tone={
                        section === "pixel"
                          ? "precon"
                          : section === "animation"
                            ? "falign"
                            : section === "engine"
                              ? "gimport"
                              : "primary"
                      }
                    />
                  ))
                ) : (
                  <p className="text-xs text-ink-3">暂无 QA 报告</p>
                )}
              </div>
            </div>
            {(report?.retry?.length ?? 0) > 0 && (
              <div className="mt-4 flex items-center gap-2 border-t border-line-subtle pt-3.5">
                <Badge tone="warning" icon="refresh">
                  修复轮 {report!.retry.length}
                </Badge>
                <span className="text-[11.5px] text-ink-3">{report!.retry.slice(-1)[0]}</span>
              </div>
            )}
          </DossierSection>
        </Card>
      </div>
    </div>
  );
}

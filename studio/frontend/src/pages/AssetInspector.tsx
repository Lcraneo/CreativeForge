import { Suspense, lazy } from "react";
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
import { CharacterArt } from "../components/CharacterArt";
import { Icon } from "../components/icons";
import { api } from "../api/client";
import { toast } from "../stores/toastStore";
const AssetViewer = lazy(() => import("../three/AssetViewer"));

export default function AssetInspector() {
  const asset = useAssetLoader();
  const navigate = useNavigate();

  if (!asset) return <AssetLoadState />;

  const quality = asset.quality;
  const report = quality?.report;
  const spec = asset.character;
  const aiImage = asset.image?.url ?? asset.source?.ai_image?.url;
  const aiImageMeta = asset.image ?? asset.source?.ai_image;
  const label = (value: string | null | undefined) => (value ? value : "—");
  const pair = (...values: Array<string | null | undefined>) =>
    values
      .map(label)
      .filter((value) => value !== "—")
      .join(" · ") || "—";

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
        <div className="rounded-xl border border-warning/50 bg-warning/[.07] px-4 py-3">
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
        <Card className="col-span-12 lg:col-span-4" title="Identity / 身份" icon="cube">
          <div className="mb-3">
            <KV label="ID" value={asset.id} />
            <KV label="Name" value={asset.name ?? "—"} />
            <KV label="Type / Role" value={`${asset.type ?? "character"} / ${asset.role ?? "—"}`} />
            <KV
              label="Source"
              value={
                asset.source?.ai_image?.width
                  ? `${asset.source.ai_image.width} × ${asset.source.ai_image.height} · AI 原画`
                  : `${asset.source.width} × ${asset.source.height}`
              }
            />
          </div>
          {aiImage ? (
            <div className="flex h-[230px] items-center justify-center overflow-hidden rounded-[10px] border border-line-subtle bg-paper">
              <SafeImage
                src={aiImage}
                alt={asset.name ?? "AI 原画"}
                sealChar="画"
                className="max-h-full max-w-full object-contain"
              />
            </div>
          ) : (
            <>
              <div className="h-[230px] overflow-hidden rounded-[10px] border border-line-subtle bg-[radial-gradient(240px_160px_at_50%_20%,rgba(26,24,20,.06),transparent_70%),#f1efe9]">
                <Suspense
                  fallback={
                    <div className="grid h-full place-items-center text-xs text-ink-3" role="status">
                      加载 3D 查看器…
                    </div>
                  }
                >
                  <AssetViewer
                    textureUrl={`/api/assets/${encodeURIComponent(asset.id)}/image.png`}
                  />
                </Suspense>
              </div>
              <div className="mt-2.5 flex items-center gap-1.5 text-[11px] text-ink-3">
                <Icon name="refresh" className="h-3.5 w-3.5" />
                3D 舞台 · 当前角色像素重建实时贴图（拖拽旋转）
              </div>
            </>
          )}
          {aiImage && aiImageMeta?.model && (
            <div className="mt-2 flex items-center gap-2">
              <span className="text-[11px] text-ink-3">AI 原画 · {aiImageMeta.model}</span>
              {(asset.image as { cached?: boolean } | undefined)?.cached && (
                <Badge tone="neutral">来自缓存</Badge>
              )}
              <button
                onClick={async () => {
                  try {
                    const r = await api.openFolder("generated");
                    toast({ tone: "success", title: "已打开图片文件夹", description: r.path });
                  } catch (cause) {
                    toast({ tone: "danger", title: "打开失败", description: String(cause).slice(0, 140) });
                  }
                }}
                className="text-[11px] font-medium text-primary underline-offset-2 hover:underline"
              >
                打开所在文件夹
              </button>
            </div>
          )}
        </Card>

        <Card
          className="col-span-12 lg:col-span-8"
          domain="primary"
          title="Character / 提示词角色档案"
          icon="spark"
          right={
            <div className="flex items-center gap-2">
              {asset.image && (
                <Badge tone="primary" icon="spark">
                  AI 原画 · {asset.image.model}
                </Badge>
              )}
              <Badge tone="primary">{asset.character?.summary ?? "CharacterSpec"}</Badge>
            </div>
          }
        >
          {spec ? (
            <div className="grid grid-cols-12 gap-5">
              <div className="col-span-12 flex items-center justify-center overflow-hidden rounded-xl border border-line-subtle bg-[radial-gradient(120px_120px_at_50%_24%,rgba(26,24,20,.06),transparent_70%),#f1efe9] py-3 md:col-span-2">
                {asset.image?.url ? (
                  <SafeImage
                    src={asset.image.url}
                    alt={asset.name ?? "concept art"}
                    className="h-[180px] w-[150px] rounded-lg object-cover"
                    fallback={
                      <CharacterArt
                        spec={asset.character}
                        palette={asset.pixel?.palette.colors}
                        view="bust"
                        className="h-[180px] w-[150px]"
                      />
                    }
                  />
                ) : (
                  <CharacterArt
                    spec={asset.character}
                    palette={asset.pixel?.palette.colors}
                    view="bust"
                    className="h-[180px] w-[150px]"
                  />
                )}
              </div>
              <div className="col-span-12 md:col-span-5">
                <KV label="Gender / Build" value={pair(spec.gender_label, spec.build_label)} />
                <KV label="Class / Element" value={pair(spec.class_label, spec.element_label)} />
                <KV label="Role" value={label(spec.role_label)} />
                <KV label="Height" value={spec.height_cm != null ? `${spec.height_cm} cm` : "—"} />
                <KV label="Hair" value={pair(spec.hair_color_label, spec.hair_style_label)} />
              </div>
              <div className="col-span-12 md:col-span-5">
                <KV label="Eyes / Skin" value={pair(spec.eyes_label, spec.skin_label)} />
                <KV label="Expression" value={label(spec.expression_label)} />
                <KV label="Weapon" value={label(spec.weapon_label)} />
                <KV
                  label="Accessory"
                  value={spec.accessory?.length ? spec.accessory.join(" / ") : "无"}
                />
                <KV label="Seed" value={spec.seed ?? "—"} />
              </div>
              <div className="col-span-12 rounded-lg border border-line-subtle bg-surface-2/50 p-3">
                <div className="mb-1 text-[10.5px] font-semibold uppercase tracking-[0.08em] text-ink-4">
                  Source Prompt
                </div>
                <p className="text-[12.5px] leading-5 text-ink-2">{asset.source.prompt ?? "—"}</p>
              </div>
              {asset.prompt_enhance?.prompt && (
                <div className="col-span-12 rounded-lg border border-primary/30 bg-primary-tint/40 p-3">
                  <div className="mb-1 flex items-center gap-1.5 text-[10.5px] font-semibold uppercase tracking-[0.08em] text-primary">
                    <Icon name="spark" className="h-3.5 w-3.5" />
                    增强提示词 · {asset.prompt_enhance.model}
                  </div>
                  <p className="text-[12.5px] leading-5 text-ink-2">
                    {asset.prompt_enhance.prompt}
                  </p>
                </div>
              )}
            </div>
          ) : (
            <p className="text-xs text-ink-3">该资产由旧版本生成，未包含 CharacterSpec。</p>
          )}
        </Card>

        <Card
          className="col-span-12 lg:col-span-6"
          domain="gimport"
          title="Engine / GImport 引擎就绪"
          icon="package"
          iconClassName="text-gimport"
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
          <div className="mb-3 flex flex-wrap gap-2">
            {Object.entries(asset.engine?.resources ?? {}).map(([key, path]) => (
              <Badge key={key} tone="neutral">
                {key}: {String(path).split("/").pop()}
              </Badge>
            ))}
          </div>
          {(asset.engine?.validation.checks ?? []).map((check) => (
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
          ))}
        </Card>

        <Card
          className="col-span-12 lg:col-span-6"
          domain="qa"
          title="Quality / QA Gate"
          icon="check"
          iconClassName="text-warning"
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
        </Card>
      </div>
    </div>
  );
}

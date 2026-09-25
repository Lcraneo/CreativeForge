import { useNavigate } from "react-router-dom";
import { useAssetLoader } from "../stores/assetStore";
import {
  Badge,
  Button,
  Card,
  EmptyState,
  KV,
  PageHeader,
  ScoreBar,
  ScoreRing,
} from "../components/ui";
import { FrameFigure } from "../components/FrameFigure";
import { CharacterArt } from "../components/CharacterArt";
import { Icon } from "../components/icons";
import { toast } from "../stores/toastStore";
import AssetViewer from "../three/AssetViewer";

const FALLBACK_PALETTE = [
  "#07090d", "#4cc2ff", "#22d3ee", "#f4d58d", "#ff9d3d", "#a16207", "#dc2626", "#7f1d1d",
  "#0ea5e9", "#075985", "#16a34a", "#14532d", "#e4e4e7", "#a1a1aa", "#3a4658", "#1b2230",
];

export default function AssetInspector() {
  const asset = useAssetLoader();
  const navigate = useNavigate();

  if (!asset) {
    return (
      <div className="mx-auto w-full max-w-[1440px] px-4 py-5 md:px-6">
        <Card>
          <EmptyState
            icon="cube"
            title="还没有资产"
            description="先在工作台生成一个资产，这里会展示 CreativeAsset 五段协议：Identity → Pixel → Animation → Engine → Quality。"
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

  const quality = asset.quality;
  const report = quality?.report;
  const frames = asset.animation?.frames ?? [];
  const phases = asset.animation?.phase?.phase ?? [];
  const isStatic = Boolean(asset.character?.static) || !asset.animation?.phase;
  const palette = asset.pixel?.palette.colors?.length
    ? asset.pixel.palette.colors.slice(0, 16)
    : FALLBACK_PALETTE;

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
            <Button variant="secondary" icon="layers" onClick={() => navigate("/design")}>
              设计三视图
            </Button>
            <Button variant="primary" icon="package" onClick={() => navigate("/export")}>
              导出工程包
            </Button>
          </>
        }
      />

      <div className="grid grid-cols-12 gap-5">
        <Card className="col-span-12 lg:col-span-4" title="Identity / 身份" icon="cube">
          <div className="mb-3">
            <KV label="ID" value={asset.id} />
            <KV label="Name" value={asset.name ?? "—"} />
            <KV label="Type / Role" value={`${asset.type ?? "character"} / ${asset.role ?? "—"}`} />
            <KV label="Source" value={`${asset.source.width} × ${asset.source.height}`} />
          </div>
          <div className="h-[230px] overflow-hidden rounded-[10px] border border-line-subtle bg-[radial-gradient(240px_160px_at_50%_20%,rgba(76,194,255,.12),transparent_70%),#0a0e15]">
            <AssetViewer />
          </div>
          <div className="mt-2.5 flex items-center gap-1.5 text-[11px] text-ink-3">
            <Icon name="refresh" className="h-3.5 w-3.5" />
            拖拽旋转 · 滚轮缩放 · 自动旋转
          </div>
        </Card>

        <Card
          className="col-span-12 md:col-span-6 lg:col-span-4"
          domain="precon"
          title="Pixel / PReCon 像素重建"
          icon="grid"
          iconClassName="text-precon"
          right={<Badge tone="precon">{Math.round((quality?.pixel?.overall ?? 0) * 100)}%</Badge>}
        >
          <KV label="Grid" value={`${asset.pixel?.grid.size ?? "—"} × ${asset.pixel?.grid.size ?? "—"}`} />
          <KV label="Grid Confidence" value={asset.pixel?.grid.confidence ?? "—"} />
          <KV label="Palette Colors" value={asset.pixel?.palette.max_colors ?? "—"} />
          <KV label="Contour Style" value={asset.pixel?.contour.style ?? "—"} />
          <KV label="Repaired" value={asset.pixel?.contour.repaired ? "yes" : "no"} />
          <div className="mt-3">
            <ScoreBar
              label="pixel overall · 阈值 0.80"
              value={quality?.pixel?.overall ?? 0}
              threshold={0.8}
              tone="precon"
            />
          </div>
          <div className="mt-4 text-[10.5px] font-semibold uppercase tracking-[0.08em] text-ink-4">
            Semantic Palette
          </div>
          <div className="mt-2 grid grid-cols-8 gap-1.5">
            {palette.map((color, index) => (
              <button
                key={`${color}-${index}`}
                title={`${color} · 点击复制`}
                onClick={() => {
                  navigator.clipboard?.writeText(color).catch(() => undefined);
                  toast({ tone: "info", title: "已复制色值", description: color });
                }}
                className="h-6 rounded-sm border border-white/[.07] transition-transform hover:scale-110"
                style={{ background: color }}
              />
            ))}
          </div>
        </Card>

        <Card
          className="col-span-12 md:col-span-6 lg:col-span-4"
          domain={isStatic ? "memory" : "falign"}
          title={isStatic ? "Static / 静态资产" : "Animation / FAlign 对齐"}
          icon={isStatic ? "cube" : "film"}
          iconClassName={isStatic ? "text-ink-3" : "text-falign"}
          right={
            isStatic ? (
              <Badge tone="neutral">无动画</Badge>
            ) : (
              <Badge tone="falign">{Math.round((quality?.animation?.overall ?? 0) * 100)}%</Badge>
            )
          }
        >
          <KV label="Action / FPS" value={`${asset.animation?.action ?? "—"} / ${asset.animation?.fps ?? "—"}`} />
          <KV label="Frames / Loop" value={`${frames.length} / ${asset.animation?.loop ? "true" : "false"}`} />
          {isStatic ? (
            <>
              <KV label="Type" value={`${asset.type ?? "prop"} · 静态立绘/图标`} />
              <div className="mt-3 flex items-center gap-3 rounded-lg border border-line-subtle bg-surface-2/50 p-3">
                <CharacterArt
                  spec={asset.character}
                  palette={asset.pixel?.palette.colors}
                  view="bust"
                  className="h-16 w-14 shrink-0"
                  detail="simple"
                />
                <p className="text-[11.5px] leading-[18px] text-ink-3">
                  该目标被识别为静态资产，规划中不包含 FAlign 切帧对齐，直接进入 GImport 引擎导入。
                </p>
              </div>
            </>
          ) : (
            <>
              <KV
                label="Phase"
                value={phases.length ? phases.map((p) => p.toFixed(2)).join(" / ") : "—"}
              />
              <KV
                label="Drift Corrected"
                value={asset.animation?.motion?.drift_corrected ? "true" : "false"}
              />
              <div className="mt-3 flex gap-2 overflow-hidden">
                {frames.slice(0, 4).map((frame, index) => (
                  <div
                    key={frame.id}
                    className="flex w-[88px] shrink-0 flex-col items-center rounded-[10px] border border-line-subtle bg-surface-1 p-2"
                  >
                    <FrameFigure
                      phase={phases[index] ?? index / Math.max(1, frames.length - 1)}
                      active={index === 0}
                      className="h-16 w-14"
                    />
                    <span className="font-mono text-[10px] text-ink-4">#{frame.id}</span>
                  </div>
                ))}
              </div>
              <div className="mt-3">
                <ScoreBar
                  label="animation overall · 阈值 0.85"
                  value={quality?.animation?.overall ?? 0}
                  threshold={0.85}
                  tone="falign"
                />
              </div>
            </>
          )}
        </Card>

        <Card
          className="col-span-12"
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
              <Badge tone="primary">
                {asset.character?.summary ?? "CharacterSpec"}
              </Badge>
            </div>
          }
        >
          {asset.character ? (
            <div className="grid grid-cols-12 gap-5">
              <div className="col-span-12 flex items-center justify-center overflow-hidden rounded-xl border border-line-subtle bg-[radial-gradient(120px_120px_at_50%_24%,rgba(76,194,255,.12),transparent_70%),#0a0e15] py-3 md:col-span-2">
                {asset.image?.url ? (
                  <img
                    src={asset.image.url}
                    alt={asset.name ?? "concept art"}
                    className="h-[180px] w-[150px] rounded-lg object-cover"
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
                <KV label="Gender / Build" value={`${asset.character.gender_label} · ${asset.character.build_label}`} />
                <KV label="Class / Element" value={`${asset.character.class_label} · ${asset.character.element_label}`} />
                <KV label="Role" value={asset.character.role_label} />
                <KV label="Height" value={`${asset.character.height_cm} cm`} />
                <KV
                  label="Hair"
                  value={`${asset.character.hair_color_label}${asset.character.hair_style_label}`}
                />
              </div>
              <div className="col-span-12 md:col-span-5">
                <KV label="Eyes / Skin" value={`${asset.character.eyes_label} · ${asset.character.skin_label}`} />
                <KV label="Expression" value={asset.character.expression_label} />
                <KV label="Weapon" value={asset.character.weapon_label} />
                <KV
                  label="Accessory"
                  value={asset.character.accessory?.length ? asset.character.accessory.join(" / ") : "无"}
                />
                <KV label="Seed" value={asset.character.seed} />
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
                  <p className="text-[12.5px] leading-5 text-ink-2">{asset.prompt_enhance.prompt}</p>
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
              <Icon name={asset.engine?.validation.status === "success" ? "check" : "x"} className="h-3.5 w-3.5" />
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
              className="flex items-center gap-2.5 border-b border-white/[.04] py-1.5 text-[12.5px] text-ink-2 last:border-0"
            >
              <Icon
                name={check.passed ? "check" : "x"}
                className={check.passed ? "h-4 w-4 text-success" : "h-4 w-4 text-danger"}
              />
              <span className="font-mono text-[11.5px]">{check.name}</span>
              <span className="ml-auto text-[11px] text-ink-3">{check.passed ? "pass" : "fail"}</span>
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
              value={report ? Object.values(report.scores).reduce((a, b) => a + b, 0) / Object.keys(report.scores).length : (asset.quality?.pixel?.overall ?? 0)}
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
              <span className="text-[11.5px] text-ink-3">
                {report!.retry.slice(-1)[0]}
              </span>
            </div>
          )}
        </Card>
      </div>
    </div>
  );
}

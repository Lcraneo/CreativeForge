import { Link } from "react-router-dom";
import { useAssetLoader } from "../stores/assetStore";
import { Badge, Card, KV, ScoreBar } from "../components/ui";
import AssetViewer from "../three/AssetViewer";

export default function AssetInspector() {
  const asset = useAssetLoader();

  if (!asset) {
    return (
      <div className="mx-auto max-w-3xl px-8 py-16 text-center text-sm text-zinc-400">
        还没有资产。先到
        <Link to="/" className="mx-1 text-cyan-300 hover:underline">
          工作台
        </Link>
        生成一个。
      </div>
    );
  }

  const quality = asset.quality;
  const report = quality?.report;

  return (
    <div className="mx-auto max-w-6xl px-6 py-6">
      <header className="mb-5 flex items-center justify-between">
        <div>
          <h1 className="pixel-title text-sm font-semibold text-zinc-200">
            CreativeAsset Inspector
          </h1>
          <p className="mt-1 text-xs text-zinc-500">
            统一资产协议是整个系统的数据中心：Identity → Pixel → Animation → Engine → Quality
          </p>
        </div>
        <Badge tone="blue">{asset.engine?.target ?? "—"}</Badge>
      </header>

      <div className="grid grid-cols-[repeat(3,minmax(0,1fr))] gap-4">
        <Card title="Identity / 身份">
          <KV label="ID" value={asset.id} />
          <KV label="Name" value={asset.name ?? "—"} />
          <KV label="Type" value={asset.type ?? "character"} />
          <KV label="Role" value={asset.role ?? "—"} />
          <KV
            label="Source"
            value={`${asset.source.width}×${asset.source.height}`}
          />
          <div className="mt-3 h-56 overflow-hidden rounded-lg border border-zinc-800">
            <AssetViewer />
          </div>
        </Card>

        <Card title="Pixel / 像素重建（PReCon）">
          <KV label="Grid" value={asset.pixel?.grid.size ?? "—"} />
          <KV label="Grid Confidence" value={asset.pixel?.grid.confidence ?? "—"} />
          <KV label="Palette Colors" value={asset.pixel?.palette.max_colors ?? "—"} />
          <KV label="Contour" value={asset.pixel?.contour.style ?? "—"} />
          <KV label="Repaired" value={asset.pixel?.contour.repaired ? "yes" : "no"} />
          {quality?.pixel && (
            <div className="mt-3 space-y-2">
              <ScoreBar label="pixel overall" value={quality.pixel.overall} threshold={0.8} />
            </div>
          )}
        </Card>

        <Card title="Animation / 动画对齐（FAlign）">
          <KV label="Action" value={asset.animation?.action ?? "—"} />
          <KV label="Frames" value={asset.animation?.frames.length ?? 0} />
          <KV label="FPS" value={asset.animation?.fps ?? "—"} />
          <KV label="Loop" value={asset.animation?.loop ? "true" : "false"} />
          <KV
            label="Phase Aligned"
            value={asset.animation?.phase?.aligned ? "true" : "false"}
          />
          <KV
            label="Drift Corrected"
            value={asset.animation?.motion?.drift_corrected ? "true" : "false"}
          />
          {quality?.animation && (
            <div className="mt-3 space-y-2">
              <ScoreBar
                label="animation overall"
                value={quality.animation.overall}
                threshold={0.85}
              />
            </div>
          )}
        </Card>
      </div>

      <div className="mt-4 grid grid-cols-[repeat(2,minmax(0,1fr))] gap-4">
        <Card title="Engine / 引擎就绪（GImport）">
          <div className="mb-2 flex gap-2">
            <Badge tone={asset.engine?.validation.status === "success" ? "green" : "red"}>
              {asset.engine?.validation.status ?? "—"}
            </Badge>
            {Object.entries(asset.engine?.resources ?? {}).map(([key, path]) => (
              <Badge key={key}>{key}: {String(path).split("/").pop()}</Badge>
            ))}
          </div>
          <ul className="space-y-1">
            {(asset.engine?.validation.checks ?? []).map((check) => (
              <li key={check.name} className="flex items-center gap-2 text-xs">
                <span className={check.passed ? "text-emerald-400" : "text-red-400"}>
                  {check.passed ? "✓" : "×"}
                </span>
                <span className="font-mono text-zinc-400">{check.name}</span>
              </li>
            ))}
          </ul>
        </Card>

        <Card title="Quality / QA Gate">
          {report ? (
            <>
              <div className="mb-3 flex items-center gap-2">
                <Badge tone={report.status === "PASS" ? "green" : "cyan"}>
                  {report.status}
                </Badge>
                <span className="text-xs text-zinc-500">
                  thresholds: pixel {report.thresholds.pixel} / anim{" "}
                  {report.thresholds.animation} / engine {report.thresholds.engine}
                </span>
              </div>
              <div className="space-y-2">
                {Object.entries(report.scores).map(([section, score]) => (
                  <ScoreBar
                    key={section}
                    label={section}
                    value={score}
                    threshold={report.thresholds[section]}
                  />
                ))}
              </div>
            </>
          ) : (
            <p className="text-xs text-zinc-500">暂无 QA 报告</p>
          )}
        </Card>
      </div>
    </div>
  );
}

import { useState } from "react";
import { Link } from "react-router-dom";
import { useAssetLoader } from "../stores/assetStore";
import { useExportStore } from "../stores/exportStore";
import { api } from "../api/client";
import { Badge, Card, KV } from "../components/ui";

const ENGINES = [
  { id: "unity", label: "Unity" },
  { id: "cocos", label: "Cocos" },
  { id: "godot", label: "Godot" },
];

export default function ExportCenter() {
  const asset = useAssetLoader();
  const { exports, busy, error, add, setBusy, setError } = useExportStore();
  const [engine, setEngine] = useState("unity");

  async function runExport() {
    if (!asset || busy) return;
    setBusy(true);
    setError(null);
    try {
      const result = await api.exportAsset(asset.id, engine);
      add(result);
    } catch (cause) {
      setError(String(cause));
    } finally {
      setBusy(false);
    }
  }

  const latest = exports[0];

  return (
    <div className="mx-auto max-w-5xl px-6 py-6">
      <header className="mb-5">
        <h1 className="pixel-title text-sm font-semibold text-zinc-200">Export Center</h1>
        <p className="mt-1 text-xs text-zinc-500">
          GImport 一键导出：CreativeAsset → Manifest → Atlas → Animation → Prefab →
          引擎工程包
        </p>
      </header>

      {!asset ? (
        <div className="rounded-xl border border-zinc-800 bg-zinc-900/50 px-6 py-12 text-center text-sm text-zinc-400">
          还没有资产。先到
          <Link to="/" className="mx-1 text-amber-300 hover:underline">
            工作台
          </Link>
          生成一个。
        </div>
      ) : (
        <div className="grid grid-cols-[1fr_360px] gap-4">
          <div className="space-y-4">
            <Card title="导出流程 / Pipeline">
              <div className="flex flex-wrap items-center gap-2 text-xs">
                {["CreativeAsset", "Manifest", "Atlas", "Animation", "Prefab", "Engine Package"].map(
                  (step, index, all) => (
                    <span key={step} className="flex items-center gap-2">
                      <span className="rounded-lg border border-zinc-700 px-2.5 py-1 text-zinc-300">
                        {step}
                      </span>
                      {index < all.length - 1 && <span className="text-zinc-600">→</span>}
                    </span>
                  ),
                )}
              </div>

              <div className="mt-5 flex items-center gap-3">
                <div className="flex gap-2">
                  {ENGINES.map((item) => (
                    <button
                      key={item.id}
                      onClick={() => setEngine(item.id)}
                      className={`rounded-lg px-4 py-2 text-sm font-medium transition-colors ${
                        engine === item.id
                          ? "bg-amber-400 text-zinc-950"
                          : "border border-zinc-700 text-zinc-400 hover:border-zinc-500"
                      }`}
                    >
                      {item.label}
                    </button>
                  ))}
                </div>
                <button
                  onClick={runExport}
                  disabled={busy}
                  className="rounded-lg bg-emerald-400 px-6 py-2 text-sm font-semibold text-zinc-950 transition-colors hover:bg-emerald-300 disabled:opacity-40"
                >
                  {busy ? "导出中…" : "导出 ⬇"}
                </button>
              </div>
              {error && <p className="mt-3 text-xs text-red-400">{error}</p>}
            </Card>

            {latest && (
              <Card
                title={`包内容 / ${latest.package}`}
                right={
                  <a
                    href={latest.download_url}
                    className="rounded-lg bg-sky-500 px-3 py-1 text-xs font-semibold text-zinc-950 hover:bg-sky-400"
                  >
                    下载 zip
                  </a>
                }
              >
                <div className="mb-3 flex gap-2">
                  <Badge tone={latest.validation.status === "success" ? "green" : "red"}>
                    {latest.validation.status}
                  </Badge>
                  <Badge>{(latest.size_bytes / 1024).toFixed(1)} KB</Badge>
                  <Badge tone="blue">{latest.engine}</Badge>
                </div>
                <pre className="overflow-x-auto rounded-lg border border-zinc-800 bg-zinc-950 p-3 font-mono text-[11px] leading-relaxed text-zinc-300">
                  {renderTree(latest.files)}
                </pre>
              </Card>
            )}
          </div>

          <div className="space-y-4">
            <Card title="资产 / Asset">
              <KV label="id" value={asset.id} />
              <KV label="name" value={asset.name ?? "—"} />
              <KV label="type" value={asset.type ?? "character"} />
              <KV label="frames" value={asset.animation?.frames.length ?? 0} />
            </Card>

            {latest && (
              <Card title="导入校验 / Runtime Validation">
                <ul className="space-y-1">
                  {latest.validation.checks.map((check) => (
                    <li key={check.name} className="flex items-center gap-2 text-xs">
                      <span className={check.passed ? "text-emerald-400" : "text-red-400"}>
                        {check.passed ? "✓" : "×"}
                      </span>
                      <span className="font-mono text-zinc-400">{check.name}</span>
                    </li>
                  ))}
                </ul>
                <div className="mt-3 border-t border-zinc-800 pt-3">
                  <KV label="score" value={latest.validation.score} />
                </div>
              </Card>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

/** files -> ascii tree */
function renderTree(files: string[]): string {
  const lines: string[] = [];
  let directory = "";
  for (const file of files) {
    const [dir, name] = file.includes("/") ? file.split("/") : ["", file];
    if (dir !== directory) {
      directory = dir;
      lines.push(dir ? `${dir}/` : ".");
    }
    lines.push(`  └── ${name}`);
  }
  return lines.join("\n");
}

import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useAssetLoader } from "../stores/assetStore";
import { useExportStore } from "../stores/exportStore";
import { api } from "../api/client";
import { toast } from "../stores/toastStore";
import {
  Badge,
  Button,
  Card,
  EmptyState,
  KV,
  PageHeader,
  Segmented,
  Stepper,
} from "../components/ui";
import { Icon } from "../components/icons";
import type { ExportResult } from "../types";

const ENGINES = [
  { id: "unity", label: "Unity", icon: "cube" as const },
  { id: "cocos", label: "Cocos", icon: "cube" as const },
  { id: "godot", label: "Godot", icon: "cube" as const },
];

type EngineId = (typeof ENGINES)[number]["id"];

export default function ExportCenter() {
  const asset = useAssetLoader();
  const navigate = useNavigate();
  const { exports, busy, error, add, setBusy, setError } = useExportStore();
  const [engine, setEngine] = useState<EngineId>("unity");
  const [packing, setPacking] = useState(false);
  const [characterPackage, setCharacterPackage] = useState<
    import("../types").CharacterPackageResult | null
  >(null);

  async function runCharacterPackage() {
    if (!asset || packing) return;
    setPacking(true);
    setError(null);
    try {
      const result = await api.exportCharacterPackage(asset.id, engine);
      setCharacterPackage(result);
      toast({
        tone: "success",
        title: `资产包已生成 ${result.package}`,
        description: `三视图 ${result.artwork_count} 张 · 动作 ${result.animations.length} 个 · 引擎文件 ${result.engine_files} 个`,
      });
    } catch (cause) {
      setError(String(cause));
      toast({ tone: "danger", title: "资产包导出失败", description: String(cause).slice(0, 180) });
    } finally {
      setPacking(false);
    }
  }

  async function runExport() {
    if (!asset || busy) return;
    setBusy(true);
    setError(null);
    try {
      const result = await api.exportAsset(asset.id, engine);
      add(result);
      toast({
        tone: "success",
        title: `已导出 ${result.package}`,
        description: `${result.engine} · ${(result.size_bytes / 1024).toFixed(1)} KB · 校验 ${result.validation.status}`,
      });
    } catch (cause) {
      setError(String(cause));
      toast({ tone: "danger", title: "导出失败", description: String(cause) });
    } finally {
      setBusy(false);
    }
  }

  if (!asset) {
    return (
      <div className="mx-auto w-full max-w-[1440px] px-4 py-5 md:px-6">
        <Card>
          <EmptyState
            icon="package"
            title="还没有可导出的资产"
            description="先在工作台生成一个资产，GImport 会将其编译为可导入引擎的工程包。"
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

  const latest: ExportResult | undefined = exports[0];
  const stage = (done: boolean) => (done ? "done" : "pending") as "done" | "pending";

  return (
    <div className="mx-auto flex w-full max-w-[1440px] flex-col gap-5 px-4 py-5 md:px-6">
      <PageHeader
        overline="Export Center"
        title="导出中心"
        description="GImport 一键导出：CreativeAsset → Manifest → Atlas → Animation → Prefab → 引擎工程包"
        actions={<Segmented options={ENGINES} value={engine} onChange={setEngine} />}
      />

      <div className="grid grid-cols-12 gap-5">
        <div className="col-span-12 flex flex-col gap-5 xl:col-span-8">
          <Card
            title="导出流程"
            icon="activity"
            iconClassName="text-gimport"
            right={
              <Badge tone={latest ? "gimport" : "neutral"}>
                {latest ? "4 / 4 完成" : "等待导出"}
              </Badge>
            }
          >
            <Stepper
              steps={[
                { id: "asset", label: "Asset", state: "done" },
                { id: "manifest", label: "Manifest", state: stage(Boolean(latest)) },
                { id: "atlas", label: "Atlas", state: stage(Boolean(latest)) },
                { id: "animation", label: "Animation", state: stage(Boolean(latest)) },
                { id: "prefab", label: "Prefab", state: stage(Boolean(latest)) },
                { id: "package", label: "Package", state: latest ? "running" : "pending" },
              ]}
            />
            <div className="mt-6 flex flex-wrap items-center gap-3">
              <Button
                variant="primary"
                size="lg"
                icon="download"
                loading={busy}
                onClick={runExport}
              >
                {busy ? "导出中…" : `导出 ${ENGINES.find((e) => e.id === engine)?.label} 工程包`}
              </Button>
              <Button
                variant="secondary"
                size="lg"
                icon="package"
                loading={packing}
                onClick={runCharacterPackage}
                title="一个角色一个 zip：原画 + 三视图 + 全动作 GIF + 引擎包"
              >
                {packing ? "打包中…" : "一键资产包（含动画）"}
              </Button>
              {latest && (
                <a
                  href={latest.download_url}
                  className="inline-flex h-10 items-center gap-2 rounded-md border border-line bg-surface-2 px-5 text-sm font-semibold text-ink transition-colors hover:bg-surface-3"
                >
                  <Icon name="download" className="h-4 w-4" />
                  下载 {latest.package}
                </a>
              )}
              <span className="text-[11.5px] text-ink-3">
                {latest
                  ? `${(latest.size_bytes / 1024).toFixed(1)} KB · ${latest.files.length} files · zip`
                  : "选择引擎后点击导出，产出真实 zip 工程包"}
              </span>
            </div>
            {characterPackage && (
              <div className="mt-4 rounded-lg border border-line-subtle bg-surface-1 p-3">
                <div className="flex flex-wrap items-center gap-2">
                  <Badge tone="primary">{characterPackage.engine}</Badge>
                  <span className="text-[12.5px] font-semibold text-ink">
                    {characterPackage.package}
                  </span>
                  <span className="text-[11.5px] text-ink-3">
                    {(characterPackage.size_bytes / 1024).toFixed(1)} KB ·{" "}
                    {characterPackage.files.length} files
                  </span>
                  <a
                    href={characterPackage.download_url}
                    className="ml-auto inline-flex items-center gap-1.5 text-[12px] font-medium text-primary underline-offset-2 hover:underline"
                  >
                    <Icon name="download" className="h-3.5 w-3.5" />
                    下载资产包
                  </a>
                </div>
                <div className="mt-2 flex flex-wrap gap-1.5">
                  {characterPackage.animations.map((item) => (
                    <Badge key={item.gif} tone="neutral">
                      {item.action} · {item.engine} · {item.frames}f
                    </Badge>
                  ))}
                  {characterPackage.missing.length > 0 && (
                    <Badge tone="warning">缺 {characterPackage.missing.length} 项（见包内 manifest）</Badge>
                  )}
                </div>
              </div>
            )}
            {error && <p className="mt-3 text-xs text-danger">{error}</p>}
          </Card>

          {latest && (
            <Card
              title="包内容"
              icon="terminal"
              iconClassName="text-gimport"
              right={
                <>
                  <Badge tone={latest.validation.status === "success" ? "success" : "danger"}>
                    {latest.validation.status}
                  </Badge>
                  <Badge tone="primary">{latest.engine}</Badge>
                </>
              }
              bodyClassName="p-4"
            >
              <pre className="cf-scroll overflow-x-auto rounded-md border border-line-subtle bg-[#faf9f5] p-4 font-mono text-[11.5px] leading-[21px] text-ink-2">
                {renderTree(latest.files)}
              </pre>
            </Card>
          )}
        </div>

        <div className="col-span-12 flex flex-col gap-5 xl:col-span-4">
          <Card title="资产摘要" icon="cube">
            <KV label="id / name" value={`${asset.id} / ${asset.name ?? "—"}`} />
            <KV label="type / role" value={`${asset.type ?? "character"} / ${asset.role ?? "—"}`} />
            <KV
              label="frames / fps"
              value={`${asset.animation?.frames.length ?? 0} / ${asset.animation?.fps ?? "—"}`}
            />
            <KV label="pixel score" value={asset.quality?.pixel?.overall ?? "—"} />
            <KV label="animation score" value={asset.quality?.animation?.overall ?? "—"} />
          </Card>

          {latest && (
            <Card
              title="运行时校验"
              icon="check"
              right={<Badge tone="success">score {latest.validation.score}</Badge>}
            >
              {latest.validation.checks.map((check) => (
                <div
                  key={check.name}
                  className="flex items-center gap-2.5 border-b border-ink/[.08] py-1.5 text-[12.5px] text-ink-2 last:border-0"
                >
                  <Icon
                    name={check.passed ? "check" : "x"}
                    className={check.passed ? "h-4 w-4 text-success" : "h-4 w-4 text-danger"}
                  />
                  <span className="truncate font-mono text-[11.5px]">{check.name}</span>
                  <span className="ml-auto text-[11px] text-ink-3">
                    {check.passed ? "pass" : "fail"}
                  </span>
                </div>
              ))}
            </Card>
          )}

          <Card title="导出历史" icon="clock">
            {exports.length === 0 ? (
              <p className="text-xs text-ink-3">还没有导出记录。</p>
            ) : (
              <ol className="relative space-y-4 pl-1">
                <span className="absolute bottom-2 left-[10px] top-2 w-0.5 rounded-sm bg-line-subtle" />
                {exports.slice(0, 5).map((item, index) => (
                  <li key={`${item.package}-${index}`} className="relative flex gap-3.5">
                    <span className="relative z-10 mt-1 grid h-[22px] w-[22px] shrink-0 place-items-center rounded-full border-2 border-success bg-canvas text-success">
                      <Icon name="check" className="h-3 w-3" />
                    </span>
                    <div className="min-w-0 flex-1">
                      <div className="truncate text-[12.5px] font-medium">{item.package}</div>
                      <div className="text-[11.5px] text-ink-3">
                        {item.engine} · {(item.size_bytes / 1024).toFixed(1)} KB
                      </div>
                    </div>
                    <a
                      href={item.download_url}
                      className="text-ink-3 transition-colors hover:text-primary"
                      title="重新下载"
                    >
                      <Icon name="download" className="h-4 w-4" />
                    </a>
                  </li>
                ))}
              </ol>
            )}
          </Card>
        </div>
      </div>
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

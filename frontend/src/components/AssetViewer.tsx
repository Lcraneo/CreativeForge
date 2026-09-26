import { useCallback, useEffect, useState } from "react";
import { api, exportZipUrl } from "../api";
import type {
  AssetDetail,
  AssetSummary,
  DnaDetail,
  ExportResult,
} from "../types";

const ENGINES = ["cocos", "unity", "godot"];

const PROFILE_LABELS: Record<string, string> = {
  appearance: "外观",
  style: "风格",
  structure: "结构",
  equipment: "装备",
  motion: "动作",
  combat: "战斗",
};

function Section(props: {
  title: string;
  aside?: string;
  children: React.ReactNode;
}) {
  return (
    <section className="border-t border-line pt-5">
      <div className="flex items-baseline justify-between">
        <div className="text-xs uppercase tracking-widest text-mute">
          {props.title}
        </div>
        {props.aside && (
          <div className="text-xs text-mute">{props.aside}</div>
        )}
      </div>
      <div className="mt-4">{props.children}</div>
    </section>
  );
}

function KV(props: { k: string; v: unknown }) {
  if (props.v == null || props.v === "") return null;
  const value = Array.isArray(props.v)
    ? props.v.join("  ")
    : typeof props.v === "object"
      ? JSON.stringify(props.v)
      : String(props.v);
  if (!value) return null;
  return (
    <div className="flex gap-3 text-xs leading-relaxed">
      <span className="w-24 shrink-0 text-mute">{props.k}</span>
      <span className="break-all text-ink">{value}</span>
    </div>
  );
}

export default function AssetViewer(props: {
  assetId?: string;
  onOpenAsset: (assetId: string) => void;
}) {
  const [assetId, setAssetId] = useState<string | undefined>(props.assetId);
  const [asset, setAsset] = useState<AssetDetail | null>(null);
  const [dna, setDna] = useState<DnaDetail | null>(null);
  const [library, setLibrary] = useState<AssetSummary[]>([]);
  const [engine, setEngine] = useState("cocos");
  const [exported, setExported] = useState<ExportResult | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async (id?: string) => {
    setError(null);
    setExported(null);
    try {
      setLibrary(await api.listAssets(20));
      if (!id) return;
      const detail = await api.getAsset(id);
      setAsset(detail);
      const characterId = detail.metadata_json.dna?.character_id;
      setDna(characterId ? await api.getDna(characterId) : null);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  }, []);

  useEffect(() => {
    setAssetId(props.assetId);
    load(props.assetId);
  }, [props.assetId, load]);

  if (!assetId) {
    return (
      <div className="py-24 text-center text-sm text-mute">
        还没有资产 —— 从创作页生成一个角色吧。
      </div>
    );
  }

  const meta = asset?.metadata_json ?? {};
  const identity = meta.identity ?? {};
  const dnaBrief = meta.dna;
  const profile = dnaBrief?.identity?.dna_profile;
  const palette = meta.pixel?.palette?.colors ?? [];
  const layers = meta.content?.layers ?? [];
  const clips = meta.animation?.clips ?? [];
  const skills = meta.combat?.skills ?? [];
  const blueprints = meta.logic?.skills ?? [];
  const atlas = meta.animation?.atlas_detail;
  const spriteCount = atlas?.sprites?.length ?? 0;

  const doExport = async () => {
    setBusy(true);
    setError(null);
    try {
      setExported(await api.exportAsset(assetId, engine));
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  };

  const fileGroups = (() => {
    const groups = new Map<string, string[]>();
    for (const file of exported?.files ?? []) {
      const dir = file.includes("/")
        ? file.slice(0, file.lastIndexOf("/"))
        : "/";
      (groups.get(dir) ?? groups.set(dir, []).get(dir)!).push(file);
    }
    return [...groups.entries()];
  })();

  return (
    <div className="grid gap-14 lg:grid-cols-[220px_1fr]">
      <aside>
        <div className="text-xs uppercase tracking-widest text-mute">资产库</div>
        <ul className="mt-4 border-t border-line">
          {library.map((item) => (
            <li key={item.id} className="border-b border-line">
              <button
                onClick={() => {
                  setAssetId(item.id);
                  load(item.id);
                }}
                className={`w-full py-3 text-left text-xs transition-colors ${
                  item.id === assetId
                    ? "font-medium text-ink"
                    : "text-ink-2 hover:text-ink"
                }`}
              >
                <span className="block truncate">{item.name || item.id.slice(0, 8)}</span>
                <span className="mt-0.5 block text-mute">{item.status}</span>
              </button>
            </li>
          ))}
          {!library.length && (
            <li className="py-3 text-xs text-mute">（空）</li>
          )}
        </ul>
      </aside>

      <div>
        <div className="flex flex-wrap items-baseline gap-x-4 gap-y-2">
          <h1 className="font-display text-4xl font-black text-ink">
            {identity.name || asset?.name || "未命名角色"}
          </h1>
          {[identity.species, identity.role, dnaBrief?.identity?.style]
            .filter(Boolean)
            .map((tag) => (
              <span key={String(tag)} className="text-xs text-mute">
                {String(tag)}
              </span>
            ))}
          <span className="ml-auto border-b border-line-2 pb-0.5 text-xs text-ink-2">
            引擎目标：{meta.engine?.target ?? "—"}
          </span>
        </div>
        {error && (
          <p className="mt-5 border-l-2 border-bad pl-3 text-sm text-bad">
            {error}
          </p>
        )}

        <div className="mt-10 space-y-9">
          <Section title="Character DNA">
            {dnaBrief ? (
              <div className="space-y-1.5">
                <KV k="character_id" v={dnaBrief.character_id} />
                <KV k="版本" v={(dnaBrief.versions ?? []).join(" → ")} />
                <KV
                  k="编码模型"
                  v={`${dna?.embedding.model ?? "—"} · ${dna?.embedding.dim ?? "—"}d`}
                />
                {typeof dnaBrief.identity_similarity === "number" && (
                  <div className="flex items-center gap-3 pt-2">
                    <span className="w-24 text-xs text-mute">身份相似度</span>
                    <div className="h-1 w-40 overflow-hidden rounded bg-line">
                      <div
                        className="h-full rounded bg-ink"
                        style={{
                          width: `${Math.round(dnaBrief.identity_similarity * 100)}%`,
                        }}
                      />
                    </div>
                    <span className="font-mono text-xs text-ink">
                      {dnaBrief.identity_similarity}
                    </span>
                  </div>
                )}
              </div>
            ) : (
              <div className="text-sm text-mute">（无 DNA 记录）</div>
            )}
            {profile && (
              <div className="mt-6 grid gap-x-10 gap-y-5 border-t border-line pt-5 sm:grid-cols-2">
                {Object.entries(profile).map(([key, value]) => (
                  <div key={key}>
                    <div className="text-xs font-medium text-ink">
                      {PROFILE_LABELS[key] ?? key}
                    </div>
                    <div className="mt-1.5 space-y-0.5">
                      {Object.entries(value as Record<string, unknown>)
                        .slice(0, 4)
                        .map(([k, v]) => (
                          <KV key={k} k={k} v={v} />
                        ))}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </Section>

          <Section
            title="图层结构"
            aside={`${layers.length} 层`}
          >
            <ul className="divide-y divide-line">
              {layers.map((layer, i) => (
                <li key={i} className="flex items-center gap-3 py-2.5 text-xs">
                  <span className="font-medium text-ink">{layer.name}</span>
                  <span className="text-mute">{layer.type}</span>
                  <span className="ml-auto font-mono text-mute">
                    conf{" "}
                    {typeof layer.confidence === "number"
                      ? layer.confidence.toFixed(2)
                      : "—"}
                  </span>
                </li>
              ))}
              {!layers.length && (
                <li className="py-2 text-sm text-mute">（无图层）</li>
              )}
            </ul>
            {palette.length > 0 && (
              <div className="mt-5 flex flex-wrap gap-2.5">
                {palette.slice(0, 12).map((color, i) => (
                  <div key={i} className="text-center">
                    <div
                      className="h-8 w-8 rounded-md border border-line-2"
                      style={{ background: color }}
                    />
                    <div className="mt-1 font-mono text-[9px] text-mute">
                      {color}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </Section>

          <Section
            title="动画"
            aside={`${clips.length} clips${spriteCount ? ` · ${spriteCount} sprites` : ""}`}
          >
            <ul className="divide-y divide-line">
              {clips.map((clip, i) => (
                <li
                  key={i}
                  className="flex items-baseline gap-4 py-2.5 text-xs"
                >
                  <span className="font-mono font-medium text-ink">
                    {clip.name}
                  </span>
                  <span className="text-mute">
                    {clip.fps ?? "—"} fps · {clip.duration ?? "—"}s
                  </span>
                  <span className="ml-auto text-mute">
                    {clip.events?.length ?? 0} events
                  </span>
                </li>
              ))}
              {!clips.length && (
                <li className="py-2 text-sm text-mute">（无动画剪辑）</li>
              )}
            </ul>
            {typeof meta.animation?.motion?.max_root_residual === "number" && (
              <div className="mt-4">
                <KV
                  k="根锚点残差"
                  v={`${meta.animation.motion.max_root_residual} px（<1 为稳定）`}
                />
              </div>
            )}
          </Section>

          <Section title="技能">
            <ul className="divide-y divide-line">
              {skills.map((skill, i) => (
                <li key={i} className="flex items-baseline gap-4 py-2.5 text-xs">
                  <span className="font-mono font-medium text-ink">
                    {skill.skill}
                  </span>
                  <span className="text-mute">{skill.animation}</span>
                  <span className="ml-auto font-mono text-ink">
                    {skill.damage}
                  </span>
                  <span className="w-14 text-right text-mute">
                    {skill.element ?? "—"}
                  </span>
                </li>
              ))}
              {!skills.length && (
                <li className="py-2 text-sm text-mute">（无技能）</li>
              )}
            </ul>
            <div className="mt-4 space-y-1">
              <KV k="hitboxes" v={meta.combat?.hitboxes?.length ?? 0} />
              <KV k="hurtboxes" v={meta.combat?.hurtboxes?.length ?? 0} />
            </div>
            {blueprints.length > 0 && (
              <div className="mt-6 rounded-lg bg-panel p-4">
                <div className="text-xs font-medium text-ink">
                  CreativeSkill 蓝图 · {blueprints[0].name}
                </div>
                <div className="mt-2 space-y-0.5">
                  <KV k="cooldown" v={blueprints[0].trigger?.cooldown} />
                  <KV k="effect" v={blueprints[0].effect} />
                  <KV k="unity 脚本" v={blueprints[0].engine?.unity?.script} />
                </div>
              </div>
            )}
          </Section>

          <Section title="引擎导出">
            <div className="flex flex-wrap items-center gap-4">
              <div className="flex overflow-hidden rounded-lg border border-line-2">
                {ENGINES.map((item) => (
                  <button
                    key={item}
                    onClick={() => setEngine(item)}
                    className={`px-4 py-1.5 text-sm capitalize transition-colors ${
                      engine === item
                        ? "bg-ink text-paper"
                        : "text-ink-2 hover:bg-panel"
                    }`}
                  >
                    {item}
                  </button>
                ))}
              </div>
              <button
                onClick={doExport}
                disabled={busy}
                className="rounded-lg bg-ink px-5 py-1.5 text-sm text-paper transition-opacity hover:opacity-85 disabled:cursor-not-allowed disabled:opacity-40"
              >
                {busy ? "导出中…" : "导出资源树"}
              </button>
              <a
                href={exportZipUrl(assetId, engine)}
                download
                className="text-sm text-ink-2 underline decoration-line-2 underline-offset-4 transition-colors hover:text-ink hover:decoration-ink"
              >
                下载 {engine}.zip
              </a>
            </div>

            {exported && (
              <div className="mt-6">
                <div className="flex flex-wrap items-center gap-4 text-xs">
                  <span className="font-mono text-ink-2">{exported.root}</span>
                  <span className="text-mute">
                    manifest {exported.quality.manifest_score} · runtime{" "}
                    {exported.quality.runtime_score}
                  </span>
                </div>
                <div className="mt-3 grid gap-x-10 gap-y-4 sm:grid-cols-2">
                  {fileGroups.map(([dir, files]) => (
                    <div key={dir}>
                      <div className="font-mono text-xs text-ink">{dir}/</div>
                      {files.map((file) => (
                        <div
                          key={file}
                          className="mt-1 font-mono text-[11px] text-mute"
                        >
                          {file.slice(dir.length + 1)}
                        </div>
                      ))}
                    </div>
                  ))}
                </div>
              </div>
            )}
          </Section>
        </div>
      </div>
    </div>
  );
}

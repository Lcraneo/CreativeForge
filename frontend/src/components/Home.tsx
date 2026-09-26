import { useEffect, useRef, useState } from "react";
import gsap from "gsap";
import { api } from "../api";
import type { AssetSummary, RegistryArtifact } from "../types";
import {
  ArchiveIllustration,
  ForgeIllustration,
  PenIllustration,
  TimelineIllustration,
} from "./Illustrations";

function formatDate(iso: string | null): string {
  if (!iso) return "";
  const d = new Date(iso);
  return `${String(d.getMonth() + 1).padStart(2, "0")}/${String(d.getDate()).padStart(2, "0")} 更新`;
}

function Card(props: {
  art: React.ReactNode;
  title: string;
  desc: string;
  onOpen: () => void;
}) {
  return (
    <button
      onClick={props.onOpen}
      className="group text-left"
      data-card
    >
      <div className="overflow-hidden">
        <div className="transition-transform duration-700 ease-out group-hover:scale-[1.04]">
          {props.art}
        </div>
      </div>
      <div className="mt-5 flex items-start justify-between gap-4">
        <div>
          <h3 className="text-lg font-medium text-ink">{props.title}</h3>
          <p className="mt-1.5 text-sm leading-relaxed text-mute">{props.desc}</p>
        </div>
        <span className="mt-1 shrink-0 text-lg text-ink transition-transform duration-500 group-hover:-translate-y-0.5 group-hover:translate-x-0.5">
          &#8599;
        </span>
      </div>
    </button>
  );
}

export default function Home(props: {
  onOpen: (view: "studio" | "timeline" | "viewer") => void;
}) {
  const [assets, setAssets] = useState<AssetSummary[]>([]);
  const [registry, setRegistry] = useState<RegistryArtifact | null>(null);
  const [training, setTraining] = useState<string | null>(null);
  const root = useRef<HTMLDivElement>(null);

  useEffect(() => {
    api.listAssets(6).then(setAssets).catch(() => {});
    api.registry().then((r) => {
      const production = r.artifacts.find(
        (a) => a.status === "production" && a.name === "dna_encoder",
      );
      setRegistry(production ?? null);
    }).catch(() => {});
  }, []);

  useEffect(() => {
    if (!root.current) return;
    const ctx = gsap.context(() => {
      gsap.fromTo(
        "[data-hero-line]",
        { y: 28, opacity: 0 },
        { y: 0, opacity: 1, duration: 0.9, ease: "power3.out", stagger: 0.12 },
      );
      gsap.fromTo(
        "[data-card]",
        { y: 26, opacity: 0 },
        { y: 0, opacity: 1, duration: 0.8, ease: "power3.out", stagger: 0.09, delay: 0.25 },
      );
      gsap.fromTo(
        "[data-row]",
        { y: 14, opacity: 0 },
        { y: 0, opacity: 1, duration: 0.6, ease: "power2.out", stagger: 0.06, delay: 0.45 },
      );
    }, root);
    return () => ctx.revert();
  }, []);

  const trainModel = async () => {
    setTraining("训练中…");
    try {
      const report = (await api.trainModel()).report;
      const before = report.metrics_before?.margin;
      const after = report.metrics_after?.margin;
      setTraining(
        `margin ${before} → ${after} · v${report.artifact?.version} 已部署`,
      );
    } catch (err) {
      setTraining(`训练失败：${err instanceof Error ? err.message : err}`);
    }
  };

  return (
    <div ref={root}>
      {/* Attention — hero */}
      <section className="pt-14 pb-12">
        <h1
          data-hero-line
          className="font-display text-[clamp(4rem,9vw,6.5rem)] leading-none font-black tracking-wide text-ink"
        >
          工作台
        </h1>
        <p data-hero-line className="mt-5 text-base text-ink-2">
          一句话，到任何引擎
        </p>
      </section>

      {/* Interest — bento cards + recent assets */}
      <div className="grid grid-cols-1 gap-x-14 gap-y-16 lg:grid-cols-12">
        <div className="grid grid-cols-1 gap-x-10 gap-y-14 sm:grid-cols-2 lg:col-span-7">
          <Card
            art={<PenIllustration />}
            title="快速开始"
            desc="用自然语言建立角色、造型与动作的标准生产流程。"
            onOpen={() => props.onOpen("studio")}
          />
          <Card
            art={<TimelineIllustration />}
            title="Agent 时间线"
            desc="查看 DAG 规划、并行分支与每一步执行轨迹。"
            onOpen={() => props.onOpen("timeline")}
          />
          <Card
            art={<ArchiveIllustration />}
            title="资产库"
            desc="按项目整理角色、造型、动作与引擎资产。"
            onOpen={() => props.onOpen("viewer")}
          />
          <div data-card>
            <div className="overflow-hidden">
              <div className="transition-transform duration-700 ease-out group-hover:scale-[1.04]">
                <ForgeIllustration />
              </div>
            </div>
            <div className="mt-5 flex items-start justify-between gap-4">
              <div>
                <h3 className="text-lg font-medium text-ink">DNA 模型工坊</h3>
                <p className="mt-1.5 text-sm leading-relaxed text-mute">
                  从资产库训练身份投影头，实时查看训练收益。
                </p>
                <div className="mt-3 flex items-center gap-3">
                  <button
                    onClick={trainModel}
                    className="rounded-full border border-ink px-4 py-1 text-xs text-ink transition-colors hover:bg-ink hover:text-paper"
                  >
                    训练模型
                  </button>
                  {registry && (
                    <span className="text-xs text-mute">
                      production v{registry.version}
                    </span>
                  )}
                </div>
                {training && (
                  <p className="mt-2 font-mono text-xs text-go">{training}</p>
                )}
              </div>
            </div>
          </div>
        </div>

        {/* Desire — live asset list */}
        <aside className="lg:col-span-5">
          <h2 data-row className="text-2xl font-semibold text-ink">
            最近资产
          </h2>
          <div
            data-row
            className="mt-6 flex items-center justify-between rounded-lg bg-panel px-4 py-3 text-sm text-ink-2"
          >
            <span>{assets.length} 个资产</span>
            <button
              onClick={() => props.onOpen("viewer")}
              className="transition-colors hover:text-ink"
            >
              资产列表
            </button>
          </div>
          <ul className="mt-2">
            {assets.map((asset) => (
              <li key={asset.id} data-row className="border-b border-line">
                <button
                  onClick={() => props.onOpen("viewer")}
                  className="group flex w-full items-center justify-between gap-4 py-4 text-left"
                >
                  <div>
                    <div className="font-medium text-ink">{asset.name}</div>
                    <div className="mt-1 text-xs text-mute">
                      {formatDate(asset.created_at)}
                    </div>
                  </div>
                  <span className="text-ink-2 transition-transform duration-500 group-hover:-translate-y-0.5 group-hover:translate-x-0.5">
                    &#8599;
                  </span>
                </button>
              </li>
            ))}
            {!assets.length && (
              <li data-row className="py-8 text-sm text-mute">
                还没有资产 —— 从「快速开始」创建第一个角色。
              </li>
            )}
          </ul>

          {/* Action */}
          <div data-row className="mt-10 flex items-center gap-3">
            <button
              onClick={() => props.onOpen("viewer")}
              className="flex items-center gap-2 rounded-lg px-4 py-2 text-sm text-ink-2 transition-colors hover:bg-panel hover:text-ink"
            >
              <span aria-hidden>&#8635;</span> 全部资产
            </button>
            <button
              onClick={() => props.onOpen("studio")}
              className="rounded-lg bg-ink px-5 py-2 text-sm text-paper transition-opacity hover:opacity-85"
            >
              + 新建资产
            </button>
          </div>
        </aside>
      </div>
    </div>
  );
}

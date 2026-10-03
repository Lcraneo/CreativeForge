import { useEffect, useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api, type ShowcaseJob } from "../api/client";
import { Badge, Button, Card, EmptyState, PageHeader, cx } from "../components/ui";
import { Icon } from "../components/icons";
import { toast } from "../stores/toastStore";
import type { HistoryRecord } from "../types";

// OneTake 五拍叙事（adapters/onetake/timeline_mapper 的固定节拍，前端只做展示）
const BEATS: Array<{ key: string; label: string; hint: string }> = [
  { key: "hook", label: "一句话意图", hint: "kinetic type 开场" },
  { key: "art", label: "原画就绪", hint: "真实 AI 原画定格" },
  { key: "pixel", label: "像素重建", hint: "PReCon 观感扫描" },
  { key: "anim", label: "动作展开", hint: "FAlign 帧序列 + 手势驱动" },
  { key: "engine", label: "引擎预览", hint: "GImport → Cocos 运行窗" },
];

const STAGE_LABEL: Record<string, string> = {
  prepare: "素材准备中…",
  compose: "合成节拍中…",
  voice: "配音合成中…",
  render: "渲染中（1080p30，约 1~3 分钟）…",
  verify: "oracle 验收中…",
  done: "完成",
  failed: "失败",
};

const ERROR_KIND_LABEL: Record<string, string> = {
  material: "素材缺失",
  environment: "渲染环境未安装",
  fatal: "生成失败",
};

/** 把历史记录收敛为可展示的人物（有资产 + 有图）——与试玩舞台同一选择语义 */
export function peopleFromHistory(records: HistoryRecord[]) {
  return (records ?? []).filter(
    (record) => record.asset_id && (record.image?.url || (record.asset ?? {}).image?.url),
  );
}

/** job 状态 → 用户可读状态短语（单测覆盖） */
export function jobStageLabel(job: Pick<ShowcaseJob, "status" | "stage"> | null): string {
  if (!job) return "待开始";
  if (job.status === "done") return "完成";
  if (job.status === "failed") return "失败";
  return STAGE_LABEL[job.stage] ?? "处理中…";
}

export default function ShowcaseStudio() {
  const [selected, setSelected] = useState<{ id: string; name: string } | null>(null);
  const [jobId, setJobId] = useState<string | null>(null);
  const [previewOpen, setPreviewOpen] = useState(false);

  const history = useQuery({
    queryKey: ["showcase-people"],
    queryFn: () => api.listHistory({ limit: 12 }),
  });
  const people = useMemo(() => peopleFromHistory(history.data?.records ?? []), [history.data]);

  const job = useQuery({
    queryKey: ["showcase-job", jobId],
    queryFn: () => api.showcaseStatus(jobId!),
    enabled: Boolean(jobId),
    refetchInterval: (query) => (query.state.data?.status === "running" ? 2500 : false),
  });
  const jobData = job.data ?? null;

  useEffect(() => {
    if (jobData?.status === "done") {
      toast({ tone: "success", title: "发布片已生成", description: "成片与 oracle 验收报告见下方" });
    }
  }, [jobData?.status]);

  async function generate() {
    if (!selected?.id || jobData?.status === "running") return;
    setPreviewOpen(false);
    try {
      const result = await api.startShowcase(selected.id);
      setJobId(result.job_id);
      toast({ tone: "info", title: "发布片生成中", description: "五拍一镜到底，约 1~3 分钟" });
    } catch (cause) {
      toast({ tone: "danger", title: "发布片生成失败", description: String(cause).slice(0, 160) });
    }
  }

  return (
    <div className="mx-auto flex w-full max-w-[1440px] flex-col gap-5 px-4 py-5 md:px-6">
      <PageHeader
        overline="Showcase"
        title="发布展示间"
        description="CreativeAsset → OneTake 一镜到底发布片：像素重建、动作展开、引擎预览，15 秒讲完整个闭环"
        actions={
          <Badge tone={jobData?.status === "done" ? "primary" : "neutral"} icon="spark">
            {jobData?.status === "done" ? "成片就绪" : jobStageLabel(jobData)}
          </Badge>
        }
      />

      <div className="grid grid-cols-12 gap-5">
        <Card className="col-span-12 lg:col-span-8" title="Asset Timeline · 一镜到底" icon="film">
          {!selected ? (
            <EmptyState
              icon="cube"
              title="先选择一个角色"
              description="从右侧近期生成中挑选一个已有原画与动作帧的角色"
            />
          ) : (
            <>
              <div className="flex flex-wrap items-center gap-3">
                <Badge tone="primary" icon="cube">
                  {selected.name}
                </Badge>
                <span className="text-[11.5px] text-ink-3">
                  发布片 15 秒 · 1080p30 草稿 · onetake 渲染管线（PolyForm NC）
                </span>
                <Button
                  variant="primary"
                  size="sm"
                  icon="spark"
                  className="ml-auto"
                  loading={jobData?.status === "running"}
                  onClick={() => void generate()}
                >
                  {jobData?.status === "running" ? "生成中…" : "Generate OneTake Demo"}
                </Button>
              </div>

              <ol className="mt-4 flex flex-col gap-0">
                {BEATS.map((beat, index) => (
                  <li key={beat.key} className="flex gap-3">
                    <div className="flex flex-col items-center">
                      <span
                        className={cx(
                          "grid h-7 w-7 place-items-center rounded-full border text-[11px] font-semibold",
                          jobData?.status === "done"
                            ? "border-primary/60 bg-primary-tint text-ink"
                            : "border-line-subtle bg-surface-2 text-ink-3",
                        )}
                      >
                        {index + 1}
                      </span>
                      {index < BEATS.length - 1 && <span className="my-1 w-px flex-1 bg-line-subtle" />}
                    </div>
                    <div className="pb-4">
                      <div className="text-[13px] font-medium text-ink">{beat.label}</div>
                      <div className="text-[11px] text-ink-3">{beat.hint}</div>
                    </div>
                  </li>
                ))}
              </ol>

              {jobData?.status === "running" && (
                <p className="flex items-center gap-1.5 text-[12px] text-ink-2">
                  <Icon name="clock" className="h-3.5 w-3.5 animate-pulse" />
                  {jobStageLabel(jobData)}
                </p>
              )}
              {jobData?.status === "failed" && (
                <div className="mt-3 rounded-md border border-danger/40 bg-danger/5 px-3 py-2 text-[12px] text-danger">
                  {ERROR_KIND_LABEL[jobData.error_kind ?? ""] ?? "生成失败"}：{jobData.error}
                </div>
              )}
              {jobData?.status === "done" && jobData.video_url && (
                <div className="mt-4 flex flex-col gap-3">
                  <video
                    key={jobData.video_url}
                    className="w-full rounded-xl border border-line-subtle bg-black"
                    src={jobData.video_url}
                    poster={jobData.poster_url}
                    controls
                    autoPlay
                    loop
                  />
                  <div className="flex flex-wrap items-center gap-2 text-[11.5px] text-ink-3">
                    {jobData.voice && (
                      <Badge tone={jobData.voice.degraded ? "neutral" : "primary"} icon="spark">
                        {jobData.voice.degraded ? "音效版" : "有声版"}
                      </Badge>
                    )}
                    {jobData.verdict && (
                      <Badge tone={jobData.verdict.passed ? "primary" : jobData.verdict.passed === null ? "neutral" : "danger"}>
                        oracle {jobData.verdict.passed === true ? "PASS" : jobData.verdict.passed === null ? "未验收" : "FAIL"}
                      </Badge>
                    )}
                    <a className="underline underline-offset-2 hover:text-ink" href={jobData.video_url} download>
                      下载成片
                    </a>
                    <button
                      className="underline underline-offset-2 hover:text-ink"
                      onClick={() => setPreviewOpen((open) => !open)}
                    >
                      {previewOpen ? "收起实时预览" : "合成实时预览（?play）"}
                    </button>
                  </div>
                  {previewOpen && jobData.preview_url && (
                    <div className="aspect-video w-full overflow-hidden rounded-xl border border-line-subtle bg-[#f1efe9]">
                      <iframe
                        title="showcase composition preview"
                        src={`${jobData.preview_url}?play`}
                        sandbox="allow-scripts"
                        className="h-full w-full"
                      />
                    </div>
                  )}
                  {jobData.verdict?.report_tail && (
                    <details className="rounded-lg border border-line-subtle bg-surface-2 px-3 py-2">
                      <summary className="cursor-pointer text-[11.5px] text-ink-3">oracle 验收报告</summary>
                      <pre className="cf-scroll mt-2 max-h-56 overflow-auto whitespace-pre-wrap font-mono text-[10.5px] leading-relaxed text-ink-2">
                        {jobData.verdict.report_tail}
                      </pre>
                    </details>
                  )}
                </div>
              )}
            </>
          )}
        </Card>

        <Card className="col-span-12 lg:col-span-4" title="选择角色 · 近期生成" icon="cube" bodyClassName="p-3">
          {history.isLoading ? (
            <p className="p-3 text-xs text-ink-3">读取近期生成记录…</p>
          ) : people.length === 0 ? (
            <p className="p-3 text-xs text-ink-3">
              还没有可用角色——先去创作工作台生成角色并补齐动作，再来生成发布片。
            </p>
          ) : (
            <div className="flex flex-col gap-2">
              {people.map((record) => (
                <button
                  key={record.id}
                  onClick={() => {
                    setSelected({ id: record.asset_id!, name: record.name || record.goal });
                    setJobId(null);
                  }}
                  className={cx(
                    "flex items-center gap-3 rounded-xl border p-2 text-left transition-all",
                    selected?.id === record.asset_id
                      ? "border-primary/60 bg-primary-tint/40"
                      : "border-line-subtle hover:border-line",
                  )}
                >
                  <img
                    src={record.image?.url ?? undefined}
                    alt={String(record.name ?? record.asset_id ?? "")}
                    loading="lazy"
                    className="h-12 w-12 rounded-md border border-line-subtle bg-[#f1efe9] object-contain"
                  />
                  <span className="min-w-0 flex-1">
                    <span className="block truncate text-[12.5px] font-medium text-ink">
                      {record.name || record.asset_id}
                    </span>
                    <span className="block truncate text-[10.5px] text-ink-3">{record.goal}</span>
                  </span>
                </button>
              ))}
            </div>
          )}
          <p className="mt-3 flex items-center gap-1.5 text-[11px] text-ink-4">
            <Icon name="clock" className="h-3 w-3" />
            发布片在本机离线渲染（Playwright + ffmpeg），不消耗模型额度。
          </p>
        </Card>
      </div>
    </div>
  );
}

import { useQuery } from "@tanstack/react-query";
import { motion } from "framer-motion";
import { api } from "../api/client";
import {
  Badge,
  Card,
  EmptyState,
  KV,
  PageHeader,
  ScoreBar,
  ScoreRing,
  Skeleton,
  Stat,
} from "../components/ui";
import { Icon } from "../components/icons";

function CompareRow({
  name,
  baseline,
  method,
  format,
  tone,
  betterDown = false,
  noBaselineScale = false,
}: {
  name: string;
  baseline: number;
  method: number;
  format: (value: number) => string;
  tone: "precon" | "falign" | "gimport";
  betterDown?: boolean;
  noBaselineScale?: boolean;
}) {
  const improved = betterDown ? method < baseline : method > baseline;
  const scale = noBaselineScale
    ? Math.max(baseline, method) || 1
    : Math.max(baseline, method, 0.0001) * 1.05;
  const baseWidth = Math.min(100, (baseline / scale) * 100);
  const methodWidth = Math.min(100, (method / scale) * 100);
  const delta =
    baseline === 0
      ? 0
      : betterDown
        ? (1 - method / baseline) * 100
        : (method / baseline - 1) * 100;

  const FILLS = {
    precon: "bg-gradient-to-r from-[#1e9fbd] to-precon",
    falign: "bg-gradient-to-r from-[#7c5cff] to-falign",
    gimport: "bg-gradient-to-r from-[#1f9d75] to-gimport",
  };

  return (
    <div className="grid grid-cols-[110px_minmax(0,1fr)_minmax(0,1fr)_118px] items-center gap-3.5 border-b border-white/[.04] py-2.5 last:border-0">
      <span className="truncate text-[12.5px] text-ink-2">{name}</span>
      <div className="relative h-1.5 overflow-hidden rounded-full bg-surface-3">
        <motion.span
          className="absolute inset-y-0 left-0 rounded-full bg-line-strong"
          initial={{ width: 0 }}
          animate={{ width: `${baseWidth}%` }}
          transition={{ duration: 0.7, ease: [0.2, 0.8, 0.2, 1] }}
        />
      </div>
      <div className="relative h-1.5 overflow-hidden rounded-full bg-surface-3">
        <motion.span
          className={`absolute inset-y-0 left-0 rounded-full ${FILLS[tone]}`}
          initial={{ width: 0 }}
          animate={{ width: `${methodWidth}%` }}
          transition={{ duration: 0.7, ease: [0.2, 0.8, 0.2, 1], delay: 0.05 }}
        />
      </div>
      <div className="flex items-center justify-end gap-2">
        <span className="tabular font-mono text-xs text-ink">{format(method)}</span>
        <Badge tone={improved ? "success" : "warning"}>
          {betterDown ? "-" : "+"}
          {Math.abs(delta).toFixed(1)}%
        </Badge>
      </div>
    </div>
  );
}

function CompareHeader({ baselineLabel, methodLabel }: { baselineLabel: string; methodLabel: string }) {
  return (
    <div className="grid grid-cols-[110px_minmax(0,1fr)_minmax(0,1fr)_118px] gap-3.5 pb-2 text-[10.5px] font-semibold uppercase tracking-[0.08em] text-ink-4">
      <span>指标</span>
      <span>{baselineLabel}</span>
      <span>{methodLabel}</span>
      <span className="text-right">提升</span>
    </div>
  );
}

export default function BenchmarkCenter() {
  const report = useQuery({
    queryKey: ["benchmark"],
    queryFn: api.benchmark,
    staleTime: Infinity,
  });

  if (report.isLoading) {
    return (
      <div className="mx-auto flex w-full max-w-[1440px] flex-col gap-5 px-4 py-5 md:px-6">
        <PageHeader overline="Benchmark Center" title="基准中心" description="正在运行真实管线评测…" />
        <div className="grid grid-cols-12 gap-5">
          <Skeleton className="col-span-12 h-80 xl:col-span-4" />
          <Skeleton className="col-span-12 h-80 xl:col-span-8" />
        </div>
      </div>
    );
  }

  if (report.isError || !report.data) {
    return (
      <div className="mx-auto w-full max-w-[1440px] px-4 py-5 md:px-6">
        <Card>
          <EmptyState
            icon="alert"
            title="评测失败"
            description={String(report.error)}
            action={
              <Badge tone="danger" icon="refresh">
                请确认后端 /api/benchmark 可用
              </Badge>
            }
          />
        </Card>
      </div>
    );
  }

  const data = report.data;

  return (
    <div className="mx-auto flex w-full max-w-[1440px] flex-col gap-5 px-4 py-5 md:px-6">
      <PageHeader
        overline="Benchmark Center"
        title="基准中心"
        description={`数据集 ${data.dataset.size} 资产 · ${data.dataset.categories.length} 类别 · ${data.dataset.animated} 动画 · 实时运行 PReCon / FAlign / GImport / Agent 真实管线`}
        actions={
          <>
            <Badge tone="neutral" icon="clock">
              生成于 {new Date(data.generated_at).toLocaleString()}
            </Badge>
            <Badge tone="ember" icon="spark">
              CF Score {(data.cf_score.overall * 100).toFixed(1)}
            </Badge>
          </>
        }
      />

      <div className="grid grid-cols-12 gap-5">
        <Card
          className="col-span-12 xl:col-span-4"
          title="CF Score 综合评分"
          icon="spark"
          iconClassName="text-ember"
          right={<Badge tone="ember">加权总分</Badge>}
        >
          <div className="flex justify-center">
            <ScoreRing value={data.cf_score.overall} label="CF SCORE · 100 分制" size={168} />
          </div>
          <div className="mt-4 space-y-3.5">
            <ScoreBar label="pixel · 权重 0.30" value={data.cf_score.components.pixel} tone="precon" />
            <ScoreBar label="animation · 权重 0.30" value={data.cf_score.components.animation} tone="falign" />
            <ScoreBar label="engine · 权重 0.25" value={data.cf_score.components.engine} tone="gimport" />
            <ScoreBar label="agent · 权重 0.15" value={data.cf_score.components.agent} tone="primary" />
          </div>
        </Card>

        <div className="col-span-12 flex flex-col gap-5 xl:col-span-8">
          <Card
            title="PReCon · 像素重建"
            icon="grid"
            iconClassName="text-precon"
            right={
              <Badge tone="precon">
                一致性 +{(data.precon.improvement * 100).toFixed(1)}%
              </Badge>
            }
          >
            <CompareHeader baselineLabel="Baseline · Pixelate" methodLabel="PReCon" />
            <CompareRow
              name="像素一致性"
              baseline={data.precon.baseline_pixel_score}
              method={data.precon.method_pixel_score}
              tone="precon"
              format={(v) => `${Math.round(v * 100)}%`}
            />
            <CompareRow
              name="轮廓保持"
              baseline={data.precon.baseline_contour}
              method={data.precon.method_contour}
              tone="precon"
              format={(v) => `${Math.round(v * 100)}%`}
            />
            <CompareRow
              name="调色板颜色数"
              baseline={data.precon.baseline_colors}
              method={data.precon.method_colors}
              tone="precon"
              betterDown
              format={(v) => `${Math.round(v)}`}
            />
          </Card>

          <Card
            title="FAlign · 动画对齐"
            icon="film"
            iconClassName="text-falign"
            right={
              <Badge tone="falign">
                漂移 -{(data.falign.drift_reduction * 100).toFixed(0)}%
              </Badge>
            }
          >
            <CompareHeader baselineLabel="Baseline · 原始帧" methodLabel="FAlign" />
            <CompareRow
              name="根漂移 px/frame"
              baseline={data.falign.baseline_root_drift}
              method={data.falign.method_root_drift}
              tone="falign"
              betterDown
              format={(v) => v.toFixed(2)}
            />
            <CompareRow
              name="脚步稳定性"
              baseline={data.falign.baseline_foot_sliding}
              method={data.falign.method_foot_sliding}
              tone="falign"
              format={(v) => `${Math.round(v * 100)}%`}
            />
            <CompareRow
              name="时序平滑度"
              baseline={data.falign.baseline_smoothness}
              method={data.falign.method_smoothness}
              tone="falign"
              format={(v) => `${Math.round(v * 100)}%`}
            />
          </Card>
        </div>

        <Card
          className="col-span-12 md:col-span-6 xl:col-span-4"
          domain="gimport"
          title="GImport · 一键导入"
          icon="package"
          right={<Badge tone="gimport">100%</Badge>}
        >
          <Stat
            label="导入成功率"
            value={`${Math.round(data.gimport.import_success_rate * 100)}%`}
            tone="text-gimport"
          />
          <div className="mt-3">
            <KV label="流程耗时" value={`1 步 · ${data.gimport.average_pipeline_seconds.toFixed(2)}s`} />
            <KV
              label="传统流程"
              value={`${data.gimport.manual_reduction.traditional_steps} 步 · ${data.gimport.time_comparison.traditional_minutes} 分钟`}
            />
            <KV label="加速比" value={`${Math.round(data.gimport.time_comparison.speedup)}×`} />
            <KV label="覆盖引擎" value="Unity / Cocos / Godot" />
          </div>
          <div className="mt-3 flex gap-1.5">
            <Badge tone="neutral">unity</Badge>
            <Badge tone="neutral">cocos</Badge>
            <Badge tone="neutral">godot</Badge>
          </div>
        </Card>

        <Card
          className="col-span-12 md:col-span-6 xl:col-span-4"
          title="Agent · 自主规划"
          icon="layers"
          right={
            <Badge tone="primary">
              {data.agent.completed} / {data.agent.total}
            </Badge>
          }
        >
          <div className="space-y-3.5">
            <ScoreBar label="任务完成率" value={data.agent.task_completion_rate} tone="gimport" />
            <ScoreBar label="规划正确率" value={data.agent.planning_accuracy} tone="gimport" />
            <ScoreBar label="失败恢复率" value={data.agent.recovery_success_rate} tone="gimport" />
          </div>
          <div className="mt-3.5">
            <KV label="平均任务耗时" value={`${data.agent.average_task_seconds.toFixed(2)} s`} />
          </div>
          <p className="mt-2 text-[11.5px] leading-[18px] text-ink-3">
            {data.agent.completed}/{data.agent.total} 个目标由 Supervisor 自主规划并调度 Art /
            Animation / Engine / QA 智能体完成，无人工干预。
          </p>
        </Card>

        <Card className="col-span-12 xl:col-span-4" title="方法学" icon="book">
          <KV label="数据集" value={`${data.dataset.size} assets / ${data.dataset.categories.length} categories`} />
          <KV label="对比基线" value="naive pixelate / raw frames" />
          <KV label="质量阈值" value=".80 / .85 / .90" />
          <KV label="复现命令" value="python -m benchmark.run_benchmark" />
          <div className="mt-3 flex items-start gap-2 rounded-md border border-line-subtle bg-surface-2/60 p-2.5 text-[11.5px] leading-[18px] text-ink-3">
            <Icon name="check" className="mt-0.5 h-4 w-4 shrink-0 text-success" />
            灰条 = 基线，彩条 = 自研方法；所有数值可在 `benchmark/results/` 中复现核对。
          </div>
        </Card>
      </div>
    </div>
  );
}

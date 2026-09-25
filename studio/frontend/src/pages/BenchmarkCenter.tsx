import { useQuery } from "@tanstack/react-query";
import { motion } from "framer-motion";
import { api } from "../api/client";
import { Badge, Card, ScoreBar } from "../components/ui";

function CompareRow({
  name,
  baseline,
  method,
  format,
  betterDown = false,
}: {
  name: string;
  baseline: number;
  method: number;
  format: (value: number) => string;
  betterDown?: boolean;
}) {
  const improved = betterDown ? method < baseline : method > baseline;
  return (
    <div className="grid grid-cols-[130px_1fr_1fr_90px] items-center gap-3 py-1.5 text-xs">
      <span className="text-zinc-400">{name}</span>
      <div className="flex items-center gap-2">
        <div className="h-1.5 flex-1 rounded-full bg-zinc-800">
          <div className="h-full rounded-full bg-zinc-500" style={{ width: "100%" }} />
        </div>
        <span className="w-16 text-right font-mono text-zinc-400">
          {format(baseline)}
        </span>
      </div>
      <div className="flex items-center gap-2">
        <div className="h-1.5 flex-1 rounded-full bg-zinc-800">
          <motion.div
            className={`h-full rounded-full ${improved ? "bg-emerald-400" : "bg-amber-400"}`}
            initial={{ width: 0 }}
            animate={{ width: "100%" }}
          />
        </div>
        <span className="w-16 text-right font-mono text-zinc-200">
          {format(method)}
        </span>
      </div>
      <Badge tone={improved ? "green" : "amber"}>
        {betterDown
          ? `-${Math.round((1 - method / baseline) * 100)}%`
          : `+${Math.round((method / baseline - 1) * 100)}%`}
      </Badge>
    </div>
  );
}

export default function BenchmarkCenter() {
  const report = useQuery({
    queryKey: ["benchmark"],
    queryFn: api.benchmark,
    refetchOnWindowFocus: false,
  });

  if (report.isLoading) {
    return (
      <div className="px-8 py-16 text-center text-sm text-zinc-400">
        正在运行基准评测（真实引擎 + 数据集）…
      </div>
    );
  }
  if (report.isError || !report.data) {
    return (
      <div className="px-8 py-16 text-center text-sm text-red-400">
        评测失败：{String(report.error)}
      </div>
    );
  }

  const data = report.data;

  return (
    <div className="mx-auto max-w-6xl px-6 py-6">
      <header className="mb-5">
        <h1 className="pixel-title text-sm font-semibold text-zinc-200">
          Benchmark Center
        </h1>
        <p className="mt-1 text-xs text-zinc-500">
          数据集 {data.dataset.size} 资产 · {data.dataset.categories.length} 类别 ·
          实时运行 PReCon / FAlign / GImport / Agent 真实管线评测
        </p>
      </header>

      <div className="grid grid-cols-5 gap-4">
        <Card title="CF Score" className="text-center">
          <div className="flex h-28 items-center justify-center">
            <svg viewBox="0 0 100 100" className="h-28 w-28">
              <circle cx="50" cy="50" r="42" fill="none" stroke="#27272a" strokeWidth="9" />
              <motion.circle
                cx="50"
                cy="50"
                r="42"
                fill="none"
                stroke="#fbbf24"
                strokeWidth="9"
                strokeLinecap="round"
                strokeDasharray={2 * Math.PI * 42}
                initial={{ strokeDashoffset: 2 * Math.PI * 42 }}
                animate={{
                  strokeDashoffset: 2 * Math.PI * 42 * (1 - data.cf_score.overall),
                }}
                transform="rotate(-90 50 50)"
              />
              <text
                x="50"
                y="55"
                textAnchor="middle"
                className="fill-zinc-100 font-mono"
                fontSize="20"
              >
                {Math.round(data.cf_score.overall * 100)}
              </text>
            </svg>
          </div>
          <div className="mt-2 space-y-1.5">
            <ScoreBar label="pixel" value={data.cf_score.components.pixel} />
            <ScoreBar label="animation" value={data.cf_score.components.animation} />
            <ScoreBar label="engine" value={data.cf_score.components.engine} />
            <ScoreBar label="agent" value={data.cf_score.components.agent} />
          </div>
        </Card>

        <Card title="PReCon · 像素重建" className="col-span-2">
          <div className="mb-2 grid grid-cols-[130px_1fr_1fr_90px] text-[10px] uppercase tracking-wider text-zinc-500">
            <span>指标</span>
            <span>Baseline · Pixelate</span>
            <span>PReCon</span>
            <span>提升</span>
          </div>
          <CompareRow
            name="像素一致性"
            baseline={data.precon.baseline_pixel_score}
            method={data.precon.method_pixel_score}
            format={(v) => `${Math.round(v * 100)}%`}
          />
          <CompareRow
            name="轮廓保持"
            baseline={data.precon.baseline_contour}
            method={data.precon.method_contour}
            format={(v) => `${Math.round(v * 100)}%`}
          />
          <CompareRow
            name="调色板颜色数"
            baseline={data.precon.baseline_colors}
            method={data.precon.method_colors}
            betterDown
            format={(v) => `${Math.round(v)}`}
          />
        </Card>

        <Card title="FAlign · 动画对齐" className="col-span-2">
          <div className="mb-2 grid grid-cols-[130px_1fr_1fr_90px] text-[10px] uppercase tracking-wider text-zinc-500">
            <span>指标</span>
            <span>Baseline · 原始帧</span>
            <span>FAlign</span>
            <span>提升</span>
          </div>
          <CompareRow
            name="根漂移 px/frame"
            baseline={data.falign.baseline_root_drift}
            method={data.falign.method_root_drift}
            betterDown
            format={(v) => v.toFixed(2)}
          />
          <CompareRow
            name="脚步稳定性"
            baseline={data.falign.baseline_foot_sliding}
            method={data.falign.method_foot_sliding}
            format={(v) => `${Math.round(v * 100)}%`}
          />
          <CompareRow
            name="时序平滑度"
            baseline={data.falign.baseline_smoothness}
            method={data.falign.method_smoothness}
            format={(v) => `${Math.round(v * 100)}%`}
          />
        </Card>
      </div>

      <div className="mt-4 grid grid-cols-2 gap-4">
        <Card title="GImport · 一键引擎导入">
          <div className="grid grid-cols-3 gap-3 text-center">
            <div>
              <div className="text-2xl font-bold text-emerald-300">
                {Math.round(data.gimport.import_success_rate * 100)}%
              </div>
              <div className="mt-1 text-[11px] text-zinc-500">导入成功率</div>
            </div>
            <div>
              <div className="text-2xl font-bold text-amber-300">
                {data.gimport.time_comparison.speedup}x
              </div>
              <div className="mt-1 text-[11px] text-zinc-500">
                对比传统 {data.gimport.time_comparison.traditional_minutes} 分钟
              </div>
            </div>
            <div>
              <div className="text-2xl font-bold text-sky-300">
                {data.gimport.manual_reduction.gimport_steps}
              </div>
              <div className="mt-1 text-[11px] text-zinc-500">
                人工步骤（传统 {data.gimport.manual_reduction.traditional_steps} 步）
              </div>
            </div>
          </div>
        </Card>

        <Card title="Agent · 自主规划">
          <div className="grid grid-cols-2 gap-x-6 gap-y-3">
            <ScoreBar label="任务完成率" value={data.agent.task_completion_rate} />
            <ScoreBar label="规划正确率" value={data.agent.planning_accuracy} />
            <ScoreBar label="失败恢复率" value={data.agent.recovery_success_rate} />
            <div className="text-xs text-zinc-500">
              平均任务耗时{" "}
              <span className="font-mono text-zinc-200">
                {data.agent.average_task_seconds.toFixed(2)}s
              </span>
            </div>
          </div>
          <p className="mt-3 text-[11px] leading-relaxed text-zinc-500">
            {data.agent.completed}/{data.agent.total} 个目标由 Supervisor
            自主规划并调度 Art / Animation / Engine / QA 智能体完成，无人工干预。
          </p>
        </Card>
      </div>
    </div>
  );
}

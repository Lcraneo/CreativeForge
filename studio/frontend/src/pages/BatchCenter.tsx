import { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { api } from "../api/client";
import { Badge, Button, Card, EmptyState, PageHeader, Segmented, Stat, cx } from "../components/ui";
import { Icon } from "../components/icons";
import { toast } from "../stores/toastStore";
import type { BatchStatus } from "../types";

const COUNT_OPTIONS = [
  { id: "4", label: "4 个" },
  { id: "9", label: "9 个" },
  { id: "12", label: "12 个" },
];
const MODE_OPTIONS = [
  { id: "seed", label: "多变体（不同随机种子）" },
  { id: "pose", label: "多姿势（同角色不同动作）" },
];
const ENGINE_OPTIONS = [
  { id: "cocos", label: "Cocos" },
  { id: "unity", label: "Unity" },
  { id: "godot", label: "Godot" },
];

const EXAMPLE_GOALS = [
  "创建一个像素RPG火焰法师Boss，带攻击动画，导入Cocos",
  "创建一个 2D 动漫风森林游侠角色，待机动画",
  "生成一个像素风骷髅战士，带攻击动画，导入Unity",
];

export default function BatchCenter() {
  const navigate = useNavigate();
  const [goal, setGoal] = useState(EXAMPLE_GOALS[0]);
  const [count, setCount] = useState("4");
  const [mode, setMode] = useState("seed");
  const [engine, setEngine] = useState("cocos");
  const [batchId, setBatchId] = useState<string | null>(null);
  const [starting, setStarting] = useState(false);
  const [exporting, setExporting] = useState(false);
  const [selected, setSelected] = useState<string[]>([]);
  const [sort, setSort] = useState("index");
  const [filter, setFilter] = useState("all");
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const batch = useQuery({
    queryKey: ["batch", batchId],
    queryFn: () => api.batchStatus(batchId!),
    enabled: Boolean(batchId),
    refetchInterval: (query) => (query.state.data?.status === "running" ? 2500 : false),
  });

  const status: BatchStatus | undefined = batch.data;
  useEffect(() => {
    return () => {
      if (pollRef.current) clearInterval(pollRef.current);
    };
  }, []);

  const tasks = useMemo(() => {
    let list = [...(status?.tasks ?? [])];
    if (filter === "ok")
      list = list.filter((task) => task.status === "pass" || task.status === "success");
    if (filter === "failed") list = list.filter((task) => task.status === "failed");
    if (sort === "score") {
      list.sort(
        (x, y) =>
          (y.scores?.overall ?? y.scores?.pixel ?? 0) - (x.scores?.overall ?? x.scores?.pixel ?? 0),
      );
    } else {
      list.sort((x, y) => x.index - y.index);
    }
    return list;
  }, [status, filter, sort]);

  const doneCount = (status?.tasks ?? []).filter(
    (task) => task.status !== "running" && task.status !== "pending",
  ).length;
  const okTasks = (status?.tasks ?? []).filter(
    (task) => task.asset_id && (task.status === "pass" || task.status === "success"),
  );

  async function start() {
    if (starting) return;
    setStarting(true);
    setSelected([]);
    try {
      const result = await api.startBatch(goal.trim(), Number(count), mode);
      setBatchId(result.batch_id);
      toast({
        tone: "info",
        title: "批量生产线已启动",
        description: `${result.count} 个任务串行执行，预计 ${Math.ceil((result.count * 20) / 60)} 分钟内完成`,
      });
    } catch (cause) {
      toast({ tone: "danger", title: "启动失败", description: String(cause).slice(0, 160) });
    } finally {
      setStarting(false);
    }
  }

  async function exportSelected() {
    if (selected.length === 0 || exporting) return;
    setExporting(true);
    try {
      const result = await api.batchExport(selected, engine);
      toast({
        tone: "success",
        title: `批量导出完成（${result.count} 个资产）`,
        description: `${(result.size_bytes / 1024).toFixed(0)} KB · 开始下载`,
      });
      window.location.href = result.download_url;
    } catch (cause) {
      toast({ tone: "danger", title: "批量导出失败", description: String(cause).slice(0, 160) });
    } finally {
      setExporting(false);
    }
  }

  function toggleSelect(assetId: string) {
    setSelected((current) =>
      current.includes(assetId) ? current.filter((id) => id !== assetId) : [...current, assetId],
    );
  }

  const running = status?.status === "running";

  return (
    <div className="mx-auto flex w-full max-w-[1440px] flex-col gap-5 px-4 py-5 md:px-6">
      <PageHeader
        overline="Batch Production Line"
        title="批量生产线"
        description="一次下单，产线串行完成 N 个资产：多变体（不同种子）/ 多姿势（同角色不同动作），一键压缩导出"
        actions={
          <>
            <Badge tone={running ? "primary" : "neutral"} icon="spark">
              {running ? `生产中 ${doneCount}/${status?.count ?? 0}` : "产线空闲"}
            </Badge>
            {okTasks.length > 0 && !running && (
              <Badge tone="success" icon="check">
                本批合格 {okTasks.length}
              </Badge>
            )}
          </>
        }
      />

      <Card title="生产订单" icon="spark">
        <textarea
          value={goal}
          onChange={(event) => setGoal(event.target.value)}
          rows={2}
          className="w-full resize-none rounded-xl border border-line bg-[#f7f5f0] px-3.5 py-3 text-[13px] text-ink outline-none transition-colors placeholder:text-ink-4 focus:border-primary/60"
          placeholder="描述这一批要生产的资产，例如：创建一个像素RPG火焰法师Boss，带攻击动画，导入Cocos"
        />
        <div className="mt-3 flex flex-wrap items-center gap-x-6 gap-y-3">
          <div className="flex items-center gap-2">
            <span className="text-[11px] uppercase tracking-[0.08em] text-ink-4">数量</span>
            <Segmented options={COUNT_OPTIONS} value={count} onChange={setCount} />
          </div>
          <div className="flex items-center gap-2">
            <span className="text-[11px] uppercase tracking-[0.08em] text-ink-4">模式</span>
            <Segmented options={MODE_OPTIONS} value={mode} onChange={setMode} />
          </div>
          <Button
            variant="ember"
            icon="spark"
            loading={starting}
            onClick={start}
            className="ml-auto"
          >
            启动批量生成
          </Button>
        </div>
      </Card>

      {!batchId ? (
        <Card>
          <EmptyState
            icon="package"
            title="产线待命"
            description="选择数量与模式后启动。多变体模式每个任务注入不同随机种子；多姿势模式让同一角色摆出 idle / walk / run / attack / jump 全套动作。"
            action={
              <div className="flex flex-wrap justify-center gap-2">
                {EXAMPLE_GOALS.map((example) => (
                  <Button
                    key={example}
                    variant="secondary"
                    size="sm"
                    onClick={() => setGoal(example)}
                  >
                    {example.slice(0, 18)}…
                  </Button>
                ))}
              </div>
            }
          />
        </Card>
      ) : (
        <>
          <div className="grid grid-cols-2 gap-5 md:grid-cols-4">
            <Stat label="批次" value={status?.id ?? "—"} />
            <Stat label="任务进度" value={`${doneCount}/${status?.count ?? 0}`} />
            <Stat label="模式" value={status?.mode === "pose" ? "多姿势" : "多变体"} />
            <Stat
              label="批次状态"
              value={
                running ? "生产中" : status?.status === "done" ? "已完成" : (status?.status ?? "—")
              }
            />
          </div>

          <Card
            title="产线产出"
            icon="grid"
            right={
              <div className="flex flex-wrap items-center gap-2">
                <Segmented
                  options={[
                    { id: "all", label: "全部" },
                    { id: "ok", label: "合格" },
                    { id: "failed", label: "失败" },
                  ]}
                  value={filter}
                  onChange={setFilter}
                />
                <Segmented
                  options={[
                    { id: "index", label: "按序号" },
                    { id: "score", label: "按评分" },
                  ]}
                  value={sort}
                  onChange={setSort}
                />
                <Segmented options={ENGINE_OPTIONS} value={engine} onChange={setEngine} />
                <Button
                  variant="ember"
                  size="sm"
                  icon="package"
                  loading={exporting}
                  onClick={exportSelected}
                  disabled={selected.length === 0}
                >
                  导出选中（{selected.length}）
                </Button>
                <Button
                  variant="secondary"
                  size="sm"
                  icon="cube"
                  onClick={() => navigate("/asset")}
                >
                  查看当前资产
                </Button>
              </div>
            }
          >
            {tasks.length === 0 ? (
              <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-4">
                {Array.from({ length: status?.count ?? 0 }).map((_, index) => (
                  <div
                    key={index}
                    className="grid h-[190px] animate-pulse place-items-center rounded-xl border border-line-subtle bg-surface-2/60 text-[11px] text-ink-4"
                  >
                    工位 {index + 1} · 排队中
                  </div>
                ))}
              </div>
            ) : (
              <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-4">
                {tasks.map((task) => {
                  const isOk = task.status === "pass" || task.status === "success";
                  const isSelected = task.asset_id ? selected.includes(task.asset_id) : false;
                  return (
                    <div
                      key={task.task_id}
                      className={cx(
                        "flex flex-col overflow-hidden rounded-xl border transition-all",
                        isSelected
                          ? "border-primary/60 shadow-[0_0_0_1px_rgba(74,111,138,.35)]"
                          : "border-line-subtle",
                      )}
                    >
                      <div className="relative grid h-[150px] place-items-center bg-[#f1efe9]">
                        {task.image_url ? (
                          <img
                            src={task.image_url}
                            alt={task.name ?? task.task_id}
                            loading="lazy"
                            className="h-full w-full object-contain p-2"
                          />
                        ) : (
                          <span
                            className={cx(
                              "text-[11px]",
                              task.status === "failed" ? "text-danger" : "animate-pulse text-ink-4",
                            )}
                          >
                            {task.status === "failed"
                              ? "生成失败"
                              : task.status === "running"
                                ? "生产中…"
                                : "排队中"}
                          </span>
                        )}
                        <span className="absolute left-2 top-2 rounded-md bg-ink/70 px-1.5 py-0.5 font-mono text-[10px] text-white">
                          #{task.index}
                        </span>
                        {task.asset_id && isOk && (
                          <input
                            type="checkbox"
                            checked={isSelected}
                            onChange={() => toggleSelect(task.asset_id!)}
                            className="absolute right-2 top-2 h-4 w-4 accent-[var(--color-primary,#4a6f8a)]"
                          />
                        )}
                      </div>
                      <div className="flex items-center justify-between gap-2 border-t border-ink/[.08] px-2.5 py-2">
                        <span className="min-w-0 flex-1 truncate text-[11px] text-ink-3">
                          {task.overrides?.seed
                            ? `seed ${task.overrides.seed}`
                            : task.overrides?.action
                              ? `姿势 ${task.overrides.action}`
                              : task.task_id}
                        </span>
                        <Badge
                          tone={isOk ? "success" : task.status === "failed" ? "danger" : "primary"}
                        >
                          {isOk ? "OK" : task.status}
                        </Badge>
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </Card>
        </>
      )}

      <div className="flex items-center gap-2 text-[11px] text-ink-4">
        <Icon name="clock" className="h-3.5 w-3.5" />
        产线串行执行以保护生成配额；每个任务完成后自动进入历史记录与版本树，可在版本控制中心回溯。
      </div>
    </div>
  );
}

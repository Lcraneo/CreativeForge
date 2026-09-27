import { useCallback, useEffect, useState } from "react";
import { api } from "../api";
import type { DagNode, Step, TaskDetail } from "../types";
import CharacterImage from "./CharacterImage";

const NODE_LABELS: Record<string, string> = {
  find_character: "Find DNA",
  generate_asset: "Generate",
  structure_asset: "AssetStruct",
  create_dna: "DNA",
  motion_align: "MotionAlign",
  combat: "Combat",
  create_logic: "Logic",
  simulate: "Simulate",
  gimport: "Export",
  quality_check: "Quality",
};

const STATUS_TEXT: Record<string, { text: string; cls: string }> = {
  completed: { text: "已完成", cls: "text-go" },
  failed: { text: "失败", cls: "text-bad" },
  waiting_review: { text: "待审核", cls: "text-warn" },
  running: { text: "执行中", cls: "text-ink-2" },
};

/** Kahn 层级：同一层 = 可并行分支，对应规划器 DAG。 */
function layerize(nodes: DagNode[], edges: [string, string][]): DagNode[][] {
  const deps = new Map<string, string[]>(
    nodes.map((n) => [
      n.id,
      edges.filter((e) => e[1] === n.id).map((e) => e[0]),
    ]),
  );
  const depth = new Map<string, number>();
  let remaining = nodes.map((n) => n.id);
  let level = 0;
  while (remaining.length && level < 24) {
    const ready = remaining.filter((id) =>
      (deps.get(id) || []).every((d) => depth.has(d)),
    );
    if (!ready.length) break;
    ready.forEach((id) => depth.set(id, level));
    remaining = remaining.filter((id) => !depth.has(id));
    level += 1;
  }
  const layers: DagNode[][] = [];
  for (const [id, lv] of depth) {
    (layers[lv] ||= []).push(nodes.find((n) => n.id === id)!);
  }
  return layers.filter(Boolean);
}

function stepMark(step?: Step): string {
  if (!step) return "○";
  if (step.status === "failed") return "✗";
  if (step.status === "healing") return "⟳";
  return "✓";
}

function markColor(step?: Step): string {
  if (!step) return "text-line-2";
  if (step.status === "failed") return "text-bad";
  if (step.status === "healing") return "text-warn";
  return "text-go";
}

export default function AgentTimeline(props: {
  taskId?: string;
  onOpenAsset: (assetId: string) => void;
  onOpenStudio: () => void;
}) {
  const [taskId, setTaskId] = useState<string | undefined>(props.taskId);
  const [task, setTask] = useState<TaskDetail | null>(null);
  const [history, setHistory] = useState<TaskDetail[]>([]);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async (id?: string) => {
    setError(null);
    try {
      const items = await api.listTasks(10);
      setHistory(items);
      if (!id && items.length) id = items[0].id;
      if (id) setTask(await api.getTask(id));
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  }, []);

  useEffect(() => {
    setTaskId(props.taskId);
    load(props.taskId);
  }, [props.taskId, load]);

  if (!taskId && !task) {
    return (
      <div className="py-24 text-center text-sm text-mute">
        还没有任务 —— 从创作页生成一个角色吧。
        <button
          onClick={props.onOpenStudio}
          className="ml-2 text-ink underline decoration-line-2 underline-offset-4 hover:decoration-ink"
        >
          前往创作
        </button>
      </div>
    );
  }

  const plan = task?.plan;
  const dag = plan?.dag;
  const layers = dag ? layerize(dag.nodes, dag.edges) : [];
  const steps = task?.steps || [];
  const stepByNode = new Map(steps.map((s) => [s.node, s]));
  const current = task?.current_node;
  const waiting = task?.status === "waiting_review";
  const statusInfo = STATUS_TEXT[task?.status ?? ""] ?? {
    text: task?.status,
    cls: "text-ink-2",
  };

  const gen = (task?.result as Record<string, unknown> | null)?.generate_asset as
    | Record<string, unknown>
    | undefined;
  const imageModel = typeof gen?.image_model === "string" ? gen.image_model : undefined;
  const imageProviderLabel =
    typeof gen?.image_provider_label === "string" ? gen.image_provider_label : undefined;
  const imageSource = typeof gen?.image_source === "string" ? gen.image_source : undefined;
  const usedExternal = imageSource === "api";
  const fellBack = imageSource === "builtin-fallback";

  const approve = async () => {
    if (!task) return;
    try {
      await fetch(`/api/v1/tasks/${task.id}/approve`, { method: "POST" });
      load(task.id);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  };

  return (
    <div className="grid gap-14 lg:grid-cols-[1fr_280px]">
      <section>
        <div className="flex flex-wrap items-baseline gap-4">
          <h1 className="font-display text-4xl font-black text-ink">时间线</h1>
          <span className={`text-sm ${statusInfo.cls}`}>{statusInfo.text}</span>
          {plan?.engine && (
            <span className="border-b border-line-2 pb-0.5 text-xs text-mute">
              → {plan.engine}
            </span>
          )}
          {task?.asset_id && (
            <button
              onClick={() => props.onOpenAsset(task.asset_id!)}
              className="ml-auto rounded-lg bg-ink px-4 py-1.5 text-xs text-paper transition-opacity hover:opacity-85"
            >
              查看资产
            </button>
          )}
          {waiting && (
            <button
              onClick={approve}
              className="ml-auto rounded-lg bg-warn px-4 py-1.5 text-xs text-paper transition-opacity hover:opacity-85"
            >
              审核通过，继续执行
            </button>
          )}
        </div>
        <p className="mt-3 break-all text-sm leading-relaxed text-ink-2">
          {task?.goal}
        </p>

        {/* 生成结果预览：任务产出资产后展示人物图像 */}
          {task?.asset_id && (
            <div className="mt-8 flex flex-wrap items-center gap-6 rounded-xl border border-line bg-panel/50 p-4">
              <div className="grid h-40 w-40 shrink-0 place-items-center overflow-hidden rounded-lg border border-line bg-paper">
                <CharacterImage
                  assetId={task.asset_id}
                  view="front"
                  size={512}
                  alt={task.goal}
                  className="h-full w-full object-contain"
                />
              </div>
              <div className="min-w-[200px] flex-1">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="text-xs uppercase tracking-widest text-mute">
                    生成角色
                  </span>
                  {imageModel && (
                    <span
                      className={`rounded-full border px-2.5 py-0.5 font-mono text-[11px] ${
                        usedExternal
                          ? "border-go/40 text-go"
                          : fellBack
                            ? "border-warn/50 text-warn"
                            : "border-line-2 text-ink-2"
                      }`}
                      title="该任务使用的图像生成模型"
                    >
                      模型 · {imageProviderLabel ? `${imageProviderLabel} / ` : ""}
                      {imageModel}
                      {fellBack ? "（已回退内置）" : ""}
                    </span>
                  )}
                </div>
                <p className="mt-2 text-sm leading-relaxed text-ink">
                  {task.goal}
                </p>
                <button
                  onClick={() => props.onOpenAsset(task.asset_id!)}
                  className="mt-3 rounded-lg bg-ink px-4 py-1.5 text-xs text-paper transition-opacity hover:opacity-85"
                >
                  查看三视图与资产
                </button>
              </div>
            </div>
          )}

        {/* DAG 分层 */}
        <div className="mt-9 space-y-2.5">
          {layers.map((layer, li) => (
            <div key={li} className="flex flex-wrap items-center gap-2.5">
              {layer.map((node) => {
                const step = stepByNode.get(node.id);
                const isCurrent =
                  current === node.id && task?.status === "running";
                return (
                  <span
                    key={node.id}
                    title={`${node.agent} (${node.id})`}
                    className={`inline-flex items-center gap-1.5 rounded-full border px-3 py-1 text-xs transition-colors ${
                      step
                        ? "border-line-2 bg-panel text-ink"
                        : "border-line text-mute"
                    } ${isCurrent ? "animate-pulse" : ""}`}
                  >
                    <span className={markColor(step)}>{stepMark(step)}</span>
                    {NODE_LABELS[node.id] ?? node.id}
                    {step?.tier && (
                      <span className="text-[10px] uppercase tracking-wider text-mute">
                        {step.tier}
                      </span>
                    )}
                    {step?.ms != null && (
                      <span className="font-mono text-[10px] text-mute">
                        {step.ms}ms
                      </span>
                    )}
                  </span>
                );
              })}
            </div>
          ))}
          {!layers.length && (
            <div className="text-sm text-mute">（无 DAG 计划）</div>
          )}
        </div>

        {/* 执行轨迹 */}
        <div className="mt-12 text-xs uppercase tracking-widest text-mute">
          执行轨迹 · {steps.length} 步
        </div>
        <ol className="mt-3 border-t border-line">
          {steps.map((step, i) => (
            <li key={i} className="border-b border-line py-3.5">
              <div className="flex flex-wrap items-baseline gap-x-4 gap-y-1">
                <span className="font-mono text-xs text-mute">
                  {String(i + 1).padStart(2, "0")}
                </span>
                <span className="w-36 text-sm font-medium text-ink">
                  {step.agent}
                </span>
                <span
                  className={`text-xs ${
                    step.status === "done"
                      ? "text-go"
                      : step.status === "healed"
                        ? "text-go"
                        : step.status === "healing"
                          ? "text-warn"
                          : "text-bad"
                  }`}
                >
                  {step.status}
                </span>
                {step.tier && (
                  <span className="text-[10px] uppercase tracking-wider text-mute">
                    {step.tier}
                  </span>
                )}
                {typeof (step.summary as Record<string, unknown>)?.confidence ===
                  "number" && (
                  <span className="font-mono text-[10px] text-mute">
                    conf{" "}
                    {(step.summary as Record<string, number>).confidence.toFixed(2)}
                  </span>
                )}
                <span className="ml-auto font-mono text-xs text-mute">
                  {step.ms}ms
                </span>
              </div>
              {step.summary != null && (
                <details className="mt-1.5">
                  <summary className="cursor-pointer text-xs text-mute transition-colors hover:text-ink">
                    摘要
                  </summary>
                  <pre className="mt-2 max-h-44 overflow-auto whitespace-pre-wrap break-all rounded-lg bg-panel p-3 font-mono text-[11px] leading-relaxed text-ink-2">
                    {JSON.stringify(step.summary, null, 2)}
                  </pre>
                </details>
              )}
            </li>
          ))}
        </ol>
        {task?.error && (
          <p className="mt-5 border-l-2 border-bad pl-3 text-sm text-bad">
            {task.error}
          </p>
        )}
      </section>

      <aside>
        {plan?.decisions?.length ? (
          <>
            <div className="text-xs uppercase tracking-widest text-mute">
              规划决策
            </div>
            <ul className="mt-4 space-y-2 border-t border-line pt-4">
              {plan.decisions.map((d, i) => (
                <li key={i} className="flex gap-2 text-xs leading-relaxed text-ink-2">
                  <span className="text-mute">—</span>
                  {d}
                </li>
              ))}
            </ul>
          </>
        ) : null}
        <div className="mt-10 text-xs uppercase tracking-widest text-mute">
          最近任务
        </div>
        <ul className="mt-3 border-t border-line">
          {history.map((item) => (
            <li key={item.id} className="border-b border-line">
              <button
                onClick={() => {
                  setTaskId(item.id);
                  load(item.id);
                }}
                className={`w-full py-3 text-left text-xs transition-colors ${
                  item.id === task?.id
                    ? "font-medium text-ink"
                    : "text-ink-2 hover:text-ink"
                }`}
              >
                <span className="block truncate">{item.goal}</span>
                <span className="mt-0.5 block text-mute">{item.status}</span>
              </button>
            </li>
          ))}
        </ul>
      </aside>
    </div>
  );
}

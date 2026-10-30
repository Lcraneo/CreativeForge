/**
 * 试玩舞台 V2 · 底部动作坞
 *
 * 旧版右侧"长画廊"压缩为横向动作卡坞：主按钮（选择动作/Preview）与
 * 次级按钮（生成 AI 动画 / 重试 / 到工作台）是同级元素——禁止 button
 * 嵌套 button。自定义动作只在用户打开动作库后出现（渐进式加载）。
 */
import { useEffect, useState, type ReactNode } from "react";
import { Badge, Button, Spinner, cx } from "../../components/ui";
import { Icon } from "../../components/icons";
import type { ActionBatchTask, PlaytestCustomAction, PlaytestStrip } from "../../types";
import type { PlaytestMode } from "./playtestEngine";
import type { StripPhase } from "./usePlaytestAssets";

export const BASE_ACTION_LABEL: Record<string, string> = {
  idle: "待机",
  walk: "行走",
  run: "奔跑",
  attack: "攻击",
  jump: "跳跃",
};

const ACTION_HINT: Record<string, string> = {
  idle: "无操作时自动播放",
  walk: "← / → 或 A / D",
  run: "移动 + Shift",
  attack: "空格 / J",
  jump: "↑ / W",
};

/** 后端 classify_error 的失败分类 → 徽章短句 */
export const ERROR_KIND_LABEL: Record<string, string> = {
  moderation: "内容审核拦截",
  quota: "额度不足",
  auth: "Key 鉴权失败",
  network: "网络超时",
  fatal: "生成失败",
  interrupted: "任务已中断",
};

const STAGE_LABEL: Record<string, string> = {
  prompt: "正在准备动作提示词…",
  video: "AI 视频生成中（约 60~90 秒）",
  sampling: "正在抽帧并稳定画面…",
  composing: "正在合成动作条带…",
};

const TASK_STATUS_LABEL: Record<ActionBatchTask["status"], string> = {
  pending: "排队",
  generating: "生成中",
  done: "已生成",
  failed: "失败",
  skipped: "已有",
  interrupted: "已中断",
};

function actionLabel(action: string): string {
  return BASE_ACTION_LABEL[action] ?? action;
}

function formatElapsed(startedAt?: number): string {
  if (!startedAt) return "";
  const seconds = Math.max(0, Math.floor(Date.now() / 1000 - startedAt));
  return `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, "0")}`;
}

/** 只让状态条和当前进度卡订阅时钟，父页面与 Canvas 不再每 400ms 重渲染。 */
function useElapsedTick(active: boolean) {
  const [, setTick] = useState(0);
  useEffect(() => {
    if (!active) return;
    const timer = window.setInterval(() => setTick((value) => value + 1), 1000);
    return () => window.clearInterval(timer);
  }, [active]);
}

/** 阶段映射进度：i2v 是大头（90s 预估线性爬升至 80%），后段快速走完 */
function stageProgressPct(task?: ActionBatchTask): number {
  if (!task) return 0;
  if (task.status === "done") return 100;
  if (task.status !== "generating") return 4;
  const base: Record<string, number> = { prompt: 5, video: 10, sampling: 84, composing: 93 };
  let pct = base[task.stage ?? "video"] ?? 10;
  if (task.stage === "video" && task.started_at) {
    // 进度条动画启发式：卡片内的秒级 tick 会触发重渲染，每次取新时刻
    // 即可平滑爬升——这里的"不纯"是有意为之
    const elapsed = Date.now() / 1000 - task.started_at;
    pct = Math.min(80, base.video + Math.round((elapsed / 90) * 70));
  }
  return pct;
}

function EngineBadge({ engine }: { engine?: string }) {
  if (engine === "ai-video") return <Badge tone="primary">AI</Badge>;
  if (engine === "rigged") return <Badge tone="neutral">骨骼</Badge>;
  if (engine === "sprite") return <Badge tone="neutral">整身形变</Badge>;
  if (engine === "procedural") return <Badge tone="neutral">程序化</Badge>;
  return null;
}

function PhaseBadge({ phase }: { phase: StripPhase }) {
  if (phase === "loading") return <Badge tone="warning">加载中</Badge>;
  if (phase === "error") return <Badge tone="danger">加载失败</Badge>;
  return null;
}

function GenerationProgress({
  task,
  submitting = false,
}: {
  task?: ActionBatchTask;
  submitting?: boolean;
}) {
  const pending = task?.status === "pending";
  const active = task?.status === "generating";
  useElapsedTick(active);

  const label = submitting
    ? "正在提交生成任务…"
    : pending
      ? "已加入队列，等待生成…"
      : STAGE_LABEL[task?.stage ?? "prompt"];
  const pct = submitting ? 0 : stageProgressPct(task);
  const elapsed = active ? formatElapsed(task?.started_at) : "";

  return (
    <div className="mt-1.5">
      <div className="flex justify-between text-[10px] text-ink-4">
        <span>{label}</span>
        <span className="font-mono">{elapsed || (submitting ? "" : `${pct}%`)}</span>
      </div>
      <div
        className="mt-1 h-1.5 overflow-hidden rounded-full bg-ink/10"
        role="progressbar"
        aria-label={label}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={submitting ? undefined : pct}
      >
        <div
          className={cx(
            "h-full rounded-full bg-primary transition-[width] duration-(--motion-progress) ease-linear",
            submitting && "w-1/3 animate-pulse-run",
          )}
          style={submitting ? undefined : { width: `${Math.max(pending ? 4 : 0, pct)}%` }}
        />
      </div>
    </div>
  );
}

function TaskChip({ task }: { task: ActionBatchTask }) {
  const status = task.status;
  const icon: ReactNode =
    status === "done" ? (
      <Icon name="check" className="h-3 w-3" />
    ) : status === "generating" ? (
      <Spinner className="h-3 w-3" />
    ) : status === "pending" ? (
      <Icon name="clock" className="h-3 w-3" />
    ) : status === "failed" || status === "interrupted" ? (
      <Icon name="alert" className="h-3 w-3" />
    ) : null;
  return (
    <span
      className={cx(
        "inline-flex h-6 items-center gap-1 rounded-sm px-2 text-[10.5px] font-medium",
        status === "generating" && "bg-primary/15 text-primary",
        status === "done" && "bg-success/15 text-success",
        status === "pending" && "bg-ink/[.06] text-ink-3",
        (status === "failed" || status === "interrupted") && "bg-danger/15 text-danger",
      )}
      title={task.note || task.error || undefined}
    >
      {icon}
      {actionLabel(task.action)}
      <span className="font-normal opacity-70">{TASK_STATUS_LABEL[status]}</span>
    </span>
  );
}

function GenerationStatus({
  tasks,
  submittingAction,
  batchRunning,
  batchDoneCount,
  batchTotal,
  batchStartedAt,
  syncError,
  onRefreshBatch,
}: {
  tasks: ActionBatchTask[];
  submittingAction: string | null;
  batchRunning: boolean;
  batchDoneCount: number;
  batchTotal: number;
  batchStartedAt?: number;
  syncError: string | null;
  onRefreshBatch: () => void;
}) {
  const activeTask = tasks.find((task) => task.status === "generating");
  const pendingCount = tasks.filter((task) => task.status === "pending").length;
  const failedTasks = tasks.filter(
    (task) => task.status === "failed" || task.status === "interrupted",
  );
  const visible = Boolean(
    submittingAction || activeTask || pendingCount || failedTasks.length || syncError,
  );
  useElapsedTick(Boolean(activeTask || batchRunning || submittingAction));
  if (!visible) return null;

  const title = submittingAction
    ? submittingAction === "batch"
      ? "正在创建全套动作生成队列"
      : `正在提交「${actionLabel(submittingAction)}」`
    : activeTask
      ? `正在生成「${actionLabel(activeTask.action)}」`
      : pendingCount
        ? "动作生成队列"
        : failedTasks.length
          ? "本轮生成已结束，部分动作失败"
          : syncError
            ? "生成状态同步暂时中断"
            : "动作生成队列";
  const detail = submittingAction
    ? "已收到点击，正在连接生成服务，请勿重复操作"
    : activeTask
      ? STAGE_LABEL[activeTask.stage ?? "prompt"]
      : pendingCount
        ? `${pendingCount} 个动作正在排队`
        : failedTasks.length
          ? "失败动作可在对应卡片上重新生成"
          : syncError
            ? "任务可能仍在后台继续，恢复连接后会更新进度"
            : "失败动作可在对应卡片上重新生成";
  const elapsed = activeTask?.started_at ? formatElapsed(activeTask.started_at) : "";
  const showClock = Boolean(activeTask || batchRunning || submittingAction);
  const queue = tasks.filter((task) => task.status !== "skipped");

  return (
    <div className="mb-2.5 rounded-lg border border-primary/25 bg-primary-tint/55 px-3 py-2.5">
      <div role="status" aria-live="polite" className="flex flex-wrap items-center gap-x-2 gap-y-1">
        {showClock ? (
          <Spinner className="text-primary" />
        ) : (
          <Icon name="alert" className="h-4 w-4 text-warning" />
        )}
        <span className="text-[12px] font-semibold text-ink">{title}</span>
        <span className="text-[10.5px] text-ink-3">{detail}</span>
        <span className="ml-auto flex items-center gap-2 font-mono text-[10.5px] text-ink-3">
          {batchTotal > 0 && (
            <span>
              {batchDoneCount}/{batchTotal}
            </span>
          )}
          {elapsed && <span>{elapsed}</span>}
          {!activeTask && batchStartedAt && batchRunning && (
            <span>{formatElapsed(batchStartedAt)}</span>
          )}
        </span>
      </div>
      {queue.length > 0 && (
        <div className="mt-2 flex flex-wrap gap-1.5" aria-label="动作生成队列">
          {queue.map((task) => (
            <TaskChip key={task.action} task={task} />
          ))}
        </div>
      )}
      {syncError && (
        <div className="mt-2 flex flex-wrap items-center gap-2 text-[10.5px] text-danger">
          <Icon name="alert" className="h-3.5 w-3.5" />
          <span>{syncError}</span>
          <button
            type="button"
            onClick={onRefreshBatch}
            className="font-semibold underline underline-offset-2 hover:text-ink"
          >
            立即重试
          </button>
        </div>
      )}
    </div>
  );
}

export interface PlaytestActionDockProps {
  actions: string[];
  customActions: PlaytestCustomAction[];
  strips: Record<string, PlaytestStrip>;
  thumbnails: Record<string, string>;
  currentAction: string;
  mode: PlaytestMode;
  submittingAction: string | null;
  batchTasks: ActionBatchTask[];
  batchRunning: boolean;
  batchDoneCount: number;
  batchTotal: number;
  batchStartedAt?: number;
  batchSyncError: string | null;
  missingCount: number;
  aiReadyCount: number;
  phase: (key: string) => StripPhase;
  customLoading: boolean;
  libraryOpen: boolean;
  assetSelected: boolean;
  onSelect: (key: string) => void;
  onResumeLive: () => void;
  onGenerateAi: (name: string) => void;
  onGenerateAll: () => void;
  onRefreshBatch: () => void;
  onOpenLibrary: () => void;
  onRetry: (key: string) => void;
  onGoWorkbench: () => void;
}

export function PlaytestActionDock(props: PlaytestActionDockProps) {
  const {
    actions,
    customActions,
    strips,
    thumbnails,
    currentAction,
    mode,
    submittingAction,
    batchTasks,
    batchRunning,
    batchDoneCount,
    batchTotal,
    batchStartedAt,
    batchSyncError,
    missingCount,
    aiReadyCount,
    phase,
    customLoading,
    libraryOpen,
    assetSelected,
    onSelect,
    onResumeLive,
    onGenerateAi,
    onGenerateAll,
    onRefreshBatch,
    onOpenLibrary,
    onRetry,
    onGoWorkbench,
  } = props;

  const batchTaskFor = (name: string) => batchTasks.find((task) => task.action === name);
  const generationLocked = Boolean(submittingAction) || batchRunning;

  return (
    <section
      aria-label="动作坞"
      aria-busy={generationLocked || batchRunning}
      className="rounded-xl border border-line-subtle bg-paper/60 p-3"
    >
      <div className="mb-2.5 flex flex-wrap items-center gap-2">
        <span className="text-[10.5px] uppercase tracking-[0.14em] text-ember">动作坞</span>
        {mode === "preview" ? (
          <Badge tone="primary">Preview · 正在预览「{BASE_ACTION_LABEL[currentAction] ?? currentAction}」</Badge>
        ) : (
          <Badge tone="neutral">Live · 实时控制</Badge>
        )}
        {assetSelected && (
          <span title="AI 动画按角色独立保存；切换角色后需要为该角色补齐">
            <Badge tone={missingCount === 0 ? "success" : "warning"}>
              本角色 AI {aiReadyCount}/5
            </Badge>
          </span>
        )}
        {mode === "preview" && (
          <Button variant="secondary" size="sm" onClick={onResumeLive}>
            恢复实时控制
          </Button>
        )}
        <span className="ml-auto flex flex-wrap items-center justify-end gap-2">
          <Button
            variant="secondary"
            size="sm"
            icon="grid"
            aria-expanded={libraryOpen}
            onClick={onOpenLibrary}
          >
            自定义动作库{customActions.length > 0 ? `（${customActions.length}）` : ""}
          </Button>
          {assetSelected && missingCount > 0 && (
            <Button
              variant="primary"
              size="sm"
              icon="spark"
              loading={batchRunning || submittingAction === "batch"}
              disabled={generationLocked}
              onClick={onGenerateAll}
            >
              {submittingAction === "batch"
                ? "正在创建生成队列…"
                : batchRunning
                  ? `生成中 ${batchDoneCount}/${batchTotal}`
                  : `补齐当前角色动作（缺 ${missingCount} 个）`}
            </Button>
          )}
        </span>
      </div>

      <GenerationStatus
        tasks={batchTasks}
        submittingAction={submittingAction}
        batchRunning={batchRunning}
        batchDoneCount={batchDoneCount}
        batchTotal={batchTotal}
        batchStartedAt={batchStartedAt}
        syncError={batchSyncError}
        onRefreshBatch={onRefreshBatch}
      />

      {!assetSelected ? (
        <p className="py-4 text-center text-[11.5px] text-ink-4">
          选择人物后，这里会列出该角色的全部动作卡，点卡即切预览。
        </p>
      ) : (
        <div className="flex gap-2.5 overflow-x-auto pb-1">
          {actions.map((name) => {
            const key = name;
            const strip = strips[name];
            const isAi = strip?.engine === "ai-video";
            const itemPhase = phase(key);
            const task = batchTaskFor(name);
            const submitting = submittingAction === name;
            const generating =
              submitting || task?.status === "pending" || task?.status === "generating";
            const problemTask = task?.status === "failed" || task?.status === "interrupted";
            const batchDone = task?.status === "done";
            const canGenerate = !isAi && !batchDone && !generationLocked;
            return (
              <div
                key={key}
                className={cx(
                  "flex w-[176px] shrink-0 flex-col rounded-xl border p-2 transition-[border-color,box-shadow] duration-(--motion-fast) ease-standard",
                  currentAction === key ? "border-primary/60 shadow-xs" : "border-line-subtle",
                )}
              >
                <button
                  onClick={() => onSelect(key)}
                  aria-pressed={currentAction === key}
                  className="text-left"
                >
                  <span className="flex flex-wrap items-center gap-1.5">
                    <span className="text-[12.5px] font-medium text-ink">
                      {BASE_ACTION_LABEL[name] ?? name}
                    </span>
                    <EngineBadge engine={strip?.engine} />
                    <PhaseBadge phase={itemPhase} />
                    {task?.status === "pending" && <Badge tone="neutral">排队</Badge>}
                    {task?.status === "generating" && <Badge tone="primary">生成中</Badge>}
                    {batchDone && <Badge tone="success">已生成</Badge>}
                  </span>
                  <span className="block truncate text-[10.5px] text-ink-3">
                    {ACTION_HINT[name] ?? ""}
                  </span>
                  {thumbnails[name] && (
                    <img
                      src={thumbnails[name]}
                      alt={`${name} 预览`}
                      loading="lazy"
                      className="mt-1.5 h-[44px] w-[128px] rounded-md border border-line-subtle bg-white object-cover object-left"
                    />
                  )}
                </button>
                {/* 次级按钮与选择按钮同级（可访问性：禁止嵌套交互） */}
                {itemPhase === "error" ? (
                  <button
                    onClick={() => onRetry(key)}
                    className="mt-1 inline-flex items-center gap-1 text-[10.5px] font-medium text-danger underline-offset-2 hover:underline"
                  >
                    <Icon name="clock" className="h-3 w-3" />
                    条带加载失败 · 点击重试
                  </button>
                ) : (
                  canGenerate && (
                    <button
                      onClick={() => onGenerateAi(name)}
                      className="mt-1 inline-flex items-center gap-1 text-[10.5px] font-medium text-primary underline-offset-2 hover:underline"
                    >
                      <Icon name="spark" className="h-3 w-3" />
                      生成 AI 动画
                    </button>
                  )
                )}
                {problemTask && (
                  <span className="mt-1 text-[10px] text-danger">
                    {ERROR_KIND_LABEL[task?.error_kind ?? ""] ||
                      task?.error ||
                      (task?.status === "interrupted" ? "任务已中断" : "生成失败")}
                  </span>
                )}
                {generating && <GenerationProgress task={task} submitting={submitting} />}
              </div>
            );
          })}

          {customLoading && (
            <div className="flex w-[176px] shrink-0 items-center justify-center rounded-xl border border-dashed border-line text-[11px] text-ink-4">
              正在加载自定义动作…
            </div>
          )}
          {libraryOpen &&
            customActions.map((item) => {
              const key = `custom:${item.name}`;
              const itemPhase = phase(key);
              return (
                <div
                  key={key}
                  className={cx(
                    "flex w-[176px] shrink-0 flex-col rounded-xl border p-2 transition-[border-color,box-shadow] duration-(--motion-fast) ease-standard",
                    currentAction === key ? "border-ember/60 shadow-xs" : "border-line-subtle",
                  )}
                >
                  <button onClick={() => onSelect(key)} aria-pressed={currentAction === key} className="text-left">
                    <span className="flex items-center gap-1.5">
                      <span className="truncate text-[12.5px] font-medium text-ink">{item.name}</span>
                      <EngineBadge engine={item.engine} />
                      <PhaseBadge phase={itemPhase} />
                    </span>
                    <span className="block truncate text-[10.5px] text-ink-3">
                      {BASE_ACTION_LABEL[item.base_action ?? ""] ?? item.base_action ?? "自定义"}
                      {item.view === "side" ? " · 侧视" : ""}
                      {item.description ? ` · ${item.description}` : ""}
                    </span>
                    {item.strip?.url && (
                      <img
                        src={item.strip.url}
                        alt={`${item.name} 预览`}
                        loading="lazy"
                        className="mt-1.5 h-[44px] w-[128px] rounded-md border border-line-subtle bg-white object-cover object-left"
                      />
                    )}
                  </button>
                  {/* 次级按钮与选择按钮同级 */}
                  {itemPhase === "error" ? (
                    <button
                      onClick={() => onRetry(key)}
                      className="mt-1 inline-flex items-center gap-1 text-[10.5px] font-medium text-danger underline-offset-2 hover:underline"
                    >
                      <Icon name="clock" className="h-3 w-3" />
                      条带加载失败 · 点击重试
                    </button>
                  ) : (
                    item.engine !== "ai-video" && (
                      <button
                        onClick={onGoWorkbench}
                        className="mt-1 inline-flex items-center gap-1 text-[10.5px] font-medium text-ember underline-offset-2 hover:underline"
                      >
                        <Icon name="spark" className="h-3 w-3" />
                        到动画工作台生成 AI 版
                      </button>
                    )
                  )}
                </div>
              );
            })}
          {!libraryOpen && (
            <button
              onClick={onOpenLibrary}
              className="flex w-[176px] shrink-0 flex-col items-center justify-center gap-1 rounded-xl border border-dashed border-line text-ink-3 hover:border-line-strong"
            >
              <Icon name="grid" className="h-4 w-4" />
              <span className="text-[11px]">打开自定义动作库</span>
            </button>
          )}
        </div>
      )}
    </section>
  );
}

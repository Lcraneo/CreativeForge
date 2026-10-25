/**
 * 试玩舞台 V2 · 底部动作坞
 *
 * 旧版右侧"长画廊"压缩为横向动作卡坞：主按钮（选择动作/Preview）与
 * 次级按钮（生成 AI 动画 / 重试 / 到工作台）是同级元素——禁止 button
 * 嵌套 button。自定义动作只在用户打开动作库后出现（渐进式加载）。
 */
import { Badge, Button, cx } from "../../components/ui";
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
};

const STAGE_LABEL: Record<string, string> = {
  prompt: "提交生成任务…",
  video: "AI 视频生成中…（约 60~90 秒）",
  sampling: "抽帧与稳定处理…",
  composing: "合成动作条带…",
};

/** 阶段映射进度：i2v 是大头（90s 预估线性爬升至 80%），后段快速走完 */
function stageProgressPct(task?: ActionBatchTask): number {
  if (!task) return 0;
  if (task.status === "done") return 100;
  if (task.status !== "generating") return 4;
  const base: Record<string, number> = { prompt: 5, video: 10, sampling: 84, composing: 93 };
  let pct = base[task.stage ?? "video"] ?? 10;
  if (task.stage === "video" && task.started_at) {
    // 进度条动画启发式：页面本就 2.5s 轮询重渲染，每次重渲染取新时刻
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

function GenerationProgress({ task, tick }: { task?: ActionBatchTask; tick: number }) {
  void tick;
  const pct = stageProgressPct(task);
  return (
    <div className="mt-1.5" data-tick={tick}>
      <div className="flex justify-between text-[10px] text-ink-4">
        <span>{STAGE_LABEL[task?.stage ?? "prompt"]}</span>
        <span className="font-mono">{pct}%</span>
      </div>
      <div className="mt-1 h-1.5 overflow-hidden rounded-full bg-ink/10">
        <div
          className="h-full rounded-full bg-primary transition-[width] duration-(--motion-progress) ease-linear"
          style={{ width: `${pct}%` }}
        />
      </div>
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
  generatingAction: string | null;
  batchTasks: ActionBatchTask[];
  batchRunning: boolean;
  batchDoneCount: number;
  batchTotal: number;
  missingCount: number;
  tick: number;
  phase: (key: string) => StripPhase;
  customLoading: boolean;
  libraryOpen: boolean;
  assetSelected: boolean;
  onSelect: (key: string) => void;
  onResumeLive: () => void;
  onGenerateAi: (name: string) => void;
  onGenerateAll: () => void;
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
    generatingAction,
    batchTasks,
    batchRunning,
    batchDoneCount,
    batchTotal,
    missingCount,
    tick,
    phase,
    customLoading,
    libraryOpen,
    assetSelected,
    onSelect,
    onResumeLive,
    onGenerateAi,
    onGenerateAll,
    onOpenLibrary,
    onRetry,
    onGoWorkbench,
  } = props;

  const batchTaskFor = (name: string) => batchTasks.find((task) => task.action === name);

  return (
    <section
      aria-label="动作坞"
      className="rounded-xl border border-line-subtle bg-paper/60 p-3"
    >
      <div className="mb-2.5 flex flex-wrap items-center gap-2">
        <span className="text-[10.5px] uppercase tracking-[0.14em] text-ember">动作坞</span>
        {mode === "preview" ? (
          <Badge tone="primary">Preview · 正在预览「{BASE_ACTION_LABEL[currentAction] ?? currentAction}」</Badge>
        ) : (
          <Badge tone="neutral">Live · 实时控制</Badge>
        )}
        {mode === "preview" && (
          <Button variant="secondary" size="sm" onClick={onResumeLive}>
            恢复实时控制
          </Button>
        )}
        <span className="ml-auto flex items-center gap-2">
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
              loading={batchRunning}
              onClick={onGenerateAll}
            >
              {batchRunning ? `补齐全套动作中…（${batchDoneCount}/${batchTotal}）` : `一键生成全部动作（缺 ${missingCount} 个）`}
            </Button>
          )}
        </span>
      </div>

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
            const generating = generatingAction === name || batchTaskFor(name)?.status === "generating";
            const failedTask = batchTaskFor(name)?.status === "failed";
            const canGenerate = !isAi && !generatingAction && !batchRunning;
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
                  <span className="flex items-center gap-1.5">
                    <span className="text-[12.5px] font-medium text-ink">
                      {BASE_ACTION_LABEL[name] ?? name}
                    </span>
                    <EngineBadge engine={strip?.engine} />
                    <PhaseBadge phase={itemPhase} />
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
                {failedTask && (
                  <span className="mt-1 text-[10px] text-danger">
                    {ERROR_KIND_LABEL[batchTaskFor(name)?.error_kind ?? ""] ||
                      batchTaskFor(name)?.error ||
                      "生成失败"}
                  </span>
                )}
                {generating && <GenerationProgress task={batchTaskFor(name)} tick={tick} />}
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

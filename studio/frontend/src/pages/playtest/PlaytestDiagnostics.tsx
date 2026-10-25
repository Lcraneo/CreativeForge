/**
 * 试玩舞台 V2 · 诊断抽屉（舞台右侧，可收起）
 *
 * 只陈列真实指标：动画来源、角色拟合度（骨骼绑定链路的 head_ratio /
 * fit_confidence）、条带加载状态、批次任务进度。实时 FPS/帧时间由
 * Debug 模式直接叠加在舞台左上角（canvas 绘制，不经 React）——本抽屉
 * 不伪造根漂移、脚滑等后端未提供的数据。
 */
import { Badge, cx } from "../../components/ui";
import { Icon } from "../../components/icons";
import type { ActionBatchTask, PlaytestCharacter, PlaytestCustomAction, PlaytestStrip } from "../../types";
import { BASE_ACTION_LABEL, ERROR_KIND_LABEL } from "./PlaytestActionDock";
import type { StripPhase } from "./usePlaytestAssets";

export interface PlaytestDiagnosticsProps {
  source?: string;
  character?: PlaytestCharacter | null;
  actions: string[];
  strips: Record<string, PlaytestStrip>;
  customActions: PlaytestCustomAction[];
  phase: (key: string) => StripPhase;
  progress: { ready: number; total: number; pct: number };
  batchTasks: ActionBatchTask[];
  onClose: () => void;
}

const SOURCE_LABEL: Record<string, string> = {
  rigged: "骨骼绑定（原画实时变形）",
  sprite: "整身形变（原画实时变形）",
  "ai-video": "AI 视频驱动",
  procedural: "程序化演示小人",
};

function PhaseDot({ phase }: { phase: StripPhase }) {
  return (
    <span
      className={cx(
        "inline-block h-1.5 w-1.5 rounded-full",
        phase === "ready" && "bg-success",
        phase === "loading" && "bg-warning",
        phase === "error" && "bg-danger",
        phase === "pending" && "bg-line-strong",
      )}
    />
  );
}

export function PlaytestDiagnostics(props: PlaytestDiagnosticsProps) {
  const { source, character, actions, strips, customActions, phase, progress, batchTasks, onClose } = props;
  const chibi = character?.proportion === "chibi";
  const activeTasks = batchTasks.filter(
    (task) => task.status === "generating" || task.status === "failed",
  );

  return (
    <aside
      role="region"
      aria-label="诊断信息"
      className="absolute inset-y-3 right-3 z-10 flex w-[264px] flex-col gap-3 overflow-y-auto rounded-xl border border-stage-line/40 bg-black/55 p-3 text-stage-text backdrop-blur-md"
    >
      <div className="flex items-center gap-2">
        <span className="text-[10.5px] uppercase tracking-[0.14em] text-stage-line">诊断 Diagnostics</span>
        <button
          onClick={onClose}
          aria-label="收起诊断抽屉"
          className="ml-auto rounded-md p-1 text-stage-text/70 hover:bg-white/10"
        >
          <Icon name="x" className="h-3.5 w-3.5" />
        </button>
      </div>

      {/* 动画来源与角色拟合度（真实返回字段，不虚构指标） */}
      <section>
        <p className="text-[11px] text-stage-text/80">动画来源</p>
        <p className="mt-0.5 text-[12px] font-medium">
          {SOURCE_LABEL[source ?? ""] ?? source ?? "—"}
        </p>
        {character && (character.head_ratio !== null || character.confidence !== null) && (
          <p className="mt-1 font-mono text-[10.5px] text-stage-text/60">
            head_ratio {character.head_ratio ?? "—"} · confidence{" "}
            {character.confidence !== null ? character.confidence.toFixed(2) : "—"}
          </p>
        )}
        {chibi && source === "rigged" && (
          <p className="mt-1.5 rounded-md border border-stage-line/40 bg-white/5 p-1.5 text-[10.5px] leading-relaxed text-stage-text/80">
            检测到 Q 版头身比，骨骼分区拟合度较低，动作可能出现轻微错位；完整动画建议在动画工作台使用
            AI 视频驱动。
          </p>
        )}
      </section>

      {/* 条带加载状态 */}
      <section>
        <p className="flex items-center justify-between text-[11px] text-stage-text/80">
          <span>条带加载</span>
          <span className="font-mono">
            {progress.ready}/{progress.total} · {progress.pct}%
          </span>
        </p>
        <ul className="mt-1.5 flex flex-col gap-1">
          {actions.map((name) => {
            const itemPhase = phase(name);
            return (
              <li key={name} className="flex items-center gap-2 text-[11px]">
                <PhaseDot phase={itemPhase} />
                <span className="flex-1">{BASE_ACTION_LABEL[name] ?? name}</span>
                {strips[name]?.engine === "ai-video" && <Badge tone="primary">AI</Badge>}
                <span className="font-mono text-[10px] text-stage-text/55">{itemPhase}</span>
              </li>
            );
          })}
          {customActions.map((item) => {
            const key = `custom:${item.name}`;
            const itemPhase = phase(key);
            return (
              <li key={key} className="flex items-center gap-2 text-[11px]">
                <PhaseDot phase={itemPhase} />
                <span className="flex-1 truncate">{item.name}</span>
                <span className="font-mono text-[10px] text-stage-text/55">{itemPhase}</span>
              </li>
            );
          })}
        </ul>
      </section>

      {/* 批次任务（AI 补生成） */}
      {activeTasks.length > 0 && (
        <section>
          <p className="text-[11px] text-stage-text/80">AI 动画批次</p>
          <ul className="mt-1.5 flex flex-col gap-1">
            {activeTasks.map((task) => (
              <li
                key={task.action}
                className={cx(
                  "rounded-md border px-2 py-1 text-[10.5px]",
                  task.status === "failed"
                    ? "border-danger/50 bg-danger/10 text-red-200"
                    : "border-stage-line/40 bg-white/5 text-stage-text/85",
                )}
              >
                {task.action} ·{" "}
                {task.status === "generating"
                  ? "AI 生成中…"
                  : ERROR_KIND_LABEL[task.error_kind ?? ""] || task.error || "生成失败"}
              </li>
            ))}
          </ul>
        </section>
      )}

      <p className="mt-auto text-[10px] leading-relaxed text-stage-text/45">
        实时 FPS / 帧时间 / 帧游标 / 包围盒由 Clean·Debug 切换叠加在舞台画布上。
      </p>
    </aside>
  );
}

import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { api, type PlanResult, type PlanTask } from "../api/client";
import { streamTask } from "../websocket/taskStream";
import { Badge, Button, Card, StatusDot, Textarea, cx } from "../components/ui";
import { Icon, type IconName } from "../components/icons";
import { toast } from "../stores/toastStore";
import type { TaskEvent } from "../types";

const EXAMPLES = [
  "创建一个像素RPG火焰法师Boss，带攻击动画，导入Cocos",
  "创建一个 2D 动漫风机械少女，待机动画",
  "生成像素弓箭手并导入 Unity",
  "把这个角色改成冰霜法师，再做攻击动画并导入 Unity",
];

const CAP_LABEL: Record<string, string> = {
  generation: "生成角色",
  edit_asset: "编辑角色",
  PReCon: "像素重建",
  FAlign: "动画对齐",
  GImport: "引擎导入",
  quality_check: "质量校验",
};
const CAP_HINT: Record<string, string> = {
  generation: "角色生成：自然语言 → 角色原画 + 资产结构（未配置模型时走离线管线）",
  edit_asset: "角色编辑：在现有资产上改，不重掷身份",
  PReCon: "像素重建：256 色 → 语义 16 色调色板 + 轮廓修复",
  FAlign: "动画对齐：锚点检测 / 根运动纠偏，帧间时间轴一致",
  GImport: "引擎导入：图集 / 动画剪辑 / Prefab → 一键引擎 zip",
  quality_check: "质量校验：像素/动画/引擎三路阈值门 + 修复轮",
};
const CAP_ICON: Record<string, IconName> = {
  generation: "spark",
  edit_asset: "refresh",
  PReCon: "grid",
  FAlign: "film",
  GImport: "package",
  quality_check: "check",
};

function capStatus(statuses: Record<string, string>, task: PlanTask): string {
  return statuses[task.id] ?? "pending";
}

export default function CreativeStudio() {
  const [goal, setGoal] = useState(EXAMPLES[0]);
  const [plan, setPlan] = useState<PlanResult | null>(null);
  const [statuses, setStatuses] = useState<Record<string, string>>({});
  const [running, setRunning] = useState(false);
  const [canvasSrc, setCanvasSrc] = useState<string | null>(null);
  const [canvasCaption, setCanvasCaption] = useState(
    "等待创作 —— 输入目标，Planner 会实时给出能力计划",
  );
  const [error, setError] = useState<string | null>(null);
  const stopRef = useRef<null | (() => void)>(null);
  const navigate = useNavigate();

  const history = useQuery({
    queryKey: ["cs-history"],
    queryFn: () => api.listHistory({ limit: 12 }),
    staleTime: 10000,
  });

  const modelSettings = useQuery({
    queryKey: ["model-settings"],
    queryFn: api.getModelSettings,
    staleTime: 15000,
  });
  const [enhancing, setEnhancing] = useState(false);
  const [turbo, setTurbo] = useState(false);
  const [onboard, setOnboard] = useState(() => localStorage.getItem("cf-onboarded") !== "1");
  const chatReady = Boolean(
    modelSettings.data?.enabled && modelSettings.data?.chat_model && modelSettings.data?.use_chat,
  );

  useEffect(() => {
    const timer = setTimeout(() => {
      const text = goal.trim();
      if (!text) {
        setPlan(null);
        return;
      }
      api
        .plan(text)
        .then(setPlan)
        .catch(() => {});
    }, 350);
    return () => clearTimeout(timer);
  }, [goal]);

  useEffect(() => () => stopRef.current?.(), []);

  function applyEvent(event: TaskEvent) {
    switch (event.type) {
      case "AGENT_START":
        setStatuses((prev) => ({ ...prev, [event.task ?? ""]: "running" }));
        break;
      case "AGENT_DONE":
        setStatuses((prev) => ({
          ...prev,
          [event.task ?? ""]: event.status === "recovered" ? "recovered" : "success",
        }));
        break;
      case "TASK_FAILED":
        setStatuses((prev) => ({ ...prev, [event.task ?? ""]: "failed" }));
        break;
      case "ASSET_UPDATE":
        if (event.image) {
          setCanvasSrc(event.image);
          setCanvasCaption("生成结果");
        } else if (event.id) {
          setCanvasSrc(`/api/assets/${event.id}/image.png?view=front`);
          setCanvasCaption(`资产 ${event.id}`);
        }
        break;
      case "TASK_COMPLETE":
        if (event.asset_id) {
          setCanvasSrc(`/api/assets/${event.asset_id}/image.png?view=front`);
          setCanvasCaption(`资产 ${event.asset_id}`);
        }
        break;
      default:
        break;
    }
  }

  async function run() {
    const text = goal.trim();
    if (!text || running) return;
    setRunning(true);
    setError(null);
    setStatuses({});
    setCanvasSrc(null);
    setCanvasCaption("创作中 —— Planner 正在调度能力…");
    try {
      const { task_id } = await api.createTask(text, undefined, turbo);
      stopRef.current = streamTask(task_id, {
        onEvent: applyEvent,
        onEnd: (status) => {
          setRunning(false);
          if (status === "failed") setError("任务失败，请到「智能体」查看详情");
        },
        onError: (message) => setError(message),
      });
      toast({
        tone: "success",
        title: `任务 ${task_id} 已进入规划`,
        description: "按目标动态调度能力，画布将实时更新",
      });
    } catch (cause) {
      setRunning(false);
      setError(String(cause));
    }
  }

  function openAsset(assetId: string) {
    setCanvasSrc(`/api/assets/${assetId}/image.png?view=front`);
    setCanvasCaption(`资产 ${assetId}`);
  }

  async function enhance() {
    const text = goal.trim();
    if (!text || enhancing) return;
    setEnhancing(true);
    setError(null);
    try {
      const result = await api.enhancePrompt(text);
      if (result?.prompt) {
        setGoal(result.prompt);
        toast({ tone: "success", title: "提示词已增强", description: `模型 ${result.model}` });
      }
    } catch (cause) {
      setError(String(cause));
    } finally {
      setEnhancing(false);
    }
  }

  const tasks = plan?.tasks ?? [];

  return (
    <div className="mx-auto flex h-[calc(100vh-3.5rem)] w-full max-w-[1600px] flex-col gap-4 px-4 py-4 md:px-6">
      <div className="grid min-h-0 flex-1 grid-cols-12 gap-4">
        <Card className="col-span-12 min-h-0 md:col-span-3" title="Project · Assets" icon="cube">
          <div className="cf-scroll h-full overflow-y-auto pr-1">
            {history.isLoading ? (
              <div className="text-xs text-ink-3">加载中…</div>
            ) : (history.data?.records.length ?? 0) === 0 ? (
              <div className="text-xs text-ink-3">还没有资产 —— 在下方描述你的第一个创意。</div>
            ) : (
              <ul className="space-y-1.5">
                {history.data!.records.map((record) => (
                  <li key={record.id}>
                    <button
                      onClick={() => record.asset_id && openAsset(record.asset_id)}
                      className="w-full truncate rounded-md border border-line-subtle bg-surface-1 px-2.5 py-2 text-left text-[12.5px] text-ink-2 transition-colors hover:border-primary/45 hover:text-ink"
                    >
                      <span className="block truncate">{record.name ?? record.goal}</span>
                      <span className="mt-0.5 block font-mono text-[10.5px] text-ink-4">
                        {record.asset_id ?? "—"} · {record.status}
                      </span>
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </Card>

        <Card
          className="col-span-12 min-h-0 md:col-span-6"
          title="Live Canvas"
          icon="grid"
          right={
            <Badge tone={running ? "primary" : canvasSrc ? "success" : "neutral"}>
              <StatusDot tone={running ? "running" : canvasSrc ? "success" : "idle"} />
              {running ? "创作中" : canvasSrc ? "已产出" : "空闲"}
            </Badge>
          }
        >
          <div className="flex h-full flex-col items-center justify-center gap-3">
            <div className="grid h-[360px] w-full place-items-center overflow-hidden rounded-xl border border-line-subtle bg-[radial-gradient(320px_180px_at_50%_35%,rgba(124,92,196,.10),transparent_70%),#f1efe9]">
              {canvasSrc ? (
                <img
                  src={canvasSrc}
                  alt="current asset"
                  className="max-h-[340px] max-w-full object-contain"
                />
              ) : (
                <div className="px-8 text-center text-[13px] text-ink-3">{canvasCaption}</div>
              )}
            </div>
            {canvasSrc && (
              <div className="flex flex-wrap items-center gap-3 text-[12px] text-ink-3">
                <span>{canvasCaption}</span>
                <Button
                  variant="secondary"
                  size="sm"
                  icon="cube"
                  onClick={() => navigate("/asset")}
                >
                  查看资产
                </Button>
                <Button
                  variant="secondary"
                  size="sm"
                  icon="film"
                  onClick={() => navigate("/animation")}
                >
                  制作动画
                </Button>
                <Button
                  variant="secondary"
                  size="sm"
                  icon="package"
                  onClick={() => navigate("/export")}
                >
                  导出
                </Button>
              </div>
            )}
          </div>
        </Card>

        <Card
          className="col-span-12 min-h-0 md:col-span-3"
          title="Execution Plan"
          icon="layers"
          right={
            plan ? (
              <Badge tone="neutral">{plan.mode === "modify" ? "修改" : "新建"}</Badge>
            ) : undefined
          }
        >
          <div className="cf-scroll h-full overflow-y-auto pr-1">
            {!plan ? (
              <div className="text-xs text-ink-3">
                输入目标后，Planner 会在这里给出动态能力计划。
              </div>
            ) : (
              <>
                <ol className="space-y-2">
                  {tasks.map((task) => {
                    const status = capStatus(statuses, task);
                    const tone =
                      status === "success" || status === "recovered"
                        ? "text-success"
                        : status === "running"
                          ? "text-primary"
                          : status === "failed"
                            ? "text-danger"
                            : "text-ink-4";
                    return (
                      <li
                        key={task.id}
                        title={
                          CAP_HINT[task.capability] ?? CAP_LABEL[task.capability] ?? task.capability
                        }
                        className="flex items-center gap-2.5 rounded-md border border-line-subtle bg-surface-1 px-2.5 py-2"
                      >
                        <Icon
                          name={CAP_ICON[task.capability] ?? "zap"}
                          className={cx("h-4 w-4 shrink-0", tone)}
                        />
                        <div className="min-w-0 flex-1">
                          <div className="truncate text-[12.5px] font-medium text-ink">
                            {CAP_LABEL[task.capability] ?? task.capability}
                            {task.engine ? ` · ${task.engine}` : ""}
                          </div>
                          <div className="truncate font-mono text-[10.5px] text-ink-4">
                            {task.agent}
                          </div>
                        </div>
                        <span className={cx("text-[11px]", tone)}>
                          {status === "running"
                            ? "⟳"
                            : status === "success" || status === "recovered"
                              ? "✓"
                              : status === "failed"
                                ? "✗"
                                : "○"}
                        </span>
                      </li>
                    );
                  })}
                </ol>
                <div className="mt-3 flex flex-wrap gap-1.5 text-[10.5px] text-ink-4">
                  <span>引擎 {plan.intent.engine}</span>
                  <span>· 风格 {plan.intent.style}</span>
                  <span>· {plan.intent.animation ? "含动画" : "静态"}</span>
                </div>
              </>
            )}
          </div>
        </Card>
      </div>

      {onboard && (
        <div className="shrink-0 rounded-2xl border border-primary/30 bg-primary-tint/30 p-3">
          <div className="flex flex-wrap items-center gap-x-4 gap-y-2 text-[12.5px] text-ink-2">
            <span className="font-semibold text-ink">3 步上手：</span>
            <span>① 直接点「执行创作」—— 内置离线管线，无需任何 API Key</span>
            <span>② 想要 AI 原画 → 「模型设置」填 Key</span>
            <span>③ 导出引擎包 / 生成动画 / 试玩</span>
            <Button
              variant="ghost"
              size="sm"
              className="ml-auto"
              onClick={() => {
                localStorage.setItem("cf-onboarded", "1");
                setOnboard(false);
              }}
            >
              知道了
            </Button>
          </div>
        </div>
      )}

      <section className="shrink-0 rounded-2xl border border-line-subtle bg-[linear-gradient(180deg,#f2efe9,#ece9e2)] p-3">
        <div className="flex items-end gap-3">
          <Textarea
            value={goal}
            onChange={(event) => setGoal(event.target.value)}
            onKeyDown={(event) => {
              if ((event.metaKey || event.ctrlKey) && event.key === "Enter") run();
            }}
            rows={2}
            className="flex-1"
            placeholder="告诉 CreativeForge 你想得到什么……（⌘↵ 执行）"
          />
          <label
            title="极速档：跳过三视图等增值步骤，最快出结果"
            className="flex cursor-pointer select-none items-center gap-1.5 text-[11.5px] text-ink-3"
          >
            <input
              type="checkbox"
              checked={turbo}
              onChange={(event) => setTurbo(event.target.checked)}
              className="h-3.5 w-3.5 accent-[var(--color-primary,#4a6f8a)]"
            />
            极速档
          </label>
          <Button
            variant="secondary"
            size="lg"
            icon="spark"
            loading={enhancing}
            onClick={enhance}
            disabled={!chatReady || enhancing}
            title={
              chatReady
                ? "用对话模型增强提示词（增强后再执行创作）"
                : "需先在「模型设置」配置对话模型"
            }
          >
            增强提示词
          </Button>
          <Button variant="ember" size="lg" icon="zap" loading={running} onClick={run}>
            {running ? "创作中…" : "执行创作"}
          </Button>
        </div>
        <div className="mt-2 flex flex-wrap items-center gap-2">
          {EXAMPLES.map((example) => (
            <button
              key={example}
              onClick={() => setGoal(example)}
              className="rounded-full border border-line-subtle bg-canvas/50 px-2.5 py-1 text-[11px] text-ink-3 transition-colors hover:border-primary/45 hover:text-primary"
            >
              {example.length > 24 ? `${example.slice(0, 24)}…` : example}
            </button>
          ))}
          {error && <span className="ml-auto text-[11.5px] text-danger">{error}</span>}
        </div>
      </section>
    </div>
  );
}

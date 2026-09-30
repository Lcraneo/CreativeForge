import { useEffect, useMemo, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { api } from "../api/client";
import { useAgentStore } from "../stores/agentStore";
import { useWorkflowStore } from "../stores/workflowStore";
import { useAssetStore } from "../stores/assetStore";
import { toast } from "../stores/toastStore";
import {
  Badge,
  Button,
  Card,
  Chip,
  EmptyState,
  Input,
  Select,
  Skeleton,
  StatusDot,
  Textarea,
  cx,
} from "../components/ui";
import { Icon } from "../components/icons";
import type { TaskSummary, GenerationOverrides } from "../types";
import type { Tone } from "../components/ui";

const EXAMPLES = [
  "生成一个像素RPG火焰法师Boss，带攻击动画，并导入Unity",
  "创建一个像素风RPG火焰法师角色，包含待机、攻击动画，并导入Cocos项目",
  "生成一把像素火焰剑道具，导入Unity",
  "做一个像素洞穴Boss，带攻击动画，导入Unity",
];

const ENGINES = [
  { id: "unity", label: "Unity" },
  { id: "cocos", label: "Cocos" },
  { id: "godot", label: "Godot" },
];

const OVERRIDE_OPTIONS: Record<string, Array<[string, string]>> = {
  style: [
    ["auto", "风格：自动"],
    ["pixel", "像素"],
    ["2d", "2D 动漫"],
  ],
  gender: [
    ["auto", "性别：自动"],
    ["female", "女性"],
    ["male", "男性"],
    ["neutral", "中性"],
  ],
  class: [
    ["auto", "职业：自动"],
    ["mage", "法师"],
    ["warrior", "战士"],
    ["archer", "弓箭手"],
    ["rogue", "刺客"],
    ["priest", "牧师"],
    ["summoner", "召唤师"],
    ["druid", "德鲁伊"],
    ["monk", "武僧"],
    ["engineer", "机械师"],
    ["bard", "吟游诗人"],
    ["hero", "冒险者"],
  ],
  element: [
    ["auto", "元素：自动"],
    ["fire", "火焰"],
    ["ice", "冰霜"],
    ["lightning", "雷霆"],
    ["poison", "剧毒"],
    ["nature", "自然"],
    ["water", "潮汐"],
    ["wind", "疾风"],
    ["holy", "神圣"],
    ["dark", "暗影"],
    ["none", "无元素"],
  ],
  hair_color: [
    ["auto", "发色：自动"],
    ["silver", "银白"],
    ["white", "白色"],
    ["gold", "金色"],
    ["black", "黑色"],
    ["red", "赤红"],
    ["blue", "海蓝"],
    ["violet", "紫罗兰"],
    ["green", "墨绿"],
    ["brown", "栗棕"],
    ["pink", "樱粉"],
    ["gray", "灰白"],
  ],
  hair_style: [
    ["auto", "发型：自动"],
    ["long", "长发"],
    ["short", "短发"],
    ["ponytail", "马尾"],
    ["twin_tail", "双马尾"],
    ["braid", "编发"],
    ["curly", "卷发"],
    ["straight", "直发"],
    ["bangs", "齐刘海"],
    ["bald", "光头"],
  ],
  expression: [
    ["auto", "神态：自动"],
    ["cold", "冷笑高傲"],
    ["warm", "温和微笑"],
    ["angry", "愤怒"],
    ["stern", "严肃"],
    ["mysterious", "神秘"],
    ["sad", "忧郁"],
    ["cute", "可爱"],
  ],
  build: [
    ["auto", "体型：自动"],
    ["slim", "修长偏瘦"],
    ["muscular", "健壮魁梧"],
    ["petite", "娇小"],
    ["tall", "高大修长"],
    ["plump", "圆润"],
  ],
  action: [
    ["auto", "动作：自动"],
    ["attack", "攻击"],
    ["walk", "行走"],
    ["idle", "待机"],
  ],
  weapon: [
    ["auto", "武器：自动"],
    ["staff", "法杖"],
    ["sword", "大剑"],
    ["bow", "长弓"],
    ["dagger", "匕首"],
    ["axe", "战斧"],
    ["hammer", "战锤"],
    ["spear", "长枪"],
    ["scythe", "镰刀"],
    ["shield", "盾"],
    ["tome", "魔典"],
    ["orb", "法球"],
    ["none", "无"],
  ],
};

const DEFAULT_STEPS = [
  "Generation 生成",
  "PReCon 像素重建",
  "FAlign 切帧对齐",
  "GImport 引擎导入",
  "QA 质量验证",
];

function statusTone(status: string): Tone {
  return status === "pass" || status === "success"
    ? "success"
    : status === "failed"
      ? "danger"
      : status === "running"
        ? "primary"
        : "neutral";
}

function Sparkline({ points, stroke }: { points: string; stroke: string }) {
  return (
    <svg viewBox="0 0 120 28" className="mt-1.5 h-7 w-full" aria-hidden="true">
      <path d={points} fill="none" stroke={stroke} strokeWidth="1.6" />
    </svg>
  );
}

export default function Workspace() {
  const [goal, setGoal] = useState(EXAMPLES[0]);
  const [engine, setEngine] = useState("unity");
  const [busy, setBusy] = useState(false);
  const [enhancing, setEnhancing] = useState(false);
  const [advanced, setAdvanced] = useState(false);
  const [height, setHeight] = useState<string>("");
  const [overrides, setOverrides] = useState<Record<string, string>>(() =>
    Object.fromEntries(Object.keys(OVERRIDE_OPTIONS).map((key) => [key, "auto"])),
  );
  const navigate = useNavigate();
  const location = useLocation();

  const startAgent = useAgentStore((state) => state.start);
  const resetWorkflow = useWorkflowStore((state) => state.reset);
  const plan = useWorkflowStore((state) => state.plan);
  const agentStatuses = useAgentStore((state) => state.agentStatuses);
  const liveTaskId = useAgentStore((state) => state.taskId);
  const progress = useAgentStore((state) => state.progress);
  const setAsset = useAssetStore((state) => state.set);

  const tasks = useQuery({ queryKey: ["tasks"], queryFn: api.listTasks });
  const benchmark = useQuery({
    queryKey: ["benchmark"],
    queryFn: api.benchmark,
    staleTime: Infinity,
  });
  const modelSettings = useQuery({
    queryKey: ["model-settings"],
    queryFn: api.getModelSettings,
    staleTime: 15000,
  });

  useEffect(() => {
    const incoming = (location.state as { goal?: string } | null)?.goal;
    if (!incoming) return;
    setGoal(incoming);
    navigate(".", { replace: true, state: null });
    toast({
      tone: "info",
      title: "已载入历史提示词",
      description: incoming.length > 30 ? `${incoming.slice(0, 30)}…` : incoming,
    });
  }, [location.state, navigate]);

  const pipeline = useMemo(() => {
    if (plan && plan.tasks.length > 0) {
      return plan.tasks.map((task) => ({
        label: `${task.capability} ${task.agent}`,
        status:
          agentStatuses[task.id] === "success" || agentStatuses[task.id] === "recovered"
            ? ("done" as const)
            : agentStatuses[task.id] === "running"
              ? ("running" as const)
              : agentStatuses[task.id] === "failed"
                ? ("failed" as const)
                : ("pending" as const),
      }));
    }
    const index = Math.min(4, Math.floor(progress / 20));
    return DEFAULT_STEPS.map((label, position) => ({
      label,
      status: !liveTaskId
        ? ("pending" as const)
        : position < index
          ? ("done" as const)
          : position === index
            ? ("running" as const)
            : ("pending" as const),
    }));
  }, [plan, agentStatuses, progress, liveTaskId]);

  async function generate() {
    if (!goal.trim() || busy) return;
    setBusy(true);
    try {
      resetWorkflow();
      setAsset(null);
      const engineLabel = ENGINES.find((item) => item.id === engine)?.label ?? "Unity";
      const text = /unity|cocos|godot/i.test(goal)
        ? goal.trim()
        : `${goal.trim()}，并导入${engineLabel}`;

      const cleaned: GenerationOverrides = {};
      for (const [key, value] of Object.entries(overrides)) {
        if (value && value !== "auto") {
          (cleaned as Record<string, string>)[key] = value;
        }
      }
      if (height.trim()) cleaned.height_cm = Number(height);

      const { task_id } = await api.createTask(text, cleaned);
      startAgent(task_id, text);
      toast({
        tone: "success",
        title: `任务 ${task_id} 已进入规划`,
        description: modelSettings.data?.enabled
          ? `将调用自定义模型 ${modelSettings.data.model} 生成原画`
          : "Supervisor 正在生成任务图并调度智能体",
      });
      navigate("/agents");
    } catch (cause) {
      toast({ tone: "danger", title: "任务创建失败", description: String(cause) });
    } finally {
      setBusy(false);
    }
  }

  async function enhancePromptText() {
    const text = goal.trim();
    if (!text || enhancing) return;
    setEnhancing(true);
    try {
      const result = await api.enhancePrompt(text);
      if (result?.prompt) {
        setGoal(result.prompt);
        toast({ tone: "success", title: "提示词已增强", description: `模型 ${result.model}` });
      }
    } catch (cause) {
      toast({ tone: "danger", title: "增强失败", description: String(cause) });
    } finally {
      setEnhancing(false);
    }
  }

  async function openTask(task: TaskSummary) {
    if (task.status === "running") {
      navigate("/agents");
      return;
    }
    if (task.asset_id && task.status === "pass") {
      try {
        const asset = await api.getAsset(task.asset_id);
        setAsset(asset);
        navigate("/asset");
      } catch {
        navigate("/asset");
      }
    }
  }

  const kpis = benchmark.data;

  return (
    <div className="mx-auto flex w-full max-w-[1440px] flex-col gap-5 px-4 py-5 md:px-6">
      <div className="grid grid-cols-12 gap-5">
        <section className="cf-sheen relative col-span-12 overflow-hidden rounded-2xl border border-line-subtle bg-[radial-gradient(620px_240px_at_88%_-30%,rgba(169,129,47,.12),transparent_70%),radial-gradient(420px_220px_at_6%_130%,rgba(62,125,90,.09),transparent_70%),linear-gradient(180deg,#f2efe9,#ece9e2)] p-6 xl:col-span-8">
          <div className="text-[11px] font-semibold uppercase tracking-[0.08em] text-ink-2">
            CreativeForge Studio · 目标输入
          </div>
          <h1 className="mt-2 font-display text-[28px] font-black leading-10">
            今天要锻造什么资产？
          </h1>
          <p className="mt-1 text-[13px] text-ink-3">
            描述需求，Supervisor 自动规划 Generation → PReCon → FAlign → GImport → QA。
          </p>

          <Textarea
            value={goal}
            onChange={(event) => setGoal(event.target.value)}
            onKeyDown={(event) => {
              if ((event.metaKey || event.ctrlKey) && event.key === "Enter") generate();
            }}
            rows={4}
            className="mt-4"
            placeholder="创建一个像素风火焰法师Boss：需要 Idle 动画、Attack 动画、Unity 导出"
          />

          <div className="mt-3 flex flex-wrap gap-2">
            {EXAMPLES.map((example) => (
              <button
                key={example}
                onClick={() => setGoal(example)}
                className="rounded-full border border-line-subtle bg-canvas/50 px-2.5 py-1 text-xs text-ink-3 transition-colors duration-(--motion-fast) ease-standard hover:border-primary/45 hover:text-primary"
              >
                {example.length > 26 ? `${example.slice(0, 26)}…` : example}
              </button>
            ))}
          </div>

          <div className="mt-4 flex flex-wrap items-center justify-between gap-3">
            <div className="flex flex-wrap items-center gap-2">
              <button type="button" onClick={() => navigate("/settings")} title="模型设置">
                <Badge
                  tone={modelSettings.data?.enabled ? "primary" : "neutral"}
                  icon="spark"
                  className="cursor-pointer"
                >
                  {modelSettings.data?.enabled
                    ? `自定义模型 · ${modelSettings.data.model}`
                    : "系统默认模型"}
                </Badge>
              </button>
              {ENGINES.map((item) => (
                <Chip
                  key={item.id}
                  icon="cube"
                  active={engine === item.id}
                  onClick={() => setEngine(item.id)}
                >
                  {item.label}
                </Chip>
              ))}
              <Button
                variant="ghost"
                size="sm"
                icon="layers"
                onClick={() => setAdvanced((value) => !value)}
              >
                {advanced ? "收起参数" : "高级参数"}
              </Button>
              <span className="text-[11.5px] text-ink-3">已输入 {goal.length} 字 · ⌘↵ 提交</span>
            </div>
            <Button
              variant="secondary"
              size="lg"
              icon="spark"
              loading={enhancing}
              onClick={enhancePromptText}
              disabled={
                !modelSettings.data?.enabled || !modelSettings.data?.chat_model || enhancing
              }
              title="用对话模型增强提示词（增强后再生成）"
            >
              增强提示词
            </Button>
            <Button variant="ember" size="lg" icon="spark" loading={busy} onClick={generate}>
              {busy ? "创建中…" : "生成资产"}
            </Button>
          </div>

          {advanced && (
            <div className="mt-4 rounded-xl border border-line-subtle bg-canvas/40 p-4">
              <div className="mb-3 flex items-center gap-2 text-[11px] uppercase tracking-[0.08em] text-ink-4">
                <Icon name="layers" className="h-3.5 w-3.5" />
                生成参数覆盖 · 默认模型与自定义 API 均生效
              </div>
              <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
                {Object.entries(OVERRIDE_OPTIONS).map(([key, options]) => (
                  <Select
                    key={key}
                    value={overrides[key]}
                    options={options.map(([value, label]) => ({ value, label }))}
                    onChange={(event) =>
                      setOverrides((prev) => ({ ...prev, [key]: event.target.value }))
                    }
                  />
                ))}
                <Input
                  type="number"
                  min={120}
                  max={230}
                  placeholder="身高 cm（自动）"
                  value={height}
                  onChange={(event) => setHeight(event.target.value)}
                />
              </div>
              <p className="mt-3 text-[11px] text-ink-4">
                留为「自动」的参数由提示词推断；参数会写入 CharacterSpec，用于调色板、原画与三视图。
              </p>
            </div>
          )}
        </section>

        <Card
          className="col-span-12 xl:col-span-4"
          title="生产管线"
          icon="activity"
          right={
            <Badge tone={liveTaskId ? "primary" : "neutral"}>
              <StatusDot tone={liveTaskId ? "running" : "idle"} />
              {liveTaskId ? `${progress}%` : "空闲"}
            </Badge>
          }
        >
          <ol className="relative space-y-4 pl-1">
            <span className="absolute bottom-2 left-[10px] top-2 w-0.5 rounded-sm bg-line-subtle" />
            {pipeline.map((step, index) => {
              const tone =
                step.status === "done"
                  ? "border-success bg-success/10 text-success"
                  : step.status === "running"
                    ? "border-primary bg-primary-tint text-primary shadow-[0_0_0_4px_rgba(26,24,20,.08)]"
                    : step.status === "failed"
                      ? "border-danger bg-danger/10 text-danger"
                      : "border-line bg-surface-1 text-ink-4";
              return (
                <li key={`${step.label}-${index}`} className="relative flex items-center gap-3.5">
                  <span
                    className={cx(
                      "relative z-10 grid h-[22px] w-[22px] shrink-0 place-items-center rounded-full border-2 bg-canvas",
                      tone,
                    )}
                  >
                    <Icon
                      name={
                        step.status === "done"
                          ? "check"
                          : step.status === "running"
                            ? "refresh"
                            : step.status === "failed"
                              ? "x"
                              : "clock"
                      }
                      className="h-3 w-3"
                    />
                  </span>
                  <div className="min-w-0">
                    <div
                      className={cx(
                        "truncate text-[12.5px]",
                        step.status === "pending" ? "text-ink-3" : "font-medium text-ink-2",
                      )}
                    >
                      {step.label}
                    </div>
                  </div>
                </li>
              );
            })}
          </ol>
        </Card>
      </div>

      <div className="grid grid-cols-2 gap-5 xl:grid-cols-4">
        <Card bodyClassName="p-4">
          {kpis ? (
            <div className="flex flex-col">
              <span className="text-xs text-ink-3">CF Score 综合评分</span>
              <span className="tabular text-[32px] font-semibold leading-10 tracking-[-0.02em] text-ember">
                {(kpis.cf_score.overall * 100).toFixed(1)}
                <small className="ml-0.5 text-base font-semibold text-ink-3">%</small>
              </span>
              <Sparkline
                points="M0 22 15 20 30 21 45 15 60 16 75 10 90 11 105 5 120 6"
                stroke="#a9812f"
              />
              <span className="text-[11px] text-ink-3">
                权重 pixel .30 / anim .30 / engine .25 / agent .15
              </span>
            </div>
          ) : (
            <Skeleton className="h-24" />
          )}
        </Card>
        <Card bodyClassName="p-4">
          {kpis ? (
            <div className="flex flex-col">
              <span className="text-xs text-ink-3">PReCon 像素一致性</span>
              <span className="tabular text-[32px] font-semibold leading-10 tracking-[-0.02em] text-precon">
                {Math.round(kpis.precon.method_pixel_score * 100)}
                <small className="ml-0.5 text-base font-semibold text-ink-3">%</small>
              </span>
              <Sparkline
                points="M0 23 15 21 30 18 45 19 60 14 75 12 90 9 105 8 120 6"
                stroke="#0e8ea8"
              />
              <span className="text-[11px] text-ink-3">
                baseline {Math.round(kpis.precon.baseline_pixel_score * 100)}% · +
                {(kpis.precon.improvement * 100).toFixed(1)}%
              </span>
            </div>
          ) : (
            <Skeleton className="h-24" />
          )}
        </Card>
        <Card bodyClassName="p-4">
          {kpis ? (
            <div className="flex flex-col">
              <span className="text-xs text-ink-3">FAlign 根漂移</span>
              <span className="tabular text-[32px] font-semibold leading-10 tracking-[-0.02em] text-falign">
                {kpis.falign.method_root_drift.toFixed(2)}
                <small className="ml-0.5 text-base font-semibold text-ink-3">px/f</small>
              </span>
              <Sparkline
                points="M0 4 15 6 30 12 45 16 60 20 75 24 90 25 105 26 120 26"
                stroke="#7c5cc4"
              />
              <span className="text-[11px] text-ink-3">
                baseline {kpis.falign.baseline_root_drift.toFixed(2)} → 纠偏 100%
              </span>
            </div>
          ) : (
            <Skeleton className="h-24" />
          )}
        </Card>
        <Card bodyClassName="p-4">
          {kpis ? (
            <div className="flex flex-col">
              <span className="text-xs text-ink-3">GImport 导入成功率</span>
              <span className="tabular text-[32px] font-semibold leading-10 tracking-[-0.02em] text-gimport">
                {Math.round(kpis.gimport.import_success_rate * 100)}
                <small className="ml-0.5 text-base font-semibold text-ink-3">%</small>
              </span>
              <Sparkline points="M0 26 20 26 40 26 60 26 80 26 100 26 120 26" stroke="#3e7d5a" />
              <span className="text-[11px] text-ink-3">
                {kpis.gimport.manual_reduction.traditional_steps} 步 →{" "}
                {kpis.gimport.manual_reduction.gimport_steps} 步 ·{" "}
                {Math.round(kpis.gimport.time_comparison.speedup)}× 提速
              </span>
            </div>
          ) : (
            <Skeleton className="h-24" />
          )}
        </Card>
      </div>

      <Card
        title="最近任务"
        icon="terminal"
        right={
          <Button variant="ghost" size="sm" icon="chevron" onClick={() => navigate("/agents")}>
            指挥中心
          </Button>
        }
        bodyClassName="p-0"
      >
        {tasks.isLoading ? (
          <div className="space-y-2 p-5">
            <Skeleton className="h-9" />
            <Skeleton className="h-9" />
          </div>
        ) : (tasks.data?.tasks.length ?? 0) === 0 ? (
          <EmptyState
            icon="cube"
            title="还没有生产记录"
            description="描述你的第一个游戏创意，智能体团队将自主规划并产出引擎就绪资产。"
            action={
              <Button variant="primary" size="sm" icon="spark" onClick={generate}>
                生成第一个资产
              </Button>
            }
          />
        ) : (
          <table className="w-full border-collapse text-[13px]">
            <thead>
              <tr className="bg-surface-2 text-left text-[10.5px] uppercase tracking-[0.08em] text-ink-4">
                <th className="px-4 py-2.5 font-semibold">任务</th>
                <th className="px-4 py-2.5 font-semibold">目标</th>
                <th className="px-4 py-2.5 font-semibold">状态</th>
                <th className="px-4 py-2.5 font-semibold">资产</th>
                <th className="px-4 py-2.5 text-right font-semibold">事件</th>
              </tr>
            </thead>
            <tbody>
              {tasks.data!.tasks.map((task) => (
                <tr
                  key={task.task_id}
                  onClick={() => openTask(task)}
                  className="cursor-pointer border-b border-ink/[.08] text-ink-2 transition-colors last:border-0 hover:bg-surface-2/60"
                >
                  <td className="px-4 py-3 font-mono text-xs text-ink-3">{task.task_id}</td>
                  <td className="max-w-[420px] truncate px-4 py-3 text-ink">{task.goal}</td>
                  <td className="px-4 py-3">
                    <Badge tone={statusTone(task.status)}>
                      <StatusDot
                        tone={
                          task.status === "running"
                            ? "running"
                            : task.status === "pass"
                              ? "success"
                              : task.status === "failed"
                                ? "failed"
                                : "idle"
                        }
                      />
                      {task.status}
                    </Badge>
                  </td>
                  <td className="px-4 py-3 font-mono text-xs">{task.asset_id ?? "—"}</td>
                  <td className="tabular px-4 py-3 text-right font-mono text-xs text-ink-3">
                    {task.event_count}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Card>

      <div className="grid grid-cols-1 gap-5 md:grid-cols-3">
        {[
          {
            domain: "precon" as const,
            name: "PReCon 像素重建",
            tone: "precon" as const,
            icon: "grid" as const,
            text: "网格推断 · 语义 16 色调色板 · 轮廓修复 · 一致性 90%",
          },
          {
            domain: "falign" as const,
            name: "FAlign 切帧对齐",
            tone: "falign" as const,
            icon: "film" as const,
            text: "锚点检测 · 运动相位对齐 · 根运动纠偏 0.00 px/frame",
          },
          {
            domain: "gimport" as const,
            name: "GImport 引擎导入",
            tone: "gimport" as const,
            icon: "package" as const,
            text: "图集 · 动画剪辑 · Prefab · 运行时校验 · 一键导出 zip",
          },
        ].map((tech) => (
          <Card key={tech.name} domain={tech.domain} bodyClassName="p-4">
            <div className="flex items-center gap-2.5">
              <Badge tone={tech.tone} icon={tech.icon}>
                {tech.name.split(" ")[0]}
              </Badge>
              <span className="text-[15px] font-semibold">{tech.name.split(" ")[1]}</span>
            </div>
            <p className="mt-2.5 text-xs leading-[18px] text-ink-3">{tech.text}</p>
            <button
              onClick={() => navigate("/technology")}
              className="mt-3 inline-flex items-center gap-1 text-xs font-medium text-primary transition-opacity hover:opacity-80"
            >
              查看技术细节
              <Icon name="chevron" className="h-3.5 w-3.5" />
            </button>
          </Card>
        ))}
      </div>
    </div>
  );
}

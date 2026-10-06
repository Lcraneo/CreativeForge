import { useEffect, useMemo, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { motion, useReducedMotion } from "framer-motion";
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
  SectionTitle,
  Select,
  Skeleton,
  Stamp,
  StatusDot,
  Textarea,
  cx,
} from "../components/ui";
import { Icon } from "../components/icons";
import { CharacterArt } from "../components/CharacterArt";
import { EASE_STANDARD, MOTION } from "../lib/motion";
import type { GenerationOverrides } from "../types";

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

const WEEKDAYS = "日一二三四五六";

function relTime(seconds: number) {
  const diff = Date.now() - seconds * 1000;
  if (diff < 60_000) return "刚刚";
  if (diff < 3_600_000) return `${Math.floor(diff / 60_000)} 分钟前`;
  if (diff < 86_400_000) return `${Math.floor(diff / 3_600_000)} 小时前`;
  if (diff < 7 * 86_400_000) return `${Math.floor(diff / 86_400_000)} 天前`;
  return new Date(seconds * 1000).toLocaleDateString();
}

/** 交错进场：整页四个节拍依次浮现；系统声明降级时直通终态 */
const RISE = {
  hidden: { opacity: 0, y: 12 },
  show: { opacity: 1, y: 0, transition: { duration: MOTION.base, ease: EASE_STANDARD } },
};

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
  const reduceMotion = useReducedMotion();

  const startAgent = useAgentStore((state) => state.start);
  const resetWorkflow = useWorkflowStore((state) => state.reset);
  const plan = useWorkflowStore((state) => state.plan);
  const agentStatuses = useAgentStore((state) => state.agentStatuses);
  const liveTaskId = useAgentStore((state) => state.taskId);
  const progress = useAgentStore((state) => state.progress);
  const setAsset = useAssetStore((state) => state.set);

  const benchmark = useQuery({
    queryKey: ["benchmark"],
    queryFn: api.benchmark,
    staleTime: 10 * 60 * 1000,
    retry: false,
  });
  const modelSettings = useQuery({
    queryKey: ["model-settings"],
    queryFn: api.getModelSettings,
    staleTime: 15000,
  });
  const recent = useQuery({
    queryKey: ["history", "recent"],
    queryFn: () => api.listHistory({ limit: 6 }),
    staleTime: 30_000,
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

  const kpis = benchmark.data;
  const works = recent.data?.records ?? [];
  const now = new Date();
  const greeting =
    now.getHours() < 5 ? "夜深了" : now.getHours() < 11 ? "早上好" : now.getHours() < 14 ? "午安" : now.getHours() < 18 ? "下午好" : "晚上好";
  const dateLabel = `${now.getMonth() + 1}月${now.getDate()}日 周${WEEKDAYS[now.getDay()]}`;

  return (
    <motion.div
      className="mx-auto flex w-full max-w-[1440px] flex-col gap-6 px-4 py-5 md:px-6"
      initial={reduceMotion ? false : "hidden"}
      animate="show"
      variants={{ hidden: {}, show: { transition: { staggerChildren: MOTION.fast } } }}
    >
      {/* 案头：目标输入 + 炉温 */}
      <div className="grid grid-cols-12 gap-5">
        <motion.section
          variants={RISE}
          className="cf-sheen relative col-span-12 overflow-hidden rounded-2xl border border-line-subtle bg-[radial-gradient(620px_240px_at_88%_-30%,rgba(169,129,47,.12),transparent_70%),radial-gradient(420px_220px_at_6%_130%,rgba(62,125,90,.09),transparent_70%),linear-gradient(180deg,#f2efe9,#ece9e2)] p-6 xl:col-span-8"
        >
          {/* 右上角落款：朱印 + 竖排题字，不压正文 */}
          <div
            className="pointer-events-none absolute right-5 top-5 hidden select-none flex-col items-center gap-3 xl:flex"
            aria-hidden="true"
          >
            <Stamp char="锻" tone="ember" size={24} />
            <span className="cf-vertical font-display text-[11px] font-semibold text-ink-3">
              入炉百炼
            </span>
          </div>

          <div className="xl:pr-20">
            <div className="text-[11px] font-semibold uppercase tracking-[0.08em] text-ink-2">
              CreativeForge 工坊 · {dateLabel}
            </div>
            <h1 className="mt-2 font-display text-[30px] font-black leading-[1.2] [text-wrap:balance] xl:text-[34px]">
              {greeting}，今天锻造什么？
            </h1>
            <p className="mt-1.5 text-[13px] text-ink-3">
              写下目标，Supervisor 自动排开五段炉程，从一句话到可入引擎的资产。
            </p>
          </div>

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

          <div className="mt-4">
            <span className="text-[11px] text-ink-4">灵感签 · 点一张即可填入</span>
            <div className="mt-2 flex flex-wrap gap-2">
              {EXAMPLES.map((example) => (
                <button
                  key={example}
                  onClick={() => setGoal(example)}
                  className="cf-slip rounded-[6px] border border-line-subtle bg-canvas px-3 py-1.5 text-xs text-ink-3 shadow-e2 transition-all duration-(--motion-fast) ease-standard hover:border-primary/45 hover:text-primary"
                >
                  {example.length > 26 ? `${example.slice(0, 26)}…` : example}
                </button>
              ))}
            </div>
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
            <div className="flex items-center gap-2">
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
        </motion.section>

        <motion.div variants={RISE} className="col-span-12 xl:col-span-4">
          <Card
            className="h-full"
            title="生产管线"
            icon="activity"
            right={
              <Badge tone={liveTaskId ? "primary" : "neutral"}>
                <StatusDot tone={liveTaskId ? "running" : "idle"} />
                {liveTaskId ? `${progress}%` : "空闲"}
              </Badge>
            }
          >
            <ol className="space-y-[15px]">
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
                  <li key={`${step.label}-${index}`} className="flex items-center gap-3">
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
                    <span
                      className={cx(
                        "min-w-0 truncate text-[12.5px]",
                        step.status === "pending" ? "text-ink-3" : "font-medium text-ink-2",
                      )}
                    >
                      {step.label}
                    </span>
                    <span className="h-px flex-1 bg-line-subtle" aria-hidden="true" />
                    <span className="tabular font-display text-[11px] font-black text-ink-4">
                      0{index + 1}
                    </span>
                  </li>
                );
              })}
            </ol>
          </Card>
        </motion.div>
      </div>

      {/* 最近出炉 */}
      <motion.div variants={RISE} className="flex flex-col gap-4">
        <SectionTitle
          title="最近出炉"
          description="工坊最新的产出档案，点开直达详情。"
          action={
            <Button variant="ghost" size="sm" onClick={() => navigate("/history")}>
              进入历史记录
              <Icon name="chevron" className="h-3.5 w-3.5" />
            </Button>
          }
        />
        {recent.isLoading ? (
          <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 xl:grid-cols-6">
            {Array.from({ length: 6 }).map((_, index) => (
              <div key={index} className="space-y-2">
                <Skeleton className="aspect-[5/4] rounded-xl" />
                <Skeleton className="h-3.5 w-3/4" />
                <Skeleton className="h-3 w-1/2" />
              </div>
            ))}
          </div>
        ) : works.length === 0 ? (
          <EmptyState
            icon="image"
            title="炉子还没开过火"
            description="第一件资产出炉后，会陈列在这里。"
            className="rounded-xl border border-line-subtle bg-gradient-to-b from-[#f0ede6] to-[#ece9e1]"
          />
        ) : (
          <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 xl:grid-cols-6">
            {works.map((record) => (
              <button
                key={record.id}
                onClick={() => navigate(`/history?open=${record.id}`)}
                className="group cf-sheen relative overflow-hidden rounded-xl border border-line-subtle bg-gradient-to-b from-[#f0ede6] to-[#ece9e1] text-left transition-all duration-(--motion-fast) ease-standard hover:-translate-y-px hover:border-line"
              >
                <div className="relative aspect-[5/4] overflow-hidden border-b border-ink/[.06] bg-[#f1efe9]">
                  {record.image?.url ? (
                    <img
                      src={record.image.url}
                      alt={record.name ?? record.goal}
                      loading="lazy"
                      className="h-full w-full object-cover transition-transform duration-(--motion-slow) ease-standard group-hover:scale-[1.04]"
                    />
                  ) : (
                    <CharacterArt
                      spec={record.character}
                      palette={record.palette}
                      view="bust"
                      className="h-full w-full"
                    />
                  )}
                </div>
                <div className="p-3">
                  <div className="flex items-center gap-1.5">
                    <StatusDot
                      tone={
                        record.status === "failed"
                          ? "failed"
                          : record.status === "pass" || record.status === "success"
                            ? "success"
                            : "running"
                      }
                      className="scale-75"
                    />
                    <span className="truncate text-[12.5px] font-semibold text-ink">
                      {record.name || record.goal}
                    </span>
                  </div>
                  <div className="mt-0.5 flex items-center justify-between gap-2 text-[10.5px] text-ink-4">
                    <span className="truncate">{record.engine ? record.engine : "未入引擎"}</span>
                    <span className="tabular shrink-0 font-mono">
                      {relTime(record.finished_at)}
                    </span>
                  </div>
                </div>
              </button>
            ))}
          </div>
        )}
      </motion.div>

      {/* 工坊读数 */}
      <motion.div variants={RISE} className="flex flex-col gap-4">
        <SectionTitle
          title="工坊读数"
          description={
            kpis
              ? `基准数据集 ${kpis.dataset.size} 个样本 · ${new Date(kpis.generated_at).toLocaleString()} · 样本评测结果，不代表当前角色质量，GImport 为内部结构校验。`
              : benchmark.isError
                ? "基准报告暂不可用，仍可继续生成资产。"
                : "正在加载基准报告，首次评测需要一些时间…"
          }
          action={
            <Button
              size="sm"
              variant="ghost"
              onClick={() => (benchmark.isError ? void benchmark.refetch() : navigate("/benchmark"))}
            >
              {benchmark.isError ? "重试加载" : "查看评测详情"}
            </Button>
          }
        />
        {!benchmark.isError && (
          <div className="grid grid-cols-2 gap-5 xl:grid-cols-4">
            <Card bodyClassName="p-4">
              {kpis ? (
                <div className="flex flex-col">
                  <span className="text-xs text-ink-3">CF Score 综合评分</span>
                  <span className="tabular text-[32px] font-semibold leading-10 tracking-[-0.02em] text-ember">
                    {(kpis.cf_score.overall * 100).toFixed(1)}
                    <small className="ml-0.5 text-base font-semibold text-ink-3">%</small>
                  </span>
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
                  <span className="text-[11px] text-ink-3">
                    基线 {kpis.falign.baseline_root_drift.toFixed(2)} px/f
                  </span>
                </div>
              ) : (
                <Skeleton className="h-24" />
              )}
            </Card>
            <Card bodyClassName="p-4">
              {kpis ? (
                <div className="flex flex-col">
                  <span className="text-xs text-ink-3">GImport 结构校验通过率</span>
                  <span className="tabular text-[32px] font-semibold leading-10 tracking-[-0.02em] text-gimport">
                    {Math.round(kpis.gimport.import_success_rate * 100)}
                    <small className="ml-0.5 text-base font-semibold text-ink-3">%</small>
                  </span>
                  <span className="text-[11px] text-ink-3">
                    管线实测 {kpis.gimport.average_pipeline_seconds.toFixed(2)} 秒 · 不含编辑器导入
                  </span>
                </div>
              ) : (
                <Skeleton className="h-24" />
              )}
            </Card>
          </div>
        )}
      </motion.div>

      {/* 炉中三匠：三段领域智能体 */}
      <motion.div variants={RISE} className="flex flex-col gap-4">
        <SectionTitle
          title="炉中三匠"
          description="PReCon、FAlign、GImport 三段领域智能体接力，完成像素重建、切帧对齐与引擎导入。"
        />
        <Card bodyClassName="p-0">
          <div className="grid divide-y divide-ink/[.06] md:grid-cols-3 md:divide-y-0 md:divide-x">
            {[
              {
                domain: "precon" as const,
                tone: "precon" as const,
                icon: "grid" as const,
                mark: "PReCon",
                name: "像素重建",
                text: "网格推断 · 调色板重建 · 轮廓修复 · 像素一致性检查",
              },
              {
                domain: "falign" as const,
                tone: "falign" as const,
                icon: "film" as const,
                mark: "FAlign",
                name: "切帧对齐",
                text: "锚点检测 · 运动相位对齐 · 根运动纠偏 · 时序检查",
              },
              {
                domain: "gimport" as const,
                tone: "gimport" as const,
                icon: "package" as const,
                mark: "GImport",
                name: "引擎导入",
                text: "图集 · 动画与预制体配置 · 包结构校验 · 一键导出 ZIP",
              },
            ].map((tech) => (
              <div key={tech.mark} className="p-5">
                <div className="flex items-center gap-2.5">
                  <Badge tone={tech.tone} icon={tech.icon}>
                    {tech.mark}
                  </Badge>
                  <span className="text-[15px] font-semibold">{tech.name}</span>
                </div>
                <p className="mt-2.5 text-xs leading-[18px] text-ink-3">{tech.text}</p>
                <button
                  onClick={() => navigate("/technology")}
                  className="mt-3 inline-flex items-center gap-1 text-xs font-medium text-primary transition-opacity hover:opacity-80"
                >
                  查看技术细节
                  <Icon name="chevron" className="h-3.5 w-3.5" />
                </button>
              </div>
            ))}
          </div>
        </Card>
      </motion.div>
    </motion.div>
  );
}

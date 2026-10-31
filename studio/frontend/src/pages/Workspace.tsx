import { useEffect, useMemo, useRef, useState } from "react";
import { NavLink, useLocation, useNavigate } from "react-router-dom";
import { motion, useReducedMotion } from "framer-motion";
import { useQuery } from "@tanstack/react-query";
import { api, ApiError } from "../api/client";
import { useAgentStore } from "../stores/agentStore";
import { useWorkflowStore } from "../stores/workflowStore";
import { useAssetStore } from "../stores/assetStore";
import { toast } from "../stores/toastStore";
import {
  Badge,
  Button,
  Card,
  Chip,
  Input,
  SafeImage,
  SectionTitle,
  Select,
  Stamp,
  StatusDot,
  Textarea,
  cx,
} from "../components/ui";
import { Icon } from "../components/icons";
import {
  RococoDivider,
  RococoFrame,
  RococoRibbon,
} from "../components/rococo/RococoOrnaments";
import { EASE_STANDARD, MOTION } from "../lib/motion";
import { NAV_GROUPS } from "../lib/navigation";
import type { GenerationOverrides, ReferenceImage } from "../types";

const REFERENCE_MAX_BYTES = 10 * 1024 * 1024;
const REFERENCE_ACCEPT = "image/jpeg,image/png,image/webp";

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${Math.round(bytes / 1024)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

/** 四大工区旅程条：章序/名称/副题直接取自导航信息架构，落点 = 各区块首站 */
const JOURNEY = NAV_GROUPS.filter((group) => group.label !== "总览").map((group) => ({
  numeral: group.numeral,
  label: group.label,
  hint: group.hint,
  to: group.items[0].to,
}));

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
  const [reference, setReference] = useState<ReferenceImage | null>(null);
  const [uploading, setUploading] = useState(false);
  const [referenceError, setReferenceError] = useState<string | null>(null);
  const referenceInput = useRef<HTMLInputElement>(null);
  const navigate = useNavigate();
  const location = useLocation();
  const reduceMotion = useReducedMotion();

  const startAgent = useAgentStore((state) => state.start);
  const resetWorkflow = useWorkflowStore((state) => state.reset);
  const plan = useWorkflowStore((state) => state.plan);
  const agentStatuses = useAgentStore((state) => state.agentStatuses);
  const liveTaskId = useAgentStore((state) => state.taskId);
  const agentStatus = useAgentStore((state) => state.status);
  const progress = useAgentStore((state) => state.progress);
  const setAsset = useAssetStore((state) => state.set);

  const modelSettings = useQuery({
    queryKey: ["model-settings"],
    queryFn: api.getModelSettings,
    staleTime: 15000,
  });
  const cloudProviders = useQuery({
    queryKey: ["cloud-providers"],
    queryFn: api.cloudProviders,
    staleTime: 60_000,
    retry: false,
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

  async function uploadReference(file: File) {
    setUploading(true);
    setReferenceError(null);
    const previous = reference;
    try {
      const meta = await api.uploadCharacterReference(file);
      setReference(meta);
      if (previous && previous.file !== meta.file) {
        // 替换后尽力释放旧文件；仍被旧角色引用时后端会拒绝，不影响新图使用
        void api.deleteCharacterReference(previous.file).catch(() => undefined);
      }
      toast({
        tone: "success",
        title: "人物正面图已上传",
        description: "生成时将作为强身份参考，并保留原图关联到新角色",
      });
    } catch (cause) {
      const message =
        cause instanceof ApiError ? cause.message.replace(/^\d+:\s*/, "") : String(cause);
      setReferenceError(message);
      toast({ tone: "danger", title: "图片上传失败", description: message });
    } finally {
      setUploading(false);
    }
  }

  function chooseReference(file: File) {
    if (busy) return;
    const typeOk =
      ["image/jpeg", "image/png", "image/webp"].includes(file.type) ||
      /\.(jpe?g|png|webp)$/i.test(file.name);
    if (!typeOk) {
      const message = "仅支持 JPG / PNG / WebP 图片";
      setReferenceError(message);
      toast({ tone: "danger", title: "图片格式不支持", description: message });
      return;
    }
    if (file.size > REFERENCE_MAX_BYTES) {
      const message = "图片超过 10MB 限制，请压缩后重新上传";
      setReferenceError(message);
      toast({ tone: "danger", title: "图片过大", description: message });
      return;
    }
    void uploadReference(file);
  }

  async function removeReference() {
    const current = reference;
    setReference(null);
    setReferenceError(null);
    if (referenceInput.current) referenceInput.current.value = "";
    if (!current) return;
    try {
      await api.deleteCharacterReference(current.file);
    } catch {
      // 已被角色引用时后端拒绝删除；服务端文件保留，本地表单先清空即可
    }
  }

  async function generate() {
    if (!goal.trim() || busy || uploading || agentStatus === "running") return;
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

      const { task_id } = await api.createTask(text, cleaned, undefined, reference?.file);
      startAgent(task_id, text);
      toast({
        tone: "success",
        title: `任务 ${task_id} 已进入规划`,
        description: reference
          ? "已携带人物正面图：将作为强身份参考生成原画与三视图"
          : modelSettings.data?.enabled
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

  const now = new Date();
  const greeting =
    now.getHours() < 5 ? "夜深了" : now.getHours() < 11 ? "早上好" : now.getHours() < 14 ? "午安" : now.getHours() < 18 ? "下午好" : "晚上好";
  const dateLabel = `${now.getMonth() + 1}月${now.getDate()}日 周${WEEKDAYS[now.getDay()]}`;
  const cloudReady = Object.values(cloudProviders.data?.readiness ?? {}).filter(Boolean).length;

  return (
    <motion.div
      className="mx-auto flex w-full max-w-[1440px] flex-col gap-7 px-4 py-6 md:px-7 md:py-8"
      initial={reduceMotion ? false : "hidden"}
      animate="show"
      variants={{ hidden: {}, show: { transition: { staggerChildren: MOTION.fast } } }}
    >
      {/* 案头：目标输入 + 炉温 */}
      <div className="grid grid-cols-12 gap-5">
        <motion.section
          variants={RISE}
          className="cf-sheen cf-vellum relative col-span-12 overflow-hidden rounded-lg border border-line bg-[radial-gradient(720px_300px_at_92%_-28%,rgba(174,191,215,.42),transparent_70%),radial-gradient(520px_260px_at_0%_120%,rgba(255,255,255,.7),transparent_72%)] xl:col-span-7"
        >
          <RococoFrame contentClassName="p-6 xl:p-8">
          {/* 右上角落款：朱印 + 竖排题字，不压正文 */}
          <div
            className="pointer-events-none absolute right-5 top-5 hidden select-none flex-col items-center gap-3 xl:flex"
            aria-hidden="true"
          >
            <Stamp char="造" tone="ember" size={24} />
            <span className="cf-vertical font-serif text-[11px] font-semibold text-ink-3">
              蓝雾工坊
            </span>
          </div>

          <div className="xl:pr-24">
            <div className="flex flex-wrap items-center justify-between gap-3 border-b border-line pb-4">
              <RococoRibbon className="cf-rococo-ribbon--mist">
                Atelier des Assets · N° 01
              </RococoRibbon>
              <span className="cf-ref">{dateLabel}</span>
            </div>
            <h1 className="mt-6 max-w-[15ch] font-serif text-[38px] font-black leading-[1.08] tracking-[-0.03em] [text-wrap:balance] xl:text-[48px]">
              {greeting}，今天锻造什么？
            </h1>
            <p className="mt-3 max-w-[52ch] text-[14px] leading-6 text-ink-3">
              写下目标，Supervisor 自动排开五段炉程，从一句话到可入引擎的资产。
            </p>
            <RococoDivider className="mt-4 h-5 w-44 text-line-strong/85" />
          </div>

          <Textarea
            value={goal}
            onChange={(event) => setGoal(event.target.value)}
            onKeyDown={(event) => {
              if ((event.metaKey || event.ctrlKey) && event.key === "Enter") generate();
            }}
            rows={5}
            className="mt-6 min-h-[142px]"
            placeholder="创建一个像素风火焰法师Boss：需要 Idle 动画、Attack 动画、Unity 导出"
          />

          <div className="mt-5">
            <span className="cf-ref">灵感签 · 点一张即可填入</span>
            <div className="mt-2 grid grid-cols-1 gap-2 sm:grid-cols-2">
              {EXAMPLES.map((example, index) => (
                <button
                  key={example}
                  onClick={() => setGoal(example)}
                  title={example}
                  className="cf-slip flex min-w-0 items-start gap-2.5 rounded-sm border border-line px-3 py-2.5 text-left text-xs leading-[18px] text-ink-3 shadow-e1 transition-[color,border-color,box-shadow,transform] duration-(--motion-fast) ease-standard hover:border-line-strong hover:text-ink active:scale-[0.98]"
                >
                  <span
                    className="cf-display-num shrink-0 pt-0.5 text-[13px] leading-none text-ember-ink-ink"
                    aria-hidden="true"
                  >
                    0{index + 1}
                  </span>
                  <span className="line-clamp-2 min-w-0 [text-wrap:pretty]">{example}</span>
                </button>
              ))}
            </div>
          </div>

          <div className="mt-4 rounded-sm border border-line bg-surface-1/60 p-3">
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div className="min-w-0">
                <span className="cf-ref">人物正面图 · 可选</span>
                <p className="mt-1 max-w-[52ch] text-[11.5px] leading-[18px] text-ink-3">
                  上传光线均匀、人物正面站立、面部和服装无遮挡的全身图。上传后将作为强身份参考生成原画与正 /
                  侧 / 背三视图；不上传则按纯文本描述生成。
                </p>
              </div>
              <div className="flex shrink-0 items-center gap-2">
                <Button
                  variant="secondary"
                  size="sm"
                  icon="image"
                  loading={uploading}
                  disabled={busy || agentStatus === "running"}
                  onClick={() => referenceInput.current?.click()}
                >
                  {uploading ? "上传中…" : reference ? "重新上传" : "上传图片"}
                </Button>
                {reference && (
                  <Button
                    variant="ghost"
                    size="sm"
                    icon="trash"
                    disabled={busy}
                    onClick={removeReference}
                  >
                    删除
                  </Button>
                )}
              </div>
            </div>
            {reference && (
              <div className="mt-3 flex items-center gap-3 rounded-sm border border-line-subtle bg-paper p-2">
                <SafeImage
                  src={reference.url}
                  alt="人物正面图"
                  sealChar="正"
                  className="h-[92px] w-[92px] shrink-0 rounded-sm object-contain"
                />
                <div className="min-w-0 text-[11.5px] leading-[18px] text-ink-3">
                  <p className="truncate font-medium text-ink-2">{reference.file}</p>
                  <p className="mt-0.5">
                    {reference.width}×{reference.height} · {formatBytes(reference.bytes)}
                  </p>
                  <p className="mt-0.5 text-ink-4">生成时会保留原图并关联到新角色。</p>
                </div>
              </div>
            )}
            {referenceError && (
              <p role="alert" className="mt-2 text-[11.5px] text-danger">
                {referenceError}
              </p>
            )}
            <input
              ref={referenceInput}
              type="file"
              accept={REFERENCE_ACCEPT}
              className="hidden"
              onChange={(event) => {
                const file = event.target.files?.[0];
                if (file) chooseReference(file);
                event.target.value = "";
              }}
            />
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
              {cloudProviders.data?.enabled && (
                <button
                  type="button"
                  onClick={() => navigate("/settings")}
                  title="云生成能力（3D / 图像 / 视频 / 音频）配置"
                >
                  <Badge
                    tone={cloudReady === 4 ? "success" : cloudReady > 0 ? "primary" : "neutral"}
                    icon="cube"
                    className="cursor-pointer"
                  >
                    {cloudReady > 0 ? `云能力 · ${cloudReady}/4 可用` : "云能力未配置"}
                  </Badge>
                </button>
              )}
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
              <Button
                variant="primary"
                size="lg"
                icon="spark"
                loading={busy}
                onClick={generate}
                disabled={busy || uploading || agentStatus === "running"}
              >
                {busy ? "创建中…" : "生成资产"}
              </Button>
            </div>
          </div>

          {advanced && (
            <div className="mt-5 border-t border-line pt-4">
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
          </RococoFrame>
        </motion.section>

        <motion.div variants={RISE} className="col-span-12 xl:col-span-5">
          <Card
            className="cf-dossier flex h-full flex-col"
            title="生产管线"
            icon="activity"
            bodyClassName="flex flex-1 flex-col p-[18px]"
            right={
              <Badge tone={liveTaskId ? "primary" : "neutral"}>
                <StatusDot tone={liveTaskId ? "running" : "idle"} />
                {liveTaskId ? `${progress}%` : "空闲"}
              </Badge>
            }
          >
            <RococoDivider className="mx-auto mb-3 h-4 w-36 text-line-strong/70" />
            {/* 纵向炉程：一条墨线贯穿五段，节点落在序号上，随任务进度点亮 */}
            <ol className="relative flex flex-1 flex-col justify-between gap-3 py-0.5">
              <span
                className="absolute bottom-3 left-[13px] top-3 w-px bg-line"
                aria-hidden="true"
              />
              {pipeline.map((step, index) => {
                const tone =
                  step.status === "done"
                    ? "border-success bg-success/10 text-success"
                    : step.status === "running"
                      ? "border-primary bg-ember-tint text-primary shadow-[0_0_0_3px_rgba(174,191,215,.32)]"
                      : step.status === "failed"
                        ? "border-danger bg-danger/10 text-danger"
                        : "border-line bg-paper text-ink-4";
                const filled = step.status !== "pending";
                return (
                  <li key={`${step.label}-${index}`} className="relative flex items-center gap-3">
                    <span
                      className={cx(
                        "relative z-10 grid h-[26px] w-[26px] shrink-0 place-items-center rounded-full border-2",
                        tone,
                      )}
                    >
                      {filled ? (
                        <Icon
                          name={
                            step.status === "done"
                              ? "check"
                              : step.status === "running"
                                ? "refresh"
                                : "x"
                          }
                          className="h-3 w-3"
                        />
                      ) : (
                        <span className="cf-display-num text-[10px] leading-none text-ink-4">
                          {index + 1}
                        </span>
                      )}
                    </span>
                    <span
                      className={cx(
                        "min-w-0 truncate text-[12.5px]",
                        step.status === "pending" ? "text-ink-3" : "font-medium text-ink-2",
                        step.status === "running" && "font-semibold text-ink",
                      )}
                    >
                      {step.label}
                    </span>
                    <span className="h-px flex-1 bg-line/70" aria-hidden="true" />
                    <span className="tabular cf-display-num text-[11px] text-ink-4">
                      0{index + 1}
                    </span>
                  </li>
                );
              })}
            </ol>
            <div className="mt-4 flex items-center gap-1.5 border-t border-line pt-3 text-[11px] text-ink-4">
              <Icon name="spark" className="h-3 w-3 shrink-0 text-ember-ink" />
              五段炉程由 Supervisor 编排 · QA 质量门自动把关
            </div>
          </Card>
        </motion.div>
      </div>

      {/* 四大工区：旅程导航条（壹→贰→叁→肆），把侧栏的信息架构在案头显性一次。
          导航不做延迟进场（不参与 stagger），即时呈现并保证后续区块动画不被卡住 */}
      <nav
        aria-label="四大工区导航"
        className="grid grid-cols-2 overflow-hidden rounded-lg border border-line bg-paper shadow-e1 md:grid-cols-4"
      >
        {JOURNEY.map((zone) => (
          <NavLink
            key={zone.label}
            to={zone.to}
            className="group flex items-center gap-3 border-b border-line px-4 py-4 transition-colors duration-(--motion-fast) ease-standard last:border-b-0 odd:border-r hover:bg-ember-tint/55 md:border-b-0 md:border-r md:last:border-r-0"
          >
            <span className="cf-display-num text-[23px] leading-none text-ember-ink-ink">
              {zone.numeral}
            </span>
            <span className="min-w-0 flex-1">
              <span className="block text-[13.5px] font-semibold text-ink">{zone.label}</span>
              <span className="block truncate text-[11px] text-ink-3">{zone.hint}</span>
            </span>
            <Icon
              name="chevron"
              className="h-3.5 w-3.5 shrink-0 text-ink-4 transition-transform duration-(--motion-fast) ease-standard group-hover:translate-x-0.5 group-hover:text-ink-2"
            />
          </NavLink>
        ))}
      </nav>

      {/* 炉中三匠：三段领域智能体 */}
      <motion.div variants={RISE} className="flex flex-col gap-4">
        <SectionTitle
          title="炉中三匠"
          description="PReCon、FAlign、GImport 三段领域智能体接力，完成像素重建、切帧对齐与引擎导入。"
        />
        <Card bodyClassName="p-0">
          <div className="grid divide-y divide-line md:grid-cols-3 md:divide-x md:divide-y-0">
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
              <div
                key={tech.mark}
                className="group relative p-5 transition-colors duration-(--motion-base) ease-standard hover:bg-ember-tint/45"
              >
                <div className="flex items-center gap-2.5">
                  <Badge tone={tech.tone} icon={tech.icon}>
                    {tech.mark}
                  </Badge>
                  <span className="text-[15px] font-semibold">{tech.name}</span>
                </div>
                <p className="mt-2.5 text-xs leading-[18px] text-ink-3 [text-wrap:pretty]">{tech.text}</p>
              </div>
            ))}
          </div>
        </Card>
      </motion.div>
    </motion.div>
  );
}

import { useEffect, useMemo, useRef, useState } from "react";
import Konva from "konva";
import { Image as KonvaImage, Layer, Rect, Stage, Text as KonvaText, Rect as KonvaRect } from "react-konva";
import { useQuery } from "@tanstack/react-query";
import { api } from "../api/client";
import { Badge, Button, Card, EmptyState, PageHeader, cx } from "../components/ui";
import { Icon } from "../components/icons";
import { preloadImage } from "../lib/preload";
import { useHeldKeys } from "../lib/keyboard";
import { toast } from "../stores/toastStore";
import type { ActionBatchTask, PlaytestStrip } from "../types";

// 补丁 C②：canvas 背板按 DPR 渲染（封顶 2），必须在 Stage 挂载前设置
Konva.pixelRatio = Math.min(window.devicePixelRatio || 1, 2);

// 帧长动态来自后端 strips.fps（16fps/16 帧=1s 循环）；旧响应回落 10fps
const FALLBACK_FRAME_MS = 100;
const MAX_TICK_MS = 50; // 后台标签页回来时单次 tick 最多推进 50ms，防跳变
const SWITCH_FADE_MS = 120; // 补丁 D③：动作切换淡入时长
const STAGE_H = 360; // 高度固定，仅宽度自适应容器
const DEFAULT_STAGE_W = 640;
const GROUND_Y = 322;
const CHAR_H = 216;
const CHAR_MAX_W = 260;
// 原实现 3.2 / 5.6 px 每 60fps 帧，换算为 px/s 后与帧率解耦
const WALK_SPEED_PX_S = 192;
const RUN_SPEED_PX_S = 336;
const OVERRIDE_TAIL_MS = 150; // attack/jump 播完帧序列后额外停留的余量

const ACTION_HINT: Record<string, string> = {
  idle: "待机 · 无操作时自动播放",
  walk: "行走 · ← / →",
  run: "奔跑 · ← / → + Shift",
  attack: "攻击 · 空格",
  jump: "跳跃 · ↑",
};

// 后端 classify_error 的失败分类 → 画廊徽章短句（详细原因看 task.error）
const ERROR_KIND_LABEL: Record<string, string> = {
  moderation: "内容审核拦截",
  quota: "额度不足",
  auth: "Key 鉴权失败",
  network: "网络超时",
  fatal: "生成失败",
};

interface OverrideAction {
  name: "attack" | "jump";
  until: number;
}

export default function PlaytestStage() {
  // 人物显式选择（用户要求：不再自动跟随「当前资产」，由用户在此挑选）
  const [selected, setSelected] = useState<{ id: string; name: string; image_url?: string } | null>(null);
  const [pickerOpen, setPickerOpen] = useState(true);
  const selectedAssetId = selected?.id ?? null;
  const history = useQuery({
    queryKey: ["playtest-people"],
    queryFn: () => api.listHistory({ limit: 12 }),
  });
  const people = useMemo(
    () =>
      (history.data?.records ?? []).filter(
        (record) => record.asset_id && (record.image?.url || (record.asset ?? {}).image?.url),
      ),
    [history.data],
  );
  const [action, setAction] = useState("idle");
  const [frameIndex, setFrameIndex] = useState(0);
  const [position, setPosition] = useState(320);
  const [facing, setFacing] = useState(1);
  const [stageW, setStageW] = useState(DEFAULT_STAGE_W);
  const [stripImages, setStripImages] = useState<Record<string, HTMLImageElement>>({});

  const rafRef = useRef<number>(0);
  const lastRef = useRef<number>(0);
  const overrideRef = useRef<OverrideAction | null>(null);
  const pinnedRef = useRef<string | null>(null);
  const actionRef = useRef("idle");
  const frameIdxRef = useRef(0);
  const frameElapsedRef = useRef(0);
  const posRef = useRef(320);
  const facingRef = useRef(1);
  const stageWRef = useRef(DEFAULT_STAGE_W);
  const fadeStartRef = useRef<number | null>(null);
  const imgNodeRef = useRef<Konva.Image | null>(null);
  const framesByActionRef = useRef<Record<string, number>>({});
  const preloadStartedRef = useRef<Set<string>>(new Set());
  const stripReadyRef = useRef(false);
  const stageBoxRef = useRef<HTMLDivElement>(null);

  const previews = useQuery({
    queryKey: ["playtest-previews", selectedAssetId],
    queryFn: () => api.playtestPreviews(selectedAssetId!),
    enabled: Boolean(selectedAssetId),
  });
  // AI 动画补生成：未生成 AI 版的动作卡显示按钮，点击调视频驱动
  // （约 60~90 秒，后端同步返回），完成后重拉预览
  const [generatingAction, setGeneratingAction] = useState<string | null>(null);
  async function generateAiAnimation(name: string) {
    if (!selected?.id || generatingAction) return;
    setGeneratingAction(name);
    try {
      const result = await api.startActionBatch(selected.id, [name]);
      setBatchId(result.batch_id);
      toast({ tone: "info", title: `「${name}」AI 动画生成中`, description: "约 90 秒，完成后自动刷新预览" });
    } catch (cause) {
      toast({ tone: "danger", title: "AI 动画生成失败", description: String(cause).slice(0, 160) });
    } finally {
      setGeneratingAction(null);
    }
  }

  // 一键补齐全套动作：批次轮询（每动作状态实时更新，全部完成刷新预览）
  const [batchId, setBatchId] = useState<string | null>(null);
  const batch = useQuery({
    queryKey: ["action-batch", batchId],
    queryFn: () => api.actionBatchStatus(batchId!),
    enabled: Boolean(batchId),
    refetchInterval: (query) => (query.state.data?.status === "running" ? 2500 : false),
  });
  const batchData = batch.data;
  const batchDoneCount = (batchData?.tasks ?? []).filter(
    (task) => task.status === "done" || task.status === "skipped",
  ).length;
  const batchRunning = batchData?.status === "running";
  const [tick, setTick] = useState(0);
  useEffect(() => {
    if (!generatingAction && !batchRunning) return;
    const timer = setInterval(() => setTick((v) => v + 1), 400);
    return () => clearInterval(timer);
  }, [generatingAction, batchRunning]);

  // refetch 引用稳定，避免依赖整个 previews（每次渲染都是新引用 → 无限 refetch）
  const refetchPreviews = previews.refetch;
  useEffect(() => {
    if ((batchData?.status === "done" || batchData?.status === "failed") && batchId) {
      void refetchPreviews();
    }
  }, [batchData?.status, batchId, refetchPreviews]);

  function batchTaskFor(name: string): ActionBatchTask | undefined {
    return (batchData?.tasks ?? []).find((t) => t.action === name);
  }

  /** 阶段映射进度：i2v 是大头（90s 预估线性爬升至 80%），后段快速走完 */
  function stageProgressPct(task?: ActionBatchTask): number {
    if (!task) return 0;
    if (task.status === "done") return 100;
    if (task.status !== "generating") return 4;
    const base: Record<string, number> = { prompt: 5, video: 10, sampling: 84, composing: 93 };
    let pct = base[task.stage ?? "video"] ?? 10;
    if (task.stage === "video" && task.started_at) {
      const elapsed = Date.now() / 1000 - task.started_at;
      pct = Math.min(80, base.video + Math.round((elapsed / 90) * 70));
    }
    return pct;
  }

  const STAGE_LABEL: Record<string, string> = {
    prompt: "提交生成任务…",
    video: "AI 视频生成中…（约 60~90 秒）",
    sampling: "抽帧与稳定处理…",
    composing: "合成动作条带…",
  };

  async function generateAllActions() {
    if (!selected?.id || generatingAction || batchRunning) return;
    const missing = (previews.data?.actions ?? []).filter(
      (name) => previews.data?.strips?.[name]?.engine !== "ai-video",
    );
    if (missing.length === 0) {
      toast({ tone: "info", title: "全部动作都已是 AI 动画帧" });
      return;
    }
    setGeneratingAction("batch");
    try {
      const result = await api.startActionBatch(selected.id);
      setBatchId(result.batch_id);
      toast({
        tone: "info",
        title: `开始补齐 ${result.snapshot.total} 个动作`,
        description: "串行生成中（每个约 90 秒），完成后自动刷新预览",
      });
    } catch (cause) {
      toast({ tone: "danger", title: "批量启动失败", description: String(cause).slice(0, 160) });
    } finally {
      setGeneratingAction(null);
    }
  }

  // 条带地址表：新结构读 strips，旧响应把 previews 图当条带用
  const stripUrls: Record<string, string> = useMemo(() => {
    const data = previews.data;
    if (!data) return {};
    if (data.strips) {
      const out: Record<string, string> = {};
      for (const [name, s] of Object.entries(data.strips)) {
        if (s?.url) out[name] = s.url;
      }
      return out;
    }
    return { ...(data.previews ?? {}) };
  }, [previews.data]);

  const stripMeta: PlaytestStrip | undefined = useMemo(() => {
    const data = previews.data;
    if (!data) return undefined;
    if (data.strips?.[action]) return data.strips[action];
    const url = stripUrls[action];
    return url
      ? { url, frames: 8, width: 96, height: 96, engine: data.source ?? "procedural" }
      : undefined;
  }, [previews.data, stripUrls, action]);

  // 补丁 A：全部动作统一预载（idle 优先 high），切换动作零请求
  useEffect(() => {
    const entries = Object.entries(stripUrls);
    if (entries.length === 0) return;
    let cancelled = false;
    const preferred = entries.find(([name]) => name === "idle") ?? entries[0];
    const ordered = [preferred, ...entries.filter((e) => e !== preferred)].filter(
      ([, url]) => !preloadStartedRef.current.has(url),
    );
    for (const [, url] of ordered) preloadStartedRef.current.add(url);

    // 首选条带加 rel=preload 提示：HTTP 缓存命中场景下浏览器可更早启动抓取，
    // 与 decode 门控一起构成零尖峰链路
    const preferredUrl = ordered[0]?.[1];
    let preloadLink: HTMLLinkElement | null = null;
    if (preferredUrl) {
      preloadLink = document.createElement("link");
      preloadLink.rel = "preload";
      preloadLink.as = "image";
      preloadLink.href = preferredUrl;
      preloadLink.setAttribute("fetchpriority", "high");
      document.head.appendChild(preloadLink);
    }

    void Promise.all(
      ordered.map(async ([name, url], index) => {
        try {
          const image = await preloadImage(url, index === 0 ? "high" : "low");
          if (!cancelled) setStripImages((prev) => ({ ...prev, [name]: image }));
        } catch {
          /* 单个条带失败不拖垮其他动作；舞台保持占位文案 */
        }
      }),
    );
    return () => {
      cancelled = true;
      preloadLink?.remove();
    };
  }, [stripUrls]);

  // 当前动作条带就绪信号：rAF 循环据此跳过占位期的帧推进
  useEffect(() => {
    stripReadyRef.current = Boolean(stripImages[action]);
  }, [stripImages, action]);

  // 加载进度：条带就绪数 / 总动作数（让用户知道选人后系统在干什么）
  const totalActions = Object.keys(stripUrls).length;
  const readyActions = Object.keys(stripImages).length;
  const progressPct =
    totalActions === 0 ? 0 : Math.round((readyActions / totalActions) * 100);

  // 各动作帧数表（循环内只读 ref，不触发重渲染）
  useEffect(() => {
    const data = previews.data;
    if (!data) return;
    const table: Record<string, number> = {};
    if (data.strips) {
      for (const [name, s] of Object.entries(data.strips)) {
        table[name] = Math.max(1, s?.frames ?? 8);
      }
      framesByActionRef.current = table;
      return;
    }
    for (const name of Object.keys(data.previews ?? {})) table[name] = 8;
    framesByActionRef.current = table;
  }, [previews.data]);

  const framesFor = (name: string) => framesByActionRef.current[name] ?? 8;

  // 帧长随后端 fps 契约走（16fps = 62.5ms/帧）；rAF 循环内只读 ref
  const frameMsRef = useRef(FALLBACK_FRAME_MS);
  useEffect(() => {
    const fps = stripMeta?.fps ?? previews.data?.fps ?? 1000 / FALLBACK_FRAME_MS;
    // 速度感知播放：奔跑步频加快 1.3 倍，行走/待机用原始帧率——
    // 移动速度与步态频率匹配，walk→run 切换观感平滑
    const scaled = action === "run" ? fps * 1.3 : fps;
    frameMsRef.current = 1000 / Math.max(1, scaled);
  }, [stripMeta, previews.data, action]);

  function triggerOverride(name: OverrideAction["name"]) {
    const durationMs = framesFor(name) * frameMsRef.current + OVERRIDE_TAIL_MS;
    overrideRef.current = { name, until: performance.now() + durationMs };
  }

  // 键盘：useHeldKeys 统一管理（blur 全清 / typing 守卫 / preventDefault），
  // 空格与 ↑ 在按下时触发一次性动作（attack/jump，含按住连发=原行为）
  const keysRef = useHeldKeys(["arrowleft", "arrowright", "arrowup", " "], (key) => {
    if (key === " ") triggerOverride("attack");
    if (key === "arrowup") triggerOverride("jump");
  });

  // 补丁 C①：舞台宽度自适应容器（高度与地面线不变，避免整套坐标换算）
  useEffect(() => {
    const el = stageBoxRef.current;
    if (!el || typeof ResizeObserver === "undefined") return;
    const observer = new ResizeObserver((entries) => {
      const width = Math.round(entries[0].contentRect.width);
      if (width > 0 && width !== stageWRef.current) {
        stageWRef.current = width;
        setStageW(width);
      }
    });
    observer.observe(el);
    return () => observer.disconnect();
  }, []);

  // 补丁 B：rAF 时间步进——累加器按固定帧长推进整数帧，状态无变化不重渲染；
  // 补丁 D：动作切换重置帧游标 + 淡入，attack/jump 播完整帧序列后回落
  useEffect(() => {
    const loop = (time: number) => {
      const delta = lastRef.current ? Math.min(time - lastRef.current, MAX_TICK_MS) : 16.7;
      lastRef.current = time;

      const keys = keysRef.current;
      const left = keys.has("arrowleft");
      const right = keys.has("arrowright");
      const running = keys.has("shift");

      const override = overrideRef.current;
      const overrideActive = override !== null && time < override.until;
      if (override !== null && !overrideActive) overrideRef.current = null;

      let nextAction = "idle";
      let fromKeys = false;
      if (overrideActive) {
        nextAction = override.name;
      } else if (left !== right) {
        nextAction = running ? "run" : "walk";
        fromKeys = true;
      } else if (pinnedRef.current) {
        nextAction = pinnedRef.current;
      }
      // 方向键永远接管钉住的动作；松键回 idle（windup 语义），不再悬在旧状态
      if (fromKeys) pinnedRef.current = null;

      if (nextAction !== actionRef.current) {
        actionRef.current = nextAction;
        frameIdxRef.current = 0;
        frameElapsedRef.current = 0;
        fadeStartRef.current = time;
        imgNodeRef.current?.opacity(0);
        setAction(nextAction);
        setFrameIndex(0);
      }

      if (left !== right) {
        const direction = right ? 1 : -1;
        const speed = ((running ? RUN_SPEED_PX_S : WALK_SPEED_PX_S) * delta) / 1000;
        if (facingRef.current !== direction) {
          facingRef.current = direction;
          setFacing(direction);
        }
        const nextX = Math.max(
          80,
          Math.min(stageWRef.current - 80, posRef.current + direction * speed),
        );
        if (nextX !== posRef.current) {
          posRef.current = nextX;
          setPosition(nextX);
        }
      }

      // 帧步进：attack/jump 停在末帧，循环动作取模；
      // 条带未就绪时跳过推进——占位期不做任何 setState（零空转重渲染）
      if (!stripReadyRef.current) {
        rafRef.current = requestAnimationFrame(loop);
        return;
      }
      const frames = framesFor(nextAction);
      const frameMs = frameMsRef.current;
      let idx = frameIdxRef.current % frames;
      let elapsed = frameElapsedRef.current + delta;
      let changed = false;
      while (elapsed >= frameMs) {
        if (overrideActive && idx >= frames - 1) {
          elapsed = frameMs;
          break;
        }
        elapsed -= frameMs;
        idx = (idx + 1) % frames;
        changed = true;
      }
      frameElapsedRef.current = elapsed;
      if (changed) {
        frameIdxRef.current = idx;
        setFrameIndex(idx);
      }

      // 淡入插值直接写 Konva 节点，不走 React
      if (fadeStartRef.current !== null && imgNodeRef.current) {
        const progress = (time - fadeStartRef.current) / SWITCH_FADE_MS;
        imgNodeRef.current.opacity(Math.min(1, progress));
        if (progress >= 1) fadeStartRef.current = null;
      }

      rafRef.current = requestAnimationFrame(loop);
    };
    rafRef.current = requestAnimationFrame(loop);
    return () => cancelAnimationFrame(rafRef.current);
  }, []);

  // 条带真实几何：frameW/H 来自图片实际尺寸（后端已裁掉空白边，帧底即脚底）
  const strip = stripImages[action] ?? null;
  const rigged = stripMeta?.engine === "rigged";
  const frames = Math.max(1, stripMeta?.frames ?? 8);
  const frameW = strip ? strip.naturalWidth / frames : (stripMeta?.width ?? 96);
  const frameH = strip ? strip.naturalHeight : (stripMeta?.height ?? 96);

  // 显示尺寸：以 CHAR_H 为基准等比缩放；过宽的角色按宽度收敛
  const charScale = CHAR_H / Math.max(1, frameH);
  const charW = Math.min(CHAR_MAX_W, frameW * charScale);
  const charH = frameH * (charW / Math.max(1, frameW));
  const feetY = GROUND_Y;

  const chibi = previews.data?.character?.proportion === "chibi";
  const missingCount = (previews.data?.actions ?? []).filter(
    (name) => previews.data?.strips?.[name]?.engine !== "ai-video",
  ).length;

  return (
    <div className="mx-auto flex w-full max-w-[1440px] flex-col gap-5 px-4 py-5 md:px-6">
      <PageHeader
        overline="Playtest"
        title="试玩舞台"
        description="绑定当前角色原画的骨骼动作——用方向键跑起来试一试，素材好不好，跑起来才知道"
        actions={
          <>
            <Badge tone={rigged ? "primary" : "neutral"} icon="spark">
              {rigged ? `角色绑定 · ${selected?.name ?? "未选择"}` : "未选择人物"}
            </Badge>
            <Button
              variant="secondary"
              size="sm"
              icon="cube"
              onClick={() => setPickerOpen(true)}
            >
              更换人物
            </Button>
          </>
        }
      />

      <div className="grid grid-cols-12 gap-5">
        <Card
          className="col-span-12 lg:col-span-8"
          title="试玩区 Playtest"
          icon="film"
          right={<Badge tone="neutral">{ACTION_HINT[action]}</Badge>}
        >
          <div
            ref={stageBoxRef}
            className="overflow-hidden rounded-xl border border-line-subtle bg-[#f1efe9]"
          >
            <Stage width={stageW} height={STAGE_H} className="max-w-full">
              <Layer listening={false}>
                {/* 地面：地面线必须在舞台内，角色脚底贴线 */}
                <Rect
                  x={0}
                  y={GROUND_Y}
                  width={stageW}
                  height={STAGE_H - GROUND_Y}
                  fill="#ddd8ca"
                />
                <Rect x={0} y={GROUND_Y} width={stageW} height={2.5} fill="#b9b3a5" />
                {strip ? (
                  <KonvaImage
                    ref={imgNodeRef}
                    image={strip}
                    x={position - charW / 2}
                    y={feetY - charH}
                    width={charW}
                    height={charH}
                    crop={{
                      x: frameIndex * frameW,
                      y: 0,
                      width: frameW,
                      height: frameH,
                    }}
                    scaleX={facing}
                    offsetX={facing === -1 ? charW : 0}
                    imageSmoothingEnabled={false}
                  />
                ) : (
                  <>
                  <KonvaText
                    x={stageW / 2 - 110}
                    y={STAGE_H / 2 - 30}
                    text={
                      !selectedAssetId
                        ? "← 先在下方选择一个试玩人物"
                        : previews.isLoading
                          ? "正在为该人物准备动作帧…"
                          : `动作帧准备中 ${progressPct}%（${readyActions}/${totalActions}）`
                    }
                    fontSize={14}
                    fill="#6f7d8c"
                  />
                  {Boolean(selectedAssetId) && (
                    <KonvaRect
                      x={stageW / 2 - 110}
                      y={STAGE_H / 2 + 6}
                      width={220}
                      height={6}
                      cornerRadius={3}
                      fill="#ddd9cf"
                    />
                  )}
                  {Boolean(selectedAssetId) && (
                    <KonvaRect
                      x={stageW / 2 - 110}
                      y={STAGE_H / 2 + 6}
                      width={Math.max(4, (220 * progressPct) / 100)}
                      height={6}
                      cornerRadius={3}
                      fill="#0e8ea8"
                    />
                  )}
                  </>
                )}
              </Layer>
            </Stage>
          </div>
          <div className="mt-3 flex flex-wrap items-center gap-2 text-[11.5px] text-ink-3">
            <kbd className="rounded-xs border border-line px-1.5 font-mono text-[10px]">←</kbd>
            <kbd className="rounded-xs border border-line px-1.5 font-mono text-[10px]">→</kbd> 移动
            <kbd className="rounded-xs border border-line px-1.5 font-mono text-[10px]">
              Shift
            </kbd>{" "}
            奔跑
            <kbd className="rounded-xs border border-line px-1.5 font-mono text-[10px]">↑</kbd> 跳跃
            <kbd className="rounded-xs border border-line px-1.5 font-mono text-[10px]">
              空格
            </kbd>{" "}
            攻击
            <span className="ml-auto">点击下方动作卡可直接切换预览</span>
          </div>
          {chibi && rigged && (
            <p className="mt-2 flex items-center gap-1.5 text-[11px] text-amber-700">
              <Icon name="clock" className="h-3 w-3" />
              检测到 Q
              版头身比，骨骼分区拟合度较低，动作可能出现轻微错位；完整动画建议在动画工作台使用 AI
              视频驱动。
            </p>
          )}
        </Card>

        <Card
          className="col-span-12 lg:col-span-4"
          title="动作画廊 Action Gallery"
          icon="grid"
          bodyClassName="p-3"
        >
          {previews.isLoading ? (
            <p className="p-3 text-xs text-ink-3">渲染动作预览…</p>
          ) : (
            <div className="flex flex-col gap-2.5">
              {missingCount > 0 && (
                <Button
                  variant="primary"
                  size="sm"
                  icon="spark"
                  loading={batchRunning}
                  onClick={generateAllActions}
                  className="mb-1"
                >
                  {batchRunning
                    ? `补齐全套动作中…（${batchDoneCount}/${batchData?.total ?? 0}）`
                    : `一键生成全部动作（缺 ${missingCount} 个）`}
                </Button>
              )}
              {batchData?.tasks
                ?.filter((task: ActionBatchTask) => task.status === "generating" || task.status === "failed")
                .map((task: ActionBatchTask) => (
                  <div
                    key={task.action}
                    className={cx(
                      "rounded-md border px-2.5 py-1.5 text-[11px]",
                      task.status === "failed"
                        ? "border-danger/40 bg-danger/5 text-danger"
                        : "border-primary/40 bg-primary-tint/40 text-ink-2",
                    )}
                  >
                    {task.action} ·{" "}
                    {task.status === "generating"
                      ? "AI 生成中…"
                      : ERROR_KIND_LABEL[task.error_kind ?? ""] || task.error || "生成失败"}
                  </div>
                ))}
              {(previews.data?.actions ?? []).map((name) => (
                <button
                  key={name}
                  onClick={() => {
                    // 钉住请求，由主循环统一应用切换（游标归零 + 淡入）
                    pinnedRef.current = name;
                  }}
                  className={cx(
                    "flex items-center gap-3 rounded-xl border p-2 text-left transition-all",
                    action === name
                      ? "border-primary/60 bg-primary-tint/40"
                      : "border-line-subtle hover:border-line",
                  )}
                >
                  <span className="min-w-0 flex-1">
                    <span className="flex items-center gap-1.5">
                      <span className="text-[12.5px] font-medium text-ink">{name}</span>
                      {previews.data?.strips?.[name]?.engine === "ai-video" && (
                        <Badge tone="primary">AI</Badge>
                      )}
                      {generatingAction === name && <Badge tone="warning">生成中</Badge>}
                    </span>
                    <span className="block truncate text-[10.5px] text-ink-3">
                      {ACTION_HINT[name]}
                    </span>
                    {previews.data?.strips?.[name]?.engine !== "ai-video" && !generatingAction && (
                      <button
                        onClick={(event) => {
                          event.stopPropagation();
                          void generateAiAnimation(name);
                        }}
                        className="mt-1 inline-flex items-center gap-1 text-[10.5px] font-medium text-primary underline-offset-2 hover:underline"
                      >
                        <Icon name="spark" className="h-3 w-3" />
                        生成 AI 动画
                      </button>
                    )}
                    {(generatingAction === name || batchTaskFor(name)?.status === "generating") && (() => {
                      const task = batchTaskFor(name) ?? { action: name, status: "generating", stage: "video", started_at: Date.now() / 1000 };
                      const pct = stageProgressPct(task);
                      void tick;
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
                    })()}
                  </span>
                  {previews.data?.previews?.[name] && (
                    <img
                      src={previews.data.previews[name]}
                      alt={name}
                      loading="lazy"
                      className="h-[46px] w-[128px] rounded-md border border-line-subtle bg-white object-cover object-left"
                    />
                  )}
                </button>
              ))}
            </div>
          )}
          <p className="mt-3 flex items-center gap-1.5 text-[11px] text-ink-4">
            <Icon name="clock" className="h-3 w-3" />
            {rigged
              ? "动作帧由当前角色原画实时变形渲染；更高质量版本可在动画工作台生成。"
              : "暂无当前资产：先在创作工作台生成角色，试玩舞台会自动绑定它的原画。"}
          </p>
        </Card>
      </div>

      {pickerOpen && (
        <Card title="选择试玩人物 · 近期生成" icon="cube" bodyClassName="p-3">
          {history.isLoading ? (
            <p className="p-3 text-xs text-ink-3">读取近期生成记录…</p>
          ) : people.length === 0 ? (
            <p className="p-3 text-xs text-ink-3">
              还没有可用的人物——先去创作工作台生成一个角色，再回到这里挑选。
            </p>
          ) : (
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-4 lg:grid-cols-6">
              {people.map((record) => (
                <button
                  key={record.id}
                  onClick={() => {
                    setStripImages({});
                    setFrameIndex(0);
                    setSelected({
                      id: record.asset_id!,
                      name: record.name || record.goal,
                      image_url: record.image?.url ?? undefined,
                    });
                    setPickerOpen(false);
                  }}
                  className={cx(
                    "flex flex-col overflow-hidden rounded-xl border transition-all",
                    selected?.id === record.asset_id
                      ? "border-primary/60"
                      : "border-line-subtle hover:border-line",
                  )}
                >
                  <img
                    src={record.image?.url ?? undefined}
                    alt={String(record.name ?? record.asset_id ?? "")}
                    loading="lazy"
                    className="h-[120px] w-full bg-[#f1efe9] object-contain"
                  />
                  <span className="truncate px-2 py-1.5 text-[11px] text-ink-3">
                    {record.name || record.asset_id}
                  </span>
                </button>
              ))}
            </div>
          )}
        </Card>
      )}
    </div>
  );
}

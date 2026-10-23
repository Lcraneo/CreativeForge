/**
 * 试玩舞台 V2 · 页面壳（PlaytestContent）
 *
 * 桌面布局：顶栏（角色/来源/当前动作/FPS/暂停/全屏）+ 16:9 深色验收
 * 舞台（Clean/Debug 切换 + 诊断抽屉）+ 底部动作坞 + 键位/进度/状态脚注。
 *
 * 渲染分层：高频状态（帧游标、位置、朝向、动作仲裁）全部住在
 * PlaytestEngine（无 React）；React 只承载低频壳（动作卡、加载、抽屉）。
 * rAF 循环里没有任何 setState —— 动画运行时整页零重渲染。
 */
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { api } from "../../api/client";
import { Badge, Button, PageHeader, cx } from "../../components/ui";
import { Icon } from "../../components/icons";
import { useHeldKeys } from "../../lib/keyboard";
import { toast } from "../../stores/toastStore";
import type { ActionBatchTask, CreativeAsset, PlaytestStrip } from "../../types";
import { PlaytestCanvas } from "./PlaytestCanvas";
import { PlaytestActionDock, BASE_ACTION_LABEL } from "./PlaytestActionDock";
import { PlaytestDiagnostics } from "./PlaytestDiagnostics";
import { PlaytestCharacterPicker } from "./PlaytestCharacterPicker";
import { usePlaytestAssets, BUILT_IN_ACTIONS } from "./usePlaytestAssets";
import { PlaytestEngine, type PlaytestMode } from "./playtestEngine";

export function PlaytestContent({ selected }: { selected: CreativeAsset | null }) {
  const [, setSearchParams] = useSearchParams();
  const navigate = useNavigate();
  const selectedAssetId = selected?.id ?? null;
  const [pickerOpen, setPickerOpen] = useState(!selected);

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

  /* ── 渐进式资源（元数据分批 + 逐张解码 + 失败重试） ─────────────── */
  const [libraryOpen, setLibraryOpen] = useState(false);
  const assets = usePlaytestAssets(selectedAssetId, { libraryOpen });
  const { meta } = assets;

  /* ── 引擎：输入 → 动作仲裁 → 帧游标/位置/朝向（全部内部维护） ──── */
  const engine = useMemo(() => new PlaytestEngine(), []);

  // 键盘：方向键/WASD 移动，Shift 奔跑，空格/J 攻击、↑/W 跳跃（按住连发）；
  // preventDefault 与输入框保护沿 useHeldKeys（与旧页一致）
  const keysRef = useHeldKeys(["arrowleft", "arrowright", "arrowup", " "], (key) => {
    if (key === " " || key === "j") engine.press("attack");
    if (key === "arrowup" || key === "w") engine.press("jump");
  });
  // 输入接线放在 effect 中（effect 里读 ref 是合法副作用位置）
  useEffect(() => {
    engine.setInputSource(() => ({
      left: keysRef.current.has("arrowleft") || keysRef.current.has("a"),
      right: keysRef.current.has("arrowright") || keysRef.current.has("d"),
      run: keysRef.current.has("shift"),
    }));
  }, [engine, keysRef]);

  // 低频订阅：动作/模式变化才通知 React（帧推进不经过这里）
  const [uiAction, setUiAction] = useState("idle");
  const [uiMode, setUiMode] = useState<PlaytestMode>("live");
  useEffect(
    () =>
      engine.onStateChange((snapshot) => {
        setUiAction(snapshot.action);
        setUiMode(snapshot.mode);
      }),
    [engine],
  );

  // 条带元数据（含自定义动作）注入引擎：帧数/帧率
  const stripMetaByKey = useMemo(() => {
    const map: Record<string, PlaytestStrip> = { ...meta.strips };
    for (const item of meta.customActions) {
      if (item.strip) map[`custom:${item.name}`] = item.strip;
    }
    return map;
  }, [meta]);
  useEffect(() => {
    for (const [key, strip] of Object.entries(stripMetaByKey)) {
      engine.setStripTiming(key, { frames: Math.max(1, strip.frames), fps: strip.fps ?? 10 });
    }
  }, [engine, stripMetaByKey]);

  /* ── 舞台控制（暂停 / 全屏 / Clean·Debug / 诊断抽屉） ──────────── */
  const [paused, setPaused] = useState(false);
  const [debug, setDebug] = useState(false);
  const [diagnosticsOpen, setDiagnosticsOpen] = useState(false);
  const [fullscreen, setFullscreen] = useState(false);
  const stageRef = useRef<HTMLDivElement>(null);

  const toggleFullscreen = useCallback(async () => {
    const node = stageRef.current;
    if (!node) return;
    try {
      if (document.fullscreenElement) await document.exitFullscreen();
      else await node.requestFullscreen();
    } catch {
      /* 浏览器策略拒绝时静默忽略（键盘 F11 仍可用） */
    }
  }, []);
  useEffect(() => {
    const onChange = () => setFullscreen(Boolean(document.fullscreenElement));
    document.addEventListener("fullscreenchange", onChange);
    return () => document.removeEventListener("fullscreenchange", onChange);
  }, []);

  // FPS 徽章：500ms 低频轮询引擎真实指标直写 DOM，绕过 React
  const fpsMeterRef = useRef<HTMLSpanElement>(null);
  useEffect(() => {
    const timer = setInterval(() => {
      if (!fpsMeterRef.current) return;
      const { fps, frameMs } = engine.getMetrics();
      fpsMeterRef.current.textContent = fps > 0 ? `${fps} FPS · ${frameMs}ms` : "— FPS";
    }, 500);
    return () => clearInterval(timer);
  }, [engine]);

  /* ── AI 动画补生成（单动作 / 一键全套 + 批次轮询） ──────────────── */
  const [generatingAction, setGeneratingAction] = useState<string | null>(null);
  const [batchId, setBatchId] = useState<string | null>(null);
  const batch = useQuery({
    queryKey: ["action-batch", batchId],
    queryFn: () => api.actionBatchStatus(batchId!),
    enabled: Boolean(batchId),
    refetchInterval: (query) => (query.state.data?.status === "running" ? 2500 : false),
  });
  const batchData = batch.data;
  const batchTasks: ActionBatchTask[] = batchData?.tasks ?? [];
  const batchDoneCount = batchTasks.filter(
    (task) => task.status === "done" || task.status === "skipped",
  ).length;
  const batchRunning = batchData?.status === "running";

  // 生成中动作的进度条平滑爬升（2.5s 轮询之间补间）
  const [tick, setTick] = useState(0);
  useEffect(() => {
    if (!generatingAction && !batchRunning) return;
    const timer = setInterval(() => setTick((value) => value + 1), 400);
    return () => clearInterval(timer);
  }, [generatingAction, batchRunning]);

  const invalidateAll = assets.invalidateAll;
  useEffect(() => {
    if ((batchData?.status === "done" || batchData?.status === "failed") && batchId) {
      invalidateAll();
    }
  }, [batchData?.status, batchId, invalidateAll]);

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

  const missingCount = BUILT_IN_ACTIONS.filter(
    (name) => meta.strips[name]?.engine !== "ai-video",
  ).length;

  async function generateAllActions() {
    if (!selected?.id || generatingAction || batchRunning) return;
    if (missingCount === 0) {
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

  /* ── 动作坞交互 ────────────────────────────────────────────────── */
  const requestActions = assets.requestActions;
  const selectAction = useCallback(
    (key: string) => {
      engine.pin(key);
      requestActions([key]);
    },
    [engine, requestActions],
  );
  const onResumeLive = useCallback(() => engine.resumeLive(), [engine]);
  const onRetry = assets.retry;
  const goWorkbench = useCallback(() => {
    if (selectedAssetId) navigate(`/animation?asset=${encodeURIComponent(selectedAssetId)}`);
  }, [navigate, selectedAssetId]);

  const actionLabel = useMemo(() => {
    if (BASE_ACTION_LABEL[uiAction]) return BASE_ACTION_LABEL[uiAction];
    if (uiAction.startsWith("custom:")) {
      const item = meta.customActions.find((entry) => `custom:${entry.name}` === uiAction);
      return item?.name ?? uiAction;
    }
    return uiAction;
  }, [uiAction, meta.customActions]);

  const rigged = meta.source === "rigged";

  const statusText = !selectedAssetId
    ? "未选择试玩人物"
    : assets.metadataError
      ? "动作数据加载失败，请稍后重试"
      : `当前动作：${actionLabel}（${uiMode === "live" ? "实时控制" : "预览"}），条带 ${assets.progress.ready}/${assets.progress.total} 就绪`;

  return (
    <div className="mx-auto flex w-full max-w-[1440px] flex-col gap-4 px-4 py-5 md:px-6">
      <PageHeader
        overline="Playtest"
        title="试玩舞台"
        description="绑定当前角色原画的骨骼动作——用方向键跑起来试一试，素材好不好，跑起来才知道"
        actions={
          <>
            <Badge tone={rigged ? "primary" : "neutral"} icon="spark">
              {rigged ? `角色绑定 · ${selected?.name ?? "未选择"}` : "未选择人物"}
            </Badge>
            <Button variant="secondary" size="sm" icon="cube" onClick={() => setPickerOpen(true)}>
              更换人物
            </Button>
          </>
        }
      />

      {/* ── 验收舞台：顶栏 + 16:9 画布 ───────────────────────────── */}
      <div className="overflow-hidden rounded-xl border border-line-subtle bg-paper">
        <div className="flex flex-wrap items-center gap-2 border-b border-line-subtle px-3 py-2">
          <span className="text-[12px] font-medium text-ink">{selected?.name ?? "未选择人物"}</span>
          <Badge tone="neutral">
            {rigged ? "骨骼绑定" : (meta.source ?? "procedural") === "ai-video" ? "AI 视频" : meta.source ?? "—"}
          </Badge>
          <span className="rounded-md border border-line bg-canvas px-2 py-0.5 text-[11px] text-ink-2">
            当前动作 · {actionLabel}
          </span>
          <Badge tone={uiMode === "live" ? "neutral" : "primary"}>
            {uiMode === "live" ? "Live 实时控制" : "Preview 预览"}
          </Badge>
          <span className="ml-auto flex items-center gap-2">
            <span
              ref={fpsMeterRef}
              aria-label="舞台帧率"
              className="rounded-md border border-line bg-canvas px-2 py-1 font-mono text-[11px] text-ink-2"
            >
              — FPS
            </span>
            <Button
              variant="secondary"
              size="sm"
              icon={paused ? "play" : "pause"}
              aria-pressed={paused}
              onClick={() => setPaused((value) => !value)}
            >
              {paused ? "继续" : "暂停"}
            </Button>
            <Button
              variant="secondary"
              size="sm"
              icon="panel"
              aria-pressed={fullscreen}
              onClick={() => void toggleFullscreen()}
            >
              {fullscreen ? "退出全屏" : "全屏"}
            </Button>
          </span>
        </div>

        {/* 桌面高度守卫：常规态舞台不高于视口减去页头/顶栏/动作坞
            （≈32rem，按 1440×900 实测固定占位标定），保证主舞台与
            动作坞在 900px 高视口下零滚动可用；全屏态交给浏览器 UA
            样式铺满，不套用该上限 */}
        <div
          ref={stageRef}
          className={cx(
            "relative w-full overflow-hidden bg-stage-bg",
            fullscreen ? "h-full" : "aspect-video max-h-[calc(100dvh-32rem)]",
          )}
        >
          <PlaytestCanvas
            engine={engine}
            images={assets.images}
            strips={stripMetaByKey}
            hasAsset={Boolean(selectedAssetId)}
            loading={assets.metadataLoading}
            progress={assets.progress}
            paused={paused}
            debug={debug}
          />

          {/* Clean / Debug 切换（舞台左下） */}
          <div
            role="group"
            aria-label="舞台渲染模式"
            className="absolute bottom-3 left-3 flex rounded-lg border border-stage-line/40 bg-black/35 p-0.5 backdrop-blur-sm"
          >
            {(["clean", "debug"] as const).map((value) => (
              <button
                key={value}
                onClick={() => setDebug(value === "debug")}
                aria-pressed={value === "debug" ? debug : !debug}
                className={cx(
                  "rounded-md px-2.5 py-1 text-[11px] font-medium transition-colors",
                  (value === "debug") === debug ? "bg-stage-line/80 text-stage-bg" : "text-stage-text/80 hover:text-stage-text",
                )}
              >
                {value === "clean" ? "Clean" : "Debug"}
              </button>
            ))}
          </div>

          {/* 诊断抽屉开关（舞台右下） */}
          <button
            onClick={() => setDiagnosticsOpen((value) => !value)}
            aria-expanded={diagnosticsOpen}
            className="absolute bottom-3 right-3 flex items-center gap-1.5 rounded-lg border border-stage-line/40 bg-black/35 px-2.5 py-1.5 text-[11px] font-medium text-stage-text/90 backdrop-blur-sm hover:text-stage-text"
          >
            <Icon name="activity" className="h-3.5 w-3.5" />
            诊断抽屉
          </button>

          {diagnosticsOpen && (
            <PlaytestDiagnostics
              source={meta.source}
              character={meta.character}
              actions={meta.actions}
              strips={meta.strips}
              customActions={meta.customActions}
              phase={assets.phase}
              progress={assets.progress}
              batchTasks={batchTasks}
              onClose={() => setDiagnosticsOpen(false)}
            />
          )}
        </div>
      </div>

      {/* ── 底部动作坞 ────────────────────────────────────────────── */}
      <PlaytestActionDock
        actions={meta.actions.length > 0 ? [...meta.actions] : [...BUILT_IN_ACTIONS]}
        customActions={meta.customActions}
        strips={meta.strips}
        thumbnails={meta.previews}
        currentAction={uiAction}
        mode={uiMode}
        generatingAction={generatingAction}
        batchTasks={batchTasks}
        batchRunning={batchRunning}
        batchDoneCount={batchDoneCount}
        batchTotal={batchData?.total ?? 0}
        missingCount={assets.metadataLoading ? 0 : missingCount}
        tick={tick}
        phase={assets.phase}
        customLoading={assets.customLoading}
        libraryOpen={libraryOpen}
        assetSelected={Boolean(selectedAssetId)}
        onSelect={selectAction}
        onResumeLive={onResumeLive}
        onGenerateAi={(name) => void generateAiAnimation(name)}
        onGenerateAll={() => void generateAllActions()}
        onOpenLibrary={() => setLibraryOpen(true)}
        onRetry={onRetry}
        onGoWorkbench={goWorkbench}
      />

      {/* ── 脚注：键位 · 进度 · 状态（aria-live） ──────────────────── */}
      <div
        id="playtest-stage-help"
        className="flex flex-wrap items-center gap-x-3 gap-y-1.5 text-[11.5px] text-ink-3"
      >
        <kbd className="rounded-xs border border-line px-1.5 font-mono text-[10px]">←</kbd>
        <kbd className="rounded-xs border border-line px-1.5 font-mono text-[10px]">→</kbd>
        <kbd className="rounded-xs border border-line px-1.5 font-mono text-[10px]">A</kbd>
        <kbd className="rounded-xs border border-line px-1.5 font-mono text-[10px]">D</kbd>
        移动
        <kbd className="rounded-xs border border-line px-1.5 font-mono text-[10px]">Shift</kbd>
        奔跑
        <kbd className="rounded-xs border border-line px-1.5 font-mono text-[10px]">↑</kbd>
        <kbd className="rounded-xs border border-line px-1.5 font-mono text-[10px]">W</kbd>
        跳跃
        <kbd className="rounded-xs border border-line px-1.5 font-mono text-[10px]">空格</kbd>
        <kbd className="rounded-xs border border-line px-1.5 font-mono text-[10px]">J</kbd>
        攻击
        <span aria-live="polite" className="text-ink-2">
          {statusText}
        </span>
      </div>

      <PlaytestCharacterPicker
        open={pickerOpen}
        loading={history.isLoading}
        people={people}
        selectedId={selected?.id}
        onClose={() => setPickerOpen(false)}
        onSelect={(assetId) => {
          setSearchParams((previous) => {
            const next = new URLSearchParams(previous);
            next.set("asset", assetId);
            return next;
          });
          setPickerOpen(false);
        }}
        onGoWorkbench={() => navigate("/")}
      />
    </div>
  );
}

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
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../../api/client";
import { Badge, Button, Card, KV, PageHeader, SafeImage, Skeleton, cx } from "../../components/ui";
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

const ACTION_VIEW_BY_ACTION: Record<string, "front" | "side"> = {
  idle: "front",
  walk: "side",
  run: "side",
  attack: "front",
  jump: "side",
};

export function PlaytestContent({ selected }: { selected: CreativeAsset | null }) {
  const [, setSearchParams] = useSearchParams();
  const navigate = useNavigate();
  const selectedAssetId = selected?.id ?? null;
  const [pickerOpen, setPickerOpen] = useState(!selected);

  const history = useQuery({
    queryKey: ["playtest-people"],
    queryFn: () => api.listHistory({ kind: "character", limit: 12 }),
  });
  const people = useMemo(
    () =>
      (history.data?.records ?? []).filter(
        (record) =>
          record.asset_id &&
          !record.asset?.pve_enemy &&
          (record.image?.url || (record.asset ?? {}).image?.url),
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
  const queryClient = useQueryClient();
  const generationLockRef = useRef(false);
  const [submittingAction, setSubmittingAction] = useState<string | null>(null);
  const [batchId, setBatchId] = useState<string | null>(null);
  const batch = useQuery({
    queryKey: ["action-batch", batchId],
    queryFn: () => api.actionBatchStatus(batchId!),
    enabled: Boolean(batchId),
    // 首次快照尚未返回时也继续重试，避免网络抖动把状态永久卡在“提交中”。
    refetchInterval: (query) =>
      query.state.data?.status === "running" || !query.state.data ? 2500 : false,
  });
  const batchData = batch.data;
  const batchTasks: ActionBatchTask[] = batchData?.tasks ?? [];
  // total 只统计本轮待生成项，因此 skipped 不能计入完成数，否则进度会虚高。
  const batchDoneCount = batchTasks.filter((task) => task.status === "done").length;
  const batchRunning = batchData?.status === "running";

  const invalidateAll = assets.invalidateAll;
  const announcedBatchRef = useRef<string | null>(null);
  useEffect(() => {
    if (!batchId || !batchData || batchData.status === "running") return;
    if (announcedBatchRef.current === batchId) return;
    announcedBatchRef.current = batchId;
    invalidateAll();

    const failed = batchData.failed_count ?? 0;
    if (batchData.status === "interrupted") {
      toast({
        tone: "warning",
        title: "动作生成被中断",
        description: "后端任务已中断，可在对应动作卡片上重新生成",
      });
    } else if (failed > 0) {
      toast({
        tone: "warning",
        title: "动作生成结束，部分失败",
        description: `${failed} 个动作未生成成功，请在卡片上查看原因并重试`,
      });
    } else {
      toast({
        tone: "success",
        title: "动作生成完成",
        description: "试玩条带已自动刷新",
      });
    }
  }, [batchData, batchId, invalidateAll]);

  const missingActions = BUILT_IN_ACTIONS.filter(
    (name) => meta.strips[name]?.engine !== "ai-video",
  );
  const missingCount = missingActions.length;

  async function generateAiAnimation(name: string) {
    if (!selected?.id || generationLockRef.current || batchRunning) return;
    generationLockRef.current = true;
    setSubmittingAction(name);
    try {
      const view = ACTION_VIEW_BY_ACTION[name] ?? "front";
      const result = await api.startActionBatch(selected.id, [name], {
        view,
        viewsByAction: { [name]: view },
      });
      // API 已返回完整快照：先写入缓存，再切 batchId，首帧就能显示队列而不是空白。
      queryClient.setQueryData(["action-batch", result.batch_id], result.snapshot);
      setBatchId(result.batch_id);
      toast({
        tone: "info",
        title: `「${name}」AI 动画生成中`,
        description: "约 90 秒，完成后自动刷新预览",
      });
    } catch (cause) {
      toast({ tone: "danger", title: "AI 动画生成失败", description: String(cause).slice(0, 160) });
    } finally {
      generationLockRef.current = false;
      setSubmittingAction(null);
    }
  }

  async function generateAllActions() {
    if (!selected?.id || generationLockRef.current || batchRunning) return;
    if (missingCount === 0) {
      toast({ tone: "info", title: "全部动作都已是 AI 动画帧" });
      return;
    }
    generationLockRef.current = true;
    setSubmittingAction("batch");
    try {
      const viewsByAction = Object.fromEntries(
        missingActions.map((name) => [name, ACTION_VIEW_BY_ACTION[name] ?? "front"]),
      );
      const result = await api.startActionBatch(selected.id, missingActions, { viewsByAction });
      queryClient.setQueryData(["action-batch", result.batch_id], result.snapshot);
      setBatchId(result.batch_id);
      toast({
        tone: "info",
        title: `开始补齐 ${result.snapshot.total} 个动作`,
        description: "串行生成中（每个约 90 秒），完成后自动刷新预览",
      });
    } catch (cause) {
      toast({ tone: "danger", title: "批量启动失败", description: String(cause).slice(0, 160) });
    } finally {
      generationLockRef.current = false;
      setSubmittingAction(null);
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
  const selectPerson = useCallback(
    (assetId: string) => {
      setSearchParams((previous) => {
        const next = new URLSearchParams(previous);
        next.set("asset", assetId);
        return next;
      });
    },
    [setSearchParams],
  );

  const actionLabel = useMemo(() => {
    if (BASE_ACTION_LABEL[uiAction]) return BASE_ACTION_LABEL[uiAction];
    if (uiAction.startsWith("custom:")) {
      const item = meta.customActions.find((entry) => `custom:${entry.name}` === uiAction);
      return item?.name ?? uiAction;
    }
    return uiAction;
  }, [uiAction, meta.customActions]);

  // rigged = 分区骨骼，sprite = 整身形变；两者都是"按角色原画变形"，
  // 仅渲染方式不同，界面统一按角色动画展示
  const bound = meta.source === "rigged" || meta.source === "sprite";

  const activeBatchTask = batchTasks.find((task) => task.status === "generating");
  const generationStatus = submittingAction
    ? submittingAction === "batch"
      ? "正在创建全套动作生成队列"
      : `正在提交「${BASE_ACTION_LABEL[submittingAction] ?? submittingAction}」`
    : activeBatchTask
      ? `正在生成「${BASE_ACTION_LABEL[activeBatchTask.action] ?? activeBatchTask.action}」`
      : batchRunning
        ? `动作生成中 ${batchDoneCount}/${batchData?.total ?? 0}`
        : null;
  const aiReadyCount = assets.metadataLoading ? 0 : BUILT_IN_ACTIONS.length - missingCount;

  const statusText = !selectedAssetId
    ? "未选择试玩人物"
    : assets.metadataError
      ? "动作数据加载失败，请稍后重试"
      : `${generationStatus ? `${generationStatus} · ` : ""}当前动作：${actionLabel}（${uiMode === "live" ? "实时控制" : "预览"}），条带 ${assets.progress.ready}/${assets.progress.total} 就绪`;

  return (
    <div className="mx-auto flex w-full max-w-[1440px] flex-col gap-4 px-4 py-5 md:px-6">
      <PageHeader
        overline="Playtest"
        title="试玩舞台"
        description="绑定当前角色原画的动画——用方向键跑起来试一试，素材好不好，跑起来才知道"
        actions={
          <>
            <Badge tone={bound ? "primary" : "neutral"} icon="spark">
              {bound ? `角色动画 · ${selected?.name ?? "未选择"}` : "未选择人物"}
            </Badge>
            <Button variant="secondary" size="sm" icon="cube" onClick={() => setPickerOpen(true)}>
              更换人物
            </Button>
          </>
        }
      />

      {/* ── 主舞台 + 右侧角色/参数栏 ─────────────────────────────── */}
      <div className="grid grid-cols-12 items-start gap-4">
      <section
        aria-label="试玩舞台"
        className="col-span-12 min-w-0 overflow-hidden rounded-lg border border-line bg-paper shadow-e1 xl:col-span-9"
      >
        <div className="flex flex-wrap items-center gap-2 border-b border-line-subtle bg-surface-1/40 px-3 py-2">
          <span className="text-[12px] font-medium text-ink">{selected?.name ?? "未选择人物"}</span>
          <Badge tone="neutral">
            {bound
              ? meta.source === "sprite"
                ? "整身形变"
                : "骨骼绑定"
              : (meta.source ?? "procedural") === "ai-video"
                ? "AI 视频"
                : meta.source ?? "—"}
          </Badge>
          <span className="rounded-md border border-line bg-canvas px-2 py-0.5 text-[11px] text-ink-2">
            当前动作 · {actionLabel}
          </span>
          <Badge tone={uiMode === "live" ? "neutral" : "primary"}>
            {uiMode === "live" ? "Live 实时控制" : "Preview 预览"}
          </Badge>
          <span className="ml-auto flex items-center gap-2">
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

        </div>
      </section>

      {/* ── 右侧栏：角色候选 + 舞台参数 + 诊断 ────────────────────── */}
      <aside className="col-span-12 grid grid-cols-1 content-start gap-3 sm:grid-cols-2 xl:col-span-3 xl:grid-cols-1">
        <Card
          title="角色"
          icon="cube"
          bodyClassName="p-2.5"
          right={
            <Badge tone={bound ? "primary" : "neutral"}>{bound ? "已绑定" : "待选择"}</Badge>
          }
        >
          <div className="flex items-center gap-2 border-b border-line-subtle pb-2">
            <span className="grid h-8 w-8 shrink-0 place-items-center rounded-md border border-line bg-surface-1 text-ink-3">
              <Icon name="cube" className="h-4 w-4" />
            </span>
            <div className="min-w-0 flex-1">
              <div className="truncate text-[12px] font-semibold text-ink">
                {selected?.name ?? "未选择人物"}
              </div>
              <div className="cf-ref truncate">
                条带 {assets.progress.ready}/{assets.progress.total} · AI {aiReadyCount}/5
              </div>
            </div>
          </div>

          {history.isLoading ? (
            <div className="mt-2 grid grid-cols-3 gap-1.5">
              {Array.from({ length: 6 }, (_, index) => (
                <Skeleton key={index} className="h-[74px] rounded-md" />
              ))}
            </div>
          ) : people.length === 0 ? (
            <p className="mt-2 py-3 text-center text-[11px] text-ink-4">
              近期生成里还没有可用角色
            </p>
          ) : (
            <div className="mt-2 grid grid-cols-3 gap-1.5">
              {people.slice(0, 6).map((record) => (
                <button
                  key={record.id}
                  onClick={() => record.asset_id && selectPerson(record.asset_id)}
                  aria-pressed={selectedAssetId === record.asset_id}
                  className={cx(
                    "flex min-w-0 flex-col overflow-hidden rounded-md border bg-paper text-left transition-colors duration-(--motion-fast) ease-standard",
                    selectedAssetId === record.asset_id
                      ? "border-primary/60"
                      : "border-line-subtle hover:border-line",
                  )}
                >
                  <SafeImage
                    src={record.image?.url ?? undefined}
                    alt={String(record.name ?? record.asset_id ?? "")}
                    className="h-[52px] w-full bg-surface-1 object-contain"
                  />
                  <span className="truncate px-1 py-0.5 text-[10px] text-ink-3">
                    {record.name || record.asset_id}
                  </span>
                </button>
              ))}
            </div>
          )}

          {people.length > 6 && (
            <Button
              variant="ghost"
              size="sm"
              className="mt-1.5 w-full justify-center text-[11px]"
              onClick={() => setPickerOpen(true)}
            >
              查看全部 {people.length} 位
            </Button>
          )}
        </Card>

        <Card
          title="舞台参数"
          icon="gauge"
          bodyClassName="p-3"
          right={
            <Badge tone={uiMode === "live" ? "neutral" : "primary"}>
              {uiMode === "live" ? "Live" : "Preview"}
            </Badge>
          }
        >
          <KV label="当前动作" value={actionLabel} mono={false} />
          <KV label="渲染来源" value={meta.source ?? "—"} />
          <KV
            label="帧率"
            value={<span ref={fpsMeterRef} aria-label="舞台帧率">— FPS</span>}
          />
          <KV label="条带进度" value={`${assets.progress.ready}/${assets.progress.total}`} />

          <div
            className="mt-1 h-1.5 overflow-hidden rounded-full bg-surface-3"
            role="progressbar"
            aria-label="条带加载进度"
            aria-valuemin={0}
            aria-valuemax={100}
            aria-valuenow={assets.progress.pct}
          >
            <div
              className="h-full rounded-full bg-primary transition-[width] duration-(--motion-progress) ease-linear"
              style={{ width: `${assets.progress.pct}%` }}
            />
          </div>

          <Button
            variant="secondary"
            size="sm"
            icon="activity"
            aria-expanded={diagnosticsOpen}
            onClick={() => setDiagnosticsOpen((value) => !value)}
            className="mt-2.5 w-full justify-center"
          >
            {diagnosticsOpen ? "收起诊断信息" : "打开诊断信息"}
          </Button>
        </Card>

        {diagnosticsOpen && (
          <div className="min-w-0 sm:col-span-2 xl:col-span-1">
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
          </div>
        )}
      </aside>
      </div>

      {/* ── 底部动作坞 ────────────────────────────────────────────── */}
      <PlaytestActionDock
        actions={meta.actions.length > 0 ? [...meta.actions] : [...BUILT_IN_ACTIONS]}
        customActions={meta.customActions}
        strips={meta.strips}
        thumbnails={meta.previews}
        currentAction={uiAction}
        mode={uiMode}
        submittingAction={submittingAction}
        batchTasks={batchTasks}
        batchRunning={batchRunning}
        batchDoneCount={batchDoneCount}
        batchTotal={batchData?.total ?? 0}
        batchStartedAt={batchData?.created_at}
        batchSyncError={batch.error ? String(batch.error).slice(0, 140) : null}
        missingCount={assets.metadataLoading ? 0 : missingCount}
        aiReadyCount={aiReadyCount}
        phase={assets.phase}
        customLoading={assets.customLoading}
        libraryOpen={libraryOpen}
        assetSelected={Boolean(selectedAssetId)}
        onSelect={selectAction}
        onResumeLive={onResumeLive}
        onGenerateAi={(name) => void generateAiAnimation(name)}
        onGenerateAll={() => void generateAllActions()}
        onRefreshBatch={() => void batch.refetch()}
        onOpenLibrary={() => setLibraryOpen(true)}
        onRetry={onRetry}
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
          selectPerson(assetId);
          setPickerOpen(false);
        }}
        onGoWorkbench={() => navigate("/workspace")}
      />
    </div>
  );
}

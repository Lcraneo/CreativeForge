import { useEffect, useMemo, useRef, useState } from "react";
import { useMutation, useQueries, useQuery, useQueryClient } from "@tanstack/react-query";
import { useNavigate, useSearchParams } from "react-router-dom";
import { api } from "../api/client";
import { Icon } from "../components/icons";
import { TouchButton, TouchControlsLayer, TouchJoystick, useTouchControls } from "../components/TouchControls";
import { SelectedAssetBoundary } from "../components/SelectedAssetBoundary";
import {
  Badge,
  Button,
  Card,
  EmptyState,
  IconButton,
  PageHeader,
  SafeImage,
  Skeleton,
  cx,
} from "../components/ui";
import { PlaytestCharacterPicker } from "./playtest/PlaytestCharacterPicker";
import { preloadImage } from "../lib/preload";
import {
  PVE_DEPTH_SCALE,
  PVE_PLAYER_HP,
  PVE_ABILITIES,
  PVE_ACTION_FALLBACK,
  PVE_SLAM_MAX_Z,
  advancePveStage,
  consumePveAudioEvents,
  createPveRuntime,
  enemyHalfWidth,
  pveActionSlot,
  pveEnemyPose,
  pveGroundDistance,
  pveHud,
  pveSortByDepth,
  pveSpriteTime,
  pveStage,
  retryPveStage,
  stepPve,
  togglePvePause,
  type PveAudioEvent,
  type PveHud,
  type PveInput,
  type PveRuntime,
  type PveRuntimeEnemy,
  type PveStagePhase,
} from "../lib/pve";
import type {
  CreativeAsset,
  PlaytestPreviews,
  PlaytestStrip,
  PveCampaign,
  PveEnemyProfile,
  PveEnemySpawn,
  PveStage,
  PveStageId,
} from "../types";
import { toast } from "../stores/toastStore";

const STAGE_HEIGHT = 440;
const DEFAULT_STAGE_WIDTH = 760;
const PLAYER_HEIGHT = 168;
const HUD_INTERVAL_MS = 90;
/** 地平线以上的留白比例，给远端角色与血条留出空间。 */
const HORIZON_BAND = 0.16;
/** 地平线附近的立绘缩放，近景为 1，形成纵深。 */
const PERSPECTIVE_FAR = 0.55;

interface SpriteSet {
  image: HTMLImageElement;
  strip: PlaytestStrip;
}

interface RenderAssets {
  player: Record<string, SpriteSet | undefined>;
  enemies: Record<string, Record<string, SpriteSet | undefined>>;
  backgrounds: Record<string, HTMLImageElement | undefined>;
}

interface Projection {
  arenaWidth: number;
  arenaDepth: number;
  /** 每逻辑 x 单位的屏幕像素，横向铺满画布。 */
  scale: number;
  /** 每逻辑 y 单位的屏幕像素，纵向铺满画布并形成透视压缩。 */
  depthScale: number;
  offsetX: number;
  top: number;
  spriteScale: number;
}

export default function PveStage() {
  const [params] = useSearchParams();
  const sceneId = params.get("scene");
  return (
    <SelectedAssetBoundary>
      {(asset) => (
        <PveContent
          key={`${sceneId ?? "no-scene"}:${asset?.id ?? "unselected"}`}
          selected={asset}
        />
      )}
    </SelectedAssetBoundary>
  );
}

function PveContent({ selected }: { selected: CreativeAsset | null }) {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [searchParams, setSearchParams] = useSearchParams();
  const sceneId = searchParams.get("scene");
  const stageBoxRef = useRef<HTMLDivElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const runtimeRef = useRef<PveRuntime | null>(null);
  const heldRef = useRef(new Set<string>());
  const shotRequestRef = useRef(false);
  const audioRef = useRef<AudioContext | null>(null);
  const stageWidthRef = useRef(DEFAULT_STAGE_WIDTH);
  const [stageWidth, setStageWidth] = useState(DEFAULT_STAGE_WIDTH);
  const [pickerOpen, setPickerOpen] = useState(!selected);
  const [hud, setHud] = useState<PveHud | null>(null);
  const [assetsReady, setAssetsReady] = useState(false);
  const [reduceMotion, setReduceMotion] = useState(false);
  const touch = useTouchControls();
  const [sequenceStageId, setSequenceStageId] = useState<PveStageId | null>(null);
  const [sequenceDraft, setSequenceDraft] = useState<Record<string, string>>({});
  const [renderAssets, setRenderAssets] = useState<RenderAssets>({
    player: {},
    enemies: {},
    backgrounds: {},
  });

  const sceneQuery = useQuery({
    queryKey: ["pve-scene", sceneId],
    queryFn: ({ signal }) => api.getScene(sceneId!, { signal, silent: true }),
    enabled: Boolean(sceneId),
    retry: false,
  });
  const scene = sceneQuery.data;
  const campaign: PveCampaign | null =
    scene?.gameplay.type === "pve" ? scene.gameplay.campaign : null;
  const legacy = Boolean(
    scene?.gameplay.type === "pve" && (scene.gameplay.legacy || !scene.gameplay.campaign),
  );
  const enemyAssetIds = useMemo(
    () => [
      ...new Set(
        (campaign?.stages ?? []).flatMap((stage) =>
          stage.enemies.map((enemy) => enemy.asset_id),
        ),
      ),
    ],
    [campaign],
  );

  const history = useQuery({
    queryKey: ["pve-people"],
    queryFn: () => api.listHistory({ kind: "character", limit: 12 }),
    enabled: pickerOpen,
  });
  const enemyRoster = useQuery({
    queryKey: ["pve-enemies"],
    queryFn: () => api.listPveEnemies(),
    refetchInterval: (query) =>
      query.state.data?.enemies.some((enemy) => !["ready", "failed"].includes(enemy.status))
        ? 1800
        : false,
  });
  const readyEnemyProfiles = (enemyRoster.data?.enemies ?? []).filter(
    (enemy) => enemy.status === "ready" && enemy.asset_id,
  );
  const saveSequence = useMutation({
    mutationFn: ({ stageId, profileIds }: { stageId: PveStageId; profileIds: string[] }) =>
      api.updatePveEnemySequence(sceneId!, profileIds, stageId),
    onSuccess: (updated) => {
      queryClient.setQueryData(["pve-scene", sceneId], updated);
      void queryClient.invalidateQueries({ queryKey: ["scenes"] });
      setSequenceStageId(null);
      toast({ tone: "success", title: "敌人序列已保存", description: "该关卡已按新阵容重新载入" });
    },
    onError: (error) => {
      toast({
        tone: "danger",
        title: "敌人序列保存失败",
        description: error instanceof Error ? error.message : "请稍后重试",
      });
    },
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

  const playerPreviews = useQuery({
    queryKey: ["pve-player-previews", selected?.id],
    queryFn: () =>
      api.playtestPreviews(selected?.id, {
        actions: ["idle", "walk", "run", "jump"],
        includeCustom: false,
      }),
    enabled: Boolean(selected?.id),
  });
  const enemyPreviewQueries = useQueries({
    queries: enemyAssetIds.map((assetId) => ({
      queryKey: [
        "pve-enemy-previews",
        assetId,
        readyEnemyProfiles.find((profile) => profile.asset_id === assetId)?.updated_at,
      ],
      queryFn: () =>
        api.playtestPreviews(assetId, {
          actions: ["idle", "walk", "attack"],
          includeCustom: true,
        }),
      enabled: Boolean(assetId),
    })),
  });
  const enemyPreviewStamp = enemyPreviewQueries.map((query) => query.dataUpdatedAt).join(":");

  const backgroundUrls = useMemo(
    () => (campaign?.stages ?? []).map((stage) => stage.background_url).filter(Boolean),
    [campaign],
  );

  const storedBestTime = useMemo(() => {
    if (!sceneId) return null;
    const stored = Number(window.localStorage.getItem(`creativeforge:pve-best:${sceneId}`));
    return Number.isFinite(stored) && stored > 0 ? stored : null;
  }, [sceneId]);
  const bestTime =
    hud?.phase === "campaign_won"
      ? Math.min(storedBestTime ?? Infinity, hud.elapsed)
      : storedBestTime;

  useEffect(() => {
    if (!sceneId || hud?.phase !== "campaign_won") return;
    window.localStorage.setItem(`creativeforge:pve-best:${sceneId}`, String(bestTime));
  }, [bestTime, hud?.phase, sceneId]);

  useEffect(() => {
    const query = window.matchMedia("(prefers-reduced-motion: reduce)");
    const sync = () => setReduceMotion(query.matches);
    sync();
    query.addEventListener("change", sync);
    return () => query.removeEventListener("change", sync);
  }, []);

  useEffect(() => {
    const element = stageBoxRef.current;
    if (!element || typeof ResizeObserver === "undefined") return;
    const observer = new ResizeObserver((entries) => {
      const width = Math.round(entries[0].contentRect.width);
      if (width > 0 && width !== stageWidthRef.current) {
        stageWidthRef.current = width;
        setStageWidth(width);
      }
    });
    observer.observe(element);
    return () => observer.disconnect();
  }, []);

  useEffect(() => {
    const previewSets: Array<[string, PlaytestPreviews | undefined]> = [
      [selected?.id ?? "", playerPreviews.data],
      ...enemyAssetIds.map(
        (assetId, index) =>
          [assetId, enemyPreviewQueries[index]?.data] as [string, PlaytestPreviews | undefined],
      ),
    ];
    let cancelled = false;
    async function load() {
      const player: Record<string, SpriteSet | undefined> = {};
      const enemies: Record<string, Record<string, SpriteSet | undefined>> = {};
      await Promise.all(
        previewSets.flatMap(([assetId, payload]) => {
          if (!assetId || !payload) return [];
          const target = assetId === selected?.id ? player : (enemies[assetId] ??= {});
          return Object.entries(payload.strips ?? {}).map(async ([action, strip]) => {
            if (!strip?.url) return;
            const slot = pveActionSlot(action);
            try {
              target[slot] = { image: await preloadImage(strip.url), strip };
            } catch {
              target[slot] = undefined;
            }
          });
        }),
      );
      const loadedBackgrounds: Record<string, HTMLImageElement | undefined> = {};
      await Promise.all(
        (campaign?.stages ?? []).map(async (stage) => {
          if (!stage.background_url) return;
          try {
            loadedBackgrounds[stage.id] = await preloadImage(stage.background_url);
          } catch {
            loadedBackgrounds[stage.id] = undefined;
          }
        }),
      );
      if (cancelled) return;
      setRenderAssets({ player, enemies, backgrounds: loadedBackgrounds });
      setAssetsReady(Boolean(player.idle));
    }
    void load();
    return () => {
      cancelled = true;
    };
    // enemyPreviewStamp changes whenever a query body or error state changes.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [backgroundUrls, campaign, enemyAssetIds, enemyPreviewStamp, playerPreviews.data, selected?.id]);

  useEffect(() => {
    if (!campaign) {
      runtimeRef.current = null;
      setHud(null);
      return;
    }
    runtimeRef.current = createPveRuntime(campaign);
    setHud(pveHud(runtimeRef.current));
  }, [campaign]);

  function ensureAudio() {
    if (!audioRef.current) {
      try {
        audioRef.current = new AudioContext();
      } catch {
        audioRef.current = null;
      }
    }
    if (audioRef.current?.state === "suspended") {
      void audioRef.current.resume();
    }
  }

  function playPveSounds(events: PveAudioEvent[]) {
    const audio = audioRef.current;
    if (!audio || events.length === 0) return;
    for (const event of events) {
      const oscillator = audio.createOscillator();
      const gain = audio.createGain();
      const now = audio.currentTime;
      const config: Record<PveAudioEvent, [OscillatorType, number, number, number]> = {
        shot: ["triangle", 620, 380, 0.07],
        hit: ["square", 230, 70, 0.09],
        hurt: ["sawtooth", 150, 55, 0.16],
        guard: ["sine", 760, 1180, 0.14],
        clear: ["sine", 440, 880, 0.2],
        win: ["triangle", 520, 1040, 0.32],
        lose: ["sawtooth", 210, 58, 0.36],
      };
      const [type, from, to, duration] = config[event];
      oscillator.type = type;
      oscillator.frequency.setValueAtTime(from, now);
      oscillator.frequency.exponentialRampToValueAtTime(Math.max(1, to), now + duration);
      gain.gain.setValueAtTime(0.035, now);
      gain.gain.exponentialRampToValueAtTime(0.0001, now + duration);
      oscillator.connect(gain).connect(audio.destination);
      oscillator.start(now);
      oscillator.stop(now + duration);
    }
  }

  useEffect(() => {
    if (!campaign || !selected || !assetsReady) return;
    const canvas = canvasRef.current;
    if (!canvas) return;
    let frame = 0;
    let lastTick = 0;
    let lastHud = 0;
    const context = canvas.getContext("2d");
    if (!context) return;

    const loop = (time: number) => {
      frame = requestAnimationFrame(loop);
      const runtime = runtimeRef.current;
      if (!runtime) return;
      const dt = lastTick ? Math.min(0.05, (time - lastTick) / 1000) : 1 / 60;
      lastTick = time;
      const keys = heldRef.current;
      stepPve(runtime, readInput(keys, shotRequestRef.current), dt);
      if (runtime.phase !== "playing" || !runtime.paused) shotRequestRef.current = false;
      playPveSounds(consumePveAudioEvents(runtime));
      drawPveScene(context, canvas, campaign, runtime, renderAssets, reduceMotion, scene?.theme.palette);
      if (time - lastHud >= HUD_INTERVAL_MS) {
        lastHud = time;
        setHud(pveHud(runtime));
      }
    };
    frame = requestAnimationFrame(loop);
    return () => cancelAnimationFrame(frame);
  }, [assetsReady, campaign, reduceMotion, renderAssets, scene?.theme.palette, selected]);

  useEffect(() => {
    const onDown = (event: KeyboardEvent) => {
      const target = event.target;
      if (
        target instanceof HTMLElement &&
        (target.isContentEditable || ["INPUT", "TEXTAREA", "SELECT"].includes(target.tagName))
      ) {
        return;
      }
      const key = event.key.toLowerCase();
      ensureAudio();
      if (
        ["arrowleft", "arrowright", "arrowup", "arrowdown", " ", "f", "j", "k", "l", "p", "escape", "enter"].includes(
          key,
        )
      ) {
        event.preventDefault();
      }
      const runtime = runtimeRef.current;
      if (runtime && !event.repeat) {
        if (key === "p" || key === "escape") {
          togglePvePause(runtime);
          setHud(pveHud(runtime));
          return;
        }
        if (key === "enter" && runtime.phase === "cleared") {
          advancePveStage(runtime);
          setHud(pveHud(runtime));
          return;
        }
        if (key === "r" && runtime.phase === "campaign_lost") {
          retryPveStage(runtime);
          setHud(pveHud(runtime));
          return;
        }
      }
      heldRef.current.add(key);
      if (!event.repeat && (key === "f" || key === "j") && !runtime?.paused) {
        shotRequestRef.current = true;
      }
    };
    const onUp = (event: KeyboardEvent) => {
      heldRef.current.delete(event.key.toLowerCase());
    };
    const clear = () => {
      heldRef.current.clear();
      shotRequestRef.current = false;
    };
    window.addEventListener("keydown", onDown);
    window.addEventListener("keyup", onUp);
    window.addEventListener("blur", clear);
    return () => {
      window.removeEventListener("keydown", onDown);
      window.removeEventListener("keyup", onUp);
      window.removeEventListener("blur", clear);
    };
  }, []);

  function startSequenceEditing(stage: PveStage) {
    setSequenceDraft(
      Object.fromEntries(
        stage.enemies.map((enemy) => [enemy.id, matchingProfileId(enemy, readyEnemyProfiles)]),
      ),
    );
    setSequenceStageId(stage.id);
  }

  function saveEnemySequence(stage: PveStage) {
    const profileIds: string[] = [];
    for (const enemy of stage.enemies) {
      const profileId = sequenceDraft[enemy.id];
      if (!profileId) {
        toast({ tone: "warning", title: "请为每个敌人槽位选择可用敌人" });
        return;
      }
      profileIds.push(profileId);
    }
    saveSequence.mutate({ stageId: stage.id, profileIds });
  }

  function restartCampaign() {
    if (!campaign) return;
    runtimeRef.current = createPveRuntime(campaign);
    shotRequestRef.current = false;
    setHud(pveHud(runtimeRef.current));
  }

  function advanceStage() {
    const runtime = runtimeRef.current;
    if (!runtime) return;
    advancePveStage(runtime);
    setHud(pveHud(runtime));
  }

  function retryStage() {
    const runtime = runtimeRef.current;
    if (!runtime) return;
    retryPveStage(runtime);
    setHud(pveHud(runtime));
  }

  function selectAsset(assetId: string) {
    const next = new URLSearchParams(searchParams);
    next.set("asset", assetId);
    setSearchParams(next);
    setPickerOpen(false);
  }

  function shoot() {
    ensureAudio();
    if (!runtimeRef.current?.paused) shotRequestRef.current = true;
  }

  // 触控与键盘共用同一按键集合（heldRef），不额外维护一套输入状态
  function holdKey(key: string, pressed: boolean) {
    if (pressed) heldRef.current.add(key);
    else heldRef.current.delete(key);
  }

  function togglePause() {
    const runtime = runtimeRef.current;
    if (!runtime) return;
    togglePvePause(runtime);
    setHud(pveHud(runtime));
  }

  if (!sceneId) {
    return (
      <div className="mx-auto w-full max-w-[1440px] px-4 py-5 md:px-6">
        <PageHeader
          overline="PVE Arcade"
          title="PVE 关卡试玩"
          description="从场景工坊选择 PVE 模式生成三关战役，再选择角色进入竞技场。"
        />
        <div className="mt-5">
          <Card>
            <EmptyState
              icon="zap"
              title="还没有选择 PVE 场景"
              description="先在工作坊里描述敌人与战场主题，生成后会直接进入三关 2.5D 战役。"
              action={
                <Button variant="primary" icon="grid" onClick={() => navigate("/scenes")}>
                  去场景工坊
                </Button>
              }
            />
          </Card>
        </div>
      </div>
    );
  }

  if (sceneQuery.isLoading) {
    return (
      <div className="mx-auto w-full max-w-[1440px] px-4 py-5 md:px-6">
        <Skeleton className="h-9 w-56 rounded-md" />
        <Skeleton className="mt-4 aspect-[16/9] w-full rounded-xl" />
      </div>
    );
  }

  if (sceneQuery.isError || !scene || scene.gameplay.type !== "pve") {
    return (
      <div className="mx-auto w-full max-w-[1440px] px-4 py-5 md:px-6">
        <Card title="PVE 场景" icon="alert" bodyClassName="p-4">
          <EmptyState
            icon="alert"
            title="无法进入这场 PVE"
            description={
              scene?.gameplay.type === "parkour"
                ? "该场景是跑酷关卡，请从场景工坊选择 PVE 模式重新生成。"
                : sceneQuery.error instanceof Error
                  ? sceneQuery.error.message
                  : "场景不存在或尚未生成完成。"
            }
            action={
              <Button variant="secondary" icon="grid" onClick={() => navigate("/scenes")}>
                返回场景工坊
              </Button>
            }
          />
        </Card>
      </div>
    );
  }

  if (legacy || !campaign) {
    return (
      <div className="mx-auto w-full max-w-[1440px] px-4 py-5 md:px-6">
        <PageHeader overline="PVE Arcade" title={scene.title} description={scene.theme.summary} />
        <Card title="旧版 PVE 场景" icon="alert" bodyClassName="p-4" className="mt-5">
          <EmptyState
            icon="alert"
            title="旧版 PVE，需重新生成"
            description="该场景使用旧的横版单关卡数据，无法进入新版 2.5D 三关战役。请在场景工坊用相同提示词重新生成。"
            action={
              <Button variant="primary" icon="grid" onClick={() => navigate("/scenes")}>
                返回场景工坊
              </Button>
            }
          />
        </Card>
      </div>
    );
  }

  const playerLoadFailed =
    playerPreviews.isError ||
    (!playerPreviews.isLoading &&
      Boolean(playerPreviews.data) &&
      !playerPreviews.data?.strips?.idle);
  const loading = !selected || playerPreviews.isLoading || !assetsReady;

  return (
    <div className="mx-auto flex w-full max-w-[1440px] flex-col gap-5 px-4 py-5 md:px-6">
      <PageHeader
        overline="PVE Arcade"
        title={scene.title}
        description={`${scene.theme.summary} · 2.5D 固定竞技场，三关连续推进，第三关挑战守关 Boss。`}
        actions={
          <>
            <Badge tone="success" icon="zap">
              PVE · {difficultyLabel(scene.gameplay.difficulty)}
            </Badge>
            <Badge tone={selected ? "primary" : "neutral"} icon="cube">
              {selected ? `出战角色 · ${selected.name || selected.id}` : "未选择人物"}
            </Badge>
          </>
        }
      />

      <div className="grid grid-cols-12 items-start gap-4">
        <div className="col-span-12 flex min-w-0 flex-col gap-3 lg:col-span-8">
          <Card
            title="PVE 战斗 · 2.5D 竞技场"
            icon="play"
            bodyClassName="p-3"
            right={
              <div className="flex items-center gap-1.5">
                <Badge tone="neutral">
                  第 {hud?.stageIndex ?? 1}/{hud?.stageCount ?? 3} 关
                </Badge>
                <button
                  type="button"
                  aria-label={hud?.paused ? "继续游戏" : "暂停游戏"}
                  onClick={togglePause}
                  className="grid h-7 w-7 place-items-center rounded-full border border-line bg-paper text-ink-2 hover:bg-surface-1 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary pointer-coarse:h-11 pointer-coarse:w-11"
                >
                  <Icon name={hud?.paused ? "play" : "pause"} className="h-3.5 w-3.5" />
                </button>
              </div>
            }
          >
            <div
              ref={stageBoxRef}
              className="relative overflow-hidden rounded-xl border border-line-subtle bg-surface-1"
            >
              <canvas
                ref={canvasRef}
                width={stageWidth}
                height={STAGE_HEIGHT}
                role="img"
                aria-label="PVE 2.5D 竞技场战斗画面"
                className="block h-auto w-full touch-none"
                onPointerDown={() => {
                  if (assetsReady) shoot();
                }}
              />

              {/* 触屏设备：八向摇杆 + 射击/跳跃/防御/闪避 */}
              {touch && assetsReady && (
                <TouchControlsLayer
                  joystick={
                    <TouchJoystick
                      onDirection={(direction, pressed) => holdKey(`arrow${direction}`, pressed)}
                    />
                  }
                >
                  <TouchButton label="射" tone="primary" onPress={shoot} />
                  <TouchButton
                    label="跳"
                    onPress={() => holdKey(" ", true)}
                    onRelease={() => holdKey(" ", false)}
                  />
                  <TouchButton
                    label="防"
                    onPress={() => holdKey("k", true)}
                    onRelease={() => holdKey("k", false)}
                  />
                  <TouchButton
                    label="闪"
                    onPress={() => holdKey("l", true)}
                    onRelease={() => holdKey("l", false)}
                  />
                </TouchControlsLayer>
              )}

              {hud && (
                <div className="pointer-events-none absolute left-3 top-3 z-[5] flex flex-wrap gap-1.5">
                  <HudChip icon="shield" text={`${hud.hp}/${PVE_PLAYER_HP}`} danger={hud.hp <= 2} />
                  <HudChip icon="crosshair" text={`敌人 ${hud.kills}/${hud.stageTotal}`} />
                  <HudChip icon="clock" text={`总 ${hud.elapsed.toFixed(1)}s`} />
                  <HudChip
                    icon="shield"
                    text={
                      hud.guardAvailable ? "单格防御就绪" : `防御 ${hud.guardCooldown.toFixed(1)}s`
                    }
                    danger={!hud.guardAvailable}
                  />
                </div>
              )}

              {hud && (
                <div className="pointer-events-none absolute left-1/2 top-12 z-[5] -translate-x-1/2 text-center">
                  <div className="rounded-full border border-line/60 bg-paper/90 px-3 py-1 text-[10.5px] font-medium text-ink-2 shadow-sm backdrop-blur-sm">
                    {hud.stageTitle}
                    {hud.stageRemaining > 0 ? ` · 剩余 ${hud.stageRemaining}` : ""}
                  </div>
                  {hud.notice && (
                    <div className="mt-1 text-[10px] font-semibold text-warning drop-shadow-sm">
                      {hud.notice}
                    </div>
                  )}
                  {hud.bossActive && (
                    <div className="mt-2 w-[min(360px,58vw)]">
                      <div className="mb-1 flex justify-between text-[9.5px] text-paper/90 drop-shadow">
                        <span>守关 Boss</span>
                        <span className="font-mono">
                          {hud.bossHp}/{hud.bossMaxHp}
                        </span>
                      </div>
                      <div className="h-2 overflow-hidden rounded-full border border-paper/35 bg-ink/45">
                        <div
                          className="h-full rounded-full bg-[linear-gradient(90deg,#8feaff,#dffaff)] transition-[width] duration-(--motion-fast)"
                          style={{
                            width: `${Math.max(
                              0,
                              (hud.bossHp / Math.max(1, hud.bossMaxHp)) * 100,
                            )}%`,
                          }}
                        />
                      </div>
                    </div>
                  )}
                </div>
              )}

              {playerLoadFailed ? (
                <div className="absolute inset-0 z-20 grid place-items-center bg-surface-1/[.92] backdrop-blur-[2px]">
                  <EmptyState
                    icon="alert"
                    title="角色动作载入失败"
                    description="无法读取待机动作条带，请重新载入后再进入 PVE。"
                    action={
                      <Button
                        variant="secondary"
                        size="sm"
                        icon="refresh"
                        onClick={() => void playerPreviews.refetch()}
                      >
                        重新载入
                      </Button>
                    }
                  />
                </div>
              ) : loading ? (
                <div className="absolute inset-0 z-20 grid place-items-center bg-surface-1/[.92] backdrop-blur-[2px]">
                  {!selected ? (
                    <EmptyState
                      icon="cube"
                      title="选择出战角色"
                      description="沿用角色的待机、行走、奔跑与跳跃动作，不要求攻击动画。"
                      action={
                        <Button
                          variant="primary"
                          size="sm"
                          icon="cube"
                          onClick={() => setPickerOpen(true)}
                        >
                          打开人物挑选
                        </Button>
                      }
                    />
                  ) : (
                    <div className="flex items-center gap-2 text-[12px] text-ink-3">
                      <Icon name="clock" className="h-4 w-4" />
                      正在准备出战角色，敌人动作将在后台继续加载…
                    </div>
                  )}
                </div>
              ) : null}

              {hud?.paused && hud.phase === "playing" && (
                <div className="absolute inset-0 z-30 grid place-items-center bg-canvas/88 p-4 backdrop-blur-[2px]">
                  <div className="w-[min(340px,88%)] rounded-xl border border-line bg-paper p-5 text-center shadow-e3">
                    <span className="mx-auto grid h-11 w-11 place-items-center rounded-full bg-primary/12 text-primary">
                      <Icon name="pause" className="h-5 w-5" />
                    </span>
                    <h3 className="mt-3 font-serif text-[20px] font-black text-ink">战斗暂停</h3>
                    <p className="mt-1 text-[11.5px] leading-5 text-ink-3">
                      当前关卡：{hud.stageTitle}
                    </p>
                    <div className="mt-4 flex justify-center gap-2">
                      <Button variant="primary" size="sm" icon="play" onClick={togglePause}>
                        继续游戏
                      </Button>
                      <Button variant="secondary" size="sm" icon="refresh" onClick={restartCampaign}>
                        重新开始战役
                      </Button>
                    </div>
                  </div>
                </div>
              )}

              {hud?.phase === "cleared" && (
                <StageClearedOverlay
                  stageTitle={hud.stageTitle}
                  stageIndex={hud.stageIndex}
                  stageCount={hud.stageCount}
                  kills={hud.kills}
                  total={hud.stageTotal}
                  elapsed={hud.elapsed}
                  hp={hud.hp}
                  onAdvance={advanceStage}
                  onRestart={restartCampaign}
                  onBack={() => navigate("/scenes")}
                />
              )}
              {hud?.phase === "campaign_won" && (
                <ResultOverlay
                  won
                  title={`${hud.grade} 级 · 战役通关`}
                  detail={`三关全部完成 · ${hud.elapsed.toFixed(1)}s · 受伤 ${hud.damageTaken} · 防御 ${hud.guardsUsed} · 命中率 ${Math.round(hud.accuracy * 100)}%${bestTime ? ` · 最佳 ${bestTime.toFixed(1)}s` : ""}`}
                  onRestart={restartCampaign}
                  onBack={() => navigate("/scenes")}
                />
              )}
              {hud?.phase === "campaign_lost" && (
                <ResultOverlay
                  won={false}
                  title={`第 ${hud.stageIndex} 关失败`}
                  detail={`已清除 ${hud.kills}/${hud.stageTotal} 个敌人 · 重试本关会恢复到进入该关时的生命与统计`}
                  onRestart={retryStage}
                  restartLabel={`重试第 ${hud.stageIndex} 关`}
                  onBack={() => navigate("/scenes")}
                />
              )}
            </div>
          </Card>

          <section className="rounded-lg border border-line bg-paper px-3.5 py-3 shadow-e1">
            <div className="flex flex-wrap items-center gap-2">
              <Button variant="primary" size="sm" icon="refresh" onClick={restartCampaign}>
                重新开始战役
              </Button>
              <Button variant="secondary" size="sm" icon="cube" onClick={() => setPickerOpen(true)}>
                更换出战角色
              </Button>
              <span className="text-[11px] text-ink-4 pointer-coarse:hidden">
                WASD / 方向键八向移动 · Shift 奔跑 · 空格跳跃 · F / J 单发攻击 · Q / E 上下瞄准 · K 防御 · L 闪避 · P 暂停 · Enter 进入下一关
              </span>
              <span className="hidden text-[11px] text-ink-4 pointer-coarse:inline">
                触屏操作：左下摇杆移动，右下按钮射击 / 跳跃 / 防御 / 闪避
              </span>
              <span className="hidden text-[11px] text-ink-3 pointer-coarse:block landscape:hidden">
                竖屏舞台偏窄，横屏游玩视野更宽
              </span>
            </div>
            <div className="mt-3 grid gap-2 sm:grid-cols-3">
              <RuleItem
                icon="crosshair"
                title="2.5D 地面战斗"
                text="x 水平、y 纵深、z 跳跃高度；地面距离按纵深压缩计算，跳跃可以躲过低矮震击。"
              />
              <RuleItem
                icon="shield"
                title="单格防御"
                text="按住 K 可抵挡一次伤害；防御碎裂后冷却 2 秒，HUD 会显示恢复进度。"
              />
              <RuleItem
                icon="flame"
                title="手动推进三关"
                text="清场后战斗冻结并显示结算；只有点击“进入下一关”或按 Enter 才会加载下一关。"
              />
            </div>
          </section>
        </div>

        <aside className="col-span-12 flex flex-col gap-3 lg:col-span-4">
          <CampaignSequenceCard
            stages={campaign.stages}
            profiles={readyEnemyProfiles}
            editingStageId={sequenceStageId}
            draft={sequenceDraft}
            saving={saveSequence.isPending}
            error={saveSequence.error instanceof Error ? saveSequence.error.message : null}
            onStart={startSequenceEditing}
            onCancel={() => setSequenceStageId(null)}
            onChange={(enemyId, profileId) =>
              setSequenceDraft((current) => ({ ...current, [enemyId]: profileId }))
            }
            onSave={saveEnemySequence}
          />

          <Card title="战斗说明" icon="info" bodyClassName="p-4">
            <p className="text-[11.5px] leading-5 text-ink-3">
              三关战役使用固定斜俯视竞技场：第 1、2 关清剿小怪，第 3 关挑战守关 Boss。
              生命、受伤、命中与累计用时跨关保留；切换关卡会重置站位、弹幕与技能冷却。
            </p>
            {scene.generation.warnings.length > 0 && (
              <p className="mt-2 text-[10.5px] leading-4 text-warning">
                {scene.generation.warnings.join("；")}
              </p>
            )}
          </Card>

          <PveEnemyForge
            profiles={enemyRoster.data?.enemies ?? []}
            loading={enemyRoster.isLoading}
            difficulty={scene.gameplay.difficulty}
            onRefresh={() => void enemyRoster.refetch()}
          />
        </aside>
      </div>

      <PlaytestCharacterPicker
        open={pickerOpen}
        loading={history.isLoading}
        people={people}
        selectedId={selected?.id}
        onClose={() => setPickerOpen(false)}
        onSelect={selectAsset}
        onGoWorkbench={() => navigate("/workspace")}
      />
    </div>
  );
}

/** 八向移动 + 跳跃 + 攻击/防御/闪避的统一输入映射。 */
function readInput(keys: Set<string>, shot: boolean): PveInput {
  return {
    left: keys.has("arrowleft") || keys.has("a"),
    right: keys.has("arrowright") || keys.has("d"),
    up: keys.has("arrowup") || keys.has("w"),
    down: keys.has("arrowdown") || keys.has("s"),
    run: keys.has("shift"),
    jump: keys.has(" "),
    shoot: shot,
    guard: keys.has("k"),
    dodge: keys.has("l"),
    aimZ: keys.has("q") ? -0.7 : keys.has("e") ? 0.7 : 0,
  };
}

function makeProjection(arena: { width: number; depth: number }, width: number, height: number): Projection {
  const top = Math.round(height * HORIZON_BAND);
  return {
    arenaWidth: arena.width,
    arenaDepth: arena.depth,
    scale: width / arena.width,
    depthScale: (height - top) / arena.depth,
    offsetX: 0,
    top,
    spriteScale: Math.max(0.55, Math.min(1.15, width / 860)),
  };
}

/** 越靠地平线（y 小）立绘越小，越靠近镜头越大，形成 2.5D 纵深。 */
function depthPerspective(projection: Projection, y: number) {
  const t = Math.min(1, Math.max(0, y / projection.arenaDepth));
  return PERSPECTIVE_FAR + (1 - PERSPECTIVE_FAR) * t;
}

/** 立绘不能高过脚底到画布顶部的可用空间，避免远端角色被裁切。 */
function actorHeight(natural: number, feetY: number) {
  return Math.max(24, Math.min(natural, feetY - 2));
}

/** y 越大越靠近镜头，屏幕 y 越大；与升序深度排序一致。 */
function projectGround(projection: Projection, x: number, y: number) {
  return {
    x: projection.offsetX + x * projection.scale,
    y: projection.top + y * projection.depthScale,
  };
}

function projectPoint(projection: Projection, x: number, y: number, z: number) {
  const ground = projectGround(projection, x, y);
  return { x: ground.x, y: ground.y - z * projection.depthScale };
}

function drawPveScene(
  context: CanvasRenderingContext2D,
  canvas: HTMLCanvasElement,
  campaign: PveCampaign,
  runtime: PveRuntime,
  assets: RenderAssets,
  reduceMotion: boolean,
  palette: { skyTop?: string; skyBottom?: string; ground?: string; accent?: string } | undefined,
) {
  const width = canvas.width;
  const height = canvas.height;
  const stage = pveStage(campaign, runtime.stageIndex);
  const projection = makeProjection(stage.arena, width, height);
  context.clearRect(0, 0, width, height);
  drawBackground(context, width, height, assets.backgrounds[stage.id], palette);

  for (const enemy of runtime.enemies) {
    if (enemy.hp > 0 || (enemy.deathAt !== null && runtime.stageTime - enemy.deathAt < PVE_DEATH_VISIBLE)) {
      drawTelegraph(context, enemy, runtime, projection);
    }
  }

  const actors = pveSortByDepth([
    ...runtime.enemies
      .filter(
        (enemy) =>
          enemy.hp > 0 ||
          (enemy.deathAt !== null && runtime.stageTime - enemy.deathAt < PVE_DEATH_VISIBLE),
      )
      .map((enemy) => ({ y: enemy.y, enemy })),
    { y: runtime.player.y, enemy: null as PveRuntimeEnemy | null },
  ]);
  for (const actor of actors) {
    if (actor.enemy) {
      drawEnemy(context, actor.enemy, runtime, assets.enemies[actor.enemy.asset_id], projection);
    } else {
      drawPlayer(context, runtime, assets.player, projection);
    }
  }

  for (const particle of runtime.particles) {
    const point = projectPoint(projection, particle.x, particle.y, particle.z);
    context.save();
    context.globalAlpha = Math.max(0, particle.life / 0.35);
    context.fillStyle = particle.color;
    context.beginPath();
    context.arc(point.x, point.y, particle.size, 0, Math.PI * 2);
    context.fill();
    context.restore();
  }
  for (const projectile of runtime.projectiles) {
    const point = projectPoint(projection, projectile.x, projectile.y, projectile.z);
    context.save();
    context.shadowColor = projectile.color;
    context.shadowBlur = 14;
    context.strokeStyle = projectile.color;
    context.globalAlpha = 0.35;
    context.lineWidth = Math.max(2, projectile.radius * 0.8);
    context.beginPath();
    context.moveTo(
      point.x - projectile.vx * 0.045 * projection.scale,
      point.y + projectile.vz * 0.045 * projection.depthScale,
    );
    context.lineTo(point.x, point.y);
    context.stroke();
    context.globalAlpha = 1;
    context.fillStyle = projectile.color;
    context.beginPath();
    context.arc(point.x, point.y, Math.max(2, projectile.radius * 0.8), 0, Math.PI * 2);
    context.fill();
    context.restore();
  }

  if (!reduceMotion && runtime.noticeUntil > runtime.stageTime) {
    const strength = Math.min(1, runtime.noticeUntil - runtime.stageTime);
    context.save();
    context.fillStyle = `rgba(13, 20, 33, ${0.16 * strength})`;
    context.fillRect(0, 0, width, height);
    context.restore();
  }
}

const PVE_DEATH_VISIBLE = 0.9;

function drawBackground(
  context: CanvasRenderingContext2D,
  width: number,
  height: number,
  image: HTMLImageElement | undefined,
  palette: { skyTop?: string; skyBottom?: string } | undefined,
) {
  if (image) {
    const scale = Math.max(width / image.naturalWidth, height / image.naturalHeight);
    const drawWidth = image.naturalWidth * scale;
    const drawHeight = image.naturalHeight * scale;
    context.drawImage(image, (width - drawWidth) / 2, (height - drawHeight) / 2, drawWidth, drawHeight);
    return;
  }
  const gradient = context.createLinearGradient(0, 0, 0, height);
  gradient.addColorStop(0, palette?.skyTop ?? "#25345a");
  gradient.addColorStop(1, palette?.skyBottom ?? "#dce6ef");
  context.fillStyle = gradient;
  context.fillRect(0, 0, width, height);
}

function drawTelegraph(
  context: CanvasRenderingContext2D,
  enemy: PveRuntimeEnemy,
  runtime: PveRuntime,
  projection: Projection,
) {
  if (!enemy.ability || enemy.abilityStage !== "windup") return;
  const ability = enemy.ability;
  const config = PVE_ABILITIES[ability];
  const base = projectGround(projection, enemy.x, enemy.y);
  context.save();
  context.globalAlpha = 0.3 + Math.sin(runtime.stageTime * 8) * 0.08;
  context.strokeStyle = "#fff1b6";
  context.fillStyle = "rgba(255, 130, 65, .35)";
  context.lineWidth = 2.5;
  context.setLineDash([7, 5]);
  if (ability === "slam") {
    const radius = config.range * projection.scale;
    context.beginPath();
    context.ellipse(base.x, base.y, radius, config.range * projection.depthScale, 0, 0, Math.PI * 2);
    context.fill();
    context.stroke();
    context.setLineDash([]);
    context.fillStyle = "rgba(255, 245, 210, .92)";
    context.font = "bold 11px sans-serif";
    context.textAlign = "center";
    context.fillText("震地 · 跳跃躲避", base.x, base.y - 6);
  } else if (ability === "shot") {
    const target = projectGround(projection, enemy.abilityTargetX, enemy.abilityTargetY);
    context.beginPath();
    context.moveTo(base.x, base.y);
    context.lineTo(target.x, target.y);
    context.stroke();
    context.setLineDash([]);
    context.beginPath();
    context.ellipse(
      target.x,
      target.y,
      12,
      12 * (projection.depthScale / projection.scale),
      0,
      0,
      Math.PI * 2,
    );
    context.fill();
    context.stroke();
  } else {
    const distance = ability === "charge" ? 420 * config.active : 260 * config.active;
    const endX = enemy.x + enemy.abilityDirectionX * distance;
    const endY = enemy.y + (enemy.abilityDirectionY * distance) / PVE_DEPTH_SCALE;
    const end = projectGround(projection, endX, endY);
    const half = enemy.radiusX * projection.scale;
    const normalX = -enemy.abilityDirectionY * half;
    const normalY = enemy.abilityDirectionX * half * (projection.depthScale / projection.scale);
    context.beginPath();
    context.moveTo(base.x + normalX, base.y + normalY);
    context.lineTo(end.x + normalX, end.y + normalY);
    context.lineTo(end.x - normalX, end.y - normalY);
    context.lineTo(base.x - normalX, base.y - normalY);
    context.closePath();
    context.fill();
    context.stroke();
    context.setLineDash([]);
    context.fillStyle = "rgba(255, 245, 210, .92)";
    context.font = "bold 11px sans-serif";
    context.textAlign = "center";
    context.fillText("冲刺！", base.x, base.y - 6);
  }
  context.restore();
}

function drawShadow(
  context: CanvasRenderingContext2D,
  projection: Projection,
  x: number,
  y: number,
  z: number,
  radius: number,
) {
  const ground = projectGround(projection, x, y);
  const shrink = Math.max(0.45, 1 - z / 320);
  const radiusPx = radius * projection.spriteScale * depthPerspective(projection, y) * shrink;
  context.save();
  context.fillStyle = "rgba(9, 14, 24, .28)";
  context.beginPath();
  context.ellipse(
    ground.x,
    ground.y + 2,
    radiusPx,
    radiusPx * 0.32,
    0,
    0,
    Math.PI * 2,
  );
  context.fill();
  context.restore();
}

function drawPlayer(
  context: CanvasRenderingContext2D,
  runtime: PveRuntime,
  sprites: Record<string, SpriteSet | undefined>,
  projection: Projection,
) {
  const player = runtime.player;
  drawShadow(context, projection, player.x, player.y, player.z, 34);
  const speed = Math.hypot(player.vx, player.vy);
  const action = !player.onGround
    ? "jump"
    : speed > 220
      ? "run"
      : speed > 1
        ? "walk"
        : "idle";
  const sprite = sprites[action] ?? sprites.idle ?? sprites.walk;
  const point = projectPoint(projection, player.x, player.y, player.z);
  const natural = PLAYER_HEIGHT * projection.spriteScale * depthPerspective(projection, player.y);
  const height = actorHeight(natural, point.y);
  if (sprite) {
    if (runtime.invulnerableUntil > runtime.stageTime && Math.floor(runtime.stageTime * 14) % 2 === 0) {
      context.globalAlpha = 0.45;
    }
    drawSprite(context, sprite, point.x, point.y, height, player.facing, runtime.stageTime);
    context.globalAlpha = 1;
  } else {
    drawFallbackActor(context, point.x, point.y, height * 0.24, height, "#e2b759");
  }
  if (runtime.guarding && runtime.guardAvailable) {
    context.save();
    context.strokeStyle = "#9edff2";
    context.lineWidth = 3;
    context.globalAlpha = 0.75;
    context.beginPath();
    context.ellipse(point.x, point.y - height * 0.5, height * 0.3, height * 0.52, 0, -Math.PI / 2, Math.PI / 2);
    context.stroke();
    context.restore();
  }
}

function drawEnemy(
  context: CanvasRenderingContext2D,
  enemy: PveRuntimeEnemy,
  runtime: PveRuntime,
  sprites: Record<string, SpriteSet | undefined> | undefined,
  projection: Projection,
) {
  const pose = pveEnemyPose(enemy, runtime.stageTime);
  const sprite = sprites?.[pose] ?? sprites?.[PVE_ACTION_FALLBACK[pose]] ?? sprites?.walk ?? sprites?.idle;
  const point = projectPoint(projection, enemy.x, enemy.y, 0);
  const natural =
    enemy.display_height * projection.spriteScale * depthPerspective(projection, enemy.y);
  const height = actorHeight(natural, point.y);
  drawShadow(context, projection, enemy.x, enemy.y, 0, enemy.kind === "boss" ? 56 : 24);
  context.save();
  context.translate(point.x, point.y);
  if (pose === "windup") context.scale(1.12, 0.88);
  if (pose === "hurt") context.rotate(-enemy.facing * 0.16);
  if (pose === "death") {
    const progress = Math.min(1, (runtime.stageTime - (enemy.deathAt ?? runtime.stageTime)) / 0.6);
    context.rotate(enemy.facing * (0.3 + progress * 1.2));
    context.scale(1, Math.max(0.12, 1 - progress));
  }
  context.translate(-point.x, -point.y);
  if (sprite) {
    drawSprite(
      context,
      sprite,
      point.x,
      point.y,
      height,
      enemy.facing,
      pveSpriteTime(pose, enemy, runtime.stageTime, sprite.strip.frames, sprite.strip.fps ?? 10),
    );
  } else {
    drawFallbackActor(
      context,
      point.x,
      point.y,
      height * (enemy.kind === "boss" ? 0.28 : 0.24),
      height,
      enemy.kind === "boss" ? "#6ccde5" : "#7fa25e",
    );
  }
  if (enemy.hitFlashUntil > runtime.stageTime) {
    if (sprite) {
      context.save();
      context.filter = "brightness(3.2) saturate(.15)";
      drawSprite(
        context,
        sprite,
        point.x,
        point.y,
        height,
        enemy.facing,
        pveSpriteTime(pose, enemy, runtime.stageTime, sprite.strip.frames, sprite.strip.fps ?? 10),
      );
      context.restore();
    } else {
      context.save();
      context.globalCompositeOperation = "screen";
      context.globalAlpha = 0.5;
      context.fillStyle = "#fff5e3";
      context.fillRect(
        point.x - enemyHalfWidth(enemy) * projection.scale,
        point.y - height,
        enemyHalfWidth(enemy) * 2 * projection.scale,
        height,
      );
      context.restore();
    }
  }
  context.restore();
  if (pose === "death") return;
  const barWidth = (enemy.kind === "boss" ? 150 : 48) * projection.spriteScale;
  const barY = Math.max(6, point.y - height - 12);
  context.save();
  context.fillStyle = "rgba(21, 30, 47, .78)";
  context.fillRect(point.x - barWidth / 2, barY, barWidth, 5);
  context.fillStyle = enemy.kind === "boss" ? "#8be8f7" : "#b7d88d";
  context.fillRect(point.x - barWidth / 2, barY, barWidth * Math.max(0, enemy.hp / enemy.max_hp), 5);
  context.restore();
}

function drawSprite(
  context: CanvasRenderingContext2D,
  sprite: SpriteSet,
  x: number,
  feetY: number,
  targetHeight: number,
  facing: 1 | -1,
  time: number,
) {
  const frames = Math.max(1, sprite.strip.frames);
  const fps = Math.max(1, sprite.strip.fps ?? 10);
  const frame = Math.floor(time * fps) % frames;
  const sourceWidth = sprite.image.naturalWidth / frames;
  const sourceHeight = sprite.image.naturalHeight;
  const displayWidth = targetHeight * (sourceWidth / Math.max(1, sourceHeight));
  context.save();
  context.translate(x, feetY);
  context.scale(facing, 1);
  context.drawImage(
    sprite.image,
    frame * sourceWidth,
    0,
    sourceWidth,
    sourceHeight,
    -displayWidth / 2,
    -targetHeight,
    displayWidth,
    targetHeight,
  );
  context.restore();
}

function drawFallbackActor(
  context: CanvasRenderingContext2D,
  x: number,
  feetY: number,
  halfWidth: number,
  height: number,
  color: string,
) {
  context.save();
  context.fillStyle = color;
  context.beginPath();
  context.roundRect(x - halfWidth, feetY - height, halfWidth * 2, height, 18);
  context.fill();
  context.restore();
}

function CampaignSequenceCard({
  stages,
  profiles,
  editingStageId,
  draft,
  saving,
  error,
  onStart,
  onCancel,
  onChange,
  onSave,
}: {
  stages: PveStage[];
  profiles: PveEnemyProfile[];
  editingStageId: PveStageId | null;
  draft: Record<string, string>;
  saving: boolean;
  error: string | null;
  onStart: (stage: PveStage) => void;
  onCancel: () => void;
  onChange: (enemyId: string, profileId: string) => void;
  onSave: (stage: PveStage) => void;
}) {
  return (
    <Card
      title="三关敌人序列"
      icon="layers"
      bodyClassName="p-3"
      right={<Badge tone="neutral">{stages.length} 关</Badge>}
    >
      <p className="mb-2 text-[10.5px] leading-4 text-ink-4">
        按关卡列出当前阵容。自定义只替换目标关，小怪与 Boss 槽位会按类型筛选敌人池。
      </p>
      <div className="flex flex-col gap-2">
        {stages.map((stage, index) => {
          const editing = editingStageId === stage.id;
          return (
            <div key={stage.id} className="rounded-md border border-line-subtle bg-canvas p-2">
              <div className="mb-1.5 flex items-center gap-1.5">
                <span className="font-mono text-[9px] text-ink-4">
                  {String(index + 1).padStart(2, "0")}
                </span>
                <span className="min-w-0 flex-1 truncate text-[10.5px] font-semibold text-ink-2">
                  {stage.title}
                </span>
                <Badge tone={stage.kind === "boss" ? "danger" : "neutral"}>
                  {stage.kind === "boss" ? "BOSS" : `${stage.enemies.length} 小怪`}
                </Badge>
                {!editing && editingStageId === null && (
                  <Button
                    variant="ghost"
                    size="sm"
                    icon="pencil"
                    disabled={profiles.length === 0}
                    onClick={() => onStart(stage)}
                  >
                    替换
                  </Button>
                )}
              </div>
              <div className="flex flex-col gap-1">
                {stage.enemies.map((enemy) => {
                  const choices = profiles.filter((profile) =>
                    profile.role === (enemy.kind === "boss" ? "boss" : "minion"),
                  );
                  return (
                    <div
                      key={enemy.id}
                      className="flex items-center gap-2 rounded-sm bg-paper/70 px-2 py-1.5"
                    >
                      <Icon
                        name={enemy.kind === "boss" ? "flame" : "zap"}
                        className={cx(
                          "h-3 w-3 shrink-0",
                          enemy.kind === "boss" ? "text-danger" : "text-success",
                        )}
                      />
                      {editing && choices.length > 0 ? (
                        <select
                          aria-label={`${enemy.id} 敌人`}
                          value={draft[enemy.id] ?? ""}
                          onChange={(event) => onChange(enemy.id, event.target.value)}
                          className="min-w-0 flex-1 rounded-sm border border-line bg-canvas px-1.5 py-1 text-[10.5px] text-ink outline-none focus:border-primary/60"
                        >
                          <option value="">选择敌人</option>
                          {choices.map((profile) => (
                            <option key={profile.id} value={profile.id}>
                              {profile.name} · {profile.stats.max_hp} HP
                            </option>
                          ))}
                        </select>
                      ) : editing ? (
                        <span className="min-w-0 flex-1 text-[10px] leading-4 text-warning">
                          敌人池暂无可用{enemy.kind === "boss" ? " Boss" : "小怪"}，请先在敌人工坊生成或重试失败的敌人
                        </span>
                      ) : (
                        <>
                          <span className="min-w-0 flex-1 truncate text-[10.5px] text-ink-2">
                            {enemy.name}
                          </span>
                          <span className="text-[9.5px] text-ink-4">{enemy.max_hp} HP</span>
                        </>
                      )}
                    </div>
                  );
                })}
              </div>
              {editing && (
                <div className="mt-2 flex justify-end gap-2">
                  <Button variant="ghost" size="sm" onClick={onCancel} disabled={saving}>
                    取消
                  </Button>
                  <Button
                    variant="primary"
                    size="sm"
                    icon="check"
                    loading={saving}
                    onClick={() => onSave(stage)}
                  >
                    保存本关
                  </Button>
                </div>
              )}
            </div>
          );
        })}
      </div>
      {error && (
        <p className="mt-2 text-[10.5px] leading-4 text-danger" role="alert">
          {error}
        </p>
      )}
    </Card>
  );
}

function matchingProfileId(enemy: PveEnemySpawn, profiles: PveEnemyProfile[]) {
  const role = enemy.kind === "boss" ? "boss" : "minion";
  const current = profiles.find(
    (profile) => profile.id === enemy.profile_id && profile.role === role,
  );
  if (current) return current.id;
  const sameAsset = profiles.find(
    (profile) => profile.role === role && profile.asset_id === enemy.asset_id,
  );
  if (sameAsset) return sameAsset.id;
  // 原 profile 已从敌人池删除时，回退到同角色的第一个可用敌人，
  // 保证进入编辑就有一组可直接保存的默认值。
  return profiles.find((profile) => profile.role === role)?.id ?? "";
}

function difficultyLabel(value: "easy" | "normal" | "hard") {
  return value === "hard" ? "挑战" : value === "easy" ? "轻松" : "标准";
}

function PveEnemyForge({
  profiles,
  loading,
  difficulty,
  onRefresh,
}: {
  profiles: PveEnemyProfile[];
  loading: boolean;
  difficulty: "easy" | "normal" | "hard";
  onRefresh: () => void;
}) {
  const queryClient = useQueryClient();
  const [prompt, setPrompt] = useState("");
  const [role, setRole] = useState<"minion" | "boss">("minion");
  const [pendingDelete, setPendingDelete] = useState<string | null>(null);
  const rebuild = useMutation({
    mutationFn: ({ id, action }: { id: string; action: string }) => api.rebuildPveAction(id, action),
    onSuccess: () => {
      onRefresh();
      void queryClient.invalidateQueries({ queryKey: ["pve-enemies"] });
    },
    onError: (error) =>
      toast({
        tone: "danger",
        title: "动作重建失败",
        description: error instanceof Error ? error.message : "请稍后重试",
      }),
  });
  const generate = useMutation({
    mutationFn: () => api.generatePveEnemy(prompt.trim(), role, difficulty),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["pve-enemies"] });
      onRefresh();
    },
  });
  const retry = useMutation({
    mutationFn: (enemyId: string) => api.retryPveEnemy(enemyId),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["pve-enemies"] });
      onRefresh();
    },
    onError: (error) =>
      toast({
        tone: "danger",
        title: "敌人重试失败",
        description: error instanceof Error ? error.message : "请稍后重试",
      }),
  });
  const remove = useMutation({
    mutationFn: (enemyId: string) => api.deletePveEnemy(enemyId),
    onSuccess: (result) => {
      void queryClient.invalidateQueries({ queryKey: ["pve-enemies"] });
      onRefresh();
      setPendingDelete(null);
      toast({ tone: "success", title: "敌人已从池中删除", description: result.removed });
    },
    onError: (error) => {
      toast({
        tone: "danger",
        title: "删除敌人失败",
        description: error instanceof Error ? error.message : "请稍后重试",
      });
    },
  });
  const customProfiles = [...profiles].sort(
    (left, right) => right.created_at - left.created_at,
  );

  return (
    <Card title="PVE 敌人工坊" icon="spark" bodyClassName="p-3">
      <p className="text-[11px] leading-[18px] text-ink-3">
        独立生成小怪或 Boss 模型与待机、移动、攻击动作，不进入玩家角色列表。场景会根据提示词语义，
        从已完成的敌人池中自动匹配三关阵容。
      </p>
      <div className="mt-3 grid grid-cols-2 gap-1.5" role="group" aria-label="敌人类型">
        {(
          [
            ["minion", "小怪"],
            ["boss", "Boss"],
          ] as const
        ).map(([value, label]) => (
          <button
            key={value}
            type="button"
            aria-pressed={role === value}
            onClick={() => setRole(value)}
            className={cx(
              "rounded-md border px-2 py-1.5 text-[11.5px] font-medium transition-colors",
              role === value
                ? "border-primary/60 bg-primary-tint text-primary"
                : "border-line bg-canvas text-ink-3 hover:bg-surface-1",
            )}
          >
            {label}
          </button>
        ))}
      </div>
      <textarea
        value={prompt}
        onChange={(event) => setPrompt(event.target.value)}
        maxLength={1200}
        rows={3}
        placeholder={
          role === "boss"
            ? "例如：机械霜狼王，重甲，蓄力冲撞，冰霜吐息"
            : "例如：迅捷毒藤精灵，远程喷射毒液，会快速追击"
        }
        className="mt-2 w-full resize-y rounded-md border border-line bg-canvas px-2.5 py-2 text-[11.5px] leading-5 text-ink outline-none placeholder:text-ink-4 focus:border-primary/60"
      />
      <Button
        variant="secondary"
        size="sm"
        icon="spark"
        className="mt-2 w-full"
        loading={generate.isPending}
        disabled={!prompt.trim() || generate.isPending}
        onClick={() => generate.mutate()}
      >
        {generate.isPending
          ? "正在创建敌人"
          : role === "boss"
            ? "生成自定义 Boss"
            : "生成自定义小怪"}
      </Button>
      {generate.error && (
        <p className="mt-2 text-[10.5px] leading-4 text-danger">
          {generate.error instanceof Error ? generate.error.message : "敌人生成失败"}
        </p>
      )}

      <div className="mt-3 border-t border-line-subtle pt-2.5">
        <div className="flex items-center gap-2">
          <span className="cf-ref">敌人池</span>
          <span className="text-[10px] text-ink-4">
            {customProfiles.length} 个自定义敌人
          </span>
        </div>
        {loading ? (
          <Skeleton className="mt-2 h-12 w-full rounded-md" />
        ) : customProfiles.length === 0 ? (
          <p className="mt-2 text-[10.5px] leading-4 text-ink-4">
            还没有自定义敌人。请先生成至少一个小怪和一个 Boss，场景才能构建 PVE 战役。
          </p>
        ) : (
          <div className="mt-2 flex max-h-72 flex-col gap-1.5 overflow-y-auto pr-1">
            {customProfiles.map((enemy) => (
              <div
                key={enemy.id}
                className="flex items-center gap-2 rounded-md border border-line-subtle bg-canvas p-1.5"
              >
                <SafeImage
                  src={enemy.asset_id ? `/api/assets/${enemy.asset_id}/image.png` : undefined}
                  alt={enemy.name}
                  className="h-10 w-10 shrink-0 rounded-sm bg-paper object-contain"
                />
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-1.5">
                    <span className="truncate text-[11px] font-medium text-ink">{enemy.name}</span>
                    <span className="shrink-0 text-[9px] text-ink-4">
                      {enemy.role === "boss" ? "Boss" : "小怪"}
                    </span>
                  </div>
                  <div className="mt-0.5 flex items-center gap-1">
                    <span className="text-[9.5px] text-ink-4">
                      {enemyStatusLabel(enemy.status)}
                    </span>
                    {enemy.behavior && (
                      <span className="rounded-sm bg-surface-1 px-1 py-0.5 text-[9px] text-ink-3">
                        {behaviorLabel(enemy.behavior)}
                      </span>
                    )}
                  </div>
                  <EnemyGenerationProgress enemy={enemy} />
                  <div className="mt-0.5 truncate text-[9px] text-ink-4">
                    {enemy.tags?.join(" · ") || "语义待提取"} · {enemy.stats.max_hp} HP ·{" "}
                    {enemy.stats.speed} 速
                  </div>
                  {enemy.error && (
                    <p className="mt-0.5 truncate text-[9px] text-danger" title={enemy.error}>
                      {enemy.error}
                    </p>
                  )}
                  {enemy.action_warning && !enemy.error && (
                    <p
                      className="mt-0.5 truncate text-[9px] text-warning"
                      title={enemy.action_warning}
                    >
                      {enemy.action_warning}
                    </p>
                  )}
                  {remove.isError && remove.variables === enemy.id && (
                    <p
                      className="mt-0.5 truncate text-[9px] text-danger"
                      title={remove.error instanceof Error ? remove.error.message : "删除失败"}
                    >
                      {remove.error instanceof Error ? remove.error.message : "删除失败"}
                    </p>
                  )}
                  <div className="mt-1 flex gap-2">
                    {(["idle", "walk", "attack"] as const).map((action) => (
                      <button
                        key={action}
                        type="button"
                        disabled={
                          rebuild.isPending ||
                          retry.isPending ||
                          !enemy.asset_id ||
                          !["ready", "failed"].includes(enemy.status)
                        }
                        className="text-[10px] text-primary disabled:opacity-40"
                        onClick={() => rebuild.mutate({ id: enemy.id, action })}
                      >
                        重建{action === "idle" ? "待机" : action === "walk" ? "行走" : "攻击"}
                      </button>
                    ))}
                    {enemy.status === "failed" && (
                      <button
                        type="button"
                        disabled={retry.isPending || retry.variables === enemy.id}
                        className="text-[10px] font-medium text-warning disabled:opacity-40"
                        onClick={() => retry.mutate(enemy.id)}
                      >
                        {retry.isPending && retry.variables === enemy.id ? "重试中" : "重试生成"}
                      </button>
                    )}
                  </div>
                </div>
                {pendingDelete === enemy.id ? (
                  <div className="flex shrink-0 flex-col items-end gap-1">
                    <button
                      type="button"
                      className="text-[10px] font-medium text-danger disabled:opacity-40"
                      disabled={remove.isPending}
                      onClick={() => remove.mutate(enemy.id)}
                    >
                      确认删除
                    </button>
                    <button
                      type="button"
                      className="text-[10px] text-ink-4"
                      onClick={() => setPendingDelete(null)}
                    >
                      取消
                    </button>
                  </div>
                ) : (
                  <IconButton
                    icon="trash"
                    label={`从敌人池删除 ${enemy.name}`}
                    disabled={
                      remove.isPending ||
                      [
                        "analyzing",
                        "generating_model",
                        "generating_views",
                        "generating_actions",
                      ].includes(enemy.status)
                    }
                    onClick={() => setPendingDelete(enemy.id)}
                    className="h-7 w-7 shrink-0"
                  />
                )}
                <Badge
                  tone={
                    enemy.status === "ready"
                      ? "success"
                      : enemy.status === "failed"
                        ? "danger"
                        : "neutral"
                  }
                >
                  {enemy.status === "ready" ? "可用" : enemy.status === "failed" ? "失败" : "生成中"}
                </Badge>
              </div>
            ))}
          </div>
        )}
      </div>
    </Card>
  );
}

function EnemyGenerationProgress({ enemy }: { enemy: PveEnemyProfile }) {
  const progress = enemyGenerationProgress(enemy.status);
  if (!progress) return null;
  return (
    <div
      className="mt-1"
      role="progressbar"
      aria-label={`${enemy.name} 生成进度`}
      aria-valuemin={0}
      aria-valuemax={100}
      aria-valuenow={progress.pct}
    >
      <div className="flex items-center justify-between text-[9px] leading-3 text-ink-3">
        <span>{progress.label}</span>
        <span className="font-mono">{progress.pct}%</span>
      </div>
      <div className="mt-1 h-1.5 w-full overflow-hidden rounded-full bg-surface-2">
        <div
          className="h-full rounded-full bg-primary transition-[width] duration-(--motion-progress) ease-linear"
          style={{ width: `${progress.pct}%` }}
        />
      </div>
    </div>
  );
}

const ENEMY_GENERATION_PROGRESS: Partial<
  Record<PveEnemyProfile["status"], { pct: number; label: string }>
> = {
  analyzing: { pct: 15, label: "解析敌人设定" },
  generating_model: { pct: 45, label: "生成敌人模型" },
  generating_views: { pct: 62, label: "生成侧视 / 背面视图" },
  generating_actions: { pct: 80, label: "补齐待机 / 行走 / 攻击动作" },
};

function enemyGenerationProgress(status: PveEnemyProfile["status"]) {
  return ENEMY_GENERATION_PROGRESS[status] ?? null;
}

function enemyStatusLabel(status: PveEnemyProfile["status"]) {
  return {
    analyzing: "分析语义",
    generating_model: "生成模型",
    generating_views: "生成三视图",
    generating_actions: "补齐动作",
    ready: "已加入场景匹配池",
    failed: "生成失败",
  }[status];
}

function behaviorLabel(behavior: string) {
  return (
    {
      chaser: "追踪",
      shooter: "远程",
      charger: "冲锋",
      guardian: "守关",
    }[behavior] ?? behavior
  );
}

function HudChip({
  icon,
  text,
  danger = false,
}: {
  icon: "shield" | "crosshair" | "clock" | "flame";
  text: string;
  danger?: boolean;
}) {
  return (
    <span
      className={cx(
        "inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-[10.5px] font-medium shadow-sm backdrop-blur-sm",
        danger
          ? "border-danger/35 bg-paper/92 text-danger"
          : "border-line/70 bg-paper/92 text-ink-2",
      )}
    >
      <Icon name={icon} className="h-3 w-3" />
      {text}
    </span>
  );
}

function RuleItem({
  icon,
  title,
  text,
}: {
  icon: "crosshair" | "shield" | "flame";
  title: string;
  text: string;
}) {
  return (
    <div className="flex gap-2.5 rounded-md bg-surface-1/65 p-2.5">
      <Icon name={icon} className="mt-0.5 h-4 w-4 shrink-0 text-primary" />
      <div>
        <div className="text-[11.5px] font-semibold text-ink">{title}</div>
        <p className="mt-0.5 text-[10.5px] leading-[16px] text-ink-3">{text}</p>
      </div>
    </div>
  );
}

function StageClearedOverlay({
  stageTitle,
  stageIndex,
  stageCount,
  kills,
  total,
  elapsed,
  hp,
  onAdvance,
  onRestart,
  onBack,
}: {
  stageTitle: string;
  stageIndex: number;
  stageCount: number;
  kills: number;
  total: number;
  elapsed: number;
  hp: number;
  onAdvance: () => void;
  onRestart: () => void;
  onBack: () => void;
}) {
  return (
    <div className="absolute inset-0 z-30 grid place-items-center bg-canvas/70 p-4 backdrop-blur-[1px]">
      <div className="w-[min(380px,92%)] rounded-xl border border-line bg-paper p-5 text-center shadow-e3">
        <span className="mx-auto grid h-11 w-11 place-items-center rounded-full bg-success/15 text-success">
          <Icon name="check" className="h-5 w-5" />
        </span>
        <h3 className="mt-3 font-serif text-[20px] font-black text-ink">第 {stageIndex} 关完成</h3>
        <p className="mt-1 text-[11.5px] leading-5 text-ink-3">
          {stageTitle} · 清除 {kills}/{total} · 累计 {elapsed.toFixed(1)}s · 剩余生命 {hp}
        </p>
        <div className="mt-4 flex flex-wrap justify-center gap-2">
          {stageIndex < stageCount ? (
            <Button variant="primary" size="sm" icon="play" onClick={onAdvance}>
              进入第 {stageIndex + 1} 关
            </Button>
          ) : null}
          <Button variant="secondary" size="sm" icon="refresh" onClick={onRestart}>
            重启战役
          </Button>
          <Button variant="ghost" size="sm" icon="grid" onClick={onBack}>
            返回工坊
          </Button>
        </div>
        <p className="mt-2 text-[10px] text-ink-4">
          只有点击按钮或按 Enter 才会进入下一关
        </p>
      </div>
    </div>
  );
}

function ResultOverlay({
  won,
  title,
  detail,
  onRestart,
  restartLabel = "再战一次",
  onBack,
}: {
  won: boolean;
  title: string;
  detail: string;
  onRestart: () => void;
  restartLabel?: string;
  onBack: () => void;
}) {
  return (
    <div className="absolute inset-0 z-30 grid place-items-center bg-canvas/88 p-4 backdrop-blur-[2px]">
      <div className="w-[min(380px,92%)] rounded-xl border border-line bg-paper p-5 text-center shadow-e3">
        <span
          className={cx(
            "mx-auto grid h-11 w-11 place-items-center rounded-full",
            won ? "bg-success/15 text-success" : "bg-danger/15 text-danger",
          )}
        >
          <Icon name={won ? "check" : "x"} className="h-5 w-5" />
        </span>
        <h3 className="mt-3 font-serif text-[20px] font-black text-ink">{title}</h3>
        <p className="mt-1 text-[11.5px] leading-5 text-ink-3">{detail}</p>
        <div className="mt-4 flex flex-wrap justify-center gap-2">
          <Button variant="primary" size="sm" icon="refresh" onClick={onRestart}>
            {restartLabel}
          </Button>
          <Button variant="secondary" size="sm" icon="grid" onClick={onBack}>
            返回场景工坊
          </Button>
        </div>
      </div>
    </div>
  );
}

/** 让 PveStagePhase 在页面类型检查里保持显式引用。 */
export type { PveStagePhase };
/** 供调试与后续扩展的纯函数再导出。 */
export { pveGroundDistance, PVE_SLAM_MAX_Z };

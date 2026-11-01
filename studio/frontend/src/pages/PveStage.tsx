import { useEffect, useMemo, useRef, useState } from "react";
import { useMutation, useQueries, useQuery, useQueryClient } from "@tanstack/react-query";
import { useNavigate, useSearchParams } from "react-router-dom";
import { api } from "../api/client";
import { Icon } from "../components/icons";
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
import { cameraX, type ArcadeAction } from "../lib/arcade";
import {
  PVE_PLAYER_HP,
  PVE_ABILITIES,
  pveVentStage,
  pveEnemyPose,
  pveActionSlot,
  PVE_ACTION_FALLBACK,
  activePveEncounter,
  backgroundLayerBlend,
  consumePveAudioEvents,
  createPveRuntime,
  enemyHalfWidth,
  enemyHeight,
  pveHud,
  pveEncounters,
  stepPve,
  togglePvePause,
  type PveAudioEvent,
  type PveHud,
  type PveRuntime,
  type PveRuntimeEnemy,
} from "../lib/pve";
import type {
  CreativeAsset,
  PlaytestPreviews,
  PlaytestStrip,
  PveEncounter,
  PveEnemy,
  PveEnemyProfile,
  PveLevel,
} from "../types";
import { toast } from "../stores/toastStore";

const STAGE_HEIGHT = 420;
const DEFAULT_STAGE_WIDTH = 760;
const PLAYER_HEIGHT = 176;
const HUD_INTERVAL_MS = 90;

interface SpriteSet {
  image: HTMLImageElement;
  strip: PlaytestStrip;
}

interface RenderAssets {
  player: Record<string, SpriteSet | undefined>;
  enemies: Record<string, Record<string, SpriteSet | undefined>>;
  backgrounds: HTMLImageElement[];
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
  const [sequenceEditing, setSequenceEditing] = useState(false);
  const [sequenceDraft, setSequenceDraft] = useState<Record<string, string>>({});
  const [renderAssets, setRenderAssets] = useState<RenderAssets>({
    player: {},
    enemies: {},
    backgrounds: [],
  });

  const sceneQuery = useQuery({
    queryKey: ["pve-scene", sceneId],
    queryFn: ({ signal }) => api.getScene(sceneId!, { signal, silent: true }),
    enabled: Boolean(sceneId),
    retry: false,
  });
  const scene = sceneQuery.data;
  const pveLevel = scene?.gameplay.type === "pve" ? scene.gameplay.level : null;
  const enemyAssetIds = useMemo(
    () => [...new Set(pveLevel?.enemies.map((enemy) => enemy.asset_id) ?? [])],
    [pveLevel],
  );

  const history = useQuery({
    queryKey: ["pve-people"],
    queryFn: () => api.listHistory({ limit: 12 }),
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
    mutationFn: (profileIds: string[]) => api.updatePveEnemySequence(sceneId!, profileIds),
    onSuccess: (updated) => {
      queryClient.setQueryData(["pve-scene", sceneId], updated);
      void queryClient.invalidateQueries({ queryKey: ["scenes"] });
      setSequenceEditing(false);
      toast({ tone: "success", title: "敌人序列已保存", description: "关卡已按新阵容重新载入" });
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
      queryKey: ["pve-enemy-previews", assetId, readyEnemyProfiles.find((profile) => profile.asset_id === assetId)?.updated_at],
      queryFn: () =>
        api.playtestPreviews(assetId, {
          actions: ["idle", "walk", "attack"],
          includeCustom: true,
        }),
      enabled: Boolean(assetId),
    })),
  });
  const enemyPreviewStamp = enemyPreviewQueries.map((query) => query.dataUpdatedAt).join(":");

  const backgroundUrls = useMemo(() => {
    const sequenced = (scene?.theme.background_urls ?? []).filter(Boolean);
    if (sequenced.length > 0) return sequenced;
    return scene?.theme.background_url ? [scene.theme.background_url] : [];
  }, [scene]);

  const storedBestTime = useMemo(() => {
    if (!sceneId) return null;
    const stored = Number(window.localStorage.getItem(`creativeforge:pve-best:${sceneId}`));
    return Number.isFinite(stored) && stored > 0 ? stored : null;
  }, [sceneId]);
  const bestTime = hud?.status === "won"
    ? Math.min(storedBestTime ?? Infinity, hud.elapsed)
    : storedBestTime;

  useEffect(() => {
    if (!sceneId || hud?.status !== "won") return;
    window.localStorage.setItem(`creativeforge:pve-best:${sceneId}`, String(bestTime));
  }, [bestTime, hud?.status, sceneId]);

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
      const loadedBackgrounds = (
        await Promise.all(backgroundUrls.map((url) => preloadImage(url).catch(() => undefined)))
      ).filter((image): image is HTMLImageElement => Boolean(image));
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
  }, [backgroundUrls, enemyAssetIds, enemyPreviewStamp, playerPreviews.data, selected?.id]);

  useEffect(() => {
    if (!pveLevel) return;
    runtimeRef.current = createPveRuntime(pveLevel);
    setHud(pveHud(runtimeRef.current, pveLevel));
  }, [pveLevel]);

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
    if (!pveLevel || !selected || !assetsReady) return;
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
      const canConsumeShot = !runtime.paused && runtime.status === "playing" && runtime.hitstopRemaining <= 0;
      stepPve(
        runtime,
        pveLevel,
        {
          left: keys.has("arrowleft") || keys.has("a"),
          right: keys.has("arrowright") || keys.has("d"),
          run: keys.has("shift"),
          jump: keys.has(" ") || keys.has("arrowup"),
          shoot: shotRequestRef.current,
          guard: keys.has("k"),
          dodge: keys.has("l"),
          aimY: keys.has("w") ? -0.7 : keys.has("s") ? 0.7 : 0,
        },
        dt,
      );
      if (canConsumeShot || runtime.status !== "playing") shotRequestRef.current = false;
      playPveSounds(consumePveAudioEvents(runtime));
      runtime.camera = cameraX(runtime.player.x, stageWidthRef.current, pveLevel.width);
      drawPveScene(context, canvas, pveLevel, runtime, renderAssets, reduceMotion);
      if (time - lastHud >= HUD_INTERVAL_MS) {
        lastHud = time;
        setHud(pveHud(runtime, pveLevel));
      }
    };
    frame = requestAnimationFrame(loop);
    return () => cancelAnimationFrame(frame);
  }, [assetsReady, pveLevel, reduceMotion, renderAssets, selected]);

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
      if (["arrowleft", "arrowright", "arrowup", " ", "f", "j", "k", "p", "escape"].includes(key)) {
        event.preventDefault();
      }
      heldRef.current.add(key);
      if (!event.repeat && (key === "p" || key === "escape")) {
        const runtime = runtimeRef.current;
        if (runtime && pveLevel) {
          togglePvePause(runtime);
          setHud(pveHud(runtime, pveLevel));
        }
      }
      if (!event.repeat && (key === "f" || key === "j") && !runtimeRef.current?.paused) {
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
  }, [pveLevel]);

  function startSequenceEditing() {
    if (!pveLevel) return;
    setSequenceDraft(
      Object.fromEntries(
        pveLevel.enemies.map((enemy) => [enemy.id, matchingProfileId(enemy, readyEnemyProfiles)]),
      ),
    );
    setSequenceEditing(true);
  }

  function saveEnemySequence() {
    if (!pveLevel) return;
    const profileIds: string[] = [];
    for (const enemy of pveLevel.enemies) {
      const profileId = sequenceDraft[enemy.id];
      if (!profileId) {
        toast({ tone: "warning", title: "请为每个敌人槽位选择可用敌人" });
        return;
      }
      profileIds.push(profileId);
    }
    saveSequence.mutate(profileIds);
  }

  function restart() {
    if (!pveLevel) return;
    runtimeRef.current = createPveRuntime(pveLevel);
    shotRequestRef.current = false;
    setHud(pveHud(runtimeRef.current, pveLevel));
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

  function togglePause() {
    const runtime = runtimeRef.current;
    if (!runtime || !pveLevel) return;
    togglePvePause(runtime);
    setHud(pveHud(runtime, pveLevel));
  }

  if (!sceneId) {
    return (
      <div className="mx-auto w-full max-w-[1440px] px-4 py-5 md:px-6">
        <PageHeader
          overline="PVE Arcade"
          title="PVE 关卡试玩"
          description="从场景工坊选择 PVE 模式生成战斗场景，再选择角色进入关卡。"
        />
        <div className="mt-5">
          <EmptyState
            icon="zap"
            title="还没有选择 PVE 场景"
            description="先在工作坊里描述敌人与战场主题，生成场景后会带着关卡直接进入这里。"
            action={
              <Button variant="primary" icon="grid" onClick={() => navigate("/scenes")}>
                去场景工坊
              </Button>
            }
          />
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

  const encounterPlan = scene.gameplay.level ? pveEncounters(scene.gameplay.level) : [];
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
        description={`${scene.theme.summary} · 远程攻击、逐区清场，再挑战提示词匹配的守关 Boss。`}
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
        <div className="col-span-12 flex min-w-0 flex-col gap-3 xl:col-span-8">
          <Card
            title="PVE 战斗 · 侧卷轴"
            icon="play"
            bodyClassName="p-3"
            right={
              <div className="flex items-center gap-1.5">
                {hud?.bossActive ? (
                  <Badge tone="danger">Boss 战</Badge>
                ) : (
                  <Badge tone="neutral">
                    {hud ? `${hud.encounterIndex}/${hud.encounterCount}` : "准备"}
                  </Badge>
                )}
                <button
                  type="button"
                  aria-label={hud?.paused ? "继续游戏" : "暂停游戏"}
                  onClick={togglePause}
                  className="grid h-7 w-7 place-items-center rounded-full border border-line bg-paper text-ink-2 hover:bg-surface-1 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary"
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
                aria-label="PVE 横版战斗画面"
                className="block h-auto w-full touch-none"
                onPointerDown={() => {
                  if (assetsReady) shoot();
                }}
              />

              {hud && (
                <div className="pointer-events-none absolute left-3 top-3 z-[5] flex flex-wrap gap-1.5">
                  <HudChip icon="shield" text={`${hud.hp}/${PVE_PLAYER_HP}`} danger={hud.hp <= 2} />
                  <HudChip icon="crosshair" text={`敌人 ${hud.defeated}/${hud.total}`} />
                  <HudChip icon="clock" text={`${hud.elapsed.toFixed(1)}s`} />
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
                    {hud.encounterTitle}
                    {hud.encounterRemaining > 0 ? ` · 剩余 ${hud.encounterRemaining}` : ""}
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

              <div className="absolute bottom-2 left-2 right-2 z-[5] flex items-end justify-end gap-1 sm:bottom-3 sm:left-auto sm:right-3 sm:gap-2">
                <TouchButton
                  label="向左"
                  icon="arrow-left"
                  onDown={() => {
                    ensureAudio();
                    heldRef.current.add("arrowleft");
                  }}
                  onUp={() => heldRef.current.delete("arrowleft")}
                />
                <TouchButton
                  label="向右"
                  icon="arrow-right"
                  onDown={() => {
                    ensureAudio();
                    heldRef.current.add("arrowright");
                  }}
                  onUp={() => heldRef.current.delete("arrowright")}
                />
                <TouchButton
                  label="跳跃"
                  icon="arrow-up"
                  onDown={() => {
                    ensureAudio();
                    heldRef.current.add(" ");
                  }}
                  onUp={() => heldRef.current.delete(" ")}
                />
                <TouchButton
                  label="单格防御"
                  icon="shield"
                  onDown={() => {
                    ensureAudio();
                    heldRef.current.add("k");
                  }}
                  onUp={() => heldRef.current.delete("k")}
                />
                <button
                  type="button"
                  aria-label="发射攻击"
                  onClick={shoot}
                  className="grid h-10 w-10 shrink-0 place-items-center rounded-full border border-primary/50 bg-ink text-paper shadow-e2 transition-transform active:scale-95 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary focus-visible:ring-offset-2 sm:h-12 sm:w-12"
                >
                  <Icon name="crosshair" className="h-5 w-5" />
                </button>
                <TouchButton label={`闪避，冷却 ${Math.ceil(hud?.dodgeCooldown ?? 0)} 秒`} icon="arrow-right" onDown={() => heldRef.current.add("l")} onUp={() => heldRef.current.delete("l")} />
                <TouchButton label="向上瞄准" icon="arrow-up" onDown={() => heldRef.current.add("w")} onUp={() => heldRef.current.delete("w")} />
                <TouchButton label="向下瞄准" icon="arrow-up" onDown={() => heldRef.current.add("s")} onUp={() => heldRef.current.delete("s")} />
                <span className="hidden text-xs xl:inline">闪避 {(hud?.dodgeCooldown ?? 0) > 0 ? `${hud?.dodgeCooldown.toFixed(1)}s` : "就绪"}</span>
              </div>

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

              {hud?.paused && hud.status === "playing" && (
                <div className="absolute inset-0 z-30 grid place-items-center bg-canvas/88 p-4 backdrop-blur-[2px]">
                  <div className="w-[min(340px,88%)] rounded-xl border border-line bg-paper p-5 text-center shadow-e3">
                    <span className="mx-auto grid h-11 w-11 place-items-center rounded-full bg-primary/12 text-primary">
                      <Icon name="pause" className="h-5 w-5" />
                    </span>
                    <h3 className="mt-3 font-serif text-[20px] font-black text-ink">战斗暂停</h3>
                    <p className="mt-1 text-[11.5px] leading-5 text-ink-3">
                      当前遭遇战：{hud.encounterTitle}
                    </p>
                    <div className="mt-4 flex justify-center gap-2">
                      <Button variant="primary" size="sm" icon="play" onClick={togglePause}>
                        继续游戏
                      </Button>
                      <Button variant="secondary" size="sm" icon="refresh" onClick={restart}>
                        重新开始
                      </Button>
                    </div>
                  </div>
                </div>
              )}

              {hud?.status === "won" && (
                <ResultOverlay
                  won
                  title={`${hud.grade} 级 · 守关 Boss 已被击败`}
                  detail={`清除 ${hud.defeated}/${hud.total} · ${hud.elapsed.toFixed(1)}s · 受伤 ${hud.damageTaken} · 防御 ${hud.guardsUsed} · 命中率 ${Math.round(hud.accuracy * 100)}%${bestTime ? ` · 最佳 ${bestTime.toFixed(1)}s` : ""}`}
                  onRestart={restart}
                  onBack={() => navigate("/scenes")}
                />
              )}
              {hud?.status === "lost" && (
                <ResultOverlay
                  won={false}
                  title="本轮挑战失败"
                  detail={`已清除 ${hud.defeated}/${hud.total} 个敌人 · 调整走位后重试`}
                  onRestart={restart}
                  onBack={() => navigate("/scenes")}
                />
              )}
            </div>
          </Card>

          <section className="rounded-lg border border-line bg-paper px-3.5 py-3 shadow-e1">
            <div className="flex flex-wrap items-center gap-2">
              <Button variant="primary" size="sm" icon="refresh" onClick={restart}>
                重新开始
              </Button>
              <Button variant="secondary" size="sm" icon="cube" onClick={() => setPickerOpen(true)}>
                更换出战角色
              </Button>
              <span className="text-[11px] text-ink-4">
                A / D 或 ← → 移动 · Shift 奔跑 · ↑ / 空格跳跃 · F / J 单发攻击 · W / S 瞄准 · K 防御 · L 闪避 · P 暂停
              </span>
            </div>
            <div className="mt-3 grid gap-2 sm:grid-cols-3">
              <RuleItem
                icon="crosshair"
                title="单次远程攻击"
                text="每次按键或点击只发射一枚能量弹，无需角色攻击动作。"
              />
              <RuleItem
                icon="shield"
                title="单格防御"
                text="按住 K 可抵挡一次伤害；防御碎裂后冷却 4 秒，HUD 会显示恢复进度。"
              />
              <RuleItem
                icon="flame"
                title="逐区突破"
                text="进入战斗区后封锁出口，清除当前敌人才会开放下一处战场与守关 Boss。"
              />
            </div>
          </section>
        </div>

        <aside className="col-span-12 flex flex-col gap-3 xl:col-span-4">
          <EnemySequenceCard
            encounters={encounterPlan}
            enemies={pveLevel?.enemies ?? []}
            profiles={readyEnemyProfiles}
            editing={sequenceEditing}
            draft={sequenceDraft}
            saving={saveSequence.isPending}
            onStart={startSequenceEditing}
            onCancel={() => setSequenceEditing(false)}
            onChange={(enemyId, profileId) =>
              setSequenceDraft((current) => ({ ...current, [enemyId]: profileId }))
            }
            onSave={saveEnemySequence}
          />

          <Card title="战斗说明" icon="info" bodyClassName="p-4">
            <p className="text-[11.5px] leading-5 text-ink-3">
              这是独立的轻量 PVE 模式，不会改动跑酷关卡。战场、遭遇战和敌人会按提示词语义生成；
              自定义敌人通过独立敌人工坊生成模型与动作，不与玩家角色混用。
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

function EnemySequenceCard({
  encounters,
  enemies,
  profiles,
  editing,
  draft,
  saving,
  onStart,
  onCancel,
  onChange,
  onSave,
}: {
  encounters: PveEncounter[];
  enemies: PveEnemy[];
  profiles: PveEnemyProfile[];
  editing: boolean;
  draft: Record<string, string>;
  saving: boolean;
  onStart: () => void;
  onCancel: () => void;
  onChange: (enemyId: string, profileId: string) => void;
  onSave: () => void;
}) {
  return (
    <Card
      title="敌人序列"
      icon="layers"
      bodyClassName="p-3"
      right={
        editing ? (
          <Badge tone="primary">编辑中</Badge>
        ) : (
          <Button
            variant="secondary"
            size="sm"
            icon="pencil"
            disabled={profiles.length === 0}
            onClick={onStart}
          >
            自定义
          </Button>
        )
      }
    >
      <p className="mb-2 text-[10.5px] leading-4 text-ink-4">
        {editing
          ? "为每个战斗槽位选择敌人。小怪与 Boss 角色会按槽位类型筛选，保存后立即重新载入关卡。"
          : "按遭遇战顺序列出当前阵容，可从敌人池替换每个槽位的敌人。"}
      </p>
      <div className="flex flex-col gap-1.5">
        {encounters.map((encounter, index) => (
          <div key={encounter.id} className="rounded-md border border-line-subtle bg-canvas p-2">
            <div className="mb-1.5 flex items-center gap-1.5">
              <span className="font-mono text-[9px] text-ink-4">
                {String(index + 1).padStart(2, "0")}
              </span>
              <span className="min-w-0 flex-1 truncate text-[10.5px] font-semibold text-ink-2">
                {encounter.title}
              </span>
              <Badge tone={encounter.kind === "boss" ? "danger" : "neutral"}>
                {encounter.kind === "boss" ? "BOSS" : "遭遇战"}
              </Badge>
            </div>
            <div className="flex flex-col gap-1">
              {encounter.enemy_ids.map((enemyId) => {
                const enemy = enemies.find((candidate) => candidate.id === enemyId);
                if (!enemy) return null;
                const role = enemy.kind === "boss" ? "boss" : "minion";
                const choices = profiles.filter((profile) => profile.role === role);
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
                    {editing ? (
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
          </div>
        ))}
        {enemies.length === 0 && <p className="text-[11px] text-ink-4">该场景尚未配置敌人。</p>}
      </div>
      {editing && (
        <div className="mt-3 flex justify-end gap-2 border-t border-line-subtle pt-3">
          <Button variant="ghost" size="sm" onClick={onCancel} disabled={saving}>
            取消
          </Button>
          <Button variant="primary" size="sm" icon="check" loading={saving} onClick={onSave}>
            保存序列
          </Button>
        </div>
      )}
    </Card>
  );
}

function matchingProfileId(enemy: PveEnemy, profiles: PveEnemyProfile[]) {
  const role = enemy.kind === "boss" ? "boss" : "minion";
  const current = profiles.find(
    (profile) => profile.id === enemy.profile_id && profile.role === role,
  );
  if (current) return current.id;
  return (
    profiles.find((profile) => profile.role === role && profile.asset_id === enemy.asset_id)?.id ??
    ""
  );
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
  const rebuild = useMutation({
    mutationFn: ({ id, action }: { id: string; action: string }) => api.rebuildPveAction(id, action),
    onSuccess: () => { onRefresh(); void queryClient.invalidateQueries({ queryKey: ["pve-enemies"] }); },
    onError: (error) => toast({ tone: "danger", title: "动作重建失败", description: error instanceof Error ? error.message : "请稍后重试" }),
  });
  const generate = useMutation({
    mutationFn: () => api.generatePveEnemy(prompt.trim(), role, difficulty),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["pve-enemies"] });
      onRefresh();
    },
  });
  const remove = useMutation({
    mutationFn: (enemyId: string) => api.deletePveEnemy(enemyId),
    onSuccess: (result) => {
      void queryClient.invalidateQueries({ queryKey: ["pve-enemies"] });
      onRefresh();
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
  const customProfiles = profiles
    .filter((enemy) => !enemy.builtin)
    .sort((left, right) => right.created_at - left.created_at);
  const builtInCount = profiles.filter((enemy) => enemy.builtin).length;

  return (
    <Card title="PVE 敌人工坊" icon="spark" bodyClassName="p-3">
      <p className="text-[11px] leading-[18px] text-ink-3">
        独立生成小怪或 Boss 模型与待机、移动、攻击动作，不进入玩家角色列表。场景会根据提示词语义，
        从已完成的敌人池中自动匹配。
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
            {builtInCount} 默认 · {customProfiles.length} 自定义
          </span>
        </div>
        {loading ? (
          <Skeleton className="mt-2 h-12 w-full rounded-md" />
        ) : customProfiles.length === 0 ? (
          <p className="mt-2 text-[10.5px] leading-4 text-ink-4">
            还没有自定义敌人，当前场景继续使用森林史莱姆与冰霜巨龙。
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
                  <div className="mt-1 flex gap-2">
                    {(["idle", "walk", "attack"] as const).map((action) => (
                      <button key={action} type="button" disabled={rebuild.isPending || enemy.status !== "ready"} className="text-[10px] text-primary disabled:opacity-40" onClick={() => rebuild.mutate({ id: enemy.id, action })}>
                        重建{action === "idle" ? "待机" : action === "walk" ? "行走" : "攻击"}
                      </button>
                    ))}
                  </div>
                </div>
                <IconButton
                  icon="trash"
                  label={`从敌人池删除 ${enemy.name}`}
                  disabled={
                    remove.isPending ||
                    ["analyzing", "generating_model", "generating_actions"].includes(enemy.status)
                  }
                  onClick={() => {
                    if (
                      window.confirm(`从敌人池删除“${enemy.name}”？已有场景中的敌人快照不会改变。`)
                    ) {
                      remove.mutate(enemy.id);
                    }
                  }}
                  className="h-7 w-7 shrink-0"
                />
                <Badge
                  tone={
                    enemy.status === "ready"
                      ? "success"
                      : enemy.status === "failed"
                        ? "danger"
                        : "neutral"
                  }
                >
                  {enemy.status === "ready" ? "可用" : enemy.role === "boss" ? "Boss" : "GEN"}
                </Badge>
              </div>
            ))}
          </div>
        )}
      </div>
    </Card>
  );
}

function enemyStatusLabel(status: PveEnemyProfile["status"]) {
  return {
    analyzing: "分析语义",
    generating_model: "生成模型",
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

function TouchButton({
  label,
  icon,
  onDown,
  onUp,
}: {
  label: string;
  icon: "arrow-left" | "arrow-right" | "arrow-up" | "shield";
  onDown: () => void;
  onUp: () => void;
}) {
  return (
    <button
      type="button"
      aria-label={label}
      onPointerDown={onDown}
      onPointerUp={onUp}
      onPointerCancel={onUp}
      onPointerLeave={onUp}
      className="grid h-8 w-8 shrink-0 touch-none place-items-center rounded-full border border-line/70 bg-paper/90 text-ink-2 shadow-sm backdrop-blur-sm active:bg-surface-1 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary sm:h-10 sm:w-10"
    >
      <Icon name={icon} className="h-4 w-4" />
    </button>
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

function ResultOverlay({
  won,
  title,
  detail,
  onRestart,
  onBack,
}: {
  won: boolean;
  title: string;
  detail: string;
  onRestart: () => void;
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
            再战一次
          </Button>
          <Button variant="secondary" size="sm" icon="grid" onClick={onBack}>
            返回场景工坊
          </Button>
        </div>
      </div>
    </div>
  );
}

function drawPveScene(
  context: CanvasRenderingContext2D,
  canvas: HTMLCanvasElement,
  level: PveLevel,
  runtime: PveRuntime,
  assets: RenderAssets,
  reduceMotion: boolean,
) {
  const width = canvas.width;
  const height = canvas.height;
  context.clearRect(0, 0, width, height);
  drawBackground(context, width, height, runtime, level, assets.backgrounds, reduceMotion);
  context.save();
  context.translate(-runtime.camera, 0);
  drawPlatforms(context, level);
  for (const cover of level.covers ?? []) {
    context.save();
    context.fillStyle = "#3f4e5b";
    context.fillRect(cover.x, cover.y - cover.height, cover.width, cover.height);
    context.fillStyle = "#98a9b4";
    context.fillRect(cover.x, cover.y - cover.height, cover.width, 6);
    context.strokeStyle = "rgba(255,255,255,.28)";
    context.strokeRect(cover.x, cover.y - cover.height, cover.width, cover.height);
    context.restore();
  }
  for (const hazard of level.hazards ?? []) {
    const stage = pveVentStage(runtime.elapsed);
    context.save();
    context.fillStyle = stage === "active" ? "#ff8050" : "#533b36";
    context.fillRect(hazard.x, hazard.y - (stage === "active" ? 28 : 6), hazard.width, stage === "active" ? 28 : 6);
    context.strokeStyle = "#fff0b0";
    context.lineWidth = 2;
    context.strokeRect(hazard.x, hazard.y - 28, hazard.width, 28);
    context.fillStyle = "#fff";
    context.font = "12px sans-serif";
    context.textAlign = "center";
    context.fillText(stage === "warning" ? "⚠ 即将喷发" : stage === "active" ? "喷发！" : "间歇喷口", hazard.x + hazard.width / 2, hazard.y - 34);
    context.restore();
  }

  const active = activePveEncounter(runtime, level);
  if (active) {
    const barrierX = active.lock_x;
    context.save();
    context.globalAlpha = 0.34 + Math.sin(runtime.elapsed * 3) * 0.08;
    context.strokeStyle = active.kind === "boss" ? "#76dff2" : "#d9bd7e";
    context.lineWidth = 5;
    context.beginPath();
    context.moveTo(barrierX, level.groundY - 190);
    context.lineTo(barrierX, level.groundY);
    context.stroke();
    context.globalAlpha = 0.16;
    context.lineWidth = 1;
    for (let offset = 8; offset < 190; offset += 18) {
      context.beginPath();
      context.moveTo(barrierX - 7, level.groundY - offset);
      context.lineTo(barrierX + 7, level.groundY - offset + 8);
      context.stroke();
    }
    context.restore();
  }

  for (const enemy of runtime.enemies) {
    const dying = enemy.deathAt !== null && runtime.elapsed - enemy.deathAt < 0.6;
    if (enemy.hp <= 0 && !dying) continue;
    if (!dying && !active?.enemy_ids.includes(enemy.id)) continue;
    if (enemy.ability && enemy.abilityStage === "windup") {
      const ability = enemy.ability;
      context.save();
      context.strokeStyle = "#fff1b6";
      context.fillStyle = "rgba(255, 130, 65, .25)";
      context.lineWidth = 3;
      context.setLineDash([8, 5]);
      context.beginPath();
      if (ability === "shot") {
        context.moveTo(enemy.x, enemy.y - enemyHeight(enemy) * 0.55);
        context.lineTo(enemy.abilityTargetX, enemy.abilityTargetY);
      } else if (ability === "slam") {
        context.rect(enemy.x - PVE_ABILITIES.slam.range, enemy.y - 24, PVE_ABILITIES.slam.range * 2, 24);
        context.fill();
      } else {
        const distance = ability === "charge" ? 420 * PVE_ABILITIES.charge.active : 260 * PVE_ABILITIES.lunge.active;
        const start = enemy.x + (enemy.abilityDirection < 0 ? -distance : 0);
        context.rect(start - enemyHalfWidth(enemy), enemy.y - enemyHeight(enemy), distance + enemyHalfWidth(enemy) * 2, enemyHeight(enemy));
        context.fill();
      }
      context.stroke();
      context.setLineDash([]);
      context.fillStyle = "#fff";
      context.font = "bold 14px sans-serif";
      context.textAlign = "center";
      context.fillText(ability === "shot" ? "瞄准！" : ability === "slam" ? "震地！跳跃" : "冲刺！", enemy.x, enemy.y - enemyHeight(enemy) - 24);
      context.restore();
    }
    drawEnemy(context, enemy, runtime, assets.enemies[enemy.asset_id]);
  }
  drawPlayer(context, runtime, assets.player);
  for (const particle of runtime.particles) {
    context.save();
    context.globalAlpha = Math.max(0, particle.life / 0.35);
    context.fillStyle = particle.color;
    context.beginPath();
    context.arc(particle.x, particle.y, particle.size, 0, Math.PI * 2);
    context.fill();
    context.restore();
  }
  for (const projectile of runtime.projectiles) {
    context.save();
    context.shadowColor = projectile.color;
    context.shadowBlur = 14;
    context.strokeStyle = projectile.color;
    context.globalAlpha = 0.35;
    context.lineWidth = Math.max(2, projectile.radius * 0.8);
    context.beginPath();
    context.moveTo(projectile.x - projectile.vx * 0.045, projectile.y - projectile.vy * 0.045);
    context.lineTo(projectile.x, projectile.y);
    context.stroke();
    context.globalAlpha = 1;
    context.fillStyle = projectile.color;
    context.beginPath();
    context.arc(projectile.x, projectile.y, projectile.radius, 0, Math.PI * 2);
    context.fill();
    context.restore();
  }
  context.restore();
  const transitionRemaining = runtime.transitionUntil - runtime.elapsed;
  if (!reduceMotion && transitionRemaining > 0) {
    const strength = Math.min(1, transitionRemaining / 0.55);
    context.save();
    context.fillStyle = `rgba(13, 20, 33, ${0.28 * strength * strength})`;
    context.fillRect(0, 0, width, height);
    context.restore();
  }
}

function drawBackground(
  context: CanvasRenderingContext2D,
  width: number,
  height: number,
  runtime: PveRuntime,
  level: PveLevel,
  backgrounds: HTMLImageElement[],
  reduceMotion: boolean,
) {
  if (backgrounds.length === 0) {
    const gradient = context.createLinearGradient(0, 0, 0, height);
    gradient.addColorStop(0, "#25345a");
    gradient.addColorStop(0.72, "#8497b1");
    gradient.addColorStop(1, "#dce6ef");
    context.fillStyle = gradient;
    context.fillRect(0, 0, width, height);
    return;
  }
  const progress = Math.max(0, Math.min(1, runtime.player.x / Math.max(1, level.width)));
  if (reduceMotion) {
    const index = Math.round(progress * (backgrounds.length - 1));
    paintBackgroundLayer(context, width, height, backgrounds[index], runtime.camera, 1);
    return;
  }
  const blend = backgroundLayerBlend(progress, backgrounds.length);
  paintBackgroundLayer(context, width, height, backgrounds[blend.from], runtime.camera, 1);
  if (blend.to !== blend.from && blend.mix > 0) {
    paintBackgroundLayer(context, width, height, backgrounds[blend.to], runtime.camera, blend.mix);
  }
}

function paintBackgroundLayer(
  context: CanvasRenderingContext2D,
  width: number,
  height: number,
  image: HTMLImageElement,
  camera: number,
  alpha: number,
) {
  context.save();
  context.globalAlpha = alpha;
  const scale = Math.max(width / image.naturalWidth, height / image.naturalHeight);
  const drawWidth = image.naturalWidth * scale;
  const drawHeight = image.naturalHeight * scale;
  const drift = -((camera * 0.18) % drawWidth);
  context.drawImage(image, drift, (height - drawHeight) / 2, drawWidth, drawHeight);
  if (drawWidth < width + 1) {
    context.drawImage(image, drift + drawWidth, (height - drawHeight) / 2, drawWidth, drawHeight);
  }
  context.restore();
}

function drawPlatforms(context: CanvasRenderingContext2D, level: PveLevel) {
  for (const platform of level.platforms) {
    context.save();
    if (platform.kind === "floating") {
      context.fillStyle = "rgba(24, 36, 52, .24)";
      context.fillRect(platform.x + 8, platform.y + platform.height + 4, platform.width - 16, 8);
    }
    context.fillStyle = platform.kind === "ground" ? "#596b7d" : "#92a7b7";
    context.fillRect(platform.x, platform.y, platform.width, platform.height);
    context.fillStyle = platform.kind === "ground" ? "#b8c8d2" : "#d7e2e8";
    context.fillRect(platform.x, platform.y, platform.width, 6);
    context.restore();
  }
}

function drawPlayer(
  context: CanvasRenderingContext2D,
  runtime: PveRuntime,
  sprites: Record<string, SpriteSet | undefined>,
) {
  const player = runtime.player;
  context.save();
  context.fillStyle = "rgba(22, 32, 50, .18)";
  context.beginPath();
  context.ellipse(player.x, player.y + 3, 34, 7, 0, 0, Math.PI * 2);
  context.fill();
  context.restore();
  const action: ArcadeAction = !player.onGround ? "jump" : Math.abs(player.vx) > 0 ? "run" : "idle";
  const sprite = sprites[action] ?? sprites.idle ?? sprites.walk;
  if (sprite) {
    if (runtime.invulnerableUntil > runtime.elapsed && Math.floor(runtime.elapsed * 14) % 2 === 0) {
      context.globalAlpha = 0.45;
    }
    drawSprite(context, sprite, player.x, player.y, PLAYER_HEIGHT, player.facing, runtime.elapsed);
    context.globalAlpha = 1;
  } else {
    drawFallbackActor(context, player.x, player.y, 38, PLAYER_HEIGHT, "#e2b759");
  }
  if (runtime.guarding && runtime.guardAvailable) {
    context.save();
    context.strokeStyle = "#9edff2";
    context.lineWidth = 3;
    context.globalAlpha = 0.75;
    context.beginPath();
    context.ellipse(player.x, player.y - 88, 48, 94, 0, -Math.PI / 2, Math.PI / 2);
    context.stroke();
    context.restore();
  }
}

function drawEnemy(
  context: CanvasRenderingContext2D,
  enemy: PveRuntimeEnemy,
  runtime: PveRuntime,
  sprites: Record<string, SpriteSet | undefined> | undefined,
) {
  const pose = pveEnemyPose(enemy, runtime.elapsed);
  const sprite = sprites?.[pose] ?? sprites?.[PVE_ACTION_FALLBACK[pose]] ?? sprites?.walk ?? sprites?.idle;
  const attackProgress = enemy.ability && enemy.abilityStage === "active"
    ? Math.max(0, Math.min(0.999, 1 - (enemy.abilityUntil - runtime.elapsed) / PVE_ABILITIES[enemy.ability].active))
    : 0;
  const animationTime = pose === "attack" && sprite
    ? attackProgress * sprite.strip.frames / Math.max(1, sprite.strip.fps ?? 10)
    : pose === "windup" || pose === "death" ? 0 : runtime.elapsed;
  context.save();
  // Dedicated procedural poses remain available when generated slots are absent.
  context.translate(enemy.x, enemy.y);
  if (pose === "windup") context.scale(1.12, 0.88);
  if (pose === "hurt") context.rotate(-enemy.facing * 0.16);
  if (pose === "death") {
    const progress = Math.min(1, (runtime.elapsed - (enemy.deathAt ?? runtime.elapsed)) / 0.6);
    context.rotate(enemy.facing * (0.3 + progress * 1.2));
    context.scale(1, Math.max(0.12, 1 - progress));
  }
  context.translate(-enemy.x, -enemy.y);
  if (sprite) {
    drawSprite(
      context,
      sprite,
      enemy.x,
      enemy.y,
      enemy.display_height,
      enemy.facing,
      animationTime,
    );
  } else {
    drawFallbackActor(
      context,
      enemy.x,
      enemy.y,
      enemy.kind === "boss" ? 68 : 28,
      enemy.display_height,
      enemy.kind === "boss" ? "#6ccde5" : "#7fa25e",
    );
  }
  if (enemy.hitFlashUntil > runtime.elapsed) {
    if (sprite) {
      context.save();
      context.filter = "brightness(3.2) saturate(.15)";
      drawSprite(
        context,
        sprite,
        enemy.x,
        enemy.y,
        enemy.display_height,
        enemy.facing,
        animationTime,
      );
      context.restore();
    } else {
      context.save();
      context.globalCompositeOperation = "screen";
      context.globalAlpha = 0.5;
      context.fillStyle = "#fff5e3";
      context.fillRect(
        enemy.x - enemyHalfWidth(enemy),
        enemy.y - enemyHeight(enemy),
        enemyHalfWidth(enemy) * 2,
        enemyHeight(enemy),
      );
      context.restore();
    }
  }
  context.restore();
  if (pose === "death") return;
  const barWidth = enemy.kind === "boss" ? 190 : 54;
  const barY = enemy.y - enemyHeight(enemy) - 14;
  context.save();
  context.fillStyle = "rgba(21, 30, 47, .78)";
  context.fillRect(enemy.x - barWidth / 2, barY, barWidth, 6);
  context.fillStyle = enemy.kind === "boss" ? "#8be8f7" : "#b7d88d";
  context.fillRect(
    enemy.x - barWidth / 2,
    barY,
    barWidth * Math.max(0, enemy.hp / enemy.max_hp),
    6,
  );
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

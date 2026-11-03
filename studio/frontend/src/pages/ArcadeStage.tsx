import { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import Konva from "konva";
import {
  Circle,
  Ellipse,
  Group,
  Image as KonvaImage,
  Layer,
  Rect,
  Stage,
  Text as KonvaText,
} from "react-konva";
import { useQuery } from "@tanstack/react-query";
import { SelectedAssetBoundary } from "../components/SelectedAssetBoundary";
import { api } from "../api/client";
import {
  Badge,
  Button,
  Card,
  EmptyState,
  PageHeader,
  SafeImage,
  Skeleton,
  cx,
} from "../components/ui";
import { Icon } from "../components/icons";
import { TouchButton, TouchControlsLayer, TouchJoystick, useTouchControls } from "../components/TouchControls";
import { preloadImage } from "../lib/preload";
import {
  backgroundSequenceAt,
  createScrollingBackgroundTexture,
  createPlatformTexture,
  platformMaterialFor,
} from "../lib/sceneVisuals";
import {
  characterGeometry,
  clipDurationMs,
  clipFor,
  clipTable,
  frameMsFor,
  type ClipTable,
} from "../lib/animator";
import { useHeldKeys } from "../lib/keyboard";
import type { CreativeAsset, ParkourScene } from "../types";
import {
  CHAR_HEIGHT,
  CHAR_MAX_WIDTH,
  GROUND_Y,
  REQUIRED_ACTIONS,
  WORLD_HEIGHT,
  buildLevel,
  cameraX,
  collectCoins,
  initialPlayer,
  inspectCharacter,
  isFallen,
  pickAction,
  respawn,
  stepPlayer,
  type ArcadeAction,
  type PlayerState,
} from "../lib/arcade";

Konva.pixelRatio = Math.min(window.devicePixelRatio || 1, 2);

const STAGE_H = WORLD_HEIGHT;
const DEFAULT_STAGE_W = 760;
const FALLBACK_FPS = 10;
const JUMP_QUEUE_MS = 140;
const ATTACK_TAIL_MS = 120;
const MAX_HEARTS = 3;
const HUD_INTERVAL_MS = 100;
const MAX_TICK_S = 0.05;

const ACTION_LABEL: Record<string, string> = {
  idle: "待机",
  walk: "行走",
  run: "奔跑",
  jump: "跳跃",
  attack: "攻击",
};

const ENGINE_LABEL: Record<string, string> = {
  "ai-video": "AI 视频",
  rigged: "骨骼",
  sprite: "整身形变",
  procedural: "程序化",
};

const STATUS_STYLE: Record<
  "pass" | "warn" | "fail",
  { icon: "check" | "alert" | "x"; tone: "success" | "warning" | "danger"; label: string }
> = {
  pass: { icon: "check", tone: "success", label: "通过" },
  warn: { icon: "alert", tone: "warning", label: "待优化" },
  fail: { icon: "x", tone: "danger", label: "需修复" },
};

interface RunResult {
  reached: boolean;
  coins: number;
  falls: number;
  seconds: number;
  avgFps: number;
}

interface HudState {
  x: number;
  action: ArcadeAction;
  coins: number;
  hearts: number;
  seconds: number;
  fps: number;
}

interface PlayerGeometry {
  image: HTMLImageElement;
  frameW: number;
  frameH: number;
  charW: number;
  charH: number;
  frames: number;
  frameMs: number;
}

export default function ArcadeStage() {
  const [params] = useSearchParams();
  const sceneId = params.get("scene");
  return (
    <SelectedAssetBoundary>
      {(asset) => (
        <ArcadeContent
          key={`${asset?.id ?? "unselected"}:${sceneId ?? "classic"}`}
          selected={asset}
        />
      )}
    </SelectedAssetBoundary>
  );
}

function ArcadeContent({ selected }: { selected: CreativeAsset | null }) {
  const [searchParams, setSearchParams] = useSearchParams();
  const navigate = useNavigate();
  const selectedAssetId = selected?.id ?? null;
  const sceneId = searchParams.get("scene");
  const sceneQuery = useQuery({
    queryKey: ["arcade-scene", sceneId],
    queryFn: ({ signal }) => api.getScene(sceneId!, { signal, silent: true }),
    enabled: Boolean(sceneId),
    retry: false,
  });
  const scene =
    sceneQuery.data?.gameplay.type === "parkour"
      ? (sceneQuery.data as ParkourScene)
      : undefined;
  const level = useMemo(
    () =>
      scene?.status === "ready" && scene.gameplay.level
        ? scene.gameplay.level
        : buildLevel(selectedAssetId ?? sceneId ?? "arcade"),
    [scene, selectedAssetId, sceneId],
  );
  const colors = useMemo(
    () => ({
      skyTop: scene?.theme.palette.skyTop ?? "#eef3f8",
      skyBottom: scene?.theme.palette.skyBottom ?? "#e1e8f1",
      ground: scene?.theme.palette.ground ?? "#d7cfbc",
      floating: scene?.theme.palette.floating ?? "#c8d0b6",
      accent: scene?.theme.palette.accent ?? "#d3a13c",
    }),
    [scene],
  );
  const backgroundUrls = useMemo(() => {
    const sequenced = (scene?.theme.background_urls ?? []).filter(Boolean);
    if (sequenced.length > 0) return sequenced;
    return scene?.theme.background_url ? [scene.theme.background_url] : [];
  }, [scene]);
  const materials = useMemo(() => {
    const environment = scene?.intent?.environment ?? "castle";
    const features = scene?.gameplay.features ?? [];
    return {
      ground: platformMaterialFor("ground", colors, environment, features),
      floating: platformMaterialFor("floating", colors, environment, features),
    };
  }, [colors, scene?.gameplay.features, scene?.intent?.environment]);
  const platformTextures = useMemo(
    () => ({
      ground: createPlatformTexture(materials.ground),
      floating: createPlatformTexture(materials.floating),
    }),
    [materials],
  );

  const stageBoxRef = useRef<HTMLDivElement>(null);
  const worldRef = useRef<Konva.Group | null>(null);
  const backgroundFallbackRef = useRef<Konva.Group | null>(null);
  const backgroundFromRef = useRef<Konva.Rect | null>(null);
  const backgroundToRef = useRef<Konva.Rect | null>(null);
  const backgroundFromIndexRef = useRef(-1);
  const backgroundToIndexRef = useRef(-1);
  const charRef = useRef<Konva.Image | null>(null);
  const shadowRef = useRef<Konva.Ellipse | null>(null);
  const stageWRef = useRef(DEFAULT_STAGE_W);

  const playerRef = useRef<PlayerState>(initialPlayer(level));
  const checkpointRef = useRef(level.spawnX);
  const heartsRef = useRef(MAX_HEARTS);
  const fallsRef = useRef(0);
  const elapsedRef = useRef(0);
  const frameCountRef = useRef(0);
  const hudAtRef = useRef(0);
  const lastTickRef = useRef(0);
  const coinsTakenRef = useRef<Set<string>>(new Set());
  const finishedRef = useRef(false);
  const pausedRef = useRef(false);
  const jumpQueuedAtRef = useRef(0);
  const attackUntilRef = useRef(0);
  const frameIdxRef = useRef(0);
  const frameElapsedRef = useRef(0);
  const lastActionRef = useRef<ArcadeAction>("idle");

  const [stageW, setStageW] = useState(DEFAULT_STAGE_W);
  const [images, setImages] = useState<Record<string, HTMLImageElement>>({});
  const [backgroundImages, setBackgroundImages] = useState<HTMLImageElement[]>([]);
  const [loadErrors, setLoadErrors] = useState<string[]>([]);
  const [coinsTaken, setCoinsTaken] = useState<Set<string>>(new Set());
  const [runResult, setRunResult] = useState<RunResult | null>(null);
  const [hud, setHud] = useState<HudState>({
    x: level.spawnX,
    action: "idle",
    coins: 0,
    hearts: MAX_HEARTS,
    seconds: 0,
    fps: 0,
  });
  const [pickerOpen, setPickerOpen] = useState(!selected);
  const backgroundTextures = useMemo(
    () =>
      backgroundImages.map((image) =>
        createScrollingBackgroundTexture(image, stageW, STAGE_H),
      ),
    [backgroundImages, stageW],
  );

  const history = useQuery({
    queryKey: ["arcade-people"],
    queryFn: () => api.listHistory({ kind: "character", limit: 12 }),
    enabled: pickerOpen,
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

  const previews = useQuery({
    queryKey: ["playtest-previews", selectedAssetId],
    queryFn: () => api.playtestPreviews(selectedAssetId!),
    enabled: Boolean(selectedAssetId),
  });

  // 动作表：帧数/帧率按动作各自声明，一次性动作不再借用上一个动作的帧长
  const clips: ClipTable = useMemo(
    () => clipTable(previews.data?.strips, previews.data?.fps ?? FALLBACK_FPS),
    [previews.data],
  );

  const stripUrls = useMemo(() => {
    const data = previews.data;
    const out: Record<string, string> = {};
    if (!data) return out;
    if (data.strips) {
      for (const [name, strip] of Object.entries(data.strips)) {
        if (strip?.url) out[name] = strip.url;
      }
    } else {
      Object.assign(out, data.previews ?? {});
    }
    // 基础试玩不要求额外生成待机；静止时显示行走条带的第一帧即可，避免
    // “少一条 idle 动画就无法进入关卡”这种与核心体验无关的阻断。
    if (!out.idle && out.walk) out.idle = out.walk;
    return out;
  }, [previews.data]);

  const stripList = useMemo(() => Object.entries(stripUrls), [stripUrls]);

  useEffect(() => {
    if (backgroundUrls.length === 0) {
      setBackgroundImages([]);
      return;
    }
    let cancelled = false;
    Promise.all(
      backgroundUrls.map(async (url, index) => {
        const image = await preloadImage(url, index === 0 ? "high" : "low").catch(
          () => null,
        );
        if (!image) return null;
        // 贴图会在开始滚动前合成为 canvas；先等 decode 完成，
        // 避免第一次绘制或背景替换时同步解码造成掉帧。
        await image.decode?.().catch(() => undefined);
        return image;
      }),
    ).then((loaded) => {
      if (!cancelled) {
        setBackgroundImages(
          loaded.filter((image): image is HTMLImageElement => image !== null),
        );
      }
    });
    return () => {
      cancelled = true;
    };
  }, [backgroundUrls]);

  // 全部条带一次性预载并 decode：动作切换零网络请求、零空帧
  useEffect(() => {
    if (stripList.length === 0) return;
    let cancelled = false;
    for (const [name, url] of stripList) {
      preloadImage(url, name === "idle" ? "high" : "low")
        .then((image) => {
          if (cancelled) return;
          setImages((previous) => (previous[name] ? previous : { ...previous, [name]: image }));
        })
        .catch(() => {
          if (cancelled) return;
          setLoadErrors((previous) => (previous.includes(url) ? previous : [...previous, url]));
        });
    }
    return () => {
      cancelled = true;
    };
  }, [stripList]);

  // 舞台宽度自适应；高度固定，世界坐标不随宽度变化
  useEffect(() => {
    const element = stageBoxRef.current;
    if (!element || typeof ResizeObserver === "undefined") return;
    const observer = new ResizeObserver((entries) => {
      const width = Math.round(entries[0].contentRect.width);
      if (width > 0 && width !== stageWRef.current) {
        stageWRef.current = width;
        setStageW(width);
      }
    });
    observer.observe(element);
    return () => observer.disconnect();
  }, []);

  const geometryFor = (action: ArcadeAction): PlayerGeometry | null => {
    const image = images[action];
    const idleImage = images.idle;
    // 目标动作条带未就绪时保持上一帧：拿 idle 图套 run/attack 的帧数，
    // 会把待机画面切成别的动作的帧序（动作串扰的直接来源）
    if (!image || !idleImage) return null;
    const geometry = characterGeometry({
      image,
      clip: clipFor(clips, action),
      baseFrameH: idleImage.naturalHeight,
      targetHeight: CHAR_HEIGHT,
      maxWidth: CHAR_MAX_WIDTH,
    });
    if (!geometry) return null;
    return {
      image,
      frameW: geometry.frameW,
      frameH: geometry.frameH,
      charW: geometry.charW,
      charH: geometry.charH,
      frames: geometry.frames,
      frameMs: frameMsFor(clips, action),
    };
  };

  // 键盘与触控共用同一触发路径：一次性动作 = 入队/置窗口，持续动作 = 键集合
  function triggerKey(key: string) {
    if (key === "arrowup") jumpQueuedAtRef.current = performance.now();
    if (key === " ") {
      // 覆盖窗口按 attack 自己的帧长算，完整播完一套帧再回落
      attackUntilRef.current = performance.now() + clipDurationMs(clips, "attack", ATTACK_TAIL_MS);
    }
  }

  function holdKey(key: string, pressed: boolean) {
    if (pressed) keysRef.current.add(key);
    else keysRef.current.delete(key);
  }

  const keysRef = useHeldKeys(["arrowleft", "arrowright", "arrowup", " "], triggerKey);
  const touch = useTouchControls();

  function finish(reached: boolean) {
    if (finishedRef.current) return;
    finishedRef.current = true;
    pausedRef.current = true;
    const seconds = elapsedRef.current;
    const avgFps = seconds > 0 ? frameCountRef.current / seconds : 0;
    setRunResult({
      reached,
      coins: coinsTakenRef.current.size,
      falls: fallsRef.current,
      seconds,
      avgFps,
    });
  }

  function restart() {
    playerRef.current = initialPlayer(level);
    checkpointRef.current = level.spawnX;
    heartsRef.current = MAX_HEARTS;
    fallsRef.current = 0;
    elapsedRef.current = 0;
    frameCountRef.current = 0;
    hudAtRef.current = 0;
    lastTickRef.current = 0;
    coinsTakenRef.current = new Set();
    setCoinsTaken(new Set());
    finishedRef.current = false;
    pausedRef.current = false;
    jumpQueuedAtRef.current = 0;
    attackUntilRef.current = 0;
    frameIdxRef.current = 0;
    frameElapsedRef.current = 0;
    lastActionRef.current = "idle";
    setRunResult(null);
    setHud({
      x: level.spawnX,
      action: "idle",
      coins: 0,
      hearts: MAX_HEARTS,
      seconds: 0,
      fps: 0,
    });
  }

  // 主循环：rAF 内只写 ref 与 Konva 节点，HUD 每 100ms 同步一次 React
  useEffect(() => {
    if (!images.idle) return;
    backgroundFromIndexRef.current = -1;
    backgroundToIndexRef.current = -1;
    let raf = 0;

    const drawBackground = (playerX: number, camera: number) => {
      if (backgroundTextures.length === 0) {
        backgroundFallbackRef.current?.x(-((camera * 0.35) % stageWRef.current));
        return;
      }
      const frame = backgroundSequenceAt(
        playerX / Math.max(1, level.goalX),
        backgroundTextures.length,
      );
      const tileWidth = Math.max(1, stageW * 2);
      const x = -((camera * 0.35) % tileWidth) - tileWidth;
      const from = backgroundFromRef.current;
      const to = backgroundToRef.current;
      const crossing = frame.to !== frame.from;

      if (from) {
        if (backgroundFromIndexRef.current !== frame.from) {
          from.fillPatternImage(backgroundTextures[frame.from]);
          backgroundFromIndexRef.current = frame.from;
        }
        from.x(x);
        from.opacity(crossing ? 1 - frame.mix : 1);
      }
      if (to) {
        if (crossing && backgroundToIndexRef.current !== frame.to) {
          to.fillPatternImage(backgroundTextures[frame.to]);
          backgroundToIndexRef.current = frame.to;
        }
        to.x(x);
        to.opacity(crossing ? frame.mix : 0);
      }
    };

    const loop = (time: number) => {
      raf = requestAnimationFrame(loop);
      if (finishedRef.current) {
        lastTickRef.current = time;
        return;
      }

      const delta = lastTickRef.current
        ? Math.min((time - lastTickRef.current) / 1000, MAX_TICK_S)
        : 1 / 60;
      lastTickRef.current = time;
      if (pausedRef.current) return;

      elapsedRef.current += delta;
      const jumpQueued =
        jumpQueuedAtRef.current > 0 && time - jumpQueuedAtRef.current < JUMP_QUEUE_MS;

      let next = stepPlayer(
        playerRef.current,
        {
          left: keysRef.current.has("arrowleft"),
          right: keysRef.current.has("arrowright"),
          run: keysRef.current.has("shift"),
          jump: jumpQueued,
        },
        level,
        delta,
      );
      if (!next.onGround) jumpQueuedAtRef.current = 0;
      if (next.onGround) checkpointRef.current = next.x;

      const picked = collectCoins(next, level.coins, coinsTakenRef.current);
      if (picked.length > 0) {
        const updated = new Set(coinsTakenRef.current);
        for (const coin of picked) updated.add(coin.id);
        coinsTakenRef.current = updated;
        setCoinsTaken(updated);
      }

      if (isFallen(next)) {
        fallsRef.current += 1;
        heartsRef.current = Math.max(0, heartsRef.current - 1);
        next = respawn(level, checkpointRef.current);
        if (heartsRef.current <= 0) {
          playerRef.current = next;
          finish(false);
          return;
        }
      }
      playerRef.current = next;

      const attacking = time < attackUntilRef.current;
      const action = pickAction(next, attacking);
      if (action !== lastActionRef.current) {
        lastActionRef.current = action;
        frameIdxRef.current = 0;
        frameElapsedRef.current = 0;
      }

      const geometry = geometryFor(action);
      if (geometry) {
        frameElapsedRef.current += delta * 1000;
        while (frameElapsedRef.current >= geometry.frameMs) {
          frameElapsedRef.current -= geometry.frameMs;
          frameIdxRef.current = (frameIdxRef.current + 1) % geometry.frames;
        }
        const frameIndex = frameIdxRef.current % geometry.frames;
        const node = charRef.current;
        if (node) {
          if (node.image() !== geometry.image) node.image(geometry.image);
          node.position({ x: next.x - geometry.charW / 2, y: next.y - geometry.charH });
          node.size({ width: geometry.charW, height: geometry.charH });
          node.crop({
            x: frameIndex * geometry.frameW,
            y: 0,
            width: geometry.frameW,
            height: geometry.frameH,
          });
          node.scaleX(next.facing);
          node.offsetX(next.facing === -1 ? geometry.charW : 0);
        }
        const shadow = shadowRef.current;
        if (shadow) {
          shadow.position({ x: next.x, y: next.y + 3 });
          shadow.radiusX(geometry.charW * 0.32);
          shadow.opacity(next.onGround ? 0.16 : 0.08);
        }

        if (next.x >= level.goalX) {
          finish(true);
          return;
        }

        frameCountRef.current += 1;
        const camera = cameraX(next.x, stageWRef.current, level.width);
        worldRef.current?.x(-camera);
        drawBackground(next.x, camera);

        if (time - hudAtRef.current >= HUD_INTERVAL_MS) {
          hudAtRef.current = time;
          setHud({
            x: next.x,
            action,
            coins: coinsTakenRef.current.size,
            hearts: heartsRef.current,
            seconds: elapsedRef.current,
            fps: frameCountRef.current / Math.max(elapsedRef.current, 0.001),
          });
        }
      }
    };
    raf = requestAnimationFrame(loop);
    return () => cancelAnimationFrame(raf);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [images, level, clips, backgroundTextures]);

  const previewsData = previews.data;
  const report = useMemo(
    () =>
      inspectCharacter({
        actions: previewsData?.actions ?? [],
        strips: previewsData?.strips ?? {},
        loadErrors,
        runtime: runResult
          ? {
              reachedGoal: runResult.reached,
              falls: runResult.falls,
              coins: runResult.coins,
              totalCoins: level.coins.length,
              avgFps: runResult.avgFps,
            }
          : undefined,
      }),
    [previewsData, loadErrors, runResult, level.coins.length],
  );

  const verdict = runResult ? report.verdict : null;
  const passCount = report.items.filter((item) => item.status === "pass").length;
  const issueCount = report.items.length - passCount;
  const progressPct = Math.min(100, Math.max(0, (hud.x / level.goalX) * 100));
  const idleGeometry = images.idle ? geometryFor("idle") : null;
  // 触控层只在真正可玩的时刻出现，避免盖在载入/空态遮罩上
  const touchReady =
    Boolean(images.idle) &&
    Boolean(selectedAssetId) &&
    !previews.isLoading &&
    !sceneQuery.isLoading &&
    !sceneQuery.isError;
  const initial = initialPlayer(level);
  const goalPlatform = level.platforms.find(
    (platform) => platform.x <= level.goalX && level.goalX <= platform.x + platform.width,
  );
  const goalTop = goalPlatform?.y ?? level.groundY;

  return (
    <div className="mx-auto flex w-full max-w-[1440px] flex-col gap-5 px-4 py-5 md:px-6">
      <PageHeader
        overline="Arcade"
        title={scene?.title || "关卡试玩场"}
        description={
          scene
            ? `${scene.theme.summary} · 跑、跳、收集金币并抵达终点`
            : "把设计好的角色放进一条横向关卡：跑、跳、攻击，通关后自动生成可交付的角色检查报告"
        }
        actions={
          <>
            {scene && (
              <Badge tone="success" icon="grid">
                {scene.gameplay.difficulty === "hard"
                  ? "挑战"
                  : scene.gameplay.difficulty === "easy"
                    ? "轻松"
                    : "标准"}
              </Badge>
            )}
            <Badge tone={selected ? "primary" : "neutral"} icon="zap">
              {selected ? `受检角色 · ${selected.name || selected.id}` : "未选择人物"}
            </Badge>
          </>
        }
      />

      <div className="grid grid-cols-12 items-start gap-4">
        <div className="col-span-12 flex min-w-0 flex-col gap-3 lg:col-span-8">
        <Card
          title="关卡试玩 · 侧卷轴"
          icon="play"
          bodyClassName="p-3"
          right={<Badge tone="neutral">{ACTION_LABEL[hud.action] ?? hud.action}</Badge>}
        >
          <div
            ref={stageBoxRef}
            className="relative overflow-hidden rounded-xl border border-line-subtle bg-surface-1"
          >
            {(!selectedAssetId ||
              previews.isLoading ||
              sceneQuery.isLoading ||
              sceneQuery.isError) && (
              <div className="absolute inset-0 z-10 grid place-items-center bg-surface-1/[.92] backdrop-blur-[2px]">
                {sceneQuery.isError ? (
                  <EmptyState
                    icon="alert"
                    title="场景加载失败"
                    description={
                      sceneQuery.error instanceof Error
                        ? sceneQuery.error.message
                        : "无法读取该场景"
                    }
                    action={
                      <Button
                        variant="secondary"
                        size="sm"
                        icon="refresh"
                        onClick={() => void sceneQuery.refetch()}
                      >
                        重新读取
                      </Button>
                    }
                  />
                ) : sceneQuery.isLoading ? (
                  <div className="flex flex-col items-center gap-2 text-xs text-ink-3">
                    <Icon name="clock" className="h-4 w-4" />
                    正在载入场景路线…
                  </div>
                ) : !selectedAssetId ? (
                  <EmptyState
                    icon="play"
                    title="选一位受检人物"
                    description="从近期生成记录中挑一个角色，进入关卡跑一遍，报告会自动生成。"
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
                  <div className="flex flex-col items-center gap-2 text-xs text-ink-3">
                    <Icon name="clock" className="h-4 w-4" />
                    正在为该人物准备动作条带…
                  </div>
                )}
              </div>
            )}

            <div className="pointer-events-none absolute left-3 top-3 z-[5] flex flex-wrap items-center gap-1.5">
              <HudChip icon="cube" text={`金币 ${coinsTaken.size}/${level.coins.length}`} />
              <HudChip
                icon="zap"
                text={`${hud.hearts}/${MAX_HEARTS}`}
                tone={hud.hearts > 1 ? "normal" : "danger"}
              />
              <HudChip icon="clock" text={`${hud.seconds.toFixed(1)}s`} />
              <HudChip icon="gauge" text={`${Math.round(hud.fps)} fps`} />
            </div>

            <Stage width={stageW} height={STAGE_H}>
              <Layer listening={false}>
                <Rect
                  width={stageW}
                  height={STAGE_H}
                  fillLinearGradientStartPoint={{ x: 0, y: 0 }}
                  fillLinearGradientEndPoint={{ x: 0, y: STAGE_H }}
                  fillLinearGradientColorStops={[
                    0,
                    colors.skyTop,
                    0.68,
                    scene?.theme.palette.skyBottom ?? "#f3f6fa",
                    1,
                    colors.skyBottom,
                  ]}
                />
                {backgroundTextures.length > 0 ? (
                  <>
                    <Rect
                      ref={backgroundFromRef}
                      x={-stageW * 2}
                      y={0}
                      width={stageW * 5}
                      height={STAGE_H}
                      fillPriority="pattern"
                      fillPatternImage={
                        backgroundTextures[0] as unknown as HTMLImageElement
                      }
                      fillPatternRepeat="repeat"
                      opacity={1}
                    />
                    <Rect
                      ref={backgroundToRef}
                      x={-stageW * 2}
                      y={0}
                      width={stageW * 5}
                      height={STAGE_H}
                      fillPriority="pattern"
                      fillPatternImage={
                        backgroundTextures[
                          Math.min(1, backgroundTextures.length - 1)
                        ] as unknown as HTMLImageElement
                      }
                      fillPatternRepeat="repeat"
                      opacity={0}
                    />
                  </>
                ) : (
                  <Group ref={backgroundFallbackRef}>
                    <Ellipse
                      x={260}
                      y={GROUND_Y + 30}
                      radiusX={300}
                      radiusY={150}
                      fill={colors.ground}
                      opacity={0.28}
                    />
                    <Ellipse
                      x={720}
                      y={GROUND_Y + 50}
                      radiusX={260}
                      radiusY={120}
                      fill={colors.floating}
                      opacity={0.24}
                    />
                    <Ellipse
                      x={1180}
                      y={GROUND_Y + 20}
                      radiusX={320}
                      radiusY={160}
                      fill={colors.ground}
                      opacity={0.24}
                    />
                    <Ellipse
                      x={1680}
                      y={GROUND_Y + 46}
                      radiusX={280}
                      radiusY={130}
                      fill={colors.floating}
                      opacity={0.22}
                    />
                    <Ellipse
                      x={2180}
                      y={GROUND_Y + 28}
                      radiusX={300}
                      radiusY={150}
                      fill={colors.ground}
                      opacity={0.2}
                    />
                  </Group>
                )}
                <Group ref={worldRef}>
                  {level.platforms.map((platform, index) => (
                    <Group key={`platform-${index}`}>
                      {platform.kind === "floating" && (
                        <Rect
                          x={platform.x + 8}
                          y={platform.y + platform.height + 3}
                          width={Math.max(0, platform.width - 16)}
                          height={10}
                          fill="#08111f"
                          opacity={0.2}
                          cornerRadius={8}
                        />
                      )}
                      <Rect
                        x={platform.x}
                        y={platform.y}
                        width={platform.width}
                        height={platform.height}
                        fill={materials[platform.kind].base}
                        fillPriority="pattern"
                        fillPatternImage={
                          platformTextures[platform.kind] as unknown as HTMLImageElement
                        }
                        fillPatternRepeat="repeat"
                        cornerRadius={platform.kind === "floating" ? 4 : 0}
                        stroke={materials[platform.kind].joint}
                        strokeWidth={platform.kind === "floating" ? 1 : 0}
                      />
                      <Rect
                        x={platform.x}
                        y={platform.y}
                        width={platform.width}
                        height={platform.kind === "ground" ? 8 : 5}
                        fill={materials[platform.kind].cap}
                        opacity={0.78}
                        cornerRadius={2}
                      />
                    </Group>
                  ))}

                  {level.coins.map((coin) =>
                    coinsTaken.has(coin.id) ? null : (
                      <Group key={coin.id} x={coin.x} y={coin.y}>
                        <Circle radius={9} fill={colors.accent} stroke="#a97a25" strokeWidth={1.5} />
                        <Circle radius={3.4} fill="#f6d98a" />
                      </Group>
                    ),
                  )}

                  <Group x={level.goalX} y={goalTop - 122}>
                    <Rect
                      x={-3}
                      width={6}
                      height={122}
                      fill={colors.ground}
                      cornerRadius={2}
                    />
                    <Rect x={2} y={4} width={56} height={34} fill={colors.accent} cornerRadius={3} />
                    <KonvaText x={10} y={13} text="终点" fontSize={14} fill="#fbf9f4" />
                  </Group>

                  <Ellipse
                    ref={shadowRef}
                    x={initial.x}
                    y={initial.y + 3}
                    radiusX={40}
                    radiusY={7}
                    fill="#25345a"
                    opacity={0.16}
                  />
                  {idleGeometry ? (
                    <KonvaImage
                      ref={charRef}
                      image={idleGeometry.image}
                      x={initial.x - idleGeometry.charW / 2}
                      y={initial.y - idleGeometry.charH}
                      width={idleGeometry.charW}
                      height={idleGeometry.charH}
                      crop={{ x: 0, y: 0, width: idleGeometry.frameW, height: idleGeometry.frameH }}
                      imageSmoothingEnabled={false}
                    />
                  ) : null}
                </Group>
              </Layer>
            </Stage>

            {/* 触屏设备：虚拟摇杆 + 跳跃/攻击/奔跑 */}
            {touch && touchReady && (
              <TouchControlsLayer
                joystick={
                  <TouchJoystick
                    onDirection={(direction, pressed) => {
                      // 侧卷轴只需要左右移动；上推等同于跳跃
                      if (direction === "up") {
                        if (pressed) triggerKey("arrowup");
                        return;
                      }
                      if (direction === "left" || direction === "right") {
                        holdKey(`arrow${direction}`, pressed);
                      }
                    }}
                  />
                }
              >
                <TouchButton label="跳" tone="primary" onPress={() => triggerKey("arrowup")} />
                <TouchButton label="攻" onPress={() => triggerKey(" ")} />
                <TouchButton
                  label="跑"
                  onPress={() => holdKey("shift", true)}
                  onRelease={() => holdKey("shift", false)}
                />
              </TouchControlsLayer>
            )}

            {runResult && (
              <div className="absolute inset-0 z-20 grid place-items-center bg-canvas/[.86] backdrop-blur-[2px]">
                <div className="w-[min(360px,88%)] rounded-xl border border-line bg-surface-1 p-5 text-center shadow-lg">
                  <span
                    className={cx(
                      "mx-auto grid h-10 w-10 place-items-center rounded-full",
                      runResult.reached ? "bg-success/15 text-success" : "bg-danger/15 text-danger",
                    )}
                  >
                    <Icon name={runResult.reached ? "check" : "x"} className="h-5 w-5" />
                  </span>
                  <h3 className="mt-2.5 text-[15px] font-semibold text-ink">
                    {runResult.reached ? (scene ? "闯关完成" : "检查完成") : "本轮终止"}
                  </h3>
                  <p className="mt-1 text-[11.5px] leading-[18px] text-ink-3">
                    金币 {runResult.coins}/{level.coins.length} · 掉落 {runResult.falls} 次 · 用时{" "}
                    {runResult.seconds.toFixed(1)}s · 平均 {Math.round(runResult.avgFps)} fps
                  </p>
                  <div className="mt-3 flex flex-wrap items-center justify-center gap-2">
                    <Button variant="primary" size="sm" icon="refresh" onClick={restart}>
                      再跑一次
                    </Button>
                    {scene && (
                      <Button variant="secondary" size="sm" icon="grid" onClick={() => navigate("/scenes")}>
                        返回场景工坊
                      </Button>
                    )}
                    <Button
                      variant="secondary"
                      size="sm"
                      icon="gauge"
                      onClick={() =>
                        navigate(`/asset?asset=${encodeURIComponent(selectedAssetId ?? "")}`)
                      }
                    >
                      查看资产档案
                    </Button>
                  </div>
                </div>
              </div>
            )}
          </div>

        </Card>

        {/* ── 关卡控制条 ────────────────────────────────────────────── */}
        <section
          aria-label="关卡控制"
          className="overflow-hidden rounded-lg border border-line bg-paper shadow-e1"
        >
          <header className="flex flex-wrap items-center gap-2 border-b border-line-subtle bg-surface-1/40 px-3.5 py-2.5">
            <h2 className="text-[13px] font-semibold text-ink">关卡控制</h2>
            <span className="cf-ref">Run Control</span>
            <span className="ml-auto font-mono text-[11px] text-ink-3">
              进度 {Math.round(progressPct)}%
            </span>
          </header>
          <div className="p-3">
            <div className="flex flex-wrap items-center gap-2">
              <Button
                variant="primary"
                size="sm"
                icon="refresh"
                onClick={restart}
                disabled={!selected}
              >
                重新开始
              </Button>
              <Button
                variant="secondary"
                size="sm"
                icon="cube"
                onClick={() => setPickerOpen(true)}
              >
                选择受检人物
              </Button>
              <span className="text-[11px] text-ink-4 pointer-coarse:hidden">
                ← → 移动 · Shift 奔跑 · ↑ 跳跃 · 空格 攻击
              </span>
              <span className="hidden text-[11px] text-ink-4 pointer-coarse:inline">
                触屏操作：左下摇杆移动，右下按钮跳跃 / 攻击 / 奔跑
              </span>
            </div>
            <div
              className="mt-2.5 h-1.5 overflow-hidden rounded-full bg-ink/[.08]"
              role="progressbar"
              aria-label="关卡推进进度"
              aria-valuemin={0}
              aria-valuemax={100}
              aria-valuenow={Math.round(progressPct)}
            >
              <div
                className="h-full rounded-full bg-primary/70"
                style={{ width: `${Math.max(2, progressPct)}%` }}
              />
            </div>
            <p className="mt-1.5 text-[10.5px] text-ink-4">
              掉进坑里会回到最近落点，三次掉落本轮终止；通关后自动生成本轮检查报告。
            </p>
            {scene?.generation.warnings.length ? (
              <p className="mt-1.5 text-[10.5px] leading-4 text-warning">
                {scene.generation.warnings.join("；")}
              </p>
            ) : null}
          </div>
        </section>
        </div>

        <div className="col-span-12 grid grid-cols-1 content-start gap-3 sm:grid-cols-2 lg:col-span-4 lg:grid-cols-1">
          <Card
            title="角色检查报告"
            icon="check"
            bodyClassName="p-4"
            right={
              verdict ? (
                <Badge tone={STATUS_STYLE[verdict].tone}>{STATUS_STYLE[verdict].label}</Badge>
              ) : (
                <Badge tone="neutral">跑一遍后补齐运行项</Badge>
              )
            }
          >
            <div className="mb-3 flex flex-wrap gap-1.5" aria-label="报告汇总">
              <Badge tone="success" icon="check">通过 {passCount}</Badge>
              {issueCount > 0 && <Badge tone="warning" icon="alert">待处理 {issueCount}</Badge>}
            </div>
            <ul className="flex flex-col gap-2.5">
              {report.items.map((item) => {
                const style = STATUS_STYLE[item.status];
                return (
                  <li key={item.key} className="flex gap-2.5">
                    <span
                      className={cx(
                        "mt-0.5 grid h-5 w-5 shrink-0 place-items-center rounded-full",
                        item.status === "pass"
                          ? "bg-success/15 text-success"
                          : item.status === "warn"
                            ? "bg-warning/15 text-warning"
                            : "bg-danger/15 text-danger",
                      )}
                    >
                      <Icon name={style.icon} className="h-3 w-3" />
                    </span>
                    <div className="min-w-0">
                      <div className="flex items-center gap-1.5">
                        <span className="text-[12.5px] font-medium text-ink">{item.label}</span>
                        <span className="text-[10.5px] text-ink-4">{style.label}</span>
                      </div>
                      <p className="mt-0.5 text-[11px] leading-[16px] text-ink-3">{item.detail}</p>
                    </div>
                  </li>
                );
              })}
            </ul>
            <p className="mt-3 flex items-center gap-1.5 text-[11px] text-ink-4">
              <Icon name="clock" className="h-3 w-3" />
              报告按「实跑结果」判定：动作覆盖与尺寸来自条带元信息，运行项来自本轮关卡。
            </p>
          </Card>

          <Card title="角色清单 Asset Manifest" icon="grid" bodyClassName="p-3">
            <div className="flex flex-col gap-1">
              <div className="grid grid-cols-[1fr_44px_44px_52px] gap-2 px-2 text-[10px] uppercase tracking-[0.08em] text-ink-4">
                <span>动作</span>
                <span className="text-right">帧</span>
                <span className="text-right">fps</span>
                <span className="text-right">引擎</span>
              </div>
              {REQUIRED_ACTIONS.map((action) => {
                const strip = previews.data?.strips?.[action];
                const present = Boolean(strip) || Boolean(previews.data?.previews?.[action]);
                return (
                  <div
                    key={action}
                    className="grid grid-cols-[1fr_44px_44px_52px] items-center gap-2 rounded-md px-2 py-1.5 text-[11.5px] odd:bg-surface-1"
                  >
                    <span className="flex items-center gap-1.5 text-ink-2">
                      {ACTION_LABEL[action]}
                      {!present && <Badge tone="danger">缺</Badge>}
                    </span>
                    <span className="text-right font-mono text-ink-3">
                      {strip?.frames ?? (present ? 8 : "—")}
                    </span>
                    <span className="text-right font-mono text-ink-3">
                      {strip?.fps ?? previews.data?.fps ?? "—"}
                    </span>
                    <span className="text-right text-[10.5px] text-ink-4">
                      {strip?.engine
                        ? (ENGINE_LABEL[strip.engine] ?? strip.engine)
                        : present
                          ? (ENGINE_LABEL[previews.data?.source ?? ""] ??
                            previews.data?.source ??
                            "—")
                          : "—"}
                    </span>
                  </div>
                );
              })}
            </div>
          </Card>
        </div>
      </div>

      {pickerOpen && (
        <Card
          title="选择受检人物 · 近期生成"
          icon="cube"
          bodyClassName="p-3"
          right={
            <Button variant="ghost" size="sm" onClick={() => setPickerOpen(false)}>
              收起
            </Button>
          }
        >
          {history.isLoading ? (
            <div className="grid grid-cols-2 gap-2.5 sm:grid-cols-4 lg:grid-cols-6">
              {Array.from({ length: 6 }, (_, index) => (
                <Skeleton key={index} className="h-[132px] rounded-lg" />
              ))}
            </div>
          ) : people.length === 0 ? (
            <EmptyState
              icon="cube"
              title="还没有可用的人物"
              description="先去工作台生成一个角色，再回到这里进入关卡检查。"
              action={
                <Button variant="primary" size="sm" icon="spark" onClick={() => navigate("/workspace")}>
                  去工作台生成
                </Button>
              }
            />
          ) : (
            <div className="grid grid-cols-2 gap-2.5 sm:grid-cols-4 lg:grid-cols-6">
              {people.map((record) => (
                <button
                  key={record.id}
                  onClick={() => {
                    setSearchParams((previous) => {
                      const next = new URLSearchParams(previous);
                      next.set("asset", record.asset_id!);
                      return next;
                    });
                    setPickerOpen(false);
                  }}
                  className={cx(
                    "flex flex-col overflow-hidden rounded-lg border bg-canvas text-left transition-[border-color,box-shadow] duration-(--motion-fast) ease-standard",
                    selected?.id === record.asset_id
                      ? "border-primary/60 shadow-e1"
                      : "border-line-subtle hover:border-line",
                  )}
                >
                  <SafeImage
                    src={record.image?.url ?? undefined}
                    alt={String(record.name ?? record.asset_id ?? "")}
                    className="h-[104px] w-full bg-paper object-contain"
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

function HudChip({
  icon,
  text,
  tone = "normal",
}: {
  icon: "cube" | "zap" | "clock" | "gauge";
  text: string;
  tone?: "normal" | "danger";
}) {
  return (
    <span
      className={cx(
        "inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[10.5px] font-medium backdrop-blur-sm",
        tone === "danger"
          ? "border-danger/40 bg-danger/10 text-danger"
          : "border-line/70 bg-canvas/70 text-ink-2",
      )}
    >
      <Icon name={icon} className="h-3 w-3" />
      {text}
    </span>
  );
}

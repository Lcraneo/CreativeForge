import { useEffect, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import { api } from "../api/client";
import { Icon } from "../components/icons";
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
import { platformMaterialFor, type PlatformMaterial } from "../lib/sceneVisuals";
import type { GameScene, ScenePalette, SceneSummary } from "../types";

const EXAMPLES = [
  "雪夜古堡，冰面高台和长距离跳跃，中等难度",
  "黄昏浮空岛，连续上升平台，节奏轻快",
  "熔岩工厂，狭窄断桥，高难度短关卡",
];

const STAGE_LABEL: Record<string, string> = {
  interpreting: "理解场景主题",
  compiling: "搭建跑酷路线",
  background: "绘制场景背景",
  ready: "场景已就绪",
  failed: "生成失败",
  interrupted: "任务已中断",
};

const DIFFICULTY_LABEL = {
  easy: "轻松",
  normal: "标准",
  hard: "挑战",
} as const;
const EXPECTED_BACKGROUNDS = { short: 3, medium: 5, long: 7 } as const;

export default function SceneStudio() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [prompt, setPrompt] = useState("");
  const [difficulty, setDifficulty] = useState<"easy" | "normal" | "hard">("normal");
  const [activeId, setActiveId] = useState<string | null>(null);

  const scenes = useQuery({
    queryKey: ["scenes"],
    queryFn: () => api.listScenes(20),
  });

  const active = useQuery({
    queryKey: ["scene", activeId],
    queryFn: ({ signal }) => api.getScene(activeId!, { signal, silent: true }),
    enabled: Boolean(activeId),
    refetchInterval: (query) =>
      query.state.data?.status === "generating" ? 1200 : false,
  });

  const create = useMutation({
    mutationFn: () => api.createScene(prompt.trim(), difficulty),
    onSuccess: (result) => {
      setActiveId(result.scene_id);
      void queryClient.invalidateQueries({ queryKey: ["scenes"] });
    },
  });
  const retryBackground = useMutation({
    mutationFn: (sceneId: string) => api.retrySceneBackground(sceneId),
    onSuccess: (result) => {
      void queryClient.invalidateQueries({ queryKey: ["scene", result.scene_id] });
    },
  });

  useEffect(() => {
    if (active.data?.status === "ready") {
      void queryClient.invalidateQueries({ queryKey: ["scenes"] });
    }
  }, [active.data?.status, queryClient]);

  const scene = active.data ?? null;
  const generating = create.isPending || scene?.status === "generating";
  const canCreate = prompt.trim().length > 0 && !generating;

  function submit() {
    if (!canCreate) return;
    create.mutate();
  }

  return (
    <div className="mx-auto flex w-full max-w-[1440px] flex-col gap-5 px-4 py-5 md:px-6">
      <PageHeader
        overline="Scene Atelier"
        title="场景工坊"
        description="描述想去的世界，生成一条可玩的横版跑酷路线。场景完成后选择已有角色，直接从场景工坊进入关卡。"
        actions={
          <Badge tone="primary" icon="spark">
            百炼 · 场景策划 + 背景生成
          </Badge>
        }
      />

      <div className="grid grid-cols-12 items-start gap-4">
        <div className="col-span-12 lg:col-span-5">
          <Card title="描述你的关卡" icon="spark" bodyClassName="p-4">
            <label htmlFor="scene-prompt" className="text-[12px] font-medium text-ink-2">
              想进入什么样的世界？
            </label>
            <textarea
              id="scene-prompt"
              value={prompt}
              onChange={(event) => setPrompt(event.target.value)}
              maxLength={2000}
              rows={6}
              placeholder="例如：月光下的漂浮城堡，连续上升平台和长距离跳跃，中等难度"
              className="mt-2 w-full resize-y rounded-md border border-line bg-canvas px-3 py-2.5 text-[13px] leading-6 text-ink outline-none transition-colors placeholder:text-ink-4 focus:border-primary/60"
              onKeyDown={(event) => {
                if ((event.ctrlKey || event.metaKey) && event.key === "Enter") submit();
              }}
            />
            <div className="mt-1.5 flex items-center justify-between text-[10.5px] text-ink-4">
              <span>Ctrl / ⌘ + Enter 开始生成</span>
              <span className="font-mono">{prompt.length}/2000</span>
            </div>

            <fieldset className="mt-4">
              <legend className="text-[12px] font-medium text-ink-2">难度</legend>
              <div className="mt-2 grid grid-cols-3 gap-2">
                {(Object.keys(DIFFICULTY_LABEL) as Array<keyof typeof DIFFICULTY_LABEL>).map(
                  (value) => (
                    <button
                      key={value}
                      type="button"
                      aria-pressed={difficulty === value}
                      onClick={() => setDifficulty(value)}
                      className={cx(
                        "rounded-md border px-2 py-2 text-[12px] transition-colors",
                        difficulty === value
                          ? "border-primary/60 bg-primary-tint font-semibold text-primary"
                          : "border-line bg-canvas text-ink-2 hover:border-line-strong hover:bg-surface-1",
                      )}
                    >
                      {DIFFICULTY_LABEL[value]}
                    </button>
                  ),
                )}
              </div>
            </fieldset>

            <div className="mt-4 rounded-md border border-line-subtle bg-surface-1/55 p-3">
              <div className="flex items-center gap-2 text-[11.5px] font-medium text-ink-2">
                <span className="grid h-5 w-5 place-items-center rounded-full bg-primary/10 text-primary">
                  <Icon name="play" className="h-3 w-3" />
                </span>
                跑酷
                <Badge tone="success">首版可用</Badge>
                <span className="ml-auto text-[10.5px] text-ink-4">PVE 即将开放</span>
              </div>
              <p className="mt-1.5 text-[10.5px] leading-4 text-ink-4">
                生成奔跑、跳跃、金币与终点路线；平台坐标由确定性编译器生成并经过连通性检查。
              </p>
            </div>

            <Button
              variant="primary"
              icon="spark"
              loading={generating}
              disabled={!canCreate}
              onClick={submit}
              className="mt-4 w-full"
            >
              {generating ? "正在构建场景" : "生成跑酷场景"}
            </Button>
            {create.error && (
              <p className="mt-2 text-[11px] leading-4 text-danger">
                {create.error instanceof Error ? create.error.message : "创建场景失败"}
              </p>
            )}

            <div className="mt-4 border-t border-line-subtle pt-3">
              <div className="cf-ref">试试这些</div>
              <div className="mt-2 flex flex-col gap-1.5">
                {EXAMPLES.map((example) => (
                  <button
                    key={example}
                    type="button"
                    onClick={() => setPrompt(example)}
                    className="rounded-sm px-1 py-1 text-left text-[11px] leading-4 text-ink-3 hover:bg-surface-1 hover:text-ink"
                  >
                    {example}
                  </button>
                ))}
              </div>
            </div>
          </Card>
        </div>

        <div className="col-span-12 lg:col-span-7">
          {active.isLoading ? (
            <Card title="场景预览" icon="grid" bodyClassName="p-4">
              <Skeleton className="h-56 w-full rounded-lg" />
              <Skeleton className="mt-3 h-16 w-full" />
            </Card>
          ) : active.error ? (
            <Card title="场景预览" icon="grid" bodyClassName="p-4">
              <EmptyState
                icon="alert"
                title="无法读取场景"
                description={active.error instanceof Error ? active.error.message : "请稍后重试"}
                action={
                  <Button variant="secondary" icon="refresh" onClick={() => active.refetch()}>
                    重新读取
                  </Button>
                }
              />
            </Card>
          ) : scene ? (
            <ScenePreview
              scene={scene}
              onPlay={() => navigate(`/arcade?scene=${encodeURIComponent(scene.id)}`)}
              onRetryBackground={() => retryBackground.mutate(scene.id)}
              retryingBackground={retryBackground.isPending}
              onRetry={() => {
                setPrompt(scene.prompt);
                setDifficulty(scene.gameplay.difficulty);
                create.reset();
              }}
            />
          ) : (
            <Card title="场景预览" icon="grid" bodyClassName="p-4">
              <EmptyState
                icon="grid"
                title="还没有生成场景"
                description="在左侧写下场景主题和玩法偏好。生成期间会依次解析主题、编译路线、绘制背景并检查连通性。"
              />
            </Card>
          )}
        </div>
      </div>

      <Card
        title="最近的场景"
        icon="clock"
        bodyClassName="p-3"
        right={<Badge tone="neutral">{scenes.data?.scenes.length ?? 0} 个</Badge>}
      >
        {scenes.isLoading ? (
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-3">
            {Array.from({ length: 3 }, (_, index) => (
              <Skeleton key={index} className="h-40 rounded-lg" />
            ))}
          </div>
        ) : (scenes.data?.scenes.length ?? 0) === 0 ? (
          <EmptyState
            icon="spark"
            title="场景库还是空的"
            description="生成后的场景会保存在这里，重启服务后仍然可以继续游玩。"
          />
        ) : (
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-3">
            {scenes.data?.scenes.map((item) => (
              <SceneCard
                key={item.id}
                scene={item}
                active={item.id === activeId}
                onOpen={() => setActiveId(item.id)}
              />
            ))}
          </div>
        )}
      </Card>
    </div>
  );
}

function ScenePreview({
  scene,
  onPlay,
  onRetryBackground,
  retryingBackground,
  onRetry,
}: {
  scene: GameScene;
  onPlay: () => void;
  onRetryBackground: () => void;
  retryingBackground: boolean;
  onRetry: () => void;
}) {
  const palette = paletteFor(scene);
  const backgroundUrls = scene.theme.background_urls?.length
    ? scene.theme.background_urls
    : scene.theme.background_url
      ? [scene.theme.background_url]
      : [];
  if (scene.status === "generating") {
    return (
      <Card title={scene.title} icon="grid" bodyClassName="p-4">
        <div className="grid min-h-60 place-items-center rounded-lg border border-line-subtle bg-[radial-gradient(circle_at_50%_20%,rgba(91,121,166,.18),transparent_62%)] p-6 text-center">
          <div>
            <span className="mx-auto grid h-12 w-12 place-items-center rounded-full border border-primary/25 bg-primary/10 text-primary">
              <Icon name="spark" className="h-5 w-5 animate-pulse" />
            </span>
            <h2 className="mt-3 font-serif text-[20px] font-black text-ink">
              {STAGE_LABEL[scene.generation.stage] ?? "正在构建场景"}
            </h2>
            <p className="mt-1 max-w-md text-[11.5px] leading-5 text-ink-3">
              正在使用百炼对话模型解析提示词，随后生成本地路线与背景。
            </p>
            {scene.generation.background_total ? (
              <p className="mt-1 font-mono text-[10.5px] text-primary">
                背景 {scene.generation.background_done ?? 0}/
                {scene.generation.background_total}
              </p>
            ) : null}
            <div className="mx-auto mt-4 flex max-w-sm items-center gap-1.5">
              {["interpreting", "compiling", "background", "ready"].map((stage, index) => {
                const current = ["interpreting", "compiling", "background", "ready"].indexOf(
                  scene.generation.stage,
                );
                return (
                  <span
                    key={stage}
                    className={cx(
                      "h-1.5 flex-1 rounded-full",
                      index <= current ? "bg-primary/70" : "bg-ink/10",
                    )}
                  />
                );
              })}
            </div>
          </div>
        </div>
      </Card>
    );
  }

  if (scene.status === "failed") {
    return (
      <Card
        title={scene.title}
        icon="grid"
        right={<Badge tone="danger" icon="x">生成失败</Badge>}
        bodyClassName="p-4"
      >
        <EmptyState
          icon="alert"
          title="场景没有生成完成"
          description={scene.error || "模型调用或关卡校验失败"}
          action={
            <Button variant="secondary" icon="refresh" onClick={onRetry}>
              带回提示词重试
            </Button>
          }
        />
      </Card>
    );
  }

  return (
    <Card
      title={scene.title}
      icon="grid"
      right={<Badge tone="success" icon="check">可游玩</Badge>}
      bodyClassName="p-3"
    >
      <div className="relative aspect-[16/9] overflow-hidden rounded-lg border border-line-subtle bg-surface-1">
        <SafeImage
          src={backgroundUrls[0]}
          alt={`${scene.title} 场景背景`}
          className="h-full w-full object-contain"
        />
        <div
          className="pointer-events-none absolute inset-x-0 top-0 h-20 bg-[linear-gradient(180deg,rgba(20,27,42,.6),transparent)]"
          aria-hidden="true"
        />
        <div className="absolute left-3 top-3 flex flex-wrap gap-1.5">
          <Badge tone="neutral">{DIFFICULTY_LABEL[scene.gameplay.difficulty]}</Badge>
          <Badge tone="neutral">金币 {scene.gameplay.level?.coins.length ?? 0}</Badge>
          <Badge tone="neutral">背景 {backgroundUrls.length} 张</Badge>
          <Badge tone="neutral">{(scene.generation.duration_ms / 1000).toFixed(1)}s</Badge>
        </div>
        {!scene.theme.background_url && (
          <div className="absolute inset-0 grid place-items-center bg-paper/45 p-4 text-center backdrop-blur-[1px]">
            <span className="rounded-md border border-warning/40 bg-paper/90 px-3 py-2 text-[11px] text-warning">
              背景生成失败，关卡使用主题色降级显示
            </span>
          </div>
        )}
      </div>

      {backgroundUrls.length > 1 && (
        <div className="mt-2 grid grid-cols-3 gap-1.5 sm:grid-cols-5 lg:grid-cols-7">
          {backgroundUrls.map((url, index) => (
            <div
              key={url}
              className="relative aspect-video overflow-hidden rounded-sm border border-line-subtle bg-surface-1"
            >
              <SafeImage
                src={url}
                alt={`${scene.title} 背景 ${index + 1}`}
                className="h-full w-full object-contain"
              />
              <span className="absolute bottom-0.5 right-1 font-mono text-[8px] text-paper drop-shadow">
                {index + 1}
              </span>
            </div>
          ))}
        </div>
      )}

      <div className="mt-3 rounded-md border border-line-subtle bg-canvas p-2.5">
        <SceneRoutePreview scene={scene} palette={palette} />
      </div>

      <p className="mt-3 text-[12px] leading-5 text-ink-2">{scene.theme.summary}</p>
      <div className="mt-2 flex flex-wrap gap-1.5">
        {scene.gameplay.features?.map((feature) => (
          <Badge key={feature} tone="neutral">
            {featureLabel(feature)}
          </Badge>
        ))}
        <Badge tone="success" icon="check">
          路线连通 · 最大间隙 {scene.gameplay.validation?.max_gap ?? 0}px
        </Badge>
      </div>
      {scene.generation.warnings.length > 0 && (
        <p className="mt-2 text-[10.5px] leading-4 text-warning">
          {scene.generation.warnings.join("；")}
        </p>
      )}
      <div className="mt-4 flex flex-wrap items-center gap-2">
        <Button variant="primary" icon="play" onClick={onPlay}>
          选择人物开始闯关
        </Button>
        {backgroundUrls.length <
          EXPECTED_BACKGROUNDS[scene.gameplay.length ?? "medium"] && (
          <Button
            variant="secondary"
            size="sm"
            icon="refresh"
            loading={retryingBackground}
            onClick={onRetryBackground}
          >
            生成连续背景
          </Button>
        )}
        <span className="text-[10.5px] text-ink-4">
          {scene.generation.chat_model ?? "对话模型"} · 路线已通过可玩性检查
        </span>
      </div>
    </Card>
  );
}

function SceneCard({
  scene,
  active,
  onOpen,
}: {
  scene: SceneSummary;
  active: boolean;
  onOpen: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onOpen}
      className={cx(
        "overflow-hidden rounded-lg border bg-canvas text-left transition-[border-color,box-shadow,transform] duration-(--motion-fast) hover:-translate-y-0.5 hover:shadow-e1",
        active ? "border-primary/60 shadow-e1" : "border-line-subtle hover:border-line",
      )}
    >
      <SafeImage
        src={scene.background_url}
        alt={`${scene.title} 场景缩略图`}
        className="h-28 w-full bg-surface-1 object-contain"
      />
      <div className="p-2.5">
        <div className="flex items-center gap-2">
          <strong className="truncate text-[12.5px] text-ink">{scene.title}</strong>
          <span className="ml-auto shrink-0">
            <Badge tone={scene.status === "ready" ? "success" : "neutral"}>
              {scene.status === "ready" ? "可玩" : STAGE_LABEL[scene.stage] ?? scene.status}
            </Badge>
          </span>
        </div>
        <p className="mt-1 line-clamp-2 text-[10.5px] leading-4 text-ink-4">{scene.prompt}</p>
        <div className="mt-2 flex items-center gap-2 text-[10px] text-ink-4">
          <span>{DIFFICULTY_LABEL[scene.difficulty]}</span>
          <span>·</span>
          <span>{scene.coin_count} 金币</span>
          <span>·</span>
          <span>{scene.background_count ?? 1} 背景</span>
        </div>
      </div>
    </button>
  );
}

function SceneRoutePreview({
  scene,
  palette,
}: {
  scene: GameScene;
  palette: ScenePalette;
}) {
  const level = scene.gameplay.level;
  if (!level) return null;
  const environment = scene.intent?.environment ?? "castle";
  const features = scene.gameplay.features ?? [];
  const groundMaterial = platformMaterialFor("ground", palette, environment, features);
  const floatingMaterial = platformMaterialFor("floating", palette, environment, features);
  const groundPattern = `ground-${scene.id}`;
  const floatingPattern = `floating-${scene.id}`;
  return (
    <svg
      viewBox={`0 0 ${level.width} ${420}`}
      role="img"
      aria-label={`${scene.title} 路线缩略图`}
      className="h-20 w-full"
      preserveAspectRatio="none"
    >
      <defs>
        <PlatformTexturePattern id={groundPattern} material={groundMaterial} />
        <PlatformTexturePattern id={floatingPattern} material={floatingMaterial} />
      </defs>
      <rect width={level.width} height="420" fill={palette.skyBottom} opacity="0.16" />
      {level.platforms.map((platform, index) => (
        <g key={`p-${index}`}>
          {platform.kind === "floating" && (
            <rect
              x={platform.x + 8}
              y={platform.y + platform.height + 3}
              width={Math.max(0, platform.width - 16)}
              height="10"
              rx="8"
              fill="#08111f"
              opacity="0.18"
            />
          )}
          <rect
            x={platform.x}
            y={platform.y}
            width={platform.width}
            height={platform.height}
            rx={platform.kind === "floating" ? 6 : 0}
            fill={`url(#${platform.kind === "ground" ? groundPattern : floatingPattern})`}
            stroke={
              platform.kind === "ground"
                ? groundMaterial.joint
                : floatingMaterial.joint
            }
            strokeWidth={platform.kind === "floating" ? 1 : 0}
          />
          <rect
            x={platform.x}
            y={platform.y}
            width={platform.width}
            height={platform.kind === "ground" ? 8 : 5}
            rx="2"
            fill={
              platform.kind === "ground" ? groundMaterial.cap : floatingMaterial.cap
            }
            opacity="0.78"
          />
        </g>
      ))}
      {level.coins.map((coin) => (
        <circle key={coin.id} cx={coin.x} cy={coin.y} r="11" fill={palette.accent} />
      ))}
      <line
        x1={level.goalX}
        x2={level.goalX}
        y1={170}
        y2={level.groundY}
        stroke={palette.accent}
        strokeWidth="10"
      />
    </svg>
  );
}

function PlatformTexturePattern({ id, material }: { id: string; material: PlatformMaterial }) {
  return (
    <pattern id={id} width="180" height="72" patternUnits="userSpaceOnUse">
      <rect width="180" height="72" fill={material.base} />
      {(material.flavor === "stone" ||
        material.flavor === "snow" ||
        material.flavor === "moss") && (
        <path
          d="M0 24H180M0 48H180M45 0V24M135 0V24M90 24V48M30 48V72M150 48V72"
          fill="none"
          stroke={material.joint}
          strokeWidth="2"
          opacity="0.55"
        />
      )}
      {material.flavor === "snow" && (
        <path
          d="M0 0H180V8H0zM18 8a4 4 0 018 0M82 8a3 3 0 016 0M145 8a4 4 0 018 0"
          fill={material.cap}
          opacity="0.72"
        />
      )}
      {material.flavor === "ice" && (
        <g fill="none" stroke={material.highlight} strokeWidth="3" opacity="0.45">
          <path d="M12 62L44 38M62 54L88 34M112 64L142 40" />
          <path d="M0 0H180V6H0z" fill={material.cap} />
        </g>
      )}
      {material.flavor === "moss" && (
        <g fill={material.highlight} opacity="0.65">
          <circle cx="22" cy="14" r="4" />
          <circle cx="68" cy="10" r="3" />
          <circle cx="128" cy="15" r="5" />
        </g>
      )}
      {material.flavor === "lava" && (
        <path
          d="M12 20l14 9 10-4 12 14M74 52l16 8 10-5 12 10M138 18l12 8 14-3"
          fill="none"
          stroke={material.highlight}
          strokeWidth="3"
          opacity="0.72"
        />
      )}
      {material.flavor === "metal" && (
        <g opacity="0.55">
          <path d="M45 0V72M90 0V72M135 0V72" stroke={material.joint} strokeWidth="2" />
          <circle cx="24" cy="16" r="2.5" fill={material.highlight} />
          <circle cx="68" cy="16" r="2.5" fill={material.highlight} />
          <circle cx="114" cy="16" r="2.5" fill={material.highlight} />
          <circle cx="158" cy="16" r="2.5" fill={material.highlight} />
        </g>
      )}
      {material.flavor === "sand" && (
        <g fill="none" stroke={material.highlight} strokeWidth="2" opacity="0.4">
          <path d="M0 18C45 8 90 28 180 18M0 42C50 30 110 52 180 42M0 64C60 54 120 74 180 64" />
        </g>
      )}
    </pattern>
  );
}

function paletteFor(scene: GameScene): ScenePalette {
  const palette = scene.theme.palette;
  return {
    skyTop: palette.skyTop ?? "#18213d",
    skyBottom: palette.skyBottom ?? "#7c8fb5",
    ground: palette.ground ?? "#c9d9e8",
    floating: palette.floating ?? "#9eb5c8",
    accent: palette.accent ?? "#79d6ff",
  };
}

function featureLabel(feature: string) {
  return (
    {
      gaps: "断桥",
      rising_platforms: "上升平台",
      floating_platforms: "浮空平台",
      long_jumps: "长距离跳跃",
      ice_theme: "冰面主题",
    }[feature] ?? feature
  );
}

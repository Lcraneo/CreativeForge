import { useEffect, useRef, useState } from "react";
import { Image as KonvaImage, Layer, Rect, Stage, Text as KonvaText } from "react-konva";
import { useQuery } from "@tanstack/react-query";
import { api } from "../api/client";
import {
  Badge,
  Button,
  Card,
  EmptyState,
  PageHeader,
  cx,
} from "../components/ui";
import { Icon } from "../components/icons";
import { useAssetStore } from "../stores/assetStore";

const FRAME = 96;
const STRIP_FRAMES = 8;
const FPS = 10;
const GROUND = 260;

const ACTION_HINT: Record<string, string> = {
  idle: "待机 · 无操作时自动播放",
  walk: "行走 · ← / →",
  run: "奔跑 · ← / → + Shift",
  attack: "攻击 · 空格",
  jump: "跳跃 · ↑",
};

/** 8 帧横向条带图加载器 */
function useStrip(src: string | undefined) {
  const [image, setImage] = useState<HTMLImageElement | null>(null);
  useEffect(() => {
    if (!src) {
      setImage(null);
      return;
    }
    const element = new window.Image();
    element.src = src;
    element.onload = () => setImage(element);
    return () => {
      element.onload = null;
    };
  }, [src]);
  return image;
}

export default function PlaytestStage() {
  const asset = useAssetStore((state) => state.asset);
  const [action, setAction] = useState("idle");
  const keysRef = useRef<Set<string>>(new Set());
  const [position, setPosition] = useState(200);
  const [facing, setFacing] = useState(1);
  const [frame, setFrame] = useState(0);
  const rafRef = useRef<number>(0);
  const lastRef = useRef<number>(0);
  const attackUntilRef = useRef<number>(0);
  const jumpUntilRef = useRef<number>(0);

  const previews = useQuery({
    queryKey: ["playtest-previews", asset?.id],
    queryFn: () => api.playtestPreviews(asset?.id),
  });

  const strip = useStrip(previews.data?.previews?.[action]);

  // 键盘状态
  useEffect(() => {
    function down(event: KeyboardEvent) {
      const key = event.key.toLowerCase();
      if (["arrowleft", "arrowright", "arrowup", " "].includes(key)) event.preventDefault();
      keysRef.current.add(key);
      if (key === " ") attackUntilRef.current = Date.now() + 700;
      if (key === "arrowup") jumpUntilRef.current = Date.now() + 750;
    }
    function up(event: KeyboardEvent) {
      keysRef.current.delete(event.key.toLowerCase());
    }
    window.addEventListener("keydown", down);
    window.addEventListener("keyup", up);
    return () => {
      window.removeEventListener("keydown", down);
      window.removeEventListener("keyup", up);
    };
  }, []);

  // 主循环：按键盘状态决定动作 + 位移，按 FPS 推进帧
  useEffect(() => {
    const loop = (time: number) => {
      const delta = lastRef.current ? time - lastRef.current : 16;
      lastRef.current = time;

      const keys = keysRef.current;
      const left = keys.has("arrowleft");
      const right = keys.has("arrowright");
      const running = keys.has("shift");
      const attacking = Date.now() < attackUntilRef.current;
      const jumping = Date.now() < jumpUntilRef.current;

      let nextAction = "idle";
      if (attacking) nextAction = "attack";
      else if (jumping) nextAction = "jump";
      else if (left || right) nextAction = running ? "run" : "walk";
      setAction(nextAction);

      if (left !== right) {
        const direction = right ? 1 : -1;
        const moveSpeed = running ? 4.2 : 2.4;
        setFacing(direction);
        setPosition((x) => Math.max(60, Math.min(420, x + direction * moveSpeed * (delta / 16.7))));
      }

      setFrame((f) => (f + (delta / 1000) * FPS) % STRIP_FRAMES);
      rafRef.current = requestAnimationFrame(loop);
    };
    rafRef.current = requestAnimationFrame(loop);
    return () => cancelAnimationFrame(rafRef.current);
  }, []);

  const currentFrame = Math.floor(frame) % STRIP_FRAMES;

  return (
    <div className="mx-auto flex w-full max-w-[1440px] flex-col gap-5 px-4 py-5 md:px-6">
      <PageHeader
        overline="Playtest"
        title="试玩舞台"
        description="用方向键跑起来试一试——素材好不好，跑起来才知道。动作帧来自确定性管线，随资产实时预览"
        actions={<Badge tone="primary" icon="spark">{asset?.name ?? "默认演示角色"}</Badge>}
      />

      <div className="grid grid-cols-12 gap-5">
        <Card
          className="col-span-12 lg:col-span-8"
          title="试玩区 Playtest"
          icon="film"
          right={<Badge tone="neutral">{ACTION_HINT[action]}</Badge>}
        >
          <div className="overflow-hidden rounded-xl border border-line-subtle bg-[#f1efe9]">
            <Stage width={480} height={320}>
              <Layer listening={false}>
                {/* 地面 */}
                <Rect x={0} y={GROUND + FRAME} width={480} height={4} fill="#b9b3a5" />
                {strip ? (
                  <KonvaImage
                    image={strip}
                    x={position - FRAME / 2}
                    y={GROUND}
                    width={FRAME}
                    height={FRAME}
                    crop={{
                      x: currentFrame * FRAME,
                      y: 0,
                      width: FRAME,
                      height: FRAME,
                    }}
                    scaleX={facing}
                    offsetX={facing === -1 ? FRAME : 0}
                  />
                ) : (
                  <KonvaText x={140} y={140} text="加载动作帧…" fontSize={14} fill="#6f7d8c" />
                )}
              </Layer>
            </Stage>
          </div>
          <div className="mt-3 flex flex-wrap items-center gap-2 text-[11.5px] text-ink-3">
            <kbd className="rounded-xs border border-line px-1.5 font-mono text-[10px]">←</kbd>
            <kbd className="rounded-xs border border-line px-1.5 font-mono text-[10px]">→</kbd> 移动
            <kbd className="rounded-xs border border-line px-1.5 font-mono text-[10px]">Shift</kbd> 奔跑
            <kbd className="rounded-xs border border-line px-1.5 font-mono text-[10px]">↑</kbd> 跳跃
            <kbd className="rounded-xs border border-line px-1.5 font-mono text-[10px]">空格</kbd> 攻击
            <span className="ml-auto">点击下方动作卡可直接切换预览</span>
          </div>
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
              {(previews.data?.actions ?? []).map((name) => (
                <button
                  key={name}
                  onClick={() => setAction(name)}
                  className={cx(
                    "flex items-center gap-3 rounded-xl border p-2 text-left transition-all",
                    action === name
                      ? "border-primary/60 bg-primary-tint/40"
                      : "border-line-subtle hover:border-line",
                  )}
                >
                  <span className="min-w-0 flex-1">
                    <span className="block text-[12.5px] font-medium text-ink">
                      {name}
                    </span>
                    <span className="block truncate text-[10.5px] text-ink-3">
                      {ACTION_HINT[name]}
                    </span>
                  </span>
                  {previews.data?.previews?.[name] && (
                    <img
                      src={previews.data.previews[name]}
                      alt={name}
                      loading="lazy"
                      className="h-[48px] rounded-md border border-line-subtle bg-white object-cover"
                      style={{ width: 48 * 4 }}
                    />
                  )}
                </button>
              ))}
            </div>
          )}
          <p className="mt-3 flex items-center gap-1.5 text-[11px] text-ink-4">
            <Icon name="clock" className="h-3 w-3" />
            预览为确定性管线渲染；完整动画请在动画工作台生成 AI 驱动版本。
          </p>
        </Card>
      </div>

      {!asset && (
        <Card>
          <EmptyState
            icon="cube"
            title="还没有当前资产"
            description="先在创作工作台生成一个角色，试玩舞台会加载它的动作帧。也可以先用默认演示角色体验操作。"
          />
        </Card>
      )}
    </div>
  );
}

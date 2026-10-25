/**
 * 试玩舞台 V2 · 原生 Canvas 2D 渲染器
 *
 * 替换本页旧的 react-konva 渲染：rAF 循环内零 React 状态更新——帧游标、
 * 位置、朝向全部由 PlaytestEngine 内部维护，本组件只读快照直接绘制。
 * React 侧的 props（图片表、调试开关等）都是低频变化，每渲染重建
 * 绘制闭包即可（动画运行时整页零重渲染，循环重建成本可忽略）。
 * ResizeObserver 维护 backing size，devicePixelRatio 上限 2，
 * imageSmoothing 关闭保像素锐利。
 */
import { useEffect, useRef } from "react";
import { createFrameLoop, type PlaytestEngine, type PlaytestSnapshot } from "./playtestEngine";
import type { PlaytestStrip } from "../../types";

interface PlaytestCanvasProps {
  engine: PlaytestEngine;
  images: Record<string, HTMLImageElement>;
  /** 含内置动作 + custom:<名称> 的条带元数据（帧数/帧率） */
  strips: Record<string, PlaytestStrip>;
  hasAsset: boolean;
  loading: boolean;
  progress: { ready: number; total: number; pct: number };
  paused: boolean;
  debug: boolean;
}

/* 深色测试台调色板：色值来自 index.css 的 stage-* 设计令牌（同一令牌
 * 也生成 React 壳的 Tailwind 工具类），此处仅做运行时解析 + 兜底 */
interface StagePalette {
  bg: string;
  ground: string;
  groundLine: string;
  debug: string;
  text: string;
  shadow: string;
}

function resolvePalette(): StagePalette {
  const styles = getComputedStyle(document.documentElement);
  const read = (name: string, fallback: string) => styles.getPropertyValue(name).trim() || fallback;
  return {
    bg: read("--color-stage-bg", "#16120d"),
    ground: read("--color-stage-ground", "#1f1a12"),
    groundLine: read("--color-stage-line", "#a9812f"),
    debug: read("--color-stage-debug", "#2f9bb5"),
    text: read("--color-stage-text", "#f2ebdb"),
    shadow: "rgba(12, 9, 5, 0.5)",
  };
}

const MONO_FONT = '12px ui-monospace, SFMono-Regular, Menlo, Consolas, monospace';
const ACTION_FADE_MS = 120;
const GROUND_RATIO = 0.82;
const CHAR_HEIGHT_RATIO = 0.56;
const CHAR_WIDTH_RATIO = 0.42;

export function PlaytestCanvas(props: PlaytestCanvasProps) {
  const { engine } = props;
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const sizeRef = useRef({ w: 0, h: 0 });
  const paletteRef = useRef<StagePalette | null>(null);

  /* ── 尺寸：ResizeObserver 维护 backing size（dpr ≤ 2） ─────────── */
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas || typeof ResizeObserver === "undefined") return;
    const resize = () => {
      const rect = canvas.getBoundingClientRect();
      const w = Math.max(1, Math.round(rect.width));
      const h = Math.max(1, Math.round(rect.height));
      if (sizeRef.current.w === w && sizeRef.current.h === h) return;
      const dpr = Math.min(window.devicePixelRatio || 1, 2);
      sizeRef.current = { w, h };
      canvas.width = Math.round(w * dpr);
      canvas.height = Math.round(h * dpr);
      engine.setStageWidth(w);
    };
    const observer = new ResizeObserver(resize);
    observer.observe(canvas);
    resize();
    return () => observer.disconnect();
  }, [engine]);

  /* ── 绘制主流程：读快照 → 直接画，零 setState ───────────────────── */
  const tick = (now: number) => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    const state = props.paused ? engine.snapshot() : engine.update(now);
    draw(ctx, state, now);
  };

  const draw = (ctx: CanvasRenderingContext2D, state: PlaytestSnapshot, now: number) => {
    const { w, h } = sizeRef.current;
    if (w === 0 || h === 0) return;
    if (!paletteRef.current) paletteRef.current = resolvePalette();
    const palette = paletteRef.current;

    const dpr = canvasRef.current ? canvasRef.current.width / w : 1;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.imageSmoothingEnabled = false;

    // 深色测试台背景 + 地面带 + 地面线
    const groundY = Math.round(h * GROUND_RATIO);
    ctx.fillStyle = palette.bg;
    ctx.fillRect(0, 0, w, h);
    ctx.fillStyle = palette.ground;
    ctx.fillRect(0, groundY, w, h - groundY);
    ctx.fillStyle = palette.groundLine;
    ctx.fillRect(0, groundY - 1, w, 2);

    const image = props.images[state.action];
    if (image && image.naturalWidth > 0) {
      const strip = props.strips[state.action];
      const cropFrames = Math.max(1, strip?.frames ?? 1);
      const cropW = image.naturalWidth / cropFrames;
      // 显示尺寸以 idle 帧高为唯一基准：各动作条带裁边后画布高度不同
      // （sprite 引擎 198~234px 不等），逐条带归一化会让角色在切换
      // 瞬间变大变小；idle 未就绪时回落当前条带
      const idleImage = props.images.idle;
      const baseFrameH =
        idleImage && idleImage.naturalHeight > 0 ? idleImage.naturalHeight : image.naturalHeight;
      const scale = Math.min(
        (h * CHAR_HEIGHT_RATIO) / baseFrameH,
        (w * CHAR_WIDTH_RATIO) / cropW,
      );
      const charW = cropW * scale;
      const charH = image.naturalHeight * scale;

      // 脚底阴影（贴地参照：露出悬空/脚滑问题的关键锚）
      ctx.fillStyle = palette.shadow;
      ctx.beginPath();
      ctx.ellipse(
        state.x,
        groundY,
        Math.max(12, charW * 0.36),
        Math.max(3, charH * 0.035),
        0,
        0,
        Math.PI * 2,
      );
      ctx.fill();

      // 角色：切换淡入 + 朝向镜像 + 像素级裁剪当前帧
      const fade = Math.min(1, (now - state.actionStartedAt) / ACTION_FADE_MS);
      const frameIdx = state.frame % cropFrames;
      ctx.save();
      ctx.globalAlpha = fade;
      ctx.translate(state.x, groundY);
      ctx.scale(state.facing, 1);
      ctx.drawImage(
        image,
        Math.round(frameIdx * cropW),
        0,
        cropW,
        image.naturalHeight,
        -charW / 2,
        -charH,
        charW,
        charH,
      );
      ctx.restore();

      if (props.debug) {
        drawDebugOverlay(
          ctx,
          palette,
          state,
          { x: state.x, top: groundY - charH, w: charW, h: charH },
          cropFrames,
          groundY,
          w,
          h,
        );
      }
    } else {
      drawPlaceholder(ctx, palette, w, h);
    }
  };

  const drawPlaceholder = (
    ctx: CanvasRenderingContext2D,
    palette: StagePalette,
    w: number,
    h: number,
  ) => {
    const centerX = w / 2;
    const centerY = h * 0.42;
    ctx.font = MONO_FONT;
    ctx.textAlign = "center";
    ctx.fillStyle = palette.text;
    if (!props.hasAsset) {
      ctx.fillText("未选择试玩人物", centerX, centerY);
      ctx.fillText("点击右上角「选择人物」从近期生成中挑选", centerX, centerY + 22);
    } else {
      ctx.fillText(
        props.loading ? "正在准备动作数据…" : "动作帧准备中",
        centerX,
        centerY,
      );
      const barW = Math.min(260, w * 0.5);
      const pct = props.progress.total === 0 ? 0 : props.progress.pct / 100;
      ctx.fillStyle = "rgba(242, 235, 219, 0.18)";
      ctx.fillRect(centerX - barW / 2, centerY + 12, barW, 4);
      ctx.fillStyle = palette.groundLine;
      ctx.fillRect(centerX - barW / 2, centerY + 12, barW * pct, 4);
      ctx.fillStyle = palette.text;
      ctx.fillText(`${props.progress.ready}/${props.progress.total} 张条带`, centerX, centerY + 34);
    }
    ctx.textAlign = "left";
  };

  const drawDebugOverlay = (
    ctx: CanvasRenderingContext2D,
    palette: StagePalette,
    state: PlaytestSnapshot,
    bbox: { x: number; top: number; w: number; h: number },
    cropFrames: number,
    groundY: number,
    w: number,
    h: number,
  ) => {
    // 竖向参考网格（每 64px 一条淡青线）
    ctx.strokeStyle = "rgba(47, 155, 181, 0.12)";
    ctx.lineWidth = 1;
    ctx.beginPath();
    for (let gx = 64; gx < w; gx += 64) {
      ctx.moveTo(gx + 0.5, 0);
      ctx.lineTo(gx + 0.5, h);
    }
    ctx.stroke();

    // 角色包围盒（虚线）
    ctx.strokeStyle = palette.debug;
    ctx.setLineDash([4, 3]);
    ctx.strokeRect(bbox.x - bbox.w / 2, bbox.top, bbox.w, bbox.h);
    ctx.setLineDash([]);

    // 脚底锚点十字
    ctx.lineWidth = 2;
    ctx.beginPath();
    ctx.moveTo(state.x - 9, groundY);
    ctx.lineTo(state.x + 9, groundY);
    ctx.moveTo(state.x, groundY - 9);
    ctx.lineTo(state.x, groundY + 9);
    ctx.stroke();

    // 左上指标块（半透明底衬保证可读；真实测量值来自引擎）
    const metrics = engine.getMetrics();
    const lines = [
      `动作 ${state.action} · ${state.mode === "preview" ? "Preview" : "Live"}`,
      `帧 ${state.frame + 1}/${cropFrames}`,
      `FPS ${metrics.fps > 0 ? metrics.fps : "—"} · ${metrics.frameMs > 0 ? metrics.frameMs : "—"}ms`,
    ];
    ctx.font = MONO_FONT;
    const textW = Math.max(...lines.map((line) => ctx.measureText(line).width));
    ctx.fillStyle = "rgba(10, 8, 5, 0.6)";
    ctx.fillRect(10, 10, textW + 16, lines.length * 16 + 10);
    ctx.fillStyle = palette.text;
    lines.forEach((line, i) => ctx.fillText(line, 18, 28 + i * 16));
  };

  /* ── rAF 循环：每渲染重建绘制闭包（父组件低频重渲染，成本可忽略）；
   * 页面隐藏自动停、卸载即停 ──────────────────────────────────────── */
  useEffect(() => {
    const loop = createFrameLoop((now) => tick(now));
    loop.start();
    return () => loop.dispose();
  });

  return (
    <canvas
      ref={canvasRef}
      className="block h-full w-full"
      role="img"
      aria-label="试玩舞台：角色动画实时画面"
      aria-describedby="playtest-stage-help"
    />
  );
}

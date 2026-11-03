/**
 * 动作播放器共用的状态机契约。
 *
 * 三条纪律（PlaytestStage / ArcadeStage 共用）：
 * 1. 帧数、帧率按动作各自查表——不允许用一个全局 frameMs 代表所有动作，
 *    否则 attack/jump 会借用上一个动作的帧长，播到一半就被切开。
 * 2. 一次性动作（attack/jump）的窗口 = 自身帧数 × 自身帧长 + 收尾余量，
 *    循环动作（idle/walk/run）随时可被接管。
 * 3. 显示尺寸以 idle 帧高为唯一基准：各动作条带裁边后的高度不同，
 *    逐动作归一化会让角色在切换瞬间变大变小。
 */
import type { PlaytestStrip } from "../types";

export interface ClipMeta {
  frames: number;
  fps: number;
}

export type ClipTable = Record<string, ClipMeta>;

export const FALLBACK_CLIP: ClipMeta = { frames: 8, fps: 10 };

/** 奔跑步频加快：移动速度与步态频率匹配，避免"脚在地上滑" */
const PLAYBACK_BOOST: Record<string, number> = { run: 1.3 };

export function clipTable(
  strips: Record<string, PlaytestStrip | undefined> | undefined,
  fallbackFps: number,
): ClipTable {
  const table: ClipTable = {};
  for (const [name, strip] of Object.entries(strips ?? {})) {
    table[name] = {
      frames: Math.max(1, strip?.frames ?? FALLBACK_CLIP.frames),
      fps: strip?.fps ?? fallbackFps ?? FALLBACK_CLIP.fps,
    };
  }
  return table;
}

export function clipFor(table: ClipTable, name: string): ClipMeta {
  return table[name] ?? FALLBACK_CLIP;
}

/** 单帧时长：按动作自己的 fps 换算（奔跑按 1.3 倍步频播放）。 */
export function frameMsFor(table: ClipTable, name: string): number {
  const { fps } = clipFor(table, name);
  const boost = PLAYBACK_BOOST[name] ?? 1;
  return 1000 / Math.max(1, fps * boost);
}

/** 将运动方向与素材自身朝向合成 Canvas 水平缩放。
 * 新侧视素材统一朝右；旧素材标记 facing=left 时需要先镜像一次。 */
export function spriteScaleX(
  direction: 1 | -1,
  sourceFacing?: "left" | "right",
): number {
  return direction * (sourceFacing === "left" ? -1 : 1);
}

/** 一次性动作完整播完所需时长（动画本体 + 收尾余量）。 */
export function clipDurationMs(table: ClipTable, name: string, tailMs = 0): number {
  return clipFor(table, name).frames * frameMsFor(table, name) + tailMs;
}

export interface CharacterGeometry {
  frameW: number;
  frameH: number;
  frames: number;
  charW: number;
  charH: number;
}

/**
 * 条带几何：帧宽来自图片实际宽度 / 声明帧数，显示尺寸按 idle 帧高等比缩放。
 * 图片未就绪或尺寸非法时返回 null，调用方应保持上一帧而不是切换成别的动作。
 */
export function characterGeometry(input: {
  image: { naturalWidth: number; naturalHeight: number } | null;
  clip: ClipMeta;
  baseFrameH: number;
  targetHeight: number;
  maxWidth: number;
}): CharacterGeometry | null {
  const { image, clip, baseFrameH, targetHeight, maxWidth } = input;
  if (!image || image.naturalWidth <= 0 || image.naturalHeight <= 0) return null;
  if (!(baseFrameH > 0) || !(targetHeight > 0)) return null;
  const frames = Math.max(1, clip.frames);
  const frameW = image.naturalWidth / frames;
  const frameH = image.naturalHeight;
  if (!Number.isFinite(frameW) || frameW <= 0) return null;
  const scale = targetHeight / baseFrameH;
  const actualScale = frameW * scale > maxWidth ? maxWidth / frameW : scale;
  return {
    frameW,
    frameH,
    frames,
    charW: frameW * actualScale,
    charH: frameH * actualScale,
  };
}

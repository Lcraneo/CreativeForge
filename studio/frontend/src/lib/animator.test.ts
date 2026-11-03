import { describe, expect, it } from "vitest";
import type { PlaytestStrip } from "../types";
import {
  FALLBACK_CLIP,
  characterGeometry,
  clipDurationMs,
  clipFor,
  clipTable,
  frameMsFor,
  spriteScaleX,
} from "./animator";

const strip = (frames: number, fps?: number): PlaytestStrip => ({
  url: "/strip.png",
  frames,
  width: 250,
  height: 237,
  fps,
  engine: "rigged",
});

describe("clipTable", () => {
  it("按动作各自声明建表，缺 fps 的条带回落到响应级帧率", () => {
    const table = clipTable(
      { idle: strip(16, 16), attack: strip(12) },
      12,
    );
    expect(clipFor(table, "idle")).toEqual({ frames: 16, fps: 16 });
    expect(clipFor(table, "attack")).toEqual({ frames: 12, fps: 12 });
    expect(clipFor(table, "missing")).toEqual(FALLBACK_CLIP);
  });

  it("空表回到 8 帧 / 10 fps 的旧响应契约", () => {
    expect(clipFor(clipTable(undefined, 10), "walk")).toEqual({ frames: 8, fps: 10 });
    expect(clipFor(clipTable({ walk: strip(0) }, 10), "walk").frames).toBe(1);
  });
});

describe("spriteScaleX", () => {
  it("右侧素材按运动方向镜像，旧左向素材先归一化", () => {
    expect(spriteScaleX(1, "right")).toBe(1);
    expect(spriteScaleX(-1, "right")).toBe(-1);
    expect(spriteScaleX(1, "left")).toBe(-1);
    expect(spriteScaleX(-1, "left")).toBe(1);
  });
});

describe("frameMsFor / clipDurationMs", () => {
  it("帧长按动作自己的 fps 换算，不再互相借用", () => {
    const table = clipTable({ idle: strip(16, 16), attack: strip(16, 8) }, 16);
    expect(frameMsFor(table, "idle")).toBeCloseTo(62.5, 5);
    expect(frameMsFor(table, "attack")).toBeCloseTo(125, 5);
  });

  it("奔跑按 1.3 倍步频播放", () => {
    const table = clipTable({ run: strip(16, 16) }, 16);
    expect(frameMsFor(table, "run")).toBeCloseTo(1000 / (16 * 1.3), 5);
  });

  it("一次性动作窗口 = 自身帧数 × 自身帧长 + 收尾", () => {
    const table = clipTable({ idle: strip(16, 16), attack: strip(16, 8) }, 16);
    expect(clipDurationMs(table, "attack", 120)).toBeCloseTo(16 * 125 + 120, 5);
  });
});

describe("characterGeometry", () => {
  const image = (width: number, height: number) => ({
    naturalWidth: width,
    naturalHeight: height,
  });

  it("以 idle 帧高为基准，切换动作时宽度不跳变", () => {
    const idle = characterGeometry({
      image: image(4000, 237),
      clip: { frames: 16, fps: 16 },
      baseFrameH: 237,
      targetHeight: 176,
      maxWidth: 220,
    });
    const run = characterGeometry({
      image: image(4032, 250),
      clip: { frames: 16, fps: 16 },
      baseFrameH: 237,
      targetHeight: 176,
      maxWidth: 220,
    });
    expect(idle).not.toBeNull();
    expect(run).not.toBeNull();
    // 两个动作的帧高不同，但同一角色宽度只随帧宽小幅变化（< 2px）
    expect(Math.abs(run!.charW - idle!.charW)).toBeLessThan(2);
  });

  it("过宽角色按最大宽度收敛，保持等比", () => {
    const geometry = characterGeometry({
      image: image(4000, 237),
      clip: { frames: 16, fps: 16 },
      baseFrameH: 237,
      targetHeight: 176,
      maxWidth: 120,
    });
    expect(geometry!.charW).toBeCloseTo(120, 5);
    expect(geometry!.charH / geometry!.charW).toBeCloseTo(237 / 250, 5);
  });

  it("图片未就绪或尺寸非法时返回 null（调用方保持上一帧）", () => {
    expect(
      characterGeometry({
        image: null,
        clip: { frames: 16, fps: 16 },
        baseFrameH: 237,
        targetHeight: 176,
        maxWidth: 220,
      }),
    ).toBeNull();
    expect(
      characterGeometry({
        image: image(0, 0),
        clip: { frames: 16, fps: 16 },
        baseFrameH: 237,
        targetHeight: 176,
        maxWidth: 220,
      }),
    ).toBeNull();
  });
});

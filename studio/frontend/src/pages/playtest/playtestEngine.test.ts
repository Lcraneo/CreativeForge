/**
 * 试玩舞台 V2 · 引擎 / 加载器 / 帧循环 / 动作坞结构测试
 *
 * 覆盖验收清单：动作切换与一次性动作优先级、回落语义、失焦清键、
 * 隐藏停帧、Preview/Live 模式、角色切换丢弃旧资源、失败重试、
 * 动作坞无嵌套按钮。
 */
import { act, createElement } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  PlaytestEngine,
  createFrameLoop,
  type PlaytestInput,
} from "./playtestEngine";
import { StripImageLoader, type StripPhase } from "./usePlaytestAssets";
import { PlaytestActionDock } from "./PlaytestActionDock";
import { useHeldKeys } from "../../lib/keyboard";
import type { PlaytestMode } from "./playtestEngine";

function createTestEngine(stageWidth = 640) {
  const input: PlaytestInput = { left: false, right: false, run: false };
  const engine = new PlaytestEngine({ stageWidth });
  engine.setInputSource(() => ({ ...input }));
  return { engine, input };
}

describe("playtest engine state machine", () => {
  it("switches idle → walk → run from keyboard input", () => {
    const { engine, input } = createTestEngine();
    expect(engine.update(0).action).toBe("idle");
    input.left = true;
    expect(engine.update(16.7).action).toBe("walk");
    input.run = true;
    expect(engine.update(33.4).action).toBe("run");
  });

  it("prioritizes attack over movement while the one-shot is playing", () => {
    const { engine, input } = createTestEngine();
    input.left = true;
    engine.update(0);
    engine.press("attack", 10);
    expect(engine.update(20).action).toBe("attack");
    expect(engine.update(500).action).toBe("attack");
  });

  it("falls back to the locomotion action after attack ends", () => {
    const { engine, input } = createTestEngine();
    input.left = true;
    engine.update(0);
    engine.press("attack", 10); // 默认 8 帧 @10fps + 150ms 余量 → until 960
    engine.update(20);
    const settled = engine.update(1000);
    expect(settled.action).toBe("walk");
  });

  it("falls back to idle after attack when standing still", () => {
    const { engine } = createTestEngine();
    engine.press("attack", 0);
    expect(engine.update(10).action).toBe("attack");
    expect(engine.update(1000).action).toBe("idle");
  });

  it("returns to the pinned preview action after jump ends", () => {
    const { engine } = createTestEngine();
    engine.pin("walk");
    expect(engine.update(10).action).toBe("walk");
    engine.press("jump", 20);
    expect(engine.update(30).action).toBe("jump");
    expect(engine.update(30).mode).toBe("preview");
    const settled = engine.update(1200);
    expect(settled.action).toBe("walk");
    expect(settled.mode).toBe("preview");
  });

  it("returns to idle after jump when live", () => {
    const { engine } = createTestEngine();
    engine.press("jump", 0);
    expect(engine.update(10).action).toBe("jump");
    expect(engine.update(1000).action).toBe("idle");
  });

  it("returns to idle when direction keys are released", () => {
    const { engine, input } = createTestEngine();
    input.right = true;
    expect(engine.update(0).action).toBe("walk");
    input.right = false;
    expect(engine.update(16.7).action).toBe("idle");
  });

  it("advances the frame cursor per strip timing and holds the last frame of one-shots", () => {
    const { engine, input } = createTestEngine();
    engine.setStripTiming("walk", { frames: 4, fps: 100 }); // 10ms/帧
    input.left = true;
    expect(engine.update(0).frame).toBe(0);
    expect(engine.update(11).frame).toBe(1);

    engine.setStripTiming("attack", { frames: 4, fps: 100 });
    input.left = false;
    engine.press("attack", 40); // until = 40 + 40 + 150
    engine.update(50);
    expect(engine.update(90).frame).toBe(3);
    expect(engine.update(100).frame).toBe(3); // 停在末帧直到 until
  });

  it("moves and flips facing only while direction keys are held", () => {
    const { engine, input } = createTestEngine(640);
    input.right = true;
    let snapshot = engine.update(0);
    const startX = snapshot.x;
    snapshot = engine.update(500);
    expect(snapshot.x).toBeGreaterThan(startX);
    expect(snapshot.facing).toBe(1);
    input.right = false;
    input.left = true;
    snapshot = engine.update(1000);
    expect(snapshot.facing).toBe(-1);
    const heldX = snapshot.x;
    expect(engine.update(1100).x).toBeLessThan(heldX);
  });

  it("clamps position to the stage margins", () => {
    const { engine, input } = createTestEngine(640);
    input.right = true;
    engine.update(0);
    for (let time = 100; time <= 20_000; time += 100) engine.update(time);
    expect(engine.update(20_100).x).toBeLessThanOrEqual(640 - 80);
  });

  it("switches between preview and live modes", () => {
    const { engine, input } = createTestEngine();
    engine.pin("walk");
    expect(engine.update(10).mode).toBe("preview");
    expect(engine.update(20).action).toBe("walk");
    // 按移动键 → 回 Live（方向键接管钉住的动作）
    input.right = true;
    const afterKey = engine.update(30);
    expect(afterKey.mode).toBe("live");
    expect(afterKey.action).toBe("walk");
    input.right = false;
    engine.pin("run");
    expect(engine.update(40).mode).toBe("preview");
    // 恢复实时控制按钮 → 回 Live
    engine.resumeLive();
    expect(engine.update(60).mode).toBe("live");
    expect(engine.update(70).action).toBe("idle");
  });

  it("clears input after blur (via useHeldKeys)", async () => {
    let keysRef: { current: Set<string> } | null = null;
    function Probe() {
      keysRef = useHeldKeys(["arrowleft", "arrowright", "arrowup", " "]);
      return null;
    }
    const container = document.createElement("div");
    document.body.append(container);
    const root = createRoot(container);
    vi.stubGlobal("IS_REACT_ACT_ENVIRONMENT", true);
    await act(async () => root.render(createElement(Probe)));
    window.dispatchEvent(new KeyboardEvent("keydown", { key: "ArrowLeft" }));
    expect(keysRef!.current.has("arrowleft")).toBe(true);
    window.dispatchEvent(new Event("blur"));
    expect(keysRef!.current.has("arrowleft")).toBe(false);
    await act(async () => root.unmount());
    container.remove();
  });
});

describe("createFrameLoop", () => {
  type FakeFrame = { id: number; cb: FrameRequestCallback };
  let frames: FakeFrame[];
  let seq: number;

  beforeEach(() => {
    seq = 0;
    frames = [];
    vi.stubGlobal("requestAnimationFrame", (cb: FrameRequestCallback) => {
      const id = ++seq;
      frames.push({ id, cb });
      return id;
    });
    vi.stubGlobal("cancelAnimationFrame", (id: number) => {
      const index = frames.findIndex((frame) => frame.id === id);
      if (index >= 0) frames.splice(index, 1);
    });
  });
  afterEach(() => {
    vi.unstubAllGlobals();
    Object.defineProperty(document, "hidden", {
      configurable: true,
      get: () => false,
    });
  });

  const setHidden = (value: boolean) =>
    Object.defineProperty(document, "hidden", { configurable: true, get: () => value });
  const drain = () => {
    const frame = frames.shift();
    if (frame) frame.cb(performance.now());
  };

  it("stops scheduling frames while the page is hidden and resumes on visible", () => {
    const frame = vi.fn();
    const loop = createFrameLoop(frame);
    loop.start();
    expect(frames.length).toBe(1);
    drain();
    expect(frame).toHaveBeenCalledTimes(1);
    expect(frames.length).toBe(1); // 播放中持续续排

    setHidden(true);
    document.dispatchEvent(new Event("visibilitychange"));
    expect(loop.isRunning()).toBe(false);
    expect(frames.length).toBe(0); // 在途帧被取消

    // 浏览器仍投递了一帧的极端时序：隐藏状态下不再续排
    drain();
    expect(frames.length).toBe(0);

    setHidden(false);
    document.dispatchEvent(new Event("visibilitychange"));
    expect(loop.isRunning()).toBe(true);
    loop.dispose();
    expect(loop.isRunning()).toBe(false);
  });

  it("stops on dispose and survives callback errors", () => {
    const frame = vi.fn(() => {
      throw new Error("draw error");
    });
    const loop = createFrameLoop(frame);
    loop.start();
    expect(() => drain()).toThrow("draw error");
    expect(frames.length).toBe(1); // 出错后下一帧照常调度
    loop.dispose();
    expect(frames.length).toBe(0);
  });

  it("throttles frame delivery under prefers-reduced-motion: reduce", () => {
    vi.stubGlobal("matchMedia", () => ({ matches: true }));
    const frame = vi.fn();
    const loop = createFrameLoop(frame);
    loop.start();
    const tick = (t: number) => {
      const queued = frames.shift();
      queued?.cb(t);
    };
    tick(0); // 首帧立即投递
    expect(frame).toHaveBeenCalledTimes(1);
    tick(50); // 未到降帧间隔（≈83ms）：跳过绘制但仍续排
    expect(frame).toHaveBeenCalledTimes(1);
    expect(frames.length).toBe(1);
    tick(100); // 超过间隔：投递
    expect(frame).toHaveBeenCalledTimes(2);
    loop.dispose();
    expect(frames.length).toBe(0);
  });

  it("delivers every frame when reduced motion is off", () => {
    vi.stubGlobal("matchMedia", () => ({ matches: false }));
    const frame = vi.fn();
    const loop = createFrameLoop(frame);
    loop.start();
    const tick = (t: number) => {
      const queued = frames.shift();
      queued?.cb(t);
    };
    tick(0);
    tick(6);
    tick(12);
    expect(frame).toHaveBeenCalledTimes(3);
    loop.dispose();
    expect(frames.length).toBe(0);
  });
});

describe("StripImageLoader", () => {
  class FakeImage {
    onload: (() => void) | null = null;
    onerror: (() => void) | null = null;
    src = "";
    decoding = "";
    decode = () => Promise.resolve();
    setAttribute = vi.fn();
    constructor() {
      instances.push(this);
    }
  }
  let instances: FakeImage[];

  beforeEach(() => {
    instances = [];
    vi.stubGlobal("Image", FakeImage);
  });
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("discards late results from the previous character after cancelAll", () => {
    const onReady = vi.fn();
    const onError = vi.fn();
    const loader = new StripImageLoader({ onReady, onError });
    loader.load("idle", "/old-character.png");
    loader.cancelAll(); // 模拟切换角色
    expect(instances[0].src).toBe(""); // 在途网络请求被中止
    instances[0].onload?.(); // 旧请求迟到
    expect(onReady).not.toHaveBeenCalled();
    expect(onError).not.toHaveBeenCalled();
  });

  it("retries a failed action and succeeds", () => {
    const onReady = vi.fn();
    const onError = vi.fn();
    const loader = new StripImageLoader({ onReady, onError });
    loader.load("run", "/run.png");
    instances[0].onerror?.();
    expect(onError).toHaveBeenCalledWith("run");
    loader.load("run", "/run.png", "high"); // 重试（高优先级）
    instances[1].onload?.();
    expect(onReady).toHaveBeenCalledWith("run", instances[1]);
  });

  it("reloads when the strip url changes (AI 生成完成后 invalidate)", () => {
    const onReady = vi.fn();
    const onError = vi.fn();
    const loader = new StripImageLoader({ onReady, onError });
    loader.load("idle", "/idle-old.png");
    instances[0].onload?.();
    expect(onReady).toHaveBeenCalledTimes(1);
    loader.load("idle", "/idle-new.png");
    instances[1].onload?.();
    expect(onReady).toHaveBeenCalledTimes(2);
    expect(onReady).toHaveBeenLastCalledWith("idle", instances[1]);
  });

  it("is idempotent for the same key and url while in flight", () => {
    const loader = new StripImageLoader({ onReady: vi.fn(), onError: vi.fn() });
    loader.load("walk", "/walk.png");
    loader.load("walk", "/walk.png");
    expect(instances.length).toBe(1);
  });
});

describe("PlaytestActionDock structure", () => {
  let root: Root;
  let container: HTMLDivElement;

  beforeEach(() => {
    vi.stubGlobal("IS_REACT_ACT_ENVIRONMENT", true);
    container = document.createElement("div");
    document.body.append(container);
    root = createRoot(container);
  });
  afterEach(async () => {
    await act(async () => root.unmount());
    container.remove();
    vi.unstubAllGlobals();
  });

  async function renderDock(overrides: Partial<Parameters<typeof PlaytestActionDock>[0]> = {}) {
    const props: Parameters<typeof PlaytestActionDock>[0] = {
      actions: ["idle", "walk", "run", "attack", "jump"],
      customActions: [
        {
          name: "旋风踢",
          base_action: "attack",
          engine: "procedural",
          strip: { url: "/custom.png", frames: 8, width: 96, height: 96, engine: "procedural" },
        },
      ],
      strips: {
        idle: { url: "/idle.png", frames: 16, fps: 16, width: 256, height: 256, engine: "rigged" },
      },
      thumbnails: {},
      currentAction: "idle",
      mode: "live" as PlaytestMode,
      submittingAction: null,
      batchTasks: [],
      batchRunning: false,
      batchDoneCount: 0,
      batchTotal: 0,
      batchSyncError: null,
      missingCount: 2,
      aiReadyCount: 3,
      phase: (() => "ready") as (key: string) => StripPhase,
      customLoading: false,
      libraryOpen: true,
      assetSelected: true,
      onSelect: vi.fn(),
      onResumeLive: vi.fn(),
      onGenerateAi: vi.fn(),
      onGenerateAll: vi.fn(),
      onRefreshBatch: vi.fn(),
      onOpenLibrary: vi.fn(),
      onRetry: vi.fn(),
      onGoWorkbench: vi.fn(),
      ...overrides,
    };
    await act(async () => root.render(createElement(PlaytestActionDock, props)));
    return props;
  }

  it("renders built-in and custom action cards without nested buttons", async () => {
    await renderDock();
    const buttons = Array.from(container.querySelectorAll("button"));
    expect(buttons.length).toBeGreaterThan(5);
    for (const button of buttons) {
      expect(button.querySelector("button")).toBeNull();
    }
    const labels = buttons.map((button) => button.textContent ?? "");
    expect(container.textContent).toContain("本角色 AI 3/5");
    expect(labels.some((text) => text.includes("待机"))).toBe(true);
    expect(labels.some((text) => text.includes("攻击"))).toBe(true);
    expect(labels.some((text) => text.includes("旋风踢"))).toBe(true);
    // 选择按钮与「生成 AI 动画」/「到动画工作台」次级按钮同级存在
    expect(labels.some((text) => text.includes("生成 AI 动画"))).toBe(true);
    expect(labels.some((text) => text.includes("到动画工作台"))).toBe(true);
  });

  it("shows a retry entry for failed strips and reports preview mode", async () => {
    await renderDock({
      phase: (() => "error") as (key: string) => StripPhase,
      mode: "preview",
      currentAction: "run",
    });
    const text = container.textContent ?? "";
    expect(text).toContain("Preview");
    expect(text).toContain("恢复实时控制");
    expect(text).toContain("重试");
  });

  it("names the active action and keeps the whole queue visible during a batch", async () => {
    await renderDock({
      batchRunning: true,
      batchDoneCount: 1,
      batchTotal: 3,
      batchTasks: [
        { action: "idle", status: "done" },
        { action: "walk", status: "generating", stage: "video", started_at: Date.now() / 1000 },
        { action: "run", status: "pending" },
      ],
    });

    const text = container.textContent ?? "";
    expect(text).toContain("正在生成「行走」");
    expect(text).toContain("待机");
    expect(text).toContain("已生成");
    expect(text).toContain("排队");
    expect(text).toContain("1/3");
  });
});

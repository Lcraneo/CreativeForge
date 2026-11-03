/**
 * 试玩舞台 V2 · 纯状态机（无 React 依赖）
 *
 * 职责集中：键盘输入 → 动作优先级仲裁（jump 一次性动作 > 移动 >
 * 钉住的预览动作 > idle）→ 帧游标推进 → 位置/朝向积分 → Live/Preview
 * 模式管理。rAF 循环内的全部状态都住在 engine 内部；React 只通过
 * onStateChange 收到低频（动作/模式变化）通知——帧推进、移动和朝向
 * 更新不再触发任何 React 重渲染。
 */

export type PlaytestMode = "live" | "preview";
export type OneShotAction = "jump";

/** 键盘输入快照（页面从 useHeldKeys 的键集合映射而来） */
export interface PlaytestInput {
  left: boolean;
  right: boolean;
  /** Shift 奔跑 */
  run: boolean;
}

export interface StripTiming {
  frames: number;
  fps: number;
}

/** 真实渲染指标：rAF 间隔的指数滑动平均（低频轮询读取，不参与渲染路径） */
export interface PlaytestMetrics {
  fps: number;
  frameMs: number;
}

export interface PlaytestSnapshot {
  mode: PlaytestMode;
  action: string;
  frame: number;
  x: number;
  facing: 1 | -1;
  /** 当前动作起始时刻（performance.now 时间基）：renderer 据此做切换淡入 */
  actionStartedAt: number;
}

// 旧实现 3.2 / 5.6 px 每 60fps 帧，换算为 px/s 后与帧率解耦
export const WALK_SPEED_PX_S = 192;
export const RUN_SPEED_PX_S = 336;
/** jump 播完帧序列后额外停留的余量 */
export const ONE_SHOT_TAIL_MS = 150;
/** 后台标签页回来时单次 tick 最多推进 50ms，防跳变 */
export const MAX_TICK_MS = 50;
/** 条带元数据缺席时的回落契约（旧响应 8 帧 @10fps） */
export const FALLBACK_FPS = 10;
export const FALLBACK_FRAMES = 8;
/** 速度感知播放：奔跑步频加快 1.3 倍，与移速匹配（沿旧实现） */
const RUN_FPS_SCALE = 1.3;
/** 位置钳制边距（与旧实现 80px/640px 舞台同比例） */
const POSITION_MARGIN_PX = 80;

export interface PlaytestEngineOptions {
  stageWidth?: number;
  onStateChange?: (snapshot: PlaytestSnapshot) => void;
}

export class PlaytestEngine {
  private inputSource: (() => PlaytestInput) | null = null;
  private fpsEMA: number | null = null;
  private frameMsEMA: number | null = null;
  private readonly listeners = new Set<(snapshot: PlaytestSnapshot) => void>();
  private readonly timings = new Map<string, StripTiming>();
  private stageWidth: number;
  private mode: PlaytestMode = "live";
  private pinned: string | null = null;
  private oneShot: { name: OneShotAction; until: number } | null = null;
  private action = "idle";
  private frame = 0;
  private frameElapsed = 0;
  private x: number;
  private facing: 1 | -1 = 1;
  private actionStartedAt = 0;
  private last: number | null = null;
  private sized = false;

  constructor(options: PlaytestEngineOptions = {}) {
    this.stageWidth = options.stageWidth ?? 640;
    this.x = this.stageWidth / 2;
    if (options.onStateChange) this.listeners.add(options.onStateChange);
  }

  /** 安装输入源（页面在 effect 中把 useHeldKeys 的键集合接线进来——
   * effect 中读 ref 是合法副作用位置，不在 useMemo/useCallback 中读） */
  setInputSource(fn: () => PlaytestInput) {
    this.inputSource = fn;
  }

  /** 订阅低频状态变化（动作/模式切换），返回退订函数 */
  onStateChange(listener: (snapshot: PlaytestSnapshot) => void): () => void {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  }

  setStageWidth(width: number) {
    this.stageWidth = width;
    // 首次得知真实舞台宽度时角色居中出场；之后只做边界钳制
    if (!this.sized) {
      this.sized = true;
      this.x = width / 2;
      return;
    }
    this.x = Math.max(POSITION_MARGIN_PX, Math.min(width - POSITION_MARGIN_PX, this.x));
  }

  /** 条带元数据就绪时注入（帧数/帧率）；null 清除回落默认 */
  setStripTiming(action: string, timing: StripTiming | null) {
    if (timing === null) this.timings.delete(action);
    else this.timings.set(action, timing);
  }

  /** 键盘一次性动作（↑/W 跳跃）：播完整帧序列 + 余量后回落；
   * 按住连发（keydown repeat）= 旧语义，每次重置 until */
  press(name: OneShotAction, now: number = performance.now()) {
    const { frames, fps } = this.timingFor(name);
    const durationMs = (frames * 1000) / Math.max(1, fps) + ONE_SHOT_TAIL_MS;
    this.oneShot = { name, until: now + durationMs };
  }

  /** Preview 模式：循环播放指定动作（点动作卡） */
  pin(action: string) {
    this.pinned = action;
    this.mode = "preview";
  }

  /** 回到 Live 模式（"恢复实时控制"按钮） */
  resumeLive() {
    this.pinned = null;
    if (this.mode !== "live") {
      this.mode = "live";
      this.emit();
    }
  }

  snapshot(): PlaytestSnapshot {
    return {
      mode: this.mode,
      action: this.action,
      frame: this.frame,
      x: this.x,
      facing: this.facing,
      actionStartedAt: this.actionStartedAt,
    };
  }

  /** 真实渲染指标（暂停时冻结在暂停前测量值） */
  getMetrics(): PlaytestMetrics {
    return {
      fps: Math.round(this.fpsEMA ?? 0),
      frameMs: Math.round((this.frameMsEMA ?? 0) * 10) / 10,
    };
  }

  /** 推进一帧。now 必须单调递增（rAF 时间戳 / 测试注入的合成时间） */
  update(now: number): PlaytestSnapshot {
    // 首 tick 只建立时间原点（delta 0），不推进帧
    const delta = this.last === null ? 0 : Math.min(now - this.last, MAX_TICK_MS);
    this.last = now;
    if (delta > 0) {
      // 真实渲染指标：rAF 间隔的指数滑动平均，供徽章/Debug 叠层低频轮询
      const instantFps = 1000 / delta;
      this.fpsEMA = this.fpsEMA === null ? instantFps : this.fpsEMA * 0.9 + instantFps * 0.1;
      this.frameMsEMA = this.frameMsEMA === null ? delta : this.frameMsEMA * 0.9 + delta * 0.1;
    }
    const input = this.inputSource?.() ?? { left: false, right: false, run: false };

    if (this.oneShot !== null && now >= this.oneShot.until) this.oneShot = null;

    // Preview 模式下按移动键 → 回 Live（方向键永远接管钉住的动作）
    if (this.mode === "preview" && (input.left || input.right)) {
      this.mode = "live";
      this.pinned = null;
      this.emit();
    }

    let next: string;
    if (this.oneShot !== null) {
      next = this.oneShot.name;
    } else if (input.left !== input.right) {
      next = input.run ? "run" : "walk";
    } else if (this.mode === "preview" && this.pinned !== null) {
      next = this.pinned;
    } else {
      next = "idle";
    }

    if (next !== this.action) {
      this.action = next;
      this.frame = 0;
      this.frameElapsed = 0;
      this.actionStartedAt = now;
      this.emit();
    }

    // 位置/朝向：仅 Live 模式下按方向键积分
    if (this.mode === "live" && input.left !== input.right) {
      const direction: 1 | -1 = input.right ? 1 : -1;
      this.facing = direction;
      const speed = ((input.run ? RUN_SPEED_PX_S : WALK_SPEED_PX_S) * delta) / 1000;
      this.x = Math.max(
        POSITION_MARGIN_PX,
        Math.min(this.stageWidth - POSITION_MARGIN_PX, this.x + direction * speed),
      );
    }

    // 帧步进：一次性动作停在末帧，循环动作取模
    const { frames, fps } = this.timingFor(next);
    const scaled = next === "run" ? fps * RUN_FPS_SCALE : fps;
    const frameMs = 1000 / Math.max(1, scaled);
    let idx = this.frame % frames;
    let elapsed = this.frameElapsed + delta;
    let changed = false;
    while (elapsed >= frameMs) {
      if (this.oneShot !== null && idx >= frames - 1) {
        elapsed = frameMs;
        break;
      }
      elapsed -= frameMs;
      idx = (idx + 1) % frames;
      changed = true;
    }
    this.frameElapsed = elapsed;
    if (changed) this.frame = idx;

    return this.snapshot();
  }

  private timingFor(action: string): StripTiming {
    return this.timings.get(action) ?? { frames: FALLBACK_FRAMES, fps: FALLBACK_FPS };
  }

  private emit() {
    if (this.listeners.size === 0) return;
    const snapshot = this.snapshot();
    for (const listener of this.listeners) listener(snapshot);
  }
}

/* ──────────────────────────────────────────────────────────────── */

export interface FrameLoop {
  start(): void;
  stop(): void;
  isRunning(): boolean;
  dispose(): void;
}

/** prefers-reduced-motion 降帧间隔（≈12fps）：reduce 偏好下抽帧播放，
 * 模拟推进随 MAX_TICK_MS 钳制同步放缓（动作与移速一致减慢），暂停能力不受影响 */
export const REDUCED_MOTION_FRAME_MS = 1000 / 12;

/** rAF 帧循环：页面隐藏（visibilitychange）时停止调度、恢复可见自动续跑。
 * 回调抛错不中断后续帧（下一帧照常调度）。遵守 prefers-reduced-motion：
 * reduce 时按 REDUCED_MOTION_FRAME_MS 抽帧（MQL.matches 为活值，系统
 * 设置变化实时生效；matchMedia 缺席的环境视为未开启）。 */
export function createFrameLoop(frame: (now: number) => void): FrameLoop {
  let rafId: number | null = null;
  let lastTick: number | null = null;
  let reducedMotion: MediaQueryList | null = null;
  const reducedMotionActive = () => {
    if (reducedMotion === null) {
      if (typeof window === "undefined" || typeof window.matchMedia !== "function") return false;
      reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)");
    }
    return reducedMotion.matches;
  };

  const step = (now: number) => {
    rafId = null;
    try {
      if (lastTick === null || now - lastTick >= REDUCED_MOTION_FRAME_MS || !reducedMotionActive()) {
        lastTick = now;
        frame(now);
      }
    } finally {
      // 回调抛错不中断后续帧（finally 保证调度，错误本身继续向 rAF 冒泡）
      if (rafId === null && !document.hidden) rafId = requestAnimationFrame(step);
    }
  };

  function start() {
    if (rafId === null && !document.hidden) rafId = requestAnimationFrame(step);
  }

  function stop() {
    if (rafId !== null) cancelAnimationFrame(rafId);
    rafId = null;
    lastTick = null; // 重启（隐藏恢复/暂停继续）后立即恢复一帧
  }

  const onVisibility = () => {
    if (document.hidden) stop();
    else start();
  };

  document.addEventListener("visibilitychange", onVisibility);
  return {
    start,
    stop,
    isRunning: () => rafId !== null,
    dispose() {
      stop();
      document.removeEventListener("visibilitychange", onVisibility);
    },
  };
}

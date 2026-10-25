/** 关卡试玩场的纯逻辑：关卡生成、角色物理、金币拾取与角色检查报告。
 *
 * 与渲染解耦，便于在 vitest 里用固定时间步验证：跑、跳、落地、掉坑、
 * 通关判定都不依赖 Konva 或浏览器。检查报告沿用 godogen 的
 * 「以跑起来的结果验收」原则——条目全部来自实际运行数据与动作条带元信息，
 * 不看代码是否编译通过。
 */

import type { PlaytestStrip } from "../types";

export type ArcadeAction = "idle" | "walk" | "run" | "attack" | "jump";

export const REQUIRED_ACTIONS: ArcadeAction[] = ["idle", "walk", "run", "jump", "attack"];

/** 关卡世界尺寸与基准地面线（世界坐标，y 向下）。 */
export const WORLD_HEIGHT = 420;
export const GROUND_Y = 348;
export const PLAYER_HALF_W = 22;

/** 角色显示尺寸与运动参数（像素 / 秒）。 */
export const CHAR_HEIGHT = 176;
export const CHAR_MAX_WIDTH = 220;
export const WALK_SPEED = 180;
export const RUN_SPEED = 300;
export const GRAVITY = 1600;
export const JUMP_SPEED = 600;
export const MAX_FALL_SPEED = 1000;
export const FALL_LIMIT = WORLD_HEIGHT + 140;

export interface ArcadePlatform {
  x: number;
  y: number;
  width: number;
  height: number;
  kind: "ground" | "floating";
}

export interface ArcadeCoin {
  id: string;
  x: number;
  y: number;
}

export interface ArcadeLevel {
  seed: string;
  width: number;
  groundY: number;
  spawnX: number;
  goalX: number;
  platforms: ArcadePlatform[];
  coins: ArcadeCoin[];
}

export interface ArcadeInput {
  left: boolean;
  right: boolean;
  run: boolean;
  jump: boolean;
}

export interface PlayerState {
  x: number;
  y: number;
  vx: number;
  vy: number;
  onGround: boolean;
  facing: 1 | -1;
}

export interface ArcadeRuntime {
  reachedGoal: boolean;
  falls: number;
  coins: number;
  totalCoins: number;
  avgFps: number;
}

export interface ReportItem {
  key: string;
  label: string;
  status: "pass" | "warn" | "fail";
  detail: string;
}

export interface CharacterReport {
  items: ReportItem[];
  verdict: "pass" | "warn" | "fail";
  passed: number;
  total: number;
}

function hashSeed(seed: string): number {
  let value = 2166136261;
  for (let index = 0; index < seed.length; index += 1) {
    value ^= seed.charCodeAt(index);
    value = Math.imul(value, 16777619);
  }
  return value >>> 0;
}

function clamp(value: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, value));
}

/** 按资产 ID 生成固定关卡：同一角色每次进入路线一致，便于对照复查。 */
export function buildLevel(seed: string): ArcadeLevel {
  const drift = hashSeed(seed) % 3; // 只做轻微变化，避免同一角色前后不可比
  const width = 2600;
  const platforms: ArcadePlatform[] = [
    { x: 0, y: GROUND_Y, width: 640, height: 72, kind: "ground" },
    { x: 740, y: GROUND_Y, width: 420, height: 72, kind: "ground" },
    { x: 840, y: 276, width: 150, height: 18, kind: "floating" },
    { x: 1260, y: GROUND_Y, width: 500, height: 72, kind: "ground" },
    { x: 1400, y: 268, width: 160, height: 18, kind: "floating" },
    { x: 1620 + drift * 10, y: 212, width: 130, height: 18, kind: "floating" },
    { x: 1860, y: GROUND_Y, width: 740, height: 72, kind: "ground" },
  ];
  const coins: ArcadeCoin[] = [
    { id: "c1", x: 300, y: 308 },
    { id: "c2", x: 460, y: 308 },
    { id: "c3", x: 560, y: 300 },
    { id: "c4", x: 860, y: 236 },
    { id: "c5", x: 915, y: 236 },
    { id: "c6", x: 970, y: 236 },
    { id: "c7", x: 1330, y: 308 },
    { id: "c8", x: 1450, y: 228 },
    { id: "c9", x: 1540, y: 228 },
    { id: "c10", x: 1670 + drift * 10, y: 172 },
    { id: "c11", x: 1980, y: 308 },
    { id: "c12", x: 2100, y: 308 },
    { id: "c13", x: 2260, y: 308 },
    { id: "c14", x: 2400, y: 300 },
  ];
  return {
    seed,
    width,
    groundY: GROUND_Y,
    spawnX: 120,
    goalX: 2480,
    platforms,
    coins,
  };
}

export function initialPlayer(level: ArcadeLevel): PlayerState {
  return { x: level.spawnX, y: level.groundY, vx: 0, vy: 0, onGround: true, facing: 1 };
}

/** 顶层支撑面：仅当角色水平范围内存在平台且脚底不高于台面时成立。 */
function supportTop(level: ArcadeLevel, x: number, feetY: number): number | null {
  let top: number | null = null;
  for (const platform of level.platforms) {
    const withinX =
      x + PLAYER_HALF_W > platform.x && x - PLAYER_HALF_W < platform.x + platform.width;
    if (!withinX) continue;
    if (feetY <= platform.y + 1) {
      top = top === null ? platform.y : Math.min(top, platform.y);
    }
  }
  return top;
}

/** 固定步长物理解算：水平即时速度、竖直重力、单向平台落地。 */
export function stepPlayer(
  state: PlayerState,
  input: ArcadeInput,
  level: ArcadeLevel,
  dtRaw: number,
): PlayerState {
  const dt = clamp(dtRaw, 0, 0.05);
  const moving = input.left !== input.right;
  const facing: 1 | -1 = moving ? (input.right ? 1 : -1) : state.facing;
  const vx = moving ? (input.right ? 1 : -1) * (input.run ? RUN_SPEED : WALK_SPEED) : 0;

  let vy = Math.min(MAX_FALL_SPEED, state.vy + GRAVITY * dt);
  if (input.jump && state.onGround) vy = -JUMP_SPEED;

  const x = clamp(state.x + vx * dt, PLAYER_HALF_W + 2, level.width - PLAYER_HALF_W - 2);
  const previousY = state.y;
  let y = state.y + vy * dt;
  let onGround = false;

  if (vy >= 0) {
    // 从上方跨过台面：取本帧跨过的最高台面（y 最小）作为落点
    let landing: number | null = null;
    for (const platform of level.platforms) {
      const withinX =
        x + PLAYER_HALF_W > platform.x && x - PLAYER_HALF_W < platform.x + platform.width;
      if (!withinX) continue;
      if (previousY <= platform.y + 1 && y >= platform.y) {
        landing = landing === null ? platform.y : Math.min(landing, platform.y);
      }
    }
    if (landing !== null) {
      y = landing;
      vy = 0;
      onGround = true;
    }
  }

  // 站立时支撑面可能因走位离开：脚底仍在台面上则继续视为着地
  if (!onGround && vy >= 0) {
    const top = supportTop(level, x, y);
    if (top !== null && Math.abs(y - top) < 2) {
      y = top;
      vy = 0;
      onGround = true;
    }
  }

  return { x, y, vx, vy, onGround, facing };
}

export function isFallen(state: PlayerState): boolean {
  return state.y > FALL_LIMIT;
}

/** 掉落复活：回到最近一次安全落点，保留位置记忆但重置速度。 */
export function respawn(level: ArcadeLevel, checkpointX: number): PlayerState {
  const x = clamp(checkpointX, PLAYER_HALF_W + 2, level.width - PLAYER_HALF_W - 2);
  return { x, y: level.groundY, vx: 0, vy: 0, onGround: true, facing: 1 };
}

/** 金币拾取：以角色身体中心为圆心做圆形判定。 */
export function collectCoins(
  state: PlayerState,
  coins: ArcadeCoin[],
  taken: ReadonlySet<string>,
): ArcadeCoin[] {
  const centerY = state.y - CHAR_HEIGHT / 2;
  const radius = Math.max(PLAYER_HALF_W, CHAR_HEIGHT / 2) * (2 / 3);
  return coins.filter(
    (coin) =>
      !taken.has(coin.id) && Math.hypot(coin.x - state.x, coin.y - centerY) <= radius,
  );
}

/** 动作优先级：空中一律跳跃（没有 jump-attack 条带，空中攻击会造成腿部串调），
 *  地面攻击 > 奔跑 > 行走 > 待机。 */
export function pickAction(
  state: PlayerState,
  attacking: boolean,
): ArcadeAction {
  if (!state.onGround) return "jump";
  if (attacking) return "attack";
  if (Math.abs(state.vx) > 0) return state.vx >= RUN_SPEED ? "run" : "walk";
  return "idle";
}

/** 相机跟随：角色保持在视口偏左 40% 处，边界收拢。 */
export function cameraX(playerX: number, viewportWidth: number, worldWidth: number): number {
  return clamp(playerX - viewportWidth * 0.4, 0, Math.max(0, worldWidth - viewportWidth));
}

/** 检查报告：动作覆盖、帧数、帧率、源分辨率、解码完整性与本轮运行表现。 */
export function inspectCharacter(input: {
  actions: string[];
  strips: Record<string, PlaytestStrip>;
  loadErrors?: string[];
  runtime?: ArcadeRuntime;
}): CharacterReport {
  const { actions, strips, loadErrors = [], runtime } = input;
  const items: ReportItem[] = [];

  const covered = new Set([...actions, ...Object.keys(strips)]);
  const missing = REQUIRED_ACTIONS.filter((action) => !covered.has(action));
  items.push({
    key: "coverage",
    label: "动作覆盖",
    status: missing.length === 0 ? "pass" : "fail",
    detail:
      missing.length === 0
        ? "待机 / 行走 / 奔跑 / 跳跃 / 攻击 五个基础动作齐全"
        : `缺少 ${missing.join("、")}，客户无法在关卡里检查对应动作`,
  });

  const loopActions: ArcadeAction[] = ["idle", "walk", "run"];
  const thinFrames = loopActions.filter((action) => {
    const strip = strips[action];
    if (!strip) return false;
    return Math.max(1, strip.frames) < 4;
  });
  items.push({
    key: "frames",
    label: "循环帧数",
    status: thinFrames.length === 0 ? "pass" : "warn",
    detail:
      thinFrames.length === 0
        ? "循环动作均 ≥ 4 帧，跑动步态不会跳帧"
        : `${thinFrames.join("、")} 少于 4 帧，循环时会有明显顿感`,
  });

  const fps = Object.values(strips).find((strip) => strip.fps)?.fps ?? 0;
  items.push({
    key: "fps",
    label: "帧率契约",
    status: fps > 0 ? "pass" : "warn",
    detail: fps > 0 ? `动作条带声明 ${fps} fps` : "未声明 fps，播放按 10 fps 回落",
  });

  const heights = Object.values(strips)
    .map((strip) => strip.height)
    .filter((height) => Number.isFinite(height) && height > 0);
  const minHeight = heights.length > 0 ? Math.min(...heights) : 0;
  items.push({
    key: "resolution",
    label: "源分辨率",
    status: minHeight >= 128 ? "pass" : minHeight >= 96 ? "warn" : "fail",
    detail:
      minHeight === 0
        ? "没有可读取的条带尺寸，无法确认显示清晰度"
        : minHeight >= 128
          ? `单帧高 ${minHeight}px，放到关卡里仍然清晰`
          : `单帧高 ${minHeight}px，放大后易发糊（godogen 建议显示尺寸 ≥128px）`,
  });

  items.push({
    key: "decode",
    label: "帧图完整性",
    status: loadErrors.length === 0 ? "pass" : "fail",
    detail:
      loadErrors.length === 0
        ? "全部动作条带解码成功"
        : `${loadErrors.length} 张条带加载失败，关卡中会出现空帧`,
  });

  if (runtime) {
    const cleanRun = runtime.reachedGoal && runtime.falls <= 1 && runtime.avgFps >= 45;
    const nearMiss =
      runtime.reachedGoal && (runtime.falls > 1 || runtime.avgFps < 45);
    items.push({
      key: "runtime",
      label: "本轮运行",
      status: cleanRun ? "pass" : nearMiss ? "warn" : "fail",
      detail: !runtime.reachedGoal
        ? `未到达终点（金币 ${runtime.coins}/${runtime.totalCoins}，掉落 ${runtime.falls} 次）`
        : `到达终点 · 金币 ${runtime.coins}/${runtime.totalCoins} · 掉落 ${runtime.falls} 次 · 平均 ${Math.round(runtime.avgFps)} fps`,
    });
  }

  const failed = items.some((item) => item.status === "fail");
  const warned = items.some((item) => item.status === "warn");
  return {
    items,
    verdict: failed ? "fail" : warned ? "warn" : "pass",
    passed: items.filter((item) => item.status === "pass").length,
    total: items.length,
  };
}

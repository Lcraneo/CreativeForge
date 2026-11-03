import { describe, expect, it } from "vitest";
import type { PlaytestStrip } from "../types";
import {
  GROUND_Y,
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
} from "./arcade";

const IDLE_INPUT = { left: false, right: false, run: false, jump: false };

function strip(overrides: Partial<PlaytestStrip> = {}): PlaytestStrip {
  return {
    url: "/strip.png",
    frames: 8,
    width: 128,
    height: 128,
    engine: "rigged",
    fps: 16,
    ...overrides,
  };
}

function stripsFor(actions: ArcadeAction[], overrides: Partial<PlaytestStrip> = {}) {
  return Object.fromEntries(actions.map((action) => [action, strip(overrides)]));
}

describe("buildLevel", () => {
  it("同一角色生成同一条路线", () => {
    expect(buildLevel("asset-1")).toEqual(buildLevel("asset-1"));
  });

  it("不同角色只有浮动平台偏移差异，终点与金币总数稳定", () => {
    const level = buildLevel("asset-1");
    expect(level.goalX).toBe(2480);
    expect(level.coins).toHaveLength(14);
    expect(level.platforms.some((platform) => platform.kind === "ground")).toBe(true);
    expect(level.coins.every((coin) => coin.y < GROUND_Y)).toBe(true);
  });
});

describe("stepPlayer", () => {
  it("静止时站稳在地面", () => {
    const level = buildLevel("a");
    const next = stepPlayer(initialPlayer(level), IDLE_INPUT, level, 1 / 60);
    expect(next.y).toBeCloseTo(GROUND_Y, 5);
    expect(next.onGround).toBe(true);
    expect(next.x).toBe(level.spawnX);
  });

  it("向右行走按速度推进并按步长累计（单帧上限 50ms）", () => {
    const level = buildLevel("a");
    const start = initialPlayer(level);
    const next = stepPlayer(start, { ...IDLE_INPUT, right: true }, level, 0.05);
    expect(next.x).toBeCloseTo(start.x + 9, 5);
    expect(next.facing).toBe(1);
  });

  it("起跳离地，随后落回地面", () => {
    const level = buildLevel("a");
    let state = stepPlayer(initialPlayer(level), { ...IDLE_INPUT, jump: true }, level, 1 / 60);
    expect(state.onGround).toBe(false);
    expect(state.y).toBeLessThan(GROUND_Y);

    for (let index = 0; index < 300 && !state.onGround; index += 1) {
      state = stepPlayer(state, IDLE_INPUT, level, 1 / 60);
    }
    expect(state.onGround).toBe(true);
    expect(state.y).toBeCloseTo(GROUND_Y, 4);
  });

  it("下落时能落在浮动平台上", () => {
    const level = buildLevel("a");
    let state: PlayerState = { x: 900, y: 230, vx: 0, vy: 60, onGround: false, facing: 1 };
    for (let index = 0; index < 120 && !state.onGround; index += 1) {
      state = stepPlayer(state, IDLE_INPUT, level, 1 / 60);
    }
    expect(state.onGround).toBe(true);
    expect(state.y).toBe(276);
  });

  it("走出平台会坠落到判死线", () => {
    const level = buildLevel("a");
    let state = initialPlayer(level);
    state.x = 700; // 第一个坑内，两侧地面都够不着
    for (let index = 0; index < 240; index += 1) {
      state = stepPlayer(state, IDLE_INPUT, level, 1 / 60);
    }
    expect(isFallen(state)).toBe(true);
  });
});

describe("respawn / coins / action", () => {
  it("复活回到检查点地面", () => {
    const level = buildLevel("a");
    const state = respawn(level, 700);
    expect(state.x).toBe(700);
    expect(state.y).toBe(GROUND_Y);
    expect(state.onGround).toBe(true);
    expect(state.vy).toBe(0);
  });

  it("复活到高台检查点的实际支撑面", () => {
    const level = buildLevel("a");
    const state = respawn(level, 900);
    expect(state.y).toBe(276);
    expect(state.onGround).toBe(true);
  });

  it("只拾取半径内且未吃过的金币", () => {
    const level = buildLevel("a");
    const state: PlayerState = {
      x: 300,
      y: GROUND_Y,
      vx: 0,
      vy: 0,
      onGround: true,
      facing: 1,
    };
    expect(collectCoins(state, level.coins, new Set()).map((coin) => coin.id)).toContain("c1");
    expect(collectCoins(state, level.coins, new Set(["c1"]))).toHaveLength(0);
  });

  it("动作优先级：攻击 > 跳跃 > 跑/走 > 待机", () => {
    const base: PlayerState = {
      x: 0,
      y: GROUND_Y,
      vx: 0,
      vy: 0,
      onGround: true,
      facing: 1,
    };
    expect(pickAction(base, true)).toBe("attack");
    expect(pickAction({ ...base, onGround: false }, false)).toBe("jump");
    // 空中按攻击仍是跳跃：没有 jump-attack 条带，混用会串到腿部帧
    expect(pickAction({ ...base, onGround: false }, true)).toBe("jump");
    expect(pickAction({ ...base, vx: 180 }, false)).toBe("walk");
    expect(pickAction({ ...base, vx: 300 }, false)).toBe("run");
    expect(pickAction(base, false)).toBe("idle");
  });
});

describe("cameraX", () => {
  it("跟随角色并收拢在关卡边界内", () => {
    expect(cameraX(0, 800, 2600)).toBe(0);
    expect(cameraX(1200, 800, 2600)).toBeCloseTo(880, 5);
    expect(cameraX(2500, 800, 2600)).toBe(1800);
    expect(cameraX(100, 3000, 2600)).toBe(0);
  });
});

describe("inspectCharacter", () => {
  const actions: ArcadeAction[] = ["idle", "walk", "run", "jump", "attack"];

  it("五项动作齐全且条带达标时判定通过", () => {
    const report = inspectCharacter({ actions, strips: stripsFor(actions) });
    expect(report.verdict).toBe("pass");
    expect(report.passed).toBe(report.total);
  });

  it("缺动作直接判失败", () => {
    const report = inspectCharacter({
      actions: ["idle", "walk", "jump", "attack"],
      strips: stripsFor(["idle", "walk", "jump", "attack"]),
    });
    expect(report.verdict).toBe("fail");
    expect(report.items.find((item) => item.key === "coverage")?.detail).toContain("run");
  });

  it("低分辨率与加载失败会被记录", () => {
    const report = inspectCharacter({
      actions,
      strips: stripsFor(actions, { height: 64 }),
      loadErrors: ["/broken.png"],
    });
    expect(report.items.find((item) => item.key === "resolution")?.status).toBe("fail");
    expect(report.items.find((item) => item.key === "decode")?.status).toBe("fail");
  });

  it("运行项只在跑完后追加，并按实跑结果判定", () => {
    const live = inspectCharacter({ actions, strips: stripsFor(actions) });
    expect(live.items.some((item) => item.key === "runtime")).toBe(false);

    const failed = inspectCharacter({
      actions,
      strips: stripsFor(actions),
      runtime: { reachedGoal: false, falls: 0, coins: 2, totalCoins: 14, avgFps: 60 },
    });
    expect(failed.items.find((item) => item.key === "runtime")?.status).toBe("fail");
    expect(failed.verdict).toBe("fail");

    const passed = inspectCharacter({
      actions,
      strips: stripsFor(actions),
      runtime: { reachedGoal: true, falls: 0, coins: 12, totalCoins: 14, avgFps: 58 },
    });
    expect(passed.verdict).toBe("pass");
  });
});

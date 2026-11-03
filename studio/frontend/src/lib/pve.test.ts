import { describe, expect, it } from "vitest";
import {
  PVE_ACTION_SLOTS,
  PVE_DEPTH_SCALE,
  PVE_MOVE_SPEED,
  PVE_SLAM_MAX_Z,
  advancePveStage,
  createPveRuntime,
  pveActionSlot,
  pveEnemyPose,
  pveGroundDistance,
  pveHud,
  pvePoseProgress,
  pveSegmentHitsBox,
  pveSortByDepth,
  pveSpriteTime,
  retryPveStage,
  stepPve,
  togglePvePause,
  type PveInput,
  type PveRuntime,
} from "./pve";
import type { PveCampaign, PveEnemySpawn, PveStage, PveStageId } from "../types";

function enemy(id: string, overrides: Partial<PveEnemySpawn> = {}): PveEnemySpawn {
  return {
    id,
    profile_id: `profile_${id}`,
    asset_id: `asset_${id}`,
    name: `敌人 ${id}`,
    kind: "minion",
    x: 1100,
    y: 620,
    max_hp: 4,
    speed: 0,
    damage: 1,
    attack_interval: 2.2,
    display_height: 92,
    behavior: "chaser",
    element: "nature",
    projectile_color: "#a9df72",
    tags: ["test"],
    ...overrides,
  };
}

function stage(
  id: PveStageId,
  kind: "minion" | "boss",
  enemies: PveEnemySpawn[],
  arena: Partial<PveStage["arena"]> = {},
): PveStage {
  return {
    id,
    title: `第 ${Number(id.slice(-1))} 关`,
    kind,
    background_url: `bg-${id}.png`,
    arena: { width: 1400, depth: 760, spawn_x: 700, spawn_y: 380, ...arena },
    enemies,
  };
}

const campaign: PveCampaign = {
  schema_version: 2,
  seed: "test",
  stages: [
    stage("stage_1", "minion", [enemy("a")]),
    stage("stage_2", "minion", [
      enemy("b"),
      enemy("c", { x: 1200, y: 300, profile_id: "profile_c", asset_id: "asset_c" }),
    ]),
    stage("stage_3", "boss", [
      enemy("boss", {
        kind: "boss",
        x: 1150,
        y: 500,
        max_hp: 20,
        damage: 2,
        display_height: 224,
        behavior: "guardian",
      }),
    ]),
  ],
};

const idle: PveInput = {
  left: false,
  right: false,
  up: false,
  down: false,
  run: false,
  jump: false,
  shoot: false,
  guard: false,
  dodge: false,
};

/** 把敌人调成静止且永不主动出手，只保留玩家可控的测试环境。 */
function quietRuntime(): PveRuntime {
  const runtime = createPveRuntime(campaign);
  for (const item of runtime.enemies) {
    item.speed = 0;
    item.shootCooldown = Number.POSITIVE_INFINITY;
  }
  return runtime;
}

function slamRuntime(playerZ: number, playerOffsetY = 0): PveRuntime {
  const runtime = quietRuntime();
  const item = runtime.enemies[0];
  item.ability = "slam";
  item.abilityStage = "active";
  item.abilityStartedAt = runtime.stageTime;
  item.abilityStageStartedAt = runtime.stageTime;
  item.abilityUntil = runtime.stageTime + 5;
  item.abilityHit = false;
  runtime.player.x = item.x;
  runtime.player.y = item.y + playerOffsetY;
  runtime.player.z = playerZ;
  runtime.player.vz = 0;
  runtime.player.onGround = playerZ === 0;
  return runtime;
}

describe("PVE 2.5D 地面移动", () => {
  it("supports eight ground directions with compressed depth speed", () => {
    const combos: Array<[Partial<PveInput>, number, number]> = [
      [{ right: true }, 1, 0],
      [{ left: true }, -1, 0],
      [{ down: true }, 0, 1],
      [{ up: true }, 0, -1],
      [{ right: true, down: true }, 1, 1],
      [{ left: true, up: true }, -1, -1],
      [{ right: true, up: true }, 1, -1],
      [{ left: true, down: true }, -1, 1],
    ];
    for (const [input, signX, signY] of combos) {
      const runtime = quietRuntime();
      const start = { x: runtime.player.x, y: runtime.player.y };
      stepPve(runtime, { ...idle, ...input }, 0.05);
      const dx = runtime.player.x - start.x;
      const dy = runtime.player.y - start.y;
      if (signX === 0) expect(Math.abs(dx)).toBeLessThan(1e-9);
      else expect(Math.sign(dx)).toBe(signX);
      if (signY === 0) expect(Math.abs(dy)).toBeLessThan(1e-9);
      else expect(Math.sign(dy)).toBe(signY);
      // 纵深方向上 1.6 的压缩让地面实际位移保持恒定速度。
      expect(Math.hypot(dx, dy * PVE_DEPTH_SCALE)).toBeCloseTo(PVE_MOVE_SPEED * 0.05, 6);
    }
  });

  it("clamps the player inside the fixed arena", () => {
    const runtime = quietRuntime();
    for (let index = 0; index < 80; index += 1) {
      stepPve(runtime, { ...idle, left: true, up: true }, 0.05);
    }
    expect(runtime.player.x).toBeGreaterThanOrEqual(20);
    expect(runtime.player.y).toBeGreaterThanOrEqual(20);
    expect(runtime.player.x).toBeLessThanOrEqual(1380);
    expect(runtime.player.y).toBeLessThanOrEqual(740);
  });

  it("jumps in z and returns to the ground", () => {
    const runtime = quietRuntime();
    stepPve(runtime, { ...idle, jump: true }, 0.05);
    expect(runtime.player.z).toBeGreaterThan(0);
    expect(runtime.player.onGround).toBe(false);
    for (let index = 0; index < 40; index += 1) stepPve(runtime, idle, 0.05);
    expect(runtime.player.z).toBe(0);
    expect(runtime.player.onGround).toBe(true);
  });
});

describe("PVE 2.5D 碰撞", () => {
  it("compresses y distance by 1.6 on the ground plane", () => {
    expect(pveGroundDistance(0, 0, 100, 0)).toBe(100);
    expect(pveGroundDistance(0, 0, 0, 100)).toBeCloseTo(160, 6);
    expect(pveGroundDistance(0, 0, 100, 100)).toBeCloseTo(Math.hypot(100, 160), 6);
  });

  it("fires straight shots that miss depth-offset enemies", () => {
    const runtime = quietRuntime();
    const target = runtime.enemies[0];
    runtime.player.x = target.x - 200;
    runtime.player.y = target.y + 200;
    runtime.player.facing = 1;
    stepPve(runtime, { ...idle, shoot: true }, 0.05);
    const shot = runtime.projectiles.find((item) => item.owner === "player");
    expect(shot?.vy).toBe(0);
    for (let index = 0; index < 20; index += 1) stepPve(runtime, idle, 0.05);
    expect(target.hp).toBe(target.max_hp);
  });

  it("keeps a straight shot when the target is far in depth", () => {
    const runtime = quietRuntime();
    const target = runtime.enemies[0];
    runtime.player.x = target.x - 200;
    runtime.player.y = 20;
    runtime.player.facing = 1;
    target.y = 740;
    stepPve(runtime, { ...idle, shoot: true }, 0.05);
    const shot = runtime.projectiles.find((item) => item.owner === "player");
    expect(shot?.vy).toBe(0);
    for (let index = 0; index < 20; index += 1) stepPve(runtime, idle, 0.05);
    expect(target.hp).toBe(target.max_hp);
  });

  it("uses the compressed distance for slam range", () => {
    const near = slamRuntime(0, 0);
    stepPve(near, idle, 0.01);
    expect(near.playerHp).toBe(5);

    // 纵深偏移 100 会按 1.6 变成 160，超出 150 的震地半径。
    const offset = slamRuntime(0, 100);
    stepPve(offset, idle, 0.01);
    expect(offset.playerHp).toBe(6);
  });

  it("lets a jump above the low slam height dodge ground damage", () => {
    const grounded = slamRuntime(0);
    stepPve(grounded, idle, 0.01);
    expect(grounded.playerHp).toBe(5);

    const airborne = slamRuntime(120);
    stepPve(airborne, idle, 0.01);
    expect(airborne.player.z).toBeGreaterThan(PVE_SLAM_MAX_Z);
    expect(airborne.playerHp).toBe(6);
  });
});

describe("PVE 2.5D 弹道", () => {
  it("sweeps projectiles in x/y/z and hits an aligned enemy", () => {
    const runtime = quietRuntime();
    const target = runtime.enemies[0];
    runtime.player.x = target.x - 200;
    runtime.player.y = target.y;
    runtime.player.facing = 1;
    stepPve(runtime, { ...idle, shoot: true }, 0.05);
    const shot = runtime.projectiles.find((item) => item.owner === "player");
    expect(shot).toBeTruthy();
    expect(shot?.y).toBeCloseTo(runtime.player.y, 6);
    // 玩家子弹按发射时的高度直线飞行，不会向目标中心转向。
    expect(shot?.z).toBeCloseTo(runtime.player.z + 42, 6);
    for (let index = 0; index < 20; index += 1) stepPve(runtime, idle, 0.05);
    expect(target.hp).toBe(target.max_hp - 1);
    expect(runtime.shotsHit).toBeGreaterThan(0);
  });

  it("keeps an upward aimed shot travelling straight", () => {
    const runtime = quietRuntime();
    const target = runtime.enemies[0];
    runtime.player.x = target.x - 200;
    runtime.player.y = target.y;
    runtime.player.facing = 1;
    stepPve(runtime, { ...idle, shoot: true, aimZ: 1 }, 0.05);
    const shot = runtime.projectiles.find((item) => item.owner === "player");
    expect(shot?.vz).toBeGreaterThan(0);
    for (let index = 0; index < 20; index += 1) stepPve(runtime, idle, 0.05);
    expect(target.hp).toBe(target.max_hp);
  });

  it("detects a 3D segment crossing a box only when all axes overlap", () => {
    const box = { minX: 100, maxX: 140, minY: 100, maxY: 130, minZ: 0, maxZ: 80 };
    expect(pveSegmentHitsBox({ x: 0, y: 112, z: 40 }, { x: 200, y: 0, z: 0 }, box)).toBe(0.5);
    expect(pveSegmentHitsBox({ x: 0, y: 112, z: 140 }, { x: 200, y: 0, z: 0 }, box)).toBeNull();
    expect(pveSegmentHitsBox({ x: 0, y: 300, z: 40 }, { x: 200, y: 0, z: 0 }, box)).toBeNull();
  });

  it("damages the player with an enemy projectile in the same 3D cell", () => {
    const runtime = quietRuntime();
    stepPve(runtime, idle, 1 / 60);
    runtime.projectiles.push({
      id: 99,
      owner: "enemy",
      x: runtime.player.x,
      y: runtime.player.y,
      z: 40,
      vx: 0,
      vy: 0,
      vz: 0,
      radius: 8,
      damage: 1,
      ttl: 2,
      color: "#fff",
    });
    stepPve(runtime, idle, 1 / 60);
    expect(runtime.playerHp).toBe(5);
  });

  it("restores the guard after a two second cooldown", () => {
    const runtime = quietRuntime();
    stepPve(runtime, { ...idle, guard: true }, 1 / 60);
    expect(runtime.guarding).toBe(true);
    expect(runtime.playerHp).toBe(6);
    runtime.projectiles.push({
      id: 98,
      owner: "enemy",
      x: runtime.player.x,
      y: runtime.player.y,
      z: 40,
      vx: 0,
      vy: 0,
      vz: 0,
      radius: 8,
      damage: 1,
      ttl: 2,
      color: "#fff",
    });
    stepPve(runtime, { ...idle, guard: true }, 1 / 60);
    expect(runtime.guardAvailable).toBe(false);
    expect(runtime.guardCooldownUntil - runtime.stageTime).toBeCloseTo(2, 6);
    expect(pveHud(runtime).guardAvailable).toBe(false);
    for (let index = 0; index < 50; index += 1) stepPve(runtime, idle, 0.05);
    expect(pveHud(runtime).guardAvailable).toBe(true);
  });
});

describe("PVE 2.5D 渲染排序", () => {
  it("sorts actors from far to near by y", () => {
    const items = [{ y: 300, id: "front" }, { y: 120, id: "far" }, { y: 240, id: "mid" }];
    expect(pveSortByDepth(items).map((item) => item.id)).toEqual(["far", "mid", "front"]);
    expect(items[0].id).toBe("front");
  });
});

describe("PVE 三关推进", () => {
  it("enters cleared after a wipe and never auto-loads the next stage", () => {
    const runtime = quietRuntime();
    runtime.projectiles.push({
      id: 7,
      owner: "enemy",
      x: 120,
      y: 120,
      z: 10,
      vx: 0,
      vy: 0,
      vz: 0,
      radius: 6,
      damage: 1,
      ttl: 5,
      color: "#fff",
    });
    runtime.enemies[0].hp = 0;
    runtime.enemies[0].deathAt = runtime.stageTime;
    stepPve(runtime, idle, 0.05);
    expect(runtime.phase).toBe("cleared");
    expect(runtime.stageIndex).toBe(0);
    expect(runtime.projectiles).toHaveLength(0);
    for (let index = 0; index < 12; index += 1) stepPve(runtime, idle, 0.05);
    expect(runtime.phase).toBe("cleared");
    expect(runtime.stageIndex).toBe(0);
  });

  it("only loads the next stage when advance is called", () => {
    const runtime = quietRuntime();
    expect(advancePveStage(runtime)).toBe(false);
    runtime.enemies[0].hp = 0;
    stepPve(runtime, idle, 0.05);
    expect(advancePveStage(runtime)).toBe(true);
    expect(runtime.stageIndex).toBe(1);
    expect(runtime.phase).toBe("playing");
    expect(runtime.enemies.map((item) => item.id)).toEqual(["b", "c"]);
    expect(runtime.stageTime).toBe(0);
  });

  it("keeps hp and cumulative stats across stages while resetting cooldowns", () => {
    const runtime = quietRuntime();
    runtime.playerHp = 4;
    runtime.damageTaken = 2;
    runtime.shotsFired = 5;
    runtime.shotsHit = 3;
    runtime.shotCooldown = 5;
    runtime.guardAvailable = false;
    runtime.guardCooldownUntil = 3;
    for (let index = 0; index < 4; index += 1) stepPve(runtime, idle, 0.05);
    runtime.enemies[0].hp = 0;
    stepPve(runtime, idle, 0.05);
    const totalTime = runtime.totalTime;
    expect(advancePveStage(runtime)).toBe(true);
    expect(runtime.playerHp).toBe(4);
    expect(runtime.damageTaken).toBe(2);
    expect(runtime.shotsFired).toBe(5);
    expect(runtime.shotsHit).toBe(3);
    expect(runtime.totalTime).toBeCloseTo(totalTime, 6);
    expect(runtime.stageTime).toBe(0);
    expect(runtime.shotCooldown).toBe(0);
    expect(runtime.guardAvailable).toBe(true);
  });

  it("wins the campaign only after the stage 3 boss dies", () => {
    const runtime = quietRuntime();
    runtime.enemies[0].hp = 0;
    stepPve(runtime, idle, 0.05);
    expect(advancePveStage(runtime)).toBe(true);

    for (const item of runtime.enemies) item.hp = 0;
    stepPve(runtime, idle, 0.05);
    expect(runtime.phase).toBe("cleared");
    expect(advancePveStage(runtime)).toBe(true);
    expect(runtime.stageIndex).toBe(2);
    expect(runtime.phase).toBe("playing");

    const boss = runtime.enemies[0];
    expect(boss.kind).toBe("boss");
    expect(pveHud(runtime).bossActive).toBe(true);
    expect(pveHud(runtime).stageCount).toBe(3);
    boss.hp = 0;
    boss.deathAt = runtime.stageTime;
    stepPve(runtime, idle, 0.05);
    expect(runtime.phase).toBe("campaign_won");
  });

  it("switches the boss to phase two at half hp", () => {
    const runtime = quietRuntime();
    runtime.enemies[0].hp = 0;
    stepPve(runtime, idle, 0.05);
    expect(advancePveStage(runtime)).toBe(true);
    for (const item of runtime.enemies) item.hp = 0;
    stepPve(runtime, idle, 0.05);
    expect(advancePveStage(runtime)).toBe(true);

    const boss = runtime.enemies[0];
    expect(boss.kind).toBe("boss");
    boss.hp = boss.max_hp / 2;
    boss.shootCooldown = 0;
    stepPve(runtime, idle, 0.01);
    expect(boss.phase).toBe(2);
    expect(runtime.notice).toContain("第二阶段");
  });

  it("retries the current stage and restores the entry snapshot", () => {
    const runtime = quietRuntime();
    runtime.playerHp = 1;
    runtime.projectiles.push({
      id: 11,
      owner: "enemy",
      x: runtime.player.x,
      y: runtime.player.y,
      z: 40,
      vx: 0,
      vy: 0,
      vz: 0,
      radius: 8,
      damage: 1,
      ttl: 2,
      color: "#fff",
    });
    stepPve(runtime, idle, 1 / 60);
    expect(runtime.phase).toBe("campaign_lost");
    expect(runtime.playerHp).toBe(0);

    expect(retryPveStage(runtime)).toBe(true);
    expect(runtime.phase).toBe("playing");
    expect(runtime.stageIndex).toBe(0);
    expect(runtime.playerHp).toBe(6);
    expect(runtime.damageTaken).toBe(0);
    expect(runtime.projectiles).toHaveLength(0);
    expect(runtime.stageTime).toBe(0);
    expect(retryPveStage(runtime)).toBe(false);
  });
});

describe("PVE 自定义敌人与动作", () => {
  it("loads custom enemies into every stage by profile and asset", () => {
    const runtime = quietRuntime();
    expect(runtime.enemies[0]).toMatchObject({ profile_id: "profile_a", asset_id: "asset_a" });
    runtime.enemies[0].hp = 0;
    stepPve(runtime, idle, 0.05);
    advancePveStage(runtime);
    expect(runtime.enemies.map((item) => [item.profile_id, item.asset_id])).toEqual([
      ["profile_b", "asset_b"],
      ["profile_c", "asset_c"],
    ]);
    for (const item of runtime.enemies) item.hp = 0;
    stepPve(runtime, idle, 0.05);
    advancePveStage(runtime);
    expect(runtime.enemies[0]).toMatchObject({
      kind: "boss",
      profile_id: "profile_boss",
      asset_id: "asset_boss",
    });
  });

  it("maps all six action slots without overwriting base actions", () => {
    expect(PVE_ACTION_SLOTS).toEqual(["idle", "walk", "windup", "attack", "hurt", "death"]);
    expect(pveActionSlot("custom:windup")).toBe("windup");
    expect(pveActionSlot("custom:hurt")).toBe("hurt");
    expect(pveActionSlot("custom:death")).toBe("death");
    expect(pveActionSlot("custom:celebrate")).toBe("custom:celebrate");
    expect(pveActionSlot("attack")).toBe("attack");
    expect(pveActionSlot("idle")).toBe("idle");
  });

  it("prioritizes death, hurt and windup poses", () => {
    const runtime = quietRuntime();
    const item = runtime.enemies[0];
    item.abilityStage = "windup";
    expect(pveEnemyPose(item, 1)).toBe("windup");
    item.hitFlashUntil = 2;
    expect(pveEnemyPose(item, 1)).toBe("hurt");
    item.hp = 0;
    expect(pveEnemyPose(item, 1)).toBe("death");
  });

  it("advances windup, hurt and death strips instead of freezing on frame 0", () => {
    const runtime = quietRuntime();
    const item = runtime.enemies[0];
    item.ability = "shot";
    item.abilityStartedAt = 0.5;
    const startFrame = pveSpriteTime("windup", item, 0.5, 8, 10);
    const midFrame = pveSpriteTime("windup", item, 0.8, 8, 10);
    expect(startFrame).toBe(0);
    expect(midFrame).toBeCloseTo(0.4, 6);
    expect(midFrame).toBeGreaterThan(startFrame);
    expect(pvePoseProgress("windup", item, 0.8)).toBeCloseTo(0.5, 6);

    item.hitFlashUntil = 1;
    const hurtEarly = pveSpriteTime("hurt", item, 0.91, 6, 10);
    const hurtLate = pveSpriteTime("hurt", item, 0.97, 6, 10);
    expect(hurtEarly).toBeCloseTo(0.3, 6);
    expect(hurtLate).toBeGreaterThan(hurtEarly);

    item.deathAt = 0;
    const deathEarly = pveSpriteTime("death", item, 0.15, 4, 10);
    const deathLate = pveSpriteTime("death", item, 0.45, 4, 10);
    expect(deathEarly).toBeCloseTo(0.1, 6);
    expect(deathLate).toBeCloseTo(0.3, 6);
    expect(deathLate).toBeGreaterThan(deathEarly);
  });
});

describe("PVE 暂停", () => {
  it("freezes the fight while paused", () => {
    const runtime = quietRuntime();
    togglePvePause(runtime);
    const before = runtime.stageTime;
    stepPve(runtime, idle, 0.05);
    expect(runtime.stageTime).toBe(before);
    expect(pveHud(runtime).paused).toBe(true);
    togglePvePause(runtime);
    expect(pveHud(runtime).paused).toBe(false);
  });
});

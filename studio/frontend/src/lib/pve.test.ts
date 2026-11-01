import { describe, expect, it } from "vitest";
import { backgroundLayerBlend, createPveRuntime, pveHud, stepPve, togglePvePause, pveEnemyPose, pveActionSlot, PVE_ACTION_SLOTS } from "./pve";
import type { PveLevel } from "../types";

const level: PveLevel = {
  seed: "test",
  width: 1800,
  groundY: 348,
  spawnX: 120,
  goalX: 1380,
  platforms: [{ x: 0, y: 348, width: 1800, height: 72, kind: "ground" }],
  enemies: [
    {
      id: "slime_1",
      asset_id: "ast64960",
      name: "森林史莱姆",
      kind: "slime",
      x: 700,
      y: 348,
      max_hp: 2,
      speed: 60,
      damage: 1,
      attack_interval: 2.4,
      display_height: 92,
    },
    {
      id: "boss_1",
      asset_id: "ast60574",
      name: "冰霜巨龙",
      kind: "boss",
      x: 1380,
      y: 348,
      max_hp: 2,
      speed: 42,
      damage: 2,
      attack_interval: 1.35,
      display_height: 224,
    },
  ],
  encounters: [
    {
      id: "encounter_1",
      title: "前庭",
      kind: "combat",
      trigger_x: 500,
      lock_x: 850,
      enemy_ids: ["slime_1"],
    },
    {
      id: "encounter_boss",
      title: "守关战",
      kind: "boss",
      trigger_x: 1200,
      lock_x: 1275,
      enemy_ids: ["boss_1"],
    },
  ],
};

const input = {
  left: false,
  right: false,
  run: false,
  jump: false,
  shoot: false,
  guard: false,
};

describe("PVE runtime", () => {
  it("maps the six-action package without overwriting base actions", () => {
    expect(PVE_ACTION_SLOTS).toEqual(["idle", "walk", "windup", "attack", "hurt", "death"]);
    expect(pveActionSlot("custom:windup")).toBe("windup");
    expect(pveActionSlot("custom:hurt")).toBe("hurt");
    expect(pveActionSlot("custom:death")).toBe("death");
    expect(pveActionSlot("custom:celebrate")).toBe("custom:celebrate");
    expect(pveActionSlot("attack")).toBe("attack");
  });
  it("lets ground melee enemies jump toward a reachable platform", () => {
    const arena: PveLevel = {
      ...level,
      platforms: [...level.platforms, { x: 520, y: 284, width: 220, height: 16, kind: "floating" }],
    };
    const runtime = createPveRuntime(arena);
    runtime.player.x = 600;
    runtime.player.y = 284;
    runtime.player.onGround = true;
    runtime.enemies[0].behavior = "chaser";
    runtime.enemies[0].shootCooldown = 99;
    stepPve(runtime, arena, input, 0.05);
    expect(runtime.enemies[0].navOnGround).toBe(false);
    expect(runtime.enemies[0].navVy).toBeLessThan(0);
    for (let index = 0; index < 30; index += 1) stepPve(runtime, arena, input, 0.05);
    expect(runtime.enemies[0].y).toBeLessThan(level.groundY);
  });

  it("uses boss cover as real projectile collision", () => {
    const arena: PveLevel = {
      ...level,
      covers: [{ id: "cover", x: 620, y: 348, width: 40, height: 120 }],
    };
    const runtime = createPveRuntime(arena);
    runtime.player.x = 530;
    runtime.projectiles.push({ id: 77, owner: "player", x: 600, y: 300, vx: 1000, vy: 0, radius: 5, damage: 1, ttl: 1, color: "#fff" });
    const enemyHp = runtime.enemies[0].hp;
    stepPve(runtime, arena, input, 0.05);
    expect(runtime.projectiles).toHaveLength(0);
    expect(runtime.enemies[0].hp).toBe(enemyHp);
  });
  it("exposes separate windup, hurt and death poses with death priority", () => {
    const enemy = createPveRuntime(level).enemies[0];
    enemy.abilityStage = "windup";
    expect(pveEnemyPose(enemy, 1)).toBe("windup");
    enemy.hitFlashUntil = 2;
    expect(pveEnemyPose(enemy, 1)).toBe("hurt");
    enemy.hp = 0;
    expect(pveEnemyPose(enemy, 1)).toBe("death");
  });
  it("guardians can contest a player on a platform instead of endlessly slamming below", () => {
    const runtime = createPveRuntime(level);
    runtime.player.x = 600;
    runtime.player.y = 284;
    runtime.player.onGround = false;
    runtime.enemies[0].behavior = "guardian";
    runtime.enemies[0].shootCooldown = 0;
    stepPve(runtime, level, input, 0.01);
    expect(runtime.enemies[0].ability).toBe("shot");
    expect(runtime.enemies[0].abilityStage).toBe("windup");
  });
  it("vents warn before damage and the bridge stays safe", () => {
    const arena = { ...level, hazards: [{ id: "vent", x: 90, y: 348, width: 64, kind: "vent" as const }] };
    const runtime = createPveRuntime(arena);
    runtime.elapsed = 1.5;
    stepPve(runtime, arena, input, 0.05);
    expect(runtime.playerHp).toBe(6);
    runtime.elapsed = 2.3;
    stepPve(runtime, arena, input, 0.05);
    expect(runtime.playerHp).toBe(5);
    const safe = createPveRuntime(arena);
    safe.elapsed = 2.3;
    safe.player.y = 284;
    safe.player.onGround = false;
    stepPve(safe, arena, input, 0.05);
    expect(safe.playerHp).toBe(6);
  });
  it("dodges with a finite invulnerability window and cannot repeat while held", () => {
    const runtime = createPveRuntime(level);
    const start = runtime.player.x;
    stepPve(runtime, level, { ...input, dodge: true }, 0.05);
    expect(runtime.player.x).toBeGreaterThan(start + 20);
    expect(runtime.invulnerableUntil).toBeGreaterThan(runtime.elapsed);
    const cooldown = runtime.dodgeCooldownUntil;
    for (let i = 0; i < 40; i++) stepPve(runtime, level, { ...input, dodge: true }, 0.05);
    expect(runtime.dodgeCooldownUntil).toBe(cooldown);
    expect(runtime.invulnerableUntil).toBeLessThan(runtime.elapsed);
  });

  it("lands on floating platforms and can aim upward", () => {
    const arena = { ...level, platforms: [...level.platforms, { x: 50, y: 240, width: 200, height: 16, kind: "floating" as const }] };
    const runtime = createPveRuntime(arena);
    runtime.player.y = 230;
    runtime.player.vy = 200;
    runtime.player.onGround = false;
    stepPve(runtime, arena, input, 0.05);
    expect(runtime.player.y).toBe(240);
    expect(runtime.player.onGround).toBe(true);
    stepPve(runtime, arena, { ...input, shoot: true, aimY: -0.7 }, 0.05);
    expect(runtime.projectiles[0].vy).toBeLessThan(0);
  });
  it("crossfades between scene backgrounds instead of snapping", () => {
    expect(backgroundLayerBlend(0.5, 5)).toEqual({ from: 2, to: 3, mix: 0 });
    expect(backgroundLayerBlend(0.625, 5).mix).toBeCloseTo(0.5);
    expect(backgroundLayerBlend(1, 5)).toEqual({ from: 4, to: 4, mix: 0 });
  });

  it("starts with all enemies alive and the boss asleep", () => {
    const runtime = createPveRuntime(level);
    const hud = pveHud(runtime, level);
    expect(hud.defeated).toBe(0);
    expect(hud.total).toBe(2);
    expect(hud.bossActive).toBe(false);
  });

  it("fires exactly one projectile for one attack input", () => {
    const runtime = createPveRuntime(level);
    runtime.player.x = 530;
    stepPve(runtime, level, { ...input, shoot: true }, 1 / 60);
    expect(runtime.projectiles.filter((item) => item.owner === "player")).toHaveLength(1);
    stepPve(runtime, level, input, 1 / 60);
    expect(runtime.projectiles.filter((item) => item.owner === "player")).toHaveLength(1);
  });

  it("locks the player inside the active encounter", () => {
    const runtime = createPveRuntime(level);
    runtime.player.x = 800;
    stepPve(runtime, level, { ...input, right: true, run: true }, 0.05);
    expect(runtime.activeEncounterIndex).toBe(0);
    expect(runtime.player.x).toBeLessThanOrEqual(850);
    expect(runtime.transitionUntil).toBeGreaterThan(runtime.elapsed);
  });

  it("hits a slime with the horizontal energy shot", () => {
    const runtime = createPveRuntime(level);
    const slime = runtime.enemies.find((enemy) => enemy.kind === "slime");
    expect(slime).toBeTruthy();
    if (!slime) return;
    runtime.player.x = slime.x - 120;
    runtime.player.y = level.groundY;
    runtime.player.facing = 1;
    stepPve(runtime, level, { ...input, shoot: true }, 1 / 60);
    let sawHitstop = false;
    for (let index = 0; index < 20; index += 1) {
      stepPve(runtime, level, input, 1 / 60);
      sawHitstop ||= runtime.hitstopRemaining > 0;
    }
    expect(slime.hp).toBeLessThan(slime.max_hp);
    expect(sawHitstop).toBe(true);
    expect(runtime.audioEvents).toContain("hit");
  });

  it("wakes and defeats the boss only after the slimes are cleared", () => {
    const runtime = createPveRuntime(level);
    expect(pveHud(runtime, level).bossActive).toBe(false);
    const slime = runtime.enemies.find((enemy) => enemy.kind === "slime");
    const boss = runtime.enemies.find((enemy) => enemy.kind === "boss");
    expect(slime && boss).toBeTruthy();
    if (!slime || !boss) return;
    boss.hp = 1;
    runtime.player.x = 550;
    stepPve(runtime, level, input, 1 / 60);
    slime.hp = 0;
    stepPve(runtime, level, input, 1 / 60);
    runtime.player.x = boss.x - 105;
    stepPve(runtime, level, input, 1 / 60);
    expect(boss.awake).toBe(true);
    expect(pveHud(runtime, level).bossActive).toBe(true);
    runtime.shotCooldown = 0;
    stepPve(runtime, level, { ...input, shoot: true }, 1 / 60);
    for (let index = 0; index < 120 && runtime.status === "playing"; index += 1) {
      stepPve(runtime, level, input, 1 / 60);
    }
    expect(runtime.status).toBe("won");
  });

  it("uses the single guard cell to negate one hit", () => {
    const runtime = createPveRuntime(level);
    runtime.player.x = 600;
    stepPve(runtime, level, input, 1 / 60);
    runtime.projectiles.push({
      id: 99,
      owner: "enemy",
      x: runtime.player.x,
      y: runtime.player.y - 88,
      vx: 0,
      vy: 0,
      radius: 8,
      damage: 2,
      ttl: 1,
      color: "#fff",
    });
    stepPve(runtime, level, { ...input, guard: true }, 1 / 60);
    expect(runtime.playerHp).toBe(6);
    expect(runtime.guardAvailable).toBe(false);
    expect(runtime.audioEvents).toContain("guard");
  });

  it("freezes gameplay while paused", () => {
    const runtime = createPveRuntime(level);
    togglePvePause(runtime);
    const before = runtime.elapsed;
    stepPve(runtime, level, input, 1 / 60);
    expect(runtime.elapsed).toBe(before);
    expect(pveHud(runtime, level).paused).toBe(true);
  });

  it("does not damage enemies outside the active encounter", () => {
    const runtime = createPveRuntime(level);
    const boss = runtime.enemies[1];
    runtime.player.x = boss.x - 100;
    runtime.player.facing = 1;
    stepPve(runtime, level, { ...input, shoot: true }, 0.05);
    for (let i = 0; i < 10; i++) stepPve(runtime, level, input, 0.05);
    expect(boss.hp).toBe(boss.max_hp);
  });

  it("sweeps fast shots and knocks the closest active enemy away", () => {
    const runtime = createPveRuntime(level);
    runtime.player.x = 530;
    stepPve(runtime, level, input, 0.01);
    const enemy = runtime.enemies[0];
    enemy.speed = 0;
    const startX = enemy.x;
    runtime.projectiles.push({ id: 100, owner: "player", x: 600, y: 300, vx: 4000, vy: 0, radius: 2, damage: 1, ttl: 1, color: "#fff" });
    stepPve(runtime, level, input, 0.05);
    expect(enemy.hp).toBe(enemy.max_hp - 1);
    expect(enemy.x).toBeGreaterThan(startX);
  });

  it("does not apply contact damage when the player is above the enemy", () => {
    const runtime = createPveRuntime(level);
    runtime.player.x = 700;
    runtime.player.y = 200;
    runtime.player.onGround = false;
    stepPve(runtime, level, input, 0.01);
    expect(runtime.playerHp).toBe(6);
  });

  it("detects fast enemy shots crossing the player", () => {
    const runtime = createPveRuntime(level);
    runtime.projectiles.push({ id: 101, owner: "enemy", x: 20, y: 260, vx: 4000, vy: 0, radius: 2, damage: 1, ttl: 1, color: "#fff" });
    stepPve(runtime, level, input, 0.05);
    expect(runtime.playerHp).toBe(5);
  });

  it("telegraphs a locked shot before firing and lets the player move away", () => {
    const runtime = createPveRuntime(level);
    runtime.player.x = 530;
    const enemy = runtime.enemies[0];
    enemy.behavior = "shooter";
    enemy.speed = 0;
    enemy.shootCooldown = 0;
    stepPve(runtime, level, input, 0.01);
    expect(enemy.abilityStage).toBe("windup");
    expect(runtime.projectiles).toHaveLength(0);
    const target = enemy.abilityTargetX;
    for (let i = 0; i < 10; i++) stepPve(runtime, level, { ...input, left: true }, 0.05);
    expect(runtime.projectiles).toHaveLength(0);
    expect(enemy.abilityTargetX).toBe(target);
    for (let i = 0; i < 3; i++) stepPve(runtime, level, input, 0.05);
    expect(runtime.projectiles.some((item) => item.owner === "enemy")).toBe(true);
  });

  it("uses different abilities for charger and chaser", () => {
    for (const [behavior, expected] of [["charger", "charge"], ["chaser", "lunge"]] as const) {
      const runtime = createPveRuntime(level);
      runtime.player.x = 600;
      const enemy = runtime.enemies[0];
      enemy.behavior = behavior;
      enemy.speed = 0;
      enemy.shootCooldown = 0;
      stepPve(runtime, level, input, 0.01);
      expect(enemy.ability).toBe(expected);
      expect(enemy.abilityStage).toBe("windup");
    }
  });

  it("applies melee damage only during the active window and guard blocks it", () => {
    const runtime = createPveRuntime(level);
    runtime.player.x = 660;
    const enemy = runtime.enemies[0];
    enemy.behavior = "chaser";
    enemy.speed = 0;
    enemy.shootCooldown = 0;
    stepPve(runtime, level, input, 0.01);
    for (let i = 0; i < 8; i++) stepPve(runtime, level, input, 0.05);
    expect(runtime.playerHp).toBe(6);
    expect(runtime.guardAvailable).toBe(true);
    for (let i = 0; i < 4; i++) stepPve(runtime, level, { ...input, guard: true }, 0.05);
    expect(runtime.playerHp).toBe(6);
    expect(runtime.guardAvailable).toBe(false);
  });

  it("switches the boss to phase two and telegraphs a dodgeable slam", () => {
    const runtime = createPveRuntime(level);
    runtime.enemies[0].hp = 0;
    runtime.nextEncounterIndex = 1;
    runtime.player.x = 1270;
    const boss = runtime.enemies[1];
    boss.hp = boss.max_hp / 2;
    boss.attacks = 1;
    boss.shootCooldown = 0;
    stepPve(runtime, level, input, 0.01);
    expect(boss.phase).toBe(2);
    expect(boss.ability).toBe("slam");
    expect(boss.abilityStage).toBe("windup");
    expect(runtime.encounterNotice).toContain("第二阶段");
    for (let i = 0; i < 15; i++) stepPve(runtime, level, input, 0.05);
    expect(runtime.playerHp).toBe(6);
    stepPve(runtime, level, { ...input, jump: true }, 0.05);
    for (let i = 0; i < 5; i++) stepPve(runtime, level, input, 0.05);
    expect(runtime.playerHp).toBe(6);
  });
});

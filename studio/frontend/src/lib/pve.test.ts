import { describe, expect, it } from "vitest";
import { backgroundLayerBlend, createPveRuntime, pveHud, stepPve, togglePvePause } from "./pve";
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
});

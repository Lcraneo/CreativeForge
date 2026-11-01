/** Lightweight side-scrolling PVE rules, kept independent from rendering. */

import {
  CHAR_HEIGHT,
  type ArcadeInput,
  type ArcadeLevel,
  type PlayerState,
  initialPlayer,
  isFallen,
  respawn,
  stepPlayer,
} from "./arcade";
import type { PveEncounter, PveEnemy, PveLevel } from "../types";

export const PVE_PLAYER_HP = 6;
export const PVE_PLAYER_DAMAGE = 1;
export const PVE_SHOT_COOLDOWN = 0.22;
export const PVE_SHOT_SPEED = 720;
export const PVE_GUARD_COOLDOWN = 4;

/** Same clock drives the vent warning, rendering and damage window. */
export function pveVentStage(elapsed: number): "idle" | "warning" | "active" {
  const phase = elapsed % 3;
  return phase < 1.4 ? "idle" : phase < 2.2 ? "warning" : "active";
}

export type PveEnemyAction = "idle" | "walk" | "attack";
export type PvePose = PveEnemyAction | "windup" | "hurt" | "death";
export const PVE_ACTION_SLOTS: PvePose[] = ["idle", "walk", "windup", "attack", "hurt", "death"];
export function pveActionSlot(identity: string): string {
  const custom = identity.startsWith("custom:") ? identity.slice("custom:".length) : identity;
  return ["windup", "hurt", "death"].includes(custom) ? custom : identity;
}
export const PVE_ACTION_FALLBACK: Record<PvePose, PveEnemyAction> = {
  idle: "idle", walk: "walk", windup: "idle", attack: "attack", hurt: "idle", death: "idle",
};
export function pveEnemyPose(enemy: PveRuntimeEnemy, elapsed: number): PvePose {
  if (enemy.hp <= 0) return "death";
  if (enemy.hitFlashUntil > elapsed) return "hurt";
  if (enemy.abilityStage === "windup") return "windup";
  return enemy.action;
}
export type PveStatus = "playing" | "won" | "lost";
export type PveAudioEvent = "shot" | "hit" | "hurt" | "guard" | "clear" | "win" | "lose";
export type PveAbility = "shot" | "lunge" | "charge" | "slam";
export type PveAbilityStage = "idle" | "windup" | "active" | "recovery";

export const PVE_ABILITIES: Record<PveAbility, { windup: number; active: number; recovery: number; range: number }> = {
  shot: { windup: 0.6, active: 0.1, recovery: 0.35, range: 560 },
  lunge: { windup: 0.45, active: 0.25, recovery: 0.5, range: 140 },
  charge: { windup: 0.65, active: 0.55, recovery: 0.8, range: 380 },
  slam: { windup: 0.8, active: 0.2, recovery: 0.65, range: 190 },
};

export interface PveRuntimeEnemy extends PveEnemy {
  hp: number;
  awake: boolean;
  facing: 1 | -1;
  action: PveEnemyAction;
  shootCooldown: number;
  hitFlashUntil: number;
  ability: PveAbility | null;
  abilityStage: PveAbilityStage;
  abilityUntil: number;
  abilityTargetX: number;
  abilityTargetY: number;
  abilityDirection: 1 | -1;
  abilityHit: boolean;
  phase: 1 | 2;
  attacks: number;
  deathAt: number | null;
  navVy: number;
  navOnGround: boolean;
  navJumpCooldown: number;
}

export interface PveProjectile {
  id: number;
  owner: "player" | "enemy";
  x: number;
  y: number;
  vx: number;
  vy: number;
  radius: number;
  damage: number;
  ttl: number;
  color: string;
}

export interface PveParticle {
  x: number;
  y: number;
  vx: number;
  vy: number;
  life: number;
  color: string;
  size: number;
}

export interface PveRuntime {
  player: PlayerState;
  enemies: PveRuntimeEnemy[];
  projectiles: PveProjectile[];
  particles: PveParticle[];
  playerHp: number;
  elapsed: number;
  status: PveStatus;
  invulnerableUntil: number;
  shotCooldown: number;
  nextProjectileId: number;
  camera: number;
  activeEncounterIndex: number;
  nextEncounterIndex: number;
  clearedEncounterIds: string[];
  encounterNoticeUntil: number;
  encounterNotice: string;
  transitionUntil: number;
  guardAvailable: boolean;
  guardCooldownUntil: number;
  guarding: boolean;
  paused: boolean;
  hitstopRemaining: number;
  audioEvents: PveAudioEvent[];
  dodgeUntil: number;
  dodgeCooldownUntil: number;
  dodgeHeld: boolean;
  dodgeDirection: 1 | -1;
  damageTaken: number;
  guardsUsed: number;
  shotsFired: number;
  shotsHit: number;
}

export interface PveInput extends ArcadeInput {
  shoot: boolean;
  guard: boolean;
  dodge?: boolean;
  aimY?: number;
}

export interface PveHud {
  hp: number;
  defeated: number;
  total: number;
  bossHp: number;
  bossMaxHp: number;
  bossActive: boolean;
  elapsed: number;
  status: PveStatus;
  encounterTitle: string;
  encounterRemaining: number;
  encounterTotal: number;
  encounterIndex: number;
  encounterCount: number;
  notice: string;
  guardAvailable: boolean;
  guardCooldown: number;
  paused: boolean;
  dodgeCooldown: number;
  damageTaken: number;
  guardsUsed: number;
  accuracy: number;
  grade: "S" | "A" | "B" | "C";
}

function arcadeLevel(level: PveLevel): ArcadeLevel {
  return {
    ...level,
    platforms: level.platforms,
    coins: [],
  };
}

export function pveEncounters(level: PveLevel): PveEncounter[] {
  if (level.encounters?.length) return level.encounters;
  const boss = level.enemies.find((enemy) => enemy.kind === "boss");
  const minions = level.enemies.filter((enemy) => enemy.kind !== "boss");
  return [
    ...(minions.length
      ? [
          {
            id: "legacy_combat",
            title: "清剿战",
            kind: "combat" as const,
            trigger_x: 520,
            lock_x: (boss?.x ?? level.width - 420) - 220,
            enemy_ids: minions.map((enemy) => enemy.id),
          },
        ]
      : []),
    ...(boss
      ? [
          {
            id: "legacy_boss",
            title: "守关战",
            kind: "boss" as const,
            trigger_x: boss.x - 520,
            lock_x: boss.x - 105,
            enemy_ids: [boss.id],
          },
        ]
      : []),
  ];
}

export function backgroundLayerBlend(progress: number, count: number) {
  if (count <= 1) return { from: 0, to: 0, mix: 0 };
  const position = Math.max(0, Math.min(1, progress)) * (count - 1);
  const from = Math.floor(position);
  const to = Math.min(count - 1, from + 1);
  const linear = position - from;
  return { from, to, mix: linear * linear * (3 - 2 * linear) };
}

export function activePveEncounter(runtime: PveRuntime, level: PveLevel): PveEncounter | null {
  return pveEncounters(level)[runtime.activeEncounterIndex] ?? null;
}

export function createPveRuntime(level: PveLevel, playerHp = PVE_PLAYER_HP): PveRuntime {
  return {
    player: initialPlayer(arcadeLevel(level)),
    enemies: level.enemies.map((enemy) => ({
      ...enemy,
      hp: enemy.max_hp,
      awake: false,
      facing: -1,
      action: "idle",
      shootCooldown: 0.7,
      hitFlashUntil: 0,
      ability: null,
      abilityStage: "idle",
      abilityUntil: 0,
      abilityTargetX: 0,
      abilityTargetY: 0,
      abilityDirection: -1,
      abilityHit: false,
      phase: 1,
      attacks: 0,
      deathAt: null,
      navVy: 0,
      navOnGround: true,
      navJumpCooldown: 0,
    })),
    projectiles: [],
    particles: [],
    playerHp,
    elapsed: 0,
    status: "playing",
    invulnerableUntil: 0,
    shotCooldown: 0,
    nextProjectileId: 1,
    camera: 0,
    activeEncounterIndex: -1,
    nextEncounterIndex: 0,
    clearedEncounterIds: [],
    encounterNoticeUntil: 0,
    encounterNotice: "",
    transitionUntil: 0,
    guardAvailable: true,
    guardCooldownUntil: 0,
    guarding: false,
    paused: false,
    hitstopRemaining: 0,
    audioEvents: [],
    dodgeUntil: 0,
    dodgeCooldownUntil: 0,
    dodgeHeld: false,
    dodgeDirection: 1,
    damageTaken: 0,
    guardsUsed: 0,
    shotsFired: 0,
    shotsHit: 0,
  };
}

export function pveHud(runtime: PveRuntime, level: PveLevel): PveHud {
  const boss = runtime.enemies.find((enemy) => enemy.kind === "boss");
  const encounters = pveEncounters(level);
  const active = activePveEncounter(runtime, level);
  const remaining = active
    ? runtime.enemies.filter((enemy) => active.enemy_ids.includes(enemy.id) && enemy.hp > 0).length
    : 0;
  return {
    hp: runtime.playerHp,
    defeated: runtime.enemies.filter((enemy) => enemy.hp <= 0).length,
    total: runtime.enemies.length,
    bossHp: boss?.hp ?? 0,
    bossMaxHp: boss?.max_hp ?? 0,
    bossActive: Boolean(active?.kind === "boss" && boss && boss.hp > 0),
    elapsed: runtime.elapsed,
    status: runtime.status,
    encounterTitle: active?.title ?? "前往下一处战场",
    encounterRemaining: remaining,
    encounterTotal: active?.enemy_ids.length ?? 0,
    encounterIndex: active
      ? runtime.activeEncounterIndex + 1
      : Math.min(encounters.length, runtime.nextEncounterIndex + 1),
    encounterCount: encounters.length,
    notice: runtime.elapsed < runtime.encounterNoticeUntil ? runtime.encounterNotice : "",
    guardAvailable: runtime.guardAvailable || runtime.elapsed >= runtime.guardCooldownUntil,
    guardCooldown: Math.max(0, runtime.guardCooldownUntil - runtime.elapsed),
    paused: runtime.paused,
    dodgeCooldown: Math.max(0, runtime.dodgeCooldownUntil - runtime.elapsed),
    damageTaken: runtime.damageTaken,
    guardsUsed: runtime.guardsUsed,
    accuracy: runtime.shotsFired ? runtime.shotsHit / runtime.shotsFired : 0,
    grade: pveGrade(runtime),
  };
}

export function pveGrade(runtime: Pick<PveRuntime, "status" | "elapsed" | "damageTaken" | "guardsUsed">): "S" | "A" | "B" | "C" {
  if (runtime.status !== "won") return "C";
  if (runtime.damageTaken === 0 && runtime.elapsed <= 150) return "S";
  if (runtime.damageTaken <= 2 && runtime.elapsed <= 180) return "A";
  return runtime.damageTaken <= 5 ? "B" : "C";
}

export function enemyHalfWidth(enemy: PveRuntimeEnemy): number {
  return enemy.kind === "boss" ? enemy.display_height * 0.3 : enemy.display_height * 0.42;
}

export function enemyHeight(enemy: PveRuntimeEnemy): number {
  return enemy.display_height;
}

function emitAudio(runtime: PveRuntime, event: PveAudioEvent) {
  runtime.audioEvents.push(event);
}

function burst(
  runtime: PveRuntime,
  x: number,
  y: number,
  color: string,
  count: number,
  strength = 90,
) {
  for (let index = 0; index < count; index += 1) {
    const angle = (index / Math.max(1, count)) * Math.PI * 2;
    runtime.particles.push({
      x,
      y,
      vx: Math.cos(angle) * strength,
      vy: Math.sin(angle) * strength - 30,
      life: 0.24 + (index % 3) * 0.05,
      color,
      size: 2 + (index % 2),
    });
  }
}

function damagePlayer(runtime: PveRuntime, damage: number) {
  if (runtime.invulnerableUntil > runtime.elapsed || runtime.status !== "playing") return;
  if (runtime.guarding && runtime.guardAvailable) {
    runtime.guardAvailable = false;
    runtime.guarding = false;
    runtime.guardCooldownUntil = runtime.elapsed + PVE_GUARD_COOLDOWN;
    runtime.guardsUsed += 1;
    runtime.invulnerableUntil = runtime.elapsed + 0.3;
    emitAudio(runtime, "guard");
    burst(runtime, runtime.player.x, runtime.player.y - 82, "#9edff2", 8, 70);
    return;
  }
  runtime.playerHp = Math.max(0, runtime.playerHp - damage);
  runtime.damageTaken += damage;
  runtime.invulnerableUntil = runtime.elapsed + 0.85;
  runtime.hitstopRemaining = Math.max(runtime.hitstopRemaining, 42);
  emitAudio(runtime, "hurt");
  burst(runtime, runtime.player.x, runtime.player.y - 88, "#ff9b86", 10, 110);
  if (runtime.playerHp <= 0) {
    runtime.status = "lost";
    emitAudio(runtime, "lose");
  }
}

function spawnEnemyShot(runtime: PveRuntime, enemy: PveRuntimeEnemy) {
  const originX = enemy.x + enemy.facing * enemyHalfWidth(enemy) * 0.55;
  const originY = enemy.y - enemyHeight(enemy) * 0.55;
  const targetX = enemy.abilityTargetX;
  const targetY = enemy.abilityTargetY;
  const dx = targetX - originX;
  const dy = targetY - originY;
  const distance = Math.max(1, Math.hypot(dx, dy));
  const speed = enemy.kind === "boss" ? 285 : enemy.behavior === "shooter" ? 265 : 235;
  runtime.projectiles.push({
    id: runtime.nextProjectileId++,
    owner: "enemy",
    x: originX,
    y: originY,
    vx: (dx / distance) * speed,
    vy: (dy / distance) * speed,
    radius: enemy.kind === "boss" ? 13 : 7,
    damage: enemy.damage,
    ttl: 4,
    color: enemy.projectile_color || (enemy.kind === "boss" ? "#8feaff" : "#a9df72"),
  });
}

function chooseAbility(enemy: PveRuntimeEnemy): PveAbility {
  if (enemy.kind === "boss") return enemy.phase === 2 ? (["shot", "slam", "charge"] as const)[enemy.attacks % 3] : "shot";
  if (enemy.behavior === "charger") return "charge";
  if (enemy.behavior === "guardian") return "slam";
  if (enemy.behavior === "shooter") return "shot";
  return "lunge";
}

// Sweep the projectile through the whole frame, including its radius. Return
// the first impact fraction so a fast shot hits the nearest enemy in its path.
function impactTime(p: PveProjectile, dt: number, left: number, top: number, right: number, bottom: number): number | null {
  let enter = 0;
  let exit = 1;
  for (const [position, delta, min, max] of [
    [p.x, p.vx * dt, left - p.radius, right + p.radius],
    [p.y, p.vy * dt, top - p.radius, bottom + p.radius],
  ]) {
    if (delta === 0) {
      if (position < min || position > max) return null;
      continue;
    }
    const a = (min - position) / delta;
    const b = (max - position) / delta;
    enter = Math.max(enter, Math.min(a, b));
    exit = Math.min(exit, Math.max(a, b));
    if (enter > exit) return null;
  }
  return enter;
}

function updateEncounter(runtime: PveRuntime, level: PveLevel, playerX: number): number {
  const encounters = pveEncounters(level);
  const active = encounters[runtime.activeEncounterIndex];
  if (active) {
    const remaining = runtime.enemies.some(
      (enemy) => active.enemy_ids.includes(enemy.id) && enemy.hp > 0,
    );
    if (!remaining) {
      if (!runtime.clearedEncounterIds.includes(active.id)) {
        runtime.clearedEncounterIds.push(active.id);
        runtime.encounterNotice = `${active.title} · 已清除`;
        runtime.encounterNoticeUntil = runtime.elapsed + 1.2;
        emitAudio(runtime, "clear");
        if (active.kind === "boss") {
          runtime.status = "won";
          emitAudio(runtime, "win");
        }
      }
      runtime.activeEncounterIndex = -1;
      runtime.nextEncounterIndex = Math.min(encounters.length, runtime.nextEncounterIndex + 1);
      return playerX;
    }
    return Math.min(playerX, active.lock_x);
  }

  const next = encounters[runtime.nextEncounterIndex];
  if (next && playerX >= next.trigger_x) {
    runtime.activeEncounterIndex = runtime.nextEncounterIndex;
    runtime.encounterNotice = next.title;
    runtime.encounterNoticeUntil = runtime.elapsed + 1.1;
    runtime.transitionUntil = runtime.elapsed + 0.55;
    return Math.min(playerX, next.lock_x);
  }
  return playerX;
}

function stepEnemyNavigation(
  enemy: PveRuntimeEnemy,
  level: PveLevel,
  player: PlayerState,
  direction: 1 | -1,
  shouldMove: boolean,
  dt: number,
) {
  enemy.navJumpCooldown = Math.max(0, enemy.navJumpCooldown - dt);
  if (shouldMove) enemy.x += direction * enemy.speed * dt;
  enemy.x = Math.max(80, Math.min(level.width - 80, enemy.x));

  const canClimb = enemy.kind !== "boss" && ["chaser", "charger"].includes(enemy.behavior || "chaser");
  if (
    canClimb && enemy.navOnGround && enemy.navJumpCooldown <= 0 &&
    player.y < enemy.y - 28 && Math.abs(player.x - enemy.x) < 300
  ) {
    enemy.navVy = -500;
    enemy.navOnGround = false;
    enemy.navJumpCooldown = 0.9;
  }

  const previousY = enemy.y;
  if (!enemy.navOnGround) {
    enemy.navVy = Math.min(1000, enemy.navVy + 1600 * dt);
    enemy.y += enemy.navVy * dt;
  }
  if (enemy.navVy >= 0) {
    let landing: number | null = null;
    for (const platform of level.platforms) {
      const half = Math.min(26, enemyHalfWidth(enemy));
      const within = enemy.x + half > platform.x && enemy.x - half < platform.x + platform.width;
      if (within && previousY <= platform.y + 1 && enemy.y >= platform.y) {
        landing = landing === null ? platform.y : Math.min(landing, platform.y);
      }
    }
    if (landing !== null) {
      enemy.y = landing;
      enemy.navVy = 0;
      enemy.navOnGround = true;
    } else if (enemy.navOnGround) {
      const supported = level.platforms.some((platform) =>
        enemy.x >= platform.x && enemy.x <= platform.x + platform.width && Math.abs(enemy.y - platform.y) < 2,
      );
      if (!supported) enemy.navOnGround = false;
    }
  }
}

export function stepPve(
  runtime: PveRuntime,
  level: PveLevel,
  input: PveInput,
  dtRaw: number,
): PveRuntime {
  if (runtime.status !== "playing" || runtime.paused) return runtime;
  const dt = Math.min(0.05, Math.max(0, dtRaw));
  if (runtime.hitstopRemaining > 0) {
    runtime.hitstopRemaining = Math.max(0, runtime.hitstopRemaining - dt * 1000);
    return runtime;
  }
  runtime.elapsed += dt;
  runtime.shotCooldown = Math.max(0, runtime.shotCooldown - dt);
  if (!runtime.guardAvailable && runtime.elapsed >= runtime.guardCooldownUntil) {
    runtime.guardAvailable = true;
  }
  runtime.guarding = input.guard && runtime.guardAvailable;
  if (input.dodge && !runtime.dodgeHeld && runtime.elapsed >= runtime.dodgeCooldownUntil) {
    runtime.dodgeDirection = input.left !== input.right ? (input.right ? 1 : -1) : runtime.player.facing;
    runtime.dodgeUntil = runtime.elapsed + 0.22;
    runtime.dodgeCooldownUntil = runtime.elapsed + 1.6;
    runtime.invulnerableUntil = Math.max(runtime.invulnerableUntil, runtime.elapsed + 0.18);
  }
  runtime.dodgeHeld = Boolean(input.dodge);
  const physicsLevel = arcadeLevel(level);
  let player = stepPlayer(runtime.player, input, physicsLevel, dt);
  if (runtime.elapsed < runtime.dodgeUntil) {
    const x = Math.max(24, Math.min(level.width - 24, runtime.player.x + runtime.dodgeDirection * 560 * dt));
    player = stepPlayer({ ...runtime.player, x }, { ...input, left: false, right: false }, physicsLevel, dt);
    player.facing = runtime.dodgeDirection;
    player.vx = runtime.dodgeDirection * 560;
  }
  player = {
    ...player,
    x: updateEncounter(runtime, level, player.x),
  };
  if (isFallen(player)) {
    damagePlayer(runtime, 1);
    player = respawn(physicsLevel, level.spawnX);
  }
  runtime.player = player;
  if (runtime.status !== "playing") return runtime;
  if (pveVentStage(runtime.elapsed) === "active") {
    for (const hazard of level.hazards ?? []) {
      if (player.x + 22 > hazard.x && player.x - 22 < hazard.x + hazard.width &&
          player.y > hazard.y - 28 && player.y - CHAR_HEIGHT < hazard.y) {
        damagePlayer(runtime, 1);
      }
    }
  }
  if (runtime.status !== "playing") return runtime;

  if (input.shoot && runtime.shotCooldown <= 0) {
    runtime.shotCooldown = PVE_SHOT_COOLDOWN;
    runtime.projectiles.push({
      id: runtime.nextProjectileId++,
      owner: "player",
      x: player.x + player.facing * 30,
      y: player.y - 82,
      vx: player.facing * PVE_SHOT_SPEED / Math.hypot(1, Math.max(-1, Math.min(1, input.aimY ?? 0))),
      vy: Math.max(-1, Math.min(1, input.aimY ?? 0)) * PVE_SHOT_SPEED / Math.hypot(1, Math.max(-1, Math.min(1, input.aimY ?? 0))),
      radius: 7,
      damage: PVE_PLAYER_DAMAGE,
      ttl: 1.5,
      color: "#f1c66c",
    });
    runtime.shotsFired += 1;
    emitAudio(runtime, "shot");
  }

  const encounter = activePveEncounter(runtime, level);
  for (const enemy of runtime.enemies) {
    if (enemy.hp <= 0) continue;
    const isActive = Boolean(encounter?.enemy_ids.includes(enemy.id));
    if (!isActive) {
      enemy.awake = false;
      enemy.action = "idle";
      continue;
    }
    enemy.awake = true;
    if (enemy.kind === "boss" && enemy.phase === 1 && enemy.hp <= enemy.max_hp / 2) {
      enemy.phase = 2;
      runtime.encounterNotice = `${enemy.name} · 第二阶段`;
      runtime.encounterNoticeUntil = runtime.elapsed + 2;
    }
    const distanceX = Math.abs(enemy.x - player.x);
    const direction = player.x < enemy.x ? -1 : 1;
    enemy.shootCooldown = Math.max(0, enemy.shootCooldown - dt);
    if (enemy.ability && enemy.abilityStage !== "idle") {
      const ability = enemy.ability;
      const config = PVE_ABILITIES[ability];
      if (runtime.elapsed >= enemy.abilityUntil) {
        if (enemy.abilityStage === "windup") {
          enemy.abilityStage = "active";
          enemy.abilityUntil = runtime.elapsed + config.active;
          if (ability === "shot") spawnEnemyShot(runtime, enemy);
        } else if (enemy.abilityStage === "active") {
          enemy.abilityStage = "recovery";
          enemy.abilityUntil = runtime.elapsed + config.recovery;
        } else {
          enemy.abilityStage = "idle";
          enemy.ability = null;
          enemy.shootCooldown = Math.max(0.5, enemy.attack_interval * (enemy.phase === 2 ? 0.8 : 1));
        }
      }
      enemy.action = enemy.abilityStage === "active" ? "attack" : "idle";
      if (enemy.abilityStage === "active" && ability !== "shot") {
        const beforeX = enemy.x;
        if (ability === "charge" || ability === "lunge") {
          const speed = ability === "charge" ? 420 : 260;
          enemy.x = Math.max(80, Math.min(level.width - 80, enemy.x + enemy.abilityDirection * speed * dt));
        }
        const reach = ability === "slam" ? config.range : enemyHalfWidth(enemy) + 25;
        const overlapsX = player.x >= Math.min(beforeX, enemy.x) - reach && player.x <= Math.max(beforeX, enemy.x) + reach;
        const overlapsY = ability === "slam"
          ? player.y > enemy.y - 24 && player.y - CHAR_HEIGHT < enemy.y
          : player.y > enemy.y - enemyHeight(enemy) && player.y - CHAR_HEIGHT < enemy.y;
        if (!enemy.abilityHit && overlapsX && overlapsY) {
          damagePlayer(runtime, enemy.damage);
          enemy.abilityHit = true;
        }
      }
      continue;
    }

    enemy.facing = direction;
    // A guardian cannot hit a raised target with a ground-only slam. Switch to
    // a telegraphed shot instead of getting stuck attacking an unreachable plane.
    const ability = enemy.behavior === "guardian" && enemy.kind !== "boss" && player.y < enemy.y - 28
      ? "shot"
      : chooseAbility(enemy);
    const config = PVE_ABILITIES[ability];
    const range = enemy.kind === "boss" && ability === "shot" ? 680 : config.range;
    const shouldMove = distanceX > range * 0.8;
    enemy.action = shouldMove ? "walk" : "idle";
    stepEnemyNavigation(enemy, level, player, direction, shouldMove, dt);
    if (distanceX < range && enemy.shootCooldown <= 0) {
      enemy.ability = ability;
      enemy.abilityStage = "windup";
      enemy.abilityUntil = runtime.elapsed + config.windup;
      enemy.abilityTargetX = player.x;
      enemy.abilityTargetY = player.y - CHAR_HEIGHT * 0.5;
      enemy.abilityDirection = direction;
      enemy.abilityHit = false;
      enemy.attacks += 1;
    }
  }

  const projectiles: PveProjectile[] = [];
  for (const projectile of runtime.projectiles) {
    const moved = {
      ...projectile,
      x: projectile.x + projectile.vx * dt,
      y: projectile.y + projectile.vy * dt,
      ttl: projectile.ttl - dt,
    };
    const travelDt = Math.min(dt, Math.max(0, projectile.ttl));
    if (travelDt <= 0) continue;
    const coverHit = (level.covers ?? []).some((cover) =>
      impactTime(projectile, travelDt, cover.x, cover.y - cover.height, cover.x + cover.width, cover.y) !== null,
    );
    if (coverHit) {
      burst(runtime, moved.x, moved.y, "#d8d2c3", 5, 45);
      continue;
    }
    if (moved.owner === "player") {
      let target: PveRuntimeEnemy | undefined;
      let nearest = Infinity;
      for (const enemy of runtime.enemies) {
        if (enemy.hp <= 0 || !encounter?.enemy_ids.includes(enemy.id)) continue;
        const halfWidth = enemyHalfWidth(enemy);
        const hit = impactTime(projectile, travelDt, enemy.x - halfWidth, enemy.y - enemyHeight(enemy), enemy.x + halfWidth, enemy.y + 4);
        if (hit !== null && hit < nearest) {
          nearest = hit;
          target = enemy;
        }
      }
      if (target) {
        target.hp = Math.max(0, target.hp - moved.damage);
        if (target.hp === 0) target.deathAt = runtime.elapsed;
        target.hitFlashUntil = runtime.elapsed + 0.16;
        runtime.shotsHit += 1;
        target.x = Math.max(80, Math.min(level.width - 80, target.x + Math.sign(projectile.vx) * 20));
        runtime.hitstopRemaining = Math.max(runtime.hitstopRemaining, 48);
        emitAudio(runtime, "hit");
        burst(runtime, moved.x, moved.y, moved.color, target.kind === "boss" ? 14 : 9);
        continue;
      }
    } else if (impactTime(projectile, travelDt, player.x - 25, player.y - CHAR_HEIGHT * 0.88, player.x + 25, player.y - CHAR_HEIGHT * 0.12) !== null) {
      damagePlayer(runtime, moved.damage);
      continue;
    }
    if (moved.ttl > 0) projectiles.push(moved);
  }
  runtime.projectiles = projectiles;

  for (const particle of runtime.particles) {
    particle.x += particle.vx * dt;
    particle.y += particle.vy * dt;
    particle.vy += 180 * dt;
    particle.life -= dt;
  }
  runtime.particles = runtime.particles.filter((particle) => particle.life > 0);
  return runtime;
}

export function togglePvePause(runtime: PveRuntime) {
  if (runtime.status === "playing") runtime.paused = !runtime.paused;
}

export function consumePveAudioEvents(runtime: PveRuntime): PveAudioEvent[] {
  const events = runtime.audioEvents;
  runtime.audioEvents = [];
  return events;
}

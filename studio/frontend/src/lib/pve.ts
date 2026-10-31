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

export type PveEnemyAction = "idle" | "walk" | "attack";
export type PveStatus = "playing" | "won" | "lost";
export type PveAudioEvent = "shot" | "hit" | "hurt" | "guard" | "clear" | "win" | "lose";

export interface PveRuntimeEnemy extends PveEnemy {
  hp: number;
  awake: boolean;
  facing: 1 | -1;
  action: PveEnemyAction;
  actionUntil: number;
  shootCooldown: number;
  contactCooldown: number;
  hitFlashUntil: number;
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
}

export interface PveInput extends ArcadeInput {
  shoot: boolean;
  guard: boolean;
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
}

function arcadeLevel(level: PveLevel): ArcadeLevel {
  return {
    ...level,
    platforms: level.platforms.filter((platform) => platform.kind === "ground"),
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
      actionUntil: 0,
      shootCooldown: 0.7,
      contactCooldown: 0,
      hitFlashUntil: 0,
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
  };
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
    runtime.invulnerableUntil = runtime.elapsed + 0.3;
    emitAudio(runtime, "guard");
    burst(runtime, runtime.player.x, runtime.player.y - 82, "#9edff2", 8, 70);
    return;
  }
  runtime.playerHp = Math.max(0, runtime.playerHp - damage);
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
  const targetX = runtime.player.x;
  const targetY = runtime.player.y - CHAR_HEIGHT * 0.5;
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
  enemy.action = "attack";
  enemy.actionUntil = runtime.elapsed + 0.32;
}

function playerHit(runtime: PveRuntime, projectile: PveProjectile): boolean {
  const playerCenterY = runtime.player.y - CHAR_HEIGHT * 0.5;
  return (
    Math.abs(projectile.x - runtime.player.x) < projectile.radius + 25 &&
    Math.abs(projectile.y - playerCenterY) < projectile.radius + CHAR_HEIGHT * 0.38
  );
}

function projectileHitsEnemy(projectile: PveProjectile, enemy: PveRuntimeEnemy): boolean {
  if (enemy.hp <= 0) return false;
  const halfWidth = enemyHalfWidth(enemy);
  const height = enemyHeight(enemy);
  return (
    Math.abs(projectile.x - enemy.x) < halfWidth + projectile.radius &&
    projectile.y >= enemy.y - height &&
    projectile.y <= enemy.y + 4
  );
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
  const physicsLevel = arcadeLevel(level);
  let player = stepPlayer(runtime.player, input, physicsLevel, dt);
  player = {
    ...player,
    x: updateEncounter(runtime, level, player.x),
  };
  if (isFallen(player)) {
    damagePlayer(runtime, 1);
    player = respawn(physicsLevel, level.spawnX);
  }
  runtime.player = player;

  if (input.shoot && runtime.shotCooldown <= 0) {
    runtime.shotCooldown = PVE_SHOT_COOLDOWN;
    runtime.projectiles.push({
      id: runtime.nextProjectileId++,
      owner: "player",
      x: player.x + player.facing * 30,
      y: player.y - 82,
      vx: player.facing * PVE_SHOT_SPEED,
      vy: 0,
      radius: 7,
      damage: PVE_PLAYER_DAMAGE,
      ttl: 1.5,
      color: "#f1c66c",
    });
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
    const distanceX = Math.abs(enemy.x - player.x);
    const direction = player.x < enemy.x ? -1 : 1;
    enemy.facing = direction;
    enemy.shootCooldown = Math.max(0, enemy.shootCooldown - dt);
    enemy.contactCooldown = Math.max(0, enemy.contactCooldown - dt);
    if (runtime.elapsed < enemy.actionUntil) {
      enemy.action = "attack";
      continue;
    }

    const behavior = enemy.behavior || "chaser";
    const preferredRange =
      behavior === "shooter" || behavior === "guardian"
        ? enemy.kind === "boss"
          ? 270
          : 230
        : behavior === "charger"
          ? 40
          : 110;
    const shouldMove = distanceX > preferredRange;
    enemy.action = shouldMove ? "walk" : "idle";
    if (shouldMove) {
      const charge = behavior === "charger" && distanceX < 420 ? 1.55 : 1;
      enemy.x += direction * enemy.speed * charge * dt;
      enemy.x = Math.max(80, Math.min(level.width - 80, enemy.x));
    }

    const attackRange = enemy.kind === "boss" ? 680 : behavior === "shooter" ? 560 : 430;
    if (distanceX < attackRange && enemy.shootCooldown <= 0) {
      spawnEnemyShot(runtime, enemy);
      enemy.shootCooldown = enemy.attack_interval;
    }

    const contactRange = enemy.kind === "boss" ? 104 : behavior === "charger" ? 64 : 48;
    if (distanceX < contactRange && enemy.contactCooldown <= 0) {
      damagePlayer(runtime, enemy.damage);
      enemy.contactCooldown = 1.1;
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
    if (moved.ttl <= 0) continue;
    if (moved.owner === "player") {
      const target = runtime.enemies.find((enemy) => projectileHitsEnemy(moved, enemy));
      if (target) {
        target.hp = Math.max(0, target.hp - moved.damage);
        target.hitFlashUntil = runtime.elapsed + 0.16;
        target.x += target.facing * 20;
        runtime.hitstopRemaining = Math.max(runtime.hitstopRemaining, 48);
        emitAudio(runtime, "hit");
        burst(runtime, moved.x, moved.y, moved.color, target.kind === "boss" ? 14 : 9);
        continue;
      }
    } else if (playerHit(runtime, moved)) {
      damagePlayer(runtime, moved.damage);
      continue;
    }
    projectiles.push(moved);
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

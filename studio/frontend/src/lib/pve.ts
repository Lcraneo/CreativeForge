/** 2.5D PVE 战役规则：x 水平、y 纵深、z 跳跃高度，固定竞技场，与渲染解耦。 */

import type { PveCampaign, PveEnemySpawn, PveStage } from "../types";

export const PVE_PLAYER_HP = 6;
export const PVE_PLAYER_DAMAGE = 1;
export const PVE_SHOT_COOLDOWN = 0.22;
export const PVE_SHOT_SPEED = 900;
export const PVE_GUARD_COOLDOWN = 2;

/** 地面纵深压缩：y 方向 1 单位只相当于 x 方向 1/1.6 的距离。 */
export const PVE_DEPTH_SCALE = 1.6;
/** 角色可活动范围到竞技场边缘的最小留白（逻辑单位）。 */
export const PVE_EDGE_MARGIN = 20;
export const PVE_PLAYER_RADIUS = 20;
export const PVE_PLAYER_DEPTH_RADIUS = 14;
export const PVE_PLAYER_HEIGHT = 84;
export const PVE_MOVE_SPEED = 230;
export const PVE_RUN_MULTIPLIER = 1.5;
export const PVE_JUMP_SPEED = 520;
export const PVE_GRAVITY = 1500;
export const PVE_DODGE_SPEED = 560;
export const PVE_SLAM_MAX_Z = 48;
export const PVE_HURT_DURATION = 0.18;
export const PVE_DEATH_DURATION = 0.6;
export const PVE_STAGE_COUNT = 3;

export type PveStagePhase = "playing" | "cleared" | "campaign_won" | "campaign_lost";
/** 用户规格中的阶段类型别名。 */
export type StagePhase = PveStagePhase;

export type PveEnemyAction = "idle" | "walk" | "attack";
export type PvePose = PveEnemyAction | "windup" | "hurt" | "death";
export const PVE_ACTION_SLOTS: PvePose[] = ["idle", "walk", "windup", "attack", "hurt", "death"];

export const PVE_ACTION_FALLBACK: Record<PvePose, PveEnemyAction> = {
  idle: "idle",
  walk: "walk",
  windup: "idle",
  attack: "attack",
  hurt: "idle",
  death: "idle",
};

export type PveAudioEvent = "shot" | "hit" | "hurt" | "guard" | "clear" | "win" | "lose";
export type PveAbility = "shot" | "lunge" | "charge" | "slam";
export type PveAbilityStage = "idle" | "windup" | "active" | "recovery";

/** 地面距离，纵深按 1.6 压缩，与攻击距离和碰撞判定共用。 */
export function pveGroundDistance(ax: number, ay: number, bx: number, by: number): number {
  const dy = (by - ay) * PVE_DEPTH_SCALE;
  return Math.hypot(bx - ax, dy);
}

/** 压缩地面上的单位方向向量；用于追踪、冲锋、冲刺和击退。 */
export function pveGroundDirection(
  ax: number,
  ay: number,
  bx: number,
  by: number,
): { x: number; y: number } {
  const dx = bx - ax;
  const dy = (by - ay) * PVE_DEPTH_SCALE;
  const length = Math.hypot(dx, dy);
  if (length < 1e-6) return { x: 0, y: 0 };
  return { x: dx / length, y: dy / length };
}

/** 绘制顺序：y 从小到大（远到近），保证后面的角色遮挡前面的角色。 */
export function pveSortByDepth<T extends { y: number }>(items: T[]): T[] {
  return [...items].sort((left, right) => left.y - right.y);
}

export const PVE_ABILITIES: Record<
  PveAbility,
  { windup: number; active: number; recovery: number; range: number }
> = {
  shot: { windup: 0.6, active: 0.1, recovery: 0.35, range: 520 },
  lunge: { windup: 0.45, active: 0.25, recovery: 0.5, range: 130 },
  charge: { windup: 0.65, active: 0.55, recovery: 0.8, range: 360 },
  slam: { windup: 0.8, active: 0.2, recovery: 0.65, range: 150 },
};

export interface PvePlayer {
  x: number;
  y: number;
  z: number;
  vx: number;
  vy: number;
  vz: number;
  onGround: boolean;
  facing: 1 | -1;
}

export interface PveRuntimeEnemy extends PveEnemySpawn {
  hp: number;
  awake: boolean;
  facing: 1 | -1;
  action: PveEnemyAction;
  shootCooldown: number;
  hitFlashUntil: number;
  ability: PveAbility | null;
  abilityStage: PveAbilityStage;
  abilityUntil: number;
  abilityStartedAt: number;
  abilityStageStartedAt: number;
  abilityTargetX: number;
  abilityTargetY: number;
  abilityTargetZ: number;
  abilityDirectionX: number;
  abilityDirectionY: number;
  abilityHit: boolean;
  phase: 1 | 2;
  attacks: number;
  deathAt: number | null;
  radiusX: number;
  depthRadius: number;
  heightZ: number;
}

export interface PveProjectile {
  id: number;
  owner: "player" | "enemy";
  x: number;
  y: number;
  z: number;
  vx: number;
  vy: number;
  vz: number;
  radius: number;
  damage: number;
  ttl: number;
  color: string;
}

export interface PveParticle {
  x: number;
  y: number;
  z: number;
  vx: number;
  vy: number;
  vz: number;
  life: number;
  color: string;
  size: number;
}

export interface PveStats {
  playerHp: number;
  damageTaken: number;
  guardsUsed: number;
  shotsFired: number;
  shotsHit: number;
  totalTime: number;
}

export interface PveRuntime {
  campaign: PveCampaign;
  stageIndex: number;
  phase: PveStagePhase;
  player: PvePlayer;
  enemies: PveRuntimeEnemy[];
  projectiles: PveProjectile[];
  particles: PveParticle[];
  playerHp: number;
  stageTime: number;
  totalTime: number;
  stageEntry: PveStats;
  invulnerableUntil: number;
  shotCooldown: number;
  nextProjectileId: number;
  guardAvailable: boolean;
  guardCooldownUntil: number;
  guarding: boolean;
  paused: boolean;
  hitstopRemaining: number;
  audioEvents: PveAudioEvent[];
  dodgeUntil: number;
  dodgeCooldownUntil: number;
  dodgeHeld: boolean;
  dodgeDirectionX: number;
  dodgeDirectionY: number;
  notice: string;
  noticeUntil: number;
  damageTaken: number;
  guardsUsed: number;
  shotsFired: number;
  shotsHit: number;
}

export interface PveInput {
  left: boolean;
  right: boolean;
  up: boolean;
  down: boolean;
  run: boolean;
  jump: boolean;
  shoot: boolean;
  guard: boolean;
  dodge: boolean;
  /** -1 向上、1 向下，0 为平射。 */
  aimZ?: number;
}

export interface PveHud {
  hp: number;
  hpMax: number;
  stageIndex: number;
  stageCount: number;
  stageTitle: string;
  stageKind: "minion" | "boss";
  phase: PveStagePhase;
  elapsed: number;
  stageElapsed: number;
  stageRemaining: number;
  stageTotal: number;
  kills: number;
  bossHp: number;
  bossMaxHp: number;
  bossActive: boolean;
  guardAvailable: boolean;
  guardCooldown: number;
  paused: boolean;
  dodgeCooldown: number;
  damageTaken: number;
  guardsUsed: number;
  shotsFired: number;
  shotsHit: number;
  accuracy: number;
  grade: "S" | "A" | "B" | "C";
  notice: string;
}

function clamp01(value: number): number {
  return Math.max(0, Math.min(1, value));
}

function clamp(value: number, min: number, max: number): number {
  return Math.max(min, Math.min(max, value));
}

export function pveStage(campaign: PveCampaign, index: number): PveStage {
  return campaign.stages[clamp(index, 0, campaign.stages.length - 1)];
}

function enemyMetrics(enemy: PveEnemySpawn): { radiusX: number; depthRadius: number; heightZ: number } {
  const scale = Math.max(40, enemy.display_height || 92);
  if (enemy.kind === "boss") {
    return {
      radiusX: Math.round(scale * 0.28),
      depthRadius: Math.round(scale * 0.2),
      heightZ: Math.round(scale * 0.62),
    };
  }
  return {
    radiusX: Math.round(scale * 0.26),
    depthRadius: Math.round(scale * 0.16),
    heightZ: Math.round(scale * 0.7),
  };
}

function runtimeEnemy(enemy: PveEnemySpawn): PveRuntimeEnemy {
  const metrics = enemyMetrics(enemy);
  return {
    ...enemy,
    hp: enemy.max_hp,
    awake: true,
    facing: -1,
    action: "idle",
    shootCooldown: 0.7,
    hitFlashUntil: 0,
    ability: null,
    abilityStage: "idle",
    abilityUntil: 0,
    abilityStartedAt: 0,
    abilityStageStartedAt: 0,
    abilityTargetX: 0,
    abilityTargetY: 0,
    abilityTargetZ: 0,
    abilityDirectionX: 0,
    abilityDirectionY: 0,
    abilityHit: false,
    phase: 1,
    attacks: 0,
    deathAt: null,
    ...metrics,
  };
}

function spawnPlayer(stage: PveStage): PvePlayer {
  return {
    x: stage.arena.spawn_x,
    y: stage.arena.spawn_y,
    z: 0,
    vx: 0,
    vy: 0,
    vz: 0,
    onGround: true,
    facing: 1,
  };
}

function statsOf(runtime: PveRuntime): PveStats {
  return {
    playerHp: runtime.playerHp,
    damageTaken: runtime.damageTaken,
    guardsUsed: runtime.guardsUsed,
    shotsFired: runtime.shotsFired,
    shotsHit: runtime.shotsHit,
    totalTime: runtime.totalTime,
  };
}

function resetStage(runtime: PveRuntime, index: number, entry: PveStats): void {
  const stage = pveStage(runtime.campaign, index);
  runtime.stageIndex = index;
  runtime.phase = "playing";
  runtime.player = spawnPlayer(stage);
  runtime.enemies = stage.enemies.map(runtimeEnemy);
  runtime.projectiles = [];
  runtime.particles = [];
  runtime.stageTime = 0;
  runtime.invulnerableUntil = 0;
  runtime.shotCooldown = 0;
  runtime.guardAvailable = true;
  runtime.guardCooldownUntil = 0;
  runtime.guarding = false;
  runtime.paused = false;
  runtime.hitstopRemaining = 0;
  runtime.dodgeUntil = 0;
  runtime.dodgeCooldownUntil = 0;
  runtime.dodgeHeld = false;
  runtime.dodgeDirectionX = 1;
  runtime.dodgeDirectionY = 0;
  runtime.stageEntry = entry;
  runtime.playerHp = entry.playerHp;
  runtime.damageTaken = entry.damageTaken;
  runtime.guardsUsed = entry.guardsUsed;
  runtime.shotsFired = entry.shotsFired;
  runtime.shotsHit = entry.shotsHit;
  runtime.totalTime = entry.totalTime;
  runtime.notice = stage.title;
  runtime.noticeUntil = 1.6;
}

export function createPveRuntime(
  campaign: PveCampaign,
  playerHp = PVE_PLAYER_HP,
): PveRuntime {
  const runtime: PveRuntime = {
    campaign,
    stageIndex: 0,
    phase: "playing",
    player: spawnPlayer(pveStage(campaign, 0)),
    enemies: [],
    projectiles: [],
    particles: [],
    playerHp,
    stageTime: 0,
    totalTime: 0,
    stageEntry: {
      playerHp,
      damageTaken: 0,
      guardsUsed: 0,
      shotsFired: 0,
      shotsHit: 0,
      totalTime: 0,
    },
    invulnerableUntil: 0,
    shotCooldown: 0,
    nextProjectileId: 1,
    guardAvailable: true,
    guardCooldownUntil: 0,
    guarding: false,
    paused: false,
    hitstopRemaining: 0,
    audioEvents: [],
    dodgeUntil: 0,
    dodgeCooldownUntil: 0,
    dodgeHeld: false,
    dodgeDirectionX: 1,
    dodgeDirectionY: 0,
    notice: "",
    noticeUntil: 0,
    damageTaken: 0,
    guardsUsed: 0,
    shotsFired: 0,
    shotsHit: 0,
  };
  resetStage(runtime, 0, runtime.stageEntry);
  return runtime;
}

/** 仅在「已清场」时加载下一关；不会因为清场自动调用。 */
export function advancePveStage(runtime: PveRuntime): boolean {
  if (runtime.phase !== "cleared" || runtime.stageIndex >= runtime.campaign.stages.length - 1) {
    return false;
  }
  const entry: PveStats = {
    ...statsOf(runtime),
    totalTime: runtime.totalTime,
  };
  resetStage(runtime, runtime.stageIndex + 1, entry);
  return true;
}

/** 失败后重试当前关：生命与累计统计回到进入本关时的快照。 */
export function retryPveStage(runtime: PveRuntime): boolean {
  if (runtime.phase !== "campaign_lost") return false;
  resetStage(runtime, runtime.stageIndex, runtime.stageEntry);
  return true;
}

export function pveGrade(
  runtime: Pick<PveRuntime, "phase" | "totalTime" | "damageTaken" | "shotsFired" | "shotsHit">,
): "S" | "A" | "B" | "C" {
  if (runtime.phase !== "campaign_won") return "C";
  const accuracy = runtime.shotsFired ? runtime.shotsHit / runtime.shotsFired : 0;
  if (runtime.damageTaken === 0 && accuracy >= 0.5 && runtime.totalTime <= 210) return "S";
  if (runtime.damageTaken <= 2 && runtime.totalTime <= 280) return "A";
  return runtime.damageTaken <= 7 ? "B" : "C";
}

export function pveHud(runtime: PveRuntime): PveHud {
  const stage = pveStage(runtime.campaign, runtime.stageIndex);
  const boss = runtime.enemies.find((enemy) => enemy.kind === "boss" && enemy.hp > 0);
  const remaining = runtime.enemies.filter((enemy) => enemy.hp > 0).length;
  return {
    hp: runtime.playerHp,
    hpMax: PVE_PLAYER_HP,
    stageIndex: runtime.stageIndex + 1,
    stageCount: PVE_STAGE_COUNT,
    stageTitle: stage.title,
    stageKind: stage.kind,
    phase: runtime.phase,
    elapsed: runtime.totalTime,
    stageElapsed: runtime.stageTime,
    stageRemaining: remaining,
    stageTotal: runtime.enemies.length,
    kills: runtime.enemies.filter((enemy) => enemy.hp <= 0).length,
    bossHp: boss?.hp ?? 0,
    bossMaxHp: boss?.max_hp ?? 0,
    bossActive: Boolean(stage.kind === "boss" && boss),
    guardAvailable: runtime.guardAvailable || runtime.stageTime >= runtime.guardCooldownUntil,
    guardCooldown: Math.max(0, runtime.guardCooldownUntil - runtime.stageTime),
    paused: runtime.paused,
    dodgeCooldown: Math.max(0, runtime.dodgeCooldownUntil - runtime.stageTime),
    damageTaken: runtime.damageTaken,
    guardsUsed: runtime.guardsUsed,
    shotsFired: runtime.shotsFired,
    shotsHit: runtime.shotsHit,
    accuracy: runtime.shotsFired ? runtime.shotsHit / runtime.shotsFired : 0,
    grade: pveGrade(runtime),
    notice: runtime.stageTime < runtime.noticeUntil ? runtime.notice : "",
  };
}

export function pveEnemyPose(enemy: PveRuntimeEnemy, now: number): PvePose {
  if (enemy.hp <= 0) return "death";
  if (enemy.hitFlashUntil > now) return "hurt";
  if (enemy.abilityStage === "windup") return "windup";
  return enemy.action;
}

/** 一次性动作（蓄力/攻击/受击/死亡）的播放进度；循环动作返回 null。 */
export function pvePoseProgress(
  pose: PvePose,
  enemy: PveRuntimeEnemy,
  now: number,
): number | null {
  switch (pose) {
    case "windup": {
      const config = enemy.ability ? PVE_ABILITIES[enemy.ability] : null;
      return clamp01((now - enemy.abilityStartedAt) / Math.max(0.01, config?.windup ?? 0.01));
    }
    case "attack": {
      const config = enemy.ability ? PVE_ABILITIES[enemy.ability] : null;
      return clamp01((now - enemy.abilityStageStartedAt) / Math.max(0.01, config?.active ?? 0.01));
    }
    case "hurt":
      return clamp01(1 - (enemy.hitFlashUntil - now) / PVE_HURT_DURATION);
    case "death":
      return clamp01((now - (enemy.deathAt ?? now)) / PVE_DEATH_DURATION);
    default:
      return null;
  }
}

/**
 * 给 drawSprite 的动画时间。循环动作使用运行时钟；
 * 一次性动作按真实进度取帧，因此 windup / death 不会再永远停在第 0 帧。
 */
export function pveSpriteTime(
  pose: PvePose,
  enemy: PveRuntimeEnemy,
  now: number,
  frames: number,
  fps: number,
): number {
  const progress = pvePoseProgress(pose, enemy, now);
  if (progress === null) return now;
  const count = Math.max(1, Math.round(frames));
  const frame = Math.min(count - 1, Math.floor(clamp01(progress) * count));
  return frame / Math.max(1, fps);
}

function emitAudio(runtime: PveRuntime, event: PveAudioEvent): void {
  runtime.audioEvents.push(event);
}

function burst(
  runtime: PveRuntime,
  x: number,
  y: number,
  z: number,
  color: string,
  count: number,
  strength = 90,
): void {
  for (let index = 0; index < count; index += 1) {
    const angle = (index / Math.max(1, count)) * Math.PI * 2;
    runtime.particles.push({
      x,
      y,
      z,
      vx: Math.cos(angle) * strength,
      vy: Math.sin(angle) * strength,
      vz: 30 + (index % 3) * 30,
      life: 0.24 + (index % 3) * 0.05,
      color,
      size: 2 + (index % 2),
    });
  }
}

function damagePlayer(runtime: PveRuntime, damage: number): void {
  if (runtime.phase !== "playing" || runtime.invulnerableUntil > runtime.stageTime) return;
  if (runtime.guarding && runtime.guardAvailable) {
    runtime.guardAvailable = false;
    runtime.guarding = false;
    runtime.guardCooldownUntil = runtime.stageTime + PVE_GUARD_COOLDOWN;
    runtime.guardsUsed += 1;
    runtime.invulnerableUntil = runtime.stageTime + 0.3;
    emitAudio(runtime, "guard");
    burst(runtime, runtime.player.x, runtime.player.y, runtime.player.z + 50, "#9edff2", 8, 70);
    return;
  }
  runtime.playerHp = Math.max(0, runtime.playerHp - damage);
  runtime.damageTaken += damage;
  runtime.invulnerableUntil = runtime.stageTime + 0.85;
  runtime.hitstopRemaining = Math.max(runtime.hitstopRemaining, 42);
  emitAudio(runtime, "hurt");
  burst(runtime, runtime.player.x, runtime.player.y, runtime.player.z + 50, "#ff9b86", 10, 110);
  if (runtime.playerHp <= 0) {
    runtime.phase = "campaign_lost";
    runtime.projectiles = [];
    emitAudio(runtime, "lose");
  }
}

function playerAabb(runtime: PveRuntime) {
  const player = runtime.player;
  return {
    minX: player.x - PVE_PLAYER_RADIUS,
    maxX: player.x + PVE_PLAYER_RADIUS,
    minY: player.y - PVE_PLAYER_DEPTH_RADIUS,
    maxY: player.y + PVE_PLAYER_DEPTH_RADIUS,
    minZ: player.z,
    maxZ: player.z + PVE_PLAYER_HEIGHT,
  };
}

function enemyAabb(enemy: PveRuntimeEnemy) {
  return {
    minX: enemy.x - enemy.radiusX,
    maxX: enemy.x + enemy.radiusX,
    minY: enemy.y - enemy.depthRadius,
    maxY: enemy.y + enemy.depthRadius,
    minZ: 0,
    maxZ: enemy.heightZ,
  };
}

/**
 * 三维线段与 AABB 的扫掠检测：快速弹丸不会穿过敌人或玩家。
 * 返回首次接触的时间比例（0..1），未命中返回 null。
 */
export function pveSegmentHitsBox(
  origin: { x: number; y: number; z: number },
  delta: { x: number; y: number; z: number },
  box: {
    minX: number;
    maxX: number;
    minY: number;
    maxY: number;
    minZ: number;
    maxZ: number;
  },
): number | null {
  let enter = 0;
  let exit = 1;
  const axes: Array<[number, number, number, number]> = [
    [origin.x, delta.x, box.minX, box.maxX],
    [origin.y, delta.y, box.minY, box.maxY],
    [origin.z, delta.z, box.minZ, box.maxZ],
  ];
  for (const [position, motion, min, max] of axes) {
    if (Math.abs(motion) < 1e-9) {
      if (position < min || position > max) return null;
      continue;
    }
    const a = (min - position) / motion;
    const b = (max - position) / motion;
    enter = Math.max(enter, Math.min(a, b));
    exit = Math.min(exit, Math.max(a, b));
    if (enter > exit) return null;
  }
  return enter <= 0 ? 0 : enter;
}

function spawnEnemyShot(runtime: PveRuntime, enemy: PveRuntimeEnemy): void {
  const origin = {
    x: enemy.x + enemy.facing * enemy.radiusX * 0.4,
    y: enemy.y,
    z: enemy.kind === "boss" ? enemy.heightZ * 0.65 : enemy.heightZ * 0.55,
  };
  const dx = enemy.abilityTargetX - origin.x;
  const dy = enemy.abilityTargetY - origin.y;
  const dz = enemy.abilityTargetZ - origin.z;
  const distance = Math.max(1, Math.hypot(dx, dy, dz));
  const speed = enemy.kind === "boss" ? 300 : enemy.behavior === "shooter" ? 280 : 250;
  runtime.projectiles.push({
    id: runtime.nextProjectileId++,
    owner: "enemy",
    x: origin.x,
    y: origin.y,
    z: origin.z,
    vx: (dx / distance) * speed,
    vy: (dy / distance) * speed,
    vz: (dz / distance) * speed,
    radius: enemy.kind === "boss" ? 12 : 7,
    damage: enemy.damage,
    ttl: 4,
    color: enemy.projectile_color || (enemy.kind === "boss" ? "#8feaff" : "#a9df72"),
  });
}

function chooseAbility(enemy: PveRuntimeEnemy): PveAbility {
  if (enemy.kind === "boss") {
    return enemy.phase === 2 ? (["shot", "slam", "charge"] as const)[enemy.attacks % 3] : "shot";
  }
  if (enemy.behavior === "charger") return "charge";
  if (enemy.behavior === "guardian") return "slam";
  if (enemy.behavior === "shooter") return "shot";
  return "lunge";
}

function beginAbility(runtime: PveRuntime, enemy: PveRuntimeEnemy, ability: PveAbility): void {
  const config = PVE_ABILITIES[ability];
  const direction = pveGroundDirection(enemy.x, enemy.y, runtime.player.x, runtime.player.y);
  enemy.facing = direction.x < 0 ? -1 : 1;
  enemy.ability = ability;
  enemy.abilityStage = "windup";
  enemy.abilityStartedAt = runtime.stageTime;
  enemy.abilityStageStartedAt = runtime.stageTime;
  enemy.abilityUntil = runtime.stageTime + config.windup;
  enemy.abilityTargetX = runtime.player.x;
  enemy.abilityTargetY = runtime.player.y;
  enemy.abilityTargetZ = runtime.player.z + PVE_PLAYER_HEIGHT * 0.5;
  enemy.abilityDirectionX = direction.x;
  enemy.abilityDirectionY = direction.y;
  enemy.abilityHit = false;
  enemy.attacks += 1;
}

function activeAbilityHitsPlayer(runtime: PveRuntime, enemy: PveRuntimeEnemy): boolean {
  if (enemy.ability === "slam") {
    const distance = pveGroundDistance(
      enemy.x,
      enemy.y,
      runtime.player.x,
      runtime.player.y,
    );
    // 跳跃（z 高于 48）可以躲过低矮的地面震击。
    return distance <= PVE_ABILITIES.slam.range && runtime.player.z <= PVE_SLAM_MAX_Z;
  }
  const distance = pveGroundDistance(
    enemy.x,
    enemy.y,
    runtime.player.x,
    runtime.player.y,
  );
  const overlapZ =
    runtime.player.z < enemy.heightZ &&
    runtime.player.z + PVE_PLAYER_HEIGHT > 0;
  return distance <= enemy.radiusX + PVE_PLAYER_RADIUS + 24 && overlapZ;
}

function stepAbility(runtime: PveRuntime, enemy: PveRuntimeEnemy, dt: number): void {
  if (!enemy.ability || enemy.abilityStage === "idle") return;
  const ability = enemy.ability;
  const config = PVE_ABILITIES[ability];
  if (runtime.stageTime >= enemy.abilityUntil) {
    if (enemy.abilityStage === "windup") {
      enemy.abilityStage = "active";
      enemy.abilityStageStartedAt = runtime.stageTime;
      enemy.abilityUntil = runtime.stageTime + config.active;
      if (ability === "shot") spawnEnemyShot(runtime, enemy);
    } else if (enemy.abilityStage === "active") {
      enemy.abilityStage = "recovery";
      enemy.abilityStageStartedAt = runtime.stageTime;
      enemy.abilityUntil = runtime.stageTime + config.recovery;
    } else {
      enemy.abilityStage = "idle";
      enemy.ability = null;
      enemy.shootCooldown = Math.max(
        0.5,
        enemy.attack_interval * (enemy.phase === 2 ? 0.8 : 1),
      );
      return;
    }
  }
  enemy.action = enemy.abilityStage === "active" ? "attack" : "idle";
  if (enemy.abilityStage !== "active") return;
  if (ability === "charge" || ability === "lunge") {
    const speed = ability === "charge" ? 420 : 260;
    enemy.x += enemy.abilityDirectionX * speed * dt;
    enemy.y += (enemy.abilityDirectionY * speed * dt) / PVE_DEPTH_SCALE;
    const stage = pveStage(runtime.campaign, runtime.stageIndex);
    enemy.x = clamp(enemy.x, PVE_EDGE_MARGIN, stage.arena.width - PVE_EDGE_MARGIN);
    enemy.y = clamp(enemy.y, PVE_EDGE_MARGIN, stage.arena.depth - PVE_EDGE_MARGIN);
  }
  if (!enemy.abilityHit && activeAbilityHitsPlayer(runtime, enemy)) {
    enemy.abilityHit = true;
    damagePlayer(runtime, enemy.damage);
  }
}

function stepEnemy(runtime: PveRuntime, enemy: PveRuntimeEnemy, dt: number): void {
  const stage = pveStage(runtime.campaign, runtime.stageIndex);
  if (enemy.kind === "boss" && enemy.phase === 1 && enemy.hp <= enemy.max_hp / 2) {
    enemy.phase = 2;
    runtime.notice = `${enemy.name} · 第二阶段`;
    runtime.noticeUntil = runtime.stageTime + 2;
  }
  enemy.shootCooldown = Math.max(0, enemy.shootCooldown - dt);
  if (enemy.ability && enemy.abilityStage !== "idle") {
    stepAbility(runtime, enemy, dt);
    return;
  }

  const distance = pveGroundDistance(
    enemy.x,
    enemy.y,
    runtime.player.x,
    runtime.player.y,
  );
  const direction = pveGroundDirection(
    enemy.x,
    enemy.y,
    runtime.player.x,
    runtime.player.y,
  );
  enemy.facing = direction.x < 0 ? -1 : 1;
  const ability = chooseAbility(enemy);
  const config = PVE_ABILITIES[ability];
  const range = enemy.kind === "boss" && ability === "shot" ? 640 : config.range;
  const shouldMove = distance > range * 0.8;
  enemy.action = shouldMove ? "walk" : "idle";
  if (shouldMove) {
    enemy.x += direction.x * enemy.speed * dt;
    enemy.y += (direction.y * enemy.speed * dt) / PVE_DEPTH_SCALE;
    enemy.x = clamp(enemy.x, PVE_EDGE_MARGIN, stage.arena.width - PVE_EDGE_MARGIN);
    enemy.y = clamp(enemy.y, PVE_EDGE_MARGIN, stage.arena.depth - PVE_EDGE_MARGIN);
  }
  if (distance <= range && enemy.shootCooldown <= 0) {
    beginAbility(runtime, enemy, ability);
  }
}

function finishStageIfCleared(runtime: PveRuntime): void {
  if (runtime.phase !== "playing") return;
  if (runtime.enemies.some((enemy) => enemy.hp > 0)) return;
  const stage = pveStage(runtime.campaign, runtime.stageIndex);
  runtime.projectiles = [];
  if (stage.kind === "boss" || runtime.stageIndex >= runtime.campaign.stages.length - 1) {
    runtime.phase = "campaign_won";
    emitAudio(runtime, "win");
  } else {
    runtime.phase = "cleared";
    emitAudio(runtime, "clear");
  }
  runtime.notice = `${stage.title} · 已完成`;
  runtime.noticeUntil = runtime.stageTime + 3;
}

export function stepPve(runtime: PveRuntime, input: PveInput, dtRaw: number): PveRuntime {
  const dt = Math.min(0.05, Math.max(0, dtRaw));
  if (runtime.paused) return runtime;
  if (runtime.phase !== "playing") {
    // 战斗冻结，只让死亡/粒子等表演继续前进。
    runtime.stageTime += dt;
    stepParticles(runtime, dt);
    return runtime;
  }
  if (runtime.hitstopRemaining > 0) {
    runtime.hitstopRemaining = Math.max(0, runtime.hitstopRemaining - dt * 1000);
    return runtime;
  }
  runtime.stageTime += dt;
  runtime.totalTime += dt;
  runtime.shotCooldown = Math.max(0, runtime.shotCooldown - dt);
  if (!runtime.guardAvailable && runtime.stageTime >= runtime.guardCooldownUntil) {
    runtime.guardAvailable = true;
  }
  runtime.guarding = input.guard && runtime.guardAvailable;

  const stage = pveStage(runtime.campaign, runtime.stageIndex);
  stepPlayerMove(runtime, stage, input, dt);
  if (runtime.phase !== "playing") {
    stepParticles(runtime, dt);
    return runtime;
  }

  if (input.shoot && runtime.shotCooldown <= 0) {
    runtime.shotCooldown = PVE_SHOT_COOLDOWN;
    const aimZ = clamp(input.aimZ ?? 0, -1, 1);
    runtime.projectiles.push({
      id: runtime.nextProjectileId++,
      owner: "player",
      x: runtime.player.x + runtime.player.facing * PVE_PLAYER_RADIUS,
      y: runtime.player.y,
      z: runtime.player.z + PVE_PLAYER_HEIGHT * 0.5,
      vx: runtime.player.facing * PVE_SHOT_SPEED,
      vy: 0,
      vz: aimZ * PVE_SHOT_SPEED * 0.45,
      radius: 6,
      damage: PVE_PLAYER_DAMAGE,
      ttl: 1.5,
      color: "#f1c66c",
    });
    runtime.shotsFired += 1;
    emitAudio(runtime, "shot");
  }

  for (const enemy of runtime.enemies) {
    if (enemy.hp <= 0) continue;
    stepEnemy(runtime, enemy, dt);
  }
  if (runtime.phase !== "playing") {
    stepParticles(runtime, dt);
    return runtime;
  }

  stepProjectiles(runtime, dt);
  stepParticles(runtime, dt);
  finishStageIfCleared(runtime);
  return runtime;
}

function stepPlayerMove(
  runtime: PveRuntime,
  stage: PveStage,
  input: PveInput,
  dt: number,
): void {
  const player = runtime.player;
  let inputX = (input.right ? 1 : 0) - (input.left ? 1 : 0);
  let inputY = (input.down ? 1 : 0) - (input.up ? 1 : 0);
  const length = Math.hypot(inputX, inputY);
  if (length > 0) {
    inputX /= length;
    inputY /= length;
    if (inputX !== 0) player.facing = inputX < 0 ? -1 : 1;
  }
  if (input.dodge && !runtime.dodgeHeld && runtime.stageTime >= runtime.dodgeCooldownUntil) {
    runtime.dodgeUntil = runtime.stageTime + 0.22;
    runtime.dodgeCooldownUntil = runtime.stageTime + 1.6;
    runtime.invulnerableUntil = Math.max(runtime.invulnerableUntil, runtime.stageTime + 0.18);
    runtime.dodgeDirectionX = length > 0 ? inputX : player.facing;
    runtime.dodgeDirectionY = length > 0 ? inputY : 0;
  }
  runtime.dodgeHeld = Boolean(input.dodge);

  const dodging = runtime.stageTime < runtime.dodgeUntil;
  const speed = PVE_MOVE_SPEED * (input.run ? PVE_RUN_MULTIPLIER : 1);
  if (dodging) {
    player.vx = runtime.dodgeDirectionX * PVE_DODGE_SPEED;
    player.vy = (runtime.dodgeDirectionY * PVE_DODGE_SPEED) / PVE_DEPTH_SCALE;
  } else {
    player.vx = inputX * speed;
    player.vy = (inputY * speed) / PVE_DEPTH_SCALE;
  }
  player.x += player.vx * dt;
  player.y += player.vy * dt;
  player.x = clamp(player.x, PVE_EDGE_MARGIN, stage.arena.width - PVE_EDGE_MARGIN);
  player.y = clamp(player.y, PVE_EDGE_MARGIN, stage.arena.depth - PVE_EDGE_MARGIN);

  if (input.jump && player.onGround) {
    player.vz = PVE_JUMP_SPEED;
    player.onGround = false;
  }
  if (!player.onGround) {
    player.vz = Math.max(-1000, player.vz - PVE_GRAVITY * dt);
    player.z += player.vz * dt;
    if (player.z <= 0) {
      player.z = 0;
      player.vz = 0;
      player.onGround = true;
    }
  }
}

function stepProjectiles(runtime: PveRuntime, dt: number): void {
  const kept: PveProjectile[] = [];
  for (const projectile of runtime.projectiles) {
    const delta = { x: projectile.vx * dt, y: projectile.vy * dt, z: projectile.vz * dt };
    const moved = {
      ...projectile,
      x: projectile.x + delta.x,
      y: projectile.y + delta.y,
      z: projectile.z + delta.z,
      ttl: projectile.ttl - dt,
    };
    if (projectile.ttl <= 0) continue;
    if (moved.owner === "player") {
      let target: PveRuntimeEnemy | undefined;
      let nearest = Infinity;
      for (const enemy of runtime.enemies) {
        if (enemy.hp <= 0) continue;
        const hit = pveSegmentHitsBox(projectile, delta, enemyAabb(enemy));
        if (hit !== null && hit < nearest) {
          nearest = hit;
          target = enemy;
        }
      }
      if (target) {
        target.hp = Math.max(0, target.hp - moved.damage);
        if (target.hp === 0) target.deathAt = runtime.stageTime;
        target.hitFlashUntil = runtime.stageTime + PVE_HURT_DURATION;
        runtime.shotsHit += 1;
        const knockback = Math.hypot(projectile.vx, projectile.vy) || 1;
        const currentStage = pveStage(runtime.campaign, runtime.stageIndex);
        target.x = clamp(
          target.x + (projectile.vx / knockback) * 14,
          PVE_EDGE_MARGIN,
          currentStage.arena.width - PVE_EDGE_MARGIN,
        );
        target.y = clamp(
          target.y + ((projectile.vy / knockback) * 14) / PVE_DEPTH_SCALE,
          PVE_EDGE_MARGIN,
          currentStage.arena.depth - PVE_EDGE_MARGIN,
        );
        runtime.hitstopRemaining = Math.max(runtime.hitstopRemaining, 48);
        emitAudio(runtime, "hit");
        burst(runtime, moved.x, moved.y, moved.z, moved.color, target.kind === "boss" ? 14 : 9);
        continue;
      }
    } else if (pveSegmentHitsBox(projectile, delta, playerAabb(runtime)) !== null) {
      damagePlayer(runtime, moved.damage);
      continue;
    }
    if (moved.ttl > 0) kept.push(moved);
  }
  runtime.projectiles = kept;
}

function stepParticles(runtime: PveRuntime, dt: number): void {
  for (const particle of runtime.particles) {
    particle.x += particle.vx * dt;
    particle.y += particle.vy * dt;
    particle.z += particle.vz * dt;
    particle.vz -= 120 * dt;
    particle.life -= dt;
  }
  runtime.particles = runtime.particles.filter((particle) => particle.life > 0);
}

export function togglePvePause(runtime: PveRuntime): void {
  if (runtime.phase === "playing") runtime.paused = !runtime.paused;
}

export function consumePveAudioEvents(runtime: PveRuntime): PveAudioEvent[] {
  const events = runtime.audioEvents;
  runtime.audioEvents = [];
  return events;
}

export function enemyHalfWidth(enemy: PveRuntimeEnemy): number {
  return enemy.radiusX;
}

export function enemyHeight(enemy: PveRuntimeEnemy): number {
  return enemy.heightZ;
}

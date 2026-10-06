/* Coin Arena · 古堡金币竞技场
 * 素材：CreativeForge 管线生成（主角 ast43024 / 敌人 ast38382 的 AI i2v 图集，
 * 32 帧 @12fps，192px），背景为同风格锚 t2i 出图。纯 Canvas 零依赖。
 *
 * 操作：←→ / A D 移动（Shift 奔跑）· 空格 / J 攻击 · R 重新开始
 */
(() => {
  "use strict";

  const W = 960, H = 540;
  const GROUND_Y = 470;
  const XL = 60, XR = 900;
  const WALK_SPEED = 230, RUN_SPEED = 400;
  const FPS = 12, FRAME_MS = 1000 / FPS;
  const ATTACK_SPF = 1000 / 32;          // 攻击动画加速播放（32fps 读条更利落）
  const ATTACK_HIT_FROM = 10, ATTACK_HIT_TO = 20; // 命中帧窗口（加速播放后的帧序号）

  const canvas = document.getElementById("stage");
  const ctx = canvas.getContext("2d");
  ctx.imageSmoothingEnabled = false;

  /* ── 资产加载 ─────────────────────────────────────────────── */
  const ASSET_V = 7; // 素材迭代版本：更新图集后递增，强制浏览器刷新缓存
  const VQ = `?v=${ASSET_V}`;
  const SHEETS = {
    hero: { idle: "assets/hero_idle.png", walk: "assets/hero_walk.png", run: "assets/hero_run.png", attack: "assets/hero_attack.png" },
    enemy: { idle: "assets/enemy_idle.png", walk: "assets/enemy_walk.png" },
  };
  const FRAMES = 32;
  const images = {};
  let loaded = 0, total = 0;
  for (const who of Object.keys(SHEETS)) {
    for (const key of Object.keys(SHEETS[who])) {
      total += 1;
      const img = new Image();
      img.src = SHEETS[who][key] + VQ;
      img.onload = () => { loaded += 1; };
      images[`${who}.${key}`] = img;
    }
  }
  const bg = new Image();
  bg.src = "assets/bg.png" + VQ;
  bg.onload = () => { loaded += 1; };
  total += 1;

  /* ── 音效（WebAudio 合成，零外部资源；首次按键后初始化）────── */
  let audio = null;
  function ensureAudio() {
    if (!audio) {
      try { audio = new (window.AudioContext || window.webkitAudioContext)(); } catch (e) { audio = null; }
    }
  }
  function beep(freqFrom, freqTo, ms, type, gain) {
    if (!audio) return;
    const osc = audio.createOscillator();
    const g = audio.createGain();
    osc.type = type || "square";
    osc.frequency.setValueAtTime(freqFrom, audio.currentTime);
    osc.frequency.exponentialRampToValueAtTime(Math.max(1, freqTo), audio.currentTime + ms / 1000);
    g.gain.setValueAtTime(gain || 0.06, audio.currentTime);
    g.gain.exponentialRampToValueAtTime(0.0001, audio.currentTime + ms / 1000);
    osc.connect(g).connect(audio.destination);
    osc.start(); osc.stop(audio.currentTime + ms / 1000);
  }
  const sfx = {
    pickup: () => beep(880, 1500, 90, "square", 0.05),
    swing: () => beep(300, 90, 120, "sawtooth", 0.04),
    hit: () => beep(180, 40, 160, "square", 0.07),
    hurt: () => beep(140, 60, 220, "triangle", 0.08),
  };

  /* ── 状态 ────────────────────────────────────────────────── */
  const state = {
    mode: "start",            // start | playing | gameover
    score: 0, coins: 0, wave: 0, lives: 3,
    time: 0,
    hero: null,
    enemies: [], coinsArr: [], particles: [],
    waveTimer: 0, spawnQueue: 0,
    shakeUntil: 0,
  };

  function makeHero() {
    return {
      x: W / 2, y: GROUND_Y, facing: 1,
      action: "idle", frame: 0, frameMs: FRAME_MS,
      attackUntil: 0, attackHit: false,
      invulnUntil: 0, hurtFlashUntil: 0,
      moving: false, running: false,
    };
  }
  function makeEnemy(x) {
    const hp = 2 + Math.floor(state.wave / 4);
    return {
      x, y: GROUND_Y, facing: 1,
      action: "walk", frame: 0,
      speed: 55 + state.wave * 7 + Math.random() * 15,
      hp, maxHp: hp,
      hitstunUntil: 0, flashUntil: 0,
      spawnFade: 1, // 出生淡入
    };
  }
  function spawnCoin() {
    state.coinsArr.push({
      x: XL + 30 + Math.random() * (XR - XL - 60),
      y: GROUND_Y - 26 - Math.random() * 60,
      born: state.time, life: 12, phase: Math.random() * Math.PI * 2,
    });
  }

  function resetGame() {
    state.score = 0; state.coins = 0; state.wave = 0; state.lives = 3;
    state.hero = makeHero();
    state.enemies = []; state.coinsArr = []; state.particles = [];
    state.waveTimer = 1.2; state.spawnQueue = 0;
    for (let i = 0; i < 4; i += 1) spawnCoin();
    state.mode = "playing";
  }

  function nextWave() {
    state.wave += 1;
    state.spawnQueue = Math.min(6, 2 + Math.floor(state.wave / 2));
    state.waveTimer = state.spawnQueue > 0 ? 0.8 : 3.2;
  }

  /* ── 输入 ────────────────────────────────────────────────── */
  const keys = new Set();
  window.addEventListener("keydown", (event) => {
    ensureAudio();
    const key = event.key.toLowerCase();
    if ([" ", "arrowup", "arrowdown", "arrowleft", "arrowright"].includes(key)) event.preventDefault();
    if (state.mode === "start" || state.mode === "gameover") {
      if (key === "r" || key === "enter" || key === " ") resetGame();
      return;
    }
    keys.add(key);
    if ((key === " " || key === "j") && state.hero) tryAttack();
    if (key === "r") resetGame();
  });
  window.addEventListener("keyup", (event) => keys.delete(event.key.toLowerCase()));
  canvas.addEventListener("click", () => { ensureAudio(); if (state.mode !== "playing") resetGame(); });

  function tryAttack() {
    const hero = state.hero;
    const now = state.time;
    if (hero.attackUntil > now) return;
    hero.attackUntil = now + FRAMES * ATTACK_SPF * 0.8; // 播放帧窗口的 80%
    hero.attackHit = false;
    sfx.swing();
  }

  /* ── 更新 ────────────────────────────────────────────────── */
  function update(dt) {
    state.time += dt;
    if (state.mode !== "playing") return;
    const hero = state.hero;
    const now = state.time;

    // 主角移动：攻击未结束前锁定动作
    const left = keys.has("arrowleft") || keys.has("a");
    const right = keys.has("arrowright") || keys.has("d");
    const running = keys.has("shift");
    hero.moving = false;
    if (hero.attackUntil <= now && (left !== right)) {
      const speed = running ? RUN_SPEED : WALK_SPEED;
      const dir = right ? 1 : -1;
      hero.x = Math.max(XL, Math.min(XR, hero.x + dir * speed * dt));
      hero.facing = dir;
      hero.moving = true;
      hero.running = running;
    }
    // 动作与帧推进
    const action = hero.attackUntil > now ? "attack"
      : hero.moving ? (hero.running ? "run" : "walk") : "idle";
    if (action !== hero.action) { hero.action = action; hero.frame = 0; }
    const spf = hero.action === "attack" ? ATTACK_SPF : FRAME_MS;
    hero.frame = Math.floor(state.time * 1000 / spf) % FRAMES;

    // 攻击判定：命中帧窗口内，面朝方向矩形
    if (hero.action === "attack" && !hero.attackHit
        && hero.frame >= ATTACK_HIT_FROM && hero.frame <= ATTACK_HIT_TO) {
      const hx = hero.facing === 1 ? hero.x + 30 : hero.x - 130;
      for (const enemy of state.enemies) {
        if (enemy.hp > 0 && Math.abs(enemy.x - (hx + 50)) < 50 + 34) {
          hero.attackHit = true;
          damageEnemy(enemy, hero.facing);
          break;
        }
      }
    }

    // 敌人 AI：追踪 + 接触伤害
    for (const enemy of state.enemies) {
      if (enemy.hp <= 0) continue;
      enemy.spawnFade = Math.min(1, enemy.spawnFade + dt * 1.5);
      if (now < enemy.hitstunUntil) {
        enemy.action = "idle";
      } else {
        const dir = Math.sign(hero.x - enemy.x) || 1;
        enemy.facing = dir;
        enemy.x += dir * enemy.speed * dt;
        enemy.action = "walk";
        // 接触伤害（主角无敌帧外）
        if (now > hero.invulnUntil && Math.abs(enemy.x - hero.x) < 52) {
          hero.lives -= 1;
          hero.invulnUntil = now + 1.2;
          hero.hurtFlashUntil = now + 0.25;
          state.shakeUntil = now + 0.25;
          hero.x = Math.max(XL, Math.min(XR, hero.x - enemy.facing * 70));
          sfx.hurt();
          burst(hero.x, hero.y - 60, "#d9534f", 10);
          if (hero.lives <= 0) { state.mode = "gameover"; return; }
        }
      }
      enemy.frame = Math.floor(state.time * 1000 / FRAME_MS) % FRAMES;
    }
    state.enemies = state.enemies.filter((enemy) => enemy.hp > 0);

    // 波次调度
    if (state.spawnQueue > 0) {
      state.waveTimer -= dt;
      if (state.waveTimer <= 0) {
        const fromLeft = Math.random() < 0.5;
        state.enemies.push(makeEnemy(fromLeft ? XL - 40 : XR + 40));
        state.spawnQueue -= 1;
        state.waveTimer = 0.9;
      }
    } else if (state.enemies.length === 0) {
      state.waveTimer -= dt;
      if (state.waveTimer <= 0) nextWave();
    }

    // 金币：旋转 / 超时 / 拾取
    if (state.coinsArr.length < 5 && Math.random() < dt * 0.5) spawnCoin();
    state.coinsArr = state.coinsArr.filter((coin) => {
      if (state.time - coin.born > coin.life) return false;
      if (Math.abs(coin.x - hero.x) < 44 && Math.abs(coin.y - (hero.y - 60)) < 90) {
        state.score += 10; state.coins += 1;
        sfx.pickup();
        burst(coin.x, coin.y, "#f5c542", 8);
        return false;
      }
      return true;
    });

    stepParticles(dt);
  }

  function damageEnemy(enemy, facing) {
    enemy.hp -= 1;
    enemy.flashUntil = state.time + 0.18;
    enemy.hitstunUntil = state.time + 0.45;
    enemy.x = Math.max(XL - 40, Math.min(XR + 40, enemy.x + facing * 130));
    sfx.hit();
    burst(enemy.x, enemy.y - 60, "#e8a13c", 12);
    if (enemy.hp <= 0) {
      state.score += 50;
      burst(enemy.x, enemy.y - 60, "#8ecfc0", 18);
      if (Math.random() < 0.6) {
        state.coinsArr.push({ x: enemy.x, y: GROUND_Y - 30, born: state.time, life: 10, phase: 0 });
      }
    }
  }

  function burst(x, y, color, count) {
    for (let i = 0; i < count; i += 1) {
      const angle = Math.random() * Math.PI * 2;
      const speed = 60 + Math.random() * 160;
      state.particles.push({
        x, y, vx: Math.cos(angle) * speed, vy: Math.sin(angle) * speed - 60,
        born: state.time, life: 0.4 + Math.random() * 0.3, color,
      });
    }
  }
  function stepParticles(dt) {
    for (const p of state.particles) {
      p.x += p.vx * dt; p.y += p.vy * dt; p.vy += 380 * dt;
    }
    state.particles = state.particles.filter((p) => state.time - p.born < p.life);
  }

  /* ── 绘制 ────────────────────────────────────────────────── */
  function drawEntity(who, entity, action, frameOverride) {
    const img = images[`${who}.${action}`];
    if (!img || !img.complete || !img.naturalWidth) return;
    const fw = img.naturalWidth / FRAMES;
    const fh = img.naturalHeight;
    const idx = (frameOverride !== undefined ? frameOverride : entity.frame) % FRAMES;
    ctx.save();
    if (entity.spawnFade !== undefined && entity.spawnFade < 1) {
      ctx.globalAlpha = entity.spawnFade;
    }
    if (who === "hero" && entity.invulnUntil > state.time
        && Math.floor(state.time * 12) % 2 === 0) {
      ctx.globalAlpha = 0.35; // 无敌帧闪烁
    }
    ctx.translate(entity.x, entity.y);
    ctx.scale(entity.facing || 1, 1);
    ctx.drawImage(img, idx * fw, 0, fw, fh, -fw / 2, -fh, fw, fh);
    if (entity.flashUntil > state.time) {
      ctx.globalCompositeOperation = "source-atop";
      ctx.globalAlpha = 0.6;
      ctx.fillStyle = "#ff5544";
      ctx.fillRect(idx * fw, 0, fw, fh);
    }
    ctx.restore();
  }

  function drawCoin(coin) {
    const age = state.time - coin.born;
    const spin = Math.abs(Math.sin(coin.phase + age * 4));
    const blink = coin.life - age < 3 && Math.floor(age * 8) % 2 === 0;
    if (blink) return;
    const w = Math.max(4, 16 * spin);
    const bob = Math.sin(age * 3 + coin.phase) * 4;
    ctx.save();
    ctx.translate(coin.x, coin.y + bob);
    ctx.fillStyle = "#f5c542";
    ctx.strokeStyle = "#a87b1c";
    ctx.lineWidth = 2;
    ctx.beginPath();
    ctx.ellipse(0, 0, w / 2, 9, 0, 0, Math.PI * 2);
    ctx.fill(); ctx.stroke();
    if (w > 10) {
      ctx.fillStyle = "#ffe28a";
      ctx.beginPath();
      ctx.ellipse(-w / 6, -2, w / 6, 4, 0, 0, Math.PI * 2);
      ctx.fill();
    }
    ctx.restore();
  }

  function drawParticles() {
    for (const p of state.particles) {
      const alpha = 1 - (state.time - p.born) / p.life;
      ctx.globalAlpha = Math.max(0, alpha);
      ctx.fillStyle = p.color;
      ctx.fillRect(p.x - 2, p.y - 2, 4, 4);
    }
    ctx.globalAlpha = 1;
  }

  function drawHeart(x, y, filled) {
    ctx.save();
    ctx.translate(x, y);
    ctx.fillStyle = filled ? "#e0554f" : "#3a3a44";
    ctx.beginPath();
    ctx.moveTo(0, 4);
    ctx.bezierCurveTo(-9, -6, -4, -13, 0, -7);
    ctx.bezierCurveTo(4, -13, 9, -6, 0, 4);
    ctx.fill();
    ctx.restore();
  }

  function drawHUD() {
    ctx.save();
    ctx.fillStyle = "rgba(16,18,26,.62)";
    ctx.fillRect(12, 12, 250, 64);
    ctx.fillStyle = "#f0ead8";
    ctx.font = "600 17px 'Segoe UI', 'Microsoft YaHei', sans-serif";
    ctx.fillText(`分数 ${state.score}`, 24, 36);
    ctx.font = "500 13px 'Segoe UI', 'Microsoft YaHei', sans-serif";
    ctx.fillStyle = "#c8c2b0";
    ctx.fillText(`金币 ${state.coins} · 波次 ${state.wave}`, 24, 58);
    for (let i = 0; i < 3; i += 1) drawHeart(190 + i * 24, 36, i < state.lives);
    ctx.restore();
  }

  function drawOverlay(title, lines, hint) {
    ctx.save();
    ctx.fillStyle = "rgba(10,12,18,.78)";
    ctx.fillRect(0, 0, W, H);
    ctx.textAlign = "center";
    ctx.fillStyle = "#f0ead8";
    ctx.font = "700 40px 'Segoe UI', 'Microsoft YaHei', sans-serif";
    ctx.fillText(title, W / 2, H / 2 - 70);
    ctx.font = "400 17px 'Segoe UI', 'Microsoft YaHei', sans-serif";
    ctx.fillStyle = "#c8c2b0";
    lines.forEach((line, index) => ctx.fillText(line, W / 2, H / 2 - 20 + index * 28));
    ctx.fillStyle = "#f5c542";
    ctx.font = "600 18px 'Segoe UI', 'Microsoft YaHei', sans-serif";
    ctx.fillText(hint, W / 2, H / 2 + 90);
    ctx.restore();
  }

  function render() {
    ctx.save();
    if (state.shakeUntil > state.time) {
      ctx.translate((Math.random() - 0.5) * 6, (Math.random() - 0.5) * 6);
    }
    if (bg.complete && bg.naturalWidth) {
      ctx.drawImage(bg, 0, 0, bg.naturalWidth, bg.naturalHeight, 0, 0, W, H);
    } else {
      ctx.fillStyle = "#1a1c26";
      ctx.fillRect(0, 0, W, H);
    }
    // 地面阴影
    for (const enemy of state.enemies) {
      ctx.fillStyle = "rgba(0,0,0,.25)";
      ctx.beginPath();
      ctx.ellipse(enemy.x, GROUND_Y + 4, 34, 7, 0, 0, Math.PI * 2);
      ctx.fill();
    }
    if (state.hero) {
      ctx.fillStyle = "rgba(0,0,0,.3)";
      ctx.beginPath();
      ctx.ellipse(state.hero.x, GROUND_Y + 4, 40, 8, 0, 0, Math.PI * 2);
      ctx.fill();
    }

    for (const coin of state.coinsArr) drawCoin(coin);
    drawParticles();

    for (const enemy of state.enemies) {
      drawEntity("enemy", enemy, enemy.action === "idle" ? "idle" : "walk");
      // 血条
      if (enemy.hp < enemy.maxHp) {
        const w = 56;
        ctx.fillStyle = "rgba(0,0,0,.5)";
        ctx.fillRect(enemy.x - w / 2, GROUND_Y - 208, w, 5);
        ctx.fillStyle = "#d9534f";
        ctx.fillRect(enemy.x - w / 2, GROUND_Y - 208, (w * enemy.hp) / enemy.maxHp, 5);
      }
    }
    if (state.hero) {
      drawEntity("hero", state.hero, state.hero.action,
        state.hero.action === "attack"
          ? Math.floor(state.hero.frame) : state.hero.frame);
    }

    ctx.restore();

    if (state.mode === "playing") drawHUD();
    if (state.mode === "start") {
      drawOverlay("古堡金币竞技场", [
        "← → 或 A D 移动 · Shift 奔跑 · 空格 / J 攻击 · R 重开",
        "收集金币 +10 分，击败小恶魔 +50 分，被碰到会掉一颗心",
        "波次会越来越难——看看你能守多少波！",
        "素材由 CreativeForge 管线生成（主角 / 敌人 / 背景 同风格）",
      ], "按任意键开始");
    }
    if (state.mode === "gameover") {
      drawOverlay("游戏结束", [
        `最终得分 ${state.score} · 金币 ${state.coins} · 坚持到第 ${state.wave} 波`,
      ], "按 R 重新开始");
    }
    if (loaded < total && state.mode === "start") {
      ctx.fillStyle = "rgba(10,12,18,.6)";
      ctx.fillRect(0, H - 34, W, 34);
      ctx.fillStyle = "#c8c2b0";
      ctx.font = "400 13px 'Segoe UI', sans-serif";
      ctx.textAlign = "center";
      ctx.fillText(`资产加载中 ${loaded}/${total}…`, W / 2, H - 12);
      ctx.textAlign = "left";
    }
  }

  /* ── 主循环：固定时间步进 ─────────────────────────────────── */
  let last = performance.now();
  let acc = 0;
  const STEP = 1000 / 60;
  function loop(now) {
    acc += Math.min(50, now - last);
    last = now;
    while (acc >= STEP) {
      update(STEP / 1000);
      acc -= STEP;
    }
    render();
    requestAnimationFrame(loop);
  }
  requestAnimationFrame(loop);
})();

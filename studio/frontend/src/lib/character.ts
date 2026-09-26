/**
 * Prompt-driven character sprite generator (front-end mirror of the backend
 * CharacterSpec). The same spec always renders the same 8×8 sprite, and
 * different prompts (hair / outfit / element / body / gender / weapon …)
 * render visibly different characters.
 */

export interface CharacterLike {
  seed?: number;
  gender?: string;
  build?: string;
  hair_style?: string;
  hair_length?: string;
  hair_color?: string;
  hair_color_hex?: string;
  skin?: string;
  skin_hex?: string;
  eyes?: string;
  eyes_hex?: string;
  role?: string;
  weapon?: string;
  accessory?: string[];
  element?: string;
  class?: string;
  expression?: string;
  height_cm?: number;
  palette?: Record<string, string>;
}

export interface SpriteInput {
  seed: number;
  gender: string;
  build: string;
  hairStyle: string;
  hairColor: string;
  skin: string;
  eyes: string;
  outline: string;
  outfit: string;
  accent: string;
  metal: string;
  role: string;
  weapon: string;
  accessory: string[];
}

export const GRID = 8;

/** Stable seed for legacy assets that predate the CharacterSpec. */
export function seedFromString(value?: string | null): number {
  if (!value) return 0;
  let hash = 0;
  for (const char of value) hash = (hash * 31 + char.charCodeAt(0)) % 2147483647;
  return hash;
}

/** PReCon palette order: outline, shadow, base, highlight, accent, hair, skin, metal, eyes. */
export function spriteInput(spec?: CharacterLike | null, palette?: string[]): SpriteInput {
  const character = spec ?? {};
  const roles = character.palette ?? {};
  const colors = palette ?? [];

  return {
    seed: Number(character.seed ?? 0) || 0,
    gender: character.gender ?? "neutral",
    build: character.build ?? "slim",
    hairStyle: character.hair_style ?? "long",
    hairColor: character.hair_color_hex ?? roles.hair ?? colors[10] ?? "#1b2230",
    skin: character.skin_hex ?? roles.skin ?? colors[12] ?? "#e8b98a",
    eyes: character.eyes_hex ?? roles.eyes ?? colors[15] ?? "#4cc2ff",
    outline: roles.outline ?? colors[0] ?? "#07090d",
    outfit: roles.base ?? colors[5] ?? "#4cc2ff",
    accent: roles.accent ?? colors[8] ?? "#ffb454",
    metal: roles.metal ?? colors[14] ?? "#94a3b8",
    role: character.role ?? "character",
    weapon: character.weapon ?? "none",
    accessory: character.accessory ?? [],
  };
}

export function shade(hex: string, amount: number): string {
  const value = hex.replace("#", "");
  const num = parseInt(value.length === 3 ? value.replace(/(.)/g, "$1$1") : value, 16);
  const channels = [(num >> 16) & 255, (num >> 8) & 255, num & 255].map((c) =>
    Math.max(0, Math.min(255, Math.round(c + 255 * amount))),
  );
  return `#${channels.map((c) => c.toString(16).padStart(2, "0")).join("")}`;
}

/** 8×8 pixel grid: `after` is the clean sprite, `before` the muddy raw input. */
export function buildSprite(spec?: CharacterLike | null, palette?: string[]): { after: (string | null)[][]; before: (string | null)[][] } {
  const input = spriteInput(spec, palette);
  const size = GRID;
  const after: (string | null)[][] = Array.from({ length: size }, () => Array(size).fill(null));
  const before: (string | null)[][] = Array.from({ length: size }, () => Array(size).fill(null));

  const put = (x: number, y: number, color: string | null) => {
    if (x < 0 || y < 0 || x >= size || y >= size) return;
    after[y][x] = color;
  };

  const seed = Math.abs(input.seed);
  const slim = input.build === "slim" || input.gender === "female" || input.build === "petite";
  const wide = input.build === "muscular" || input.build === "tall";
  const petite = input.build === "petite";
  const top = petite ? 1 : 0;

  const hair = input.hairColor;
  const hairDark = shade(hair, -0.18);
  const skin = input.skin;
  const skinDark = shade(skin, -0.18);
  const outfit = input.outfit;
  const outfitDark = shade(outfit, -0.16);
  const accent = input.accent;
  const metal = input.metal;
  const outline = input.outline;
  const eyes = input.eyes;

  // ---- head / face -------------------------------------------------------
  const headLeft = 3;
  const headRight = 4;
  if (input.hairStyle !== "bald") {
    for (let x = 2; x <= 5; x += 1) put(x, top, hair);
    put(2, top + 1, hairDark);
    put(5, top + 1, hairDark);
  }
  put(3, top + 1, skin);
  put(4, top + 1, skin);
  put(3, top + 2, skin);
  put(4, top + 2, skin);

  // eyes
  put(3, top + 2, eyes);
  put(4, top + 2, eyes);

  // hair by style
  if (input.hairStyle === "long") {
    put(2, top + 2, hair);
    put(5, top + 2, hair);
    put(2, top + 3, hairDark);
    put(5, top + 3, hairDark);
    put(2, top + 4, hairDark);
    put(5, top + 4, hairDark);
  } else if (input.hairStyle === "ponytail") {
    put(6, top + 1, hair);
    put(6, top + 2, hair);
    put(6, top + 3, hairDark);
  } else if (input.hairStyle === "twin_tail") {
    put(1, top + 2, hair);
    put(1, top + 3, hairDark);
    put(6, top + 2, hair);
    put(6, top + 3, hairDark);
  } else if (input.hairStyle === "braid") {
    put(6, top + 2, hair);
    put(6, top + 3, hairDark);
    put(6, top + 4, hair);
  } else if (input.hairStyle === "curly") {
    put(2, top, hair);
    put(5, top, hair);
    put(1, top + 1, hair);
    put(6, top + 1, hair);
  } else if (input.hairStyle === "bangs") {
    put(3, top + 1, hair);
    put(4, top + 1, hair);
  }

  // ---- torso -------------------------------------------------------------
  const shoulderLeft = wide ? 2 : slim ? 3 : 2;
  const shoulderRight = wide ? 5 : slim ? 4 : 5;
  for (let y = top + 3; y <= top + 5; y += 1) {
    for (let x = shoulderLeft; x <= shoulderRight; x += 1) {
      put(x, y, y === top + 5 ? outfitDark : outfit);
    }
  }
  // arms
  put(shoulderLeft - 1, top + 3, outfitDark);
  put(shoulderRight + 1, top + 3, outfitDark);
  put(shoulderLeft - 1, top + 4, skin);
  put(shoulderRight + 1, top + 4, skin);

  // ---- legs / feet -------------------------------------------------------
  const legY = top + 6;
  put(3, legY, outfitDark);
  put(4, legY, outfitDark);
  put(3, legY + 1, outline);
  put(4, legY + 1, outline);

  // ---- accessories -------------------------------------------------------
  if (input.accessory.includes("cape")) {
    put(shoulderLeft - 1, top + 4, accent);
    put(shoulderLeft - 1, top + 5, accent);
  }
  if (input.accessory.includes("wings")) {
    put(shoulderLeft - 1, top + 2, accent);
    put(shoulderRight + 1, top + 2, accent);
  }
  if (input.accessory.includes("crown")) {
    put(3, top, accent);
    put(4, top, accent);
  }
  if (input.accessory.includes("horns")) {
    put(2, top, accent);
    put(5, top, accent);
  }
  if (input.accessory.includes("halo")) {
    put(3, 0, accent);
    put(4, 0, accent);
  }
  if (input.accessory.includes("mask")) {
    put(3, top + 2, outline);
    put(4, top + 2, outline);
  }

  // ---- weapon ------------------------------------------------------------
  const weapon = input.weapon;
  const weaponShaft = metal;
  if (weapon === "staff") {
    put(6, top + 1, accent);
    for (let y = top + 2; y <= top + 6; y += 1) put(6, y, metal);
  } else if (weapon === "bow") {
    put(6, top + 2, metal);
    put(6, top + 3, metal);
    put(6, top + 4, metal);
    put(7, top + 3, metal);
  } else if (weapon === "sword") {
    for (let y = top + 3; y <= top + 5; y += 1) put(6, y, weaponShaft);
    put(6, top + 6, accent);
  } else if (weapon === "dagger") {
    put(6, top + 4, weaponShaft);
    put(6, top + 5, accent);
  } else if (weapon === "axe") {
    put(6, top + 3, weaponShaft);
    put(6, top + 4, metal);
    put(6, top + 5, metal);
  } else if (weapon === "hammer") {
    put(6, top + 3, metal);
    put(6, top + 4, accent);
    put(6, top + 5, weaponShaft);
  } else if (weapon === "scythe") {
    put(6, top + 2, accent);
    put(6, top + 3, metal);
    for (let y = top + 4; y <= top + 6; y += 1) put(6, y, weaponShaft);
  } else if (weapon === "tome") {
    put(1, top + 4, accent);
    put(1, top + 5, metal);
  } else if (weapon === "orb") {
    put(6, top + 2, accent);
  }

  // ---- role accent -------------------------------------------------------
  if (input.role === "boss") {
    put(shoulderLeft, top + 3, accent);
    put(shoulderRight, top + 3, accent);
  }
  // seed-driven spark so two same-class prompts still differ
  put(seed % 2 === 0 ? 0 : 7, top + (seed % 3), accent);

  // ---- raw (before) variant: muddy, off-grid, no clean silhouette --------
  for (let y = 0; y < size; y += 1) {
    for (let x = 0; x < size; x += 1) {
      const clean = after[y][x];
      const base = clean ?? shade(input.outline, ((x + y) % 5) * 0.02);
      const delta = ((((seed + x * 7 + y * 13) % 9) - 4) / 4) * 34;
      before[y][x] = shade(base, delta / 255);
    }
  }

  return { after, before };
}

export function spriteSignature(spec?: CharacterLike | null, palette?: string[]): string {
  const input = spriteInput(spec, palette);
  return [input.seed, input.hairColor, input.outfit, input.accent, input.eyes].join("-");
}

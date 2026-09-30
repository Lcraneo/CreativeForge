/**
 * Deterministic 8x8 sprite generation for the Pixel Studio
 * Before / After comparison:
 *   - "before" emulates the raw AI original (off-palette noise, ragged edge)
 *   - "after"  is the PReCon result (semantic palette, clean silhouette)
 */

export const GRID = 8;

export type Sprite = Array<Array<string | null>>;

export interface SpriteSpec {
  seed?: number;
  hair_color_hex?: string;
  skin_hex?: string;
  eyes_hex?: string;
  palette?: Record<string, string>;
}

/** FNV-1a string hash folded into a positive 31-bit int. */
export function seedFromString(value?: string | null): number {
  if (!value) return 20260926;
  let hash = 2166136261;
  for (const ch of value) {
    hash ^= ch.codePointAt(0) ?? 0;
    hash = Math.imul(hash, 16777619);
  }
  return (hash >>> 0) % 2147483647 || 1;
}

function mulberry32(seed: number): () => number {
  let a = seed >>> 0;
  return () => {
    a |= 0;
    a = (a + 0x6d2b79f5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

function hexToRgb(hex: string): [number, number, number] {
  const clean = hex.replace("#", "");
  const full =
    clean.length === 3
      ? clean
          .split("")
          .map((ch) => ch + ch)
          .join("")
      : clean.padEnd(6, "0").slice(0, 6);
  return [
    parseInt(full.slice(0, 2), 16) || 0,
    parseInt(full.slice(2, 4), 16) || 0,
    parseInt(full.slice(4, 6), 16) || 0,
  ];
}

function rgbToHex(r: number, g: number, b: number): string {
  const part = (v: number) =>
    Math.max(0, Math.min(255, Math.round(v)))
      .toString(16)
      .padStart(2, "0");
  return `#${part(r)}${part(g)}${part(b)}`;
}

function shade(hex: string, amount: number): string {
  const [r, g, b] = hexToRgb(hex);
  if (amount >= 0) {
    return rgbToHex(r + (255 - r) * amount, g + (255 - g) * amount, b + (255 - b) * amount);
  }
  return rgbToHex(r * (1 + amount), g * (1 + amount), b * (1 + amount));
}

/** Semantic mask of the 8x8 sprite: h=hair s=skin e=eyes o=outfit b=boots .=empty */
const MASK = [
  "..hhhh..",
  ".hhhhhh.",
  ".hssssh.",
  ".hseseh.",
  "..ssss..",
  ".oooooo.",
  ".oooooo.",
  "..b..b..",
];

export function buildSprite(
  spec: SpriteSpec | null | undefined,
  palette: string[],
): { before: Sprite; after: Sprite } {
  const seed = spec?.seed ?? seedFromString(spec?.hair_color_hex ?? "cf");
  const random = mulberry32(seed);

  const colors = {
    hair: spec?.hair_color_hex || spec?.palette?.hair || palette[3] || "#8a5a3b",
    skin: spec?.skin_hex || palette[11] || "#e8b98a",
    eyes: spec?.eyes_hex || palette[0] || "#1a1814",
    outfit: spec?.palette?.base || spec?.palette?.outfit || palette[1] || "#4cc2ff",
    boots: spec?.palette?.outline || palette[0] || "#1a1814",
  };

  const after: Sprite = MASK.map((row) =>
    row.split("").map((cell) => {
      switch (cell) {
        case "h":
          return colors.hair;
        case "s":
          return colors.skin;
        case "e":
          return colors.eyes;
        case "o":
          return colors.outfit;
        case "b":
          return colors.boots;
        default:
          return null;
      }
    }),
  );

  // "before": same subject, but 64-color noise, ragged silhouette, off-grid feel
  const noiseColors = palette.flatMap((color) => [shade(color, 0.25), shade(color, -0.2), color]);
  const before: Sprite = after.map((row, y) =>
    row.map((cell, x) => {
      const edge = x === 0 || x === 7 || y === 0 || y === 7;
      if (!cell && !(edge && random() < 0.35)) {
        if (random() < 0.12) return noiseColors[Math.floor(random() * noiseColors.length)];
        return null;
      }
      if (!cell) return null;
      const jitter = random();
      if (jitter < 0.45) return shade(cell, (random() - 0.5) * 0.55);
      if (jitter < 0.6) return noiseColors[Math.floor(random() * noiseColors.length)];
      return cell;
    }),
  );

  return { before, after };
}

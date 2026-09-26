/**
 * Art parameters for the vector character renderer.
 *
 * The backend CharacterSpec is translated into an explicit drawing spec:
 * a soft anime-style palette (no pure black line work), body proportions
 * from build/gender/height, the garment template from the class, and the
 * hair / face / weapon / accessory variants.
 */

import { shade, spriteInput, type CharacterLike } from "./character";

export interface ArtPalette {
  line: string;
  outline: string;
  shadow: string;
  base: string;
  baseShadow: string;
  highlight: string;
  accent: string;
  accentSoft: string;
  hair: string;
  hairShadow: string;
  hairLight: string;
  skin: string;
  skinShadow: string;
  skinLight: string;
  eyes: string;
  metal: string;
  metalDark: string;
  white: string;
}

export interface ArtGeometry {
  cx: number;
  topY: number;
  groundY: number;
  headCy: number;
  headRx: number;
  headRy: number;
  chinY: number;
  neckW: number;
  shoulderY: number;
  shoulderHalf: number;
  bustY: number;
  bustR: number;
  waistY: number;
  waistHalf: number;
  hipY: number;
  hipHalf: number;
  kneeY: number;
  ankleY: number;
  shoeY: number;
  armW: number;
  heightPx: number;
}

export type Garment = "suit" | "robe" | "armor" | "tunic" | "hood";

export interface ArtParams {
  palette: ArtPalette;
  geometry: ArtGeometry;
  garment: Garment;
  hairStyle: string;
  hairLength: string;
  expression: string;
  gender: string;
  build: string;
  weapon: string;
  accessory: string[];
  seed: number;
  hasRibbon: boolean;
  hasEarrings: boolean;
}

const GARMENT_BY_CLASS: Record<string, Garment> = {
  mage: "robe",
  priest: "robe",
  summoner: "robe",
  druid: "robe",
  warrior: "armor",
  archer: "tunic",
  engineer: "tunic",
  rogue: "hood",
  monk: "tunic",
  bard: "suit",
  hero: "suit",
};

export function artParams(
  spec?: CharacterLike | null,
  paletteColors?: string[],
): ArtParams {
  const input = spriteInput(spec, paletteColors);
  const classKey = (spec?.class ?? "hero") as string;
  const garment = GARMENT_BY_CLASS[classKey] ?? "suit";

  const outline = input.outline;
  const hair = input.hairColor;
  const hairShadow = shade(hair, -0.24);
  const hairLight = shade(hair, 0.26);
  const skin = input.skin;
  const skinShadow = shade(skin, -0.16);
  const skinLight = shade(skin, 0.18);
  const base = input.outfit;
  const baseShadow = shade(base, -0.22);
  const highlight = shade(base, 0.5);
  const accent = input.accent;
  const eyes = input.eyes;
  const metal = input.metal;

  const female = input.gender === "female";
  const muscular = input.build === "muscular" || input.build === "tall";
  const petite = input.build === "petite";

  // canonical figure: ~7.25 heads tall (soft anime proportions)
  const topY = 86;
  const groundY = 726;
  const heightPx = groundY - topY;
  const headRy = heightPx / 14.6;
  const headRx = headRy * (female ? 0.76 : 0.8);
  const headCy = topY + headRy;
  const chinY = headCy + headRy;
  const shoulderY = chinY + (petite ? 24 : 30);
  const shoulderHalf =
    (muscular ? 62 : petite ? 44 : 52) + (female ? -5 : 0);
  const waistY = shoulderY + (muscular ? 118 : 124);
  const waistHalf = female ? 25 : muscular ? 33 : 29;
  const hipY = waistY + 42;
  const hipHalf = female ? 37 : muscular ? 36 : 34;
  const kneeY = hipY + 182;
  const ankleY = groundY - (petite ? 22 : 28);
  const shoeY = groundY;

  const line = shade(hair, -0.66);

  return {
    palette: {
      line,
      outline,
      shadow: shade(line, 0.12),
      base,
      baseShadow,
      highlight,
      accent,
      accentSoft: shade(accent, 0.4),
      hair,
      hairShadow,
      hairLight,
      skin,
      skinShadow,
      skinLight,
      eyes,
      metal,
      metalDark: shade(metal, -0.25),
      white: "#f7f5f2",
    },
    geometry: {
      cx: 200,
      topY,
      groundY,
      headCy,
      headRx,
      headRy,
      chinY,
      neckW: female ? 10 : 12,
      shoulderY,
      shoulderHalf,
      bustY: shoulderY + 58,
      bustR: female ? 24 : 20,
      waistY,
      waistHalf,
      hipY,
      hipHalf,
      kneeY,
      ankleY,
      shoeY,
      armW: female ? 9 : 11,
      heightPx,
    },
    garment,
    hairStyle: input.hairStyle,
    hairLength: (spec?.hair_length as string) ?? "long",
    expression: (spec?.expression as string) ?? "cold",
    gender: input.gender,
    build: input.build,
    weapon: input.weapon,
    accessory: input.accessory,
    seed: input.seed,
    hasRibbon:
      input.hairStyle === "ponytail" ||
      input.hairStyle === "twin_tail" ||
      (female && input.hairStyle === "long" && input.seed % 2 === 0),
    hasEarrings:
      female || input.accessory.includes("necklace") || input.accessory.includes("crown"),
  };
}

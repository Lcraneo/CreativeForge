import { cx } from "./ui";
import type { CharacterSpec } from "../types";

type ArtView = "bust" | "front" | "side" | "back";

interface ArtSpec {
  hair_color_hex?: string;
  skin_hex?: string;
  eyes_hex?: string;
  hair_style?: string;
  hair_length?: string;
  build?: string;
  palette?: Record<string, string>;
}

const DEFAULTS = {
  hair: "#8a5a3b",
  skin: "#e8b98a",
  eyes: "#4a6f8a",
  outfit: "#1a1814",
  accent: "#a9812f",
  line: "#1a1814",
};

/**
 * Deterministic pixel character rendered from CharacterSpec fields.
 * Views: bust (portrait), front / side / back (full-body turnaround).
 */
export function CharacterArt({
  spec,
  palette,
  view = "bust",
  className,
  detail = "detailed",
}: {
  spec?: ArtSpec | Partial<CharacterSpec> | null;
  palette?: string[];
  view?: ArtView;
  className?: string;
  detail?: "simple" | "detailed";
}) {
  const colors = {
    hair: spec?.hair_color_hex || DEFAULTS.hair,
    skin: spec?.skin_hex || DEFAULTS.skin,
    eyes: spec?.eyes_hex || DEFAULTS.eyes,
    outfit: spec?.palette?.base || spec?.palette?.outfit || palette?.[1] || DEFAULTS.outfit,
    accent: spec?.palette?.outfit || palette?.[4] || DEFAULTS.accent,
    line: spec?.palette?.outline || palette?.[0] || DEFAULTS.line,
  };

  const hairStyle = spec?.hair_style ?? spec?.hair_length ?? "";
  const bald = /bald/i.test(hairStyle);
  const longHair = /long|straight|braid|curly/i.test(hairStyle);
  const ponytail = /ponytail|twin/i.test(hairStyle);
  const bulky = /muscular|tall|plump/i.test(spec?.build ?? "");

  const cells = buildCells(colors, view, {
    bald,
    longHair,
    ponytail,
    bulky,
    simple: detail === "simple",
  });

  return (
    <svg
      viewBox={`0 0 ${view === "bust" ? 16 : 18} ${view === "bust" ? 16 : 22}`}
      shapeRendering="crispEdges"
      role="img"
      aria-label={`character ${view} view`}
      className={cx(className, "opacity-95")}
    >
      {cells.map(([x, y, fill], index) => (
        <rect key={index} x={x} y={y} width={1} height={1} fill={fill} />
      ))}
    </svg>
  );
}

type Cell = [number, number, string];

function buildCells(
  c: { hair: string; skin: string; eyes: string; outfit: string; accent: string; line: string },
  view: ArtView,
  traits: { bald: boolean; longHair: boolean; ponytail: boolean; bulky: boolean; simple: boolean },
): Cell[] {
  const cells: Cell[] = [];
  const push = (x: number, y: number, fill: string) => cells.push([x, y, fill]);
  const { bald, longHair, ponytail, bulky, simple } = traits;

  if (view === "bust") {
    // hair cap
    if (!bald) for (let x = 4; x <= 11; x += 1) push(x, 0, c.hair);
    if (!bald) for (let x = 3; x <= 12; x += 1) push(x, 1, c.hair);
    for (let x = 3; x <= 12; x += 1) push(x, 2, bald ? c.skin : c.hair);
    if (bald) for (let x = 4; x <= 11; x += 1) push(x, 2, c.skin);
    // face rows 3-6
    for (let y = 3; y <= 6; y += 1) {
      for (let x = 4; x <= 11; x += 1) {
        if (longHair && (x === 4 || x === 11)) push(x, y, c.hair);
        else push(x, y, c.skin);
      }
    }
    if (!bald && !longHair) {
      push(4, 3, c.hair);
      push(11, 3, c.hair);
    }
    // eyes
    push(6, 4, c.eyes);
    push(9, 4, c.eyes);
    if (!simple) {
      push(5, 5, c.accent); // cheeks
      push(10, 5, c.accent);
      push(7, 6, c.line); // mouth
      push(8, 6, c.line);
    }
    // long hair falls past shoulders
    if (longHair) {
      for (let y = 7; y <= 11; y += 1) {
        push(3, y, c.hair);
        push(12, y, c.hair);
      }
    }
    if (ponytail) for (let y = 2; y <= 9; y += 1) push(13, y, c.hair);
    // neck + shoulders
    push(7, 7, c.skin);
    push(8, 7, c.skin);
    for (let x = 2; x <= 13; x += 1) push(x, 8, c.outfit);
    for (let y = 9; y <= 15; y += 1) {
      for (let x = 2; x <= 13; x += 1) {
        if (y >= 12 && (x < 4 || x > 11)) continue; // taper
        push(x, y, c.outfit);
      }
    }
    if (!simple) for (let x = 7; x <= 8; x += 1) push(x, 10, c.accent); // clasp
    return cells;
  }

  // ---- full body (front / side / back), 18 x 22 ----
  const headX = 5;
  const headW = view === "side" ? 7 : 8;
  const armLen = 5;

  if (view === "back") {
    for (let y = 1; y <= 7; y += 1)
      for (let x = headX; x < headX + headW; x += 1) push(x, y, bald ? c.skin : c.hair);
    if (!bald && (longHair || ponytail))
      for (let y = 8; y <= 13; y += 1)
        for (let x = headX + 2; x < headX + headW - 2; x += 1) push(x, y, c.hair);
  } else {
    for (let y = 1; y <= 2; y += 1)
      for (let x = headX; x < headX + headW; x += 1) push(x, y, bald ? c.skin : c.hair);
    for (let y = 3; y <= 6; y += 1)
      for (let x = headX; x < headX + headW; x += 1) {
        const edge = x === headX || x === headX + headW - 1;
        push(x, y, edge && !bald && longHair ? c.hair : c.skin);
      }
    if (view === "front") {
      push(headX + 2, 4, c.eyes);
      push(headX + headW - 3, 4, c.eyes);
      if (!simple) {
        push(headX + 4, 6, c.line);
        push(headX + 5, 6, c.line);
      }
    } else {
      // side profile: one eye near the front edge, nose bump
      push(headX + headW - 2, 4, c.eyes);
      push(headX + headW, 4, c.skin);
      if (!simple) push(headX + headW - 3, 6, c.line);
    }
  }

  // torso rows 8-13
  const inset = view === "side" ? 1 : 0;
  for (let y = 8; y <= 13; y += 1) {
    for (let x = headX + 1 + inset; x < headX + headW - 1 - inset; x += 1) push(x, y, c.outfit);
  }
  if (view === "front" && !simple) {
    for (let x = headX + 3; x <= headX + headW - 4; x += 1) push(x, 9, c.accent); // collar
    push(headX + 4, 12, c.line);
    push(headX + headW - 5, 12, c.line);
  }
  // arms
  const armY0 = 8;
  for (let y = armY0; y < armY0 + armLen; y += 1) {
    push(headX + (view === "side" ? 1 : 0), y, y === armY0 + armLen - 1 ? c.skin : c.outfit);
    push(headX + headW - 1, y, y === armY0 + armLen - 1 ? c.skin : c.outfit);
  }
  // legs rows 14-19 + feet 20
  for (let y = 14; y <= 19; y += 1) {
    for (let x = headX + 2; x <= headX + 4; x += 1) push(x, y, c.line);
    for (let x = headX + headW - 5; x <= headX + headW - 3; x += 1) push(x, y, c.line);
  }
  if (view === "side") {
    for (let y = 14; y <= 19; y += 1)
      for (let x = headX + 2; x <= headX + headW - 3; x += 1) push(x, y, c.line);
    for (let x = headX + 2; x <= headX + headW - 1; x += 1) push(x, 20, c.line);
  } else {
    for (let x = headX + 1; x <= headX + 4; x += 1) push(x, 20, c.line);
    for (let x = headX + headW - 5; x <= headX + headW - 2; x += 1) push(x, 20, c.line);
  }
  return cells;
}

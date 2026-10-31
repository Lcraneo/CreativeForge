import type { ScenePalette, ScenePlatform } from "../types";

export type PlatformMaterialFlavor =
  | "stone"
  | "snow"
  | "ice"
  | "moss"
  | "lava"
  | "metal"
  | "sand";

export interface PlatformMaterial {
  kind: ScenePlatform["kind"];
  flavor: PlatformMaterialFlavor;
  base: string;
  joint: string;
  highlight: string;
  cap: string;
}

export function containRect(
  intrinsicWidth: number,
  intrinsicHeight: number,
  viewportWidth: number,
  viewportHeight: number,
) {
  if (
    intrinsicWidth <= 0 ||
    intrinsicHeight <= 0 ||
    viewportWidth <= 0 ||
    viewportHeight <= 0
  ) {
    return { x: 0, y: 0, width: 0, height: 0, scale: 0 };
  }
  const scale = Math.min(viewportWidth / intrinsicWidth, viewportHeight / intrinsicHeight);
  const width = intrinsicWidth * scale;
  const height = intrinsicHeight * scale;
  return {
    x: (viewportWidth - width) / 2,
    y: (viewportHeight - height) / 2,
    width,
    height,
    scale,
  };
}

export function coverBackgroundRect(
  intrinsicWidth: number,
  intrinsicHeight: number,
  viewportWidth: number,
  viewportHeight: number,
) {
  if (
    intrinsicWidth <= 0 ||
    intrinsicHeight <= 0 ||
    viewportWidth <= 0 ||
    viewportHeight <= 0
  ) {
    return {
      width: 0,
      height: 0,
      cropX: 0,
      cropY: 0,
      cropWidth: 0,
      cropHeight: 0,
    };
  }
  const scale = Math.max(viewportWidth / intrinsicWidth, viewportHeight / intrinsicHeight);
  const cropWidth = viewportWidth / scale;
  const cropHeight = viewportHeight / scale;
  return {
    width: viewportWidth,
    height: viewportHeight,
    cropX: (intrinsicWidth - cropWidth) / 2,
    cropY: (intrinsicHeight - cropHeight) / 2,
    cropWidth,
    cropHeight,
  };
}

export function backgroundSequenceAt(progress: number, count: number) {
  if (count <= 0) return { from: 0, to: 0, mix: 0 };
  if (count === 1) return { from: 0, to: 0, mix: 0 };
  const clamped = Math.max(0, Math.min(1, progress));
  const position = clamped * (count - 1);
  const from = Math.min(count - 1, Math.floor(position));
  const to = Math.min(count - 1, from + 1);
  return { from, to, mix: position - from };
}

export function platformMaterialFor(
  kind: ScenePlatform["kind"],
  palette: ScenePalette,
  environment = "castle",
  features: readonly string[] = [],
): PlatformMaterial {
  const base = kind === "ground" ? palette.ground : palette.floating;
  let flavor: PlatformMaterialFlavor = "stone";
  if (features.includes("ice_theme") || environment === "snow") {
    flavor = kind === "ground" ? "snow" : "ice";
  } else if (environment === "forest") {
    flavor = "moss";
  } else if (environment === "lava") {
    flavor = "lava";
  } else if (environment === "desert") {
    flavor = "sand";
  } else if (environment === "city") {
    flavor = "metal";
  }
  return {
    kind,
    flavor,
    base,
    joint: mixHex(base, "#101722", 0.28),
    highlight: mixHex(base, palette.accent, 0.48),
    cap: mixHex(base, kind === "floating" ? "#ffffff" : "#e9f3ff", 0.34),
  };
}

export function createPlatformTexture(material: PlatformMaterial): HTMLCanvasElement {
  const width = 128;
  const height = 72;
  const canvas = document.createElement("canvas");
  canvas.width = width;
  canvas.height = height;
  const context = canvas.getContext("2d");
  if (!context) return canvas;

  context.fillStyle = material.base;
  context.fillRect(0, 0, width, height);
  context.lineCap = "round";

  if (material.flavor === "stone" || material.flavor === "snow") {
    drawBricks(context, material);
  } else if (material.flavor === "ice") {
    drawIce(context, material);
  } else if (material.flavor === "moss") {
    drawBricks(context, material);
    drawMoss(context, material);
  } else if (material.flavor === "lava") {
    drawLava(context, material);
  } else if (material.flavor === "metal") {
    drawMetal(context, material);
  } else {
    drawSand(context, material);
  }

  if (material.flavor === "snow") {
    context.fillStyle = "rgba(255,255,255,.52)";
    context.fillRect(0, 0, width, 9);
    for (let x = 8; x < width; x += 24) {
      context.beginPath();
      context.arc(x, 9, 3, 0, Math.PI);
      context.fill();
    }
  }
  return canvas;
}

function drawBricks(context: CanvasRenderingContext2D, material: PlatformMaterial) {
  context.strokeStyle = material.joint;
  context.globalAlpha = 0.55;
  context.lineWidth = 2;
  for (const y of [24, 49]) {
    context.beginPath();
    context.moveTo(0, y);
    context.lineTo(128, y);
    context.stroke();
  }
  for (const [x, y] of [
    [32, 0],
    [96, 0],
    [64, 24],
    [16, 49],
    [80, 49],
  ] as const) {
    context.beginPath();
    context.moveTo(x, y);
    context.lineTo(x, y + 24);
    context.stroke();
  }
  context.globalAlpha = 0.18;
  context.fillStyle = material.cap;
  for (const [x, y] of [
    [14, 13],
    [53, 36],
    [108, 61],
  ] as const) {
    context.fillRect(x, y, 8, 2);
  }
}

function drawIce(context: CanvasRenderingContext2D, material: PlatformMaterial) {
  context.globalAlpha = 0.35;
  context.strokeStyle = material.highlight;
  context.lineWidth = 3;
  for (const [x, y, dx, dy] of [
    [8, 58, 28, -20],
    [52, 50, 24, -15],
    [92, 62, 30, -22],
  ] as const) {
    context.beginPath();
    context.moveTo(x, y);
    context.lineTo(x + dx, y + dy);
    context.stroke();
  }
  context.fillStyle = "rgba(255,255,255,.48)";
  for (const [x, y, radius] of [
    [22, 18, 2],
    [74, 28, 1.5],
    [112, 14, 2],
  ] as const) {
    context.beginPath();
    context.arc(x, y, radius, 0, Math.PI * 2);
    context.fill();
  }
  context.globalAlpha = 1;
  context.fillStyle = material.cap;
  context.fillRect(0, 0, 128, 6);
}

function drawMoss(context: CanvasRenderingContext2D, material: PlatformMaterial) {
  context.globalAlpha = 0.62;
  context.fillStyle = material.highlight;
  for (const [x, y, radius] of [
    [15, 12, 4],
    [45, 8, 3],
    [88, 13, 5],
    [118, 9, 3],
  ] as const) {
    context.beginPath();
    context.arc(x, y, radius, 0, Math.PI * 2);
    context.fill();
  }
}

function drawLava(context: CanvasRenderingContext2D, material: PlatformMaterial) {
  context.globalAlpha = 0.68;
  context.strokeStyle = material.highlight;
  context.lineWidth = 3;
  for (const [x, y] of [
    [12, 20],
    [58, 48],
    [96, 18],
  ] as const) {
    context.beginPath();
    context.moveTo(x, y);
    context.lineTo(x + 14, y + 9);
    context.lineTo(x + 24, y + 5);
    context.lineTo(x + 34, y + 18);
    context.stroke();
  }
}

function drawMetal(context: CanvasRenderingContext2D, material: PlatformMaterial) {
  context.globalAlpha = 0.45;
  context.strokeStyle = material.joint;
  context.lineWidth = 2;
  for (const x of [32, 64, 96]) {
    context.beginPath();
    context.moveTo(x, 0);
    context.lineTo(x, 72);
    context.stroke();
  }
  context.fillStyle = material.highlight;
  for (const x of [16, 48, 80, 112]) {
    context.beginPath();
    context.arc(x, 16, 2.5, 0, Math.PI * 2);
    context.fill();
  }
}

function drawSand(context: CanvasRenderingContext2D, material: PlatformMaterial) {
  context.globalAlpha = 0.4;
  context.strokeStyle = material.highlight;
  context.lineWidth = 2;
  for (const y of [16, 38, 60]) {
    context.beginPath();
    context.moveTo(0, y);
    context.bezierCurveTo(32, y - 9, 64, y + 9, 128, y);
    context.stroke();
  }
}

function mixHex(left: string, right: string, amount: number): string {
  const a = parseHex(left);
  const b = parseHex(right);
  const channel = (index: number) =>
    Math.round(a[index] + (b[index] - a[index]) * Math.max(0, Math.min(1, amount)));
  return `#${channel(0).toString(16).padStart(2, "0")}${channel(1)
    .toString(16)
    .padStart(2, "0")}${channel(2).toString(16).padStart(2, "0")}`;
}

function parseHex(value: string): [number, number, number] {
  const match = /^#([0-9a-f]{6})$/i.exec(value);
  if (!match) return [96, 110, 126];
  const numeric = Number.parseInt(match[1], 16);
  return [(numeric >> 16) & 255, (numeric >> 8) & 255, numeric & 255];
}

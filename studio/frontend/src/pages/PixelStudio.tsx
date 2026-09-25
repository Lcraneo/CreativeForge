import { useMemo, useState } from "react";
import { Circle, Group, Layer, Line, Rect, Stage } from "react-konva";
import { useAssetLoader } from "../stores/assetStore";
import { Badge, Card, KV } from "../components/ui";

const GRID = 8;
const CELL = 26;

/** Deterministic pseudo-random from a seed string (no PIL needed). */
function seeded(seed: string) {
  let value = 0;
  for (const char of seed) value = (value * 31 + char.charCodeAt(0)) % 2147483647;
  return () => {
    value = (value * 48271) % 2147483647;
    return value / 2147483647;
  };
}

interface Pixel {
  color: string;
  noisy: string;
}

/** Builds an 8×8 sprite: "after" uses a 16-color semantic palette, "before"
 * is the muddy 64-color downscale — the PReCon before/after story. */
function buildSprite(seed: string): Pixel[][] {
  const random = seeded(seed);
  const palette = [
    "#09090b", "#f4d58d", "#38bdf8", "#b45309", "#dc2626", "#7f1d1d",
    "#0ea5e9", "#075985", "#16a34a", "#14532d", "#e4e4e7", "#71717a",
    "#a16207", "#fb923c", "#fde68a", "#3f3f46",
  ];
  const rows: Pixel[][] = [];
  for (let y = 0; y < GRID; y += 1) {
    const row: Pixel[] = [];
    for (let x = 0; x < GRID; x += 1) {
      // simple hooded-mage silhouette
      const inBody =
        y >= 1 && y <= 6 && x >= 2 && x <= 5 && !(y === 6 && (x === 2 || x === 5));
      const inStaff = x === 6 && y >= 2 && y <= 5;
      const color = inStaff
        ? palette[12]
        : inBody
          ? palette[y <= 2 ? 2 : y <= 4 ? 3 : 4]
          : palette[0];
      const jitter = (random() - 0.5) * 44;
      const noisy = shiftColor(color, jitter);
      row.push({ color, noisy });
    }
    rows.push(row);
  }
  return rows;
}

function shiftColor(hex: string, delta: number): string {
  const num = parseInt(hex.slice(1), 16);
  const channels = [(num >> 16) & 255, (num >> 8) & 255, num & 255].map((c) =>
    Math.max(0, Math.min(255, Math.round(c + delta))),
  );
  return `#${channels.map((c) => c.toString(16).padStart(2, "0")).join("")}`;
}

const PALETTE_DISPLAY = [
  "#09090b", "#f4d58d", "#38bdf8", "#b45309", "#dc2626", "#7f1d1d",
  "#0ea5e9", "#075985", "#16a34a", "#14532d", "#e4e4e7", "#71717a",
  "#a16207", "#fb923c", "#fde68a", "#3f3f46",
];

export default function PixelStudio() {
  const asset = useAssetLoader();
  const [showRaw, setShowRaw] = useState(false);
  const sprite = useMemo(() => buildSprite(asset?.id ?? "mage001"), [asset?.id]);

  return (
    <div className="mx-auto max-w-5xl px-6 py-6">
      <header className="mb-5 flex items-center justify-between">
        <div>
          <h1 className="pixel-title text-sm font-semibold text-zinc-200">Pixel Studio</h1>
          <p className="mt-1 text-xs text-zinc-500">
            PReCon 像素重建：AI 图片 → 网格推断 → 语义化 16 色调色板 → 轮廓修复
          </p>
        </div>
        <div className="flex gap-2">
          <button
            onClick={() => setShowRaw(false)}
            className={`rounded-lg px-3 py-1.5 text-xs font-medium ${
              !showRaw ? "bg-cyan-400 text-zinc-950" : "border border-zinc-700 text-zinc-400"
            }`}
          >
            After · PReCon
          </button>
          <button
            onClick={() => setShowRaw(true)}
            className={`rounded-lg px-3 py-1.5 text-xs font-medium ${
              showRaw ? "bg-cyan-400 text-zinc-950" : "border border-zinc-700 text-zinc-400"
            }`}
          >
            Before · AI 原图
          </button>
        </div>
      </header>

      <div className="grid grid-cols-[auto_1fr] gap-4">
        <Card title={showRaw ? "AI 生成原图（64 色，网格错位）" : "像素资产（16 色，8×8 网格）"}>
          <Stage width={GRID * CELL} height={GRID * CELL} className="rounded-lg">
            <Layer>
              {sprite.map((row, y) =>
                row.map((pixel, x) => (
                  <Rect
                    key={`${x}-${y}`}
                    x={x * CELL}
                    y={y * CELL}
                    width={CELL - (showRaw ? 0 : 2)}
                    height={CELL - (showRaw ? 0 : 2)}
                    fill={showRaw ? pixel.noisy : pixel.color}
                    cornerRadius={showRaw ? 0 : 2}
                  />
                )),
              )}
              {!showRaw && (
                <Group listening={false}>
                  {Array.from({ length: GRID + 1 }, (_, i) => (
                    <Line
                      key={`h${i}`}
                      points={[0, i * CELL - 1, GRID * CELL, i * CELL - 1]}
                      stroke="rgba(255,255,255,0.05)"
                      strokeWidth={1}
                    />
                  ))}
                  {Array.from({ length: GRID + 1 }, (_, i) => (
                    <Line
                      key={`v${i}`}
                      points={[i * CELL - 1, 0, i * CELL - 1, GRID * CELL]}
                      stroke="rgba(255,255,255,0.05)"
                      strokeWidth={1}
                    />
                  ))}
                </Group>
              )}
            </Layer>
          </Stage>
          <div className="mt-3 flex items-center gap-2">
            <Badge tone={showRaw ? "red" : "green"}>
              {showRaw ? "64 colors" : "16 colors"}
            </Badge>
            <Badge tone={showRaw ? "cyan" : "blue"}>
              grid {showRaw ? "off-grid" : "aligned"}
            </Badge>
          </div>
        </Card>

        <div className="space-y-4">
          <Card title="调色板 / Semantic Palette">
            <div className="grid grid-cols-8 gap-1.5">
              {PALETTE_DISPLAY.map((color) => (
                <div
                  key={color}
                  className="h-7 rounded border border-zinc-700"
                  style={{ background: color }}
                  title={color}
                />
              ))}
            </div>
            <div className="mt-3 space-y-1">
              <KV label="outline" value="#09090b" />
              <KV label="base" value="#38bdf8" />
              <KV label="shadow" value="#7f1d1d" />
              <KV label="highlight" value="#fde68a" />
            </div>
          </Card>

          <Card title="网格推断 / Grid Inference">
            <div className="flex items-center gap-4">
              <Stage width={88} height={88}>
                <Layer>
                  {Array.from({ length: 3 }, (_, i) =>
                    Array.from({ length: 3 }, (_, j) => (
                      <Circle
                        key={`${i}-${j}`}
                        x={16 + j * 28}
                        y={16 + i * 28}
                        radius={4}
                        fill={i === 1 && j === 1 ? "#38bdf8" : "#52525b"}
                      />
                    )),
                  )}
                </Layer>
              </Stage>
              <div className="flex-1 space-y-1">
                <KV label="grid size" value={asset?.pixel?.grid.size ?? 8} />
                <KV
                  label="confidence"
                  value={asset?.pixel?.grid.confidence ?? 0.9}
                />
                <KV
                  label="palette colors"
                  value={asset?.pixel?.palette.max_colors ?? 16}
                />
              </div>
            </div>
          </Card>
        </div>
      </div>
    </div>
  );
}

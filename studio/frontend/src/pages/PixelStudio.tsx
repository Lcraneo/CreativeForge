import { useEffect, useMemo, useState } from "react";
import { Circle, Group, Layer, Line, Rect, Stage } from "react-konva";
import { useAssetLoader } from "../stores/assetStore";
import {
  Badge,
  Button,
  Card,
  KV,
  PageHeader,
  ScoreBar,
  Segmented,
  Stat,
} from "../components/ui";
import { Icon } from "../components/icons";
import { toast } from "../stores/toastStore";
import { GRID, buildSprite, seedFromString } from "../lib/character";

const CELL = 26;

const FALLBACK_PALETTE = [
  "#07090d", "#4cc2ff", "#22d3ee", "#f4d58d", "#ff9d3d", "#a16207", "#dc2626", "#7f1d1d",
  "#0ea5e9", "#075985", "#16a34a", "#14532d", "#e4e4e7", "#a1a1aa", "#3a4658", "#1b2230",
];

export default function PixelStudio() {
  const asset = useAssetLoader();
  const [mode, setMode] = useState<"after" | "before">("after");
  const showRaw = mode === "before";

  const spec = asset?.character ?? { seed: seedFromString(asset?.id) };
  const palette = asset?.pixel?.palette.colors?.length
    ? asset.pixel.palette.colors.slice(0, 16)
    : FALLBACK_PALETTE;

  const sprite = useMemo(
    () => buildSprite(spec, palette),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [asset?.id, asset?.character?.seed, palette],
  );

  useEffect(() => {
    function onKey(event: KeyboardEvent) {
      if (event.key === "ArrowLeft") setMode("before");
      if (event.key === "ArrowRight") setMode("after");
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  const character = asset?.character;
  const chips = character
    ? [
        character.gender_label,
        character.class_label,
        character.element !== "none" ? character.element_label : null,
        character.hair_color_label && character.hair_style_label
          ? `${character.hair_color_label}${character.hair_style_label}`
          : null,
        character.build_label,
        character.expression_label,
      ].filter(Boolean)
    : [];

  return (
    <div className="mx-auto flex w-full max-w-[1440px] flex-col gap-5 px-4 py-5 md:px-6">
      <PageHeader
        overline="Pixel Studio"
        title="像素工作台"
        description="PReCon 像素重建：AI 原图 → 网格推断 → 语义 16 色调色板 → 轮廓修复"
        actions={
          <Segmented
            options={[
              { id: "after", label: "After · PReCon" },
              { id: "before", label: "Before · AI 原图" },
            ]}
            value={mode}
            onChange={setMode}
          />
        }
      />

      {chips.length > 0 && (
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-[11px] uppercase tracking-[0.08em] text-ink-4">Prompt spec</span>
          {chips.map((chip) => (
            <Badge key={String(chip)} tone="neutral">
              {chip}
            </Badge>
          ))}
          <span className="text-[11.5px] text-ink-3">
            {character?.height_cm}cm · {character?.weapon_label}
            {character?.accessory?.length ? ` · ${character.accessory.join("/")}` : ""}
          </span>
        </div>
      )}

      <div className="grid grid-cols-12 gap-5">
        <Card
          className="col-span-12 self-start lg:col-span-6"
          title={showRaw ? "AI 生成原图 · 64 色 · 网格错位" : "像素资产 · 16 色 · 8×8 网格"}
          icon="grid"
          iconClassName="text-precon"
          right={<Badge tone="neutral">26 px / 格 · ←→ 切换</Badge>}
        >
          <div className="flex justify-center rounded-[10px] border border-line-subtle bg-[#0a0e15] py-5">
            <Stage width={GRID * CELL} height={GRID * CELL} className="rounded-lg">
              <Layer>
                {sprite[showRaw ? "before" : "after"].map((row, y) =>
                  row.map((color, x) => {
                    if (!color) return null;
                    return (
                      <Rect
                        key={`${x}-${y}`}
                        x={x * CELL}
                        y={y * CELL}
                        width={CELL - (showRaw ? 0 : 2)}
                        height={CELL - (showRaw ? 0 : 2)}
                        fill={color}
                        cornerRadius={showRaw ? 0 : 3}
                      />
                    );
                  }),
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
          </div>
          <div className="mt-3 flex items-center gap-2">
            <Badge tone={showRaw ? "danger" : "success"}>{showRaw ? "64 colors" : "16 colors"}</Badge>
            <Badge tone={showRaw ? "warning" : "precon"}>
              grid {showRaw ? "off-grid" : "aligned"}
            </Badge>
            <Badge tone="neutral">conf {asset?.pixel?.grid.confidence ?? 0.92}</Badge>
          </div>
        </Card>

        <div className="col-span-12 flex flex-col gap-5 lg:col-span-6">
          <Card
            title="语义调色板 Semantic Palette"
            icon="grid"
            iconClassName="text-precon"
            right={<Badge tone="neutral">点击复制 hex</Badge>}
          >
            <div className="grid grid-cols-8 gap-1.5">
              {palette.map((color, index) => (
                <button
                  key={`${color}-${index}`}
                  title={color}
                  onClick={() => {
                    navigator.clipboard?.writeText(color).catch(() => undefined);
                    toast({ tone: "info", title: "已复制色值", description: color });
                  }}
                  className="h-7 rounded-sm border border-white/[.07] transition-transform duration-150 ease-standard hover:scale-110"
                  style={{ background: color }}
                />
              ))}
            </div>
            <div className="mt-3">
              <KV label="outline" value={character?.palette?.outline ?? "#07090D"} />
              <KV label="base / outfit" value={character?.palette?.base ?? "#4CC2FF"} />
              <KV label="hair" value={character?.hair_color_hex ?? "#1B2230"} />
              <KV label="skin / eyes" value={`${character?.skin_hex ?? "#E8B98A"} · ${character?.eyes_hex ?? "#4CC2FF"}`} />
            </div>
          </Card>

          <div className="grid grid-cols-12 gap-5">
            <Card className="col-span-12 md:col-span-6" title="网格推断" icon="search">
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
                          fill={i === 1 && j === 1 ? "#22d3ee" : "#3a4658"}
                        />
                      )),
                    )}
                  </Layer>
                </Stage>
                <div className="flex-1">
                  <KV label="grid size" value={`${asset?.pixel?.grid.size ?? 8} × ${asset?.pixel?.grid.size ?? 8}`} />
                  <KV label="confidence" value={asset?.pixel?.grid.confidence ?? 0.92} />
                  <KV label="colors" value={asset?.pixel?.palette.max_colors ?? 16} />
                  <KV label="seed" value={character?.seed ?? "—"} />
                </div>
              </div>
            </Card>

            <Card
              className="col-span-12 md:col-span-6"
              title="质量 Quality"
              icon="gauge"
              right={
                <Badge tone={(asset?.quality?.pixel?.overall ?? 0.9) >= 0.8 ? "success" : "danger"}>
                  {(asset?.quality?.pixel?.overall ?? 0.9) >= 0.8 ? "PASS" : "RETRY"}
                </Badge>
              }
            >
              <Stat
                label="pixel overall"
                value={`${Math.round((asset?.quality?.pixel?.overall ?? 0.9) * 100)}%`}
                tone="text-precon"
              />
              <div className="mt-3">
                <ScoreBar
                  label="阈值 0.80"
                  value={asset?.quality?.pixel?.overall ?? 0.9}
                  threshold={0.8}
                  tone="precon"
                />
              </div>
              <p className="mt-3 text-[11.5px] text-ink-3">
                轮廓修复 {asset?.pixel?.contour.repaired ? "已启用" : "未触发"} · 调色板收敛 256 →{" "}
                {asset?.pixel?.palette.max_colors ?? 16}
              </p>
            </Card>
          </div>

          <Card bodyClassName="p-4">
            <div className="flex items-center gap-2 text-[12.5px] text-ink-3">
              <Icon name="activity" className="h-4 w-4 text-primary" />
              快捷键：<kbd className="rounded-xs border border-line px-1.5 font-mono text-[10px]">←</kbd>
              查看原图 ·
              <kbd className="rounded-xs border border-line px-1.5 font-mono text-[10px]">→</kbd>
              查看 PReCon 结果 ·
              <Button
                variant="ghost"
                size="sm"
                onClick={() =>
                  toast({
                    tone: "info",
                    title: "PReCon 管线",
                    description: "网格推断 → 调色板重建 → 轮廓修复 → 一致性评估",
                  })
                }
              >
                了解管线
              </Button>
            </div>
          </Card>
        </div>
      </div>
    </div>
  );
}

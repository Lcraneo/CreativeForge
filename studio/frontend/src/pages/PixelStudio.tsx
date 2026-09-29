import { useEffect, useMemo, useRef, useState } from "react";
import { Circle, Group, Layer, Line, Rect, Stage } from "react-konva";
import type { KonvaEventObject } from "konva/lib/Node";
import { useAssetLoader, useAssetStore } from "../stores/assetStore";
import { api } from "../api/client";
import {
  Badge,
  Button,
  Card,
  KV,
  PageHeader,
  ScoreBar,
  Segmented,
  Stat,
  cx,
} from "../components/ui";
import { Icon } from "../components/icons";
import { toast } from "../stores/toastStore";
import { GRID, buildSprite, seedFromString } from "../lib/character";

const CELL = 26;

const FALLBACK_PALETTE = [
  "#07090d", "#4cc2ff", "#22d3ee", "#f4d58d", "#ff9d3d", "#a16207", "#dc2626", "#7f1d1d",
  "#0ea5e9", "#075985", "#16a34a", "#14532d", "#e4e4e7", "#a1a1aa", "#3a4658", "#1b2230",
];

type Tool = "pencil" | "spray" | "brush" | "eraser" | "picker";

const TOOLS: Array<{ id: Tool; label: string; icon: "pencil" | "spark" | "brush" | "eraser" | "search" }> = [
  { id: "pencil", label: "铅笔", icon: "pencil" },
  { id: "spray", label: "喷枪", icon: "spark" },
  { id: "brush", label: "毛笔", icon: "brush" },
  { id: "eraser", label: "橡皮", icon: "eraser" },
  { id: "picker", label: "拾色", icon: "search" },
];

type Cells = Array<Array<string | null>>;

export default function PixelStudio() {
  const asset = useAssetLoader();
  const setAsset = useAssetStore((state) => state.set);
  const [mode, setMode] = useState<"after" | "before">("after");
  const showRaw = mode === "before";

  // ── 编辑状态 ──────────────────────────────────────────────
  const [editing, setEditing] = useState(false);
  const [editCells, setEditCells] = useState<Cells | null>(null);
  const [tool, setTool] = useState<Tool>("pencil");
  const [brushSize, setBrushSize] = useState(1);
  const [activeColor, setActiveColor] = useState("#07090d");
  const [colorHistory, setColorHistory] = useState<string[]>([]);
  const [customPalette, setCustomPalette] = useState<string[] | null>(null);
  const [dirty, setDirty] = useState(false);
  const [saving, setSaving] = useState(false);
  const [exporting, setExporting] = useState(false);
  const drawingRef = useRef(false);
  const editedAtRef = useRef(0);

  const spec = asset?.character ?? { seed: seedFromString(asset?.id) };
  const palette = asset?.pixel?.palette.colors?.length
    ? asset.pixel.palette.colors.slice(0, 16)
    : FALLBACK_PALETTE;
  const realPixels = asset?.pixel?.pixels;

  const sprite = useMemo(
    () => buildSprite(spec, palette),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [asset?.id, asset?.character?.seed, palette],
  );

  // AI 原图模式：有真实重建矩阵用矩阵，否则退回合成 sprite
  const cells: Cells = showRaw
    ? sprite.before
    : (realPixels ?? sprite.after);
  const cellsSize = cells.length || GRID;
  const aiImage = asset?.image?.url ?? asset?.source?.ai_image?.url;
  const editedPng = asset?.pixel?.edited_png as string | undefined;
  const displayCells = editing && editCells ? editCells : cells;
  // 编辑画布自适应：画布区域约 560px 宽
  const CELL_D = Math.max(6, Math.min(CELL, Math.floor(560 / Math.max(1, cellsSize))));

  function enterEditing() {
    setEditCells(cells.map((row) => [...row]));
    if (!customPalette) setCustomPalette([...palette]);
    setEditing(true);
  }

  function exitEditing() {
    setEditing(false);
    setEditCells(null);
    setDirty(false);
  }

  function pushHistory(color: string) {
    setColorHistory((current) => [color, ...current.filter((c) => c !== color)].slice(0, 10));
  }

  function paintAt(baseX: number, baseY: number) {
    if (!editCells) return;
    const size = cellsSize;
    const next = editCells.map((row) => [...row]);

    const put = (x: number, y: number) => {
      if (x < 0 || y < 0 || x >= size || y >= size) return;
      next[y][x] = tool === "eraser" ? null : activeColor;
    };

    if (tool === "pencil") {
      const half = brushSize - 1;
      for (let dy = 0; dy <= half; dy += 1)
        for (let dx = 0; dx <= half; dx += 1) put(baseX + dx, baseY + dy);
    } else if (tool === "brush") {
      const radius = brushSize + 0.2;
      for (let dy = -radius; dy <= radius; dy += 1)
        for (let dx = -radius; dx <= radius; dx += 1)
          if (dx * dx + dy * dy <= radius * radius) put(baseX + dx, baseY + dy);
    } else if (tool === "spray") {
      const radius = brushSize * 2.2;
      const dots = brushSize * 8;
      for (let i = 0; i < dots; i += 1) {
        const angle = Math.random() * Math.PI * 2;
        const distance = Math.sqrt(Math.random()) * radius;
        put(Math.round(baseX + Math.cos(angle) * distance), Math.round(baseY + Math.sin(angle) * distance));
      }
    }
    setEditCells(next);
    setDirty(true);
    if (tool !== "eraser") pushHistory(activeColor);
  }

  function pickAt(x: number, y: number) {
    const color = editCells?.[y]?.[x];
    if (color) {
      setActiveColor(color);
      pushHistory(color);
      toast({ tone: "info", title: "已拾色", description: color });
    }
  }

  function onPointer(event: KonvaEventObject<MouseEvent | TouchEvent>, isMove = false) {
    if (!editing) return;
    const stage = event.target.getStage();
    if (!stage) return;
    if (isMove && !drawingRef.current) return;
    const position = stage.getPointerPosition();
    if (!position) return;
    const x = Math.floor(position.x / CELL_D);
    const y = Math.floor(position.y / CELL_D);
    if (x < 0 || y < 0 || x >= cellsSize || y >= cellsSize) return;
    if (tool === "picker") {
      if (!isMove) pickAt(x, y);
      return;
    }
    paintAt(x, y);
  }

  async function saveEdit() {
    if (!asset?.id || !editCells || saving) return;
    setSaving(true);
    try {
      const result = await api.savePixelEdit(asset.id, editCells, customPalette ?? palette);
      editedAtRef.current = Date.now();
      setDirty(false);
      toast({
        tone: "success",
        title: "像素编辑已保存",
        description: "已写回 CreativeAsset 并生成编辑版渲染图",
      });
      try {
        setAsset(await api.getAsset(asset.id));
      } catch {
        /* refresh is best-effort */
      }
      void result;
    } catch (cause) {
      toast({ tone: "danger", title: "保存失败", description: String(cause).slice(0, 160) });
    } finally {
      setSaving(false);
    }
  }

  async function reexport(engine: string) {
    if (!asset?.id || exporting) return;
    setExporting(true);
    try {
      const result = await api.exportAsset(asset.id, engine);
      toast({
        tone: "success",
        title: "已重新导出",
        description: `${result.files.length} 个文件 · ${(result.size_bytes / 1024).toFixed(0)} KB`,
      });
      window.location.href = result.download_url;
    } catch (cause) {
      toast({ tone: "danger", title: "导出失败", description: String(cause).slice(0, 160) });
    } finally {
      setExporting(false);
    }
  }

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

  const paletteInUse = customPalette ?? palette;

  return (
    <div className="mx-auto flex w-full max-w-[1440px] flex-col gap-5 px-4 py-5 md:px-6">
      <PageHeader
        overline="Pixel Studio"
        title="像素工作台"
        description={
          editing
            ? "编辑模式：画笔直接改像素，保存即写回 CreativeAsset，一键重新导出引擎资产"
            : "PReCon 像素重建：AI 原图 → 网格推断 → 语义 16 色调色板 → 轮廓修复"
        }
        actions={
          <div className="flex items-center gap-2">
            {!editing ? (
              <Button variant="ember" icon="pencil" onClick={enterEditing} disabled={!asset}>
                进入编辑
              </Button>
            ) : (
              <>
                <Button
                  variant="secondary"
                  icon="package"
                  loading={exporting}
                  onClick={() => reexport("cocos")}
                >
                  重新导出
                </Button>
                <Button
                  variant="ember"
                  icon="check"
                  loading={saving}
                  onClick={saveEdit}
                  disabled={!dirty}
                >
                  {dirty ? "保存修改*" : "已保存"}
                </Button>
                <Button variant="ghost" onClick={exitEditing}>
                  退出编辑
                </Button>
              </>
            )}
            {!editing && (
              <Segmented
                options={[
                  { id: "after", label: "After · PReCon" },
                  { id: "before", label: "Before · AI 原图" },
                ]}
                value={mode}
                onChange={setMode}
              />
            )}
          </div>
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
            {[
              character?.height_cm != null ? `${character.height_cm}cm` : null,
              character?.weapon_label,
              character?.accessory?.length ? character.accessory.join("/") : null,
            ]
              .filter(Boolean)
              .join(" · ")}
          </span>
        </div>
      )}

      <div className="grid grid-cols-12 gap-5">
        <Card
          className="col-span-12 self-start lg:col-span-6"
          title={
            editing
              ? "像素编辑画布"
              : showRaw
                ? (aiImage ? "AI 生成原图" : "AI 生成原图 · 64 色 · 网格错位")
                : "像素资产 · PReCon 重建"
          }
          icon="grid"
          iconClassName="text-precon"
          right={
            <Badge tone={editing ? (dirty ? "warning" : "success") : "neutral"}>
              {editing ? (dirty ? "未保存*" : "已同步") : `${cellsSize} px / 格 · ←→ 切换`}
            </Badge>
          }
        >
          {editing ? (
            <>
              <div className="mb-3 flex flex-wrap items-center gap-2">
                <Segmented
                  options={TOOLS.map((item) => ({ id: item.id, label: item.label }))}
                  value={tool}
                  onChange={(next) => setTool(next)}
                />
                <Segmented
                  options={[
                    { id: "1", label: "1px" },
                    { id: "2", label: "2px" },
                    { id: "3", label: "3px" },
                  ]}
                  value={String(brushSize)}
                  onChange={(next) => setBrushSize(Number(next))}
                />
                <span className="text-[11px] text-ink-4">
                  {tool === "picker" ? "点击画布取色" : "按住拖动绘制"}
                </span>
              </div>
              <div className="flex justify-center rounded-[10px] border border-line-subtle bg-white py-4">
                <Stage
                  width={cellsSize * CELL_D}
                  height={cellsSize * CELL_D}
                  onMouseDown={(event) => {
                    drawingRef.current = true;
                    onPointer(event);
                  }}
                  onMouseMove={(event) => onPointer(event, true)}
                  onMouseUp={() => {
                    drawingRef.current = false;
                  }}
                  onMouseLeave={() => {
                    drawingRef.current = false;
                  }}
                  onTouchStart={(event) => {
                    drawingRef.current = true;
                    onPointer(event);
                  }}
                  onTouchMove={(event) => onPointer(event, true)}
                  onTouchEnd={() => {
                    drawingRef.current = false;
                  }}
                  style={{ cursor: tool === "picker" ? "crosshair" : "cell" }}
                >
                  <Layer listening={false}>
                    {displayCells.map((row, y) =>
                      row.map((color, x) => (
                        <Rect
                          key={`${x}-${y}`}
                          x={x * CELL_D}
                          y={y * CELL_D}
                          width={CELL_D}
                          height={CELL_D}
                          fill={color ?? "#ffffff"}
                          stroke="rgba(26,24,20,0.06)"
                          strokeWidth={1}
                        />
                      )),
                    )}
                  </Layer>
                </Stage>
              </div>
              <div className="mt-3 flex flex-wrap items-center gap-2">
                <span
                  className="h-8 w-8 rounded-md border-2 border-line"
                  style={{ background: activeColor }}
                  title={activeColor}
                />
                <span className="font-mono text-[11.5px] text-ink-3">{activeColor}</span>
                <label className="ml-auto flex cursor-pointer items-center gap-1.5 text-[11.5px] text-primary">
                  <Icon name="spark" className="h-3.5 w-3.5" />
                  自定义颜色
                  <input
                    type="color"
                    value={activeColor}
                    onChange={(event) => {
                      setActiveColor(event.target.value);
                      pushHistory(event.target.value);
                    }}
                    className="h-0 w-0 opacity-0"
                  />
                </label>
              </div>
            </>
          ) : (
            <div className="flex justify-center rounded-[10px] border border-line-subtle bg-[#f1efe9] py-5">
              {showRaw && aiImage ? (
                <img src={aiImage} alt="AI 原图" className="max-h-[220px] rounded-lg" />
              ) : editedPng ? (
                <img
                  src={`${editedPng}?v=${editedAtRef.current}`}
                  alt="编辑版像素图"
                  className="max-h-[260px] rounded-lg bg-white p-1"
                />
              ) : (
                <Stage width={cellsSize * CELL} height={(cells[0]?.length ?? GRID) * CELL} className="rounded-lg">
                  <Layer>
                    {cells.map((row, y) =>
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
                        {Array.from({ length: cellsSize + 1 }, (_, i) => (
                          <Line
                            key={`h${i}`}
                            points={[0, i * CELL - 1, cellsSize * CELL, i * CELL - 1]}
                            stroke="rgba(26,24,20,0.08)"
                            strokeWidth={1}
                          />
                        ))}
                        {Array.from({ length: cellsSize + 1 }, (_, i) => (
                          <Line
                            key={`v${i}`}
                            points={[i * CELL - 1, 0, i * CELL - 1, cellsSize * CELL]}
                            stroke="rgba(26,24,20,0.08)"
                            strokeWidth={1}
                          />
                        ))}
                      </Group>
                    )}
                  </Layer>
                </Stage>
              )}
            </div>
          )}
          <div className="mt-3 flex items-center gap-2">
            <Badge tone={editing ? "precon" : showRaw ? "danger" : "success"}>
              {editing ? "编辑模式" : showRaw ? "原图" : `${asset?.pixel?.palette?.max_colors ?? 16} colors`}
            </Badge>
            {!editing && (
              <Badge tone={showRaw ? "warning" : "precon"}>
                {showRaw ? "原图" : asset?.pixel?.pixels ? "AI 重建" : "grid aligned"}
              </Badge>
            )}
            {editedPng && (
              <Badge tone="success">
                <Icon name="check" className="mr-1 inline h-3 w-3" />
                含编辑版渲染图
              </Badge>
            )}
            {!editing && <Badge tone="neutral">conf {asset?.pixel?.grid.confidence ?? 0.92}</Badge>}
          </div>
        </Card>

        <div className="col-span-12 flex flex-col gap-5 lg:col-span-6">
          <Card
            title={editing ? "调色板 · 点击选色" : "语义调色板 Semantic Palette"}
            icon="grid"
            iconClassName="text-precon"
            right={
              <Badge tone="neutral">
                {editing ? `${paletteInUse.length} 色 · 拾色器可用` : "点击复制 hex"}
              </Badge>
            }
          >
            <div className="grid grid-cols-8 gap-1.5">
              {paletteInUse.map((color, index) => (
                <button
                  key={`${color}-${index}`}
                  title={color}
                  onClick={() => {
                    if (editing) {
                      setActiveColor(color);
                      pushHistory(color);
                    } else {
                      navigator.clipboard?.writeText(color).catch(() => undefined);
                      toast({ tone: "info", title: "已复制色值", description: color });
                    }
                  }}
                  className={cx(
                    "h-7 rounded-sm border transition-transform duration-150 ease-standard hover:scale-110",
                    editing && activeColor === color
                      ? "border-2 border-primary"
                      : "border-ink/[.12]",
                  )}
                  style={{ background: color }}
                />
              ))}
              {editing && (
                <button
                  onClick={() => {
                    setCustomPalette((current) => [...(current ?? palette), activeColor].slice(0, 32));
                    toast({ tone: "info", title: "已加入自定义色板", description: activeColor });
                  }}
                  title="把当前颜色加入色板"
                  className="grid h-7 place-items-center rounded-sm border border-dashed border-line text-ink-4 hover:border-primary hover:text-primary"
                >
                  +
                </button>
              )}
            </div>

            {editing && colorHistory.length > 0 && (
              <div className="mt-3">
                <p className="mb-1.5 text-[11px] uppercase tracking-[0.08em] text-ink-4">颜色历史</p>
                <div className="flex flex-wrap gap-1.5">
                  {colorHistory.map((color, index) => (
                    <button
                      key={`${color}-${index}`}
                      title={color}
                      onClick={() => setActiveColor(color)}
                      className="h-6 w-6 rounded-sm border border-ink/[.15] hover:scale-110"
                      style={{ background: color }}
                    />
                  ))}
                </div>
              </div>
            )}

            <div className="mt-3">
              <KV label="outline" value={character?.palette?.outline ?? "#07090D"} />
              <KV label="base / outfit" value={character?.palette?.base ?? "#4CC2FF"} />
              <KV label="hair" value={character?.hair_color_hex ?? "#1B2230"} />
              <KV label="skin / eyes" value={`${character?.skin_hex ?? "#E8B98A"} · ${character?.eyes_hex ?? "#4CC2FF"}`} />
            </div>
          </Card>

          {!editing && (
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
                            fill={i === 1 && j === 1 ? "#0e8ea8" : "#b9b3a5"}
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
          )}

          <Card bodyClassName="p-4">
            {editing ? (
              <div className="flex items-center gap-2 text-[12.5px] text-ink-3">
                <Icon name="activity" className="h-4 w-4 text-primary" />
                编辑闭环：画笔修改 → 保存写回 CreativeAsset → 「重新导出」生成引擎 zip（资产完整性保持）。
                {dirty && <Badge tone="warning">有未保存修改</Badge>}
              </div>
            ) : (
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
            )}
          </Card>
        </div>
      </div>
    </div>
  );
}

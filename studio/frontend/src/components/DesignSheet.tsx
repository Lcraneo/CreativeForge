import { useEffect, useState } from "react";
import { CharacterArt } from "./CharacterArt";
import { artParams } from "../lib/art";
import { shade, type CharacterLike } from "../lib/character";

interface SheetProps {
  spec?: CharacterLike | null;
  palette?: string[];
  name?: string;
  assetId?: string;
  prompt?: string;
  imageUrl?: string;
}

const INK = "#2f3b52";
const DIM = "#2f6fd0";
const PAPER = "#f4f0e9";

const FRONT = { x: 150, y: 108, w: 372, h: 725 };
const SIDE = { x: 618, y: 108, w: 372, h: 725 };
const TOP = { x: 1058, y: 176, w: 330, h: 330 };
const BUST = { x: 1400, y: 120, w: 250, h: 307 };

/** px -> sheet coordinate inside a viewport */
function makeProject(p: { x: number; y: number; w: number; h: number }, minX = 0, span = 400) {
  const s = p.w / span;
  return {
    s,
    x: (lx: number) => p.x + (lx - minX) * s,
    y: (ly: number) => p.y + ly * s,
  };
}

function HalfDim({
  y,
  xEdge,
  dir = -1,
  label,
}: {
  y: number;
  xEdge: number;
  dir?: -1 | 1;
  label: string;
}) {
  const xEnd = xEdge + dir * 36;
  const arrow =
    dir === -1
      ? `M ${xEdge - 7} ${y - 4} L ${xEdge} ${y} L ${xEdge - 7} ${y + 4} Z`
      : `M ${xEdge + 7} ${y - 4} L ${xEdge} ${y} L ${xEdge + 7} ${y + 4} Z`;
  return (
    <g stroke={DIM} fill={DIM} fontFamily="JetBrains Mono, Consolas, monospace" fontSize="11">
      <line x1={xEdge} y1={y} x2={xEnd} y2={y} />
      <line x1={xEdge} y1={y - 4} x2={xEdge} y2={y + 4} />
      <path d={arrow} strokeWidth="0.6" />
      <text x={xEnd + dir * 5} y={y + 4} textAnchor={dir === -1 ? "end" : "start"} stroke="none">
        {label}
      </text>
    </g>
  );
}

function DimV({ x, y1, y2, label }: { x: number; y1: number; y2: number; label: string }) {
  return (
    <g stroke={DIM} strokeWidth="1" fill={DIM} fontFamily="JetBrains Mono, Consolas, monospace" fontSize="11">
      <line x1={x} y1={y1} x2={x} y2={y2} />
      <line x1={x - 5} y1={y1} x2={x + 5} y2={y1} />
      <line x1={x - 5} y1={y2} x2={x + 5} y2={y2} />
      <path d={`M ${x - 4} ${y1 + 7} L ${x} ${y1} L ${x + 4} ${y1 + 7} Z`} strokeWidth="0.6" />
      <path d={`M ${x - 4} ${y2 - 7} L ${x} ${y2} L ${x + 4} ${y2 - 7} Z`} strokeWidth="0.6" />
      <text x={x - 7} y={(y1 + y2) / 2} textAnchor="end" stroke="none" dominantBaseline="middle">
        {label}
      </text>
    </g>
  );
}

function DimH({ x1, x2, y, label }: { x1: number; x2: number; y: number; label: string }) {
  return (
    <g stroke={DIM} strokeWidth="1" fill={DIM} fontFamily="JetBrains Mono, Consolas, monospace" fontSize="11">
      <line x1={x1} y1={y} x2={x2} y2={y} />
      <line x1={x1} y1={y - 5} x2={x1} y2={y + 5} />
      <line x1={x2} y1={y - 5} x2={x2} y2={y + 5} />
      <path d={`M ${x1 + 7} ${y - 4} L ${x1} ${y} L ${x1 + 7} ${y + 4} Z`} strokeWidth="0.6" />
      <path d={`M ${x2 - 7} ${y - 4} L ${x2} ${y} L ${x2 - 7} ${y + 4} Z`} strokeWidth="0.6" />
      <text x={(x1 + x2) / 2} y={y - 7} textAnchor="middle" stroke="none">
        {label}
      </text>
    </g>
  );
}

function Callout({ x, y, tx, ty, index }: { x: number; y: number; tx: number; ty: number; index: number }) {
  return (
    <g fontFamily="Inter, 'PingFang SC', sans-serif" fontSize="12">
      <line x1={x} y1={y} x2={tx} y2={ty} stroke={INK} strokeWidth="0.9" strokeDasharray="3 2" />
      <circle cx={tx} cy={ty} r="10" fill="#ffffff" stroke={INK} strokeWidth="1.2" />
      <text x={tx} y={ty + 4} textAnchor="middle" fill={INK} fontWeight="600">
        {index}
      </text>
    </g>
  );
}

function ViewLabel({ x, y, zh, en }: { x: number; y: number; zh: string; en: string }) {
  return (
    <g textAnchor="middle" fontFamily="Inter, 'PingFang SC', sans-serif">
      <text x={x} y={y} fill={INK} fontSize="15" fontWeight="700">
        {zh}
      </text>
      <text x={x} y={y + 17} fill={shade(INK, 0.35)} fontSize="11" letterSpacing="1.5">
        {en}
      </text>
    </g>
  );
}

export function DesignSheet({ spec, palette, name, assetId, prompt, imageUrl }: SheetProps) {
  const [failedViews, setFailedViews] = useState<Record<string, boolean>>({});
  useEffect(() => setFailedViews({}), [imageUrl, assetId]);

  // No external concept art -> use the deterministic 2D renderer's three
  // orthographic views so the sheet stays one consistent style.
  const generated = !imageUrl && !!assetId;
  const viewUrl = (view: string) =>
    `/api/assets/${encodeURIComponent(assetId as string)}/image.png?view=${view}&size=512`;
  const rasterSrc = (view: string) =>
    imageUrl && view === "front" ? imageUrl : viewUrl(view);
  const useRaster = (view: string) =>
    (view === "front" && !!imageUrl) || (generated && !failedViews[view]);
  const failView = (view: string) =>
    setFailedViews((prev) => ({ ...prev, [view]: true }));

  const p = artParams(spec, palette);
  const g = p.geometry;
  const front = makeProject(FRONT, -30, 460);
  const side = makeProject(SIDE, -30, 460);
  const top = makeProject(TOP, 0, 400);
  const today = new Date().toISOString().slice(0, 10);

  // real-world design measures (cm) derived from height + build + gender
  const heightCm = (spec?.height_cm as number) ?? 170;
  const female = spec?.gender === "female";
  const build = spec?.build ?? "slim";
  const buildAdj = build === "muscular" ? 4 : build === "petite" ? -3 : 0;
  const mShoulder = Math.round(heightCm * (female ? 0.225 : 0.245)) + buildAdj;
  const mWaist = Math.round(heightCm * (female ? 0.145 : 0.165)) + (build === "muscular" ? 4 : 0);
  const mHip = Math.round(heightCm * (female ? 0.19 : 0.175)) + buildAdj;
  const mHead = Math.round(heightCm / 7.6);
  const mLeg = Math.round(heightCm * 0.47);
  const mHeadDepth = Math.round(mHead * 0.8);
  const mChestDepth = Math.round(mShoulder * 0.44);
  const mHemDepth = Math.round(mHip * 0.95);
  const mHeadWidth = Math.round(mHead * 0.68);

  const swatches = palette?.length
    ? palette.slice(0, 16)
    : [
        p.palette.line, p.palette.hairShadow, p.palette.hair, p.palette.hairLight,
        p.palette.skinShadow, p.palette.skin, p.palette.skinLight, p.palette.white,
        p.palette.baseShadow, p.palette.base, p.palette.highlight, p.palette.accentSoft,
        p.palette.accent, p.palette.metalDark, p.palette.metal, p.palette.eyes,
      ];

  const rows: Array<[string, string]> = [
    ["名称 NAME", String(name ?? "—")],
    ["编号 ID", String(assetId ?? "—")],
    ["性别 GENDER", String((spec as { gender_label?: string })?.gender_label ?? "—")],
    ["职业 CLASS", String((spec as { class_label?: string })?.class_label ?? "—")],
    ["元素 ELEMENT", String((spec as { element_label?: string })?.element_label ?? "—")],
    ["身高 HEIGHT", `${(spec?.height_cm as number) ?? "—"} cm`],
    ["肩宽 / 腰围", `${mShoulder} / ${mWaist} cm`],
    ["臀围 / 腿长", `${mHip} / ${mLeg} cm`],
    ["体型 BUILD", String((spec as { build_label?: string })?.build_label ?? "—")],
    [
      "发型 HAIR",
      `${(spec as { hair_color_label?: string })?.hair_color_label ?? ""}${(spec as { hair_style_label?: string })?.hair_style_label ?? ""}`,
    ],
    ["神态 FACE", String((spec as { expression_label?: string })?.expression_label ?? "—")],
    ["武器 WEAPON", String((spec as { weapon_label?: string })?.weapon_label ?? "—")],
    [
      "配饰 ACCESSORY",
      spec?.accessory?.length ? spec.accessory.join(" / ") : "无",
    ],
  ];

  const calloutItems = [
    `发型与发饰：${(spec as { hair_color_label?: string })?.hair_color_label ?? ""}${(spec as { hair_style_label?: string })?.hair_style_label ?? ""}`,
    `五官与妆容：${(spec as { expression_label?: string })?.expression_label ?? "—"} · ${(spec as { eyes_label?: string })?.eyes_label ?? ""}瞳`,
    `服装结构：${p.garment === "robe" ? "法袍 · 腰封 · 领饰" : p.garment === "armor" ? "胸甲 · 护肩 · 甲裙" : p.garment === "hood" ? "兜帽斗篷 · 束带" : p.garment === "tunic" ? "束腰上衣 · 腰带" : "短外套 · 吊带 · 百褶裙"}`,
    `武器：${(spec as { weapon_label?: string })?.weapon_label ?? "无"}`,
    "下装与鞋履：百褶裙 · 长袜 · 厚底鞋",
  ];

  return (
    <svg
      viewBox="0 0 1680 1000"
      width="100%"
      style={{ background: PAPER, display: "block" }}
      fontFamily="Inter, 'PingFang SC', 'Microsoft YaHei', sans-serif"
    >
      {/* drawing frame */}
      <rect x="10" y="10" width="1660" height="980" fill="none" stroke={INK} strokeWidth="2" />
      <rect x="26" y="26" width="1628" height="948" fill="none" stroke={INK} strokeWidth="0.8" />
      {/* zone letters */}
      {["A", "B", "C", "D"].map((zone, index) => (
        <text key={zone} x={850} y={22 + index * 0} fill={INK} fontSize="10" opacity="0" />
      ))}

      {/* header */}
      <text x="48" y="64" fill={INK} fontSize="20" fontWeight="800" letterSpacing="0.5">
        CHARACTER DESIGN SHEET · 角色设计三视图
      </text>
      <text x="48" y="86" fill={shade(INK, 0.3)} fontSize="12">
        {String((spec as { summary?: string })?.summary ?? "CreativeForge 生成角色")}　|　{String(prompt ?? "").slice(0, 64)}
      </text>
      <line x1="48" y1="98" x2="1632" y2="98" stroke={INK} strokeWidth="1" />

      {/* ground line */}
      <line x1={FRONT.x - 30} y1={front.y(g.groundY)} x2={FRONT.x + FRONT.w + 20} y2={front.y(g.groundY)} stroke={INK} strokeWidth="1.4" />
      <line x1={SIDE.x - 30} y1={side.y(g.groundY)} x2={SIDE.x + SIDE.w + 20} y2={side.y(g.groundY)} stroke={INK} strokeWidth="1.4" />

      {/* front view */}
      <g>
        <svg x={FRONT.x} y={FRONT.y} width={FRONT.w} height={FRONT.h} viewBox="-30 0 460 780">
          {useRaster("front") ? (
            <image
              href={rasterSrc("front")}
              x="0"
              y="0"
              width="400"
              height="780"
              preserveAspectRatio="xMidYMid slice"
              onError={() => failView("front")}
            />
          ) : (
            <CharacterArt spec={spec} palette={palette} view="front" />
          )}
        </svg>
        {/* center line */}
        <line
          x1={front.x(g.cx)}
          y1={FRONT.y - 8}
          x2={front.x(g.cx)}
          y2={FRONT.y + FRONT.h + 6}
          stroke="#94a3b8"
          strokeWidth="0.8"
          strokeDasharray="12 4 3 4"
        />
        <DimV x={FRONT.x - 44} y1={front.y(g.topY)} y2={front.y(g.groundY)} label={`${spec?.height_cm ?? "—"} cm`} />
        <DimV x={FRONT.x - 16} y1={front.y(g.topY)} y2={front.y(g.chinY)} label={`头高 ${mHead}`} />
        <HalfDim y={front.y(g.shoulderY - 14)} xEdge={front.x(g.cx - g.shoulderHalf)} dir={-1} label={`肩 ${mShoulder}`} />
        <HalfDim y={front.y(g.shoulderY - 14)} xEdge={front.x(g.cx + g.shoulderHalf)} dir={1} label={String(mShoulder)} />
        <HalfDim y={front.y(g.waistY)} xEdge={front.x(g.cx - g.waistHalf)} dir={-1} label={`腰 ${mWaist}`} />
        <HalfDim y={front.y(g.hipY + 18)} xEdge={front.x(g.cx + g.hipHalf)} dir={1} label={`臀 ${mHip}`} />
        <DimV x={FRONT.x + FRONT.w + 26} y1={front.y(g.hipY)} y2={front.y(g.groundY)} label={`腿长 ${mLeg}`} />
        <Callout x={front.x(g.cx + g.headRx + 6)} y={front.y(g.headCy - 12)} tx={FRONT.x - 6} ty={FRONT.y + 26} index={1} />
        <Callout x={front.x(g.cx + 10)} y={front.y(g.headCy + g.headRy * 0.6)} tx={FRONT.x + FRONT.w - 4} ty={FRONT.y + 66} index={2} />
        <Callout x={front.x(g.cx + g.bustR)} y={front.y(g.bustY)} tx={FRONT.x + FRONT.w - 4} ty={front.y(g.bustY)} index={3} />
        <Callout x={front.x(g.cx + g.shoulderHalf + 26)} y={front.y(g.waistY + 30)} tx={FRONT.x + FRONT.w - 4} ty={front.y(g.waistY + 60)} index={4} />
        <Callout x={front.x(g.cx + 14)} y={front.y(g.groundY - 12)} tx={FRONT.x + FRONT.w - 4} ty={front.y(g.groundY - 6)} index={5} />
        <ViewLabel x={front.x(g.cx)} y={FRONT.y + FRONT.h + 34} zh={useRaster("front") ? "正视图 · 2D 原画" : "正视图"} en="FRONT VIEW" />
      </g>

      {/* side view */}
      <g>
        <svg x={SIDE.x} y={SIDE.y} width={SIDE.w} height={SIDE.h} viewBox="-30 0 460 780">
          {useRaster("side") ? (
            <image
              href={rasterSrc("side")}
              x="0"
              y="0"
              width="400"
              height="780"
              preserveAspectRatio="xMidYMid slice"
              onError={() => failView("side")}
            />
          ) : (
            <CharacterArt spec={spec} palette={palette} view="side" />
          )}
        </svg>
        <HalfDim y={side.y(g.headCy - 10)} xEdge={side.x(g.cx - g.headRx - 6)} dir={-1} label={`头深 ${mHeadDepth}`} />
        <HalfDim y={side.y(g.bustY)} xEdge={side.x(g.cx - g.bustR - 18)} dir={-1} label={`厚 ${mChestDepth}`} />
        <HalfDim y={side.y(g.hipY + 60)} xEdge={side.x(g.cx + g.waistHalf + 30)} dir={1} label={`摆 ${mHemDepth}`} />
        <Callout x={side.x(g.cx - g.headRx - 24)} y={side.y(g.headCy + 30)} tx={SIDE.x + SIDE.w - 2} ty={SIDE.y + 40} index={1} />
        <Callout x={side.x(g.cx + g.bustR + 4)} y={side.y(g.bustY + 6)} tx={SIDE.x + SIDE.w - 2} ty={side.y(g.bustY + 40)} index={3} />
        <ViewLabel x={side.x(g.cx)} y={SIDE.y + SIDE.h + 34} zh="左侧面图" en="LEFT VIEW" />
      </g>

      {/* top view */}
      <g>
        <svg x={TOP.x} y={TOP.y} width={TOP.w} height={TOP.h} viewBox="0 0 400 400">
          {useRaster("back") ? (
            <image
              href={rasterSrc("back")}
              x="0"
              y="0"
              width="400"
              height="400"
              preserveAspectRatio="xMidYMid meet"
              onError={() => failView("back")}
            />
          ) : (
            <CharacterArt spec={spec} palette={palette} view="top" />
          )}
        </svg>
        <DimH x1={top.x(200 - g.shoulderHalf * 1.3)} x2={top.x(200 + g.shoulderHalf * 1.3)} y={top.y(330)} label={`肩宽 ${mShoulder}`} />
        <DimH x1={top.x(200 - g.headRx * 1.5)} x2={top.x(200 + g.headRx * 1.5)} y={top.y(150)} label={`头宽 ${mHeadWidth}`} />
        <DimV x={TOP.x + TOP.w + 22} y1={top.y(196 - g.headRx * 1.12)} y2={top.y(226 + g.shoulderHalf * 1.3 * 0.4)} label={`总深 ${mChestDepth + mHeadDepth}`} />
        <Callout x={top.x(262)} y={top.y(120)} tx={TOP.x + TOP.w - 4} ty={TOP.y + 20} index={1} />
        <Callout x={top.x(200)} y={top.y(196)} tx={TOP.x + TOP.w - 4} ty={TOP.y + 150} index={3} />
        <ViewLabel x={top.x(200)} y={TOP.y + TOP.h + 34} zh="后视图" en="BACK VIEW" />
      </g>

      {/* portrait detail */}
      <g>
        <rect x={BUST.x - 14} y={BUST.y - 16} width={BUST.w + 28} height={BUST.h + 32} fill="#faf7f1" stroke={INK} strokeWidth="1" />
        <svg x={BUST.x} y={BUST.y} width={BUST.w} height={BUST.h} viewBox="104 40 192 236">
          <CharacterArt spec={spec} palette={palette} view="bust" detail="full" background={false} />
        </svg>
        <text x={BUST.x + BUST.w / 2} y={BUST.y - 26} textAnchor="middle" fill={INK} fontSize="12" fontWeight="600">
          面部细节 DETAIL
        </text>
        <Callout x={BUST.x + BUST.w * 0.62} y={BUST.y + BUST.h * 0.42} tx={BUST.x + BUST.w + 16} ty={BUST.y + 30} index={2} />
      </g>

      {/* legend / key details */}
      <g>
        <text x="48" y="330" fill={INK} fontSize="12" fontWeight="700">
          关键细节 KEY DETAILS
        </text>
        {calloutItems.map((item, index) => (
          <text key={index} x="48" y={352 + index * 20} fill={shade(INK, 0.2)} fontSize="11.5">
            {`${index + 1}  ${item}`}
          </text>
        ))}
      </g>

      {/* spec table */}
      <g>
        <text x="48" y="486" fill={INK} fontSize="12" fontWeight="700">
          角色规格 SPECIFICATION
        </text>
        <rect x="48" y="496" width="360" height={rows.length * 22 + 8} fill="#faf7f1" stroke={INK} strokeWidth="0.9" />
        {rows.map(([key, value], index) => (
          <g key={key}>
            <line x1="48" y1={496 + 22 * (index + 1)} x2="408" y2={496 + 22 * (index + 1)} stroke={INK} strokeWidth="0.35" opacity="0.5" />
            <text x="58" y={513 + index * 22} fill={shade(INK, 0.3)} fontSize="10.5" fontWeight="600">
              {key}
            </text>
            <text x="398" y={513 + index * 22} textAnchor="end" fill={INK} fontSize="11">
              {value || "—"}
            </text>
          </g>
        ))}
      </g>

      {/* palette */}
      <g>
        <text x="48" y={520 + rows.length * 22} fill={INK} fontSize="12" fontWeight="700">
          配色板 COLOR PALETTE
        </text>
        {swatches.map((color, index) => (
          <g key={`${color}-${index}`}>
            <rect
              x={48 + (index % 8) * 47}
              y={532 + rows.length * 22 + Math.floor(index / 8) * 58}
              width="42"
              height="34"
              rx="4"
              fill={color}
              stroke={INK}
              strokeWidth="0.7"
            />
            <text
              x={48 + (index % 8) * 47 + 21}
              y={532 + rows.length * 22 + Math.floor(index / 8) * 58 + 48}
              textAnchor="middle"
              fill={shade(INK, 0.3)}
              fontSize="8.5"
              fontFamily="JetBrains Mono, Consolas, monospace"
            >
              {color.toUpperCase()}
            </text>
          </g>
        ))}
      </g>

      {/* scale bar */}
      <g>
        <text x="48" y={660 + rows.length * 22} fill={INK} fontSize="10" fontWeight="600">
          比例尺 SCALE
        </text>
        {Array.from({ length: 6 }, (_, index) => (
          <g key={index}>
            <rect
              x={48 + index * 36}
              y={670 + rows.length * 22}
              width="36"
              height="9"
              fill={index % 2 ? "#ffffff" : INK}
              stroke={INK}
              strokeWidth="0.6"
            />
          </g>
        ))}
        <text x={48} y={694 + rows.length * 22} fill={shade(INK, 0.3)} fontSize="9.5" fontFamily="JetBrains Mono, monospace">
          0        10       20       30 cm
        </text>
      </g>

      {/* title block */}
      <g>
        <rect x="1120" y="836" width="512" height="118" fill="#faf7f1" stroke={INK} strokeWidth="1.4" />
        <line x1="1120" y1="872" x2="1632" y2="872" stroke={INK} strokeWidth="0.8" />
        <line x1="1120" y1="908" x2="1632" y2="908" stroke={INK} strokeWidth="0.8" />
        <line x1="1376" y1="836" x2="1376" y2="954" stroke={INK} strokeWidth="0.8" />
        <text x="1132" y="858" fill={shade(INK, 0.3)} fontSize="10" fontWeight="600">PROJECT 项目</text>
        <text x="1400" y="858" fill={shade(INK, 0.3)} fontSize="10" fontWeight="600">DRAWING 图名</text>
        <text x="1132" y="893" fill={INK} fontSize="12" fontWeight="700">CreativeForge AI</text>
        <text x="1400" y="893" fill={INK} fontSize="12" fontWeight="700">{String(name ?? "Character")} · 角色设计三视图</text>
        <text x="1132" y="930" fill={shade(INK, 0.3)} fontSize="10" fontWeight="600">DRAWING NO. 图号</text>
        <text x="1400" y="930" fill={shade(INK, 0.3)} fontSize="10" fontWeight="600">SCALE / UNIT 比例 / 单位</text>
        <text x="1132" y="948" fill={INK} fontSize="11" fontFamily="JetBrains Mono, monospace">{String(assetId ?? "—")}</text>
        <text x="1400" y="948" fill={INK} fontSize="11" fontFamily="JetBrains Mono, monospace">1:10 · cm</text>
        <text x="1650" y="862" fill={shade(INK, 0.3)} fontSize="9.5" textAnchor="end">DATE {today}</text>
        <text x="1650" y="882" fill={shade(INK, 0.3)} fontSize="9.5" textAnchor="end">REV v1.0</text>
        <text x="1650" y="924" fill={shade(INK, 0.3)} fontSize="9.5" textAnchor="end">DESIGN 生成管线</text>
        <text x="1650" y="946" fill={shade(INK, 0.3)} fontSize="9.5" textAnchor="end">CHECK QA PASS</text>
      </g>

      {/* view title */}
      <text x="1632" y="70" textAnchor="end" fill={shade(INK, 0.35)} fontSize="11" fontFamily="JetBrains Mono, monospace">
        SHEET 1 / 1　·　FRONT / SIDE / TOP
      </text>
    </svg>
  );
}

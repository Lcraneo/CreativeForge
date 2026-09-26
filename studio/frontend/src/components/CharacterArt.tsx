import { useId, type ReactNode } from "react";
import { artParams, type ArtParams } from "../lib/art";
import { shade, type CharacterLike } from "../lib/character";

export type CharacterView = "front" | "side" | "top" | "bust";

interface Props {
  spec?: CharacterLike | null;
  palette?: string[];
  view?: CharacterView;
  className?: string;
  detail?: "full" | "simple";
  background?: boolean;
}

/**
 * Vector character illustration (soft anime style): smooth line art,
 * layered hair strands, shaded clothing, face highlights and weapon details.
 * Driven entirely by the CharacterSpec so every prompt renders a person
 * that matches its description.
 */
export function CharacterArt({
  spec,
  palette,
  view = "front",
  className,
  detail = "full",
  background = false,
}: Props) {
  const rawId = useId().replace(/:/g, "");
  const p = artParams(spec, palette);
  const id = `art-${rawId}`;

  const viewBox =
    view === "top" ? "0 0 400 400" : view === "bust" ? "104 40 192 236" : "0 0 400 780";

  return (
    <svg viewBox={viewBox} className={className} role="img" aria-label="角色设计图">
      <defs>
        <linearGradient id={`${id}-hair`} x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" stopColor={p.palette.hairLight} />
          <stop offset="0.45" stopColor={p.palette.hair} />
          <stop offset="1" stopColor={p.palette.hairShadow} />
        </linearGradient>
        <linearGradient id={`${id}-hair-back`} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor={p.palette.hair} />
          <stop offset="1" stopColor={shade(p.palette.hair, -0.34)} />
        </linearGradient>
        <linearGradient id={`${id}-skin`} x1="0.2" y1="0" x2="0.9" y2="1">
          <stop offset="0" stopColor={p.palette.skinLight} />
          <stop offset="0.6" stopColor={p.palette.skin} />
          <stop offset="1" stopColor={p.palette.skinShadow} />
        </linearGradient>
        <linearGradient id={`${id}-cloth`} x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" stopColor={shade(p.palette.base, 0.16)} />
          <stop offset="0.55" stopColor={p.palette.base} />
          <stop offset="1" stopColor={p.palette.baseShadow} />
        </linearGradient>
        <linearGradient id={`${id}-cloth-dark`} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor={shade(p.palette.baseShadow, -0.04)} />
          <stop offset="1" stopColor={shade(p.palette.baseShadow, -0.24)} />
        </linearGradient>
        <linearGradient id={`${id}-metal`} x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" stopColor={shade(p.palette.metal, 0.32)} />
          <stop offset="0.5" stopColor={p.palette.metal} />
          <stop offset="1" stopColor={p.palette.metalDark} />
        </linearGradient>
        <radialGradient id={`${id}-iris`} cx="0.5" cy="0.42" r="0.65">
          <stop offset="0" stopColor={shade(p.palette.eyes, 0.4)} />
          <stop offset="0.55" stopColor={p.palette.eyes} />
          <stop offset="1" stopColor={shade(p.palette.eyes, -0.42)} />
        </radialGradient>
        <radialGradient id={`${id}-blush`} cx="0.5" cy="0.5" r="0.5">
          <stop offset="0" stopColor="#e58a8a" stopOpacity="0.5" />
          <stop offset="1" stopColor="#e58a8a" stopOpacity="0" />
        </radialGradient>
        <filter id={`${id}-soft`} x="-30%" y="-30%" width="160%" height="160%">
          <feGaussianBlur stdDeviation="3" />
        </filter>
      </defs>

      {background && <rect x="-20" y="-20" width="440" height="820" fill="#efe9e1" />}

      {view === "top" ? (
        <TopView p={p} id={id} />
      ) : view === "side" ? (
        <SideView p={p} id={id} detail={detail} />
      ) : (
        <FrontView p={p} id={id} detail={detail} />
      )}
    </svg>
  );
}

/* ------------------------------------------------------------------ */
/* helpers                                                             */
/* ------------------------------------------------------------------ */

function Mirror({ children }: { children: ReactNode }) {
  return (
    <g>
      {children}
      <g transform="translate(400 0) scale(-1 1)">{children}</g>
    </g>
  );
}

function HairBack({ p, id, detail }: { p: ArtParams; id: string; detail: string }) {
  const g = p.geometry;
  const style = p.hairStyle;
  if (style === "bald") return null;

  const long = style === "long" || style === "curly" || style === "braid" || style === "straight";
  const to = long ? g.hipY + 70 : style === "short" ? g.chinY + 24 : g.shoulderY + 46;
  const wave = p.seed % 2 === 0 ? 1 : -1;
  const hw = g.headRx + 12;

  const half = (
    <path
      d={[
        `M ${g.cx + 2} ${g.topY - 4}`,
        `C ${g.cx + hw + 10} ${g.topY} ${g.cx + hw + 30} ${g.headCy + 30} ${g.cx + hw + 24} ${g.headCy + 96}`,
        `C ${g.cx + hw + 34 + wave * 8} ${g.headCy + 180} ${g.cx + hw + 10} ${to - 70} ${g.cx + hw + 18} ${to}`,
        `C ${g.cx + hw + 4} ${to + 16} ${g.cx + hw - 20} ${to + 18} ${g.cx + hw - 24} ${to - 14}`,
        `C ${g.cx + hw - 34} ${to - 96} ${g.cx + hw - 16} ${g.headCy + 170} ${g.cx + hw - 18} ${g.headCy + 96}`,
        `C ${g.cx + hw - 20} ${g.headCy + 30} ${g.cx + hw - 26} ${g.topY + 10} ${g.cx + 2} ${g.topY - 4}`,
        "Z",
      ].join(" ")}
      fill={`url(#${id}-hair-back)`}
      stroke={p.palette.line}
      strokeWidth={detail === "simple" ? 2 : 2.4}
    />
  );

  return (
    <g>
      <Mirror>{half}</Mirror>
      {detail === "full" && style === "curly" && (
        <Mirror>
          <path
            d={`M ${g.cx + hw - 4} ${g.headCy + 40} q 22 26 4 52 q -18 26 6 50 q 20 24 0 52 q -16 24 4 46`}
            fill="none"
            stroke={p.palette.hairShadow}
            strokeWidth="2"
            opacity="0.55"
          />
        </Mirror>
      )}
      {style === "ponytail" && (
        <path
          d={[
            `M ${g.cx + 34} ${g.headCy - g.headRy + 8}`,
            `C ${g.cx + 92} ${g.headCy - 30} ${g.cx + 108} ${g.headCy + 70} ${g.cx + 86} ${g.headCy + 150}`,
            `C ${g.cx + 74} ${g.headCy + 200} ${g.cx + 52} ${g.headCy + 210} ${g.cx + 44} ${g.headCy + 180}`,
            `C ${g.cx + 62} ${g.headCy + 120} ${g.cx + 70} ${g.headCy + 40} ${g.cx + 26} ${g.headCy - 20}`,
            "Z",
          ].join(" ")}
          fill={`url(#${id}-hair)`}
          stroke={p.palette.line}
          strokeWidth="2.2"
        />
      )}
      {style === "twin_tail" && (
        <Mirror>
          <path
            d={[
              `M ${g.cx + 30} ${g.headCy - g.headRy + 14}`,
              `C ${g.cx + 78} ${g.headCy - 10} ${g.cx + 88} ${g.headCy + 80} ${g.cx + 66} ${g.headCy + 156}`,
              `C ${g.cx + 56} ${g.headCy + 196} ${g.cx + 36} ${g.headCy + 200} ${g.cx + 32} ${g.headCy + 166}`,
              `C ${g.cx + 44} ${g.headCy + 110} ${g.cx + 52} ${g.headCy + 40} ${g.cx + 22} ${g.headCy - 18}`,
              "Z",
            ].join(" ")}
            fill={`url(#${id}-hair)`}
            stroke={p.palette.line}
            strokeWidth="2.2"
          />
        </Mirror>
      )}
      {style === "braid" && (
        <g>
          {Array.from({ length: 6 }, (_, index) => (
            <ellipse
              key={index}
              cx={g.cx - g.headRx - 12 + (index % 2 ? 5 : -3)}
              cy={g.shoulderY + 26 + index * 34}
              rx="15"
              ry="12"
              fill={index % 2 ? p.palette.hair : p.palette.hairShadow}
              stroke={p.palette.line}
              strokeWidth="1.8"
            />
          ))}
          <path
            d={`M ${g.cx - g.headRx - 6} ${g.shoulderY + 250} l 4 26 l 12 -20 z`}
            fill={p.palette.accent}
            stroke={p.palette.line}
            strokeWidth="1.4"
          />
        </g>
      )}
    </g>
  );
}

function Bangs({ p, id, detail }: { p: ArtParams; id: string; detail: string }) {
  const g = p.geometry;
  if (p.hairStyle === "bald") return null;
  const rootY = g.topY + 6;
  const templeY = g.headCy - g.headRy * 0.55;
  const browY = g.headCy - g.headRy * 0.18;
  const longLock = p.hairLength === "long";
  const lockEnd = longLock ? g.waistY + 16 : g.chinY + 14;

  return (
    <g>
      {/* crown volume (avoids the flat-helmet look) */}
      <path
        d={[
          `M ${g.cx - g.headRx - 4} ${g.headCy - g.headRy * 0.5}`,
          `C ${g.cx - g.headRx - 7} ${g.topY - 14} ${g.cx + g.headRx + 7} ${g.topY - 14} ${g.cx + g.headRx + 4} ${g.headCy - g.headRy * 0.5}`,
          `C ${g.cx + g.headRx - 6} ${g.topY - 3} ${g.cx - g.headRx + 6} ${g.topY - 3} ${g.cx - g.headRx - 4} ${g.headCy - g.headRy * 0.5}`,
          "Z",
        ].join(" ")}
        fill={`url(#${id}-hair)`}
        stroke={p.palette.line}
        strokeWidth="2.1"
      />
      {/* skull cap (sits on the head, never towers above it) */}
      <path
        d={[
          `M ${g.cx - g.headRx - 2} ${g.headCy - g.headRy * 0.3}`,
          `C ${g.cx - g.headRx - 2} ${g.topY - 2} ${g.cx + g.headRx + 2} ${g.topY - 2} ${g.cx + g.headRx + 2} ${g.headCy - g.headRy * 0.3}`,
          `C ${g.cx + g.headRx - 4} ${g.headCy - g.headRy * 0.85} ${g.cx - g.headRx + 4} ${g.headCy - g.headRy * 0.85} ${g.cx - g.headRx - 2} ${g.headCy - g.headRy * 0.3}`,
          "Z",
        ].join(" ")}
        fill={`url(#${id}-hair)`}
        stroke={p.palette.line}
        strokeWidth="2.1"
      />
      {/* parted fringe: sweeps to the sides, leaving the eyes clear */}
      <Mirror>
        <path
          d={[
            `M ${g.cx + 3} ${rootY}`,
            `C ${g.cx + 26} ${rootY + 2} ${g.cx + g.headRx - 2} ${templeY - 8} ${g.cx + g.headRx + 3} ${browY}`,
            `C ${g.cx + g.headRx - 12} ${browY - 10} ${g.cx + 28} ${g.headCy - g.headRy * 0.52} ${g.cx + 5} ${rootY + 10}`,
            "Z",
          ].join(" ")}
          fill={`url(#${id}-hair)`}
          stroke={p.palette.line}
          strokeWidth="2"
        />
      </Mirror>
      {/* side locks: tapered strands framing the face */}
      <Mirror>
        <path
          d={[
            `M ${g.cx + g.headRx - 2} ${templeY - 2}`,
            `C ${g.cx + g.headRx + 14} ${g.headCy + 34} ${g.cx + g.headRx + 10} ${g.headCy + 116} ${g.cx + g.headRx + 6} ${lockEnd - 40}`,
            `C ${g.cx + g.headRx + 4} ${lockEnd - 10} ${g.cx + g.headRx - 2} ${lockEnd + 8} ${g.cx + g.headRx - 7} ${lockEnd + 20}`,
            `C ${g.cx + g.headRx - 6} ${lockEnd - 20} ${g.cx + g.headRx - 10} ${g.headCy + 90} ${g.cx + g.headRx - 11} ${g.headCy + 12}`,
            "Z",
          ].join(" ")}
          fill={`url(#${id}-hair)`}
          stroke={p.palette.line}
          strokeWidth="2"
        />
      </Mirror>
      {detail === "full" && (
        <>
          <Mirror>
            <path
              d={`M ${g.cx + 12} ${rootY + 4} C ${g.cx + 30} ${g.topY + 16} ${g.cx + g.headRx - 4} ${g.headCy - g.headRy * 0.4} ${g.cx + g.headRx + 1} ${browY - 4}`}
              fill="none"
              stroke={p.palette.hairLight}
              strokeWidth="2.4"
              opacity="0.65"
            />
          </Mirror>
          <Mirror>
            <path
              d={`M ${g.cx + g.headRx + 1} ${g.headCy + 40} C ${g.cx + g.headRx + 3} ${g.headCy + 120} ${g.cx + g.headRx - 8} ${lockEnd - 60} ${g.cx + g.headRx - 10} ${lockEnd - 20}`}
              fill="none"
              stroke={p.palette.hairLight}
              strokeWidth="2"
              opacity="0.5"
            />
          </Mirror>
        </>
      )}
    </g>
  );
}

function Face({ p, id }: { p: ArtParams; id: string }) {
  const g = p.geometry;
  const female = p.gender === "female";
  const eyeX = g.headRx * 0.46;
  const eyeY = g.headCy + g.headRy * 0.14;
  const ew = g.headRx * 0.36;
  const eh = g.headRy * (female ? 0.27 : 0.23);

  const open = p.expression === "cute" ? 1.15 : p.expression === "cold" || p.expression === "mysterious" ? 0.74 : p.expression === "warm" ? 1 : 0.9;
  const browTilt = p.expression === "angry" ? 8 : p.expression === "sad" ? -6 : p.expression === "cold" ? 3 : 0;
  const mouth =
    p.expression === "warm"
      ? `M ${g.cx - 9} ${g.headCy + g.headRy * 0.6} Q ${g.cx} ${g.headCy + g.headRy * 0.7 + 5} ${g.cx + 9} ${g.headCy + g.headRy * 0.6}`
      : p.expression === "angry"
        ? `M ${g.cx - 9} ${g.headCy + g.headRy * 0.68} Q ${g.cx} ${g.headCy + g.headRy * 0.6} ${g.cx + 9} ${g.headCy + g.headRy * 0.68}`
        : p.expression === "cute"
          ? `M ${g.cx - 7} ${g.headCy + g.headRy * 0.62} Q ${g.cx} ${g.headCy + g.headRy * 0.72} ${g.cx + 7} ${g.headCy + g.headRy * 0.62}`
          : `M ${g.cx - 8} ${g.headCy + g.headRy * 0.64} Q ${g.cx - 1} ${g.headCy + g.headRy * 0.68} ${g.cx + 9} ${g.headCy + g.headRy * 0.6}`;

  const almond = [
    `M ${-ew} 0`,
    `Q ${-ew * 0.5} ${-eh * open} 0 ${-eh * open * 0.92}`,
    `Q ${ew * 0.5} ${-eh * open} ${ew} 0`,
    `Q ${ew * 0.5} ${eh * 0.52} 0 ${eh * 0.48}`,
    `Q ${-ew * 0.5} ${eh * 0.52} ${-ew} 0`,
    "Z",
  ].join(" ");

  const eye = (
    <g>
      <path
        d={almond}
        fill="#fbfaf8"
        stroke={p.palette.line}
        strokeWidth="1.4"
      />
      <ellipse
        cx="0"
        cy={-eh * 0.04}
        rx={ew * 0.62}
        ry={eh * 0.82}
        fill={`url(#${id}-iris)`}
        stroke={shade(p.palette.eyes, -0.55)}
        strokeWidth="1.1"
      />
      <ellipse cx="0" cy={-eh * 0.04} rx={ew * 0.26} ry={eh * 0.44} fill="#1b1215" />
      <circle cx={-ew * 0.22} cy={-eh * 0.42} r={ew * 0.22} fill="#ffffff" opacity="0.98" />
      <circle cx={ew * 0.26} cy={eh * 0.22} r={ew * 0.1} fill="#ffffff" opacity="0.85" />
      <path
        d={`M ${-ew - 1} -1 Q ${-ew * 0.5} ${-eh * open - 3} ${ew + 1} -1`}
        fill="none"
        stroke={p.palette.line}
        strokeWidth={female ? 2.8 : 2.3}
        strokeLinecap="round"
      />
      {/* eyelid crease */}
      <path
        d={`M ${-ew - 1} ${-eh * open * 0.35} Q 0 ${-eh * open - 7} ${ew + 1} ${-eh * open * 0.35}`}
        fill="none"
        stroke={p.palette.skinShadow}
        strokeWidth="1.1"
        opacity="0.75"
      />
      {/* lower lash */}
      <path
        d={`M ${-ew * 0.7} ${eh * 0.52} Q 0 ${eh * 0.66} ${ew * 0.7} ${eh * 0.52}`}
        fill="none"
        stroke={p.palette.line}
        strokeWidth="0.9"
        opacity="0.55"
      />
      {female && (
        <path
          d={`M ${ew + 2} -2 l 7 -5`}
          stroke={p.palette.line}
          strokeWidth="2"
          strokeLinecap="round"
          fill="none"
        />
      )}
      <path
        d={`M ${-ew * 0.8} ${eh * 0.5} Q 0 ${eh * 0.62} ${ew * 0.8} ${eh * 0.5}`}
        fill="none"
        stroke={p.palette.line}
        strokeWidth="1"
        opacity="0.6"
      />
    </g>
  );

  const brow = (
    <path
      d={`M ${-ew - 2} ${-eh - 8 + browTilt * 0.5} Q 0 ${-eh - 13 - browTilt} ${ew + 2} ${-eh - 8 - browTilt * 0.5}`}
      fill="none"
      stroke={p.palette.hairShadow}
      strokeWidth={female ? 1.9 : 1.7}
      strokeLinecap="round"
      opacity="0.9"
    />
  );

  return (
    <g>
      <Mirror>
        <g transform={`translate(${g.cx + eyeX} ${eyeY})`}>
          {eye}
          {brow}
        </g>
      </Mirror>
      {/* nose */}
      <path
        d={`M ${g.cx + 2} ${g.headCy + g.headRy * 0.38} q -5 5 -2 7`}
        fill="none"
        stroke={p.palette.skinShadow}
        strokeWidth="1.4"
        strokeLinecap="round"
      />
      <path
        d={mouth}
        fill="none"
        stroke={p.palette.line}
        strokeWidth="1.7"
        strokeLinecap="round"
      />
      {p.expression === "angry" && (
        <path
          d={`M ${g.cx - 4} ${g.headCy + g.headRy * 0.52} l 8 -5`}
          stroke={p.palette.line}
          strokeWidth="1.3"
          strokeLinecap="round"
        />
      )}
      {female && (
        <Mirror>
          <ellipse
            cx={g.cx + g.headRx * 0.52}
            cy={g.headCy + g.headRy * 0.42}
            rx={g.headRx * 0.3}
            ry={g.headRy * 0.16}
            fill={`url(#${id}-blush)`}
          />
        </Mirror>
      )}
      {/* ears */}
      <Mirror>
        <path
          d={[
            `M ${g.cx + g.headRx - 2} ${g.headCy + 6}`,
            `q 10 2 8 14 q -2 10 -10 8`,
            `q -2 -12 2 -22 Z`,
          ].join(" ")}
          fill={p.palette.skin}
          stroke={p.palette.line}
          strokeWidth="1.6"
        />
      </Mirror>
      {p.hasEarrings && (
        <Mirror>
          <circle cx={g.cx + g.headRx + 4} cy={g.headCy + 24} r="3.6" fill="#f3ede4" stroke={p.palette.line} strokeWidth="1" />
        </Mirror>
      )}
      {p.accessory.includes("mask") && (
        <path
          d={`M ${g.cx - g.headRx * 0.8} ${g.headCy + g.headRy * 0.3} q ${g.headRx * 0.8} ${g.headRy * 0.5} ${g.headRx * 1.6} 0 q -${g.headRx * 0.2} ${g.headRy * 0.45} -${g.headRx * 0.8} ${g.headRy * 0.45} q -${g.headRx * 0.6} 0 -${g.headRx * 0.8} -${g.headRy * 0.45} Z`}
          fill={p.palette.baseShadow}
          stroke={p.palette.line}
          strokeWidth="1.6"
          opacity="0.92"
        />
      )}
      {p.accessory.includes("goggles") && (
        <g>
          <rect
            x={g.cx - g.headRx - 4}
            y={g.headCy - g.headRy * 0.72}
            width={g.headRx * 2 + 8}
            height="7"
            rx="3"
            fill={p.palette.metalDark}
            stroke={p.palette.line}
            strokeWidth="1.2"
          />
          <Mirror>
            <circle cx={g.cx + g.headRx * 0.5} cy={g.headCy - g.headRy * 0.68} r="9" fill={p.palette.metal} stroke={p.palette.line} strokeWidth="1.4" />
          </Mirror>
        </g>
      )}
    </g>
  );
}

function Ribbon({ p }: { p: ArtParams }) {
  const g = p.geometry;
  const x = g.cx - g.headRx - 4;
  const y = g.headCy - g.headRy * 0.55;
  return (
    <g>
      <path d={`M ${x} ${y} q -20 -14 -24 0 q -4 14 24 4 z`} fill="#efe6d6" stroke={p.palette.line} strokeWidth="1.5" />
      <path d={`M ${x} ${y} q -16 14 -8 22 q 10 6 12 -18 z`} fill="#e3d7c3" stroke={p.palette.line} strokeWidth="1.5" />
      <circle cx={x - 1} cy={y + 2} r="4" fill="#f6efe2" stroke={p.palette.line} strokeWidth="1.2" />
    </g>
  );
}

function Weapon({ p, id }: { p: ArtParams; id: string }) {
  const g = p.geometry;
  const x = g.cx + g.shoulderHalf + 34;
  const handY = g.waistY + 40;
  switch (p.weapon) {
    case "staff": {
      const sx = g.cx + g.shoulderHalf + 8;
      const fistY = g.waistY + 96;
      return (
        <g>
          <path
            d={`M ${sx} ${fistY + 84} C ${sx - 5} ${g.hipY} ${sx + 5} ${g.bustY} ${sx} ${g.headCy - 56}`}
            fill="none"
            stroke={`url(#${id}-metal)`}
            strokeWidth="7"
            strokeLinecap="round"
          />
          <circle cx={sx} cy={g.headCy - 64} r="14" fill={p.palette.accent} opacity="0.35" filter={`url(#${id}-soft)`} />
          <circle cx={sx} cy={g.headCy - 64} r="9" fill={p.palette.accent} stroke={p.palette.line} strokeWidth="1.6" />
          <ellipse cx={sx} cy={fistY} rx="8.5" ry="10.5" fill={p.palette.skin} stroke={p.palette.line} strokeWidth="1.6" />
          <path
            d={`M ${sx - 6} ${fistY - 3} h 12 M ${sx - 6} ${fistY + 5} h 12`}
            stroke={p.palette.skinShadow}
            strokeWidth="1.2"
          />
        </g>
      );
    }
    case "sword":
      return (
        <g>
          <path d={`M ${x} ${g.headCy - 40} L ${x + 6} ${handY + 16}`} stroke={`url(#${id}-metal)`} strokeWidth="8" strokeLinecap="round" />
          <path d={`M ${x} ${g.headCy - 40} L ${x + 6} ${handY + 16}`} stroke={p.palette.line} strokeWidth="8" strokeOpacity="0.2" strokeLinecap="round" />
          <path d={`M ${x - 8} ${handY + 14} h 28`} stroke={p.palette.accent} strokeWidth="6" strokeLinecap="round" />
          <path d={`M ${x + 4} ${handY + 18} v 26`} stroke={p.palette.hairShadow} strokeWidth="7" strokeLinecap="round" />
        </g>
      );
    case "bow":
      return (
        <g>
          <path
            d={`M ${x - 6} ${g.bustY - 20} C ${x + 34} ${g.waistY - 10} ${x + 34} ${g.waistY + 60} ${x - 6} ${g.waistY + 110}`}
            fill="none"
            stroke={p.palette.metalDark}
            strokeWidth="6"
            strokeLinecap="round"
          />
          <path
            d={`M ${x - 6} ${g.bustY - 20} L ${x - 6} ${g.waistY + 110}`}
            stroke={p.palette.line}
            strokeWidth="1.4"
            opacity="0.7"
          />
        </g>
      );
    case "axe":
    case "hammer":
      return (
        <g>
          <path d={`M ${x} ${handY + 80} V ${g.headCy + 6}`} stroke={p.palette.hairShadow} strokeWidth="7" strokeLinecap="round" />
          {p.weapon === "axe" ? (
            <path
              d={`M ${x} ${g.headCy + 4} q 30 -16 34 14 q -22 12 -34 -2 z`}
              fill={`url(#${id}-metal)`}
              stroke={p.palette.line}
              strokeWidth="1.8"
            />
          ) : (
            <rect x={x - 20} y={g.headCy - 8} width="40" height="26" rx="6" fill={`url(#${id}-metal)`} stroke={p.palette.line} strokeWidth="1.8" />
          )}
        </g>
      );
    case "dagger":
      return (
        <path d={`M ${x} ${handY + 4} l 4 34 l -8 0 z`} fill={`url(#${id}-metal)`} stroke={p.palette.line} strokeWidth="1.4" />
      );
    case "tome":
      return (
        <g transform={`translate(${g.cx - g.shoulderHalf - 30} ${g.waistY + 10})`}>
          <rect x="-20" y="0" width="40" height="30" rx="4" fill={p.palette.accent} stroke={p.palette.line} strokeWidth="1.8" />
          <path d="M 0 0 v 30" stroke={p.palette.line} strokeWidth="1.4" />
          <path d="M -14 8 h 10 M 6 8 h 10" stroke="#ffffff" strokeWidth="1.4" opacity="0.8" />
        </g>
      );
    case "orb":
      return (
        <g>
          <circle cx={x} cy={g.bustY + 30} r="15" fill={p.palette.accent} opacity="0.4" filter={`url(#${id}-soft)`} />
          <circle cx={x} cy={g.bustY + 30} r="9" fill={p.palette.accent} stroke={p.palette.line} strokeWidth="1.6" />
        </g>
      );
    case "scythe":
      return (
        <g>
          <path d={`M ${x} ${handY + 80} V ${g.headCy - 20}`} stroke={p.palette.hairShadow} strokeWidth="7" />
          <path d={`M ${x} ${g.headCy - 20} q 42 2 46 40`} fill="none" stroke={`url(#${id}-metal)`} strokeWidth="6" strokeLinecap="round" />
        </g>
      );
    default:
      return null;
  }
}

/* ------------------------------------------------------------------ */
/* front view                                                          */
/* ------------------------------------------------------------------ */

function FrontView({ p, id, detail }: { p: ArtParams; id: string; detail: string }) {
  const g = p.geometry;
  const stroke = p.palette.line;
  const lw = detail === "simple" ? 1.6 : 1.9;

  const skirtTop = g.hipY - 12;
  const skirtBottom = g.hipY + (p.garment === "robe" ? 300 : 118);
  const skirtFlare = p.garment === "robe" ? 66 : 42;

  return (
    <g>
      {p.accessory.includes("cape") && (
        <path
          d={`M ${g.cx - g.shoulderHalf - 6} ${g.shoulderY} C ${g.cx - g.shoulderHalf - 50} ${g.hipY} ${g.cx - g.shoulderHalf - 40} ${g.waistY + 130} ${g.cx - g.shoulderHalf - 18} ${g.waistY + 190} L ${g.cx + g.shoulderHalf + 18} ${g.waistY + 190} C ${g.cx + g.shoulderHalf + 40} ${g.waistY + 130} ${g.cx + g.shoulderHalf + 50} ${g.hipY} ${g.cx + g.shoulderHalf + 6} ${g.shoulderY} Z`}
          fill={`url(#${id}-cloth-dark)`}
          stroke={stroke}
          strokeWidth={lw}
          opacity="0.95"
        />
      )}
      {p.accessory.includes("wings") && (
        <Mirror>
          <path
            d={`M ${g.cx + g.shoulderHalf - 8} ${g.shoulderY - 6} C ${g.cx + g.shoulderHalf + 60} ${g.shoulderY - 90} ${g.cx + g.shoulderHalf + 120} ${g.shoulderY - 60} ${g.cx + g.shoulderHalf + 70} ${g.shoulderY + 40} C ${g.cx + g.shoulderHalf + 40} ${g.shoulderY + 6} ${g.cx + g.shoulderHalf + 20} ${g.shoulderY + 30} ${g.cx + g.shoulderHalf - 8} ${g.shoulderY - 6} Z`}
            fill={p.palette.highlight}
            stroke={stroke}
            strokeWidth={lw}
            opacity="0.9"
          />
        </Mirror>
      )}

      <HairBack p={p} id={id} detail={detail} />

      {/* neck */}
      <path
        d={`M ${g.cx - g.neckW} ${g.chinY - 12} L ${g.cx - g.neckW - 2} ${g.shoulderY + 4} L ${g.cx + g.neckW + 2} ${g.shoulderY + 4} L ${g.cx + g.neckW} ${g.chinY - 12} Z`}
        fill={p.palette.skinShadow}
        stroke={stroke}
        strokeWidth={lw}
      />

      {/* legs */}
      <Mirror>
        <path
          d={[
            `M ${g.cx + 6} ${skirtBottom - 30}`,
            `C ${g.cx + 14} ${g.kneeY} ${g.cx + 12} ${g.kneeY + 70} ${g.cx + 10} ${g.ankleY}`,
            `L ${g.cx + 24} ${g.ankleY}`,
            `C ${g.cx + 26} ${g.kneeY + 70} ${g.cx + 28} ${g.kneeY} ${g.cx + g.hipHalf - 4} ${skirtBottom - 30}`,
            "Z",
          ].join(" ")}
          fill={`url(#${id}-skin)`}
          stroke={stroke}
          strokeWidth={lw}
        />
      </Mirror>

      {/* skirt / lower garment */}
      {p.garment === "robe" ? (
        <path
          d={`M ${g.cx - g.waistHalf - 4} ${g.waistY} L ${g.cx - g.waistHalf - skirtFlare} ${skirtBottom} Q ${g.cx} ${skirtBottom + 22} ${g.cx + g.waistHalf + skirtFlare} ${skirtBottom} L ${g.cx + g.waistHalf + 4} ${g.waistY} Z`}
          fill={`url(#${id}-cloth)`}
          stroke={stroke}
          strokeWidth={lw}
        />
      ) : (
        <path
          d={`M ${g.cx - g.waistHalf - 2} ${skirtTop} L ${g.cx - g.waistHalf - skirtFlare} ${skirtBottom} Q ${g.cx} ${skirtBottom + 18} ${g.cx + g.waistHalf + skirtFlare} ${skirtBottom} L ${g.cx + g.waistHalf + 2} ${skirtTop} Z`}
          fill={`url(#${id}-cloth-dark)`}
          stroke={stroke}
          strokeWidth={lw}
        />
      )}
      {detail === "full" &&
        Array.from({ length: 7 }, (_, index) => {
          const spread = (index - 3) / 3;
          return (
            <path
              key={index}
              d={`M ${g.cx + spread * g.waistHalf} ${skirtTop + 8} L ${g.cx + spread * (g.waistHalf + skirtFlare)} ${skirtBottom - 6}`}
              stroke={shade(p.palette.baseShadow, -0.35)}
              strokeWidth="1.2"
              opacity="0.7"
              fill="none"
            />
          );
        })}
      {p.garment === "robe" && (
        <path
          d={`M ${g.cx + 6} ${g.waistY + 4} L ${g.cx + g.waistHalf + skirtFlare * 0.72} ${skirtBottom - 8} L ${g.cx + g.waistHalf + 4} ${g.waistY + 4} Z`}
          fill={shade(p.palette.baseShadow, -0.1)}
          opacity="0.5"
        />
      )}

      {/* socks + shoes (robe hems cover the knees, so only shoe tips show) */}
      {p.garment === "robe" ? (
        <Mirror>
          <path
            d={`M ${g.cx + 8} ${g.ankleY - 4} q -2 12 2 18 h 18 q 6 0 6 -8 l 0 -6 q 0 -4 -6 -4 z`}
            fill={shade(p.palette.hairShadow, -0.35)}
            stroke={stroke}
            strokeWidth={1.4}
          />
        </Mirror>
      ) : (
        <Mirror>
          <path
            d={`M ${g.cx + 8} ${g.kneeY + 6} L ${g.cx + 24} ${g.kneeY + 6} L ${g.cx + 22} ${g.ankleY - 4} L ${g.cx + 10} ${g.ankleY - 4} Z`}
            fill={p.palette.highlight}
            stroke={stroke}
            strokeWidth={1.4}
          />
          <path d={`M ${g.cx + 8} ${g.kneeY + 16} H ${g.cx + 24}`} stroke={stroke} strokeWidth="1" opacity="0.35" />
          <path
            d={`M ${g.cx + 6} ${g.ankleY - 6} h 20 q 8 0 8 10 l 0 8 q 0 6 -8 6 h -22 q -8 0 -8 -8 l 0 -8 q 0 -10 10 -10 z`}
            fill={shade(p.palette.hairShadow, -0.32)}
            stroke={stroke}
            strokeWidth={1.4}
          />
          <path d={`M ${g.cx + 6} ${g.ankleY + 2} h 28`} stroke={stroke} strokeWidth="1" opacity="0.35" />
          <path d={`M ${g.cx + 12} ${g.ankleY - 6} h 12`} stroke={p.palette.accent} strokeWidth="2" />
        </Mirror>
      )}

      {/* torso */}
      <path
        d={`M ${g.cx - g.bustR - 8} ${g.bustY - 26} C ${g.cx - g.waistHalf - 8} ${g.waistY - 20} ${g.cx - g.waistHalf} ${g.waistY} ${g.cx - g.waistHalf} ${g.waistY + 6} L ${g.cx + g.waistHalf} ${g.waistY + 6} C ${g.cx + g.waistHalf} ${g.waistY} ${g.cx + g.waistHalf + 8} ${g.waistY - 20} ${g.cx + g.bustR + 8} ${g.bustY - 26} Z`}
        fill={`url(#${id}-skin)`}
        stroke={stroke}
        strokeWidth={lw}
      />

      {/* arms */}
      <Mirror>
        <path
          d={[
            `M ${g.cx + g.shoulderHalf - 12} ${g.shoulderY + 2}`,
            `C ${g.cx + g.shoulderHalf + 16} ${g.bustY} ${g.cx + g.shoulderHalf + 12} ${g.waistY + 20} ${g.cx + g.shoulderHalf + 4} ${g.waistY + 96}`,
            `L ${g.cx + g.shoulderHalf + 4 + g.armW} ${g.waistY + 96}`,
            `C ${g.cx + g.shoulderHalf + 12 + g.armW} ${g.waistY + 20} ${g.cx + g.shoulderHalf + 22 + g.armW} ${g.bustY} ${g.cx + g.shoulderHalf - 2} ${g.shoulderY + 6}`,
            "Z",
          ].join(" ")}
          fill={`url(#${id}-cloth)`}
          stroke={stroke}
          strokeWidth={lw}
        />
        <ellipse
          cx={g.cx + g.shoulderHalf + 6}
          cy={g.waistY + 106}
          rx={g.armW + 2}
          ry={g.armW + 6}
          fill={p.palette.skin}
          stroke={stroke}
          strokeWidth={lw}
        />
      </Mirror>

      {/* garment upper body */}
      {p.garment === "armor" && (
        <g>
          <path
            d={`M ${g.cx - g.shoulderHalf + 6} ${g.shoulderY + 2} Q ${g.cx} ${g.bustY + 14} ${g.cx + g.shoulderHalf - 6} ${g.shoulderY + 2} L ${g.cx + g.waistHalf + 6} ${g.waistY} L ${g.cx - g.waistHalf - 6} ${g.waistY} Z`}
            fill={`url(#${id}-metal)`}
            stroke={stroke}
            strokeWidth={lw}
          />
          <path d={`M ${g.cx} ${g.bustY - 24} v 76`} stroke={p.palette.accent} strokeWidth="2" opacity="0.8" />
          <Mirror>
            <ellipse cx={g.cx + g.shoulderHalf - 4} cy={g.shoulderY + 4} rx="26" ry="18" fill={`url(#${id}-metal)`} stroke={stroke} strokeWidth={lw} />
          </Mirror>
          {Array.from({ length: 4 }, (_, index) => (
            <path
              key={index}
              d={`M ${g.cx - 34 + index * 22} ${g.waistY + 6} l 0 44`}
              stroke={p.palette.accent}
              strokeWidth="8"
              strokeLinecap="round"
              opacity="0.85"
            />
          ))}
        </g>
      )}

      {p.garment === "robe" && (
        <g>
          <path
            d={`M ${g.cx - g.neckW - 8} ${g.chinY - 8} Q ${g.cx} ${g.chinY + 16} ${g.cx + g.neckW + 8} ${g.chinY - 8} L ${g.cx + g.bustR + 6} ${g.bustY - 34} Q ${g.cx} ${g.bustY - 8} ${g.cx - g.bustR - 6} ${g.bustY - 34} Z`}
            fill={p.palette.base}
            stroke={stroke}
            strokeWidth={lw}
          />
          <path
            d={`M ${g.cx - g.bustR - 6} ${g.bustY - 34} Q ${g.cx} ${g.bustY - 8} ${g.cx + g.bustR + 6} ${g.bustY - 34}`}
            fill="none"
            stroke={p.palette.accent}
            strokeWidth="2.4"
          />
          <path
            d={`M ${g.cx - g.shoulderHalf + 4} ${g.shoulderY + 2} Q ${g.cx} ${g.bustY + 18} ${g.cx + g.shoulderHalf - 4} ${g.shoulderY + 2} L ${g.cx + g.waistHalf + 4} ${g.waistY} L ${g.cx - g.waistHalf - 4} ${g.waistY} Z`}
            fill={`url(#${id}-cloth)`}
            stroke={stroke}
            strokeWidth={lw}
          />
          <path
            d={`M ${g.cx - g.waistHalf - 8} ${g.waistY - 6} H ${g.cx + g.waistHalf + 8} L ${g.cx + g.waistHalf + 2} ${g.waistY + 16} H ${g.cx - g.waistHalf - 2} Z`}
            fill={p.palette.accent}
            stroke={stroke}
            strokeWidth="1.6"
          />
          <path d={`M ${g.cx} ${g.shoulderY + 10} V ${g.waistY - 6}`} stroke={shade(p.palette.baseShadow, -0.2)} strokeWidth="1.6" />
          <circle cx={g.cx} cy={g.shoulderY + 34} r="4" fill={p.palette.accent} stroke={stroke} strokeWidth="1.2" />
          <path d={`M ${g.cx - 16} ${g.shoulderY + 62} q 16 10 32 0`} fill="none" stroke={p.palette.accent} strokeWidth="2" />
        </g>
      )}

      {p.garment === "tunic" && (
        <g>
          <path
            d={`M ${g.cx - g.shoulderHalf + 4} ${g.shoulderY + 2} Q ${g.cx} ${g.bustY + 16} ${g.cx + g.shoulderHalf - 4} ${g.shoulderY + 2} L ${g.cx + g.waistHalf + 6} ${g.waistY + 18} L ${g.cx - g.waistHalf - 6} ${g.waistY + 18} Z`}
            fill={`url(#${id}-cloth)`}
            stroke={stroke}
            strokeWidth={lw}
          />
          <path
            d={`M ${g.cx - g.waistHalf - 8} ${g.waistY + 2} H ${g.cx + g.waistHalf + 8} V ${g.waistY + 16} H ${g.cx - g.waistHalf - 8} Z`}
            fill={p.palette.hairShadow}
            stroke={stroke}
            strokeWidth="1.4"
          />
          <rect x={g.cx - 7} y={g.waistY + 4} width="14" height="10" rx="2" fill={p.palette.accent} stroke={stroke} strokeWidth="1.2" />
        </g>
      )}

      {p.garment === "hood" && (
        <g>
          <path
            d={`M ${g.cx - g.shoulderHalf + 6} ${g.shoulderY + 4} Q ${g.cx} ${g.bustY + 20} ${g.cx + g.shoulderHalf - 6} ${g.shoulderY + 4} L ${g.cx + g.waistHalf + 4} ${g.waistY + 16} L ${g.cx - g.waistHalf - 4} ${g.waistY + 16} Z`}
            fill={`url(#${id}-cloth)`}
            stroke={stroke}
            strokeWidth={lw}
          />
          <path
            d={`M ${g.cx - g.headRx - 10} ${g.headCy - 6} C ${g.cx - g.headRx - 16} ${g.headCy - g.headRy - 34} ${g.cx + g.headRx + 16} ${g.headCy - g.headRy - 34} ${g.cx + g.headRx + 10} ${g.headCy - 6} C ${g.cx + 40} ${g.headCy - g.headRy - 10} ${g.cx - 40} ${g.headCy - g.headRy - 10} ${g.cx - g.headRx - 10} ${g.headCy - 6} Z`}
            fill={`url(#${id}-cloth-dark)`}
            stroke={stroke}
            strokeWidth={lw}
          />
          <path d={`M ${g.cx - g.shoulderHalf + 10} ${g.shoulderY + 20} L ${g.cx + g.waistHalf} ${g.waistY + 6}`} stroke={p.palette.accent} strokeWidth="3" />
        </g>
      )}

      {p.garment === "suit" && (
        <g>
          {/* camisole */}
          <path
            d={`M ${g.cx - g.bustR - 4} ${g.bustY - 34} L ${g.cx - g.waistHalf - 4} ${g.waistY} L ${g.cx + g.waistHalf + 4} ${g.waistY} L ${g.cx + g.bustR + 4} ${g.bustY - 34} Z`}
            fill={p.palette.white}
            stroke={stroke}
            strokeWidth="1.4"
          />
          <Mirror>
            <path d={`M ${g.cx + 10} ${g.bustY - 40} q 14 10 22 4`} fill="none" stroke={stroke} strokeWidth="2.2" />
          </Mirror>
          {/* jacket */}
          <path
            d={`M ${g.cx - g.shoulderHalf + 2} ${g.shoulderY} C ${g.cx - g.bustR - 22} ${g.bustY} ${g.cx - g.waistHalf - 14} ${g.waistY - 16} ${g.cx - g.waistHalf - 6} ${g.waistY + 8} L ${g.cx - 10} ${g.waistY + 6} L ${g.cx - 20} ${g.bustY - 6} L ${g.cx - g.bustR + 6} ${g.bustY - 36} Z`}
            fill={`url(#${id}-cloth)`}
            stroke={stroke}
            strokeWidth={lw}
          />
          <path
            d={`M ${g.cx + g.shoulderHalf - 2} ${g.shoulderY} C ${g.cx + g.bustR + 22} ${g.bustY} ${g.cx + g.waistHalf + 14} ${g.waistY - 16} ${g.cx + g.waistHalf + 6} ${g.waistY + 8} L ${g.cx + 10} ${g.waistY + 6} L ${g.cx + 20} ${g.bustY - 6} L ${g.cx + g.bustR - 6} ${g.bustY - 36} Z`}
            fill={`url(#${id}-cloth)`}
            stroke={stroke}
            strokeWidth={lw}
          />
          <path d={`M ${g.cx - 10} ${g.waistY + 6} L ${g.cx - 22} ${g.bustY - 10}`} stroke={shade(p.palette.baseShadow, -0.3)} strokeWidth="2" />
          <path d={`M ${g.cx + 10} ${g.waistY + 6} L ${g.cx + 22} ${g.bustY - 10}`} stroke={shade(p.palette.baseShadow, -0.3)} strokeWidth="2" />
          <Mirror>
            <circle cx={g.cx + g.bustR - 10} cy={g.bustY + 4} r="3.4" fill={p.palette.accent} stroke={stroke} strokeWidth="1" />
          </Mirror>
          {/* collar */}
          <path
            d={`M ${g.cx - g.bustR + 2} ${g.bustY - 40} L ${g.cx - 4} ${g.bustY - 18} L ${g.cx - 16} ${g.bustY - 44} Z`}
            fill={shade(p.palette.base, -0.08)}
            stroke={stroke}
            strokeWidth="1.4"
          />
          <path
            d={`M ${g.cx + g.bustR - 2} ${g.bustY - 40} L ${g.cx + 4} ${g.bustY - 18} L ${g.cx + 16} ${g.bustY - 44} Z`}
            fill={shade(p.palette.base, -0.08)}
            stroke={stroke}
            strokeWidth="1.4"
          />
        </g>
      )}

      {/* head + face */}
      <path
        d={[
          `M ${g.cx} ${g.headCy - g.headRy}`,
          `C ${g.cx + g.headRx * 0.96} ${g.headCy - g.headRy} ${g.cx + g.headRx} ${g.headCy - g.headRy * 0.1} ${g.cx + g.headRx * 0.9} ${g.headCy + g.headRy * 0.38}`,
          `C ${g.cx + g.headRx * 0.7} ${g.headCy + g.headRy * 0.8} ${g.cx + g.headRx * 0.34} ${g.chinY} ${g.cx} ${g.chinY + 2}`,
          `C ${g.cx - g.headRx * 0.34} ${g.chinY} ${g.cx - g.headRx * 0.7} ${g.headCy + g.headRy * 0.8} ${g.cx - g.headRx * 0.9} ${g.headCy + g.headRy * 0.38}`,
          `C ${g.cx - g.headRx} ${g.headCy - g.headRy * 0.1} ${g.cx - g.headRx * 0.96} ${g.headCy - g.headRy} ${g.cx} ${g.headCy - g.headRy}`,
          "Z",
        ].join(" ")}
        fill={`url(#${id}-skin)`}
        stroke={stroke}
        strokeWidth={lw}
      />
      <Face p={p} id={id} />
      <Bangs p={p} id={id} detail={detail} />
      {p.hasRibbon && <Ribbon p={p} />}
      {p.accessory.includes("crown") && (
        <path
          d={`M ${g.cx - 22} ${g.headCy - g.headRy + 2} l 6 -14 l 8 10 l 8 -14 l 8 14 l 8 -10 l 6 14 z`}
          fill={p.palette.metal}
          stroke={stroke}
          strokeWidth="1.4"
        />
      )}
      {p.accessory.includes("horns") && (
        <Mirror>
          <path
            d={`M ${g.cx + 22} ${g.headCy - g.headRy + 6} C ${g.cx + 44} ${g.headCy - g.headRy - 24} ${g.cx + 40} ${g.headCy - g.headRy - 48} ${g.cx + 24} ${g.headCy - g.headRy - 54} C ${g.cx + 34} ${g.headCy - g.headRy - 28} ${g.cx + 32} ${g.headCy - g.headRy - 12} ${g.cx + 18} ${g.headCy - g.headRy + 2} Z`}
            fill={p.palette.metalDark}
            stroke={stroke}
            strokeWidth="1.5"
          />
        </Mirror>
      )}
      {p.accessory.includes("halo") && (
        <ellipse
          cx={g.cx}
          cy={g.headCy - g.headRy - 26}
          rx="30"
          ry="9"
          fill="none"
          stroke={p.palette.accent}
          strokeWidth="4"
          opacity="0.9"
        />
      )}
      {p.accessory.includes("necklace") && (
        <g>
          <path
            d={`M ${g.cx - 16} ${g.shoulderY - 2} Q ${g.cx} ${g.shoulderY + 18} ${g.cx + 16} ${g.shoulderY - 2}`}
            fill="none"
            stroke="#f3ede4"
            strokeWidth="1.6"
          />
          <circle cx={g.cx} cy={g.shoulderY + 16} r="4" fill={p.palette.accent} stroke={stroke} strokeWidth="1" />
        </g>
      )}

      <Weapon p={p} id={id} />

      {/* floor shadow */}
      <ellipse cx={g.cx} cy={g.groundY + 6} rx={66} ry={9} fill="#3b3129" opacity="0.18" />
    </g>
  );
}

/* ------------------------------------------------------------------ */
/* side view                                                           */
/* ------------------------------------------------------------------ */

function SideView({ p, id, detail }: { p: ArtParams; id: string; detail: string }) {
  const g = p.geometry;
  const stroke = p.palette.line;
  const lw = 1.9;
  const front = g.cx + g.headRx * 0.82;

  return (
    <g>
      {/* back hair volume */}
      {p.hairStyle !== "bald" && (
        <path
          d={[
            `M ${g.cx - 4} ${g.topY - 6}`,
            `C ${g.cx - g.headRx - 26} ${g.topY + 6} ${g.cx - g.headRx - 40} ${g.headCy + 40} ${g.cx - g.headRx - 30} ${p.hairLength === "long" ? g.hipY + 80 : g.shoulderY + 40}`,
            `C ${g.cx - g.headRx - 12} ${p.hairLength === "long" ? g.hipY + 60 : g.shoulderY + 20} ${g.cx - g.headRx - 4} ${g.headCy + 70} ${g.cx - g.headRx + 8} ${g.headCy - 6}`,
            "Z",
          ].join(" ")}
          fill={`url(#${id}-hair-back)`}
          stroke={stroke}
          strokeWidth="2.2"
        />
      )}

      {/* body block: back + chest profile */}
      <path
        d={[
          `M ${g.cx - 16} ${g.shoulderY - 6}`,
          `C ${g.cx + 6} ${g.shoulderY - 16} ${g.cx + g.bustR + 10} ${g.bustY - 10} ${g.cx + g.bustR + 6} ${g.bustY + 8}`,
          `C ${g.cx + g.waistHalf + 4} ${g.waistY - 16} ${g.cx + g.waistHalf + 2} ${g.waistY + 6} ${g.cx + g.waistHalf + 2} ${g.waistY + 10}`,
          `L ${g.cx - g.waistHalf - 6} ${g.waistY + 10}`,
          `C ${g.cx - g.waistHalf - 2} ${g.bustY} ${g.cx - g.bustR - 24} ${g.bustY - 6} ${g.cx - 16} ${g.shoulderY - 6}`,
          "Z",
        ].join(" ")}
        fill={`url(#${id}-cloth)`}
        stroke={stroke}
        strokeWidth={lw}
      />

      {/* skirt side */}
      <path
        d={`M ${g.cx - g.waistHalf - 4} ${g.hipY - 14} L ${g.cx - g.waistHalf - (p.garment === "robe" ? 44 : 30)} ${p.garment === "robe" ? g.ankleY : g.hipY + 110} L ${g.cx + g.waistHalf + (p.garment === "robe" ? 44 : 30)} ${p.garment === "robe" ? g.ankleY : g.hipY + 110} L ${g.cx + g.waistHalf + 2} ${g.hipY - 14} Z`}
        fill={`url(#${id}-cloth-dark)`}
        stroke={stroke}
        strokeWidth={lw}
      />

      {/* legs side */}
      <path
        d={`M ${g.cx - 2} ${g.hipY + 96} C ${g.cx + 2} ${g.kneeY} ${g.cx + 2} ${g.ankleY - 20} ${g.cx + 6} ${g.ankleY} L ${g.cx + 24} ${g.ankleY} C ${g.cx + 22} ${g.ankleY - 30} ${g.cx + 20} ${g.kneeY} ${g.cx + 22} ${g.hipY + 96} Z`}
        fill={`url(#${id}-skin)`}
        stroke={stroke}
        strokeWidth={lw}
      />
      {/* shoe side */}
      <path
        d={`M ${g.cx + 2} ${g.ankleY - 2} h 26 q 10 0 10 12 l 0 8 q 0 6 -8 6 l -34 0 q -8 0 -8 -8 l 0 -6 q 0 -12 12 -12 z`}
        fill={shade(p.palette.baseShadow, -0.55)}
        stroke={stroke}
        strokeWidth={lw}
      />

      {/* arm side */}
      <path
        d={`M ${g.cx + 6} ${g.bustY - 18} C ${g.cx + 26} ${g.waistY} ${g.cx + 26} ${g.waistY + 60} ${g.cx + 22} ${g.waistY + 100}`}
        fill="none"
        stroke={`url(#${id}-cloth)`}
        strokeWidth={g.armW * 2}
        strokeLinecap="round"
      />
      <circle cx={g.cx + 22} cy={g.waistY + 104} r={g.armW} fill={p.palette.skin} stroke={stroke} strokeWidth="1.6" />

      {/* neck + head profile */}
      <path
        d={`M ${g.cx - 6} ${g.chinY - 16} L ${g.cx - 4} ${g.shoulderY - 4} L ${g.cx + 12} ${g.shoulderY - 8} L ${g.cx + 10} ${g.chinY - 8} Z`}
        fill={p.palette.skinShadow}
        stroke={stroke}
        strokeWidth={lw}
      />
      <path
        d={[
          `M ${g.cx - 6} ${g.topY + 4}`,
          `C ${front - 2} ${g.topY + 6} ${front + 6} ${g.headCy - g.headRy * 0.5} ${front + 2} ${g.headCy - 2}`,
          `C ${front + 8} ${g.headCy + 8} ${front + 6} ${g.headCy + 14} ${front - 2} ${g.headCy + 16}`,
          `C ${front + 2} ${g.headCy + 24} ${front - 2} ${g.headCy + 30} ${front - 8} ${g.headCy + 34}`,
          `C ${g.cx + 18} ${g.chinY - 2} ${g.cx + 6} ${g.chinY + 6} ${g.cx - 2} ${g.chinY + 2}`,
          `C ${g.cx - 12} ${g.chinY - 10} ${g.cx - 16} ${g.headCy} ${g.cx - 16} ${g.headCy - 20}`,
          `C ${g.cx - 16} ${g.topY + 20} ${g.cx - 14} ${g.topY + 8} ${g.cx - 6} ${g.topY + 4}`,
          "Z",
        ].join(" ")}
        fill={`url(#${id}-skin)`}
        stroke={stroke}
        strokeWidth={lw}
      />
      {/* profile eye */}
      <path
        d={`M ${front - 12} ${g.headCy + 2} l 12 2`}
        stroke={stroke}
        strokeWidth="2.2"
        strokeLinecap="round"
      />
      <path
        d={`M ${front - 14} ${g.headCy + 14} l 8 2`}
        stroke={stroke}
        strokeWidth="1.4"
        strokeLinecap="round"
      />
      {/* front hair */}
      <path
        d={[
          `M ${g.cx - 8} ${g.topY + 2}`,
          `C ${front + 4} ${g.topY + 4} ${front + 10} ${g.headCy - g.headRy * 0.4} ${front - 2} ${g.headCy - 6}`,
          `C ${g.cx + 24} ${g.headCy - g.headRy * 0.7} ${g.cx + 8} ${g.topY + 8} ${g.cx - 8} ${g.topY + 2}`,
          "Z",
        ].join(" ")}
        fill={`url(#${id}-hair)`}
        stroke={stroke}
        strokeWidth="2"
      />
      {detail === "full" && p.hairStyle === "long" && (
        <path
          d={`M ${g.cx - g.headRx - 26} ${g.headCy + 40} C ${g.cx - g.headRx - 38} ${g.waistY} ${g.cx - g.headRx - 24} ${g.hipY + 30} ${g.cx - g.headRx - 16} ${g.hipY + 70}`}
          fill="none"
          stroke={p.palette.hairLight}
          strokeWidth="3"
          opacity="0.6"
        />
      )}
      {p.weapon === "staff" && (
        <g>
          <path d={`M ${g.cx - g.headRx - 34} ${g.hipY + 60} V ${g.headCy - 50}`} stroke={`url(#${id}-metal)`} strokeWidth="7" strokeLinecap="round" />
          <circle cx={g.cx - g.headRx - 34} cy={g.headCy - 58} r="9" fill={p.palette.accent} stroke={stroke} strokeWidth="1.6" />
        </g>
      )}
      <ellipse cx={g.cx} cy={g.groundY + 6} rx={58} ry={8} fill="#3b3129" opacity="0.18" />
    </g>
  );
}

/* ------------------------------------------------------------------ */
/* top view (engineering)                                              */
/* ------------------------------------------------------------------ */

function TopView({ p, id }: { p: ArtParams; id: string }) {
  const g = p.geometry;
  const stroke = p.palette.line;
  const headR = g.headRx * 1.5;
  const shoulder = g.shoulderHalf * 1.3;

  return (
    <g>
      {/* center lines */}
      <g stroke="#94a3b8" strokeWidth="1" strokeDasharray="14 5 3 5">
        <line x1="200" y1="30" x2="200" y2="370" />
        <line x1="30" y1="200" x2="370" y2="200" />
      </g>
      {/* shoulders (behind head) */}
      <ellipse
        cx="200"
        cy="226"
        rx={shoulder}
        ry={shoulder * 0.4}
        fill={`url(#${id}-cloth)`}
        stroke={stroke}
        strokeWidth="1.8"
      />
      {/* arms suggestion */}
      <Mirror>
        <ellipse cx={200 + shoulder - 8} cy="238" rx="9" ry="22" fill={shade(p.palette.baseShadow, -0.1)} stroke={stroke} strokeWidth="1.4" />
      </Mirror>
      {/* head from above */}
      <ellipse
        cx="200"
        cy="196"
        rx={headR}
        ry={headR * 1.12}
        fill={`url(#${id}-hair)`}
        stroke={stroke}
        strokeWidth="2"
      />
      {/* hair part + swirl */}
      <path
        d={`M 200 78 C 226 96 236 150 216 196`}
        fill="none"
        stroke={p.palette.hairShadow}
        strokeWidth="2"
        opacity="0.8"
      />
      <path
        d={`M 200 92 C 176 104 166 140 176 172`}
        fill="none"
        stroke={p.palette.hairLight}
        strokeWidth="2.2"
        opacity="0.7"
      />
      {/* face direction marker (front) */}
      <path d="M 186 84 L 200 66 L 214 84 Z" fill={p.palette.skin} stroke={stroke} strokeWidth="1.4" />
      <path d={`M 200 66 l 0 14`} stroke={stroke} strokeWidth="1.2" />
      {/* ears */}
      <Mirror>
        <ellipse cx={200 + headR - 2} cy="204" rx="7" ry="11" fill={p.palette.skin} stroke={stroke} strokeWidth="1.4" />
      </Mirror>
      {p.weapon === "staff" && <circle cx={200 + shoulder + 22} cy="250" r="8" fill={p.palette.accent} stroke={stroke} strokeWidth="1.4" />}
      {p.hairStyle === "ponytail" && (
        <path
          d={`M 200 250 C 236 268 244 306 214 336 C 204 320 210 292 194 276`}
          fill={`url(#${id}-hair)`}
          stroke={stroke}
          strokeWidth="1.8"
        />
      )}
    </g>
  );
}

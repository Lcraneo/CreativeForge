/**
 * FAlign frame stand-in: stick figure posed by motion phase.
 * Shared by Animation Studio and Asset Inspector.
 */
export function FrameFigure({
  phase,
  active = false,
  className = "h-20 w-16",
}: {
  phase: number;
  active?: boolean;
  className?: string;
}) {
  const swing = Math.sin(phase * Math.PI * 2) * 10;
  const arm = Math.cos(phase * Math.PI * 2) * 22;
  return (
    <svg viewBox="0 0 64 80" className={`${className} ${active ? "opacity-100" : "opacity-60"}`}>
      <line
        x1={46 + swing / 2}
        y1={14}
        x2={50 + swing}
        y2={66}
        stroke="#a16207"
        strokeWidth="2.5"
        strokeLinecap="round"
      />
      <circle cx={46 + swing / 2} cy={12} r={3.5} fill="#ff9d3d" />
      <circle cx="32" cy="16" r="9" fill="#f4d58d" />
      <path d="M23 14 L32 4 L41 14 Z" fill="#a78bfa" />
      <line
        x1="32"
        y1="25"
        x2="32"
        y2="50"
        stroke="#a78bfa"
        strokeWidth="7"
        strokeLinecap="round"
      />
      <line
        x1="32"
        y1="32"
        x2="44"
        y2={34 + arm / 2}
        stroke="#f4d58d"
        strokeWidth="3.4"
        strokeLinecap="round"
      />
      <line
        x1="32"
        y1="32"
        x2="20"
        y2={34 - arm / 2}
        stroke="#f4d58d"
        strokeWidth="3.4"
        strokeLinecap="round"
      />
      <line
        x1="32"
        y1="50"
        x2={26 - swing / 3}
        y2="70"
        stroke="#3a4658"
        strokeWidth="4"
        strokeLinecap="round"
      />
      <line
        x1="32"
        y1="50"
        x2={38 + swing / 3}
        y2="70"
        stroke="#3a4658"
        strokeWidth="4"
        strokeLinecap="round"
      />
      {active && <circle cx="32" cy="72" r="2.4" fill="#34d399" />}
    </svg>
  );
}

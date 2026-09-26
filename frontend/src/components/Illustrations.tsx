/** Abstract geometric illustrations for the workbench cards — flat
 *  monochrome compositions in warm grays, echoing editorial print. */

const base = "h-full w-full";

export function PenIllustration() {
  return (
    <svg viewBox="0 0 280 150" className={base} aria-hidden>
      <rect x="36" y="96" width="150" height="6" rx="3" fill="#d9d5cb" />
      <g transform="rotate(-32 140 70)">
        <rect x="96" y="34" width="88" height="26" rx="13" fill="#23211c" />
        <rect x="178" y="40" width="18" height="14" rx="7" fill="#55514a" />
        <path d="M96 40 L64 47 L96 54 Z" fill="#55514a" />
        <path d="M64 47 L52 47 L64 44 Z" fill="#1a1814" />
        <circle cx="118" cy="47" r="3.5" fill="#f5f3ef" />
      </g>
      <circle cx="216" cy="38" r="14" fill="#edebe5" />
      <circle cx="216" cy="38" r="14" stroke="#d9d5cb" fill="none" />
      <path d="M212 38 l5 5 l9 -11" stroke="#55514a" strokeWidth="2.5" fill="none" strokeLinecap="round" />
    </svg>
  );
}

export function TimelineIllustration() {
  return (
    <svg viewBox="0 0 280 150" className={base} aria-hidden>
      <rect x="34" y="46" width="212" height="58" rx="10" fill="#23211c" />
      {[0, 1, 2, 3, 4].map((i) => (
        <rect key={`t${i}`} x={46 + i * 42} y="52" width="10" height="6" rx="2" fill="#f5f3ef" opacity="0.85" />
      ))}
      {[0, 1, 2, 3, 4].map((i) => (
        <rect key={`b${i}`} x={46 + i * 42} y="92" width="10" height="6" rx="2" fill="#f5f3ef" opacity="0.85" />
      ))}
      {[0, 1, 2, 3].map((i) => (
        <rect key={`f${i}`} x={62 + i * 42} y="64" width="30" height="22" rx="4" fill={i === 1 ? "#e0b53f" : "#edebe5"} />
      ))}
      <path d="M76 70 l10 5 l-10 5 Z" fill="#23211c" />
      <rect x="34" y="118" width="118" height="4" rx="2" fill="#d9d5cb" />
      <rect x="34" y="118" width="72" height="4" rx="2" fill="#1a1814" />
      <circle cx="238" cy="120" r="3" fill="#1a1814" />
    </svg>
  );
}

export function ArchiveIllustration() {
  return (
    <svg viewBox="0 0 280 150" className={base} aria-hidden>
      <rect x="52" y="30" width="120" height="82" rx="10" fill="#e6e3db" stroke="#d3cfc5" />
      <rect x="66" y="44" width="92" height="16" rx="5" fill="#23211c" />
      <rect x="66" y="66" width="92" height="16" rx="5" fill="#c9c5bb" />
      <rect x="66" y="88" width="60" height="16" rx="5" fill="#edebe5" stroke="#d3cfc5" />
      <g transform="translate(158 62)">
        <rect x="0" y="0" width="84" height="64" rx="10" fill="#23211c" />
        <circle cx="24" cy="24" r="9" fill="#e0b53f" />
        <rect x="40" y="18" width="32" height="5" rx="2.5" fill="#f5f3ef" opacity="0.85" />
        <rect x="40" y="28" width="24" height="5" rx="2.5" fill="#f5f3ef" opacity="0.5" />
        <rect x="12" y="44" width="60" height="5" rx="2.5" fill="#f5f3ef" opacity="0.35" />
      </g>
      <rect x="52" y="124" width="190" height="4" rx="2" fill="#d9d5cb" />
    </svg>
  );
}

export function ForgeIllustration() {
  return (
    <svg viewBox="0 0 280 150" className={base} aria-hidden>
      <path d="M60 96 L120 96 L112 122 L52 122 Z" fill="#23211c" />
      <rect x="44" y="122" width="88" height="8" rx="4" fill="#55514a" />
      <rect x="104" y="58" width="96" height="26" rx="6" fill="#e6e3db" stroke="#d3cfc5" />
      <rect x="104" y="90" width="72" height="6" rx="3" fill="#c9c5bb" />
      <g transform="translate(148 20)">
        <path d="M18 0 L23 14 L38 14 L26 23 L31 37 L18 28 L5 37 L10 23 L-2 14 L13 14 Z" fill="#e0b53f" />
      </g>
      <circle cx="228" cy="100" r="12" fill="none" stroke="#d9d5cb" strokeWidth="2" />
      <path d="M223 100 l4 4 l7 -9" stroke="#3e7d5a" strokeWidth="2.5" fill="none" strokeLinecap="round" />
      <rect x="196" y="126" width="64" height="4" rx="2" fill="#d9d5cb" />
    </svg>
  );
}

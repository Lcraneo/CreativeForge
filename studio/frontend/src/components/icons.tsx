import type { SVGProps } from "react";

/**
 * Forge UI icon set — 20px grid, 1.7 stroke, round terminals.
 * No emoji, no external assets.
 */
const PATHS = {
  spark: <path d="M10 2.5 11.8 8l5.7.4-4.4 3.7 1.4 5.6L10 14.6l-4.5 3.1 1.4-5.6L2.5 8.4 8.2 8z" />,
  layers: (
    <>
      <path d="M10 3 17 7l-7 4-7-4z" />
      <path d="M3 11l7 4 7-4" />
      <path d="M3 14.5l7 4 7-4" />
    </>
  ),
  cube: (
    <>
      <path d="M10 2.6 17 6.4v7.2L10 17.4 3 13.6V6.4z" />
      <path d="M3 6.4 10 10.2l7-3.8M10 10.2v7.2" />
    </>
  ),
  grid: (
    <>
      <path d="M3.5 3.5h5v5h-5z" />
      <path d="M11.5 3.5h5v5h-5z" />
      <path d="M3.5 11.5h5v5h-5z" />
      <path d="M11.5 11.5h5v5h-5z" />
    </>
  ),
  film: (
    <>
      <path d="M3.5 5.5h13v9h-13z" />
      <path d="M6.5 5.5v9M13.5 5.5v9M3.5 10h13" />
    </>
  ),
  package: (
    <>
      <path d="M10 2.8 17 6.5v7L10 17.2 3 13.5v-7z" />
      <path d="M3 6.5 10 10.3l7-3.8M10 10.3v6.9" />
    </>
  ),
  gauge: (
    <>
      <path d="M4 14.5a7.5 7.5 0 1 1 12 0" />
      <path d="M10 11l3.2-3.2" />
      <circle cx="10" cy="14.5" r="1" />
    </>
  ),
  book: (
    <>
      <path d="M4 4.5h4.5a2 2 0 0 1 2 2v9a2 2 0 0 0-2-2H4z" />
      <path d="M16 4.5h-4.5a2 2 0 0 0-2 2v9a2 2 0 0 1 2-2H16z" />
    </>
  ),
  activity: <path d="M2.5 10h3l2-5 3 10 2.5-5h4.5" />,
  terminal: (
    <>
      <path d="M3.5 4.5h13v11h-13z" />
      <path d="M6.5 8l2 2-2 2M10.5 12.5h3" />
    </>
  ),
  check: <path d="M4.5 10.5l3.5 3.5 7.5-8" />,
  alert: (
    <>
      <path d="M10 3.5 17.5 16.5h-15z" />
      <path d="M10 8v3.5M10 14h.01" />
    </>
  ),
  x: <path d="M5.5 5.5l9 9M14.5 5.5l-9 9" />,
  chevron: <path d="M8 5l5 5-5 5" />,
  chevronDown: <path d="M5 8l5 5 5-5" />,
  search: (
    <>
      <circle cx="8.5" cy="8.5" r="4.5" />
      <path d="M12 12l4 4" />
    </>
  ),
  panel: (
    <>
      <path d="M3.5 4.5h13v11h-13z" />
      <path d="M8.5 4.5v11" />
    </>
  ),
  download: <path d="M10 3.5v9M6 9l4 4 4-4M4 16.5h12" />,
  play: <path d="M7 4.5l8 5.5-8 5.5z" />,
  pause: <path d="M7.5 4.5v11M12.5 4.5v11" />,
  refresh: (
    <>
      <path d="M16 10a6 6 0 1 1-1.8-4.3" />
      <path d="M16.5 3.5v3h-3" />
    </>
  ),
  plus: <path d="M10 5v10M5 10h10" />,
  copy: (
    <>
      <rect x="7.5" y="7.5" width="9" height="9" rx="1.5" />
      <path d="M12.5 7.5v-2a1.5 1.5 0 0 0-1.5-1.5H5A1.5 1.5 0 0 0 3.5 5.5v6A1.5 1.5 0 0 0 5 13h2" />
    </>
  ),
  external: (
    <>
      <path d="M9 4.5H4.5v11h11V11" />
      <path d="M12 4.5h3.5V8M15.5 4.5 9.5 10.5" />
    </>
  ),
  clock: (
    <>
      <circle cx="10" cy="10" r="6.5" />
      <path d="M10 6.5V10l2.5 1.5" />
    </>
  ),
} as const;

export type IconName = keyof typeof PATHS;

export function Icon({
  name,
  className = "h-5 w-5",
  strokeWidth = 1.7,
  ...rest
}: { name: IconName; strokeWidth?: number } & SVGProps<SVGSVGElement>) {
  return (
    <svg
      viewBox="0 0 20 20"
      fill="none"
      stroke="currentColor"
      strokeWidth={strokeWidth}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      className={className}
      {...rest}
    >
      {PATHS[name]}
    </svg>
  );
}

import type { SVGProps } from "react";

/** Inline stroke icon set (feather-style, 24 viewBox, currentColor). */
const ICON_PATHS = {
  activity: <path d="M3 12h4l2.5-7 4.5 14 2.5-7H21" />,
  "arrow-left": (
    <>
      <path d="M19 12H5" />
      <path d="m11 6-6 6 6 6" />
    </>
  ),
  "arrow-right": (
    <>
      <path d="M5 12h14" />
      <path d="m13 6 6 6-6 6" />
    </>
  ),
  "arrow-up": (
    <>
      <path d="M12 19V5" />
      <path d="m6 11 6-6 6 6" />
    </>
  ),
  alert: (
    <>
      <path d="M12 4 21 19H3L12 4z" />
      <path d="M12 10v4" />
      <path d="M12 16.6v.01" />
    </>
  ),
  book: (
    <>
      <path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20" />
      <path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z" />
    </>
  ),
  check: <path d="M5 12.5l4.5 4.5L19 7.5" />,
  pencil: <path d="M17 3.5 20.5 7 8 19.5 3.5 20.5 4.5 16 17 3.5z" />,
  brush: (
    <>
      <path d="M20 4 10.5 13.5" />
      <path d="M9 14.5c-1.8.4-2.6 1.6-3 3.5-.3 1.4-1 2-2.5 2 1 1.5 2.5 2 4 1.5 1.8-.6 2.6-2 3-3.5" />
    </>
  ),
  eraser: (
    <>
      <path d="M7.5 20.5H21" />
      <path d="m5 16 9.5-9.5a2 2 0 0 1 2.8 0l3.2 3.2a2 2 0 0 1 0 2.8L14 19H8l-3-3z" />
    </>
  ),
  chevron: <path d="M9 5l7 7-7 7" />,
  clock: (
    <>
      <circle cx="12" cy="12" r="8.5" />
      <path d="M12 7.5V12l3 2" />
    </>
  ),
  crosshair: (
    <>
      <circle cx="12" cy="12" r="7.5" />
      <path d="M12 2v4M12 18v4M2 12h4M18 12h4" />
    </>
  ),
  cube: (
    <>
      <path d="M21 8.2 12 3 3 8.2v7.6L12 21l9-5.2V8.2z" />
      <path d="M3 8.2l9 5.2 9-5.2" />
      <path d="M12 13.4V21" />
    </>
  ),
  download: (
    <>
      <path d="M12 3v12" />
      <path d="m7 10 5 5 5-5" />
      <path d="M4 20h16" />
    </>
  ),
  film: (
    <>
      <rect x="3.5" y="4" width="17" height="16" rx="2" />
      <path d="M7 4v16M17 4v16M3.5 9H7M3.5 15H7M17 9h3.5M17 15h3.5" />
    </>
  ),
  flame: (
    <>
      <path d="M12.5 21c4.1 0 6.5-2.9 6.5-6.3 0-2.6-1.5-4.7-3.2-6.4-.5 1.5-1.3 2.4-2.4 3.1.2-3.1-1.3-5.7-3.9-7.4.2 3-1.1 4.8-2.8 6.6-1.3 1.4-1.7 2.8-1.7 4.1C5 18.1 7.4 21 12.5 21z" />
      <path d="M9.5 17.5c0-1.8 1.4-3 2.5-4.5 1 1.5 2.5 2.7 2.5 4.5a2.5 2.5 0 0 1-5 0z" />
    </>
  ),
  gauge: (
    <>
      <path d="M4.5 14a7.5 7.5 0 1 1 15 0" />
      <path d="M12 14l3.8-4.2" />
      <path d="M12 14v.01" />
    </>
  ),
  grid: (
    <>
      <rect x="4" y="4" width="7" height="7" rx="1" />
      <rect x="13" y="4" width="7" height="7" rx="1" />
      <rect x="4" y="13" width="7" height="7" rx="1" />
      <rect x="13" y="13" width="7" height="7" rx="1" />
    </>
  ),
  layers: (
    <>
      <path d="M12 3.5 21 8.5l-9 5-9-5 9-5z" />
      <path d="m4.5 12.5 7.5 4.2 7.5-4.2" />
      <path d="m4.5 16.5 7.5 4.2 7.5-4.2" />
    </>
  ),
  package: (
    <>
      <path d="M21 8.2 12 3 3 8.2v7.6L12 21l9-5.2V8.2z" />
      <path d="M3.3 8.1 12 13l8.7-4.9" />
      <path d="M12 13v8" />
    </>
  ),
  panel: (
    <>
      <rect x="3.5" y="4.5" width="17" height="15" rx="2" />
      <path d="M9.5 4.5v15" />
    </>
  ),
  play: <path d="M8 5.5v13l10-6.5-10-6.5z" />,
  pause: <path d="M9 5v14M15 5v14" />,
  refresh: (
    <>
      <path d="M21 4v6h-6" />
      <path d="M20.5 13a8.5 8.5 0 1 1-2-7.5L21 8" />
    </>
  ),
  search: (
    <>
      <circle cx="11" cy="11" r="7" />
      <path d="M20.5 20.5 16 16" />
    </>
  ),
  spark: (
    <path d="M12 3c.6 3.9 2.1 5.4 6 6-3.9.6-5.4 2.1-6 6-.6-3.9-2.1-5.4-6-6 3.9-.6 5.4-2.1 6-6z" />
  ),
  terminal: <path d="M4 17.5l5.5-5.5L4 6.5M12.5 19H20" />,
  trash: (
    <>
      <path d="M4.5 7h15" />
      <path d="M9.5 7V4.5h5V7" />
      <path d="M6.5 7l1 13.5h9L17.5 7" />
      <path d="M10 11v6M14 11v6" />
    </>
  ),
  image: (
    <>
      <rect x="3.5" y="4.5" width="17" height="15" rx="2" />
      <circle cx="9" cy="10" r="1.6" />
      <path d="M3.5 17.5 9 12.5l4 3.5 3-2.5 4.5 4" />
    </>
  ),
  info: (
    <>
      <circle cx="12" cy="12" r="8.5" />
      <path d="M12 11v5M12 8v.01" />
    </>
  ),
  key: (
    <>
      <circle cx="7.5" cy="16.5" r="3.8" />
      <path d="M10.2 13.8 20 4" />
      <path d="M15.5 8.5 18 11" />
      <path d="M18.5 5.5 21 8" />
    </>
  ),
  shield: (
    <>
      <path d="M12 3 19 6v5c0 4.4-2.8 7.7-7 10-4.2-2.3-7-5.6-7-10V6l7-3z" />
      <path d="M9 12.5 11 15l4-5" />
    </>
  ),
  zap: <path d="M13 2 3 14h9l-1 8 10-12h-9l1-8z" />,
  x: <path d="M6 6l12 12M18 6 6 18" />,
} as const;

export type IconName = keyof typeof ICON_PATHS;

export function Icon({ name, className, ...rest }: { name: IconName } & SVGProps<SVGSVGElement>) {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.8"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      className={className}
      {...rest}
    >
      {ICON_PATHS[name]}
    </svg>
  );
}

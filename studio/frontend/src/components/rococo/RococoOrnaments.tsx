import type { ReactNode, SVGProps } from "react";
import "./rococo.css";

type SvgProps = SVGProps<SVGSVGElement>;

function cx(...parts: Array<string | false | null | undefined>) {
  return parts.filter(Boolean).join(" ");
}

export function RococoDivider({ className, ...rest }: SvgProps) {
  return (
    <svg
      viewBox="0 0 240 24"
      fill="none"
      aria-hidden="true"
      className={cx("cf-rococo-divider", className)}
      {...rest}
    >
      <g stroke="currentColor" strokeWidth="0.9" strokeLinecap="round">
        <path d="M3 12h58c13 0 20-7 30-7 8 0 13 4 17 7" />
        <path d="M237 12h-58c-13 0-20-7-30-7-8 0-13 4-17 7" />
        <path d="M22 12c13 0 18-4 28-4 7 0 11 2 14 4" />
        <path d="M218 12c-13 0-18-4-28-4-7 0-11 2-14 4" />
        <path d="M86 12c8 0 12-3 18-3 6 0 10 2 13 3" />
        <path d="M154 12c-8 0-12-3-18-3-6 0-10 2-13 3" />
      </g>
      <path d="m120 2 3.1 6.7 6.9 1.3-6.9 1.3L120 18l-3.1-6.7L110 10l6.9-1.3L120 2Z" fill="currentColor" />
      <circle cx="120" cy="20" r="1.25" fill="currentColor" />
    </svg>
  );
}

export function RococoFleuron({ className, ...rest }: SvgProps) {
  return (
    <svg
      viewBox="0 0 32 24"
      fill="none"
      aria-hidden="true"
      className={cx("cf-rococo-fleuron", className)}
      {...rest}
    >
      <g stroke="currentColor" strokeWidth="1" strokeLinecap="round">
        <path d="M2 12h7c3.5 0 5.5-4 9-4 2.2 0 3.8 1.4 5 4" />
        <path d="M30 12h-7c-3.5 0-5.5-4-9-4-2.2 0-3.8 1.4-5 4" />
        <path d="M11 17c3-1 4-3.5 5-6" />
        <path d="M21 17c-3-1-4-3.5-5-6" />
      </g>
      <circle cx="16" cy="12" r="2" fill="currentColor" />
    </svg>
  );
}

export function RococoCorner({ className, ...rest }: SvgProps) {
  return (
    <svg
      viewBox="0 0 120 120"
      fill="none"
      aria-hidden="true"
      className={cx("cf-rococo-corner", className)}
      {...rest}
    >
      <g stroke="currentColor" strokeWidth="1.05" strokeLinecap="round" strokeLinejoin="round">
        <path d="M5 115V29C5 15 15 5 29 5h86" />
        <path d="M17 97V40c0-13 11-24 24-24h56" strokeDasharray="3 4.5" opacity="0.72" />
        <path d="M29 46c0-10 8-18 18-18s18 8 18 18c0 9-7 17-16 17-7 0-13-5-13-12 0-6 4-10 9-10 4 0 7 2 7 6" />
        <path d="M64 8c-8 8-9 19-2 25 7 5 16 2 18-7 1-6-3-11-9-14" />
        <path d="M9 72c12 0 22 10 22 23v20" />
        <path d="M44 8c3 4 4 8 2 12M8 45c4-2 8-2 12 1" opacity="0.78" />
      </g>
      <circle cx="75" cy="35" r="1.8" fill="currentColor" />
      <path d="M64 64c5 2 8 5 9 10" stroke="currentColor" strokeWidth="1" strokeLinecap="round" />
    </svg>
  );
}

export function RococoCrest({ className, ...rest }: SvgProps) {
  return (
    <svg
      viewBox="0 0 64 72"
      fill="none"
      aria-hidden="true"
      className={cx("cf-rococo-crest", className)}
      {...rest}
    >
      <path
        d="M32 3C20 3 11 12 11 23v10c0 14 9 24 21 34 12-10 21-20 21-34V23C53 12 44 3 32 3Z"
        stroke="currentColor"
        strokeWidth="1.1"
      />
      <path
        d="M32 9c-7 0-13 6-13 14v9c0 10 6 18 13 24 7-6 13-14 13-24v-9c0-8-6-14-13-14Z"
        stroke="currentColor"
        strokeWidth="0.8"
        strokeDasharray="2 3"
      />
      <path
        d="M12 22c-5-3-9-2-10 1 2 4 6 5 10 3M52 22c5-3 9-2 10 1-2 4-6 5-10 3M12 48c-5-3-9-2-10 1 2 4 6 5 10 3M52 48c5-3 9-2 10 1-2 4-6 5-10 3"
        stroke="currentColor"
        strokeWidth="0.9"
        strokeLinecap="round"
      />
      <text
        x="32"
        y="39"
        textAnchor="middle"
        fill="currentColor"
        fontFamily="var(--font-display)"
        fontSize="17"
        fontWeight="600"
        letterSpacing="-1"
      >
        CF
      </text>
    </svg>
  );
}

export function RococoFrame({
  children,
  className,
  contentClassName,
  corners = true,
}: {
  children?: ReactNode;
  className?: string;
  contentClassName?: string;
  corners?: boolean;
}) {
  return (
    <div className={cx("cf-rococo-frame", className)}>
      <svg
        viewBox="0 0 1000 620"
        preserveAspectRatio="none"
        fill="none"
        aria-hidden="true"
        className="cf-rococo-frame__lines"
      >
        <path
          d="M20 20H420C450 20 460 6 500 6C540 6 550 20 580 20H980C990 20 996 26 996 36V584C996 594 990 600 980 600H20C10 600 4 594 4 584V36C4 26 10 20 20 20Z"
          stroke="currentColor"
          strokeWidth="1.15"
          vectorEffect="non-scaling-stroke"
          className="cf-rococo-frame__line"
        />
        <path
          d="M28 28H424C452 28 462 16 500 16C538 16 548 28 576 28H972C980 28 985 33 985 40V576C985 583 980 588 972 588H28C20 588 15 583 15 576V40C15 33 20 28 28 28Z"
          stroke="currentColor"
          strokeWidth="0.8"
          strokeDasharray="4 5"
          opacity="0.68"
          vectorEffect="non-scaling-stroke"
          className="cf-rococo-frame__line cf-rococo-frame__line--inner"
        />
        <path d="M470 6h-24M530 6h24" stroke="currentColor" strokeWidth="0.9" />
        <circle cx="500" cy="2" r="3.5" stroke="currentColor" strokeWidth="1" fill="var(--color-paper)" />
        <path d="M500 5v4" stroke="currentColor" strokeWidth="0.9" />
      </svg>
      {corners && (
        <>
          <RococoCorner className="cf-rococo-corner--tl" />
          <RococoCorner className="cf-rococo-corner--tr" />
          <RococoCorner className="cf-rococo-corner--br" />
          <RococoCorner className="cf-rococo-corner--bl" />
        </>
      )}
      <div className={cx("relative z-10", contentClassName)}>{children}</div>
    </div>
  );
}

export function RococoRibbon({ children, className }: { children: ReactNode; className?: string }) {
  return <span className={cx("cf-rococo-ribbon", className)}>{children}</span>;
}

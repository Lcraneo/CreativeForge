import { motion } from "framer-motion";
import {
  useId,
  type ButtonHTMLAttributes,
  type InputHTMLAttributes,
  type ReactNode,
  type SelectHTMLAttributes,
  type TextareaHTMLAttributes,
} from "react";
import { Icon, type IconName } from "./icons";

export function cx(...parts: Array<string | false | null | undefined>) {
  return parts.filter(Boolean).join(" ");
}

/* ------------------------------------------------------------------ */
/* Button                                                              */
/* ------------------------------------------------------------------ */

type ButtonVariant = "primary" | "ember" | "secondary" | "ghost" | "danger";
type ButtonSize = "sm" | "md" | "lg";

const BUTTON_VARIANTS: Record<ButtonVariant, string> = {
  primary:
    "bg-primary text-[#05121c] hover:bg-primary-hover active:bg-primary-active shadow-[0_0_20px_-6px_rgba(76,194,255,.55)]",
  ember:
    "bg-gradient-to-br from-ember to-[#ff7a6b] text-[#1c0f04] shadow-[0_0_22px_-6px_rgba(255,180,84,.55)] hover:brightness-110",
  secondary:
    "bg-surface-2 border border-line text-ink hover:bg-surface-3 hover:border-line-strong",
  ghost: "text-ink-2 hover:bg-surface-2 hover:text-ink",
  danger:
    "bg-danger/15 border border-danger/40 text-danger hover:bg-danger/25",
};

const BUTTON_SIZES: Record<ButtonSize, string> = {
  sm: "h-8 px-3 text-xs",
  md: "h-[34px] px-4 text-[13px]",
  lg: "h-10 px-5 text-sm",
};

export function Button({
  variant = "secondary",
  size = "md",
  icon,
  loading = false,
  className,
  children,
  disabled,
  ...rest
}: {
  variant?: ButtonVariant;
  size?: ButtonSize;
  icon?: IconName;
  loading?: boolean;
  children?: ReactNode;
} & ButtonHTMLAttributes<HTMLButtonElement>) {
  return (
    <button
      type="button"
      disabled={disabled || loading}
      className={cx(
        "inline-flex select-none items-center justify-center gap-2 whitespace-nowrap rounded-md font-semibold transition-all duration-150 ease-standard active:translate-y-px disabled:pointer-events-none disabled:opacity-45",
        BUTTON_VARIANTS[variant],
        BUTTON_SIZES[size],
        className,
      )}
      {...rest}
    >
      {loading ? <Spinner /> : icon ? <Icon name={icon} className="h-4 w-4" /> : null}
      {children}
    </button>
  );
}

export function IconButton({
  icon,
  label,
  className,
  ...rest
}: { icon: IconName; label: string } & ButtonHTMLAttributes<HTMLButtonElement>) {
  return (
    <button
      type="button"
      aria-label={label}
      title={label}
      className={cx(
        "grid h-8 w-8 place-items-center rounded-md border border-line-subtle bg-surface-1 text-ink-2 transition-colors duration-150 ease-standard hover:border-line hover:text-ink",
        className,
      )}
      {...rest}
    >
      <Icon name={icon} className="h-4 w-4" />
    </button>
  );
}

/* ------------------------------------------------------------------ */
/* Card                                                                */
/* ------------------------------------------------------------------ */

const DOMAIN_BARS = {
  primary: "bg-primary",
  ember: "bg-ember",
  supervisor: "bg-supervisor",
  precon: "bg-precon",
  falign: "bg-falign",
  gimport: "bg-gimport",
  qa: "bg-qa",
  memory: "bg-memory",
} as const;

export function Card({
  title,
  right,
  icon,
  iconClassName,
  domain,
  className,
  bodyClassName,
  interactive = false,
  children,
}: {
  title?: ReactNode;
  right?: ReactNode;
  icon?: IconName;
  iconClassName?: string;
  domain?: keyof typeof DOMAIN_BARS;
  className?: string;
  bodyClassName?: string;
  interactive?: boolean;
  children: ReactNode;
}) {
  return (
    <section
      className={cx(
        "cf-sheen relative overflow-hidden rounded-xl border border-line-subtle bg-gradient-to-b from-[#10151d] to-[#0d1118]",
        interactive &&
          "transition-all duration-150 ease-standard hover:-translate-y-px hover:border-line",
        className,
      )}
    >
      {domain && (
        <span
          className={cx("absolute inset-y-0 left-0 w-[3px]", DOMAIN_BARS[domain])}
        />
      )}
      {(title || right) && (
        <header className="flex items-center justify-between gap-3 border-b border-white/[.045] px-[18px] py-[13px]">
          <div className="flex min-w-0 items-center gap-2.5">
            {icon && (
              <Icon name={icon} className={cx("h-4 w-4 shrink-0 text-primary", iconClassName)} />
            )}
            <h3 className="truncate text-[15px] font-semibold leading-[22px]">{title}</h3>
          </div>
          {right}
        </header>
      )}
      <div className={cx("p-[18px]", bodyClassName)}>{children}</div>
    </section>
  );
}

export function PageHeader({
  overline,
  title,
  description,
  actions,
}: {
  overline?: string;
  title: string;
  description?: ReactNode;
  actions?: ReactNode;
}) {
  return (
    <div className="flex flex-wrap items-end justify-between gap-4">
      <div className="min-w-0">
        {overline && (
          <div className="mb-1 text-[11px] font-semibold uppercase tracking-[0.08em] text-ink-3">
            {overline}
          </div>
        )}
        <h1 className="text-2xl font-semibold leading-8 tracking-[-0.01em]">{title}</h1>
        {description && (
          <p className="mt-1 max-w-3xl text-[13px] leading-5 text-ink-3">{description}</p>
        )}
      </div>
      {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* Badge / Dot / Chip                                                  */
/* ------------------------------------------------------------------ */

export type Tone =
  | "neutral"
  | "primary"
  | "success"
  | "warning"
  | "danger"
  | "precon"
  | "falign"
  | "gimport"
  | "ember";

const BADGE_TONES: Record<Tone, string> = {
  neutral: "bg-white/[.06] text-ink-2",
  primary: "bg-primary/15 text-primary",
  success: "bg-success/15 text-success",
  warning: "bg-warning/15 text-warning",
  danger: "bg-danger/15 text-danger",
  precon: "bg-precon/15 text-precon",
  falign: "bg-falign/15 text-falign",
  gimport: "bg-gimport/15 text-gimport",
  ember: "bg-ember/15 text-ember",
};

export function Badge({
  tone = "neutral",
  icon,
  children,
  className,
}: {
  tone?: Tone;
  icon?: IconName;
  children: ReactNode;
  className?: string;
}) {
  return (
    <span
      className={cx(
        "inline-flex h-[22px] items-center gap-1.5 whitespace-nowrap rounded-sm px-2 text-xs font-medium",
        BADGE_TONES[tone],
        className,
      )}
    >
      {icon && <Icon name={icon} className="h-3.5 w-3.5" />}
      {children}
    </span>
  );
}

const DOT_TONES: Record<string, string> = {
  idle: "bg-ink-4 shadow-[0_0_0_4px_rgba(76,87,104,.15)]",
  running: "bg-primary animate-pulse-run",
  success: "bg-success shadow-[0_0_0_4px_rgba(52,211,153,.14)]",
  failed: "bg-danger shadow-[0_0_0_4px_rgba(251,113,133,.13)]",
  warning: "bg-warning shadow-[0_0_0_4px_rgba(251,191,36,.13)]",
};

export function StatusDot({
  tone = "idle",
  className,
}: {
  tone?: keyof typeof DOT_TONES | "recovered";
  className?: string;
}) {
  const key = tone === "recovered" ? "success" : tone;
  return <span className={cx("inline-block h-2 w-2 shrink-0 rounded-full", DOT_TONES[key], className)} />;
}

export function Chip({
  active = false,
  icon,
  children,
  className,
  ...rest
}: { active?: boolean; icon?: IconName; children: ReactNode } & ButtonHTMLAttributes<HTMLButtonElement>) {
  return (
    <button
      type="button"
      className={cx(
        "inline-flex h-8 select-none items-center gap-2 rounded-full border px-3 text-[12.5px] transition-colors duration-150 ease-standard",
        active
          ? "border-primary/45 bg-primary-tint text-primary"
          : "border-line-subtle bg-surface-1 text-ink-2 hover:border-line hover:text-ink",
        className,
      )}
      {...rest}
    >
      {icon && <Icon name={icon} className="h-4 w-4" />}
      {children}
    </button>
  );
}

/* ------------------------------------------------------------------ */
/* Inputs                                                              */
/* ------------------------------------------------------------------ */

export function Input({
  icon,
  className,
  ...rest
}: { icon?: IconName } & InputHTMLAttributes<HTMLInputElement>) {
  return (
    <label
      className={cx(
        "flex h-9 items-center gap-2.5 rounded-md border border-line bg-surface-2 px-3 transition-all duration-150 ease-standard focus-within:border-primary focus-within:shadow-[0_0_0_3px_rgba(76,194,255,.12)]",
        className,
      )}
    >
      {icon && <Icon name={icon} className="h-4 w-4 shrink-0 text-ink-3" />}
      <input
        className="min-w-0 flex-1 bg-transparent text-[13px] text-ink outline-none placeholder:text-ink-4"
        {...rest}
      />
    </label>
  );
}

export function Textarea({
  className,
  ...rest
}: TextareaHTMLAttributes<HTMLTextAreaElement>) {
  return (
    <textarea
      className={cx(
        "w-full resize-none rounded-[10px] border border-line bg-[#0a0e15] px-4 py-3.5 text-sm leading-6 text-ink outline-none transition-all duration-150 ease-standard placeholder:text-ink-4 focus:border-primary focus:shadow-[0_0_0_3px_rgba(76,194,255,.12)]",
        className,
      )}
      {...rest}
    />
  );
}

export function Select({
  options,
  className,
  ...rest
}: {
  options: Array<{ value: string; label: string }>;
} & SelectHTMLAttributes<HTMLSelectElement>) {
  return (
    <select
      className={cx(
        "h-9 w-full appearance-none rounded-md border border-line bg-surface-2 bg-[url('data:image/svg+xml;utf8,<svg xmlns=%22http://www.w3.org/2000/svg%22 viewBox=%220 0 20 20%22 fill=%22none%22 stroke=%22%2376839a%22 stroke-width=%221.7%22><path d=%22M5 8l5 5 5-5%22/></svg>')] bg-[length:16px] bg-[right_10px_center] bg-no-repeat px-3 pr-8 text-[13px] text-ink outline-none transition-all duration-150 ease-standard focus:border-primary focus:shadow-[0_0_0_3px_rgba(76,194,255,.12)]",
        className,
      )}
      {...rest}
    >
      {options.map((option) => (
        <option key={option.value} value={option.value} className="bg-surface-1">
          {option.label}
        </option>
      ))}
    </select>
  );
}

export function Switch({
  checked,
  onChange,
  label,
}: {
  checked: boolean;
  onChange: (checked: boolean) => void;
  label?: string;
}) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      aria-label={label}
      onClick={() => onChange(!checked)}
      className={cx(
        "relative h-5 w-9 shrink-0 rounded-full border transition-colors duration-150 ease-standard",
        checked ? "border-primary bg-primary/30" : "border-line bg-surface-3",
      )}
    >
      <span
        className={cx(
          "absolute top-0.5 h-3.5 w-3.5 rounded-full transition-all duration-150 ease-standard",
          checked ? "left-[18px] bg-primary" : "left-0.5 bg-ink-3",
        )}
      />
    </button>
  );
}

/* ------------------------------------------------------------------ */
/* Segmented / Tabs                                                    */
/* ------------------------------------------------------------------ */

export function Segmented<T extends string>({
  options,
  value,
  onChange,
  className,
}: {
  options: Array<{ id: T; label: string; icon?: IconName }>;
  value: T;
  onChange: (value: T) => void;
  className?: string;
}) {
  return (
    <div
      role="tablist"
      className={cx(
        "inline-flex items-center gap-1 rounded-[10px] border border-line-subtle bg-surface-2 p-1",
        className,
      )}
    >
      {options.map((option) => (
        <button
          key={option.id}
          role="tab"
          aria-selected={value === option.id}
          onClick={() => onChange(option.id)}
          className={cx(
            "flex h-7 select-none items-center gap-1.5 rounded-[7px] px-3.5 text-[12.5px] transition-colors duration-150 ease-standard",
            value === option.id
              ? "bg-surface-3 font-semibold text-ink shadow-[inset_0_1px_0_rgba(255,255,255,.07)]"
              : "text-ink-2 hover:text-ink",
          )}
        >
          {option.icon && <Icon name={option.icon} className="h-4 w-4" />}
          {option.label}
        </button>
      ))}
    </div>
  );
}

export function Tabs({
  items,
  value,
  onChange,
  className,
}: {
  items: Array<{ id: string; label: string; count?: number }>;
  value: string;
  onChange: (id: string) => void;
  className?: string;
}) {
  return (
    <div className={cx("flex gap-5 border-b border-line-subtle", className)}>
      {items.map((item) => (
        <button
          key={item.id}
          onClick={() => onChange(item.id)}
          className={cx(
            "relative pb-2.5 pt-2 text-[13px] transition-colors duration-150 ease-standard",
            value === item.id ? "font-semibold text-ink" : "text-ink-3 hover:text-ink-2",
          )}
        >
          {item.label}
          {item.count !== undefined && (
            <span className="ml-1.5 font-mono text-[10.5px] text-ink-4">{item.count}</span>
          )}
          {value === item.id && (
            <span className="absolute inset-x-0 -bottom-px h-0.5 rounded-sm bg-primary" />
          )}
        </button>
      ))}
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* Data display                                                        */
/* ------------------------------------------------------------------ */

const SCORE_FILLS: Record<string, string> = {
  primary: "bg-primary",
  success: "bg-gradient-to-r from-[#2fbfe0] to-success",
  danger: "bg-gradient-to-r from-warning to-danger",
  precon: "bg-gradient-to-r from-[#1e9fbd] to-precon",
  falign: "bg-gradient-to-r from-[#7c5cff] to-falign",
  gimport: "bg-gradient-to-r from-[#1f9d75] to-gimport",
  ember: "bg-gradient-to-r from-ember to-[#ff7a6b]",
};

export function ScoreBar({
  label,
  value,
  threshold,
  tone = "auto",
  format = (v: number) => `${Math.round(v * 100)}%`,
  className,
}: {
  label: ReactNode;
  value: number;
  threshold?: number;
  tone?: keyof typeof SCORE_FILLS | "auto";
  format?: (value: number) => string;
  className?: string;
}) {
  const percent = Math.max(0, Math.min(100, value * 100));
  const fill =
    tone === "auto"
      ? threshold === undefined || value >= threshold
        ? "success"
        : "danger"
      : tone;
  return (
    <div className={className}>
      <div className="mb-[6px] flex items-baseline justify-between gap-3 text-xs">
        <span className="min-w-0 truncate text-ink-2">{label}</span>
        <span className="tabular shrink-0 font-mono text-[12.5px] text-ink">{format(value)}</span>
      </div>
      <div className="relative h-1.5 rounded-full bg-surface-3">
        <motion.div
          className={cx("h-1.5 rounded-full", SCORE_FILLS[fill])}
          initial={{ width: 0 }}
          animate={{ width: `${percent}%` }}
          transition={{ duration: 0.5, ease: [0.2, 0.8, 0.2, 1] }}
        />
        {threshold !== undefined && (
          <span
            className="absolute -top-[3px] -bottom-[3px] w-0.5 rounded-sm bg-ink-3"
            style={{ left: `${Math.min(100, threshold * 100)}%` }}
            title={`阈值 ${threshold}`}
          />
        )}
      </div>
    </div>
  );
}

export function ScoreRing({
  value,
  label,
  size = 132,
  thickness = 10,
  format = (v: number) => `${Math.round(v * 100)}`,
}: {
  value: number;
  label?: string;
  size?: number;
  thickness?: number;
  format?: (value: number) => string;
}) {
  const id = useId().replace(/:/g, "");
  const radius = (100 - thickness * 2 - 4) / 2;
  const circumference = 2 * Math.PI * radius;
  return (
    <svg viewBox="0 0 100 100" style={{ width: size, height: size }} role="img" aria-label={label}>
      <defs>
        <linearGradient id={`ring-${id}`} x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" stopColor="#4cc2ff" />
          <stop offset="1" stopColor="#8b7bff" />
        </linearGradient>
      </defs>
      <circle
        cx="50"
        cy="50"
        r={radius}
        fill="none"
        stroke="var(--color-surface-3)"
        strokeWidth={thickness}
      />
      <motion.circle
        cx="50"
        cy="50"
        r={radius}
        fill="none"
        stroke={`url(#ring-${id})`}
        strokeWidth={thickness}
        strokeLinecap="round"
        strokeDasharray={circumference}
        initial={{ strokeDashoffset: circumference }}
        animate={{ strokeDashoffset: circumference * (1 - Math.min(1, Math.max(0, value))) }}
        transition={{ duration: 0.8, ease: [0.2, 0.8, 0.2, 1] }}
        transform="rotate(-90 50 50)"
      />
      <text
        x="50"
        y="52"
        textAnchor="middle"
        fill="var(--color-ink)"
        fontSize="22"
        fontFamily="var(--font-mono)"
        fontWeight="700"
      >
        {format(value)}
      </text>
      {label && (
        <text
          x="50"
          y="66"
          textAnchor="middle"
          fill="var(--color-ink-3)"
          fontSize="7.5"
          fontFamily="var(--font-sans)"
        >
          {label}
        </text>
      )}
    </svg>
  );
}

export function KV({
  label,
  value,
  mono = true,
}: {
  label: ReactNode;
  value: ReactNode;
  mono?: boolean;
}) {
  return (
    <div className="flex items-baseline justify-between gap-4 border-b border-white/[.05] py-2 text-[12.5px] last:border-b-0">
      <span className="shrink-0 text-ink-3">{label}</span>
      <span
        className={cx("min-w-0 truncate text-right text-ink", mono && "font-mono tabular")}
        title={typeof value === "string" ? value : undefined}
      >
        {value}
      </span>
    </div>
  );
}

export function Stat({
  label,
  value,
  hint,
  tone,
  icon,
  chart,
  className,
}: {
  label: ReactNode;
  value: ReactNode;
  hint?: ReactNode;
  tone?: string;
  icon?: IconName;
  chart?: ReactNode;
  className?: string;
}) {
  return (
    <div className={cx("flex min-w-0 flex-col gap-0.5", className)}>
      <div className="flex items-center gap-1.5 text-xs text-ink-3">
        {icon && <Icon name={icon} className="h-3.5 w-3.5" />}
        <span className="truncate">{label}</span>
      </div>
      <div className={cx("tabular text-[32px] font-semibold leading-10 tracking-[-0.02em]", tone)}>
        {value}
      </div>
      {chart}
      {hint && <div className="text-[11px] text-ink-3">{hint}</div>}
    </div>
  );
}

export function Stepper({
  steps,
  className,
}: {
  steps: Array<{ id: string; label: string; state: "done" | "running" | "pending" | "failed" }>;
  className?: string;
}) {
  const iconOf = (state: string) =>
    state === "done" ? "check" : state === "failed" ? "x" : state === "running" ? "refresh" : "clock";
  const colorOf = (state: string) =>
    state === "done"
      ? "border-success bg-success/10 text-success"
      : state === "running"
        ? "border-primary bg-primary-tint text-primary shadow-[0_0_0_4px_rgba(76,194,255,.1)]"
        : state === "failed"
          ? "border-danger bg-danger/10 text-danger"
          : "border-line bg-surface-1 text-ink-4";
  return (
    <div className={cx("flex flex-wrap items-center", className)}>
      {steps.map((step, index) => (
        <div key={step.id} className="flex items-center">
          <div
            className={cx(
              "flex items-center gap-2.5 text-[12.5px]",
              step.state === "pending" ? "text-ink-3" : "text-ink-2",
            )}
          >
            <span
              className={cx(
                "grid h-[26px] w-[26px] shrink-0 place-items-center rounded-full border-[1.5px]",
                colorOf(step.state),
              )}
            >
              <Icon name={iconOf(step.state)} className="h-3.5 w-3.5" />
            </span>
            <span className={cx(step.state === "running" && "font-semibold text-ink")}>
              {step.label}
            </span>
          </div>
          {index < steps.length - 1 && (
            <span
              className={cx(
                "mx-2 h-0.5 w-5 rounded-sm",
                step.state === "done" ? "bg-success/50" : "bg-line-subtle",
              )}
            />
          )}
        </div>
      ))}
    </div>
  );
}

export function Spinner({ className }: { className?: string }) {
  return (
    <span
      className={cx(
        "inline-block h-3.5 w-3.5 animate-spin-slow rounded-full border-2 border-current border-t-transparent",
        className,
      )}
    />
  );
}

export function Skeleton({ className }: { className?: string }) {
  return (
    <div
      className={cx(
        "animate-shimmer rounded-sm bg-surface-2 bg-[linear-gradient(90deg,var(--color-surface-2)_25%,var(--color-surface-3)_50%,var(--color-surface-2)_75%)] bg-[length:200%_100%]",
        className,
      )}
    />
  );
}

export function EmptyState({
  icon = "cube",
  title,
  description,
  action,
  className,
}: {
  icon?: IconName;
  title: ReactNode;
  description?: ReactNode;
  action?: ReactNode;
  className?: string;
}) {
  return (
    <div className={cx("flex flex-col items-center gap-2.5 px-5 py-11 text-center", className)}>
      <span className="grid h-11 w-11 place-items-center rounded-xl bg-primary-tint text-primary">
        <Icon name={icon} className="h-5 w-5" />
      </span>
      <div className="text-[15px] font-semibold">{title}</div>
      {description && (
        <p className="max-w-sm text-[12.5px] leading-[19px] text-ink-3">{description}</p>
      )}
      {action && <div className="mt-1">{action}</div>}
    </div>
  );
}

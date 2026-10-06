import { motion } from "framer-motion";
import {
  useId,
  useState,
  type ButtonHTMLAttributes,
  type ImgHTMLAttributes,
  type InputHTMLAttributes,
  type ReactNode,
  type SelectHTMLAttributes,
  type TextareaHTMLAttributes,
} from "react";
import { Icon, type IconName } from "./icons";
import { MOTION, EASE_STANDARD } from "../lib/motion";

export function cx(...parts: Array<string | false | null | undefined>) {
  return parts.filter(Boolean).join(" ");
}

/* ------------------------------------------------------------------ */
/* Button                                                              */
/* ------------------------------------------------------------------ */

type ButtonVariant = "primary" | "ember" | "secondary" | "ghost" | "danger";
type ButtonSize = "sm" | "md" | "lg";

const BUTTON_VARIANTS: Record<ButtonVariant, string> = {
  /* 墨锭按钮：实底 + 顶部内高光，像一块被磨亮的墨 */
  primary:
    "bg-primary text-canvas hover:bg-primary-hover active:bg-primary-active shadow-[0_6px_16px_-8px_rgba(26,24,20,.55),inset_0_1px_0_rgba(255,255,255,.14)]",
  ember:
    "bg-gradient-to-br from-ember to-[#c46a3a] text-[#fdfcf9] shadow-[0_6px_16px_-8px_rgba(169,129,47,.6),inset_0_1px_0_rgba(255,255,255,.28)] hover:brightness-110",
  secondary: "bg-surface-2 border border-line text-ink hover:bg-surface-3 hover:border-line-strong",
  ghost: "text-ink-2 hover:bg-surface-2 hover:text-ink",
  danger: "bg-danger/15 border border-danger/40 text-danger hover:bg-danger/25",
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
        // transition 只声明会变的属性（禁 transition-all）；按压 = scale .96 触觉反馈
        "inline-flex select-none items-center justify-center gap-2 whitespace-nowrap rounded-md font-semibold transition-[color,background-color,border-color,box-shadow,transform] duration-(--motion-fast) ease-standard active:scale-[0.96] disabled:pointer-events-none disabled:opacity-45",
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
        "grid h-8 w-8 place-items-center rounded-md border border-line-subtle bg-surface-1 text-ink-2 transition-[color,background-color,border-color,box-shadow,transform] duration-(--motion-fast) ease-standard hover:border-line hover:text-ink active:scale-[0.96]",
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
        "cf-sheen relative overflow-hidden rounded-xl border border-line-subtle bg-gradient-to-b from-[#f0ede6] to-[#ece9e1] shadow-e1",
        interactive &&
          "cf-raise hover:-translate-y-px hover:border-line hover:shadow-e3",
        className,
      )}
    >
      {domain && <span className={cx("absolute inset-y-0 left-0 w-[3px]", DOMAIN_BARS[domain])} />}
      {(title || right) && (
        <header className="flex items-center justify-between gap-3 border-b border-ink/[.08] px-[18px] py-[13px]">
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
    <div className="flex flex-wrap items-end justify-between gap-4 border-b border-line-subtle pb-4">
      <div className="min-w-0">
        {overline && (
          <div className="mb-2 flex items-center gap-2">
            <span className="h-1.5 w-1.5 shrink-0 rotate-45 rounded-[1px] bg-ember" aria-hidden="true" />
            <span className="text-[11px] font-semibold uppercase tracking-[0.14em] text-ink-3">
              {overline}
            </span>
          </div>
        )}
        <h1 className="font-display text-[28px] font-black leading-9 [text-wrap:balance]">{title}</h1>
        {description && (
          <p className="mt-1.5 max-w-3xl text-[13px] leading-5 text-ink-3 [text-wrap:pretty]">{description}</p>
        )}
      </div>
      {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
    </div>
  );
}

/**
 * 印章：方形宋体字，墨印（实底）或朱印（描边）。
 * 全站的"人手迹"符号——品牌、空状态、英雄区点题，克制使用。
 */
export function Stamp({
  char,
  tone = "ink",
  size = 28,
  className,
  title,
}: {
  char: string;
  tone?: "ink" | "ember";
  size?: number;
  className?: string;
  title?: string;
}) {
  return (
    <span
      title={title}
      aria-hidden={!title}
      className={cx(
        "inline-grid shrink-0 select-none place-items-center rounded-[6px] font-display font-black leading-none",
        tone === "ink"
          ? "bg-ink text-canvas shadow-[0_4px_10px_-4px_rgba(26,24,20,.5)]"
          : "border-[1.5px] border-ember bg-ember/[.08] text-ember",
        className,
      )}
      style={{ width: size, height: size, fontSize: Math.round(size * 0.5) }}
    >
      {char}
    </span>
  );
}

/** 小节标题：ember 短竖条 + 宋体黑字 + 可选说明与右侧动作，用于页内分区节奏 */
export function SectionTitle({
  eyebrow,
  title,
  description,
  action,
  className,
}: {
  eyebrow?: string;
  title: ReactNode;
  description?: ReactNode;
  action?: ReactNode;
  className?: string;
}) {
  return (
    <div className={cx("flex flex-wrap items-end justify-between gap-x-4 gap-y-2", className)}>
      <div className="min-w-0">
        {eyebrow && (
          <div className="mb-0.5 text-[10.5px] font-semibold uppercase tracking-[0.12em] text-ink-4">
            {eyebrow}
          </div>
        )}
        <div className="flex items-center gap-2.5">
          <span className="h-2 w-2 shrink-0 rotate-45 rounded-[1px] bg-ember" aria-hidden="true" />
          <h2 className="font-display text-[19px] font-black leading-7">{title}</h2>
        </div>
        {description && <p className="mt-1 max-w-3xl text-xs leading-5 text-ink-3 [text-wrap:pretty]">{description}</p>}
      </div>
      {action && <div className="flex flex-wrap items-center gap-2">{action}</div>}
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
  neutral: "bg-ink/[.06] text-ink-2",
  primary: "bg-primary/15 text-primary",
  success: "bg-success/15 text-success",
  warning: "bg-warning/15 text-[color:var(--color-ember-ink)]",
  danger: "bg-danger/15 text-danger",
  precon: "bg-precon/15 text-precon",
  falign: "bg-falign/15 text-falign",
  gimport: "bg-gimport/15 text-gimport",
  ember: "bg-ember/15 text-[color:var(--color-ember-ink)]",
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
  idle: "bg-ink-4 shadow-[0_0_0_4px_rgba(26,24,20,.12)]",
  running: "bg-primary animate-pulse-run",
  success: "bg-success shadow-[0_0_0_4px_rgba(62,125,90,.16)]",
  failed: "bg-danger shadow-[0_0_0_4px_rgba(169,79,61,.16)]",
  warning: "bg-warning shadow-[0_0_0_4px_rgba(169,129,47,.16)]",
};

export function StatusDot({
  tone = "idle",
  className,
}: {
  tone?: keyof typeof DOT_TONES | "recovered";
  className?: string;
}) {
  const key = tone === "recovered" ? "success" : tone;
  return (
    <span className={cx("inline-block h-2 w-2 shrink-0 rounded-full", DOT_TONES[key], className)} />
  );
}

export function Chip({
  active = false,
  icon,
  children,
  className,
  ...rest
}: {
  active?: boolean;
  icon?: IconName;
  children: ReactNode;
} & ButtonHTMLAttributes<HTMLButtonElement>) {
  return (
    <button
      type="button"
      className={cx(
        "inline-flex h-8 select-none items-center gap-2 rounded-full border px-3 text-[12.5px] transition-[color,background-color,border-color,box-shadow,transform] duration-(--motion-fast) ease-standard active:scale-[0.96]",
        active
          ? "border-primary/45 bg-primary-tint text-primary shadow-[inset_0_1px_0_rgba(255,255,255,.55)]"
          : "border-line-subtle bg-paper text-ink-2 hover:border-line hover:text-ink",
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
        "flex h-9 items-center gap-2.5 rounded-md border border-line bg-surface-2 px-3 transition-[border-color,box-shadow] duration-(--motion-fast) ease-standard focus-within:border-primary focus-within:shadow-[0_0_0_3px_rgba(26,24,20,.12)]",
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

export function Textarea({ className, ...rest }: TextareaHTMLAttributes<HTMLTextAreaElement>) {
  return (
    <textarea
      className={cx(
        "w-full resize-none rounded-[10px] border border-line bg-paper px-4 py-3.5 text-sm leading-6 text-ink shadow-[inset_0_1px_2px_rgba(26,24,20,.04)] outline-none transition-[border-color,box-shadow] duration-(--motion-fast) ease-standard placeholder:text-ink-4 hover:border-line-strong focus:border-primary focus:shadow-[0_0_0_3px_rgba(26,24,20,.1)]",
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
        "h-9 w-full appearance-none rounded-md border border-line bg-surface-2 bg-[url('data:image/svg+xml;utf8,<svg xmlns=%22http://www.w3.org/2000/svg%22 viewBox=%220 0 20 20%22 fill=%22none%22 stroke=%22%23918c82%22 stroke-width=%221.7%22><path d=%22M5 8l5 5 5-5%22/></svg>')] bg-[length:16px] bg-[right_10px_center] bg-no-repeat px-3 pr-8 text-[13px] text-ink outline-none transition-[border-color,box-shadow] duration-(--motion-fast) ease-standard focus:border-primary focus:shadow-[0_0_0_3px_rgba(26,24,20,.12)]",
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
        "relative h-5 w-9 shrink-0 rounded-full border transition-colors duration-(--motion-fast) ease-standard",
        checked ? "border-primary bg-primary/30" : "border-line bg-surface-3",
      )}
    >
      {/* 滑块位移走 transform（合成器友好），不动画 left 布局属性 */}
      <span
        className={cx(
          "absolute left-0.5 top-0.5 h-3.5 w-3.5 rounded-full transition-transform duration-(--motion-base) ease-standard",
          checked ? "translate-x-[14px] bg-primary" : "translate-x-0 bg-ink-3",
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
            "flex h-7 select-none items-center gap-1.5 rounded-[7px] border px-3.5 text-[12.5px] transition-colors duration-(--motion-fast) ease-standard",
            value === option.id
              ? "border-line-subtle bg-paper font-semibold text-ink shadow-e2"
              : "border-transparent text-ink-2 hover:text-ink",
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
  // 每个实例独立的 layoutId，切换时墨色下划线在标签间平滑滑移
  const groupId = useId().replace(/:/g, "");
  return (
    <div className={cx("flex gap-5 border-b border-line-subtle", className)}>
      {items.map((item) => (
        <button
          key={item.id}
          onClick={() => onChange(item.id)}
          className={cx(
            "relative pb-2.5 pt-2 text-[13px] transition-colors duration-(--motion-fast) ease-standard",
            value === item.id ? "font-semibold text-ink" : "text-ink-3 hover:text-ink-2",
          )}
        >
          {item.label}
          {item.count !== undefined && (
            <span className="ml-1.5 font-mono text-[10.5px] text-ink-4">{item.count}</span>
          )}
          {value === item.id && (
            <motion.span
              layoutId={`tabs-underline-${groupId}`}
              className="absolute inset-x-0 -bottom-px h-0.5 rounded-sm bg-primary"
              transition={{ duration: MOTION.base, ease: EASE_STANDARD }}
            />
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
  success: "bg-gradient-to-r from-[#6fa287] to-success",
  danger: "bg-gradient-to-r from-warning to-danger",
  precon: "bg-gradient-to-r from-[#4fb3c7] to-precon",
  falign: "bg-gradient-to-r from-[#9d85d0] to-falign",
  gimport: "bg-gradient-to-r from-[#5f9c7d] to-gimport",
  ember: "bg-gradient-to-r from-ember to-[#c46a3a]",
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
    tone === "auto" ? (threshold === undefined || value >= threshold ? "success" : "danger") : tone;
  return (
    <div className={className}>
      <div className="mb-[6px] flex items-baseline justify-between gap-3 text-xs">
        <span className="min-w-0 truncate text-ink-2">{label}</span>
        <span className="tabular shrink-0 font-mono text-[12.5px] text-ink">{format(value)}</span>
      </div>
      <div className="relative h-1.5 overflow-hidden rounded-full bg-surface-3">
        {/* 填充用 scaleX（transform 合成器通道）揭示，不动画 width 布局属性 */}
        <motion.div
          className={cx("h-full w-full origin-left rounded-full", SCORE_FILLS[fill])}
          initial={{ scaleX: 0 }}
          animate={{ scaleX: Math.max(percent / 100, 0.0001) }}
          transition={{ duration: MOTION.reveal, ease: EASE_STANDARD }}
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
          <stop offset="0" stopColor="var(--color-ink)" />
          <stop offset="1" stopColor="var(--color-ember)" />
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
        transition={{ duration: MOTION.reveal, ease: EASE_STANDARD }}
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
          y="96"
          textAnchor="middle"
          fill="var(--color-ink-3)"
          fontSize="6.5"
          fontFamily="var(--font-sans)"
          letterSpacing="0.3"
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
    <div className="flex items-baseline justify-between gap-4 border-b border-ink/[.08] py-2 text-[12.5px] last:border-b-0">
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
  display = false,
  className,
}: {
  label: ReactNode;
  value: ReactNode;
  hint?: ReactNode;
  tone?: string;
  icon?: IconName;
  chart?: ReactNode;
  /** 展示级数字：宋体黑字重，编辑风大数字观感 */
  display?: boolean;
  className?: string;
}) {
  return (
    <div className={cx("flex min-w-0 flex-col gap-0.5", className)}>
      <div className="flex items-center gap-1.5 text-xs text-ink-3">
        {icon && <Icon name={icon} className="h-3.5 w-3.5" />}
        <span className="truncate">{label}</span>
      </div>
      <div
        className={cx(
          "tabular text-[32px] font-semibold leading-10 tracking-[-0.02em]",
          display && "cf-display-num",
          tone,
        )}
      >
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
    state === "done"
      ? "check"
      : state === "failed"
        ? "x"
        : state === "running"
          ? "refresh"
          : "clock";
  const colorOf = (state: string) =>
    state === "done"
      ? "border-success bg-success/10 text-success"
      : state === "running"
        ? "border-primary bg-primary-tint text-primary shadow-[0_0_0_4px_rgba(26,24,20,.08)]"
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
      <span className="cf-hatch relative grid h-12 w-12 place-items-center rounded-[10px] border border-line bg-paper text-ink-2 shadow-e2">
        <Icon name={icon} className="h-5 w-5" />
        <span
          className="absolute -right-1 -top-1 h-2 w-2 rotate-45 rounded-[1px] bg-ember shadow-[0_0_0_3px_rgba(245,243,239,.9)]"
          aria-hidden="true"
        />
      </span>
      <div className="text-[15px] font-semibold">{title}</div>
      {description && (
        <p className="max-w-sm text-[12.5px] leading-[19px] text-ink-3 [text-wrap:pretty]">{description}</p>
      )}
      {action && <div className="mt-1">{action}</div>}
    </div>
  );
}

/**
 * SafeImage：图片加载失败（文件被清理、404）时优雅回退，
 * 用朱印字代替破图标——资产名的首字入印，破图也是"作品档案"。
 * 尺寸/描边由 className 透传给回退容器，布局零抖动。
 */
export function SafeImage({
  src,
  alt,
  className,
  sealChar,
  fallback,
  ...rest
}: {
  src?: string | null;
  alt: string;
  className?: string;
  /** 印面文字；默认取 alt 首个非 ASCII 字符，否则"印" */
  sealChar?: string;
  /** 完全自定义回退内容（如 CharacterArt 像素人） */
  fallback?: ReactNode;
} & Omit<ImgHTMLAttributes<HTMLImageElement>, "src" | "alt" | "children">) {
  const [failed, setFailed] = useState(false);
  const trimmed = alt.trim();
  const seal = sealChar ?? (trimmed && /\P{ASCII}/u.test(trimmed[0]) ? trimmed[0] : "印");

  if (!src || failed) {
    return (
      <span
        role="img"
        aria-label={alt}
        className={cx(
          "cf-hatch relative grid shrink-0 place-items-center overflow-hidden bg-paper",
          className,
        )}
      >
        {fallback ?? (
          <svg viewBox="0 0 24 24" className="h-full w-full" aria-hidden="true">
            <text
              x="12"
              y="16.5"
              textAnchor="middle"
              fontSize="13"
              className="fill-ink/30 font-display font-black"
            >
              {seal}
            </text>
          </svg>
        )}
      </span>
    );
  }

  return (
    <img
      src={src}
      alt={alt}
      loading="lazy"
      onError={() => setFailed(true)}
      className={cx(
        // 图片发丝描边：亮色环境用纯黑 10%，避免图片边缘"脏边"并稳定轮廓层次
        "outline-1 -outline-offset-1 outline-black/10",
        className,
      )}
      {...rest}
    />
  );
}

/** 异常态：网络失败、权限不足、流中断等需要用户介入的场景 */
export function ErrorState({
  title = "加载失败",
  description,
  action,
  className,
}: {
  title?: ReactNode;
  description?: ReactNode;
  action?: ReactNode;
  className?: string;
}) {
  return (
    <div className={cx("flex flex-col items-center gap-2.5 px-5 py-10 text-center", className)}>
      <span className="grid h-12 w-12 place-items-center rounded-[10px] border border-danger/40 bg-danger/10 text-danger">
        <Icon name="alert" className="h-5 w-5" />
      </span>
      <div className="text-[15px] font-semibold">{title}</div>
      {description && (
        <p className="max-w-sm text-[12.5px] leading-[19px] text-ink-3">{description}</p>
      )}
      {action && <div className="mt-1">{action}</div>}
    </div>
  );
}

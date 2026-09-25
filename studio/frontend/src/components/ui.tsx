import type { ReactNode } from "react";

export function Card({
  title,
  right,
  children,
  className = "",
}: {
  title?: ReactNode;
  right?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  return (
    <section
      className={`rounded-xl border border-zinc-800 bg-zinc-900/50 p-4 ${className}`}
    >
      {(title || right) && (
        <header className="mb-3 flex items-center justify-between">
          <h2 className="pixel-title text-xs font-semibold text-zinc-300">{title}</h2>
          {right}
        </header>
      )}
      {children}
    </section>
  );
}

export function Badge({
  tone = "zinc",
  children,
}: {
  tone?: "zinc" | "green" | "amber" | "red" | "blue";
  children: ReactNode;
}) {
  const tones: Record<string, string> = {
    zinc: "bg-zinc-700/40 text-zinc-300",
    green: "bg-emerald-500/15 text-emerald-300",
    amber: "bg-amber-400/15 text-amber-300",
    red: "bg-red-500/15 text-red-300",
    blue: "bg-sky-500/15 text-sky-300",
  };
  return (
    <span
      className={`inline-flex items-center rounded px-2 py-0.5 text-[11px] font-medium ${tones[tone]}`}
    >
      {children}
    </span>
  );
}

export function ScoreBar({
  label,
  value,
  threshold,
}: {
  label: string;
  value: number;
  threshold?: number;
}) {
  const percent = Math.round(value * 100);
  const tone =
    threshold === undefined || value >= threshold
      ? "bg-emerald-400"
      : "bg-amber-400";
  return (
    <div>
      <div className="mb-1 flex items-center justify-between text-xs">
        <span className="text-zinc-400">{label}</span>
        <span className="font-mono text-zinc-200">{percent}%</span>
      </div>
      <div className="h-1.5 overflow-hidden rounded-full bg-zinc-800">
        <div
          className={`h-full rounded-full ${tone}`}
          style={{ width: `${Math.min(100, percent)}%` }}
        />
      </div>
    </div>
  );
}

export function KV({ label, value }: { label: string; value: ReactNode }) {
  return (
    <div className="flex items-baseline justify-between gap-4 border-b border-zinc-800/70 py-1.5 last:border-0">
      <span className="text-xs text-zinc-500">{label}</span>
      <span className="font-mono text-xs text-zinc-200">{value}</span>
    </div>
  );
}

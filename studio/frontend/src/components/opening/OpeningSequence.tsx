import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { OPENING } from "../../lib/motion";
import "./opening.css";

type OpeningMode = "full" | "short" | "reduced" | "off";

const DAY_KEY = "creativeforge.opening.day";

function todayKey() {
  const d = new Date();
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
}

function detectMode(): OpeningMode {
  if (typeof window === "undefined") return "off";
  const hash = decodeURIComponent(window.location.hash.slice(1)).toLowerCase();
  if (hash.includes("noopening")) return "off";
  const forced = hash.includes("opening") || hash.includes("ouverture");
  if (!forced) {
    try {
      if (window.localStorage.getItem(DAY_KEY) === todayKey()) return "off";
    } catch {
      // A private browser can reject storage; the opening still has a safe path.
    }
  }
  if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return "reduced";
  if (window.matchMedia("(max-width: 767px)").matches) return "short";
  return "full";
}

function durationFor(mode: OpeningMode) {
  if (mode === "reduced") return OPENING.reduced;
  if (mode === "short") return OPENING.short;
  return OPENING.full;
}

const FRAMES = [
  {
    key: "idea",
    className: "cf-opening-frame cf-opening-frame--idea",
    content: (
      <>
        <span className="cf-opening-kicker">D’une idée</span>
        <span className="cf-opening-script">à l’atelier</span>
        <span className="cf-opening-cn">从一句话，到可入引擎的作品</span>
      </>
    ),
  },
  {
    key: "forge",
    className: "cf-opening-frame cf-opening-frame--forge",
    content: (
      <>
        <span className="cf-opening-ghost-word">FORGE</span>
        <span className="cf-opening-outline-word">FORGE</span>
        <span className="cf-opening-cn">资产工坊 · 蓝雾厅</span>
      </>
    ),
  },
  {
    key: "monogram",
    className: "cf-opening-frame cf-opening-frame--monogram",
    content: (
      <>
        <span className="cf-opening-oval">
          <span>CF</span>
        </span>
        <span className="cf-opening-cn">CreativeForge</span>
        <span className="cf-opening-ref">N° 01 · MMXXVI</span>
      </>
    ),
  },
  {
    key: "atelier",
    className: "cf-opening-frame cf-opening-frame--atelier",
    content: (
      <>
        <span className="cf-opening-stroke-word">ATELIER</span>
        <span className="cf-opening-rule" />
        <span className="cf-opening-cn">规划 · 生成 · 对齐 · 试玩 · 导出</span>
      </>
    ),
  },
  {
    key: "final",
    className: "cf-opening-frame cf-opening-frame--final",
    content: (
      <>
        <span className="cf-opening-seal" aria-hidden="true">造</span>
        <span className="cf-opening-final-word">CreativeForge</span>
        <span className="cf-opening-final-sub">Le Salon Bleu des Assets</span>
        <span className="cf-opening-final-cn">蓝雾工坊</span>
      </>
    ),
  },
] as const;

export function OpeningSequence() {
  const [mode] = useState<OpeningMode>(detectMode);
  const [ready, setReady] = useState(false);
  const [closing, setClosing] = useState(false);
  const [active, setActive] = useState(mode !== "off");
  const finished = useRef(false);
  const timer = useRef<number | null>(null);

  useEffect(() => {
    if (!active || mode === "off") return;
    const root = document.getElementById("root");
    const html = document.documentElement;
    const previousOverflow = html.style.overflow;
    if (root) {
      root.setAttribute("inert", "");
      root.setAttribute("aria-hidden", "true");
    }
    html.style.overflow = "hidden";
    try {
      window.localStorage.setItem(DAY_KEY, todayKey());
    } catch {
      // Storage is an enhancement, never a gate.
    }

    let alive = true;
    const fontReady = document.fonts?.ready ?? Promise.resolve();
    const readyFallback = new Promise<void>((resolve) => window.setTimeout(resolve, 420));
    Promise.race([fontReady, readyFallback]).then(() => {
      if (alive) setReady(true);
    });

    return () => {
      alive = false;
      if (timer.current) window.clearTimeout(timer.current);
      html.style.overflow = previousOverflow;
      if (root) {
        root.removeAttribute("inert");
        root.removeAttribute("aria-hidden");
      }
    };
  }, [active, mode]);

  useEffect(() => {
    if (!active || !ready || mode === "off" || finished.current) return;
    const delay = mode === "reduced" ? 900 : durationFor(mode) * 1000;
    timer.current = window.setTimeout(() => finish(), delay);
    return () => {
      if (timer.current) window.clearTimeout(timer.current);
    };
  }, [active, ready, mode]);

  useEffect(() => {
    const root = document.getElementById("root");
    if (!root) return;
    if (active && ready && !closing) root.classList.add("cf-opening-reveal");
    else root.classList.remove("cf-opening-reveal");
    return () => root.classList.remove("cf-opening-reveal");
  }, [active, ready, closing]);

  function finish(how: "complete" | "skip" = "complete") {
    if (finished.current) return;
    finished.current = true;
    setClosing(true);
    window.setTimeout(() => {
      setActive(false);
      window.requestAnimationFrame(() => {
        document.getElementById("cf-main")?.focus({ preventScroll: true });
      });
    }, OPENING.skipFade * 1000);
    if (how === "skip") {
      document.dispatchEvent(new CustomEvent("creativeforge:opening-skip"));
    }
  }

  useEffect(() => {
    if (!active || mode === "off") return;
    function onKey(event: KeyboardEvent) {
      if (event.key === "Escape" || event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        finish("skip");
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [active, mode]);

  if (
    mode === "off" ||
    !active
  ) return null;

  return createPortal(
    <div
      className={[
        "cf-opening",
        `cf-opening--${mode}`,
        ready ? "is-ready" : "",
        closing ? "is-closing" : "",
      ]
        .filter(Boolean)
        .join(" ")}
      data-opening-mode={mode}
      role="dialog"
      aria-modal="true"
      aria-label="CreativeForge 开场"
      onPointerDown={(event) => {
        if ((event.target as HTMLElement).closest("button")) return;
        event.preventDefault();
        finish("skip");
      }}
    >
      <div className="cf-opening-fog" aria-hidden="true" />
      <div className="cf-opening-arch" aria-hidden="true">
        <svg viewBox="0 0 900 560" preserveAspectRatio="none">
          <ellipse cx="450" cy="280" rx="392" ry="238" />
          <ellipse cx="450" cy="280" rx="322" ry="184" />
          <path d="M58 280H842M450 42V518" />
          <circle cx="450" cy="280" r="7" />
        </svg>
      </div>

      <div className="cf-opening-meta cf-opening-meta--left" aria-hidden="true">
        <span>CREATIVEFORGE</span>
        <span>ATELIER D’ASSETS · MMXXVI</span>
      </div>
      <div className="cf-opening-meta cf-opening-meta--right" aria-hidden="true">
        <span>N° 03</span>
        <span>BLUE MIST / IVORY / INK</span>
      </div>

      <div className="cf-opening-stage">
        {FRAMES.map((frame) => (
          <div key={frame.key} className={frame.className}>
            {frame.content}
          </div>
        ))}
      </div>

      <div className="cf-opening-bottom">
        <span>LE SALON DU CODE DEVIENT L’ATELIER DES ASSETS</span>
        <span className="cf-opening-bottom-line" aria-hidden="true" />
        <button type="button" autoFocus onClick={() => finish("skip")} className="cf-opening-skip">
          跳过 · ESC
        </button>
      </div>
      <span className="cf-opening-cursor" aria-hidden="true" />
    </div>,
    document.body,
  );
}

/**
 * 移动端触控层：虚拟摇杆 + 动作键。
 *
 * 只在「手指设备」或「窄屏」出现（`(pointer: coarse)` / `max-width:1023px`），
 * 桌面端保持键鼠体验不变。组件不派发 KeyboardEvent，而是把方向与动作
 * 交给各页面，由页面写进自己已有的按键集合/动作 API——与键盘走同一条路径。
 */
import { useEffect, useRef, useState, type ReactNode } from "react";
import { cx } from "./ui";

export type TouchDirection = "left" | "right" | "up" | "down";

/** 是否显示触控层：粗指针（手指）或窄屏设备。 */
export function useTouchControls(): boolean {
  const [enabled, setEnabled] = useState(false);
  useEffect(() => {
    if (typeof window.matchMedia !== "function") return;
    const coarse = window.matchMedia("(pointer: coarse)");
    const narrow = window.matchMedia("(max-width: 1023px)");
    const update = () => setEnabled(coarse.matches || narrow.matches);
    update();
    coarse.addEventListener("change", update);
    narrow.addEventListener("change", update);
    return () => {
      coarse.removeEventListener("change", update);
      narrow.removeEventListener("change", update);
    };
  }, []);
  return enabled;
}

/** 摇杆推杆死区：低于该比例不产生方向，避免手指抖动误触。 */
const DEAD_ZONE = 0.34;

export function TouchJoystick({
  onDirection,
  className,
  label = "移动摇杆",
}: {
  onDirection: (direction: TouchDirection, pressed: boolean) => void;
  className?: string;
  label?: string;
}) {
  const boxRef = useRef<HTMLDivElement>(null);
  const pointerRef = useRef<number | null>(null);
  const activeRef = useRef<Set<TouchDirection>>(new Set());
  const [offset, setOffset] = useState({ x: 0, y: 0 });

  const commit = (next: Set<TouchDirection>) => {
    const previous = activeRef.current;
    if (previous.size === 0 && next.size === 0) return;
    activeRef.current = next;
    for (const direction of previous) if (!next.has(direction)) onDirection(direction, false);
    for (const direction of next) if (!previous.has(direction)) onDirection(direction, true);
  };

  const move = (clientX: number, clientY: number) => {
    const element = boxRef.current;
    if (!element) return;
    const rect = element.getBoundingClientRect();
    const radius = rect.width / 2;
    const max = radius * 0.58;
    let dx = clientX - (rect.left + radius);
    let dy = clientY - (rect.top + radius);
    const distance = Math.hypot(dx, dy);
    if (distance > max) {
      dx = (dx / distance) * max;
      dy = (dy / distance) * max;
    }
    setOffset({ x: dx, y: dy });
    const nx = dx / max;
    const ny = dy / max;
    const next = new Set<TouchDirection>();
    if (nx <= -DEAD_ZONE) next.add("left");
    if (nx >= DEAD_ZONE) next.add("right");
    if (ny <= -DEAD_ZONE) next.add("up");
    if (ny >= DEAD_ZONE) next.add("down");
    commit(next);
  };

  const release = () => {
    pointerRef.current = null;
    setOffset({ x: 0, y: 0 });
    commit(new Set());
  };

  return (
    <div
      ref={boxRef}
      role="group"
      aria-label={label}
      className={cx(
        "pointer-events-auto relative h-24 w-24 shrink-0 touch-none select-none rounded-full border-2 border-paper/45 bg-ink/25 shadow-[0_6px_18px_-10px_rgba(0,0,0,.6)] backdrop-blur-sm sm:h-28 sm:w-28",
        className,
      )}
      onPointerDown={(event) => {
        event.preventDefault();
        event.stopPropagation();
        pointerRef.current = event.pointerId;
        event.currentTarget.setPointerCapture(event.pointerId);
        move(event.clientX, event.clientY);
      }}
      onPointerMove={(event) => {
        if (pointerRef.current !== event.pointerId) return;
        event.preventDefault();
        event.stopPropagation();
        move(event.clientX, event.clientY);
      }}
      onPointerUp={(event) => {
        if (pointerRef.current !== event.pointerId) return;
        event.stopPropagation();
        release();
      }}
      onPointerCancel={release}
    >
      <span
        className="absolute left-1/2 top-1/2 h-10 w-10 rounded-full border border-paper/60 bg-paper/85 shadow-e1 sm:h-12 sm:w-12"
        style={{ transform: `translate(calc(-50% + ${offset.x}px), calc(-50% + ${offset.y}px))` }}
        aria-hidden="true"
      />
    </div>
  );
}

export function TouchButton({
  label,
  hint,
  tone = "secondary",
  onPress,
  onRelease,
  className,
}: {
  label: string;
  hint?: string;
  tone?: "primary" | "secondary";
  onPress: () => void;
  /** 按住类动作（奔跑/防御/跳跃）在抬起时回调 */
  onRelease?: () => void;
  className?: string;
}) {
  const pointerRef = useRef<number | null>(null);
  const [held, setHeld] = useState(false);

  return (
    <button
      type="button"
      aria-label={hint ? `${label}（${hint}）` : label}
      className={cx(
        "pointer-events-auto grid h-14 w-14 touch-none select-none place-items-center rounded-full border-2 text-[12px] font-semibold leading-tight transition-transform duration-(--motion-fast)",
        tone === "primary"
          ? "border-paper/55 bg-primary/85 text-paper"
          : "border-paper/55 bg-paper/85 text-ink",
        held && "scale-95",
        className,
      )}
      onPointerDown={(event) => {
        event.preventDefault();
        event.stopPropagation();
        pointerRef.current = event.pointerId;
        event.currentTarget.setPointerCapture(event.pointerId);
        setHeld(true);
        onPress();
      }}
      onPointerUp={(event) => {
        if (pointerRef.current !== event.pointerId) return;
        event.stopPropagation();
        pointerRef.current = null;
        setHeld(false);
        onRelease?.();
      }}
      onPointerCancel={() => {
        pointerRef.current = null;
        setHeld(false);
        onRelease?.();
      }}
    >
      {label}
    </button>
  );
}

/** 舞台内浮层：左下摇杆、右下动作键；不遮挡点按（仅控件本身可点）。 */
export function TouchControlsLayer({
  joystick,
  children,
  className,
}: {
  joystick?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  return (
    <div
      className={cx(
        "pointer-events-none absolute inset-x-0 bottom-0 z-[15] flex items-end justify-between gap-2 p-2.5",
        className,
      )}
    >
      {joystick}
      <div className="flex flex-wrap items-end justify-end gap-2">{children}</div>
    </div>
  );
}

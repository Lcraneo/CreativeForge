import { create } from "zustand";

export type ToastTone = "info" | "success" | "danger" | "warning";

export interface ToastItem {
  id: number;
  tone: ToastTone;
  title: string;
  description?: string;
}

interface ToastRecord extends ToastItem {
  /** 绝对过期时间：后台标签页计时器被节流后，回到前台可据此立即清理。 */
  expiresAt: number;
}

interface ToastState {
  items: ToastRecord[];
  push: (item: Omit<ToastItem, "id">) => void;
  dismiss: (id: number) => void;
  /** 清理已过预设时长但仍留在队列里的条目（兜底）。 */
  dismissExpired: () => void;
}

let seq = 0;

const AUTO_DISMISS_MS: Record<ToastTone, number> = {
  info: 4200,
  success: 3600,
  warning: 5000,
  danger: 6500,
};

/** 每条提示自己的自动消失定时器；手动关闭时同步清除，避免悬挂计时。 */
const timers = new Map<number, ReturnType<typeof setTimeout>>();

function clearTimer(id: number) {
  const timer = timers.get(id);
  if (timer === undefined) return;
  clearTimeout(timer);
  timers.delete(id);
}

export const useToastStore = create<ToastState>((set, get) => ({
  items: [],
  push: (item) => {
    const id = (seq += 1);
    const durationMs = AUTO_DISMISS_MS[item.tone] ?? 4200;
    const { items } = get();
    // 队列上限 4 条：被挤掉的条目连同计时器一起回收。
    if (items.length >= 4) {
      items.slice(0, items.length - 3).forEach((existing) => clearTimer(existing.id));
    }
    set({
      items: [...items.slice(-3), { id, ...item, expiresAt: Date.now() + durationMs }],
    });
    const timer = setTimeout(() => {
      timers.delete(id);
      get().dismiss(id);
    }, durationMs);
    timers.set(id, timer);
  },
  dismiss: (id) => {
    clearTimer(id);
    set((state) => ({ items: state.items.filter((existing) => existing.id !== id) }));
  },
  dismissExpired: () => {
    const now = Date.now();
    const expired = get().items.filter((item) => item.expiresAt <= now);
    if (expired.length === 0) return;
    expired.forEach((item) => clearTimer(item.id));
    set((state) => ({ items: state.items.filter((item) => item.expiresAt > now) }));
  },
}));

/** Fire a toast from anywhere (module-level store, no provider needed). */
export function toast(options: { tone: ToastTone; title: string; description?: string }) {
  useToastStore.getState().push(options);
}

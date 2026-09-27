import { create } from "zustand";

export type ToastTone = "info" | "success" | "danger" | "warning";

export interface ToastItem {
  id: number;
  tone: ToastTone;
  title: string;
  description?: string;
}

interface ToastState {
  items: ToastItem[];
  push: (item: Omit<ToastItem, "id">) => void;
  dismiss: (id: number) => void;
}

let seq = 0;

const AUTO_DISMISS_MS: Record<ToastTone, number> = {
  info: 4200,
  success: 3600,
  warning: 5000,
  danger: 6500,
};

export const useToastStore = create<ToastState>((set, get) => ({
  items: [],
  push: (item) => {
    const id = (seq += 1);
    set((state) => ({ items: [...state.items.slice(-3), { id, ...item }] }));
    setTimeout(() => get().dismiss(id), AUTO_DISMISS_MS[item.tone] ?? 4200);
  },
  dismiss: (id) =>
    set((state) => ({ items: state.items.filter((existing) => existing.id !== id) })),
}));

/** Fire a toast from anywhere (module-level store, no provider needed). */
export function toast(options: { tone: ToastTone; title: string; description?: string }) {
  useToastStore.getState().push(options);
}

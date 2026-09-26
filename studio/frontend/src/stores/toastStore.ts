import { create } from "zustand";

export type ToastTone = "info" | "success" | "warning" | "danger";

export interface ToastItem {
  id: number;
  title: string;
  description?: string;
  tone: ToastTone;
}

interface ToastState {
  toasts: ToastItem[];
  push: (toast: Omit<ToastItem, "id">) => void;
  remove: (id: number) => void;
}

let sequence = 0;

export const useToastStore = create<ToastState>((set) => ({
  toasts: [],
  push: (item) => {
    const id = (sequence += 1);
    set((state) => ({ toasts: [...state.toasts, { id, ...item }] }));
    setTimeout(
      () => set((state) => ({ toasts: state.toasts.filter((t) => t.id !== id) })),
      4200,
    );
  },
  remove: (id) =>
    set((state) => ({ toasts: state.toasts.filter((t) => t.id !== id) })),
}));

export function toast(item: Omit<ToastItem, "id">) {
  useToastStore.getState().push(item);
}

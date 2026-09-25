import { create } from "zustand";
import type { ExportResult } from "../types";

interface ExportState {
  exports: ExportResult[];
  busy: boolean;
  error: string | null;
  add: (result: ExportResult) => void;
  setBusy: (busy: boolean) => void;
  setError: (error: string | null) => void;
}

export const useExportStore = create<ExportState>((set) => ({
  exports: [],
  busy: false,
  error: null,
  add: (result) => set((state) => ({ exports: [result, ...state.exports], error: null })),
  setBusy: (busy) => set({ busy }),
  setError: (error) => set({ error }),
}));

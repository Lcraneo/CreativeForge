import { create } from "zustand";
import type { CharacterPackageResult, ExportResult } from "../types";

export function exportScope(assetId: string, engine: string, kind: "engine" | "character") {
  return JSON.stringify([assetId, engine, kind]);
}

interface ExportState {
  exports: ExportResult[];
  characterPackages: CharacterPackageResult[];
  pending: Record<string, boolean>;
  errors: Record<string, string | null>;
  add: (result: ExportResult) => void;
  addCharacterPackage: (result: CharacterPackageResult) => void;
  begin: (scope: string) => boolean;
  finish: (scope: string, error?: string) => void;
}

export const useExportStore = create<ExportState>((set, get) => ({
  exports: [],
  characterPackages: [],
  pending: {},
  errors: {},
  add: (result) => set((state) => ({ exports: [result, ...state.exports] })),
  addCharacterPackage: (result) =>
    set((state) => ({ characterPackages: [result, ...state.characterPackages] })),
  begin: (scope) => {
    if (get().pending[scope]) return false;
    set((state) => ({
      pending: { ...state.pending, [scope]: true },
      errors: { ...state.errors, [scope]: null },
    }));
    return true;
  },
  finish: (scope, error) =>
    set((state) => ({
      pending: { ...state.pending, [scope]: false },
      errors: { ...state.errors, [scope]: error ?? null },
    })),
}));

import { create } from "zustand";
import { useEffect, useRef } from "react";
import type { CreativeAsset } from "../types";
import { api } from "../api/client";

interface AssetState {
  asset: CreativeAsset | null;
  loading: boolean;
  error: string | null;
  set: (asset: CreativeAsset | null) => void;
  setLoading: (loading: boolean) => void;
  setError: (error: string | null) => void;
}

export const useAssetStore = create<AssetState>((set) => ({
  asset: null,
  loading: false,
  error: null,
  set: (asset) => set({ asset, error: null }),
  setLoading: (loading) => set({ loading }),
  setError: (error) => set({ error }),
}));

/** Loads the given (or latest) asset once per mount/key. Falls back to the
 *  newest history record when the runtime holds no assets (e.g. after restart). */
export function useAssetLoader(assetId?: string | null): CreativeAsset | null {
  const asset = useAssetStore((state) => state.asset);
  const set = useAssetStore((state) => state.set);
  const setLoading = useAssetStore((state) => state.setLoading);
  const requested = useRef<string | null>(null);

  useEffect(() => {
    const key = assetId ?? "latest";
    if (requested.current === key) return;
    requested.current = key;
    if (!assetId && useAssetStore.getState().asset) return;
    let cancelled = false;
    setLoading(true);
    const loader = assetId ? api.getAsset(assetId) : api.latestAsset();
    const latestFromHistory = () =>
      api.listHistory({ limit: 1 }).then((history) => {
        const fromHistory = history.records[0]?.asset ?? null;
        if (!fromHistory) throw new Error("no asset yet");
        return fromHistory;
      });
    loader
      .then((result) => {
        if (cancelled) return;
        set(result);
        setLoading(false);
      })
      .catch(() => {
        if (cancelled) return;
        if (assetId) {
          setLoading(false);
          return;
        }
        latestFromHistory()
          .then((fromHistory) => {
            if (cancelled) return;
            set(fromHistory);
            setLoading(false);
          })
          .catch(() => {
            if (!cancelled) setLoading(false);
          });
      });
    return () => {
      cancelled = true;
    };
  }, [assetId, set, setLoading]);

  return asset;
}

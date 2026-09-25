import { create } from "zustand";
import { useEffect } from "react";
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

/** Loads the given (or latest) asset once per mount. */
export function useAssetLoader(assetId?: string | null): CreativeAsset | null {
  const asset = useAssetStore((state) => state.asset);
  const loading = useAssetStore((state) => state.loading);
  const set = useAssetStore((state) => state.set);
  const setLoading = useAssetStore((state) => state.setLoading);

  useEffect(() => {
    if (asset || loading) return;
    let cancelled = false;
    setLoading(true);
    const loader = assetId ? api.getAsset(assetId) : api.latestAsset();
    loader
      .then((result) => {
        if (!cancelled) set(result);
      })
      .catch(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [assetId, asset, loading]);

  return asset;
}

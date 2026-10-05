import { create } from "zustand";
import { useEffect } from "react";
import { useSearchParams } from "react-router-dom";
import type { CreativeAsset } from "../types";
import { api, ApiError } from "../api/client";

interface AssetState {
  asset: CreativeAsset | null;
  loading: boolean;
  error: string | null;
  retryVersion: number;
  retry: () => void;
  patch: (id: string, changes: Partial<CreativeAsset>) => void;
  set: (asset: CreativeAsset | null) => void;
  setLoading: (loading: boolean) => void;
  setError: (error: string | null) => void;
}

export const useAssetStore = create<AssetState>((set) => ({
  asset: null,
  loading: false,
  error: null,
  retryVersion: 0,
  retry: () => set((state) => ({ retryVersion: state.retryVersion + 1 })),
  patch: (id, changes) =>
    set((state) => (state.asset?.id === id ? { asset: { ...state.asset, ...changes, id } } : {})),
  set: (asset) => set({ asset, error: null }),
  setLoading: (loading) => set({ loading }),
  setError: (error) => set({ error }),
}));

/** Keep the selected asset in the URL so deep links cannot silently fall back
 * to whichever asset happened to be generated most recently. */
export function assetHref(path: string, assetId?: string | null): string {
  if (!assetId) return path;
  const hashAt = path.indexOf("#");
  const hash = hashAt < 0 ? "" : path.slice(hashAt);
  const base = hashAt < 0 ? path : path.slice(0, hashAt);
  const queryAt = base.indexOf("?");
  const pathname = queryAt < 0 ? base : base.slice(0, queryAt);
  const params = new URLSearchParams(queryAt < 0 ? "" : base.slice(queryAt + 1));
  params.set("asset", assetId);
  return `${pathname}?${params.toString()}${hash}`;
}

/** Explicit URLs never fall back to another asset. Each effect owns its request,
 * including StrictMode remounts, retries and browser history navigation. */
export function useAssetLoader(assetId?: string | null): CreativeAsset | null {
  const [searchParams] = useSearchParams();
  const routeAssetId = assetId ?? (searchParams.get("asset") || null);
  const asset = useAssetStore((state) => state.asset);
  const retryVersion = useAssetStore((state) => state.retryVersion);

  useEffect(() => {
    if (!routeAssetId && useAssetStore.getState().asset) {
      useAssetStore.setState({ loading: false, error: null });
      return;
    }
    const controller = new AbortController();
    useAssetStore.setState({ asset: null, loading: true, error: null });
    const loader = routeAssetId
      ? api.getAsset(routeAssetId, { signal: controller.signal, silent: true })
      : api.latestAsset({ signal: controller.signal });
    loader
      .then((result) => {
        if (controller.signal.aborted) return;
        if (routeAssetId && result.id !== routeAssetId) throw new Error("asset ID mismatch");
        // A generation result selected while loading must not be overwritten.
        if (routeAssetId || !useAssetStore.getState().asset) useAssetStore.getState().set(result);
        useAssetStore.setState({ loading: false });
      })
      .catch((cause: unknown) => {
        if (controller.signal.aborted) return;
        const empty = !routeAssetId && cause instanceof ApiError && cause.status === 404;
        useAssetStore.setState({
          loading: false,
          error: useAssetStore.getState().asset || empty ? null : assetLoadError(cause),
        });
      });
    return () => {
      controller.abort();
      useAssetStore.setState({ loading: false });
    };
  }, [routeAssetId, retryVersion]);

  return routeAssetId && asset?.id !== routeAssetId ? null : asset;
}

export function assetLoadError(cause: unknown): string {
  if (cause instanceof ApiError && cause.status === 404)
    return "指定资产不存在或已被删除，请从历史记录重新选择。";
  if (cause instanceof ApiError && (cause.status === 401 || cause.status === 403))
    return "当前无权读取资产，请检查访问凭证后重试。";
  return "资产加载失败，请检查网络或服务状态后重试。";
}

import { useCallback } from "react";
import { useLocation } from "react-router-dom";
import { assetHref, useAssetStore } from "../stores/assetStore";

const ASSET_PAGES = new Set(["/asset", "/design", "/animation", "/export"]);

export function navigationHref(path: string, search: string, currentId?: string | null) {
  const explicitId = new URLSearchParams(search).get("asset");
  return assetHref(path, explicitId || (ASSET_PAGES.has(path) ? currentId : null));
}

export function useAssetNavigation() {
  const { search } = useLocation();
  const currentId = useAssetStore((state) => state.asset?.id);
  return useCallback(
    (path: string) => navigationHref(path, search, currentId),
    [search, currentId],
  );
}

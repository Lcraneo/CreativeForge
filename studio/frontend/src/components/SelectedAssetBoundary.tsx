import type { ReactNode } from "react";
import { useQuery } from "@tanstack/react-query";
import { useSearchParams } from "react-router-dom";
import { api } from "../api/client";
import { assetLoadError } from "../stores/assetStore";
import type { CreativeAsset } from "../types";
import { AssetLoadFeedback } from "./AssetLoadState";

/** Explicit picker pages never infer a selection from the global/latest asset. */
export function SelectedAssetBoundary({
  children,
}: {
  children: (asset: CreativeAsset | null) => ReactNode;
}) {
  const [params] = useSearchParams();
  const id = params.get("asset");
  const query = useQuery({
    queryKey: ["selected-asset", id],
    queryFn: async ({ signal }) => {
      const asset = await api.getAsset(id!, { signal, silent: true });
      if (asset.id !== id) throw new Error("asset ID mismatch");
      return asset;
    },
    enabled: Boolean(id),
    retry: false,
    staleTime: 30_000,
  });
  if (id && !query.data)
    return (
      <div className="mx-auto w-full max-w-[1440px] px-4 py-5 md:px-6">
        <AssetLoadFeedback
          loading={query.isFetching}
          error={query.error ? assetLoadError(query.error) : null}
          retry={() => {
            void query.refetch();
          }}
        />
      </div>
    );
  return children(id ? (query.data ?? null) : null);
}

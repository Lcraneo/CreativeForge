import { Link } from "react-router-dom";
import { useAssetStore } from "../stores/assetStore";
import { Button, Card, Skeleton } from "./ui";

export function AssetLoadFeedback({
  loading,
  error,
  retry,
}: {
  loading: boolean;
  error: string | null;
  retry: () => void;
}) {
  return (
    <Card>
      {loading ? (
        <div role="status" aria-live="polite">
          <p className="mb-3 text-sm text-ink-2">正在加载所选资产…</p>
          <Skeleton className="h-32" />
        </div>
      ) : (
        <div className="space-y-3 text-sm">
          <p role={error ? "alert" : "status"}>
            {error || "还没有资产，请先生成或从历史记录选择。"}
          </p>
          <div className="flex flex-wrap items-center gap-4">
            <Button icon="refresh" onClick={retry}>
              重新加载
            </Button>
            <Link
              className="inline-flex min-h-11 items-center text-primary underline"
              to="/history"
            >
              选择历史资产
            </Link>
            <Link className="inline-flex min-h-11 items-center text-primary underline" to="/workspace">
              去生成资产
            </Link>
          </div>
        </div>
      )}
    </Card>
  );
}

export function AssetLoadState() {
  const loading = useAssetStore((state) => state.loading);
  const error = useAssetStore((state) => state.error);
  const retry = useAssetStore((state) => state.retry);
  return (
    <div className="mx-auto w-full max-w-[1440px] px-4 py-5 md:px-6">
      <AssetLoadFeedback loading={loading} error={error} retry={retry} />
    </div>
  );
}

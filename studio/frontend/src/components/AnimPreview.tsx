import { useEffect, useState } from "react";
import { api } from "../api/client";

interface Props {
  assetId: string;
  action?: string;
  fps?: number;
  duration?: number;
  size?: number;
  className?: string;
}

/**
 * Real animated preview for an asset: asks the animation service to build a
 * style-consistent cycle and shows the resulting GIF. Falls back to the
 * character's still image while generating / on failure (never pixel art).
 */
export function AnimPreview({
  assetId,
  action = "walk",
  fps = 10,
  duration = 0.8,
  size = 256,
  className,
}: Props) {
  const [url, setUrl] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    setUrl(null);
    api
      .createAnimation({ asset_id: assetId, action, fps, duration, size })
      .then((result) => {
        if (alive) setUrl(result.urls.gif);
      })
      .catch(() => {});
    return () => {
      alive = false;
    };
  }, [assetId, action, fps, duration, size]);

  const src = url || `/api/assets/${assetId}/image.png?view=front&size=384`;
  return <img src={src} alt="animation preview" className={className} />;
}

import { useEffect, useState } from "react";
import { assetViewUrl, type CharacterView } from "../api";

interface Props {
  assetId: string;
  view?: CharacterView;
  size?: number;
  alt?: string;
  className?: string;
  /** shown when the image fails to load */
  fallback?: React.ReactNode;
}

/**
 * Character artwork (`GET /api/v1/assets/{id}/image.png`), 2D style.
 *
 * Renders a real raster image with a graceful fallback: a failed/broken
 * reference must never hide the character, so we swap to the placeholder.
 */
export default function CharacterImage({
  assetId,
  view = "front",
  size = 512,
  alt = "character",
  className,
  fallback,
}: Props) {
  const src = assetViewUrl(assetId, view, size);
  const [failed, setFailed] = useState(false);

  useEffect(() => setFailed(false), [src]);

  if (failed) {
    return (
      <div
        role="img"
        aria-label={alt}
        className={`grid place-items-center bg-panel text-center text-[10px] leading-tight text-mute ${className ?? ""}`}
      >
        {fallback ?? "图像暂不可用"}
      </div>
    );
  }

  return (
    <img
      src={src}
      alt={alt}
      width={size}
      height={size}
      loading="lazy"
      decoding="async"
      onError={() => setFailed(true)}
      className={className}
    />
  );
}

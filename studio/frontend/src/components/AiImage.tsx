import { useEffect, useState, type ReactNode } from "react";

interface Props {
  src?: string;
  alt?: string;
  className?: string;
  fallback: ReactNode;
}

/**
 * Image with a guaranteed character fallback.
 *
 * Concept art can come from an external image model (arbitrary URL / file) or
 * from the deterministic backend renderer. If the reference is missing or the
 * request fails, we render the vector character instead of leaving a broken
 * image — a character must never disappear from the console.
 */
export function AiImage({ src, alt, className, fallback }: Props) {
  const [failed, setFailed] = useState(false);

  useEffect(() => setFailed(false), [src]);

  if (!src || failed) return <>{fallback}</>;

  return (
    <img
      src={src}
      alt={alt}
      loading="lazy"
      decoding="async"
      onError={() => setFailed(true)}
      className={className}
    />
  );
}

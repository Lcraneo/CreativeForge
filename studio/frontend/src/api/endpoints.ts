const configuredBackend = (import.meta.env.VITE_BACKEND_URL ?? import.meta.env.VITE_BACKEND ?? "")
  .trim()
  .replace(/\/+$/, "");

/** Resolve a backend path for both the local same-origin build and split hosting. */
export function backendUrl(path: string): string {
  if (!configuredBackend || /^https?:\/\//i.test(path)) return path;
  return `${configuredBackend}${path.startsWith("/") ? path : `/${path}`}`;
}

/** Build the WebSocket endpoint from the same backend origin used by REST. */
export function backendWebSocketUrl(path: string): string {
  const explicit = (import.meta.env.VITE_WS_BACKEND_URL ?? "").trim().replace(/\/+$/, "");
  const base = explicit || configuredBackend.replace(/^http/i, "ws");
  if (base) return `${base}${path.startsWith("/") ? path : `/${path}`}`;

  const protocol = location.protocol === "https:" ? "wss" : "ws";
  return `${protocol}://${location.host}${path.startsWith("/") ? path : `/${path}`}`;
}

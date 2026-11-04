import { afterEach, describe, expect, it, vi } from "vitest";

afterEach(() => {
  vi.unstubAllEnvs();
  vi.resetModules();
});

describe("split deployment endpoints", () => {
  it("keeps local development on same-origin paths", async () => {
    const { backendUrl } = await import("./endpoints");
    expect(backendUrl("/api/health")).toBe("/api/health");
  });

  it("routes REST, assets and WebSocket to the configured backend origin", async () => {
    vi.stubEnv("VITE_BACKEND_URL", "https://api.example.com/");
    const { backendUrl, backendWebSocketUrl } = await import("./endpoints");

    expect(backendUrl("/api/health")).toBe(
      "https://api.example.com/api/health",
    );
    expect(backendWebSocketUrl("/ws/tasks/task-1/stream")).toBe(
      "wss://api.example.com/ws/tasks/task-1/stream",
    );
  });

  it("does not rewrite already absolute artifact URLs", async () => {
    vi.stubEnv("VITE_BACKEND_URL", "https://api.example.com");
    const { backendUrl } = await import("./endpoints");
    expect(backendUrl("https://cdn.example.com/asset.png")).toBe(
      "https://cdn.example.com/asset.png",
    );
  });
});

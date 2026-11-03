import { beforeEach, describe, expect, it } from "vitest";

import { assetHref, useAssetStore } from "./assetStore";

beforeEach(() => {
  useAssetStore.setState({ asset: null, loading: false, error: null });
});

describe("assetStore", () => {
  it("assetHref encodes a stable deep-link context", () => {
    expect(assetHref("/asset", "hero/火焰" as string)).toBe(
      "/asset?asset=hero%2F%E7%81%AB%E7%84%B0",
    );
    expect(assetHref("/design?tab=side", "hero-1")).toBe("/design?tab=side&asset=hero-1");
    expect(assetHref("/asset", null)).toBe("/asset");
  });
  it("初始为空", () => {
    const state = useAssetStore.getState();
    expect(state.asset).toBeNull();
    expect(state.loading).toBe(false);
    expect(state.error).toBeNull();
  });

  it("replaces existing asset parameters without losing the fragment", () => {
    expect(assetHref("/design?asset=old&tab=side&asset=duplicate#preview", "new")).toBe(
      "/design?asset=new&tab=side#preview",
    );
  });

  it("merges updates only into the originating asset", () => {
    useAssetStore.getState().set({ id: "b", name: "B" } as never);
    useAssetStore.getState().patch("a", { name: "late A" });
    expect(useAssetStore.getState().asset?.name).toBe("B");
    useAssetStore.getState().patch("b", { cutout_png: "b.png" });
    expect(useAssetStore.getState().asset).toEqual({ id: "b", name: "B", cutout_png: "b.png" });
  });

  it("set 写入资产并清除错误", () => {
    useAssetStore.getState().setError("boom");
    useAssetStore.getState().set({ id: "hero001" } as never);
    const state = useAssetStore.getState();
    expect(state.asset).toEqual({ id: "hero001" });
    expect(state.error).toBeNull();
  });

  it("set(null) 与 setLoading/setError 独立生效", () => {
    useAssetStore.getState().set({ id: "a" } as never);
    useAssetStore.getState().set(null);
    useAssetStore.getState().setLoading(true);
    useAssetStore.getState().setError("e1");
    const state = useAssetStore.getState();
    expect(state.asset).toBeNull();
    expect(state.loading).toBe(true);
    expect(state.error).toBe("e1");
  });
});

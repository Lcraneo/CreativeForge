import { beforeEach, describe, expect, it } from "vitest";

import { useAssetStore } from "./assetStore";

beforeEach(() => {
  useAssetStore.setState({ asset: null, loading: false, error: null });
});

describe("assetStore", () => {
  it("初始为空", () => {
    const state = useAssetStore.getState();
    expect(state.asset).toBeNull();
    expect(state.loading).toBe(false);
    expect(state.error).toBeNull();
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

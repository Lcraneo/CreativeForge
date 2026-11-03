import { act, StrictMode, useLayoutEffect } from "react";
import { createRoot, type Root } from "react-dom/client";
import { MemoryRouter, useNavigate, type NavigateFunction } from "react-router-dom";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { api, ApiError } from "../api/client";
import { AssetLoadState } from "../components/AssetLoadState";
import { useAssetLoader, useAssetStore } from "./assetStore";
import type { CreativeAsset } from "../types";

const asset = (id: string) => ({ id, name: id }) as CreativeAsset;
let root: Root;
let container: HTMLDivElement;
let navigate: NavigateFunction;
let renders: Array<string | null>;
function Harness() {
  const current = useAssetLoader();
  const routerNavigate = useNavigate();
  useLayoutEffect(() => {
    navigate = routerNavigate;
    renders.push(current?.id ?? null);
  }, [routerNavigate, current]);
  return current ? <output>{current.id}</output> : <AssetLoadState />;
}
function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason: unknown) => void;
  const promise = new Promise<T>((yes, no) => {
    resolve = yes;
    reject = no;
  });
  return { promise, resolve, reject };
}
beforeEach(() => {
  vi.stubGlobal("IS_REACT_ACT_ENVIRONMENT", true);
  useAssetStore.setState({ asset: null, loading: false, error: null, retryVersion: 0 });
  renders = [];
  container = document.createElement("div");
  document.body.append(container);
  root = createRoot(container);
});
afterEach(async () => {
  await act(async () => root.unmount());
  container.remove();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});
async function render(url = "/asset?asset=a", strict = false) {
  const tree = (
    <MemoryRouter
      initialEntries={[url]}
      future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
    >
      <Harness />
    </MemoryRouter>
  );
  await act(async () => root.render(strict ? <StrictMode>{tree}</StrictMode> : tree));
}

it("finishes loading after StrictMode effect cleanup and cancels the first request", async () => {
  const get = vi.spyOn(api, "getAsset").mockResolvedValue(asset("a"));
  await render(undefined, true);
  expect(get).toHaveBeenCalledTimes(2);
  expect(get.mock.calls[0][1]?.signal?.aborted).toBe(true);
  expect(container.querySelector("output")?.textContent).toBe("a");
  expect(useAssetStore.getState().loading).toBe(false);
});

it("hides mismatched assets synchronously and ignores late responses on rapid navigation", async () => {
  const a = deferred<CreativeAsset>();
  const b = deferred<CreativeAsset>();
  const get = vi
    .spyOn(api, "getAsset")
    .mockImplementation((id) => (id === "a" ? a.promise : b.promise));
  useAssetStore.getState().set(asset("old"));
  await render();
  expect(renders).not.toContain("old");
  await act(async () => navigate("/export?asset=b"));
  expect(get.mock.calls[0][1]?.signal?.aborted).toBe(true);
  await act(async () => b.resolve(asset("b")));
  await act(async () => a.resolve(asset("a")));
  expect(container.querySelector("output")?.textContent).toBe("b");
  expect(useAssetStore.getState().asset?.id).toBe("b");
});

it("recovers the same ID through the visible retry button without latest/history fallback", async () => {
  const get = vi
    .spyOn(api, "getAsset")
    .mockRejectedValueOnce(new ApiError(404, "missing"))
    .mockResolvedValueOnce(asset("a"));
  const latest = vi.spyOn(api, "latestAsset");
  const history = vi.spyOn(api, "listHistory");
  await render();
  expect(container.querySelector('[role="alert"]')?.textContent).toContain("不存在");
  const retry = Array.from(container.querySelectorAll("button")).find(
    (button) => button.textContent === "重新加载",
  )!;
  await act(async () => retry.click());
  expect(get).toHaveBeenCalledTimes(2);
  expect(container.querySelector("output")?.textContent).toBe("a");
  expect(latest).not.toHaveBeenCalled();
  expect(history).not.toHaveBeenCalled();
});

it("restores explicit IDs on browser back and forward", async () => {
  vi.spyOn(api, "getAsset").mockImplementation(async (id) => asset(id));
  await render();
  await act(async () => navigate("/asset?asset=b"));
  expect(container.querySelector("output")?.textContent).toBe("b");
  await act(async () => navigate(-1));
  expect(container.querySelector("output")?.textContent).toBe("a");
  await act(async () => navigate(1));
  expect(container.querySelector("output")?.textContent).toBe("b");
});

it("distinguishes an empty latest response from service failure", async () => {
  vi.spyOn(api, "latestAsset")
    .mockRejectedValueOnce(new ApiError(404, "no asset yet"))
    .mockRejectedValueOnce(new ApiError(503, "unavailable"));
  await render("/asset");
  expect(container.textContent).toContain("还没有资产");
  expect(container.querySelector('[role="alert"]')).toBeNull();
  await act(async () => useAssetStore.getState().retry());
  expect(container.querySelector('[role="alert"]')?.textContent).toContain("加载失败");
});

it("does not overwrite a newly generated asset when a latest request finishes", async () => {
  const pending = deferred<CreativeAsset>();
  vi.spyOn(api, "latestAsset").mockReturnValue(pending.promise);
  await render("/asset");
  await act(async () => useAssetStore.getState().set(asset("new")));
  await act(async () => pending.resolve(asset("old")));
  expect(container.querySelector("output")?.textContent).toBe("new");
});

it("rejects a response with a different asset ID", async () => {
  vi.spyOn(api, "getAsset").mockResolvedValue(asset("wrong"));
  await render();
  expect(container.querySelector("output")).toBeNull();
  expect(container.querySelector('[role="alert"]')).not.toBeNull();
});

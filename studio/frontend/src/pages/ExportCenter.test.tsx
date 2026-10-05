import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import ExportCenter from "./ExportCenter";
import { useAssetStore } from "../stores/assetStore";
import { exportScope, useExportStore } from "../stores/exportStore";
import { api } from "../api/client";
import type { CharacterPackageResult, CreativeAsset, ExportResult } from "../types";

function result(assetId: string, engine: string): ExportResult {
  return {
    asset_id: assetId,
    engine,
    package: `${assetId}-${engine}.zip`,
    download_url: `/api/exports/${assetId}-${engine}.zip`,
    files: ["Config/atlas.json"],
    size_bytes: 1024,
    contents: [],
    validation: { status: "success", score: 1, checks: [] },
  };
}
const asset = (id: string) => ({ id, name: id }) as CreativeAsset;
let root: Root;
let container: HTMLDivElement;

beforeEach(() => {
  vi.stubGlobal("IS_REACT_ACT_ENVIRONMENT", true);
  useAssetStore.setState({ asset: asset("a"), loading: false, error: null });
  useExportStore.setState({ exports: [], characterPackages: [], pending: {}, errors: {} });
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
async function render() {
  await act(async () =>
    root.render(
      <MemoryRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
        <ExportCenter />
      </MemoryRouter>,
    ),
  );
}
async function click(text: string) {
  const button = Array.from(container.querySelectorAll("button")).find(
    (item) => item.textContent === text,
  );
  expect(button, `button ${text}`).toBeDefined();
  await act(async () => button!.click());
}
const downloads = () =>
  Array.from(container.querySelectorAll("a")).map((link) => link.getAttribute("href"));

describe("export context", () => {
  it("only displays downloads for the selected asset and engine", async () => {
    useExportStore.setState({
      exports: [result("b", "godot"), result("a", "cocos"), result("a", "unity")],
    });
    await render();
    expect(downloads()).toEqual(["/api/exports/a-unity.zip", "/api/exports/a-unity.zip"]);
    await click("Cocos");
    expect(downloads()).toEqual(["/api/exports/a-cocos.zip", "/api/exports/a-cocos.zip"]);
    await act(async () => useAssetStore.getState().set(asset("b")));
    expect(downloads()).toEqual([]);
  });

  it("keeps an in-flight export bound to its origin after the user changes asset", async () => {
    let resolve!: (value: ExportResult) => void;
    const exportAsset = vi.spyOn(api, "exportAsset").mockImplementation(
      () =>
        new Promise((r) => {
          resolve = r;
        }),
    );
    await render();
    await click("导出 Unity 配置包");
    expect(exportAsset).toHaveBeenCalledExactlyOnceWith("a", "unity");
    const scope = exportScope("a", "unity", "engine");
    expect(useExportStore.getState().begin(scope)).toBe(false);
    await act(async () => useAssetStore.getState().set(asset("b")));
    expect(container.textContent).not.toContain("正在打包");
    await act(async () => resolve(result("a", "unity")));
    expect(downloads()).toEqual([]);
    await act(async () => useAssetStore.getState().set(asset("a")));
    expect(downloads()).toContain("/api/exports/a-unity.zip");
    expect(container.textContent).toContain("打包完成");
  });

  it("scopes package results and persistent errors to the current engine", async () => {
    useExportStore.setState({
      characterPackages: [
        {
          ...result("a", "unity"),
          artwork_count: 1,
          engine_files: 2,
          animations: [],
          missing: [],
        } as CharacterPackageResult,
      ],
      errors: { [exportScope("a", "unity", "engine")]: "disk full" },
    });
    await render();
    expect(downloads()).toContain("/api/exports/a-unity.zip");
    expect(container.textContent).toContain("disk full");
    await click("Godot");
    expect(downloads()).toEqual([]);
    expect(container.textContent).not.toContain("disk full");
  });
});

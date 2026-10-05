import { act, useEffect, type ReactNode } from "react";
import { createRoot, type Root } from "react-dom/client";
import { MemoryRouter, useLocation, useNavigate, type NavigateFunction } from "react-router-dom";
import { QueryClient, QueryClientProvider, notifyManager } from "@tanstack/react-query";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { api, ApiError } from "../api/client";
import { navigationHref } from "../lib/assetNavigation";
import { useAssetStore } from "../stores/assetStore";
import type { CreativeAsset } from "../types";
import Layout from "./Layout";
import ShowcaseStudio from "../pages/ShowcaseStudio";
import AnimationStudio from "../pages/AnimationStudio";

vi.mock("./ModelApiPanel", () => ({ ModelApiPanel: () => null }));
vi.mock("./StorageApiConfig", () => ({ default: () => null }));

let container: HTMLDivElement;
let root: Root;
let client: QueryClient;
let navigate: NavigateFunction;
const asset = (id: string) => ({ id, name: `角色 ${id}` }) as CreativeAsset;
function LocationProbe() {
  const routerNavigate = useNavigate();
  useEffect(() => { navigate = routerNavigate; }, [routerNavigate]);
  const location = useLocation();
  return (
    <output data-location>
      {location.pathname}
      {location.search}
    </output>
  );
}
beforeEach(() => {
  vi.stubGlobal("IS_REACT_ACT_ENVIRONMENT", true);
  notifyManager.setScheduler(queueMicrotask);
  useAssetStore.setState({ asset: asset("global"), loading: false, error: null });
  localStorage.clear();
  vi.spyOn(api, "health").mockResolvedValue({ status: "ok" });
  // jsdom has no native modal implementation; verify wiring, not browser focus containment.
  Object.defineProperty(HTMLDialogElement.prototype, "showModal", {
    configurable: true,
    value: function (this: HTMLDialogElement) {
      this.open = true;
    },
  });
  Object.defineProperty(HTMLDialogElement.prototype, "close", {
    configurable: true,
    value: function (this: HTMLDialogElement) {
      this.open = false;
    },
  });
  client = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: Infinity } } });
  container = document.createElement("div");
  document.body.append(container);
  root = createRoot(container);
});
afterEach(async () => {
  await act(async () => root.unmount());
  client.clear();
  container.remove();
  notifyManager.setScheduler((callback) => setTimeout(callback, 0));
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
  Reflect.deleteProperty(HTMLDialogElement.prototype, "showModal");
  Reflect.deleteProperty(HTMLDialogElement.prototype, "close");
});
async function render(child: ReactNode, url: string) {
  await act(async () =>
    root.render(
      <QueryClientProvider client={client}>
        <MemoryRouter
          initialEntries={[url]}
          future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
        >
          <LocationProbe />
          {child}
        </MemoryRouter>
      </QueryClientProvider>,
    ),
  );
}
async function click(label: string) {
  const button = Array.from(container.querySelectorAll("button")).find((node) =>
    node.textContent?.includes(label),
  );
  expect(button).toBeDefined();
  await act(async () => button!.click());
}

it("keeps explicit context even when the global asset differs; picker pages remain explicit", () => {
  expect(navigationHref("/export", "?asset=missing", "global")).toBe("/export?asset=missing");
  expect(navigationHref("/design", "", "global")).toBe("/design?asset=global");
  expect(navigationHref("/showcase", "", "global")).toBe("/showcase");
  expect(navigationHref("/playtest", "?asset=chosen", "global")).toBe("/playtest?asset=chosen");
});

it("offers all 14 destinations in the mobile dialog and restores trigger focus", async () => {
  await render(<Layout />, "/asset?asset=chosen");
  const more = container.querySelector<HTMLButtonElement>('[aria-label="更多功能"]')!;
  more.focus();
  await act(async () => more.click());
  const dialog = container.querySelector("dialog")!;
  expect(dialog.open).toBe(true);
  expect(dialog.querySelectorAll("a")).toHaveLength(14);
  expect(dialog.querySelector('a[href="/export?asset=chosen"]')).not.toBeNull();
  expect(dialog.querySelector('a[href="/animation?asset=chosen"]')).not.toBeNull();
  await act(async () =>
    dialog.dispatchEvent(new Event("cancel", { bubbles: true, cancelable: true })),
  );
  expect(dialog.open).toBe(false);
  expect(document.activeElement).toBe(more);
});

it("carries context through keyboard navigation and the complete command palette", async () => {
  await render(<Layout />, "/history?asset=chosen");
  await act(async () => window.dispatchEvent(new KeyboardEvent("keydown", { key: "3" })));
  expect(container.querySelector("[data-location]")?.textContent).toBe("/asset?asset=chosen");
  await click("命令");
  const palette = container.querySelector('[role="dialog"]')!;
  expect(palette.querySelectorAll("button")).toHaveLength(14);
  const first = palette.querySelector("input")!;
  const buttons = Array.from(palette.querySelectorAll("button"));
  const last = buttons[buttons.length - 1];
  first.focus();
  await act(async () =>
    first.dispatchEvent(
      new KeyboardEvent("keydown", { key: "Tab", shiftKey: true, bubbles: true, cancelable: true }),
    ),
  );
  expect(document.activeElement).toBe(last);
  await act(async () =>
    last.dispatchEvent(
      new KeyboardEvent("keydown", { key: "Tab", bubbles: true, cancelable: true }),
    ),
  );
  expect(document.activeElement).toBe(first);
  await click("发布展示间");
  expect(container.querySelector("[data-location]")?.textContent).toBe("/showcase?asset=chosen");
});

it("loads a deep link outside recent history and restores selection through back/forward", async () => {
  const get = vi.spyOn(api, "getAsset").mockImplementation(async (id) => asset(id));
  vi.spyOn(api, "listHistory").mockResolvedValue({ records: [], total: 0 } as never);
  const generate = vi
    .spyOn(api, "startShowcase")
    .mockResolvedValue({ job_id: "job-old", snapshot: {} } as never);
  vi.spyOn(api, "showcaseStatus").mockResolvedValue({
    id: "job-old",
    status: "failed",
    stage: "failed",
    error: "OLD JOB ERROR",
  } as never);
  await render(<ShowcaseStudio />, "/showcase?asset=older-than-12&tab=video");
  expect(get.mock.calls[0][0]).toBe("older-than-12");
  expect(container.textContent).toContain("角色 older-than-12");
  await click("Generate OneTake Demo");
  expect(generate).toHaveBeenCalledWith("older-than-12");
  await act(async () => navigate("/showcase?asset=b&tab=video"));
  expect(container.textContent).toContain("角色 b");
  expect(container.textContent).not.toContain("OLD JOB ERROR");
  await act(async () => navigate(-1));
  expect(container.textContent).toContain("角色 older-than-12");
  await act(async () => navigate(1));
  expect(container.textContent).toContain("角色 b");
});

it("keeps an unselected showcase empty despite a global asset and preserves other query parameters on selection", async () => {
  const get = vi.spyOn(api, "getAsset").mockImplementation(async (id) => asset(id));
  vi.spyOn(api, "listHistory").mockResolvedValue({
    records: [{ id: "record", asset_id: "picked", name: "可选人物", image: { url: "/image.png" } }],
    total: 1,
  } as never);
  await render(<ShowcaseStudio />, "/showcase?tab=video");
  expect(get).not.toHaveBeenCalled();
  expect(container.textContent).toContain("先选择一个角色");
  await click("可选人物");
  expect(container.querySelector("[data-location]")?.textContent).toBe(
    "/showcase?tab=video&asset=picked",
  );
  expect(container.textContent).toContain("角色 picked");
  await act(async () => navigate(-1));
  expect(container.textContent).toContain("先选择一个角色");
});

it("blocks the animation editor and its preview requests when the explicit asset fails", async () => {
  vi.spyOn(api, "getAsset").mockRejectedValue(new ApiError(404, "missing"));
  const preview = vi.spyOn(api, "previewAnimationFrame");
  const latest = vi.spyOn(api, "latestAsset");
  await render(<AnimationStudio />, "/animation?asset=missing");
  expect(container.querySelector('[role="alert"]')?.textContent).toContain("不存在");
  expect(container.textContent).not.toContain("动作预览 Motion Preview");
  expect(preview).not.toHaveBeenCalled();
  expect(latest).not.toHaveBeenCalled();
});

it("migrates legacy animation tasks only for the backend-confirmed asset", async () => {
  const legacy = JSON.stringify({ id: "task-a", kind: "base" });
  localStorage.setItem("cf:animation-video-task", legacy);
  vi.spyOn(api, "getAsset").mockImplementation(async (id) => asset(id));
  vi.spyOn(api, "listHistory").mockResolvedValue({ records: [], total: 0 } as never);
  vi.spyOn(api, "listCustomActions").mockResolvedValue({ actions: [] });
  vi.spyOn(api, "rigCheck").mockResolvedValue({ status: "ok" } as never);
  vi.spyOn(api, "getVideoTask").mockResolvedValue({
    id: "task-a",
    asset_id: "a",
    status: "running",
    stage: "video",
    progress: 35,
  });
  await render(<AnimationStudio />, "/animation?asset=b");
  expect(localStorage.getItem("cf:animation-video-task")).toBe(legacy);
  expect(localStorage.getItem("cf:animation-video-task:b")).toBeNull();
  await act(async () => navigate("/animation?asset=a"));
  expect(localStorage.getItem("cf:animation-video-task")).toBeNull();
  expect(localStorage.getItem("cf:animation-video-task:a")).toBe(legacy);
  await act(async () => navigate("/animation?asset=b"));
  expect(localStorage.getItem("cf:animation-video-task:a")).toBe(legacy);
  expect(container.textContent).not.toContain("35%");
});

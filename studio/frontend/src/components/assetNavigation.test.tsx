import { act, type ReactNode } from "react";
import { createRoot, type Root } from "react-dom/client";
import { MemoryRouter, useLocation } from "react-router-dom";
import { QueryClient, QueryClientProvider, notifyManager } from "@tanstack/react-query";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { api } from "../api/client";
import { navigationHref } from "../lib/assetNavigation";
import { useAssetStore } from "../stores/assetStore";
import type { CreativeAsset } from "../types";
import Layout from "./Layout";

let container: HTMLDivElement;
let root: Root;
let client: QueryClient;
const asset = (id: string) => ({ id, name: `角色 ${id}` }) as CreativeAsset;
function LocationProbe() {
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
  expect(navigationHref("/playtest", "?asset=chosen", "global")).toBe("/playtest?asset=chosen");
});

it("offers all 11 destinations in the mobile dialog and restores trigger focus", async () => {
  await render(<Layout />, "/asset?asset=chosen");
  const more = container.querySelector<HTMLButtonElement>('[aria-label="更多功能"]')!;
  more.focus();
  await act(async () => more.click());
  const dialog = container.querySelector("dialog")!;
  expect(dialog.open).toBe(true);
  expect(dialog.querySelectorAll("a")).toHaveLength(11);
  expect(dialog.querySelector('a[href="/scenes?asset=chosen"]')).not.toBeNull();
  expect(dialog.querySelector('a[href="/design?asset=chosen"]')).not.toBeNull();
  expect(dialog.querySelector('a[href^="/animation"]')).toBeNull();
  expect(dialog.querySelector('a[href="/arcade?asset=chosen"]')).not.toBeNull();
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
  expect(palette.querySelectorAll("button")).toHaveLength(11);
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
  await click("版本控制");
  expect(container.querySelector("[data-location]")?.textContent).toBe("/versions?asset=chosen");
});

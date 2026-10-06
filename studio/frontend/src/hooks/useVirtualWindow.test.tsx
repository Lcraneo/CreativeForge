import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { useRef } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { useVirtualWindow, type VirtualWindowResult } from "./useVirtualWindow";

vi.stubGlobal("IS_REACT_ACT_ENVIRONMENT", true);

let container: HTMLDivElement;
let root: Root;

beforeEach(() => {
  container = document.createElement("div");
  document.body.append(container);
  root = createRoot(container);
});

afterEach(async () => {
  await act(async () => root.unmount());
  container.remove();
});

function defineScroll(el: HTMLElement, { top, height }: { top: number; height: number }) {
  Object.defineProperty(el, "scrollTop", { value: top, configurable: true });
  Object.defineProperty(el, "clientHeight", { value: height, configurable: true });
}

async function flushFrame() {
  await act(async () => {
    await new Promise((resolve) => setTimeout(resolve, 40));
  });
}

describe("useVirtualWindow", () => {
  it("renders the first window without any scroll and reports exact total height", async () => {
    let latest: VirtualWindowResult | null = null;
    function Harness() {
      const ref = useRef<HTMLDivElement | null>(null);
      latest = useVirtualWindow({ count: 500, rowHeight: 40, overscan: 2, containerRef: ref });
      return <div ref={ref} />;
    }
    await act(async () => root.render(<Harness />));
    expect(latest!.totalHeight).toBe(500 * 40);
    expect(latest!.virtualItems[0]).toEqual({ index: 0, offsetTop: 0 });
    expect(latest!.virtualItems.length).toBeLessThan(10);
  });

  it("slides the window with scroll and keeps overscan margins", async () => {
    let latest: VirtualWindowResult | null = null;
    let el: HTMLDivElement | null = null;
    function Harness() {
      const ref = useRef<HTMLDivElement | null>(null);
      latest = useVirtualWindow({ count: 500, rowHeight: 40, overscan: 2, containerRef: ref });
      return (
        <div
          ref={(node) => {
            ref.current = node;
            el = node;
          }}
        />
      );
    }
    await act(async () => root.render(<Harness />));
    defineScroll(el!, { top: 400, height: 200 });
    await act(async () => el!.dispatchEvent(new Event("scroll")));
    await flushFrame();
    // floor(400/40)-2 = 8 起，ceil(600/40)+2 = 17 止
    expect(latest!.virtualItems[0].index).toBe(8);
    expect(latest!.virtualItems[0].offsetTop).toBe(8 * 40);
    expect(latest!.virtualItems.at(-1)!.index).toBe(16);
  });

  it("clamps the window when the dataset shrinks below the current scroll", async () => {
    let latest: VirtualWindowResult | null = null;
    let el: HTMLDivElement | null = null;
    function Harness({ count }: { count: number }) {
      const ref = useRef<HTMLDivElement | null>(null);
      latest = useVirtualWindow({ count, rowHeight: 40, overscan: 2, containerRef: ref });
      return (
        <div
          ref={(node) => {
            ref.current = node;
            el = node;
          }}
        />
      );
    }
    await act(async () => root.render(<Harness count={500} />));
    defineScroll(el!, { top: 19600, height: 200 });
    await act(async () => el!.dispatchEvent(new Event("scroll")));
    await flushFrame();
    await act(async () => root.render(<Harness count={10} />));
    await flushFrame();
    for (const item of latest!.virtualItems) {
      expect(item.index).toBeLessThan(10);
    }
    expect(latest!.totalHeight).toBe(10 * 40);
  });
});

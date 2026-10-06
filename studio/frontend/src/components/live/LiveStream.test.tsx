import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { LiveStream } from "./LiveStream";
import { normalizeTaskEvents } from "../../hooks/useTaskFeed";
import type { TaskEvent } from "../../types";

vi.stubGlobal("IS_REACT_ACT_ENVIRONMENT", true);

let container: HTMLDivElement;
let root: Root;

beforeEach(() => {
  container = document.createElement("div");
  document.body.append(container);
  root = createRoot(container);
  localStorage.removeItem("cf-live-virtual");
});

afterEach(async () => {
  await act(async () => root.unmount());
  container.remove();
  vi.restoreAllMocks();
});

function ev(type: TaskEvent["type"], extra: Partial<TaskEvent> = {}): TaskEvent {
  return { type, at: 1760000000, ...extra } as TaskEvent;
}

function seed(n: number): TaskEvent[] {
  const types: TaskEvent["type"][] = [
    "AGENT_START",
    "PROGRESS",
    "MODEL_IMAGE",
    "ASSET_UPDATE",
    "QUALITY_REPORT",
    "AGENT_DONE",
  ];
  return Array.from({ length: n }, (_, i) =>
    ev(types[i % types.length], {
      agent: `agent-${i % 3}`,
      detail: `事件 #${i}`,
    }),
  );
}

async function render(ui: React.ReactElement) {
  await act(async () => root.render(ui));
  await act(async () => new Promise((resolve) => setTimeout(resolve, 30)));
}

const buttons = (label: string) =>
  Array.from(container.querySelectorAll("button")).filter((node) =>
    node.textContent?.includes(label),
  );

describe("LiveStream", () => {
  it("shows the empty state when no events arrived yet", async () => {
    await render(<LiveStream items={[]} />);
    expect(container.textContent).toContain("等待事件");
  });

  it("switches content by kind chips and clears the filter back", async () => {
    await render(<LiveStream items={normalizeTaskEvents(seed(18))} />);
    const before = container.querySelectorAll("button").length;
    expect(before).toBeGreaterThan(0);
    await act(async () => buttons("质量")[0].click());
    // 质量类只有 QUALITY_REPORT / TASK_COMPLETE / TASK_FAILED
    expect(container.textContent).toContain("显示 3 / 18 条");
    await act(async () => buttons("全部")[0].click());
    expect(container.textContent).toContain("显示 18 / 18 条");
  });

  it("searches across title/agent/detail and offers a way out when nothing matches", async () => {
    await render(<LiveStream items={normalizeTaskEvents(seed(18))} />);
    const input = container.querySelector<HTMLInputElement>('input[aria-label="筛选事件"]')!;
    expect(input).not.toBeNull();
    // 受控组件：jsdom 需要跑 React 的 value tracker
    const setter = Object.getOwnPropertyDescriptor(
      HTMLInputElement.prototype,
      "value",
    )!.set!;
    await act(async () => {
      setter.call(input, "agent-1");
      input.dispatchEvent(new Event("input", { bubbles: true }));
    });
    expect(container.textContent).toContain("显示 6 / 18 条");
    await act(async () => {
      setter.call(input, "zzz-不存在");
      input.dispatchEvent(new Event("input", { bubbles: true }));
    });
    expect(container.textContent).toContain("没有匹配的事件");
    await act(async () => buttons("清除筛选")[0].click());
    expect(container.textContent).toContain("显示 18 / 18 条");
  });

  it("renders error state with a working retry and non-fatal notice separately", async () => {
    const onRetry = vi.fn();
    await render(
      <LiveStream items={[]} error="WebSocket 握手失败" onRetry={onRetry} />,
    );
    expect(container.textContent).toContain("实时流中断");
    await act(async () => buttons("重新连接")[0].click());
    expect(onRetry).toHaveBeenCalledTimes(1);

    await render(
      <LiveStream items={normalizeTaskEvents(seed(6))} notice="连接中断，正在重试任务状态…" />,
    );
    expect(container.textContent).toContain("连接中断，正在重试任务状态…");
    expect(container.textContent).not.toContain("实时流中断");
  });

  it("virtualizes large feeds: only a window of rows exists in the DOM", async () => {
    await render(<LiveStream items={normalizeTaskEvents(seed(300))} height={400} rowHeight={40} />);
    const rows = container.querySelectorAll('[style*="position: absolute"]');
    expect(rows.length).toBeGreaterThan(0);
    expect(rows.length).toBeLessThan(40);
    expect(container.textContent).toContain("虚拟滚动");
    expect(container.textContent).toContain("显示 300 / 300 条");
  });

  it("stays a plain animated list under the threshold", async () => {
    await render(<LiveStream items={normalizeTaskEvents(seed(30))} height={400} rowHeight={40} />);
    expect(container.querySelectorAll('[style*="position: absolute"]')).toHaveLength(0);
    expect(container.textContent).not.toContain("虚拟滚动");
  });
});

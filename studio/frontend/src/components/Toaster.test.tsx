import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { Toaster } from "./Toaster";
import { toast, useToastStore } from "../stores/toastStore";

let container: HTMLDivElement;
let root: Root;

beforeEach(() => {
  vi.stubGlobal("IS_REACT_ACT_ENVIRONMENT", true);
  useToastStore.setState({ items: [] });
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

async function renderToaster() {
  await act(async () => root.render(<Toaster />));
}

function click(element: Element) {
  element.dispatchEvent(new MouseEvent("click", { bubbles: true }));
}

it("任务开始/结束提示各自带关闭按钮，点击只关闭当前条目", async () => {
  await renderToaster();
  await act(async () => {
    toast({ tone: "info", title: "开始补齐 4 个动作", description: "串行生成中" });
    toast({ tone: "success", title: "动作生成完成", description: "试玩条带已自动刷新" });
  });

  const buttons = Array.from(container.querySelectorAll('button[aria-label^="关闭提示"]'));
  expect(buttons).toHaveLength(2);
  expect(buttons[0].getAttribute("aria-label")).toBe("关闭提示：开始补齐 4 个动作");
  expect(buttons[1].getAttribute("aria-label")).toBe("关闭提示：动作生成完成");

  // 关闭第一条（任务开始），任务结束提示必须保留
  await act(async () => click(buttons[0]));
  expect(useToastStore.getState().items.map((item) => item.title)).toEqual(["动作生成完成"]);

  // 关闭动画结束后，DOM 中也只剩任务结束这一条
  await act(async () => {
    await new Promise((resolve) => setTimeout(resolve, 300));
  });
  const cards = container.querySelectorAll('[role="status"]');
  expect(cards).toHaveLength(1);
  expect(cards[0].textContent).toContain("动作生成完成");
});

it("关闭按钮不会因冒泡误删相邻提示", async () => {
  await renderToaster();
  await act(async () => {
    toast({ tone: "warning", title: "动作生成被中断" });
    toast({ tone: "success", title: "三视图已生成" });
  });

  const buttons = Array.from(container.querySelectorAll('button[aria-label^="关闭提示"]'));
  await act(async () => click(buttons[1]));

  expect(useToastStore.getState().items.map((item) => item.title)).toEqual(["动作生成被中断"]);
});

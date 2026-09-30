import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { toast, useToastStore } from "./toastStore";

function reset() {
  useToastStore.setState({ items: [] });
}

beforeEach(reset);
afterEach(() => vi.useRealTimers());

describe("toastStore", () => {
  it("push 追加并带自增 id", () => {
    toast({ tone: "info", title: "第一条" });
    toast({ tone: "danger", title: "第二条" });
    const { items } = useToastStore.getState();
    expect(items).toHaveLength(2);
    expect(items[0].id).toBeLessThan(items[1].id);
    expect(items[1].tone).toBe("danger");
  });

  it("最多保留 4 条（旧的被挤掉）", () => {
    for (let index = 0; index < 6; index += 1) {
      toast({ tone: "info", title: `t${index}` });
    }
    const items = useToastStore.getState().items;
    expect(items).toHaveLength(4);
    expect(items[0].title).toBe("t2");
  });

  it("dismiss 移除指定条目", () => {
    toast({ tone: "info", title: "a" });
    toast({ tone: "info", title: "b" });
    const [first] = useToastStore.getState().items;
    useToastStore.getState().dismiss(first.id);
    const items = useToastStore.getState().items;
    expect(items).toHaveLength(1);
    expect(items[0].title).toBe("b");
  });

  it("到时自动消失（info 4.2s）", () => {
    vi.useFakeTimers();
    toast({ tone: "info", title: "稍等" });
    expect(useToastStore.getState().items).toHaveLength(1);
    vi.advanceTimersByTime(4300);
    expect(useToastStore.getState().items).toHaveLength(0);
  });
});

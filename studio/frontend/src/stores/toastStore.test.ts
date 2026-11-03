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

  it("手动关闭后不会误删其他提示，剩余提示仍会自动消失", () => {
    vi.useFakeTimers();
    toast({ tone: "success", title: "任务开始" });
    toast({ tone: "success", title: "任务结束" });
    const [start] = useToastStore.getState().items;
    useToastStore.getState().dismiss(start.id);
    expect(useToastStore.getState().items.map((item) => item.title)).toEqual(["任务结束"]);
    vi.advanceTimersByTime(4000);
    expect(useToastStore.getState().items).toHaveLength(0);
  });

  it("后台计时器被节流时，回到前台按过期时间兜底清理", () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-10-30T09:30:00"));
    toast({ tone: "info", title: "任务开始" });
    toast({ tone: "danger", title: "任务失败" });
    // 模拟页面切到后台：Date 前进 5s，但定时器回调没有执行
    vi.setSystemTime(new Date("2026-10-30T09:30:05"));
    useToastStore.getState().dismissExpired();
    const items = useToastStore.getState().items;
    expect(items).toHaveLength(1);
    expect(items[0].title).toBe("任务失败");
  });
});

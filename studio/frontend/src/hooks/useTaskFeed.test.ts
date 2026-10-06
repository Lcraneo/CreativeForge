import { describe, expect, it } from "vitest";
import { normalizeTaskEvents, trimBuffer, filterStreamItems, countByKind } from "./useTaskFeed";
import type { TaskEvent } from "../types";

function ev(partial: Partial<Omit<TaskEvent, "type">> & { type?: string }): TaskEvent {
  return { ...partial } as TaskEvent;
}

describe("normalizeTaskEvents", () => {
  it("maps event types to kind/title/tone with stable log-index ids", () => {
    const items = normalizeTaskEvents([
      ev({ type: "AGENT_START", agent: "precon-1", at: 100 }),
      ev({ type: "QUALITY_REPORT", detail: "pixel 0.91" }),
      ev({ type: "MYSTERY_TYPE" }),
    ]);
    expect(items.map((item) => item.id)).toEqual(["e0", "e1", "e2"]);
    expect(items[0].kind).toBe("schedule");
    expect(items[0].title).toBe("节点启动");
    expect(items[1].kind).toBe("quality");
    expect(items[1].detail).toBe("pixel 0.91");
    expect(items[2].kind).toBe("system");
    expect(items[2].title).toBe("MYSTERY_TYPE");
  });

  it("falls back through detail/action/stage/progress for the detail column", () => {
    const items = normalizeTaskEvents([
      ev({ action: "cut-frames" }),
      ev({ stage: "video" }),
      ev({ progress: 42 }),
    ]);
    expect(items.map((item) => item.detail)).toEqual(["cut-frames", "video", "42%"]);
  });
});

describe("trimBuffer", () => {
  it("keeps the tail when over the cap and returns the same array within cap", () => {
    const rows = Array.from({ length: 10 }, (_, i) => i);
    expect(trimBuffer(rows, 4)).toEqual([6, 7, 8, 9]);
    expect(trimBuffer(rows, 20)).toBe(rows);
  });
});

describe("filterStreamItems / countByKind", () => {
  const items = normalizeTaskEvents([
    ev({ type: "AGENT_START", agent: "precon-1" }),
    ev({ type: "MODEL_IMAGE", detail: "keyart v2" }),
    ev({ type: "QUALITY_REPORT", detail: "pixel 达标" }),
  ]);

  it("filters by kind and by keyword across raw/title/agent/detail", () => {
    expect(filterStreamItems(items, { kind: "quality", query: "" })).toHaveLength(1);
    expect(filterStreamItems(items, { kind: "all", query: "precon" })).toHaveLength(1);
    expect(filterStreamItems(items, { kind: "generate", query: "KEYART" })).toHaveLength(1);
    expect(filterStreamItems(items, { kind: "all", query: "不存在" })).toHaveLength(0);
  });

  it("counts per kind", () => {
    expect(countByKind(items)).toEqual({
      schedule: 1,
      generate: 1,
      engine: 0,
      quality: 1,
      system: 0,
    });
  });
});

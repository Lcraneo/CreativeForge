import { describe, expect, it } from "vitest";

import { jobStageLabel, peopleFromHistory } from "./ShowcaseStudio";
import type { HistoryRecord } from "../types";

describe("ShowcaseStudio helpers", () => {
  it("peopleFromHistory 只保留有资产且有图的人物", () => {
    const records = [
      { id: "r1", asset_id: "a1", name: "骑士", goal: "g", image: { url: "/a.png" } },
      { id: "r2", asset_id: null, name: "无资产", goal: "g", image: { url: "/b.png" } },
      { id: "r3", asset_id: "a3", name: "无图", goal: "g", image: null },
    ] as unknown as HistoryRecord[];
    const people = peopleFromHistory(records);
    expect(people.map((p) => p.asset_id)).toEqual(["a1"]);
  });

  it("jobStageLabel 覆盖运行态/完成/失败/空态", () => {
    expect(jobStageLabel(null)).toBe("待开始");
    expect(jobStageLabel({ status: "running", stage: "render" })).toContain("渲染中");
    expect(jobStageLabel({ status: "done", stage: "done" })).toBe("完成");
    expect(jobStageLabel({ status: "failed", stage: "failed" })).toBe("失败");
    expect(jobStageLabel({ status: "running", stage: "mystery" })).toBe("处理中…");
  });
});

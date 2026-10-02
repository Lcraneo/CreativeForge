/** 基础/自定义动作分离选择模型的契约测试。
 * 固化:互斥选中、按来源解析生成参数(基础=内置默认 / 自定义=preset 原样)、
 * 删除选中项后的回落。 */
import { describe, expect, it } from "vitest";
import {
  BUILTIN_ACTIONS,
  editorStateFor,
  isBuiltinAction,
  resolveGeneration,
  selectionAfterRemoval,
  type ActionPresetLike,
} from "./actionSelection";

const DEFAULTS = { bob: 1, stride: 1, arm: 1, lift: 1, lean: 0, lag: 0.45, cycles: 1 };

const PRESETS: ActionPresetLike[] = [
  {
    name: "轻快小跑",
    action: "run",
    view: "side",
    pose_config: { ...DEFAULTS, stride: 1.6, bob: 1.3 },
  },
  {
    name: "挥刀连击",
    action: "attack",
    view: "front",
    pose_config: { ...DEFAULTS, arm: 1.8, lag: 0.2 },
  },
];

describe("action selection model", () => {
  it("内置动作清单固定为 5 个基础动作", () => {
    expect(BUILTIN_ACTIONS).toEqual(["idle", "walk", "run", "attack", "jump"]);
  });

  it("基础动作生成:参数不传(内置默认),view 取工作区选择", () => {
    const plan = resolveGeneration({ kind: "base", name: "walk" }, PRESETS, "front");
    expect(plan).toEqual({ action: "walk", view: "front" });
    expect(plan?.pose_config).toBeUndefined();
  });

  it("自定义动作生成:严格按 preset 保存时的 action/view/pose_config 原样", () => {
    const plan = resolveGeneration({ kind: "custom", name: "轻快小跑" }, PRESETS, "front");
    expect(plan).toEqual({
      action: "run",
      view: "side",
      pose_config: { ...DEFAULTS, stride: 1.6, bob: 1.3 },
    });
    // 工作区视角不影响自定义动作——即使当前是 front 也用保存的 side
    expect(resolveGeneration({ kind: "custom", name: "轻快小跑" }, PRESETS, "front")?.view).toBe(
      "side",
    );
  });

  it("选中的自定义动作被删除后解析返回 null(生成按钮禁用,不静默回落基础动作)", () => {
    expect(resolveGeneration({ kind: "custom", name: "已删除" }, PRESETS, "side")).toBeNull();
  });

  it("基础动作名不在内置清单时同样拒绝生成", () => {
    expect(isBuiltinAction("walk")).toBe(true);
    expect(isBuiltinAction("轻快小跑")).toBe(false);
    expect(resolveGeneration({ kind: "base", name: "轻快小跑" }, PRESETS, "side")).toBeNull();
  });

  it("编辑器跟随基础动作载入内置默认参数,view 保持不变(null)", () => {
    const state = editorStateFor({ kind: "base", name: "attack" }, PRESETS, DEFAULTS);
    expect(state?.action).toBe("attack");
    expect(state?.view).toBeNull();
    expect(state?.pose_config).toEqual(DEFAULTS);
  });

  it("编辑器跟随自定义动作载入 preset 参数(与默认合并)", () => {
    const state = editorStateFor({ kind: "custom", name: "挥刀连击" }, PRESETS, DEFAULTS);
    expect(state?.action).toBe("attack");
    expect(state?.view).toBe("front");
    expect(state?.pose_config).toEqual({ ...DEFAULTS, arm: 1.8, lag: 0.2 });
  });

  it("删除当前选中的自定义动作 → 回落到默认基础动作;删除未选中项 → 状态不变", () => {
    expect(selectionAfterRemoval("轻快小跑", { kind: "custom", name: "轻快小跑" })).toEqual({
      kind: "base",
      name: "walk",
    });
    expect(
      selectionAfterRemoval("轻快小跑", { kind: "custom", name: "挥刀连击" }),
    ).toBeNull();
    expect(selectionAfterRemoval("轻快小跑", { kind: "base", name: "idle" })).toBeNull();
  });
});

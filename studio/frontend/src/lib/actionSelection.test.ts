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

  it("基础动作生成:参数不传(内置默认),view 取工作区选择,无自定义身份", () => {
    const plan = resolveGeneration({ kind: "base", name: "walk" }, PRESETS, "front");
    expect(plan).toEqual({ action: "walk", view: "front" });
    expect(plan?.pose_config).toBeUndefined();
    expect(plan?.custom_action).toBeUndefined();
  });

  it("自定义动作生成:严格按 preset 保存时的 action/view/pose_config 原样", () => {
    const plan = resolveGeneration({ kind: "custom", name: "轻快小跑" }, PRESETS, "front");
    expect(plan).toEqual({
      action: "run",
      view: "side",
      pose_config: { ...DEFAULTS, stride: 1.6, bob: 1.3 },
      custom_action: "轻快小跑",
    });
    // 工作区视角不影响自定义动作——即使当前是 front 也用保存的 side
    expect(resolveGeneration({ kind: "custom", name: "轻快小跑" }, PRESETS, "front")?.view).toBe(
      "side",
    );
  });

  it("命名空间隔离:自定义动作必带 custom_action 身份,运动族(action)不代表归属", () => {
    // 敲竹板场景复现:自定义动作保存的运动族是 walk,生成计划也必须
    // 携带 custom_action 名称——后端据此以 "custom:<名称>" 记账,
    // 绝不占用内置 walk 槽位
    const clapper: ActionPresetLike = {
      name: "原地敲竹板待机循环动画",
      action: "walk",
      view: "side",
      pose_config: { ...DEFAULTS },
    };
    const plan = resolveGeneration({ kind: "custom", name: clapper.name }, [clapper], "front");
    expect(plan?.action).toBe("walk"); // 仅运动族
    expect(plan?.custom_action).toBe("原地敲竹板待机循环动画"); // 播放归属
    expect(plan?.custom_action).not.toBe(plan?.action);
  });

  it("同名冲突:自定义动作与内置动作同名时,两个命名空间互不污染", () => {
    const builtinNamed: ActionPresetLike = {
      name: "walk",
      action: "walk",
      view: "front",
      pose_config: { ...DEFAULTS },
    };
    // 自定义身份始终携带(后端加 custom: 前缀记账)
    const customPlan = resolveGeneration({ kind: "custom", name: "walk" }, [builtinNamed], "front");
    expect(customPlan?.custom_action).toBe("walk");
    expect(customPlan?.action).toBe("walk");
    // 基础动作生成无 custom_action —— 不可能与自定义记录混淆
    const basePlan = resolveGeneration({ kind: "base", name: "walk" }, [builtinNamed], "front");
    expect(basePlan?.custom_action).toBeUndefined();
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

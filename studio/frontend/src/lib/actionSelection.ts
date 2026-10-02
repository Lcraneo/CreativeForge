/**
 * 基础动作与自定义动作的分离选择模型。
 *
 * 内置 5 个基础动作与用户保存的自定义动作是两套完全独立的来源:
 * - 任意时刻至多一个「当前活跃动作」(判别联合 ActionSource),基础与
 *   自定义互斥——选中一侧自动取消另一侧,杜绝按钮状态互相干扰;
 * - 生成参数一律从选中来源解析:基础动作使用内置默认参数(姿态引擎
 *   内置曲线),自定义动作严格按保存时的 action/view/pose_config 原样
 *   生成,二者不走同一条参数路径。
 */
import type { PoseConfig } from "../api/client";

export const BUILTIN_ACTIONS = ["idle", "walk", "run", "attack", "jump"] as const;
export type BuiltinAction = (typeof BUILTIN_ACTIONS)[number];

export interface ActionPresetLike {
  name: string;
  action: string;
  view: string;
  pose_config: PoseConfig;
}

export type ActionSource = { kind: "base"; name: string } | { kind: "custom"; name: string };

export interface GenerationPlan {
  action: string;
  view: string;
  pose_config?: PoseConfig;
}

export function isBuiltinAction(name: string): boolean {
  return (BUILTIN_ACTIONS as readonly string[]).includes(name);
}

/** 生成参数解析。
 * 基础动作:view 取工作区视角选择,pose_config 不传(姿态引擎内置默认);
 * 自定义动作:action/view/pose_config 全部来自 preset 原样。
 * 选中项在 presets 中已不存在(被删除)时返回 null,生成按钮保持禁用。 */
export function resolveGeneration(
  source: ActionSource,
  presets: ActionPresetLike[],
  workspaceView: string,
): GenerationPlan | null {
  if (source.kind === "base") {
    if (!isBuiltinAction(source.name)) return null;
    return { action: source.name, view: workspaceView };
  }
  const preset = presets.find((item) => item.name === source.name);
  if (!preset) return null;
  return { action: preset.action, view: preset.view, pose_config: preset.pose_config };
}

/** 编辑器(预览台)跟随选中动作载入的姿态状态。
 * 基础动作:载入内置默认参数,view 返回 null 表示保持编辑器当前视角;
 * 自定义动作:载入 preset 参数。 */
export function editorStateFor(
  source: ActionSource,
  presets: ActionPresetLike[],
  defaults: PoseConfig,
): { action: string; view: string | null; pose_config: PoseConfig } | null {
  if (source.kind === "base") {
    if (!isBuiltinAction(source.name)) return null;
    return { action: source.name, view: null, pose_config: { ...defaults } };
  }
  const preset = presets.find((item) => item.name === source.name);
  if (!preset) return null;
  return {
    action: preset.action,
    view: preset.view,
    pose_config: { ...defaults, ...preset.pose_config },
  };
}

/** 删除自定义动作后的回落选中项:被删的是当前选中项时回到默认基础动作。 */
export function selectionAfterRemoval(
  removedName: string,
  current: ActionSource,
  fallback: BuiltinAction = "walk",
): ActionSource | null {
  if (current.kind === "custom" && current.name === removedName) {
    return { kind: "base", name: fallback };
  }
  return null;
}

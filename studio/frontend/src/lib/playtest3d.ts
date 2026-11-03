import type { Playtest3DClip, Playtest3DManifest } from "../types";

/** 试玩舞台 3D POC-0 的动作契约纯函数。

 * 只做「字符串 / 布尔 → 标准动作」的无副作用映射，供页面与 Canvas 共用；
 * 禁止在此出现 three / React 依赖（动画状态机与渲染各自独立实现）。
 */

export const STANDARD_ACTIONS = ["idle", "walk", "run", "jump", "attack"] as const;
export type StandardAction = (typeof STANDARD_ACTIONS)[number];

/** 循环播放的动作；jump/attack 为一次性（播放完回 idle）。 */
export const LOOP_ACTIONS: ReadonlySet<StandardAction> = new Set(["idle", "walk", "run"]);

/** manifest 缺省声明的 5 个标准动作（后端未返回 clips 时的兜底）。 */
export const STANDARD_CLIPS: Playtest3DClip[] = [
  { name: "idle", loop: true },
  { name: "walk", loop: true },
  { name: "run", loop: true },
  { name: "jump", loop: false },
  { name: "attack", loop: false },
];

/** GLB 加载/校验失败原因（由 Canvas 在加载后裁定）。 */
export type Playtest3DLoadError = "download_failed" | "parse_failed" | "no_skeleton" | "no_animations";

export function isLoopAction(action: string): boolean {
  return LOOP_ACTIONS.has(action as StandardAction);
}

export function defaultAction(): StandardAction {
  return "idle";
}

/** 把 GLB clip 名规整为可比较的小写无分隔形式。 */
export function normalizeClipName(name: string): string {
  return name.trim().toLowerCase().replace(/[\s_-]+/g, "");
}

/** 判断某个 GLB clip 名是否可作为指定标准动作的源片段。 */
export function clipMatchesAction(clipName: string, action: StandardAction): boolean {
  return normalizeClipName(clipName) === action;
}

/** 每个标准动作实际对应的 GLB source clip 名；缺失时为 null。 */
export type ResolvedClips = Record<StandardAction, string | null>;

/**
 * 把 GLB 实际携带的 clip 名映射到 5 个标准动作。
 * 优先使用 manifest 的 source_clip；否则按名字就近匹配。
 */
export function resolveClips(
  clipNames: readonly string[],
  manifestClips: readonly Playtest3DClip[],
): ResolvedClips {
  const byName = new Map(manifestClips.map((clip) => [clip.name, clip]));
  const resolved = {} as ResolvedClips;
  for (const action of STANDARD_ACTIONS) {
    const declared = byName.get(action);
    const source = declared?.source_clip;
    if (source && clipNames.includes(source)) {
      resolved[action] = source;
      continue;
    }
    resolved[action] = clipNames.find((name) => clipMatchesAction(name, action)) ?? null;
  }
  return resolved;
}

/** 缺失的动作列表（用于「未生成」提示）。 */
export function missingActions(resolved: ResolvedClips): StandardAction[] {
  return STANDARD_ACTIONS.filter((action) => !resolved[action]);
}

/** manifest declared 的 clips；后端未返回时回落 5 个标准动作。 */
export function effectiveClips(manifest: Playtest3DManifest): Playtest3DClip[] {
  return manifest.clips?.length ? manifest.clips : STANDARD_CLIPS;
}

/** 后端 manifest 的「不可用」原因 → 用户可读文案。 */
export function manifestErrorLabel(error: string | null | undefined): string {
  switch (error) {
    case "mesh_missing":
      return "该角色尚未生成 3D 模型";
    case "mesh_failed":
      return "3D 模型生成失败";
    case "unsupported_format":
      return "3D 模型格式不受支持";
    case "path_invalid":
      return "3D 模型文件路径无效";
    case "asset_not_found":
      return "未找到该角色资产";
    default:
      return "3D 资源不可用";
  }
}

/** Canvas 加载/校验失败原因 → 用户可读文案。 */
export function loadErrorLabel(error: Playtest3DLoadError): string {
  switch (error) {
    case "download_failed":
      return "GLB 下载失败";
    case "parse_failed":
      return "GLB 文件损坏或无法解析";
    case "no_skeleton":
      return "GLB 缺少骨骼（skin），无法播放动画";
    case "no_animations":
      return "GLB 不含任何动画片段";
  }
}

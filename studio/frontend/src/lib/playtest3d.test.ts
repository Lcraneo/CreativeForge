import { describe, expect, it } from "vitest";
import type { Playtest3DClip, Playtest3DManifest } from "../types";
import {
  STANDARD_ACTIONS,
  STANDARD_CLIPS,
  defaultAction,
  effectiveClips,
  clipMatchesAction,
  isLoopAction,
  loadErrorLabel,
  manifestErrorLabel,
  missingActions,
  normalizeClipName,
  resolveClips,
} from "./playtest3d";

const fixtureClips: Playtest3DClip[] = [
  { name: "idle", source_clip: "Idle", loop: true },
  { name: "walk", source_clip: "Walk", loop: true },
  { name: "run", source_clip: "Run", loop: true },
  { name: "jump", source_clip: "Jump", loop: false },
  { name: "attack", source_clip: "Attack", loop: false },
];

describe("动作契约常量", () => {
  it("只暴露 5 个标准动作且顺序稳定", () => {
    expect(STANDARD_ACTIONS).toEqual(["idle", "walk", "run", "jump", "attack"]);
  });

  it("循环/一次性规则：idle/walk/run 循环，jump/attack 一次性", () => {
    expect(STANDARD_ACTIONS.map(isLoopAction)).toEqual([
      true,
      true,
      true,
      false,
      false,
    ]);
    expect(defaultAction()).toBe("idle");
  });
});

describe("normalizeClipName / clipMatchesAction", () => {
  it("忽略大小写与分隔符差异", () => {
    expect(normalizeClipName("Idle")).toBe("idle");
    expect(normalizeClipName(" Run ")).toBe("run");
    expect(normalizeClipName("leg_upper_L")).toBe("legupperl");
    expect(clipMatchesAction("Idle", "idle")).toBe(true);
    expect(clipMatchesAction("attack_01", "attack")).toBe(false);
  });
});

describe("resolveClips", () => {
  it("优先用 manifest 的 source_clip，建立动作→GLB clip 映射", () => {
    const resolved = resolveClips(["Idle", "Walk", "Run", "Jump", "Attack"], fixtureClips);
    expect(resolved.idle).toBe("Idle");
    expect(resolved.jump).toBe("Jump");
    expect(resolved.attack).toBe("Attack");
    expect(missingActions(resolved)).toEqual([]);
  });

  it("manifest 没给 source_clip 时按名字就近匹配", () => {
    const clips: Playtest3DClip[] = STANDARD_CLIPS.map((c) => ({ ...c, source_clip: null }));
    const resolved = resolveClips(["idle", "walk", "run"], clips);
    expect(resolved.idle).toBe("idle");
    expect(resolved.walk).toBe("walk");
    expect(resolved.run).toBe("run");
    expect(resolved.jump).toBeNull();
    expect(resolved.attack).toBeNull();
    expect(missingActions(resolved)).toEqual(["jump", "attack"]);
  });

  it("source_clip 指向的 clip 不存在时回退名字匹配", () => {
    const clips: Playtest3DClip[] = [
      { name: "idle", source_clip: "DoesNotExist", loop: true },
    ];
    expect(resolveClips(["idle", "walk"], clips).idle).toBe("idle");
  });

  it("缺少动作不得借其他动作片段（返回 null 而不是错配）", () => {
    const resolved = resolveClips(["idle"], STANDARD_CLIPS);
    expect(resolved.walk).toBeNull();
    expect(resolved.run).toBeNull();
    expect(resolved.jump).toBeNull();
    expect(resolved.attack).toBeNull();
  });
});

describe("effectiveClips", () => {
  const manifest = (clips: Playtest3DClip[]): Playtest3DManifest => ({
    version: "1.0",
    asset_id: "x",
    available: true,
    clips,
    fallback_url: "/playtest",
  });

  it("manifest clips 为空时回落 5 个标准动作", () => {
    expect(effectiveClips(manifest([]))).toEqual(STANDARD_CLIPS);
    expect(effectiveClips(manifest(fixtureClips))).toEqual(fixtureClips);
  });
});

describe("错误文案", () => {
  it("manifest 错误有可读文案", () => {
    expect(manifestErrorLabel("mesh_missing")).toContain("3D");
    expect(manifestErrorLabel("asset_not_found")).toContain("未找到");
    expect(manifestErrorLabel(null)).toBe("3D 资源不可用");
    expect(manifestErrorLabel("bogus")).toBe("3D 资源不可用");
  });

  it("加载错误有可读文案", () => {
    expect(loadErrorLabel("no_skeleton")).toContain("骨骼");
    expect(loadErrorLabel("no_animations")).toContain("动画片段");
    expect(loadErrorLabel("download_failed")).toContain("下载失败");
    expect(loadErrorLabel("parse_failed")).toContain("损坏");
  });
});
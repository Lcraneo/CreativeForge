import { useMemo } from "react";
import type { TaskEvent } from "../types";

/** 事件分类：筛选片（chips）按此聚合 */
export type StreamKind = "schedule" | "generate" | "engine" | "quality" | "system";

export interface StreamItem {
  /** 稳定键 = 事件在日志中的序号（append-only，不用数组下标防错位） */
  id: string;
  raw: string;
  kind: StreamKind;
  title: string;
  tone: "primary" | "success" | "danger" | "warning" | "precon" | "falign" | "neutral";
  at?: number;
  agent?: string;
  detail?: string;
  repair?: boolean;
}

export const STREAM_KINDS: Array<{ id: StreamKind; label: string }> = [
  { id: "schedule", label: "调度" },
  { id: "generate", label: "生成" },
  { id: "engine", label: "引擎" },
  { id: "quality", label: "质量" },
  { id: "system", label: "系统" },
];

const EVENT_META: Record<string, { kind: StreamKind; title: string; tone: StreamItem["tone"] }> = {
  PLAN_CREATED: { kind: "schedule", title: "任务图就绪", tone: "primary" },
  AGENT_START: { kind: "schedule", title: "节点启动", tone: "primary" },
  AGENT_DONE: { kind: "schedule", title: "节点完成", tone: "success" },
  PROGRESS: { kind: "schedule", title: "进度推进", tone: "falign" },
  MODEL_START: { kind: "generate", title: "模型开工", tone: "primary" },
  MODEL_ENHANCE: { kind: "generate", title: "提示词增强", tone: "precon" },
  MODEL_IMAGE: { kind: "generate", title: "原画出图", tone: "success" },
  MODEL_FALLBACK: { kind: "generate", title: "模型降级", tone: "danger" },
  ASSET_UPDATE: { kind: "engine", title: "资产更新", tone: "precon" },
  QUALITY_REPORT: { kind: "quality", title: "质量报告", tone: "warning" },
  TASK_COMPLETE: { kind: "quality", title: "任务完成", tone: "success" },
  TASK_FAILED: { kind: "quality", title: "任务失败", tone: "danger" },
  STREAM_END: { kind: "system", title: "流结束", tone: "neutral" },
  ERROR: { kind: "system", title: "流错误", tone: "danger" },
};

export function normalizeTaskEvents(events: TaskEvent[]): StreamItem[] {
  return events.map((event, index) => {
    const meta = EVENT_META[event.type] ?? { kind: "system" as const, title: event.type, tone: "neutral" as const };
    return {
      id: `e${index}`,
      raw: event.type,
      kind: meta.kind,
      title: meta.title,
      tone: meta.tone,
      at: event.at,
      agent: event.agent ?? event.task,
      detail: event.detail ?? event.action ?? event.stage ?? (event.progress != null ? `${event.progress}%` : undefined),
      repair: event.repair,
    };
  });
}

/** 追加式日志的内存上限：超出后从头丢弃（老事件去历史页看） */
export function trimBuffer<T>(items: T[], max: number): T[] {
  return items.length <= max ? items : items.slice(items.length - max);
}

export interface FeedFilter {
  kind: StreamKind | "all";
  query: string;
}

export function filterStreamItems(items: StreamItem[], filter: FeedFilter): StreamItem[] {
  const q = filter.query.trim().toLowerCase();
  return items.filter((item) => {
    if (filter.kind !== "all" && item.kind !== filter.kind) return false;
    if (!q) return true;
    return `${item.raw} ${item.title} ${item.agent ?? ""} ${item.detail ?? ""}`
      .toLowerCase()
      .includes(q);
  });
}

export function countByKind(items: StreamItem[]): Record<StreamKind, number> {
  const counts = { schedule: 0, generate: 0, engine: 0, quality: 0, system: 0 };
  for (const item of items) counts[item.kind] += 1;
  return counts;
}

/** AgentDashboard 事件数组 → 筛选/搜索就绪的流（全部 memo 化） */
export function useTaskFeed(events: TaskEvent[], buffer = 400) {
  return useMemo(() => {
    const items = trimBuffer(normalizeTaskEvents(events), buffer);
    return { items, counts: countByKind(items) };
  }, [events, buffer]);
}

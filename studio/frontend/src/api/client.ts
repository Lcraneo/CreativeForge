import type {
  BenchmarkReport,
  CreativeAsset,
  ExportResult,
  GenerationOverrides,
  HistoryRecord,
  HistorySummary,
  ModelSettings,
  ModelTestResult,
  TaskEvent,
  TaskSummary,
} from "../types";

export interface TaskDetail {
  task_id: string;
  goal: string;
  status: string;
  plan: import("../types").Plan | null;
  asset_id: string | null;
  error: string | null;
  events: TaskEvent[];
}

export interface StyleProfile {
  style: string;
  style_label: string;
  confidence: number;
  palette_size: number;
  edge_density: number;
  flat_ratio: number;
  saturation: number;
  luminance_std: number;
}

export interface ConsistencyReport {
  palette: number;
  color: number;
  line: number;
  hash: number;
  overall: number;
  passed: boolean;
  floor: number;
  frames_checked: number;
}

export interface AnimationResult {
  id: string;
  source: string;
  action: string;
  fps: number;
  duration: number;
  frame_count: number;
  size: number;
  loop: boolean;
  style: StyleProfile;
  style_label: string;
  character: {
    bbox: number[];
    size: number[];
    aspect: number;
    head_ratio: number;
    center: number[];
    palette: string[];
  };
  consistency: ConsistencyReport;
  sheet_size: number[];
  frames: number;
  urls: { gif: string; sheet: string; thumb: string };
  created_at: number;
}

export interface AnimationRequestPayload {
  asset_id?: string;
  image?: string;
  action?: string;
  fps?: number;
  duration?: number;
  size?: number;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...init,
  });
  if (!response.ok) {
    const detail = await response.text().catch(() => response.statusText);
    throw new Error(`${response.status}: ${detail}`);
  }
  return response.json() as Promise<T>;
}

export const api = {
  health: () => request<{ status: string }>("/api/health"),

  createTask: (goal: string, overrides?: GenerationOverrides) =>
    request<{ task_id: string; status: string; stream_url: string }>(
      "/api/tasks",
      { method: "POST", body: JSON.stringify({ goal, overrides }) },
    ),

  listTasks: () => request<{ tasks: TaskSummary[] }>("/api/tasks"),

  getTaskDetail: (taskId: string) =>
    request<TaskDetail>(`/api/tasks/${taskId}`),

  getAsset: (assetId: string) => request<CreativeAsset>(`/api/assets/${assetId}`),

  generateDesignViews: (assetId: string) =>
    request<CreativeAsset["design_views"]>("/api/design/views", {
      method: "POST",
      body: JSON.stringify({ asset_id: assetId }),
    }),

  latestAsset: () => request<CreativeAsset>("/api/assets/latest"),

  createAnimation: (payload: AnimationRequestPayload) =>
    request<AnimationResult>("/api/animation", {
      method: "POST",
      body: JSON.stringify(payload),
    }),

  analyzeAnimationSource: (image: string) =>
    request<{ style: StyleProfile; character: AnimationResult["character"]; palette: string[] }>(
      "/api/animation/analyze",
      { method: "POST", body: JSON.stringify({ image }) },
    ),

  exportAsset: (assetId: string, engine: string) =>
    request<ExportResult>("/api/export", {
      method: "POST",
      body: JSON.stringify({ asset_id: assetId, engine }),
    }),

  benchmark: () => request<BenchmarkReport>("/api/benchmark"),

  listHistory: (params: { engine?: string; q?: string; limit?: number } = {}) => {
    const search = new URLSearchParams();
    if (params.engine) search.set("engine", params.engine);
    if (params.q) search.set("q", params.q);
    if (params.limit) search.set("limit", String(params.limit));
    const query = search.toString();
    return request<{ records: HistorySummary[]; total: number }>(
      `/api/history${query ? `?${query}` : ""}`,
    );
  },

  getHistory: (recordId: string) => request<HistoryRecord>(`/api/history/${recordId}`),

  deleteHistory: (recordId: string) =>
    request<{ status: string; removed: number }>(`/api/history/${recordId}`, {
      method: "DELETE",
    }),

  clearHistory: () =>
    request<{ status: string }>("/api/history", { method: "DELETE" }),

  getModelSettings: () => request<ModelSettings>("/api/settings/model"),

  getModelPresets: () =>
    request<{ presets: Record<string, import("../types").ProviderPreset> }>(
      "/api/settings/model/presets",
    ),

  saveModelSettings: (payload: Partial<ModelSettings> & { api_key?: string | null }) =>
    request<ModelSettings>("/api/settings/model", {
      method: "PUT",
      body: JSON.stringify(payload),
    }),

  testModelSettings: () =>
    request<ModelTestResult>("/api/settings/model/test", { method: "POST" }),

  clearModelKey: () =>
    request<ModelSettings>("/api/settings/model/key", { method: "DELETE" }),
};

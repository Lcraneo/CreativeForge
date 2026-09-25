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

  latestAsset: () => request<CreativeAsset>("/api/assets/latest"),

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

  clearHistory: () =>
    request<{ status: string }>("/api/history", { method: "DELETE" }),

  getModelSettings: () => request<ModelSettings>("/api/settings/model"),

  getModelPresets: () =>
    request<{ presets: import("../types").ProviderPreset[] }>("/api/settings/model/presets"),

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

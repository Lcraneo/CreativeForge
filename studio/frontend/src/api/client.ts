import type {
  BenchmarkReport,
  CreativeAsset,
  ExportResult,
  GenerationOverrides,
  HistoryRecord,
  HistorySummary,
  ModelSettings,
  ModelTestResult,
  MultipartSession,
  StorageConfigList,
  StorageConfigPublic,
  StorageTestResult,
  BatchExportResult,
  BatchStatus,
  PixelEditResult,
  RollbackRecord,
  TaskEvent,
  TaskSummary,
  VersionDiff,
  VersionGroup,
  VersionTree,
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
  frame_urls?: string[];
  urls: { gif: string; sheet: string; thumb: string };
  created_at: number;
}

export interface PoseConfig {
  [key: string]: number;
}

export interface CustomActionPreset {
  name: string;
  action: string;
  view: string;
  pose_config: PoseConfig;
  created_at: number;
  updated_at: number;
}

export interface AnimationRequestPayload {
  asset_id?: string;
  image?: string;
  action?: string;
  fps?: number;
  duration?: number;
  size?: number;
  skeletal?: boolean;
  view?: string;
  pose_config?: PoseConfig;
  use_video?: boolean;
}

export interface PlanTask {
  id: string;
  capability: string;
  agent: string;
  action: string;
  engine?: string;
}

export interface PlanResult {
  goal: string;
  asset_id?: string | null;
  mode: string;
  intent: {
    engine: string;
    style: string;
    animation: boolean;
    static: boolean;
    pixel: boolean;
    modify: boolean;
    engine_import: boolean;
  };
  tasks: PlanTask[];
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

  /* ── P1-A 版本控制 ── */
  versionGroups: () =>
    request<{ groups: VersionGroup[] }>("/api/versions/groups"),
  versionTree: (name: string) =>
    request<VersionTree>(`/api/versions/tree?name=${encodeURIComponent(name)}`),
  versionDiff: (name: string, a: number, b: number) =>
    request<VersionDiff>(
      `/api/versions/diff?name=${encodeURIComponent(name)}&a=${a}&b=${b}`,
    ),
  rollbackVersions: (recordIds: string[]) =>
    request<{
      status: string;
      restored: number;
      entries: { ok?: boolean; record_id: string; asset_id?: string; name?: string | null; version_no?: number | null; error?: string }[];
      rollback_id: string;
      current_asset_id: string | null;
    }>("/api/versions/rollback", {
      method: "POST",
      body: JSON.stringify({ record_ids: recordIds }),
    }),
  rollbackLog: () =>
    request<{ rollbacks: RollbackRecord[] }>("/api/versions/rollbacks"),
  tagVersion: (recordId: string, tag: string) =>
    request<{ status: string; record_id: string; tag: string }>("/api/versions/tag", {
      method: "POST",
      body: JSON.stringify({ record_id: recordId, tag }),
    }),
  reviewAsset: (assetId: string, approved: boolean, note?: string) =>
    request<{ status: string; asset_id: string | null; review: import("../types").ReviewInfo }>(
      "/api/assets/review",
      { method: "POST", body: JSON.stringify({ asset_id: assetId, approved, note }) },
    ),
  restyleAsset: (assetId: string, style: string) =>
    request<import("../types").RestyleInfo>("/api/design/restyle", {
      method: "POST",
      body: JSON.stringify({ asset_id: assetId, style }),
    }),
  cutoutAsset: (assetId: string) =>
    request<{ status: string; cutout_png: string; asset_id: string | null }>("/api/design/cutout", {
      method: "POST",
      body: JSON.stringify({ asset_id: assetId }),
    }),
  rigCheck: (assetId?: string | null) =>
    request<{
      proportion: string;
      head_ratio: number;
      head_height: number;
      confidence: number;
      recommendation: string;
      message: string;
    }>(`/api/animation/rig-check${assetId ? `?asset_id=${encodeURIComponent(assetId)}` : ""}`),
  enhanceActionText: (text: string) =>
    request<{ text: string }>("/api/animation/custom-actions/enhance", {
      method: "POST",
      body: JSON.stringify({ text }),
    }),
  interpretActionText: (text: string) =>
    request<import("../types").InterpretedAction>("/api/animation/custom-actions/interpret", {
      method: "POST",
      body: JSON.stringify({ text }),
    }),
  playtestPreviews: (assetId?: string | null) =>
    request<import("../types").PlaytestPreviews>(
      `/api/playtest/previews${assetId ? `?asset_id=${encodeURIComponent(assetId)}` : ""}`,
    ),

  /* ── P1-B 批量生产线 ── */
  startBatch: (goal: string, count: number, mode: string, overrides?: Record<string, unknown>) =>
    request<{ batch_id: string; count: number; mode: string }>("/api/batch", {
      method: "POST",
      body: JSON.stringify({ goal, count, mode, overrides }),
    }),
  batchStatus: (batchId: string) =>
    request<BatchStatus>(`/api/batch/${batchId}`),
  batchExport: (assetIds: string[], engine: string) =>
    request<BatchExportResult>("/api/export/batch", {
      method: "POST",
      body: JSON.stringify({ asset_ids: assetIds, engine }),
    }),

  /* ── P2 像素编辑 ── */
  savePixelEdit: (assetId: string, pixels: Array<Array<string | null>>, palette?: string[]) =>
    request<PixelEditResult>(`/api/assets/${assetId}/pixel`, {
      method: "PUT",
      body: JSON.stringify({ pixels, palette }),
    }),

  createTask: (goal: string, overrides?: GenerationOverrides, turbo?: boolean) =>
    request<{ task_id: string; status: string; stream_url: string }>(
      "/api/tasks",
      { method: "POST", body: JSON.stringify({ goal, overrides, turbo }) },
    ),

  plan: (goal: string, assetId?: string) =>
    request<PlanResult>("/api/plan", {
      method: "POST",
      body: JSON.stringify({ goal, asset_id: assetId }),
    }),

  enhancePrompt: (goal: string, overrides?: GenerationOverrides) =>
    request<{ model: string; prompt: string }>("/api/prompt/enhance", {
      method: "POST",
      body: JSON.stringify({ goal, overrides }),
    }),

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

  createAnimationSequence: (payload: { frames: string[]; fps?: number; size?: number }) =>
    request<AnimationResult>("/api/animation/sequence", {
      method: "POST",
      body: JSON.stringify(payload),
    }),

  previewAnimationFrame: async (payload: {
    asset_id?: string;
    action: string;
    view: string;
    phase: number;
    size?: number;
    pose_config?: PoseConfig;
  }): Promise<string> => {
    const response = await fetch("/api/animation/preview-frame", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    if (!response.ok) throw new Error(`${response.status}: ${await response.text()}`);
    return URL.createObjectURL(await response.blob());
  },

  listCustomActions: () =>
    request<{ actions: CustomActionPreset[] }>("/api/animation/custom-actions"),

  saveCustomAction: (payload: { name: string; action: string; view: string; pose_config: PoseConfig }) =>
    request<CustomActionPreset>("/api/animation/custom-actions", {
      method: "POST",
      body: JSON.stringify(payload),
    }),

  deleteCustomAction: (name: string) =>
    request<{ status: string }>(`/api/animation/custom-actions/${encodeURIComponent(name)}`, {
      method: "DELETE",
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

  // ── 对象存储：API 配置（CRUD + 设默认 + 连通性测试） ─────────────────────
  // 凭证本地加密存储、界面脱敏；新增/编辑时提交明文，后端落盘加密。
  listStorageConfigs: () =>
    request<StorageConfigList>("/api/storage/configs"),

  createStorageConfig: (payload: Record<string, unknown>) =>
    request<StorageConfigPublic>("/api/storage/configs", {
      method: "POST",
      body: JSON.stringify(payload),
    }),

  updateStorageConfig: (id: string, payload: Record<string, unknown>) =>
    request<StorageConfigPublic>(`/api/storage/configs/${id}`, {
      method: "PUT",
      body: JSON.stringify(payload),
    }),

  deleteStorageConfig: (id: string) =>
    request<{ status: string; removed: string }>(
      `/api/storage/configs/${id}`,
      { method: "DELETE" },
    ),

  setDefaultStorageConfig: (id: string) =>
    request<StorageConfigPublic>(`/api/storage/configs/${id}/default`, {
      method: "POST",
    }),

  testStorageConfig: (payload: {
    config_id?: string;
    provider?: string;
    access_key?: string;
    secret_key?: string;
    region?: string;
    bucket?: string;
    endpoint?: string;
    name?: string;
  }) =>
    request<StorageTestResult>("/api/storage/configs/test", {
      method: "POST",
      body: JSON.stringify(payload),
    }),

  // ── 对象存储：大文件分片上传（断点续传 / 失败重试） ─────────────────────
  startMultipart: (payload: {
    key: string;
    total_size: number;
    part_size?: number;
    content_type?: string;
    config_id?: string;
  }) =>
    request<MultipartSession>("/api/storage/multipart/start", {
      method: "POST",
      body: JSON.stringify(payload),
    }),

  getMultipartStatus: (sessionId: string) =>
    request<MultipartSession>(`/api/storage/multipart/${sessionId}`),

  resumeMultipart: (sessionId: string) =>
    request<MultipartSession>(`/api/storage/multipart/${sessionId}/resume`, {
      method: "POST",
    }),

  uploadMultipartPart: async (sessionId: string, partNumber: number, data: Blob) => {
    const form = new FormData();
    form.append("file", data, `part-${partNumber}`);
    const response = await fetch(
      `/api/storage/multipart/${sessionId}/${partNumber}`,
      { method: "PUT", body: form },
    );
    if (!response.ok) throw new Error(`${response.status}: ${await response.text()}`);
    return (await response.json()) as MultipartSession;
  },

  completeMultipart: (sessionId: string) =>
    request<MultipartSession>(`/api/storage/multipart/${sessionId}/complete`, {
      method: "POST",
    }),

  abortMultipart: (sessionId: string) =>
    request<MultipartSession>(`/api/storage/multipart/${sessionId}/abort`, {
      method: "POST",
    }),
};

import type {
  BenchmarkReport,
  CreativeAsset,
  ExportResult,
  GenerationOverrides,
  HistoryRecord,
  HistorySummary,
  ModelSettings,
  ModelTestResult,
  ModelUsage,
  MultipartSession,
  StorageConfigList,
  StorageConfigPublic,
  StorageTestResult,
  ActionBatchSnapshot,
  BatchExportResult,
  BatchStatus,
  CharacterPackageResult,
  PixelEditResult,
  RollbackRecord,
  TaskEvent,
  TaskSummary,
  VersionDiff,
  VersionGroup,
  VersionTree,
} from "../types";
import { toast } from "../stores/toastStore";

/* ── 认证：token 从 VITE_STUDIO_TOKEN 或 localStorage 读取 ──
 * header（fetch 用）与 cookie（<img src="/api/..."> 和 WebSocket 握手用）
 * 双通道同步，后端 security.py 两边都认。留空 = 后端未启用鉴权。 */
const TOKEN_STORAGE_KEY = "studio_token";

function readStoredToken(): string {
  const fromEnv = (import.meta.env.VITE_STUDIO_TOKEN ?? "").trim();
  if (fromEnv) return fromEnv;
  try {
    return localStorage.getItem(TOKEN_STORAGE_KEY) ?? "";
  } catch {
    return "";
  }
}

function writeCookie(token: string) {
  document.cookie = token
    ? `${TOKEN_STORAGE_KEY}=${encodeURIComponent(token)}; path=/; SameSite=Strict`
    : `${TOKEN_STORAGE_KEY}=; path=/; Max-Age=0; SameSite=Strict`;
}

export function setStudioToken(token: string) {
  studioToken = token.trim();
  try {
    if (studioToken) localStorage.setItem(TOKEN_STORAGE_KEY, studioToken);
    else localStorage.removeItem(TOKEN_STORAGE_KEY);
  } catch {
    /* 存储不可用（隐私模式等）：仅内存与 cookie 生效 */
  }
  writeCookie(studioToken);
}

let studioToken = "";

export function authHeaders(): Record<string, string> {
  return studioToken ? { Authorization: `Bearer ${studioToken}` } : {};
}

setStudioToken(readStoredToken());

export interface TaskDetail {
  task_id: string;
  goal: string;
  status: string;
  plan: import("../types").Plan | null;
  asset_id: string | null;
  error: string | null;
  events: TaskEvent[];
}

/* ── OneTake 发布展示视频任务（showcase_service）── */
export interface ShowcaseJob {
  id: string;
  asset_id: string | null;
  asset_name: string | null;
  status: "running" | "done" | "failed";
  stage: string;
  created_at: number;
  duration: number;
  error: string | null;
  error_kind?: string;
  verdict?: { passed: boolean | null; report_tail?: string; error?: string } | null;
  /* 配音链路状态（showcase_service voice 阶段）：degraded=true 为纯音效降级版 */
  voice?: {
    status?: string;
    degraded?: boolean;
    error?: string;
    model?: string;
    voice?: string;
    segments?: number;
    cached?: number;
    polished?: boolean;
  } | null;
  video_url?: string;
  poster_url?: string;
  preview_url?: string;
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

let lastToastKey = "";
let lastToastAt = 0;

interface RequestInitInternal extends RequestInit {
  /** 静默模式：预期可能 404 的探活请求不弹全局错误 toast，由调用方自行处理 */
  silent?: boolean;
}

async function request<T>(path: string, init?: RequestInitInternal): Promise<T> {
  const { silent, ...rest } = init ?? {};
  const response = await fetch(path, {
    ...rest,
    headers: { "Content-Type": "application/json", ...authHeaders(), ...rest?.headers },
  });
  if (!response.ok) {
    const detail = await response.text().catch(() => response.statusText);
    const error = new Error(`${response.status}: ${detail}`);
    // 统一错误提示：同一消息 2.5s 内只弹一次；页面层自己的 catch 依旧生效
    const now = Date.now();
    if (!silent && (error.message !== lastToastKey || now - lastToastAt > 2500)) {
      lastToastKey = error.message;
      lastToastAt = now;
      toast({
        tone: "danger",
        title: "请求失败",
        description: detail.slice(0, 160) || error.message,
      });
    }
    throw error;
  }
  return response.json() as Promise<T>;
}

export const api = {
  health: () => request<{ status: string }>("/api/health"),

  /* ── P1-A 版本控制 ── */
  versionGroups: () => request<{ groups: VersionGroup[] }>("/api/versions/groups"),
  versionTree: (name: string) =>
    request<VersionTree>(`/api/versions/tree?name=${encodeURIComponent(name)}`),
  versionDiff: (name: string, a: number, b: number) =>
    request<VersionDiff>(`/api/versions/diff?name=${encodeURIComponent(name)}&a=${a}&b=${b}`),
  rollbackVersions: (recordIds: string[]) =>
    request<{
      status: string;
      restored: number;
      entries: {
        ok?: boolean;
        record_id: string;
        asset_id?: string;
        name?: string | null;
        version_no?: number | null;
        error?: string;
      }[];
      rollback_id: string;
      current_asset_id: string | null;
    }>("/api/versions/rollback", {
      method: "POST",
      body: JSON.stringify({ record_ids: recordIds }),
    }),
  rollbackLog: () => request<{ rollbacks: RollbackRecord[] }>("/api/versions/rollbacks"),
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
  openFolder: (target: "generated" | "animation" | "exports") =>
    request<{ status: string; path: string }>("/api/open-folder", {
      method: "POST",
      body: JSON.stringify({ target }),
    }),
  startActionBatch: (assetId: string, actions?: string[]) =>
    request<{ batch_id: string; snapshot: ActionBatchSnapshot }>("/api/animation/batch-actions", {
      method: "POST",
      body: JSON.stringify({ asset_id: assetId, actions }),
    }),
  actionBatchStatus: (batchId: string) =>
    request<ActionBatchSnapshot>(`/api/animation/batch-actions/${batchId}`),
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

  /* ── OneTake 发布展示视频（External Creative Capability）── */
  startShowcase: (assetId: string, duration?: number) =>
    request<{ job_id: string; snapshot: ShowcaseJob }>("/api/showcase", {
      method: "POST",
      body: JSON.stringify({ asset_id: assetId, duration }),
    }),
  showcaseStatus: (jobId: string) => request<ShowcaseJob>(`/api/showcase/${jobId}`),
  /* ── P1-B 批量生产线 ── */
  startBatch: (goal: string, count: number, mode: string, overrides?: Record<string, unknown>) =>
    request<{ batch_id: string; count: number; mode: string }>("/api/batch", {
      method: "POST",
      body: JSON.stringify({ goal, count, mode, overrides }),
    }),
  batchStatus: (batchId: string) => request<BatchStatus>(`/api/batch/${batchId}`),
  queueSnapshot: () => request<import("../types").QueueSnapshot>("/api/queue/snapshot"),
  batchExport: (assetIds: string[], engine: string) =>
    request<BatchExportResult>("/api/export/batch", {
      method: "POST",
      body: JSON.stringify({ asset_ids: assetIds, engine }),
    }),
  exportCharacterPackage: (assetId: string, engine: string) =>
    request<CharacterPackageResult>("/api/export/character-package", {
      method: "POST",
      body: JSON.stringify({ asset_id: assetId, engine }),
    }),

  /* ── P2 像素编辑 ── */
  savePixelEdit: (assetId: string, pixels: Array<Array<string | null>>, palette?: string[]) =>
    request<PixelEditResult>(`/api/assets/${assetId}/pixel`, {
      method: "PUT",
      body: JSON.stringify({ pixels, palette }),
    }),

  createTask: (goal: string, overrides?: GenerationOverrides, turbo?: boolean) =>
    request<{ task_id: string; status: string; stream_url: string }>("/api/tasks", {
      method: "POST",
      body: JSON.stringify({ goal, overrides, turbo }),
    }),

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

  getTaskDetail: (taskId: string) => request<TaskDetail>(`/api/tasks/${taskId}`),

  getAsset: (assetId: string) => request<CreativeAsset>(`/api/assets/${assetId}`),

  generateDesignViews: (assetId: string) =>
    request<CreativeAsset["design_views"]>("/api/design/views", {
      method: "POST",
      body: JSON.stringify({ asset_id: assetId }),
    }),

  latestAsset: () =>
    // 探活请求：404（后端重启后尚无资产）由 assetStore 的历史回退处理，不弹全局错误
    request<CreativeAsset>("/api/assets/latest", { silent: true }),

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
    skeletal?: boolean;
    image?: string;
  }): Promise<string> => {
    const response = await fetch("/api/animation/preview-frame", {
      method: "POST",
      headers: { "Content-Type": "application/json", ...authHeaders() },
      body: JSON.stringify(payload),
    });
    if (!response.ok) throw new Error(`${response.status}: ${await response.text()}`);
    return URL.createObjectURL(await response.blob());
  },

  listCustomActions: () =>
    request<{ actions: CustomActionPreset[] }>("/api/animation/custom-actions"),

  saveCustomAction: (payload: {
    name: string;
    action: string;
    view: string;
    pose_config: PoseConfig;
  }) =>
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

  clearHistory: () => request<{ status: string }>("/api/history", { method: "DELETE" }),

  getModelSettings: () => request<ModelSettings>("/api/settings/model"),

  getModelPresets: () =>
    request<{ presets: Record<string, import("../types").ProviderPreset> }>(
      "/api/settings/model/presets",
    ),

  listStyleTemplates: () =>
    request<{ templates: import("../types").StyleTemplate[] }>(
      "/api/design/style-templates",
    ),

  saveModelSettings: (
    payload: Partial<ModelSettings> & {
      api_key?: string | null;
      api_key_pool_add?: string[];
      api_key_pool_remove?: number[];
    },
  ) =>
    request<ModelSettings>("/api/settings/model", {
      method: "PUT",
      body: JSON.stringify(payload),
    }),

  testModelSettings: () => request<ModelTestResult>("/api/settings/model/test", { method: "POST" }),

  clearModelKey: () => request<ModelSettings>("/api/settings/model/key", { method: "DELETE" }),

  modelUsage: () => request<ModelUsage>("/api/settings/model/usage"),

  clearModelUsage: () => request<{ status: string }>("/api/settings/model/usage", { method: "DELETE" }),

  // ── 对象存储：API 配置（CRUD + 设默认 + 连通性测试） ─────────────────────
  // 凭证本地加密存储、界面脱敏；新增/编辑时提交明文，后端落盘加密。
  listStorageConfigs: () => request<StorageConfigList>("/api/storage/configs"),

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
    request<{ status: string; removed: string }>(`/api/storage/configs/${id}`, {
      method: "DELETE",
    }),

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
    const response = await fetch(`/api/storage/multipart/${sessionId}/${partNumber}`, {
      method: "PUT",
      body: form,
      headers: { ...authHeaders() },
    });
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

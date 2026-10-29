import type {
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
  CharacterPackageResult,
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
  urls: { gif: string; sheet: string; thumb: string; video?: string };
  /** i2v 直通 mp4 的交付规格（分辨率/帧率/时长/码率）；GIF 兜底路径无此字段 */
  video_spec?: {
    width: number;
    height: number;
    fps: number;
    duration: number;
    bytes: number;
    bitrate_kbps?: number;
  };
  /** V3.5 装备/服装识别（看图认出武器/甲胄/裙装/披风/发长/饰物，labels 为中文徽章文案） */
  equipment?: EquipmentInfo;
  /** V3.5 流畅度：walk/run 帧混合（伪运动模糊）已应用 */
  motion_blend?: boolean;
  /** V3.5 生成后自动质检：三维量化指标分级（pass/warn/fail）+ 可读问题列表 */
  qa?: { grade: "pass" | "warn" | "fail"; metrics?: Record<string, number>; issues?: string[] };
  created_at: number;
}

/** V3.5 装备/服装识别结果。labels 为中文标签（前端徽章直接渲染），
 * summary_* 为拼好的中/英摘要（i2v 润色上下文用）。 */
export interface EquipmentInfo {
  weapon?: string | null;
  weapon_label?: string | null;
  armor?: string;
  skirt?: boolean;
  skirt_length?: string;
  cape?: boolean;
  hair?: string;
  outfit?: string;
  accessories?: string[];
  labels?: string[];
  summary_zh?: string;
  summary_en?: string;
}

/** 多段编排段（AI 解读「先…然后…」类描述生成）：action 为该段基元，
 * weight 为时长比重，turn 为该段转身幅度（度）。 */
export interface MotionPhase {
  action: string;
  weight: number;
  turn?: number;
}

/** 姿态参数：数值键为滑杆参数（bob/stride/arm/lift/lean/lag/cycles/turn），
 * phases 为可选多段编排（非数值，保存/生成链路透传）。 */
export type PoseConfig = { [key: string]: number } & { phases?: MotionPhase[] };

export interface CustomActionPreset {
  name: string;
  action: string;
  view: string;
  pose_config: PoseConfig;
  created_at: number;
  updated_at: number;
  /** 动作完整描述（自然语言创作时用户输入的原文，可空） */
  description?: string;
  /** 修改次数：创建=1，每次覆盖保存/改名 +1 */
  revision?: number;
}

/** 修改历史快照：一次覆盖保存前的旧版本（最新在前，后端封顶 12 条） */
export interface CustomActionHistoryEntry {
  time: number;
  /** edit=编辑覆盖 / import=动作包导入覆盖 */
  trigger: string;
  revision: number;
  action: string;
  view: string;
  pose_config: PoseConfig;
  description?: string;
}

/** 动作详情（GET /api/animation/custom-actions/{name}）：列表字段 + 修改历史 */
export interface CustomActionDetail extends CustomActionPreset {
  history: CustomActionHistoryEntry[];
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
  /** V2 双档：定稿档走 video_model_final（plus）出片，成本约 2.8× */
  final_quality?: boolean;
  /** V3 网格变形：膝/肘皮肤化开关；缺省跟随后端默认（mesh） */
  deform?: "mesh" | "rigid";
  /** V3 次级运动：发层摆动（首次对该源图花约 0.3 元提取发层，之后缓存免费） */
  secondary_motion?: boolean;
  /** V3.5 装备/服装识别：骨骼链姿态自适应 + i2v 提示词贴合（按源图缓存，约 0.002 元/角色） */
  equipment_aware?: boolean;
  /** 自定义动作的用户描述：仅 i2v 链消费（独立润色通道，词表外动作的
   * 表达通道）；基础动作不带，内置词表路径保持原样 */
  action_description?: string;
  /** 自定义动作名称（命名空间隔离）：后端以此把产物记为 "custom:<名称>"，
   * 与内置动作槽位严格分离；基础动作不带 */
  custom_action?: string;
}

/** 生成任务快照（任务化轮询）：running 带 stage/progress；终态带 result
 * （done）或 error/error_kind（failed，与批次同款失败分类）；interrupted =
 * 后端重启导致任务中断（终态，落盘任务恢复标记） */
export interface VideoTaskSnapshot {
  id: string;
  status: "running" | "done" | "failed" | "interrupted";
  stage: "queued" | "prompt" | "video" | "sampling" | "composing" | "done" | "interrupted";
  progress: number;
  asset_id?: string;
  requested_action?: string;
  /** 自定义动作名称（命名空间隔离）：有值时 requested_action 为运动族，
   * 播放归属以 custom_action 为准 */
  custom_action?: string | null;
  result?: AnimationResult;
  error?: string;
  error_kind?: string;
}

let lastToastKey = "";
let lastToastAt = 0;

interface RequestInitInternal extends RequestInit {
  /** 静默模式：预期可能 404 的探活请求不弹全局错误 toast，由调用方自行处理 */
  silent?: boolean;
  /** 超时分级：普通读取/状态轮询限时；不传 = 不限时（长任务创建、同步
   * 生成等慢端点）。超时以 408 ApiError 抛出，与调用方 signal 组合生效 */
  timeoutMs?: number;
}

export class ApiError extends Error {
  constructor(public readonly status: number, detail: string) {
    super(`${status}: ${detail}`);
    this.name = "ApiError";
  }
}

async function request<T>(path: string, init?: RequestInitInternal): Promise<T> {
  const { silent, timeoutMs, ...rest } = init ?? {};
  // 手动组合调用方 signal 与超时（AbortSignal.any 尚未 everywhere）：任一
  // 触发都中止 fetch；超时转为 408 ApiError，主动取消保持 AbortError
  let signal = rest.signal ?? null;
  let timer: ReturnType<typeof setTimeout> | undefined;
  let timedOut = false;
  if (timeoutMs) {
    const controller = new AbortController();
    if (signal) {
      if (signal.aborted) controller.abort();
      else signal.addEventListener("abort", () => controller.abort(), { once: true });
    }
    timer = setTimeout(() => {
      timedOut = true;
      controller.abort();
    }, timeoutMs);
    signal = controller.signal;
  }
  let response: Response;
  try {
    response = await fetch(path, {
      ...rest,
      signal: signal ?? undefined,
      headers: { "Content-Type": "application/json", ...authHeaders(), ...rest?.headers },
    });
  } catch (cause) {
    if (timer !== undefined) clearTimeout(timer);
    if (timedOut && !(cause instanceof Error && cause.name === "AbortError" && rest.signal?.aborted)) {
      throw new ApiError(408, "请求超时，请检查网络后重试");
    }
    throw cause;
  }
  if (timer !== undefined) clearTimeout(timer);
  if (!response.ok) {
    const detail = await response.text().catch(() => response.statusText);
    const error = new ApiError(response.status, detail);
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
  health: () => request<{ status: string; frontend_stale?: boolean }>("/api/health"),

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
  startActionBatch: (
    assetId: string,
    actions?: string[],
    opts?: { view?: string; forceActions?: string[] },
  ) =>
    request<{ batch_id: string; snapshot: ActionBatchSnapshot }>("/api/animation/batch-actions", {
      method: "POST",
      body: JSON.stringify({
        asset_id: assetId,
        actions,
        view: opts?.view,
        force_actions: opts?.forceActions,
      }),
    }),
  actionBatchStatus: (batchId: string) =>
    request<ActionBatchSnapshot>(`/api/animation/batch-actions/${batchId}`, {
      timeoutMs: 15_000,
    }),
  /** 动作×视角矩阵：每个 (动作, 视角) 的最新交付状态与运行中批次 */
  animationMatrix: (assetId?: string | null) =>
    request<import("../types").ActionMatrix>(
      `/api/animation/matrix${assetId ? `?asset_id=${encodeURIComponent(assetId)}` : ""}`,
      { timeoutMs: 15_000 },
    ),
  rigCheck: (assetId?: string | null) =>
    request<{
      proportion: string;
      head_ratio: number;
      head_height: number;
      confidence: number;
      recommendation: string;
      message: string;
    }>(
      `/api/animation/rig-check${assetId ? `?asset_id=${encodeURIComponent(assetId)}` : ""}`,
      { timeoutMs: 15_000 },
    ),
  enhanceActionText: (text: string) =>
    request<{ text: string }>("/api/animation/custom-actions/enhance", {
      method: "POST",
      body: JSON.stringify({ text }),
    }),
  interpretActionText: (text: string, assetId?: string) =>
    request<import("../types").InterpretedAction>("/api/animation/custom-actions/interpret", {
      method: "POST",
      body: JSON.stringify({ text, asset_id: assetId }),
    }),
  /** 试玩舞台预览。V2 渐进式加载：actions 过滤内置动作（缺省=全部），
   * includeCustom=false 跳过自定义动作条带渲染——两者均向后兼容 */
  playtestPreviews: (
    assetId?: string | null,
    opts?: { actions?: string[]; includeCustom?: boolean },
  ) => {
    const search = new URLSearchParams();
    if (assetId) search.set("asset_id", assetId);
    if (opts?.actions) search.set("actions", opts.actions.join(","));
    if (opts?.includeCustom === false) search.set("include_custom", "0");
    const query = search.toString();
    return request<import("../types").PlaytestPreviews>(
      `/api/playtest/previews${query ? `?${query}` : ""}`,
    );
  },

  exportCharacterPackage: (assetId: string, engine: string) =>
    request<CharacterPackageResult>("/api/export/character-package", {
      silent: true, // 导出页保留错误并提供操作反馈，避免重复 toast
      method: "POST",
      body: JSON.stringify({ asset_id: assetId, engine }),
    }),

  createTask: (goal: string, overrides?: GenerationOverrides, turbo?: boolean) =>
    request<{ task_id: string; status: string; stream_url: string }>("/api/tasks", {
      method: "POST",
      body: JSON.stringify({ goal, overrides, turbo }),
    }),

  enhancePrompt: (goal: string, overrides?: GenerationOverrides) =>
    request<{ model: string; prompt: string }>("/api/prompt/enhance", {
      method: "POST",
      body: JSON.stringify({ goal, overrides }),
    }),

  listTasks: () => request<{ tasks: TaskSummary[] }>("/api/tasks", { timeoutMs: 15_000 }),

  getTaskDetail: (taskId: string, options?: { signal?: AbortSignal; silent?: boolean }) =>
    request<TaskDetail>(`/api/tasks/${taskId}`, { timeoutMs: 10_000, ...options }),

  getAsset: (assetId: string, options?: { signal?: AbortSignal; silent?: boolean }) =>
    request<CreativeAsset>(`/api/assets/${encodeURIComponent(assetId)}`, {
      timeoutMs: 15_000,
      ...options,
    }),

  generateDesignViews: (assetId: string) =>
    // 三视图只允许手动触发；双栏生图可能耗时数分钟，放宽到 5 分钟
    request<{
      design_views: CreativeAsset["design_views"];
      failures?: string[];
      model?: string;
      status?: string;
    }>("/api/design/views", {
      method: "POST",
      body: JSON.stringify({ asset_id: assetId }),
      timeoutMs: 300_000,
    }),

  latestAsset: (options?: { signal?: AbortSignal }) =>
    // 后端已经解析持久化历史；404 表示暂无资产，其余错误由页面提供重试。
    request<CreativeAsset>("/api/assets/latest", { timeoutMs: 15_000, ...options, silent: true }),

  createAnimation: (payload: AnimationRequestPayload) =>
    request<AnimationResult>("/api/animation", {
      method: "POST",
      body: JSON.stringify(payload),
    }),

  // 生成任务化（体验优化）：AI 视频链入队立即返回，轮询阶段进度；
  // 刷新后凭 localStorage 里的 task_id 续接。idempotencyKey 由调用方在
  // 「一次用户提交」内生成——同键且任务仍在运行时后端复用，不重复扣费
  startVideoTask: (payload: AnimationRequestPayload, opts?: { idempotencyKey?: string }) =>
    request<{ task_id: string; snapshot: VideoTaskSnapshot }>("/api/animation/tasks", {
      method: "POST",
      body: JSON.stringify(payload),
      headers: opts?.idempotencyKey
        ? { "Idempotency-Key": opts.idempotencyKey }
        : undefined,
    }),

  getVideoTask: (taskId: string) =>
    request<VideoTaskSnapshot>(`/api/animation/tasks/${encodeURIComponent(taskId)}`, {
      timeoutMs: 15_000,
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
    description?: string;
    /** 编辑保存时指向被编辑的旧动作名（改名=旧名；就地修改=同名） */
    original_name?: string;
  }) =>
    request<CustomActionPreset>("/api/animation/custom-actions", {
      method: "POST",
      body: JSON.stringify(payload),
    }),

  getCustomAction: (name: string) =>
    request<CustomActionDetail>(`/api/animation/custom-actions/${encodeURIComponent(name)}`),

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
      silent: true,
      method: "POST",
      body: JSON.stringify({ asset_id: assetId, engine }),
    }),

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

  clearModelUsage: () =>
    request<{ status: string }>("/api/settings/model/usage", { method: "DELETE" }),

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

  /* ── 云生成能力（A 部分）── */
  cloudProviders: () =>
    request<import("../types").CloudProvidersResponse>("/api/settings/cloud/providers", {
      timeoutMs: 15_000,
    }),

  cloudSaveProvider: (providerId: string, changes: Record<string, unknown>) =>
    request<import("../types").CloudProvider>(
      `/api/settings/cloud/providers/${encodeURIComponent(providerId)}`,
      { method: "PUT", body: JSON.stringify(changes) },
    ),

  cloudTestProvider: (providerId: string) =>
    request<import("../types").CloudTestResult>(
      `/api/settings/cloud/providers/${encodeURIComponent(providerId)}/test`,
      { method: "POST", timeoutMs: 20_000 },
    ),

  cloudSetKey: (providerId: string, apiKey: string) =>
    request<import("../types").CloudProvider>(
      `/api/settings/cloud/providers/${encodeURIComponent(providerId)}/key`,
      { method: "PUT", body: JSON.stringify({ api_key: apiKey }) },
    ),

  cloudUsage: () =>
    request<import("../types").CloudUsageSnapshot>("/api/settings/cloud/usage", {
      timeoutMs: 15_000,
    }),

  cloudGenerateImage: (payload: {
    prompt: string;
    size?: string;
    seed?: number;
    asset_id?: string;
    provider?: string;
  }) =>
    request<import("../types").CloudGenerationResult>("/api/cloud/image", {
      method: "POST",
      body: JSON.stringify(payload),
      timeoutMs: 180_000,
    }),

  cloudGenerateAudio: (payload: {
    kind?: "dialogue" | "sfx";
    text?: string;
    prompt?: string;
    voice?: string;
    asset_id?: string;
    provider?: string;
  }) =>
    request<import("../types").CloudGenerationResult>("/api/cloud/audio", {
      method: "POST",
      body: JSON.stringify(payload),
      timeoutMs: 180_000,
    }),

  cloudStart3d: (payload: {
    prompt?: string;
    image_url?: string;
    seed?: number;
    decimation_target?: number;
    texture_size?: number;
    asset_id?: string;
    provider?: string;
  }) =>
    request<{ task_id: string; status: string; snapshot: import("../types").CloudTaskSnapshot }>(
      "/api/cloud/3d",
      { method: "POST", body: JSON.stringify(payload) },
    ),

  cloudGet3dTask: (taskId: string) =>
    request<import("../types").CloudTaskSnapshot>(
      `/api/cloud/3d/${encodeURIComponent(taskId)}`,
      { timeoutMs: 15_000 },
    ),

  cloudStartVideo: (payload: {
    prompt?: string;
    image_url?: string;
    duration?: number;
    ratio?: string;
    asset_id?: string;
    provider?: string;
  }) =>
    request<{ task_id: string; status: string; snapshot: import("../types").CloudTaskSnapshot }>(
      "/api/cloud/video",
      { method: "POST", body: JSON.stringify(payload) },
    ),

  cloudGetVideoTask: (taskId: string) =>
    request<import("../types").CloudTaskSnapshot>(
      `/api/cloud/video/${encodeURIComponent(taskId)}`,
      { timeoutMs: 15_000 },
    ),

  cloudArtifactUrl: (relPath: string) => `/api/cloud/artifacts/${relPath}`,

  /* ── 试玩舞台 3D POC-0 ── */
  /** 3D 试玩清单：无 assetId 走离网固定夹具；有则从资产 mesh 槽位解析 GLB。 */
  playtest3DManifest: (assetId?: string | null) =>
    request<import("../types").Playtest3DManifest>(
      `/api/playtest/3d${assetId ? `?asset_id=${encodeURIComponent(assetId)}` : ""}`,
    ),
};

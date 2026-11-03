import type {
  CreativeAsset,
  ExportResult,
  GenerationOverrides,
  HistoryRecord,
  HistorySummary,
  ModelSettings,
  ModelTestResult,
  ModelUsage,
  ActionBatchSnapshot,
  CharacterPackageResult,
  GameScene,
  RollbackRecord,
  SceneSummary,
  TaskEvent,
  TaskSummary,
  VersionDiff,
  VersionGroup,
  VersionTree,
} from "../types";
import { toast } from "../stores/toastStore";
import { backendUrl } from "./endpoints";

export { backendUrl } from "./endpoints";

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

export function getStudioToken(): string {
  return studioToken;
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
    response = await fetch(backendUrl(path), {
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
    opts?: {
      view?: string;
      viewsByAction?: Record<string, string>;
      forceActions?: string[];
    },
  ) =>
    request<{ batch_id: string; snapshot: ActionBatchSnapshot }>("/api/animation/batch-actions", {
      method: "POST",
      body: JSON.stringify({
        asset_id: assetId,
        actions,
        view: opts?.view,
        views_by_action: opts?.viewsByAction,
        force_actions: opts?.forceActions,
      }),
    }),
  actionBatchStatus: (batchId: string) =>
    request<ActionBatchSnapshot>(`/api/animation/batch-actions/${batchId}`, {
      timeoutMs: 15_000,
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

  createScene: (
    prompt: string,
    difficulty: "easy" | "normal" | "hard",
    gameplay: "parkour" | "pve" = "parkour",
  ) =>
    request<{ scene_id: string; status: string; stage: string }>("/api/scenes", {
      method: "POST",
      body: JSON.stringify({ prompt, difficulty, gameplay }),
    }),

  listScenes: (limit = 20) =>
    request<{ scenes: SceneSummary[] }>(`/api/scenes?limit=${limit}`, {
      timeoutMs: 15_000,
    }),

  getScene: (sceneId: string, options?: { signal?: AbortSignal; silent?: boolean }) =>
    request<GameScene>(`/api/scenes/${encodeURIComponent(sceneId)}`, {
      timeoutMs: 15_000,
      ...options,
    }),

  deleteScene: (sceneId: string) =>
    request<{ status: string; removed: string }>(
      `/api/scenes/${encodeURIComponent(sceneId)}`,
      { method: "DELETE" },
    ),

  updatePveEnemySequence: (sceneId: string, profileIds: string[], stageId?: string) =>
    request<GameScene>(`/api/scenes/${encodeURIComponent(sceneId)}/pve/enemy-sequence`, {
      method: "PUT",
      body: JSON.stringify({ profile_ids: profileIds, stage_id: stageId ?? null }),
    }),

  retrySceneBackground: (sceneId: string) =>
    request<{ scene_id: string; status: string; stage: string }>(
      `/api/scenes/${encodeURIComponent(sceneId)}/background`,
      { method: "POST" },
    ),

  listPveEnemies: () =>
    request<{ enemies: import("../types").PveEnemyProfile[] }>("/api/pve/enemies", {
      timeoutMs: 15_000,
    }),

  getPveEnemy: (enemyId: string) =>
    request<import("../types").PveEnemyProfile>(`/api/pve/enemies/${encodeURIComponent(enemyId)}`, {
      timeoutMs: 15_000,
    }),

  deletePveEnemy: (enemyId: string) =>
    request<{ status: string; removed: string }>(
      `/api/pve/enemies/${encodeURIComponent(enemyId)}`,
      { method: "DELETE" },
    ),

  rebuildPveAction: (enemyId: string, action: string) =>
    request<import("../types").PveEnemyProfile>(`/api/pve/enemies/${encodeURIComponent(enemyId)}/actions/${encodeURIComponent(action)}/rebuild`, { method: "POST" }),

  retryPveEnemy: (enemyId: string) =>
    request<import("../types").PveEnemyProfile>(
      `/api/pve/enemies/${encodeURIComponent(enemyId)}/retry`,
      { method: "POST" },
    ),

  generatePveEnemy: (
    prompt: string,
    role: "minion" | "boss",
    difficulty: "easy" | "normal" | "hard",
  ) =>
    request<import("../types").PveEnemyProfile>("/api/pve/enemies/generate", {
      method: "POST",
      body: JSON.stringify({ prompt, role, difficulty }),
    }),

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

  exportAsset: (assetId: string, engine: string) =>
    request<ExportResult>("/api/export", {
      silent: true,
      method: "POST",
      body: JSON.stringify({ asset_id: assetId, engine }),
    }),

  listHistory: (params: {
    engine?: string;
    q?: string;
    limit?: number;
    kind?: "character" | "pve_enemy";
  } = {}) => {
    const search = new URLSearchParams();
    if (params.engine) search.set("engine", params.engine);
    if (params.q) search.set("q", params.q);
    if (params.limit) search.set("limit", String(params.limit));
    if (params.kind) search.set("kind", params.kind);
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

  cloudArtifactUrl: (relPath: string) => backendUrl(`/api/cloud/artifacts/${relPath}`),

  /* ── 试玩舞台 3D POC-0 ── */
  /** 3D 试玩清单：无 assetId 走离网固定夹具；有则从资产 mesh 槽位解析 GLB。 */
  playtest3DManifest: (assetId?: string | null) =>
    request<import("../types").Playtest3DManifest>(
      `/api/playtest/3d${assetId ? `?asset_id=${encodeURIComponent(assetId)}` : ""}`,
    ),
};

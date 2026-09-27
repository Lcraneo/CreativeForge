import type {
  AssetDetail,
  AssetSummary,
  CreateResponse,
  DnaDetail,
  ExportResult,
  ProviderListing,
  RegistryArtifact,
  TaskDetail,
} from "./types";

async function asJson<T>(response: Response): Promise<T> {
  if (!response.ok) {
    const detail = await response.text();
    throw new Error(`${response.status} ${detail.slice(0, 200)}`);
  }
  return response.json() as Promise<T>;
}

async function post<T>(path: string, body?: unknown): Promise<T> {
  return asJson<T>(
    await fetch(path, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: body === undefined ? undefined : JSON.stringify(body),
    }),
  );
}

async function get<T>(path: string): Promise<T> {
  return asJson<T>(await fetch(path));
}

async function put<T>(path: string, body?: unknown): Promise<T> {
  return asJson<T>(
    await fetch(path, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: body === undefined ? undefined : JSON.stringify(body),
    }),
  );
}

async function del<T>(path: string): Promise<T> {
  return asJson<T>(await fetch(path, { method: "DELETE" }));
}

export interface CreateAssetPayload {
  prompt: string;
  engine?: string;
  user_id?: string;
  provider?: string;
  model?: string;
}

export const api = {
  createAsset: (payload: CreateAssetPayload) =>
    post<CreateResponse>("/api/v1/assets/create", payload),

  getTask: (taskId: string) => get<TaskDetail>(`/api/v1/tasks/${taskId}`),

  listTasks: (limit = 10) =>
    get<TaskDetail[]>(`/api/v1/tasks?limit=${limit}`),

  listAssets: (limit = 20) =>
    get<AssetSummary[]>(`/api/v1/assets?limit=${limit}`),

  getAsset: (assetId: string) => get<AssetDetail>(`/api/v1/assets/${assetId}`),

  getDna: (characterId: string) =>
    get<DnaDetail>(`/api/v1/dna/${characterId}`),

  exportAsset: (assetId: string, engine: string) =>
    post<ExportResult>("/api/v1/assets/export", { asset_id: assetId, engine }),

  registry: () =>
    get<{ artifacts: RegistryArtifact[] }>("/api/v1/models/registry"),

  trainModel: (name = "dna_encoder") =>
    post<{ report: { metrics_before?: { margin?: number }; metrics_after?: { margin?: number }; artifact?: { version?: number } } }>(
      "/api/v1/models/train",
      { name },
    ),

  providers: () => get<ProviderListing>("/api/v1/providers"),

  saveProviderSettings: (payload: {
    provider: string;
    model?: string;
    api_key?: string;
    secret_key?: string;
    secret_id?: string;
    app_key?: string;
  }) => put<ProviderListing>("/api/v1/providers/settings", payload),

  testProvider: (payload: { provider: string; model?: string }) =>
    post<{ ok: boolean; message: string; provider_label?: string; model?: string }>(
      "/api/v1/providers/test",
      payload,
    ),

  createProvider: (payload: {
    label: string;
    endpoint: string;
    vendor?: string;
    models?: string[] | string;
    default_model?: string;
    default_size?: string;
    auth?: { mode?: string };
    credential_fields?: string[];
    body?: Record<string, unknown>;
    image_paths?: string[];
    notes?: string;
  }) => post<{ provider: string; listing: ProviderListing }>("/api/v1/providers", payload),

  deleteProvider: (id: string) => del<ProviderListing>(`/api/v1/providers/${id}`),
};

export function exportZipUrl(assetId: string, engine: string): string {
  return `/api/v1/assets/${assetId}/export.zip?engine=${encodeURIComponent(engine)}`;
}

export function assetImageUrl(assetId: string, size = 512): string {
  return `/api/v1/assets/${encodeURIComponent(assetId)}/image.png?view=front&size=${size}`;
}

export type CharacterView = "front" | "side" | "back";

export function assetViewUrl(
  assetId: string,
  view: CharacterView = "front",
  size = 512,
): string {
  return `/api/v1/assets/${encodeURIComponent(assetId)}/image.png?view=${view}&size=${size}`;
}

export function assetSheetUrl(assetId: string, size = 768): string {
  return `/api/v1/assets/${encodeURIComponent(assetId)}/views.png?size=${size}`;
}

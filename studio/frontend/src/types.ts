/** Shared types mirroring the backend payloads (CreativeAsset contract). */

export interface PlanTask {
  id: string;
  agent: string;
  action: string;
  capability: string;
  engine?: string;
  goal?: string;
  repair?: boolean;
}

export interface Plan {
  goal: string;
  intent: {
    goal: string;
    style: string;
    asset_type: string;
    engine: string;
    requires: Record<string, boolean>;
    needs_animation: boolean;
  };
  tasks: PlanTask[];
}

export interface TaskEvent {
  type:
    | "PLAN_CREATED"
    | "AGENT_START"
    | "AGENT_DONE"
    | "PROGRESS"
    | "ASSET_UPDATE"
    | "QUALITY_REPORT"
    | "TASK_FAILED"
    | "TASK_COMPLETE"
    | "MODEL_START"
    | "MODEL_ENHANCE"
    | "MODEL_IMAGE"
    | "MODEL_FALLBACK"
    | "STREAM_END"
    | "ERROR";
  at?: number;
  task?: string;
  agent?: string;
  action?: string;
  capability?: string;
  status?: string;
  progress?: number;
  repair?: boolean;
  round?: number;
  plan?: Plan;
  tasks?: string[];
  asset_id?: string | null;
  id?: string;
  name?: string;
  image?: string;
  engine?: string;
  scores?: Record<string, number>;
  detail?: string;
  stage?: string;
  view?: string;
  prompt?: string;
  url?: string;
}

export interface Anchor {
  x: number;
  y: number;
}

export interface CharacterSpec {
  goal: string;
  seed: number;
  gender: string;
  gender_label: string;
  class: string;
  class_label: string;
  element: string;
  element_label: string;
  role: string;
  role_label: string;
  height_cm: number;
  build: string;
  build_label: string;
  hair_color: string;
  hair_color_hex: string;
  hair_color_label: string;
  hair_style: string;
  hair_style_label: string;
  hair_length: string;
  skin: string;
  skin_hex: string;
  skin_label: string;
  eyes: string;
  eyes_hex: string;
  eyes_label: string;
  expression: string;
  expression_label: string;
  outfit_hex: string | null;
  outfit_label: string;
  accessory: string[];
  weapon: string;
  weapon_label: string;
  action: string;
  fps: number;
  frame_count: number;
  static: boolean;
  style: string;
  type: string;
  summary: string;
  palette?: Record<string, string>;
}

export interface AnimationFrame {
  id: number;
  image: string;
  action?: string;
  anchor?: {
    root: Anchor;
    feet: Anchor;
  };
}

export interface DesignViewImage {
  url: string;
  model?: string;
  file?: string;
}

export interface CreativeAsset {
  id: string;
  name?: string;
  type?: string;
  role?: string;
  source: {
    width: number;
    height: number;
    prompt?: string;
    ai_image?: {
      file?: string;
      url?: string;
      model?: string;
      path?: string;
      width?: number;
      height?: number;
    };
  };
  animation?: {
    action: string;
    fps: number;
    loop: boolean;
    frames: AnimationFrame[];
    anchor?: Array<{ root: Anchor; feet: Anchor; center?: Anchor; head?: Anchor }>;
    phase?: { action: string; phase: number[]; aligned: boolean };
    motion?: {
      root_dx: number;
      root_dy: number;
      drift_corrected: boolean;
      real_motion: boolean;
      root_track: Array<{ dx: number; dy: number }>;
      corrections: Array<{ dx: number; dy: number }>;
    };
  };
  pixel?: {
    grid: { size: number; phase_x: number; phase_y: number; confidence: number };
    palette: {
      max_colors: number;
      colors: string[];
      semantic_roles: Record<string, string | null>;
    };
    contour: { thickness: number; connectivity: number; style: string; repaired: boolean };
    pixels?: Array<Array<string | null>>;
    edited_png?: string;
    edited_at?: number;
    style?: string;
  };
  quality?: {
    pixel?: { overall: number; [key: string]: number };
    animation?: { overall: number; [key: string]: number };
    engine?: { overall: number; status?: string };
    report?: {
      scores: Record<string, number>;
      thresholds: Record<string, number>;
      retry: string[];
      status: string;
    };
  };
  engine?: {
    target: string;
    manifest: { asset_id: string; resources: Record<string, string>; valid: boolean };
    validation: {
      status: string;
      score: number;
      checks: Array<{ name: string; passed: boolean; detail?: unknown }>;
    };
    resources: Record<string, string>;
  };
  character?: CharacterSpec;
  image?: GeneratedImage;
  design_views?: {
    front?: DesignViewImage;
    side?: DesignViewImage;
    back?: DesignViewImage;
  };
  restyle?: RestyleInfo;
  cutout_png?: string;
  review?: ReviewInfo;
  prompt_enhance?: PromptEnhance;
  memory?: Record<string, unknown>;
}

export interface GeneratedImage {
  file: string;
  url: string;
  mime: string;
  provider: string;
  model: string;
  size: string;
  prompt?: string;
  elapsed_ms?: number;
}

export interface ModelSettings {
  enabled: boolean;
  provider: string;
  base_url: string;
  model: string;
  chat_model: string;
  edit_model?: string;
  video_model?: string;
  use_chat: boolean;
  use_image: boolean;
  use_video?: boolean;
  size: string;
  negative_prompt?: string;
  seed?: string;
  prompt_extend?: boolean;
  watermark?: boolean;
  video_size?: string;
  video_prompt_extend?: boolean;
  /** 动作描述 AI 增强：对话模型润色 i2v 提示词（失败自动回退原模板） */
  video_ai_enhance?: boolean;
  timeout: number;
  style?: string;
  has_key?: boolean;
  key_hint?: string;
  /** 备用 Key 池（额度耗尽/鉴权失败自动切换）；此处为脱敏回显 */
  api_key_pool?: string[];
  api_key_pool_size?: number;
}

export interface ProviderPreset {
  id: string;
  label: string;
  base_url: string;
  chat_model: string;
  model: string;
  style?: string;
  note?: string;
}

/** 风格提示词模板（确定性风格条款，幂等拼接到提示词尾部） */
export interface StyleTemplate {
  id: string;
  label: string;
  clause: string;
  negative?: string;
  note?: string;
}

export interface PromptEnhance {
  prompt: string;
  model: string;
  provider: string;
  elapsed_ms?: number;
}

export interface ModelTestResult {
  ok: boolean;
  status?: number;
  detail?: string;
}

export interface GenerationOverrides {
  style?: string;
  gender?: string;
  class?: string;
  element?: string;
  hair_color?: string;
  hair_style?: string;
  expression?: string;
  build?: string;
  weapon?: string;
  action?: string;
  height_cm?: number;
  role?: string;
  static?: boolean;
}

export interface TaskSummary {
  task_id: string;
  goal: string;
  status: string;
  created_at: number;
  asset_id: string | null;
  event_count: number;
}

export interface ExportResult {
  package: string;
  engine: string;
  asset_id: string;
  contents: string[];
  files: string[];
  size_bytes: number;
  download_url: string;
  validation: CreativeAsset["engine"] extends undefined
    ? never
    : {
        status: string;
        score: number;
        checks: Array<{ name: string; passed: boolean; detail?: unknown }>;
      };
}

export interface BenchmarkReport {
  generated_at: string;
  dataset: { size: number; categories: string[]; animated: number };
  precon: {
    baseline_pixel_score: number;
    method_pixel_score: number;
    improvement: number;
    baseline_colors: number;
    method_colors: number;
    baseline_contour: number;
    method_contour: number;
  };
  falign: {
    baseline_root_drift: number;
    method_root_drift: number;
    drift_reduction: number;
    baseline_foot_sliding: number;
    method_foot_sliding: number;
    baseline_smoothness: number;
    method_smoothness: number;
    method_overall: number;
  };
  gimport: {
    import_success_rate: number;
    average_pipeline_seconds: number;
    manual_reduction: { traditional_steps: number; gimport_steps: number; reduction: number };
    time_comparison: {
      traditional_minutes: number;
      reference_seconds: number;
      speedup: number;
      measured_seconds: number;
    };
  };
  agent: {
    task_completion_rate: number;
    planning_accuracy: number;
    recovery_success_rate: number;
    average_task_seconds: number;
    completed: number;
    total: number;
  };
  cf_score: {
    weights: Record<string, number>;
    components: { pixel: number; animation: number; engine: number; agent: number };
    overall: number;
  };
}

export interface HistoryCharacter {
  summary?: string;
  seed?: number;
  gender?: string;
  gender_label?: string;
  class?: string;
  class_label?: string;
  element?: string;
  element_label?: string;
  role?: string;
  role_label?: string;
  hair_color?: string;
  hair_color_hex?: string;
  hair_color_label?: string;
  hair_style?: string;
  hair_style_label?: string;
  hair_length?: string;
  skin?: string;
  skin_hex?: string;
  skin_label?: string;
  eyes?: string;
  eyes_hex?: string;
  eyes_label?: string;
  expression?: string;
  expression_label?: string;
  build?: string;
  build_label?: string;
  height_cm?: number;
  weapon?: string;
  weapon_label?: string;
  accessory?: string[];
  palette?: Record<string, string>;
}

export interface HistorySummary {
  id: string;
  task_id: string;
  created_at: number;
  finished_at: number;
  goal: string;
  engine: string | null;
  status: string;
  report_status: string | null;
  asset_id: string | null;
  name: string | null;
  type: string | null;
  role: string | null;
  action: string | null;
  frames: number | null;
  fps: number | null;
  scores: Record<string, number>;
  qa_rounds: number;
  elapsed_seconds: number | null;
  error: string | null;
  character: HistoryCharacter;
  palette: string[];
  image?: GeneratedImage | null;
  enhanced_prompt?: string | null;
  asset?: CreativeAsset | null;
}

export interface HistoryRecord extends HistorySummary {
  asset?: CreativeAsset | null;
}

// ── 对象存储（三渲二改造 · 第二/三项） ─────────────────────────────────────

export interface StorageProviderPreset {
  id: string;
  label: string;
  addressing: string;
  regions: string[];
  endpoint_template: string;
  credential_hint: string;
}

/** 对象存储配置的脱敏视图（后端永不回显明文凭证） */
export interface StorageConfigPublic {
  id: string;
  name: string;
  provider: string;
  access_key: string; // 脱敏，如 R8oG****D_Qu
  secret_key: string; // 脱敏
  has_secret: boolean;
  region: string;
  bucket: string;
  endpoint: string;
  is_default: boolean;
  created_at: number;
  updated_at: number;
}

export interface StorageConfigList {
  configs: StorageConfigPublic[];
  presets: Record<string, StorageProviderPreset>;
  default_id: string | null;
}

export interface StorageTestResult {
  ok: boolean;
  latency_ms?: number;
  detail?: string;
}

export interface MultipartSession {
  session_id: string;
  config_id: string;
  key: string;
  total_size: number;
  part_size: number;
  total_parts: number;
  uploaded_parts: number[];
  missing_parts: number[];
  bytes_done: number;
  progress: number;
  status: string;
  created_at: number;
  updated_at: number;
}

/* ── P1-A 资产版本控制 ─────────────────────────────────────────── */

export interface VersionView {
  version_no: number;
  record_id: string;
  asset_id: string | null;
  task_id: string | null;
  name: string | null;
  created_at: number;
  engine: string | null;
  seed: number | null;
  action: string | null;
  status: string | null;
  image_url: string | null;
  scores: { pixel?: number; animation?: number; engine?: number };
  palette: string[];
  goal: string | null;
  review_tag?: string | null;
}

export interface VersionGroup {
  name: string;
  count: number;
  latest_at: number;
}

export interface VersionTree {
  name: string;
  count: number;
  latest: VersionView | null;
  versions: VersionView[];
}

export interface VersionDiff {
  a: VersionView;
  b: VersionView;
  fields: Array<{ field: string; a: unknown; b: unknown }>;
}

export interface RollbackEntry {
  ok?: boolean;
  record_id: string;
  asset_id?: string;
  name?: string | null;
  version_no?: number | null;
  error?: string;
}

export interface RollbackRecord {
  id: string;
  at: number;
  count: number;
  entries: RollbackEntry[];
}

/* ── P1-B 批量生成与导出 ───────────────────────────────────────── */

export interface BatchTask {
  task_id: string;
  index: number;
  status: string;
  asset_id?: string | null;
  name?: string | null;
  image_url?: string | null;
  overrides?: { seed?: number; action?: string };
  scores?: Record<string, number>;
  error?: string;
}

export interface BatchStatus {
  id: string;
  goal: string;
  count: number;
  mode: string;
  status: string;
  created_at: number;
  tasks: BatchTask[];
}

export interface BatchExportResult {
  package: string;
  engine: string;
  count: number;
  size_bytes: number;
  download_url: string;
  assets: Array<{
    asset_id: string;
    name?: string | null;
    ok: boolean;
    error?: string;
    validation_score?: number;
  }>;
}

/** 角色资产包一键导出（原画 + 三视图 + 全动作 GIF + 引擎包） */
export interface CharacterPackageResult {
  package: string;
  asset_id: string;
  engine: string;
  artwork_count: number;
  engine_files: number;
  engine_error?: string | null;
  missing: string[];
  size_bytes: number;
  download_url: string;
  files: string[];
  animations: Array<{
    action: string;
    engine: string;
    frames: number;
    fps?: number;
    gif: string;
    animation_id?: string;
    generated_at?: number;
  }>;
}

export interface ReviewInfo {
  approved: boolean;
  note?: string | null;
  at?: number;
}

export interface RestyleInfo {
  style: string;
  url: string;
  file?: string;
  model?: string;
}

export interface ActionBatchTask {
  action: string;
  status: "pending" | "generating" | "done" | "failed" | "skipped";
  note?: string;
  error?: string;
  /** 失败分类：moderation/quota/auth/network/fatal（后端 classify_error） */
  error_kind?: string;
  animation_id?: string;
}

export interface ActionBatchSnapshot {
  id: string;
  asset_id: string;
  status: "running" | "done";
  total: number;
  tasks: ActionBatchTask[];
}

export interface InterpretedAction {
  label: string;
  base_action: string;
  view: string;
  pose_config: Record<string, number>;
  source_text?: string;
}

export interface PlaytestStrip {
  url: string;
  frames: number;
  /** 播放帧率（fps）；旧响应缺失时前端回落 10 */
  fps?: number;
  width: number;
  height: number;
  engine: string;
}

export interface PlaytestCharacter {
  proportion: "chibi" | "normal" | string;
  confidence: number | null;
  head_ratio: number | null;
  source_hash: string | null;
}

export interface PlaytestPreviews {
  previews: Record<string, string>;
  actions: string[];
  strips?: Record<string, PlaytestStrip>;
  fps?: number;
  source?: "rigged" | "procedural" | string;
  character?: PlaytestCharacter | null;
}

export interface PixelEditResult {
  status: string;
  asset_id: string | null;
  size: number;
  edited_png: string | null;
  image_url: string;
}

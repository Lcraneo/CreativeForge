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
    | "MODEL_VIEWS"
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
  /** 后端返回的视角标记；front 恒为角色原画 */
  view?: "front" | "side" | "back";
  /** side / back 来源：qwen 双栏设定图裁切 */
  source?: string;
  /** 裁切来源的双栏原图文件名 */
  sheet_file?: string;
  /** 在双栏图中的裁切框 [x0, y0, x1, y1] */
  bbox?: number[];
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
  /** 用户上传的人物正面图（强身份参考），与角色资产一同持久化 */
  reference_image?: ReferenceImage;
  /** 参考图流程中三视图生成失败的原因（原画与正面图仍保留，可重试） */
  design_views_error?: { kind: string; detail: string } | null;
  restyle?: RestyleInfo;
  cutout_png?: string;
  review?: ReviewInfo;
  prompt_enhance?: PromptEnhance;
  memory?: Record<string, unknown>;
  /** A 失败透明化：AI 生图失败（内容审核/额度/网络等）后的降级原因，
   *  此时 pixel 资产为离线示意产物；前端据此展示失败徽章 */
  model_fallback?: { kind: string; detail: string } | null;
  pve_enemy?: boolean;
  pve_role?: "minion" | "boss";
}

/** 用户上传的人物正面图：文件与代理 URL 均指向本地持久化产物 */
export interface ReferenceImage {
  file: string;
  url: string;
  mime: string;
  width: number;
  height: number;
  bytes: number;
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
  /** 命中提示词缓存（本次生成零额度消耗） */
  cached?: boolean;
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
  /** 生图失败策略：strict=任务失败并返回原因与建议（默认，不静默降级）；
   *  degrade=自动降级为离线示意资产（带 model_fallback 标记） */
  image_fallback_policy?: "strict" | "degrade";
  timeout: number;
  style?: string;
  has_key?: boolean;
  key_hint?: string;
  /** 备用 Key 池（额度耗尽/鉴权失败自动切换）；此处为脱敏回显 */
  api_key_pool?: string[];
  api_key_pool_size?: number;
  /** Key 健康状态（本次运行内，重启清零）：ok/quota/auth/error/unknown */
  key_health?: { primary?: string; pool?: string[] };
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

/** 额度仪表：本地估算用量（非账单） */
export interface ModelUsage {
  totals: { today: number; week: number; month: number };
  currency: string;
  by_kind: Array<{ kind: string; calls: number; cost: number }>;
  by_model: Array<{ kind: string; model: string; calls: number; cost: number }>;
  days: Array<{ date: string; calls: number; cost: number }>;
  recent: Array<{ at: number; kind: string; model: string; meta?: Record<string, unknown> }>;
  prices: Record<string, number>;
  note: string;
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
  /** A 失败透明化：AI 生图失败（如内容审核拦截）时记录分类+人话原因，
   * 产物为离线示意；前端据此展示「AI 生图失败」徽章与重试入口 */
  model_image_error?: { kind: string; detail: string } | null;
  asset?: CreativeAsset | null;
}

export interface HistoryRecord extends HistorySummary {
  asset?: CreativeAsset | null;
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
  /** 本动作实际使用的生成视角：idle/attack=front，walk/run/jump=side */
  view?: "front" | "side" | string;
  /** interrupted = 后端重启导致任务中断（终态，见后端 task_store） */
  status: "pending" | "generating" | "done" | "failed" | "skipped" | "interrupted";
  stage?: "prompt" | "video" | "sampling" | "composing" | "done" | "interrupted";
  started_at?: number;
  progress?: number;
  note?: string;
  error?: string;
  /** 失败分类：moderation/quota/auth/network/fatal/interrupted */
  error_kind?: string;
  animation_id?: string;
}

export interface ActionBatchSnapshot {
  id: string;
  asset_id: string;
  /** mixed = 同一批包含正面与侧面动作 */
  view?: string;
  /** failed = 全部动作生成失败（部分失败仍为 done，failed_count 记失败数）；
   * interrupted = 后端重启中断（终态，任务已落盘可追溯） */
  status: "running" | "done" | "failed" | "interrupted";
  total: number;
  failed_count?: number;
  tasks: ActionBatchTask[];
  created_at?: number;
}

export interface PlaytestStrip {
  url: string;
  frames: number;
  /** 播放帧率（fps）；旧响应缺失时前端回落 10 */
  fps?: number;
  width: number;
  height: number;
  engine: string;
  /** 条带对应的动作视角（诊断用） */
  view?: "front" | "side" | string;
  /** 侧视源图朝向；旧记录按历史左向兼容 */
  facing?: "left" | "right";
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
  source?: "rigged" | "sprite" | "procedural" | string;
  character?: PlaytestCharacter | null;
  /** 自定义动作陈列（命名空间隔离）：条带键 custom:<名称>，与内置槽位互不占用 */
  custom_actions?: PlaytestCustomAction[];
}

export interface ScenePalette {
  skyTop: string;
  skyBottom: string;
  ground: string;
  floating: string;
  accent: string;
}

export interface ScenePlatform {
  x: number;
  y: number;
  width: number;
  height: number;
  kind: "ground" | "floating";
}

export interface SceneCoin {
  id: string;
  x: number;
  y: number;
}

export interface SceneLevel {
  seed: string;
  width: number;
  groundY: number;
  spawnX: number;
  goalX: number;
  platforms: ScenePlatform[];
  coins: SceneCoin[];
}

export interface PveEnemy {
  id: string;
  profile_id?: string | null;
  asset_id: string;
  name: string;
  kind: "slime" | "boss";
  x: number;
  y: number;
  max_hp: number;
  speed: number;
  damage: number;
  attack_interval: number;
  display_height: number;
  behavior?: "chaser" | "shooter" | "charger" | "guardian" | string;
  element?: string;
  projectile_color?: string;
  tags?: string[];
}

export interface PveEncounter {
  id: string;
  title: string;
  kind: "combat" | "boss";
  trigger_x: number;
  lock_x: number;
  enemy_ids: string[];
}

export interface PveLevel {
  seed: string;
  width: number;
  groundY: number;
  spawnX: number;
  goalX: number;
  platforms: ScenePlatform[];
  enemies: PveEnemy[];
  encounters?: PveEncounter[];
}

export interface PveEnemyProfile {
  id: string;
  name: string;
  role: "minion" | "boss";
  prompt: string;
  summary: string;
  tags: string[];
  behavior: "chaser" | "shooter" | "charger" | "guardian";
  element: string;
  projectile_color: string;
  asset_id: string | null;
  status:
    | "analyzing"
    | "generating_model"
    | "generating_actions"
    | "ready"
    | "failed";
  builtin: boolean;
  difficulty?: "easy" | "normal" | "hard";
  stats: {
    max_hp: number;
    speed: number;
    damage: number;
    attack_interval: number;
    display_height: number;
  };
  task_id?: string;
  action_batch_id?: string;
  action_warning?: string | null;
  error?: string | null;
  created_at: number;
  updated_at: number;
}

export interface SceneValidation {
  ok: boolean;
  issues: string[];
  max_gap: number;
  max_rise: number;
}

export interface ParkourGameplay {
  type: "parkour";
  difficulty: "easy" | "normal" | "hard";
  length?: "short" | "medium" | "long";
  features?: string[];
  level: SceneLevel | null;
  validation?: SceneValidation;
}

export interface PveGameplay {
  type: "pve";
  difficulty: "easy" | "normal" | "hard";
  length?: "short" | "medium" | "long";
  features?: string[];
  level: PveLevel | null;
  validation?: SceneValidation;
}

export type SceneGameplay = ParkourGameplay | PveGameplay;

export interface GameScene {
  schema_version: number;
  id: string;
  title: string;
  prompt: string;
  status: "generating" | "ready" | "failed";
  gameplay: SceneGameplay;
  theme: {
    summary: string;
    palette: Partial<ScenePalette>;
    background_url: string | null;
    background_urls?: string[];
  };
  generation: {
    stage: string;
    warnings: string[];
    attempts: number;
    duration_ms: number;
    background_total?: number;
    background_done?: number;
    chat_model?: string;
    image_model?: string;
  };
  intent?: {
    title: string;
    summary: string;
    environment: string;
    difficulty: string;
    length: string;
    features: string[];
    palette: ScenePalette;
  };
  created_at: number;
  updated_at: number;
  error: string | null;
}

export type ParkourScene = Omit<GameScene, "gameplay"> & {
  gameplay: ParkourGameplay;
};

export interface SceneSummary {
  id: string;
  title: string;
  prompt: string;
  status: GameScene["status"];
  stage: string;
  gameplay_type?: "parkour" | "pve";
  difficulty: GameScene["gameplay"]["difficulty"];
  background_url: string | null;
  background_count?: number;
  coin_count: number;
  enemy_count?: number;
  created_at: number;
  error: string | null;
}

/** 试玩舞台自定义动作条目 */
export interface PlaytestCustomAction {
  name: string;
  base_action?: string;
  view?: string;
  description?: string;
  /** ai-video = AI 动画帧；rigged = 骨骼按保存参数渲染；procedural = 姿态引擎 */
  engine: string;
  strip: PlaytestStrip;
}

/* ── 云生成能力（A 部分）─────────────────────────────────────────────── */

export interface CloudProvider {
  id: string;
  label: string;
  capabilities: string[];
  slot: string;
  protocol: string;
  env_keys: string[];
  credential_ref: string | null;
  notes: string;
  free_tier: string;
  price_note: string;
  priority: number;
  fallback: string;
  enabled: boolean;
  base_url: string;
  model: string;
  model_options: string[];
  extra_fields: string[];
  region: string;
  workspace_id: string;
  missing_fields: string[];
  updated_at: number;
  has_key: boolean;
  key_hint: string;
  key_source: "env" | "store" | "credential_ref" | "";
  configured: boolean;
}

export interface CloudProvidersResponse {
  enabled: boolean;
  providers: CloudProvider[];
  readiness: Record<string, boolean>;
  config: {
    enabled: boolean;
    sidecar_enabled: boolean;
    cache_dir: string;
    cache_ttl_days: number;
    cache_max_mb: number;
    timeout: number;
    max_retries: number;
  };
}

export interface CloudTestResult {
  ok: boolean;
  status: number | null;
  detail: string;
  latency_ms: number;
  provider: string;
  key_source: string;
  has_key: boolean;
}

export interface CloudGenerationResult {
  status: "succeeded" | "failed";
  provider?: string;
  local_path?: string;
  bytes?: number;
  sha256?: string;
  kind?: string;
  format?: string;
  model?: string;
  error_class?: string;
  error_message?: string;
  attempts?: Array<{ provider: string; status: string; error_class?: string | null }>;
}

export interface CloudTaskSnapshot {
  id: string;
  status: "running" | "succeeded" | "failed";
  stage: string;
  progress: number;
  provider?: string;
  result?: CloudGenerationResult;
  error?: string;
  error_class?: string;
  created_at: number;
  updated_at: number;
}

export interface CloudUsageSnapshot {
  enabled: boolean;
  providers: Record<
    string,
    { calls: number; cache_hits: number; bytes: number; errors: number; slots: Record<string, unknown> }
  >;
  totals: { calls: number; cache_hits: number; bytes: number; errors: number };
  cache: { dir: string; files: number; bytes: number; max_bytes: number; ttl_days: number };
}

/* ── 试玩舞台 3D POC-0 ───────────────────────────────────────────── */

/** 3D 清单里的单个标准动作：name 为 idle/walk/run/jump/attack 之一。 */
export interface Playtest3DClip {
  name: string;
  /** GLB 内实际 clip 名（后端无法解析 GLB 时省略，前端按名字就近映射）。 */
  source_clip?: string | null;
  loop: boolean;
}

/** 后端 3D 清单的「不可用」原因（前端据此展示错误文案与 2D 回退）。 */
export type Playtest3DManifestError =
  | "mesh_missing"
  | "mesh_failed"
  | "unsupported_format"
  | "path_invalid"
  | "asset_not_found";

export interface Playtest3DManifest {
  version: string;
  asset_id: string;
  available: boolean;
  error?: Playtest3DManifestError | null;
  mesh_url?: string | null;
  bytes?: number | null;
  sha256?: string | null;
  rig?: { provider?: string | null; rigged: boolean } | null;
  clips: Playtest3DClip[];
  fallback_url: string;
}

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
  engine?: string;
  scores?: Record<string, number>;
  detail?: string;
}

export interface Anchor {
  x: number;
  y: number;
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

export interface CreativeAsset {
  id: string;
  name?: string;
  type?: string;
  role?: string;
  source: { width: number; height: number; prompt?: string };
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
    palette: { max_colors: number; colors: string[]; semantic_roles: Record<string, string | null> };
    contour: { thickness: number; connectivity: number; style: string; repaired: boolean };
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
  validation: CreativeAsset["engine"] extends undefined ? never : {
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

export interface Intent {
  type?: string;
  engine?: string;
  style?: string;
  requirements?: string[];
  actions?: string[];
}

export interface DagNode {
  id: string;
  agent: string;
  input?: string[];
  output?: string[];
  status?: string;
}

export interface Dag {
  nodes: DagNode[];
  edges: [string, string][];
}

export interface Plan {
  mode?: string;
  tasks?: string[];
  engine?: string;
  goal?: string;
  intent?: Intent;
  dag?: Dag;
  decisions?: string[];
  capabilities?: string[];
}

export interface Step {
  node: string;
  agent: string;
  status: string;
  ms: number;
  tier?: string;
  summary?: unknown;
}

export interface CreateResponse {
  task_id: string;
  status: string;
  plan: Plan;
  result: Record<string, unknown>;
  asset_id: string | null;
  review?: { point?: string; type?: string } | null;
}

export interface TaskDetail {
  id: string;
  goal: string;
  status: string;
  plan: Plan | null;
  result: Record<string, unknown> | null;
  created_at: string | null;
  current_node: string | null;
  steps: Step[] | null;
  asset_id: string | null;
  error: string | null;
  source: string;
}

export interface AssetSummary {
  id: string;
  name: string;
  asset_type: string;
  status: string;
  created_at: string | null;
}

export interface Layer {
  name: string;
  type: string;
  image?: string;
  bbox?: number[];
  confidence?: number;
}

export interface Clip {
  name: string;
  fps?: number;
  duration?: number;
  frames?: number;
  events?: { type?: string; frame?: number }[];
}

export interface Skill {
  skill?: string;
  animation?: string;
  damage?: number;
  element?: string;
}

export interface Box {
  name?: string;
  frames?: unknown[];
  [key: string]: unknown;
}

export interface DnaProfile {
  appearance?: Record<string, unknown>;
  style?: { name?: string };
  structure?: Record<string, unknown>;
  equipment?: Record<string, unknown>;
  motion?: Record<string, unknown>;
  combat?: Record<string, unknown>;
}

export interface DnaBrief {
  character_id: string;
  identity?: { name?: string; species?: string; role?: string; style?: string; dna_profile?: DnaProfile } ;
  version?: string;
  versions?: string[];
  identity_similarity?: number;
}

export interface DnaDetail {
  character_id: string;
  identity: Record<string, unknown>;
  embedding: { model?: string; dim?: number };
  versions: string[];
}

export interface ExportQuality {
  manifest_score?: number;
  runtime_score?: number;
  checks?: Record<string, boolean>;
}

export interface ExportResult {
  asset_id: string;
  engine: string;
  root: string;
  files: string[];
  quality: ExportQuality;
}

export interface SkillBlueprint {
  name?: string;
  type?: string;
  trigger?: { cooldown?: number };
  animation?: string;
  damage?: number;
  effect?: string;
  engine?: { unity?: { script?: string }; cocos?: Record<string, unknown> };
}

export interface AssetMetadata {
  identity?: {
    name?: string;
    prompt?: string;
    species?: string;
    role?: string;
  };
  content?: {
    image?: string;
    layers?: Layer[];
    graph?: { id?: string; children?: unknown[] };
  };
  pixel?: { palette?: { colors?: string[] } };
  animation?: {
    action?: string;
    clips?: Clip[];
    motion?: { max_root_residual?: number };
    atlas_detail?: { size?: number[]; sprites?: { name?: string; w?: number; h?: number }[] };
  };
  combat?: { skills?: Skill[]; hitboxes?: Box[]; hurtboxes?: Box[] };
  logic?: { skills?: SkillBlueprint[] };
  dna?: DnaBrief;
  style?: { name?: string };
  quality?: Record<string, unknown>;
  engine?: {
    target?: string;
    resources?: {
      engine?: string;
      root?: string;
      files?: Record<string, unknown>;
      quality?: ExportQuality;
    };
  };
}

export interface AssetDetail {
  id: string;
  name: string;
  asset_type: string;
  status: string;
  created_at: string | null;
  project_id: string;
  metadata_json: AssetMetadata;
}

export interface RegistryArtifact {
  id: string;
  name: string;
  kind: string;
  version: number;
  status: string;
  metrics?: { before?: Record<string, number>; after?: Record<string, number> };
  config?: Record<string, unknown>;
}

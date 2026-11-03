import { create } from "zustand";
import type { Plan, TaskEvent } from "../types";

export interface WorkflowNode {
  id: string;
  label: string;
  sublabel?: string;
  kind: "supervisor" | "agent" | "engine" | "qa" | "memory";
}

export interface WorkflowEdge {
  from: string;
  to: string;
}

interface WorkflowState {
  plan: Plan | null;
  nodes: WorkflowNode[];
  edges: WorkflowEdge[];
  currentNode: string | null;

  setPlan: (plan: Plan) => void;
  applyEvent: (event: TaskEvent) => void;
  reset: () => void;
}

/** Capability -> engine displayed under the specialist agent node. */
const ENGINE_OF_CAPABILITY: Record<string, string> = {
  generation: "AI Image",
  PReCon: "PReCon",
  FAlign: "FAlign",
  GImport: "GImport",
  QA: "Quality Gate",
  Memory: "Checkpoint",
};

const AGENT_OF_CAPABILITY: Record<string, string> = {
  generation: "ArtAgent",
  PReCon: "ArtAgent",
  FAlign: "AnimationAgent",
  GImport: "EngineAgent",
  QA: "QAAgent",
  Memory: "MemoryAgent",
};

export function buildGraph(plan: Plan): { nodes: WorkflowNode[]; edges: WorkflowEdge[] } {
  const nodes: WorkflowNode[] = [
    { id: "supervisor", label: "Supervisor", sublabel: "任务规划", kind: "supervisor" },
  ];
  const edges: WorkflowEdge[] = [];

  const seen = new Set<string>();
  const orderedIds: string[] = [];
  for (const task of plan.tasks) {
    const agent = AGENT_OF_CAPABILITY[task.capability] ?? task.agent;
    const nodeId = `${agent}:${task.capability}`;
    if (!seen.has(nodeId)) {
      seen.add(nodeId);
      orderedIds.push(nodeId);
      nodes.push({
        id: nodeId,
        label: agent,
        sublabel: ENGINE_OF_CAPABILITY[task.capability] ?? task.capability,
        kind: task.capability === "generation" ? "agent" : "engine",
      });
    }
  }

  nodes.push({ id: "qa", label: "QA Agent", sublabel: "质量验证", kind: "qa" });
  nodes.push({ id: "memory", label: "Memory Agent", sublabel: "检查点", kind: "memory" });

  let previous = "supervisor";
  for (const nodeId of orderedIds) {
    edges.push({ from: previous, to: nodeId });
    previous = nodeId;
  }
  edges.push({ from: previous, to: "qa" });
  edges.push({ from: "qa", to: "memory" });

  return { nodes, edges };
}

/** Map a live event task id to its graph node id. */
export function nodeIdForTask(plan: Plan | null, taskId?: string): string | null {
  if (!plan || !taskId) return null;
  if (taskId === "QA1") return "qa";
  if (taskId === "M01") return "memory";
  const task = plan.tasks.find((item) => item.id === taskId);
  if (!task) return null;
  return `${AGENT_OF_CAPABILITY[task.capability] ?? task.agent}:${task.capability}`;
}

export const useWorkflowStore = create<WorkflowState>((set) => ({
  plan: null,
  nodes: [],
  edges: [],
  currentNode: null,

  setPlan: (plan) => {
    const { nodes, edges } = buildGraph(plan);
    set({ plan, nodes, edges, currentNode: null });
  },

  applyEvent: (event) =>
    set((state) => {
      if (event.type === "PLAN_CREATED" && event.plan) {
        const graph = buildGraph(event.plan);
        return { plan: event.plan, ...graph, currentNode: null };
      }
      if (event.type === "AGENT_START") {
        return { currentNode: nodeIdForTask(state.plan, event.task) ?? state.currentNode };
      }
      return {};
    }),

  reset: () => set({ plan: null, nodes: [], edges: [], currentNode: null }),
}));

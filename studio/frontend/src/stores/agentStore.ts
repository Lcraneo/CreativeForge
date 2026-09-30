import { create } from "zustand";
import type { TaskEvent } from "../types";

export type NodeStatus = "idle" | "running" | "success" | "failed" | "recovered";

interface AgentState {
  taskId: string | null;
  goal: string;
  status: "idle" | "running" | "pass" | "failed";
  events: TaskEvent[];
  agentStatuses: Record<string, NodeStatus>;
  progress: number;
  lastError: string | null;

  start: (taskId: string, goal: string) => void;
  applyEvent: (event: TaskEvent) => void;
  finish: (status: string) => void;
  reset: () => void;
}

export const useAgentStore = create<AgentState>((set) => ({
  taskId: null,
  goal: "",
  status: "idle",
  events: [],
  agentStatuses: {},
  progress: 0,
  lastError: null,

  start: (taskId, goal) =>
    set({
      taskId,
      goal,
      status: "running",
      events: [],
      agentStatuses: {},
      progress: 0,
      lastError: null,
    }),

  applyEvent: (event) =>
    set((state) => {
      const agentStatuses = { ...state.agentStatuses };
      switch (event.type) {
        case "AGENT_START":
          agentStatuses[event.task ?? ""] = "running";
          break;
        case "AGENT_DONE":
          agentStatuses[event.task ?? ""] = event.status === "recovered" ? "recovered" : "success";
          break;
        case "TASK_FAILED":
          agentStatuses[event.task ?? ""] = "failed";
          break;
        default:
          break;
      }
      return {
        events: [...state.events, event],
        agentStatuses,
        progress: event.progress ?? state.progress,
      };
    }),

  finish: (status) =>
    set({
      status:
        status === "pass" || status === "success"
          ? "pass"
          : status === "failed"
            ? "failed"
            : "pass",
    }),

  reset: () =>
    set({
      taskId: null,
      goal: "",
      status: "idle",
      events: [],
      agentStatuses: {},
      progress: 0,
      lastError: null,
    }),
}));

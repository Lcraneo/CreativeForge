import { useEffect, useMemo } from "react";
import { Link } from "react-router-dom";
import {
  Background,
  Controls,
  ReactFlow,
  type Edge,
  type Node,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { motion } from "framer-motion";
import { useAgentStore, type NodeStatus } from "../stores/agentStore";
import { nodeIdForTask, useWorkflowStore } from "../stores/workflowStore";
import { useAssetStore } from "../stores/assetStore";
import { streamTask } from "../websocket/taskStream";
import { api } from "../api/client";
import { Badge, Card } from "../components/ui";
import type { Plan } from "../types";

const KIND_LABEL: Record<string, string> = {
  supervisor: "规划",
  agent: "生成",
  engine: "自研引擎",
  qa: "质量",
  memory: "记忆",
};

function nodeStyle(status: NodeStatus, active: boolean): React.CSSProperties {
  const base: React.CSSProperties = {
    borderRadius: 10,
    border: "1px solid #3f3f46",
    background: "#18181b",
    color: "#e4e4e7",
    padding: "10px 16px",
    fontSize: 12,
    width: 168,
  };
  if (active) {
    return { ...base, borderColor: "#38bdf8", boxShadow: "0 0 18px rgba(56,189,248,.35)" };
  }
  if (status === "success" || status === "recovered")
    return { ...base, borderColor: "#34d399" };
  if (status === "failed") return { ...base, borderColor: "#f87171" };
  if (status === "running")
    return { ...base, borderColor: "#38bdf8", boxShadow: "0 0 14px rgba(56,189,248,.25)" };
  return base;
}

/** Simple layered layout: supervisor top, chain middle, QA/memory bottom. */
function layout(nodes: { id: string }[]) {
  const positions = new Map<string, { x: number; y: number }>();
  const middle = nodes.slice(1, -2);
  const width = middle.length * 220;
  middle.forEach((node, index) => {
    positions.set(node.id, {
      x: index * 220 - width / 2 + 110,
      y: 40,
    });
  });
  positions.set("supervisor", { x: 0, y: -110 });
  const tail = nodes.slice(-2);
  tail.forEach((node, index) => {
    positions.set(node.id, { x: -110 + index * 220, y: 190 });
  });
  return positions;
}

export default function AgentDashboard() {
  const { taskId, goal, status, events, agentStatuses, progress } = useAgentStore();
  const { nodes, edges, plan, currentNode } = useWorkflowStore();
  const setAsset = useAssetStore((s) => s.set);
  const applyAgentEvent = useAgentStore((s) => s.applyEvent);
  const finishAgent = useAgentStore((s) => s.finish);
  const applyWorkflowEvent = useWorkflowStore((s) => s.applyEvent);

  useEffect(() => {
    if (!taskId) return;
    const stop = streamTask(taskId, {
      onEvent: (event) => {
        applyAgentEvent(event);
        applyWorkflowEvent(event);
        if (event.type === "ASSET_UPDATE" && event.id) {
          api.getAsset(event.id).then(setAsset).catch(() => undefined);
        }
      },
      onEnd: (final) => finishAgent(final),
    });
    return stop;
  }, [taskId, applyAgentEvent, applyWorkflowEvent, finishAgent, setAsset]);

  const graphNodes: Node[] = useMemo(() => {
    const positions = layout(nodes);
    return nodes.map((node) => {
      const taskForNode = reverseTask(plan, node.id);
      const nodeStatus: NodeStatus =
        (taskForNode && agentStatuses[taskForNode]) || "idle";
      return {
        id: node.id,
        position: positions.get(node.id) ?? { x: 0, y: 0 },
        data: {
          label: (
            <div>
              <div className="font-semibold">{node.label}</div>
              <div className="text-[10px] text-zinc-500">
                {node.sublabel} · {KIND_LABEL[node.kind]}
              </div>
            </div>
          ),
        },
        style: nodeStyle(nodeStatus, currentNode === node.id),
      };
    });
  }, [nodes, plan, agentStatuses, currentNode]);

  const graphEdges: Edge[] = edges.map((edge) => ({
    id: `${edge.from}->${edge.to}`,
    source: edge.from,
    target: edge.to,
    animated: true,
    style: { stroke: "#52525b" },
  }));

  if (!taskId) {
    return (
      <div className="mx-auto max-w-3xl px-8 py-16 text-center">
        <h1 className="pixel-title text-lg font-semibold text-zinc-200">
          Agent Command Center
        </h1>
        <p className="mt-3 text-sm text-zinc-400">
          还没有正在运行的任务。回到工作台输入一个游戏创意，再回来看智能体团队工作。
        </p>
        <Link
          to="/"
          className="mt-6 inline-block rounded-lg bg-cyan-400 px-5 py-2 text-sm font-semibold text-zinc-950 hover:bg-cyan-300"
        >
          去创建任务
        </Link>
      </div>
    );
  }

  return (
    <div className="flex h-full flex-col gap-4 px-6 py-5">
      <header className="flex items-center justify-between">
        <div>
          <h1 className="pixel-title text-sm font-semibold text-zinc-200">
            Agent Command Center
          </h1>
          <p className="mt-1 max-w-3xl truncate text-xs text-zinc-500">{goal}</p>
        </div>
        <div className="flex items-center gap-3">
          <span className="font-mono text-xs text-zinc-500">{taskId}</span>
          <Badge
            tone={
              status === "pass" ? "green" : status === "failed" ? "red" : "cyan"
            }
          >
            {status === "running" ? `运行中 ${progress}%` : status}
          </Badge>
        </div>
      </header>

      <div className="grid min-h-0 flex-1 grid-cols-[1fr_340px] gap-4">
        <Card title="任务图 / Task Graph" className="min-h-0">
          <div className="h-full min-h-[360px]">
            <ReactFlow
              nodes={graphNodes}
              edges={graphEdges}
              fitView
              proOptions={{ hideAttribution: true }}
              nodesDraggable={false}
              nodesConnectable={false}
            >
              <Background color="#27272a" gap={22} />
              <Controls showInteractive={false} />
            </ReactFlow>
          </div>
        </Card>

        <div className="flex min-h-0 flex-col gap-4">
          <Card title="事件流 / Event Stream">
            <motion.div layout className="max-h-56 space-y-1.5 overflow-y-auto font-mono text-[11px]">
              {events.map((event, index) => (
                <motion.div
                  key={index}
                  initial={{ opacity: 0, x: -8 }}
                  animate={{ opacity: 1, x: 0 }}
                  className="flex gap-2"
                >
                  <span className="text-zinc-600">
                    {new Date((event.at ?? 0) * 1000).toLocaleTimeString([], {
                      minute: "2-digit",
                      second: "2-digit",
                    })}
                  </span>
                  <span
                    className={
                      event.type === "AGENT_START"
                        ? "text-sky-300"
                        : event.type === "AGENT_DONE"
                          ? "text-emerald-300"
                          : event.type === "TASK_FAILED"
                            ? "text-red-300"
                            : "text-zinc-300"
                    }
                  >
                    {event.type}
                  </span>
                  {event.agent && <span className="text-zinc-500">{event.agent}</span>}
                </motion.div>
              ))}
              {events.length === 0 && (
                <p className="text-zinc-600">等待事件…</p>
              )}
            </motion.div>
          </Card>

          <Card title="Agent Timeline / 执行轨迹">
            <div className="relative space-y-3 pl-4">
              <div className="absolute left-[7px] top-2 bottom-2 w-px bg-zinc-700" />
              {(events.length ? events.slice(-8) : []).map((event, index) => (
                <motion.div
                  key={`timeline-${index}`}
                  initial={{ opacity: 0, y: 6 }}
                  animate={{ opacity: 1, y: 0 }}
                  className="relative flex items-start gap-3 text-xs"
                >
                  <span className="relative z-10 mt-1 h-2 w-2 rounded-full bg-cyan-400 ring-4 ring-cyan-400/10" />
                  <div>
                    <div className="font-medium text-zinc-200">{event.type}</div>
                    <div className="text-zinc-500">
                      {event.agent ?? "Agent System"} · {new Date((event.at ?? 0) * 1000).toLocaleTimeString([], { minute: "2-digit", second: "2-digit" })}
                    </div>
                  </div>
                </motion.div>
              ))}
              {events.length === 0 && <p className="text-zinc-600">等待 Agent 状态变化…</p>}
            </div>
          </Card>

          <Card title="质量报告 / QA">
            {status === "pass" ? (
              <div className="space-y-2 text-xs">
                <p className="text-emerald-300">全部检查通过 ✓</p>
                <Link to="/asset" className="inline-block text-cyan-300 hover:underline">
                  查看资产 Inspector →
                </Link>
              </div>
            ) : (
              <p className="text-xs text-zinc-500">
                {status === "failed" ? "任务失败，请重试" : "智能体团队工作中…"}
              </p>
            )}
          </Card>
        </div>
      </div>
    </div>
  );
}

/** Which plan task id renders into this graph node id. */
function reverseTask(plan: Plan | null, nodeId: string): string | null {
  if (!plan) return null;
  if (nodeId === "qa") return "QA1";
  if (nodeId === "memory") return "M01";
  for (const task of plan.tasks) {
    if (nodeIdForTask(plan, task.id) === nodeId) return task.id;
  }
  return null;
}

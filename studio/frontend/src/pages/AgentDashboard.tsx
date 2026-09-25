import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
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
import {
  Badge,
  Button,
  Card,
  EmptyState,
  PageHeader,
  ScoreBar,
  StatusDot,
  Tabs,
  cx,
} from "../components/ui";
import { Icon } from "../components/icons";
import type { Plan, TaskEvent } from "../types";

const KIND_LABEL: Record<string, string> = {
  supervisor: "规划",
  agent: "生成",
  engine: "自研引擎",
  qa: "质量",
  memory: "记忆",
};

const DOMAIN_COLOR: Record<string, string> = {
  supervisor: "#60a5fa",
  precon: "#22d3ee",
  falign: "#a78bfa",
  gimport: "#34d399",
  qa: "#fbbf24",
  memory: "#94a3b8",
  default: "#4cc2ff",
};

function domainOf(id: string) {
  if (id === "supervisor") return "supervisor";
  if (id.toLowerCase().includes("precon")) return "precon";
  if (id.toLowerCase().includes("falign")) return "falign";
  if (id.toLowerCase().includes("gimport")) return "gimport";
  if (id === "qa") return "qa";
  if (id === "memory") return "memory";
  return "default";
}

function nodeStyle(status: NodeStatus, active: boolean, domain: string): React.CSSProperties {
  const color = DOMAIN_COLOR[domain] ?? DOMAIN_COLOR.default;
  const base: React.CSSProperties = {
    borderRadius: 12,
    border: "1px solid #2a3444",
    background: "linear-gradient(180deg,#151a24,#10141c)",
    color: "#e9eef6",
    padding: "10px 12px",
    fontSize: 12,
    width: 186,
    boxShadow: "0 6px 18px -10px rgba(0,0,0,.9)",
  };
  if (status === "success" || status === "recovered")
    return { ...base, borderColor: "rgba(52,211,153,.45)" };
  if (status === "failed") return { ...base, borderColor: "rgba(251,113,133,.6)" };
  if (active || status === "running")
    return {
      ...base,
      borderColor: color,
      boxShadow: `0 0 0 1px ${color}55, 0 0 26px -6px ${color}88`,
    };
  return { ...base, opacity: 0.78 };
}

function layout(nodes: { id: string }[]) {
  const positions = new Map<string, { x: number; y: number }>();
  const middle = nodes.slice(1, -2);
  const width = middle.length * 220;
  middle.forEach((node, index) => {
    positions.set(node.id, { x: index * 220 - width / 2 + 110, y: 40 });
  });
  positions.set("supervisor", { x: 0, y: -110 });
  const tail = nodes.slice(-2);
  tail.forEach((node, index) => {
    positions.set(node.id, { x: -110 + index * 220, y: 190 });
  });
  return positions;
}

const EVENT_TONE: Record<string, string> = {
  AGENT_START: "text-primary",
  AGENT_DONE: "text-success",
  TASK_FAILED: "text-danger",
  ASSET_UPDATE: "text-precon",
  QUALITY_REPORT: "text-warning",
  TASK_COMPLETE: "text-success",
  PROGRESS: "text-falign",
};

export default function AgentDashboard() {
  const { taskId, goal, status, events, agentStatuses, progress } = useAgentStore();
  const { nodes, edges, plan, currentNode } = useWorkflowStore();
  const setAsset = useAssetStore((sandbox) => sandbox.set);
  const applyAgentEvent = useAgentStore((state) => state.applyEvent);
  const finishAgent = useAgentStore((state) => state.finish);
  const applyWorkflowEvent = useWorkflowStore((state) => state.applyEvent);
  const navigate = useNavigate();

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
      const domain = domainOf(node.id);
      return {
        id: node.id,
        position: positions.get(node.id) ?? { x: 0, y: 0 },
        data: {
          label: (
            <div className="flex items-center gap-2.5 text-left">
              <span
                className="grid h-7 w-7 shrink-0 place-items-center rounded-lg"
                style={{
                  background: `${DOMAIN_COLOR[domain]}22`,
                  color: DOMAIN_COLOR[domain],
                }}
              >
                <Icon
                  name={
                    domain === "precon"
                      ? "grid"
                      : domain === "falign"
                        ? "film"
                        : domain === "gimport"
                          ? "package"
                          : domain === "qa"
                            ? "check"
                            : domain === "memory"
                              ? "cube"
                              : domain === "supervisor"
                                ? "layers"
                                : "spark"
                  }
                  className="h-4 w-4"
                />
              </span>
              <span className="min-w-0">
                <span className="block truncate text-[12.5px] font-semibold leading-[17px]">
                  {node.label}
                </span>
                <span className="block truncate text-[10.5px] leading-[15px] text-ink-3">
                  {node.sublabel} · {KIND_LABEL[node.kind]}
                </span>
              </span>
            </div>
          ),
        },
        style: nodeStyle(nodeStatus, currentNode === node.id, domain),
      };
    });
  }, [nodes, plan, agentStatuses, currentNode]);

  const graphEdges: Edge[] = edges.map((edge) => ({
    id: `${edge.from}->${edge.to}`,
    source: edge.from,
    target: edge.to,
    animated: true,
    style: { stroke: "#3a4658", strokeDasharray: "5 5" },
  }));

  const qualityEvent = events.filter((event) => event.type === "QUALITY_REPORT").at(-1);
  const repairCount = events.filter((event) => event.repair).length;
  const runningNode = nodes.find((node) => node.id === currentNode);

  if (!taskId) {
    return (
      <div className="mx-auto w-full max-w-[1440px] px-4 py-5 md:px-6">
        <Card>
          <EmptyState
            icon="layers"
            title="还没有正在运行的任务"
            description="回到工作台输入一个游戏创意，Supervisor 会规划任务图并调度 Art / Animation / Engine / QA 智能体。"
            action={
              <Button variant="primary" icon="spark" onClick={() => navigate("/")}>
                去创建任务
              </Button>
            }
          />
        </Card>
      </div>
    );
  }

  const statusTone =
    status === "pass" ? "success" : status === "failed" ? "danger" : "primary";

  return (
    <div className="mx-auto flex w-full max-w-[1440px] flex-col gap-5 px-4 py-5 md:px-6">
      <PageHeader
        overline="Agent Command Center"
        title="智能体指挥中心"
        description={`「${goal}」`}
        actions={
          <>
            <span className="font-mono text-xs text-ink-3">{taskId}</span>
            <Badge tone={statusTone}>
              <StatusDot tone={status === "pass" ? "success" : status === "failed" ? "failed" : "running"} />
              {status === "running" ? `运行中 ${progress}%` : status.toUpperCase()}
            </Badge>
            {status === "pass" && (
              <Button variant="primary" size="sm" icon="cube" onClick={() => navigate("/asset")}>
                查看资产
              </Button>
            )}
          </>
        }
      />

      <div className="grid grid-cols-12 gap-5">
        <Card
          className="col-span-12 xl:col-span-8"
          title="任务图 Task Graph"
          icon="layers"
          right={
            <div className="flex gap-1.5">
              <Badge tone="neutral">{nodes.length} 节点</Badge>
              <Badge tone="neutral">{edges.length} 边</Badge>
            </div>
          }
          bodyClassName="p-3"
        >
          <div className="h-[430px] overflow-hidden rounded-xl border border-line-subtle bg-[radial-gradient(420px_200px_at_50%_0%,rgba(96,165,250,.09),transparent_70%)]">
            <ReactFlow
              nodes={graphNodes}
              edges={graphEdges}
              fitView
              proOptions={{ hideAttribution: true }}
              nodesDraggable={false}
              nodesConnectable={false}
            >
              <Background color="#1e2633" gap={24} />
              <Controls showInteractive={false} />
            </ReactFlow>
          </div>
        </Card>

        <Card
          className="col-span-12 xl:col-span-4"
          title="执行记录"
          icon="activity"
          bodyClassName="p-0"
        >
          <RightPanel
            events={events}
            qualityEvent={qualityEvent}
            progress={progress}
            status={status}
          />
        </Card>

        <Card className="col-span-12 md:col-span-4" title="当前节点" icon="spark">
          {runningNode ? (
            <>
              <div className="flex items-center gap-2">
                <Badge tone="primary">{runningNode.label}</Badge>
                <span className="text-xs text-ink-3">{runningNode.sublabel}</span>
              </div>
              <div className="mt-3 space-y-0">
                <div className="flex justify-between border-b border-white/[.05] py-2 text-[12.5px]">
                  <span className="text-ink-3">进度</span>
                  <span className="tabular font-mono">{progress}%</span>
                </div>
                <div className="flex justify-between border-b border-white/[.05] py-2 text-[12.5px]">
                  <span className="text-ink-3">任务 ID</span>
                  <span className="font-mono">{taskId}</span>
                </div>
                <div className="flex justify-between py-2 text-[12.5px]">
                  <span className="text-ink-3">状态</span>
                  <span className={cx(status === "failed" ? "text-danger" : "text-primary")}>
                    {status}
                  </span>
                </div>
              </div>
            </>
          ) : (
            <p className="text-xs text-ink-3">等待调度…</p>
          )}
        </Card>

        <Card className="col-span-12 md:col-span-4" title="质量门" icon="gauge">
          <div className="space-y-3.5">
            <ScoreBar label="pixel · 阈值 0.80" value={qualityEvent?.scores?.pixel ?? 0} threshold={0.8} />
            <ScoreBar
              label="animation · 阈值 0.85"
              value={qualityEvent?.scores?.animation ?? 0}
              threshold={0.85}
            />
            <ScoreBar
              label="engine · 阈值 0.90"
              value={qualityEvent?.scores?.engine ?? 0}
              threshold={0.9}
            />
          </div>
          <p className="mt-3 text-[11px] text-ink-3">
            {qualityEvent
              ? `最新报告：${qualityEvent.status ?? "—"}`
              : "等待 QA Agent 验证…"}
          </p>
        </Card>

        <Card className="col-span-12 md:col-span-4" title="修复与恢复" icon="refresh">
          <div className="flex flex-wrap items-center gap-2">
            <Badge tone={repairCount > 0 ? "warning" : "neutral"}>
              {repairCount > 0 ? `修复轮 ${repairCount}` : "0 轮修复"}
            </Badge>
            <Badge tone="neutral" icon="refresh">
              checkpoint
            </Badge>
          </div>
          <p className="mt-3 text-xs leading-[19px] text-ink-3">
            失败时自动降级：Unity → Cocos → 人工介入。检查点写入 Memory Agent，可从任务图任意节点恢复。
          </p>
        </Card>
      </div>
    </div>
  );
}

function RightPanel({
  events,
  qualityEvent,
  progress,
  status,
}: {
  events: TaskEvent[];
  qualityEvent: TaskEvent | undefined;
  progress: number;
  status: string;
}) {
  const [tab, setTab] = useState("events");
  const recent = events.slice(-7).reverse();

  return (
    <div>
      <div className="px-[18px] pt-3">
        <Tabs
          items={[
            { id: "events", label: "事件流", count: events.length },
            { id: "timeline", label: "时间线" },
            { id: "quality", label: "质量" },
          ]}
          value={tab}
          onChange={setTab}
        />
      </div>
      <div className="cf-scroll max-h-[430px] overflow-y-auto p-[18px]">
        {tab === "events" && (
          <div className="font-mono text-[11.5px] leading-[19px]" aria-live="polite">
            {events.length === 0 && <p className="text-ink-4">等待事件…</p>}
            {events.map((event, index) => (
              <motion.div
                key={index}
                initial={{ opacity: 0, x: -6 }}
                animate={{ opacity: 1, x: 0 }}
                transition={{ duration: 0.18 }}
                className="flex items-baseline gap-2.5"
              >
                <span className="shrink-0 text-ink-4">
                  {new Date((event.at ?? 0) * 1000).toLocaleTimeString([], {
                    minute: "2-digit",
                    second: "2-digit",
                  })}
                </span>
                <span className={cx("shrink-0 font-medium", EVENT_TONE[event.type] ?? "text-ink-2")}>
                  {event.type}
                </span>
                <span className="truncate text-ink-3">
                  {event.agent ?? event.task ?? event.detail ?? ""}
                </span>
              </motion.div>
            ))}
          </div>
        )}

        {tab === "timeline" && (
          <ol className="relative space-y-4 pl-1">
            <span className="absolute bottom-2 left-[10px] top-2 w-0.5 rounded-sm bg-line-subtle" />
            {recent.length === 0 && <p className="text-xs text-ink-4">等待 Agent 状态变化…</p>}
            {recent.map((event, index) => (
              <li key={index} className="relative flex gap-3.5">
                <span className="relative z-10 mt-1 grid h-[22px] w-[22px] shrink-0 place-items-center rounded-full border-2 border-primary bg-canvas text-primary">
                  <Icon name="activity" className="h-3 w-3" />
                </span>
                <div className="min-w-0">
                  <div className="text-[12.5px] font-medium">{event.type}</div>
                  <div className="truncate text-[11.5px] text-ink-3">
                    {event.agent ?? event.task ?? "Agent System"} ·{" "}
                    {new Date((event.at ?? 0) * 1000).toLocaleTimeString([], {
                      minute: "2-digit",
                      second: "2-digit",
                    })}
                  </div>
                </div>
              </li>
            ))}
          </ol>
        )}

        {tab === "quality" && (
          <div className="space-y-3.5">
            {qualityEvent?.scores ? (
              Object.entries(qualityEvent.scores).map(([section, score]) => (
                <ScoreBar
                  key={section}
                  label={section}
                  value={score}
                  threshold={
                    section === "pixel" ? 0.8 : section === "animation" ? 0.85 : 0.9
                  }
                />
              ))
            ) : (
              <p className="text-xs text-ink-3">
                {status === "failed" ? "任务失败，请重试" : "QA 尚未产出报告…"}
              </p>
            )}
            <div className="border-t border-line-subtle pt-3">
              <div className="flex items-center justify-between text-xs text-ink-3">
                <span>整体进度</span>
                <span className="tabular font-mono text-ink">{progress}%</span>
              </div>
            </div>
          </div>
        )}
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

import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { api } from "../api/client";
import { useAgentStore } from "../stores/agentStore";
import { useWorkflowStore } from "../stores/workflowStore";
import { useAssetStore } from "../stores/assetStore";
import { Badge, Card } from "../components/ui";

const EXAMPLES = [
  "生成一个像素RPG火焰法师Boss，带攻击动画，并导入Unity",
  "创建一个像素风RPG火焰法师角色，包含待机、攻击动画，并导入Cocos项目",
  "生成一把像素火焰剑道具，导入Unity",
  "做一个像素洞穴Boss，带攻击动画，导入Unity",
];

export default function Workspace() {
  const [goal, setGoal] = useState(EXAMPLES[0]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const navigate = useNavigate();

  const startAgent = useAgentStore((s) => s.start);
  const resetWorkflow = useWorkflowStore((s) => s.reset);
  const resetAsset = useAssetStore((s) => s.set);

  const tasks = useQuery({ queryKey: ["tasks"], queryFn: api.listTasks });

  async function generate() {
    if (!goal.trim() || busy) return;
    setBusy(true);
    setError(null);
    try {
      resetWorkflow();
      resetAsset(null);
      const { task_id } = await api.createTask(goal.trim());
      startAgent(task_id, goal.trim());
      navigate("/agents");
    } catch (cause) {
      setError(String(cause));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="mx-auto max-w-4xl px-8 py-10">
      <header className="mb-8">
        <h1 className="pixel-title text-2xl font-bold">
          <span className="text-sky-400">CreativeForge</span> Studio
        </h1>
        <p className="mt-2 text-sm text-zinc-400">
          描述你的游戏创意，智能体团队自主规划并产出可导入引擎的资产
        </p>
      </header>

      <Card title="创建你的游戏资产 / Create your game asset">
        <textarea
          value={goal}
          onChange={(event) => setGoal(event.target.value)}
          rows={4}
          className="w-full resize-none rounded-lg border border-zinc-700 bg-zinc-950 p-3 text-sm text-zinc-100 outline-none focus:border-amber-400/60"
          placeholder="创建一个像素风火焰法师Boss：需要 Idle 动画、Attack 动画、Unity 导出"
        />
        <div className="mt-3 flex flex-wrap gap-2">
          {EXAMPLES.map((example) => (
            <button
              key={example}
              onClick={() => setGoal(example)}
              className="rounded-full border border-zinc-700 px-3 py-1 text-xs text-zinc-400 transition-colors hover:border-amber-400/50 hover:text-amber-300"
            >
              {example.length > 26 ? example.slice(0, 26) + "…" : example}
            </button>
          ))}
        </div>
        {error && <p className="mt-3 text-xs text-red-400">{error}</p>}
        <div className="mt-4 flex items-center justify-between">
          <span className="text-xs text-zinc-500">
            Supervisor 将自动规划 Generation → PReCon → FAlign → GImport → QA
          </span>
          <button
            onClick={generate}
            disabled={busy || !goal.trim()}
            className="rounded-lg bg-amber-400 px-6 py-2 text-sm font-semibold text-zinc-950 transition-colors hover:bg-amber-300 disabled:opacity-40"
          >
            {busy ? "创建中…" : "Generate ⚡"}
          </button>
        </div>
      </Card>

      <Card title="最近任务 / Recent tasks" className="mt-6">
        {tasks.isLoading ? (
          <p className="text-xs text-zinc-500">加载中…</p>
        ) : (tasks.data?.tasks.length ?? 0) === 0 ? (
          <p className="text-xs text-zinc-500">还没有任务，从上面开始第一次创作。</p>
        ) : (
          <ul className="divide-y divide-zinc-800/70">
            {tasks.data!.tasks.map((task) => (
              <li key={task.task_id} className="flex items-center gap-3 py-2">
                <span className="font-mono text-xs text-zinc-500">{task.task_id}</span>
                <span className="flex-1 truncate text-sm text-zinc-300">{task.goal}</span>
                <Badge
                  tone={
                    task.status === "pass"
                      ? "green"
                      : task.status === "failed"
                        ? "red"
                        : "amber"
                  }
                >
                  {task.status}
                </Badge>
                {task.asset_id && (
                  <span className="font-mono text-xs text-zinc-500">{task.asset_id}</span>
                )}
              </li>
            ))}
          </ul>
        )}
      </Card>
    </div>
  );
}

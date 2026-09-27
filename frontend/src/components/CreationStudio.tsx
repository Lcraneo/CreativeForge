import { useState } from "react";
import { api } from "../api";
import type { ProviderSelection } from "../types";
import ModelPicker from "./ModelPicker";

const EXAMPLES = [
  "创建一个赛博朋克机械猫战士，装备火焰剑，有攻击动画，导入Cocos",
  "创建一个像素RPG火焰法师Boss，带攻击技能，导入Unity",
  "创建一个日式动漫风格的精灵弓箭手，有跳跃动画，导入Godot",
];

const ENGINES = ["cocos", "unity", "godot"];
const STYLES = ["自动", "赛博朋克", "像素", "日式动漫"];
const PIPELINE = [
  "Generate",
  "AssetStruct",
  "DNA",
  "MotionAlign",
  "Combat",
  "Export",
  "Quality",
];

function Segmented(props: {
  options: string[];
  value: string;
  onChange: (v: string) => void;
}) {
  return (
    <div className="flex overflow-hidden rounded-lg border border-line-2">
      {props.options.map((item) => (
        <button
          key={item}
          onClick={() => props.onChange(item)}
          className={`px-4 py-1.5 text-sm capitalize transition-colors ${
            props.value === item
              ? "bg-ink text-paper"
              : "text-ink-2 hover:bg-panel"
          }`}
        >
          {item}
        </button>
      ))}
    </div>
  );
}

export default function CreationStudio(props: {
  onCreated: (taskId: string, assetId: string | null) => void;
  onOpenAsset: (assetId: string) => void;
}) {
  const [prompt, setPrompt] = useState(EXAMPLES[0]);
  const [engine, setEngine] = useState("cocos");
  const [style, setStyle] = useState("自动");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [model, setModel] = useState<ProviderSelection>({
    provider: "builtin",
    model: "",
  });
  const [lastAssetId, setLastAssetId] = useState<string | null>(() =>
    window.localStorage.getItem("cf.lastAssetId"),
  );

  const buildPrompt = () => {
    if (style === "自动" || prompt.includes(style)) return prompt;
    return `${prompt}，${style}风格`;
  };

  const generate = async () => {
    if (!prompt.trim() || busy) return;
    setBusy(true);
    setError(null);
    try {
      const body = await api.createAsset({
        prompt: buildPrompt(),
        engine,
        user_id: "studio",
        provider: model.provider,
        model: model.model,
      });
      if (body.asset_id) setLastAssetId(body.asset_id);
      props.onCreated(body.task_id, body.asset_id);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="grid gap-14 lg:grid-cols-[1fr_300px]">
      <section>
        <h1 className="font-display text-4xl font-black text-ink">创作</h1>
        <p className="mt-3 text-sm text-ink-2">
          描述目标，Agent Runtime 自主规划任务图并串起全链路生产。
        </p>

        <textarea
          value={prompt}
          onChange={(e) => setPrompt(e.target.value)}
          rows={4}
          placeholder="描述你想创建的角色 / 动画 / 引擎…"
          className="mt-8 w-full resize-none rounded-xl border border-line-2 bg-panel/60 p-5 text-[15px] leading-relaxed text-ink outline-none transition-colors placeholder:text-mute focus:border-ink"
        />

        <div className="mt-4 flex flex-wrap gap-x-6 gap-y-2">
          {EXAMPLES.map((example, i) => (
            <button
              key={i}
              onClick={() => setPrompt(example)}
              className="text-xs text-mute underline decoration-line-2 underline-offset-4 transition-colors hover:text-ink hover:decoration-ink"
            >
              {example.slice(0, 16)}…
            </button>
          ))}
        </div>

        <div className="mt-9 flex flex-wrap items-end gap-8">
          <div>
            <div className="mb-2 text-xs uppercase tracking-widest text-mute">
              引擎
            </div>
            <Segmented options={ENGINES} value={engine} onChange={setEngine} />
          </div>
          <div>
            <div className="mb-2 text-xs uppercase tracking-widest text-mute">
              风格
            </div>
            <Segmented options={STYLES} value={style} onChange={setStyle} />
          </div>
          <button
            onClick={generate}
            disabled={busy || !prompt.trim()}
            className="ml-auto rounded-lg bg-ink px-8 py-2.5 text-sm text-paper transition-all hover:opacity-85 disabled:cursor-not-allowed disabled:opacity-40"
          >
            {busy ? "Agent 执行中…" : "开始生成"}
          </button>
        </div>

        <ModelPicker value={model} onChange={setModel} />

        {busy && (
          <div className="mt-6 h-[3px] w-full overflow-hidden rounded bg-line">
            <div className="h-full w-1/3 animate-pulse rounded bg-ink" />
          </div>
        )}
        {error && (
          <p className="mt-5 border-l-2 border-bad pl-3 text-sm text-bad">
            创建失败：{error}
          </p>
        )}
      </section>

      <aside>
        <div className="text-xs uppercase tracking-widest text-mute">
          核心闭环
        </div>
        <ol className="mt-5 border-t border-line">
          {PIPELINE.map((stage, i) => (
            <li
              key={stage}
              className="flex items-baseline gap-4 border-b border-line py-3"
            >
              <span className="font-display text-sm text-mute">
                {String(i + 1).padStart(2, "0")}
              </span>
              <span className="text-sm text-ink">{stage}</span>
            </li>
          ))}
        </ol>
        {lastAssetId && (
          <>
            <div className="mt-10 text-xs uppercase tracking-widest text-mute">
              最近资产
            </div>
            <button
              onClick={() => props.onOpenAsset(lastAssetId)}
              className="mt-3 break-all text-left font-mono text-xs leading-relaxed text-ink-2 underline decoration-line-2 underline-offset-4 hover:text-ink"
            >
              {lastAssetId}
            </button>
          </>
        )}
      </aside>
    </div>
  );
}

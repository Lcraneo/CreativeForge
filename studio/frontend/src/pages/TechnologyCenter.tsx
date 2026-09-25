import { useNavigate } from "react-router-dom";
import { Badge, Button, Card, KV, PageHeader, Stepper } from "../components/ui";
import { Icon, type IconName } from "../components/icons";

const ENGINES: Array<{
  name: string;
  overline: string;
  domain: "precon" | "falign" | "gimport";
  icon: IconName;
  description: string;
  metrics: Array<{ label: string; value: string }>;
  tone: "precon" | "falign" | "gimport";
}> = [
  {
    name: "PReCon",
    overline: "PIXEL RECONSTRUCTION",
    domain: "precon",
    icon: "grid",
    tone: "precon",
    description: "AI 图片 → 网格推断 → 语义化调色板重建 → 轮廓修复 → 风格一致性。",
    metrics: [
      { label: "像素一致性", value: "90%" },
      { label: "调色板", value: "37 → 16 色" },
      { label: "轮廓保持", value: "88%" },
    ],
  },
  {
    name: "FAlign",
    overline: "FRAME ALIGNMENT",
    domain: "falign",
    icon: "film",
    tone: "falign",
    description: "切帧 → 锚点检测 → 运动相位对齐 → 根运动纠偏 → 时序一致性。",
    metrics: [
      { label: "根漂移", value: "2.25 → 0.00 px/f" },
      { label: "时序平滑", value: "96%" },
      { label: "脚滑修正", value: "95%" },
    ],
  },
  {
    name: "GImport",
    overline: "ENGINE IMPORT",
    domain: "gimport",
    icon: "package",
    tone: "gimport",
    description: "图集 → 动画剪辑 → Prefab → 引擎适配 → 运行时校验 → 一键导出。",
    metrics: [
      { label: "导入成功率", value: "100%" },
      { label: "流程", value: "12 步 → 1 步" },
      { label: "引擎", value: "Unity / Cocos / Godot" },
    ],
  },
];

export default function TechnologyCenter() {
  const navigate = useNavigate();

  return (
    <div className="mx-auto flex w-full max-w-[1440px] flex-col gap-5 px-4 py-5 md:px-6">
      <PageHeader
        overline="Technology Center"
        title="技术中心"
        description="三项自研引擎，覆盖从自然语言描述到引擎工程包的全链路"
        actions={
          <Badge tone="gimport" icon="check">
            已接入生产管线
          </Badge>
        }
      />

      <section className="cf-sheen relative overflow-hidden rounded-2xl border border-line-subtle bg-[radial-gradient(700px_260px_at_88%_-30%,rgba(76,194,255,.2),transparent_70%),radial-gradient(460px_240px_at_4%_130%,rgba(139,123,255,.13),transparent_70%),linear-gradient(180deg,#111826,#0c1017)] p-7">
        <div className="text-[11px] font-semibold uppercase tracking-[0.08em] text-primary">
          CreativeForge Engine
        </div>
        <h2 className="mt-2.5 max-w-3xl text-[40px] font-semibold leading-[48px] tracking-[-0.02em]">
          把创意
          <span className="bg-gradient-to-br from-[#7ad1ff] to-[#b9a8ff] bg-clip-text text-transparent">
            锻造
          </span>
          成可运行的资产
        </h2>
        <p className="mt-3 max-w-2xl text-sm leading-[22px] text-ink-2">
          CreativeAsset 统一协议连接像素重建、动画切帧对齐与引擎自动导入。多智能体自主规划，
          产物可直接导入 Unity / Cocos / Godot。
        </p>
        <div className="mt-5 flex flex-wrap gap-2.5">
          <Button variant="ember" size="lg" icon="spark" onClick={() => navigate("/")}>
            立即生成资产
          </Button>
          <Button variant="secondary" size="lg" icon="gauge" onClick={() => navigate("/benchmark")}>
            查看基准数据
          </Button>
        </div>
      </section>

      <div className="grid grid-cols-1 gap-5 lg:grid-cols-3">
        {ENGINES.map((engine) => (
          <Card key={engine.name} domain={engine.domain}>
            <div className="flex items-center gap-3">
              <span
                className={`grid h-10 w-10 place-items-center rounded-[10px] ${
                  engine.tone === "precon"
                    ? "bg-precon/15 text-precon"
                    : engine.tone === "falign"
                      ? "bg-falign/15 text-falign"
                      : "bg-gimport/15 text-gimport"
                }`}
              >
                <Icon name={engine.icon} className="h-5 w-5" />
              </span>
              <div>
                <div
                  className={`text-lg font-semibold leading-6 ${
                    engine.tone === "precon"
                      ? "text-precon"
                      : engine.tone === "falign"
                        ? "text-falign"
                        : "text-gimport"
                  }`}
                >
                  {engine.name}
                </div>
                <div className="text-[10.5px] font-semibold uppercase tracking-[0.08em] text-ink-4">
                  {engine.overline}
                </div>
              </div>
            </div>
            <p className="mt-3 text-[13px] leading-5 text-ink-2">{engine.description}</p>
            <div className="mt-3">
              {engine.metrics.map((metric) => (
                <KV key={metric.label} label={metric.label} value={metric.value} />
              ))}
            </div>
            <button
              onClick={() => navigate("/benchmark")}
              className="mt-3 inline-flex items-center gap-1 text-xs font-medium text-primary transition-opacity hover:opacity-80"
            >
              查看基准数据
              <Icon name="chevron" className="h-3.5 w-3.5" />
            </button>
          </Card>
        ))}
      </div>

      <Card title="生产流程" icon="activity">
        <Stepper
          steps={[
            { id: "gen", label: "Generation", state: "done" },
            { id: "precon", label: "PReCon", state: "done" },
            { id: "falign", label: "FAlign", state: "done" },
            { id: "gimport", label: "GImport", state: "done" },
            { id: "qa", label: "QA Gate", state: "done" },
            { id: "engine", label: "Engine Ready", state: "running" },
          ]}
        />
        <p className="mt-4 text-[12.5px] leading-5 text-ink-3">
          Supervisor 解析自然语言目标 → 生成任务图 → 调度 Art / Animation / Engine 智能体 →
          QA 验证与修复轮 → 产出一键导出包。全流程带检查点与失败恢复。
        </p>
      </Card>

      <div className="grid grid-cols-1 gap-5 lg:grid-cols-2">
        <Card title="统一资产协议" icon="cube" right={<Badge tone="primary">CreativeAsset v1.0</Badge>}>
          <KV label="Identity" value="id / name / type / role / source" />
          <KV label="Pixel" value="grid / palette / contour" />
          <KV label="Animation" value="frames / phase / motion" />
          <KV label="Engine" value="manifest / resources / validation" />
          <KV label="Quality" value="pixel / animation / engine / report" />
          <p className="mt-3 text-[11.5px] leading-[18px] text-ink-3">
            所有引擎与智能体只通过协议读写，保证产物在管线内可验证、可复现、可替换引擎。
          </p>
        </Card>

        <Card title="多智能体协作" icon="layers" right={<Badge tone="primary">Autonomous</Badge>}>
          <KV label="Supervisor" value="规划 · 路由 · QA/修复循环 · 记忆" />
          <KV label="Art Agent" value="Generation + PReCon" />
          <KV label="Animation Agent" value="FAlign" />
          <KV label="Engine Agent" value="GImport：Unity / Cocos / Godot" />
          <KV label="QA / Memory" value="质量门 · 阈值 · 检查点" />
          <p className="mt-3 text-[11.5px] leading-[18px] text-ink-3">
            失败自动降级（Unity → Cocos → 人工介入），任务图任意节点均可从检查点恢复。
          </p>
        </Card>
      </div>

      <div className="flex flex-wrap items-center justify-between gap-3 border-t border-line-subtle pt-5 text-xs text-ink-4">
        <span>CreativeForge AI · AI Game Asset Factory</span>
        <span className="flex items-center gap-2">
          <Icon name="book" className="h-3.5 w-3.5" />
          文档：docs/architecture.md · docs/design/02-visual-spec.md
        </span>
      </div>
    </div>
  );
}

import { useMemo, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../api/client";
import { assetHref, useAssetStore } from "../stores/assetStore";
import { toast } from "../stores/toastStore";
import {
  Badge,
  Button,
  Card,
  EmptyState,
  KV,
  PageHeader,
  SafeImage,
  ScoreBar,
  Skeleton,
  StatusDot,
  cx,
} from "../components/ui";
import { CharacterArt } from "../components/CharacterArt";
import { Icon } from "../components/icons";
import type { HistorySummary } from "../types";

const ENGINES = [
  { id: "all", label: "全部" },
  { id: "unity", label: "Unity" },
  { id: "cocos", label: "Cocos" },
  { id: "godot", label: "Godot" },
];

function statusTone(status: string) {
  return status === "pass" || status === "success"
    ? "success"
    : status === "failed"
      ? "danger"
      : status === "running"
        ? "primary"
        : "neutral";
}

function timeLabel(seconds: number) {
  return new Date(seconds * 1000).toLocaleString([], {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export default function HistoryCenter() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const setAsset = useAssetStore((state) => state.set);
  const [engine, setEngine] = useState("all");
  const [query, setQuery] = useState("");
  const [searchParams, setSearchParams] = useSearchParams();
  // 深链支持：/history?open=<id> 直达某条档案（首页「最近出炉」等入口）
  const [selectedId, setSelectedId] = useState<string | null>(() => searchParams.get("open"));
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [deleting, setDeleting] = useState(false);

  const records = useQuery({
    queryKey: ["history", engine, query],
    queryFn: () =>
      api.listHistory({
        engine: engine === "all" ? undefined : engine,
        q: query.trim() || undefined,
        limit: 80,
      }),
  });

  const detailQuery = useQuery({
    queryKey: ["history-record", selectedId],
    queryFn: () => api.getHistory(selectedId!),
    enabled: Boolean(selectedId),
  });

  const rows = records.data?.records ?? [];
  const allShownSelected = rows.length > 0 && rows.every((record) => selected.has(record.id));

  function toggleAll() {
    setSelected((prev) => {
      const next = new Set(prev);
      if (allShownSelected) rows.forEach((record) => next.delete(record.id));
      else rows.forEach((record) => next.add(record.id));
      return next;
    });
  }

  function toggleOne(id: string) {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  async function deleteSelected() {
    const ids = [...selected];
    if (ids.length === 0 || deleting) return;
    setDeleting(true);
    try {
      const results = await Promise.all(ids.map((id) => api.deleteHistory(id).catch(() => null)));
      const removed = results.reduce((sum, result) => sum + (result?.removed ?? 0), 0);
      if (selectedId && ids.includes(selectedId)) setSelectedId(null);
      setSelected(new Set());
      await queryClient.invalidateQueries({ queryKey: ["history"] });
      toast({
        tone: "success",
        title: `已删除 ${removed} 条档案`,
        description:
          removed < ids.length ? `${ids.length - removed} 条不存在或早已删除` : undefined,
      });
    } catch (cause) {
      toast({ tone: "danger", title: "删除失败", description: String(cause) });
    } finally {
      setDeleting(false);
    }
  }
  const detail = detailQuery.data;
  const bestScores = useMemo(() => {
    if (!detail?.scores) return [];
    const order = ["pixel", "animation", "engine", "agent"];
    return order
      .filter((key) => detail.scores[key] !== undefined)
      .map((key) => [key, detail.scores[key]] as const);
  }, [detail]);

  async function openAsset(record: HistorySummary) {
    if (!record.asset_id) return;
    try {
      const asset = record.asset ?? (await api.getAsset(record.asset_id));
      setAsset(asset);
      navigate(assetHref("/asset", record.asset_id));
    } catch (cause) {
      toast({ tone: "danger", title: "资产加载失败", description: String(cause) });
    }
  }

  // A 失败透明化：AI 生图失败（审核拦截/额度等）的档案一键重试——
  // 直接以原目标创建新任务并跳转智能体指挥中心跟进
  async function retryGeneration(goal: string) {
    try {
      const { task_id } = await api.createTask(goal);
      toast({
        tone: "success",
        title: `重试任务 ${task_id} 已创建`,
        description: "正在按原目标重新生成，到「智能体」跟进进度",
      });
      navigate("/agents");
    } catch (cause) {
      toast({ tone: "danger", title: "重试失败", description: String(cause).slice(0, 160) });
    }
  }

  return (
    <div className="mx-auto flex w-full max-w-[1440px] flex-col gap-5 px-4 py-5 md:px-6">
      <PageHeader
        overline="History"
        title="历史记录"
        description="每次资产生产的完整档案：目标、角色规格、质量分数与导出引擎"
        actions={
          <>
            <div className="flex gap-1">
              {ENGINES.map((item) => (
                <button
                  key={item.id}
                  onClick={() => setEngine(item.id)}
                  className={cx(
                    "h-8 rounded-md border px-3 text-[12.5px] transition-colors",
                    engine === item.id
                      ? "border-primary bg-primary-tint font-semibold text-primary"
                      : "border-line-subtle bg-surface-1 text-ink-2 hover:border-line hover:text-ink",
                  )}
                >
                  {item.label}
                </button>
              ))}
            </div>
            <div className="relative">
              <Icon
                name="search"
                className="pointer-events-none absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-ink-3"
              />
              <input
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                placeholder="搜索目标 / 资产名"
                className="h-8 w-44 rounded-md border border-line bg-surface-2 pl-8 pr-2.5 text-[12.5px] text-ink outline-none placeholder:text-ink-4 focus:border-primary"
              />
            </div>
            {selected.size > 0 && (
              <>
                <Button
                  variant="secondary"
                  size="sm"
                  icon="x"
                  onClick={() => setSelected(new Set())}
                >
                  取消选择
                </Button>
                <Button
                  variant="danger"
                  size="sm"
                  icon="trash"
                  loading={deleting}
                  onClick={deleteSelected}
                >
                  删除选中（{selected.size}）
                </Button>
              </>
            )}
          </>
        }
      />

      <div className="grid grid-cols-12 gap-5">
        <Card
          className={cx("col-span-12", selectedId ? "xl:col-span-7" : "xl:col-span-12")}
          title={`生产档案${records.data ? ` · ${records.data.total} 条` : ""}`}
          icon="clock"
          bodyClassName="p-0"
        >
          {records.isLoading ? (
            <div className="space-y-2 p-5">
              <Skeleton className="h-10" />
              <Skeleton className="h-10" />
              <Skeleton className="h-10" />
            </div>
          ) : rows.length === 0 ? (
            <EmptyState
              icon="clock"
              title="暂无历史记录"
              description="完成一次资产生成后，档案会自动归档到这里，可随时回看与重跑。"
              action={
                <Button variant="primary" size="sm" icon="spark" onClick={() => navigate("/")}>
                  去生成资产
                </Button>
              }
            />
          ) : (
            <div className="cf-scroll overflow-x-auto">
              <table className="w-full border-collapse text-[13px]">
                <thead>
                  <tr className="bg-surface-2 text-left text-[10.5px] uppercase tracking-[0.08em] text-ink-4">
                    <th className="w-10 px-3 py-2.5">
                      <input
                        type="checkbox"
                        aria-label="全选当前列表"
                        className="h-3.5 w-3.5 translate-y-px accent-ink"
                        checked={allShownSelected}
                        onChange={toggleAll}
                      />
                    </th>
                    <th className="w-14 px-3 py-2.5">
                      <span className="sr-only">缩略图</span>
                    </th>
                    <th className="px-4 py-2.5 font-semibold">时间</th>
                    <th className="px-4 py-2.5 font-semibold">目标 / 资产</th>
                    <th className="px-4 py-2.5 font-semibold">状态</th>
                    <th className="px-4 py-2.5 font-semibold">引擎</th>
                    <th className="px-4 py-2.5 font-semibold">QA</th>
                    <th className="px-4 py-2.5 text-right font-semibold">耗时</th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map((record) => (
                    <tr
                      key={record.id}
                      onClick={() => setSelectedId(record.id)}
                      className={cx(
                        "cursor-pointer border-b border-ink/[.08] text-ink-2 transition-colors last:border-0 hover:bg-surface-2/60",
                        selectedId === record.id && "bg-primary-tint/60",
                        selected.has(record.id) && selectedId !== record.id && "bg-success/[.06]",
                      )}
                    >
                      <td className="px-3 py-3" onClick={(event) => event.stopPropagation()}>
                        <input
                          type="checkbox"
                          aria-label={`选择 ${record.name || record.goal}`}
                          className="h-3.5 w-3.5 translate-y-px accent-ink"
                          checked={selected.has(record.id)}
                          onChange={() => toggleOne(record.id)}
                        />
                      </td>
                      <td className="px-3 py-2.5">
                        <SafeImage
                          src={record.image?.url ?? undefined}
                          alt={record.name || record.goal || "资产"}
                          className="h-10 w-10 rounded-md border border-line-subtle bg-paper object-cover"
                          fallback={
                            <CharacterArt
                              spec={record.character}
                              palette={record.palette}
                              view="bust"
                              className="h-8 w-8"
                            />
                          }
                        />
                      </td>
                      <td className="whitespace-nowrap px-4 py-3 font-mono text-[11.5px] text-ink-3">
                        {timeLabel(record.finished_at || record.created_at)}
                      </td>
                      <td className="max-w-[320px] px-4 py-3">
                        <div className="truncate text-ink">{record.name || record.goal}</div>
                        <div className="truncate text-[11px] text-ink-3">
                          {record.character?.class_label}
                          {record.character?.element_label && record.character.element !== "none"
                            ? ` · ${record.character.element_label}`
                            : ""}
                          {record.frames ? ` · ${record.frames}f` : ""}
                        </div>
                        {record.model_image_error && (
                          <span
                            className="mt-1 inline-block"
                            title={`AI 生图失败：${record.model_image_error.detail}`}
                          >
                            <Badge tone="warning">AI 生图失败 · 离线示意</Badge>
                          </span>
                        )}
                      </td>
                      <td className="px-4 py-3">
                        <Badge tone={statusTone(record.status)}>
                          <StatusDot
                            tone={
                              record.report_status === "PASS"
                                ? "success"
                                : record.status === "failed"
                                  ? "failed"
                                  : "idle"
                            }
                          />
                          {record.report_status || record.status}
                        </Badge>
                      </td>
                      <td className="px-4 py-3 font-mono text-[11.5px]">{record.engine ?? "—"}</td>
                      <td className="px-4 py-3 font-mono text-[11.5px] text-ink-3">
                        {record.qa_rounds} 轮
                      </td>
                      <td className="px-4 py-3 text-right font-mono text-[11.5px] text-ink-3">
                        {record.elapsed_seconds != null
                          ? `${record.elapsed_seconds.toFixed(1)}s`
                          : "—"}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Card>

        {selectedId && (
          <Card
            className="col-span-12 xl:col-span-5"
            title="档案详情"
            icon="cube"
            right={
              <Button
                variant="ghost"
                size="sm"
                icon="x"
                onClick={() => {
                  setSelectedId(null);
                  if (searchParams.get("open")) setSearchParams({}, { replace: true });
                }}
              >
                关闭
              </Button>
            }
          >
            {detailQuery.isLoading || !detail ? (
              <div className="space-y-2">
                <Skeleton className="h-24" />
                <Skeleton className="h-6" />
                <Skeleton className="h-6" />
              </div>
            ) : (
              <div className="flex flex-col gap-4">
                <div className="flex gap-4">
                  <div className="grid h-[120px] w-[104px] shrink-0 place-items-center overflow-hidden rounded-[10px] border border-line-subtle bg-paper">
                    <SafeImage
                      src={detail.image?.url ?? undefined}
                      alt={detail.name ?? "asset"}
                      className="h-full w-full object-cover"
                      fallback={
                        <CharacterArt
                          spec={detail.character}
                          palette={detail.palette}
                          view="bust"
                          className="h-[96px] w-[88px]"
                        />
                      }
                    />
                  </div>
                  <div className="min-w-0 flex-1">
                    <div className="truncate text-[15px] font-semibold text-ink">
                      {detail.name || detail.goal}
                    </div>
                    <p className="mt-0.5 line-clamp-2 text-[12px] leading-[18px] text-ink-3">
                      {detail.character?.summary || detail.goal}
                    </p>
                    <div className="mt-2 flex flex-wrap gap-1.5">
                      {detail.character?.class_label && (
                        <Badge tone="neutral">{detail.character.class_label}</Badge>
                      )}
                      {detail.character?.element_label && detail.character.element !== "none" && (
                        <Badge tone="neutral">{detail.character.element_label}</Badge>
                      )}
                      {detail.character?.weapon_label && (
                        <Badge tone="neutral">{detail.character.weapon_label}</Badge>
                      )}
                    </div>
                    <div className="mt-2 flex flex-wrap gap-1.5">
                      {detail.palette?.slice(0, 8).map((color, index) => (
                        <span
                          key={`${color}-${index}`}
                          title={color}
                          className="h-4 w-4 rounded-sm border border-ink/[.12]"
                          style={{ background: color }}
                        />
                      ))}
                    </div>
                  </div>
                </div>

                {bestScores.length > 0 && (
                  <div>
                    {bestScores.map(([key, value]) => (
                      <ScoreBar
                        key={key}
                        label={`${key} · 阈值 ${key === "pixel" ? 0.8 : key === "animation" ? 0.85 : 0.9}`}
                        value={value}
                        threshold={key === "pixel" ? 0.8 : key === "animation" ? 0.85 : 0.9}
                        tone={
                          key === "pixel"
                            ? "precon"
                            : key === "animation"
                              ? "falign"
                              : key === "engine"
                                ? "gimport"
                                : "primary"
                        }
                      />
                    ))}
                  </div>
                )}

                {detail.model_image_error && (
                  <div className="rounded-lg border border-warning/50 bg-warning/[.06] p-3">
                    <div className="text-[12px] font-semibold text-warning">
                      AI 生图失败：{detail.model_image_error.detail}
                    </div>
                    <p className="mt-1 text-[11.5px] leading-[18px] text-ink-3">
                      当前产物是离线确定性示意，可能与目标主题不符。可原样重试（后端会对
                      审核拦截自动改写提示词再生成），或回工作台改写描述。
                    </p>
                    <Button
                      variant="secondary"
                      size="sm"
                      icon="refresh"
                      className="mt-2"
                      onClick={() => retryGeneration(detail.goal)}
                    >
                      重试生成
                    </Button>
                  </div>
                )}

                <div>
                  <KV label="task" value={detail.task_id} />
                  <KV label="asset" value={detail.asset_id ?? "—"} />
                  <KV label="seed" value={detail.character?.seed ?? "—"} />
                  {detail.error && <KV label="error" value={detail.error} />}
                </div>

                {detail.enhanced_prompt && (
                  <div className="rounded-lg border border-line-subtle bg-surface-2/50 p-3">
                    <div className="mb-1 text-[10.5px] font-semibold uppercase tracking-[0.08em] text-ink-4">
                      增强提示词
                    </div>
                    <p className="line-clamp-4 text-[12px] leading-[19px] text-ink-2">
                      {detail.enhanced_prompt}
                    </p>
                  </div>
                )}

                <div className="flex flex-wrap gap-2">
                  <Button
                    variant="primary"
                    size="sm"
                    icon="cube"
                    disabled={!detail.asset_id}
                    onClick={() => openAsset(detail)}
                  >
                    打开资产
                  </Button>
                  <Button
                    variant="secondary"
                    size="sm"
                    icon="refresh"
                    onClick={() => {
                      navigate("/", { state: { goal: detail.goal } });
                      toast({
                        tone: "info",
                        title: "已带回目标描述",
                        description: "可在工作台微调后重新生成",
                      });
                    }}
                  >
                    重跑此目标
                  </Button>
                </div>
              </div>
            )}
          </Card>
        )}
      </div>
    </div>
  );
}

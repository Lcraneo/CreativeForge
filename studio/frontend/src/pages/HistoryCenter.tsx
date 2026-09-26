import { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { api } from "../api/client";
import { useAssetStore } from "../stores/assetStore";
import { toast } from "../stores/toastStore";
import {
  Badge,
  Button,
  Card,
  EmptyState,
  Input,
  PageHeader,
  Segmented,
  Skeleton,
} from "../components/ui";
import { CharacterArt } from "../components/CharacterArt";
import { AiImage } from "../components/AiImage";
import { Icon } from "../components/icons";
import type { HistorySummary } from "../types";

const ENGINES = [
  { id: "all", label: "全部" },
  { id: "unity", label: "Unity" },
  { id: "cocos", label: "Cocos" },
  { id: "godot", label: "Godot" },
];

function formatTime(seconds?: number) {
  if (!seconds) return "—";
  const date = new Date(seconds * 1000);
  return date.toLocaleString([], {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function statusTone(status?: string) {
  return status === "pass" || status === "success"
    ? "success"
    : status === "failed"
      ? "danger"
      : "primary";
}

export default function HistoryCenter() {
  const [engine, setEngine] = useState("all");
  const [keyword, setKeyword] = useState("");
  const [search, setSearch] = useState("");
  const navigate = useNavigate();
  const setAsset = useAssetStore((state) => state.set);

  const query = useQuery({
    queryKey: ["history", engine, search],
    queryFn: () =>
      api.listHistory({
        engine: engine === "all" ? undefined : engine,
        q: search || undefined,
        limit: 200,
      }),
    refetchOnWindowFocus: false,
  });

  const records = useMemo(() => query.data?.records ?? [], [query.data]);

  async function viewAsset(record: HistorySummary) {
    try {
      const detail = await api.getHistory(record.record_id);
      if (!detail.asset) {
        toast({ tone: "warning", title: "该记录没有资产快照" });
        return;
      }
      setAsset(detail.asset);
      toast({
        tone: "success",
        title: `已载入 ${detail.asset.name ?? detail.asset.id}`,
        description: `${record.record_id} · ${detail.goal.slice(0, 24)}`,
      });
      navigate("/asset");
    } catch (cause) {
      toast({ tone: "danger", title: "载入资产失败", description: String(cause) });
    }
  }

  async function openDesign(record: HistorySummary) {
    try {
      const detail = await api.getHistory(record.record_id);
      if (!detail.asset) {
        toast({ tone: "warning", title: "该记录没有资产快照" });
        return;
      }
      setAsset(detail.asset);
      navigate("/design");
    } catch (cause) {
      toast({ tone: "danger", title: "载入设计稿失败", description: String(cause) });
    }
  }

  function reusePrompt(record: HistorySummary) {
    navigate("/", { state: { goal: record.goal } });
  }

  function copyPrompt(record: HistorySummary) {
    navigator.clipboard?.writeText(record.goal).catch(() => undefined);
    toast({ tone: "info", title: "已复制提示词", description: record.record_id });
  }

  return (
    <div className="mx-auto flex w-full max-w-[1440px] flex-col gap-5 px-4 py-5 md:px-6">
      <PageHeader
        overline="Generation History"
        title="历史记录"
        description={
          query.data
            ? `共 ${query.data.total} 条生成记录 · 时间 / 提示词 / 角色属性 / 资产快照全部可检索`
            : "查看时间、提示词、角色形象与资产快照"
        }
        actions={
          <>
            <Button
              variant="secondary"
              size="sm"
              icon="refresh"
              onClick={() => query.refetch()}
            >
              刷新
            </Button>
            <Button
              variant="primary"
              size="sm"
              icon="spark"
              onClick={() => navigate("/")}
            >
              新建生成
            </Button>
          </>
        }
      />

      <div className="flex flex-wrap items-center gap-3">
        <Segmented
          options={ENGINES}
          value={engine}
          onChange={setEngine as (value: string) => void}
        />
        <form
          className="ml-auto w-full max-w-sm"
          onSubmit={(event) => {
            event.preventDefault();
            setSearch(keyword.trim());
          }}
        >
          <Input
            icon="search"
            value={keyword}
            onChange={(event) => setKeyword(event.target.value)}
            placeholder="按提示词 / 角色 / 名称检索…"
          />
        </form>
      </div>

      {query.isLoading ? (
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
          <Skeleton className="h-44" />
          <Skeleton className="h-44" />
        </div>
      ) : query.isError ? (
        <Card>
          <EmptyState
            icon="alert"
            title="历史加载失败"
            description={String(query.error)}
            action={
              <Button variant="secondary" size="sm" icon="refresh" onClick={() => query.refetch()}>
                重试
              </Button>
            }
          />
        </Card>
      ) : records.length === 0 ? (
        <Card>
          <EmptyState
            icon="clock"
            title={search ? "没有匹配的记录" : "还没有生成记录"}
            description={
              search
                ? "换一个关键词，或清空筛选后重试。"
                : "在工作台描述一个游戏角色，生成后这里会保留完整历史。"
            }
            action={
              <Button variant="primary" size="sm" icon="spark" onClick={() => navigate("/")}>
                去生成第一个角色
              </Button>
            }
          />
        </Card>
      ) : (
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
          {records.map((record) => (
            <Card
              key={record.record_id}
              bodyClassName="p-4"
              className="transition-colors hover:border-line"
            >
              <div className="flex gap-4">
                <div className="grid h-28 w-24 shrink-0 place-items-center overflow-hidden rounded-xl border border-line-subtle bg-[radial-gradient(70px_70px_at_50%_25%,rgba(76,194,255,.1),transparent_70%),#0a0e15]">
                  <AiImage
                    src={
                      record.image?.url ||
                      (record.asset_id
                        ? `/api/assets/${encodeURIComponent(record.asset_id)}/image.png?size=192`
                        : undefined)
                    }
                    alt={record.name ?? "concept art"}
                    className="h-full w-full object-cover"
                    fallback={
                      <CharacterArt
                        spec={record.character}
                        palette={record.palette}
                        view="bust"
                        detail="simple"
                        className="h-[114px] w-[92px]"
                      />
                    }
                  />
                </div>

                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2">
                    <span className="font-mono text-[11px] text-ink-4">
                      {record.record_id} · {record.task_id}
                    </span>
                    <Badge tone={statusTone(record.status)}>
                      {record.report_status ?? record.status}
                    </Badge>
                    {record.engine && <Badge tone="neutral">{record.engine}</Badge>}
                    {record.image && (
                      <Badge tone="primary" icon="spark">
                        AI 原画
                      </Badge>
                    )}
                    {record.enhanced_prompt && (
                      <Badge tone="primary" icon="activity">
                        提示词增强
                      </Badge>
                    )}
                    <span className="ml-auto text-[11px] text-ink-4">
                      {formatTime(record.created_at)}
                    </span>
                  </div>

                  <p className="mt-1.5 line-clamp-2 text-[13px] leading-5 text-ink" title={record.goal}>
                    {record.goal}
                  </p>

                  <div className="mt-2 flex flex-wrap items-center gap-1.5">
                    {record.character.summary && (
                      <span className="text-[11.5px] text-ink-3">{record.character.summary}</span>
                    )}
                    {record.frames ? (
                      <Badge tone="neutral">
                        {record.action} · {record.frames} 帧
                      </Badge>
                    ) : (
                      <Badge tone="neutral">静态</Badge>
                    )}
                    {record.character.height_cm && (
                      <Badge tone="neutral">{record.character.height_cm}cm</Badge>
                    )}
                  </div>

                  <div className="mt-2 flex flex-wrap gap-1.5">
                    {Object.entries(record.scores).map(([section, score]) => (
                      <Badge
                        key={section}
                        tone={
                          section === "pixel"
                            ? "precon"
                            : section === "animation"
                              ? "falign"
                              : section === "engine"
                                ? "gimport"
                                : "neutral"
                        }
                      >
                        {section} {Math.round(score * 100)}%
                      </Badge>
                    ))}
                    {record.elapsed_seconds != null && (
                      <Badge tone="neutral">
                        {record.elapsed_seconds < 1
                          ? `${Math.round(record.elapsed_seconds * 1000)}ms`
                          : `${record.elapsed_seconds.toFixed(2)}s`}
                      </Badge>
                    )}
                  </div>
                </div>
              </div>

              {record.error && (
                <p className="mt-3 rounded-md border border-danger/30 bg-danger/10 px-3 py-2 text-[11.5px] text-danger">
                  {record.error}
                </p>
              )}

              <div className="mt-3 flex flex-wrap items-center gap-2 border-t border-line-subtle pt-3">
                <Button
                  variant="secondary"
                  size="sm"
                  icon="cube"
                  onClick={() => viewAsset(record)}
                  disabled={!record.asset_id}
                >
                  查看资产
                </Button>
                <Button
                  variant="secondary"
                  size="sm"
                  icon="layers"
                  onClick={() => openDesign(record)}
                  disabled={!record.asset_id}
                >
                  三视图
                </Button>
                <Button
                  variant="ghost"
                  size="sm"
                  icon="refresh"
                  onClick={() => reusePrompt(record)}
                >
                  复用提示词
                </Button>
                <button
                  onClick={() => copyPrompt(record)}
                  className="ml-auto inline-flex items-center gap-1.5 text-[11.5px] text-ink-3 transition-colors hover:text-primary"
                >
                  <Icon name="copy" className="h-3.5 w-3.5" />
                  复制提示词
                </button>
              </div>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}

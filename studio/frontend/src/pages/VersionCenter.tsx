import { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { api } from "../api/client";
import {
  Badge,
  Button,
  Card,
  EmptyState,
  KV,
  PageHeader,
  SafeImage,
  ScoreBar,
  StatusDot,
  cx,
} from "../components/ui";
import { Icon } from "../components/icons";
import { toast } from "../stores/toastStore";
import { assetHref, useAssetStore } from "../stores/assetStore";
import type { VersionView } from "../types";

function timeLabel(seconds?: number) {
  if (!seconds) return "—";
  return new Date(seconds * 1000).toLocaleString([], {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export default function VersionCenter() {
  const navigate = useNavigate();
  const setAsset = useAssetStore((state) => state.set);
  const groups = useQuery({
    queryKey: ["version-groups"],
    queryFn: api.versionGroups,
  });
  const [selected, setSelected] = useState<string | null>(null);
  const tree = useQuery({
    queryKey: ["version-tree", selected],
    queryFn: () => api.versionTree(selected!),
    enabled: Boolean(selected),
  });
  const [checked, setChecked] = useState<VersionView[]>([]);
  const [diffPair, setDiffPair] = useState<[number, number] | null>(null);
  const [confirming, setConfirming] = useState(false);
  const [rollingBack, setRollingBack] = useState(false);
  const rollbacks = useQuery({ queryKey: ["rollback-log"], queryFn: api.rollbackLog });

  const versions = tree.data?.versions ?? [];
  const versionA = useMemo(
    () => versions.find((v) => v.version_no === diffPair?.[0]) ?? null,
    [versions, diffPair],
  );
  const versionB = useMemo(
    () => versions.find((v) => v.version_no === diffPair?.[1]) ?? null,
    [versions, diffPair],
  );

  function toggle(version: VersionView) {
    setConfirming(false);
    setChecked((current) => {
      const exists = current.some((item) => item.version_no === version.version_no);
      if (exists) return current.filter((item) => item.version_no !== version.version_no);
      // 最多选两个：既支持多选回滚，也支撑 A/B 对比
      return [...current.slice(-1), version];
    });
  }

  async function tagVersion(tag: string) {
    if (checked.length !== 1) return;
    try {
      await api.tagVersion(checked[0].record_id, tag);
      toast({
        tone: tag === "approved" ? "success" : "info",
        title:
          tag === "approved" ? "已标记定稿" : tag === "needs-work" ? "已标记待改" : "已清除标记",
        description: `v${checked[0].version_no} · ${checked[0].name ?? ""}`,
      });
      tree.refetch();
    } catch (cause) {
      toast({ tone: "danger", title: "标记失败", description: String(cause).slice(0, 160) });
    }
  }

  async function doRollback() {
    if (checked.length === 0) return;
    setRollingBack(true);
    try {
      const result = await api.rollbackVersions(checked.map((item) => item.record_id));
      const failed = result.entries.filter((entry) => !entry.ok);
      toast({
        tone: failed.length ? "warning" : "success",
        title: `已回滚 ${result.restored} 个版本`,
        description: failed.length
          ? `${failed.length} 个版本无法恢复（缺少资产快照）`
          : `回滚编号 ${result.rollback_id} · 当前资产已切换`,
      });
      setChecked([]);
      setConfirming(false);
      rollbacks.refetch();
      if (result.current_asset_id) {
        try {
          setAsset(await api.getAsset(result.current_asset_id));
        } catch {
          /* asset store refresh is best-effort */
        }
      }
    } catch (cause) {
      toast({ tone: "danger", title: "回滚失败", description: String(cause).slice(0, 160) });
    } finally {
      setRollingBack(false);
    }
  }

  const groupList = groups.data?.groups ?? [];
  const focused = diffPair ? versionB : checked.at(-1) ?? versions.at(-1) ?? null;
  const focusedScores = focused
    ? (["pixel", "animation", "engine"] as const).filter(
        (key) => focused.scores[key] != null,
      )
    : [];

  return (
    <div className="mx-auto flex w-full max-w-[1440px] flex-col gap-5 px-4 py-5 md:px-6">
      <PageHeader
        overline="Asset Version Control"
        title="版本控制中心"
        description="每一代生成的资产自动入树：版本追踪 · 差异对比 · 一键回滚 —— 改坏了随时撤回"
        actions={
          <Badge tone="primary" icon="clock">
            回滚审计 {rollbacks.data?.rollbacks.length ?? 0} 次
          </Badge>
        }
      />

      <div className="grid grid-cols-12 gap-5">
        {/* 左：资产家族 + 版本列表 */}
        <div className="col-span-12 flex min-w-0 flex-col gap-5 lg:col-span-3">
          <Card title="资产家族" icon="layers" bodyClassName="p-0">
            {groupList.length === 0 ? (
              <p className="p-4 text-xs text-ink-3">还没有历史版本，先去工作台生成资产。</p>
            ) : (
              <div className="cf-scroll max-h-[280px] overflow-y-auto">
                {groupList.map((group) => (
                  <button
                    key={group.name}
                    onClick={() => {
                      setSelected(group.name);
                      setChecked([]);
                      setDiffPair(null);
                      setConfirming(false);
                    }}
                    className={cx(
                      "flex w-full items-center gap-3 border-b border-ink/[.08] px-4 py-3 text-left transition-colors last:border-0",
                      selected === group.name ? "bg-primary-tint/60" : "hover:bg-surface-2/60",
                    )}
                  >
                    <span className="min-w-0 flex-1">
                      <span className="block truncate text-[13px] font-medium text-ink">
                        {group.name}
                      </span>
                      <span className="block text-[11px] text-ink-3">
                        {timeLabel(group.latest_at)}
                      </span>
                    </span>
                    <Badge tone={group.count > 1 ? "precon" : "neutral"}>v{group.count}</Badge>
                  </button>
                ))}
              </div>
            )}
          </Card>

          <Card
            title="版本列表"
            icon="clock"
            bodyClassName="p-0"
            right={selected ? <Badge tone="neutral">{versions.length} 个版本</Badge> : undefined}
          >
            {!selected ? (
              <p className="p-4 text-xs text-ink-3">先在左侧选择一个资产家族。</p>
            ) : tree.isLoading ? (
              <p className="p-4 text-xs text-ink-3">加载版本树…</p>
            ) : versions.length === 0 ? (
              <p className="p-4 text-xs text-ink-3">该名称下没有版本记录。</p>
            ) : (
              <ol className="cf-scroll max-h-[520px] overflow-y-auto">
                {versions.map((version) => {
                  const isChecked = checked.some(
                    (item) => item.version_no === version.version_no,
                  );
                  const isLatest = version.version_no === versions.length;
                  return (
                    <li
                      key={version.record_id}
                      className={cx(
                        "flex items-center gap-2.5 border-b border-ink/[.08] px-3 py-2.5 last:border-0",
                        isChecked && "bg-primary-tint/40",
                      )}
                    >
                      <input
                        type="checkbox"
                        checked={isChecked}
                        onChange={() => toggle(version)}
                        aria-label={`选择 v${version.version_no}`}
                        className="h-3.5 w-3.5 shrink-0 accent-[var(--color-primary,#4a6f8a)]"
                      />
                      <button
                        onClick={() => toggle(version)}
                        className="flex min-w-0 flex-1 items-center gap-2.5 text-left"
                      >
                        {version.image_url ? (
                          <SafeImage
                            src={version.image_url}
                            alt={`v${version.version_no}`}
                            sealChar={`v${version.version_no}`.slice(-1)}
                            className="h-10 w-10 shrink-0 rounded-md border border-line-subtle bg-paper object-cover"
                          />
                        ) : (
                          <span className="grid h-10 w-10 shrink-0 place-items-center rounded-md border border-line-subtle bg-surface-2 text-ink-4">
                            <Icon name="cube" className="h-4 w-4" />
                          </span>
                        )}
                        <span className="min-w-0 flex-1">
                          <span className="flex flex-wrap items-center gap-1.5">
                            <span className="font-mono text-[12px] font-semibold text-primary">
                              v{version.version_no}
                            </span>
                            {isLatest && <Badge tone="success">当前</Badge>}
                            {version.review_tag === "approved" && (
                              <Badge tone="primary">定稿</Badge>
                            )}
                            {version.review_tag === "needs-work" && (
                              <Badge tone="warning">待改</Badge>
                            )}
                          </span>
                          <span className="mt-0.5 block truncate text-[12px] text-ink">
                            {version.action ? `${version.action} · ` : ""}
                            {version.goal || version.name}
                          </span>
                          <span className="block truncate text-[10.5px] text-ink-4">
                            {timeLabel(version.created_at)}
                            {version.engine ? ` · ${version.engine}` : ""}
                          </span>
                        </span>
                        <StatusDot
                          tone={
                            version.status === "PASS"
                              ? "success"
                              : version.status === "FAILED"
                                ? "failed"
                                : "idle"
                          }
                        />
                      </button>
                    </li>
                  );
                })}
              </ol>
            )}
          </Card>
        </div>

        {/* 中：版本对比或详情 */}
        <div className="col-span-12 flex min-w-0 flex-col gap-5 lg:col-span-5">
          {!selected ? (
            <Card>
              <EmptyState
                icon="layers"
                title="选择一个资产家族"
                description="同名资产的所有生成记录会按时间组成版本树（v1 → vN），选中后可对比差异并一键回滚。"
              />
            </Card>
          ) : versionA && versionB ? (
            <Card
              title={`差异对比 · v${versionA.version_no} ↔ v${versionB.version_no}`}
              icon="grid"
              right={
                <Button variant="ghost" size="sm" onClick={() => setDiffPair(null)}>
                  关闭对比
                </Button>
              }
            >
              <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
                {[versionA, versionB].map((version) => (
                  <div key={version.version_no} className="rounded-xl border border-line-subtle p-3">
                    <div className="mb-2 flex items-center justify-between">
                      <Badge tone="primary">v{version.version_no}</Badge>
                      <span className="text-[11px] text-ink-3">
                        {timeLabel(version.created_at)}
                      </span>
                    </div>
                    {version.image_url ? (
                      <SafeImage
                        src={version.image_url}
                        alt={`v${version.version_no}`}
                        sealChar={`v${version.version_no}`.slice(-1)}
                        className="mx-auto h-[220px] max-w-full object-contain"
                      />
                    ) : (
                      <div className="grid h-[220px] place-items-center text-xs text-ink-4">
                        无图
                      </div>
                    )}
                    {version.palette.length > 0 && (
                      <div className="mt-2 flex flex-wrap gap-1">
                        {version.palette.slice(0, 12).map((color, index) => (
                          <span
                            key={`${color}-${index}`}
                            className="h-4 w-4 rounded-sm border border-ink/[.12]"
                            style={{ background: color }}
                          />
                        ))}
                      </div>
                    )}
                  </div>
                ))}
              </div>
              <DiffTable pair={[versionA, versionB]} />
            </Card>
          ) : (
            <Card
              title={focused ? `版本详情 · v${focused.version_no}` : "版本详情"}
              icon="cube"
            >
              {tree.isLoading ? (
                <p className="p-2 text-xs text-ink-3">加载版本树…</p>
              ) : !focused ? (
                <p className="p-2 text-xs text-ink-3">该家族暂无版本记录。</p>
              ) : (
                <div className="flex flex-col gap-4">
                  <div className="flex items-center justify-between">
                    <Badge tone="primary">v{focused.version_no}</Badge>
                    <span className="text-[11px] text-ink-3">{timeLabel(focused.created_at)}</span>
                  </div>
                  {focused.image_url ? (
                    <SafeImage
                      src={focused.image_url}
                      alt={`v${focused.version_no}`}
                      sealChar={`v${focused.version_no}`.slice(-1)}
                      className="mx-auto h-[260px] max-w-full object-contain"
                    />
                  ) : (
                    <div className="grid h-[260px] place-items-center rounded-xl border border-line-subtle text-xs text-ink-4">
                      无图
                    </div>
                  )}
                  <div>
                    <div className="truncate text-[14px] font-semibold text-ink">
                      {focused.goal || focused.name}
                    </div>
                    <div className="mt-1 flex flex-wrap items-center gap-1.5">
                      {focused.engine && <Badge tone="neutral">{focused.engine}</Badge>}
                      <Badge
                        tone={
                          focused.status === "PASS"
                            ? "success"
                            : focused.status === "FAILED"
                              ? "danger"
                              : "neutral"
                        }
                      >
                        <StatusDot
                          tone={
                            focused.status === "PASS"
                              ? "success"
                              : focused.status === "FAILED"
                                ? "failed"
                                : "idle"
                          }
                        />
                        {focused.status || "—"}
                      </Badge>
                      {focused.seed != null && <Badge tone="neutral">seed {focused.seed}</Badge>}
                    </div>
                  </div>
                  {focused.palette.length > 0 && (
                    <div className="flex flex-wrap gap-1">
                      {focused.palette.slice(0, 12).map((color, index) => (
                        <span
                          key={`${color}-${index}`}
                          title={color}
                          className="h-4 w-4 rounded-sm border border-ink/[.12]"
                          style={{ background: color }}
                        />
                      ))}
                    </div>
                  )}
                  <div className="rounded-xl border border-line-subtle px-3 py-1">
                    <KV label="家族" value={selected} mono={false} />
                    <KV label="task" value={focused.task_id ?? "—"} />
                    <KV label="asset" value={focused.asset_id ?? "—"} />
                  </div>
                  {focusedScores.length > 0 && (
                    <div className="space-y-3">
                      {focusedScores.map((key) => (
                        <ScoreBar
                          key={key}
                          label={key}
                          value={focused.scores[key]!}
                          threshold={key === "pixel" ? 0.8 : key === "animation" ? 0.85 : 0.9}
                          tone={
                            key === "pixel" ? "precon" : key === "animation" ? "falign" : "gimport"
                          }
                        />
                      ))}
                    </div>
                  )}
                </div>
              )}
            </Card>
          )}
        </div>

        {/* 右：版本操作 + 版本信息 */}
        <div className="col-span-12 flex min-w-0 flex-col gap-5 lg:col-span-4">
          <Card title="版本操作" icon="refresh">
            <div className="flex flex-wrap items-center gap-1.5">
              {checked.length === 0 ? (
                <span className="text-[11.5px] text-ink-3">勾选 1–2 个版本后可操作</span>
              ) : (
                checked.map((version) => (
                  <Badge key={version.record_id} tone="primary">
                    v{version.version_no}
                  </Badge>
                ))
              )}
            </div>
            <div className="mt-3 flex flex-col gap-2">
              {checked.length === 2 && (
                <Button
                  variant="secondary"
                  size="sm"
                  icon="grid"
                  onClick={() => setDiffPair([checked[0].version_no, checked[1].version_no])}
                >
                  对比 v{checked[0].version_no} / v{checked[1].version_no}
                </Button>
              )}
              {checked.length >= 1 && !confirming && (
                <Button
                  variant="secondary"
                  size="sm"
                  icon="refresh"
                  onClick={() => setConfirming(true)}
                >
                  回滚选中（{checked.length}）
                </Button>
              )}
              {checked.length === 1 && (
                <div className="grid grid-cols-2 gap-2">
                  <Button
                    variant="ghost"
                    size="sm"
                    icon="check"
                    onClick={() => tagVersion("approved")}
                  >
                    标记定稿
                  </Button>
                  <Button variant="ghost" size="sm" onClick={() => tagVersion("needs-work")}>
                    待改
                  </Button>
                </div>
              )}
              {confirming && (
                <>
                  <Button
                    variant="ember"
                    size="sm"
                    icon="refresh"
                    loading={rollingBack}
                    onClick={doRollback}
                  >
                    确认回滚 {checked.length} 个版本
                  </Button>
                  <Button variant="ghost" size="sm" onClick={() => setConfirming(false)}>
                    取消
                  </Button>
                </>
              )}
              <Button
                variant="ghost"
                size="sm"
                icon="cube"
                className="justify-start"
                onClick={() =>
                  navigate(assetHref("/asset", useAssetStore.getState().asset?.id))
                }
              >
                打开当前资产
              </Button>
            </div>
          </Card>

          <Card title="版本信息" icon="cube">
            {!selected ? (
              <p className="text-xs text-ink-3">选择资产家族后显示版本信息。</p>
            ) : !focused ? (
              <p className="text-xs text-ink-3">该家族暂无版本记录。</p>
            ) : (
              <>
                <div className="flex items-center gap-2">
                  <span className="font-mono text-[14px] font-semibold text-primary">
                    v{focused.version_no}
                  </span>
                  {focused.version_no === versions.length && (
                    <Badge tone="success">当前</Badge>
                  )}
                </div>
                <p className="mt-1 line-clamp-2 text-[12px] leading-[18px] text-ink-3">
                  {focused.goal || focused.name}
                </p>
                <div className="mt-2">
                  <KV label="创建" value={timeLabel(focused.created_at)} />
                  <KV label="引擎" value={focused.engine ?? "—"} />
                  <KV label="seed" value={focused.seed ?? "—"} />
                  <KV label="task" value={focused.task_id ?? "—"} />
                  <KV label="asset" value={focused.asset_id ?? "—"} />
                </div>
              </>
            )}
          </Card>
        </div>
      </div>

      <Card title="回滚审计日志" icon="clock" bodyClassName="p-0">
        {(rollbacks.data?.rollbacks ?? []).length === 0 ? (
          <p className="p-4 text-xs text-ink-3">
            还没有回滚操作。回滚（单个或批量）都会在这里留痕，可追溯、可审计。
          </p>
        ) : (
          <div className="cf-scroll max-h-[240px] overflow-y-auto">
            {rollbacks.data!.rollbacks.map((record) => (
              <div
                key={record.id}
                className="flex items-center gap-3 border-b border-ink/[.08] px-[18px] py-2.5 text-[12px] last:border-0"
              >
                <span className="shrink-0 font-mono text-[11px] text-ink-3">{record.id}</span>
                <span className="shrink-0 text-ink-3">{timeLabel(record.at)}</span>
                <span className="min-w-0 flex-1 truncate text-ink">
                  恢复 {record.count} 个版本：
                  {record.entries
                    .map(
                      (entry) => `v${entry.version_no ?? "?"} ${entry.name ?? entry.record_id}`,
                    )
                    .join("、")}
                </span>
                <Badge tone="success">
                  <StatusDot tone="success" /> done
                </Badge>
              </div>
            ))}
          </div>
        )}
      </Card>
    </div>
  );
}

function DiffTable({ pair }: { pair: [VersionView, VersionView] }) {
  const [a, b] = pair;
  const diff = useQuery({
    queryKey: ["version-diff", a.name, a.version_no, b.version_no],
    queryFn: () => api.versionDiff(a.name!, a.version_no, b.version_no!),
    enabled: Boolean(a.name),
  });
  const fields = diff.data?.fields ?? [];
  if (fields.length === 0) {
    return (
      <p className="mt-3 text-[11px] text-ink-4">两个版本结构参数一致，差异在画面内容本身。</p>
    );
  }
  return (
    <div className="mt-4 space-y-0 rounded-xl border border-line-subtle">
      {fields.map((field) => (
        <div
          key={field.field}
          className="flex items-center gap-3 border-b border-ink/[.08] px-4 py-2 text-[12px] last:border-0"
        >
          <span className="w-28 shrink-0 text-ink-3">{field.field}</span>
          <span className="min-w-0 flex-1 truncate font-mono text-[11px] text-ink">
            {String(field.a ?? "—")}
          </span>
          <Icon name="chevron" className="h-3 w-3 shrink-0 text-ink-4" />
          <span className="min-w-0 flex-1 truncate font-mono text-[11px] text-primary">
            {String(field.b ?? "—")}
          </span>
        </div>
      ))}
    </div>
  );
}

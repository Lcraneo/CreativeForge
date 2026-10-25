/**
 * 试玩舞台 3D · POC-0 页面（内测，懒加载，不进主导航）
 *
 * 闭环：?asset= 深链 → 拉取 3D manifest → 加载真实 GLB → 自动居中播放
 * idle → 拖拽旋转/缩放 → 切换 5 个标准动作；加载失败或缺动作时给出
 * 明确错误态与「回到 2D 舞台」回退入口。
 *
 * 渲染分层：真正的 three/R3F 逻辑全部在 ../../three/Playtest3DCanvas 内，
 * 本文件只是「manifest 拉取 + 动作坞 + 错误/加载态」的薄壳，并经 React.lazy
 * 在 manifest 可用后再加载 three 相关 chunk（保持主入口零 three 体积）。
 */
import { lazy, Suspense, useCallback, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { api } from "../../api/client";
import { Badge, Button, ErrorState, PageHeader, cx } from "../../components/ui";
import { Icon } from "../../components/icons";
import {
  STANDARD_ACTIONS,
  effectiveClips,
  loadErrorLabel,
  manifestErrorLabel,
  missingActions,
  type Playtest3DLoadError,
  type ResolvedClips,
  type StandardAction,
} from "../../lib/playtest3d";

const Playtest3DCanvas = lazy(() => import("../../three/Playtest3DCanvas"));

const ACTION_LABEL: Record<StandardAction, string> = {
  idle: "待机",
  walk: "行走",
  run: "奔跑",
  jump: "跳跃",
  attack: "攻击",
};

export default function Playtest3DPage() {
  const [params] = useSearchParams();
  const assetId = params.get("asset");

  const query = useQuery({
    queryKey: ["playtest3d-manifest", assetId],
    queryFn: () => api.playtest3DManifest(assetId),
    retry: false,
  });
  const manifest = query.data;

  const [activeAction, setActiveAction] = useState<StandardAction>("idle");
  const [resolved, setResolved] = useState<ResolvedClips | null>(null);
  const [loadError, setLoadError] = useState<Playtest3DLoadError | null>(null);
  const [retryKey, setRetryKey] = useState(0);

  const handleReady = useCallback((info: { resolved: ResolvedClips }) => {
    setResolved(info.resolved);
    setLoadError(null);
  }, []);
  const handleError = useCallback((error: Playtest3DLoadError) => {
    setLoadError(error);
  }, []);
  const handleSettled = useCallback((action: StandardAction) => {
    setActiveAction(action);
  }, []);

  const fallbackUrl = manifest?.fallback_url ?? "/playtest";
  // manifest 不可用或接口失败 → 进入错误态（带 2D 回退）；加载中 → 等待
  const busy = query.isLoading && !manifest;

  const missing = resolved ? missingActions(resolved) : [];
  const actionLabel = ACTION_LABEL[activeAction];

  return (
    <div className="mx-auto flex w-full max-w-[1440px] flex-col gap-4 px-4 py-5 md:px-6">
      <PageHeader
        overline="Playtest 3D · POC-0"
        title="试玩舞台 3D"
        description="加载角色的真实 GLB 模型，用鼠标拖拽旋转、滚轮缩放，切换 5 个标准动作验收绑定与动画——这是桌面端内测能力，正式 2D 舞台不受影响"
        actions={
          <>
            <Badge tone="primary" icon="cube">
              3D 内测
            </Badge>
            <Link
              to={fallbackUrl}
              className="inline-flex h-8 items-center gap-2 rounded-md border border-line bg-surface-2 px-3 text-xs font-semibold text-ink transition-[color,background-color,border-color] hover:border-line-strong hover:bg-surface-3"
            >
              <Icon name="refresh" className="h-4 w-4" />回到 2D 舞台
            </Link>
          </>
        }
      />

      {/* ── 接口失败 / manifest 不可用：错误态 + 2D 回退 ─────────────── */}
      {query.error || (manifest && !manifest.available) ? (
        <ErrorState
          title={manifest ? manifestErrorLabel(manifest.error ?? null) : "3D 清单加载失败"}
          description="该角色暂时无法进入 3D 试玩，可先回 2D 舞台继续验收。"
          action={
            <div className="flex items-center gap-2">
              {query.error && (
                <Button variant="secondary" size="sm" icon="refresh" onClick={() => void query.refetch()}>
                  重试
                </Button>
              )}
              <Link
                to={fallbackUrl}
                className="inline-flex h-8 items-center gap-2 rounded-md border border-line bg-surface-2 px-3 text-xs font-semibold text-ink transition-[color,background-color,border-color] hover:border-line-strong hover:bg-surface-3"
              >
                <Icon name="refresh" className="h-4 w-4" />回到 2D 舞台
              </Link>
            </div>
          }
        />
      ) : busy || !manifest ? (
        <div className="grid min-h-[40vh] place-items-center text-xs tracking-[0.16em] text-ink-4">
          加载中…
        </div>
      ) : (
        <>
          {/* ── 验收舞台：顶栏 + 16:9 画布 ───────────────────────────── */}
          <div className="overflow-hidden rounded-xl border border-line-subtle bg-paper">
            <div className="flex flex-wrap items-center gap-2 border-b border-line-subtle px-3 py-2">
              <span className="text-[12px] font-medium text-ink">
                {assetId ?? "3D 夹具角色"}
              </span>
              <Badge tone="neutral">真实 GLB · AnimationMixer</Badge>
              <span className="rounded-md border border-line bg-canvas px-2 py-0.5 text-[11px] text-ink-2">
                当前动作 · {actionLabel}
              </span>
              {missing.length > 0 && (
                <Badge tone="warning">缺失 {missing.length} 个动作</Badge>
              )}
              <span className="ml-auto text-[11px] text-ink-3">拖拽旋转 · 滚轮缩放</span>
            </div>

            <div className="relative h-[520px]">
              <Suspense
                fallback={
                  <div className="grid h-full place-items-center text-xs text-ink-4">
                    加载 3D 引擎中…
                  </div>
                }
              >
                <Playtest3DCanvas
                  key={retryKey}
                  meshUrl={manifest.mesh_url ?? ""}
                  manifestClips={effectiveClips(manifest)}
                  activeAction={activeAction}
                  onReady={handleReady}
                  onError={handleError}
                  onActionSettled={handleSettled}
                />
              </Suspense>

              {/* GLB 加载中：半透明遮罩（不阻挡） */}
              {!loadError && resolved === null && (
                <div className="pointer-events-none absolute inset-0 flex items-center justify-center bg-paper/70">
                  <span className="flex items-center gap-2 text-xs text-ink-3">
                    <span className="inline-block h-3.5 w-3.5 animate-spin-slow rounded-full border-2 border-current border-t-transparent" />
                    正在加载 GLB 模型…
                  </span>
                </div>
              )}

              {/* GLB 下载失败 / 损坏 / 无骨骼 / 无动画：可操作错误态 */}
              {loadError && (
                <div className="absolute inset-0 flex items-center justify-center bg-paper/95">
                  <ErrorState
                    title={loadErrorLabel(loadError)}
                    description="3D 模型无法播放，可重试或回到 2D 舞台。"
                    action={
                      <div className="flex items-center gap-2">
                        <Button
                          variant="secondary"
                          size="sm"
                          icon="refresh"
                          onClick={() => {
                            setLoadError(null);
                            setResolved(null);
                            setRetryKey((value) => value + 1);
                          }}
                        >
                          重新加载
                        </Button>
                        <Link
                          to={fallbackUrl}
                          className="inline-flex h-8 items-center gap-2 rounded-md border border-line bg-surface-2 px-3 text-xs font-semibold text-ink transition-[color,background-color,border-color] hover:border-line-strong hover:bg-surface-3"
                        >
                          <Icon name="refresh" className="h-4 w-4" />回到 2D 舞台
                        </Link>
                      </div>
                    }
                  />
                </div>
              )}
            </div>
          </div>

          {/* ── 底部动作坞：5 个标准动作 ─────────────────────────────── */}
          <div className="flex flex-wrap items-center gap-2">
            {STANDARD_ACTIONS.map((action) => {
              const isMissing = resolved !== null && resolved[action] === null;
              const disabled = resolved === null || isMissing || loadError !== null;
              const active = activeAction === action && !isMissing && !loadError;
              return (
                <button
                  key={action}
                  type="button"
                  onClick={() => setActiveAction(action)}
                  disabled={disabled}
                  aria-pressed={active}
                  className={cx(
                    "inline-flex h-11 min-w-[92px] select-none items-center justify-center gap-2 rounded-lg border px-4 text-[13px] font-semibold transition-[color,background-color,border-color,box-shadow]",
                    active
                      ? "border-primary bg-primary text-canvas shadow-[inset_0_1px_0_rgba(255,255,255,.14)]"
                      : isMissing
                        ? "border-dashed border-line bg-surface-1 text-ink-4"
                        : "border-line bg-paper text-ink-2 hover:border-line-strong hover:text-ink disabled:opacity-45",
                  )}
                >
                  {ACTION_LABEL[action]}
                  {isMissing && <span className="text-[10px] font-normal">未生成</span>}
                </button>
              );
            })}
          </div>

          {/* ── 状态脚注（aria-live） ────────────────────────────────── */}
          <div className="flex flex-wrap items-center gap-x-3 gap-y-1.5 text-[11.5px] text-ink-3">
            <span aria-live="polite" className="text-ink-2">
              {loadError
                ? loadErrorLabel(loadError)
                : resolved === null
                  ? "3D 模型加载中…"
                  : `当前动作：${actionLabel}；` +
                    (missing.length > 0
                      ? `未生成：${missing.map((name) => ACTION_LABEL[name]).join("、")}`
                      : "5 个标准动作均可用")}
            </span>
          </div>
        </>
      )}
    </div>
  );
}
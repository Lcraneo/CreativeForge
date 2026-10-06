import { memo, useEffect, useMemo, useRef, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { Button, Chip, EmptyState, ErrorState, Input, Skeleton, StatusDot, cx } from "../ui";
import { Icon } from "../icons";
import { useVirtualWindow } from "../../hooks/useVirtualWindow";
import { filterStreamItems, STREAM_KINDS, type StreamItem, type StreamKind } from "../../hooks/useTaskFeed";
import { SLIDE_IN, useMotionPref } from "../../lib/motionPresets";

/**
 * 实况流 · 动态内容容器
 * - 交互切换：分类 chips + 关键词搜索（点击/输入即时重组内容）
 * - 动画：普通模式下行插入/移除走 AnimatePresence（SLIDE_IN 预设）；
 *   虚拟模式（大流量）为滚动性能放弃逐行退场动画，仅保留 header 脉冲
 * - 状态：loading 骨架（行高对齐成品，零 CLS）/ error 可重试 /
 *   筛选无匹配 / 空数据指引
 * - 大数据：行数超过 virtualThreshold 自动切换零依赖虚拟滚动
 */
export interface LiveStreamProps {
  items: StreamItem[];
  loading?: boolean;
  /** 致命错误（可重试） */
  error?: string | null;
  /** 非致命提示（如连接中断自动重连中），不阻断内容 */
  notice?: string | null;
  onRetry?: () => void;
  emptyTitle?: string;
  emptyDescription?: string;
  emptyAction?: React.ReactNode;
  /** 滚动视口高度 px */
  height?: number;
  /** 固定行高 px（骨架与虚拟化共用，保证零 CLS） */
  rowHeight?: number;
  /** 超过该行数启用虚拟滚动；设 Infinity 强制普通列表 */
  virtualThreshold?: number;
  className?: string;
}

function StreamRowView({ item }: { item: StreamItem }) {
  return (
    <div className="flex h-full items-center gap-2.5 px-1">
      <span
        className={cx(
          "h-1.5 w-1.5 shrink-0 rounded-full",
          item.tone === "success" && "bg-success",
          item.tone === "danger" && "bg-danger",
          item.tone === "warning" && "bg-warning",
          item.tone === "primary" && "bg-primary",
          item.tone === "precon" && "bg-precon",
          item.tone === "falign" && "bg-falign",
          item.tone === "neutral" && "bg-ink-4",
        )}
        aria-hidden="true"
      />
      <span className="tabular w-[52px] shrink-0 font-mono text-[10.5px] text-ink-4">
        {item.at
          ? new Date(item.at * 1000).toLocaleTimeString([], { minute: "2-digit", second: "2-digit" })
          : "--:--"}
      </span>
      <span className="w-[70px] shrink-0 truncate text-[12px] font-semibold text-ink-2">
        {item.title}
        {item.repair && <span className="ml-1 text-[10px] font-medium text-warning">R</span>}
      </span>
      {item.agent && (
        <span className="hidden w-[104px] shrink-0 truncate font-mono text-[10.5px] text-ink-4 sm:block">
          {item.agent}
        </span>
      )}
      <span className="min-w-0 flex-1 truncate text-[11.5px] text-ink-3" title={item.detail}>
        {item.detail ?? ""}
      </span>
    </div>
  );
}

const StreamRow = memo(StreamRowView);

function SkeletonRows({ rows, rowHeight }: { rows: number; rowHeight: number }) {
  return (
    <div aria-hidden="true">
      {Array.from({ length: rows }).map((_, index) => (
        <div key={index} style={{ height: rowHeight }} className="flex items-center gap-2.5 px-1">
          <Skeleton className="h-1.5 w-1.5 rounded-full" />
          <Skeleton className="h-3 w-[46px]" />
          <Skeleton className="h-3 w-[62px]" />
          <Skeleton className="hidden h-3 w-[96px] sm:block" />
          <Skeleton className="h-3 flex-1" />
        </div>
      ))}
    </div>
  );
}

export function LiveStream({
  items,
  loading = false,
  error = null,
  notice = null,
  onRetry,
  emptyTitle = "等待事件",
  emptyDescription = "任务开跑后，调度与各智能体的动作会实时滚动到这里。",
  emptyAction,
  height = 430,
  rowHeight = 40,
  virtualThreshold = 80,
  className,
}: LiveStreamProps) {
  const pref = useMotionPref();
  const [kind, setKind] = useState<StreamKind | "all">("all");
  const [query, setQuery] = useState("");
  const containerRef = useRef<HTMLDivElement>(null);
  const stickBottom = useRef(true);

  // 性能基准开关（仅 dev）：cf-live-virtual = on|off 强制虚拟/普通模式
  const benchOverride = import.meta.env.DEV ? localStorage.getItem("cf-live-virtual") : null;
  const threshold =
    benchOverride === "off"
      ? Number.POSITIVE_INFINITY
      : benchOverride === "on"
        ? 0
        : virtualThreshold;

  const filtered = useMemo(() => filterStreamItems(items, { kind, query }), [items, kind, query]);
  const virtual = filtered.length > threshold;
  const window_ = useVirtualWindow({
    count: filtered.length,
    rowHeight,
    containerRef,
  });

  // 切换筛选/搜索后回到顶部，让内容切换可感知
  useEffect(() => {
    if (containerRef.current) containerRef.current.scrollTop = 0;
  }, [kind, query]);

  // 贴底跟随：用户在底部附近时新事件自动滚入；向上翻阅时不打扰
  useEffect(() => {
    const el = containerRef.current;
    if (!el || !stickBottom.current) return;
    el.scrollTop = el.scrollHeight;
  }, [filtered.length, virtual]);

  function onScroll() {
    const el = containerRef.current;
    if (!el) return;
    stickBottom.current = el.scrollTop + el.clientHeight >= el.scrollHeight - 60;
  }

  const showSearch = items.length > 8;
  const hasFilter = kind !== "all" || query.trim() !== "";

  return (
    <div className={cx("flex min-h-0 flex-col", className)}>
      {/* 交互区：分类 chips + 搜索 */}
      <div className="flex flex-wrap items-center gap-2 px-1 pb-2.5">
        <Chip active={kind === "all"} onClick={() => setKind("all")}>
          全部
        </Chip>
        {STREAM_KINDS.map((k) => (
          <Chip key={k.id} active={kind === k.id} onClick={() => setKind(k.id)}>
            {k.label}
          </Chip>
        ))}
        {showSearch && (
          <Input
            icon="search"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="搜事件 / 智能体…"
            className="ml-auto h-8 w-[180px]"
            aria-label="筛选事件"
          />
        )}
      </div>

      {/* 非致命提示：连接中断自动重连中 */}
      <AnimatePresence initial={false}>
        {notice && !error && (
          <motion.div
            {...pref.pick(SLIDE_IN)}
            className="mb-2 flex items-center gap-2 rounded-md border border-warning/40 bg-warning/10 px-3 py-1.5 text-[11.5px] text-ink-2"
          >
            <StatusDot tone="warning" />
            {notice}
          </motion.div>
        )}
      </AnimatePresence>

      {/* 内容区 */}
      <div
        ref={containerRef}
        onScroll={onScroll}
        className="cf-scroll min-h-0 overflow-y-auto overscroll-contain rounded-lg border border-line-subtle bg-canvas/60"
        style={{ height }}
      >
        {loading ? (
          <SkeletonRows rows={Math.min(9, Math.floor(height / rowHeight))} rowHeight={rowHeight} />
        ) : error ? (
          <ErrorState
            title="实时流中断"
            description={error}
            action={
              onRetry && (
                <Button variant="secondary" size="sm" icon="refresh" onClick={onRetry}>
                  重新连接
                </Button>
              )
            }
          />
        ) : items.length === 0 ? (
          <EmptyState
            icon="activity"
            title={emptyTitle}
            description={emptyDescription}
            action={emptyAction}
          />
        ) : filtered.length === 0 ? (
          <EmptyState
            icon="search"
            title="没有匹配的事件"
            description={
              query.trim()
                ? `没有包含「${query.trim()}」${kind === "all" ? "" : `的${STREAM_KINDS.find((k) => k.id === kind)?.label ?? ""}类`}事件。`
                : "该分类下暂无事件，换个分类看看。"
            }
            action={
              hasFilter && (
                <Button
                  variant="secondary"
                  size="sm"
                  icon="x"
                  onClick={() => {
                    setKind("all");
                    setQuery("");
                  }}
                >
                  清除筛选
                </Button>
              )
            }
          />
        ) : virtual ? (
          /* 大流量模式：零依赖虚拟滚动，绝对定位行 + 总高占位 */
          <div style={{ height: window_.totalHeight, position: "relative" }}>
            {window_.virtualItems.map(({ index, offsetTop }) => {
              const item = filtered[index];
              if (!item) return null;
              return (
                <div
                  key={item.id}
                  style={{ position: "absolute", top: offsetTop, height: rowHeight, left: 0, right: 0 }}
                >
                  <StreamRow item={item} />
                </div>
              );
            })}
          </div>
        ) : (
          /* 普通模式：插入/移除都有过渡，读屏用户可感知增量的完整清单 */
          <div role="log" aria-live="polite" aria-relevant="additions">
            <AnimatePresence initial={false} mode="popLayout">
              {filtered.map((item) => (
                <motion.div
                  key={item.id}
                  layout
                  {...pref.pick(SLIDE_IN)}
                  style={{ height: rowHeight }}
                  className="border-b border-ink/[.05] last:border-b-0"
                >
                  <StreamRow item={item} />
                </motion.div>
              ))}
            </AnimatePresence>
          </div>
        )}
      </div>

      {/* 计数条：内容规模与模式可感知 */}
      <div className="flex items-center justify-between px-1 pt-2 text-[10.5px] text-ink-4">
        <span>
          {loading
            ? "正在接入事件流…"
            : `显示 ${filtered.length} / ${items.length} 条${virtual ? " · 虚拟滚动" : ""}`}
        </span>
        <span className="flex items-center gap-1">
          <Icon name="activity" className="h-3 w-3" />
          实时
        </span>
      </div>
    </div>
  );
}

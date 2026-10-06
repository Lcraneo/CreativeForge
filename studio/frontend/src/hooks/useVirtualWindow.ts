import { useCallback, useEffect, useRef, useState, type RefObject } from "react";

export interface VirtualItem {
  index: number;
  offsetTop: number;
}

export interface VirtualWindowOptions {
  /** 数据总数 */
  count: number;
  /** 固定行高 px（本组件按等高行设计，保证 totalHeight 精确、无 CLS） */
  rowHeight: number;
  /** 视口外上下各多渲染几行，滚动时不露白 */
  overscan?: number;
  /** 滚动容器 */
  containerRef: RefObject<HTMLElement | null>;
}

export interface VirtualWindowResult {
  /** 当前窗口内应渲染的行 */
  virtualItems: VirtualItem[];
  /** 占位总高（撑出真实滚动条） */
  totalHeight: number;
  /** 行数低于该值时没必要虚拟化（供调用方降级为普通列表 + 进出场动画） */
  staticBreakEven: number;
}

/**
 * 零依赖定高虚拟滚动窗口：
 * - 滚动回调 rAF 节流 + passive 监听，只在窗口变化时 setState；
 * - ResizeObserver 跟随容器高度变化（特性缺失时退化为仅滚动驱动）；
 * - jsdom/无 IO 环境安全：没有布局引擎也能渲染首窗。
 */
export function useVirtualWindow({
  count,
  rowHeight,
  overscan = 6,
  containerRef,
}: VirtualWindowOptions): VirtualWindowResult {
  const [range, setRange] = useState<{ start: number; end: number }>({ start: 0, end: 0 });
  const frame = useRef(0);

  const recalc = useCallback(() => {
    const el = containerRef.current;
    const top = el?.scrollTop ?? 0;
    const viewport = el?.clientHeight ?? 0;
    const start = Math.max(0, Math.floor(top / rowHeight) - overscan);
    const end = Math.min(count, Math.ceil((top + viewport) / rowHeight) + overscan);
    setRange((prev) => (prev.start === start && prev.end === end ? prev : { start, end }));
  }, [containerRef, count, overscan, rowHeight]);

  // 滚动驱动：rAF 合并同一帧内的多次 scroll 事件
  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    const onScroll = () => {
      if (frame.current) return;
      frame.current = requestAnimationFrame(() => {
        frame.current = 0;
        recalc();
      });
    };
    el.addEventListener("scroll", onScroll, { passive: true });
    return () => {
      el.removeEventListener("scroll", onScroll);
      if (frame.current) cancelAnimationFrame(frame.current);
      frame.current = 0;
    };
  }, [containerRef, recalc]);

  // 数据量变化 / 首挂载：立即重算一次（含窗口高度）
  useEffect(() => {
    recalc();
  }, [recalc]);

  // 容器高度变化（如折叠侧栏、旋转屏幕）跟随
  useEffect(() => {
    const el = containerRef.current;
    if (!el || typeof ResizeObserver === "undefined") return;
    const observer = new ResizeObserver(() => recalc());
    observer.observe(el);
    return () => observer.disconnect();
  }, [containerRef, recalc]);

  const start = Math.min(range.start, Math.max(0, count - 1));
  const end = Math.max(range.end, Math.min(count, start + 1));
  const virtualItems: VirtualItem[] = [];
  for (let index = start; index < end; index += 1) {
    virtualItems.push({ index, offsetTop: index * rowHeight });
  }
  return {
    virtualItems,
    totalHeight: count * rowHeight,
    staticBreakEven: overscan * 4 + 8,
  };
}

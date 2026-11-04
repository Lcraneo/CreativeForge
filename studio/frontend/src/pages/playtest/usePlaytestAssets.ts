/**
 * 试玩舞台 V2 · 渐进式动作资源加载
 *
 * 元数据三段式（替代旧的"一次全量预载"）：
 * 1. core：idle + walk 立即请求——首帧可操作的最快路径；
 * 2. rest：run/jump 在 core 就绪后等浏览器空闲再请求；用户提前
 *    点击未加载的动作时立即发起（eager 旁路）；
 *
 * 图片解码逐张进行（无上限 Promise.all 会把五条条带的解码内存一次推
 * 满）；单动作失败只标记该动作并提供重试，不阻塞其他动作。切换角色时
 * （组件按 asset id 重挂载）cancelAll 中止在途请求并丢弃迟到结果。
 */
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../../api/client";
import type { PlaytestCharacter, PlaytestStrip } from "../../types";

export const BUILT_IN_ACTIONS = ["idle", "walk", "run", "jump"] as const;
const PRIORITY_ACTIONS = ["idle", "walk"];
const REST_ACTIONS = ["run", "jump"];

export type StripPhase = "pending" | "loading" | "ready" | "error";

/* ── 条带图片加载器（可独立测试：代际守卫 + 取消 + 重试） ─────────── */

export interface StripImageLoaderHandlers {
  onReady: (key: string, image: HTMLImageElement) => void;
  onError: (key: string) => void;
}

export class StripImageLoader {
  private generation = 0;
  private readonly inflight = new Map<string, HTMLImageElement>();
  /** key → 已就绪的条带 URL：URL 变化（AI 生成完成后 invalidate）会重新加载 */
  private readonly readyUrls = new Map<string, string>();

  constructor(private readonly handlers: StripImageLoaderHandlers) {}

  /** 加载条带图片；同 key 同 URL 在途/就绪时幂等跳过。失败后可再次 load = 重试 */
  load(key: string, url: string, priority: "high" | "low" = "low") {
    if (this.inflight.has(key) || this.readyUrls.get(key) === url) return;
    const generation = this.generation;
    const image = new window.Image();
    image.decoding = "async";
    image.setAttribute("fetchpriority", priority);
    this.inflight.set(key, image);
    image.onload = () => {
      this.inflight.delete(key);
      if (generation !== this.generation) return;
      this.readyUrls.set(key, url);
      this.handlers.onReady(key, image);
    };
    image.onerror = () => {
      this.inflight.delete(key);
      if (generation !== this.generation) return;
      this.handlers.onError(key);
    };
    image.src = url;
    if (typeof image.decode === "function") void image.decode().catch(() => undefined);
  }

  /** 取消全部在途请求并作废迟到回调（角色切换） */
  cancelAll() {
    this.generation += 1;
    for (const image of this.inflight.values()) image.src = "";
    this.inflight.clear();
    this.readyUrls.clear();
  }

  isReady(key: string, url?: string) {
    return url === undefined ? this.readyUrls.has(key) : this.readyUrls.get(key) === url;
  }
}

/* ── 元数据合并 ─────────────────────────────────────────────────── */

export interface PlaytestAssetMeta {
  /** 内置动作（固定顺序） */
  actions: string[];
  strips: Record<string, PlaytestStrip>;
  previews: Record<string, string>;
  source?: string;
  fps?: number;
  character?: PlaytestCharacter | null;
}

function mergeMeta(
  responses: Array<import("../../types").PlaytestPreviews | undefined>,
): PlaytestAssetMeta {
  const knownActions = new Set<string>();
  const strips: Record<string, PlaytestStrip> = {};
  const previews: Record<string, string> = {};
  let source: string | undefined;
  let fps: number | undefined;
  let character: PlaytestCharacter | null | undefined;
  for (const data of responses) {
    if (!data) continue;
    for (const action of data.actions ?? []) knownActions.add(action);
    Object.assign(strips, data.strips ?? {});
    Object.assign(previews, data.previews ?? {});
    if (data.source) source = data.source;
    if (data.fps) fps = data.fps;
    if (data.character !== undefined) character = data.character;
  }
  return {
    actions: BUILT_IN_ACTIONS.filter((action) => knownActions.has(action)),
    strips,
    previews,
    source,
    fps,
    character,
  };
}

/* ── 空闲门：requestIdleCallback 限时等待，eager promise 可提前放行 ── */

function idleWait(timeoutMs: number): Promise<void> {
  return new Promise((resolve) => {
    if (typeof requestIdleCallback === "function") {
      requestIdleCallback(() => resolve(), { timeout: timeoutMs });
    } else {
      setTimeout(resolve, 200);
    }
  });
}

/** eager 旁路的可控 Promise：resolve 句柄由 state 持有（避免在 useMemo 中写 ref） */
class Deferred {
  readonly promise: Promise<void>;
  resolve!: () => void;

  constructor() {
    this.promise = new Promise<void>((resolve) => {
      this.resolve = resolve;
    });
  }
}

/* ── Hook ───────────────────────────────────────────────────────── */

export function usePlaytestAssets(assetId: string | null) {
  // eager 旁路：用户点击未加载动作时立即放行 rest 请求（不等空闲）
  const [eagerGate] = useState(() => new Deferred());
  const requestedRef = useRef<Set<string>>(new Set());

  const core = useQuery({
    queryKey: ["playtest-previews-core", assetId],
    queryFn: () =>
      api.playtestPreviews(assetId!, { actions: PRIORITY_ACTIONS }),
    enabled: Boolean(assetId),
  });
  const rest = useQuery({
    queryKey: ["playtest-previews-rest", assetId],
    queryFn: async () => {
      await Promise.race([idleWait(1500), eagerGate]);
      return api.playtestPreviews(assetId!, { actions: REST_ACTIONS });
    },
    enabled: Boolean(assetId && core.data),
  });

  // AI 条带后台打包完成前先用兜底条带；短暂轮询后自动切回 AI（最多 8 次）
  const [aiPollAttempts, setAiPollAttempts] = useState(0);
  const deferredAi = [
    ...(core.data?.deferred_ai ?? []),
    ...(rest.data?.deferred_ai ?? []),
  ].join(",");
  useEffect(() => {
    if (!deferredAi || aiPollAttempts >= 8) return;
    const timer = setTimeout(() => {
      setAiPollAttempts((count) => count + 1);
      void core.refetch();
      if (rest.data) void rest.refetch();
    }, 3000);
    return () => clearTimeout(timer);
  }, [deferredAi, aiPollAttempts, core.refetch, rest.refetch, rest.data]);

  const meta = useMemo(
    () => mergeMeta([core.data, rest.data]),
    [core.data, rest.data],
  );

  /** 条带地址表：内置动作以 strips 优先（旧响应回落 previews）；自定义
   * 动作以 custom:<名称> 身份并入同一键空间（播放循环零特判） */
  const stripUrls = useMemo(() => {
    const urls: Record<string, string> = {};
    for (const name of meta.actions) {
      const strip = meta.strips[name];
      if (strip?.url) urls[name] = strip.url;
      else if (meta.previews[name]) urls[name] = meta.previews[name];
    }
    return urls;
  }, [meta]);

  const [images, setImages] = useState<Record<string, HTMLImageElement>>({});
  const [errors, setErrors] = useState<ReadonlySet<string>>(() => new Set());

  const loader = useMemo(
    () =>
      new StripImageLoader({
        onReady: (key, image) => setImages((prev) => ({ ...prev, [key]: image })),
        onError: (key) =>
          setErrors((prev) => {
            if (prev.has(key)) return prev;
            const next = new Set(prev);
            next.add(key);
            return next;
          }),
      }),
    [],
  );

  // 卸载时中止在途图片请求（切换角色 = 组件按 asset id 重挂载）
  useEffect(() => () => loader.cancelAll(), [loader]);

  // 元数据到位后逐张调度解码：优先动作 high，其余 low（渐进、无 Promise.all）
  useEffect(() => {
    for (const [key, url] of Object.entries(stripUrls)) {
      loader.load(key, url, PRIORITY_ACTIONS.includes(key) || requestedRef.current.has(key) ? "high" : "low");
    }
  }, [stripUrls, loader]);

  const retry = useCallback(
    (key: string) => {
      const url = stripUrls[key];
      if (!url) return;
      setErrors((prev) => {
        if (!prev.has(key)) return prev;
        const next = new Set(prev);
        next.delete(key);
        return next;
      });
      loader.load(key, url, "high");
    },
    [loader, stripUrls],
  );

  /** 点击尚未加载的动作：立即高优先级请求（触发 rest/custom 元数据 eager） */
  const requestActions = useCallback(
    (names: readonly string[]) => {
      for (const name of names) requestedRef.current.add(name);
      eagerGate.resolve();
    },
    [eagerGate],
  );

  const phase = useCallback(
    (key: string): StripPhase => {
      if (key in images) return "ready";
      if (errors.has(key)) return "error";
      return stripUrls[key] ? "loading" : "pending";
    },
    [images, errors, stripUrls],
  );

  const total = Object.keys(stripUrls).length;
  const readyCount = Object.keys(stripUrls).filter((key) => key in images).length;

  /** AI 动画批次完成后刷新全部元数据（条带 URL 随内容哈希变化） */
  const queryClient = useQueryClient();
  const invalidateAll = useCallback(() => {
    if (!assetId) return;
    void queryClient.invalidateQueries({ queryKey: ["playtest-previews-core", assetId] });
    void queryClient.invalidateQueries({ queryKey: ["playtest-previews-rest", assetId] });
  }, [assetId, queryClient]);

  return {
    meta,
    stripUrls,
    images,
    phase,
    retry,
    requestActions,
    invalidateAll,
    progress: {
      total,
      ready: readyCount,
      pct: total === 0 ? 0 : Math.round((readyCount / total) * 100),
    },
    metadataLoading: core.isLoading || rest.isPending,
    metadataError: core.error ?? rest.error,
  };
}

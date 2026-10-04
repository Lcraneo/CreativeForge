import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { ModelApiPanel } from "../components/ModelApiPanel";
import { useAssetLoader, useAssetStore } from "../stores/assetStore";
import { clearHidden, hidePerson, loadHidden, loadRecent, pushRecent, type PersonEntry } from "../lib/peopleHistory";
import {
  api,
  type AnimationResult,
  type CustomActionDetail,
  type CustomActionPreset,
  type MotionPhase,
  type PoseConfig,
} from "../api/client";
import {
  editorStateFor,
  resolveGeneration,
  selectionAfterRemoval,
  type ActionSource,
} from "../lib/actionSelection";
import { Badge, Button, Card, PageHeader, ScoreBar, Textarea, cx } from "../components/ui";
import StorageApiConfig from "../components/StorageApiConfig";
import { Icon } from "../components/icons";
import { toast } from "../stores/toastStore";
import { preloadImages } from "../lib/preload";

const ACTIONS = ["idle", "walk", "run", "attack", "jump"];
const ACTION_LABELS: Record<string, string> = {
  idle: "待机",
  walk: "行走",
  run: "奔跑",
  attack: "攻击",
  jump: "跳跃",
  sequence: "序列帧",
};
const SIZES = [256, 384, 512, 768];

const POSE_PARAMS: Array<{
  key: keyof PoseConfig;
  label: string;
  min: number;
  max: number;
  step: number;
}> = [
  { key: "bob", label: "上下起伏", min: 0, max: 2, step: 0.05 },
  { key: "stride", label: "步幅 / 腿部摆动", min: 0, max: 2, step: 0.05 },
  { key: "arm", label: "摆臂幅度", min: 0, max: 2, step: 0.05 },
  { key: "lift", label: "抬脚高度", min: 0, max: 2, step: 0.05 },
  { key: "lean", label: "身体前倾 (°)", min: -15, max: 30, step: 1 },
  { key: "lag", label: "手臂滞后 (重叠)", min: 0, max: 1.2, step: 0.05 },
  { key: "cycles", label: "循环周期数", min: 0.25, max: 3, step: 0.25 },
  { key: "turn", label: "转身幅度 (°)", min: 0, max: 180, step: 5 },
  // 弯腰包络（方案3，opt-in）：每循环一次「弯下→直起」，riganim 消费为
  // 上身俯身旋转——鞠躬/点头/欠身类礼仪动作的骨骼链表达
  { key: "bow", label: "弯腰幅度 (°)", min: 0, max: 90, step: 5 },
];

const DEFAULT_POSE_CONFIG: PoseConfig = {
  bob: 1,
  stride: 1,
  arm: 1,
  lift: 1,
  lean: 0,
  lag: 0.45,
  cycles: 1,
  turn: 0,
  bow: 0,
};

/** 后端 epoch 秒 → 本地「MM-DD HH:mm」；缺省给 —（卡片与详情弹窗的时间元数据） */
const fmtTime = (value?: number) =>
  value
    ? new Date(value * 1000).toLocaleString("zh-CN", {
        month: "2-digit",
        day: "2-digit",
        hour: "2-digit",
        minute: "2-digit",
      })
    : "—";

/** 视频任务阶段中文标签（生成任务化的进度条文案） */
const TASK_STAGE_LABELS: Record<string, string> = {
  queued: "排队中",
  prompt: "准备提示词与源图",
  video: "AI 视频生成中（约 60~90 秒）",
  sampling: "抽帧与循环接缝处理",
  composing: "合成动画",
  done: "完成",
};
/** 刷新恢复：进行中视频任务的 localStorage 键（id + 来源 kind） */
const VIDEO_TASK_KEY = "cf:animation-video-task";

interface SeqFrame {
  name: string;
  dataUrl: string;
}

export default function AnimationStudio() {
  const asset = useAssetLoader();
  const setAsset = useAssetStore((state) => state.set);
  // 历史人物（P1 体验）：数据源为后端生成历史（每个生成过的人物一行），
  // localStorage 只记录「隐藏清单」与「最近使用排序」——后端数据不受影响
  const historyQuery = useQuery({
    queryKey: ["animation-people"],
    queryFn: () => api.listHistory({ limit: 30 }),
  });
  const [hiddenIds, setHiddenIds] = useState<string[]>(() => loadHidden());

  // 展示列表：后端最近生成 → 按资产去重（每人取最近一条）→ 过滤已隐藏 → 前 12
  const people: PersonEntry[] = useMemo(() => {
    const seen = new Set<string>();
    const out: PersonEntry[] = [];
    for (const record of historyQuery.data?.records ?? []) {
      const assetId = record.asset_id;
      if (!assetId || seen.has(assetId) || hiddenIds.includes(assetId)) continue;
      seen.add(assetId);
      out.push({
        asset_id: assetId,
        name: record.name || record.goal || "未命名人物",
        image_url: record.image?.url ?? record.asset?.image?.url,
        selected_at: record.finished_at || record.created_at || 0,
      });
      if (out.length >= 12) break;
    }
    // 最近使用过的人物置顶（载入/生成过的排前面）
    out.sort((a, b) => {
      const ra = loadRecent().find((p) => p.asset_id === a.asset_id)?.selected_at ?? 0;
      const rb = loadRecent().find((p) => p.asset_id === b.asset_id)?.selected_at ?? 0;
      return rb - ra;
    });
    return out;
  }, [historyQuery.data, hiddenIds]);
  const [showPeople, setShowPeople] = useState(false);

  // 载入历史人物（事件处理器；命名避开 use 前缀——非 Hook，react-hooks 规则按
  // 名字识别会误报"回调内调用 Hook"）
  function loadPerson(entry: PersonEntry) {
    api
      .getAsset(entry.asset_id)
      .then((loaded) => {
        setAsset(loaded);
        pushRecent({
          asset_id: loaded.id,
          name: loaded.name,
          image_url: loaded.image?.url ?? entry.image_url,
        });
        toast({ tone: "success", title: `已载入「${entry.name}」`, description: "生成与动作编辑将使用该人物" });
      })
      .catch((cause) =>
        toast({ tone: "danger", title: "载入失败", description: String(cause).slice(0, 140) }),
      );
  }

  const [mode, setMode] = useState<"smart" | "sequence" | "cloud">("smart");
  const [skeletal, setSkeletal] = useState(true);
  // V3 网格变形：膝/肘皮肤化开关（仅骨骼模式生效；关闭=刚体分区 v5/v6 行为）
  const [meshSkin, setMeshSkin] = useState(true);
  // V3 次级运动：发层摆动开关（首次开启对该资产花约 0.3 元提取发层，之后缓存免费）
  const [hairMotion, setHairMotion] = useState(false);
  const rigCheck = useQuery({
    queryKey: ["rig-check", asset?.id],
    queryFn: () => api.rigCheck(asset?.id ?? undefined),
    enabled: Boolean(asset?.id),
    staleTime: 60000,
  });
  const [useVideo, setUseVideo] = useState(false);
  // V2 双档：定稿档（plus）开关——草稿确认动作后勾选出定稿片
  const [finalQuality, setFinalQuality] = useState(false);
  // V3.5 装备/服装识别：看图认出武器/服装并贴合动作（骨骼链姿态自适应 +
  // i2v 提示词上下文/武器保持子句）；按源图缓存，同一角色终身只识别一次
  const [equipmentAware, setEquipmentAware] = useState(true);
  const [view, setView] = useState("side");
  // ── 动作选择(基础/自定义彻底分离)────────────────────────────
  // 基础动作(内置 5 种)与自定义动作(用户保存)是两个独立来源,
  // selected 判别联合保证任意时刻至多一个活跃动作、无双选中/双空态;
  // 生成参数由 resolveGeneration 按来源解析,两条路径互不掺和。
  const [selected, setSelected] = useState<ActionSource>({ kind: "base", name: "walk" });
  const [busySource, setBusySource] = useState<"base" | "custom" | null>(null);
  const [fps, setFps] = useState(12);
  const [duration, setDuration] = useState(1.0);
  const [size, setSize] = useState(384);
  const [result, setResult] = useState<AnimationResult | null>(null);
  const [upload, setUpload] = useState<{ name: string; dataUrl: string } | null>(null);
  const [seqFrames, setSeqFrames] = useState<SeqFrame[]>([]);
  const seqFileRef = useRef<HTMLInputElement>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [preview, setPreview] = useState(false);
  const [previewLoading, setPreviewLoading] = useState(false);
  const [previewError, setPreviewError] = useState(false);
  const [mainError, setMainError] = useState(false);
  // mp4 直通预览失败时回退 GIF（浏览器解码器差异/文件缺失兜底）。
  // 新结果到来时在渲染期重置（React 认可的派生状态调整模式——react-hooks
  // 门禁禁止在 effect 体内直接 setState，首版 setVideoFailed(false) 被拦）
  const [videoFailedRaw, setVideoFailedRaw] = useState(false);
  const [videoFailedFor, setVideoFailedFor] = useState<string | null>(null);
  const videoUrl = result?.urls.video ?? null;
  if (videoFailedFor !== videoUrl) {
    setVideoFailedFor(videoUrl);
    setVideoFailedRaw(false);
  }
  const videoFailed = videoFailedRaw && videoUrl !== null;
  const fileRef = useRef<HTMLInputElement>(null);

  // -- 动作编辑器状态 -----------------------------------------------------
  const [editorAction, setEditorAction] = useState("walk");
  const [editorView, setEditorView] = useState("side");
  const [poseConfig, setPoseConfig] = useState<PoseConfig>(DEFAULT_POSE_CONFIG);
  // 自然语言自定义动作（P1 体验）：描述 → 润色 → 结构化参数套用编辑器
  const [nlText, setNlText] = useState("");
  const [nlBusy, setNlBusy] = useState<"enhance" | "apply" | null>(null);
  const nlPast = useRef<string[]>([]);
  const nlFuture = useRef<string[]>([]);

  function nlChange(value: string) {
    nlPast.current.push(nlText);
    if (nlPast.current.length > 50) nlPast.current.shift();
    nlFuture.current = [];
    setNlText(value);
  }
  function nlUndo() {
    const previous = nlPast.current.pop();
    if (previous === undefined) return;
    nlFuture.current.push(nlText);
    setNlText(previous);
  }
  function nlRedo() {
    const next = nlFuture.current.pop();
    if (next === undefined) return;
    nlPast.current.push(nlText);
    setNlText(next);
  }
  async function nlEnhance() {
    const text = nlText.trim();
    if (!text || nlBusy) return;
    setNlBusy("enhance");
    try {
      const result = await api.enhanceActionText(text);
      nlChange(result.text);
      toast({ tone: "success", title: "文案已增强", description: "润色后的动作说明已填入" });
    } catch (cause) {
      toast({ tone: "danger", title: "文案增强失败", description: String(cause).slice(0, 160) });
    } finally {
      setNlBusy(null);
    }
  }
  async function nlApply() {
    const text = nlText.trim();
    if (!text || nlBusy) return;
    setNlBusy("apply");
    try {
      const action = await api.interpretActionText(text, asset?.id);
      setEditorAction(action.base_action);
      setEditorView(action.view as "front" | "side");
      setPoseConfig({ ...DEFAULT_POSE_CONFIG, ...action.pose_config });
      setPhase(0);
      setPresetName(action.label);
      // 词表外动作标记：常驻提示条引导切换 AI 视频驱动（下次解读无标记时清除）
      setSuggestVideoAction(
        action.suggest_video ? action.label || text.slice(0, 8) : null,
      );
      toast({
        tone: "success",
        title: `已套用动作「${action.label}」`,
        description: action.suggest_video
          ? "该动作超出骨骼引擎词表——建议用「AI 视频驱动」生成（见上方提示条）"
          : `${action.base_action} · ${action.view} · 滑杆参数已更新，可直接生成或微调后保存`,
      });
    } catch (cause) {
      toast({ tone: "danger", title: "动作解读失败", description: String(cause).slice(0, 160) });
    } finally {
      setNlBusy(null);
    }
  }
  const [phase, setPhase] = useState(0);
  const [frameUrl, setFrameUrl] = useState<string | null>(null);
  const [previewWarn, setPreviewWarn] = useState<string | null>(null);
  const [playing, setPlaying] = useState(false);
  const [presets, setPresets] = useState<CustomActionPreset[]>([]);
  const [presetName, setPresetName] = useState("");
  const [editorBusy, setEditorBusy] = useState(false);
  // 自定义动作编辑/详情（P2 体验）：编辑复用创作台（保存走覆盖链路，改名时
  // 后端迁移元数据），详情弹窗展示完整描述、参数与修改历史（可追溯）
  const [editingName, setEditingName] = useState<string | null>(null);
  const [detailName, setDetailName] = useState<string | null>(null);
  const [detail, setDetail] = useState<CustomActionDetail | null>(null);
  const [detailBusy, setDetailBusy] = useState(false);
  // 解读出的词表外动作（鞠躬/挥手等一次性手势）：常驻提示条 + 一键切换
  // AI 视频驱动——骨骼链只能给近似姿态，用户该在出片前就知道走哪条链
  const [suggestVideoAction, setSuggestVideoAction] = useState<string | null>(null);
  // 生成任务化：AI 视频链（60~90s）走异步任务轮询——阶段进度条 + 刷新恢复
  const [videoTaskId, setVideoTaskId] = useState<string | null>(null);
  const [videoTaskStage, setVideoTaskStage] = useState<{ stage: string; progress: number }>({
    stage: "queued",
    progress: 0,
  });

  // 资产原图:本地端点优先——后端 /api/assets/{id}/image.png 会做本地解析
  // 与缓存,不依赖远端签名 URL;OSS 直链只作本地服务不可用时的兜底
  const assetImage =
    (asset?.id ? `/api/assets/${asset.id}/image.png?view=front&size=512` : undefined) ||
    (asset as { image?: { url?: string } } | null)?.image?.url ||
    (asset?.source as { ai_image?: { url?: string } } | undefined)?.ai_image?.url;

  const generate = useCallback(
    async (source: ActionSource) => {
      if (busy) return;
      // 参数严格按来源解析:基础动作=内置默认(不带 pose_config),
      // 自定义动作=preset 原样——选中项被删等异常时拒绝生成
      const plan = resolveGeneration(source, presets, view);
      if (!plan) {
        setError("所选动作不存在,请重新选择");
        return;
      }
      setBusy(true);
      setBusySource(source.kind);
      setError(null);
      setMainError(false);
      try {
        const payload: Parameters<typeof api.createAnimation>[0] = {
          action: plan.action,
          fps,
          duration,
          size,
          skeletal,
          view: plan.view,
          pose_config: plan.pose_config,
          deform: skeletal ? (meshSkin ? "mesh" : "rigid") : undefined,
          secondary_motion: skeletal ? hairMotion : false,
          equipment_aware: equipmentAware,
          use_video: useVideo,
          final_quality: useVideo ? finalQuality : false,
        };
        if (upload) {
          payload.image = upload.dataUrl.split(",")[1];
        } else if (asset?.id) {
          payload.asset_id = asset.id;
        }
        // 自定义动作的描述随请求送达 i2v 链（词表外动作的表达通道）；
        // 基础动作不带——内置词表路径保持原样
        if (source.kind === "custom") {
          payload.action_description =
            presets.find((preset) => preset.name === source.name)?.description ?? "";
        }
        // 生成任务化：AI 视频链（60~90s 大头）走异步任务——立即拿 task_id
        // 轮询阶段进度，刷新后凭 localStorage 续接；骨骼/序列帧秒级完成维持同步
        if (useVideo) {
          try {
            const started = await api.startVideoTask(payload);
            window.localStorage.setItem(
              VIDEO_TASK_KEY,
              JSON.stringify({ id: started.task_id, kind: source.kind }),
            );
            setVideoTaskStage({
              stage: started.snapshot?.stage ?? "queued",
              progress: started.snapshot?.progress ?? 0,
            });
            setVideoTaskId(started.task_id);
          } catch (err) {
            setError(err instanceof Error ? err.message : String(err));
            setBusy(false);
            setBusySource(null);
          }
          return;
        }
        const animationResult = await api.createAnimation(payload);
        // 自动记录当前人物到历史（下次直接载入）
        if (asset?.id) {
          pushRecent({ asset_id: asset.id, name: asset.name, image_url: asset.image?.url });
        }
        // 生成成功后清掉编辑器相位帧：展示区 frameUrl 优先级高于 result，
        // 不清会导致画布停在静态预览帧、动画 GIF 永远不显示（"无法播放"）。
        // 用户下次拖时间轴/调滑杆时相位帧自动恢复。
        setFrameUrl((oldUrl) => {
          if (oldUrl) URL.revokeObjectURL(oldUrl);
          return null;
        });
        setPlaying(false);
        setResult(animationResult);
      } catch (err) {
        setError(err instanceof Error ? err.message : String(err));
      } finally {
        setBusy(false);
        setBusySource(null);
      }
    },
    [busy, presets, view, fps, duration, size, upload, asset?.id, skeletal, meshSkin, hairMotion, equipmentAware, useVideo, finalQuality],
  );

  // 预载门控：新结果一到就把 gif/sheet/逐帧全部预载 + decode，
  // 用户往下滚动到逐帧网格/播放时不再有首次解码尖峰
  // （mp4 回退标记的重置在上方渲染期完成——react-hooks 禁止 effect 内直接 setState）
  useEffect(() => {
    if (!result) return;
    void preloadImages(
      [result.urls.gif, result.urls.sheet, ...(result.frame_urls ?? [])],
      0,
    );
  }, [result]);

  // 视频任务轮询：阶段进度 → 终态收尾（done 与同步成功同款：清相位帧/
  // 停播放/记最近人物；failed 报错清态）。轮询单次失败不终止（网络抖动，
  // 下个周期重试）；asset?.id 变化重挂轮询对同一 task_id 无害
  useEffect(() => {
    if (!videoTaskId) return;
    let alive = true;
    const poll = async () => {
      try {
        const snap = await api.getVideoTask(videoTaskId);
        if (!alive) return;
        if (snap.status === "running") {
          setVideoTaskStage({ stage: snap.stage, progress: snap.progress });
          return;
        }
        window.localStorage.removeItem(VIDEO_TASK_KEY);
        setVideoTaskId(null);
        setBusy(false);
        setBusySource(null);
        if (snap.status === "done" && snap.result) {
          setFrameUrl((oldUrl) => {
            if (oldUrl) URL.revokeObjectURL(oldUrl);
            return null;
          });
          setPlaying(false);
          setResult(snap.result);
          setError(null);
          if (asset?.id) {
            pushRecent({ asset_id: asset.id, name: asset.name, image_url: asset.image?.url });
          }
          toast({
            tone: "success",
            title: "AI 视频生成完成",
            description: snap.result.qa
              ? snap.result.qa.grade === "pass"
                ? "自动质检通过，循环接缝已处理"
                : snap.result.qa.grade === "warn"
                  ? "质检关注：详情见结果徽章"
                  : "质检异常：建议更换描述或重试"
              : "循环接缝已自动处理",
          });
        } else {
          setError(snap.error || "AI 视频生成失败");
        }
      } catch {
        /* 单次轮询失败不终止——下个周期重试 */
      }
    };
    void poll();
    const timer = setInterval(poll, 2000);
    return () => {
      alive = false;
      clearInterval(timer);
    };
  }, [videoTaskId, asset?.id]);

  // 刷新恢复：上次未收尾的视频任务凭 localStorage 续接——running 恢复
  // busy 态并续轮询、done 直接展示结果、failed/失效静默清除
  useEffect(() => {
    let saved: { id: string; kind: "base" | "custom" } | null = null;
    try {
      saved = JSON.parse(window.localStorage.getItem(VIDEO_TASK_KEY) || "null");
    } catch {
      saved = null;
    }
    if (!saved?.id) return;
    const ref = saved;
    let alive = true;
    api
      .getVideoTask(ref.id)
      .then((snap) => {
        if (!alive) return;
        if (snap.status === "running") {
          setBusy(true);
          setBusySource(ref.kind);
          setVideoTaskStage({ stage: snap.stage, progress: snap.progress });
          setVideoTaskId(ref.id);
          toast({
            tone: "info",
            title: "检测到进行中的生成任务",
            description: "已恢复进度显示，完成后自动展示结果",
          });
        } else if (snap.status === "done" && snap.result) {
          window.localStorage.removeItem(VIDEO_TASK_KEY);
          setResult(snap.result);
        } else {
          window.localStorage.removeItem(VIDEO_TASK_KEY);
        }
      })
      .catch(() => window.localStorage.removeItem(VIDEO_TASK_KEY));
    return () => {
      alive = false;
    };
  }, []);

  // -- 编辑器：相位预览（防抖）、播放循环、预设列表 ------------------------
  useEffect(() => {
    if (mode !== "smart") return;
    let alive = true;
    const timer = setTimeout(() => {
      api
        .previewAnimationFrame({
          action: editorAction,
          view: editorView,
          phase,
          size: 384,
          pose_config: poseConfig,
          skeletal: true,
          asset_id: asset?.id,
          image: upload?.dataUrl?.split(",")[1],
        })
        .then((url) => {
          if (!alive) {
            URL.revokeObjectURL(url);
            return;
          }
          setPreviewWarn(null);
          setFrameUrl((old) => {
            if (old) URL.revokeObjectURL(old);
            return url;
          });
        })
        .catch((cause) => {
          if (!alive) return;
          // 相位帧渲染失败(最常见:资产原图缺失/远端失效 409)不再静默,
          // 画布退回展示资产原图,并给出可见原因
          const text = String((cause as Error)?.message ?? cause);
          const detail = /"detail"\s*:\s*"([^"]+)"/.exec(text)?.[1] ?? text.replace(/^\d+:\s*/, "");
          setPreviewWarn(detail.slice(0, 140));
          setFrameUrl((old) => {
            if (old) URL.revokeObjectURL(old);
            return null;
          });
        });
    }, 120);
    return () => {
      alive = false;
      clearTimeout(timer);
    };
  }, [mode, editorAction, editorView, phase, poseConfig, size, asset?.id, upload]);

  useEffect(() => {
    if (mode !== "smart" || !playing) return;
    const timer = setInterval(() => setPhase((p) => (p + 1 / 12) % 1), 90);
    return () => clearInterval(timer);
  }, [mode, playing]);

  useEffect(() => {
    if (mode !== "smart") return;
    api
      .listCustomActions()
      .then((r) => setPresets(r.actions))
      .catch(() => {});
  }, [mode]);

  // ── 动作选择:基础/自定义互斥,编辑器(预览台)跟随载入 ──────────────
  // 选中一侧自动取消另一侧——基础区与自定义区的按钮/徽章状态由各自的
  // selected.kind 判定,不会互相干扰;编辑器滑杆只影响预览与「保存为自定义」。
  const selectBase = useCallback(
    (name: string) => {
      const source: ActionSource = { kind: "base", name };
      const state = editorStateFor(source, presets, DEFAULT_POSE_CONFIG);
      if (!state) return;
      setSelected(source);
      setEditorAction(state.action);
      if (state.view) setEditorView(state.view);
      setPoseConfig(state.pose_config);
      setPhase(0);
    },
    [presets],
  );

  const selectCustom = useCallback(
    (name: string, list?: Array<{ name: string; action: string; view: string; pose_config: PoseConfig }>) => {
      const source: ActionSource = { kind: "custom", name };
      const state = editorStateFor(source, list ?? presets, DEFAULT_POSE_CONFIG);
      if (!state) return;
      setSelected(source);
      setEditorAction(state.action);
      if (state.view) setEditorView(state.view);
      setPoseConfig(state.pose_config);
      setPhase(0);
    },
    [presets],
  );

  const savePreset = async () => {
    if (!presetName.trim() || editorBusy) return;
    setEditorBusy(true);
    try {
      // 编辑态：original_name 指向被编辑的旧动作——同名=就地覆盖（后端保留
      // 创建时间/版本数/历史），改名=整卡迁移元数据；描述取自然语言框原文
      await api.saveCustomAction({
        name: presetName.trim(),
        action: editorAction,
        view: editorView,
        pose_config: poseConfig,
        description: nlText.trim(),
        ...(editingName ? { original_name: editingName } : {}),
      });
      const r = await api.listCustomActions();
      setPresets(r.actions);
      const savedName = presetName.trim();
      // 保存即选中:新动作立刻成为当前活跃动作,可在自定义动作区直接生成
      if (r.actions.some((p) => p.name === savedName)) {
        selectCustom(savedName, r.actions);
      }
      const wasEditing = editingName !== null;
      setPresetName("");
      setEditingName(null);
      setError(null);
      toast({
        tone: "success",
        title: wasEditing
          ? `自定义动作「${savedName}」已保存修改并选中`
          : `自定义动作「${savedName}」已保存并选中`,
        description: wasEditing
          ? "创建时间与修改历史已保留，可在动作库点「详情」查看版本记录"
          : "在自定义动作区点击「用此动作生成」即可按该动作出片",
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setEditorBusy(false);
    }
  };

  // 编辑已有动作：整卡载入创作台（名称/描述/基底/视角/滑杆参数），保存时
  // 走覆盖链路——不新建记录，创建时间等元数据由后端保留
  const startEdit = (preset: CustomActionPreset) => {
    setEditingName(preset.name);
    setPresetName(preset.name);
    setEditorAction(preset.action);
    setEditorView(preset.view);
    setPoseConfig(preset.pose_config);
    setNlText(preset.description ?? "");
    // 旧版动作（无 revision 字段=描述存档功能上线前创建）载入编辑时提醒
    // 补写描述——否则用户会以为描述又被弄丢了
    if (!preset.description && !preset.revision) {
      toast({
        tone: "info",
        title: `「${preset.name}」创建于描述存档功能之前`,
        description: "当时的描述未能保存——在自然语言框补写后点「保存修改」即可归档",
      });
    }
  };

  const cancelEdit = () => {
    setEditingName(null);
    setPresetName("");
  };

  // 详情弹窗：列表接口不带修改历史，单独拉完整记录（含历史快照）
  const openDetail = async (name: string) => {
    setDetailName(name);
    setDetail(null);
    setDetailBusy(true);
    try {
      setDetail(await api.getCustomAction(name));
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
      setDetailName(null);
    } finally {
      setDetailBusy(false);
    }
  };

  const removePreset = async (name: string) => {
    try {
      await api.deleteCustomAction(name);
      setPresets((prev) => prev.filter((p) => p.name !== name));
      // 删除的是当前选中动作时,回落到默认基础动作,不留悬空选中态
      const fallback = selectionAfterRemoval(name, selected);
      if (fallback) setSelected(fallback);
      // 删除的是正在编辑/查看详情的动作时,收起对应面板,不留悬空引用
      if (editingName === name) {
        setEditingName(null);
        setPresetName("");
      }
      if (detailName === name) setDetailName(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  };

  const openPreview = () => {
    if (!result) return;
    setPreviewError(false);
    setPreviewLoading(true);
    setPreview(true);
  };

  const onFile = (file?: File) => {
    if (!file) return;
    const reader = new FileReader();
    reader.onload = () => setUpload({ name: file.name, dataUrl: String(reader.result) });
    reader.readAsDataURL(file);
  };

  const onSeqFiles = (files: FileList | null) => {
    if (!files || files.length === 0) return;
    const collator = new Intl.Collator(undefined, { numeric: true, sensitivity: "base" });
    const incoming = Array.from(files)
      .sort((a, b) => collator.compare(a.name, b.name))
      .map(
        (file) =>
          new Promise<SeqFrame>((resolve, reject) => {
            const reader = new FileReader();
            reader.onload = () => resolve({ name: file.name, dataUrl: String(reader.result) });
            reader.onerror = () => reject(reader.error);
            reader.readAsDataURL(file);
          }),
      );
    Promise.all(incoming)
      .then((frames) => setSeqFrames((prev) => [...prev, ...frames].slice(0, 60)))
      .catch(() => setError("读取序列帧图片失败，请重试"));
  };

  const composeSequence = useCallback(async () => {
    if (seqFrames.length < 2 || busy) return;
    setBusy(true);
    setError(null);
    setMainError(false);
    try {
      setResult(
        await api.createAnimationSequence({
          frames: seqFrames.map((frame) => frame.dataUrl),
          fps,
          size,
        }),
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }, [seqFrames, fps, size, busy]);

  const quality = asset?.quality?.animation;
  const rootTrack = asset?.animation?.motion?.root_track ?? [];
  const corrections = asset?.animation?.motion?.corrections ?? [];
  const trackPath = rootTrack
    .map((point, index) => {
      const x = (index / Math.max(1, rootTrack.length - 1)) * 640;
      const y = 45 - point.dx * 6;
      return `${index === 0 ? "M" : "L"}${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .join(" ");

  const isLocomotion = editorAction === "walk" || editorAction === "run";

  // 编辑器滑杆只影响预览与「保存为自定义」;与选中动作的保存参数不一致时
  // 明确提示,避免"预览是 A、生成是 B"的困惑
  const editorDirty = useMemo(() => {
    const plan = editorStateFor(selected, presets, DEFAULT_POSE_CONFIG);
    if (!plan) return false;
    return POSE_PARAMS.some(
      (param) =>
        Math.abs((poseConfig[param.key] ?? 0) - (plan.pose_config[param.key] ?? 0)) > 1e-6,
    );
  }, [selected, presets, poseConfig]);

  return (
    <div className="mx-auto flex w-full max-w-[1440px] flex-col gap-5 px-4 py-5 md:px-6">
      <PageHeader
        overline="Animation Studio"
        title="动画工作台"
        description="全身骨骼关节动画（含侧视横版步态）· 源图变形 · 序列帧合成 · 动作自定义编辑"
        actions={
          <>
            {result && <Badge tone="falign">{ACTION_LABELS[result.action] ?? result.action}</Badge>}
            {result && <Badge tone="neutral">{result.frame_count} frames</Badge>}
            {result && <Badge tone="neutral">{result.fps} fps</Badge>}
            {result?.motion_blend && <Badge tone="neutral">帧混合</Badge>}
            {result?.qa && (
              <span
                title={(result.qa.issues ?? []).join("；") || "量化质检全部通过"}
                className="inline-flex"
              >
                <Badge
                  tone={
                    result.qa.grade === "pass"
                      ? "success"
                      : result.qa.grade === "warn"
                        ? "warning"
                        : "danger"
                  }
                >
                  {result.qa.grade === "pass"
                    ? "质检通过"
                    : result.qa.grade === "warn"
                      ? "质检关注"
                      : "质检异常"}
                </Badge>
              </span>
            )}
            {result?.equipment?.labels?.slice(0, 4).map((label) => (
              <Badge key={label} tone="primary">
                {label}
              </Badge>
            ))}
            {result && (
              <Badge tone={result.consistency.passed ? "success" : "warning"}>
                一致性 {(result.consistency.overall * 100).toFixed(0)}%
              </Badge>
            )}
          </>
        }
      />

      <div className="grid grid-cols-12 gap-5">
        <div className="col-span-12 flex flex-col gap-5 xl:col-span-8">
          <Card
            title="动作预览 Motion Preview"
            icon="play"
            iconClassName="text-falign"
            right={
              result ? (
                <div className="flex items-center gap-3">
                  <button
                    onClick={openPreview}
                    className="rounded-md border border-line-subtle px-2.5 py-1 text-[12px] text-ink-2 hover:bg-surface-2"
                  >
                    在线预览
                  </button>
                  <a
                    className="text-[12px] text-ink-3 underline decoration-line"
                    href={result.urls.gif}
                    download
                  >
                    下载 GIF
                  </a>
                  {result.urls.video && (
                    <a
                      className="text-[12px] text-ink-3 underline decoration-line"
                      href={result.urls.video}
                      download
                    >
                      下载 MP4
                    </a>
                  )}
                </div>
              ) : undefined
            }
          >
            <div className="flex h-[320px] items-center justify-center rounded-[10px] border border-line-subtle bg-[radial-gradient(300px_160px_at_50%_40%,rgba(124,92,196,.10),transparent_70%),#f1efe9]">
              {frameUrl ? (
                <img
                  src={frameUrl}
                  alt="pose preview"
                  className="max-h-[300px] max-w-full object-contain"
                />
              ) : result ? (
                mainError ? (
                  <div className="px-6 text-center text-sm text-danger">
                    动画预览加载失败。可点击「在线预览」或「下载 GIF」查看。
                  </div>
                ) : result.urls.video && !videoFailed ? (
                  /* i2v 直通 mp4：720p/24fps 原速原画质；加载失败回退 GIF */
                  <video
                    src={result.urls.video}
                    autoPlay
                    loop
                    muted
                    playsInline
                    onError={() => setVideoFailedRaw(true)}
                    className="max-h-[300px] max-w-full object-contain"
                  />
                ) : (
                  <img
                    src={result.urls.gif}
                    alt="animation preview"
                    onError={() => setMainError(true)}
                    className="max-h-[300px] max-w-full object-contain"
                  />
                )
              ) : upload ? (
                <img
                  src={upload.dataUrl}
                  alt="source"
                  className="max-h-[300px] max-w-full object-contain"
                />
              ) : assetImage ? (
                <img
                  src={assetImage}
                  alt="source"
                  className="max-h-[300px] max-w-full object-contain"
                />
              ) : (
                <div className="text-sm text-ink-3">生成资产，或上传一张图片作为动画源。</div>
              )}
            </div>
            {previewWarn && (
              <div className="mt-2 rounded-md border border-line-subtle bg-surface-2 px-3 py-1.5 text-[12px] text-danger">
                相位预览不可用:{previewWarn}
              </div>
            )}
            <div className="mt-2.5 flex flex-wrap items-center gap-3 text-[11px] text-ink-3">
              <span>
                源：
                {mode === "sequence"
                    ? `序列帧 · ${seqFrames.length} 张`
                    : upload
                      ? `上传 · ${upload.name}`
                      : asset
                        ? `资产 · ${asset.name ?? asset.id}`
                        : "—"}
              </span>
              {result && (
                <span>
                  输出 {result.size}px · {result.duration}s · 循环
                  {result.urls.video
                    ? ` · MP4 ${result.video_spec?.width ?? "?"}×${
                        result.video_spec?.height ?? "?"
                      }@${
                        result.video_spec ? Math.round(result.video_spec.fps) : "?"
                      }`
                    : ""}
                </span>
              )}
            </div>
            {videoTaskId && (
              <div className="mt-2.5">
                <div className="mb-1 flex items-center justify-between text-[11px] text-ink-3">
                  <span>{TASK_STAGE_LABELS[videoTaskStage.stage] ?? videoTaskStage.stage}</span>
                  <span className="font-mono">{Math.round(videoTaskStage.progress)}%</span>
                </div>
                <div className="h-1.5 overflow-hidden rounded-full bg-surface-2">
                  <div
                    className="h-full rounded-full bg-primary transition-all duration-700"
                    style={{
                      width: `${Math.max(4, Math.min(100, videoTaskStage.progress))}%`,
                    }}
                  />
                </div>
              </div>
            )}
          </Card>

          <Card
            title={mode === "cloud" ? "云存储 API 配置" : "生成参数 Animation Settings"}
            icon={mode === "cloud" ? "package" : "panel"}
            iconClassName={mode === "cloud" ? "text-accent" : "text-falign"}
          >
            <div className="mb-4 flex items-center gap-3">
              <div className="flex overflow-hidden rounded-lg border border-line-subtle">
                {(
                  [
                    ["smart", "创作工作区"],
                    ["sequence", "序列帧导入"],
                    ["cloud", "云存储"],
                  ] as const
                ).map(([value, label]) => (
                  <button
                    key={value}
                    onClick={() => setMode(value)}
                    className={cx(
                      "px-3 py-1.5 text-[12px] transition-colors",
                      mode === value ? "bg-primary text-white" : "text-ink-2 hover:bg-surface-2",
                    )}
                  >
                    {label}
                  </button>
                ))}
              </div>
              <span className="text-[11px] text-ink-4">
                {mode === "smart"
                  ? "智能生成 + 动作精修一体：调参数、拖时间轴逐帧预览真实人物，可保存为自定义动作复用"
                  : mode === "sequence"
                      ? "标准序列帧工作流：按文件名顺序导入帧图，直接合成为循环动画"
                      : "六厂商对象存储 API 配置：凭证加密存储、脱敏展示、连通性测试"}
              </span>
            </div>

            {mode === "cloud" && <StorageApiConfig />}

            {mode === "smart" && (
              <div className="flex flex-col gap-4">
                <div className="rounded-lg border border-line-subtle bg-surface-2/30 p-3">
                  <div className="mb-2 flex items-center justify-between">
                    <span className="text-[11px] uppercase tracking-widest text-ink-4">
                      历史人物 · 点击载入到当前工作区
                    </span>
                    {people.length > 0 && (
                      <button
                        onClick={() => {
                          setHiddenIds(clearHidden());
                          toast({ tone: "info", title: "历史人物记录已清空" });
                        }}
                        className="text-[10.5px] text-ink-4 underline-offset-2 hover:text-danger hover:underline"
                        title="仅从本列表隐藏，生成历史不受影响"
                      >
                        全部隐藏
                      </button>
                    )}
                  </div>
                  {people.length === 0 ? (
                    <p className="text-[11.5px] text-ink-4">
                      暂无历史选择——生成动画或点击人物后自动记录，最近 12 个跨会话保留。
                    </p>
                  ) : (
                    <div className="flex flex-wrap gap-2.5">
                      {people.map((person) => (
                        <div
                          key={person.asset_id}
                          className={cx(
                            "group relative flex items-center gap-2 rounded-lg border py-1.5 pl-1.5 pr-2.5 transition-colors",
                            asset?.id === person.asset_id
                              ? "border-primary/60 bg-primary-tint/40"
                              : "border-line-subtle bg-surface-1 hover:border-line",
                          )}
                        >
                          <button
                            onClick={() => loadPerson(person)}
                            title={`载入「${person.name}」`}
                            className="flex items-center gap-2 text-left"
                          >
                            {person.image_url ? (
                              <img
                                src={person.image_url}
                                alt={person.name}
                                loading="lazy"
                                className="h-9 w-9 rounded-md border border-line-subtle bg-[#f1efe9] object-contain"
                              />
                            ) : (
                              <span className="grid h-9 w-9 place-items-center rounded-md border border-line-subtle bg-surface-2 text-ink-4">
                                <Icon name="cube" className="h-4 w-4" />
                              </span>
                            )}
                            <span className="max-w-[110px] truncate text-[11.5px] text-ink-2">
                              {person.name}
                            </span>
                          </button>
                          <button
                            onClick={(event) => {
                              event.stopPropagation();
                              setHiddenIds(hidePerson(person.asset_id));
                            }}
                            title="从历史记录移除"
                            className="text-[11px] leading-none text-ink-4 hover:text-danger"
                          >
                            ×
                          </button>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
                {useVideo && (
                  <div className="rounded-lg border border-line-subtle bg-surface-2/40 px-3 py-2 text-[11.5px] text-ink-3">
                    AI 视频驱动由提示词控制动作，下方参数滑杆仅对「全身骨骼」生效；预览区仍展示角色骨架绑定效果。
                  </div>
                )}
                {suggestVideoAction && !useVideo && (
                  <div className="flex flex-wrap items-center justify-between gap-2 rounded-lg border border-ember/40 bg-ember-tint/20 px-3 py-2">
                    <span className="text-[11.5px] text-ink">
                      「{suggestVideoAction}」超出骨骼引擎词表（内置 5 种动作之外的一次性手势）——全身骨骼只能给近似姿态，AI 视频驱动才能真实演出该动作。
                    </span>
                    <Button
                      variant="secondary"
                      size="sm"
                      icon="spark"
                      onClick={() => {
                        setUseVideo(true);
                        setSuggestVideoAction(null);
                      }}
                    >
                      切换到 AI 视频驱动
                    </Button>
                  </div>
                )}
                <div className="flex flex-wrap items-center gap-6">
                  <div>
                    <div className="mb-2 text-[11px] uppercase tracking-widest text-ink-4">
                      生成方式
                    </div>
                    <div className="flex overflow-hidden rounded-lg border border-line-subtle">
                      <button
                        onClick={() => {
                          setUseVideo(false);
                          setSkeletal(true);
                        }}
                        title="姿态引擎驱动的全身关节动画，含预备/跟随/重叠动作"
                        className={cx(
                          "px-3 py-1.5 text-[12px] transition-colors",
                          skeletal && !useVideo
                            ? "bg-primary text-white"
                            : "text-ink-2 hover:bg-surface-2",
                        )}
                      >
                        全身骨骼
                      </button>
                      <button
                        onClick={() => {
                          setUseVideo(false);
                          setSkeletal(false);
                        }}
                        title="对源图做变形动画，最大程度保留原画外观"
                        className={cx(
                          "px-3 py-1.5 text-[12px] transition-colors",
                          !skeletal && !useVideo
                            ? "bg-primary text-white"
                            : "text-ink-2 hover:bg-surface-2",
                        )}
                      >
                        源图驱动
                      </button>
                      <button
                        onClick={() => setUseVideo(true)}
                        title="Windup 式图生视频：AI 原画本身动起来，需自定义模型，耗时约 1~3 分钟"
                        className={cx(
                          "px-3 py-1.5 text-[12px] transition-colors",
                          useVideo ? "bg-primary text-white" : "text-ink-2 hover:bg-surface-2",
                        )}
                      >
                        AI 视频驱动
                      </button>
                    </div>
                    {useVideo && (
                      <label
                        className="mt-2 flex cursor-pointer items-center gap-2 text-[12px] text-ink-2"
                        title="定稿档用更高质量的 i2v 模型（wan2.2-i2v-plus）出片，成本约 2.8×；草稿档确认动作后再开"
                      >
                        <input
                          type="checkbox"
                          checked={finalQuality}
                          onChange={(event) => setFinalQuality(event.target.checked)}
                        />
                        高清定稿（plus 档）
                      </label>
                    )}
                    {skeletal && (
                      <label
                        className="mt-2 flex cursor-pointer items-center gap-2 text-[12px] text-ink-2"
                        title="V3 网格变形：膝/肘屈曲由关节点硬折弯变为过渡带内连续弯曲（皮肤化），姿态端点不变。关闭即回到刚体分区（v5/v6 行为）"
                      >
                        <input
                          type="checkbox"
                          checked={meshSkin}
                          onChange={(event) => setMeshSkin(event.target.checked)}
                        />
                        网格变形（膝/肘皮肤化）
                      </label>
                    )}
                    {skeletal && (
                      <label
                        className="mt-2 flex cursor-pointer items-center gap-2 text-[12px] text-ink-2"
                        title="V3 次级运动：AI 提取发层并按相位滞后跟随步伐摆动。该资产首次开启会调用一次图像编辑（约 0.3 元），之后按源图缓存免费；幅度可用自定义参数 hair_amp/hair_lag 调节"
                      >
                        <input
                          type="checkbox"
                          checked={hairMotion}
                          onChange={(event) => setHairMotion(event.target.checked)}
                        />
                        次级运动（发丝摆动）
                      </label>
                    )}
                    <label
                      className="mt-2 flex cursor-pointer items-center gap-2 text-[12px] text-ink-2"
                      title="V3.5 装备/服装识别：AI 看图认出武器、甲胄、裙装、披风等细节——骨骼链自动贴合姿态（持械攻击摆臂加大/重甲起伏收敛/长裙步幅微收，你的滑杆参数优先），AI 视频驱动把装备并入提示词并在攻击时锁定手中武器。按源图缓存，同一角色终身只识别一次（约 0.002 元）"
                    >
                      <input
                        type="checkbox"
                        checked={equipmentAware}
                        onChange={(event) => setEquipmentAware(event.target.checked)}
                      />
                      服装识别（动作贴合）
                    </label>
                  </div>
                  {skeletal &&
                    selected.kind === "base" &&
                    (selected.name === "walk" || selected.name === "run") && (
                    <div>
                      <div className="mb-2 text-[11px] uppercase tracking-widest text-ink-4">
                        生成视角 · 基础动作专用
                      </div>
                      <div className="flex overflow-hidden rounded-lg border border-line-subtle">
                        <button
                          onClick={() => setView("side")}
                          title="2D 横版侧视步态：腿部交替支撑/摆动，运动最自然"
                          className={cx(
                            "px-3 py-1.5 text-[12px] transition-colors",
                            view === "side"
                              ? "bg-primary text-white"
                              : "text-ink-2 hover:bg-surface-2",
                          )}
                        >
                          侧视横版
                        </button>
                        <button
                          onClick={() => setView("front")}
                          title="正面视角，面向镜头"
                          className={cx(
                            "px-3 py-1.5 text-[12px] transition-colors",
                            view === "front"
                              ? "bg-primary text-white"
                              : "text-ink-2 hover:bg-surface-2",
                          )}
                        >
                          正面
                        </button>
                      </div>
                    </div>
                  )}
                  {useVideo && (
                    <div className="w-full">
                      <ModelApiPanel
                        scope="video"
                        title="视频生成 API 配置"
                        contextNote="AI 视频驱动使用的图生视频 API（当前仅百炼支持）。修改会双向同步至「模型广场」。"
                        defaultCollapsed
                      />
                    </div>
                  )}
                  {skeletal && !useVideo && rigCheck.data?.proportion === "chibi" && (
                    <div className="w-full rounded-lg border border-warning/40 bg-warning/10 px-3 py-2 text-[12px] leading-[18px] text-ink">
                      ⚠ {rigCheck.data.message}
                      <button
                        onClick={() => setUseVideo(true)}
                        className="ml-2 font-medium text-primary underline-offset-2 hover:underline"
                      >
                        切换到 AI 视频驱动
                      </button>
                    </div>
                  )}
                  {/* 基础动作区:内置 5 种动作 + 该区的「生成动画」按钮。
                      活跃标识(徽章/边框高亮)只在 selected.kind === "base" 时出现,
                      与自定义动作区的状态完全隔离。 */}
                  <div
                    className={cx(
                      "w-full rounded-lg border p-3 transition-colors",
                      selected.kind === "base"
                        ? "border-primary/50 bg-primary-tint/30"
                        : "border-line-subtle bg-surface-2/30",
                    )}
                  >
                    <div className="mb-2.5 flex flex-wrap items-center justify-between gap-2">
                      <div className="flex flex-wrap items-center gap-2">
                        <span className="text-[11px] uppercase tracking-widest text-ink-4">
                          基础动作 · 内置 5 种
                        </span>
                        {selected.kind === "base" && (
                          <span className="rounded-full bg-primary px-2 py-0.5 text-[10px] font-medium text-white">
                            当前使用 · {ACTION_LABELS[selected.name]}
                          </span>
                        )}
                      </div>
                      <Button
                        variant="primary"
                        size="sm"
                        icon="spark"
                        loading={busySource === "base"}
                        disabled={busy || selected.kind !== "base"}
                        onClick={() => {
                          if (selected.kind === "base") void generate(selected);
                        }}
                        title={
                          selected.kind !== "base"
                            ? "当前使用的是自定义动作——点击上方任一基础动作切换回来"
                            : `按内置默认参数生成「${ACTION_LABELS[selected.name]}」动画`
                        }
                      >
                        {busySource === "base"
                          ? "生成中…"
                          : selected.kind === "base"
                            ? `生成动画（${ACTION_LABELS[selected.name]}）`
                            : "生成动画"}
                      </Button>
                    </div>
                    <div className="flex flex-wrap gap-2">
                      {ACTIONS.map((item) => {
                        const active = selected.kind === "base" && selected.name === item;
                        return (
                          <button
                            key={item}
                            onClick={() => selectBase(item)}
                            title={`内置${ACTION_LABELS[item]}动作,使用姿态引擎默认参数`}
                            className={cx(
                              "rounded-lg border px-3.5 py-1.5 text-[12px] transition-colors",
                              active
                                ? "border-primary bg-primary text-white"
                                : "border-line-subtle bg-surface-1 text-ink-2 hover:border-line hover:bg-surface-2",
                            )}
                          >
                            {ACTION_LABELS[item]}
                          </button>
                        );
                      })}
                    </div>
                    {selected.kind !== "base" && (
                      <p className="mt-2 text-[10.5px] text-ink-4">
                        当前活跃的是自定义动作——点击任一基础动作切换后,此区的「生成动画」按钮才会激活。
                        自定义动作的创建与使用都在下方「自定义动作功能区」,与本区相互独立。
                      </p>
                    )}
                  </div>
                </div>
                <div className="flex flex-wrap items-end gap-6">
                  <label className="text-[11px] text-ink-4">
                    <span className="mb-2 block uppercase tracking-widest">帧率 {fps} fps</span>
                    <input
                      type="range"
                      min={4}
                      max={30}
                      value={fps}
                      onChange={(e) => setFps(Number(e.target.value))}
                    />
                  </label>
                  <label className="text-[11px] text-ink-4">
                    <span className="mb-2 block uppercase tracking-widest">
                      时长 {duration.toFixed(1)}s
                    </span>
                    <input
                      type="range"
                      min={0.3}
                      max={4}
                      step={0.1}
                      value={duration}
                      onChange={(e) => setDuration(Number(e.target.value))}
                    />
                  </label>
                  <label className="text-[11px] text-ink-4">
                    <span className="mb-2 block uppercase tracking-widest">分辨率</span>
                    <select
                      value={size}
                      onChange={(e) => setSize(Number(e.target.value))}
                      className="rounded-lg border border-line-subtle bg-surface-1 px-2 py-1.5 text-[12px]"
                    >
                      {SIZES.map((option) => (
                        <option key={option} value={option}>
                          {option} x {option}
                        </option>
                      ))}
                    </select>
                  </label>
                  <div className="ml-auto flex items-center gap-3">
                    <input
                      ref={fileRef}
                      type="file"
                      accept="image/*"
                      className="hidden"
                      onChange={(e) => onFile(e.target.files?.[0])}
                    />
                    <Button
                      variant="secondary"
                      size="sm"
                      icon="image"
                      onClick={() => fileRef.current?.click()}
                    >
                      上传源图
                    </Button>
                  </div>
                </div>
                {upload && (
                  <button
                    className="text-[11px] text-ink-3 underline"
                    onClick={() => setUpload(null)}
                  >
                    清除上传，改用当前资产
                  </button>
                )}
              </div>
            )}

            {mode === "smart" && (
              <div className="flex flex-col gap-4">
                {/* ── 自定义动作功能区分界 ─────────────────────────────
                    本分隔线以下只服务自定义动作：创作台（调参/命名/保存）
                    与动作库（选卡/生成）。基础动作的服务只在上方基础动作
                    区，两区不交叉、不互相包含。 */}
                <div className="flex items-center gap-3" aria-hidden>
                  <span className="h-px flex-1 bg-line-subtle" />
                  <span className="text-[11px] font-semibold uppercase tracking-widest text-ember">
                    自定义动作 · 功能区（创作与使用）
                  </span>
                  <span className="h-px flex-1 bg-line-subtle" />
                </div>
                <div className="flex flex-wrap items-center gap-6">
                  <div className="flex items-center gap-2">
                    <span className="text-[11px] uppercase tracking-widest text-ink-4">
                      创作台 · 当前参数
                    </span>
                    {selected.kind === "base" ? (
                      <span className="rounded-full border border-line-subtle bg-surface-2 px-2.5 py-0.5 text-[10.5px] font-medium text-ink-2">
                        创作基底 · 内置「{ACTION_LABELS[editorAction]}」（改动不影响上方基础动作区）
                      </span>
                    ) : (
                      <span className="rounded-full border border-ember/40 bg-ember-tint/30 px-2.5 py-0.5 text-[10.5px] font-medium text-ink">
                        编辑中 · {selected.name}（基于
                        {ACTION_LABELS[editorAction] ?? editorAction}）
                      </span>
                    )}
                    {editorDirty && (
                      <span className="text-[10px] text-warning">
                        滑杆已调整(仅影响预览)——生成按所选动作的保存参数,调整后请保存为新自定义动作
                      </span>
                    )}
                  </div>
                  {isLocomotion && (
                    <div>
                      <div className="mb-2 text-[11px] uppercase tracking-widest text-ink-4">
                        预览视角 · 仅创作台预览
                      </div>
                      <div className="flex overflow-hidden rounded-lg border border-line-subtle">
                        {(["side", "front"] as const).map((item) => (
                          <button
                            key={item}
                            onClick={() => setEditorView(item)}
                            className={cx(
                              "px-3 py-1.5 text-[12px] transition-colors",
                              editorView === item
                                ? "bg-primary text-white"
                                : "text-ink-2 hover:bg-surface-2",
                            )}
                          >
                            {item === "side" ? "侧视横版" : "正面"}
                          </button>
                        ))}
                      </div>
                    </div>
                  )}
                  <div className="ml-auto flex items-center gap-2">
                    <Button
                      variant="secondary"
                      size="sm"
                      icon="play"
                      onClick={() => setPlaying((p) => !p)}
                    >
                      {playing ? "暂停" : "播放循环"}
                    </Button>
                  </div>
                </div>

                {Array.isArray(poseConfig.phases) && poseConfig.phases.length >= 2 && (
                  <div className="flex flex-wrap items-center gap-1.5 rounded-lg border border-ember/30 bg-ember-tint/10 px-3 py-2">
                    <span className="text-[10.5px] font-medium text-ink-3">编排序列</span>
                    {(poseConfig.phases as MotionPhase[]).map((seg, index) => (
                      <span
                        key={index}
                        className="rounded-full border border-ember/30 bg-ember-tint/20 px-2 py-0.5 text-[10px] text-ink-2"
                      >
                        {index + 1}. {ACTION_LABELS[seg.action] ?? seg.action}
                        {seg.turn ? ` · 转${Math.round(seg.turn)}°` : ""}
                      </span>
                    ))}
                    <span className="text-[10px] text-ink-4">
                      （AI 解读生成；滑杆为全局幅度，保存后按序列出片）
                    </span>
                  </div>
                )}

                <div className="rounded-lg border border-line-subtle bg-surface-2/40 p-3">
                  <div className="mb-2 flex items-center justify-between">
                    <span className="text-[11px] uppercase tracking-widest text-ink-4">
                      自然语言创作 · 一句话生成动作参数（自定义动作专用）
                    </span>
                    <div className="flex items-center gap-1.5">
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={nlUndo}
                        disabled={nlPast.current.length === 0}
                      >
                        撤销
                      </Button>
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={nlRedo}
                        disabled={nlFuture.current.length === 0}
                      >
                        重做
                      </Button>
                    </div>
                  </div>
                  <Textarea
                    value={nlText}
                    onChange={(event) => nlChange(event.target.value)}
                    rows={2}
                    placeholder="例：角色快速挥刀两下，然后向后跳开，落地时微微下蹲。支持换行与 Ctrl+Z 撤销。"
                    className="w-full"
                  />
                  <div className="mt-2 flex flex-wrap items-center gap-2">
                    <Button
                      variant="secondary"
                      size="sm"
                      icon="spark"
                      loading={nlBusy === "enhance"}
                      onClick={nlEnhance}
                      disabled={!nlText.trim()}
                      title="用对话模型把描述润色成专业动作说明"
                    >
                      文案增强
                    </Button>
                    <Button
                      variant="primary"
                      size="sm"
                      icon="zap"
                      loading={nlBusy === "apply"}
                      onClick={nlApply}
                      disabled={!nlText.trim()}
                      title="把描述解读成动作参数，自动套用到下方滑杆与时间轴"
                    >
                      套用到动作编辑器
                    </Button>
                    <span className="text-[10.5px] text-ink-4">
                      套用后可在下方滑杆微调,保存后在下方「动作库」中生成
                    </span>
                  </div>
                </div>

                <div className="grid grid-cols-2 gap-x-8 gap-y-3 md:grid-cols-4">
                  {POSE_PARAMS.map((param) => (
                    <label key={param.key} className="text-[11px] text-ink-4">
                      <span className="mb-1.5 flex justify-between uppercase tracking-widest">
                        <span>{param.label}</span>
                        <span className="font-mono text-ink-3">
                          {String(poseConfig[param.key] ?? 0)}
                        </span>
                      </span>
                      <input
                        type="range"
                        min={param.min}
                        max={param.max}
                        step={param.step}
                        value={Number(poseConfig[param.key] ?? 0)}
                        onChange={(e) =>
                          setPoseConfig((prev) => ({
                            ...prev,
                            [param.key]: Number(e.target.value),
                          }))
                        }
                        className="w-full"
                      />
                    </label>
                  ))}
                </div>

                <div>
                  <div className="mb-2 flex items-center justify-between text-[11px] uppercase tracking-widest text-ink-4">
                    <span>时间轴 · 12 相位</span>
                    <span className="font-mono normal-case text-ink-3">
                      phase {phase.toFixed(2)}
                    </span>
                  </div>
                  <div className="flex gap-1">
                    {Array.from({ length: 12 }, (_, index) => index / 12).map((value, index) => (
                      <button
                        key={value}
                        onClick={() => {
                          setPlaying(false);
                          setPhase(value);
                        }}
                        title={`相位 ${value.toFixed(2)}`}
                        className={cx(
                          "h-7 flex-1 rounded-md border font-mono text-[10px] transition-colors",
                          Math.abs(phase - value) < 1 / 24
                            ? "border-primary bg-primary text-white"
                            : "border-line-subtle bg-surface-1 text-ink-3 hover:bg-surface-2",
                        )}
                      >
                        {index + 1}
                      </button>
                    ))}
                  </div>
                  <input
                    type="range"
                    min={0}
                    max={1}
                    step={1 / 60}
                    value={phase}
                    onChange={(e) => {
                      setPlaying(false);
                      setPhase(Number(e.target.value));
                    }}
                    className="mt-2 w-full"
                  />
                </div>

                {editingName && (
                  <div className="flex flex-wrap items-center justify-between gap-2 rounded-md border border-ember/40 bg-ember-tint/20 px-3 py-2">
                    <span className="text-[11px] text-ember">
                      正在编辑「{editingName}」——保存后覆盖该动作（保留创建时间并记入修改历史；改名则整卡迁移元数据）
                    </span>
                    <button
                      onClick={cancelEdit}
                      className="text-[11px] text-ink-3 underline-offset-2 hover:text-ink hover:underline"
                    >
                      取消编辑
                    </button>
                  </div>
                )}
                <div className="flex flex-wrap items-end gap-4 rounded-lg border border-line-subtle bg-surface-2/40 p-3">
                  <label className="text-[11px] text-ink-4">
                    <span className="mb-1.5 block uppercase tracking-widest">
                      {editingName ? "编辑自定义动作（保存即覆盖）" : "保存当前调参为新自定义动作"}
                    </span>
                    <input
                      value={presetName}
                      onChange={(e) => setPresetName(e.target.value)}
                      placeholder="动作名称，如：轻快小跑"
                      className="h-8 w-44 rounded-md border border-line bg-surface-1 px-2.5 text-[12px] text-ink outline-none placeholder:text-ink-4 focus:border-primary"
                    />
                  </label>
                  <Button
                    variant="secondary"
                    size="sm"
                    icon="check"
                    loading={editorBusy}
                    disabled={!presetName.trim()}
                    onClick={savePreset}
                  >
                    {editingName ? "保存修改" : "保存"}
                  </Button>
                  <span className="text-[10.5px] text-ink-4">
                    {editingName
                      ? "可改动作基底、视角、滑杆与描述后保存；改名称即另存为新动作（元数据随迁）。"
                      : "保存后自动选中,到下方「动作库」点击「用此动作生成」。"}
                  </span>
                </div>

                {/* ── 动作库分界：创作台到此为止，下面是已保存动作的选择与生成 ── */}
                <div className="flex items-center gap-3" aria-hidden>
                  <span className="h-px flex-1 bg-line-subtle" />
                  <span className="text-[11px] font-semibold uppercase tracking-widest text-ember">
                    自定义动作 · 动作库（选中后生成）
                  </span>
                  <span className="h-px flex-1 bg-line-subtle" />
                </div>

                {/* 自定义动作区:与基础动作区(上方 primary 高亮)完全独立的
                    存储来源与生成入口,ember 暖橙做区域识别色。 */}
                <div
                  className={cx(
                    "flex flex-col gap-3 rounded-lg border p-3 transition-colors",
                    selected.kind === "custom"
                      ? "border-ember/50 bg-ember-tint/20"
                      : "border-line-subtle bg-surface-2/30",
                  )}
                >
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="text-[11px] uppercase tracking-widest text-ink-4">
                        动作库 · 已保存的自定义动作
                      </span>
                      {selected.kind === "custom" && (
                        <span className="rounded-full bg-ember px-2 py-0.5 text-[10px] font-medium text-white">
                          当前使用 · {selected.name}
                        </span>
                      )}
                    </div>
                    <Button
                      variant="primary"
                      size="sm"
                      icon="spark"
                      loading={busySource === "custom"}
                      disabled={busy || selected.kind !== "custom"}
                      onClick={() => {
                        if (selected.kind === "custom") void generate(selected);
                      }}
                      title={
                        selected.kind !== "custom"
                          ? "先在下方动作库点击一张自定义动作卡片选中"
                          : `严格按「${selected.name}」保存时的参数生成动画`
                      }
                    >
                      {busySource === "custom"
                        ? "生成中…"
                        : selected.kind === "custom"
                          ? `用此动作生成（${selected.name}）`
                          : "用此动作生成"}
                    </Button>
                  </div>
                  {presets.length === 0 ? (
                    <p className="text-[11.5px] text-ink-4">
                      暂无自定义动作——在上方创作台调整动作与参数后,输入名称保存即可出现在这里。
                    </p>
                  ) : (
                    <div className="grid grid-cols-1 gap-2 sm:grid-cols-2 lg:grid-cols-3">
                      {presets.map((preset) => {
                        const active = selected.kind === "custom" && selected.name === preset.name;
                        return (
                          <div
                            key={preset.name}
                            className={cx(
                              "group relative flex flex-col gap-1.5 rounded-lg border px-2.5 py-2 transition-colors",
                              active
                                ? "border-ember bg-ember-tint/40"
                                : "border-line-subtle bg-surface-1 hover:border-line",
                            )}
                          >
                            <div className="flex items-center gap-2.5">
                              <button
                                onClick={() => selectCustom(preset.name)}
                                title={`选中「${preset.name}」`}
                                className="flex min-w-0 flex-1 items-center gap-2.5 text-left"
                              >
                                <span
                                  className={cx(
                                    "grid h-5 w-5 shrink-0 place-items-center rounded-full border transition-colors",
                                    active
                                      ? "border-ember bg-ember text-white"
                                      : "border-line text-transparent",
                                  )}
                                >
                                  <Icon name="check" className="h-3 w-3" />
                                </span>
                                <span className="min-w-0">
                                  <span className="block truncate text-[12px] text-ink">
                                    {preset.name}
                                  </span>
                                  <span className="block text-[10.5px] text-ink-4">
                                    基于{ACTION_LABELS[preset.action] ?? preset.action} ·{" "}
                                    {preset.view === "side" ? "侧视" : "正面"}
                                    {preset.revision && preset.revision > 1
                                      ? ` · 已修改 ${preset.revision - 1} 次`
                                      : ""}
                                  </span>
                                </span>
                              </button>
                              {/* 每张卡片专属的生成按钮：点卡片=选中，点生成=选中并
                                  立即按该动作保存参数出片——与基础动作区"每个动作
                                  可直接生成"对齐，自定义动作不再依赖顶部总按钮 */}
                              <button
                                onClick={() => {
                                  selectCustom(preset.name);
                                  void generate({ kind: "custom", name: preset.name });
                                }}
                                disabled={busy}
                                title={`选中并立即按「${preset.name}」保存时的参数生成动画`}
                                className={cx(
                                  "shrink-0 rounded-md border px-2 py-1 text-[10.5px] transition-colors",
                                  active
                                    ? "border-ember bg-ember text-white hover:opacity-90"
                                    : "border-line-subtle bg-surface-2 text-ink-2 hover:border-ember hover:text-ember",
                                )}
                              >
                                {busy && active ? "生成中…" : "生成"}
                              </button>
                            </div>
                            {/* 第二行：描述摘要（详情看全文）+ 详情/编辑/删除入口 */}
                            <div className="flex items-center gap-2">
                              <span
                                className="min-w-0 flex-1 truncate text-[10.5px] text-ink-4"
                                title={
                                  preset.description ||
                                  (preset.revision
                                    ? "未填写描述——点「详情」查看完整参数"
                                    : "旧版创建的动作，描述未存档——点「编辑」补写后保存即可归档")
                                }
                              >
                                {preset.description ||
                                  (preset.revision
                                    ? "（未填写描述）"
                                    : "（描述未存档 · 旧版创建，编辑可补写）")}
                              </span>
                              <button
                                onClick={() => void openDetail(preset.name)}
                                title="查看完整描述、姿态参数、创建/修改时间与修改历史"
                                className="shrink-0 text-[10.5px] text-ink-3 hover:text-primary"
                              >
                                详情
                              </button>
                              <button
                                onClick={() => startEdit(preset)}
                                title="载入上方创作台，修改动作属性与参数后覆盖保存"
                                className="shrink-0 text-[10.5px] text-ink-3 hover:text-ember"
                              >
                                编辑
                              </button>
                              <button
                                onClick={() => removePreset(preset.name)}
                                title="删除该自定义动作"
                                className="shrink-0 text-[11px] leading-none text-ink-4 hover:text-danger"
                              >
                                ×
                              </button>
                            </div>
                          </div>
                        );
                      })}
                    </div>
                  )}
                  {selected.kind !== "custom" && (
                    <p className="text-[10.5px] text-ink-4">
                      每张卡片的「生成」按钮可选中并立即按该动作出片（严格按保存时的参数执行）；点卡片本身仅选中,顶部按钮对应当前选中项。
                    </p>
                  )}
                </div>
              </div>
            )}

            {mode === "sequence" && (
              <div className="flex flex-col gap-4">
                <div className="flex flex-wrap items-end gap-6">
                  <label className="text-[11px] text-ink-4">
                    <span className="mb-2 block uppercase tracking-widest">帧率 {fps} fps</span>
                    <input
                      type="range"
                      min={2}
                      max={30}
                      value={fps}
                      onChange={(e) => setFps(Number(e.target.value))}
                    />
                  </label>
                  <label className="text-[11px] text-ink-4">
                    <span className="mb-2 block uppercase tracking-widest">分辨率</span>
                    <select
                      value={size}
                      onChange={(e) => setSize(Number(e.target.value))}
                      className="rounded-lg border border-line-subtle bg-surface-1 px-2 py-1.5 text-[12px]"
                    >
                      {SIZES.map((option) => (
                        <option key={option} value={option}>
                          {option} x {option}
                        </option>
                      ))}
                    </select>
                  </label>
                  <div className="ml-auto flex items-center gap-3">
                    <input
                      ref={seqFileRef}
                      type="file"
                      accept="image/*"
                      multiple
                      className="hidden"
                      onChange={(e) => {
                        onSeqFiles(e.target.files);
                        e.target.value = "";
                      }}
                    />
                    <Button
                      variant="secondary"
                      size="sm"
                      icon="image"
                      onClick={() => seqFileRef.current?.click()}
                    >
                      导入序列帧
                    </Button>
                    <Button
                      variant="primary"
                      size="sm"
                      icon="film"
                      onClick={composeSequence}
                      disabled={busy || seqFrames.length < 2}
                    >
                      {busy ? "合成中…" : `合成动画（${seqFrames.length} 帧）`}
                    </Button>
                  </div>
                </div>
                {seqFrames.length > 0 && (
                  <div>
                    <div className="mb-2 flex items-center justify-between text-[11px] text-ink-4">
                      <span>
                        已导入 {seqFrames.length} 帧 · 按文件名顺序播放（时长约{" "}
                        {(seqFrames.length / fps).toFixed(2)}s）
                      </span>
                      <button
                        className="underline hover:text-ink-2"
                        onClick={() => setSeqFrames([])}
                      >
                        清空全部
                      </button>
                    </div>
                    <div className="cf-scroll flex max-h-[120px] flex-wrap gap-2 overflow-y-auto rounded-[10px] border border-line-subtle bg-surface-1 p-2">
                      {seqFrames.map((frame, index) => (
                        <div
                          key={`${frame.name}-${index}`}
                          className="group relative h-14 w-14 shrink-0 overflow-hidden rounded-md border border-line-subtle bg-[#f1efe9]"
                          title={`${frame.name} · 第 ${index + 1} 帧`}
                        >
                          <img
                            src={frame.dataUrl}
                            alt={frame.name}
                            className="h-full w-full object-contain"
                          />
                          <button
                            onClick={() =>
                              setSeqFrames((prev) => prev.filter((_, i) => i !== index))
                            }
                            className="absolute right-0 top-0 hidden h-4 w-4 items-center justify-center rounded-bl-md bg-ink/80 text-[9px] text-canvas group-hover:flex"
                            aria-label={`移除 ${frame.name}`}
                          >
                            ✕
                          </button>
                          <span className="absolute bottom-0 left-0 bg-ink/70 px-1 text-[9px] text-canvas">
                            {index + 1}
                          </span>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            )}

            {error && (
              <p className="mt-3 border-l-2 border-danger pl-3 text-[12.5px] text-danger">
                {error}
              </p>
            )}
          </Card>

          {result && (
            <Card
              title="帧序列 Sprite Sheet"
              icon="film"
              iconClassName="text-falign"
              right={
                <a
                  className="text-[12px] text-ink-3 underline decoration-line"
                  href={result.urls.sheet}
                  download
                >
                  下载雪碧图
                </a>
              }
            >
              <div className="cf-scroll overflow-x-auto rounded-[10px] border border-line-subtle bg-surface-1 p-2">
                <img src={result.urls.sheet} alt="sprite sheet" className="max-h-[220px]" />
              </div>
            </Card>
          )}

          {result && result.frame_urls && result.frame_urls.length > 0 && (
            <Card
              title={`关键帧 Keyframes · ${result.frame_count} 帧`}
              icon="grid"
              iconClassName="text-falign"
              right={
                <span className="text-[12px] text-ink-3">
                  {result.action === "sequence" ? "导入序列 · 原样合成" : "全身骨骼 · 关节动画"}
                </span>
              }
            >
              <div className="cf-scroll flex gap-3 overflow-x-auto pb-1">
                {result.frame_urls.map((url, index) => (
                  <figure key={url} className="shrink-0">
                    <div className="h-[130px] w-[130px] overflow-hidden rounded-lg border border-line-subtle bg-[#f1efe9]">
                      <img
                        src={url}
                        alt={`frame ${index + 1}`}
                        className="h-full w-full object-contain"
                        loading="lazy"
                      />
                    </div>
                    <figcaption className="mt-1 text-center font-mono text-[10.5px] text-ink-4">
                      #{index + 1}
                    </figcaption>
                  </figure>
                ))}
              </div>
            </Card>
          )}

          {rootTrack.length > 0 && (
            <Card
              title="根运动轨迹 Root Motion（漂移 → 纠偏）"
              icon="activity"
              iconClassName="text-falign"
            >
              <svg viewBox="0 0 640 90" className="h-[90px] w-full">
                <line x1="0" y1="45" x2="640" y2="45" stroke="#b9b3a5" strokeDasharray="5 5" />
                <path d={trackPath} fill="none" stroke="#a94f3d" strokeWidth="2" />
                {rootTrack.map((point, index) => {
                  const x = (index / Math.max(1, rootTrack.length - 1)) * 640;
                  const y = 45 - (point.dx + (corrections[index]?.dx ?? 0)) * 6;
                  return <circle key={index} cx={x} cy={y} r="3.5" fill="#3e7d5a" />;
                })}
              </svg>
            </Card>
          )}
        </div>

        <div className="col-span-12 flex flex-col gap-5 xl:col-span-4">
          <Card title="风格识别 Style Analysis" icon="layers" iconClassName="text-falign">
            {result ? (
              <div className="space-y-3.5">
                <div className="flex items-center justify-between">
                  <span className="text-[13px] text-ink-2">识别风格</span>
                  <Badge tone="falign">{result.style_label}</Badge>
                </div>
                <ScoreBar label="置信度" value={result.style.confidence} />
                <ul className="space-y-2 text-[12px] text-ink-3">
                  <li className="flex justify-between">
                    <span>色板规模</span>
                    <span className="font-mono">{result.style.palette_size}</span>
                  </li>
                  <li className="flex justify-between">
                    <span>线条密度</span>
                    <span className="font-mono">{result.style.edge_density.toFixed(3)}</span>
                  </li>
                  <li className="flex justify-between">
                    <span>平涂占比</span>
                    <span className="font-mono">{result.style.flat_ratio.toFixed(3)}</span>
                  </li>
                  <li className="flex justify-between">
                    <span>饱和度</span>
                    <span className="font-mono">{result.style.saturation.toFixed(3)}</span>
                  </li>
                </ul>
              </div>
            ) : (
              <div className="text-[12.5px] text-ink-3">生成动画后展示源图的风格识别结果。</div>
            )}
          </Card>

          <Card
            title="一致性校验 Consistency"
            icon="check"
            iconClassName="text-falign"
            right={
              result ? (
                <Badge tone={result.consistency.passed ? "success" : "warning"}>
                  {result.consistency.passed ? "PASS" : "RETRY"}
                </Badge>
              ) : undefined
            }
          >
            {result ? (
              <div className="space-y-3.5">
                <ScoreBar label="色彩 Palette" value={result.consistency.palette} tone="falign" />
                <ScoreBar label="色调 Color" value={result.consistency.color} tone="gimport" />
                <ScoreBar label="线条 Line" value={result.consistency.line} tone="falign" />
                <ScoreBar label="感知哈希 Hash" value={result.consistency.hash} tone="gimport" />
                <ScoreBar
                  label={`综合 · 阈值 ${result.consistency.floor}`}
                  value={result.consistency.overall}
                  threshold={result.consistency.floor}
                />
                <div className="text-[11px] text-ink-4">
                  对比 {result.consistency.frames_checked} 帧
                </div>
              </div>
            ) : (
              <div className="text-[12.5px] text-ink-3">
                通过视觉相似度分析（配色 / 线条 / 感知哈希）校验生成动画与源图的一致性。
              </div>
            )}
          </Card>

          {result && result.character.palette.length > 0 && (
            <Card title="人物特征 Character" icon="cube">
              <ul className="space-y-2 text-[12px] text-ink-3">
                <li className="flex justify-between">
                  <span>包围盒</span>
                  <span className="font-mono">{result.character.bbox.join(",")}</span>
                </li>
                <li className="flex justify-between">
                  <span>宽高比</span>
                  <span className="font-mono">{result.character.aspect}</span>
                </li>
                <li className="flex justify-between">
                  <span>中心</span>
                  <span className="font-mono">{result.character.center.join(",")}</span>
                </li>
              </ul>
              <div className="mt-3 flex flex-wrap gap-1.5">
                {result.character.palette.map((color) => (
                  <span
                    key={color}
                    className="h-5 w-5 rounded border border-line-subtle"
                    style={{ background: color }}
                    title={color}
                  />
                ))}
              </div>
            </Card>
          )}

          {quality && (
            <Card title="FAlign 质量 Quality" icon="gauge" iconClassName="text-falign">
              <div className="space-y-3.5">
                <ScoreBar label="Anchor 锚点稳定" value={quality.anchor_score ?? 0} tone="falign" />
                <ScoreBar label="Motion 根运动" value={quality.motion_score ?? 0} tone="gimport" />
                <ScoreBar
                  label="Temporal 时序平滑"
                  value={quality.temporal_score ?? 0}
                  tone="falign"
                />
              </div>
            </Card>
          )}
        </div>
      </div>

      {preview && result && (
        <div
          className="fixed inset-0 z-50 grid place-items-center bg-black/60 p-6"
          onClick={() => setPreview(false)}
        >
          <div
            className="relative max-h-[90vh] max-w-[92vw] rounded-2xl border border-line-subtle bg-surface-1 p-4 shadow-2xl"
            onClick={(event) => event.stopPropagation()}
          >
            <button
              onClick={() => setPreview(false)}
              className="absolute -right-3 -top-3 grid h-8 w-8 place-items-center rounded-full border border-line-subtle bg-surface-1 text-ink-2"
            >
              ✕
            </button>
            {previewLoading && !previewError && (
              <div className="grid h-[320px] w-[320px] place-items-center text-sm text-ink-3">
                正在加载动画…
              </div>
            )}
            {previewError && (
              <div className="grid h-[320px] w-[320px] place-items-center px-6 text-center text-sm text-danger">
                在线预览加载失败，请点击「下载 GIF」查看。
              </div>
            )}
            <img
              src={result.urls.gif}
              alt="animation preview"
              className={cx(
                "max-h-[80vh] max-w-[88vw] object-contain",
                (previewLoading || previewError) && "hidden",
              )}
              onLoad={() => setPreviewLoading(false)}
              onError={() => {
                setPreviewLoading(false);
                setPreviewError(true);
              }}
            />
          </div>
        </div>
      )}

      {/* 自定义动作详情弹窗：完整描述 + 元数据（创建/修改时间、版本数）+
          修改历史快照——列表卡片只放摘要，全量信息在这里追溯 */}
      {detailName && (
        <div
          className="fixed inset-0 z-50 grid place-items-center bg-black/60 p-6"
          onClick={() => setDetailName(null)}
        >
          <div
            className="relative max-h-[85vh] w-full max-w-lg overflow-y-auto rounded-2xl border border-line-subtle bg-surface-1 p-5 shadow-2xl"
            onClick={(event) => event.stopPropagation()}
          >
            <button
              onClick={() => setDetailName(null)}
              className="absolute -right-3 -top-3 grid h-8 w-8 place-items-center rounded-full border border-line-subtle bg-surface-1 text-ink-2"
            >
              ✕
            </button>
            {detailBusy || !detail ? (
              <div className="grid h-40 place-items-center text-sm text-ink-3">
                正在加载动作详情…
              </div>
            ) : (
              <div className="flex flex-col gap-4">
                <div>
                  <h3 className="text-[15px] font-semibold text-ink">{detail.name}</h3>
                  <p className="mt-0.5 text-[11px] text-ink-4">
                    基于{ACTION_LABELS[detail.action] ?? detail.action} ·{" "}
                    {detail.view === "side" ? "侧视" : "正面"} · 第 {detail.revision ?? 1} 版
                  </p>
                </div>

                <div>
                  <p className="mb-1 text-[10.5px] uppercase tracking-widest text-ink-4">
                    动作描述
                  </p>
                  <p className="whitespace-pre-wrap rounded-md border border-line-subtle bg-surface-2/40 p-2.5 text-[12px] leading-relaxed text-ink-2">
                    {detail.description ||
                      (detail.revision
                        ? "（未填写描述——可点「编辑此动作」补写并保存）"
                        : "该动作创建于「描述存档」功能上线之前，当时在自然语言框填写的描述未被保存下来，且无法从本地数据找回。点下方「编辑此动作」补写描述并保存即可归档，之后的每次修改都会自动记入历史。")}
                  </p>
                </div>

                <div className="grid grid-cols-2 gap-x-4 gap-y-1.5 text-[11.5px]">
                  <span className="text-ink-4">创建时间</span>
                  <span className="text-ink-2">{fmtTime(detail.created_at)}</span>
                  <span className="text-ink-4">最后修改</span>
                  <span className="text-ink-2">{fmtTime(detail.updated_at)}</span>
                  <span className="text-ink-4">累计修改</span>
                  <span className="text-ink-2">{Math.max(0, (detail.revision ?? 1) - 1)} 次</span>
                </div>

                <div>
                  <p className="mb-1 text-[10.5px] uppercase tracking-widest text-ink-4">
                    姿态参数
                  </p>
                  <div className="grid grid-cols-2 gap-x-4 gap-y-1 text-[11.5px]">
                    {POSE_PARAMS.map((param) => (
                      <div key={param.key} className="flex justify-between gap-2">
                        <span className="text-ink-4">{param.label}</span>
                        <span className="font-mono text-ink-2">
                          {typeof detail.pose_config[param.key] === "number"
                            ? detail.pose_config[param.key]
                            : "—"}
                        </span>
                      </div>
                    ))}
                  </div>
                  {Array.isArray(detail.pose_config.phases) &&
                    detail.pose_config.phases.length >= 2 && (
                      <p className="mt-2 text-[11px] text-ink-3">
                        多段编排：
                        {detail.pose_config.phases
                          .map(
                            (seg) =>
                              `${ACTION_LABELS[seg.action] ?? seg.action}(比重${seg.weight}${
                                seg.turn ? ` · 转${Math.round(seg.turn)}°` : ""
                              })`,
                          )
                          .join(" → ")}
                      </p>
                    )}
                </div>

                <div>
                  <p className="mb-1 text-[10.5px] uppercase tracking-widest text-ink-4">
                    修改历史（{detail.history?.length ?? 0} 条快照）
                  </p>
                  {(detail.history?.length ?? 0) === 0 ? (
                    <p className="text-[11px] text-ink-4">
                      尚无修改记录——该动作自创建以来未被覆盖保存过。
                    </p>
                  ) : (
                    <ol className="flex flex-col gap-1.5">
                      {detail.history.map((entry, index) => (
                        <li
                          key={`${entry.time}-${index}`}
                          className="rounded-md border border-line-subtle bg-surface-2/30 px-2.5 py-1.5 text-[11px]"
                        >
                          <div className="text-ink-4">
                            v{entry.revision} · {fmtTime(entry.time)} ·{" "}
                            {entry.trigger === "import" ? "动作包导入覆盖前" : "编辑覆盖前"}
                          </div>
                          <div className="mt-0.5 text-ink-2">
                            基于{ACTION_LABELS[entry.action] ?? entry.action} ·{" "}
                            {entry.view === "side" ? "侧视" : "正面"}
                            {entry.description ? ` · ${entry.description}` : ""}
                          </div>
                        </li>
                      ))}
                    </ol>
                  )}
                </div>

                <div className="flex justify-end gap-2">
                  <Button
                    variant="secondary"
                    size="sm"
                    onClick={() => {
                      const target = presets.find((p) => p.name === detail.name);
                      setDetailName(null);
                      if (target) startEdit(target);
                    }}
                  >
                    编辑此动作
                  </Button>
                  <Button variant="primary" size="sm" onClick={() => setDetailName(null)}>
                    关闭
                  </Button>
                </div>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

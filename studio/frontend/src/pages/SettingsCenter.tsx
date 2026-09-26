import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../api/client";
import { toast } from "../stores/toastStore";
import {
  Badge,
  Button,
  Card,
  Input,
  PageHeader,
  Segmented,
  Skeleton,
  StatusDot,
  Switch,
  cx,
} from "../components/ui";
import { Icon } from "../components/icons";
import type { ModelTestResult, ProviderPreset } from "../types";

const SIZES = [
  { id: "512x512", label: "512²" },
  { id: "768x768", label: "768²" },
  { id: "1024x1024", label: "1024²" },
  { id: "1024x1792", label: "1024×1792" },
];

const CHAT_SUGGESTIONS = ["deepseek-chat", "deepseek-reasoner", "gpt-4o-mini", "glm-4-flash"];
const IMAGE_SUGGESTIONS = ["gpt-image-1", "FLUX.1-schnell", "cogview-3-flash", "dall-e-3"];

export default function SettingsCenter() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const settings = useQuery({ queryKey: ["model-settings"], queryFn: api.getModelSettings });
  const presets = useQuery({ queryKey: ["model-presets"], queryFn: api.getModelPresets, staleTime: Infinity });

  const [enabled, setEnabled] = useState(false);
  const [provider, setProvider] = useState("custom");
  const [baseUrl, setBaseUrl] = useState("");
  const [apiKey, setApiKey] = useState("");
  const [model, setModel] = useState("");
  const [chatModel, setChatModel] = useState("");
  const [useChat, setUseChat] = useState(true);
  const [useImage, setUseImage] = useState(true);
  const [size, setSize] = useState("1024x1024");
  const [timeout, setTimeoutValue] = useState(60);
  const [testResult, setTestResult] = useState<ModelTestResult | null>(null);

  useEffect(() => {
    const data = settings.data;
    if (!data) return;
    setEnabled(data.enabled);
    setProvider(data.provider);
    setBaseUrl(data.base_url);
    setModel(data.model);
    setChatModel(data.chat_model);
    setUseChat(data.use_chat);
    setUseImage(data.use_image);
    setSize(data.size);
    setTimeoutValue(data.timeout);
    setApiKey("");
  }, [settings.data]);

  function applyPreset(preset: ProviderPreset) {
    setProvider(preset.id);
    setBaseUrl(preset.base_url || baseUrl);
    setChatModel(preset.chat_model || "");
    setModel(preset.image_model || "");
    setUseChat(preset.use_chat);
    setUseImage(preset.use_image);
    if (preset.id === "system") {
      setEnabled(false);
    } else {
      setEnabled(true);
    }
    setTestResult(null);
  }

  const save = useMutation({
    mutationFn: () =>
      api.saveModelSettings({
        enabled,
        provider,
        base_url: baseUrl,
        model,
        chat_model: chatModel,
        use_chat: useChat,
        use_image: useImage,
        size,
        timeout,
        api_key: apiKey.trim() ? apiKey.trim() : undefined,
      }),
    onSuccess: (data) => {
      queryClient.setQueryData(["model-settings"], data);
      setApiKey("");
      toast({
        tone: "success",
        title: "配置已保存",
        description: data.enabled
          ? `当前使用 ${data.provider} · ${[data.use_chat && data.chat_model, data.use_image && data.model].filter(Boolean).join(" + ") || "未启用能力"}`
          : "当前使用系统默认模型",
      });
    },
    onError: (error) => toast({ tone: "danger", title: "保存失败", description: String(error) }),
  });

  const test = useMutation({
    mutationFn: api.testModelSettings,
    onSuccess: (result) => {
      setTestResult(result);
      toast({
        tone: result.ok ? "success" : "warning",
        title: result.ok ? "连接成功" : "连接失败",
        description: result.message,
      });
    },
    onError: (error) => toast({ tone: "danger", title: "验证失败", description: String(error) }),
  });

  const clearKey = useMutation({
    mutationFn: api.clearModelKey,
    onSuccess: (data) => {
      queryClient.setQueryData(["model-settings"], data);
      setApiKey("");
      toast({ tone: "info", title: "已清除本地保存的密钥" });
    },
  });

  const capabilities = settings.data?.capabilities;
  const dirty =
    settings.data !== undefined &&
    (enabled !== settings.data.enabled ||
      provider !== settings.data.provider ||
      baseUrl !== settings.data.base_url ||
      model !== settings.data.model ||
      chatModel !== settings.data.chat_model ||
      useChat !== settings.data.use_chat ||
      useImage !== settings.data.use_image ||
      size !== settings.data.size ||
      timeout !== settings.data.timeout ||
      apiKey.trim().length > 0);

  const activePreset = presets.data?.presets.find((item) => item.id === provider);

  return (
    <div className="mx-auto flex w-full max-w-[1100px] flex-col gap-5 px-4 py-5 md:px-6">
      <PageHeader
        overline="Model Settings"
        title="模型设置"
        description="接入第三方模型 API（OpenAI 兼容）：对话模型增强角色设定与提示词，图像模型生成概念原画；可随时切回系统默认管线"
        actions={
          <>
            <Button variant="secondary" icon="activity" loading={test.isPending} onClick={() => test.mutate()}>
              测试连接
            </Button>
            <Button variant="primary" icon="download" loading={save.isPending} disabled={!dirty} onClick={() => save.mutate()}>
              保存配置
            </Button>
          </>
        }
      />

      {settings.isLoading ? (
        <Skeleton className="h-64" />
      ) : (
        <>
          <Card
            title="生成引擎"
            icon="spark"
            right={
              <Badge tone={enabled ? "primary" : "neutral"}>
                <StatusDot tone={enabled ? "running" : "idle"} />
                {enabled ? `${activePreset?.label ?? provider}` : "系统默认模型"}
              </Badge>
            }
          >
            <div className="flex flex-wrap items-center justify-between gap-4">
              <div className="min-w-0">
                <div className="text-[13px] font-semibold">启用第三方模型</div>
                <p className="mt-1 max-w-2xl text-[12px] leading-[19px] text-ink-3">
                  开启后：先用对话模型增强提示词（MODEL_ENHANCE），再按需生成原画（MODEL_IMAGE）；
                  任一环节失败都会自动回退系统默认管线并记录 MODEL_FALLBACK，任务不会中断。
                </p>
              </div>
              <div className="flex items-center gap-3">
                <span className="text-xs text-ink-3">{enabled ? "已启用" : "已关闭"}</span>
                <Switch checked={enabled} onChange={setEnabled} label="启用第三方模型" />
              </div>
            </div>

            <div className="mt-4">
              <div className="mb-2 text-[10.5px] font-semibold uppercase tracking-[0.08em] text-ink-4">
                厂商预设
              </div>
              <div className="flex flex-wrap gap-2">
                {(presets.data?.presets ?? []).map((preset) => (
                  <button
                    key={preset.id}
                    onClick={() => applyPreset(preset)}
                    className={cx(
                      "rounded-lg border px-3 py-1.5 text-[12.5px] transition-colors",
                      provider === preset.id
                        ? "border-primary/50 bg-primary-tint font-semibold text-primary"
                        : "border-line-subtle bg-surface-1 text-ink-2 hover:border-line hover:text-ink",
                    )}
                  >
                    {preset.label}
                  </button>
                ))}
              </div>
              {activePreset?.note && (
                <p className="mt-2 text-[11.5px] leading-[18px] text-ink-3">{activePreset.note}</p>
              )}
            </div>

            {enabled && capabilities && (
              <div className="mt-3 flex flex-wrap items-center gap-2">
                <Badge tone={capabilities.chat ? "success" : "neutral"} icon="activity">
                  提示词增强 {capabilities.chat ? "已就绪" : "未配置"}
                </Badge>
                <Badge tone={capabilities.image ? "success" : "neutral"} icon="spark">
                  原画生成 {capabilities.image ? "已就绪" : "未配置"}
                </Badge>
                {!capabilities.image && (
                  <span className="text-[11.5px] text-ink-3">
                    未配置图像模型时，原画由系统默认矢量管线产出。
                  </span>
                )}
              </div>
            )}
            {settings.data?.env_override && (
              <div className="mt-3 flex items-center gap-2 rounded-md border border-warning/30 bg-warning/10 px-3 py-2 text-[11.5px] text-warning">
                <Icon name="alert" className="h-3.5 w-3.5" />
                检测到环境变量 CF_MODEL_API_KEY / CF_MODEL_BASE_URL，环境变量优先生效。
              </div>
            )}
          </Card>

          <Card title="API 配置" icon="terminal" bodyClassName="p-5">
            <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
              <label className="flex flex-col gap-1.5">
                <span className="text-xs text-ink-3">API 地址 Base URL</span>
                <Input
                  icon="external"
                  value={baseUrl}
                  onChange={(event) => setBaseUrl(event.target.value)}
                  placeholder="https://api.deepseek.com/v1"
                  spellCheck={false}
                />
                <span className="text-[11px] text-ink-4">
                  DeepSeek 官方填 https://api.deepseek.com/v1；可填根地址或完整的 /v1/... 路径。
                </span>
              </label>

              <label className="flex flex-col gap-1.5">
                <span className="text-xs text-ink-3">API 密钥 API Key</span>
                <Input
                  icon="check"
                  type="password"
                  value={apiKey}
                  onChange={(event) => setApiKey(event.target.value)}
                  placeholder={
                    settings.data?.has_key
                      ? `已保存 ${settings.data.key_hint}（留空表示不修改）`
                      : "sk-..."
                  }
                  autoComplete="off"
                  spellCheck={false}
                />
                <span className="text-[11px] text-ink-4">
                  密钥不会再返回给前端；仅保存在本机 data 目录。
                </span>
              </label>

              <label className="flex flex-col gap-1.5">
                <span className="flex items-center justify-between text-xs text-ink-3">
                  对话模型 Chat Model
                  <span className="flex items-center gap-2 text-[11px] text-ink-4">
                    提示词增强
                    <Switch checked={useChat} onChange={setUseChat} label="提示词增强" />
                  </span>
                </span>
                <Input
                  icon="activity"
                  value={chatModel}
                  onChange={(event) => setChatModel(event.target.value)}
                  list="cf-chat-suggestions"
                  placeholder="deepseek-chat"
                  spellCheck={false}
                />
                <datalist id="cf-chat-suggestions">
                  {CHAT_SUGGESTIONS.map((item) => (
                    <option key={item} value={item} />
                  ))}
                </datalist>
              </label>

              <label className="flex flex-col gap-1.5">
                <span className="flex items-center justify-between text-xs text-ink-3">
                  图像模型 Image Model
                  <span className="flex items-center gap-2 text-[11px] text-ink-4">
                    生成原画
                    <Switch checked={useImage} onChange={setUseImage} label="生成原画" />
                  </span>
                </span>
                <Input
                  icon="spark"
                  value={model}
                  onChange={(event) => setModel(event.target.value)}
                  list="cf-image-suggestions"
                  placeholder="gpt-image-1 / FLUX.1-schnell（DeepSeek 官方无图像接口，可留空）"
                  spellCheck={false}
                />
                <datalist id="cf-image-suggestions">
                  {IMAGE_SUGGESTIONS.map((item) => (
                    <option key={item} value={item} />
                  ))}
                </datalist>
              </label>

              <label className="flex flex-col gap-1.5">
                <span className="text-xs text-ink-3">超时（秒）</span>
                <Input
                  icon="clock"
                  type="number"
                  min={5}
                  max={300}
                  value={timeout}
                  onChange={(event) => setTimeoutValue(Number(event.target.value) || 60)}
                />
              </label>

              <div className="flex flex-col gap-1.5 md:col-span-2">
                <span className="text-xs text-ink-3">输出尺寸 Size（仅图像模型）</span>
                <Segmented options={SIZES} value={size} onChange={setSize as (value: string) => void} />
              </div>
            </div>

            <div className="mt-5 flex flex-wrap items-center gap-2 border-t border-line-subtle pt-4">
              <Button
                variant="secondary"
                size="sm"
                icon="refresh"
                loading={test.isPending}
                onClick={() => test.mutate()}
              >
                验证密钥
              </Button>
              <Button
                variant="ghost"
                size="sm"
                icon="x"
                loading={clearKey.isPending}
                disabled={!settings.data?.has_key}
                onClick={() => clearKey.mutate()}
              >
                清除已保存密钥
              </Button>
              {testResult && (
                <span
                  className={cx(
                    "ml-auto inline-flex items-center gap-2 text-[12px]",
                    testResult.ok ? "text-success" : "text-danger",
                  )}
                >
                  <Icon name={testResult.ok ? "check" : "alert"} className="h-3.5 w-3.5" />
                  {testResult.message}
                  {testResult.latency_ms !== undefined && (
                    <span className="font-mono text-ink-3">{testResult.latency_ms}ms</span>
                  )}
                </span>
              )}
            </div>
            {testResult?.models && testResult.models.length > 0 && (
              <div className="mt-3 flex flex-wrap gap-1.5">
                {testResult.models.slice(0, 16).map((item) => (
                  <button
                    key={item}
                    onClick={() => {
                      if (/image|flux|cogview|dall|sd|stable/i.test(item)) setModel(item);
                      else setChatModel(item);
                    }}
                    title="点击填入：含 image/flux 等关键词的填入图像模型，其余填入对话模型"
                    className="rounded-sm border border-line-subtle bg-surface-2 px-2 py-0.5 font-mono text-[11px] text-ink-2 transition-colors hover:border-primary/50 hover:text-primary"
                  >
                    {item}
                  </button>
                ))}
              </div>
            )}
          </Card>

          <div className="grid grid-cols-1 gap-5 lg:grid-cols-2">
            <Card title="DeepSeek 接入说明" icon="book">
              <ul className="space-y-2.5 text-[12.5px] leading-5 text-ink-2">
                <li className="flex gap-2.5">
                  <Icon name="check" className="mt-0.5 h-4 w-4 shrink-0 text-primary" />
                  <span>
                    官方 API 兼容 OpenAI 协议：地址{" "}
                    <span className="font-mono">https://api.deepseek.com/v1</span>，模型{" "}
                    <span className="font-mono">deepseek-chat</span> /{" "}
                    <span className="font-mono">deepseek-reasoner</span>。
                  </span>
                </li>
                <li className="flex gap-2.5">
                  <Icon name="check" className="mt-0.5 h-4 w-4 shrink-0 text-primary" />
                  <span>
                    DeepSeek 目前是文本模型：用于把口语化需求扩写成专业美术提示词，
                    角色结构、调色板、三视图与工程包仍由系统管线产出。
                  </span>
                </li>
                <li className="flex gap-2.5">
                  <Icon name="check" className="mt-0.5 h-4 w-4 shrink-0 text-primary" />
                  <span>
                    若你使用支持图像的聚合网关（如硅基流动 / 智谱 / 自建 NewAPI），
                    在预设里选对应厂商，同时开启「生成原画」即可用 FLUX / CogView 等出图。
                  </span>
                </li>
              </ul>
            </Card>

            <Card title="数据安全" icon="check">
              <ul className="space-y-2.5 text-[12.5px] leading-5 text-ink-2">
                <li className="flex gap-2.5">
                  <Icon name="check" className="mt-0.5 h-4 w-4 shrink-0 text-success" />
                  密钥不会通过任何接口返回，页面只显示 sk-****最后四位。
                </li>
                <li className="flex gap-2.5">
                  <Icon name="check" className="mt-0.5 h-4 w-4 shrink-0 text-success" />
                  配置保存在本机 studio/backend/data（已加入 .gitignore），仅进程可读。
                </li>
                <li className="flex gap-2.5">
                  <Icon name="check" className="mt-0.5 h-4 w-4 shrink-0 text-success" />
                  支持环境变量 CF_MODEL_API_KEY / CF_MODEL_BASE_URL，无需落盘。
                </li>
                <li className="flex gap-2.5">
                  <Icon name="check" className="mt-0.5 h-4 w-4 shrink-0 text-success" />
                  增强后的提示词与原画都会写入资产和历史，可追溯来源模型。
                </li>
              </ul>
              <Button
                variant="secondary"
                size="sm"
                icon="spark"
                className="mt-4"
                onClick={() => navigate("/")}
              >
                去工作台生成
              </Button>
            </Card>
          </div>
        </>
      )}
    </div>
  );
}

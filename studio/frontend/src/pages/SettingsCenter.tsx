import { useEffect, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../api/client";
import { toast } from "../stores/toastStore";
import {
  Badge,
  Button,
  Card,
  Input,
  KV,
  PageHeader,
  Select,
  Skeleton,
  Switch,
} from "../components/ui";
import { Icon } from "../components/icons";
import type { ModelSettings, ProviderPreset } from "../types";

interface FormState {
  enabled: boolean;
  provider: string;
  base_url: string;
  model: string;
  chat_model: string;
  use_chat: boolean;
  use_image: boolean;
  size: string;
  timeout: number;
}

function toForm(settings: ModelSettings): FormState {
  return {
    enabled: settings.enabled,
    provider: settings.provider,
    base_url: settings.base_url,
    model: settings.model,
    chat_model: settings.chat_model,
    use_chat: settings.use_chat,
    use_image: settings.use_image,
    size: settings.size,
    timeout: settings.timeout,
  };
}

function applyPreset(form: FormState, preset: ProviderPreset): FormState {
  return {
    ...form,
    provider: preset.id,
    base_url: preset.base_url,
    model: preset.model,
    chat_model: preset.chat_model,
  };
}

export default function SettingsCenter() {
  const queryClient = useQueryClient();
  const settings = useQuery({
    queryKey: ["model-settings"],
    queryFn: api.getModelSettings,
  });
  const presets = useQuery({
    queryKey: ["model-presets"],
    queryFn: api.getModelPresets,
    staleTime: Infinity,
  });

  const [form, setForm] = useState<FormState | null>(null);
  const [apiKey, setApiKey] = useState("");
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(false);
  const [testResult, setTestResult] = useState<{ ok: boolean; text: string } | null>(null);

  useEffect(() => {
    if (settings.data && !form) setForm(toForm(settings.data));
  }, [settings.data, form]);

  async function persist(): Promise<ModelSettings> {
    if (!form) throw new Error("表单未就绪");
    const payload: Record<string, unknown> = { ...form };
    if (apiKey.trim()) payload.api_key = apiKey.trim();
    const next = await api.saveModelSettings(payload as Parameters<typeof api.saveModelSettings>[0]);
    queryClient.setQueryData(["model-settings"], next);
    setForm(toForm(next));
    setApiKey("");
    return next;
  }

  async function save() {
    if (!form || saving) return;
    setSaving(true);
    try {
      const next = await persist();
      toast({
        tone: "success",
        title: "模型设置已保存",
        description: next.enabled ? `自定义模型 ${next.model || "(未填 model)"} 将用于原画与提示词增强` : "已回到系统默认离线管线",
      });
    } catch (cause) {
      toast({ tone: "danger", title: "保存失败", description: String(cause) });
    } finally {
      setSaving(false);
    }
  }

  async function test() {
    if (testing || !form) return;
    setTesting(true);
    setTestResult(null);
    try {
      // 后端只测已保存的配置：先静默落盘当前表单（含密钥），避免填了却报 not configured
      await persist();
      const result = await api.testModelSettings();
      const text = result.ok
        ? `连接成功${result.status ? ` · HTTP ${result.status}` : ""}${result.detail ? ` · ${result.detail}` : ""}`
        : result.detail && result.detail !== "not configured"
          ? result.detail
          : result.status
            ? `连接失败 · HTTP ${result.status}`
            : "未配置：请填写 Base URL 与 API Key（保存后自动重试）";
      setTestResult({ ok: result.ok, text });
      toast({
        tone: result.ok ? "success" : "danger",
        title: result.ok ? "连接成功" : "连接失败",
        description: text,
      });
    } catch (cause) {
      setTestResult({ ok: false, text: String(cause) });
      toast({ tone: "danger", title: "连接失败", description: String(cause) });
    } finally {
      setTesting(false);
    }
  }

  async function clearKey() {
    try {
      const next = await api.clearModelKey();
      queryClient.setQueryData(["model-settings"], next);
      setApiKey("");
      toast({ tone: "success", title: "已清除后端保存的 API Key" });
    } catch (cause) {
      toast({ tone: "danger", title: "删除失败", description: String(cause) });
    }
  }

  if (settings.isLoading || !form) {
    return (
      <div className="mx-auto flex w-full max-w-[1440px] flex-col gap-5 px-4 py-5 md:px-6">
        <PageHeader overline="Model Settings" title="模型设置" description="正在读取当前配置…" />
        <div className="grid grid-cols-12 gap-5">
          <Skeleton className="col-span-12 h-40 lg:col-span-7" />
          <Skeleton className="col-span-12 h-40 lg:col-span-5" />
        </div>
      </div>
    );
  }

  const presetEntries = Object.entries(presets.data?.presets ?? {});
  const presetOptions = [
    { value: "custom", label: "自定义 / 手动填写" },
    ...presetEntries.map(([id, preset]) => ({ value: id, label: preset.label || id })),
  ];
  const activePreset = presetOptions.some((option) => option.value === form.provider)
    ? form.provider
    : "custom";
  const data = settings.data!;

  return (
    <div className="mx-auto flex w-full max-w-[1440px] flex-col gap-5 px-4 py-5 md:px-6">
      <PageHeader
        overline="Model Settings"
        title="模型设置"
        description="接入自定义大模型用于提示词增强与原画生成；未启用时使用确定性离线管线"
        actions={
          <Badge tone={data.enabled ? "primary" : "neutral"} icon={data.enabled ? "spark" : "cube"}>
            {data.enabled ? "自定义模型已启用" : "系统默认管线"}
          </Badge>
        }
      />

      <div className="grid grid-cols-12 gap-5">
        <div className="col-span-12 flex flex-col gap-5 lg:col-span-7">
          <Card title="启用与预设" icon="spark">
            <div className="flex items-center justify-between gap-4 py-1">
              <div>
                <div className="text-[13.5px] font-semibold text-ink">启用自定义模型</div>
                <p className="mt-0.5 text-[12px] text-ink-3">
                  关闭后始终使用离线确定性管线（无需网络与 Key）
                </p>
              </div>
              <Switch
                checked={form.enabled}
                onChange={(enabled) => setForm({ ...form, enabled })}
                label="启用自定义模型"
              />
            </div>
            <div className="mt-4">
              <div className="mb-1.5 text-[11px] font-semibold uppercase tracking-[0.08em] text-ink-4">
                服务商预设
              </div>
              <Select
                value={activePreset}
                options={presetOptions}
                onChange={(event) => {
                  const preset = presetEntries.find(([id]) => id === event.target.value)?.[1];
                  setForm((current) =>
                    preset && current
                      ? applyPreset({ ...current, provider: event.target.value }, { ...preset, id: event.target.value })
                      : current,
                  );
                }}
              />
              {activePreset !== "custom" &&
                (() => {
                  const preset = presetEntries.find(([id]) => id === activePreset)?.[1];
                  if (!preset) return null;
                  return (
                    <div className="mt-2 rounded-md border border-line-subtle bg-surface-1 p-2.5 text-[11.5px] leading-[18px] text-ink-3">
                      <span className="font-semibold text-ink-2">{preset.label}</span>
                      ：图像 <code className="font-mono">{preset.model || "—"}</code> · 对话{" "}
                      <code className="font-mono">{preset.chat_model || "—"}</code>
                      {preset.note && <span> · {preset.note}</span>}
                    </div>
                  );
                })()}
            </div>
          </Card>

          <Card title="连接配置" icon="terminal">
            <div className="grid grid-cols-1 gap-3.5 md:grid-cols-2">
              <label className="block">
                <span className="mb-1.5 block text-[11px] font-semibold uppercase tracking-[0.08em] text-ink-4">
                  Base URL
                </span>
                <Input
                  value={form.base_url}
                  onChange={(event) => setForm({ ...form, base_url: event.target.value })}
                  placeholder="https://api.example.com/v1"
                />
              </label>
              <label className="block">
                <span className="mb-1.5 block text-[11px] font-semibold uppercase tracking-[0.08em] text-ink-4">
                  图像模型 model
                </span>
                <Input
                  value={form.model}
                  onChange={(event) => setForm({ ...form, model: event.target.value })}
                  placeholder="image-model-name"
                />
              </label>
              <label className="block">
                <span className="mb-1.5 block text-[11px] font-semibold uppercase tracking-[0.08em] text-ink-4">
                  对话模型 chat_model
                </span>
                <Input
                  value={form.chat_model}
                  onChange={(event) => setForm({ ...form, chat_model: event.target.value })}
                  placeholder="chat-model-name"
                />
              </label>
              <label className="block">
                <span className="mb-1.5 block text-[11px] font-semibold uppercase tracking-[0.08em] text-ink-4">
                  生成尺寸 size
                </span>
                <Input
                  value={form.size}
                  onChange={(event) => setForm({ ...form, size: event.target.value })}
                  placeholder="1024x1024"
                />
              </label>
              <label className="block">
                <span className="mb-1.5 block text-[11px] font-semibold uppercase tracking-[0.08em] text-ink-4">
                  超时 timeout（秒）
                </span>
                <Input
                  type="number"
                  min={5}
                  max={600}
                  value={form.timeout}
                  onChange={(event) =>
                    setForm({ ...form, timeout: Number(event.target.value) || 60 })
                  }
                />
              </label>
              <div className="grid grid-cols-2 gap-3 self-end">
                <label className="flex items-center justify-between gap-2 rounded-md border border-line-subtle bg-surface-1 px-3 py-2">
                  <span className="text-[12px] text-ink-2">提示词增强</span>
                  <Switch
                    checked={form.use_chat}
                    onChange={(use_chat) => setForm({ ...form, use_chat })}
                  />
                </label>
                <label className="flex items-center justify-between gap-2 rounded-md border border-line-subtle bg-surface-1 px-3 py-2">
                  <span className="text-[12px] text-ink-2">图像生成</span>
                  <Switch
                    checked={form.use_image}
                    onChange={(use_image) => setForm({ ...form, use_image })}
                  />
                </label>
              </div>
            </div>
          </Card>

          <Card title="鉴权 API Key" icon="key">
            <div className="flex flex-wrap items-end gap-3">
              <label className="min-w-[240px] flex-1">
                <span className="mb-1.5 block text-[11px] font-semibold uppercase tracking-[0.08em] text-ink-4">
                  密钥（仅提交时发送，保存在后端本机）
                </span>
                <Input
                  type="password"
                  autoComplete="new-password"
                  value={apiKey}
                  onChange={(event) => setApiKey(event.target.value)}
                  placeholder="sk-…"
                  icon="key"
                />
              </label>
              <div className="flex gap-2">
                <Button variant="secondary" icon="x" onClick={clearKey}>
                  清除 Key
                </Button>
                <Button variant="secondary" icon="refresh" loading={testing} onClick={test}>
                  测试连接
                </Button>
                <Button variant="primary" icon="check" loading={saving} onClick={save}>
                  保存设置
                </Button>
              </div>
            </div>
            {testResult && (
              <div
                className={`mt-3 flex items-start gap-2 rounded-md border p-2.5 text-[12px] leading-[18px] ${
                  testResult.ok
                    ? "border-success/40 bg-success/10 text-ink-2"
                    : "border-danger/40 bg-danger/10 text-ink-2"
                }`}
              >
                <Icon
                  name={testResult.ok ? "check" : "alert"}
                  className={`mt-0.5 h-3.5 w-3.5 shrink-0 ${testResult.ok ? "text-success" : "text-danger"}`}
                />
                <span>{testResult.text}</span>
              </div>
            )}
          </Card>
        </div>

        <div className="col-span-12 flex flex-col gap-5 lg:col-span-5">
          <Card title="当前配置" icon="activity">
            <KV label="provider" value={data.provider || "—"} />
            <KV label="base_url" value={data.base_url || "—"} />
            <KV label="image model" value={data.model || "—"} />
            <KV label="chat model" value={data.chat_model || "—"} />
            <KV label="enabled" value={data.enabled ? "true" : "false"} />
            <KV label="size / timeout" value={`${data.size} · ${data.timeout}s`} />
          </Card>

          <Card title="工作方式" icon="book">
            <ul className="space-y-2.5 text-[12.5px] leading-[19px] text-ink-2">
              <li className="flex items-start gap-2.5">
                <Icon name="check" className="mt-0.5 h-4 w-4 shrink-0 text-success" />
                提示词增强：对话模型把自然语言目标改写为高质量图像提示词。
              </li>
              <li className="flex items-start gap-2.5">
                <Icon name="check" className="mt-0.5 h-4 w-4 shrink-0 text-success" />
                原画生成：图像模型产出原图，交给 PReCon 重建为 16 色像素资产。
              </li>
              <li className="flex items-start gap-2.5">
                <Icon name="check" className="mt-0.5 h-4 w-4 shrink-0 text-success" />
                调用失败会自动回退离线管线，任务不会中断（MODEL_FALLBACK 事件）。
              </li>
              <li className="flex items-start gap-2.5">
                <Icon name="alert" className="mt-0.5 h-4 w-4 shrink-0 text-warning" />
                Key 仅保存在后端本机 model_settings.json 中，页面不回显。
              </li>
            </ul>
          </Card>
        </div>
      </div>
    </div>
  );
}

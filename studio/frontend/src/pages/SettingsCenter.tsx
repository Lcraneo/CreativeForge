import { useEffect, useState, type ReactNode } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../api/client";
import { toast } from "../stores/toastStore";
import {
  Badge,
  Button,
  Card,
  Input,
  PageHeader,
  Select,
  Skeleton,
  Switch,
  cx,
} from "../components/ui";
import { Icon, type IconName } from "../components/icons";
import type { ModelSettings, ProviderPreset } from "../types";

interface FormState {
  enabled: boolean;
  provider: string;
  base_url: string;
  model: string;
  chat_model: string;
  edit_model: string;
  video_model: string;
  use_chat: boolean;
  use_image: boolean;
  use_video: boolean;
  size: string;
  negative_prompt: string;
  seed: string;
  prompt_extend: boolean;
  watermark: boolean;
  video_size: string;
  video_prompt_extend: boolean;
  timeout: number;
}

function toForm(settings: ModelSettings): FormState {
  return {
    enabled: settings.enabled,
    provider: settings.provider,
    base_url: settings.base_url,
    model: settings.model,
    chat_model: settings.chat_model,
    edit_model: settings.edit_model ?? "",
    video_model: settings.video_model ?? "",
    use_chat: settings.use_chat,
    use_image: settings.use_image,
    use_video: settings.use_video ?? true,
    size: settings.size,
    negative_prompt: settings.negative_prompt ?? "",
    seed: settings.seed ?? "",
    prompt_extend: settings.prompt_extend ?? false,
    watermark: settings.watermark ?? false,
    video_size: settings.video_size ?? "1280*720",
    video_prompt_extend: settings.video_prompt_extend ?? false,
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

/** 能力卡片：一个"用途"对应一个模型字段，凭证共用。 */
function Capability(props: {
  icon: IconName;
  name: string;
  purpose: string;
  support: string;
  modelValue: string;
  modelKey: "chat_model" | "model" | "edit_model" | "video_model";
  placeholder: string;
  enabled: boolean;
  onEnabled?: (value: boolean) => void;
  onModel: (value: string) => void;
  active: boolean;
  always?: boolean;
  extra?: ReactNode;
}) {
  const status = !props.active
    ? { label: "未启用（用离线内核）", tone: "neutral" as const }
    : props.always
      ? { label: "自动", tone: "primary" as const }
      : props.enabled
        ? { label: "启用", tone: "success" as const }
        : { label: "关闭", tone: "neutral" as const };
  return (
    <div className="rounded-xl border border-line-subtle bg-surface-1 p-3.5">
      <div className="flex items-start gap-3">
        <span className="mt-0.5 grid h-8 w-8 shrink-0 place-items-center rounded-lg bg-primary-tint text-primary">
          <Icon name={props.icon} className="h-4 w-4" />
        </span>
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-[13.5px] font-semibold text-ink">{props.name}</span>
            <Badge tone={status.tone}>{status.label}</Badge>
          </div>
          <p className="mt-0.5 text-[11.5px] leading-[17px] text-ink-3">{props.purpose}</p>
          <p className="mt-0.5 text-[11px] leading-[16px] text-ink-4">{props.support}</p>
        </div>
        {props.onEnabled && (
          <Switch checked={props.enabled} onChange={props.onEnabled} />
        )}
      </div>
      <label className="mt-3 block">
        <span className="mb-1 block text-[10.5px] font-semibold uppercase tracking-[0.08em] text-ink-4">
          模型 {props.modelKey}
        </span>
        <Input
          value={props.modelValue}
          onChange={(event) => props.onModel(event.target.value)}
          placeholder={props.placeholder}
        />
      </label>
      {props.extra && <div className="mt-3">{props.extra}</div>}
    </div>
  );
}

export default function SettingsCenter() {
  const queryClient = useQueryClient();
  const settings = useQuery({ queryKey: ["model-settings"], queryFn: api.getModelSettings });
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
        description: next.enabled
          ? "文本 / 图像 / 视频各能力已按上面选择的模型生效"
          : "已回到系统默认离线管线",
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
      toast({ tone: result.ok ? "success" : "danger", title: result.ok ? "连接成功" : "连接失败", description: text });
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
  const on = form.enabled;
  const videoProviderOk = /dashscope|aliyuncs|百炼/i.test(`${form.provider} ${form.base_url}`);

  const summary: Array<{ label: string; model: string; on: boolean; note?: string }> = [
    { label: "文本 · 提示词增强", model: form.chat_model || "—", on: on && form.use_chat },
    { label: "图像 · 原画生成", model: form.model || "—", on: on && form.use_image },
    { label: "图像编辑 · 三视图/抠图", model: form.edit_model || "服务商默认（自动）", on },
    { label: "视频 · 图生视频", model: form.video_model || "服务商默认", on: on && form.use_video, note: videoProviderOk ? "百炼" : "仅百炼支持" },
  ];

  return (
    <div className="mx-auto flex w-full max-w-[1440px] flex-col gap-5 px-4 py-5 md:px-6">
      <PageHeader
        overline="Model Settings"
        title="模型设置"
        description="按“用途”为每个能力选择模型；Base URL 与 API Key 只需配置一次，全部能力共用"
        actions={
          <Badge tone={data.enabled ? "primary" : "neutral"} icon={data.enabled ? "spark" : "cube"}>
            {data.enabled ? "自定义模型已启用" : "系统默认管线"}
          </Badge>
        }
      />

      <div className="grid grid-cols-12 gap-5">
        <div className="col-span-12 flex flex-col gap-5 lg:col-span-7">
          {/* 连接（所有能力共用） */}
          <Card title="连接（所有能力共用）" icon="terminal">
            <div className="flex items-center justify-between gap-4 rounded-lg border border-line-subtle bg-surface-1 px-3 py-2.5">
              <div>
                <div className="text-[13px] font-semibold text-ink">启用自定义模型</div>
                <p className="mt-0.5 text-[11.5px] text-ink-3">关闭后所有能力回退离线确定性管线（无需网络与 Key）</p>
              </div>
              <Switch checked={form.enabled} onChange={(enabled) => setForm({ ...form, enabled })} label="启用自定义模型" />
            </div>

            <div className="mt-4 grid grid-cols-1 gap-3.5 md:grid-cols-2">
              <label className="block">
                <span className="mb-1.5 block text-[11px] font-semibold uppercase tracking-[0.08em] text-ink-4">服务商预设</span>
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
              </label>
              <label className="block">
                <span className="mb-1.5 block text-[11px] font-semibold uppercase tracking-[0.08em] text-ink-4">Base URL（共用）</span>
                <Input
                  value={form.base_url}
                  onChange={(event) => setForm({ ...form, base_url: event.target.value })}
                  placeholder="https://api.example.com/v1"
                />
              </label>
              <label className="block md:col-span-2">
                <span className="mb-1.5 block text-[11px] font-semibold uppercase tracking-[0.08em] text-ink-4">
                  API Key（共用 · 仅提交时发送，存后端本机）
                </span>
                <Input
                  type="password"
                  autoComplete="new-password"
                  value={apiKey}
                  onChange={(event) => setApiKey(event.target.value)}
                  placeholder={data.has_key ? `已保存 ${data.key_hint}（留空保持不变）` : "sk-…"}
                  icon="key"
                />
              </label>
              <label className="block">
                <span className="mb-1.5 block text-[11px] font-semibold uppercase tracking-[0.08em] text-ink-4">生成尺寸 size</span>
                <Input value={form.size} onChange={(event) => setForm({ ...form, size: event.target.value })} placeholder="1024x1024" />
              </label>
              <label className="block">
                <span className="mb-1.5 block text-[11px] font-semibold uppercase tracking-[0.08em] text-ink-4">超时 timeout（秒）</span>
                <Input
                  type="number"
                  min={5}
                  max={600}
                  value={form.timeout}
                  onChange={(event) => setForm({ ...form, timeout: Number(event.target.value) || 60 })}
                />
              </label>
            </div>

            {activePreset !== "custom" &&
              (() => {
                const preset = presetEntries.find(([id]) => id === activePreset)?.[1];
                if (!preset) return null;
                return (
                  <div className="mt-3 rounded-md border border-line-subtle bg-surface-1 p-2.5 text-[11.5px] leading-[18px] text-ink-3">
                    <span className="font-semibold text-ink-2">{preset.label}</span>
                    ：文本 <code className="font-mono">{preset.chat_model || "—"}</code> · 图像{" "}
                    <code className="font-mono">{preset.model || "—"}</code>
                    {preset.note && <span> · {preset.note}</span>}
                  </div>
                );
              })()}

            <div className="mt-3 flex flex-wrap items-center gap-2">
              <Button variant="secondary" icon="x" onClick={clearKey}>
                清除 Key
              </Button>
              <Button variant="secondary" icon="refresh" loading={testing} onClick={test}>
                测试连接
              </Button>
              <Button variant="primary" icon="check" loading={saving} onClick={save}>
                保存设置
              </Button>
              {testResult && (
                <span className={cx("text-[12px]", testResult.ok ? "text-success" : "text-danger")}>{testResult.text}</span>
              )}
            </div>
          </Card>

          {/* 能力 → 模型 */}
          <Card title="能力 → 模型（共用上面的地址与 Key）" icon="layers">
            <div className="grid grid-cols-1 gap-3">
              <Capability
                icon="terminal"
                name="文本 · 提示词增强"
                purpose="用对话模型把自然语言目标改写为高质量图像提示词。"
                support="支持任意 OpenAI 兼容服务商。"
                modelKey="chat_model"
                modelValue={form.chat_model}
                placeholder="如 qwen3-omni-flash / gpt-4o-mini"
                enabled={form.use_chat}
                onEnabled={(use_chat) => setForm({ ...form, use_chat })}
                onModel={(value) => setForm({ ...form, chat_model: value })}
                active={on}
              />
              <Capability
                icon="grid"
                name="图像 · 原画生成"
                purpose="用图像模型产出原画，交给 PReCon 重建为游戏资产。"
                support="支持任意 OpenAI 兼容服务商（/images/generations）。"
                modelKey="model"
                modelValue={form.model}
                placeholder="如 wanx2.1-t2i-turbo / gpt-image-1"
                enabled={form.use_image}
                onEnabled={(use_image) => setForm({ ...form, use_image })}
                onModel={(value) => setForm({ ...form, model: value })}
                active={on}
                extra={
                  <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
                    <label className="block md:col-span-2">
                      <span className="mb-1 block text-[10.5px] font-semibold uppercase tracking-[0.08em] text-ink-4">
                        负面提示词 negative_prompt（百炼生效）
                      </span>
                      <Input
                        value={form.negative_prompt}
                        onChange={(event) => setForm({ ...form, negative_prompt: event.target.value })}
                        placeholder="lowres, bad hands, extra fingers, watermark, ..."
                      />
                    </label>
                    <label className="block">
                      <span className="mb-1 block text-[10.5px] font-semibold uppercase tracking-[0.08em] text-ink-4">
                        固定种子 seed（留空 = 随机）
                      </span>
                      <Input
                        value={form.seed}
                        onChange={(event) => setForm({ ...form, seed: event.target.value })}
                        placeholder="如 1234"
                      />
                    </label>
                    <div className="flex flex-col justify-end gap-2">
                      <label className="flex items-center justify-between gap-2 rounded-md border border-line-subtle px-3 py-2">
                        <span className="text-[12px] text-ink-2">平台改写提示词 prompt_extend</span>
                        <Switch
                          checked={form.prompt_extend}
                          onChange={(prompt_extend) => setForm({ ...form, prompt_extend })}
                        />
                      </label>
                      <label className="flex items-center justify-between gap-2 rounded-md border border-line-subtle px-3 py-2">
                        <span className="text-[12px] text-ink-2">添加水印 watermark</span>
                        <Switch checked={form.watermark} onChange={(watermark) => setForm({ ...form, watermark })} />
                      </label>
                    </div>
                  </div>
                }
              />
              <Capability
                icon="refresh"
                name="图像编辑 · 三视图 / 抠图"
                purpose="生成侧/背三视图与主体分割（动作动画受益）。"
                support="百炼：qwen-image-edit → wanx2.1-imageedit 回退；其他服务商不支持时自动回退离线。"
                modelKey="edit_model"
                modelValue={form.edit_model}
                placeholder="留空 = 服务商默认（qwen-image-edit）"
                enabled
                onModel={(value) => setForm({ ...form, edit_model: value })}
                active={on}
                always
              />
              <Capability
                icon="film"
                name="视频 · 图生视频（i2v）"
                purpose="让当前角色原画动起来，再抽帧合成为动画。"
                support={`当前仅支持阿里百炼 DashScope（wan2.2-i2v-flash / wanx2.1-i2v-turbo）${videoProviderOk ? "" : "，当前服务商不是百炼，将不可用"}。`}
                modelKey="video_model"
                modelValue={form.video_model}
                placeholder="留空 = wan2.2-i2v-flash"
                enabled={form.use_video}
                onEnabled={(use_video) => setForm({ ...form, use_video })}
                onModel={(value) => setForm({ ...form, video_model: value })}
                active={on}
                extra={
                  <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
                    <label className="block">
                      <span className="mb-1 block text-[10.5px] font-semibold uppercase tracking-[0.08em] text-ink-4">
                        视频尺寸 video_size
                      </span>
                      <Input
                        value={form.video_size}
                        onChange={(event) => setForm({ ...form, video_size: event.target.value })}
                        placeholder="1280*720"
                      />
                    </label>
                    <label className="flex items-center justify-between gap-2 self-end rounded-md border border-line-subtle px-3 py-2">
                      <span className="text-[12px] text-ink-2">视频平台改写 prompt_extend</span>
                      <Switch
                        checked={form.video_prompt_extend}
                        onChange={(video_prompt_extend) => setForm({ ...form, video_prompt_extend })}
                      />
                    </label>
                  </div>
                }
              />
            </div>
          </Card>
        </div>

        <div className="col-span-12 flex flex-col gap-5 lg:col-span-5">
          <Card title="能力 → 模型 对照" icon="check" right={<Badge tone={data.enabled ? "primary" : "neutral"}>{data.enabled ? "启用中" : "离线"}</Badge>}>
            <ul className="space-y-2.5">
              {summary.map((row) => (
                <li key={row.label} className="flex items-center gap-3 rounded-md border border-line-subtle bg-surface-1 px-3 py-2">
                  <span className={cx("h-2 w-2 shrink-0 rounded-full", row.on ? "bg-success" : "bg-ink-4/40")} />
                  <span className="min-w-0 flex-1">
                    <span className="block truncate text-[12.5px] text-ink-2">{row.label}</span>
                    <span className="block truncate font-mono text-[11px] text-ink-4">
                      {row.on ? row.model : "使用离线内核"}
                    </span>
                  </span>
                  {row.note && <span className="shrink-0 text-[10.5px] text-ink-4">{row.note}</span>}
                </li>
              ))}
            </ul>
            <div className="mt-3 border-t border-line-subtle pt-3 text-[11.5px] leading-[18px] text-ink-3">
              provider <code className="font-mono">{data.provider || "—"}</code> · base_url{" "}
              <code className="font-mono break-all">{data.base_url || "—"}</code>
            </div>
          </Card>

          <Card title="工作方式" icon="book">
            <ul className="space-y-2.5 text-[12.5px] leading-[19px] text-ink-2">
              <li className="flex items-start gap-2.5">
                <Icon name="check" className="mt-0.5 h-4 w-4 shrink-0 text-success" />
                一套 Base URL + API Key 同时供 <b>文本 / 图像 / 图像编辑 / 视频</b> 使用，无需分别填写。
              </li>
              <li className="flex items-start gap-2.5">
                <Icon name="check" className="mt-0.5 h-4 w-4 shrink-0 text-success" />
                每个能力独立选择模型；某能力关闭或调用失败时，仅该能力回退离线内核（MODEL_FALLBACK 事件），任务不中断。
              </li>
              <li className="flex items-start gap-2.5">
                <Icon name="alert" className="mt-0.5 h-4 w-4 shrink-0 text-warning" />
                视频（i2v）当前仅支持阿里百炼 DashScope；其他服务商即使填了 Key 也无法出视频。
              </li>
              <li className="flex items-start gap-2.5">
                <Icon name="key" className="mt-0.5 h-4 w-4 shrink-0 text-primary" />
                Key 仅保存在后端本机 model_settings.json，页面不回显。
              </li>
            </ul>
          </Card>
        </div>
      </div>
    </div>
  );
}

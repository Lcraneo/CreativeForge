import { useEffect, useMemo, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../api/client";
import { toast } from "../stores/toastStore";
import {
  Badge,
  Button,
  Card,
  Input,
  Select,
  Switch,
  cx,
} from "./ui";
import { Icon } from "./icons";
import {
  firstError,
  validateModelSettings,
  type SettingsScope,
} from "../lib/modelSettings";
import type { ModelSettings, ProviderPreset } from "../types";

/**
 * 统一的 API 配置面板（P1 任务 2）：
 * - 嵌入各工作台（scope=image → 工作台；scope=video → 动画工作台）
 * - 与「模型广场」（SettingsCenter）共享同一份 ["model-settings"] 数据源，
 *   保存后写回全局缓存并失效查询 → 双向同步、天然一致，无冲突可能
 * - 统一 UI/UX：字段、校验、保存/测试交互与模型广场完全一致
 */

interface PanelProps {
  scope: "image" | "video";
  title: string;
  contextNote: string;
  defaultCollapsed?: boolean;
}

interface PanelForm {
  enabled: boolean;
  provider: string;
  base_url: string;
  model: string;
  video_model: string;
  size: string;
  video_size: string;
  timeout: number;
}

export function ModelApiPanel({ scope, title, contextNote, defaultCollapsed = true }: PanelProps) {
  const queryClient = useQueryClient();
  const settings = useQuery({ queryKey: ["model-settings"], queryFn: api.getModelSettings });
  const presets = useQuery({
    queryKey: ["model-presets"],
    queryFn: api.getModelPresets,
    staleTime: Infinity,
  });

  const [collapsed, setCollapsed] = useState(defaultCollapsed);
  const [form, setForm] = useState<PanelForm | null>(null);
  const [apiKey, setApiKey] = useState("");
  const [dirty, setDirty] = useState(false);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(false);

  const data = settings.data;
  useEffect(() => {
    if (!data) return;
    setForm((current) => {
      if (current && dirty) return current; // 仅用户编辑中才不覆盖
      return {
        enabled: data.enabled,
        provider: data.provider,
        base_url: data.base_url,
        model: data.model,
        video_model: data.video_model ?? "",
        size: data.size,
        video_size: data.video_size ?? "1280*720",
        timeout: data.timeout,
      };
    });
  }, [data, dirty]);

  /** 统一的表单编辑入口：标记 dirty（编辑中不被远端覆盖）后打补丁 */
  function patchForm(patch: Partial<PanelForm>) {
    setDirty(true);
    setForm((current) => (current ? { ...current, ...patch } : current));
  }

  const presetEntries = useMemo(
    () => Object.entries(presets.data?.presets ?? {}),
    [presets.data],
  );
  const presetOptions = [
    { value: "custom", label: "自定义 / 手动填写" },
    ...presetEntries.map(([id, preset]) => ({ value: id, label: preset.label || id })),
  ];

  async function save(silent = false) {
    if (!form || saving) return;
    const payload: Record<string, unknown> = {
      enabled: form.enabled,
      provider: form.provider,
      base_url: form.base_url,
      timeout: form.timeout,
    };
    // 作用域字段裁剪：image 面板只提交图像相关；video 面板只提交视频相关
    if (scope === "image") {
      payload.model = form.model;
      payload.size = form.size;
      payload.use_image = true;
    } else {
      payload.video_model = form.video_model;
      payload.video_size = form.video_size;
      payload.use_video = true;
    }
    const scopedErrors = validateModelSettings(
      {
        enabled: form.enabled,
        base_url: form.base_url,
        api_key: apiKey || undefined,
        model: scope === "image" ? form.model : undefined,
        video_model: scope === "video" ? form.video_model : undefined,
        size: scope === "image" ? form.size : undefined,
        video_size: scope === "video" ? form.video_size : undefined,
        timeout: form.timeout,
      },
      scope === "image" ? "image" : "video",
    );
    if (Object.keys(scopedErrors).length > 0) {
      setErrors(scopedErrors);
      toast({ tone: "danger", title: "配置校验未通过", description: firstError(scopedErrors) ?? "" });
      return;
    }
    setErrors({});
    if (apiKey.trim()) payload.api_key = apiKey.trim();

    setSaving(true);
    try {
      const next = await api.saveModelSettings(payload as Parameters<typeof api.saveModelSettings>[0]);
      queryClient.setQueryData(["model-settings"], next);
      queryClient.invalidateQueries({ queryKey: ["model-settings"] });
      setApiKey("");
      setDirty(false);
      if (!silent) {
        toast({
          tone: "success",
          title: "API 配置已保存",
          description: "已同步至模型广场与本工作台，立即生效",
        });
      }
    } catch (cause) {
      toast({ tone: "danger", title: "保存失败", description: String(cause).slice(0, 200) });
    } finally {
      setSaving(false);
    }
  }

  async function test() {
    if (testing) return;
    setTesting(true);
    try {
      await save(true);
      const result = await api.testModelSettings();
      toast({
        tone: result.ok ? "success" : "danger",
        title: result.ok ? "连接成功" : "连接失败",
        description: result.detail || (result.ok ? `HTTP ${result.status ?? ""}` : "请检查 Base URL 与 Key"),
      });
    } catch (cause) {
      toast({ tone: "danger", title: "连接测试失败", description: String(cause).slice(0, 160) });
    } finally {
      setTesting(false);
    }
  }

  const on = form?.enabled ?? false;
  const activePreset =
    form && presetOptions.some((option) => option.value === form.provider)
      ? form.provider
      : "custom";
  const summary =
    scope === "image"
      ? `图像模型 ${form?.model || "—"} · ${form?.size || "—"}`
      : `视频模型 ${form?.video_model || "—"} · ${form?.video_size || "—"}`;

  return (
    <Card
      title={title}
      icon="terminal"
      right={
        <div className="flex items-center gap-1.5">
          <Badge tone={on ? "primary" : "neutral"}>
            {on ? "已启用" : "离线管线"}
          </Badge>
          <Button variant="ghost" size="sm" onClick={() => setCollapsed((c) => !c)}>
            {collapsed ? "展开配置" : "收起"}
          </Button>
        </div>
      }
    >
      {collapsed ? (
        <p className="flex items-center gap-2 text-[12px] text-ink-3">
          <Icon name="cube" className="h-3.5 w-3.5 text-ink-4" />
          {summary} —— 修改会双向同步至「模型广场」
        </p>
      ) : (
        <div className="flex flex-col gap-3.5">
          <p className="text-[11.5px] leading-[17px] text-ink-3">{contextNote}</p>

          <div className="flex items-center justify-between gap-4 rounded-lg border border-line-subtle bg-surface-1 px-3 py-2.5">
            <div>
              <div className="text-[13px] font-semibold text-ink">启用自定义模型</div>
              <p className="mt-0.5 text-[11.5px] text-ink-3">
                关闭后本工作台回退离线确定性管线（无需网络与 Key）
              </p>
            </div>
            <Switch
              checked={on}
              onChange={(enabled) => patchForm({ enabled })}
              label="启用自定义模型"
            />
          </div>

          <div className="grid grid-cols-1 gap-3.5 md:grid-cols-2">
            <label className="block">
              <span className="mb-1.5 block text-[11px] font-semibold uppercase tracking-[0.08em] text-ink-4">
                服务商预设
              </span>
              <Select
                value={activePreset}
                options={presetOptions}
                onChange={(event) => {
                  const preset = presetEntries.find(([id]) => id === event.target.value)?.[1] as
                    | (ProviderPreset & { id: string })
                    | undefined;
                  patchForm({
                    provider: event.target.value,
                    base_url: preset?.base_url ?? (form?.base_url ?? ""),
                    ...(scope === "image" && preset?.model ? { model: preset.model } : {}),
                  });
                }}
              />
            </label>
            <label className="block">
              <span className="mb-1.5 block text-[11px] font-semibold uppercase tracking-[0.08em] text-ink-4">
                Base URL
              </span>
              <Input
                value={form?.base_url ?? ""}
                onChange={(event) => patchForm({ base_url: event.target.value })}
                placeholder="https://dashscope.aliyuncs.com/compatible-mode/v1"
                className={errors.base_url ? "border-danger" : ""}
              />
              {errors.base_url && <span className="mt-1 block text-[11px] text-danger">{errors.base_url}</span>}
            </label>
            <label className="block">
              <span className="mb-1.5 block text-[11px] font-semibold uppercase tracking-[0.08em] text-ink-4">
                API Key（留空保持已保存的值）
              </span>
              <Input
                type="password"
                value={apiKey}
                onChange={(event) => {
                  setDirty(true);
                  setApiKey(event.target.value);
                }}
                placeholder={data?.enabled ? "已保存（不回显）· 输入新值覆盖" : "sk-..."}
                className={errors.api_key ? "border-danger" : ""}
              />
              {errors.api_key && <span className="mt-1 block text-[11px] text-danger">{errors.api_key}</span>}
            </label>
            <label className="block">
              <span className="mb-1.5 block text-[11px] font-semibold uppercase tracking-[0.08em] text-ink-4">
                {scope === "image" ? "图像模型 MODEL" : "视频模型 MODEL"}
              </span>
              <Input
                value={scope === "image" ? form?.model ?? "" : form?.video_model ?? ""}
                onChange={(event) =>
                  patchForm(
                    scope === "image"
                      ? { model: event.target.value }
                      : { video_model: event.target.value },
                  )
                }
                placeholder={scope === "image" ? "wanx2.1-t2i-turbo" : "wan2.2-i2v-flash"}
                className={errors.model || errors.video_model ? "border-danger" : ""}
              />
              {(scope === "image" ? errors.model : errors.video_model) && (
                <span className="mt-1 block text-[11px] text-danger">
                  {scope === "image" ? errors.model : errors.video_model}
                </span>
              )}
            </label>
            <label className="block">
              <span className="mb-1.5 block text-[11px] font-semibold uppercase tracking-[0.08em] text-ink-4">
                {scope === "image" ? "生图尺寸 SIZE" : "视频尺寸 SIZE"}
              </span>
              <Input
                value={scope === "image" ? form?.size ?? "" : form?.video_size ?? ""}
                onChange={(event) =>
                  patchForm(
                    scope === "image"
                      ? { size: event.target.value }
                      : { video_size: event.target.value },
                  )
                }
                placeholder={scope === "image" ? "1024x1024" : "1280*720"}
                className={errors.size || errors.video_size ? "border-danger" : ""}
              />
              {(scope === "image" ? errors.size : errors.video_size) && (
                <span className="mt-1 block text-[11px] text-danger">
                  {scope === "image" ? errors.size : errors.video_size}
                </span>
              )}
            </label>
            <label className="block">
              <span className="mb-1.5 block text-[11px] font-semibold uppercase tracking-[0.08em] text-ink-4">
                超时 TIMEOUT（秒）
              </span>
              <Input
                type="number"
                value={form?.timeout ?? 60}
                onChange={(event) => patchForm({ timeout: Number(event.target.value) })}
                className={errors.timeout ? "border-danger" : ""}
              />
              {errors.timeout && <span className="mt-1 block text-[11px] text-danger">{errors.timeout}</span>}
            </label>
          </div>

          <div className="flex flex-wrap items-center gap-2">
            <Button variant="primary" size="sm" icon="check" loading={saving} onClick={() => save()}>
              保存（同步模型广场）
            </Button>
            <Button variant="secondary" size="sm" icon="activity" loading={testing} onClick={test}>
              保存并测试连接
            </Button>
            <span className="text-[10.5px] text-ink-4">
              Key 仅保存在后端本机，页面不回显
            </span>
          </div>
        </div>
      )}
    </Card>
  );
}

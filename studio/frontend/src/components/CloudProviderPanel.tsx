import { useEffect, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../api/client";
import { toast } from "../stores/toastStore";
import { Badge, Button, Card, Input, Select, Switch } from "./ui";
import { Icon } from "./icons";
import type { CloudProvider } from "../types";

/**
 * 云生成能力面板（S4）：
 * - 与「模型广场」并列，独立维护「每厂商一条连接 + 独立密钥」
 * - ARK 复用模型广场的 volcengine Key（credential_ref），无需重复填写
 * - 保存后统一失效 ["cloud-providers"]，生成面与配置面读同一份存储
 */

const CAPABILITY_LABEL: Record<string, string> = {
  gen_3d_object_cloud: "3D 物体",
  gen_image_cloud: "图像",
  gen_cg_video_cloud: "CG 视频",
  gen_audio_cloud: "音频",
};

const KEY_SOURCE_LABEL: Record<string, string> = {
  env: "环境变量",
  store: "本机加密存储",
  credential_ref: "复用模型广场",
  "": "未配置",
};

function ProviderRow({ provider }: { provider: CloudProvider }) {
  const queryClient = useQueryClient();
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState({
    enabled: provider.enabled,
    base_url: provider.base_url,
    model: provider.model,
    workspace_id: provider.workspace_id,
  });
  const [apiKey, setApiKey] = useState("");
  const [dirty, setDirty] = useState(false);
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(false);

  useEffect(() => {
    if (dirty) return;
    setForm({
      enabled: provider.enabled,
      base_url: provider.base_url,
      model: provider.model,
      workspace_id: provider.workspace_id,
    });
  }, [provider.enabled, provider.base_url, provider.model, provider.workspace_id, dirty]);

  function patch(next: Partial<typeof form>) {
    setDirty(true);
    setForm((current) => ({ ...current, ...next }));
  }

  async function save(silent = false) {
    if (saving) return;
    setSaving(true);
    try {
      let latest = await api.cloudSaveProvider(provider.id, form);
      if (apiKey.trim()) {
        latest = await api.cloudSetKey(provider.id, apiKey.trim());
        setApiKey("");
      }
      setDirty(false);
      queryClient.setQueryData(
        ["cloud-providers"],
        (current: { providers?: CloudProvider[] } | undefined) =>
          current
            ? {
                ...current,
                providers: current.providers?.map((item) =>
                  item.id === latest.id ? latest : item,
                ),
              }
            : current,
      );
      queryClient.invalidateQueries({ queryKey: ["cloud-providers"] });
      if (!silent) {
        toast({ tone: "success", title: `${provider.label} 配置已保存` });
      }
    } catch (cause) {
      toast({ tone: "danger", title: "保存失败", description: String(cause).slice(0, 180) });
    } finally {
      setSaving(false);
    }
  }

  async function test() {
    if (testing) return;
    setTesting(true);
    try {
      await save(true);
      const result = await api.cloudTestProvider(provider.id);
      toast({
        tone: result.ok ? "success" : "danger",
        title: result.ok ? `${provider.label} 连接可用` : `${provider.label} 连接失败`,
        description: `${result.detail} · ${result.latency_ms}ms`,
      });
    } catch (cause) {
      toast({ tone: "danger", title: "探测失败", description: String(cause).slice(0, 180) });
    } finally {
      setTesting(false);
    }
  }

  const caps = provider.capabilities.map((cap) => CAPABILITY_LABEL[cap] ?? cap).join(" / ");

  return (
    <div className="rounded-lg border border-line-subtle bg-surface-1">
      <div className="flex flex-wrap items-center gap-2 px-3 py-2.5">
        <span
          className={
            "h-2 w-2 shrink-0 rounded-full " +
            (provider.configured ? "bg-success" : "bg-ink-4/40")
          }
        />
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-1.5">
            <span className="text-[13px] font-semibold text-ink">{provider.label}</span>
            <Badge tone={provider.enabled ? "primary" : "neutral"}>
              {provider.enabled ? "启用" : "停用"}
            </Badge>
            <Badge tone={provider.has_key ? "success" : "warning"}>
              {KEY_SOURCE_LABEL[provider.key_source] ?? provider.key_source}
            </Badge>
            {provider.missing_fields.length > 0 && (
              <Badge tone="warning">缺 {provider.missing_fields.join(" / ")}</Badge>
            )}
          </div>
          <div className="mt-0.5 truncate text-[11px] text-ink-4">
            {caps} · <code className="font-mono">{provider.model || "—"}</code> · 优先级{" "}
            {provider.priority}
            {provider.price_note ? ` · ${provider.price_note}` : ""}
          </div>
        </div>
        <Button variant="ghost" size="sm" onClick={() => setOpen((value) => !value)}>
          {open ? "收起" : "配置"}
        </Button>
      </div>

      {open && (
        <div className="flex flex-col gap-3 border-t border-line-subtle px-3 py-3">
          <p className="text-[11.5px] leading-[17px] text-ink-3">{provider.notes}</p>

          <label className="flex items-center justify-between gap-3 rounded-md border border-line-subtle px-3 py-2">
            <span className="text-[12.5px] text-ink-2">启用该厂商</span>
            <Switch
              checked={form.enabled}
              onChange={(enabled) => patch({ enabled })}
              label={`启用 ${provider.label}`}
            />
          </label>

          <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
            <label className="block md:col-span-2">
              <span className="mb-1.5 block text-[11px] font-semibold uppercase tracking-[0.08em] text-ink-4">
                Base URL
              </span>
              <Input
                value={form.base_url}
                onChange={(event) => patch({ base_url: event.target.value })}
                placeholder="https://..."
              />
            </label>

            <label className="block">
              <span className="mb-1.5 block text-[11px] font-semibold uppercase tracking-[0.08em] text-ink-4">
                模型 MODEL
              </span>
              {provider.model_options.length > 0 ? (
                <Select
                  value={form.model}
                  options={provider.model_options.map((option) => ({ value: option, label: option }))}
                  onChange={(event) => patch({ model: event.target.value })}
                />
              ) : (
                <Input
                  value={form.model}
                  onChange={(event) => patch({ model: event.target.value })}
                  placeholder="模型 ID 或推理接入点"
                />
              )}
            </label>

            {provider.extra_fields.includes("workspace_id") && (
              <label className="block">
                <span className="mb-1.5 block text-[11px] font-semibold uppercase tracking-[0.08em] text-ink-4">
                  业务空间 Workspace ID
                </span>
                <Input
                  value={form.workspace_id}
                  onChange={(event) => patch({ workspace_id: event.target.value })}
                  placeholder="百炼 3D 仅华北2地域，需填写业务空间 ID"
                />
              </label>
            )}

            <label className="block md:col-span-2">
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
                placeholder={
                  provider.has_key
                    ? `已保存 ${provider.key_hint}（不回显）· 输入新值覆盖`
                    : `未配置 · 可填 ${provider.env_keys.join(" / ")} 或直接写入`
                }
              />
            </label>
          </div>

          <div className="flex flex-wrap items-center gap-2">
            <Button variant="primary" size="sm" icon="check" loading={saving} onClick={() => save()}>
              保存
            </Button>
            <Button
              variant="secondary"
              size="sm"
              icon="activity"
              loading={testing}
              onClick={test}
            >
              保存并测试连通性
            </Button>
            <span className="flex items-center gap-1 text-[10.5px] text-ink-4">
              <Icon name="key" className="h-3 w-3" />
              Key 仅加密保存在后端本机，页面不回显
            </span>
          </div>
        </div>
      )}
    </div>
  );
}

export function CloudProviderPanel() {
  const providers = useQuery({
    queryKey: ["cloud-providers"],
    queryFn: api.cloudProviders,
    staleTime: 15_000,
  });

  const data = providers.data;
  const list = data?.providers ?? [];
  const readiness = data?.readiness ?? {};

  return (
    <Card
      title="云生成能力（3D / 图像 / 视频 / 音频）"
      icon="cube"
      right={
        <Badge tone={data?.enabled ? "primary" : "neutral"}>
          {data?.enabled ? "已启用" : "总开关关闭"}
        </Badge>
      }
    >
      {providers.isLoading ? (
        <p className="text-[12px] text-ink-3">正在读取云厂商配置…</p>
      ) : providers.isError ? (
        <p className="text-[12px] text-danger">
          读取失败：{String(providers.error).slice(0, 160)}
        </p>
      ) : (
        <div className="flex flex-col gap-3">
          <div className="flex flex-wrap gap-1.5">
            {Object.entries(readiness).map(([capability, ready]) => (
              <Badge key={capability} tone={ready ? "success" : "neutral"}>
                {CAPABILITY_LABEL[capability] ?? capability} · {ready ? "可用" : "未配置"}
              </Badge>
            ))}
          </div>

          <p className="text-[11.5px] leading-[17px] text-ink-3">
            云厂商与「模型广场」是两套独立连接：这里按能力（3D / 图像 / 视频 / 音频）分别配置，
            方舟 ARK 默认复用模型广场的 volcengine Key。总开关关闭时
            （<code className="font-mono">CF_CLOUD_BACKENDS=off</code>）云能力不注册，系统行为与融合前一致。
          </p>

          <div className="flex flex-col gap-2">
            {list.map((provider) => (
              <ProviderRow key={provider.id} provider={provider} />
            ))}
          </div>

          {data?.config && (
            <div className="border-t border-line-subtle pt-2 text-[10.5px] leading-[16px] text-ink-4">
              缓存目录 <code className="font-mono break-all">{data.config.cache_dir}</code> · TTL{" "}
              {data.config.cache_ttl_days} 天 · 上限 {data.config.cache_max_mb} MB · 超时{" "}
              {data.config.timeout}s · 重试 {data.config.max_retries} 次
            </div>
          )}
        </div>
      )}
    </Card>
  );
}

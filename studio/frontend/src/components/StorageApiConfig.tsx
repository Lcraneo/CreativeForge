import { useEffect, useMemo, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../api/client";
import { toast } from "../stores/toastStore";
import {
  Badge,
  Button,
  Card,
  EmptyState,
  Input,
  Select,
  Switch,
  cx,
} from "./ui";
import { Icon } from "./icons";
import type {
  StorageConfigPublic,
  StorageProviderPreset,
} from "../types";

interface FormState {
  id: string | null;            // null = 新增
  name: string;
  provider: string;
  access_key: string;            // 编辑时空串 = 保持原值
  secret_key: string;
  region: string;
  bucket: string;
  endpoint: string;
  is_default: boolean;
}

const EMPTY_FORM: FormState = {
  id: null, name: "", provider: "kodo", access_key: "", secret_key: "",
  region: "cn-east-1", bucket: "", endpoint: "", is_default: false,
};

const PROVIDER_LABELS: Record<string, string> = {
  oss: "阿里云 OSS", cos: "腾讯云 COS", kodo: "七牛云 Kodo",
  obs: "华为云 OBS", tos: "火山引擎 TOS", bos: "百度智能云 BOS",
};

/**
 * 动画工作台「云存储」面板：六厂商对象存储 API 配置的 CRUD + 设默认 + 连通性测试。
 *
 * 安全约束（与 SettingsCenter 同源模式）：
 *  - SecretId / SecretKey 走密码框，**只写不回显**；编辑时空串表示保持原值；
 *  - 列表展示一律脱敏（后端返回 mask_secret 后的值）；
 *  - 凭证本地加密存储，前端永不在日志/控制台打印。
 */
export default function StorageApiConfig() {
  const queryClient = useQueryClient();
  const configs = useQuery({
    queryKey: ["storage-configs"],
    queryFn: api.listStorageConfigs,
  });

  const [form, setForm] = useState<FormState | null>(null);
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(false);
  const [testResult, setTestResult] = useState<{ ok: boolean; text: string } | null>(null);

  useEffect(() => {
    if (configs.data && !form) setForm(EMPTY_FORM);
  }, [configs.data, form]);

  const presets = configs.data?.presets ?? {};
  const currentPreset: StorageProviderPreset | undefined = presets[form?.provider ?? "kodo"];
  const regionOptions = useMemo(() => {
    const regions = currentPreset?.regions ?? [];
    return regions.map((r) => ({ value: r, label: r }));
  }, [currentPreset]);

  function invalidate() {
    queryClient.invalidateQueries({ queryKey: ["storage-configs"] });
  }

  function edit(config: StorageConfigPublic) {
    setForm({
      id: config.id,
      name: config.name,
      provider: config.provider,
      access_key: "",
      secret_key: "",
      region: config.region,
      bucket: config.bucket,
      endpoint: config.endpoint,
      is_default: config.is_default,
    });
    setTestResult(null);
  }

  function resetForm() {
    setForm({ ...EMPTY_FORM });
    setTestResult(null);
  }

  async function save() {
    if (!form || saving) return;
    if (!form.name.trim() || !form.bucket.trim() || !form.region.trim()) {
      toast({ tone: "danger", title: "请补全必填项", description: "名称 / 厂商 / 地域 / Bucket 均必填" });
      return;
    }
    if (!form.id && (!form.access_key.trim() || !form.secret_key.trim())) {
      toast({ tone: "danger", title: "缺少凭证", description: "新增配置必须填写 SecretId / SecretKey" });
      return;
    }
    setSaving(true);
    try {
      const payload: Record<string, unknown> = {
        name: form.name.trim(),
        provider: form.provider,
        region: form.region,
        bucket: form.bucket.trim(),
        endpoint: form.endpoint.trim(),
        is_default: form.is_default,
      };
      if (form.access_key.trim()) payload.access_key = form.access_key.trim();
      if (form.secret_key.trim()) payload.secret_key = form.secret_key.trim();
      if (form.id) {
        await api.updateStorageConfig(form.id, payload);
      } else {
        await api.createStorageConfig(payload);
      }
      invalidate();
      resetForm();
      toast({ tone: "success", title: form.id ? "配置已更新" : "配置已新增", description: "凭证已加密落盘" });
    } catch (cause) {
      toast({ tone: "danger", title: "保存失败", description: String(cause) });
    } finally {
      setSaving(false);
    }
  }

  async function remove(config: StorageConfigPublic) {
    if (!confirm(`删除配置「${config.name}」？`)) return;
    try {
      await api.deleteStorageConfig(config.id);
      invalidate();
      if (form?.id === config.id) resetForm();
      toast({ tone: "success", title: "已删除配置", description: config.name });
    } catch (cause) {
      toast({ tone: "danger", title: "删除失败", description: String(cause) });
    }
  }

  async function setDefault(config: StorageConfigPublic) {
    try {
      await api.setDefaultStorageConfig(config.id);
      invalidate();
      toast({ tone: "success", title: "已设为默认", description: config.name });
    } catch (cause) {
      toast({ tone: "danger", title: "设置失败", description: String(cause) });
    }
  }

  async function test() {
    if (!form || testing) return;
    setTesting(true);
    setTestResult(null);
    try {
      const payload = {
        config_id: form.id ?? undefined,
        name: form.name || undefined,
        provider: form.provider,
        access_key: form.access_key.trim() || undefined,
        secret_key: form.secret_key.trim() || undefined,
        region: form.region,
        bucket: form.bucket.trim(),
        endpoint: form.endpoint.trim() || undefined,
      };
      const result = await api.testStorageConfig(payload);
      const text = result.ok
        ? `连接成功${result.latency_ms ? ` · ${result.latency_ms}ms` : ""}${result.detail ? ` · ${result.detail}` : ""}`
        : result.detail || "连接失败";
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

  if (configs.isLoading || !form) {
    return (
      <div className="h-40 animate-pulse rounded-xl border border-line-subtle bg-surface-2" />
    );
  }

  const list = configs.data?.configs ?? [];
  const isEditing = form.id !== null;

  return (
    <div className="grid grid-cols-12 gap-5">
        {/* 配置列表 */}
        <div className="col-span-12 flex flex-col gap-3 lg:col-span-5">
          <Card title="配置列表" icon="layers">
            {list.length === 0 ? (
              <EmptyState icon="package" title="还没有配置" description="右侧填写新增第一份配置" />
            ) : (
              <ul className="flex flex-col gap-2.5">
                {list.map((config) => (
                  <li
                    key={config.id}
                    className={cx(
                      "rounded-lg border bg-surface-1 p-3 transition-colors",
                      form.id === config.id ? "border-primary" : "border-line-subtle hover:border-line",
                    )}
                  >
                    <div className="flex items-start justify-between gap-2">
                      <div className="min-w-0">
                        <div className="flex items-center gap-1.5">
                          <span className="truncate text-[12.5px] font-semibold text-ink">{config.name}</span>
                          {config.is_default && (
                            <Badge tone="primary" icon="check">默认</Badge>
                          )}
                        </div>
                        <div className="mt-0.5 text-[11px] text-ink-3">
                          {PROVIDER_LABELS[config.provider] ?? config.provider} · {config.bucket}
                          {config.region ? ` · ${config.region}` : ""}
                        </div>
                        <div className="mt-0.5 font-mono text-[10px] text-ink-4">
                          {config.access_key || "（无凭证）"}
                        </div>
                      </div>
                    </div>
                    <div className="mt-2 flex flex-wrap gap-1.5">
                      <Button variant="secondary" className="px-2 py-1 text-[11px]" onClick={() => edit(config)}>
                        编辑
                      </Button>
                      {!config.is_default && (
                        <Button
                          variant="secondary"
                          icon="check"
                          className="px-2 py-1 text-[11px]"
                          onClick={() => setDefault(config)}
                        >
                          设为默认
                        </Button>
                      )}
                      <Button
                        variant="secondary"
                        icon="trash"
                        className="px-2 py-1 text-[11px] text-danger"
                        onClick={() => remove(config)}
                      />
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </Card>
        </div>

        {/* 配置表单 */}
        <div className="col-span-12 flex flex-col gap-5 lg:col-span-7">
          <Card title={isEditing ? "编辑配置" : "新增配置"} icon="terminal">
            <div className="grid grid-cols-1 gap-3.5 md:grid-cols-2">
              <label className="block">
                <span className="mb-1.5 block text-[11px] font-semibold uppercase tracking-[0.08em] text-ink-4">
                  配置名称
                </span>
                <Input
                  value={form.name}
                  onChange={(e) => setForm({ ...form, name: e.target.value })}
                  placeholder="如：七牛-生产桶"
                />
              </label>

              <label className="block">
                <span className="mb-1.5 block text-[11px] font-semibold uppercase tracking-[0.08em] text-ink-4">
                  服务商
                </span>
                <Select
                  value={form.provider}
                  options={Object.entries(presets).map(([id, p]) => ({
                    value: id,
                    label: p.label,
                  }))}
                  onChange={(e) => {
                    const provider = e.target.value;
                    const nextRegion = presets[provider]?.regions[0] ?? "";
                    setForm({ ...form, provider, region: nextRegion });
                  }}
                />
              </label>

              <label className="block">
                <span className="mb-1.5 block text-[11px] font-semibold uppercase tracking-[0.08em] text-ink-4">
                  地域 region
                </span>
                <Select
                  value={form.region}
                  options={regionOptions}
                  onChange={(e) => setForm({ ...form, region: e.target.value })}
                />
              </label>

              <label className="block">
                <span className="mb-1.5 block text-[11px] font-semibold uppercase tracking-[0.08em] text-ink-4">
                  Bucket
                </span>
                <Input
                  value={form.bucket}
                  onChange={(e) => setForm({ ...form, bucket: e.target.value })}
                  placeholder="bucket-name"
                />
              </label>

              <label className="block md:col-span-2">
                <span className="mb-1.5 block text-[11px] font-semibold uppercase tracking-[0.08em] text-ink-4">
                  自定义 Endpoint（可选，优先于地域模板）
                </span>
                <Input
                  value={form.endpoint}
                  onChange={(e) => setForm({ ...form, endpoint: e.target.value })}
                  placeholder="https://s3.cn-east-1.qiniucs.com"
                />
              </label>

              <label className="block">
                <span className="mb-1.5 block text-[11px] font-semibold uppercase tracking-[0.08em] text-ink-4">
                  SecretId / AccessKey {isEditing && <span className="text-ink-4">（留空保持原值）</span>}
                </span>
                <Input
                  type="password"
                  autoComplete="new-password"
                  value={form.access_key}
                  onChange={(e) => setForm({ ...form, access_key: e.target.value })}
                  placeholder={isEditing ? "••••（保持原值，重新填写以更新）" : "AccessKey"}
                  icon="key"
                />
              </label>

              <label className="block">
                <span className="mb-1.5 block text-[11px] font-semibold uppercase tracking-[0.08em] text-ink-4">
                  SecretKey {isEditing && <span className="text-ink-4">（留空保持原值）</span>}
                </span>
                <Input
                  type="password"
                  autoComplete="new-password"
                  value={form.secret_key}
                  onChange={(e) => setForm({ ...form, secret_key: e.target.value })}
                  placeholder={isEditing ? "••••（保持原值，重新填写以更新）" : "SecretKey"}
                  icon="key"
                />
              </label>

              <label className="flex items-center justify-between gap-2 rounded-md border border-line-subtle bg-surface-1 px-3 py-2 md:col-span-2">
                <div>
                  <div className="text-[12px] font-semibold text-ink-2">设为默认</div>
                  <p className="text-[11px] text-ink-4">导出 / 上传缺省配置项时自动选用</p>
                </div>
                <Switch
                  checked={form.is_default}
                  onChange={(v) => setForm({ ...form, is_default: v })}
                  label="设为默认"
                />
              </label>
            </div>

            {currentPreset && (
              <div className="mt-3 rounded-md border border-line-subtle bg-surface-1 p-2.5 text-[11.5px] leading-[18px] text-ink-3">
                <span className="font-semibold text-ink-2">{currentPreset.label}</span>
                ：端点 <code className="font-mono">{currentPreset.endpoint_template}</code>
                · 寻址 <code className="font-mono">{currentPreset.addressing}</code>
                · {currentPreset.credential_hint}
              </div>
            )}

            <div className="mt-4 flex flex-wrap items-end gap-2">
              {isEditing && (
                <Button variant="secondary" icon="x" onClick={resetForm}>
                  取消编辑
                </Button>
              )}
              <Button variant="secondary" icon="refresh" loading={testing} onClick={test}>
                测试连接
              </Button>
              <Button variant="primary" icon="check" loading={saving} onClick={save}>
                {isEditing ? "保存修改" : "新增配置"}
              </Button>
            </div>

            {testResult && (
              <div
                className={cx(
                  "mt-3 flex items-start gap-2 rounded-md border p-2.5 text-[12px] leading-[18px]",
                  testResult.ok
                    ? "border-success/40 bg-success/10 text-ink-2"
                    : "border-danger/40 bg-danger/10 text-ink-2",
                )}
              >
                <Icon
                  name={testResult.ok ? "check" : "alert"}
                  className={cx("mt-0.5 h-3.5 w-3.5 shrink-0", testResult.ok ? "text-success" : "text-danger")}
                />
                <span>{testResult.text}</span>
              </div>
            )}
          </Card>

          <Card title="安全说明" icon="key">
            <ul className="space-y-2 text-[12px] leading-[19px] text-ink-2">
              <li className="flex items-start gap-2.5">
                <Icon name="check" className="mt-0.5 h-4 w-4 shrink-0 text-success" />
                SecretId / SecretKey 用 Fernet 对称加密落盘，密钥文件 600 权限本机独立存放。
              </li>
              <li className="flex items-start gap-2.5">
                <Icon name="check" className="mt-0.5 h-4 w-4 shrink-0 text-success" />
                列表与表单一律脱敏展示，密码框只写不回显；编辑留空即保持原值。
              </li>
              <li className="flex items-start gap-2.5">
                <Icon name="check" className="mt-0.5 h-4 w-4 shrink-0 text-success" />
                凭证仅从加密配置文件或 .env 环境变量读取，代码内无任何硬编码。
              </li>
              <li className="flex items-start gap-2.5">
                <Icon name="alert" className="mt-0.5 h-4 w-4 shrink-0 text-warning" />
                连通性测试与异常文本均经 redact，不会把密钥写进日志。
              </li>
            </ul>
          </Card>
        </div>
    </div>
  );
}

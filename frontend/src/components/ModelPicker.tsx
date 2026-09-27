import { useCallback, useEffect, useState } from "react";
import { api } from "../api";
import type { ProviderListing, ProviderSelection } from "../types";

const FIELD_LABELS: Record<string, string> = {
  api_key: "API Key",
  secret_key: "Secret Key / SK",
  secret_id: "SecretId / AK",
  app_key: "AppKey / AppId",
};

interface Props {
  value: ProviderSelection;
  onChange: (value: ProviderSelection) => void;
}

/**
 * Image-model picker for the creation page.
 *
 * Lists the built-in core + seven pre-registered vendors + custom providers,
 * lets the user pick a model, store credentials and test connectivity. When
 * nothing is chosen the backend keeps using the project's built-in generator.
 */
export default function ModelPicker({ value, onChange }: Props) {
  const [listing, setListing] = useState<ProviderListing | null>(null);
  const [open, setOpen] = useState(false);
  const [creds, setCreds] = useState<Record<string, string>>({});
  const [status, setStatus] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [showCustom, setShowCustom] = useState(false);
  const [custom, setCustom] = useState({
    label: "",
    endpoint: "",
    models: "",
    default_model: "",
    auth_mode: "bearer",
    image_paths: "data.0.url, data.0.b64_json",
    notes: "",
  });

  const reload = useCallback(async () => {
    const data = await api.providers();
    setListing(data);
    return data;
  }, []);

  useEffect(() => {
    reload()
      .then((data) => {
        if (!value.provider) {
          onChange({
            provider: data.selected.provider || "builtin",
            model: data.selected.model || "",
          });
        }
      })
      .catch(() => {});
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [reload]);

  const selected = listing?.providers.find((p) => p.id === value.provider);
  const isBuiltin = !selected || selected.builtin;

  const selectProvider = (id: string) => {
    const provider = listing?.providers.find((p) => p.id === id);
    const next = { provider: id, model: provider?.default_model || "" };
    onChange(next);
    setStatus(null);
    api.saveProviderSettings(next).catch(() => {});
  };

  const saveCreds = async () => {
    if (!selected) return;
    setBusy(true);
    setStatus(null);
    try {
      await api.saveProviderSettings({
        provider: selected.id,
        model: value.model,
        api_key: creds.api_key,
        secret_key: creds.secret_key,
        secret_id: creds.secret_id,
        app_key: creds.app_key,
      });
      await reload();
      setStatus("配置已保存");
    } catch (err) {
      setStatus(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  };

  const test = async () => {
    if (!selected) return;
    setBusy(true);
    setStatus("测试中…");
    try {
      const result = await api.testProvider({ provider: selected.id, model: value.model });
      setStatus(result.message);
    } catch (err) {
      setStatus(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  };

  const addCustom = async () => {
    if (!custom.label.trim() || !custom.endpoint.trim()) {
      setStatus("请填写名称与接口地址");
      return;
    }
    setBusy(true);
    try {
      const models = custom.models
        .split(",")
        .map((m) => m.trim())
        .filter(Boolean);
      const created = await api.createProvider({
        label: custom.label.trim(),
        endpoint: custom.endpoint.trim(),
        models,
        default_model: custom.default_model.trim() || models[0] || "",
        auth: { mode: custom.auth_mode },
        image_paths: custom.image_paths
          .split(",")
          .map((p) => p.trim())
          .filter(Boolean),
        notes: custom.notes.trim() || undefined,
      });
      setListing(created.listing);
      setShowCustom(false);
      setCustom({ ...custom, label: "", endpoint: "", models: "", default_model: "" });
      selectProvider(created.provider);
      setStatus("已新增服务商");
    } catch (err) {
      setStatus(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="mt-9">
      <div className="mb-2 flex items-center gap-3">
        <span className="text-xs uppercase tracking-widest text-mute">
          图像模型
        </span>
        {selected && !isBuiltin && (
          <span
            className={`text-[11px] ${selected.has_key ? "text-go" : "text-warn"}`}
          >
            {selected.has_key ? `已配置 ${selected.key_hint}` : "未配置密钥"}
          </span>
        )}
        <button
          type="button"
          onClick={() => setOpen((v) => !v)}
          className="ml-auto text-xs text-ink-2 underline decoration-line-2 underline-offset-4 transition-colors hover:text-ink hover:decoration-ink"
        >
          {open ? "收起配置" : "配置 API / 新增服务商"}
        </button>
      </div>

      <div className="flex flex-wrap items-center gap-3">
        <select
          value={value.provider}
          onChange={(e) => selectProvider(e.target.value)}
          className="rounded-lg border border-line-2 bg-panel/60 px-3 py-1.5 text-sm text-ink outline-none focus:border-ink"
        >
          {listing?.providers.map((provider) => (
            <option key={provider.id} value={provider.id}>
              {provider.builtin ? provider.label : `${provider.vendor} · ${provider.label}${provider.custom ? "（自定义）" : ""}`}
            </option>
          ))}
          {!listing && <option value="builtin">项目内置管线（默认）</option>}
        </select>

        {!isBuiltin && selected && (
          <>
            <input
              list="cf-model-options"
              value={value.model}
              onChange={(e) => {
                onChange({ provider: value.provider, model: e.target.value });
              }}
              placeholder="模型 ID"
              className="w-64 rounded-lg border border-line-2 bg-panel/60 px-3 py-1.5 text-sm text-ink outline-none focus:border-ink"
            />
            <datalist id="cf-model-options">
              {selected.models.map((model) => (
                <option key={model} value={model} />
              ))}
            </datalist>
            <button
              type="button"
              onClick={test}
              disabled={busy}
              className="rounded-lg border border-line-2 px-3 py-1.5 text-xs text-ink-2 transition-colors hover:bg-panel disabled:opacity-40"
            >
              测试连接
            </button>
          </>
        )}
        {isBuiltin && (
          <span className="text-xs text-mute">
            未选用外部 API，默认沿用项目内置生成内核。
          </span>
        )}
      </div>

      {status && <p className="mt-2 font-mono text-xs text-ink-2">{status}</p>}

      {open && (
        <div className="mt-4 rounded-xl border border-line bg-panel/40 p-4">
          {selected && !isBuiltin ? (
            <>
              <div className="text-xs leading-relaxed text-mute">
                {selected.label} · {selected.vendor}
                {selected.notes ? ` — ${selected.notes}` : ""}
              </div>
              <div className="mt-3 grid gap-3 sm:grid-cols-2">
                {selected.credential_fields.map((field) => (
                  <label key={field} className="text-xs text-ink-2">
                    <span className="mb-1 block text-mute">
                      {FIELD_LABELS[field] ?? field}
                    </span>
                    <input
                      type="password"
                      value={creds[field] ?? ""}
                      onChange={(e) =>
                        setCreds((prev) => ({ ...prev, [field]: e.target.value }))
                      }
                      placeholder={selected.has_key ? "已保存（留空保持不变）" : "粘贴密钥"}
                      className="w-full rounded-lg border border-line-2 bg-paper px-3 py-1.5 text-sm text-ink outline-none focus:border-ink"
                    />
                  </label>
                ))}
              </div>
              <div className="mt-3 flex flex-wrap items-center gap-3">
                <button
                  type="button"
                  onClick={saveCreds}
                  disabled={busy}
                  className="rounded-lg bg-ink px-4 py-1.5 text-xs text-paper transition-opacity hover:opacity-85 disabled:opacity-40"
                >
                  保存配置
                </button>
                {selected.custom && (
                  <button
                    type="button"
                    onClick={async () => {
                      await api.deleteProvider(selected.id);
                      await reload();
                      selectProvider("builtin");
                    }}
                    className="text-xs text-bad underline decoration-line-2 underline-offset-4"
                  >
                    删除该自定义服务商
                  </button>
                )}
              </div>
            </>
          ) : (
            <div className="text-xs text-mute">
              当前使用内置管线，无需密钥。
            </div>
          )}

          <div className="mt-5 border-t border-line pt-4">
            <button
              type="button"
              onClick={() => setShowCustom((v) => !v)}
              className="text-xs font-medium text-ink underline decoration-line-2 underline-offset-4"
            >
              {showCustom ? "取消" : "+ 新增自定义服务商（OpenAI 兼容或自定义模板）"}
            </button>
            {showCustom && (
              <div className="mt-3 grid gap-3 sm:grid-cols-2">
                <input
                  value={custom.label}
                  onChange={(e) => setCustom({ ...custom, label: e.target.value })}
                  placeholder="名称，如 My SD WebUI"
                  className="rounded-lg border border-line-2 bg-paper px-3 py-1.5 text-sm text-ink outline-none focus:border-ink"
                />
                <input
                  value={custom.endpoint}
                  onChange={(e) => setCustom({ ...custom, endpoint: e.target.value })}
                  placeholder="接口地址 https://.../images/generations"
                  className="rounded-lg border border-line-2 bg-paper px-3 py-1.5 text-sm text-ink outline-none focus:border-ink"
                />
                <input
                  value={custom.models}
                  onChange={(e) => setCustom({ ...custom, models: e.target.value })}
                  placeholder="模型列表（逗号分隔）"
                  className="rounded-lg border border-line-2 bg-paper px-3 py-1.5 text-sm text-ink outline-none focus:border-ink"
                />
                <input
                  value={custom.default_model}
                  onChange={(e) => setCustom({ ...custom, default_model: e.target.value })}
                  placeholder="默认模型 ID"
                  className="rounded-lg border border-line-2 bg-paper px-3 py-1.5 text-sm text-ink outline-none focus:border-ink"
                />
                <select
                  value={custom.auth_mode}
                  onChange={(e) => setCustom({ ...custom, auth_mode: e.target.value })}
                  className="rounded-lg border border-line-2 bg-paper px-3 py-1.5 text-sm text-ink outline-none focus:border-ink"
                >
                  <option value="bearer">Bearer 鉴权</option>
                  <option value="header">Header 鉴权（X-App-Id）</option>
                  <option value="none">无鉴权</option>
                </select>
                <input
                  value={custom.image_paths}
                  onChange={(e) => setCustom({ ...custom, image_paths: e.target.value })}
                  placeholder="图像字段路径，逗号分隔"
                  className="rounded-lg border border-line-2 bg-paper px-3 py-1.5 text-sm text-ink outline-none focus:border-ink"
                />
                <button
                  type="button"
                  onClick={addCustom}
                  disabled={busy}
                  className="rounded-lg bg-ink px-4 py-1.5 text-xs text-paper transition-opacity hover:opacity-85 disabled:opacity-40 sm:col-span-2"
                >
                  新增服务商
                </button>
                <p className="text-[11px] leading-relaxed text-mute sm:col-span-2">
                  请求体占位符：{"{prompt} {model} {size} {width} {height} {negative}"}；
                  响应路径支持 <code>data.0.url</code> / <code>data.0.b64_json</code>。
                </p>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

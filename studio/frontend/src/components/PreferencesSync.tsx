import { useRef, useState } from "react";
import { Button, Card } from "./ui";
import { Icon } from "./icons";
import { toast } from "../stores/toastStore";

/** 工作区偏好（localStorage）键清单——导出/导入只覆盖这里列出的键。
 * studio_token 属于凭证，刻意不进导出文件。 */
const PREFERENCE_KEYS = [
  { key: "cf-rail", label: "侧栏折叠状态" },
  { key: "cf-onboarded", label: "新手引导已读" },
  { key: "creativeforge.toon-settings", label: "三渲二卡通渲染参数" },
] as const;

interface PreferencesFile {
  version: number;
  exportedAt: string;
  preferences: Record<string, string>;
}

/** 偏好导入/导出：本工具无账号体系，跨浏览器迁移走 JSON 文件
 * （quality-plan Q3 3.5 的既定路线；服务端键位同步留给账号体系落地后）。 */
export default function PreferencesSync() {
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [busy, setBusy] = useState(false);

  const collect = (): PreferencesFile => {
    const preferences: Record<string, string> = {};
    for (const { key } of PREFERENCE_KEYS) {
      const value = localStorage.getItem(key);
      if (value !== null) preferences[key] = value;
    }
    return {
      version: 1,
      exportedAt: new Date().toISOString(),
      preferences,
    };
  };

  const exportPreferences = () => {
    const payload = collect();
    const count = Object.keys(payload.preferences).length;
    const blob = new Blob([JSON.stringify(payload, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = `creativeforge-preferences-${payload.exportedAt.slice(0, 10)}.json`;
    anchor.click();
    URL.revokeObjectURL(url);
    toast({ tone: "success", title: "偏好已导出", description: `共 ${count} 项设置` });
  };

  const importPreferences = (file: File) => {
    setBusy(true);
    const reader = new FileReader();
    reader.onload = () => {
      try {
        const parsed = JSON.parse(String(reader.result)) as PreferencesFile;
        if (parsed.version !== 1 || typeof parsed.preferences !== "object") {
          throw new Error("文件格式不符");
        }
        let applied = 0;
        for (const { key } of PREFERENCE_KEYS) {
          const value = parsed.preferences[key];
          if (typeof value === "string") {
            localStorage.setItem(key, value);
            applied += 1;
          }
        }
        if (applied === 0) throw new Error("文件里没有可识别的偏好项");
        toast({
          tone: "success",
          title: "偏好已导入",
          description: `共 ${applied} 项，即将刷新页面生效`,
        });
        setTimeout(() => window.location.reload(), 900);
      } catch (error) {
        toast({
          tone: "danger",
          title: "导入失败",
          description: error instanceof Error ? error.message : String(error),
        });
      } finally {
        setBusy(false);
      }
    };
    reader.onerror = () => {
      setBusy(false);
      toast({ tone: "danger", title: "读取文件失败" });
    };
    reader.readAsText(file);
  };

  return (
    <Card title="偏好迁移" icon="layers">
      <p className="text-[12.5px] leading-[20px] text-ink-2">
        把侧栏、引导、卡通渲染参数等工作区偏好导出为一个 JSON
        文件，在另一台浏览器导入即可复原。本工具没有账号体系，迁移走文件而非云端同步；
        API Key 属于凭证，永远不会出现在导出文件里。
      </p>
      <ul className="mt-3 space-y-1.5 text-[11.5px] text-ink-3">
        {PREFERENCE_KEYS.map(({ key, label }) => {
          const present = localStorage.getItem(key) !== null;
          return (
            <li key={key} className="flex items-center gap-1.5">
              <Icon
                name="check"
                className={`h-3.5 w-3.5 shrink-0 ${present ? "text-success" : "text-ink-4"}`}
              />
              {label}
              <span className="font-mono text-[10px] text-ink-4">{key}</span>
            </li>
          );
        })}
      </ul>
      <div className="mt-4 flex gap-3">
        <Button variant="secondary" icon="download" onClick={exportPreferences}>
          导出偏好
        </Button>
        <Button variant="secondary" icon="package" disabled={busy} onClick={() => fileInputRef.current?.click()}>
          导入偏好
        </Button>
        <input
          ref={fileInputRef}
          type="file"
          accept="application/json,.json"
          className="hidden"
          onChange={(event) => {
            const file = event.target.files?.[0];
            if (file) importPreferences(file);
            event.target.value = "";
          }}
        />
      </div>
    </Card>
  );
}

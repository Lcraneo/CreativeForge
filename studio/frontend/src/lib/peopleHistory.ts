/** 动画工作台「历史人物」列表管理（localStorage）：
 *  - 展示数据源是后端生成历史（每个生成过的人物一行）；
 *  - 本地记录仅承担**列表管理**：隐藏单条/全部（不影响后端历史数据）；
 *  - 隐藏清单跨会话保留。 */

export interface PersonEntry {
  asset_id: string;
  name: string;
  image_url?: string;
  selected_at: number;
}

const HIDDEN_KEY = "cf-people-hidden";
const SELECTED_KEY = "cf-people-selected";

function readKey(key: string): string[] {
  try {
    const raw = localStorage.getItem(key);
    const data = raw ? JSON.parse(raw) : [];
    return Array.isArray(data) ? data.filter((x) => typeof x === "string" && x) : [];
  } catch {
    return [];
  }
}

function writeKey(key: string, items: unknown[]) {
  try {
    localStorage.setItem(key, JSON.stringify(items));
  } catch {
    /* 隐私模式/容量满：静默降级 */
  }
}

export function loadHidden(): string[] {
  return readKey(HIDDEN_KEY);
}

export function hidePerson(assetId: string): string[] {
  const items = readKey(HIDDEN_KEY);
  if (!items.includes(assetId)) {
    items.push(assetId);
    writeKey(HIDDEN_KEY, items);
  }
  return items;
}

export function clearHidden(): string[] {
  writeKey(HIDDEN_KEY, []);
  return [];
}

/** 最近使用排序记录（跨会话）：载入/生成过的人物置顶。 */
export function loadRecent(): PersonEntry[] {
  try {
    const raw = localStorage.getItem(SELECTED_KEY);
    const data = raw ? JSON.parse(raw) : [];
    return Array.isArray(data) ? data.filter((p) => p && p.asset_id) : [];
  } catch {
    return [];
  }
}

export function pushRecent(entry: { asset_id: string; name?: string; image_url?: string }): PersonEntry[] {
  const items = loadRecent().filter((p) => p.asset_id !== entry.asset_id);
  const next = [
    { asset_id: entry.asset_id, name: entry.name || "未命名人物", image_url: entry.image_url, selected_at: Date.now() },
    ...items,
  ].slice(0, 12);
  writeKey(SELECTED_KEY, next.map((p) => ({ asset_id: p.asset_id, name: p.name, image_url: p.image_url, selected_at: p.selected_at })));
  return next;
}

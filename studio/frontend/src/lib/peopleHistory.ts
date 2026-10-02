/** 动画工作台「历史人物」持久化（localStorage）：
 *  记录用户在动画工作台选择/使用过的人物，按最近使用排序、去重、限量。
 *  选择与清除均为同步操作，跨会话保留。 */

export interface PersonEntry {
  asset_id: string;
  name: string;
  image_url?: string;
  selected_at: number;
}

const KEY = "cf-animation-people";
const CAP = 12;

export function loadPeople(): PersonEntry[] {
  try {
    const raw = localStorage.getItem(KEY);
    const data = raw ? JSON.parse(raw) : [];
    return Array.isArray(data) ? data.filter((p) => p && p.asset_id) : [];
  } catch {
    return [];
  }
}

function save(items: PersonEntry[]) {
  try {
    localStorage.setItem(KEY, JSON.stringify(items));
  } catch {
    /* 隐私模式/容量满：静默降级为会话内记忆 */
  }
}

/** 记录一次人物使用：按 asset_id 去重置顶，超出容量裁剪最旧。 */
export function pushPerson(entry: { asset_id: string; name?: string; image_url?: string }): PersonEntry[] {
  const items = loadPeople().filter((p) => p.asset_id !== entry.asset_id);
  const next = [
    {
      asset_id: entry.asset_id,
      name: entry.name || "未命名人物",
      image_url: entry.image_url,
      selected_at: Date.now(),
    },
    ...items,
  ].slice(0, CAP);
  save(next);
  return next;
}

export function removePerson(assetId: string): PersonEntry[] {
  const next = loadPeople().filter((p) => p.asset_id !== assetId);
  save(next);
  return next;
}

export function clearPeople(): PersonEntry[] {
  save([]);
  return [];
}

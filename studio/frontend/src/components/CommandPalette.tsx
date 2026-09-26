import { useEffect, useMemo, useRef, useState, type KeyboardEvent as ReactKeyboardEvent } from "react";
import { useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { api } from "../api/client";
import { Icon, type IconName } from "./icons";
import { cx } from "./ui";

interface CommandItem {
  id: string;
  group: string;
  label: string;
  hint?: string;
  icon: IconName;
  run: () => void;
}

const NAV_ITEMS: Array<{ to: string; label: string; group: string; icon: IconName }> = [
  { to: "/", label: "工作台", group: "生产", icon: "spark" },
  { to: "/agents", label: "智能体指挥中心", group: "生产", icon: "layers" },
  { to: "/asset", label: "资产检查器", group: "资产", icon: "cube" },
  { to: "/pixel", label: "像素工作台", group: "资产", icon: "grid" },
  { to: "/animation", label: "动画工作台", group: "资产", icon: "film" },
  { to: "/export", label: "导出中心", group: "交付", icon: "package" },
  { to: "/benchmark", label: "基准中心", group: "洞察", icon: "gauge" },
  { to: "/technology", label: "技术中心", group: "洞察", icon: "book" },
  { to: "/settings", label: "模型设置（第三方 API）", group: "洞察", icon: "terminal" },
];

export function CommandPalette({
  open,
  onOpenChange,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const [query, setQuery] = useState("");
  const [cursor, setCursor] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);
  const navigate = useNavigate();
  const tasks = useQuery({ queryKey: ["tasks"], queryFn: api.listTasks, staleTime: 5000 });

  useEffect(() => {
    function onKeyDown(event: KeyboardEvent) {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        onOpenChange(!open);
      }
      if (event.key === "Escape") onOpenChange(false);
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [open, onOpenChange]);

  useEffect(() => {
    if (open) {
      setQuery("");
      setCursor(0);
      requestAnimationFrame(() => inputRef.current?.focus());
    }
  }, [open]);

  const items = useMemo<CommandItem[]>(() => {
    const list: CommandItem[] = NAV_ITEMS.map((item) => ({
      id: `nav:${item.to}`,
      group: "导航",
      label: item.label,
      hint: item.group,
      icon: item.icon,
      run: () => navigate(item.to),
    }));
    list.push({
      id: "action:new-task",
      group: "操作",
      label: "创建新的资产任务",
      hint: "回到工作台输入目标",
      icon: "plus",
      run: () => navigate("/"),
    });
    for (const task of tasks.data?.tasks.slice(0, 6) ?? []) {
      list.push({
        id: `task:${task.task_id}`,
        group: "最近任务",
        label: task.goal,
        hint: `${task.task_id} · ${task.status}`,
        icon: "terminal",
        run: () => navigate(task.status === "running" ? "/agents" : "/asset"),
      });
    }
    return list;
  }, [navigate, tasks.data]);

  const filtered = useMemo(() => {
    const keyword = query.trim().toLowerCase();
    if (!keyword) return items;
    return items.filter(
      (item) =>
        item.label.toLowerCase().includes(keyword) ||
        item.hint?.toLowerCase().includes(keyword),
    );
  }, [items, query]);

  useEffect(() => setCursor(0), [query]);

  if (!open) return null;

  const groups: Array<{ name: string; items: CommandItem[] }> = [];
  for (const item of filtered) {
    const group = groups.find((entry) => entry.name === item.group);
    if (group) group.items.push(item);
    else groups.push({ name: item.group, items: [item] });
  }

  function onKeyDown(event: ReactKeyboardEvent) {
    if (event.key === "ArrowDown") {
      event.preventDefault();
      setCursor((value) => Math.min(filtered.length - 1, value + 1));
    } else if (event.key === "ArrowUp") {
      event.preventDefault();
      setCursor((value) => Math.max(0, value - 1));
    } else if (event.key === "Enter") {
      event.preventDefault();
      filtered[cursor]?.run();
      onOpenChange(false);
    }
  }

  let flatIndex = -1;

  return (
    <div
      className="fixed inset-0 z-50 flex items-start justify-center bg-canvas/70 px-4 pt-24 backdrop-blur-sm"
      onClick={() => onOpenChange(false)}
      role="dialog"
      aria-modal="true"
      aria-label="命令面板"
    >
      <div
        className="w-full max-w-[560px] overflow-hidden rounded-2xl border border-line-subtle bg-surface-1 shadow-e3"
        onClick={(event) => event.stopPropagation()}
      >
        <div className="flex items-center gap-3 border-b border-line-subtle px-4 py-3">
          <Icon name="search" className="h-4 w-4 text-ink-3" />
          <input
            ref={inputRef}
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            onKeyDown={onKeyDown}
            placeholder="搜索页面、任务或操作…"
            className="min-w-0 flex-1 bg-transparent text-sm outline-none placeholder:text-ink-4"
          />
          <kbd className="rounded-xs border border-line px-1.5 py-0.5 font-mono text-[10px] text-ink-3">
            ESC
          </kbd>
        </div>
        <div className="cf-scroll max-h-[380px] overflow-y-auto p-2">
          {groups.length === 0 && (
            <div className="px-3 py-8 text-center text-[12.5px] text-ink-3">
              没有匹配的结果
            </div>
          )}
          {groups.map((group) => (
            <div key={group.name} className="mb-1">
              <div className="px-3 py-1.5 text-[10.5px] font-semibold uppercase tracking-[0.08em] text-ink-4">
                {group.name}
              </div>
              {group.items.map((item) => {
                flatIndex += 1;
                const active = flatIndex === cursor;
                const index = flatIndex;
                return (
                  <button
                    key={item.id}
                    onMouseEnter={() => setCursor(index)}
                    onClick={() => {
                      item.run();
                      onOpenChange(false);
                    }}
                    className={cx(
                      "flex w-full items-center gap-3 rounded-md px-3 py-2 text-left text-[13px] transition-colors",
                      active ? "bg-primary-tint text-ink" : "text-ink-2 hover:bg-surface-2",
                    )}
                  >
                    <Icon
                      name={item.icon}
                      className={cx("h-4 w-4 shrink-0", active ? "text-primary" : "text-ink-3")}
                    />
                    <span className="min-w-0 flex-1 truncate">{item.label}</span>
                    {item.hint && (
                      <span className="shrink-0 font-mono text-[10.5px] text-ink-4">{item.hint}</span>
                    )}
                  </button>
                );
              })}
            </div>
          ))}
        </div>
        <div className="flex items-center gap-4 border-t border-line-subtle px-4 py-2 text-[10.5px] text-ink-4">
          <span>
            <kbd className="mr-1 font-mono">↑↓</kbd>选择
          </span>
          <span>
            <kbd className="mr-1 font-mono">↵</kbd>打开
          </span>
          <span className="ml-auto">
            <kbd className="mr-1 font-mono">⌘K</kbd>唤出
          </span>
        </div>
      </div>
    </div>
  );
}

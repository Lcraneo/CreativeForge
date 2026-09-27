import { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { motion } from "framer-motion";
import { Icon, type IconName } from "./icons";
import { cx } from "./ui";

interface Command {
  id: string;
  label: string;
  group: string;
  icon: IconName;
  keywords?: string;
  run: () => void;
}

/** ⌘K command palette: fuzzy route jumping (listener stays global). */
export function CommandPalette({
  open,
  onOpenChange,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const navigate = useNavigate();
  const [query, setQuery] = useState("");
  const [active, setActive] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    function onKey(event: KeyboardEvent) {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        onOpenChange(!open);
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onOpenChange]);

  useEffect(() => {
    if (open) {
      setQuery("");
      setActive(0);
      requestAnimationFrame(() => inputRef.current?.focus());
    }
  }, [open]);

  const commands = useMemo<Command[]>(() => {
    const go = (path: string) => {
      navigate(path);
      onOpenChange(false);
    };
    return [
      { id: "workspace", label: "工作台", group: "生产", icon: "spark", keywords: "goal generate 生成", run: () => go("/") },
      { id: "agents", label: "智能体指挥中心", group: "生产", icon: "layers", keywords: "task graph 任务图", run: () => go("/agents") },
      { id: "history", label: "历史记录", group: "生产", icon: "clock", keywords: "records 历史", run: () => go("/history") },
      { id: "asset", label: "资产检查器", group: "资产", icon: "cube", keywords: "inspector asset 资产", run: () => go("/asset") },
      { id: "design", label: "角色设计三视图", group: "资产", icon: "image", keywords: "turnaround 三视图 design", run: () => go("/design") },
      { id: "pixel", label: "像素工作台", group: "资产", icon: "grid", keywords: "precon pixel 像素", run: () => go("/pixel") },
      { id: "animation", label: "动画工作台", group: "资产", icon: "film", keywords: "falign animation 动画", run: () => go("/animation") },
      { id: "export", label: "导出中心", group: "交付 · 洞察", icon: "package", keywords: "gimport export 导出 unity cocos godot", run: () => go("/export") },
      { id: "benchmark", label: "基准中心", group: "交付 · 洞察", icon: "gauge", keywords: "benchmark 基准评测", run: () => go("/benchmark") },
      { id: "technology", label: "技术中心", group: "交付 · 洞察", icon: "book", keywords: "technology 技术", run: () => go("/technology") },
      { id: "settings", label: "模型设置", group: "交付 · 洞察", icon: "terminal", keywords: "model settings api key 模型", run: () => go("/settings") },
    ];
  }, [navigate, onOpenChange]);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return commands;
    return commands.filter((command) =>
      `${command.label} ${command.group} ${command.keywords ?? ""}`.toLowerCase().includes(q),
    );
  }, [commands, query]);

  if (!open) return null;

  function onKeyDown(event: React.KeyboardEvent) {
    if (event.key === "Escape") {
      onOpenChange(false);
      return;
    }
    if (event.key === "ArrowDown") {
      event.preventDefault();
      setActive((index) => Math.min(filtered.length - 1, index + 1));
    }
    if (event.key === "ArrowUp") {
      event.preventDefault();
      setActive((index) => Math.max(0, index - 1));
    }
    if (event.key === "Enter" && filtered[active]) {
      filtered[active].run();
    }
  }

  return (
    <div
      className="fixed inset-0 z-50 bg-ink/25 backdrop-blur-[2px]"
      onClick={() => onOpenChange(false)}
      onKeyDown={onKeyDown}
      role="dialog"
      aria-modal="true"
      aria-label="命令面板"
    >
      <motion.div
        initial={{ opacity: 0, y: -10, scale: 0.985 }}
        animate={{ opacity: 1, y: 0, scale: 1 }}
        transition={{ duration: 0.18, ease: [0.2, 0.8, 0.2, 1] }}
        className="mx-auto mt-[16vh] w-[560px] max-w-[calc(100vw-2rem)] overflow-hidden rounded-xl border border-line bg-[#faf9f5] shadow-e3"
        onClick={(event) => event.stopPropagation()}
      >
        <div className="flex items-center gap-2.5 border-b border-line-subtle px-4">
          <Icon name="search" className="h-4 w-4 shrink-0 text-ink-3" />
          <input
            ref={inputRef}
            value={query}
            onChange={(event) => {
              setQuery(event.target.value);
              setActive(0);
            }}
            placeholder="搜索页面与操作…"
            className="h-12 w-full bg-transparent text-sm text-ink outline-none placeholder:text-ink-4"
          />
          <kbd className="rounded-xs border border-line px-1.5 py-0.5 font-mono text-[10px] text-ink-3">
            ESC
          </kbd>
        </div>
        <div className="cf-scroll max-h-[340px] overflow-y-auto p-1.5">
          {filtered.length === 0 && (
            <p className="px-3 py-6 text-center text-[13px] text-ink-3">没有匹配的结果</p>
          )}
          {filtered.map((command, index) => (
            <button
              key={command.id}
              onClick={command.run}
              onMouseEnter={() => setActive(index)}
              className={cx(
                "flex w-full items-center gap-3 rounded-md px-3 py-2.5 text-left text-[13.5px] transition-colors",
                index === active ? "bg-ink/[.06] text-ink" : "text-ink-2",
              )}
            >
              <Icon
                name={command.icon}
                className={cx("h-4 w-4 shrink-0", index === active ? "text-primary" : "text-ink-3")}
              />
              <span className="min-w-0 flex-1 truncate">
                {command.label}
                <span className="ml-2 text-[11px] text-ink-4">{command.group}</span>
              </span>
              {index === active && <Icon name="chevron" className="h-3.5 w-3.5 text-ink-4" />}
            </button>
          ))}
        </div>
      </motion.div>
    </div>
  );
}

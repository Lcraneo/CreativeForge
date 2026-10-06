import { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { motion } from "framer-motion";
import { Icon, type IconName } from "./icons";
import { NAV_GROUPS } from "../lib/navigation";
import { useAssetNavigation } from "../lib/assetNavigation";
import { cx } from "./ui";
import { MOTION, EASE_STANDARD } from "../lib/motion";

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
  const href = useAssetNavigation();
  const dialogRef = useRef<HTMLDivElement>(null);
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
      const previous = document.activeElement as HTMLElement | null;
      const frame = requestAnimationFrame(() => {
        // 面板打开是异步聚焦；若焦点已被用户/测试移入面板内（如焦点陷阱），
        // 不得抢回输入框，否则 Shift+Tab 等焦点操作会被覆盖
        if (dialogRef.current?.contains(document.activeElement)) return;
        inputRef.current?.focus();
      });
      return () => {
        cancelAnimationFrame(frame);
        previous?.focus();
      };
    }
  }, [open]);

  const commands = useMemo<Command[]>(() => {
    const go = (path: string) => {
      navigate(href(path));
      onOpenChange(false);
    };
    return NAV_GROUPS.flatMap((group) =>
      group.items
        .flatMap((item) => [item, ...(item.children ?? [])])
        .map((item) => ({
          id: item.to,
          label: item.label,
          group: group.label,
          icon: item.icon,
          keywords: `${item.to} ${item.to === "/export" ? "unity cocos godot" : ""}`,
          run: () => go(item.to),
        })),
    );
  }, [navigate, href, onOpenChange]);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return commands;
    return commands.filter((command) =>
      `${command.label} ${command.group} ${command.keywords ?? ""}`.toLowerCase().includes(q),
    );
  }, [commands, query]);

  if (!open) return null;

  function onKeyDown(event: React.KeyboardEvent) {
    if (event.key === "Tab") {
      const controls = Array.from(
        dialogRef.current?.querySelectorAll<HTMLElement>("input, button") ?? [],
      );
      const first = controls[0];
      const last = controls[controls.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last?.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first?.focus();
      }
      return;
    }
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
    if (event.key === "Enter" && event.target === inputRef.current && filtered[active]) {
      event.preventDefault();
      filtered[active].run();
    }
  }

  return (
    <div
      className="fixed inset-0 z-50 bg-ink/25 backdrop-blur-[2px]"
      onClick={() => onOpenChange(false)}
      onKeyDown={onKeyDown}
      ref={dialogRef}
      role="dialog"
      aria-modal="true"
      aria-label="命令面板"
    >
      <motion.div
        initial={{ opacity: 0, y: -10, scale: 0.985 }}
        animate={{ opacity: 1, y: 0, scale: 1 }}
        transition={{ duration: MOTION.base, ease: EASE_STANDARD }}
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
            aria-label="搜索页面与操作"
            placeholder="搜索页面与操作…"
            className="h-12 w-full bg-transparent text-sm text-ink outline-none placeholder:text-ink-4"
          />
          <kbd className="rounded-xs border border-line px-1.5 py-0.5 font-mono text-[10px] text-ink-3">
            ESC
          </kbd>
        </div>
        <div className="cf-scroll max-h-[min(340px,60dvh)] overflow-y-auto p-1.5">
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

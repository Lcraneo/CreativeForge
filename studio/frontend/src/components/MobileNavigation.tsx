import { useEffect, useRef } from "react";
import { NavLink } from "react-router-dom";
import { NAV_GROUPS } from "../lib/navigation";
import { useAssetNavigation } from "../lib/assetNavigation";
import { Icon } from "./icons";
import { RococoDivider } from "./rococo/RococoOrnaments";

export function MobileNavigation({ open, onClose }: { open: boolean; onClose: () => void }) {
  const dialog = useRef<HTMLDialogElement>(null);
  const href = useAssetNavigation();
  useEffect(() => {
    const node = dialog.current;
    if (!node || !open) return;
    const previous = document.activeElement as HTMLElement | null;
    node.showModal();
    return () => {
      node.close();
      previous?.focus();
    };
  }, [open]);
  return (
    <dialog
      ref={dialog}
      aria-labelledby="mobile-nav-title"
      onCancel={(event) => {
        event.preventDefault();
        onClose();
      }}
      onClick={(event) => {
        if (event.target === event.currentTarget) onClose();
      }}
      className="m-auto max-h-[85dvh] w-[calc(100%-2rem)] max-w-md overflow-y-auto rounded-lg border border-line bg-paper p-0 text-ink shadow-e3 backdrop:bg-ink/25"
    >
      <div className="p-4 pb-[max(1rem,env(safe-area-inset-bottom))]">
        <div className="mb-2 flex items-center justify-between">
          <h2 id="mobile-nav-title" className="font-serif text-xl font-black">
            全部功能
          </h2>
          <button
            type="button"
            autoFocus
            onClick={onClose}
            className="min-h-11 min-w-11 rounded-sm border border-line bg-canvas px-3"
          >
            关闭
          </button>
        </div>
        <RococoDivider className="mb-3 h-4 w-40 text-line-strong/70" />
        <nav aria-label="全部功能">
          {NAV_GROUPS.map((group) => (
            <section key={group.label} className="mb-3">
              <h3 className="mb-2 text-xs text-ink-3">{group.label}</h3>
              <div className="grid grid-cols-2 gap-2">
                {group.items
                  .flatMap((item) => [item, ...(item.children ?? [])])
                  .map((item) => (
                    <NavLink
                      key={item.to}
                      to={href(item.to)}
                      end={item.to === "/"}
                      onClick={onClose}
                      className={({ isActive }) =>
                        `flex min-h-11 items-center gap-2 rounded-sm border px-3 text-sm ${isActive ? "border-primary/30 bg-ember-tint font-semibold text-ink" : "border-line bg-canvas text-ink-2"}`
                      }
                    >
                      <Icon name={item.icon} className="h-4 w-4 shrink-0" />
                      {item.label}
                    </NavLink>
                  ))}
              </div>
            </section>
          ))}
        </nav>
      </div>
    </dialog>
  );
}

import { AnimatePresence, motion } from "framer-motion";
import { useToastStore, type ToastTone } from "../stores/toastStore";
import { Icon, type IconName } from "./icons";

const TONES: Record<ToastTone, { bar: string; icon: IconName; iconClass: string }> = {
  info: { bar: "bg-primary", icon: "activity", iconClass: "text-primary" },
  success: { bar: "bg-success", icon: "check", iconClass: "text-success" },
  warning: { bar: "bg-warning", icon: "alert", iconClass: "text-warning" },
  danger: { bar: "bg-danger", icon: "x", iconClass: "text-danger" },
};

export function Toaster() {
  const toasts = useToastStore((state) => state.toasts);
  const remove = useToastStore((state) => state.remove);

  return (
    <div className="pointer-events-none fixed bottom-5 right-5 z-[60] flex w-80 flex-col gap-2.5">
      <AnimatePresence initial={false}>
        {toasts.map((toast) => {
          const tone = TONES[toast.tone];
          return (
            <motion.output
              key={toast.id}
              role="status"
              initial={{ opacity: 0, y: 10, scale: 0.98 }}
              animate={{ opacity: 1, y: 0, scale: 1 }}
              exit={{ opacity: 0, y: 6 }}
              transition={{ duration: 0.18, ease: [0.2, 0.8, 0.2, 1] }}
              className="pointer-events-auto relative overflow-hidden rounded-xl border border-line-subtle bg-surface-1 shadow-e3"
            >
              <span className={`absolute inset-x-0 top-0 h-0.5 ${tone.bar}`} />
              <div className="flex items-start gap-2.5 px-4 py-3">
                <Icon name={tone.icon} className={`mt-0.5 h-4 w-4 shrink-0 ${tone.iconClass}`} />
                <div className="min-w-0 flex-1">
                  <div className="text-[13px] font-semibold">{toast.title}</div>
                  {toast.description && (
                    <div className="mt-0.5 text-xs leading-[18px] text-ink-3">
                      {toast.description}
                    </div>
                  )}
                </div>
                <button
                  aria-label="关闭通知"
                  onClick={() => remove(toast.id)}
                  className="text-ink-4 transition-colors hover:text-ink-2"
                >
                  <Icon name="x" className="h-3.5 w-3.5" />
                </button>
              </div>
            </motion.output>
          );
        })}
      </AnimatePresence>
    </div>
  );
}

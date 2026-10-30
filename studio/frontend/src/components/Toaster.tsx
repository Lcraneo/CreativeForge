import { useEffect } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { useToastStore, type ToastTone } from "../stores/toastStore";
import { Icon } from "./icons";
import { cx } from "./ui";
import { MOTION, EASE_STANDARD } from "../lib/motion";

const TONE_BAR: Record<ToastTone, string> = {
  info: "bg-ink-3",
  success: "bg-success",
  danger: "bg-danger",
  warning: "bg-warning",
};

export function Toaster() {
  const items = useToastStore((state) => state.items);
  const dismiss = useToastStore((state) => state.dismiss);
  const dismissExpired = useToastStore((state) => state.dismissExpired);

  // 后台标签页会节流 setTimeout：回到前台时按绝对过期时间补一次清理，
  // 保证提示不会因为切走页面而一直挂在视野里。
  useEffect(() => {
    const sweep = () => dismissExpired();
    const onVisibilityChange = () => {
      if (document.visibilityState === "visible") sweep();
    };
    document.addEventListener("visibilitychange", onVisibilityChange);
    window.addEventListener("focus", sweep);
    sweep();
    return () => {
      document.removeEventListener("visibilitychange", onVisibilityChange);
      window.removeEventListener("focus", sweep);
    };
  }, [dismissExpired]);

  return (
    <div className="pointer-events-none fixed bottom-20 right-4 z-50 flex flex-col-reverse gap-2.5 md:bottom-5 md:right-5">
      <AnimatePresence initial={false}>
        {items.map((item) => (
          <motion.div
            key={item.id}
            layout
            initial={{ opacity: 0, y: 14, scale: 0.97 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, x: 24, transition: { duration: MOTION.fast } }}
            transition={{ duration: MOTION.base, ease: EASE_STANDARD }}
            className="pointer-events-auto relative flex w-[330px] max-w-[calc(100vw-2rem)] cursor-pointer gap-3 overflow-hidden rounded-lg border border-line bg-[#faf9f5]/95 py-3 pl-4 pr-2.5 shadow-e3 backdrop-blur-md"
            onClick={() => dismiss(item.id)}
            role="status"
          >
            <span className={cx("absolute inset-y-0 left-0 w-[3px]", TONE_BAR[item.tone])} />
            <div className="min-w-0 flex-1">
              <div className="text-[13px] font-semibold leading-[19px] text-ink">{item.title}</div>
              {item.description && (
                <div className="mt-0.5 line-clamp-2 text-[12px] leading-[18px] text-ink-3">
                  {item.description}
                </div>
              )}
            </div>
            <button
              type="button"
              aria-label={`关闭提示：${item.title}`}
              title="关闭"
              onClick={(event) => {
                // 只关闭当前条目；阻止冒泡到整张提示卡，避免误触其他提示。
                event.stopPropagation();
                dismiss(item.id);
              }}
              className="grid h-6 w-6 shrink-0 place-items-center self-start rounded-md text-ink-3 transition-[color,background-color,transform] duration-(--motion-fast) ease-standard hover:bg-surface-2 hover:text-ink active:scale-[0.94] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/25"
            >
              <Icon name="x" className="h-3.5 w-3.5" />
            </button>
          </motion.div>
        ))}
      </AnimatePresence>
    </div>
  );
}

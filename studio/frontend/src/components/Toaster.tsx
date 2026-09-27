import { AnimatePresence, motion } from "framer-motion";
import { useToastStore, type ToastTone } from "../stores/toastStore";
import { cx } from "./ui";

const TONE_BAR: Record<ToastTone, string> = {
  info: "bg-ink-3",
  success: "bg-success",
  danger: "bg-danger",
  warning: "bg-warning",
};

export function Toaster() {
  const items = useToastStore((state) => state.items);
  const dismiss = useToastStore((state) => state.dismiss);

  return (
    <div className="pointer-events-none fixed bottom-20 right-4 z-50 flex flex-col-reverse gap-2.5 md:bottom-5 md:right-5">
      <AnimatePresence initial={false}>
        {items.map((item) => (
          <motion.div
            key={item.id}
            layout
            initial={{ opacity: 0, y: 14, scale: 0.97 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, x: 24, transition: { duration: 0.16 } }}
            transition={{ duration: 0.22, ease: [0.2, 0.8, 0.2, 1] }}
            className="pointer-events-auto relative flex w-[330px] max-w-[calc(100vw-2rem)] cursor-pointer gap-3 overflow-hidden rounded-lg border border-line bg-[#faf9f5]/95 py-3 pl-4 pr-3.5 shadow-e3 backdrop-blur-md"
            onClick={() => dismiss(item.id)}
            role="status"
          >
            <span className={cx("absolute inset-y-0 left-0 w-[3px]", TONE_BAR[item.tone])} />
            <div className="min-w-0">
              <div className="text-[13px] font-semibold leading-[19px] text-ink">{item.title}</div>
              {item.description && (
                <div className="mt-0.5 line-clamp-2 text-[12px] leading-[18px] text-ink-3">
                  {item.description}
                </div>
              )}
            </div>
          </motion.div>
        ))}
      </AnimatePresence>
    </div>
  );
}

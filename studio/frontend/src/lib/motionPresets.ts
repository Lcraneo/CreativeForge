import { useReducedMotion } from "framer-motion";
import { EASE_STANDARD, MOTION } from "./motion";

/**
 * 动效预设层：动态内容区的过渡参数统一从这里取。
 * - 时长一律引用 lib/motion.ts 的令牌阶梯，禁止裸写 ms；
 * - 弹簧参数收敛到无过冲区间（规范禁弹跳过冲）；
 * - useMotionPref() 在系统声明 reduced-motion 时把入场归零，
 *   组件侧只需解构预设，不自行判断。
 */

export const SPRING_SOFT = { type: "spring", stiffness: 170, damping: 28, mass: 1 } as const;

export interface EnterExitPreset {
  initial: Record<string, number>;
  animate: Record<string, number>;
  exit: Record<string, number>;
  transition: { duration: number; ease: readonly number[] };
}

const makePreset = (
  initial: Record<string, number>,
  exitY: number,
  duration: number,
): EnterExitPreset => ({
  initial,
  animate: { opacity: 1, x: 0, y: 0 },
  exit: { opacity: 0, y: exitY },
  transition: { duration, ease: EASE_STANDARD },
});

/** 列表行插入/移除：淡入 + 轻上移（默认动效） */
export const FADE_RISE: EnterExitPreset = makePreset({ opacity: 0, y: 10 }, -6, MOTION.base);
/** 事件流行进场：淡入 + 左侧滑入，更快一档 */
export const SLIDE_IN: EnterExitPreset = makePreset({ opacity: 0, x: -8 }, 0, MOTION.fast);
/** 视图/内容切换：快淡入，无位移 */
export const CONTENT_SWAP: EnterExitPreset = makePreset({ opacity: 0, y: 6 }, 0, MOTION.fast);

/** 父子交错编排：给 map 出来的子项挂 item 变体 */
export const STAGGER_PARENT = {
  hidden: {},
  show: { transition: { staggerChildren: MOTION.fast } },
} as const;
export const STAGGER_ITEM = {
  hidden: { opacity: 0, y: 12 },
  show: { opacity: 1, y: 0, transition: { duration: MOTION.base, ease: EASE_STANDARD } },
} as const;

/**
 * reduced-motion 感知：返回一份"即时"预设覆盖（时长 0 / 无位移）。
 * 用法：const pref = useMotionPref(); <motion.div {...pref.pick(FADE_RISE)}>
 */
export function useMotionPref() {
  const reduce = useReducedMotion();
  return {
    reduce,
    pick(preset: EnterExitPreset): EnterExitPreset {
      if (!reduce) return preset;
      return {
        initial: { opacity: 0 },
        animate: { opacity: 1 },
        exit: { opacity: 0 },
        transition: { duration: MOTION.instant, ease: EASE_STANDARD },
      };
    },
  };
}

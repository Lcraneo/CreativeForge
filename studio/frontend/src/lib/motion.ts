/** 动效令牌（TS 侧）：与 index.css @theme 的 --motion-* 同源同值。
 * framer-motion 用秒、CSS 用毫秒，两处共用同一套阶梯；组件内禁止裸写时长。 */
export const MOTION = {
  instant: 0.09,
  fast: 0.12,
  base: 0.18,
  slow: 0.26,
  deliberate: 0.32,
  /** 入场/数据揭示类动画统一时长 */
  reveal: 0.6,
} as const;

/** 开屏是产品里唯一允许的完整编排，单独成组，避免污染日常动效。 */
export const OPENING = {
  short: 1.6,
  reduced: 1.15,
  full: 4.5,
  skipFade: 0.24,
  hold: 0.2,
} as const;

export const EASE_STANDARD = [0.22, 1, 0.36, 1] as const;

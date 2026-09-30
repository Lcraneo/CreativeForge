/** 动效令牌（TS 侧）：与 index.css @theme 的 --motion-* 同源同值。
 * framer-motion 用秒、CSS 用毫秒，两处共用同一套阶梯；组件内禁止裸写时长。 */
export const MOTION = {
  instant: 0.09,
  fast: 0.12,
  base: 0.18,
  slow: 0.26,
  /** 入场/数据揭示类动画统一时长 */
  reveal: 0.6,
} as const;

export const EASE_STANDARD = [0.2, 0.8, 0.2, 1] as const;

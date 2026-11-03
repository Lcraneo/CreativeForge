import { useEffect, useRef } from "react";

/** 输入类目标（输入框/文本域/下拉/可编辑元素）不劫持按键。 */
export function isTypingTarget(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) return false;
  return (
    target.isContentEditable ||
    target.tagName === "INPUT" ||
    target.tagName === "TEXTAREA" ||
    target.tagName === "SELECT"
  );
}

/** 按住键集合（游戏式操控语义）：
 * - blur 全清——切窗回来角色不再"卡键"继续跑；
 * - preventDefaultKeys 阻止页面默认行为（方向键滚动、空格翻页）；
 * - 可选 onPress 在每次 keydown（含 repeat）时回调，驱动一次性动作触发；
 * - 输入类目标聚焦时完全放行，不劫持。 */
export function useHeldKeys(
  preventDefaultKeys: readonly string[] = [],
  onPress?: (key: string) => void,
) {
  const keysRef = useRef<Set<string>>(new Set());
  const pressRef = useRef(onPress);
  pressRef.current = onPress;
  const preventRef = useRef(preventDefaultKeys);
  preventRef.current = preventDefaultKeys;

  useEffect(() => {
    const down = (event: KeyboardEvent) => {
      if (isTypingTarget(event.target)) return;
      const key = event.key.toLowerCase();
      if (preventRef.current.includes(key)) event.preventDefault();
      keysRef.current.add(key);
      pressRef.current?.(key);
    };
    const up = (event: KeyboardEvent) => {
      keysRef.current.delete(event.key.toLowerCase());
    };
    const clear = () => keysRef.current.clear();

    window.addEventListener("keydown", down);
    window.addEventListener("keyup", up);
    window.addEventListener("blur", clear);
    return () => {
      window.removeEventListener("keydown", down);
      window.removeEventListener("keyup", up);
      window.removeEventListener("blur", clear);
    };
  }, []);

  return keysRef;
}

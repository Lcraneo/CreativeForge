import { describe, expect, it } from "vitest";

import { isTypingTarget } from "./keyboard";

describe("isTypingTarget", () => {
  it("input/textarea/select 属于输入目标", () => {
    for (const tag of ["input", "textarea", "select"]) {
      expect(isTypingTarget(document.createElement(tag))).toBe(true);
    }
  });

  it("普通元素与 window 不属于输入目标", () => {
    expect(isTypingTarget(document.createElement("div"))).toBe(false);
    expect(isTypingTarget(window)).toBe(false);
    expect(isTypingTarget(null)).toBe(false);
  });

  it("contentEditable 元素属于输入目标", () => {
    const editable = document.createElement("div");
    Object.defineProperty(editable, "isContentEditable", { value: true });
    expect(isTypingTarget(editable)).toBe(true);
  });
});

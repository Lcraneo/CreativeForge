/** 架构边界测试（windup playtest-boundaries 同款纪律）：
 * 用测试固化模块约束，比文档更硬。 */
import { readFileSync, readdirSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

const SRC = join(process.cwd(), "src");

function walk(dir: string): string[] {
  return readdirSync(dir, { withFileTypes: true }).flatMap((entry) => {
    const full = join(dir, entry.name);
    if (entry.isDirectory()) return walk(full);
    return /\.(ts|tsx)$/.test(entry.name) && !/\.test\.(ts|tsx)$/.test(entry.name) ? [full] : [];
  });
}

const allFiles = walk(SRC);
const read = (file: string) => readFileSync(file, "utf8");

describe("architecture boundaries", () => {
  it("pages 不直接 import three / @react-three（3D 走 three/ 封装）", () => {
    const violations = walk(join(SRC, "pages")).filter((file) =>
      /from "(three|@react-three\/[\w-]+)"/.test(read(file)),
    );
    expect(violations).toEqual([]);
  });

  it("裸 fetch 只允许出现在 api/client.ts", () => {
    const violations = allFiles.filter(
      (file) => !file.includes("api\\client.ts") && /\bfetch\(/.test(read(file)),
    );
    expect(violations).toEqual([]);
  });

  it("过渡时长走令牌：不允许裸 duration-N / duration-[Nms]", () => {
    const violations = allFiles.filter((file) =>
      /duration-\d|duration-\[\d+ms\]/.test(read(file)),
    );
    expect(violations).toEqual([]);
  });

  it("framer-motion 时长走 MOTION 令牌，组件内禁止裸写秒数", () => {
    const violations = allFiles
      .filter((file) => !file.includes("lib\\motion.ts"))
      .filter((file) => /duration:\s*0?\.\d+/.test(read(file)));
    expect(violations).toEqual([]);
  });

  it("third_party/onetake 只经 showcase API 触达（前端零直连）", () => {
    // onetake 的 comp/motion.js 以 iframe/文件 URL 承载，前端源码不允许
    // 出现对其路径的 import 或字符串拼接（防 bbox 泄漏到主 bundle）
    const violations = allFiles.filter((file) =>
      /third_party|onetake\/(lib|scripts|templates)/.test(read(file)),
    );
    expect(violations).toEqual([]);
  });
});

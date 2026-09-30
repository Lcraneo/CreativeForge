import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { api, authHeaders, setStudioToken } from "./client";
import { useToastStore } from "../stores/toastStore";

const fetchMock = vi.fn();

beforeEach(() => {
  vi.stubGlobal("fetch", fetchMock);
  fetchMock.mockReset();
  setStudioToken("");
  useToastStore.setState({ items: [] });
});

afterEach(() => {
  vi.unstubAllGlobals();
  document.cookie = "studio_token=; path=/; Max-Age=0";
});

describe("auth token", () => {
  it("未设置令牌时不带 Authorization 头", () => {
    expect(authHeaders()).toEqual({});
  });

  it("setStudioToken 同步 header 与 cookie", () => {
    setStudioToken("tok-123");
    expect(authHeaders()).toEqual({ Authorization: "Bearer tok-123" });
    expect(document.cookie).toContain("studio_token=tok-123");
  });

  it("清空令牌同时清 cookie", () => {
    setStudioToken("tok-123");
    setStudioToken("");
    expect(authHeaders()).toEqual({});
    expect(document.cookie).not.toContain("tok-123");
  });
});

describe("request 错误通道", () => {
  it("成功响应原样解析 JSON", async () => {
    fetchMock.mockResolvedValue(new Response(JSON.stringify({ status: "ok" }), { status: 200 }));
    await expect(api.health()).resolves.toEqual({ status: "ok" });
  });

  it("失败响应抛错并弹一次 toast", async () => {
    fetchMock.mockResolvedValue(new Response("boom", { status: 500 }));
    await expect(api.health()).rejects.toThrow("500: boom");
    expect(useToastStore.getState().items).toHaveLength(1);
  });

  it("同一错误 2.5s 内去重，页面 catch 不受影响", async () => {
    vi.useFakeTimers();
    fetchMock.mockResolvedValue(new Response("boom", { status: 500 }));
    await expect(api.health()).rejects.toThrow();
    await expect(api.health()).rejects.toThrow();
    expect(useToastStore.getState().items).toHaveLength(1);
    vi.advanceTimersByTime(2600);
    await expect(api.health()).rejects.toThrow();
    expect(useToastStore.getState().items).toHaveLength(2);
    vi.useRealTimers();
  });
});

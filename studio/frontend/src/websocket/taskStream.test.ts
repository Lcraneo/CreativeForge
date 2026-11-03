import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { api, type TaskDetail } from "../api/client";
import { streamTask } from "./taskStream";
import { useAgentStore } from "../stores/agentStore";
import type { TaskEvent } from "../types";

class Socket {
  static current: Socket;
  onmessage: ((event: { data: string }) => void) | null = null;
  onerror: (() => void) | null = null;
  onclose: (() => void) | null = null;
  close = vi.fn();
  constructor() {
    Socket.current = this;
  }
  send(event: TaskEvent) {
    this.onmessage?.({ data: JSON.stringify(event) });
  }
}

const plan: TaskEvent = { type: "AGENT_START", task: "art", at: 1 };
const done: TaskEvent = { type: "TASK_COMPLETE", status: "pass", at: 2 };
const snapshot = (events: TaskEvent[], status = "running") => ({ events, status }) as TaskDetail;
let stop: (() => void) | undefined;

beforeEach(() => {
  vi.useFakeTimers();
  vi.stubGlobal("WebSocket", Socket);
});
afterEach(() => {
  stop?.();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
  vi.useRealTimers();
});

describe("task stream", () => {
  it("applies events and terminal status immediately, without animation delays", () => {
    const onEvent = vi.fn();
    const onEnd = vi.fn();
    stop = streamTask("task", { onEvent, onEnd });
    Socket.current.send(plan);
    Socket.current.send(done);
    Socket.current.send({ type: "STREAM_END", status: "pass" });
    expect(onEvent.mock.calls.map(([event]) => event)).toEqual([plan, done]);
    expect(onEnd).toHaveBeenCalledExactlyOnceWith("pass");
    expect(Socket.current.close).toHaveBeenCalledOnce();
  });

  it("continues after the socket cursor without replaying previous events", async () => {
    const read = vi.spyOn(api, "getTaskDetail").mockResolvedValue(snapshot([plan, done], "pass"));
    const onEvent = vi.fn();
    const onEnd = vi.fn();
    stop = streamTask("task", { onEvent, onEnd });
    Socket.current.send(plan);
    Socket.current.onerror?.();
    await vi.advanceTimersByTimeAsync(0);
    expect(read).toHaveBeenCalledOnce();
    expect(onEvent.mock.calls.map(([event]) => event)).toEqual([plan, done]);
    expect(onEnd).toHaveBeenCalledExactlyOnceWith("pass");
    await vi.advanceTimersByTimeAsync(10000);
    expect(read).toHaveBeenCalledOnce();
  });

  it("never overlaps slow polls and ignores responses after stopping", async () => {
    let resolve!: (value: TaskDetail) => void;
    const read = vi.spyOn(api, "getTaskDetail").mockImplementation(
      () =>
        new Promise((r) => {
          resolve = r;
        }),
    );
    const onEvent = vi.fn();
    const onEnd = vi.fn();
    stop = streamTask("task", { onEvent, onEnd });
    Socket.current.onerror?.();
    await vi.advanceTimersByTimeAsync(20000);
    expect(read).toHaveBeenCalledOnce();
    const signal = read.mock.calls[0][1]?.signal;
    stop();
    expect(signal?.aborted).toBe(true);
    resolve(snapshot([done], "pass"));
    await vi.advanceTimersByTimeAsync(0);
    expect(onEvent).not.toHaveBeenCalled();
    expect(onEnd).not.toHaveBeenCalled();
  });

  it("backs off on network failures and handles fail as a terminal state", async () => {
    const read = vi
      .spyOn(api, "getTaskDetail")
      .mockRejectedValueOnce(new Error("offline"))
      .mockResolvedValue(snapshot([], "fail"));
    const onEnd = vi.fn();
    stop = streamTask("task", { onEvent: vi.fn(), onEnd });
    Socket.current.onerror?.();
    await vi.advanceTimersByTimeAsync(1999);
    expect(read).toHaveBeenCalledOnce();
    await vi.advanceTimersByTimeAsync(1);
    expect(onEnd).toHaveBeenCalledExactlyOnceWith("fail");
    useAgentStore.getState().finish("fail");
    expect(useAgentStore.getState().status).toBe("failed");
  });

  it("ends an unknown-task socket error as failure", () => {
    const onEnd = vi.fn();
    const onError = vi.fn();
    stop = streamTask("missing", { onEvent: vi.fn(), onEnd, onError });
    Socket.current.send({ type: "ERROR", detail: "unknown task" });
    expect(onError).toHaveBeenCalledExactlyOnceWith("unknown task");
    expect(onEnd).toHaveBeenCalledExactlyOnceWith("failed");
  });
});

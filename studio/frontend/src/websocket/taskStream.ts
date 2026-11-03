import type { TaskEvent } from "../types";
import { api } from "../api/client";

export interface StreamHandlers {
  onEvent: (event: TaskEvent) => void;
  onEnd: (status: string) => void;
  onError?: (message: string) => void;
}

const POLL_INTERVAL_MS = 1000;
const MAX_RETRY_MS = 10000;
const TERMINAL_STATES = new Set(["pass", "success", "failed", "fail"]);

/** Apply real events immediately. REST continues the same append-only event
 * log after a socket failure; presentation animations never delay task state. */
export function streamTask(taskId: string, handlers: StreamHandlers): () => void {
  let closed = false;
  let polling = false;
  let cursor = 0;
  let failures = 0;
  let ws: WebSocket | null = null;
  let pollTimer: ReturnType<typeof setTimeout> | null = null;
  const controller = new AbortController();

  function closeSocket() {
    if (!ws) return;
    ws.onmessage = null;
    ws.onerror = null;
    ws.onclose = null;
    ws.close();
    ws = null;
  }

  function stop() {
    closed = true;
    if (pollTimer !== null) clearTimeout(pollTimer);
    controller.abort();
    closeSocket();
  }

  function finish(status: string) {
    if (closed) return;
    stop();
    handlers.onEnd(status);
  }

  function dispatch(event: TaskEvent) {
    if (closed) return;
    if (event.type === "STREAM_END") {
      finish(event.status ?? "unknown");
    } else {
      cursor += 1;
      handlers.onEvent(event);
    }
  }

  async function poll() {
    if (closed) return;
    try {
      const task = await api.getTaskDetail(taskId, { signal: controller.signal, silent: true });
      if (closed) return;
      failures = 0;
      // Both transports read the same append-only log. Keep the socket cursor
      // so fallback cannot replay already-applied asset updates or errors.
      while (!closed && cursor < task.events.length) dispatch(task.events[cursor]);
      if (TERMINAL_STATES.has(task.status)) finish(task.status);
    } catch {
      if (closed) return;
      failures += 1;
      if (failures === 1) handlers.onError?.("连接中断，正在重试任务状态…");
    }
    if (!closed) {
      pollTimer = setTimeout(
        poll,
        Math.min(MAX_RETRY_MS, POLL_INTERVAL_MS * 2 ** Math.min(failures, 4)),
      );
    }
  }

  function startPolling() {
    if (polling || closed) return;
    polling = true;
    closeSocket();
    void poll();
  }

  try {
    const protocol = location.protocol === "https:" ? "wss" : "ws";
    ws = new WebSocket(`${protocol}://${location.host}/ws/tasks/${taskId}/stream`);
    ws.onmessage = (message) => {
      let event: TaskEvent;
      try {
        event = JSON.parse(message.data as string) as TaskEvent;
        if (!event || typeof event.type !== "string") throw new Error("invalid event");
      } catch {
        startPolling();
        return;
      }
      if (event.type === "ERROR") {
        handlers.onError?.(event.detail ?? "stream error");
        finish("failed");
      } else {
        dispatch(event);
      }
    };
    ws.onerror = startPolling;
    ws.onclose = startPolling;
  } catch {
    startPolling();
  }

  return stop;
}

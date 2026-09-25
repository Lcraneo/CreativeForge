import type { TaskEvent } from "../types";
import { api } from "../api/client";

export interface StreamHandlers {
  onEvent: (event: TaskEvent) => void;
  onEnd: (status: string) => void;
  onError?: (message: string) => void;
}

const DISPATCH_INTERVAL_MS = 170;

/**
 * Follows one task's event stream over WebSocket; falls back to REST polling
 * when the socket cannot be established. Replayed history is dispatched with
 * a small stagger so the agent graph animates even for instant pipelines.
 */
export function streamTask(taskId: string, handlers: StreamHandlers): () => void {
  let closed = false;
  let ended = false;
  const queue: TaskEvent[] = [];

  const dispatchTimer = setInterval(() => {
    if (closed) return;
    const event = queue.shift();
    if (event) handlers.onEvent(event);
    else if (ended) {
      handlers.onEnd(finalStatus);
      stop();
    }
  }, DISPATCH_INTERVAL_MS);

  let finalStatus = "unknown";
  let ws: WebSocket | null = null;
  let pollTimer: ReturnType<typeof setInterval> | null = null;

  function finish(event: TaskEvent) {
    finalStatus = event.status ?? "unknown";
    ended = true;
  }

  function startPolling() {
    if (pollTimer || closed) return;
    let cursor = 0;
    pollTimer = setInterval(async () => {
      if (closed) return;
      try {
        const task = await api.getTaskDetail(taskId);
        for (; cursor < task.events.length; cursor += 1) {
          const event = task.events[cursor];
          if (event.type === "STREAM_END") finish(event);
          else queue.push(event);
        }
        if (!ended && ["pass", "success", "failed"].includes(task.status)) {
          finish({ type: "STREAM_END", status: task.status });
        }
      } catch {
        /* transient poll failure — next tick retries */
      }
    }, 400);
  }

  try {
    const protocol = location.protocol === "https:" ? "wss" : "ws";
    ws = new WebSocket(`${protocol}://${location.host}/ws/tasks/${taskId}/stream`);
    ws.onmessage = (message) => {
      const event = JSON.parse(message.data as string) as TaskEvent;
      if (event.type === "STREAM_END") finish(event);
      else if (event.type === "ERROR") handlers.onError?.(event.detail ?? "stream error");
      else queue.push(event);
    };
    ws.onerror = () => {
      if (!closed && !ended) startPolling();
    };
    ws.onclose = () => {
      if (!closed && !ended) startPolling();
    };
  } catch {
    startPolling();
  }

  function stop() {
    closed = true;
    clearInterval(dispatchTimer);
    if (pollTimer) clearInterval(pollTimer);
    try {
      ws?.close();
    } catch {
      /* already closed */
    }
  }

  return stop;
}

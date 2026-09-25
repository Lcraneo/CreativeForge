"""WebSocket task stream: replays stored events, then follows live ones.

    ws://host/ws/tasks/{task_id}/stream

Event protocol (Phase 8):
    PLAN_CREATED | AGENT_START | AGENT_DONE | PROGRESS | ASSET_UPDATE |
    QUALITY_REPORT | TASK_FAILED | TASK_COMPLETE | STREAM_END
"""

import asyncio

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

POLL_SECONDS = 0.15
TERMINAL_STATES = ("success", "failed", "pass", "fail")


def build_ws_router(runtime):
    router = APIRouter()

    @router.websocket("/ws/tasks/{task_id}/stream")
    async def task_stream(websocket: WebSocket, task_id: str):
        await websocket.accept()
        cursor = 0
        try:
            while True:
                task = runtime.tasks.get(task_id)
                if task is None:
                    await websocket.send_json({
                        "type": "ERROR", "detail": "unknown task"
                    })
                    break

                events = task["events"]
                while cursor < len(events):
                    await websocket.send_json(events[cursor])
                    cursor += 1

                if task["status"] in TERMINAL_STATES and cursor >= len(events):
                    await websocket.send_json({
                        "type": "STREAM_END", "status": task["status"]
                    })
                    break
                await asyncio.sleep(POLL_SECONDS)
        except WebSocketDisconnect:
            return

    return router

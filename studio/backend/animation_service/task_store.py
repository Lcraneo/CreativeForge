"""动画生成任务落盘：进程重启后运行中的任务标记 interrupted（终态）。

视频生成任务（_VIDEO_TASKS）与动作批次（_ACTION_BATCHES）此前是纯内存态，
后端重启即蒸发：前端凭 localStorage 续接的 task_id 变成 404，用户只看到
任务悄悄消失。此模块把两份任务表的快照原子落盘：

- 每次任务状态迁移后 ``save()``（只存任务描述字段，不含源图字节）；
- 进程启动时 ``restore()``：读回快照；仍处于 running 的任务线程已随旧
  进程消亡、永远不会再有状态更新——标记为 interrupted，前端据此显示
  「后端重启中断」并允许重新发起，而不是无限轮询。

不承诺恢复执行：i2v 任务的输入（源图字节、供应商侧任务 ID）没有持久化，
标记中断即语义终点。单进程部署专用，与 persistence.py 同一套原子写约定。
"""

import logging
import os
import threading
import time

from studio.backend.persistence import atomic_write_json, read_json_recover

logger = logging.getLogger(__name__)

# studio/backend/animation_service/task_store.py → studio/backend/data/
DATA_PATH = os.path.normpath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir, "data", "animation_tasks.json")
)

_INTERRUPTED_NOTE = "后端已重启，任务中断——请重新发起生成"
_SAVE_LOCK = threading.Lock()


def _interrupt_video_task(task: dict) -> None:
    task["status"] = "interrupted"
    task["stage"] = "interrupted"
    task["error"] = _INTERRUPTED_NOTE
    task["error_kind"] = "interrupted"


def restore(video_tasks: dict, action_batches: dict, *, path: str = DATA_PATH, max_age: float | None = None) -> int:
    """启动时读回快照：running 标记 interrupted，返回恢复的条数。

    ``max_age`` 传任务 TTL：超过 TTL 的历史条目直接丢弃（与内存态的
    惰性清理同语义），避免久未启动后把陈旧任务灌回内存。"""

    saved = read_json_recover(path)
    if not isinstance(saved, dict):
        return 0
    now = time.time()
    restored = 0
    for task_id, task in (saved.get("video_tasks") or {}).items():
        if not isinstance(task, dict) or task.get("id") != task_id:
            continue
        if max_age is not None and now - (task.get("created_at") or 0) > max_age:
            continue
        if task.get("status") == "running":
            _interrupt_video_task(task)
        video_tasks[task_id] = task
        restored += 1
    for batch_id, batch in (saved.get("action_batches") or {}).items():
        if not isinstance(batch, dict) or batch.get("id") != batch_id:
            continue
        if max_age is not None and now - (batch.get("created_at") or 0) > max_age:
            continue
        if batch.get("status") == "running":
            batch["status"] = "interrupted"
            for entry in batch.get("tasks") or []:
                if isinstance(entry, dict) and entry.get("status") in ("pending", "generating"):
                    entry["status"] = "interrupted"
                    entry["note"] = _INTERRUPTED_NOTE
        action_batches[batch_id] = batch
        restored += 1
    return restored


def save(video_tasks: dict, action_batches: dict, *, path: str = DATA_PATH) -> None:
    """快照落盘（每次状态迁移后调用）。写失败只告警——内存态任务继续运行，
    下一次迁移会再尝试覆盖。"""

    with _SAVE_LOCK:
        payload = {
            "saved_at": time.time(),
            "video_tasks": {
                key: value for key, value in video_tasks.items() if isinstance(value, dict)
            },
            "action_batches": {
                key: value for key, value in action_batches.items() if isinstance(value, dict)
            },
        }
        try:
            atomic_write_json(path, payload)
        except OSError:
            logger.warning("Could not persist animation tasks; keeping in-memory state", exc_info=True)

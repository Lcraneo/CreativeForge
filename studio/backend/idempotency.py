"""生成类 POST 的幂等键存储：同键短窗口内复用首个结果，防重复扣费。

i2v 生成是真实计费请求。客户端的 fetch 不会自动重试 POST，但双击竞态、
代理层重发等仍可能让同一逻辑请求触发两次生成。客户端在「一次用户提交」
里生成一个 Idempotency-Key 随请求头发送；服务端在 TTL 窗口内见到同键：

- 已存任务仍在运行 → 返回已存快照（不重复入队、不重复扣费）；
- 已存任务已终结（done/failed）→ 放行新任务（用户重试同一配置是合法诉求）。

单进程内存实现：重启即清空，与生成任务的内存态生命周期一致（TTL 取
任务 TTL 同量级）。
"""

import threading
import time


class IdempotencyStore:
    def __init__(self, ttl: float = 900.0, clock=time.time):
        self.ttl = ttl
        self.clock = clock
        self._lock = threading.Lock()
        self._entries: dict[str, tuple[object, float]] = {}

    def _prune_locked(self) -> None:
        now = self.clock()
        for key in list(self._entries):
            if now - self._entries[key][1] > self.ttl:
                del self._entries[key]

    def get(self, key: str | None):
        """返回该键已存的值；无键/过期返回 None。"""
        if not key:
            return None
        with self._lock:
            self._prune_locked()
            entry = self._entries.get(key)
            return entry[0] if entry else None

    def put(self, key: str | None, value) -> None:
        if not key:
            return
        with self._lock:
            self._prune_locked()
            self._entries[key] = (value, self.clock())

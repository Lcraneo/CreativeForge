"""JSON 持久化基础设施：原子写 + 损坏自动恢复。

Studio 后端全部持久层是单文件 JSON（history / model settings / storage
configs / play cache）。此前的写入是直接 ``open(path, "w")``：进程在写一半时
被杀会留下截断的 JSON，下次读取静默清零，用户的配置和历史就这么丢掉。

约定：
- ``atomic_write_json``   写临时文件 → 保留上一份好副本到 ``<path>.bak`` →
                          ``os.replace`` 原子落盘（同目录，跨进程可见）。
- ``read_json_recover``   先读主文件；损坏/缺失时回退 ``<path>.bak``；
                          都不可用返回 ``None``，由调用方套默认值。
"""

import json
import os
import shutil


def atomic_write_json(path, data, *, indent=2):
    """原子写 JSON：tmp + rename，成功后旧副本留在 ``<path>.bak``。"""
    directory = os.path.dirname(os.path.abspath(path))
    os.makedirs(directory, exist_ok=True)
    tmp_path = path + ".tmp"
    with open(tmp_path, "w", encoding="utf-8") as handle:
        json.dump(data, handle, ensure_ascii=False, indent=indent)
    if os.path.isfile(path):
        # 只有主文件当前可解析才算"好副本"——损坏文件不值得备份
        try:
            with open(path, "r", encoding="utf-8") as handle:
                json.load(handle)
            shutil.copyfile(path, path + ".bak")
        except (ValueError, OSError):
            pass
    os.replace(tmp_path, path)


def read_json_recover(path):
    """读 JSON，主文件损坏时回退 ``<path>.bak``；两处都不可用返回 ``None``。"""
    for candidate in (path, path + ".bak"):
        if not os.path.isfile(candidate):
            continue
        try:
            with open(candidate, "r", encoding="utf-8") as handle:
                return json.load(handle)
        except (ValueError, OSError):
            continue
    return None

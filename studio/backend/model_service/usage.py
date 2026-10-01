"""用量台账（额度仪表）：本地估算，非账单。

DashScope 不提供余额查询 API，这里在每次第三方模型调用成功后记录一条
（时间/类别/模型），按内置牌价估算金额。牌价随时可能调整、促销与免费
额度也无法感知——数字仅供趋势参考，精确用量以服务商控制台为准。

牌价可用 ``usage_prices.json`` 覆盖（格式与 PRICES 相同的
``"kind|model": 元/次`` 扁平键）。
"""

import os
import threading
import time

from studio.backend.persistence import atomic_write_json

_LEDGER_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "usage_ledger.json")
_PRICES_OVERRIDE_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "usage_prices.json"
)
_MAX_ENTRIES = 5000

# 内置估算牌价（元/次成功调用；近似值，2026-10 整理）
# video 按 5 秒/条估算（i2v 默认时长）；chat 按单轮对话典型 token 估算
PRICES = {
    "image|wanx2.1-t2i-turbo": 0.14,
    "image|wanx2.1-t2i-plus": 0.20,
    "image|gpt-image-1": 0.30,
    "image|cogview-3-flash": 0.0,
    "image|Kwai-Kolors/Kolors": 0.14,
    "edit|qwen-image-edit": 0.30,
    "edit|wanx2.1-imageedit": 0.20,
    "video|wan2.2-i2v-plus": 3.50,
    "video|wan2.2-i2v-flash": 1.25,
    "video|wanx2.1-i2v-turbo": 1.00,
    "chat|*": 0.004,
}
_DEFAULT_PRICE = 0.15

_lock = threading.Lock()
_ledger: list | None = None


def _load():
    global _ledger
    if _ledger is not None:
        return _ledger
    try:
        import json

        with open(_LEDGER_PATH, "r", encoding="utf-8") as handle:
            data = json.load(handle)
        _ledger = data if isinstance(data, list) else []
    except (ValueError, OSError):
        _ledger = []
    return _ledger


def _save():
    atomic_write_json(_LEDGER_PATH, _ledger or [])


def _prices():
    """内置牌价 + 用户覆盖（usage_prices.json）。"""
    prices = dict(PRICES)
    try:
        import json

        with open(_PRICES_OVERRIDE_PATH, "r", encoding="utf-8") as handle:
            override = json.load(handle)
        if isinstance(override, dict):
            prices.update({str(k): float(v) for k, v in override.items()})
    except (ValueError, TypeError, OSError):
        pass
    return prices


def price_for(kind, model):
    prices = _prices()
    key = "{}|{}".format(kind, model or "")
    if key in prices:
        return prices[key]
    return prices.get(kind + "|*", _DEFAULT_PRICE)


def record_usage(kind, model, meta=None):
    """记录一次成功调用（image/edit/video/chat）。永不抛错——统计不能
    影响业务链路。"""

    try:
        with _lock:
            ledger = _load()
            ledger.append(
                {"at": time.time(), "kind": str(kind or "?"), "model": str(model or "?"),
                 "meta": meta or {}}
            )
            if len(ledger) > _MAX_ENTRIES:
                del ledger[: len(ledger) - _MAX_ENTRIES]
            _save()
    except Exception:  # noqa: BLE001
        pass


def clear_usage():
    with _lock:
        global _ledger
        _ledger = []
        _save()


def _day_start(ts):
    t = time.localtime(ts)
    return time.mktime((t.tm_year, t.tm_mon, t.tm_mday, 0, 0, 0, 0, 0, -1))


def usage_summary():
    ledger = _load()
    now = time.time()
    today0 = _day_start(now)
    week0 = today0 - 6 * 86400
    month0 = today0 - 29 * 86400
    prices = _prices()

    totals = {"today": 0.0, "week": 0.0, "month": 0.0}
    by_kind: dict[str, dict] = {}
    by_model: dict[str, dict] = {}
    days: dict[str, dict] = {}
    for entry in ledger:
        at = entry.get("at", 0)
        kind = entry.get("kind", "?")
        model = entry.get("model", "?")
        cost = price_for(kind, model)
        if at >= today0:
            totals["today"] += cost
        if at >= week0:
            totals["week"] += cost
        if at >= month0:
            totals["month"] += cost
            kind_bucket = by_kind.setdefault(kind, {"kind": kind, "calls": 0, "cost": 0.0})
            kind_bucket["calls"] += 1
            kind_bucket["cost"] += cost
            model_bucket = by_model.setdefault(
                "{}|{}".format(kind, model), {"kind": kind, "model": model, "calls": 0, "cost": 0.0}
            )
            model_bucket["calls"] += 1
            model_bucket["cost"] += cost
            date = time.strftime("%Y-%m-%d", time.localtime(at))
            day_bucket = days.setdefault(date, {"date": date, "calls": 0, "cost": 0.0})
            day_bucket["calls"] += 1
            day_bucket["cost"] += cost

    KIND_ORDER = {"video": 0, "image": 1, "edit": 2, "chat": 3}
    return {
        "totals": {k: round(v, 2) for k, v in totals.items()},
        "currency": "CNY",
        "by_kind": sorted(
            by_kind.values(), key=lambda b: (KIND_ORDER.get(b["kind"], 9), -b["calls"])
        ),
        "by_model": sorted(by_model.values(), key=lambda b: -b["cost"]),
        "days": [days[key] for key in sorted(days, reverse=True)[:14]],
        "recent": list(reversed(ledger[-10:])),
        "prices": prices,
        "note": "本地估算（内置牌价，可用 usage_prices.json 覆盖）；非账单，精确用量以服务商控制台为准",
    }

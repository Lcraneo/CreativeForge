"""一次性历史数据修复：把以基础动作词入账的自定义动画迁移到 custom: 命名空间。

缺陷背景（2026-10-06 修复前生成的记录）：自定义动作经 i2v 链生成时，
meta.requested_action 记的是运动族词（walk/idle），导致：
- 试玩舞台按动作名匹配时自定义动画抢占内置条带（用户实测「敲竹板」抢占 walk）；
- 批次补齐把内置动作误判为已交付而跳过。

修复判据（确定性，无猜测）：custom_motion_prompt_cache.json 里每个自定义
描述对应的润色英文子句是自定义链路的唯一产物——meta.motion_prompt 以该
子句开头 ⇒ 该记录必出自自定义动作生成。子句 → 自定义动作名的映射通过
重算缓存 key（sha1(chat_model + "|" + 描述)）恢复；模型名从
model_settings(.bak) 收集，映射不上的子句人工指认。

运行一次即可：python studio/backend/tools/repair_custom_action_identity.py
"""

import hashlib
import json
import os
import sys
import time

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..")))

from studio.backend.persistence import atomic_write_json  # noqa: E402

BACKEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
DATA_DIR = os.path.join(BACKEND_DIR, "data")
ANIMATION_DIR = os.path.join(DATA_DIR, "animation")
CUSTOM_ACTION_PREFIX = "custom:"  # 与 service.py 的命名空间前缀保持一致
CUSTOM_ACTIONS_PATH = os.path.join(ANIMATION_DIR, "custom_actions.json")
PROMPT_CACHE_PATH = os.path.join(DATA_DIR, "custom_motion_prompt_cache.json")
MODEL_SETTINGS_CANDIDATES = [
    os.path.join(DATA_DIR, "model_settings.json"),
    os.path.join(DATA_DIR, "model_settings.json.bak"),
]


def collect_chat_models() -> list[str]:
    models: list[str] = []
    for path in MODEL_SETTINGS_CANDIDATES:
        try:
            with open(path, "r", encoding="utf-8") as handle:
                settings = json.load(handle)
        except (OSError, ValueError):
            continue
        for key in ("chat_model", "model"):
            value = settings.get(key)
            if isinstance(value, str) and value and value not in models:
                models.append(value)
        for preset in settings.get("presets") or []:
            if isinstance(preset, dict):
                for key in ("chat_model", "model"):
                    value = preset.get(key)
                    if isinstance(value, str) and value and value not in models:
                        models.append(value)
    return models


def main() -> int:
    with open(CUSTOM_ACTIONS_PATH, "r", encoding="utf-8") as handle:
        custom_actions = json.load(handle)
    with open(PROMPT_CACHE_PATH, "r", encoding="utf-8") as handle:
        prompt_cache = json.load(handle)

    # 描述全集：当前描述 + 修改历史里的旧描述（编辑过的动作两代描述都可能
    # 有产物在外）
    descriptions: list[tuple[str, str]] = []  # (description, action_name)
    for name, item in custom_actions.items():
        descriptions.append((item.get("description") or "", name))
        for old in item.get("history") or []:
            descriptions.append((old.get("description") or "", name))

    models = collect_chat_models()
    clause_to_name: dict[str, str] = {}
    unmapped_clauses = set(prompt_cache.values())
    for description, name in descriptions:
        if not description:
            continue
        # 直接重算缓存 key（与 custom_motion_clause 的缓存读同构），不发请求
        for model in models + [""]:
            key = "custom|" + hashlib.sha1("|".join([model, description]).encode("utf-8")).hexdigest()[:20]
            cached = prompt_cache.get(key)
            if isinstance(cached, str) and cached:
                clause_to_name[cached] = name
                unmapped_clauses.discard(cached)

    # 重算仍未覆盖的缓存子句：按语义前缀人工指认（缓存 key 的 chat_model
    # 已不在 model_settings 中，无法重算）。子句与描述一一对应、肉眼可核。
    MANUAL_CLAUSE_MAP = {
        "Bend deeply at the waist": "鞠躬致意",
        "Bend forward at the waist": "鞠躬致意",
        "Standing still, one hand rhythmically taps a bamboo clapper": "原地敲竹板待机循环动画",
    }
    for clause in sorted(unmapped_clauses):
        name = next(
            (name for prefix, name in MANUAL_CLAUSE_MAP.items() if clause.startswith(prefix)),
            None,
        )
        if name:
            clause_to_name[clause] = name
            unmapped_clauses.discard(clause)

    print("== 子句 → 自定义动作映射 ==")
    for clause, name in clause_to_name.items():
        print(f"  [{name}] {clause[:70]}…")
    for clause in sorted(unmapped_clauses):
        print(f"  [未映射] {clause[:70]}…")
    if unmapped_clauses:
        print("!! 存在未映射子句——请人工确认后修改脚本 clause_to_name 再跑")
        return 2

    import glob

    repaired = 0
    for meta_path in sorted(glob.glob(os.path.join(ANIMATION_DIR, "*.json"))):
        if os.path.basename(meta_path) == "custom_actions.json":
            continue
        try:
            with open(meta_path, "r", encoding="utf-8") as handle:
                meta = json.load(handle)
        except (OSError, ValueError):
            continue
        motion_prompt = meta.get("motion_prompt") or ""
        matched_name = next(
            (name for clause, name in clause_to_name.items() if motion_prompt.startswith(clause)),
            None,
        )
        if not matched_name:
            continue
        if meta.get("custom_action") == matched_name and str(meta.get("requested_action") or "").startswith(
            CUSTOM_ACTION_PREFIX
        ):
            continue  # 已修复过
        before = meta.get("requested_action")
        meta["requested_action"] = CUSTOM_ACTION_PREFIX + matched_name
        meta["custom_action"] = matched_name
        meta["legacy_identity_repair"] = {"from": before, "at": time.time()}
        atomic_write_json(meta_path, meta)
        repaired += 1
        print(f"修复 {os.path.basename(meta_path)}: requested_action {before!r} -> custom:{matched_name!r}")
    print(f"== 完成：修复 {repaired} 条记录 ==")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

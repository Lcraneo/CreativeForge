"""Generate reusable PVE enemies separately from player characters."""

from __future__ import annotations

import hashlib
import json
import os
import re
import threading
import time
import uuid
from typing import Callable

from studio.backend.persistence import atomic_write_json, read_json_recover

DEFAULT_PVE_ENEMY_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "data",
    "pve_enemies.json",
)

DIFFICULTIES = ("easy", "normal", "hard")
ROLES = ("minion", "boss")
BEHAVIORS = ("chaser", "shooter", "charger", "guardian")
TAGS = (
    "fast",
    "ranged",
    "flying",
    "armored",
    "ice",
    "fire",
    "toxic",
    "beast",
    "undead",
    "construct",
)

_ELEMENT_COLORS = {
    "ice": "#8feaff",
    "fire": "#ff9b62",
    "toxic": "#9fe56f",
    "arcane": "#c8a6ff",
    "earth": "#c7b089",
    "physical": "#e8d49d",
}


def _builtin_profiles() -> list[dict]:
    return [
        {
            "id": "builtin_slime",
            "name": "森林史莱姆",
            "role": "minion",
            "prompt": "森林史莱姆，圆润果冻身体，近身追踪并喷射酸液",
            "summary": "基础近战与酸液攻击的小型怪物",
            "tags": ["toxic", "beast"],
            "behavior": "chaser",
            "element": "toxic",
            "projectile_color": _ELEMENT_COLORS["toxic"],
            "asset_id": "ast64960",
            "status": "ready",
            "builtin": True,
            "stats": {
                "max_hp": 3,
                "speed": 72,
                "damage": 1,
                "attack_interval": 2.4,
                "display_height": 92,
            },
            "created_at": 0,
            "updated_at": 0,
        },
        {
            "id": "builtin_frost_dragon",
            "name": "冰霜巨龙",
            "role": "boss",
            "prompt": "冰霜巨龙 Boss，双翼展开，冰晶鳞片，发射冰弹守关",
            "summary": "冰霜古堡的巨型守关 Boss",
            "tags": ["ice", "flying", "beast"],
            "behavior": "guardian",
            "element": "ice",
            "projectile_color": _ELEMENT_COLORS["ice"],
            "asset_id": "ast60574",
            "status": "ready",
            "builtin": True,
            "stats": {
                "max_hp": 24,
                "speed": 42,
                "damage": 2,
                "attack_interval": 1.35,
                "display_height": 224,
            },
            "created_at": 0,
            "updated_at": 0,
        },
    ]


class PveEnemyStore:
    def __init__(self, path: str | None = None):
        self.path = path or DEFAULT_PVE_ENEMY_PATH
        self._lock = threading.Lock()
        self._custom: dict[str, dict] = {}
        self._load()

    def _load(self):
        data = read_json_recover(self.path)
        records = data.get("enemies") if isinstance(data, dict) else None
        if not isinstance(records, list):
            return
        for record in records:
            if not isinstance(record, dict) or not record.get("id"):
                continue
            if record.get("status") in {
                "analyzing",
                "generating_model",
                "generating_actions",
            }:
                record["status"] = "failed"
                record["error"] = "服务重启导致生成中断，请重新生成"
            self._custom[str(record["id"])] = record

    def _save_locked(self):
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        atomic_write_json(
            self.path,
            {"enemies": list(self._custom.values())},
            indent=2,
        )

    def list(self) -> list[dict]:
        with self._lock:
            custom = [dict(item) for item in self._custom.values()]
        return _builtin_profiles() + sorted(
            custom, key=lambda item: item.get("created_at", 0), reverse=True
        )

    def ready(self) -> list[dict]:
        return [item for item in self.list() if item.get("status") == "ready"]

    def get(self, enemy_id: str) -> dict | None:
        for item in _builtin_profiles():
            if item["id"] == enemy_id:
                return item
        with self._lock:
            item = self._custom.get(enemy_id)
            return dict(item) if item else None

    def save(self, record: dict) -> dict:
        record = dict(record)
        record["updated_at"] = time.time()
        with self._lock:
            self._custom[str(record["id"])] = record
            self._save_locked()
        return dict(record)

    def update(self, enemy_id: str, patch: dict) -> dict | None:
        with self._lock:
            record = self._custom.get(enemy_id)
            if record is None:
                return None
            record.update(patch)
            record["updated_at"] = time.time()
            self._save_locked()
            return dict(record)

    def delete(self, enemy_id: str) -> bool:
        with self._lock:
            if self._custom.pop(enemy_id, None) is None:
                return False
            self._save_locked()
            return True


def _json_object(text: str) -> dict:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\s*```$", "", cleaned)
    match = re.search(r"\{.*\}", cleaned, flags=re.DOTALL)
    if not match:
        raise ValueError("模型未返回 JSON")
    value = json.loads(match.group(0))
    if not isinstance(value, dict):
        raise ValueError("模型返回值不是对象")
    return value


def _fallback_analysis(prompt: str) -> dict:
    lowered = prompt.lower()
    tags = []
    keyword_groups = {
        "fast": ("快速", "迅捷", "轻巧", "fast", "swift"),
        "ranged": ("远程", "射击", "喷射", "法术", "ranged", "shoot", "spit"),
        "flying": ("飞行", "翼", "龙", "flying", "wing", "dragon"),
        "armored": ("重甲", "盔甲", "机械", "armored", "armor", "mechanical"),
        "ice": ("冰", "霜", "雪", "frost", "ice"),
        "fire": ("火", "熔岩", "烈焰", "fire", "lava"),
        "toxic": ("毒", "酸", "腐", "toxic", "acid"),
        "beast": ("兽", "狼", "虫", "史莱姆", "beast", "wolf", "insect", "slime"),
        "undead": ("亡灵", "骷髅", "幽魂", "undead", "skeleton", "ghost"),
        "construct": ("机械", "魔像", "构装", "construct", "golem", "robot"),
    }
    for tag, words in keyword_groups.items():
        if any(word in lowered for word in words):
            tags.append(tag)
    if not tags:
        tags = ["beast"]
    behavior = "shooter" if "ranged" in tags else "charger" if "fast" in tags else "chaser"
    element = next(
        (tag for tag in ("ice", "fire", "toxic") if tag in tags),
        "physical",
    )
    return {
        "name": prompt.strip().split("，")[0][:18] or "自定义敌人",
        "summary": prompt.strip()[:90],
        "tags": tags,
        "behavior": behavior,
        "element": element,
    }


class PveEnemyService:
    def __init__(
        self,
        runtime,
        store: PveEnemyStore | None = None,
        chat_fn: Callable[[str, dict], str] | None = None,
    ):
        self.runtime = runtime
        self.store = store or PveEnemyStore()
        self._chat_fn = chat_fn or self._chat
        self.claim_builtin_assets()

    def claim_builtin_assets(self) -> None:
        """Classify bundled enemies as PVE resources instead of player candidates."""

        history = getattr(self.runtime, "history", None)
        if history is None:
            return
        for profile in _builtin_profiles():
            history.patch_asset(
                profile["asset_id"],
                {"pve_enemy": True, "pve_role": profile["role"]},
            )

    def ready_profiles(self) -> list[dict]:
        return self.store.ready()

    def start_generation(
        self, prompt: str, role: str, difficulty: str = "normal"
    ) -> dict:
        now = time.time()
        enemy_id = "pve_" + uuid.uuid4().hex[:10]
        record = {
            "id": enemy_id,
            "name": "正在分析敌人",
            "role": role,
            "prompt": prompt.strip()[:1200],
            "summary": "",
            "tags": [],
            "behavior": "chaser",
            "element": "physical",
            "projectile_color": _ELEMENT_COLORS["physical"],
            "asset_id": None,
            "status": "analyzing",
            "builtin": False,
            "difficulty": difficulty,
            "stats": self._stats(role, difficulty, "chaser", []),
            "created_at": now,
            "updated_at": now,
            "error": None,
            "action_warning": None,
        }
        self.store.save(record)
        threading.Thread(
            target=self._run,
            args=(enemy_id,),
            name=f"creativeforge-pve-enemy-{enemy_id}",
            daemon=True,
        ).start()
        return record

    def _run(self, enemy_id: str):
        record = self.store.get(enemy_id)
        if record is None:
            return
        try:
            analysis = self._analyze(
                record["prompt"],
                record["role"],
                record.get("difficulty") or "normal",
                self.runtime.model_settings.effective(),
            )
            stats = self._stats(
                record["role"],
                record.get("difficulty") or "normal",
                analysis["behavior"],
                analysis["tags"],
            )
            record = self.store.update(
                enemy_id,
                {
                    **analysis,
                    "stats": stats,
                    "projectile_color": _ELEMENT_COLORS.get(
                        analysis["element"], _ELEMENT_COLORS["physical"]
                    ),
                    "status": "generating_model",
                },
            )
            task_id = self.runtime.start_task(
                self._asset_prompt(record), overrides={"style": "pixel"}
            )
            self.store.update(enemy_id, {"task_id": task_id})
            task = self._wait_task(task_id)
            asset_id = task.get("asset_id")
            if not asset_id:
                raise RuntimeError(task.get("error") or "敌人模型生成失败")
            tag = {"pve_enemy": True, "pve_role": record.get("role") or "minion"}
            asset = self.runtime.assets.get(asset_id)
            if isinstance(asset, dict):
                asset.update(tag)
                self.runtime.assets.save(asset)
            for _ in range(10):
                if self.runtime.history.patch_asset(asset_id, tag):
                    break
                time.sleep(0.1)
            self.store.update(
                enemy_id,
                {
                    "asset_id": asset_id,
                    "status": "generating_actions",
                    "error": None,
                },
            )
            warning = self._generate_actions(enemy_id, asset_id)
            if not warning:
                warning = self._prepack_ai_strips(asset_id)
            self.store.update(
                enemy_id,
                {
                    "status": "ready",
                    "action_warning": warning,
                    "error": None,
                },
            )
        except Exception as error:  # noqa: BLE001 - async generation must reach terminal state
            self.store.update(
                enemy_id,
                {"status": "failed", "error": str(error)[:500]},
            )

    def _wait_task(self, task_id: str) -> dict:
        deadline = time.time() + 420
        while time.time() < deadline:
            task = self.runtime.tasks.get(task_id) or {}
            if task.get("status") not in ("running", None):
                return task
            time.sleep(0.5)
        raise RuntimeError("敌人模型生成超时")

    def _generate_actions(self, enemy_id: str, asset_id: str) -> str | None:
        from studio.backend.animation_service.service import AnimationService

        settings = self.runtime.model_settings.effective()
        if not (settings.get("enabled") and settings.get("api_key")):
            return "动作模型未启用，试玩时将使用程序化动作"
        asset = self.runtime.assets.get(asset_id)
        if asset is None:
            record = self.runtime.history.get(asset_id)
            asset = record.get("asset") if record else None
        if not isinstance(asset, dict):
            return "敌人资产记录不可用，试玩时将使用程序化动作"
        service = AnimationService(
            os.path.join(
                os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                "data",
                "animation",
            )
        )
        source = service._asset_render(asset, view="front")
        if not source:
            return "敌人正面源图不可用，试玩时将使用程序化动作"
        actions = ["idle", "walk", "attack"]
        views = {action: "front" for action in actions}
        batch_id = service.start_action_batch(
            asset_id,
            source,
            settings,
            actions=actions,
            enhance_context=f"{asset.get('name') or ''}；PVE 敌人",
            views_by_action=views,
        )
        self.store.update(enemy_id, {"action_batch_id": batch_id})
        deadline = time.time() + 360
        while time.time() < deadline:
            snapshot = service.action_batch_snapshot(batch_id) or {}
            if snapshot.get("status") in ("done", "failed", "interrupted"):
                if snapshot.get("status") == "done":
                    failed = int(snapshot.get("failed_count") or 0)
                    return f"{failed} 个动作生成失败，已回退程序化动作" if failed else None
                return "AI 动作生成失败，已回退程序化动作"
            time.sleep(1)
        return "AI 动作生成超时，已回退程序化动作"

    def _prepack_ai_strips(self, asset_id: str) -> str | None:
        """Build playtest strips once so first PVE entry only loads PNGs."""

        import re as _re

        from PIL import Image

        from artgen.sourceanim import cutout_white_background
        from studio.backend.animation_service.service import collect_ai_strips

        animation_dir = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "data",
            "animation",
        )
        cache_dir = os.path.join(animation_dir, "play_cache")
        os.makedirs(cache_dir, exist_ok=True)
        actions = ["idle", "walk", "attack"]
        views = {action: "front" for action in actions}
        strips = collect_ai_strips(
            animation_dir,
            asset_id,
            actions,
            view_by_action=views,
        )
        for action in actions:
            meta = strips.get(action)
            if not meta:
                continue
            frame_files = [
                os.path.join(animation_dir, os.path.basename(url))
                for url in (meta.get("frame_urls") or [])
            ]
            samples = [path for path in frame_files if os.path.isfile(path)]
            if len(samples) < 4:
                continue
            digest = hashlib.sha1(
                "ai|matte-v3|{}|{}".format(meta.get("id"), len(frame_files)).encode()
            ).hexdigest()[:10]
            safe_action = _re.sub(
                r"[^\w-]+", "_", str(meta.get("requested_action") or action), flags=_re.UNICODE
            )
            out_path = os.path.join(
                cache_dir,
                "play_ai_{}_{}_matte-v3.png".format(safe_action, digest),
            )
            if os.path.isfile(out_path):
                continue
            images = []
            try:
                for path in samples:
                    with Image.open(path) as handle:
                        frame = cutout_white_background(handle)
                    if frame is None:
                        images = []
                        break
                    if frame.width > 288:
                        frame = (
                            frame.convert("RGBa")
                            .resize(
                                (288, max(1, int(frame.height * 288 / frame.width))),
                                Image.LANCZOS,
                            )
                            .convert("RGBA")
                        )
                    images.append(frame)
            except Exception:
                images = []
            if not images:
                continue
            frame_w = max(image.width for image in images)
            frame_h = max(image.height for image in images)
            sheet = Image.new("RGBA", (frame_w * len(images), frame_h), (0, 0, 0, 0))
            for index, frame in enumerate(images):
                sheet.paste(
                    frame,
                    (index * frame_w + (frame_w - frame.width) // 2, frame_h - frame.height),
                )
            sheet.save(out_path, "PNG")
        missing = [action for action in actions if action not in strips]
        return (
            "部分动作条带未预打包，首次进入时将使用程序化动作" if missing else None
        )

    def _analyze(
        self, prompt: str, role: str, difficulty: str, settings: dict
    ) -> dict:
        system_prompt = (
            "你是 2D 横版 PVE 敌人设计师。只返回一个 JSON 对象，不要坐标、代码或解释。\n"
            "根据敌人描述提取：name(中文短名)、summary(中文一句话)、"
            "tags(仅可从 fast,ranged,flying,armored,ice,fire,toxic,beast,undead,construct 选择)、"
            "behavior(chaser/shooter/charger/guardian 之一)、element"
            "(physical/ice/fire/toxic/arcane/earth 之一)。\n"
            f"角色类型：{role}；难度：{difficulty}。\n"
            f"敌人描述：{prompt}"
        )
        try:
            raw = _json_object(self._chat_fn(system_prompt, settings))
            fallback = _fallback_analysis(prompt)
            tags = [
                str(tag)
                for tag in (raw.get("tags") if isinstance(raw.get("tags"), list) else [])
                if str(tag) in TAGS
            ]
            behavior = str(raw.get("behavior") or "")
            if behavior not in BEHAVIORS:
                behavior = fallback["behavior"]
            element = str(raw.get("element") or "")
            if element not in _ELEMENT_COLORS:
                element = fallback["element"]
            return {
                "name": str(raw.get("name") or fallback["name"])[:24],
                "summary": str(raw.get("summary") or fallback["summary"])[:120],
                "tags": tags or fallback["tags"],
                "behavior": behavior,
                "element": element,
            }
        except Exception:
            return _fallback_analysis(prompt)

    @staticmethod
    def _stats(
        role: str, difficulty: str, behavior: str, tags: list[str]
    ) -> dict:
        if difficulty not in DIFFICULTIES:
            difficulty = "normal"
        if role not in ROLES:
            role = "minion"
        if role == "boss":
            stats = {
                "max_hp": {"easy": 18, "normal": 24, "hard": 32}[difficulty],
                "speed": 44,
                "damage": 2,
                "attack_interval": 1.4,
                "display_height": 224,
            }
        else:
            stats = {
                "max_hp": {"easy": 2, "normal": 3, "hard": 4}[difficulty],
                "speed": {"easy": 62, "normal": 74, "hard": 88}[difficulty],
                "damage": 1,
                "attack_interval": 2.3,
                "display_height": 92,
            }
        if behavior == "charger":
            stats["speed"] += 18
            stats["attack_interval"] = max(1.1, stats["attack_interval"] - 0.3)
        elif behavior == "shooter":
            stats["speed"] = max(45, stats["speed"] - 12)
            stats["attack_interval"] = max(1.0, stats["attack_interval"] - 0.25)
        elif behavior == "guardian":
            stats["max_hp"] += 4 if role == "boss" else 1
        if "flying" in tags:
            stats["display_height"] += 12
        return stats

    @staticmethod
    def _asset_prompt(record: dict) -> str:
        role = "PVE 守关 Boss，压迫感体型" if record["role"] == "boss" else "PVE 小怪"
        tags = "、".join(record.get("tags") or [])
        return (
            f"{record['prompt']}。{role}，{tags}。"
            "2D 横版游戏敌人，单人全身，轮廓清晰，适合游戏剪影识别，"
            "像素风与动漫平涂均可，纯白背景，无地面、无文字、无边框、无其他人物。"
        )

    @staticmethod
    def _chat(prompt: str, settings: dict) -> str:
        import httpx

        base_url = (settings.get("base_url") or "").rstrip("/")
        api_key = settings.get("api_key")
        model = settings.get("chat_model") or settings.get("model")
        if not base_url or not api_key or not model:
            raise RuntimeError("对话模型未配置完整")
        response = httpx.post(
            base_url + "/chat/completions",
            headers={"Authorization": "Bearer " + api_key, "Content-Type": "application/json"},
            json={
                "model": model,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.35,
            },
            timeout=float(settings.get("timeout", 60)),
        )
        response.raise_for_status()
        return response.json()["choices"][0]["message"]["content"].strip()

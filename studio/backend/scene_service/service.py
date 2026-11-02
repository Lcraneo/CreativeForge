"""Scene generation orchestration, model calls, and JSON persistence."""

from __future__ import annotations

import copy
import json
import os
import re
import shutil
import threading
import time
import uuid
from typing import Any, Callable

import httpx

from studio.backend.model_service.service import ImageProvider, safe_generated_path
from studio.backend.persistence import atomic_write_json, read_json_recover
from studio.backend.scene_service.compiler import (
    compile_pve,
    compile_parkour,
    normalize_intent,
    validate_pve,
    validate_parkour,
)

SCENE_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "scenes"
)
DEFAULT_SCENE_PATH = os.path.join(SCENE_DIR, "scenes.json")
_SAFE_ID = re.compile(r"^scene_[0-9a-f]{12}$")
BACKGROUND_COUNT_BY_LENGTH = {"short": 3, "medium": 5, "long": 7}
PVE_BACKGROUND_COUNT = 3
_BACKGROUND_SHOTS = (
    "opening establishing panorama at the entrance of the route",
    "early route with the first foreground landmarks and layered depth",
    "middle of the route, a different landmark from the opening view",
    "deep route transition with elevated terrain and distant silhouettes",
    "approach to the final area with the destination visible ahead",
    "final ascent with a strong vertical landmark and colder light",
    "destination gate or exit vista that concludes the environment",
)
_PVE_BACKGROUND_SHOTS = (
    "stage 1 battlefield establishing shot: one continuous seamless ground plane "
    "stretching from the immediate foreground to the distant horizon, strong "
    "perspective depth with a low horizon line, distant landmarks and clear "
    "foreground-to-background scale",
    "stage 2 battlefield view: the same continuous ground plane pushing deeper "
    "into hostile territory, different landmarks from stage 1, clear depth "
    "layers and a fully walkable floor",
    "stage 3 boss lair: a continuous ground floor leading to a distant focal "
    "landmark, ominous rim light and strong depth from foreground to the boss "
    "position",
)


def _json_object(text: str) -> dict:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\s*```$", "", cleaned)
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start < 0 or end <= start:
        raise ValueError("模型未返回 JSON 对象")
    value = json.loads(cleaned[start : end + 1])
    if not isinstance(value, dict):
        raise ValueError("模型返回的 JSON 顶层必须是对象")
    return value


class SceneStore:
    def __init__(self, path: str = DEFAULT_SCENE_PATH):
        self.path = path
        self.scene_dir = os.path.dirname(os.path.abspath(path))
        self._lock = threading.Lock()
        self._records: dict[str, dict] = {}
        self._load()

    def _load(self) -> None:
        data = read_json_recover(self.path)
        if isinstance(data, list):
            self._records = {
                record["id"]: record
                for record in data
                if isinstance(record, dict) and isinstance(record.get("id"), str)
            }
        interrupted = False
        legacy = False
        for record in self._records.values():
            if record.get("status") == "generating":
                record["status"] = "failed"
                record["error"] = "后端服务重启，生成任务已中断"
                record["generation"] = {
                    **(record.get("generation") or {}),
                    "stage": "interrupted",
                }
                interrupted = True
            gameplay = record.get("gameplay") or {}
            if (
                gameplay.get("type") == "pve"
                and gameplay.get("level")
                and not gameplay.get("campaign")
                and not gameplay.get("legacy")
            ):
                gameplay["legacy"] = True
                record["gameplay"] = gameplay
                legacy = True
        if interrupted or legacy:
            self._save_locked()

    def _save_locked(self) -> None:
        atomic_write_json(
            self.path,
            sorted(self._records.values(), key=lambda item: item.get("created_at", 0)),
        )

    def upsert(self, record: dict) -> dict:
        with self._lock:
            self._records[record["id"]] = record
            self._save_locked()
            return dict(record)

    def update(self, scene_id: str, patch: dict) -> dict | None:
        with self._lock:
            record = self._records.get(scene_id)
            if record is None:
                return None
            record.update(patch)
            self._save_locked()
            return dict(record)

    def get(self, scene_id: str) -> dict | None:
        with self._lock:
            record = self._records.get(scene_id)
            return dict(record) if record is not None else None

    def list(self, limit: int = 20) -> list[dict]:
        with self._lock:
            records = sorted(
                self._records.values(),
                key=lambda item: item.get("created_at", 0),
                reverse=True,
            )[:limit]
        summaries = []
        for record in records:
            gameplay = record.get("gameplay") or {}
            level = gameplay.get("level") or {}
            campaign = gameplay.get("campaign") or {}
            theme = record.get("theme") or {}
            background_urls = theme.get("background_urls") or (
                [theme["background_url"]] if theme.get("background_url") else []
            )
            enemy_count = (
                sum(len(stage.get("enemies") or []) for stage in campaign.get("stages") or [])
                if campaign.get("stages")
                else len(level.get("enemies") or [])
            )
            summaries.append(
                {
                    "id": record.get("id"),
                    "title": record.get("title"),
                    "prompt": record.get("prompt"),
                    "status": record.get("status"),
                    "stage": (record.get("generation") or {}).get("stage"),
                    "gameplay_type": gameplay.get("type") or "parkour",
                    "legacy": bool(gameplay.get("legacy")),
                    "difficulty": gameplay.get("difficulty"),
                    "background_url": theme.get("background_url"),
                    "background_count": len(background_urls),
                    "coin_count": len(level.get("coins") or []),
                    "enemy_count": enemy_count,
                    "created_at": record.get("created_at"),
                    "error": record.get("error"),
                }
            )
        return summaries

    def delete(self, scene_id: str) -> bool:
        with self._lock:
            if self._records.pop(scene_id, None) is None:
                return False
            self._save_locked()
        for name in os.listdir(self.scene_dir):
            if name == f"{scene_id}.png" or (
                name.startswith(f"{scene_id}_") and name.endswith(".png")
            ):
                os.remove(os.path.join(self.scene_dir, name))
        return True

    def background_path(self, scene_id: str, index: int = 0) -> str | None:
        if not _SAFE_ID.fullmatch(scene_id):
            return None
        if index < 0:
            return None
        with self._lock:
            if scene_id not in self._records:
                return None
        path = os.path.join(self.scene_dir, f"{scene_id}_{index}.png")
        if os.path.isfile(path):
            return path
        legacy = os.path.join(self.scene_dir, f"{scene_id}.png")
        return legacy if index == 0 and os.path.isfile(legacy) else None


class SceneService:
    def __init__(
        self,
        store: SceneStore | None = None,
        settings_provider: Callable[[], dict] | None = None,
        chat_fn: Callable[[str, dict], str] | None = None,
        image_fn: Callable[[str, dict], dict] | None = None,
        pve_enemy_provider: Callable[[], list[dict]] | None = None,
    ):
        self.store = store or SceneStore()
        self._settings_provider = settings_provider or (lambda: {})
        self._chat_fn = chat_fn or self._chat
        self._image_fn = image_fn or self._generate_background
        self._pve_enemy_provider = pve_enemy_provider or (lambda: [])

    def start(
        self, prompt: str, difficulty: str = "normal", gameplay: str = "parkour"
    ) -> dict:
        now = time.time()
        scene_id = "scene_" + uuid.uuid4().hex[:12]
        record = {
            "schema_version": 1,
            "id": scene_id,
            "title": "正在构建场景",
            "prompt": prompt.strip()[:2000],
            "status": "generating",
            "gameplay": {
                "type": gameplay,
                "difficulty": difficulty,
                "level": None,
            },
            "theme": {
                "summary": "",
                "palette": {},
                "background_url": None,
                "background_urls": [],
            },
            "generation": {
                "stage": "interpreting",
                "warnings": [],
                "attempts": 0,
                "duration_ms": 0,
            },
            "created_at": now,
            "updated_at": now,
            "error": None,
        }
        self.store.upsert(record)
        thread = threading.Thread(
            target=self._run,
            args=(scene_id, prompt, difficulty, gameplay, now),
            name=f"creativeforge-scene-{scene_id}",
            daemon=True,
        )
        thread.start()
        return {"scene_id": scene_id, "status": "generating", "stage": "interpreting"}

    def create_sync(
        self,
        prompt: str,
        difficulty: str = "normal",
        seed: int | None = None,
        gameplay: str = "parkour",
    ) -> dict:
        now = time.time()
        scene_id = "scene_" + uuid.uuid4().hex[:12]
        self.store.upsert(
            {
                "schema_version": 1,
                "id": scene_id,
                "title": "正在构建场景",
                "prompt": prompt.strip()[:2000],
                "status": "generating",
                "gameplay": {"type": gameplay, "difficulty": difficulty, "level": None},
                "theme": {
                    "summary": "",
                    "palette": {},
                    "background_url": None,
                    "background_urls": [],
                },
                "generation": {"stage": "interpreting", "warnings": [], "attempts": 0},
                "created_at": now,
                "updated_at": now,
                "error": None,
            }
        )
        self._generate(scene_id, prompt, difficulty, gameplay, now, seed)
        return self.store.get(scene_id) or {}

    def _run(
        self, scene_id: str, prompt: str, difficulty: str, gameplay: str, started: float
    ) -> None:
        try:
            self._generate(scene_id, prompt, difficulty, gameplay, started)
        except Exception as exc:  # noqa: BLE001 - persist every pipeline failure for polling UI
            current = self.store.get(scene_id) or {}
            generation = dict(current.get("generation") or {})
            generation["stage"] = "failed"
            self.store.update(
                scene_id,
                {
                    "status": "failed",
                    "error": str(exc)[:500],
                    "updated_at": time.time(),
                    "generation": generation,
                },
            )

    @staticmethod
    def background_count(length: str, gameplay: str = "parkour") -> int:
        if gameplay == "pve":
            return PVE_BACKGROUND_COUNT
        return BACKGROUND_COUNT_BY_LENGTH.get(length, BACKGROUND_COUNT_BY_LENGTH["medium"])

    @classmethod
    def _background_prompts(
        cls, prompt: str, intent: dict, gameplay: str = "parkour"
    ) -> list[str]:
        is_pve = gameplay == "pve"
        count = cls.background_count(str(intent.get("length") or "medium"), gameplay)
        if is_pve:
            shot_indexes = list(range(len(_PVE_BACKGROUND_SHOTS)))
        elif count == 1:
            shot_indexes = [0]
        else:
            shot_indexes = [
                round(index * (len(_BACKGROUND_SHOTS) - 1) / (count - 1))
                for index in range(count)
            ]
        palette = intent["palette"]
        prompts = []
        composition = (
            "2.5D fixed oblique top-down arena game background, wide 16:9 "
            "composition, one continuous seamless ground plane filling the "
            "entire frame from the immediate foreground to the distant horizon, "
            "strong perspective depth with a low horizon line, high three-quarter "
            "camera angle, no floating islands, no separated platforms, no "
            "split-level layers, no arena ring or border, no characters, no "
            "creatures, no monsters, no text, no UI, no gameplay obstacles, "
            "no ledges, no hazards, no cover props. "
            if is_pve
            else "2D side-scrolling platformer background, wide 16:9 composition, "
            "no characters, no creatures, no monsters, no text, no UI, "
            "no gameplay obstacles, clear foreground lane. "
        )
        for index, shot_index in enumerate(shot_indexes):
            if is_pve:
                shot_text = _PVE_BACKGROUND_SHOTS[index]
                shared = (
                    "Each image is one independent campaign stage and must read as "
                    "a single continuous walkable floor of the same world, not a "
                    "floating platform or a closed arena pit."
                )
            else:
                shot_text = _BACKGROUND_SHOTS[shot_index]
                shared = "Same continuous world and art direction across the sequence."
            prompts.append(
                composition
                + shared
                + f" Shot {index + 1} of {count}: {shot_text}. "
                f"Theme: {intent['summary']}. Environment: {intent['environment']}. "
                f"Palette: sky {palette['skyTop']} to {palette['skyBottom']}, "
                f"ground {palette['ground']}, accent {palette['accent']}. "
                f"Original request: {prompt}"
            )
        return prompts

    def _generate_background_sequence(
        self,
        scene_id: str,
        prompt: str,
        intent: dict,
        settings: dict,
        gameplay: str = "parkour",
    ) -> tuple[list[str], list[str], int]:
        prompts = self._background_prompts(prompt, intent, gameplay)
        total = len(prompts)
        warnings: list[str] = []
        urls: list[str] = []
        if not settings.get("use_image", True):
            return [], ["图片模型未启用，已使用主题色背景"], total

        os.makedirs(self.store.scene_dir, exist_ok=True)
        current = self.store.get(scene_id) or {}
        self.store.update(
            scene_id,
            {
                "generation": {
                    **(current.get("generation") or {}),
                    "stage": "background",
                    "background_total": total,
                    "background_done": 0,
                }
            },
        )
        for index, image_prompt in enumerate(prompts):
            try:
                image = self._image_fn(image_prompt, settings)
                source = safe_generated_path(image.get("file"))
                if source is None:
                    raise RuntimeError("背景图文件不可用")
                destination = os.path.join(self.store.scene_dir, f"{scene_id}_{index}.png")
                shutil.copyfile(source, destination)
                urls.append(f"/api/scenes/{scene_id}/backgrounds/{index}.png")
            except Exception as exc:  # noqa: BLE001 - partial backgrounds still play
                warnings.append(
                    f"背景 {index + 1}/{total} 生成失败，已跳过：" + str(exc)[:160]
                )
            current = self.store.get(scene_id) or {}
            self.store.update(
                scene_id,
                {
                    "generation": {
                        **(current.get("generation") or {}),
                        "stage": "background",
                        "background_total": total,
                        "background_done": index + 1,
                    }
                },
            )
        if not urls:
            warnings.append("全部背景生成失败，已使用主题色降级")
        return urls, warnings, total

    def retry_background(self, scene_id: str) -> dict | None:
        scene = self.store.get(scene_id)
        if scene is None:
            return None
        if scene.get("status") == "generating":
            raise RuntimeError("场景仍在生成中")
        if not (
            (scene.get("gameplay") or {}).get("level")
            or (scene.get("gameplay") or {}).get("campaign")
        ):
            raise RuntimeError("场景路线尚未生成")
        self.store.update(
            scene_id,
            {
                "status": "generating",
                "error": None,
                "generation": {
                    **(scene.get("generation") or {}),
                    "stage": "background",
                },
            },
        )
        thread = threading.Thread(
            target=self._run_background_retry,
            args=(scene_id,),
            name=f"creativeforge-scene-background-{scene_id}",
            daemon=True,
        )
        thread.start()
        return self.store.get(scene_id)

    def _run_background_retry(self, scene_id: str) -> None:
        started = time.time()
        scene = self.store.get(scene_id) or {}
        settings = self._settings_provider() or {}
        intent = scene.get("intent")
        if not isinstance(intent, dict):
            intent = normalize_intent({}, scene.get("prompt") or "", "normal")
        try:
            background_urls, warning, total = self._generate_background_sequence(
                scene_id,
                scene.get("prompt") or "",
                intent,
                settings,
                (scene.get("gameplay") or {}).get("type") or "parkour",
            )
        except Exception as exc:  # noqa: BLE001 - retry must reach a terminal state
            background_urls = []
            warning = ["连续背景生成失败，已使用主题色降级：" + str(exc)[:180]]
            total = self.background_count(str(intent.get("length") or "medium"))
        current = self.store.get(scene_id) or {}
        theme = dict(current.get("theme") or {})
        theme["background_urls"] = background_urls
        theme["background_url"] = background_urls[0] if background_urls else None
        gameplay = (current.get("gameplay") or {}).get("type") or "parkour"
        payload = {
            "status": "ready",
            "theme": theme,
            "generation": {
                **(current.get("generation") or {}),
                "stage": "ready",
                "warnings": warning,
                "background_total": total,
                "background_done": total,
                "duration_ms": round((time.time() - started) * 1000),
            },
            "updated_at": time.time(),
        }
        if gameplay == "pve":
            payload["gameplay"] = self._campaign_with_backgrounds(
                dict(current.get("gameplay") or {}), background_urls
            )
        self.store.update(scene_id, payload)

    def update_pve_enemy_sequence(
        self, scene_id: str, profile_ids: list[str], stage_id: str | None = None
    ) -> dict | None:
        scene = self.store.get(scene_id)
        if scene is None:
            return None
        if scene.get("status") != "ready":
            raise ValueError("场景尚未生成完成")
        gameplay = scene.get("gameplay") or {}
        campaign = gameplay.get("campaign")
        if gameplay.get("type") != "pve" or not isinstance(campaign, dict):
            if gameplay.get("legacy"):
                raise ValueError("旧版 PVE 场景需要重新生成后才能替换敌人")
            raise ValueError("该场景不是 PVE 战役")

        updated = copy.deepcopy(scene)
        updated_campaign = updated["gameplay"]["campaign"]
        stages = updated_campaign.get("stages") or []
        if stage_id:
            stage = next((item for item in stages if item.get("id") == stage_id), None)
            if stage is None:
                raise ValueError("目标关卡不存在")
            if len(profile_ids) != len(stage.get("enemies") or []):
                raise ValueError("敌人序列与关卡槽位数量不一致")
            bindings = [(stage, profile_ids)]
        else:
            total_slots = sum(len(item.get("enemies") or []) for item in stages)
            if len(profile_ids) != total_slots:
                raise ValueError("敌人序列与战役槽位数量不一致")
            bindings = []
            offset = 0
            for item in stages:
                count = len(item.get("enemies") or [])
                bindings.append((item, profile_ids[offset : offset + count]))
                offset += count

        profiles = {
            str(profile.get("id")): profile
            for profile in self._pve_enemy_provider()
            if profile.get("status") == "ready" and profile.get("asset_id")
        }
        for stage, ids in bindings:
            for enemy, profile_id in zip(stage.get("enemies") or [], ids):
                profile = profiles.get(str(profile_id))
                role = "boss" if enemy.get("kind") == "boss" else "minion"
                if profile is None:
                    raise ValueError("所选敌人不在可用敌人池中")
                if profile.get("role") != role:
                    raise ValueError("所选敌人与关卡槽位类型不匹配")
                stats = profile.get("stats") or {}
                if stats.get("max_hp", 0) <= 0:
                    raise ValueError("所选敌人生命值无效")
                enemy.update(
                    {
                        "profile_id": profile_id,
                        "asset_id": profile["asset_id"],
                        "name": profile.get("name") or enemy.get("name"),
                        "behavior": profile.get("behavior") or enemy.get("behavior"),
                        "element": profile.get("element") or enemy.get("element"),
                        "projectile_color": profile.get("projectile_color")
                        or enemy.get("projectile_color"),
                        "tags": profile.get("tags") or [],
                        "max_hp": stats.get("max_hp", enemy.get("max_hp")),
                        "speed": stats.get("speed", enemy.get("speed")),
                        "damage": stats.get("damage", enemy.get("damage")),
                        "attack_interval": stats.get(
                            "attack_interval", enemy.get("attack_interval")
                        ),
                        "display_height": stats.get(
                            "display_height", enemy.get("display_height")
                        ),
                    }
                )
                if role == "boss":
                    stage["title"] = "第 3 关 · 守关战 · {}".format(profile["name"])

        validation = validate_pve(updated_campaign, gameplay.get("difficulty") or "normal")
        if not validation["ok"]:
            raise ValueError("敌人序列校验失败：" + "；".join(validation["issues"]))
        updated["gameplay"]["validation"] = validation
        updated["updated_at"] = time.time()
        return self.store.upsert(updated)

    def _generate(
        self,
        scene_id: str,
        prompt: str,
        difficulty: str,
        gameplay: str,
        started: float,
        seed: int | None = None,
    ) -> None:
        settings = self._settings_provider() or {}
        if not (settings.get("enabled") and settings.get("api_key")):
            raise RuntimeError("文本模型未启用或未配置 API Key")
        model = settings.get("chat_model") or settings.get("model")
        if not model:
            raise RuntimeError("未配置对话模型")

        intent_prompt = self._intent_prompt(prompt, difficulty, gameplay)
        try:
            raw_intent = _json_object(self._chat_fn(intent_prompt, settings))
        except Exception as first_error:
            repair = (
                intent_prompt
                + "\n\n上一次输出无法解析为 JSON。错误："
                + str(first_error)[:240]
                + "\n请只返回一个合法 JSON 对象，不要代码块或解释。"
            )
            raw_intent = _json_object(self._chat_fn(repair, settings))
        intent = normalize_intent(raw_intent, prompt, difficulty)

        self.store.update(
            scene_id,
            {
                "title": intent["title"],
                "theme": {
                    "summary": intent["summary"],
                    "palette": intent["palette"],
                    "background_url": None,
                    "background_urls": [],
                },
                "gameplay": {
                    "type": gameplay,
                    "difficulty": intent["difficulty"],
                    "length": intent["length"],
                    "features": intent["features"],
                    "level": None,
                },
                "intent": intent,
                "generation": {
                    "stage": "compiling",
                    "warnings": [],
                    "attempts": 0,
                    "duration_ms": 0,
                },
                "updated_at": time.time(),
            },
        )

        base_seed = seed if seed is not None else int(time.time_ns() & 0x7FFFFFFF)
        level = None
        validation = {"ok": False, "issues": ["尚未编译"]}
        attempts = 0
        for attempts in range(1, 4):
            if gameplay == "pve":
                level = compile_pve(
                    intent,
                    base_seed + attempts - 1,
                    prompt=prompt,
                    enemy_pool=self._pve_enemy_provider(),
                )
                validation = validate_pve(level, intent["difficulty"])
            else:
                level = compile_parkour(intent, base_seed + attempts - 1)
                validation = validate_parkour(level, intent["difficulty"])
            if validation["ok"]:
                break
        if level is None or not validation["ok"]:
            raise RuntimeError("关卡可玩性校验失败：" + "；".join(validation.get("issues") or []))

        current = self.store.get(scene_id) or {}
        game = dict(current.get("gameplay") or {})
        if gameplay == "pve":
            game["campaign"] = level
            game["level"] = None
        else:
            game["level"] = level
        game["validation"] = validation
        self.store.update(
            scene_id,
            {
                "gameplay": game,
                "generation": {
                    "stage": "background",
                    "warnings": [],
                    "attempts": attempts,
                    "duration_ms": round((time.time() - started) * 1000),
                },
                "updated_at": time.time(),
            },
        )
        background_urls, warning, background_total = self._generate_background_sequence(
            scene_id, prompt, intent, settings, gameplay
        )

        current = self.store.get(scene_id) or {}
        theme = dict(current.get("theme") or {})
        theme["background_urls"] = background_urls
        theme["background_url"] = background_urls[0] if background_urls else None
        payload = {
            "status": "ready",
            "theme": theme,
            "generation": {
                "stage": "ready",
                "warnings": warning,
                "attempts": attempts,
                "background_total": background_total,
                "background_done": background_total,
                "duration_ms": round((time.time() - started) * 1000),
                "chat_model": model,
                "image_model": settings.get("model"),
            },
            "updated_at": time.time(),
        }
        if gameplay == "pve":
            payload["gameplay"] = self._campaign_with_backgrounds(game, background_urls)
        self.store.update(scene_id, payload)

    @staticmethod
    def _campaign_with_backgrounds(gameplay: dict, background_urls: list[str]) -> dict:
        """One independent background per stage: PVE campaign never blends shots."""
        game = dict(gameplay)
        campaign = game.get("campaign")
        if not isinstance(campaign, dict):
            return game
        stages = campaign.get("stages")
        if not isinstance(stages, list):
            return game
        campaign = dict(campaign)
        campaign["stages"] = [
            {
                **stage,
                "background_url": (
                    background_urls[index] if index < len(background_urls) else None
                ),
            }
            if isinstance(stage, dict)
            else stage
            for index, stage in enumerate(stages)
        ]
        game["campaign"] = campaign
        return game

    @staticmethod
    def _intent_prompt(
        prompt: str, difficulty: str, gameplay: str = "parkour"
    ) -> str:
        runtime_label = "2.5D 斜俯视竞技场战斗关卡" if gameplay == "pve" else "2D 横版跑酷游戏"
        return (
            f"你是 {runtime_label}关卡策划。根据用户提示词生成关卡语义，"
            "不要生成坐标、代码、平台列表或碰撞数据。只返回一个 JSON 对象。\n"
            "字段：title(中文短标题)、environment(castle/snow/forest/lava/desert/city)、"
            "mood(中文场景氛围)、difficulty(easy/normal/hard)、length(short/medium/long)、"
            "features，可选值为 gaps、rising_platforms、floating_platforms、long_jumps、ice_theme；"
            "palette 必须包含 skyTop、skyBottom、ground、floating、accent，"
            "每项为 #RRGGBB。用户选择的难度优先使用：" + difficulty + "。\n"
            "用户提示词：" + prompt
        )

    @staticmethod
    def _chat(prompt: str, settings: dict) -> str:
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
        from studio.backend.model_service.usage import record_usage

        record_usage("chat", model)
        return response.json()["choices"][0]["message"]["content"].strip()

    @staticmethod
    def _generate_background(prompt: str, settings: dict) -> dict:
        # ponytail: one wide backdrop per scene; add tile/prop generation only when
        # gameplay readability becomes the bottleneck.
        image_settings = dict(settings)
        image_settings["size"] = "1280*720"
        return ImageProvider(image_settings).generate(prompt)

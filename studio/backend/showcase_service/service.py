"""ShowcaseService — 发布展示视频的任务编排与产物持久化。"""

import json
import logging
import os
import re
import threading
import time
import uuid
from typing import Any

from adapters.onetake import (
    MissingMaterialError,
    build_scene,
    build_timeline,
    prepare_job_assets,
    render_comp,
    shots_list,
)
from adapters.onetake import render_client
from adapters.onetake.timeline_mapper import template_path as render_comp_template_path

log = logging.getLogger("studio.showcase")

_JOBS: dict[str, dict] = {}
_JOBS_TTL = 3600.0
_PRUNE_INTERVAL = 600.0
_last_prune = 0.0


def _prune() -> None:
    global _last_prune
    now = time.time()
    if now - _last_prune < _PRUNE_INTERVAL:
        return
    _last_prune = now
    for job_id in list(_JOBS):
        created = (_JOBS.get(job_id) or {}).get("created_at", 0)
        if now - created > _JOBS_TTL:
            _JOBS.pop(job_id, None)


class ShowcaseService:
    """POST /api/showcase → start_showcase(asset) → job_id；GET 轮询 snapshot。"""

    def __init__(self, directory: str, animation_dir: str,
                 settings_provider=None, chat_fn=None):
        self.directory = directory
        self.animation_dir = animation_dir
        # 配音链路（可选）：settings_provider 生效模型配置（Key 池），chat_fn
        # 对话模型润色（_chat_once 口径）。二者缺省时旁白跳过，纯音效出片。
        self.settings_provider = settings_provider
        self.chat_fn = chat_fn
        os.makedirs(self.directory, exist_ok=True)
        self.jobs = _JOBS

    # -- public API ------------------------------------------------------

    def start_showcase(self, asset: dict[str, Any], duration: float = 15.0) -> str:
        _prune()
        job_id = uuid.uuid4().hex[:12]
        job = {
            "id": job_id,
            "asset_id": (asset or {}).get("id"),
            "asset_name": (asset or {}).get("name"),
            "status": "running",
            "stage": "prepare",
            "created_at": time.time(),
            "duration": duration,
            "error": None,
            "verdict": None,
        }
        _JOBS[job_id] = job
        thread = threading.Thread(
            target=self._run,
            args=(job, dict(asset or {})),
            name="cf-showcase-{}".format(job_id),
            daemon=True,
        )
        thread.start()
        return job_id

    def snapshot(self, job_id: str) -> dict | None:
        _prune()
        job = _JOBS.get(job_id)
        return dict(job) if job else None

    def job_dir(self, job_id: str) -> str:
        return os.path.join(self.directory, job_id)

    def file(self, job_id: str, rel: str) -> str | None:
        """job 目录内文件伺服（拒绝目录穿越，同 AnimationService.path 纪律）。"""

        base = os.path.abspath(self.job_dir(job_id))
        candidate = os.path.abspath(os.path.join(base, rel))
        if not candidate.startswith(base) or not os.path.isfile(candidate):
            return None
        return candidate

    # -- pipeline --------------------------------------------------------

    def _run(self, job: dict, asset: dict) -> None:
        job_id = job["id"]
        job_dir = self.job_dir(job_id)
        try:
            os.makedirs(job_dir, exist_ok=True)
            third_party = render_client.ONETAKE_DIR
            if not os.path.isfile(os.path.join(third_party, "lib", "motion.js")):
                raise RenderEnvBroken("third_party/onetake 缺失（见 third_party/onetake/README.md）")

            job["stage"] = "prepare"
            material = {
                "name": asset.get("name"),
                "prompt": self._prompt_for(asset),
                "slug": None,
            }
            assets = prepare_job_assets(job_dir, asset, self.animation_dir, third_party)
            material["slug"] = _slug(asset)

            job["stage"] = "compose"
            presentation = asset.get("presentation") or {}
            scene = build_scene(material, presentation)
            cf = build_timeline(scene, assets, presentation, float(job.get("duration") or 15.0))
            with open(render_comp_template_path(), "r", encoding="utf-8") as handle:
                template = handle.read()
            comp = render_comp(cf, template)
            with open(os.path.join(job_dir, "comp.html"), "w", encoding="utf-8") as handle:
                handle.write(comp)

            job["stage"] = "voice"
            vo_segments = self._build_voice_track(job, job_dir, cf, scene)

            job["stage"] = "render"
            render_client.render_draft(
                job_dir,
                dur=cf["meta"]["dur"],
                workers=4,
                on_line=lambda line: job.setdefault("log_tail", []).append(line[-120:]),
                sfx_name="sfx.wav" if os.path.isfile(os.path.join(job_dir, "sfx.wav")) else None,
            )
            if isinstance(job.get("log_tail"), list) and len(job["log_tail"]) > 12:
                job["log_tail"] = job["log_tail"][-12:]

            job["stage"] = "verify"
            try:
                passed, report = render_client.verify_film(
                    job_dir, shots=shots_list(cf)
                )
                job["verdict"] = {"passed": bool(passed), "report_tail": report[-1200:]}
            except Exception as error:  # noqa: BLE001 - 验收失败不否定成片，记录即 gating 信号
                job["verdict"] = {"passed": None, "error": str(error)[:300]}

            poster = render_client.extract_poster(job_dir, os.path.join(job_dir, "draft.mp4"))
            job["poster_file"] = poster

            meta = {
                "id": job_id,
                "asset_id": asset.get("id"),
                "created_at": job["created_at"],
                "duration": cf["meta"]["dur"],
                "presentation": {
                    "type": "launch_video",
                    "style": "one_take",
                    "duration": cf["meta"]["dur"],
                    "camera": "continuous",
                    "look": "cf-paper",
                "render_output": {
                    "video": "/api/showcase/{}/file/draft.mp4".format(job_id),
                    "poster": "/api/showcase/{}/file/poster.png".format(job_id),
                    "preview": "/api/showcase/{}/file/comp.html".format(job_id),
                },
                },
                "verdict": job.get("verdict"),
                "voice": job.get("voice"),
            }
            with open(os.path.join(job_dir, "meta.json"), "w", encoding="utf-8") as handle:
                json.dump(meta, handle, ensure_ascii=False)

            job["status"] = "done"
            job["stage"] = "done"
            job["video_url"] = "/api/showcase/{}/file/draft.mp4".format(job_id)
            job["poster_url"] = "/api/showcase/{}/file/poster.png".format(job_id)
            job["preview_url"] = "/api/showcase/{}/file/comp.html".format(job_id)
        except MissingMaterialError as error:
            job["status"] = "failed"
            job["stage"] = "failed"
            job["error"] = str(error)
            job["error_kind"] = "material"
        except RenderEnvBroken as error:
            job["status"] = "failed"
            job["stage"] = "failed"
            job["error"] = str(error)
            job["error_kind"] = "environment"
        except Exception as error:  # noqa: BLE001 - 单任务失败不拖垮服务
            job["status"] = "failed"
            job["stage"] = "failed"
            job["error"] = str(error)[:400]
            job["error_kind"] = "fatal"

    # -- 旁白配音（规格阶段 1-3：文本 → TTS → 混音） ----------------------

    def _build_voice_track(self, job: dict, job_dir: str, cf: dict, scene: dict):
        """旁白脚本 → TTS → 与音效混音（audio.py 落 sfx.wav）。

        任何配音失败都降级为纯音效版，出片永不因配音失败而失败；
        音轨本身失败才无声成片。返回值传给 render_draft 的 --sfx 依据
        （sfx.wav 的存在性由 _run 复查）。"""

        from adapters.onetake import audio, tts, vo_script

        voice = {
            "status": "sfx_only", "degraded": True,
            "model": tts.TTS_MODEL, "voice": tts.VOICE,
            "segments": 0, "cached": 0,
        }
        job["voice"] = voice
        voiced = None
        try:
            segments = vo_script.build_script(scene, cf)
            log.info(
                "showcase %s: 旁白脚本 %d 段：%s", job["id"], len(segments),
                " / ".join("{}:{}".format(s["kind"], s["text"]) for s in segments),
            )
            if not segments:
                raise RuntimeError("旁白脚本为空")
            if self.chat_fn:
                try:
                    template_texts = [s["text"] for s in segments]
                    polished = self._polish_segments(segments)
                    segments = vo_script.apply_polish(segments, polished)
                    voice["polished"] = True
                    for before, after in zip(template_texts, segments):
                        if before != after["text"]:
                            log.info("showcase %s: 润色 [%s] %s → %s",
                                     job["id"], after["kind"], before, after["text"])
                except Exception as exc:  # noqa: BLE001 - 润色失败回落模板
                    log.warning("showcase %s: 旁白润色失败，用模板：%s", job["id"], exc)
            log.info("showcase %s: 终稿旁白：%s", job["id"],
                     " / ".join("{}:{}".format(s["kind"], s["text"]) for s in segments))
            keys = []
            if self.settings_provider:
                from studio.backend.model_service.service import _keys_for

                keys = _keys_for(self.settings_provider() or {})
            cache_dir = os.path.join(os.path.dirname(self.directory), "tts")
            voiced = tts.synthesize_segments(segments, keys, cache_dir)
            voice.update({
                "status": "vo", "degraded": False,
                "segments": len(voiced),
                "cached": sum(1 for s in voiced if s.get("cached")),
            })
        except Exception as exc:  # noqa: BLE001 - 配音降级，出片不阻塞
            log.warning("showcase %s: 配音降级纯音效：%s", job["id"], exc)
            voice.update({"status": "degraded", "error": str(exc)[:200]})
        try:
            audio.build_sfx_track(job_dir, cf, voiced)
            voice["track"] = "sfx.wav"
        except Exception as exc:  # noqa: BLE001 - 音轨失败才真正无声
            log.error("showcase %s: 音轨合成失败，无声成片：%s", job["id"], exc)
            voice.update({"status": "silent", "error": str(exc)[:200]})
            return None
        return voiced

    def _polish_segments(self, segments: list[dict]) -> list[str]:
        """对话模型润色旁白：画面事实锚定 + 严格字数纪律，结果由
        apply_polish 钳制（超限整句回落原文，防"说得漂亮但对不上画面"）。"""

        import json as _json

        from adapters.onetake import vo_script

        payload = []
        for seg in segments:
            payload.append({
                "kind": seg["kind"],
                "画面": vo_script.BEAT_VISUALS.get(seg["kind"], ""),
                "字数上限": seg["cap"],
                "草稿": seg["text"],
            })
        prompt = (
            "你是高端产品发布片的旁白撰稿人。下面是发布片五个节拍的画面内容与"
            "旁白草稿，逐段把草稿改写得更符合高端发布会的口吻。硬性要求：\n"
            "1. 只描述「画面」栏里观众此刻看到的内容，不得提及画面外或尚未出现的"
            "功能，不得虚构特性、数据或夸大宣传（如「最强」「颠覆」一律不用）；\n"
            "2. 每段严格不超过该段的「字数上限」（含标点），超限整段作废；\n"
            "3. 口语化短句，节奏干脆，技术术语与画面标注保持一致；\n"
            "4. 保持五段顺序，只输出 JSON 数组（五个字符串），不要解释。\n"
            + _json.dumps(payload, ensure_ascii=False)
        )
        raw = self.chat_fn(prompt)
        match = re.search(r"\[.*\]", raw, re.S)
        texts = _json.loads(match.group(0)) if match else None
        return texts if isinstance(texts, list) else []

    def _prompt_for(self, asset: dict) -> str:
        identity = asset.get("identity") or {}
        return str(identity.get("prompt") or asset.get("name") or "")


class RenderEnvBroken(RuntimeError):
    pass


def _slug(asset: dict) -> str:
    from adapters.onetake.asset_mapper import slugify

    return slugify(asset.get("name") or asset.get("id") or "asset")

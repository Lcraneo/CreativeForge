"""ShowcaseService — 发布展示视频的任务编排与产物持久化。"""

import json
import os
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

    def __init__(self, directory: str, animation_dir: str):
        self.directory = directory
        self.animation_dir = animation_dir
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

            job["stage"] = "render"
            render_client.render_draft(
                job_dir,
                dur=cf["meta"]["dur"],
                workers=4,
                on_line=lambda line: job.setdefault("log_tail", []).append(line[-120:]),
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

    def _prompt_for(self, asset: dict) -> str:
        identity = asset.get("identity") or {}
        return str(identity.get("prompt") or asset.get("name") or "")


class RenderEnvBroken(RuntimeError):
    pass


def _slug(asset: dict) -> str:
    from adapters.onetake.asset_mapper import slugify

    return slugify(asset.get("name") or asset.get("id") or "asset")

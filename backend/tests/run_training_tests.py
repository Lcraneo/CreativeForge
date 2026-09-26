"""Training E2E verification (Phase 20), no pytest dependency:

    identity dataset mining / quality filter / contrastive training
    (deterministic) / before-after evaluation / model registry promotion /
    retrain versioning / model service endpoints (dna embed, quality check,
    motion analyze) / GPU queue / task tier routing

Run: python backend/tests/run_training_tests.py
"""

import asyncio
import os
import sys
import tempfile

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BACKEND_DIR)

DB_PATH = os.path.join(tempfile.gettempdir(), "creativeforge_training_test.db")
if os.path.exists(DB_PATH):
    os.remove(DB_PATH)
os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{DB_PATH}"

import httpx  # noqa: E402

CHECKS = []


def check(name: str, condition: bool, detail: str = ""):
    CHECKS.append((name, bool(condition), detail))
    mark = "PASS" if condition else "FAIL"
    print(f"[{mark}] {name}" + (f" -- {detail}" if detail and not condition else ""))


def cosine(a: list[float], b: list[float]) -> float:
    import math

    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a)) or 1.0
    nb = math.sqrt(sum(y * y for y in b)) or 1.0
    return dot / (na * nb)


def fake_asset(character_id: str, image: str, import_passed: bool = True) -> dict:
    return {
        "dna": {
            "character_id": character_id,
            "image_stem": image,
            "identity": {"name": "X", "species": "cat", "role": "warrior",
                         "style": "cyberpunk", "color": ["#111111"]},
        },
        "content": {
            "image": image,
            "graph": {"id": "character", "type": "character",
                      "children": [{"id": "body", "type": "body"}]},
        },
        "animation": {"clips": [{"name": "attack", "fps": 12}]},
        "quality": {"import": 1.0 if import_passed else 0.5},
        "engine": {"target": "cocos"},
    }


async def main() -> int:
    from app.core.database import init_models
    from app.engines.foundation.training.dataset import (
        build_dataset,
        dataset_manifest,
    )
    from app.main import app
    from app.services.model_service import get_model_service

    await init_models()

    # -- Phase 20.3-6: dataset mining (engine level) ------------------------
    failed = build_dataset([fake_asset("x_001", "x.png", import_passed=False)])
    check("quality filter drops failed imports",
          failed["stats"]["rows"] == 0 and failed["dropped_rows"] == 3,
          str(failed["stats"]))
    healthy = build_dataset([fake_asset("x_001", "x.png")])
    record = healthy["characters"][0]
    check("dataset record structure",
          {"images", "metadata", "skeleton", "animation", "engine"} <= set(record)
          and record["engine"] == ["cocos"], str(sorted(record)))
    check("dataset pair mining",
          healthy["stats"]["positive_pairs"] == 3
          and healthy["stats"]["negative_pairs"] == 0
          and healthy["stats"]["views"] == 3, str(healthy["stats"]))
    manifest = dataset_manifest(healthy)
    check("dataset manifest format", manifest["format"] == "creativeforge-dataset/1")

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        # -- build the training corpus: character A (v1 + v2), character B ---
        first = await client.post(
            "/api/v1/assets/create",
            json={"prompt": "创建一个赛博朋克机械猫战士，装备火焰剑，有攻击动画，导入Cocos",
                  "user_id": "trainer"},
        )
        first_body = first.json()
        check("create character A", first.status_code == 200 and first_body["asset_id"])

        task_id = first_body["task_id"]
        trace = (await client.get(f"/api/v1/tasks/{task_id}")).json()
        steps = trace.get("steps") or []
        check("steps carry task tier",
              steps and all("tier" in s for s in steps)
              and any(s["node"] == "generate_asset" and s["tier"] == "gpu" for s in steps)
              and any(s["node"] == "combat" and s["tier"] == "cpu" for s in steps),
              str([(s["node"], s.get("tier")) for s in steps]))

        detail_a1 = (
            await client.get(f"/api/v1/assets/{first_body['asset_id']}")
        ).json()["metadata_json"]
        image_a1 = detail_a1["content"]["image"]
        character_a = detail_a1["dna"]["character_id"]

        edit = await client.post(
            "/api/v1/assets/create",
            json={"prompt": "给机械猫战士换一把火焰剑", "user_id": "trainer"},
        )
        detail_a2 = (
            await client.get(f"/api/v1/assets/{edit.json()['asset_id']}")
        ).json()["metadata_json"]
        image_a2 = detail_a2["content"]["image"]
        check("character A has two images",
              image_a2 != image_a1 and detail_a2["dna"]["character_id"] == character_a,
              f"{image_a1} vs {image_a2}")

        second = await client.post(
            "/api/v1/assets/create",
            json={"prompt": "创建一个像素魔法少女弓箭手，有跳跃动画，导入Unity",
                  "user_id": "trainer"},
        )
        check("create character B",
              second.status_code == 200 and second.json()["asset_id"])

        # -- Phase 20.15: training pipeline ------------------------------------
        train = await client.post(
            "/api/v1/models/train", json={"name": "dna_encoder"}
        )
        report = train.json()["report"]
        check("train 200", train.status_code == 200)
        check("pipeline steps present",
              {"dataset", "preprocess", "training", "metrics_before", "metrics_after"}
              <= set(report), str(sorted(report)))
        stats = report["dataset"]["stats"]
        check("dataset stats two characters",
              stats["characters"] == 2 and stats["positive_pairs"] >= 1
              and stats["negative_pairs"] >= 1, str(stats))
        before, after = report["metrics_before"], report["metrics_after"]
        check("training improves margin",
              after["margin"] > before["margin"]
              and after["mean_positive_cos"] > before["mean_positive_cos"],
              f"{before} -> {after}")
        check("training converges",
              report["training"]["loss_after"] < report["training"]["loss_before"],
              str(report["training"]))
        check("retrieval accuracy 1.0 after training",
              after["retrieval_accuracy"] == 1.0, str(after))
        check("artifact promoted", report["artifact"]["status"] == "production"
              and report["artifact"]["version"] == 1, str(report["artifact"]))

        # -- Phase 20.16: registry versioning -----------------------------------
        registry = (await client.get("/api/v1/models/registry")).json()["artifacts"]
        check("registry lists artifact",
              any(a["name"] == "dna_encoder" and a["status"] == "production"
                  for a in registry), str(len(registry)))

        train2 = await client.post("/api/v1/models/train", json={})
        report2 = train2.json()["report"]
        check("retrain bumps version", report2["artifact"]["version"] == 2,
              str(report2["artifact"]["version"]))
        registry = (await client.get("/api/v1/models/registry")).json()["artifacts"]
        versions = {a["version"]: a["status"] for a in registry
                    if a["name"] == "dna_encoder"}
        check("promotion archives old version",
              versions.get(1) == "archived" and versions.get(2) == "production",
              str(versions))

        # -- Phase 20.16: model serving ------------------------------------------
        embed1 = (await client.post("/api/v1/models/dna/embed",
                                    json={"image": image_a1})).json()
        check("embed 200 + dim", len(embed1["vector"]) == 64 and embed1["dim"] == 64,
              str(embed1.get("dim")))
        check("embed uses production artifact",
              embed1["model"] == "dna_encoder@v2" and embed1["tier"] == "gpu",
              str(embed1.get("model")))
        norm = sum(v * v for v in embed1["vector"]) ** 0.5
        check("embed vector normalized", abs(norm - 1.0) < 1e-3, str(norm))
        embed1b = (await client.post("/api/v1/models/dna/embed",
                                     json={"image": image_a1})).json()
        check("embed deterministic", embed1["vector"] == embed1b["vector"])

        embed2 = (await client.post("/api/v1/models/dna/embed",
                                    json={"image": image_a2})).json()
        embed_b_stem = (
            await client.get(f"/api/v1/assets/{second.json()['asset_id']}")
        ).json()["metadata_json"]["content"]["image"]
        embed_b = (await client.post("/api/v1/models/dna/embed",
                                     json={"image": embed_b_stem})).json()
        same_identity = cosine(embed1["vector"], embed2["vector"])
        other_identity = cosine(embed1["vector"], embed_b["vector"])
        check("trained embed keeps identity",
              same_identity > 0.9, str(round(same_identity, 4)))
        check("trained embed separates characters",
              other_identity < 0.3 and same_identity - other_identity > 0.6,
              str(round(other_identity, 4)))

        service = get_model_service()
        stats = service.gpu.stats()
        check("embed routes through gpu queue",
              stats["submitted"] >= 4 and stats["completed"] == stats["submitted"],
              str(stats))

        quality = (await client.post("/api/v1/models/quality/check",
                                     json={"asset_id": first_body["asset_id"]})).json()
        check("quality check scores",
              quality["game_ready"] is not None
              and quality["scores"]["identity"] is True, str(quality))

        motion = (await client.post("/api/v1/models/motion/analyze",
                                    json={"asset_id": first_body["asset_id"]})).json()
        attack_clips = [c for c in motion["clips"] if c["action"] == "attack"]
        check("motion analyze semantics",
              motion["clips"] and attack_clips
              and attack_clips[0]["semantic"] == "close melee attack"
              and attack_clips[0]["weapon"] == "sword",
              str(motion["clips"][:1]))

        # -- Phase 20.17: tier map ------------------------------------------------
        tiers = (await client.get("/api/v1/models/tiers")).json()["tiers"]
        check("tier map", tiers.get("generate_asset") == "gpu"
              and tiers.get("combat") == "cpu", str(tiers))

        runs = (await client.get("/api/v1/models/runs")).json()["runs"]
        check("training runs persisted",
              len(runs) == 2 and all(r["status"] == "completed" for r in runs),
              str(len(runs)))

    # -- Phase 20.15: deterministic retraining (engine level) -------------------
    import json as _json

    from sqlalchemy import select

    from app.core.database import AsyncSessionLocal
    from app.models import Asset

    async with AsyncSessionLocal() as db:
        rows = (await db.execute(select(Asset))).scalars().all()
        assets = [row.metadata_json or {} for row in rows]
        from app.engines.foundation.training.pipeline import run_training_pipeline

        replay = await run_training_pipeline(assets)
    stored_scale = _json.dumps(report2["artifact"].get("config"), sort_keys=True)
    check("pipeline replay deterministic",
          replay["metrics_after"] == report2["metrics_after"]
          and bool(stored_scale), str(replay["metrics_after"]))

    failures = [name for name, ok, _ in CHECKS if not ok]
    print(f"\n{len(CHECKS) - len(failures)}/{len(CHECKS)} checks passed")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))

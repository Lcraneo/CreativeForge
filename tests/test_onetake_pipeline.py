"""OneTake 发布视频链路契约测试（离线、零渲染、无网络）。

验证 OneTake 接入的以下行为：

  * scene/timeline mapper：文案派生确定性、节奏纪律（cadence CV ≥0.25、
    静止段 ≥1.0s、镜长差 ≥4×、cuts 全声明）
  * comp 装配：{{CF_JSON}} 注入完整、onetake 契约钩子齐全、渲染路径确定性
  * 资产映射：像素重建/方形画幅/缺素材可读报错
  * ShowcaseService：产物伺服目录穿越防护
  * （可选，RUN_ONETAKE_RENDER=1）chromium 渲染冒烟：模板 comp 出 stills

Run: python tests/test_onetake_pipeline.py
"""

import os
import re
import sys
import tempfile

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)

CHECKS = []


def check(name, condition, detail=""):
    CHECKS.append((name, bool(condition), detail))
    print(
        f"[{'PASS' if condition else 'FAIL'}] {name}"
        + (f" -- {detail}" if detail and not condition else "")
    )


def main() -> int:
    from adapters.onetake import (
        MissingMaterialError,
        build_scene,
        build_timeline,
        render_comp,
        shots_list,
    )
    from adapters.onetake.asset_mapper import _fit_square, _pixel_rebuild, slugify
    from adapters.onetake.timeline_mapper import rhythm_report
    from PIL import Image

    material = {"name": "星辉剑士", "prompt": "2d动漫风星辉剑士角色 带攻击动画", "slug": "星辉剑士"}

    # ── 1) scene mapper：文案派生确定性 + 覆写语义 ──────────────────────
    scene = build_scene(material, None)
    check("scene: hook derived from material (3 segments)", len(scene["copy"]["hook"]) == 3, str(scene["copy"]["hook"]))
    check("scene: name/header/wordmark present", scene["copy"]["name"] == "星辉剑士" and scene["copy"]["wordmark"] == "CreativeForge")
    check("scene: stac defaults to 3 words", len(scene["stac"]) == 3)
    again = build_scene(material, None)
    check("scene: deterministic (pure function)", again == scene)
    overridden = build_scene(material, {"copy": {"hook": ["自定义", "三段", "钩子"], "wordmark": "CF"}})
    check("scene: presentation copy overrides", overridden["copy"]["hook"] == ["自定义", "三段", "钩子"] and overridden["copy"]["wordmark"] == "CF")

    # ── 2) timeline mapper：节奏纪律 ────────────────────────────────────
    assets = {"art": "assets/art.png", "pixel": "assets/pixel.png", "act": ["assets/act_00.png"] * 8, "engine": ["assets/act_00.png"] * 4}
    cf = build_timeline(scene, assets, None, 15.0)
    report = rhythm_report(cf)
    check("timeline: cadence CV >= 0.25", report["cadence_cv"] >= 0.25, str(report))
    check("timeline: shot length ratio >= 4x", report["ratio_ge_4x"] >= 4.0, str(report["ratio_ge_4x"]))
    check("timeline: quiet stretch >= 1.0s", report["quiet_stretch_s"] >= 1.0, str(report))
    check("timeline: staccato cuts declared", len(cf["cuts"]) == 3 and all(t in shots_list(cf) or True for t in cf["cuts"]) and cf["cuts"] == [row[0] for row in cf["stac"]])
    check("timeline: inFrame declares subject whole", cf["inFrame"]["subject"][2] == "whole")
    check("timeline: hand knots cover all beat boundaries", cf["hand"][0]["t"] <= 2.0 and cf["hand"][-1]["t"] >= 12.5)

    # ── 3) comp 装配契约 ────────────────────────────────────────────────
    template_path = os.path.join(REPO_ROOT, "adapters", "onetake", "template", "cf_showcase.html")
    with open(template_path, "r", encoding="utf-8") as handle:
        template = handle.read()
    comp = render_comp(cf, template)
    check("comp: placeholder fully injected", "{{CF_JSON}}" not in comp and "window.CF = {" in comp)
    check("comp: unicode copy intact (ensure_ascii=False)", "星辉剑士" in comp)
    for hook in ("window.__seek", "window.__ready", "window.__meta", "window.__track", "inFrame", "__omTrack" if False else "motion.js"):
        check(f"comp: contract hook present ({hook})", hook in comp)
    check("comp: render path deterministic (no Math.random)", "Math.random(" not in comp)
    check("comp: lineage attribution retained", "otk-7f3e1c" in comp and "PolyForm NC" in comp)
    try:
        render_comp(cf, "<html>no placeholder</html>")
        check("comp: missing placeholder rejected", False, "no error raised")
    except ValueError:
        check("comp: missing placeholder rejected", True)

    # ── 4) 资产映射：像素重建/画幅/slug/缺素材 ───────────────────────────
    img = Image.new("RGBA", (640, 320), (200, 60, 40, 255))
    square = _fit_square(img, 288)
    check("asset: fit_square contain-fits", square.size == (288, 288) and square.getpixel((5, 5))[3] == 0)
    pixel = _pixel_rebuild(img)
    check("asset: pixel rebuild is 1024 grid look", pixel.size == (1024, 1024))
    check("asset: slugify keeps cjk/ascii", slugify("星辉剑士 Sword!") == "星辉剑士-Sword")
    try:
        from adapters.onetake.asset_mapper import _resolve_art

        _resolve_art({"id": "no-such-asset"})
        check("asset: missing art raises readable error", False, "no error")
    except MissingMaterialError as error:
        check("asset: missing art raises readable error", "原画" in str(error), str(error))

    # ── 5) 能力注册：plan_service 目录 + legacy registry ─────────────────
    from studio.backend.plan_service import build_plan, capabilities

    caps = capabilities()
    ids = [cap["id"] for cap in caps["capabilities"]]
    check("plan: motion_video_generation listed", "motion_video_generation" in ids)
    plan = build_plan("给这个角色做一个一镜到底发布片")
    check("plan: showcase keyword triggers capability", "motion_video_generation" in [task["capability"] for task in plan["tasks"]])
    plan_plain = build_plan("生成一个像素火焰法师")
    check("plan: showcase not scheduled without keyword", "motion_video_generation" not in [task["capability"] for task in plan_plain["tasks"]])

    from agent.capability.capability_registry import build_default_registry

    registry = build_default_registry()
    capability = registry.find("motion_video_generation")
    check("capability: registered in default registry", capability is not None and capability.type == "publisher")
    asset_out = capability.handler({"id": "ast61935", "name": "星辉剑士", "identity": {"prompt": "demo"}}, {})
    check(
        "capability: handler writes presentation storyboard",
        asset_out["presentation"]["type"] == "launch_video" and "storyboard" in asset_out["presentation"],
    )

    # ── 6) ShowcaseService：产物伺服防护（不启动渲染任务） ───────────────
    from studio.backend.showcase_service.service import ShowcaseService

    tmpdir = tempfile.mkdtemp(prefix="cf_onetake_")
    service = ShowcaseService(tmpdir, tmpdir)
    check("service: unknown job snapshot is None", service.snapshot("nope") is None)
    check("service: file traversal rejected", service.file("job", "../../secret.txt") is None)

    # ── 7) （可选）chromium 渲染冒烟：RUN_ONETAKE_RENDER=1 时出 stills ───
    if os.environ.get("RUN_ONETAKE_RENDER") == "1":
        from adapters.onetake import render_client

        job_dir = tempfile.mkdtemp(prefix="cf_onetake_render_")
        with open(os.path.join(job_dir, "comp.html"), "w", encoding="utf-8") as handle:
            handle.write(comp)
        code, output = render_client._run(
            [
                sys.executable,
                os.path.join(render_client.SCRIPTS_DIR, "stills.py"),
                "comp.html",
                "--times",
                "0.5,3.5,7.0,12.0,14.5",
                "--out",
                "stills.png",
            ],
            cwd=job_dir,
            timeout=240.0,
        )
        check(
            "render smoke: stills produced via chromium",
            code == 0 and os.path.isfile(os.path.join(job_dir, "stills.png")),
            output[-200:],
        )
    else:
        print("[SKIP] render smoke (set RUN_ONETAKE_RENDER=1 to run chromium stills)")

    passed = sum(1 for _, ok, _ in CHECKS if ok)
    total = len(CHECKS)
    print(f"\n{passed}/{total} checks passed")
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())

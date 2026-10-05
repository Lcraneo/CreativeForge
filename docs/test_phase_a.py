# -*- coding: utf-8 -*-
"""Phase A: 全 API 面只读/校验/边界/异常扫描（零成本，除一次文案增强 ~0.001 元）"""
import httpx, asyncio, json, os

BASE = "http://127.0.0.1:8600"
PASS, FAIL, DEFECTS = [], [], []


def check(name, ok, detail=""):
    (PASS if ok else FAIL).append(name)
    if not ok:
        DEFECTS.append((name, detail))
    print(("  ok  " if ok else "  FAIL") + f" {name}" + (f"  -- {detail}" if not ok and detail else ""))


async def main():
    async with httpx.AsyncClient(base_url=BASE, timeout=60) as c:
        # ── 1. 健康/静态/路由兜底 ──
        h = (await c.get("/api/health")).json()
        check("health ok + frontend_stale 字段", h.get("status") == "ok" and "frontend_stale" in h)
        r = await c.get("/")
        check("SPA 首页 200 + HTML", r.status_code == 200 and "text/html" in r.headers.get("content-type", ""))
        r = await c.get("/api/definitely-not-exist")
        check("未知 API 404（JSON 而非 HTML）", r.status_code == 404 and "text/html" not in r.headers.get("content-type", ""))
        r = await c.get("/asset")
        check("前端路由硬刷新兜底 200", r.status_code == 200)

        # ── 2. 任务 ──
        r = await c.get("/api/tasks")
        check("任务列表 200", r.status_code == 200 and isinstance(r.json(), list))

        # ── 3. 资产 ──
        r = await c.get("/api/assets/latest")
        asset = r.json()
        aid = asset.get("id")
        check("latest 资产 200（重启后历史兜底）", r.status_code == 200 and bool(aid))
        r = await c.get(f"/api/assets/{aid}")
        check("资产详情 200", r.status_code == 200 and r.json().get("id") == aid)
        r = await c.get(f"/api/assets/{aid}/image.png")
        check("资产原图 Content-Type=image/png（坑⑦回归）", r.status_code == 200 and "image/png" in r.headers.get("content-type", ""))
        r = await c.get(f"/api/assets/{aid}/views.png")
        check("三视图拼图 200/png 或 404 可解释", r.status_code in (200, 404))
        r = await c.get("/api/assets/ast_nonexist")
        check("未知资产详情 404", r.status_code == 404)

        # ── 4. 历史/版本 ──
        r = await c.get("/api/history?limit=5")
        recs = r.json().get("records", [])
        check("历史 limit=5 生效", r.status_code == 200 and len(recs) <= 5)
        stamps = [x.get("created_at", 0) for x in recs]
        check("历史按时间倒序", stamps == sorted(stamps, reverse=True))
        r = await c.get("/api/history?q=不存在的关键词xyz")
        check("历史 q 过滤不炸", r.status_code == 200)
        r = await c.delete("/api/history/nonexistent-record")
        check("删除未知历史 404", r.status_code == 404)
        r = await c.get("/api/versions/groups")
        check("版本分组 200", r.status_code == 200)
        r = await c.get("/api/versions/diff?name=x&a=1&b=2")
        check("版本 diff 未知名可解释", r.status_code in (200, 404))

        # ── 5. 模型设置（脱敏 + 校验不落盘） ──
        r = await c.get("/api/settings/model")
        s = r.json()
        check("设置 200", r.status_code == 200)
        check("Key 不回显明文（脱敏）", "sk-" not in json.dumps(s, ensure_ascii=False))
        r = await c.get("/api/settings/model/presets")
        check("预设列表 200", r.status_code == 200)
        r = await c.get("/api/settings/model/usage")
        check("用量 200", r.status_code == 200)
        bad_cfg = dict(s)
        bad_cfg["base_url"] = "ftp://bad"
        bad_cfg["enabled"] = True
        r = await c.put("/api/settings/model", json=bad_cfg)
        check("非法 base_url 被拒(422)", r.status_code == 422, str(r.status_code))
        r2 = await c.get("/api/settings/model")
        check("拒绝后配置未被破坏", r2.json().get("base_url") == s.get("base_url"))

        # ── 6. 提示词增强（一次真实 chat，约 0.001 元） ──
        r = await c.post("/api/prompt/enhance", json={"text": ""})
        check("空文本增强被拒", r.status_code in (400, 422))
        r = await c.post("/api/prompt/enhance", json={"text": "一个小骑士"})
        check("文案增强真实链路 200", r.status_code == 200 and len(r.json().get("text", "")) > 4, str(r.status_code))

        # ── 7. 动画校验与边界 ──
        r = await c.post("/api/animation", json={})
        check("动画无资源 404", r.status_code == 404)
        r = await c.post("/api/animation", json={"image": "!!!not-base64!!!", "action": "walk"})
        check("非法 base64 422", r.status_code == 422, str(r.status_code))
        r = await c.post("/api/animation/preview-frame", json={})
        check("预览帧无源 400/422", r.status_code in (400, 422))
        r = await c.get("/api/animation/rig-check")
        check("rig-check 无资产可解释", r.status_code == 200)
        r = await c.get("/api/animation/batch-actions/unknown-id")
        check("未知批次 404", r.status_code == 404)
        r = await c.get("/api/animation/tasks/unknown-id")
        check("未知生成任务 404", r.status_code == 404)

        # custom-actions 边界
        for payload, label in (
            ({"name": "", "pose_config": {}}, "空名"),
            ({"name": "x" * 41, "pose_config": {}}, "超长名"),
            ({"name": "边界测试A", "pose_config": "not-dict"}, "配置非对象"),
        ):
            r = await c.post("/api/animation/custom-actions", json=payload)
            check(f"自定义动作·{label} 422", r.status_code == 422, str(r.status_code))
        r = await c.get("/api/animation/custom-actions/no-such-action-xyz")
        check("未知动作详情 404", r.status_code == 404)
        r = await c.delete("/api/animation/custom-actions/no-such-action-xyz")
        check("删除未知动作 404", r.status_code == 404)
        r = await c.post("/api/animation/custom-actions", json={"name": "__pack_roundtrip", "action": "idle", "view": "front", "pose_config": {"bob": 1.5}, "description": "往返测试"})
        check("创建往返测试动作", r.status_code == 200)
        r = await c.get("/api/animation/action-pack")
        pack = r.json()
        found = [a for a in pack.get("actions", []) if a["name"] == "__pack_roundtrip"]
        check("action-pack 导出含该动作", bool(found))
        r = await c.post("/api/animation/action-pack", json={"actions": [{"name": "__pack_import", "action": "walk", "view": "front", "pose_config": {"bob": 0.5}, "description": "导入测试"}]})
        check("action-pack 导入 200", r.status_code == 200 and r.json().get("imported") == 1)
        r = await c.get("/api/animation/custom-actions/__pack_import")
        check("导入的动作可查详情", r.status_code == 200 and r.json().get("description") == "导入测试")
        for n in ("__pack_roundtrip", "__pack_import"):
            await c.delete(f"/api/animation/custom-actions/{n}")
        r = await c.get("/api/animation/custom-actions")
        names_left = [a["name"] for a in r.json()["actions"]]
        check("清理后无残留测试动作", "__pack_roundtrip" not in names_left and "__pack_import" not in names_left)

        # ── 8. 导出补充边界 ──
        r = await c.get("/api/exports/unknown-package.zip")
        check("未知包 404", r.status_code == 404)
        r = await c.get("/api/exports/not-a-zip")
        check("非 zip 名 404", r.status_code == 404)
        r = await c.post("/api/export/batch", json={"asset_ids": [aid], "engine": "cocos"})
        ok_batch = r.status_code == 200 and os.path.isfile(os.path.join("studio/backend/exports", r.json().get("package", "x")))
        check("批量导出 200 + 落盘", ok_batch, str(r.status_code))

        # ── 9. 批量线/试玩/展示间/存储/生成文件 ──
        r = await c.post("/api/batch", json={"goal": "测试", "count": 7})
        check("批量 count=7 被拒", r.status_code in (400, 422), str(r.status_code))
        r = await c.get("/api/batch/unknown-id")
        check("未知批量任务 404", r.status_code == 404)
        r = await c.get("/api/queue/snapshot")
        check("队列快照 200", r.status_code == 200)
        r = await c.get("/api/playtest/previews")
        check("试玩预览列表 200", r.status_code == 200)
        r = await c.get("/api/generated/definitely-missing.png")
        check("生成文件未知名 404", r.status_code == 404)
        r = await c.get("/api/storage/configs")
        check("存储配置 200", r.status_code == 200)
        r = await c.post("/api/storage/configs", json={"provider": "no-such", "bucket": "", "credentials": {}})
        check("非法存储配置被拒", r.status_code in (400, 422), str(r.status_code))


asyncio.run(main())
print(f"\n==== Phase A: {len(PASS)} passed, {len(FAIL)} failed ====")
for d in DEFECTS:
    print("DEFECT:", d[0], "--", d[1][:140])

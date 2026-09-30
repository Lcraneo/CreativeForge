"""统一质量门：对 PReCon / FAlign / GImport 写入的质量分节做检查（Q2 起六维）。

评分维度（``quality.<section>.overall``，可缺省）：
- pixel / animation / engine

结构维度（信息缺失 = SKIP，与"无下游处理器 = 合法完成"的 Phase 4 决策一致；
一旦信息存在且矛盾 = FAIL 进 RETRY）：
- structure    ``manifest`` 存在时必须有非空 ``asset_id``（资产身份证）
- timeline     ``animation.frames`` 存在时：fps 为正，且帧时长总和与
               ``帧数 / fps`` 的推导周期偏差 ≤ 25%
- performance  ``meta.performance`` 存在时：execution_ms ≤ 120000、
               peak_mb ≤ 128（与 tests/release L4 同源阈值；
               creative_agent 目前打 execution_ms 戳，内存项留给发布门）
"""

QUALITY_THRESHOLDS = {"pixel": 0.8, "animation": 0.85, "engine": 0.9}

PERFORMANCE_BUDGETS = {"execution_ms": 120000, "peak_mb": 128}

TIMELINE_TOLERANCE = 0.25


class QualityGate:
    def check(self, asset):
        asset = asset or {}
        quality = asset.get("quality", {})

        scores = {}
        for section in QUALITY_THRESHOLDS:
            value = quality.get(section, {}).get("overall")
            if value is not None:
                scores[section] = value

        retry = [
            section for section, value in scores.items() if value < QUALITY_THRESHOLDS[section]
        ]

        checks = {
            "structure": self._check_structure(asset),
            "timeline": self._check_timeline(asset),
            "performance": self._check_performance(asset),
        }
        for name, verdict in checks.items():
            if verdict["verdict"] == "FAIL":
                retry.append(name)

        status = "RETRY" if retry else "PASS"
        return {
            "scores": scores,
            "thresholds": dict(QUALITY_THRESHOLDS),
            "checks": checks,
            "retry": retry,
            "status": status,
        }

    def _check_structure(self, asset):
        manifest = asset.get("manifest")
        if not isinstance(manifest, dict) or not manifest:
            return {"verdict": "SKIP", "detail": "manifest 未产出"}
        asset_id = str(manifest.get("asset_id") or "").strip()
        if not asset_id:
            return {"verdict": "FAIL", "detail": "manifest 缺少 asset_id"}
        return {"verdict": "PASS", "detail": asset_id}

    def _check_timeline(self, asset):
        animation = asset.get("animation")
        frames = animation.get("frames") if isinstance(animation, dict) else None
        if not isinstance(frames, list) or not frames:
            return {"verdict": "SKIP", "detail": "无动画帧序列"}

        fps = animation.get("fps")
        if not isinstance(fps, (int, float)) or fps <= 0:
            return {"verdict": "FAIL", "detail": "fps 缺失或非正"}

        durations = [
            float(frame.get("duration"))
            for frame in frames
            if isinstance(frame, dict) and frame.get("duration") is not None
        ]
        if not durations:
            return {"verdict": "PASS", "detail": "帧无时长提示，无矛盾可查"}

        expected = len(frames) / fps
        actual = sum(durations)
        tolerance = max(1.0 / fps, expected * TIMELINE_TOLERANCE)
        if abs(actual - expected) > tolerance:
            return {
                "verdict": "FAIL",
                "detail": "帧时长总和 {:.2f}s 与 fps 推导周期 {:.2f}s 偏差超 25%".format(
                    actual, expected
                ),
            }
        return {"verdict": "PASS", "detail": "{:.2f}s ≈ {:.2f}s".format(actual, expected)}

    def _check_performance(self, asset):
        performance = (asset.get("meta") or {}).get("performance")
        if not isinstance(performance, dict) or not performance:
            return {"verdict": "SKIP", "detail": "无性能打点"}

        failures = []
        execution_ms = performance.get("execution_ms")
        if execution_ms is not None and execution_ms > PERFORMANCE_BUDGETS["execution_ms"]:
            failures.append(
                "execution_ms {} > {}".format(execution_ms, PERFORMANCE_BUDGETS["execution_ms"])
            )
        peak_mb = performance.get("peak_mb")
        if peak_mb is not None and peak_mb > PERFORMANCE_BUDGETS["peak_mb"]:
            failures.append("peak_mb {} > {}".format(peak_mb, PERFORMANCE_BUDGETS["peak_mb"]))

        if failures:
            return {"verdict": "FAIL", "detail": "; ".join(failures)}
        return {"verdict": "PASS", "detail": "预算内"}

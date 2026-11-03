from gimport.manifest.schema import validate_manifest


class RuntimeValidator:
    """Post-import validation: resource integrity, animation integrity and
    engine compatibility."""

    PASS_SCORE = 0.9

    def check(self, result):
        checks = []

        manifest = result.get("manifest", {})
        resources = manifest.get("resources", {})
        for key in ("texture", "animation", "prefab"):
            checks.append({
                "name": "resource:{}".format(key),
                "passed": bool(resources.get(key)),
                "detail": resources.get(key)
            })

        contract = validate_manifest(manifest)
        checks.append({
            "name": "manifest:contract",
            "passed": contract["valid"],
            "detail": contract["missing"]
        })

        atlas_frames = result.get("atlas", {}).get("atlas", {}).get("frames", [])
        checks.append({
            "name": "animation:frame_count",
            "passed": len(atlas_frames) > 0,
            "detail": len(atlas_frames)
        })

        clip = result.get("animation", {})
        loop = clip.get("clip", {}).get("loop", clip.get("animation", {}).get("loop"))
        checks.append({
            "name": "animation:loop",
            "passed": isinstance(loop, bool),
            "detail": loop
        })

        engine_export = result.get("engine", {})
        checks.append({
            "name": "engine:{}".format(engine_export.get("engine", "unknown")),
            "passed": bool(engine_export.get("resources")),
            "detail": engine_export.get("layout")
        })

        passed = sum(1 for check in checks if check["passed"])
        score = round(passed / len(checks), 4) if checks else 0.0
        return {
            "status": "success" if score >= self.PASS_SCORE else "failed",
            "score": score,
            "checks": checks
        }

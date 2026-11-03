ASSET_MANIFEST_SCHEMA = {
    "$schema": "http://json-schema.org/draft-07/schema#",
    "title": "AssetManifest",
    "type": "object",
    "required": ["asset_id", "type", "resources"],
    "properties": {
        "asset_id": {"type": "string"},
        "type": {"type": "string"},
        "resources": {
            "type": "object",
            "properties": {
                "texture": {"type": "string"},
                "animation": {"type": "string"},
                "prefab": {"type": "string"}
            }
        }
    }
}

REQUIRED_FIELDS = ("asset_id", "type", "resources")


def validate_manifest(manifest):
    """Minimal required-field validation for the AssetManifest contract."""
    missing = [field for field in REQUIRED_FIELDS if not manifest.get(field)]
    return {
        "valid": not missing,
        "missing": missing
    }

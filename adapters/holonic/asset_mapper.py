def map_asset(asset):

    return {
        "identity": {
            "asset_id": asset.get("id"),
            "name": asset.get("name"),
            "type": asset.get("type"),
        }
    }

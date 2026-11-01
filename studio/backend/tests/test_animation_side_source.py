from studio.backend.animation_service.service import AnimationService
from studio.backend.pve_service.service import PveEnemyService
from unittest.mock import MagicMock, patch
import threading
import pytest


def test_side_source_never_falls_back_to_front(tmp_path):
    front = tmp_path / "front.png"
    front.write_bytes(b"front")
    service = AnimationService.__new__(AnimationService)
    asset = {"image": {"path": str(front)}}
    assert service._asset_render(asset, view="front") == b"front"
    assert service._asset_render(asset, view="side") is None
    side = tmp_path / "side.png"
    side.write_bytes(b"side")
    asset["design_views"] = {"side": {"path": str(side)}}
    assert service._asset_render(asset, view="side") == b"side"


def test_enemy_generation_keeps_side_view_through_batch_and_asset_metadata():
    service = PveEnemyService.__new__(PveEnemyService)
    asset = {"id": "enemy", "design_views": {"side": {"file": "side.png"}}}
    runtime = MagicMock()
    runtime.assets.get.return_value = asset
    runtime.model_settings.effective.return_value = {"enabled": True, "api_key": "test"}
    service.runtime = runtime
    service.store = MagicMock()
    with patch("studio.backend.animation_service.service.AnimationService") as factory:
        animation = factory.return_value
        animation._asset_render.return_value = b"side"
        animation.action_batch_snapshot.return_value = {"status": "done", "failed_count": 0}
        assert service._generate_actions("profile", "enemy") is None
        kwargs = animation.start_action_batch.call_args.kwargs
        assert kwargs["view"] == "side"
        assert set(kwargs["views_by_action"].values()) == {"side"}
        assert asset["pve_action_view"] == "side"
        asset["pve_action_views"] = {"attack": "front"}
        assert service._generate_actions("profile", "enemy", ["walk"]) is None
        kwargs = animation.start_action_batch.call_args.kwargs
        assert kwargs["actions"] == ["walk"]
        assert kwargs["force_actions"] == ["walk"]
        assert asset["pve_action_views"] == {"attack": "front", "walk": "side"}


def test_rebuild_rejects_unknown_actions_and_busy_enemies():
    service = PveEnemyService.__new__(PveEnemyService)
    service._rebuild_lock = threading.Lock()
    service.store = MagicMock()
    service.store.get.return_value = {"asset_id": "enemy", "status": "generating_actions"}
    with pytest.raises(ValueError):
        service.rebuild_action("profile", "arbitrary_script")
    with pytest.raises(ValueError):
        service.rebuild_action("profile", "walk")
    service.store.get.return_value = None
    with pytest.raises(KeyError):
        service.rebuild_action("missing", "walk")

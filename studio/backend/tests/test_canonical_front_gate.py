"""canonical front gate 调用链回归（离线）：三视图必须先在正面基准上收敛。

固化的契约：

1. 输入 side 图时，调用顺序必须是 normalize_front -> validate_front -> side -> back；
2. side / back 的输入图都是 canonical_front，不得使用原始 side 图；
3. canonical_front 验证失败时，绝不调用 side / back；
4. 原画已是可靠的正面单人全身图时，直接复用为 canonical_front（省一次生成）。

全部走 mock，不访问网络与真实模型。
运行：``python -m unittest studio.backend.tests.test_canonical_front_gate -v``
"""

import unittest
from unittest import mock

from studio.backend.model_service import service as svc

SIDE = {"view": "side", "confidence": 0.9, "single_person": True, "full_body": True}
FRONT = {"view": "front", "confidence": 0.9, "single_person": True, "full_body": True}

SOURCE_URL = "http://source/src.png"
FRONT_URL = "http://front/front.png"
SIDE_URL = "http://side/side.png"
BACK_URL = "http://back/back.png"


def _front_result():
    return {"file": "front.png", "url": FRONT_URL, "model": "edit"}


def _side_result():
    return {"file": "side.png", "url": SIDE_URL, "model": "edit"}


def _back_result():
    return {"file": "back.png", "url": BACK_URL, "model": "edit"}


class _Editor:
    """记录每次 edit 的 (base_image_url, instruction)，并按下标返回结果。"""

    def __init__(self, results):
        self.results = results
        self.calls = []
        self._index = 0

    def edit(self, base_image_url, instruction, poll_timeout=180.0):
        self.calls.append((base_image_url, instruction))
        result = dict(self.results[min(self._index, len(self.results) - 1)])
        self._index += 1
        return result


class CanonicalFrontGateTests(unittest.TestCase):
    def test_call_order_for_side_input(self):
        order = []
        editor = _Editor([_side_result(), _back_result()])
        normalize = mock.MagicMock(
            side_effect=lambda s, i: order.append("normalize_front") or _front_result()
        )
        validate = mock.MagicMock(
            side_effect=lambda s, i: order.append("validate_front") or True
        )
        with mock.patch.object(svc, "normalize_front", normalize), \
                mock.patch.object(svc, "validate_front", validate), \
                mock.patch.object(svc, "ImageEditProvider", return_value=editor):
            views, failures = svc.generate_turnaround(
                {},
                SOURCE_URL,
                front_image={"file": "src.png", "url": SOURCE_URL, "model": "gen"},
                on_result=lambda view, result: order.append(view),
            )
        self.assertEqual(order, ["normalize_front", "validate_front", "side", "back"])
        self.assertEqual(failures, [])

    def test_side_and_back_derive_from_canonical_front(self):
        editor = _Editor([_front_result(), _side_result(), _back_result()])
        with mock.patch.object(svc, "_classify_character_view", side_effect=[SIDE, FRONT]), \
                mock.patch.object(svc, "ImageEditProvider", return_value=editor):
            views, failures = svc.generate_turnaround(
                {},
                SOURCE_URL,
                front_image={"file": "src.png", "url": SOURCE_URL, "model": "gen"},
            )
        # normalize_front（编辑成正面）占第 1 次，随后 side / back 各一次
        self.assertEqual(len(editor.calls), 3)
        self.assertEqual(editor.calls[0][0], SOURCE_URL)
        # side / back 的输入图都必须是 canonical_front
        self.assertEqual(editor.calls[1][0], FRONT_URL)
        self.assertEqual(editor.calls[2][0], FRONT_URL)
        # side 请求没有使用原始 side 图
        self.assertNotEqual(editor.calls[1][0], SOURCE_URL)
        self.assertEqual(views["front"]["url"], FRONT_URL)
        self.assertEqual(views["side"]["url"], SIDE_URL)
        self.assertEqual(views["back"]["url"], BACK_URL)
        self.assertEqual(failures, [])

    def test_canonical_front_failure_blocks_side_and_back(self):
        editor = _Editor([_front_result(), _front_result(), _side_result(), _back_result()])
        with mock.patch.object(svc, "_classify_character_view", return_value=SIDE), \
                mock.patch.object(svc, "ImageEditProvider", return_value=editor):
            with self.assertRaises(svc.CanonicalFrontError) as ctx:
                svc.generate_turnaround(
                    {},
                    SOURCE_URL,
                    front_image={"file": "src.png", "url": SOURCE_URL, "model": "gen"},
                )
        self.assertEqual(str(ctx.exception), "无法建立可靠的正面基准图，未生成侧视和背视")
        # 初次编辑 + 强化重试 = 2 次；从未触达 side / back
        self.assertEqual(len(editor.calls), 2)

    def test_valid_front_source_is_reused_without_extra_edit(self):
        editor = _Editor([_side_result(), _back_result()])
        with mock.patch.object(svc, "_classify_character_view", return_value=FRONT), \
                mock.patch.object(svc, "ImageEditProvider", return_value=editor):
            views, failures = svc.generate_turnaround(
                {},
                SOURCE_URL,
                front_image={"file": "src.png", "url": SOURCE_URL, "model": "gen"},
            )
        # 复用原画：不产生 front 编辑，仅 side / back 两次
        self.assertEqual(len(editor.calls), 2)
        self.assertEqual(editor.calls[0][0], SOURCE_URL)
        self.assertEqual(editor.calls[1][0], SOURCE_URL)
        self.assertTrue(views["front"].get("reused"))
        self.assertEqual(failures, [])


if __name__ == "__main__":
    unittest.main()
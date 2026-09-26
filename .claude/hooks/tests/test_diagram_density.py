"""図解の密度の検査（2026-08-29）。

手書き頁のSVG 6枚を**全文読んで**分かった差を固定する。前回は数え上げだけで
見落としていた＝箱の中の階層・帯・軸・曲線・中央揃えが出せていなかった。
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

HOOKS_DIR = Path(__file__).resolve().parents[1]
if str(HOOKS_DIR) not in sys.path:
    sys.path.insert(0, str(HOOKS_DIR))

from visual.artifact_inspection import inspect_artifact_html
from visual.contracts import ExplanationPlan
from visual.receipts import _has_external_dependency
from visual.render_components import render_components

NL = chr(10)


def _plan(*components: str) -> ExplanationPlan:
    return ExplanationPlan(
        audience="project_novice",
        depth="deep",
        components=tuple(components),
        reason_codes=(),
        provisional=False,
        should_continue=False,
        delivery="local_html",
        publish_policy="never",
    )


LAYERED = {
    "title": "主張の深さ4層",
    "axis": {"top": "浅い（見えやすい）", "bottom": "深い（書かれていない）"},
    "box_width": 430,
    "nodes": [
        {"id": "l1", "num": "1", "title": "表層＝数字・出典", "col": 0, "row": 0,
         "text": "資料に書いてあるものをそのまま見る。", "note": "担当＝既存レンズ",
         "tone": "good"},
        {"id": "l2", "num": "2", "title": "論証＝つながり", "col": 0, "row": 1,
         "text": "前提から結論への飛びを見る。", "tone": "good"},
        {"id": "l3", "num": "3", "title": "前提＝暗黙の仮定", "col": 0, "row": 2,
         "text": "書かれていないが必要な仮定。", "note": "部分的",
         "tone": "warn"},
    ],
    "bands": [
        {"col": 1, "w": 150, "label": "決定論の層", "note": "AIを呼ばない・追加0",
         "items": ["掛け算の検算", "確信度の算出", "関門10個の判定"], "tone": "acc"},
    ],
    "edges": [
        {"from": "l1", "to": "l2"},
        {"from": "l2", "to": "l3", "curve": True, "label": "深くなる"},
    ],
}


class BoxHierarchyTests(unittest.TestCase):
    """箱の中が役割で分かれる（番号・見出し・本文・補足）。"""

    def setUp(self):
        self.html = render_components(
            _plan("diagram"), title="図", content={"diagram": LAYERED}
        )

    def test_number_title_body_and_note_use_different_sizes(self):
        self.assertIn('font-size="15.0" font-weight="700">1</text>', self.html)
        self.assertIn('font-size="13.5" font-weight="700">表層＝数字・出典</text>', self.html)
        self.assertIn('font-size="12.0">資料に書いてあるものをそのまま見る。</text>', self.html)
        self.assertIn('font-size="10.5">担当＝既存レンズ</text>', self.html)

    def test_box_width_can_be_forced_so_columns_line_up(self):
        widths = []
        text = self.html
        i = 0
        while True:
            i = text.find('<rect x=', i)
            if i < 0:
                break
            j = text.find('width="', i)
            k = text.find('"', j + 7)
            widths.append(text[j + 7:k])
            i = k
        # 3つの箱が同じ幅にそろう（帯は別の幅）
        self.assertGreaterEqual(widths.count("430.0"), 3)


class BandTests(unittest.TestCase):
    """帯（領域）を箱の背面に置ける。"""

    def test_band_is_dashed_and_holds_its_own_items(self):
        html = render_components(
            _plan("diagram"), title="図", content={"diagram": LAYERED}
        )

        self.assertIn('stroke-dasharray="5 4"', html)
        self.assertIn("決定論の層", html)
        self.assertIn("AIを呼ばない・追加0", html)
        self.assertIn("掛け算の検算", html)
        self.assertIn("関門10個の判定", html)
        # 帯は中央揃えで並ぶ
        self.assertGreaterEqual(html.count('text-anchor="middle"'), 4)


class AxisTests(unittest.TestCase):
    """軸＝左端の縦線と両端のラベル。"""

    def test_axis_line_and_both_labels(self):
        html = render_components(
            _plan("diagram"), title="図", content={"diagram": LAYERED}
        )

        self.assertIn("<line ", html)
        self.assertIn("浅い（見えやすい）", html)
        self.assertIn("深い（書かれていない）", html)


class CurveTests(unittest.TestCase):
    """曲線の矢印。"""

    def test_curved_edge_uses_a_bezier(self):
        html = render_components(
            _plan("diagram"),
            title="図",
            content={"diagram": {
                "nodes": [
                    {"id": "a", "label": "左上", "col": 0, "row": 0},
                    {"id": "b", "label": "右下", "col": 1, "row": 1},
                ],
                "edges": [{"from": "a", "to": "b", "curve": True}],
            }},
        )

        # 2026-09-12：制御点1つ（自由配置の curve）は二次 Q、2つなら三次 C。どちらもベジェ。
        self.assertRegex(html, r" [CQ] ")

    def test_without_curve_it_stays_an_elbow(self):
        html = render_components(
            _plan("diagram"),
            title="図",
            content={"diagram": {
                "nodes": [
                    {"id": "a", "label": "左上", "col": 0, "row": 0},
                    {"id": "b", "label": "右下", "col": 1, "row": 1},
                ],
                "edges": [{"from": "a", "to": "b"}],
            }},
        )

        self.assertNotIn(" C ", html)


class CenterAlignTests(unittest.TestCase):
    def test_node_can_be_centered(self):
        html = render_components(
            _plan("diagram"),
            title="図",
            content={"diagram": {"nodes": [
                {"id": "a", "label": "まんなか", "align": "center"},
            ]}},
        )

        self.assertIn('text-anchor="middle"', html)


class StillSafeTests(unittest.TestCase):
    """密度を上げても、安全と検査の性質は変わらない。"""

    def test_raw_markup_in_any_field_is_escaped(self):
        html = render_components(
            _plan("diagram"),
            title="図",
            content={"diagram": {
                "nodes": [{"id": "a", "title": "<script>x</script>", "note": "<b>y</b>"}],
                "bands": [{"col": 1, "label": "<i>z</i>", "items": ["<u>w</u>"]}],
                "axis": {"top": "<em>t</em>"},
            }},
        )

        for bad in ("<script>x", "<b>y</b>", "<i>z</i>", "<u>w</u>", "<em>t</em>"):
            self.assertNotIn(bad, html)
        self.assertIn("&lt;script&gt;", html)

    def test_diagram_still_passes_both_gates(self):
        html = render_components(
            _plan("diagram"), title="図", content={"diagram": LAYERED}
        )

        self.assertFalse(_has_external_dependency(html))
        inspection = inspect_artifact_html(
            html, required_components=("diagram",), glossary_entries={}
        )
        self.assertEqual(inspection.errors, ())

    def test_old_label_only_style_still_works(self):
        html = render_components(
            _plan("diagram"),
            title="図",
            content={"diagram": {
                "nodes": [{"id": "a", "label": "1行目" + NL + "2行目"}],
            }},
        )

        self.assertIn("1行目", html)
        self.assertIn("2行目", html)


if __name__ == "__main__":
    unittest.main()

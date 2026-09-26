"""頁全体の2段組み＝側柱の検査（2026-08-30 ユーザー裁定）。

⚠️裁定が2つあり、素直に読むとぶつかる。
  Q1＝「頁全体の2段組みも要る」／判定2＝「節そのものは横に並べないほうがよい＝採用」。
  両立の形＝**側柱は節ではない**（`data-component` を持たない添え物）。
  ここでその不変条件を固定する＝側柱に節が混ざったら検査が落ちる。
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
from visual.render_components import render_components


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


class RailTests(unittest.TestCase):
    def setUp(self):
        self.html = render_components(
            _plan("walkthrough", "evidence"),
            title="題",
            content={
                "walkthrough": "見出し：本文",
                "evidence": "実測：内容｜出所",
                "rail": [
                    {"heading": "この頁の要点",
                     "items": ["1つめ", "2つめ"],
                     "note": "⚠️側柱は添え物である。"},
                    {"heading": "数字", "table": {"head": ["A"], "rows": [["1"]]}},
                ],
            },
        )

    def test_the_page_declares_the_two_column_layout(self):
        self.assertIn('<div class="wrap" data-layout="rail">', self.html)
        self.assertIn('<main class="flow">', self.html)
        self.assertIn('<aside class="rail">', self.html)

    def test_the_rail_is_not_a_section(self):
        # ⚠️ここが判定2（節そのものは横に並べない）を守る一線。
        rail = self.html[self.html.index('<aside class="rail">'):]
        rail = rail[: rail.index("</aside>")]
        self.assertNotIn("data-component", rail)
        self.assertNotIn("<section", rail)

    def test_the_sections_stay_in_one_column_in_document_order(self):
        flow = self.html[self.html.index('<main class="flow">'):]
        flow = flow[: flow.index("</main>")]
        self.assertLess(flow.index('data-component="walkthrough"'),
                        flow.index('data-component="evidence"'))
        self.assertEqual(flow.count("<section"), 2)

    def test_the_rail_content_is_rendered_with_the_usual_blocks(self):
        self.assertIn('<p class="rail-head">この頁の要点</p>', self.html)
        self.assertIn('<ul class="bullets">', self.html)
        self.assertIn("<table>", self.html)

    def test_the_two_columns_only_apply_on_wide_screens(self):
        # ⚠️境目は1100px→1000pxに下げた（2026-09-01）。実害＝1000px以下では側柱が本文の
        #   後ろに回り、**目次が頁の93〜96%の位置**に落ちていた（表示枠が狭い環境で常にそう）。
        self.assertIn("@media(min-width:1000px)", self.html)
        # 狭い画面では側柱を見出しの直後へ。ここが消えると目次が最下部に戻る。
        self.assertIn('.wrap[data-layout="rail"]>.rail{order:-1}', self.html)
        self.assertIn('.wrap[data-layout="rail"]>.rail{order:0;position:sticky', self.html)
        self.assertIn('.wrap[data-layout="rail"]{display:grid;'
                      'grid-template-columns:minmax(0,1fr) 19rem;', self.html)

    def test_the_page_still_passes_the_inspector(self):
        inspection = inspect_artifact_html(
            self.html, required_components=("walkthrough", "evidence"), glossary_entries={}
        )

        self.assertEqual(inspection.errors, ())
        self.assertEqual(inspection.missing_components, ())

    def test_markup_in_the_rail_is_escaped(self):
        html = render_components(
            _plan("walkthrough"),
            title="題",
            content={"walkthrough": "見出し：本文",
                     "rail": [{"heading": "<b>h</b>", "text": "<script>x</script>"}]},
        )

        self.assertNotIn("<b>h</b>", html)
        self.assertIn("&lt;script&gt;", html)


class NoRailTests(unittest.TestCase):
    """側柱を渡さない頁は今までと同じ形のまま。"""

    def setUp(self):
        self.html = render_components(
            _plan("walkthrough"), title="題", content={"walkthrough": "見出し：本文"}
        )

    def test_one_column_pages_are_unchanged(self):
        self.assertIn('<div class="wrap">', self.html)
        # ⚠️CSSには常に `.wrap[data-layout="rail"]` の規則が載っている。
        #   見るのは**器に属性が付いたか**であって、文字列が出るかではない。
        self.assertNotIn('class="wrap" data-layout', self.html)
        self.assertNotIn('<main class="flow">', self.html)
        self.assertNotIn('<aside class="rail">', self.html)

    def test_an_empty_rail_does_not_switch_the_layout(self):
        html = render_components(
            _plan("walkthrough"), title="題",
            content={"walkthrough": "見出し：本文", "rail": []},
        )

        self.assertNotIn('class="wrap" data-layout', html)


if __name__ == "__main__":
    unittest.main()

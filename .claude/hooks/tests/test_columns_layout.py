"""横並びのレイアウトの検査（2026-08-29 ユーザー承認）。

⚠️手書き頁の実測＝`grid-template-columns:1fr 1fr` が5箇所、
   `repeat(auto-fit,minmax(…,1fr))` 系のタイルが10箇所。この2つが横並びの正体だった。

節そのものは縦に積むまま。**節の中に横並びの塊を置く**設計にしている。
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


class ColumnsTests(unittest.TestCase):
    """2段組み・3段組み。"""

    def test_two_columns_hold_independent_blocks(self):
        html = render_components(
            _plan("walkthrough"),
            title="題",
            content={"walkthrough": [{
                "heading": "前と後",
                "columns": [
                    {"heading": "前", "text": "できなかったこと。",
                     "items": ["横に並べられない"]},
                    {"heading": "後", "text": "できるようになったこと。",
                     "table": {"head": ["A"], "rows": [["1"]]}},
                ],
            }]},
        )

        self.assertIn('class="cols" data-cols="2"', html)
        self.assertEqual(html.count('class="col"'), 2)
        self.assertIn("<h3>前</h3>", html)
        self.assertIn("<h3>後</h3>", html)
        self.assertIn('<ul class="bullets">', html)
        self.assertIn("<table>", html)

    def test_three_columns(self):
        html = render_components(
            _plan("walkthrough"),
            title="題",
            content={"walkthrough": [{"columns": [
                {"text": "左"}, {"text": "中"}, {"text": "右"},
            ]}]},
        )

        self.assertIn('data-cols="3"', html)
        self.assertEqual(html.count('class="col"'), 3)

    def test_more_than_four_columns_is_capped(self):
        html = render_components(
            _plan("walkthrough"),
            title="題",
            content={"walkthrough": [{"columns": [{"text": str(i)} for i in range(6)]}]},
        )

        self.assertIn('data-cols="4"', html)
        self.assertEqual(html.count('class="col"'), 6)

    def test_columns_collapse_on_narrow_screens(self):
        html = render_components(
            _plan("walkthrough"),
            title="題",
            content={"walkthrough": [{"columns": [{"text": "左"}, {"text": "右"}]}]},
        )

        # ⚠️狭い画面で横スクロールを出さないための1行。消すと390pxで溢れる。
        self.assertIn(".cols[data-cols]{grid-template-columns:1fr}", html)
        self.assertIn('.cols[data-cols="2"]{grid-template-columns:1fr 1fr}', html)


class TilesTests(unittest.TestCase):
    """短い項目を敷き詰める。"""

    def test_tiles_wrap_and_carry_tones(self):
        html = render_components(
            _plan("examples"),
            title="題",
            content={"examples": [{"tiles": [
                {"title": "確認済み", "text": "説明", "tone": "good"},
                {"title": "注意", "tone": "warn"},
                {"title": "失敗", "tone": "bad"},
                {"title": "素の印"},
            ]}]},
        )

        self.assertIn('class="tiles"', html)
        self.assertEqual(html.count('class="tile"'), 4)
        # ⚠️`data-tone=` だけを数えるとCSSの `.tile[data-tone="good"]` まで拾う。
        self.assertEqual(html.count('<div class="tile" data-tone='), 3)
        self.assertIn('data-tone="good"', html)
        self.assertIn("repeat(auto-fit,minmax(11rem,1fr))", html)


class SafetyTests(unittest.TestCase):
    def test_markup_inside_columns_and_tiles_is_escaped(self):
        html = render_components(
            _plan("walkthrough"),
            title="題",
            content={"walkthrough": [{
                "columns": [{"heading": "<b>h</b>", "text": "<script>x</script>"}],
                "tiles": [{"title": "<i>t</i>", "text": "<u>u</u>"}],
            }]},
        )

        for bad in ("<b>h</b>", "<script>x", "<i>t</i>", "<u>u</u>"):
            self.assertNotIn(bad, html)
        self.assertIn("&lt;script&gt;", html)

    def test_page_with_columns_still_passes_the_inspector(self):
        html = render_components(
            _plan("walkthrough", "examples"),
            title="題",
            content={
                "walkthrough": [{"columns": [{"text": "左"}, {"text": "右"}]}],
                "examples": [{"tiles": [{"title": "印"}]}],
            },
        )

        inspection = inspect_artifact_html(
            html, required_components=("walkthrough", "examples"), glossary_entries={}
        )

        self.assertEqual(inspection.errors, ())
        self.assertEqual(inspection.missing_components, ())


if __name__ == "__main__":
    unittest.main()

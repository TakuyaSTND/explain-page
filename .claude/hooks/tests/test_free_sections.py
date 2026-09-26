"""節の自由化の検査（2026-08-29 ユーザー要望）。

手書き頁の節は「壱　いま何ができて、何ができないか（4層の梯子）」のように
**その頁の中身を語る言葉**だった。レンダラーは「全体像」「具体例」という
部品の名前をそのまま出すので、どの頁も同じ見出しになっていた。

⚠️並び順は元から自由だった（`plan.components` の順で出る）。固定だったのは
  見出し・番号・同じ部品の繰り返しの3つ。
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


def _order_of(html: str) -> list[str]:
    """出てきた順に data-component を拾う。"""
    out = []
    i = 0
    key = '<section data-component="'
    while True:
        i = html.find(key, i)
        if i < 0:
            break
        j = html.find('"', i + len(key))
        out.append(html[i + len(key):j])
        i = j
    return out


class OrderWasAlreadyFreeTests(unittest.TestCase):
    """並び順は元から自由。ここでそれを固定しておく。"""

    def test_components_appear_in_the_order_given(self):
        html = render_components(
            _plan("details", "table", "walkthrough"),
            title="題",
            content={"details": "見出し：本文", "table": {"head": ["A"], "rows": [["1"]]},
                     "walkthrough": "見出し：本文"},
        )

        self.assertEqual(_order_of(html), ["details", "table", "walkthrough"])


class FreeSectionTests(unittest.TestCase):
    """節を一覧で書くと、見出し・番号・繰り返しが自由になる。"""

    def setUp(self):
        self.html = render_components(
            _plan("walkthrough", "table", "evidence"),
            title="題",
            content={
                "sections": [
                    {"component": "walkthrough", "num": "壱",
                     "label": "いま何ができて、何ができないか",
                     "content": "背景：これまでの話。"},
                    {"component": "table", "num": "弐", "label": "実測の突き合わせ",
                     "content": {"head": ["A"], "rows": [["1"]]}},
                    {"component": "table", "num": "参", "label": "別の切り口",
                     "content": {"head": ["B"], "rows": [["2"]]}},
                ],
                "evidence": "実測：内容｜どこで",
            },
        )

    def test_headings_are_the_authors_words_not_the_component_names(self):
        self.assertIn("いま何ができて、何ができないか", self.html)
        self.assertIn("実測の突き合わせ", self.html)
        self.assertNotIn("<h2>順番に説明</h2>", self.html)

    def test_sections_can_be_numbered(self):
        self.assertIn('<span class="sec-no">壱</span>', self.html)
        self.assertIn('<span class="sec-no">弐</span>', self.html)
        self.assertIn('<span class="sec-no">参</span>', self.html)

    def test_the_same_component_can_appear_more_than_once(self):
        self.assertEqual(_order_of(self.html).count("table"), 2)
        self.assertIn("<th>A</th>", self.html)
        self.assertIn("<th>B</th>", self.html)

    def test_components_not_listed_are_still_emitted_so_the_receipt_holds(self):
        # ⚠️書き忘れた部品を落とすと検品証が落ちる。安全網として末尾に足す。
        self.assertIn("evidence", _order_of(self.html))

    def test_the_page_still_passes_the_inspector(self):
        inspection = inspect_artifact_html(
            self.html,
            required_components=("walkthrough", "table", "evidence"),
            glossary_entries={},
        )

        self.assertEqual(inspection.missing_components, ())
        self.assertEqual(inspection.errors, ())


class SummaryPlacementTests(unittest.TestCase):
    """全体像も節として好きな位置に置ける。"""

    def test_summary_moves_when_listed_in_sections(self):
        html = render_components(
            _plan("summary", "table"),
            title="題",
            content={
                "sections": [
                    {"component": "table", "label": "先に表", "content": {"head": ["A"], "rows": [["1"]]}},
                    {"component": "summary", "label": "あとで案内板", "content": "Goal：確かめる。"},
                ],
            },
        )

        self.assertEqual(_order_of(html), ["table", "summary"])
        self.assertIn("あとで案内板", html)

    def test_summary_stays_at_the_top_when_not_listed(self):
        html = render_components(
            _plan("summary", "table"),
            title="題",
            content={"summary": "Goal：確かめる。", "table": {"head": ["A"], "rows": [["1"]]}},
        )

        self.assertEqual(_order_of(html)[0], "summary")


class BackwardCompatibilityTests(unittest.TestCase):
    def test_dict_only_content_is_unchanged(self):
        html = render_components(
            _plan("overview", "walkthrough"),
            title="題",
            content={"overview": "本文", "walkthrough": "見出し：本文"},
        )

        self.assertIn('class="lede"', html)
        self.assertIn("<h2>順番に説明</h2>", html)
        self.assertNotIn('class="sec-no"', html)


if __name__ == "__main__":
    unittest.main()

"""案の一覧（proposals ブロック）の検査（2026-10-19・利用者の選択）。

案ごとに図・見積もり・利点と代償を1枚のカードにする。図は visual/exhibits.py の kind か SVG の文字列で渡し、
許可リストで組み直される。使う頁にだけ CSS が付く。
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

HOOKS_DIR = Path(__file__).resolve().parents[1]
if str(HOOKS_DIR) not in sys.path:
    sys.path.insert(0, str(HOOKS_DIR))

from visual.blocks import number_blocks
from visual.contracts import ExplanationPlan
from visual.exhibits import EXHIBITS, exhibit_svg
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


def _render(proposals):
    return render_components(
        _plan("visual"),
        title="題",
        content={"visual": [{"proposals": proposals}]},
    )


class ProposalsBlockTests(unittest.TestCase):
    def test_card_has_number_title_rating_figure_and_text(self):
        html = _render([{
            "no": "1", "title": "中核を先頭に出す", "claim": "一番上に置く。",
            "exhibit": "core_first", "rating": {"accuracy": 3, "cost": -1},
            "pros": "形がそのまま出る", "cons": "読む量は変わらない",
            "notes": ["口調は先輩の形", "一番重い1点を名指しする"],
        }])
        self.assertIn('<div class="props">', html)
        self.assertIn('class="prop-no">案1<', html)
        self.assertIn("中核を先頭に出す", html)
        self.assertIn("精度向上 +3", html)
        self.assertIn("コスト削減 −1", html)
        self.assertIn('<figure class="prop-fig"><svg', html)
        self.assertIn('<p class="prop-pc"><b>利点</b>', html)
        self.assertIn('<p class="prop-pc"><b>代償</b>', html)
        self.assertIn('<ul class="bullets">', html)

    def test_recommended_marks_the_card_and_adds_a_badge(self):
        html = _render([
            {"no": "1", "title": "A", "recommended": True},
            {"no": "2", "title": "B"},
        ])
        self.assertEqual(html.count('<article class="prop" data-recommended="1">'), 1)
        self.assertEqual(html.count('<article class="prop" data-recommended="0">'), 1)
        self.assertEqual(html.count(">推奨<"), 1)

    def test_rating_can_be_a_plain_string(self):
        html = _render([{"no": "1", "title": "A", "rating": "+3／−1"}])
        self.assertIn('<p class="prop-rate">+3／−1</p>', html)

    def test_svg_string_is_accepted_and_rebuilt_from_the_allowlist(self):
        svg = '<svg viewBox="0 0 10 10"><rect x="1" y="1" width="5" height="5"/><script>alert(1)</script></svg>'
        html = _render([{"no": "1", "title": "A", "exhibit": svg}])
        self.assertIn('class="prop-fig"', html)
        self.assertNotIn("<script>alert", html)
        self.assertIn("<rect", html)

    def test_dict_exhibit_with_caption(self):
        html = _render([{"no": "1", "title": "A", "exhibit": {"kind": "type", "caption": "型の図"}}])
        self.assertIn("<figcaption>型の図</figcaption>", html)

    def test_unknown_kind_says_so_and_keeps_the_card(self):
        html = _render([{"no": "1", "title": "A", "exhibit": "nothing_like_this"}])
        self.assertIn('class="prop-fig-missing"', html)
        self.assertIn('class="prop"', html)

    def test_no_exhibit_is_fine(self):
        html = _render([{"no": "1", "title": "A", "claim": "文だけ"}])
        self.assertNotIn('<figure class="prop-fig">', html)
        self.assertIn("文だけ", html)

    def test_css_only_when_used(self):
        used = _render([{"no": "1", "title": "A"}])
        unused = render_components(_plan("visual"), title="題", content={"visual": [{"text": "文"}]})
        self.assertIn(".prop-body{display:grid", used)
        self.assertNotIn(".prop-body{display:grid", unused)

    def test_every_exhibit_kind_renders_and_stays_small(self):
        for kind in EXHIBITS:
            with self.subTest(kind=kind):
                svg = exhibit_svg(kind)
                self.assertLess(len(svg.encode("utf-8")), 8000)
                html = _render([{"no": "1", "title": kind, "exhibit": kind}])
                self.assertIn('<figure class="prop-fig"><svg', html)
                self.assertNotIn("http", svg)

    def test_unknown_kind_raises_in_the_helper(self):
        with self.assertRaises(ValueError):
            exhibit_svg("nothing_like_this")

    def test_each_card_becomes_a_numbered_unit_for_review(self):
        html = _render([{"no": "1", "title": "A"}, {"no": "2", "title": "B"}])
        numbered, blocks = number_blocks(html)
        self.assertGreaterEqual(numbered.count('data-blk="'), 2)
        self.assertTrue(any(b.kind == "proposal" for b in blocks))

    def test_decision_option_thumb_helper_returns_svg(self):
        from visual.exhibits import option_thumb

        thumb = option_thumb("gold")
        self.assertIn("svg", thumb)
        self.assertTrue(thumb["svg"].startswith("<svg"))


if __name__ == "__main__":
    unittest.main()

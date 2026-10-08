"""判断の選択肢に「利点」と「代償」を分けて置く（2026-10-08・赤ペン流の判断の頁）。

ねらい＝非推奨の選択肢にも「選ぶ理由（利点）」を書かせ、実質1択の頁を減らす。
既存の書き方（why だけ・文字列だけの options）は1バイトも変えない。
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


def _page(options, *, kind="radio") -> str:
    content = {"decision": {"groups": [{"legend": "どれで進めるか", "kind": kind, "options": options}]}}
    return render_components(_plan("decision"), title="判断", content=content)


class ProsConsRenderTests(unittest.TestCase):
    def test_pros_and_cons_appear_inside_one_pros_cons_span(self):
        html = _page(
            [
                {
                    "label": "案A",
                    "recommended": True,
                    "pros": "一覧を見ながら詳細を読める",
                    "cons": "狭い画面では一覧が隠れる",
                },
                {"label": "案B", "pros": "実装が小さい", "cons": "一覧が長いと下へ押し出される"},
            ]
        )

        self.assertIn(
            '<span class="pros-cons"><b class="pro">利点</b> 一覧を見ながら詳細を読める'
            '<br><b class="con">代償</b> 狭い画面では一覧が隠れる</span>',
            html,
        )
        self.assertEqual(html.count('<span class="pros-cons">'), 2)

    def test_only_pros_shows_only_the_pros_line(self):
        html = _page([{"label": "案A", "pros": "手間が無い"}])

        self.assertIn('<b class="pro">利点</b> 手間が無い', html)
        self.assertNotIn('class="con"', html)

    def test_only_cons_shows_only_the_cons_line(self):
        html = _page([{"label": "案A", "cons": "費用がかかる"}])

        self.assertIn('<b class="con">代償</b> 費用がかかる', html)
        self.assertNotIn('class="pro"', html)

    def test_list_values_are_joined_with_the_slash(self):
        html = _page([{"label": "案A", "pros": ["速い", "安い", ""], "cons": ["脆い"]}])

        self.assertIn('<b class="pro">利点</b> 速い／安い<br>', html)
        self.assertIn('<b class="con">代償</b> 脆い</span>', html)

    def test_pros_and_cons_are_escaped(self):
        html = _page([{"label": "案A", "pros": "<script>alert(1)</script>"}])

        self.assertNotIn("<script>alert(1)</script>", html)
        self.assertIn("&lt;script&gt;alert(1)&lt;/script&gt;", html)

    def test_why_and_pros_cons_are_both_shown(self):
        html = _page([{"label": "案A", "why": "補足の理由", "pros": "利点の文", "cons": "代償の文"}])

        self.assertIn('<span class="why">補足の理由</span>', html)
        self.assertIn('<b class="pro">利点</b> 利点の文', html)
        # 利点・代償は why より前に置く（読む順）。
        self.assertLess(html.index("代償の文"), html.index("補足の理由"))

    def test_checkbox_options_take_pros_and_cons_too(self):
        html = _page([{"label": "論点X", "pros": "追加費用0"}], kind="checkbox")

        self.assertIn('type="checkbox" name="decision"', html)
        self.assertIn('<b class="pro">利点</b> 追加費用0', html)


class BackwardCompatibilityTests(unittest.TestCase):
    def test_why_only_option_keeps_the_exact_old_markup(self):
        html = _page([{"label": "案B", "why": "理由"}])

        self.assertIn(
            '<label class="choice"><input type="radio" name="decision" data-req="1" '
            'data-label="案B"><span>案B<span class="why">理由</span></span></label>',
            html,
        )

    def test_string_only_options_have_no_pros_cons_and_no_thumb(self):
        html = _page(["案A", "案B"])

        self.assertNotIn('<span class="pros-cons">', html)
        self.assertNotIn('<span class="thumb', html)
        self.assertNotIn('class="choice has-thumb"', html)
        self.assertIn(
            '<label class="choice"><input type="radio" name="decision" data-req="1" '
            'data-label="案A"><span>案A</span></label>',
            html,
        )


class InspectionTests(unittest.TestCase):
    def test_page_with_pros_and_cons_still_passes_the_decision_gate(self):
        html = _page(
            [
                {"label": "案A", "recommended": True, "pros": "安い", "cons": "取りこぼす"},
                {"label": "案B", "pros": "確実", "cons": "時間がかかる"},
            ]
        )

        inspection = inspect_artifact_html(
            html, required_components=("decision",), glossary_entries={}
        )

        self.assertEqual(inspection.missing_decision_parts, ())
        self.assertEqual(inspection.errors, ())

    def test_pros_cons_css_uses_theme_variables_only(self):
        html = _page([{"label": "案A", "pros": "安い"}])
        start = html.index(".pros-cons{")
        end = html.index("\n", start)
        rule = html[start:end]

        self.assertIn("var(--pass)", rule)
        self.assertIn("var(--fail)", rule)
        self.assertNotIn("#", rule)


if __name__ == "__main__":
    unittest.main()

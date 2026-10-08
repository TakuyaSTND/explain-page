"""手書き頁21枚を走査して見つかった「まだ出せない要素」の検査（2026-08-29）。

走査＝承認済みの置き場（一時フォルダの下）と作業フォルダの手書きHTML 21枚（レンダラー製は除外）。
タグとclassを数え上げ、レンダラーに無いものを洗い出した結果を、ここで固定する。
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


class CellBreakTests(unittest.TestCase):
    """表のセルの中で改行できる（手書き頁は br を55回使っていた）。"""

    def test_newline_inside_a_cell_becomes_a_small_note(self):
        # 2026-10-01（ユーザー承認の P5）：セルの改行の後は小さい注記になる（以前は br だけ）。
        # 3行目以降は注記の中で改行する。注記にしない改行は [[br]] で書ける。
        html = render_components(
            _plan("table"),
            title="表",
            content={"table": {"head": ["項目"], "rows": [
                ["1行目" + NL + "2行目" + NL + "3行目"],
                ["前[[br]]後"],
            ]}},
        )

        self.assertIn('1行目<span class="cell-note">2行目<br>3行目</span>', html)
        self.assertIn("前<br>後", html)

    def test_explicit_break_notation(self):
        html = render_components(
            _plan("overview"), title="題", content={"overview": "前[[br]]後"}
        )

        self.assertIn("前<br>後", html)


class MemoryTests(unittest.TestCase):
    """入力した内容を憶える（手書き頁は2枚が localStorage を使っていた）。"""

    def test_the_page_remembers_and_can_forget(self):
        html = render_components(
            _plan("decision"),
            title="題",
            content={"decision": {"options": ["案A"], "judgments": ["判定1"]}},
        )

        self.assertIn("localStorage.setItem", html)
        self.assertIn("localStorage.getItem", html)
        self.assertIn("localStorage.removeItem", html)
        self.assertIn('id="forget-decision"', html)
        # ⚠️私邸窓では例外が出るので必ず try で包む
        self.assertIn("try{localStorage", html)


class InlineNotationTests(unittest.TestCase):
    """弱い強調とハイライト（手書き頁は em 41回・mark 4枚）。"""

    def test_em_and_mark(self):
        html = render_components(
            _plan("overview"),
            title="題",
            content={"overview": "*弱い強調* と ==目立たせ== と **太字**。"},
        )

        self.assertIn("<em>弱い強調</em>", html)
        self.assertIn("<mark>目立たせ</mark>", html)
        self.assertIn("<strong>太字</strong>", html)

    def test_bold_is_not_eaten_by_the_em_rule(self):
        html = render_components(
            _plan("overview"), title="題", content={"overview": "**太字だけ**"}
        )

        self.assertIn("<strong>太字だけ</strong>", html)
        self.assertNotIn("<em>", html)


class BlockPartsTests(unittest.TestCase):
    """塊に置ける部品（手書き頁は ol 16枚・dl 16枚・囲み34箇所・hr 2枚・引用1枚）。"""

    def _html(self):
        return render_components(
            _plan("walkthrough"),
            title="題",
            content={"walkthrough": [{
                "heading": "全部入り",
                "text": "本文。",
                "ordered": ["ひとつめ", "ふたつめ"],
                "pairs": [["語", "説明"], "語2：説明2"],
                "quote": "原文をそのまま。",
                "note": {"tone": "warn", "title": "注意", "text": "気をつける。"},
                "caption": "この塊の補足。",
                "divider": True,
            }]},
        )

    def test_every_part_is_rendered(self):
        html = self._html()

        self.assertIn('<ol class="numbered">', html)
        self.assertEqual(html.count("<li>"), 2)
        self.assertIn('<dl class="pairs">', html)
        self.assertEqual(html.count("<dt>"), 2)
        self.assertIn("<blockquote>", html)
        self.assertIn('class="note warn"', html)
        self.assertIn('class="cap"', html)
        self.assertIn("<hr>", html)

    def test_note_tone_is_fixed_to_meaning(self):
        html = render_components(
            _plan("walkthrough"),
            title="題",
            content={"walkthrough": [{"note": [
                {"tone": "good", "text": "確認済み"},
                {"tone": "bad", "text": "失敗"},
            ]}]},
        )

        self.assertIn('class="note good"', html)
        self.assertIn('class="note bad"', html)


class DecisionShapeTests(unittest.TestCase):
    """複数選択と数値入力（手書き頁は checkbox 2枚・number 2枚）。"""

    def test_multi_turns_choices_into_checkboxes(self):
        html = render_components(
            _plan("decision"),
            title="題",
            content={"decision": {"multi": True, "options": ["案A", "案B"]}},
        )

        self.assertEqual(html.count('type="checkbox" name="decision"'), 2)
        self.assertNotIn('type="radio" name="decision"', html)

    def test_single_choice_stays_a_radio_by_default(self):
        html = render_components(
            _plan("decision"), title="題", content={"decision": {"options": ["案A"]}}
        )

        self.assertIn('type="radio" name="decision"', html)

    def test_numbers_are_collected_into_the_request(self):
        html = render_components(
            _plan("decision"),
            title="題",
            content={"decision": {
                "options": ["案A"],
                "numbers": [{"label": "何日で", "unit": "日", "min": "1", "max": "30"}],
            }},
        )

        self.assertIn('type="number" name="decision-number"', html)
        self.assertIn('min="1"', html)
        self.assertIn('max="30"', html)
        self.assertIn("日", html)
        self.assertIn("decision-number", html)


class EverythingTogetherTests(unittest.TestCase):
    def test_a_page_using_every_part_passes_the_inspector(self):
        html = render_components(
            _plan("overview", "summary", "walkthrough", "examples", "visual",
                  "diagram", "table", "log", "decision", "evidence", "glossary", "details"),
            title="全部入り",
            content={
                "overview": "*弱い* と ==目立ち== と [[good:印]]。",
                "summary": "Goal：確かめる。",
                "walkthrough": [{"heading": "節", "ordered": ["1"], "pairs": [["語", "説明"]],
                                 "quote": "引用", "note": {"tone": "good", "text": "済"},
                                 "caption": "補足", "divider": True}],
                "examples": [{"cards": [{"badge": "J1", "title": "件名", "text": "本文"}]}],
                "visual": "左｜右",
                "diagram": {"nodes": [{"id": "a", "label": "箱"}]},
                "table": [{"heading": "表", "head": ["A"], "rows": [["1" + NL + "2"]]}],
                "log": "ログ",
                "decision": {"multi": True, "options": ["案A"], "judgments": ["判定1"],
                             "numbers": [{"label": "件数"}]},
                "evidence": "実測：内容｜どこで",
                "glossary": "語：説明",
                "details": [{"summary": "畳む", "table": {"head": ["A"], "rows": [["1"]]}}],
            },
        )

        inspection = inspect_artifact_html(
            html,
            required_components=("overview", "summary", "walkthrough", "examples",
                                 "visual", "diagram", "table", "log", "decision",
                                 "evidence", "glossary", "details"),
            glossary_entries={},
        )

        self.assertEqual(inspection.errors, ())
        self.assertEqual(inspection.missing_components, ())
        self.assertEqual(inspection.missing_decision_parts, ())


class UnpairedEmphasisTests(unittest.TestCase):
    """対の無い ** は、空の <em></em> に化けて記号ごと消えるのでなく、文字のまま出す（2026-10-09）。"""

    def _overview(self, text: str) -> str:
        html = render_components(_plan("overview"), title="題", content={"overview": text})
        return html.split('<p class="lede">', 1)[1].split("</p>", 1)[0]

    def test_a_double_star_inside_a_word_stays_as_text(self):
        self.assertEqual(self._overview("a**b"), "a**b")

    def test_an_opening_double_star_with_no_close_stays_as_text(self):
        self.assertEqual(self._overview("**x"), "**x")

    def test_a_closing_double_star_alone_stays_as_text(self):
        self.assertEqual(self._overview("x**"), "x**")

    def test_an_empty_bold_stays_as_text(self):
        self.assertEqual(self._overview("****"), "****")

    def test_no_empty_emphasis_tag_is_ever_made(self):
        for text in ("a**b", "**x", "x**", "****", "**a** と **b", "***x*", "*a* と **"):
            html = self._overview(text)
            self.assertNotIn("<em></em>", html, text)
            self.assertNotIn("<strong></strong>", html, text)

    def test_a_pair_around_text_is_still_bold_and_the_stray_one_stays(self):
        self.assertEqual(
            self._overview("**太字** と **対の無い"),
            "<strong>太字</strong> と **対の無い",
        )

    def test_weak_emphasis_works_as_before(self):
        self.assertEqual(self._overview("*弱い強調*"), "<em>弱い強調</em>")
        self.assertEqual(self._overview("a*b*c"), "a<em>b</em>c")

    def test_two_single_stars_still_pair_up_as_commonmark_does(self):
        # 仕様どおりの挙動（3*4 と 5*6 を掛け算として書くと強調になる）＝変えない。
        self.assertEqual(self._overview("3*4 and 5*6"), "3<em>4 and 5</em>6")

    def test_a_double_star_inside_a_table_cell_and_a_list_item_stays_as_text(self):
        html = render_components(
            _plan("walkthrough"),
            title="題",
            content={"walkthrough": [{"heading": "節", "ordered": ["a**b"]}]},
        )

        self.assertNotIn("<em></em>", html)
        self.assertIn("a**b", html)


if __name__ == "__main__":
    unittest.main()

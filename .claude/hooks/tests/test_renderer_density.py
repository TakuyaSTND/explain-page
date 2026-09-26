"""参照頁の密度に追いつくための追加分の検査（2026-08-29）。

参照＝artifact 589b3b61「前提と政治判断の審査設計」。実測で
表14枚・小見出し31個・バッジ64個・カード16枚・入力42個あり、
当時のレンダラーではどれも出せなかった。ここではその差分を固定する。
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


class ManyTablesTests(unittest.TestCase):
    """1つの節に表を何枚でも置ける（参照は1頁に14枚）。"""

    def test_a_list_of_tables_renders_them_all(self):
        html = render_components(
            _plan("table"),
            title="表",
            content={"table": [
                {"heading": "1枚目", "caption": "ひとつめ", "head": ["A"], "rows": [["1"]]},
                {"heading": "2枚目", "caption": "ふたつめ", "head": ["B"], "rows": [["2"]]},
                {"heading": "3枚目", "head": ["C"], "rows": [["3"]]},
            ]},
        )

        self.assertEqual(html.count("<table>"), 3)
        self.assertEqual(html.count("<caption>"), 2)
        self.assertEqual(html.count("<h3>"), 3)
        self.assertIn("1枚目", html)
        self.assertIn("3枚目", html)

    def test_column_widths_are_honoured(self):
        html = render_components(
            _plan("table"),
            title="表",
            content={"table": {
                "head": ["#", "論点", "決定"],
                "widths": ["56px", "150px", ""],
                "rows": [["D5", "意味グラフ", "小さく試す"]],
            }},
        )

        self.assertIn('<th style="width:56px">#</th>', html)
        self.assertIn('<th style="width:150px">論点</th>', html)
        self.assertIn("<th>決定</th>", html)


class InlineBadgeTests(unittest.TestCase):
    """本文と表のセルにバッジを置ける（参照は64個）。"""

    def test_badge_notation_in_running_text(self):
        html = render_components(
            _plan("overview"),
            title="題",
            content={"overview": "実装は [[good:完了]] だが較正は [[warn:要較正]] のまま。"},
        )

        self.assertIn('<span class="badge b-good">完了</span>', html)
        self.assertIn('<span class="badge b-warn">要較正</span>', html)

    def test_five_tones_including_the_purple_one(self):
        html = render_components(
            _plan("overview"),
            title="題",
            content={"overview": "[[good:済]][[warn:注意]][[bad:失敗]][[new:新規]][[acc:参考]]"},
        )

        for cls in ("b-good", "b-warn", "b-bad", "b-new", "b-acc"):
            self.assertIn(cls, html)
        self.assertIn("--new:#6A4FA3", html)

    def test_badge_without_a_tone_falls_back_to_accent(self):
        html = render_components(
            _plan("overview"), title="題", content={"overview": "[[素の印]]"}
        )

        self.assertIn('<span class="badge b-acc">素の印</span>', html)

    def test_badge_text_is_escaped(self):
        html = render_components(
            _plan("overview"), title="題", content={"overview": "[[good:<b>x</b>]]"}
        )

        self.assertIn("&lt;b&gt;x&lt;/b&gt;", html)
        self.assertNotIn("<b>x</b>", html)

    def test_badges_work_inside_table_cells(self):
        html = render_components(
            _plan("table"),
            title="表",
            content={"table": {"head": ["項目", "状態"], "rows": [["Q8", "[[good:完了]]"]]}},
        )

        self.assertIn('<span class="badge b-good">完了</span>', html)


class SectionBlocksTests(unittest.TestCase):
    """1つの節の中に小見出し・箇条書き・表・カードを混ぜられる。"""

    def test_a_component_accepts_a_list_of_blocks(self):
        html = render_components(
            _plan("walkthrough"),
            title="題",
            content={"walkthrough": [
                {"heading": "第1ラウンド", "text": "決めたこと。",
                 "table": {"head": ["#"], "rows": [["D5"]]}},
                {"heading": "第2ラウンド", "items": ["ひとつ", "ふたつ"]},
            ]},
        )

        self.assertEqual(html.count("<h3>"), 2)
        self.assertIn("第1ラウンド", html)
        self.assertIn("<table>", html)
        self.assertIn('<ul class="bullets">', html)
        self.assertEqual(html.count("<li>"), 2)

    def test_plain_string_content_is_unchanged(self):
        html = render_components(
            _plan("walkthrough"), title="題", content={"walkthrough": "見出し：本文"}
        )

        self.assertIn('<ol class="steps">', html)
        self.assertNotIn("<h3>見出し</h3>", html)


class CardTests(unittest.TestCase):
    """判定を1件ずつカードで見せられる（参照は16枚）。"""

    def test_cards_carry_a_badge_a_title_and_a_tone(self):
        html = render_components(
            _plan("examples"),
            title="題",
            content={"examples": [
                {"cards": [
                    {"badge": "判定 J8", "tone": "warn", "title": "実装の穴を1件見つけた",
                     "text": "タグが最終出力で消えていた。", "items": ["原因", "直し"]},
                    {"badge": "判定 J9", "tone": "good", "title": "較正は通った"},
                ]}
            ]},
        )

        self.assertEqual(html.count('class="card"'), 2)
        self.assertIn('data-tone="warn"', html)
        self.assertIn('<span class="badge b-warn">判定 J8</span>', html)
        self.assertIn('<ul class="bullets">', html)


class ObjectionReasonTests(unittest.TestCase):
    """判定ごとに理由を書ける（参照は判定11件それぞれに理由欄があった）。"""

    def test_each_judgment_gets_its_own_reason_field(self):
        html = render_components(
            _plan("decision"),
            title="題",
            content={"decision": {
                "options": ["案A"],
                "judgments": ["判定1", "判定2", "判定3"],
            }},
        )

        self.assertEqual(html.count('class="obj-row"'), 3)
        self.assertEqual(html.count('class="obj-why"'), 3)
        self.assertIn('aria-label="判定1 の理由"', html)
        # 依頼文の組み立てが理由を拾う
        self.assertIn("obj-why", html)
        self.assertIn("この判定は違う。理由＝", html)

    def test_whole_page_still_passes_the_inspector(self):
        html = render_components(
            _plan("overview", "table", "examples", "decision"),
            title="題",
            content={
                "overview": "[[good:完了]] 本文。",
                "table": [{"heading": "表1", "head": ["A"], "rows": [["1"]]}],
                "examples": [{"cards": [{"badge": "J1", "title": "件名", "text": "本文。"}]}],
                "decision": {"options": ["案A"], "judgments": ["判定1"]},
            },
        )

        inspection = inspect_artifact_html(
            html,
            required_components=("overview", "table", "examples", "decision"),
            glossary_entries={},
        )

        self.assertEqual(inspection.errors, ())
        self.assertEqual(inspection.missing_components, ())
        self.assertEqual(inspection.missing_decision_parts, ())


if __name__ == "__main__":
    unittest.main()

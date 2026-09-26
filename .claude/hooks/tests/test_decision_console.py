"""判断コンソールの密度の検査（2026-08-29）。

参照＝artifact 589b3b61 の console 節。実測で fieldset 4つ・選択肢ごとの理由・
4択の段階評価・「推奨をまとめて選択」・判定カードに直付けの異議欄があった。
当時のレンダラーは**1行のラベルだけ**で、なぜその案なのかを書けなかった。
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


RICH = {
    "groups": [
        {
            "legend": "Q1 どれで進めるか",
            "intro": "予測は左に出してある。あなたの裁定だけが確定値になる。",
            "kind": "radio",
            "options": [
                {"label": "案A", "why": "理由＝いちばん安い。ただし取りこぼす",
                 "recommended": True},
                {"label": "案B", "why": "理由＝確実だが時間がかかる"},
            ],
            "note": "⚠️推奨をまとめて選ぶと、こちらの予測がそのまま入る。",
        },
        {
            "legend": "Q2 残る論点（複数選択可）",
            "kind": "checkbox",
            "options": [
                {"label": "論点X", "why": "追加費用0", "badge": "推奨", "tone": "good",
                 "recommended": True},
                {"label": "論点Y", "why": "非推奨。次の作業と混ざる"},
            ],
        },
        {
            "legend": "Q3 個別の裁定",
            "kind": "scale",
            "items": [
                {"title": "1. 主体の断絶", "badge": "予測＝採用", "tone": "acc",
                 "text": "誰が引き受けるかが書かれていない。",
                 "recommended": "採用"},
                {"title": "2. 上限の単位", "badge": "予測＝割引採用", "tone": "warn",
                 "text": "1人あたりか1事故あたりかが書かれていない。",
                 "choices": ["採用", "割引採用", "軽視", "棄却"],
                 "recommended": "割引採用"},
            ],
        },
        {"legend": "自由記述（補足・条件）", "kind": "free",
         "placeholder": "例：この分野で題材を作ってほしい"},
    ],
    "judgments": ["判定1は違う"],
    "note": "⚠️予測と違う裁定こそが較正の材料になる。",
}


class DecisionDensityTests(unittest.TestCase):
    def setUp(self):
        self.html = render_components(
            _plan("decision"), title="判断", content={"decision": RICH}
        )

    def test_multiple_question_groups_each_with_a_legend_and_intro(self):
        self.assertEqual(self.html.count("<fieldset"), 5)  # 4群＋異議
        self.assertIn("Q1 どれで進めるか", self.html)
        self.assertIn("Q3 個別の裁定", self.html)
        self.assertIn('class="intro"', self.html)

    def test_every_option_can_carry_a_reason(self):
        self.assertGreaterEqual(self.html.count('class="why"'), 4)
        self.assertIn("理由＝いちばん安い。ただし取りこぼす", self.html)
        self.assertIn("非推奨。次の作業と混ざる", self.html)

    def test_groups_are_independent(self):
        self.assertIn('name="decision"', self.html)
        self.assertIn('name="decision-2"', self.html)
        self.assertIn('name="decision-3-1"', self.html)
        self.assertIn('name="decision-3-2"', self.html)

    def test_scale_rows_have_four_choices_and_a_prediction_badge(self):
        self.assertEqual(self.html.count('class="scale-row"'), 2)
        self.assertEqual(self.html.count('class="pick"'), 8)
        self.assertIn("予測＝採用", self.html)
        self.assertIn("誰が引き受けるかが書かれていない。", self.html)

    def test_recommendations_are_marked_for_the_bulk_button(self):
        self.assertGreaterEqual(self.html.count('data-rec="1"'), 4)
        self.assertIn('id="recommend-decision"', self.html)
        self.assertIn("dataset.rec", self.html)

    def test_free_text_group_becomes_the_objection_textarea(self):
        self.assertIn('id="decision-objection"', self.html)
        self.assertIn("例：この分野で題材を作ってほしい", self.html)

    def test_notes_are_shown_for_group_and_page(self):
        self.assertIn("推奨をまとめて選ぶと", self.html)
        self.assertIn("予測と違う裁定こそが", self.html)

    def test_all_required_decision_parts_are_present(self):
        inspection = inspect_artifact_html(
            self.html, required_components=("decision",), glossary_entries={}
        )

        self.assertEqual(inspection.missing_decision_parts, ())
        self.assertEqual(inspection.errors, ())


class CardObjectionTests(unittest.TestCase):
    """判定カードに異議の口を直接付けられる（参照頁は11件そうしていた）。"""

    def test_card_carries_its_own_objection_row(self):
        html = render_components(
            _plan("examples"),
            title="題",
            content={"examples": [{"cards": [
                {"badge": "判定 J4", "tone": "good", "title": "本命の空白を捕捉した",
                 "right": "要較正", "right_tone": "warn",
                 "text": "baselineで素通りした仮定を捕捉に変えた。",
                 "objection": "静学前提の新規捕捉（J4）"},
            ]}]},
        )

        self.assertIn('class="obj-row"', html)
        self.assertIn('data-label="静学前提の新規捕捉（J4）"', html)
        self.assertIn('class="obj-why"', html)
        self.assertIn('class="scores"', html)
        self.assertIn("要較正", html)


class BackwardCompatibilityTests(unittest.TestCase):
    """これまでの書き方が壊れていないこと。"""

    def test_plain_option_list_still_works(self):
        html = render_components(
            _plan("decision"), title="題", content={"decision": ["案A", "案B"]}
        )

        self.assertEqual(html.count('name="decision"'), 2)
        self.assertIn('id="decision-prompt"', html)

    def test_multi_and_numbers_still_work(self):
        html = render_components(
            _plan("decision"),
            title="題",
            content={"decision": {"multi": True, "options": ["案A"],
                                  "numbers": [{"label": "件数", "unit": "件"}]}},
        )

        self.assertIn('type="checkbox" name="decision"', html)
        self.assertIn('type="number" name="decision-number"', html)


if __name__ == "__main__":
    unittest.main()

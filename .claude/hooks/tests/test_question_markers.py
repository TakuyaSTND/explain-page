"""節の見出しの「→ Q1」と、問いの錨（2026-10-09）。

読む人が「この節はどの問いに関わるか」を見出しから辿れるようにする。
  - 定義JSONの sections[i].asks（問いの番号の配列）が、見出しの直後の飛び先 `#q-N` になる。
  - 選ぶ行が1つ以上ある群（自由記述でない）だけが問いで、`<fieldset id="q-N">` と
    `<legend><span class="q-no">QN</span>…` を持つ。番号は頁の先頭から通し。
  - 番号は回答文の Q 番号（DECISION_SCRIPT の questions()）と同じ規則で数える。
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
from visual.render_components import _question_numbers, render_components
from visual.section_labels import check_sections

DECISION = {
    "groups": [
        {
            "legend": "配置はどれにするか",
            "kind": "radio",
            "options": [{"label": "案A", "recommended": True}, {"label": "案B"}],
        },
        {"legend": "空の群", "kind": "scale", "items": []},
        {
            "legend": "足すもの",
            "kind": "checkbox",
            "options": ["利点の欄", "補足の欄"],
        },
        {"legend": "自由に書く", "kind": "free", "placeholder": "自由に"},
    ],
    "judgments": ["判定1は違う"],
}


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


def _page(asks_first=None, asks_second=None, *, with_toc: bool = False) -> str:
    first: dict = {"component": "walkthrough", "label": "背景", "num": "壱", "content": "背景：本文"}
    second: dict = {"component": "examples", "label": "実例", "content": "例：本文"}
    if asks_first is not None:
        first["asks"] = asks_first
    if asks_second is not None:
        second["asks"] = asks_second
    content: dict = {
        "sections": [
            first,
            second,
            {"component": "decision", "label": "選ぶこと", "content": DECISION},
        ]
    }
    if with_toc:
        content["rail"] = [{"heading": "目次", "toc": True}]
    return render_components(
        _plan("walkthrough", "examples", "decision"), title="問いの印", content=content
    )


def _h2(html: str, heading: str) -> str:
    """見出しの文字を含む h2 を1つ切り出す（正規表現を使わない）。"""
    for chunk in html.split("<h2>")[1:]:
        text = chunk.split("</h2>", 1)[0]
        if heading in text:
            return text
    raise AssertionError("h2 が見つからない: " + heading)


class SectionRefTests(unittest.TestCase):
    def test_asks_become_links_right_after_the_heading_text(self):
        html = _page(asks_first=[1, "Q2"])

        h2 = _h2(html, "背景")
        self.assertTrue(h2.startswith('<span class="sec-no">壱</span>背景'), h2)
        self.assertIn('<a class="q-ref" href="#q-1" aria-label="Q1 へ移動">→ Q1</a>', h2)
        self.assertIn('<a class="q-ref" href="#q-2" aria-label="Q2 へ移動">→ Q2</a>', h2)
        self.assertLess(h2.index("→ Q1"), h2.index("→ Q2"))
        # 見出しの文字のあとに並ぶ（番号の札や見出しの前には出ない）。
        self.assertLess(h2.index("背景"), h2.index("→ Q1"))

    def test_sections_without_asks_have_no_link(self):
        html = _page(asks_first=[1])

        self.assertNotIn("q-ref", _h2(html, "実例"))
        self.assertNotIn("q-ref", _h2(html, "選ぶこと"))

    def test_each_section_can_point_to_its_own_questions(self):
        html = _page(asks_first=[1], asks_second=["q2"])

        self.assertIn('href="#q-1"', _h2(html, "背景"))
        self.assertNotIn('href="#q-2"', _h2(html, "背景"))
        self.assertIn('href="#q-2"', _h2(html, "実例"))

    def test_unreadable_values_are_dropped_and_duplicates_are_merged(self):
        html = _page(asks_first=["x", 0, -1, True, None, 1.5, "Q", "1", 1, "Q1", " q2 "])

        h2 = _h2(html, "背景")
        self.assertEqual(h2.count('class="q-ref"'), 2)
        self.assertIn("→ Q1", h2)
        self.assertIn("→ Q2", h2)

    def test_numbers_are_read_the_same_way_in_every_accepted_form(self):
        self.assertEqual(_question_numbers([1, "1", "Q1", "q1"]), [1])
        self.assertEqual(_question_numbers(["Q3", 1, "2"]), [3, 1, 2])
        self.assertEqual(_question_numbers("x"), [])
        self.assertEqual(_question_numbers(None), [])
        self.assertEqual(_question_numbers({"a": 1}), [])
        self.assertEqual(_question_numbers([]), [])

    def test_a_link_to_a_question_that_does_not_exist_still_builds(self):
        # 存在しない番号の知らせは組み立て道具の側（頁の警告）の仕事。ここでは頁を壊さない。
        html = _page(asks_first=[9])

        self.assertIn('href="#q-9"', html)
        self.assertNotIn('id="q-9"', html)

    def test_asks_given_outside_the_sections_list_are_ignored(self):
        html = render_components(
            _plan("decision"),
            title="一覧なし",
            content={"decision": DECISION, "asks": [1]},
        )

        self.assertNotIn('class="q-ref"', html)

    def test_the_toc_does_not_carry_the_arrow(self):
        html = _page(asks_first=[1], asks_second=[2], with_toc=True)

        toc = html.split('<nav class="toc">', 1)[1].split("</nav>", 1)[0]
        self.assertIn("背景", toc)
        self.assertNotIn("→", toc)
        self.assertNotIn("q-ref", toc)

    def test_check_sections_ignores_asks(self):
        sections = [
            {"component": "walkthrough", "label": "背景", "content": "背景：本文", "asks": [1, "x", 0]},
            {"component": "decision", "label": "選ぶこと", "content": DECISION, "asks": "Q1"},
        ]

        self.assertEqual(check_sections(sections), [])

    def test_css_has_the_link_the_badge_and_the_target_highlight(self):
        html = _page(asks_first=[1])

        style = html.split("<style>", 1)[1].split("</style>", 1)[0]
        self.assertIn(".q-ref{", style)
        self.assertIn(".q-no{", style)
        self.assertIn("fieldset:target{", style)
        self.assertIn('fieldset[id^="q-"]{scroll-margin-top', style)


class QuestionAnchorTests(unittest.TestCase):
    def test_answerable_groups_get_a_through_number_and_a_badge(self):
        html = _page()

        self.assertIn('<fieldset id="q-1"><legend><span class="q-no">Q1</span>配置はどれにするか</legend>', html)
        # 選ぶ行が空の群は問いに数えない＝次の群が Q2 になる（回答文の Q 番号と同じ）。
        self.assertIn('<fieldset id="q-2"><legend><span class="q-no">Q2</span>足すもの</legend>', html)
        self.assertNotIn('id="q-3"', html)
        self.assertNotIn("Q3", html.split("</style>", 1)[1].split("<script>", 1)[0])

    def test_free_text_empty_and_objection_groups_have_no_anchor(self):
        html = _page()

        self.assertIn("<fieldset><legend>空の群</legend>", html)
        self.assertIn("<fieldset><legend>自由に書く</legend>", html)
        self.assertIn('<fieldset class="objections"><legend>判定への異議</legend>', html)
        self.assertEqual(html.count('class="q-no"'), 2)

    def test_numbers_continue_across_two_decision_sections(self):
        first = {"groups": [{"legend": "最初の問い", "kind": "radio", "options": ["甲", "乙"]}]}
        second = {"groups": [{"legend": "あとの問い", "kind": "number", "options": [{"label": "回数"}]}]}
        html = render_components(
            _plan("decision"),
            title="二つの節",
            content={
                "sections": [
                    {"component": "decision", "label": "選ぶこと その1", "content": first},
                    {"component": "decision", "label": "選ぶこと その2", "content": second},
                ]
            },
        )

        self.assertEqual(html.count('id="q-1"'), 1)
        self.assertEqual(html.count('id="q-2"'), 1)
        self.assertLess(html.index('id="q-1"'), html.index('id="q-2"'))

    def test_the_old_option_style_numbers_its_groups_too(self):
        html = render_components(
            _plan("decision"),
            title="旧い書き方",
            content={
                "decision": {
                    "options": ["案A"],
                    "numbers": [{"label": "何日で", "unit": "日"}],
                }
            },
        )

        self.assertIn('<span class="q-no">Q1</span>選択肢', html)
        self.assertIn('<span class="q-no">Q2</span>数を入れる', html)


class GateTests(unittest.TestCase):
    def test_the_inspector_accepts_a_page_with_markers(self):
        html = _page(asks_first=[1, 2], asks_second=["Q2"], with_toc=True)

        inspection = inspect_artifact_html(
            html,
            required_components=("walkthrough", "examples", "decision"),
            glossary_entries={},
        )

        self.assertEqual(inspection.errors, ())
        self.assertEqual(inspection.missing_decision_parts, ())

    def test_internal_links_are_not_external_dependencies(self):
        html = _page(asks_first=[1, 2])
        inspection = inspect_artifact_html(
            html,
            required_components=("walkthrough", "examples", "decision"),
            glossary_entries={},
        )

        self.assertNotIn("external", " ".join(inspection.errors))
        self.assertEqual(inspection.errors, ())


if __name__ == "__main__":
    unittest.main()

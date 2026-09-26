"""側柱の目次の検査（2026-08-30 ユーザー選択）。

⚠️目次は**節の見出しから自動で組む**＝手で書かせない。手で書けるようにすると、
   節を足したときに目次だけが古くなる（見出しと中身のずれと同じ型の事故）。
   ∴ここで固定するのは「目次の文字が節の見出しと同じであること」と
   「飛び先が実在する節を指していること」の2つ。
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


def _ids(html: str, needle: str) -> list[str]:
    """出てきた順に属性値を拾う。⚠️正規表現を使わず索引で切る（この repo の決まり）。"""
    out = []
    i = 0
    while True:
        i = html.find(needle, i)
        if i < 0:
            return out
        j = html.find('"', i + len(needle))
        out.append(html[i + len(needle):j])
        i = j


class TocTests(unittest.TestCase):
    def setUp(self):
        self.html = render_components(
            _plan("summary", "walkthrough", "table", "evidence"),
            title="題",
            content={
                "sections": [
                    {"component": "summary", "num": "序", "label": "この頁の見取り図",
                     "content": "Goal：目的。"},
                    {"component": "walkthrough", "num": "壱", "label": "背景の説明",
                     "content": "見出し：本文"},
                    {"component": "table", "num": "弐", "label": "測った数",
                     "content": {"head": ["A"], "rows": [["1"]]}},
                ],
                "evidence": "実測：内容｜出所",
                "rail": [{"heading": "目次", "toc": True}],
            },
        )

    def test_every_section_has_a_landing_spot(self):
        anchors = _ids(self.html, 'data-component="walkthrough" id="')
        self.assertEqual(anchors, ["sec-2"])

    def test_the_toc_lists_every_section_including_the_auto_appended_one(self):
        links = _ids(self.html, '<li><a href="#')
        # ⚠️節の一覧に書き忘れた evidence も末尾に足されるので、目次にも出る。
        self.assertEqual(links, ["sec-1", "sec-2", "sec-3", "sec-4"])

    def test_the_toc_uses_the_same_words_as_the_headings(self):
        toc = self.html[self.html.index('<nav class="toc">'):]
        toc = toc[: toc.index("</nav>")]
        for label in ("この頁の見取り図", "背景の説明", "測った数"):
            self.assertIn(label, toc)
            self.assertIn(label, self.html[: self.html.index('<aside class="rail">')])

    def test_the_toc_carries_the_section_numbers(self):
        self.assertIn('<span class="toc-no">序</span>', self.html)
        self.assertIn('<span class="toc-no">壱</span>', self.html)
        self.assertIn('<span class="toc-no">弐</span>', self.html)

    def test_every_link_points_at_a_real_section(self):
        for anchor in _ids(self.html, '<li><a href="#'):
            self.assertIn('id="%s"' % anchor, self.html)

    def test_the_toc_lives_in_the_rail_and_is_not_a_section(self):
        rail = self.html[self.html.index('<aside class="rail">'):]
        rail = rail[: rail.index("</aside>")]
        self.assertIn('<nav class="toc">', rail)
        self.assertNotIn("data-component", rail)

    def test_the_page_still_passes_the_inspector(self):
        inspection = inspect_artifact_html(
            self.html,
            required_components=("summary", "walkthrough", "table", "evidence"),
            glossary_entries={},
        )

        self.assertEqual(inspection.errors, ())
        self.assertEqual(inspection.missing_components, ())

    def test_no_extra_script_is_added(self):
        # ⚠️検査器は承認済みの1本以外の script を拒む。目次は素の錨だけで作る。
        self.assertEqual(self.html.count("<script>"), 1)


class WithoutTocTests(unittest.TestCase):
    def test_sections_still_get_ids_even_without_a_toc(self):
        html = render_components(
            _plan("walkthrough"), title="題", content={"walkthrough": "見出し：本文"}
        )

        self.assertIn('data-component="walkthrough" id="sec-1"', html)
        self.assertNotIn('<nav class="toc">', html)

    def test_a_rail_without_the_toc_flag_has_no_index(self):
        html = render_components(
            _plan("walkthrough"),
            title="題",
            content={"walkthrough": "見出し：本文", "rail": [{"heading": "要点", "text": "本文"}]},
        )

        self.assertIn('<aside class="rail">', html)
        self.assertNotIn('<nav class="toc">', html)


if __name__ == "__main__":
    unittest.main()

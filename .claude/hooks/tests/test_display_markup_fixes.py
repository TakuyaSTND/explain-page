"""頁の見え方の2つの直しの試験（2026-10-08・利用者の指摘「この作業を終わらせてから」）。

1. 用語の説明に Markdown の ** と ` が出ていた＝吹き出し（data-d・aria-label）・側柱の用語リスト・
   図の箱の吹き出しに、用語集の文がそのまま入っていた（試問の読み手が見つけた）。
2. 狭い画面で根拠欄の行が用語の語のところで割れていた＝セル（td）を格子（grid）にしていたので、
   文と用語の語（span）がばらばらの升に入った。見出しを上・中身を下に積む形にした。
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

HOOKS_DIR = Path(__file__).resolve().parents[1]
if str(HOOKS_DIR) not in sys.path:
    sys.path.insert(0, str(HOOKS_DIR))

from visual.contracts import ExplanationPlan  # noqa: E402
from visual.glossary import GlossaryEntry  # noqa: E402
from visual.render_components import render_components  # noqa: E402

BT = chr(96)


def _plan(*components):
    return ExplanationPlan(
        audience="project_novice",
        depth="deep",
        components=tuple(components),
        reason_codes=("project_novice_default",),
        provisional=False,
        should_continue=False,
        delivery="local_html",
        publish_policy="never",
    )


def _entries():
    description = "毎回の依頼で**組み直して**渡す文。置き場は " + BT + "%TEMP%" + BT + " の下"
    return {"指示文": GlossaryEntry(term="指示文", description=description, provenance="test")}


def _body(html):
    start = html.find("<body>")
    return html[start:] if start >= 0 else html


class GlossaryMarkupTests(unittest.TestCase):
    def setUp(self):
        content = {
            "sections": [
                {"component": "examples", "label": "例", "content": [
                    {"text": "指示文を読む。指示文は毎回変わる。"},
                    {"diagram": {"nodes": [{"id": "a", "title": "指示文", "text": "毎回"}], "edges": []}},
                ]},
            ],
            "rail": [{"heading": "この頁の用語", "glossary": True}],
        }
        self.html = _body(render_components(
            _plan("examples"), title="題", content=content, glossary_entries=_entries()
        ))

    def test_tooltip_has_no_markdown_markers(self):
        self.assertIn('data-d="毎回の依頼で組み直して渡す文。置き場は %TEMP% の下"', self.html)
        self.assertIn('aria-label="指示文：毎回の依頼で組み直して渡す文。置き場は %TEMP% の下"', self.html)

    def test_rail_glossary_has_no_markdown_markers(self):
        start = self.html.find('<dl class="gl">')
        self.assertGreaterEqual(start, 0)
        rail = self.html[start:self.html.find("</dl>", start)]
        self.assertIn("<dd>毎回の依頼で組み直して渡す文。置き場は %TEMP% の下</dd>", rail)

    def test_no_bold_markers_leak_anywhere_in_the_body(self):
        script = self.html.find("<script>")
        visible = self.html[:script] if script >= 0 else self.html
        self.assertNotIn("**組み直して**", visible)
        self.assertNotIn(BT + "%TEMP%" + BT, visible)


class EvidenceCellLayoutTests(unittest.TestCase):
    def test_narrow_evidence_cells_stack_instead_of_grid(self):
        html = render_components(_plan("evidence"), title="題", content={
            "evidence": "実測：指示文を読んだ｜手元の記録",
        }, glossary_entries=_entries())
        self.assertIn('section[data-component="evidence"] td{display:block;', html)
        self.assertNotIn("grid-template-columns:minmax(7rem,35%) minmax(0,1fr)", html)
        self.assertIn(
            'section[data-component="evidence"] td::before{content:attr(data-label);display:block;', html
        )


if __name__ == "__main__":
    unittest.main()

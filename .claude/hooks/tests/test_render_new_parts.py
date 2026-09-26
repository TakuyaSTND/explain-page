"""担当Aが足した7部品の回帰検査（2026-09-08）。

③側柱の用語リスト自動生成／④コード差分／⑤図の枠（num・source）／
⑥数値の図の配線（chart、担当Bの render_chart が無い間は表に落ちる）／
⑦引用の訳文と出所／⑧印刷様式／⑨数式とコピー釦の汎用化（formula、
担当Cの tex_to_mathml が無い間は code に落ちる）。

⚠️charts.py・formula.py は並行作業中で存在しない前提＝フォールバック経路を固定する。
   SVG／MathMLが来た場合の経路は、モジュール参照を一時的に差し替えて確かめる。
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

HOOKS_DIR = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = HOOKS_DIR.parent / "scripts"
for entry in (str(HOOKS_DIR), str(SCRIPTS_DIR)):
    if entry not in sys.path:
        sys.path.insert(0, entry)

import visual.render_components as rc
from visual.artifact_inspection import inspect_artifact_html
from visual.contracts import ExplanationPlan
from visual.glossary import GlossaryEntry
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


class DiffBlockTests(unittest.TestCase):
    """④コード差分。"""

    def _html(self, diff):
        return render_components(
            _plan("details"),
            title="差分",
            content={"details": [{"summary": "変更", "diff": diff}]},
        )

    def test_add_and_delete_lines_get_their_own_span(self):
        html = self._html("-旧い行" + NL + "+新しい行" + NL + " そのまま")

        self.assertIn('<pre class="log diff">', html)
        self.assertIn('<span class="del">-旧い行</span>', html)
        self.assertIn('<span class="add">+新しい行</span>', html)
        self.assertIn('<span class="ctx"> そのまま</span>', html)

    def test_a_list_of_lines_is_accepted(self):
        html = self._html(["+A", "-B"])

        self.assertIn('<span class="add">+A</span>', html)
        self.assertIn('<span class="del">-B</span>', html)

    def test_markup_is_escaped_not_decorated(self):
        html = self._html("+<script>bad()</script>")

        self.assertIn("&lt;script&gt;", html)
        self.assertNotIn("<script>bad()", html)

    def test_a_copy_button_is_attached(self):
        html = self._html("+A" + NL + "-B")

        self.assertIn('class="copy-btn" data-copy="+A', html)

    def test_blank_diff_renders_nothing(self):
        html = self._html("")

        self.assertNotIn('class="log diff"', html)

    def test_page_with_diff_still_passes_the_inspector(self):
        html = self._html("+A" + NL + "-B")

        inspection = inspect_artifact_html(
            html, required_components=("details",), glossary_entries={}
        )
        self.assertEqual(inspection.errors, ())


class DiagramCaptionTests(unittest.TestCase):
    """⑤図の枠＝num・source を足した figcaption 相当の1行。"""

    def test_without_num_or_source_behaves_as_before(self):
        html = render_components(
            _plan("diagram"),
            title="図",
            content={"diagram": {
                "nodes": [{"id": "a", "label": "箱"}],
                "caption": "ただの補足",
            }},
        )

        self.assertIn('<p class="cap">ただの補足</p>', html)

    def test_num_and_source_are_combined_into_one_caption_line(self):
        html = render_components(
            _plan("diagram"),
            title="図",
            content={"diagram": {
                "nodes": [{"id": "a", "label": "箱"}],
                "caption": "左から右へ読む",
                "num": "図1",
                "source": "path/to/data.csv",
            }},
        )

        self.assertIn(
            '<p class="cap">図1｜左から右へ読む｜出所：path/to/data.csv</p>', html
        )

    def test_source_alone_still_shows_even_without_a_caption(self):
        html = render_components(
            _plan("diagram"),
            title="図",
            content={"diagram": {
                "nodes": [{"id": "a", "label": "箱"}],
                "num": "図2",
            }},
        )

        self.assertIn('<p class="cap">図2</p>', html)


class ChartBlockTests(unittest.TestCase):
    """⑥数値の図の配線。担当Bの render_chart が無い間は表に落ちる。"""

    def setUp(self):
        self._original = rc.render_chart

    def tearDown(self):
        rc.render_chart = self._original

    def _spec(self):
        return {
            "kind": "line",
            "title": "件数",
            "labels": ["4月", "5月"],
            "series": [{"name": "検品", "values": [3, 7]}],
            "unit": "件",
            "source": "path/to/log.json",
        }

    def test_falls_back_to_a_table_when_the_module_is_absent(self):
        rc.render_chart = None
        html = render_components(
            _plan("details"),
            title="図",
            content={"details": [{"summary": "推移", "chart": self._spec()}]},
        )

        self.assertIn('class="chart-wrap chart-fallback"', html)
        self.assertIn("<table>", html)
        self.assertIn("<th>件数</th>", html)
        self.assertIn("4月", html)
        self.assertIn("出所：path/to/log.json", html)

    def test_falls_back_when_the_module_raises(self):
        def boom(spec):
            raise ValueError("非数値")

        rc.render_chart = boom
        html = render_components(
            _plan("details"),
            title="図",
            content={"details": [{"summary": "推移", "chart": self._spec()}]},
        )

        self.assertIn("chart-fallback", html)
        self.assertNotIn("<svg", html)

    def test_uses_the_svg_when_the_module_returns_one(self):
        rc.render_chart = lambda spec: '<svg class="dia"><title>件数</title></svg>'
        html = render_components(
            _plan("details"),
            title="図",
            content={"details": [{"summary": "推移", "chart": self._spec()}]},
        )

        self.assertIn('<div class="dia-wrap chart-wrap">', html)
        self.assertIn("<svg", html)

    def test_a_dangerous_svg_is_rejected_in_favour_of_the_table(self):
        rc.render_chart = lambda spec: '<svg onload="bad()"><script>x</script></svg>'
        html = render_components(
            _plan("details"),
            title="図",
            content={"details": [{"summary": "推移", "chart": self._spec()}]},
        )

        self.assertNotIn("<svg", html)
        self.assertNotIn("onload", html)
        self.assertIn("chart-fallback", html)


class FormulaBlockTests(unittest.TestCase):
    """⑨数式。担当Cの tex_to_mathml が無い間は code に落ちる。"""

    def setUp(self):
        self._original = rc.tex_to_mathml

    def tearDown(self):
        rc.tex_to_mathml = self._original

    def test_falls_back_to_code_when_the_module_is_absent(self):
        rc.tex_to_mathml = None
        html = render_components(
            _plan("details"),
            title="式",
            content={"details": [{"summary": "式", "formula": {
                "tex": "x^2+y^2=z^2", "reading": "三平方の定理",
            }}]},
        )

        self.assertIn('<div class="formula">', html)
        self.assertIn("<code>x^2+y^2=z^2</code>", html)
        self.assertIn('<p class="formula-reading">三平方の定理</p>', html)

    def test_falls_back_when_the_module_raises_or_returns_none(self):
        rc.tex_to_mathml = lambda tex: None
        html = render_components(
            _plan("details"),
            title="式",
            content={"details": [{"summary": "式", "formula": {"tex": "a+b"}}]},
        )

        self.assertIn("<code>a+b</code>", html)

    def test_uses_the_mathml_when_the_module_returns_one(self):
        rc.tex_to_mathml = lambda tex: "<math><mi>x</mi></math>"
        html = render_components(
            _plan("details"),
            title="式",
            content={"details": [{"summary": "式", "formula": {"tex": "x"}}]},
        )

        self.assertIn("<math><mi>x</mi></math>", html)
        self.assertNotIn("<code>x</code>", html)

    def test_a_copy_button_is_attached_with_the_original_tex(self):
        rc.tex_to_mathml = None
        html = render_components(
            _plan("details"),
            title="式",
            content={"details": [{"summary": "式", "formula": {"tex": "a<b"}}]},
        )

        self.assertIn('class="copy-btn" data-copy="a&lt;b"', html)

    def test_empty_tex_renders_nothing(self):
        html = render_components(
            _plan("details"),
            title="式",
            content={"details": [{"summary": "式", "formula": {"tex": ""}}]},
        )

        self.assertNotIn('class="formula"', html)


class QuoteTranslationTests(unittest.TestCase):
    """⑦引用の訳文と出所。"""

    def test_string_form_is_unchanged(self):
        html = render_components(
            _plan("details"),
            title="引用",
            content={"details": [{"summary": "原文", "quote": "そのまま。"}]},
        )

        self.assertIn("<blockquote>そのまま。</blockquote>", html)

    def test_dict_form_shows_original_and_translation_and_source(self):
        html = render_components(
            _plan("details"),
            title="引用",
            content={"details": [{"summary": "原文", "quote": {
                "original": "Hello, world.",
                "ja": "やあ、世界。",
                "source": "path/to/book.txt",
            }}]},
        )

        self.assertIn('<p class="q-original">Hello, world.</p>', html)
        self.assertIn('<p class="q-ja">やあ、世界。</p>', html)
        self.assertIn('<footer class="q-source">path/to/book.txt</footer>', html)


class RailGlossaryTests(unittest.TestCase):
    """③側柱の用語リスト自動生成。"""

    def _entries(self):
        return {
            "検品証": GlossaryEntry(
                term="検品証", description="機械が調べて残す記録", provenance="project"
            ),
            "受理": GlossaryEntry(
                term="受理", description="通ったものとして扱うこと", provenance="project"
            ),
        }

    def test_a_term_used_twice_in_the_body_is_listed(self):
        html = render_components(
            _plan("walkthrough"),
            title="題",
            content={
                "walkthrough": "背景：検品証を確認した。" + NL + "結果：検品証は揃っていた。",
                "rail": [{"heading": "用語", "glossary": True}],
            },
            glossary_entries=self._entries(),
        )

        rail = html[html.index('<aside class="rail">'): html.index("</aside>")]
        self.assertIn('<p class="rail-head">用語</p>', rail)
        self.assertIn("<dl class=\"gl\">", rail)
        self.assertIn("<dt>検品証</dt><dd>機械が調べて残す記録</dd>", rail)

    def test_a_term_used_only_once_is_not_listed(self):
        html = render_components(
            _plan("walkthrough"),
            title="題",
            content={
                "walkthrough": "背景：受理された。",
                "rail": [{"heading": "用語", "glossary": True}],
            },
            glossary_entries=self._entries(),
        )

        # 1語も無いので側柱そのものが出ない（見出しごと消える）。
        self.assertNotIn('<aside class="rail">', html)

    def test_glossary_block_does_not_suppress_other_rail_items(self):
        html = render_components(
            _plan("walkthrough"),
            title="題",
            content={
                "walkthrough": "背景：受理された（一度だけ）。",
                "rail": [
                    {"heading": "用語", "glossary": True},
                    {"heading": "要点", "text": "側柱は生きている。"},
                ],
            },
            glossary_entries=self._entries(),
        )

        self.assertIn('<aside class="rail">', html)
        self.assertIn('<p class="rail-head">要点</p>', html)
        self.assertNotIn('<p class="rail-head">用語</p>', html)

    def test_the_rail_glossary_is_not_a_section(self):
        html = render_components(
            _plan("walkthrough"),
            title="題",
            content={
                "walkthrough": "背景：検品証を確認した。" + NL + "結果：検品証は揃っていた。",
                "rail": [{"heading": "用語", "glossary": True}],
            },
            glossary_entries=self._entries(),
        )

        rail = html[html.index('<aside class="rail">'): html.index("</aside>")]
        self.assertNotIn("data-component", rail)
        self.assertNotIn("<section", rail)

    def test_page_still_passes_the_inspector(self):
        html = render_components(
            _plan("walkthrough"),
            title="題",
            content={
                "walkthrough": "背景：検品証を確認した。" + NL + "結果：検品証は揃っていた。",
                "rail": [{"heading": "用語", "glossary": True}],
            },
            glossary_entries=self._entries(),
        )

        inspection = inspect_artifact_html(
            html, required_components=("walkthrough",), glossary_entries=self._entries()
        )
        self.assertEqual(inspection.errors, ())
        self.assertEqual(inspection.missing_components, ())


class PrintStyleTests(unittest.TestCase):
    """⑧印刷様式。"""

    def setUp(self):
        self.html = render_components(
            _plan("overview"), title="題", content={"overview": "本文"}
        )

    def test_a4_and_margin(self):
        self.assertIn("@media print", self.html)
        self.assertIn("@page{size:A4;margin:15mm}", self.html)

    def test_theme_and_copy_controls_are_hidden(self):
        self.assertIn(
            '#theme-toggle,.copy-btn,#copy-decision{display:none !important}', self.html
        )

    def test_the_rail_is_forced_static_after_the_body(self):
        self.assertIn('.wrap[data-layout="rail"]{display:block}', self.html)
        self.assertIn(
            '.wrap[data-layout="rail"]>.rail{order:0;position:static', self.html
        )

    def test_blocks_do_not_split_across_pages(self):
        self.assertIn("break-inside:avoid", self.html)

    def test_tooltip_balloons_are_hidden(self):
        self.assertIn('.t::after{display:none !important}', self.html)

    def test_no_forbidden_css_constructs(self):
        # ⚠️検品器は @import と url(…) を「外部依存」として拒む。
        self.assertNotIn("@import", self.html)
        self.assertNotIn("url(", self.html)


class GenericCopyButtonScriptTests(unittest.TestCase):
    """⑨コピー釦の汎用化＝末尾scriptは相変わらず1本だけ。"""

    def test_still_exactly_one_inline_script(self):
        html = render_components(
            _plan("details"),
            title="題",
            content={"details": [
                {"summary": "式", "formula": {"tex": "a"}},
                {"summary": "差分", "diff": "+a"},
                {"summary": "ログ", "log": "テスト"},
            ]},
        )

        self.assertEqual(html.count("<script>"), 1)
        self.assertIn("data-copy", html)
        self.assertIn("querySelectorAll('[data-copy]')", html)

    def test_the_script_has_no_network_calls(self):
        html = render_components(_plan("overview"), title="題", content={"overview": "本文"})

        for banned in ("fetch(", "XMLHttpRequest", "WebSocket", "EventSource", "sendBeacon"):
            self.assertNotIn(banned, html)


if __name__ == "__main__":
    unittest.main()

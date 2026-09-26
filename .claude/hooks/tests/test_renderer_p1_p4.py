"""レンダラーに足したP1〜P4の回帰検査（2026-08-29 ユーザー裁定）。

P1＝一般の表とログ／P2＝左右に並べる図／P3＝明暗の切替と見出しのホバー／
P4＝折りたたみの中に表・ログ・箇条書きを入れられるようにする。

⚠️どれも「これまで書けなかったものが書ける」という追加であり、
   これまでの書き方を壊していないことも同時に確かめる。
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


class TableComponentTests(unittest.TestCase):
    """P1：一般の表。見出し行・桁揃え・補足。"""

    def test_string_form_builds_a_table_with_header_and_caption(self):
        html = render_components(
            _plan("table"),
            title="比較",
            content={"table": NL.join([
                "項目｜レンダラー版｜手書き版",
                "検品｜合格｜不合格",
                "大きさ｜26144｜38983",
                "補足：同じ検査器にかけた結果",
            ])},
        )

        self.assertIn('data-component="table"', html)
        self.assertIn("<th>項目</th>", html)
        self.assertIn("<th>レンダラー版</th>", html)
        self.assertIn('<caption>同じ検査器にかけた結果</caption>', html)
        # 数値だけのセルは桁を揃える
        self.assertIn('class="num">26144<', html)
        # 文字のセルには付けない
        self.assertIn('data-label="レンダラー版">合格<', html)

    def test_mapping_form_is_accepted(self):
        html = render_components(
            _plan("table"),
            title="比較",
            content={"table": {
                "caption": "辞書でも書ける",
                "head": ["名前", "件数"],
                "rows": [["テスト", "189"]],
            }},
        )

        self.assertIn("<th>名前</th>", html)
        self.assertIn('class="num">189<', html)
        self.assertIn("辞書でも書ける", html)

    def test_ascii_pipe_also_works(self):
        html = render_components(
            _plan("table"),
            title="比較",
            content={"table": "A|B" + NL + "1|2"},
        )

        self.assertIn("<th>A</th>", html)
        self.assertIn("<th>B</th>", html)

    def test_short_rows_are_padded_so_columns_do_not_shift(self):
        html = render_components(
            _plan("table"),
            title="比較",
            content={"table": "A｜B｜C" + NL + "1｜2"},
        )

        self.assertEqual(html.count("<td"), 3)


class LogComponentTests(unittest.TestCase):
    """P1：ログをそのまま貼る。"""

    def test_log_keeps_newlines_and_escapes_markup(self):
        html = render_components(
            _plan("log"),
            title="記録",
            content={"log": "テスト：189 passed" + NL + "<script>bad</script>"},
        )

        self.assertIn('<pre class="log">', html)
        self.assertIn("&lt;script&gt;", html)
        self.assertNotIn("<script>bad", html)
        self.assertIn("<h3>", html)

    def test_log_accepts_a_list(self):
        html = render_components(
            _plan("log"),
            title="記録",
            content={"log": ["前：174 passed", "後：189 passed"]},
        )

        self.assertEqual(html.count('<pre class="log">'), 2)


class VisualColumnsTests(unittest.TestCase):
    """P2：縦棒で区切った行は左右に並べる。"""

    def test_pipe_line_becomes_columns(self):
        html = render_components(
            _plan("visual"),
            title="図",
            content={"visual": "変更前｜変更後"},
        )

        self.assertIn('class="flow-cols"', html)
        self.assertEqual(html.count('class="flow-cell"'), 2)

    def test_plain_flow_still_works(self):
        html = render_components(
            _plan("visual"),
            title="図",
            content={"visual": "依頼" + NL + "↓" + NL + "結果"},
        )

        self.assertEqual(html.count('class="flow-step"'), 2)
        self.assertIn('class="flow-arrow"', html)
        self.assertNotIn('class="flow-cols"', html)


class ThemeToggleTests(unittest.TestCase):
    """P3：明暗を手で切り替えられるようにする。"""

    def test_toggle_button_and_handler_exist(self):
        html = render_components(_plan("overview"), title="題", content={"overview": "本文"})

        self.assertIn('id="theme-toggle"', html)
        self.assertIn("data-theme", html)
        self.assertIn("setAttribute('data-theme'", html)

    def test_toggle_uses_no_inline_event_attribute(self):
        # 検査器は on* 属性を禁じている。addEventListener で付けること。
        html = render_components(_plan("overview"), title="題", content={"overview": "本文"})

        self.assertNotIn("onclick=", html)
        self.assertIn("addEventListener('click'", html)


class HeadingTooltipTests(unittest.TestCase):
    """P3：見出しにも用語ホバーを付ける。"""

    def _entries(self):
        return {"コミット": GlossaryEntry(
            term="コミット",
            description="変更を履歴として確定させること",
            provenance="project",
        )}

    def test_details_summary_gets_a_tooltip(self):
        html = render_components(
            _plan("details"),
            title="詳細",
            content={"details": "コミット：まだしていない"},
            glossary_entries=self._entries(),
        )

        self.assertIn('<summary><span class="t"', html)

    def test_examples_heading_gets_a_tooltip(self):
        html = render_components(
            _plan("examples"),
            title="例",
            content={"examples": "コミット：あとでする"},
            glossary_entries=self._entries(),
        )

        self.assertIn('<b><span class="t"', html)

    def test_heading_terms_no_longer_count_as_unwrapped(self):
        html = render_components(
            _plan("details"),
            title="詳細",
            content={"details": "コミット：まだしていない"},
            glossary_entries=self._entries(),
        )

        inspection = inspect_artifact_html(
            html, required_components=("details",), glossary_entries=self._entries()
        )

        self.assertEqual(inspection.unwrapped_identifiers, ())


class DetailsStructureTests(unittest.TestCase):
    """P4：折りたたみの中に表・ログ・箇条書きを入れられる。"""

    def test_details_can_hold_a_table_a_log_and_bullets(self):
        html = render_components(
            _plan("details"),
            title="詳細",
            content={"details": [
                {
                    "summary": "検査の結果",
                    "text": "3つとも入る。",
                    "items": ["1件目", "2件目"],
                    "table": "名前｜件数" + NL + "テスト｜189",
                    "log": "189 passed",
                },
            ]},
        )

        self.assertIn("<summary>", html)
        self.assertIn('<ul class="bullets">', html)
        self.assertEqual(html.count("<li>"), 2)
        self.assertIn("<th>名前</th>", html)
        self.assertIn('<pre class="log">', html)

    def test_plain_string_details_still_works(self):
        html = render_components(
            _plan("details"),
            title="詳細",
            content={"details": "見出し：本文"},
        )

        self.assertIn("<summary>", html)
        self.assertIn('<div class="in">', html)


if __name__ == "__main__":
    unittest.main()


class VisualPipeTableTests(unittest.TestCase):
    """2026-09-10：縦棒の行が2行以上続いて列数が同じなら普通の表として組む。"""

    def test_two_or_more_pipe_rows_become_a_table(self):
        html = render_components(
            _plan("visual"),
            title="図",
            content={"visual": "項目｜前｜後\nissueの置き場｜書いていない｜GitHubのIssues\n新設したファイル｜0本｜3本"},
        )

        self.assertIn("<table>", html)
        self.assertIn("<th>項目</th>", html)
        self.assertEqual(html.count("<tr>"), 3)
        self.assertNotIn('class="flow-cell"', html)

    def test_single_pipe_row_stays_side_by_side(self):
        html = render_components(
            _plan("visual"),
            title="図",
            content={"visual": "変更前｜変更後\n↓\n結果"},
        )

        self.assertIn('class="flow-cols"', html)
        self.assertNotIn("<table>", html)

    def test_uneven_column_counts_stay_side_by_side(self):
        html = render_components(
            _plan("visual"),
            title="図",
            content={"visual": "A｜B\nC｜D｜E"},
        )

        self.assertNotIn("<table>", html)
        self.assertEqual(html.count('class="flow-cols"'), 2)

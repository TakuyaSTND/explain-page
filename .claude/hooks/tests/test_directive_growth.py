"""指示文の増え方の試験（2026-10-08・判断の頁を赤ペン流に寄せた変更）。

何を守るか＝指示文はターンごとに丸ごと出るので、足した文の長さがそのまま毎回の費用になる。
①判断を求める回（reasons に decision_required・頁を作る回）の増分は 150 字以内
②判断でない頁の回には試問の行を出さない ③頁を作らない回（Markdown）は1字も変えない。

基準値の取り方＝この変更の前のコード（直前のコミットの instructions.py）に、同じ固定の
断片ファイルと同じ名前の設定を与えて測った長さを定数にした。⚠️実物の断片ファイル
（html-output.md）や配布ごとの名前に左右されないよう、断片は試験の中で固定し、
回答集めの道具の名前と置き場の名前も試験の中で固定する。
"""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

HOOKS_DIR = Path(__file__).resolve().parents[1]
if str(HOOKS_DIR) not in sys.path:
    sys.path.insert(0, str(HOOKS_DIR))

from visual import branding  # noqa: E402
from visual.contracts import ExplanationPlan  # noqa: E402
from visual.instructions import FIGURE_KEYS_TEXT, PAGE_PHILOSOPHY_LINE, PREFLIGHT_LINE, compile_directive  # noqa: E402

ALL_COMPONENTS = (
    "overview", "summary", "walkthrough", "examples", "progress",
    "visual", "decision", "evidence", "glossary", "details",
)
FIXED_QA_TOOL = "qa-tool"
FIXED_DIR_NAME = "visual-pages"

# 変更の前のコードで、上の固定の断片・名前を与えて測った長さ。
BASELINE_DECISION_PAGE = 2405    # 頁を作る回・reasons に decision_required
BASELINE_PLAIN_PAGE = 2410       # 頁を作る回・decision_required なし
BASELINE_MARKDOWN = 1084         # 頁を作らない回
GROWTH_LIMIT_DECISION = 150
# 2026-10-31：利用者の指示で足した見せ方の思想の行（頁を作る回だけ・約270字）は別枠＝
#   上限の150字は、それ以外の増分を見張る。思想の行そのものの長さは下の試験で固定する。
PHILOSOPHY_ALLOWANCE = len(PAGE_PHILOSOPHY_LINE)
# 2026-11-05：利用者が報告の頁の Q1 で「足す」を選んだ図の鍵4つの文（105字）も別枠＝150字の見張りは、それ以外の増分に効いたまま。
FIGURE_KEYS_ALLOWANCE = len(FIGURE_KEYS_TEXT)
FIGURE_KEYS_MAX = 110
# 2026-10-31：利用者の指示「スクショは基本的にホバーに移して」の1文（約40字）を足したので 300→330。
PHILOSOPHY_MAX = 330


def _fragment_file(directory):
    body = "".join(
        "<!-- HOOK_COMPONENT:%s:START -->%s の断片（固定の文）。<!-- HOOK_COMPONENT:%s:END -->\n"
        % (name, name, name)
        for name in ALL_COMPONENTS
    )
    body += "<!-- HOOK_STYLE:START -->見た目の決まり（固定の文）。<!-- HOOK_STYLE:END -->\n"
    path = Path(directory) / "fragments.md"
    path.write_text(body, encoding="utf-8")
    return path


def _plan(delivery="local_html", reasons=("project_novice_default",)):
    return ExplanationPlan(
        audience="project_novice", depth="deep", components=ALL_COMPONENTS,
        reason_codes=tuple(reasons), provisional=False, should_continue=False,
        delivery=delivery, publish_policy="always",
    )


class _FixedBranding(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.fragments = _fragment_file(self._tmp.name)
        for name, value in (("QA_PAGE_TOOL", FIXED_QA_TOOL), ("ARTIFACT_DIR_NAME", FIXED_DIR_NAME)):
            patcher = patch.object(branding, name, value, create=True)
            patcher.start()
            self.addCleanup(patcher.stop)

    def directive(self, plan, **kwargs):
        return compile_directive(plan, self.fragments, **kwargs)


class GrowthTests(_FixedBranding):
    def test_decision_page_turn_grows_by_at_most_the_limit(self):
        length = len(self.directive(_plan(reasons=("decision_required",))))

        growth = length - BASELINE_DECISION_PAGE - PHILOSOPHY_ALLOWANCE - FIGURE_KEYS_ALLOWANCE
        self.assertGreater(growth, 0)
        self.assertLessEqual(growth, GROWTH_LIMIT_DECISION, "増分=%d字" % growth)

    def test_figure_keys_text_is_short_and_listed(self):
        # 別枠にした図の鍵の文そのものの長さを固定する（足すときは利用者に増える字数を見せてから）。
        self.assertLessEqual(len(FIGURE_KEYS_TEXT), FIGURE_KEYS_MAX)
        directive = self.directive(_plan())
        for key in ("`mermaid`", "`fishbone`", "`waterfall`", "`dumbbell`"):
            self.assertIn(key, directive)

    def test_plain_page_turn_grows_less_than_the_decision_turn(self):
        length = len(self.directive(_plan()))

        growth = length - BASELINE_PLAIN_PAGE - PHILOSOPHY_ALLOWANCE - FIGURE_KEYS_ALLOWANCE
        self.assertGreater(growth, 0)
        self.assertLess(growth, GROWTH_LIMIT_DECISION - len(PREFLIGHT_LINE))

    def test_markdown_turn_is_unchanged(self):
        # ⚠️頁を作らない回には、判断の回でも1字も足さない（基準値は reasons に decision_required の回）。
        length = len(self.directive(_plan("markdown", ("decision_required",))))

        self.assertEqual(length, BASELINE_MARKDOWN)


class PhilosophyLineTests(_FixedBranding):
    """2026-10-31：見せ方の思想の行＝頁を作る回だけ・先頭・長さの上限。"""

    def test_page_turns_start_with_the_line_and_markdown_turns_do_not_have_it(self):
        for plan in (_plan(), _plan(reasons=("decision_required",))):
            directive = self.directive(plan)
            self.assertEqual(directive.count(PAGE_PHILOSOPHY_LINE), 1)
            self.assertLess(directive.index("見せ方の思想"), directive.index("頁は手書きしない"))
        self.assertNotIn("見せ方の思想", self.directive(_plan("markdown", ("decision_required",))))

    def test_the_line_stays_short(self):
        self.assertLessEqual(len(PAGE_PHILOSOPHY_LINE), PHILOSOPHY_MAX)
        for needle in ("key", "[[info:", "tabs", "情報量は削らない"):
            self.assertIn(needle, PAGE_PHILOSOPHY_LINE)


class PreflightLineTests(_FixedBranding):
    def test_decision_turn_has_the_line_once_after_the_renderer_line(self):
        directive = self.directive(_plan(reasons=("decision_required",)))

        self.assertEqual(directive.count(PREFLIGHT_LINE), 1)
        self.assertLess(directive.index("頁は手書きしない"), directive.index("[試問]"))
        self.assertLess(directive.index("[試問]"), directive.index("[readability]"))

    def test_non_decision_page_turn_has_no_line(self):
        self.assertNotIn("[試問]", self.directive(_plan()))

    def test_markdown_turn_has_no_line(self):
        self.assertNotIn("[試問]", self.directive(_plan("markdown", ("decision_required",))))

    def test_codex_turn_keeps_both_lines(self):
        directive = self.directive(_plan(reasons=("decision_required",)), runtime="codex")

        self.assertIn("--runtime codex", directive)
        self.assertIn("[試問]", directive)

    def test_the_line_is_runtime_neutral_and_says_what_to_do_without_a_subagent(self):
        for needle in ("サブエージェント", "同期", "省く"):
            self.assertIn(needle, PREFLIGHT_LINE)
        for needle in ("http://", "https://", "file://"):
            self.assertNotIn(needle, PREFLIGHT_LINE)


class RendererLineTests(_FixedBranding):
    def test_options_are_told_to_carry_pros_cons_and_thumb(self):
        directive = self.directive(_plan())

        for needle in ("pros", "cons", "thumb", "非推奨にも利点"):
            self.assertIn(needle, directive)

    def test_answer_sheet_exception_names_both_tools_and_the_akapen_folder(self):
        directive = self.directive(_plan())

        self.assertIn("回答集めのシートだけ", directive)
        self.assertIn(FIXED_QA_TOOL, directive)
        self.assertIn("akapen", directive)
        self.assertIn("%TEMP%/" + FIXED_DIR_NAME + "/akapen/", directive)
        self.assertIn("検品証を取らない", directive)
        self.assertIn("シートだけの回は差し戻さない", directive)
        self.assertIn("報告と判断の頁は必ずレンダラーで作る", directive)

    def test_without_a_qa_tool_the_exception_is_not_printed(self):
        # ⚠️公開版は回答集めの道具の名前を持たない＝この例外の文を出さない（今までどおり）。
        with patch.object(branding, "QA_PAGE_TOOL", None, create=True):
            directive = self.directive(_plan())

        self.assertNotIn("回答集めのシート", directive)
        self.assertNotIn("akapen", directive)
        self.assertIn("報告と判断の頁は必ずレンダラーで作る", directive)


if __name__ == "__main__":
    unittest.main()

"""用語の包装が語の境目を見るか（2026-09-29 に見つかった既存の欠陥）。

実例＝本文「目盛りをきりのよい数に」の「盛り」に「数字を大きく見せる操作」の説明が付き、
表の欄と決定欄の理由にあったファイル名「discord-feedback-skill-gap」の feedback に
戻りの経路の説明が付いた。部分一致で包み、英数字の隣だけを別の語とみなしていたため。

既存の頁144本を組み直して測った結果（消えた包装89件・増えた包装32件・検品の合否の変化0本）
で規則を決めた。⚠️日本語は字種で決めない＝「前が漢字なら別の語」にすると、責任【主体】・
前回【致命傷】・人間【較正】のような正しい包装が約70件消える。∴語ごとの一覧で止める。
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
from visual.term_boundary import contains_term, find_term

MORI = "数字を大きく見せる操作。"
FEEDBACK = "戻りの経路があるか。"


def _entry(term: str, description: str) -> GlossaryEntry:
    return GlossaryEntry(term=term, description=description, provenance="test")


ENTRIES = {
    "盛り": _entry("盛り", MORI),
    "feedback": _entry("feedback", FEEDBACK),
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


def _render(components, content, entries=ENTRIES):
    return render_components(
        _plan(*components), title="題", content=content, glossary_entries=entries
    )


def _inspect(html, components, entries=ENTRIES):
    return inspect_artifact_html(
        html, required_components=tuple(components), glossary_entries=entries
    )


class ReportedCasesTests(unittest.TestCase):
    """報告された3つの形を、頁の定義から組んで確かめる。"""

    def test_mori_inside_memori_is_not_wrapped(self):
        html = _render(("walkthrough",), {"walkthrough": "軸：目盛りをきりのよい数に揃える。"})

        self.assertNotIn(MORI, html)
        self.assertIn("目盛りをきりのよい数に", html)

    def test_file_name_in_a_table_cell_is_not_wrapped(self):
        html = _render(
            ("walkthrough",),
            {"walkthrough": [{
                "heading": "置き場",
                "text": "頁のファイルは次のとおり。",
                "table": {"head": ["頁"], "rows": [["discord-feedback-skill-gap"]]},
            }]},
        )

        self.assertNotIn(FEEDBACK, html)
        self.assertIn("discord-feedback-skill-gap", html)

    def test_file_name_in_a_decision_why_is_not_wrapped(self):
        html = _render(
            ("decision",),
            {"decision": {"groups": [{
                "legend": "Q1 どれで進めるか",
                "kind": "radio",
                "options": [
                    {"label": "案A", "why": "discord-feedback-skill-gap の頁を直す",
                     "recommended": True},
                    {"label": "案B", "why": "何もしない"},
                ],
            }]}},
        )

        self.assertNotIn(FEEDBACK, html)
        self.assertIn('<span class="why">discord-feedback-skill-gap', html)

    def test_the_later_real_occurrence_is_wrapped_instead(self):
        # 取りこぼしの確認＝誤りの箇所を飛ばしたあと、本当の用法は包まれる。
        html = _render(
            ("walkthrough",),
            {"walkthrough": "軸：目盛りを揃える。discord-feedback-skill-gap の頁で、"
                            "数字の盛りと feedback の欄を点検した。"},
        )

        self.assertIn(">盛り</span>と ", html)
        self.assertIn(">feedback</span> の欄", html)
        self.assertEqual(html.count('<span class="t"'), 2)

    def test_the_inspector_does_not_demand_the_skipped_occurrences(self):
        # ⚠️検品器が別の規則だと、包まなかった語を「未包装」と責めて頁が落ちる。
        #   「：」の無い行は手順の本文（li の中の p）になる＝検品器が包装を求める場所。
        components = ("walkthrough",)
        html = _render(
            components,
            {"walkthrough": "目盛りを揃える。ファイルは discord-feedback-skill-gap にある。"},
        )
        inspection = _inspect(html, components)

        self.assertIn("<p>目盛りを揃える。", html)
        self.assertEqual(inspection.unwrapped_identifiers, ())
        self.assertNotIn(MORI, html)
        self.assertNotIn(FEEDBACK, html)


class AsciiTermTests(unittest.TestCase):
    """英字の語＝語の端が英数字の側だけ、英字の語と地続きなら別の語とみなす。"""

    def test_hyphen_joined_names_are_not_the_term(self):
        self.assertEqual(find_term("policy-issue-picker/", "issue"), -1)
        self.assertEqual(find_term("discord-feedback-skill-gap", "feedback"), -1)
        self.assertEqual(find_term("workspace-evidence", "evidence"), -1)

    def test_file_extensions_and_hosts_are_not_the_term(self):
        self.assertEqual(find_term("references/feedback-core.md", "feedback"), -1)
        self.assertEqual(find_term("feedback.md を読む", "feedback"), -1)
        self.assertEqual(find_term("https://laws.e-gov.go.jp/", "laws"), -1)

    def test_url_paths_are_not_the_term(self):
        self.assertEqual(find_term("https://www.mhlw.go.jp/data/roudou/", "data"), -1)

    def test_folder_names_inside_a_file_path_are_not_the_term(self):
        self.assertEqual(find_term("docs/ai-work/claims/claude-code-x.md", "claims"), -1)

    def test_slash_separated_lists_still_match(self):
        # ⚠️「/」は「または」の意味でも使う＝並びの中の語は包む。
        self.assertEqual(find_term("P0/P1/P2 の順", "P1"), 3)
        self.assertEqual(find_term("data/ident/means_ends のいずれか", "data"), 0)
        self.assertGreaterEqual(find_term("既存の API/DB、国保連", "API"), 0)

    def test_file_name_at_the_end_of_a_path_still_matches(self):
        text = ".claude/scripts/render_page.py に渡す"
        self.assertEqual(find_term(text, "render_page.py"), text.index("render_page.py"))

    def test_slash_command_names_are_not_the_term(self):
        self.assertEqual(find_term("/feedback はOpenAIへの報告", "feedback"), -1)

    def test_plain_words_still_match(self):
        self.assertEqual(find_term("severity、issue、why", "issue"), 9)
        self.assertEqual(find_term("（feedback）", "feedback"), 1)
        self.assertEqual(find_term("feedback. 次へ", "feedback"), 0)

    def test_the_old_ascii_rule_still_holds(self):
        self.assertEqual(find_term("Codex", "Code"), -1)
        self.assertEqual(find_term("APIs", "API"), -1)
        self.assertEqual(find_term("render_page_x", "render_page"), -1)


class JapaneseTermTests(unittest.TestCase):
    """日本語の語＝語ごとの一覧で止め、それ以外の複合語は包む。"""

    def test_listed_words_stop_the_match(self):
        self.assertFalse(contains_term("目盛りをきりのよい数に", "盛り"))
        self.assertFalse(contains_term("要点を盛り込む", "盛り"))
        self.assertFalse(contains_term("地域若者サポートステーション", "ポート"))
        self.assertFalse(contains_term("検査用エクスポートへ渡す", "ポート"))
        self.assertFalse(contains_term("取引先へ波及し得る", "波"))
        self.assertFalse(contains_term("関連言及はあるが", "連言"))
        self.assertFalse(contains_term("感度分析として", "感度"))

    def test_the_real_use_still_matches(self):
        self.assertTrue(contains_term("海外の効果を無補正で持ち込む盛りがある", "盛り"))
        self.assertTrue(contains_term("待受のポート番号", "ポート"))
        self.assertTrue(contains_term("7体を6枠に出すと2波になる", "波"))
        self.assertTrue(contains_term("連言の関係", "連言"))
        self.assertTrue(contains_term("感度が低い", "感度"))

    def test_ordinary_compounds_are_still_wrapped(self):
        # 測定で正しかった複合語＝前が漢字・後ろが漢字・前が片仮名。
        self.assertTrue(contains_term("責任主体が曖昧", "主体"))
        self.assertTrue(contains_term("前回致命傷候補", "致命傷"))
        self.assertTrue(contains_term("人間較正を経る", "較正"))
        self.assertTrue(contains_term("ディスクキャッシュ層", "キャッシュ"))
        self.assertTrue(contains_term("未コミットの変更", "コミット"))

    def test_japanese_terms_next_to_ascii_are_wrapped(self):
        # 以前は英数字の判定が日本語の語にも掛かり、正しい用法を取りこぼしていた。
        self.assertEqual(find_term("Claude正本からCodex版", "正本"), 6)
        self.assertEqual(find_term("11レンズ→独立反証", "レンズ"), 2)
        self.assertEqual(find_term("誤指摘の罠2件", "罠"), 4)
        self.assertEqual(find_term("ローカルGitコミット", "コミット"), 7)


class InspectorContextTests(unittest.TestCase):
    """検品器は、包装の span をまたいだ同じ文で境目を判定する（レンダラーと同じ）。"""

    def test_a_word_next_to_a_wrapped_term_is_judged_in_the_same_sentence(self):
        # 「目」を包むと、検品器が span で切った断片「盛りを…」だけを見た場合、
        #   直前の「目」が見えずに「盛り」を未包装と責める。同じ文で見れば責めない。
        entries = {
            "目": _entry("目", "見る器官。"),
            "盛り": _entry("盛り", MORI),
        }
        components = ("walkthrough",)
        html = _render(components, {"walkthrough": "目盛りを揃える。"}, entries)
        inspection = _inspect(html, components, entries)

        self.assertIn('<p><span class="t"', html)
        self.assertIn(">目</span>盛り", html)
        self.assertNotIn(MORI, html)
        self.assertEqual(inspection.unwrapped_identifiers, ())

    def test_an_unwrapped_first_use_in_prose_is_still_reported(self):
        # 検品の厳しさは緩めない＝本当の初出を包まなければ、今までどおり責める。
        html = (
            '<!doctype html><html><body><section data-component="walkthrough">'
            "<p>目盛りを揃えたあと、数字の盛りを疑う。</p></section></body></html>"
        )
        inspection = _inspect(html, ("walkthrough",))

        self.assertEqual(inspection.unwrapped_identifiers, ("盛り",))


if __name__ == "__main__":
    unittest.main()

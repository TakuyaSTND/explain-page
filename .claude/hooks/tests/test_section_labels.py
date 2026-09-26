"""見出しと中身のずれを止める検査（2026-08-30 ユーザー選択）。

⚠️空振り（正しい頁を止めてしまう）が最悪の失敗＝作業が進まなくなる。
   ∴実際に作った2枚の頁（節の自由化・横並び）で0件になることを較正で確かめた上で、
   ここでは「捕まえるべきずれ」と「捕まえてはいけない普通の見出し」を両方固定する。
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

HOOKS_DIR = Path(__file__).resolve().parents[1]
if str(HOOKS_DIR) not in sys.path:
    sys.path.insert(0, str(HOOKS_DIR))

from visual.section_labels import check_sections


class BorrowedWordTests(unittest.TestCase):
    """別の部品が持つ言葉を見出しに借りたら止める。"""

    def test_evidence_word_on_a_walkthrough_section_is_stopped(self):
        problems = check_sections(
            [{"component": "walkthrough", "num": "壱", "label": "根拠をまとめる", "content": "本文"}]
        )

        self.assertEqual(len(problems), 1)
        self.assertIn("evidence の言葉", problems[0])
        self.assertIn("根拠", problems[0])

    def test_decision_word_on_an_examples_section_is_stopped(self):
        problems = check_sections(
            [{"component": "examples", "label": "裁定の実例", "content": "本文"}]
        )

        self.assertEqual(len(problems), 1)
        self.assertIn("decision の言葉", problems[0])

    def test_the_owner_may_use_its_own_word(self):
        problems = check_sections(
            [
                {"component": "evidence", "label": "根拠と、確かめていないこと", "content": "実測：内容｜出所"},
                {"component": "decision", "label": "決めてほしいこと", "content": {"options": ["案"]}},
                {"component": "examples", "label": "2段組みの実例", "content": "本文"},
            ]
        )

        self.assertEqual(problems, [])

    def test_ordinary_headings_are_not_stopped(self):
        # ⚠️空振り防止。実際に作った頁の見出しをそのまま入れてある。
        problems = check_sections(
            [
                {"component": "walkthrough", "label": "なぜ横並びが要ったか（数えて決めた）", "content": "本文"},
                {"component": "visual", "label": "狭い画面での畳み方", "content": "左｜右"},
                {"component": "table", "label": "手書き頁で実際に使われていた横並び", "content": {"head": ["A"], "rows": [["1"]]}},
                {"component": "glossary", "label": "この頁で使った言葉", "content": "語：説明"},
            ]
        )

        self.assertEqual(problems, [])


class SoftWordTests(unittest.TestCase):
    """「まとめ」だけの見出しは summary と見分けが付かない。"""

    def test_a_bare_summary_word_is_stopped(self):
        problems = check_sections([{"component": "evidence", "label": "まとめ", "content": "実測：内容｜出所"}])

        self.assertEqual(len(problems), 1)
        self.assertIn("見分けが付かない", problems[0])

    def test_the_same_word_inside_a_longer_heading_is_allowed(self):
        problems = check_sections(
            [{"component": "evidence", "label": "測ったことのまとめ方", "content": "実測：内容｜出所"}]
        )

        self.assertEqual(problems, [])


class EmptyBodyTests(unittest.TestCase):
    def test_a_section_without_content_is_stopped(self):
        problems = check_sections([{"component": "walkthrough", "num": "壱", "label": "背景"}], {})

        self.assertEqual(len(problems), 1)
        self.assertIn("中身が無い", problems[0])

    def test_content_may_come_from_the_component_dictionary(self):
        problems = check_sections(
            [{"component": "walkthrough", "label": "背景"}], {"walkthrough": "見出し：本文"}
        )

        self.assertEqual(problems, [])

    def test_an_empty_string_counts_as_missing(self):
        problems = check_sections([{"component": "walkthrough", "label": "背景"}], {"walkthrough": "   "})

        self.assertEqual(len(problems), 1)


class DuplicateTests(unittest.TestCase):
    def test_the_same_heading_twice_is_stopped(self):
        problems = check_sections(
            [
                {"component": "table", "num": "壱", "label": "実測", "content": {"head": ["A"], "rows": [["1"]]}},
                {"component": "table", "num": "弐", "label": "実測", "content": {"head": ["B"], "rows": [["2"]]}},
            ]
        )

        self.assertEqual(len(problems), 1)
        self.assertIn("2回出ている", problems[0])

    def test_the_same_number_twice_is_stopped(self):
        problems = check_sections(
            [
                {"component": "table", "num": "壱", "label": "実測", "content": {"head": ["A"], "rows": [["1"]]}},
                {"component": "table", "num": "壱", "label": "別の切り口", "content": {"head": ["B"], "rows": [["2"]]}},
            ]
        )

        self.assertEqual(len(problems), 1)
        self.assertIn("番号", problems[0])

    def test_repeating_a_component_with_distinct_headings_is_allowed(self):
        # ⚠️同じ部品の繰り返しは前回わざわざ開いた機能。ここで塞がない。
        problems = check_sections(
            [
                {"component": "table", "num": "壱", "label": "実測", "content": {"head": ["A"], "rows": [["1"]]}},
                {"component": "table", "num": "弐", "label": "別の切り口", "content": {"head": ["B"], "rows": [["2"]]}},
            ]
        )

        self.assertEqual(problems, [])


class MalformedTests(unittest.TestCase):
    def test_a_section_without_a_component_is_stopped(self):
        problems = check_sections([{"label": "見出しだけ"}])

        self.assertEqual(len(problems), 1)
        self.assertIn("部品名が無い", problems[0])

    def test_a_non_mapping_entry_is_stopped(self):
        problems = check_sections(["節ではない"])

        self.assertEqual(len(problems), 1)

    def test_no_sections_is_not_an_error(self):
        self.assertEqual(check_sections([]), [])
        self.assertEqual(check_sections(None), [])




class ExpandedLexiconTests(unittest.TestCase):
    """2026-08-31：持ち主の言葉を7部品→13部品に増やした分。

    ⚠️増やすほど空振りの危険が上がる。実際に作った頁5枚・節104個で0件を確かめた上で入れた。
    """

    def test_newly_owned_words_are_caught(self):
        cases = (
            ("table", "対照表を作った", "walkthrough"),
            ("log", "実行の記録", "examples"),
            ("evidence", "裏取りの経過", "walkthrough"),
            ("overview", "一言でいうと", "walkthrough"),
            ("diagram", "流れ図の説明", "table"),
            ("visual", "図で見るとこうなる", "diagram"),
            ("summary", "3行でいうと", "progress"),
        )
        for owner, label, wrong_component in cases:
            with self.subTest(label=label):
                problems = check_sections(
                    [{"component": wrong_component, "label": label, "content": "本文"}]
                )
                self.assertEqual(len(problems), 1, problems)
                self.assertIn("%s の言葉" % owner, problems[0])

    def test_the_owner_itself_is_never_stopped(self):
        cases = (
            ("table", "対照表を作った"),
            ("log", "実行の記録"),
            ("evidence", "裏取りの経過"),
            ("overview", "一言でいうと"),
            ("diagram", "流れ図の説明"),
            ("visual", "図で見るとこうなる"),
            ("summary", "3行でいうと"),
        )
        for component, label in cases:
            with self.subTest(label=label):
                self.assertEqual(
                    check_sections([{"component": component, "label": label, "content": "本文"}]),
                    [],
                )

    def test_headings_from_the_pages_we_actually_built_still_pass(self):
        # ⚠️空振りの較正。実際に出した頁の見出しをそのまま並べてある。
        built = (
            ("walkthrough", "2つの選択がぶつかった話と、その解き方"),
            ("walkthrough", "目次を自動で組むことにした理由"),
            ("diagram", "側柱はどこに立つのか"),
            ("diagram", "目次はどこから来るのか"),
            ("table", "4つの依頼と、やったこと"),
            ("table", "10万バイト級で測った結果"),
            ("examples", "側柱の実物と、止まる見出しの例"),
            ("visual", "広い画面と狭い画面"),
            ("visual", "小さい頁と大きい頁"),
            ("log", "検査の記録"),
            ("progress", "いまの状態"),
            ("decision", "決めてほしいこと"),
            ("evidence", "根拠と、確かめていないこと"),
            ("glossary", "この頁で使った言葉"),
            ("details", "畳んである細部"),
        )
        problems = check_sections(
            [{"component": c, "label": label, "content": "本文"} for c, label in built]
        )

        self.assertEqual(problems, [])


if __name__ == "__main__":
    unittest.main()

"""判断の問いが実質1択になっていないかの警告の試験（2026-10-08・案1）。

何を守るか＝推奨が付いているのに、推奨でない案に利点（pros）も「利点」の語も無い問いは、
人から見て「推奨を選ぶしかない」実質1択になる。render_page.py はそれを組む前に1行ずつ知らせる
（止めはしない）。利用者の実際の定義は利点／代償を why の中に「利点：…／代償：…」で書くので、
why に「利点」を含む案は警告しない。
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

HOOKS_DIR = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = HOOKS_DIR.parent / "scripts"
for _entry in (str(HOOKS_DIR), str(SCRIPTS_DIR)):
    if _entry not in sys.path:
        sys.path.insert(0, _entry)

import render_page as rp  # noqa: E402


def _group(options, legend="進め方", kind="radio"):
    return {"legend": legend, "kind": kind, "options": options}


def _content(*groups):
    return {"decision": {"groups": list(groups)}}


class WarnsOnPracticallyOneChoiceTests(unittest.TestCase):
    def test_non_recommended_option_without_pros_is_one_line(self):
        content = _content(_group([
            {"label": "案A", "recommended": True},
            {"label": "案B", "why": "遅いが丁寧"},
        ]))

        lines = rp.decision_option_warnings(content)

        self.assertEqual(len(lines), 1)
        self.assertEqual(
            lines[0],
            "⚠️実質1択の恐れ（止めはしない）: Q1「進め方」の「案B」に利点（pros）が無い"
            "＝非推奨でも選ぶ理由を1行書く",
        )

    def test_one_line_per_option_without_pros(self):
        content = _content(_group([
            {"label": "案A", "recommended": True},
            {"label": "案B"},
            {"label": "案C"},
        ]))

        self.assertEqual(len(rp.decision_option_warnings(content)), 2)

    def test_checkbox_groups_are_checked_too(self):
        content = _content(_group([
            {"label": "甲", "recommended": True},
            {"label": "乙"},
        ], kind="checkbox"))

        self.assertEqual(len(rp.decision_option_warnings(content)), 1)

    def test_kind_defaults_to_radio(self):
        content = {"decision": {"groups": [{"legend": "問い", "options": [
            {"label": "甲", "recommended": True}, {"label": "乙"},
        ]}]}}

        self.assertEqual(len(rp.decision_option_warnings(content)), 1)

    def test_old_style_options_are_checked(self):
        content = {"decision": {"options": [
            {"label": "甲", "recommended": True}, {"label": "乙"},
        ]}}

        lines = rp.decision_option_warnings(content)

        self.assertEqual(len(lines), 1)
        self.assertIn("Q1「選択肢」の「乙」", lines[0])

    def test_warning_text_has_no_forbidden_scheme(self):
        content = _content(_group([
            {"label": "案A", "recommended": True}, {"label": "案B"},
        ]))

        for line in rp.decision_option_warnings(content):
            self.assertNotIn("http://", line)
            self.assertNotIn("https://", line)
            self.assertNotIn("file://", line)


class DoesNotWarnTests(unittest.TestCase):
    def test_why_with_the_word_riten_counts_as_a_reason(self):
        content = _content(_group([
            {"label": "案A", "recommended": True},
            {"label": "案B", "why": "利点：安い／代償：遅い"},
        ]))

        self.assertEqual(rp.decision_option_warnings(content), [])

    def test_pros_string_counts(self):
        content = _content(_group([
            {"label": "案A", "recommended": True},
            {"label": "案B", "pros": "安い", "cons": "遅い"},
        ]))

        self.assertEqual(rp.decision_option_warnings(content), [])

    def test_pros_list_counts_and_blank_pros_does_not(self):
        counted = _content(_group([
            {"label": "案A", "recommended": True},
            {"label": "案B", "pros": ["安い", "速い"]},
        ]))
        blank = _content(_group([
            {"label": "案A", "recommended": True},
            {"label": "案B", "pros": ["", "  "]},
            {"label": "案C", "pros": "   "},
        ]))

        self.assertEqual(rp.decision_option_warnings(counted), [])
        self.assertEqual(len(rp.decision_option_warnings(blank)), 2)

    def test_group_without_any_recommendation_is_left_alone(self):
        content = _content(_group([{"label": "案A"}, {"label": "案B"}]))

        self.assertEqual(rp.decision_option_warnings(content), [])

    def test_string_only_options_get_one_line_per_group(self):
        # 2026-10-08（リード）：文字列だけの群は推奨の印も利点も付かない＝辞書の形へ寄せる指摘。
        content = _content(_group(["案A（推奨）", "案B"]))

        lines = rp.decision_option_warnings(content)
        self.assertEqual(len(lines), 1)
        self.assertIn("選択肢が文字だけ", lines[0])
        self.assertIn("Q1", lines[0])

    def test_a_single_string_option_is_left_alone(self):
        self.assertEqual(rp.decision_option_warnings(_content(_group(["案A"]))), [])

    def test_string_option_next_to_a_recommended_dict_lacks_pros(self):
        content = _content(_group([{"label": "案A", "recommended": True}, "案B"]))

        lines = rp.decision_option_warnings(content)
        self.assertEqual(len(lines), 1)
        self.assertIn("「案B」に利点（pros）が無い", lines[0])

    def test_scale_number_and_free_are_out_of_scope(self):
        content = _content(
            {"legend": "段階", "kind": "scale", "items": [{"title": "安全"}]},
            {"legend": "数", "kind": "number", "options": [
                {"label": "件数", "recommended": True}, {"label": "日数"},
            ]},
            {"legend": "自由記述", "kind": "free"},
        )

        self.assertEqual(rp.decision_option_warnings(content), [])

    def test_no_decision_at_all(self):
        self.assertEqual(rp.decision_option_warnings({"overview": "本文"}), [])

    def test_odd_shapes_do_not_raise(self):
        for decision in ("単独の値", {"groups": ["甲"]}, {"options": "甲"}, {}):
            self.assertEqual(rp.decision_option_warnings({"decision": decision}), [])
        # 文字列2つの配列は「選択肢が文字だけ」の1行になる（例外は出さない）。
        self.assertEqual(len(rp.decision_option_warnings({"decision": ["甲", "乙"]})), 1)


class WhereItLooksTests(unittest.TestCase):
    def test_decision_sections_in_the_section_list_are_checked(self):
        content = {"sections": [
            {"component": "walkthrough", "content": "手順：本文"},
            {"component": "decision", "label": "決めること", "content": {"groups": [
                _group([{"label": "甲", "recommended": True}, {"label": "乙"}]),
            ]}},
        ]}

        lines = rp.decision_option_warnings(content)

        self.assertEqual(len(lines), 1)
        self.assertIn("Q1「進め方」の「乙」", lines[0])

    def test_question_numbers_run_through_the_page_and_skip_free_groups(self):
        content = {"sections": [
            {"component": "decision", "content": {"groups": [
                {"legend": "自由記述", "kind": "free"},
                _group([{"label": "甲", "recommended": True}, {"label": "乙", "why": "利点：安い"}],
                       legend="一つ目"),
            ]}},
            {"component": "decision", "content": {"groups": [
                _group([{"label": "丙", "recommended": True}, {"label": "丁"}], legend="二つ目"),
            ]}},
        ]}

        lines = rp.decision_option_warnings(content)

        # free は数えない＝一つ目が Q1・二つ目が Q2（回答文の番号と同じ）。
        self.assertEqual(len(lines), 1)
        self.assertIn("Q2「二つ目」の「丁」", lines[0])

    def test_top_level_decision_is_used_when_the_section_list_has_none(self):
        content = {
            "sections": [{"component": "walkthrough", "content": "手順：本文"}],
            "decision": {"groups": [_group([{"label": "甲", "recommended": True}, {"label": "乙"}])]},
        }

        self.assertEqual(len(rp.decision_option_warnings(content)), 1)

    def test_decision_section_without_its_own_content_falls_back_to_the_top_level(self):
        content = {
            "sections": [{"component": "decision", "label": "決めること"}],
            "decision": {"groups": [_group([{"label": "甲", "recommended": True}, {"label": "乙"}])]},
        }

        self.assertEqual(len(rp.decision_option_warnings(content)), 1)


class LimitTests(unittest.TestCase):
    def _many(self, count):
        options = [{"label": "推奨案", "recommended": True}]
        options += [{"label": "案%d" % number} for number in range(count)]
        return _content(_group(options))

    def test_ten_lines_are_shown_in_full(self):
        lines = rp.decision_option_warnings(self._many(10))

        self.assertEqual(len(lines), 10)
        self.assertTrue(all("実質1択" in line for line in lines))

    def test_eleven_warnings_become_ten_lines_and_a_remainder(self):
        lines = rp.decision_option_warnings(self._many(11))

        self.assertEqual(len(lines), 11)
        self.assertIn("ほか1件", lines[-1])
        self.assertTrue(all("実質1択" in line for line in lines[:10]))

    def test_long_names_are_cut(self):
        content = _content(_group(
            [{"label": "推奨", "recommended": True}, {"label": "あ" * 80}],
            legend="い" * 80,
        ))

        line = rp.decision_option_warnings(content)[0]

        self.assertNotIn("あ" * 40, line)
        self.assertNotIn("い" * 40, line)


class ReachesTheToolOutputTests(unittest.TestCase):
    """main() が組む前に警告を出し、頁の組み立ては止めない。"""

    def test_main_prints_the_warning_and_still_builds(self):
        import contextlib
        import io
        import json
        import tempfile
        import types
        from unittest.mock import patch

        spec = {
            "name": "warn-check",
            "title": "警告の確認",
            "components": list(rp.ALL_COMPONENTS),
            "reasons": ["project_novice_default"],
            "publish": "never",
            "content": {
                "overview": "警告の確認用の頁である。",
                "summary": "Goal：警告を確かめる。\nNow：試験中である。",
                "walkthrough": "手順一：試験のための本文である。",
                "examples": "例一：試験のための本文である。",
                "progress": "現在地：試験中である。",
                "visual": "図の見本：試験のための本文である。",
                "decision": {"groups": [_group([
                    {"label": "案A", "recommended": True}, {"label": "案B"},
                ])]},
                "evidence": "実測：試験のための値である｜.claude/hooks/tests/test_decision_option_warnings.py",
                "glossary": "用語一：試験のための説明である。",
                "details": "記録：試験のための詳細である。",
            },
        }
        fake_smoke = types.SimpleNamespace(status="pass", errors=(), metrics={})
        with tempfile.TemporaryDirectory() as td:
            spec_path = Path(td) / "spec.json"
            spec_path.write_text(json.dumps(spec, ensure_ascii=False), encoding="utf-8")
            out_root = Path(td) / "root"
            buffer = io.StringIO()
            with patch.object(rp, "run_visual_smoke", return_value=fake_smoke), \
                 patch.object(rp, "_approved_root_for", return_value=str(out_root)), \
                 contextlib.redirect_stdout(buffer):
                code = rp.main(["render_page.py", str(spec_path)])
            built = (out_root / "warn-check.html").is_file()

        text = buffer.getvalue()
        self.assertIn("実質1択の恐れ（止めはしない）", text)
        self.assertLess(text.index("実質1択の恐れ"), text.index("書き出した:"))
        self.assertTrue(built)
        self.assertIn(code, (0, 1))


if __name__ == "__main__":
    unittest.main()

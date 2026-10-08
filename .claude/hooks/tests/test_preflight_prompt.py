"""判断の頁の試問の文の試験（2026-10-08・案5）。

何を守るか＝reasons に decision_required がある頁を組んだとき、render_page.py の出力の末尾に
「文脈ゼロの読者に読ませる試問の文」が付く。判断の頁以外には付かない（毎回の費用を判断の回に限る）。
節の見出しは、レンダラーが実際に頁へ出す文字（「選ぶこと」「根拠」「用語」。節の一覧で自分で
付けた見出しがあればそれ）に合わせる。この試験は一時フォルダの置き場にだけ書く。
"""
from __future__ import annotations

import contextlib
import io
import json
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch

HOOKS_DIR = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = HOOKS_DIR.parent / "scripts"
for _entry in (str(HOOKS_DIR), str(SCRIPTS_DIR)):
    if _entry not in sys.path:
        sys.path.insert(0, _entry)

import render_page as rp  # noqa: E402

START = "---- ここから ----"
END = "---- ここまで ----"
CLOSING = "出力は問いごとに「通過 / 落ちた問いと理由」で。頁を直す提案は不要です。"


def _spec(reasons=("project_novice_default", "decision_required"), **extra):
    spec = {
        "name": "preflight-check",
        "title": "試問の確認",
        "components": list(rp.ALL_COMPONENTS),
        "reasons": list(reasons),
        "publish": "never",
        "content": {
            "overview": "試問の確認用の頁である。",
            "summary": "Goal：試問の文を確かめる。\nNow：試験中である。",
            "walkthrough": "手順一：試験のための本文である。",
            "examples": "例一：試験のための本文である。",
            "progress": "現在地：試験中である。",
            "visual": "図の見本：試験のための本文である。",
            "decision": {"groups": [{"legend": "進め方", "kind": "radio", "options": [
                {"label": "案A", "why": "利点：速い", "recommended": True},
                {"label": "案B", "pros": "丁寧", "cons": "遅い"},
            ]}]},
            "evidence": "実測：試験のための値である｜.claude/hooks/tests/test_preflight_prompt.py",
            "glossary": "用語一：試験のための説明である。",
            "details": "記録：試験のための詳細である。",
        },
    }
    spec.update(extra)
    return spec


def _run_main(spec):
    """main() を一時フォルダの置き場で走らせる。返るもの＝(出力, 完全版のpath, 完全版の本文)。

    文字だけの版（<name>-text.txt）は同じ置き場に書かれる＝そのpathは完全版のpathの拡張子を
    -text.txt に替えたもの（試験では一時フォルダが消えるので、pathの文字だけを使う）。
    """
    fake_smoke = types.SimpleNamespace(status="pass", errors=(), metrics={})
    with tempfile.TemporaryDirectory() as td:
        spec_path = Path(td) / "spec.json"
        spec_path.write_text(json.dumps(spec, ensure_ascii=False), encoding="utf-8")
        out_root = Path(td) / "root"
        buffer = io.StringIO()
        with patch.object(rp, "run_visual_smoke", return_value=fake_smoke), \
             patch.object(rp, "_approved_root_for", return_value=str(out_root)), \
             contextlib.redirect_stdout(buffer):
            rp.main(["render_page.py", str(spec_path)])
        full = out_root / (spec["name"] + ".html")
        html = full.read_text(encoding="utf-8")
        return buffer.getvalue(), str(full), html


class PrintedOnlyForDecisionPagesTests(unittest.TestCase):
    def test_decision_required_prints_the_prompt_after_the_publish_note(self):
        text, full, _html = _run_main(_spec())

        self.assertIn("[試問] この頁は判断を求める（reasons に decision_required）", text)
        self.assertIn(START, text)
        self.assertIn(END, text)
        self.assertIn(CLOSING, text)
        self.assertLess(text.index("publish には**器用**"), text.index("[試問]"))
        self.assertLess(text.index(START), text.index(END))

    def test_five_questions_are_inside_the_block(self):
        text, _full, _html = _run_main(_spec())

        block = text[text.index(START):text.index(END)]
        for number in range(1, 6):
            self.assertIn("\n%d. " % number, block)

    def test_the_reader_is_given_the_text_only_version_and_the_full_page_for_looks(self):
        text, full, _html = _run_main(_spec())
        text_path = full[:-len(".html")] + "-text.txt"

        self.assertIn(
            "頁（文字だけの版）: %s（Read で開く。画像・図・script・style を外した本文。"
            "〔用語〕はホバーで説明の付く語）" % text_path,
            text,
        )
        self.assertIn("元の頁（見た目の確認だけに使う）: %s" % full, text)
        self.assertNotIn("頁: %s（Read で開く）" % full, text)
        # 文字だけの版が先・元の頁が後（読み手が先に読むのは文字だけの版）。
        self.assertLess(text.index("頁（文字だけの版）"), text.index("元の頁（見た目の確認だけに使う）"))

    def test_the_machine_checked_items_are_not_given_to_the_reader(self):
        text, _full, _html = _run_main(_spec())

        block = text[text.index(START):text.index(END)]
        self.assertIn(
            "機械で済ませた検査（空の強調・図の記号・図番号の重複・問いへの飛び先）は見なくてよい。", block
        )
        self.assertLess(block.index("元の頁（見た目の確認だけに使う）"), block.index("機械で済ませた検査"))
        self.assertLess(block.index("機械で済ませた検査"), block.index("読者宣言"))

    def test_without_a_text_path_the_old_single_page_line_is_used(self):
        prompt = rp.preflight_prompt(_spec(), "page.html")

        self.assertIn("頁: page.html（Read で開く）", prompt)
        self.assertNotIn("文字だけの版", prompt)
        self.assertNotIn("元の頁", prompt)
        self.assertIn("機械で済ませた検査", prompt)

    def test_with_a_text_path_both_paths_are_named(self):
        prompt = rp.preflight_prompt(_spec(), "page.html", "page-text.txt")

        self.assertIn("頁（文字だけの版）: page-text.txt（Read で開く。", prompt)
        self.assertIn("元の頁（見た目の確認だけに使う）: page.html", prompt)

    def test_question_one_explains_the_arrow_marker_on_headings(self):
        prompt = rp.preflight_prompt(_spec(), "page.html", "page-text.txt")
        block = prompt[prompt.index(START):prompt.index(END)]
        question_one = block[block.index("\n1. "):block.index("\n2. ")]

        self.assertIn("節の見出しの「→ Q1」は、その節がどの問いに関わるかの印です。", question_one)

    def test_without_decision_required_nothing_is_printed(self):
        text, _full, _html = _run_main(_spec(reasons=("project_novice_default",)))

        self.assertNotIn("[試問]", text)
        self.assertNotIn(START, text)

    def test_the_prompt_has_no_forbidden_scheme(self):
        text, _full, _html = _run_main(_spec())

        block = text[text.index("[試問]"):]
        for needle in ("http://", "https://", "file://"):
            self.assertNotIn(needle, block)


class ReaderDeclarationTests(unittest.TestCase):
    def test_allowed_words_and_reader_are_put_in(self):
        spec = _spec(preflight={"reader": "このリポジトリを初めて読む人。", "allowed": ["フック", "検品証"]})

        text, _full, _html = _run_main(spec)

        self.assertIn("読者宣言: このリポジトリを初めて読む人。説明なしで使ってよい語は フック、検品証 だけ", text)

    def test_default_reader_and_no_allowed_words(self):
        text, _full, _html = _run_main(_spec())

        self.assertIn("読者宣言: このプロジェクトを初めて読む人。説明なしで使ってよい語は無い", text)

    def test_allowed_may_be_a_single_string(self):
        prompt = rp.preflight_prompt(_spec(preflight={"allowed": "フック"}), "page.html")

        self.assertIn("説明なしで使ってよい語は フック だけ", prompt)

    def test_a_broken_preflight_field_falls_back_to_the_default(self):
        prompt = rp.preflight_prompt(_spec(preflight="読者"), "page.html")

        self.assertIn("このプロジェクトを初めて読む人", prompt)


class HeadingsMatchTheRenderedPageTests(unittest.TestCase):
    def test_default_headings_are_the_ones_the_page_prints(self):
        text, _full, html = _run_main(_spec())

        for heading in ("選ぶこと", "根拠", "用語"):
            self.assertIn("「%s」の節" % heading, text)
            self.assertIn(">%s</h2>" % heading, html.replace("</span>", ""))

    def test_a_section_label_chosen_by_the_page_is_used(self):
        spec = _spec()
        spec["content"]["sections"] = [
            {"component": "decision", "label": "決めてほしい点",
             "content": spec["content"]["decision"]},
            {"component": "evidence", "label": "確かめた場所"},
        ]

        text, _full, html = _run_main(spec)

        self.assertIn("「決めてほしい点」の節", text)
        self.assertIn("「確かめた場所」の節", text)
        self.assertNotIn("「選ぶこと」の節", text)
        self.assertIn("決めてほしい点</h2>", html)

    def test_prompt_names_each_question_for_the_three_sections(self):
        prompt = rp.preflight_prompt(_spec(), "page.html")
        block = prompt[prompt.index(START):prompt.index(END)]

        self.assertIn("1. 「選ぶこと」の節の各問", block)
        self.assertIn("2. 頁の断定（本文・判定・推奨）に、「根拠」の節の表の行", block)
        self.assertIn("頁の「用語」の節", block)


if __name__ == "__main__":
    unittest.main()

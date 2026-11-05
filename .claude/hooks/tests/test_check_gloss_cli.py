from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

CHECKER_PATH = Path(__file__).resolve().parents[2] / "scripts" / "check_gloss.py"


def load_checker():
    spec = importlib.util.spec_from_file_location("check_gloss_cli", CHECKER_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {CHECKER_PATH}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class CheckGlossCliTests(unittest.TestCase):
    def test_strict_fails_when_second_occurrence_has_wrong_description(self):
        checker = load_checker()
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            shared = root / "shared.md"
            project = root / "project.md"
            html = root / "page.html"
            shared.write_text("# shared\n", encoding="utf-8")
            project.write_text(
                "| 用語 | 説明 |\n|---|---|\n| claims | 正しい説明 |\n",
                encoding="utf-8",
            )
            html.write_text(
                '<span class="t" tabindex="0" data-d="正しい説明">claims</span>'
                '<span class="t" tabindex="0" data-d="誤った説明">claims</span>',
                encoding="utf-8",
            )
            checker.SHARED_HOME = str(shared)
            checker.SHARED_MIRROR = str(shared)
            checker.GLOSS = str(project)
            old_argv = sys.argv
            sys.argv = [str(CHECKER_PATH), str(html), "--strict"]
            try:
                with contextlib.redirect_stdout(io.StringIO()):
                    code = checker.main()
            finally:
                sys.argv = old_argv

        self.assertEqual(code, 2)

    def test_reference_list_leaves_out_words_that_have_a_rule(self):
        # 2026-10-18：規則表（固有の用語集の隣）にある語は、③の参考（包んでいない語）に混ぜない。
        #   普通の言葉としても使う語なので、包まないのが正しい場合が大半＝書く側に義務があるように読めてしまう。
        #   ⚠️頁を落とす判定は変えない（この試験は終了値ではなく③の語の一覧だけを見る）。
        checker = load_checker()
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            shared = root / "shared.md"
            project = root / "project.md"
            html = root / "page.html"
            shared.write_text("# shared\n", encoding="utf-8")
            project.write_text(
                "| 用語 | 説明 |\n|---|---|\n| 実時間 | 時計の時間 |\n| ボトルネック | 一番の詰まり所 |\n",
                encoding="utf-8",
            )
            (root / "glossary-context.json").write_text(
                json.dumps({"_comment": "説明", "実時間": {"cues": []}}, ensure_ascii=False),
                encoding="utf-8",
            )
            html.write_text("<p>実時間とボトルネックを測る</p>", encoding="utf-8")
            checker.SHARED_HOME = str(shared)
            checker.SHARED_MIRROR = str(shared)
            checker.GLOSS = str(project)
            old_argv = sys.argv
            sys.argv = [str(CHECKER_PATH), str(html)]
            output = io.StringIO()
            try:
                with contextlib.redirect_stdout(output):
                    checker.main()
            finally:
                sys.argv = old_argv

        text = output.getvalue()
        self.assertIn("規則表 1語", text)
        self.assertIn("ボトルネック", text)
        self.assertNotIn("実時間", text)

    def test_without_a_rule_file_nothing_is_left_out(self):
        checker = load_checker()
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            shared = root / "shared.md"
            project = root / "project.md"
            html = root / "page.html"
            shared.write_text("# shared\n", encoding="utf-8")
            project.write_text(
                "| 用語 | 説明 |\n|---|---|\n| 実時間 | 時計の時間 |\n",
                encoding="utf-8",
            )
            html.write_text("<p>実時間を測る</p>", encoding="utf-8")
            checker.SHARED_HOME = str(shared)
            checker.SHARED_MIRROR = str(shared)
            checker.GLOSS = str(project)
            old_argv = sys.argv
            sys.argv = [str(CHECKER_PATH), str(html)]
            output = io.StringIO()
            try:
                with contextlib.redirect_stdout(output):
                    checker.main()
            finally:
                sys.argv = old_argv

        text = output.getvalue()
        self.assertNotIn("規則表", text)
        self.assertIn("実時間", text)


if __name__ == "__main__":
    unittest.main()

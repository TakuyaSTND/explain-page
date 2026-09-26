from __future__ import annotations

import contextlib
import importlib.util
import io
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


if __name__ == "__main__":
    unittest.main()

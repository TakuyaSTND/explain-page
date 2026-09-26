from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path

sys.dont_write_bytecode = True

CLAUDE_DIR = Path(__file__).resolve().parents[2]
CHECKER_PATH = CLAUDE_DIR / "scripts" / "check_gloss.py"


def load_checker():
    spec = importlib.util.spec_from_file_location("current_check_gloss", CHECKER_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {CHECKER_PATH}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class GlossaryCharacterizationTests(unittest.TestCase):
    def setUp(self):
        self.checker = load_checker()

    def test_project_entry_overrides_shared_entry(self):
        with tempfile.TemporaryDirectory() as td:
            td_path = Path(td)
            shared = td_path / "shared.md"
            project = td_path / "project.md"
            shared.write_text("| 用語 | 説明 |\n|---|---|\n| M | 共通の説明 |\n", encoding="utf-8")
            project.write_text("| 用語 | 説明 |\n|---|---|\n| M | Project固有の説明 |\n", encoding="utf-8")
            self.checker.SHARED_HOME = str(shared)
            self.checker.SHARED_MIRROR = str(shared)
            self.checker.GLOSS = str(project)
            glossary = self.checker.load_glossary()
        self.assertEqual(glossary["M"], "Project固有の説明")
        self.assertEqual(self.checker.OVERRIDE, ["M"])

    def test_mirror_is_used_when_home_shared_is_missing(self):
        with tempfile.TemporaryDirectory() as td:
            td_path = Path(td)
            missing_home = td_path / "missing.md"
            mirror = td_path / "mirror.md"
            project = td_path / "project.md"
            mirror.write_text("| 用語 | 説明 |\n|---|---|\n| Hook | 共通説明 |\n", encoding="utf-8")
            project.write_text("# project\n", encoding="utf-8")
            self.checker.SHARED_HOME = str(missing_home)
            self.checker.SHARED_MIRROR = str(mirror)
            self.checker.GLOSS = str(project)
            glossary = self.checker.load_glossary()
        self.assertEqual(glossary["Hook"], "共通説明")

    def test_non_span_tooltip_is_extracted(self):
        html = '<code class="t" data-d="説明">claims</code>'
        hovered, unresolved = self.checker.hovered(html)
        self.assertEqual(hovered, [("claims", "説明")])
        self.assertEqual(unresolved, 0)

    def test_unreadable_tooltip_is_reported(self):
        html = '<span class="t" data-d="説明"><b>claims</b></span>'
        hovered, unresolved = self.checker.hovered(html)
        self.assertEqual(hovered, [])
        self.assertEqual(unresolved, 1)

    def test_markdown_emphasis_is_ignored_when_comparing(self):
        self.assertEqual(self.checker.norm("**説明**と`code`"), "説明とcode")


if __name__ == "__main__":
    unittest.main()

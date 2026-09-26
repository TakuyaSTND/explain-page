from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

HOOKS_DIR = Path(__file__).resolve().parents[1]
if str(HOOKS_DIR) not in sys.path:
    sys.path.insert(0, str(HOOKS_DIR))

from visual.glossary import load_glossary_snapshot


class GlossaryResolverTests(unittest.TestCase):
    def test_home_shared_is_used_and_project_override_wins(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            home = root / "home.md"
            mirror = root / "mirror.md"
            project = root / "project.md"
            home.write_text(
                "| 用語 | 説明 |\n|---|---|\n| Hook | 共通説明 |\n| M | 共通M |\n",
                encoding="utf-8",
            )
            mirror.write_text(
                "| 用語 | 説明 |\n|---|---|\n| Hook | 古い控え |\n",
                encoding="utf-8",
            )
            project.write_text(
                "| 用語 | 説明 |\n|---|---|\n| M | Project固有M |\n",
                encoding="utf-8",
            )

            snapshot, entries = load_glossary_snapshot(home, mirror, project)

        self.assertEqual(snapshot.shared_source, "home")
        self.assertFalse(snapshot.mirror_matches_home)
        self.assertEqual(snapshot.project_overrides, ("M",))
        self.assertEqual(entries["Hook"].description, "共通説明")
        self.assertEqual(entries["Hook"].provenance, "shared")
        self.assertEqual(entries["M"].description, "Project固有M")
        self.assertEqual(entries["M"].provenance, "project")
        self.assertEqual(snapshot.shared_count, 2)
        self.assertEqual(snapshot.project_count, 1)
        self.assertEqual(snapshot.effective_count, 2)


if __name__ == "__main__":
    unittest.main()

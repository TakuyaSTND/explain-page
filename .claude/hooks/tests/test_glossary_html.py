from __future__ import annotations

import sys
import unittest
from pathlib import Path

HOOKS_DIR = Path(__file__).resolve().parents[1]
if str(HOOKS_DIR) not in sys.path:
    sys.path.insert(0, str(HOOKS_DIR))

from visual.glossary import GlossaryEntry
from visual.glossary_check import check_html


class GlossaryHtmlCheckTests(unittest.TestCase):
    def test_missing_aria_describedby_target_is_reported(self):
        entries = {"Hook": GlossaryEntry("Hook", "説明", "shared")}
        html = '<span class="t" data-d="説明" aria-describedby="missing">Hook</span>'

        result = check_html(html, entries)

        self.assertEqual(len(result.accessibility_errors), 1)
        self.assertIn("missing", result.accessibility_errors[0])

    def test_tooltip_without_keyboard_or_aria_path_is_reported(self):
        entries = {
            "Hook": GlossaryEntry("Hook", "自動で走る仕組み。", "shared")
        }
        html = '<span class="t" data-d="自動で走る仕組み。">Hook</span>'

        result = check_html(html, entries)

        self.assertEqual(len(result.accessibility_errors), 1)
        self.assertIn("Hook", result.accessibility_errors[0])

    def test_second_occurrence_mismatch_is_not_hidden_by_first_correct_one(self):
        entries = {
            "claims": GlossaryEntry(
                term="claims",
                description="資料の主張を1つずつに分けた一覧。",
                provenance="project",
            )
        }
        html = """
<p><span class="t" tabindex="0" data-d="資料の主張を1つずつに分けた一覧。">claims</span></p>
<p><span class="t" tabindex="0" data-d="まったく違う説明">claims</span></p>
"""

        result = check_html(html, entries)

        self.assertEqual(len(result.mismatches), 1)
        self.assertEqual(result.mismatches[0].term, "claims")
        self.assertEqual(result.mismatches[0].occurrence, 2)
        self.assertEqual(result.unresolved, 0)


if __name__ == "__main__":
    unittest.main()

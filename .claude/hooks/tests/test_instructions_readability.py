from __future__ import annotations

import sys
import unittest
from pathlib import Path

HOOKS_DIR = Path(__file__).resolve().parents[1]
if str(HOOKS_DIR) not in sys.path:
    sys.path.insert(0, str(HOOKS_DIR))

from visual.contracts import ExplanationPlan
from visual.instructions import compile_directive


def _build_directive(delivery: str = "local_html", publish_policy: str = "never") -> str:
    html_output = Path(__file__).resolve().parents[2] / "html-output.md"
    plan = ExplanationPlan(
        audience="project_novice",
        depth="deep",
        components=("overview",),
        reason_codes=(),
        provisional=False,
        should_continue=False,
        delivery=delivery,
        publish_policy=publish_policy,
    )
    return compile_directive(plan, html_output)


class ReadabilitySectionTests(unittest.TestCase):
    def test_readability_section_is_present(self):
        directive = _build_directive()

        self.assertIn("[readability]", directive)

    def test_readability_section_present_even_without_local_html_delivery(self):
        # Markdownで答えるだけのターンでも、書き方の規律（readability）は常に出す。
        directive = _build_directive(delivery="markdown", publish_policy="never")

        self.assertIn("[readability]", directive)

    def test_readability_section_covers_all_six_borrowed_points(self):
        directive = _build_directive()

        for required in (
            "定訳",
            "助詞",
            "造語",
            "体言止め",
            "矢印",
            "判断材料",
        ):
            self.assertIn(required, directive)

    def test_readability_section_cites_source_without_a_url(self):
        directive = _build_directive()

        self.assertIn("出所", directive)
        self.assertIn("ja-text-communication", directive)
        self.assertNotIn("https://", directive)

    def test_component_catalog_names_new_widgets(self):
        directive = _build_directive()

        for required in ("`diff`", "`chart`", "`formula`"):
            self.assertIn(required, directive)


if __name__ == "__main__":
    unittest.main()

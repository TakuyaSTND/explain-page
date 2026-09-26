from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

HOOKS_DIR = Path(__file__).resolve().parents[1]
if str(HOOKS_DIR) not in sys.path:
    sys.path.insert(0, str(HOOKS_DIR))

from visual.contracts import ExplanationPlan
from visual.instructions import compile_directive, load_fragments


class InstructionCompilerTests(unittest.TestCase):
    def test_directive_restores_reference_parity_contracts(self):
        html_output = Path(__file__).resolve().parents[2] / "html-output.md"
        plan = ExplanationPlan(
            audience="project_novice",
            depth="deep",
            components=("summary", "decision", "evidence", "glossary", "details"),
            reason_codes=("decision_required",),
            provisional=False,
            should_continue=False,
            delivery="local_html",
            publish_policy="never",
        )

        directive = compile_directive(plan, html_output)

        for required in (
            "data-theme",
            "inline code",
            "provenance footer",
            "3行summary",
            "どこで確かめたか",
            "local evidence path",
            "推奨",
            "warn tone",
            "caption",
            "numeric cell",
            "未包装",
            "Gate",
            "visual smoke",
        ):
            self.assertIn(required, directive)

    def test_full_directive_preserves_existing_html_features(self):
        html_output = Path(__file__).resolve().parents[2] / "html-output.md"
        plan = ExplanationPlan(
            audience="project_novice",
            depth="deep",
            components=("decision", "evidence", "details", "glossary"),
            reason_codes=(),
            provisional=False,
            should_continue=False,
            delivery="local_html",
            publish_policy="never",
        )

        directive = compile_directive(plan, html_output)

        for required in (
            "<pre>",
            "コピーボタン",
            "全部選ぶ",
            "これは違う",
            "実測",
            "仮定",
            "推奨",
            "一次",
            "<details>",
            "CSS token",
            "body背景",
            "logicを実際に走らせる",
        ):
            self.assertIn(required, directive)

    def test_glossary_directive_preserves_hover_markup_and_checker(self):
        html_output = Path(__file__).resolve().parents[2] / "html-output.md"
        plan = ExplanationPlan(
            audience="project_novice",
            depth="deep",
            components=("glossary",),
            reason_codes=(),
            provisional=False,
            should_continue=False,
            delivery="local_html",
            publish_policy="never",
        )

        directive = compile_directive(plan, html_output)

        self.assertIn('class="t"', directive)
        self.assertIn("data-d", directive)
        self.assertIn('tabindex="0"', directive)
        self.assertIn("check_gloss.py", directive)

    def test_real_directive_requires_visual_hierarchy(self):
        html_output = Path(__file__).resolve().parents[2] / "html-output.md"
        plan = ExplanationPlan(
            audience="project_novice",
            depth="deep",
            components=("overview",),
            reason_codes=(),
            provisional=False,
            should_continue=False,
            delivery="local_html",
            publish_policy="never",
        )

        directive = compile_directive(plan, html_output)

        self.assertIn("本文を全部同じ", directive)
        self.assertIn("太字", directive)
        self.assertIn("意味のある色", directive)
        self.assertIn("font", directive)
        self.assertNotIn("外部fontへ依存せず", directive)
        self.assertIn("外部URL", directive)

    def test_real_fragments_require_more_background_terms_and_examples(self):
        html_output = Path(__file__).resolve().parents[2] / "html-output.md"

        fragments = load_fragments(html_output)

        self.assertIn("変更前", fragments["walkthrough"])
        self.assertIn("なぜ今", fragments["walkthrough"])
        self.assertIn("Before/After", fragments["examples"])
        self.assertIn("反例", fragments["examples"])
        self.assertIn("元の専門語", fragments["glossary"])
        self.assertIn("何をする", fragments["glossary"])

    def test_visual_and_decision_fragments_are_compiled_together(self):
        source = """
<!-- HOOK_COMPONENT:walkthrough:START -->
背景・用語・理由・具体例を順に説明する。
<!-- HOOK_COMPONENT:walkthrough:END -->
<!-- HOOK_COMPONENT:visual:START -->
関係を図で示し、図の読み方も説明する。
<!-- HOOK_COMPONENT:visual:END -->
<!-- HOOK_COMPONENT:decision:START -->
選択肢と貼り返す依頼文を用意する。
<!-- HOOK_COMPONENT:decision:END -->
""".strip()
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "html-output.md"
            path.write_text(source, encoding="utf-8")
            plan = ExplanationPlan(
                audience="project_novice",
                depth="guided",
                components=("walkthrough", "visual", "decision"),
                reason_codes=("visual_comparison", "decision_required"),
                provisional=True,
                should_continue=False,
                delivery="local_html",
                publish_policy="never",
            )

            directive = compile_directive(plan, path)

        self.assertIn("audience=project_novice", directive)
        self.assertIn("背景・用語・理由・具体例", directive)
        self.assertIn("関係を図で示し", directive)
        self.assertIn("選択肢と貼り返す依頼文", directive)
        self.assertIn("components=walkthrough,visual,decision", directive)


if __name__ == "__main__":
    unittest.main()

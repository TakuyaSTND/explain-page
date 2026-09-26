"""差し戻しと「記録を作れなかった」の文の見やすさの試験（2026-09-26・V4・V6・名前の1行）。

V4＝停止時の差し戻しで、依頼時と同じ指示文の全文（約4,000字）を繰り返し、理由の1行が
末尾に埋もれていた。いまは計画・直し方・後から増えた部品の書き方と、具体的な理由だけ。
V6＝「外部の依存あり」で記録を作れなかったとき、当たった箇所を添える。
名前の1行＝指示文の「回答集めは〇〇で」の〇〇は利用者の機械ごとの道具＝
branding.QA_PAGE_TOOL が None の配布（公開版）では出さない。
"""
from __future__ import annotations

import sys
from dataclasses import replace
import tempfile
import unittest
from pathlib import Path

HOOKS_DIR = Path(__file__).resolve().parents[1]
if str(HOOKS_DIR) not in sys.path:
    sys.path.insert(0, str(HOOKS_DIR))

from visual import branding  # noqa: E402
from visual.contracts import ExplanationPlan, GlossarySnapshot, HookEnvelope  # noqa: E402
from visual.entrypoint import handle_event  # noqa: E402
from visual.instructions import compile_directive, compile_stop_reminder  # noqa: E402
from visual.policy import load_policy  # noqa: E402
from visual.receipts import build_receipt, describe_skip, receipt_problems  # noqa: E402
from visual.state import StateStore  # noqa: E402

HTML_OUTPUT = Path(__file__).resolve().parents[2] / "html-output.md"
COMMON = {"cwd": "C:/repo", "session_id": "session", "turn_id": "turn"}


def _plan(components):
    return ExplanationPlan(
        audience="project_novice", depth="deep", components=tuple(components),
        reason_codes=("project_novice_default",), provisional=False,
        should_continue=False, delivery="local_html", publish_policy="always",
    )


def _glossary():
    return GlossarySnapshot(
        "home", "shared.md", "shared", "shared", "project",
        "effective", 1, 0, 1, (), (), True,
    )


def _envelope():
    return HookEnvelope(
        1, "claude", "", "PostToolUse", "C:/repo", "",
        "session", "turn", "", "", "", "", "", (), False, 0,
        frozenset({"can_receipt"}), True,
    )


class StopReminderIsShortTests(unittest.TestCase):
    def test_reminder_is_much_shorter_and_keeps_the_plan(self):
        plan = _plan(("overview", "summary", "walkthrough", "examples", "evidence", "glossary", "details"))
        full = compile_directive(plan, HTML_OUTPUT)
        short = compile_stop_reminder(plan, plan.components, HTML_OUTPUT)
        self.assertLess(len(short), len(full) / 3)
        self.assertIn("components=" + ",".join(plan.components), short)
        self.assertIn("reasons=project_novice_default", short)
        self.assertIn("[差し戻し]", short)

    def test_only_components_added_after_the_prompt_get_their_guidance(self):
        plan = _plan(("overview", "decision", "evidence"))
        short = compile_stop_reminder(plan, ("overview", "evidence"), HTML_OUTPUT)
        self.assertIn("[decision]", short)
        self.assertNotIn("[overview]", short)
        self.assertNotIn("[evidence]", short)

    def test_stop_with_a_saved_plan_uses_the_short_reminder(self):
        policy = load_policy(path=None, env={})
        with tempfile.TemporaryDirectory() as td:
            state = StateStore(Path(td) / "state.db")
            handle_event(
                {**COMMON, "hook_event_name": "UserPromptSubmit", "prompt": "この件をHTMLの頁にまとめて"},
                runtime="codex", project_root="C:/repo", policy=policy,
                html_output_path=HTML_OUTPUT, state_store=state,
            )
            stop = handle_event(
                {**COMMON, "hook_event_name": "Stop",
                 "last_assistant_message": "図で比較しました。" + "選択肢を並べて説明します。" * 60,
                 "stop_hook_active": False},
                runtime="codex", project_root="C:/repo", policy=policy,
                html_output_path=HTML_OUTPUT, state_store=state,
            )
        self.assertEqual(stop.get("decision"), "block")
        reason = stop["reason"]
        self.assertIn("[差し戻し]", reason)
        self.assertIn("[receipt_missing]", reason)
        self.assertNotIn("[readability]", reason)  # 決まりの全文は繰り返さない
        self.assertLess(len(reason), 2500)


class ReceiptProblemsAreSpecificTests(unittest.TestCase):
    def _receipt(self, td, required):
        page = Path(td) / "page.html"
        page.write_text('<header data-component="overview"><p>本文</p></header>', encoding="utf-8")
        receipt = build_receipt(
            page, envelope=_envelope(), glossary=_glossary(), glossary_entries={},
            local_root=td, previewed=True, required_components=required,
            visual_smoke_status="pass",
        )
        # 最小の頁は用語の検査の前提（共通の用語集）を満たさない＝ここでは合格の状態にして、
        # 確かめたい条件（部品の変化・頁に無い部品）だけを見る。
        return replace(receipt, gloss_check="pass")

    def test_components_changed_after_publishing_is_named(self):
        with tempfile.TemporaryDirectory() as td:
            receipt = self._receipt(td, ("overview", "progress"))
            problems = receipt_problems(
                receipt, _glossary(), local_root=td, max_artifact_bytes=10_000_000,
                required_components=("overview",),
            )
        self.assertTrue(any("公開のあとで要る部品が変わった" in p for p in problems), problems)

    def test_a_valid_receipt_has_no_problems(self):
        with tempfile.TemporaryDirectory() as td:
            receipt = self._receipt(td, ("overview",))
            problems = receipt_problems(
                receipt, _glossary(), local_root=td, max_artifact_bytes=10_000_000,
                required_components=("overview",),
            )
        self.assertEqual(problems, [])

    def test_missing_part_on_the_page_is_named(self):
        with tempfile.TemporaryDirectory() as td:
            receipt = self._receipt(td, ("overview",))
            problems = receipt_problems(
                receipt, _glossary(), local_root=td, max_artifact_bytes=10_000_000,
                required_components=("overview", "decision"),
            )
        self.assertTrue(any("decision" in p for p in problems), problems)


class SkipReasonShowsWhereItHitTests(unittest.TestCase):
    def test_external_dependency_detail_is_shown(self):
        line = describe_skip(
            "C:/tmp/page.html",
            ValueError("artifact contains an external dependency: 通信のコード: fetch("),
            "C:/tmp",
        )
        self.assertIn("[検品証なし]", line)
        self.assertIn("当たった箇所=通信のコード: fetch(", line)

    def test_plain_reason_still_works(self):
        line = describe_skip("C:/x.html", ValueError("artifact path is outside the approved local root"))
        self.assertIn("承認済みの置き場の外", line)
        self.assertNotIn("当たった箇所", line)


class QaToolLineFollowsBrandingTests(unittest.TestCase):
    def _directive_with(self, value):
        import visual.instructions as instructions

        original = getattr(branding, "QA_PAGE_TOOL", None)
        branding.QA_PAGE_TOOL = value
        try:
            return instructions.compile_directive(_plan(("overview",)), HTML_OUTPUT)
        finally:
            branding.QA_PAGE_TOOL = original

    def test_no_qa_tool_means_no_carve_out_sentence(self):
        directive = self._directive_with(None)
        self.assertNotIn("尋問の回答集め", directive)
        self.assertIn("報告と判断の頁は必ずレンダラーで作る", directive)

    def test_a_named_qa_tool_is_mentioned(self):
        directive = self._directive_with("some-qa-tool")
        self.assertIn("some-qa-tool", directive)
        self.assertIn("尋問の回答集めだけ", directive)


if __name__ == "__main__":
    unittest.main()

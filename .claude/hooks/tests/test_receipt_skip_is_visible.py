"""不具合1・不具合2の回帰検査（2026-08-29）。

不具合1＝承認済みの置き場の外にHTMLを書くと、検品証が作られないのに**何も出なかった**。
不具合2＝計画が markdown のターンでも、指示文が「Artifactで公開し…」と要求していた。

どちらも「黙って間違う」型なので、直したことを検査で固定する。
"""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

HOOKS_DIR = Path(__file__).resolve().parents[1]
if str(HOOKS_DIR) not in sys.path:
    sys.path.insert(0, str(HOOKS_DIR))

from visual.contracts import ExplanationPlan
from visual.entrypoint import handle_event
from visual.instructions import compile_directive, delivery_line
from visual.policy import load_policy
from visual.state import StateStore


def _plan(delivery: str, publish: str) -> ExplanationPlan:
    return ExplanationPlan(
        audience="project_novice",
        depth="deep",
        components=("overview",),
        reason_codes=(),
        provisional=False,
        should_continue=False,
        delivery=delivery,
        publish_policy=publish,
    )


class MarkdownTurnDoesNotDemandPublishTests(unittest.TestCase):
    """不具合2：頁を作らないターンで公開を要求しない。"""

    def test_markdown_delivery_wins_over_publish_always(self):
        self.assertNotIn("Artifactで公開", delivery_line("always", "markdown"))
        self.assertIn("Markdownの文章のまま", delivery_line("always", "markdown"))

    def test_local_html_delivery_still_uses_publish_policy(self):
        self.assertIn("Artifactで公開", delivery_line("always", "local_html"))
        self.assertIn("Local-only", delivery_line("never", "local_html"))
        self.assertIn("1行で尋ね", delivery_line("ask", "local_html"))

    def test_default_argument_keeps_old_behaviour(self):
        # 呼び出し側が delivery を渡さない場合は、これまでどおり publish だけで決める。
        self.assertIn("Artifactで公開", delivery_line("always"))

    def test_compiled_directive_follows_the_plan(self):
        html_output = Path(__file__).resolve().parents[2] / "html-output.md"

        markdown_directive = compile_directive(_plan("markdown", "always"), html_output)
        html_directive = compile_directive(_plan("local_html", "always"), html_output)

        self.assertNotIn("Artifactで公開", markdown_directive)
        self.assertIn("Artifactで公開", html_directive)


class ReceiptSkipIsVisibleTests(unittest.TestCase):
    """不具合1：検品証を作れなかったことを、沈黙でなく文字と記録で出す。"""

    def _run_post_tool_use(self, td: Path, html: Path):
        html_output = Path(__file__).resolve().parents[2] / "html-output.md"
        policy = load_policy(path=None, env={})
        state = StateStore(td / "state.db")
        shared = td / "shared.md"
        mirror = td / "mirror.md"
        project = td / "project.md"
        shared.write_text(
            "| 用語 | 説明 |\n|---|---|\n| Hook | 説明 |\n", encoding="utf-8"
        )
        mirror.write_bytes(shared.read_bytes())
        project.write_text("# project\n", encoding="utf-8")
        approved = td / "approved"
        approved.mkdir(exist_ok=True)
        result = handle_event(
            {
                "cwd": "C:/repo",
                "session_id": "session",
                "turn_id": "turn",
                "hook_event_name": "PostToolUse",
                "tool_name": "Write",
                "tool_input": {"file_path": str(html)},
            },
            runtime="codex",
            project_root="C:/repo",
            policy=policy,
            html_output_path=html_output,
            state_store=state,
            glossary_paths=(shared, mirror, project),
            local_artifact_root=approved,
        )
        return result, state

    def test_outside_the_approved_root_reports_instead_of_staying_silent(self):
        with tempfile.TemporaryDirectory() as tmp:
            td = Path(tmp)
            outside = td / "outside.html"
            outside.write_text(
                "<!doctype html><title>Report</title><p>説明</p>", encoding="utf-8"
            )

            result, state = self._run_post_tool_use(td, outside)

            # ①その場で見える文字が返る
            self.assertTrue(result, "返り値が空＝以前の「黙って降りる」に戻っている")
            self.assertIn("検品証なし", result["systemMessage"])
            self.assertIn("承認済みの置き場の外", result["systemMessage"])
            self.assertIn(
                "検品証なし",
                result["hookSpecificOutput"]["additionalContext"],
            )
            # ②あとから数えられる記録が残る
            skips = state.load_receipt_skips(
                project_hash=self._project_hash("C:/repo")
            )
            self.assertEqual(len(skips), 1)
            self.assertEqual(skips[0][0], str(outside))
            self.assertIn("承認済みの置き場の外", skips[0][1])

    def test_missing_file_also_reports(self):
        with tempfile.TemporaryDirectory() as tmp:
            td = Path(tmp)
            ghost = td / "approved" / "ghost.html"

            result, state = self._run_post_tool_use(td, ghost)

            self.assertIn("見つからない", result["systemMessage"])
            self.assertEqual(
                len(state.load_receipt_skips(project_hash=self._project_hash("C:/repo"))),
                1,
            )

    def test_inside_the_approved_root_is_unchanged(self):
        with tempfile.TemporaryDirectory() as tmp:
            td = Path(tmp)
            approved = td / "approved"
            approved.mkdir()
            inside = approved / "report.html"
            inside.write_text(
                "<!doctype html><title>Report</title><p>説明</p>", encoding="utf-8"
            )

            result, state = self._run_post_tool_use(td, inside)

            # 作れたときは今までどおり何も返さない＝画面を汚さない
            self.assertEqual(result, {})
            self.assertEqual(
                state.load_receipt_skips(project_hash=self._project_hash("C:/repo")),
                (),
            )

    @staticmethod
    def _project_hash(project_root: str) -> str:
        import hashlib
        import os

        normalized = os.path.normcase(os.path.abspath(project_root))
        return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


if __name__ == "__main__":
    unittest.main()

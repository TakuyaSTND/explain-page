"""頁を作らない回の指示文を短くする（2026-09-28 ユーザー承認＝「削る」）の試験。

試験する物＝
  `visual/instructions.py` の compile_directive：頁を作らない回（markdown）は
    見た目の決まりを出さず、頁用の部品の書き方を短い版（INLINE_FRAGMENTS）に替える。
    頁を作る回（local_html）は従来どおり。
  `visual/entrypoint.py` の停止時：依頼時の計画が「頁を作らない」だったのに頁が要ると
    分かった回は、短い差し戻しではなく全文を出す（その回には頁用の書き方が出ていない）。

⚠️本物の承認済みの置き場の state.db は汚さない＝一時フォルダの StateStore を使う。
"""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

HOOKS_DIR = Path(__file__).resolve().parents[1]
CLAUDE_DIR = HOOKS_DIR.parent
if str(HOOKS_DIR) not in sys.path:
    sys.path.insert(0, str(HOOKS_DIR))

from visual.contracts import ExplanationPlan  # noqa: E402
from visual.entrypoint import handle_event  # noqa: E402
from visual.instructions import INLINE_FRAGMENTS, compile_directive  # noqa: E402
from visual.policy import load_policy  # noqa: E402
from visual.state import StateStore  # noqa: E402

HTML_OUTPUT = CLAUDE_DIR / "html-output.md"
ALL = ("overview", "summary", "walkthrough", "examples", "progress", "visual",
       "decision", "evidence", "glossary", "details")


def _plan(delivery):
    return ExplanationPlan(
        audience="project_novice",
        depth="deep",
        components=ALL,
        reason_codes=("project_novice_default",),
        provisional=True,
        should_continue=False,
        delivery=delivery,
        publish_policy="always",
    )


class InlineDirectiveTests(unittest.TestCase):
    def test_markdown_turn_drops_the_page_only_rules(self):
        text = compile_directive(_plan("markdown"), HTML_OUTPUT)
        self.assertNotIn("[visual_style]", text)
        self.assertNotIn('<span class="t"', text)
        self.assertNotIn("<pre>", text)
        self.assertNotIn("<details>", text)
        self.assertIn("[glossary] " + INLINE_FRAGMENTS["glossary"], text)
        self.assertIn("[evidence] " + INLINE_FRAGMENTS["evidence"], text)
        # 頁でも Markdown でも使える書き方はそのまま残る。
        self.assertIn("[walkthrough] ", text)
        self.assertIn("[readability] ", text)

    def test_page_turn_keeps_the_full_rules(self):
        text = compile_directive(_plan("local_html"), HTML_OUTPUT)
        self.assertIn("[visual_style]", text)
        self.assertIn('<span class="t"', text)
        for fragment in INLINE_FRAGMENTS.values():
            if fragment:
                self.assertNotIn(fragment, text)

    def test_markdown_turn_is_much_shorter(self):
        page = compile_directive(_plan("local_html"), HTML_OUTPUT)
        markdown = compile_directive(_plan("markdown"), HTML_OUTPUT)
        self.assertLess(len(markdown), len(page) * 0.6)


class StopFallsBackToTheFullTextTests(unittest.TestCase):
    """依頼時は頁なし→応答が長くて頁が要る、の回は全文で差し戻す。"""

    def _run_turn(self, policy, response):
        with tempfile.TemporaryDirectory() as td:
            state = StateStore(Path(td) / "state.db")
            common = {"cwd": str(CLAUDE_DIR.parent), "session_id": "s-inline", "turn_id": "t1"}
            handle_event(
                {**common, "hook_event_name": "UserPromptSubmit", "prompt": "ありがとう"},
                runtime="claude",
                project_root=str(CLAUDE_DIR.parent),
                policy=policy,
                html_output_path=HTML_OUTPUT,
                state_store=state,
                local_artifact_root=Path(td) / "root",
            )
            return handle_event(
                {**common, "hook_event_name": "Stop", "last_assistant_message": response,
                 "stop_hook_active": False},
                runtime="claude",
                project_root=str(CLAUDE_DIR.parent),
                policy=policy,
                html_output_path=HTML_OUTPUT,
                state_store=state,
                local_artifact_root=Path(td) / "root",
            )

    def test_auto_markdown_prompt_then_long_answer_gets_the_full_text(self):
        policy = replace(load_policy(path=None, env={}), explain_mode="auto")
        result = self._run_turn(policy, "これは長い応答です。" * 90)
        text = json.dumps(result, ensure_ascii=False)
        self.assertIn("block", text)
        self.assertIn("[visual_style]", text)
        self.assertNotIn("[差し戻し]", text)

    def test_always_keeps_the_short_reminder(self):
        policy = replace(load_policy(path=None, env={}), explain_mode="always")
        result = self._run_turn(policy, "これは長い応答です。" * 90)
        text = json.dumps(result, ensure_ascii=False)
        self.assertIn("[差し戻し]", text)
        self.assertNotIn("[visual_style]", text)


if __name__ == "__main__":
    unittest.main()

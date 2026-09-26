from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

HOOKS_DIR = Path(__file__).resolve().parents[1]
if str(HOOKS_DIR) not in sys.path:
    sys.path.insert(0, str(HOOKS_DIR))

from visual.subagents import digest_from_payload


class SubagentDigestTests(unittest.TestCase):
    def test_huge_duration_is_clamped_before_sqlite(self):
        digest = digest_from_payload(
            "hermes",
            {
                "extra": {
                    "parent_turn_id": "turn",
                    "child_session_id": "child",
                    "child_summary": '{"result":"done"}',
                    "duration_ms": "9" * 1000,
                }
            },
        )

        self.assertGreaterEqual(digest.duration_ms, 0)
        self.assertLessEqual(digest.duration_ms, 86_400_000)

    def test_claude_digest_prefers_prompt_id_like_adapter(self):
        digest = digest_from_payload(
            "claude",
            {
                "prompt_id": "parent-prompt",
                "turn_id": "other-turn",
                "agent_id": "child",
                "last_assistant_message": '{"result":"done"}',
            },
        )

        self.assertEqual(digest.parent_turn_id, "parent-prompt")

    def test_digest_redacts_secret_markers_and_bounds_text(self):
        payload = {
            "hook_event_name": "subagent_stop",
            "session_id": "parent",
            "cwd": "C:/repo",
            "extra": {
                "parent_turn_id": "turn",
                "child_session_id": "child",
                "child_summary": json.dumps(
                    {
                        "goal": "G" * 500,
                        "result": "SECRET-CANARY token=abc123 " + "R" * 5000,
                        "evidence": ["E" * 500 for _ in range(20)],
                        "risk": "K" * 500,
                        "needs_human": "N" * 500,
                    }
                ),
                "child_status": "success",
            },
        }

        digest = digest_from_payload("hermes", payload)

        self.assertNotIn("SECRET-CANARY", repr(digest))
        self.assertNotIn("abc123", repr(digest))
        self.assertLessEqual(len(digest.goal), 200)
        self.assertLessEqual(len(digest.result), 1000)
        self.assertLessEqual(len(digest.evidence), 10)
        self.assertTrue(all(len(item) <= 300 for item in digest.evidence))
        self.assertLessEqual(len(digest.risk), 200)
        self.assertLessEqual(len(digest.needs_human), 300)

    def test_claude_and_codex_subagent_stop_share_the_same_schema(self):
        summary = json.dumps(
            {
                "goal": "比較",
                "result": "結果",
                "evidence": ["fixture"],
                "risk": "low",
                "needs_human": "",
            },
            ensure_ascii=False,
        )
        for runtime in ("claude", "codex"):
            with self.subTest(runtime=runtime):
                payload = {
                    "hook_event_name": "SubagentStop",
                    "session_id": "parent-session",
                    "turn_id": "parent-turn",
                    "prompt_id": "parent-turn",
                    "agent_id": "child",
                    "agent_type": "researcher",
                    "last_assistant_message": summary,
                }

                digest = digest_from_payload(runtime, payload)

                self.assertEqual(digest.parent_turn_id, "parent-turn")
                self.assertEqual(digest.child_session_id, "child")
                self.assertEqual(digest.result, "結果")
                self.assertEqual(digest.evidence, ("fixture",))

    def test_hermes_subagent_stop_becomes_small_digest(self):
        summary = {
            "goal": "Hook仕様を確認する",
            "result": "visualとdecisionは組み合わせ可能",
            "evidence": ["official-hooks.md", "test_composer.py"],
            "risk": "medium",
            "needs_human": "採用判断",
        }
        payload = {
            "hook_event_name": "subagent_stop",
            "session_id": "parent-session",
            "extra": {
                "parent_turn_id": "parent-turn",
                "child_session_id": "child-session",
                "child_role": "researcher",
                "child_summary": json.dumps(summary, ensure_ascii=False),
                "child_status": "success",
                "tool_call_history": [
                    {"tool": "read_file", "input": "private raw content"}
                ],
                "duration_ms": 1234,
            },
        }

        digest = digest_from_payload("hermes", payload)

        self.assertEqual(digest.parent_turn_id, "parent-turn")
        self.assertEqual(digest.child_session_id, "child-session")
        self.assertEqual(digest.goal, summary["goal"])
        self.assertEqual(digest.result, summary["result"])
        self.assertEqual(digest.evidence, tuple(summary["evidence"]))
        self.assertEqual(digest.risk, "medium")
        self.assertEqual(digest.needs_human, "採用判断")
        self.assertEqual(digest.status, "success")
        self.assertEqual(digest.duration_ms, 1234)
        self.assertNotIn("private raw content", repr(digest))


if __name__ == "__main__":
    unittest.main()

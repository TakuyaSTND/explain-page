"""出所の分からない記録を指示文に流さない検査（2026-08-31 実害）。

⚠️**ユーザーの言葉に見える文が、こちらの記録に混ざっていた。**
   `subagent_digests_v2` に「作り直さないでいい」「止めず指示文で促すだけにする」という行があり、
   別セッションがそれを見て「ユーザーの承認が記録されている」と読みかけた
   （その場では承認として扱わず照会してきた＝正しい判断だった）。

正体＝子の最後の発言をそのまま `result` に入れていたもので、`agent_type` も `goal` も空だった。
∴誰の言葉か分からない。にもかかわらず次のターンの指示文に `status=success` の結果として
差し込まれていた＝**届いていない発言が、確定した承認として読める**。

∴出所が分からないものには印を付け、内容は渡さない（件数だけ知らせる＝沈黙にはしない）。
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

HOOKS_DIR = Path(__file__).resolve().parents[1]
if str(HOOKS_DIR) not in sys.path:
    sys.path.insert(0, str(HOOKS_DIR))

from visual.subagents import UNATTRIBUTED, digest_from_payload, is_unattributed


class MarkingTests(unittest.TestCase):
    def test_a_bare_message_with_no_agent_type_is_unattributed(self):
        digest = digest_from_payload(
            "claude",
            {"last_assistant_message": "作り直さないでいい", "agent_id": "a1", "prompt_id": "t1"},
        )

        self.assertEqual(digest.goal, UNATTRIBUTED)
        self.assertEqual(digest.status, UNATTRIBUTED)
        self.assertTrue(is_unattributed(digest))
        # ⚠️中身そのものは残す（監査のため）。渡さないのは指示文への差し込みだけ。
        self.assertEqual(digest.result, "作り直さないでいい")

    def test_a_declared_goal_is_kept(self):
        digest = digest_from_payload(
            "claude",
            {
                "last_assistant_message": '{"goal":"調べる","result":"できた"}',
                "agent_id": "a2",
                "prompt_id": "t1",
            },
        )

        self.assertEqual(digest.goal, "調べる")
        self.assertEqual(digest.status, "success")
        self.assertFalse(is_unattributed(digest))

    def test_an_agent_type_is_enough_to_attribute(self):
        digest = digest_from_payload(
            "claude",
            {
                "last_assistant_message": "できた",
                "agent_type": "workflow-subagent",
                "agent_id": "a3",
                "prompt_id": "t1",
            },
        )

        self.assertEqual(digest.goal, "workflow-subagent")
        self.assertFalse(is_unattributed(digest))

    def test_hermes_payloads_are_marked_the_same_way(self):
        digest = digest_from_payload(
            "hermes", {"extra": {"child_summary": "終わった", "child_session_id": "c1"}}
        )

        self.assertTrue(is_unattributed(digest))

    def test_hermes_with_a_role_is_attributed(self):
        digest = digest_from_payload(
            "hermes",
            {"extra": {"child_summary": "終わった", "child_role": "調査係", "child_session_id": "c1"}},
        )

        self.assertEqual(digest.goal, "調査係")
        self.assertFalse(is_unattributed(digest))


class DirectiveTests(unittest.TestCase):
    """指示文の側で、内容を落として件数だけ知らせる。"""

    def test_the_entrypoint_filters_before_building_the_payload(self):
        source = (HOOKS_DIR / "visual" / "entrypoint.py").read_text(encoding="utf-8")

        self.assertIn("named = [item for item in digests if not is_unattributed(item)]", source)
        self.assertIn("dropped = len(digests) - len(named)", source)
        self.assertIn("for item in named", source)

    def test_the_dropped_count_is_still_reported(self):
        # ⚠️黙って落とすと「失敗が沈黙として現れる」型になる＝件数は必ず出す。
        source = (HOOKS_DIR / "visual" / "entrypoint.py").read_text(encoding="utf-8")

        self.assertIn("[subagent_digests_dropped]", source)
        self.assertIn("ユーザーの発言ではない", source)


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.dont_write_bytecode = True

HOOKS_DIR = Path(__file__).resolve().parents[1]
if str(HOOKS_DIR) not in sys.path:
    sys.path.insert(0, str(HOOKS_DIR))

from visual.composer import compose_plan, structure_weight
from visual.contracts import HookEnvelope
from visual.policy import load_policy


class CurrentRegressionTests(unittest.TestCase):
    def test_numbered_list_counts_every_item(self):
        text = "\n".join(f"{i}. item" for i in range(1, 11))
        self.assertEqual(structure_weight(text), 10)

    def test_fenced_code_comments_do_not_count_as_headings(self):
        text = "```python\n" + "\n".join(f"# comment {i}" for i in range(8)) + "\n```"
        self.assertEqual(structure_weight(text), 0)

    def test_record_only_artifact_does_not_require_decision_controls(self):
        envelope = HookEnvelope(
            schema_version=1,
            runtime="claude",
            runtime_version="",
            event="UserPromptSubmit",
            project_root="C:/repo",
            profile_id="",
            session_id="session",
            turn_id="turn",
            invocation_id="",
            user_message="処理フローを図で説明する記録用Artifact。人の判断は不要",
            response_text="",
            response_sha256="",
            transcript_path="",
            changed_paths=(),
            stop_hook_active=False,
            attempt=0,
            capabilities=frozenset({"can_context"}),
            valid_for_state=True,
        )
        plan = compose_plan(envelope, load_policy(path=None, env={}))
        self.assertIn("visual", plan.components)
        self.assertNotIn("decision", plan.components)


if __name__ == "__main__":
    unittest.main()

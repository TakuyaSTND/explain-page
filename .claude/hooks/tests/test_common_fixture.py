from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

HOOKS_DIR = Path(__file__).resolve().parents[1]
if str(HOOKS_DIR) not in sys.path:
    sys.path.insert(0, str(HOOKS_DIR))

from visual.adapters import from_claude, from_codex, from_hermes
from visual.composer import compose_plan
from visual.policy import load_policy


class CommonPilotFixtureTests(unittest.TestCase):
    def test_all_three_runtimes_choose_the_same_components(self):
        fixture_path = Path(__file__).resolve().parent / "fixtures" / "cases.json"
        cases = json.loads(fixture_path.read_text(encoding="utf-8"))
        policy = load_policy(path=None, env={})

        for case in cases:
            with self.subTest(case=case["name"]):
                response = "長い説明。" * int(case.get("response_repeat", 0))
                message = case["message"]
                common = {"cwd": "C:/repo", "session_id": "session"}
                envelopes = {
                    "claude": from_claude(
                        {
                            **common,
                            "hook_event_name": "UserPromptSubmit",
                            "prompt_id": "turn",
                            "prompt": message,
                            "last_assistant_message": response,
                        },
                        "C:/repo",
                    ),
                    "codex": from_codex(
                        {
                            **common,
                            "hook_event_name": "UserPromptSubmit",
                            "turn_id": "turn",
                            "prompt": message,
                            "last_assistant_message": response,
                        },
                        "C:/repo",
                    ),
                    "hermes": from_hermes(
                        {
                            **common,
                            "hook_event_name": "pre_llm_call",
                            "extra": {
                                "turn_id": "turn",
                                "task_id": "task",
                                "user_message": message,
                                "assistant_response": response,
                            },
                        },
                        "C:/repo",
                    ),
                }
                plans = {name: compose_plan(env, policy) for name, env in envelopes.items()}
                component_sets = {plan.components for plan in plans.values()}
                self.assertEqual(len(component_sets), 1)
                components = set(plans["hermes"].components)
                self.assertTrue(set(case["include"]).issubset(components))
                self.assertTrue(set(case["exclude"]).isdisjoint(components))
                if case.get("reason"):
                    self.assertIn(case["reason"], plans["hermes"].reason_codes)


if __name__ == "__main__":
    unittest.main()

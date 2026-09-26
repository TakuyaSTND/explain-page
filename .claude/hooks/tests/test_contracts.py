from __future__ import annotations

import hashlib
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

HOOKS_DIR = Path(__file__).resolve().parents[1]
if str(HOOKS_DIR) not in sys.path:
    sys.path.insert(0, str(HOOKS_DIR))

from visual import branding
from visual.adapters import from_claude, from_codex, from_hermes
from visual.contracts import ArtifactReceipt, ExplanationPlan


class HookEnvelopeAdapterTests(unittest.TestCase):
    def test_direct_transcript_rejects_mismatched_context_metadata(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            claude = root / "claude.jsonl"
            claude.write_text(
                json.dumps(
                    {"type": "session_meta", "session_id": "foreign", "cwd": "C:/foreign"}
                )
                + "\n"
                + json.dumps(
                    {
                        "type": "assistant",
                        "message": {"content": [{"type": "text", "text": "FOREIGN"}]},
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            codex = root / "codex.jsonl"
            codex.write_text(
                json.dumps(
                    {
                        "type": "session_meta",
                        "payload": {"id": "foreign", "cwd": "C:/repo"},
                    }
                )
                + "\n"
                + json.dumps(
                    {
                        "type": "response_item",
                        "payload": {
                            "type": "message",
                            "role": "assistant",
                            "content": [{"type": "output_text", "text": "FOREIGN"}],
                        },
                    }
                )
                + "\n",
                encoding="utf-8",
            )

            claude_envelope = from_claude(
                {
                    "hook_event_name": "Stop",
                    "cwd": "C:/repo",
                    "session_id": "expected",
                    "prompt_id": "turn",
                    "transcript_path": str(claude),
                },
                project_root="C:/repo",
            )
            codex_envelope = from_codex(
                {
                    "hook_event_name": "Stop",
                    "cwd": "C:/repo",
                    "session_id": "expected",
                    "turn_id": "turn",
                    "transcript_path": str(codex),
                },
                project_root="C:/repo",
            )

        self.assertEqual(claude_envelope.response_text, "")
        self.assertEqual(codex_envelope.response_text, "")

    def test_direct_transcript_rejects_mixed_expected_and_foreign_metadata(self):
        with tempfile.TemporaryDirectory() as td:
            transcript = Path(td) / "mixed.jsonl"
            records = [
                {"type": "session_meta", "payload": {"session_id": "expected", "cwd": "C:/repo"}},
                {
                    "type": "response_item",
                    "payload": {
                        "type": "message",
                        "role": "assistant",
                        "content": [{"type": "output_text", "text": "EXPECTED"}],
                    },
                },
                {"type": "session_meta", "payload": {"session_id": "foreign", "cwd": "C:/foreign"}},
                {
                    "type": "response_item",
                    "payload": {
                        "type": "message",
                        "role": "assistant",
                        "content": [{"type": "output_text", "text": "FOREIGN-LATEST"}],
                    },
                },
            ]
            transcript.write_text(
                "\n".join(json.dumps(record) for record in records), encoding="utf-8"
            )
            envelope = from_codex(
                {
                    "hook_event_name": "Stop",
                    "cwd": "C:/repo",
                    "session_id": "expected",
                    "turn_id": "turn",
                    "transcript_path": str(transcript),
                },
                project_root="C:/repo",
            )

        self.assertEqual(envelope.response_text, "")

    def test_codex_discovery_rejects_mixed_session_metadata_in_one_file(self):
        with tempfile.TemporaryDirectory() as td:
            home = Path(td)
            sessions = home / ".codex" / "sessions"
            sessions.mkdir(parents=True)
            target = str(home / "project")
            transcript = sessions / "mixed.jsonl"
            records = [
                {"type": "session_meta", "payload": {"session_id": "expected", "cwd": target}},
                {"type": "session_meta", "payload": {"session_id": "foreign", "cwd": target}},
                {
                    "type": "response_item",
                    "payload": {
                        "type": "message",
                        "role": "assistant",
                        "content": [{"type": "output_text", "text": "FOREIGN-LATEST"}],
                    },
                },
            ]
            transcript.write_text(
                "\n".join(json.dumps(record) for record in records), encoding="utf-8"
            )
            with patch("visual.adapters.Path.home", return_value=home):
                envelope = from_codex(
                    {
                        "hook_event_name": "Stop",
                        "cwd": target,
                        "session_id": "expected",
                        "turn_id": "turn",
                    },
                    project_root=target,
                )

        self.assertEqual(envelope.response_text, "")

    def test_malformed_attempt_and_false_string_do_not_crash_or_flip_true(self):
        payload = {
            "hook_event_name": "Stop",
            "cwd": "C:/repo",
            "session_id": "session",
            "turn_id": "turn",
            "last_assistant_message": "response",
            "attempt": "not-int",
            "stop_hook_active": "false",
        }

        envelope = from_codex(payload, project_root="C:/repo")

        self.assertEqual(envelope.attempt, 0)
        self.assertFalse(envelope.stop_hook_active)

    def test_symlink_escape_is_outside_project_scope(self):
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            project = base / "project"
            outside = base / "outside"
            project.mkdir()
            outside.mkdir()
            link = project / "linked-outside"
            try:
                link.symlink_to(outside, target_is_directory=True)
            except OSError as exc:
                self.skipTest(f"symlink unavailable: {exc}")
            payload = {
                "hook_event_name": "Stop",
                "cwd": str(link),
                "session_id": "session",
                "turn_id": "turn",
                "last_assistant_message": "response",
            }

            envelope = from_codex(payload, project_root=str(project))

        self.assertFalse(envelope.valid_for_state)

    def test_hermes_subagent_stop_uses_parent_turn_id(self):
        payload = {
            "hook_event_name": "subagent_stop",
            "cwd": "C:/repo",
            "session_id": "parent-session",
            "extra": {
                "parent_turn_id": "parent-turn",
                "child_session_id": "child",
                "child_summary": "summary",
            },
        }

        envelope = from_hermes(payload, project_root="C:/repo")

        self.assertEqual(envelope.turn_id, "parent-turn")
        self.assertTrue(envelope.valid_for_state)
        self.assertIn("can_subagent", envelope.capabilities)

    def test_payload_outside_project_is_not_valid_for_state(self):
        payload = {
            "hook_event_name": "Stop",
            "cwd": "C:/other-project",
            "session_id": "foreign-session",
            "turn_id": "foreign-turn",
            "last_assistant_message": "別Projectの回答",
        }

        envelope = from_codex(payload, project_root="C:/repo")

        self.assertFalse(envelope.valid_for_state)

    def test_hermes_pre_verify_carries_final_response_and_changed_paths(self):
        payload = {
            "hook_event_name": "pre_verify",
            "cwd": "C:/repo",
            "session_id": "hermes-session",
            "extra": {
                "turn_id": "turn-h2",
                "final_response": "実装結果の説明",
                "changed_paths": ["src/a.py", "tests/test_a.py"],
                "attempt": 1,
                "coding": True,
                "model": "gpt-test",
                "platform": "desktop",
            },
        }

        envelope = from_hermes(payload, project_root="C:/repo")

        self.assertEqual(envelope.response_text, "実装結果の説明")
        self.assertEqual(envelope.changed_paths, ("src/a.py", "tests/test_a.py"))
        self.assertEqual(envelope.attempt, 1)
        self.assertIn("can_continue", envelope.capabilities)

    def test_hermes_pre_llm_call_uses_extra_turn_and_user_message(self):
        payload = {
            "hook_event_name": "pre_llm_call",
            "cwd": "C:/repo",
            "session_id": "hermes-session",
            "extra": {
                "turn_id": "turn-h1",
                "task_id": "task-h1",
                "user_message": "3案を図で比較して最後に選びたい",
                "model": "gpt-test",
                "platform": "desktop",
            },
        }

        envelope = from_hermes(payload, project_root="C:/repo")

        self.assertEqual(envelope.runtime, "hermes")
        self.assertEqual(envelope.event, "pre_llm_call")
        self.assertEqual(envelope.turn_id, "turn-h1")
        self.assertEqual(envelope.user_message, payload["extra"]["user_message"])
        self.assertEqual(envelope.response_text, "")
        self.assertIn("can_context", envelope.capabilities)
        self.assertTrue(envelope.valid_for_state)

    def test_claude_stop_uses_direct_last_assistant_message(self):
        text = "Claudeの最終説明"
        payload = {
            "hook_event_name": "Stop",
            "cwd": "C:/repo",
            "session_id": "claude-session",
            "prompt_id": "prompt-1",
            "last_assistant_message": text,
            "transcript_path": "C:/must-not-be-read.jsonl",
            "stop_hook_active": False,
        }

        envelope = from_claude(payload, project_root="C:/repo")

        self.assertEqual(envelope.runtime, "claude")
        self.assertEqual(envelope.turn_id, "prompt-1")
        self.assertEqual(envelope.response_text, text)
        self.assertTrue(envelope.valid_for_state)
        self.assertIn("can_continue", envelope.capabilities)

    def test_codex_stop_uses_direct_last_assistant_message(self):
        text = "初心者向けの説明本文"
        payload = {
            "hook_event_name": "Stop",
            "cwd": "C:/repo",
            "session_id": "codex-session",
            "turn_id": "turn-1",
            "last_assistant_message": text,
            "transcript_path": "C:/must-not-be-read.jsonl",
            "stop_hook_active": False,
            "permission_mode": "default",
        }

        envelope = from_codex(payload, project_root="C:/repo")

        self.assertEqual(envelope.runtime, "codex")
        self.assertEqual(envelope.event, "Stop")
        self.assertEqual(envelope.project_root, "C:/repo")
        self.assertEqual(envelope.session_id, "codex-session")
        self.assertEqual(envelope.turn_id, "turn-1")
        self.assertEqual(envelope.response_text, text)
        self.assertEqual(
            envelope.response_sha256,
            hashlib.sha256(text.encode("utf-8")).hexdigest(),
        )
        self.assertTrue(envelope.valid_for_state)
        self.assertIn("can_continue", envelope.capabilities)

    def test_claude_falls_back_to_last_assistant_text_in_jsonl(self):
        with tempfile.TemporaryDirectory() as td:
            transcript = Path(td) / "claude.jsonl"
            transcript.write_text(
                "\n".join(
                    [
                        json.dumps({"type": "user", "message": {"content": "質問"}}),
                        json.dumps(
                            {
                                "type": "assistant",
                                "message": {"content": [{"type": "text", "text": "回答"}]},
                            }
                        ),
                    ]
                ),
                encoding="utf-8",
            )

            envelope = from_claude(
                {
                    "hook_event_name": "Stop",
                    "cwd": "C:/repo",
                    "session_id": "session",
                    "prompt_id": "turn",
                    "transcript_path": str(transcript),
                },
                project_root="C:/repo",
            )

        self.assertEqual(envelope.response_text, "回答")

    def test_direct_response_fields_precede_transcript_fallback(self):
        with tempfile.TemporaryDirectory() as td:
            transcript = Path(td) / "claude.jsonl"
            transcript.write_text(
                json.dumps(
                    {
                        "type": "assistant",
                        "message": {"content": [{"type": "text", "text": "記録"}]},
                    }
                ),
                encoding="utf-8",
            )
            envelope = from_claude(
                {
                    "hook_event_name": "Stop",
                    "cwd": "C:/repo",
                    "session_id": "session",
                    "prompt_id": "turn",
                    "last_assistant_message": "直接回答",
                    "final_response": "別の直接回答",
                    "transcript_path": str(transcript),
                },
                project_root="C:/repo",
            )

        self.assertEqual(envelope.response_text, "直接回答")

    def test_malformed_transcript_fallback_is_empty(self):
        with tempfile.TemporaryDirectory() as td:
            transcript = Path(td) / "malformed.jsonl"
            transcript.write_text("not-json\n{\n", encoding="utf-8")
            with patch("visual.adapters.Path.home", return_value=Path(td)):
                envelope = from_codex(
                    {
                        "hook_event_name": "Stop",
                        "cwd": "C:/repo",
                        "session_id": "session",
                        "turn_id": "turn",
                        "transcript_path": str(transcript),
                    },
                    project_root="C:/repo",
                )
        self.assertEqual(envelope.response_text, "")

    def test_codex_uses_codex_transcript_format_without_claude_parser(self):
        with tempfile.TemporaryDirectory() as td:
            transcript = Path(td) / "codex.jsonl"
            transcript.write_text(
                json.dumps(
                    {
                        "type": "response_item",
                        "payload": {
                            "type": "message",
                            "role": "assistant",
                            "content": [{"type": "output_text", "text": "Codex回答"}],
                        },
                    }
                ),
                encoding="utf-8",
            )
            envelope = from_codex(
                {
                    "hook_event_name": "Stop",
                    "cwd": "C:/repo",
                    "session_id": "session",
                    "turn_id": "turn",
                    "transcript_path": str(transcript),
                },
                project_root="C:/repo",
            )

        self.assertEqual(envelope.response_text, "Codex回答")

    def test_codex_does_not_parse_claude_shaped_transcript(self):
        with tempfile.TemporaryDirectory() as td:
            transcript = Path(td) / "claude-shaped.jsonl"
            transcript.write_text(
                json.dumps(
                    {
                        "type": "assistant",
                        "message": {"content": [{"type": "text", "text": "Claudeだけ"}]},
                    }
                ),
                encoding="utf-8",
            )
            with patch("visual.adapters.Path.home", return_value=Path(td)):
                envelope = from_codex(
                    {
                        "hook_event_name": "Stop",
                        "cwd": "C:/repo",
                        "session_id": "session",
                        "turn_id": "turn",
                        "transcript_path": str(transcript),
                    },
                    project_root="C:/repo",
                )

        self.assertEqual(envelope.response_text, "")

    def test_transcript_fallback_respects_max_bytes_for_trusted_path(self):
        with tempfile.TemporaryDirectory() as td:
            transcript = Path(td) / "too-large.jsonl"
            transcript.write_text(
                "x" * 256
                + "\n"
                + json.dumps(
                    {
                        "type": "assistant",
                        "message": {"content": [{"type": "text", "text": "late"}]},
                    }
                ),
                encoding="utf-8",
            )
            envelope = from_claude(
                {
                    "hook_event_name": "Stop",
                    "cwd": "C:/repo",
                    "session_id": "session",
                    "prompt_id": "turn",
                    "transcript_path": str(transcript),
                },
                project_root="C:/repo",
                max_transcript_bytes=64,
            )

        self.assertEqual(envelope.response_text, "")

    def test_codex_session_discovery_checks_cwd_and_only_newest_eight_files(self):
        with tempfile.TemporaryDirectory() as td:
            home = Path(td)
            sessions = home / ".codex" / "sessions"
            sessions.mkdir(parents=True)
            target = str(home / "project")
            for index in range(9):
                path = sessions / f"session-{index}.jsonl"
                path.write_text(
                    json.dumps(
                        {
                            "type": "session_meta",
                            "payload": {"cwd": target if index == 0 else "C:/other"},
                        }
                    )
                    + "\n"
                    + json.dumps(
                        {
                            "type": "response_item",
                            "payload": {
                                "type": "message",
                                "role": "assistant",
                                "content": [{"type": "output_text", "text": f"答{index}"}],
                            },
                        }
                    ),
                    encoding="utf-8",
                )
                os.utime(path, (100 + index, 100 + index))

            with patch("visual.adapters.Path.home", return_value=home):
                envelope = from_codex(
                    {
                        "hook_event_name": "Stop",
                        "cwd": target,
                        "session_id": "session",
                        "turn_id": "turn",
                    },
                    project_root=target,
                )

        self.assertEqual(envelope.response_text, "")

    def test_codex_session_discovery_accepts_legacy_turn_context_cwd(self):
        with tempfile.TemporaryDirectory() as td:
            home = Path(td)
            sessions = home / ".codex" / "sessions"
            sessions.mkdir(parents=True)
            target = str(home / "project")
            transcript = sessions / "legacy-turn-context.jsonl"
            transcript.write_text(
                json.dumps(
                    {"type": "turn_context", "payload": {"cwd": target}}
                )
                + "\n"
                + json.dumps(
                    {
                        "type": "response_item",
                        "payload": {
                            "type": "message",
                            "role": "assistant",
                            "content": [{"type": "output_text", "text": "legacy"}],
                        },
                    }
                ),
                encoding="utf-8",
            )

            with patch("visual.adapters.Path.home", return_value=home):
                envelope = from_codex(
                    {
                        "hook_event_name": "Stop",
                        "cwd": target,
                        "session_id": "session",
                        "turn_id": "turn",
                    },
                    project_root=target,
                )

        self.assertEqual(envelope.response_text, "legacy")

    def test_codex_turn_context_with_foreign_session_id_is_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            home = Path(td)
            sessions = home / ".codex" / "sessions"
            sessions.mkdir(parents=True)
            target = str(home / "project")
            transcript = sessions / "foreign-turn-context.jsonl"
            transcript.write_text(
                json.dumps(
                    {
                        "type": "turn_context",
                        "payload": {
                            "cwd": target,
                            "session_id": "foreign-session",
                        },
                    }
                )
                + "\n"
                + json.dumps(
                    {
                        "type": "response_item",
                        "payload": {
                            "type": "message",
                            "role": "assistant",
                            "content": [{"type": "output_text", "text": "foreign"}],
                        },
                    }
                ),
                encoding="utf-8",
            )

            with patch("visual.adapters.Path.home", return_value=home):
                envelope = from_codex(
                    {
                        "hook_event_name": "Stop",
                        "cwd": target,
                        "session_id": "expected-session",
                        "turn_id": "turn",
                    },
                    project_root=target,
                )

        self.assertEqual(envelope.response_text, "")

    def test_codex_nested_turn_context_metadata_is_bound(self):
        variants = (
            {
                "cwd": "TARGET",
                "metadata": {"session_id": "foreign-session"},
            },
            {
                "metadata": {
                    "cwd": "TARGET",
                    "session_id": "foreign-session",
                }
            },
            {
                "turn_context": {
                    "cwd": "TARGET",
                    "session_id": "foreign-session",
                }
            },
        )
        for index, payload_template in enumerate(variants):
            with self.subTest(index=index), tempfile.TemporaryDirectory() as td:
                home = Path(td)
                sessions = home / ".codex" / "sessions"
                sessions.mkdir(parents=True)
                target = str(home / "project")
                payload = json.loads(
                    json.dumps(payload_template).replace("TARGET", target.replace("\\", "\\\\"))
                )
                transcript = sessions / f"nested-{index}.jsonl"
                transcript.write_text(
                    json.dumps({"type": "turn_context", "payload": payload})
                    + "\n"
                    + json.dumps(
                        {
                            "type": "response_item",
                            "payload": {
                                "type": "message",
                                "role": "assistant",
                                "content": [{"type": "output_text", "text": "foreign"}],
                            },
                        }
                    ),
                    encoding="utf-8",
                )
                with patch("visual.adapters.Path.home", return_value=home):
                    envelope = from_codex(
                        {
                            "hook_event_name": "Stop",
                            "cwd": target,
                            "session_id": "expected-session",
                            "turn_id": "turn",
                        },
                        project_root=target,
                    )

                self.assertEqual(envelope.response_text, "")

    def test_codex_discovery_binds_cwd_and_session_id(self):
        with tempfile.TemporaryDirectory() as td:
            home = Path(td)
            sessions = home / ".codex" / "sessions"
            sessions.mkdir(parents=True)
            target = str(home / "project")

            wrong = sessions / "newer-wrong-session.jsonl"
            wrong.write_text(
                json.dumps(
                    {
                        "type": "session_meta",
                        "payload": {"cwd": target, "session_id": "wrong-session"},
                    }
                )
                + "\n"
                + json.dumps(
                    {
                        "type": "response_item",
                        "payload": {
                            "type": "message",
                            "role": "assistant",
                            "content": [{"type": "output_text", "text": "wrong"}],
                        },
                    }
                ),
                encoding="utf-8",
            )
            matching = sessions / "older-matching-session.jsonl"
            matching.write_text(
                json.dumps(
                    {
                        "type": "session_meta",
                        "payload": {"cwd": target, "session_id": "target-session"},
                    }
                )
                + "\n"
                + json.dumps(
                    {
                        "type": "response_item",
                        "payload": {
                            "type": "message",
                            "role": "assistant",
                            "content": [{"type": "output_text", "text": "matching"}],
                        },
                    }
                ),
                encoding="utf-8",
            )
            os.utime(wrong, (200, 200))
            os.utime(matching, (100, 100))

            with patch("visual.adapters.Path.home", return_value=home):
                envelope = from_codex(
                    {
                        "hook_event_name": "Stop",
                        "cwd": target,
                        "session_id": "target-session",
                        "turn_id": "turn",
                    },
                    project_root=target,
                )

        self.assertEqual(envelope.response_text, "matching")

    def test_v3_receipt_metadata_is_optional_for_legacy_constructors(self):
        legacy = ArtifactReceipt(
            "hermes", "C:/repo", "session", "turn", "report.html", "sha", 1,
            "now", "pass", "gloss", "home+project", "pass", True, "local",
        )
        plan = ExplanationPlan(
            "project_novice", "deep", ("overview",), (), False, False,
            "local_html", "never", (branding.LEGACY_ENV_MIN,),
        )

        self.assertEqual(legacy.required_components, ())
        self.assertEqual(plan.deprecated_aliases, (branding.LEGACY_ENV_MIN,))


if __name__ == "__main__":
    unittest.main()

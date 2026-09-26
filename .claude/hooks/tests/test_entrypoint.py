from __future__ import annotations

import json
import hashlib
import os
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

HOOKS_DIR = Path(__file__).resolve().parents[1]
if str(HOOKS_DIR) not in sys.path:
    sys.path.insert(0, str(HOOKS_DIR))

from visual import branding
from visual.contracts import HookEnvelope
from visual.entrypoint import build_preflight_context, handle_event
from visual.policy import load_policy
from visual.state import StateStore


class EntrypointTests(unittest.TestCase):
    def test_unverified_artifact_marker_does_not_bypass_stop(self):
        html_output = Path(__file__).resolve().parents[2] / "html-output.md"
        policy = load_policy(path=None, env={})
        with tempfile.TemporaryDirectory() as td:
            state = StateStore(Path(td) / "state.db")
            common = {"cwd": "C:/repo", "session_id": "session", "turn_id": "turn"}
            handle_event(
                {**common, "hook_event_name": "UserPromptSubmit", "prompt": "3案を図で比較して"},
                runtime="codex", project_root="C:/repo", policy=policy,
                html_output_path=html_output, state_store=state,
            )
            result = handle_event(
                {
                    **common,
                    "hook_event_name": "Stop",
                    "last_assistant_message": "<title>fake artifact</title>",
                    "stop_hook_active": False,
                },
                runtime="codex", project_root="C:/repo", policy=policy,
                html_output_path=html_output, state_store=state,
            )

        self.assertEqual(result.get("decision"), "block")

    def test_command_off_mode_does_not_create_state_file(self):
        script = Path(__file__).resolve().parents[1] / "understanding-composer.py"
        project_root = Path(__file__).resolve().parents[3]
        with tempfile.TemporaryDirectory() as td:
            state_path = Path(td) / "state.db"
            completed = subprocess.run(
                [
                    sys.executable,
                    str(script),
                    "--runtime",
                    "codex",
                    "--project-root",
                    str(project_root),
                    "--state-path",
                    str(state_path),
                ],
                input=json.dumps(
                    {
                        "hook_event_name": "UserPromptSubmit",
                        "cwd": str(project_root),
                        "session_id": "session",
                        "turn_id": "turn",
                        "prompt": "説明して",
                    }
                ),
                text=True,
                encoding="utf-8",
                capture_output=True,
                env={**os.environ, branding.ENV_MODE: "off"},
                check=False,
            )

        self.assertEqual(completed.returncode, 0)
        self.assertEqual(completed.stdout, "")
        self.assertFalse(state_path.exists())

    def test_disabled_policy_returns_no_context_and_saves_no_plan(self):
        html_output = Path(__file__).resolve().parents[2] / "html-output.md"
        policy = load_policy(path=None, env={branding.ENV_MODE: "off"})
        with tempfile.TemporaryDirectory() as td:
            state = StateStore(Path(td) / "state.db")
            result = handle_event(
                {
                    "hook_event_name": "UserPromptSubmit",
                    "cwd": "C:/repo",
                    "session_id": "session",
                    "turn_id": "turn",
                    "prompt": "説明して",
                },
                runtime="codex",
                project_root="C:/repo",
                policy=policy,
                html_output_path=html_output,
                state_store=state,
            )

        self.assertEqual(result, {})

    def test_hermes_non_coding_pre_verify_does_not_continue(self):
        html_output = Path(__file__).resolve().parents[2] / "html-output.md"
        policy = load_policy(path=None, env={})
        with tempfile.TemporaryDirectory() as td:
            state = StateStore(Path(td) / "state.db")
            common = {"cwd": "C:/repo", "session_id": "session"}
            handle_event(
                {
                    **common,
                    "hook_event_name": "pre_llm_call",
                    "extra": {"turn_id": "turn", "user_message": "3案を図で比較して"},
                },
                runtime="hermes", project_root="C:/repo", policy=policy,
                html_output_path=html_output, state_store=state,
            )
            result = handle_event(
                {
                    **common,
                    "hook_event_name": "pre_verify",
                    "extra": {
                        "turn_id": "turn",
                        "final_response": "説明だけ",
                        "coding": False,
                        "attempt": 0,
                    },
                },
                runtime="hermes", project_root="C:/repo", policy=policy,
                html_output_path=html_output, state_store=state,
            )

        self.assertEqual(result, {})

    def test_hermes_pre_verify_uses_continue_wire_shape(self):
        html_output = Path(__file__).resolve().parents[2] / "html-output.md"
        policy = load_policy(path=None, env={})
        with tempfile.TemporaryDirectory() as td:
            state = StateStore(Path(td) / "state.db")
            common = {
                "cwd": "C:/repo",
                "session_id": "session",
            }
            handle_event(
                {
                    **common,
                    "hook_event_name": "pre_llm_call",
                    "extra": {
                        "turn_id": "turn",
                        "user_message": "3案を図で比較して選びたい",
                    },
                },
                runtime="hermes",
                project_root="C:/repo",
                policy=policy,
                html_output_path=html_output,
                state_store=state,
            )
            result = handle_event(
                {
                    **common,
                    "hook_event_name": "pre_verify",
                    "extra": {
                        "turn_id": "turn",
                        "final_response": "説明文だけです。",
                        "coding": True,
                        "attempt": 0,
                    },
                },
                runtime="hermes",
                project_root="C:/repo",
                policy=policy,
                html_output_path=html_output,
                state_store=state,
            )

        self.assertEqual(result.get("action"), "continue")
        self.assertIn("visual", result.get("message", ""))
        self.assertNotIn("decision", result)

    def test_unpreviewed_receipt_does_not_suppress_fallback(self):
        html_output = Path(__file__).resolve().parents[2] / "html-output.md"
        policy = load_policy(path=None, env={})
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            state = StateStore(root / "state.db")
            html = root / "report.html"
            html.write_text("<!doctype html><title>Report</title><p>説明</p>", encoding="utf-8")
            shared = root / "shared.md"
            mirror = root / "mirror.md"
            project = root / "project.md"
            shared.write_text("| 用語 | 説明 |\n|---|---|\n| Hook | 説明 |\n", encoding="utf-8")
            mirror.write_bytes(shared.read_bytes())
            project.write_text("# project\n", encoding="utf-8")
            common = {"cwd": "C:/repo", "session_id": "session", "turn_id": "turn"}
            handle_event(
                {**common, "hook_event_name": "UserPromptSubmit", "prompt": "3案を図で比較して選びたい"},
                runtime="codex", project_root="C:/repo", policy=policy,
                html_output_path=html_output, state_store=state,
            )
            handle_event(
                {**common, "hook_event_name": "PostToolUse", "tool_name": "Write", "tool_input": {"file_path": str(html)}},
                runtime="codex", project_root="C:/repo", policy=policy,
                html_output_path=html_output, state_store=state,
                glossary_paths=(shared, mirror, project), local_artifact_root=root,
            )
            result = handle_event(
                {**common, "hook_event_name": "Stop", "last_assistant_message": "HTMLを書きました。", "stop_hook_active": False},
                runtime="codex", project_root="C:/repo", policy=policy,
                html_output_path=html_output, state_store=state,
            )

        self.assertEqual(result["decision"], "block")

    def test_failed_glossary_receipt_does_not_suppress_fallback(self):
        html_output = Path(__file__).resolve().parents[2] / "html-output.md"
        policy = load_policy(path=None, env={})
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            state = StateStore(root / "state.db")
            html = root / "bad.html"
            html.write_text(
                '<span class="t" tabindex="0" data-d="誤った説明">Hook</span>',
                encoding="utf-8",
            )
            shared = root / "shared.md"
            mirror = root / "mirror.md"
            project = root / "project.md"
            shared.write_text(
                "| 用語 | 説明 |\n|---|---|\n| Hook | 正しい説明 |\n",
                encoding="utf-8",
            )
            mirror.write_bytes(shared.read_bytes())
            project.write_text("# project\n", encoding="utf-8")
            common = {"cwd": "C:/repo", "session_id": "session", "turn_id": "turn"}
            handle_event(
                {**common, "hook_event_name": "UserPromptSubmit", "prompt": "3案を図で比較して選びたい"},
                runtime="codex",
                project_root="C:/repo",
                policy=policy,
                html_output_path=html_output,
                state_store=state,
            )
            handle_event(
                {
                    **common,
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
                local_artifact_root=root,
            )
            result = handle_event(
                {
                    **common,
                    "hook_event_name": "Stop",
                    "last_assistant_message": "HTMLを作りました。",
                    "stop_hook_active": False,
                },
                runtime="codex",
                project_root="C:/repo",
                policy=policy,
                html_output_path=html_output,
                state_store=state,
            )

        self.assertEqual(result["decision"], "block")

    def test_parent_fallback_includes_child_digest_but_not_raw_history(self):
        html_output = Path(__file__).resolve().parents[2] / "html-output.md"
        policy = load_policy(path=None, env={})
        with tempfile.TemporaryDirectory() as td:
            store = StateStore(Path(td) / "state.db")
            common = {
                "cwd": "C:/repo",
                "session_id": "session",
            }
            handle_event(
                {
                    **common,
                    "hook_event_name": "pre_llm_call",
                    "extra": {
                        "turn_id": "parent-turn",
                        "user_message": "subagentの結果を図でまとめて対応を選びたい",
                    },
                },
                runtime="hermes",
                project_root="C:/repo",
                policy=policy,
                html_output_path=html_output,
                state_store=store,
            )
            handle_event(
                {
                    **common,
                    "hook_event_name": "subagent_stop",
                    "extra": {
                        "turn_id": "parent-turn",
                        "parent_turn_id": "parent-turn",
                        "child_session_id": "child",
                        "child_summary": json.dumps(
                            {
                                "goal": "比較",
                                "result": "案Bが最も分かりやすい",
                                "evidence": ["fixture"],
                                "risk": "low",
                                "needs_human": "案を選ぶ",
                            },
                            ensure_ascii=False,
                        ),
                        "child_status": "success",
                        "tool_call_history": [{"raw": "private-history"}],
                    },
                },
                runtime="hermes",
                project_root="C:/repo",
                policy=policy,
                html_output_path=html_output,
                state_store=store,
            )
            result = handle_event(
                {
                    **common,
                    "hook_event_name": "pre_verify",
                    "extra": {
                        "turn_id": "parent-turn",
                        "final_response": "説明だけです",
                        "changed_paths": ["src/a.py"],
                        "coding": True,
                        "attempt": 0,
                    },
                },
                runtime="hermes",
                project_root="C:/repo",
                policy=policy,
                html_output_path=html_output,
                state_store=store,
            )

        self.assertIn("案Bが最も分かりやすい", result["message"])
        self.assertIn("progress", result["message"])
        self.assertNotIn("private-history", result["message"])

    def test_hermes_subagent_stop_is_saved_without_raw_tool_history(self):
        html_output = Path(__file__).resolve().parents[2] / "html-output.md"
        policy = load_policy(path=None, env={})
        with tempfile.TemporaryDirectory() as td:
            store = StateStore(Path(td) / "state.db")
            payload = {
                "hook_event_name": "subagent_stop",
                "cwd": "C:/repo",
                "session_id": "parent-session",
                "extra": {
                    "turn_id": "parent-turn",
                    "parent_turn_id": "parent-turn",
                    "child_session_id": "child",
                    "child_role": "researcher",
                    "child_summary": json.dumps(
                        {
                            "goal": "比較",
                            "result": "visualとdecisionを併用",
                            "evidence": ["fixture"],
                            "risk": "low",
                            "needs_human": "",
                        },
                        ensure_ascii=False,
                    ),
                    "child_status": "success",
                    "tool_call_history": [{"raw": "private"}],
                    "duration_ms": 20,
                },
            }

            result = handle_event(
                payload,
                runtime="hermes",
                project_root="C:/repo",
                policy=policy,
                html_output_path=html_output,
                state_store=store,
            )
            normalized = os.path.normcase(os.path.abspath("C:/repo"))
            project_hash = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
            digests = store.load_digests(
                runtime="hermes",
                profile_id="",
                session_id="parent-session",
                project_hash=project_hash,
                parent_turn_id="parent-turn",
            )

        self.assertEqual(result, {})
        self.assertEqual(len(digests), 1)
        self.assertEqual(digests[0].result, "visualとdecisionを併用")
        self.assertNotIn("private", repr(digests[0]))

    def test_post_tool_receipt_prevents_stop_regeneration(self):
        html_output = Path(__file__).resolve().parents[2] / "html-output.md"
        policy = load_policy(path=None, env={})
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            state = StateStore(root / "state.db")
            html = root / "report.html"
            html.write_text("<!doctype html><title>Report</title><p>説明</p>", encoding="utf-8")
            shared = root / "shared.md"
            mirror = root / "mirror.md"
            project = root / "project.md"
            shared.write_text("| 用語 | 説明 |\n|---|---|\n| Hook | 説明 |\n", encoding="utf-8")
            mirror.write_bytes(shared.read_bytes())
            project.write_text("# project\n", encoding="utf-8")
            common = {
                "cwd": "C:/repo",
                "session_id": "session",
                "turn_id": "turn",
            }
            handle_event(
                {
                    **common,
                    "hook_event_name": "UserPromptSubmit",
                    "prompt": "3案を図で比較して最後に選びたい",
                },
                runtime="codex",
                project_root="C:/repo",
                policy=policy,
                html_output_path=html_output,
                state_store=state,
            )
            handle_event(
                {
                    **common,
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
                local_artifact_root=root,
            )
            handle_event(
                {
                    **common,
                    "hook_event_name": "PostToolUse",
                    "tool_name": "open_preview",
                    "tool_input": {"path": str(html)},
                },
                runtime="codex",
                project_root="C:/repo",
                policy=policy,
                html_output_path=html_output,
                state_store=state,
                glossary_paths=(shared, mirror, project),
                local_artifact_root=root,
            )
            result = handle_event(
                {
                    **common,
                    "hook_event_name": "Stop",
                    "last_assistant_message": "最終説明",
                    "stop_hook_active": False,
                },
                runtime="codex",
                project_root="C:/repo",
                policy=policy,
                html_output_path=html_output,
                state_store=state,
                glossary_paths=(shared, mirror, project),
                local_artifact_root=root,
            )

        self.assertEqual(result.get("decision"), "block")
        self.assertIn("decision", result.get("reason", ""))
        self.assertIn("visual", result.get("reason", ""))

    def test_command_preflight_and_stop_share_state_across_processes(self):
        script = Path(__file__).resolve().parents[1] / "understanding-composer.py"
        project_root = Path(__file__).resolve().parents[3]
        with tempfile.TemporaryDirectory() as td:
            state_path = Path(td) / "state.db"
            base_command = [
                sys.executable,
                str(script),
                "--runtime",
                "codex",
                "--project-root",
                str(project_root),
                "--state-path",
                str(state_path),
            ]
            preflight = {
                "hook_event_name": "UserPromptSubmit",
                "cwd": str(project_root),
                "session_id": "session",
                "turn_id": "turn",
                "prompt": "3案を図で比較して最後に選びたい",
            }
            stop = {
                "hook_event_name": "Stop",
                "cwd": str(project_root),
                "session_id": "session",
                "turn_id": "turn",
                "last_assistant_message": "説明だけです。",
                "stop_hook_active": False,
            }
            pre = subprocess.run(
                base_command,
                input=json.dumps(preflight, ensure_ascii=False),
                text=True,
                encoding="utf-8",
                capture_output=True,
                check=False,
            )
            first = subprocess.run(
                base_command,
                input=json.dumps(stop, ensure_ascii=False),
                text=True,
                encoding="utf-8",
                capture_output=True,
                check=False,
            )
            second = subprocess.run(
                base_command,
                input=json.dumps(stop, ensure_ascii=False),
                text=True,
                encoding="utf-8",
                capture_output=True,
                check=False,
            )

        self.assertEqual(pre.returncode, 0, pre.stderr)
        self.assertEqual(first.returncode, 0, first.stderr)
        self.assertEqual(json.loads(first.stdout)["decision"], "block")
        self.assertEqual(second.returncode, 0, second.stderr)
        self.assertEqual(second.stdout, "")

    def test_stop_uses_saved_plan_and_same_response_falls_back_once(self):
        html_output = Path(__file__).resolve().parents[2] / "html-output.md"
        policy = load_policy(path=None, env={})
        with tempfile.TemporaryDirectory() as td:
            store = StateStore(Path(td) / "state.db")
            preflight = {
                "hook_event_name": "UserPromptSubmit",
                "cwd": "C:/repo",
                "session_id": "session",
                "turn_id": "turn",
                "prompt": "3案を図で比較して最後に選びたい",
            }
            handle_event(
                preflight,
                runtime="codex",
                project_root="C:/repo",
                policy=policy,
                html_output_path=html_output,
                state_store=store,
            )
            stop = {
                "hook_event_name": "Stop",
                "cwd": "C:/repo",
                "session_id": "session",
                "turn_id": "turn",
                "last_assistant_message": "説明文だけでArtifactはありません。",
                "stop_hook_active": False,
            }
            first = handle_event(
                stop,
                runtime="codex",
                project_root="C:/repo",
                policy=policy,
                html_output_path=html_output,
                state_store=store,
            )
            second = handle_event(
                stop,
                runtime="codex",
                project_root="C:/repo",
                policy=policy,
                html_output_path=html_output,
                state_store=store,
            )

        self.assertEqual(first["decision"], "block")
        self.assertIn("visual", first["reason"])
        self.assertIn("decision", first["reason"])
        self.assertEqual(second, {})

    def test_command_entrypoint_reads_stdin_and_writes_claude_json(self):
        script = Path(__file__).resolve().parents[1] / "understanding-composer.py"
        project_root = Path(__file__).resolve().parents[3]
        payload = {
            "hook_event_name": "UserPromptSubmit",
            "cwd": str(project_root),
            "session_id": "session",
            "prompt_id": "turn",
            "prompt": "3案を図で比較して1案を選びたい",
        }

        completed = subprocess.run(
            [
                sys.executable,
                str(script),
                "--runtime",
                "claude",
                "--project-root",
                str(project_root),
            ],
            input=json.dumps(payload, ensure_ascii=False),
            text=True,
            encoding="utf-8",
            capture_output=True,
            check=False,
        )

        self.assertEqual(completed.returncode, 0, completed.stderr)
        result = json.loads(completed.stdout)
        context = result["hookSpecificOutput"]["additionalContext"]
        self.assertIn("visual", context)
        self.assertIn("decision", context)

    def test_preflight_output_shape_matches_each_runtime(self):
        html_output = Path(__file__).resolve().parents[2] / "html-output.md"
        policy = load_policy(path=None, env={})
        prompt = "3案を図で比較して最後に選びたい"

        claude = handle_event(
            {
                "hook_event_name": "UserPromptSubmit",
                "cwd": "C:/repo",
                "session_id": "session",
                "prompt_id": "turn",
                "prompt": prompt,
            },
            runtime="claude",
            project_root="C:/repo",
            policy=policy,
            html_output_path=html_output,
        )
        hermes = handle_event(
            {
                "hook_event_name": "pre_llm_call",
                "cwd": "C:/repo",
                "session_id": "session",
                "extra": {"turn_id": "turn", "user_message": prompt},
            },
            runtime="hermes",
            project_root="C:/repo",
            policy=policy,
            html_output_path=html_output,
        )

        claude_context = claude["hookSpecificOutput"]["additionalContext"]
        self.assertEqual(claude["hookSpecificOutput"]["hookEventName"], "UserPromptSubmit")
        self.assertEqual(hermes["context"], claude_context)
        self.assertIn("visual", claude_context)
        self.assertIn("decision", claude_context)

    def test_preflight_context_keeps_visual_and_decision(self):
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
            user_message="3案を図で比較して最後に採用案を選びたい",
            response_text="",
            response_sha256="",
            transcript_path="",
            changed_paths=(),
            stop_hook_active=False,
            attempt=0,
            capabilities=frozenset({"can_context"}),
            valid_for_state=True,
        )
        html_output = Path(__file__).resolve().parents[2] / "html-output.md"

        context = build_preflight_context(
            envelope,
            policy=load_policy(path=None, env={}),
            html_output_path=html_output,
        )

        self.assertIn("audience=project_novice", context)
        self.assertIn("visual", context)
        self.assertIn("decision", context)
        self.assertIn("背景", context)
        self.assertIn("具体例", context)

    def test_claude_stop_failure_returns_safe_terminal_sequence_without_state(self):
        html_output = Path(__file__).resolve().parents[2] / "html-output.md"
        policy = load_policy(path=None, env={})
        with tempfile.TemporaryDirectory() as td:
            state_path = Path(td) / "state.db"
            state = StateStore(state_path)
            result = handle_event(
                {
                    "hook_event_name": "StopFailure",
                    "cwd": "C:/repo",
                    "error_type": "server_error",
                    "reason": "provider unavailable",
                    "error": {"message": "raw-secret-body", "token": "SECRET_VALUE"},
                },
                runtime="claude",
                project_root="C:/repo",
                policy=policy,
                html_output_path=html_output,
                state_store=state,
            )
            connection = sqlite3.connect(state_path)
            plan_count = connection.execute(
                "SELECT COUNT(*) FROM preflight_plans"
            ).fetchone()[0]
            digest_count = connection.execute(
                "SELECT COUNT(*) FROM subagent_digests_v2"
            ).fetchone()[0]
            connection.close()

        self.assertIsInstance(result.get("terminalSequence"), str)
        self.assertTrue(result["terminalSequence"])
        self.assertNotIn("systemMessage", result)
        self.assertNotIn("raw-secret-body", repr(result))
        self.assertNotIn("SECRET_VALUE", repr(result))
        self.assertIn("server_error", result["terminalSequence"])
        self.assertEqual(plan_count, 0)
        self.assertEqual(digest_count, 0)

    def test_codex_stop_failure_and_unknown_event_are_noops(self):
        html_output = Path(__file__).resolve().parents[2] / "html-output.md"
        policy = load_policy(path=None, env={})

        codex = handle_event(
            {
                "hook_event_name": "StopFailure",
                "cwd": "C:/repo",
                "session_id": "session",
                "turn_id": "turn",
                "error_type": "api_timeout",
                "reason": "provider unavailable",
            },
            runtime="codex",
            project_root="C:/repo",
            policy=policy,
            html_output_path=html_output,
        )
        unknown = handle_event(
            {
                "hook_event_name": "unknown_event",
                "cwd": "C:/repo",
                "session_id": "session",
                "turn_id": "turn",
                "last_assistant_message": "should not continue",
            },
            runtime="claude",
            project_root="C:/repo",
            policy=policy,
            html_output_path=html_output,
        )

        self.assertEqual(codex, {})
        self.assertEqual(unknown, {})

    def test_claude_stop_failure_uses_only_official_error_type_classes(self):
        html_output = Path(__file__).resolve().parents[2] / "html-output.md"
        policy = load_policy(path=None, env={})
        official_types = (
            "rate_limit",
            "overloaded",
            "authentication_failed",
            "oauth_org_not_allowed",
            "billing_error",
            "invalid_request",
            "model_not_found",
            "server_error",
            "max_output_tokens",
            "unknown",
        )

        for error_type in official_types:
            with self.subTest(error_type=error_type):
                result = handle_event(
                    {
                        "hook_event_name": "StopFailure",
                        "cwd": "C:/repo",
                        "error_type": error_type,
                        "reason": "do not expose this reason",
                        "error": {"message": "raw-transcript-content", "token": "SECRET"},
                    },
                    runtime="claude",
                    project_root="C:/repo",
                    policy=policy,
                    html_output_path=html_output,
                )

                self.assertIn(error_type, result.get("terminalSequence", ""))
                self.assertNotIn("raw-transcript-content", repr(result))
                self.assertNotIn("SECRET", repr(result))

    def test_preview_runs_visual_smoke_with_policy_timeout(self):
        html_output = Path(__file__).resolve().parents[2] / "html-output.md"
        policy = load_policy(path=None, env={})
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            html = root / "report.html"
            html.write_text("<p>説明</p>", encoding="utf-8")
            shared = root / "shared.md"
            mirror = root / "mirror.md"
            project = root / "project.md"
            shared.write_text("| 用語 | 説明 |\n|---|---|\n| Hook | 説明 |\n", encoding="utf-8")
            mirror.write_bytes(shared.read_bytes())
            project.write_text("# project\n", encoding="utf-8")
            state = StateStore(root / "state.db")
            with patch(
                "visual.entrypoint.run_visual_smoke",
                return_value={"status": "pass", "errors": []},
                create=True,
            ) as smoke:
                handle_event(
                    {
                        "hook_event_name": "PostToolUse",
                        "cwd": "C:/repo",
                        "session_id": "session",
                        "turn_id": "turn",
                        "tool_name": "open_preview",
                        "tool_input": {"path": str(html)},
                    },
                    runtime="codex",
                    project_root="C:/repo",
                    policy=policy,
                    html_output_path=html_output,
                    state_store=state,
                    glossary_paths=(shared, mirror, project),
                    local_artifact_root=root,
                )

        smoke.assert_called_once_with(
            str(html), timeout_seconds=policy.visual_smoke_timeout_seconds
        )

    def test_write_and_edit_receipts_keep_visual_smoke_not_run(self):
        html_output = Path(__file__).resolve().parents[2] / "html-output.md"
        policy = load_policy(path=None, env={})
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            html = root / "report.html"
            html.write_text("<p>説明</p>", encoding="utf-8")
            shared = root / "shared.md"
            mirror = root / "mirror.md"
            project = root / "project.md"
            shared.write_text("| 用語 | 説明 |\n|---|---|\n| Hook | 説明 |\n", encoding="utf-8")
            mirror.write_bytes(shared.read_bytes())
            project.write_text("# project\n", encoding="utf-8")
            state = StateStore(root / "state.db")
            with patch("visual.entrypoint.run_visual_smoke", create=True) as smoke:
                for tool_name in ("Write", "Edit"):
                    handle_event(
                        {
                            "hook_event_name": "PostToolUse",
                            "cwd": "C:/repo",
                            "session_id": "session",
                            "turn_id": tool_name,
                            "tool_name": tool_name,
                            "tool_input": {"file_path": str(html)},
                        },
                        runtime="codex",
                        project_root="C:/repo",
                        policy=policy,
                        html_output_path=html_output,
                        state_store=state,
                        glossary_paths=(shared, mirror, project),
                        local_artifact_root=root,
                    )
                    loaded = state.load_receipt(
                        runtime="codex",
                        project_hash=hashlib.sha256(
                            os.path.normcase(os.path.abspath("C:/repo")).encode("utf-8")
                        ).hexdigest(),
                        session_id="session",
                        turn_id=tool_name,
                    )
                    self.assertEqual(loaded.visual_smoke, "not_run")

        smoke.assert_not_called()

    def test_thin_preview_artifact_cannot_suppress_stop(self):
        html_output = Path(__file__).resolve().parents[2] / "html-output.md"
        policy = load_policy(path=None, env={})
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            html = root / "thin.html"
            html.write_text("<!doctype html><title>薄い</title>", encoding="utf-8")
            shared = root / "shared.md"
            mirror = root / "mirror.md"
            project = root / "project.md"
            shared.write_text("| 用語 | 説明 |\n|---|---|\n| Hook | 説明 |\n", encoding="utf-8")
            mirror.write_bytes(shared.read_bytes())
            project.write_text("# project\n", encoding="utf-8")
            state = StateStore(root / "state.db")
            common = {"cwd": "C:/repo", "session_id": "session", "turn_id": "turn"}
            handle_event(
                {**common, "hook_event_name": "UserPromptSubmit", "prompt": "3案を図で比較して選びたい"},
                runtime="codex", project_root="C:/repo", policy=policy,
                html_output_path=html_output, state_store=state,
            )
            handle_event(
                {**common, "hook_event_name": "PostToolUse", "tool_name": "open_preview", "tool_input": {"path": str(html)}},
                runtime="codex", project_root="C:/repo", policy=policy,
                html_output_path=html_output, state_store=state,
                glossary_paths=(shared, mirror, project), local_artifact_root=root,
            )
            result = handle_event(
                {**common, "hook_event_name": "Stop", "last_assistant_message": "説明だけです。"},
                runtime="codex", project_root="C:/repo", policy=policy,
                html_output_path=html_output, state_store=state,
                glossary_paths=(shared, mirror, project), local_artifact_root=root,
            )

        self.assertEqual(result.get("decision"), "block")


if __name__ == "__main__":
    unittest.main()

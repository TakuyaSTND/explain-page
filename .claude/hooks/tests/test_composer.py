from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

HOOKS_DIR = Path(__file__).resolve().parents[1]
if str(HOOKS_DIR) not in sys.path:
    sys.path.insert(0, str(HOOKS_DIR))

from visual import branding
from visual.policy import load_policy, parse_controls
from visual.composer import compose_plan, conversion_signals, structure_weight
from visual.contracts import HookEnvelope
from visual.entrypoint import build_preflight_context


class ExplanationPolicyTests(unittest.TestCase):
    def test_wrong_policy_types_fall_back_to_defaults(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "policy.json"
            path.write_text(
                '{"default_components":"oops","min_chars":"oops",'
                '"min_blocks":null,"state_ttl_seconds":{},'
                '"max_artifact_bytes":[],"publish":"invalid"}',
                encoding="utf-8",
            )

            policy = load_policy(path=path, env={})

        self.assertEqual(policy.default_components, ("overview", "walkthrough", "examples", "evidence", "glossary", "details"))
        self.assertEqual(policy.min_chars, 700)
        self.assertEqual(policy.min_blocks, 8)
        self.assertEqual(policy.state_ttl_seconds, 86400)
        self.assertEqual(policy.max_artifact_bytes, 2097152)
        self.assertEqual(policy.publish, "never")

    def test_project_policy_matches_explicit_publish_setting(self):
        policy_path = Path(__file__).resolve().parents[2] / "visual-hook-policy.json"

        policy = load_policy(path=policy_path, env={})

        self.assertEqual(policy.publish, "always")

    def test_private_request_overrides_publish_always(self):
        policy_path = Path(__file__).resolve().parents[2] / "visual-hook-policy.json"
        policy = load_policy(path=policy_path, env={})
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
            user_message="private repoを説明して。外部公開しない",
            response_text="",
            response_sha256="",
            transcript_path="",
            changed_paths=(),
            stop_hook_active=False,
            attempt=0,
            capabilities=frozenset({"can_context"}),
            valid_for_state=True,
        )

        plan = compose_plan(envelope, policy)

        self.assertEqual(plan.publish_policy, "never")
        self.assertIn("private_local_only", plan.reason_codes)

    def test_malformed_policy_falls_back_to_safe_defaults(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "policy.json"
            path.write_text("{broken", encoding="utf-8")

            policy = load_policy(path=path, env={})

        self.assertTrue(policy.enabled)
        self.assertEqual(policy.default_audience, "project_novice")
        self.assertEqual(policy.default_depth, "deep")

    def test_heavy_structure_adds_summary_even_when_text_is_short(self):
        response = "\n".join(f"{i}. item" for i in range(1, 9))
        envelope = HookEnvelope(
            schema_version=1,
            runtime="claude",
            runtime_version="",
            event="Stop",
            project_root="C:/repo",
            profile_id="",
            session_id="session",
            turn_id="turn",
            invocation_id="",
            user_message="結果を説明して",
            response_text=response,
            response_sha256="hash",
            transcript_path="",
            changed_paths=(),
            stop_hook_active=False,
            attempt=0,
            capabilities=frozenset({"can_continue"}),
            valid_for_state=True,
        )

        plan = compose_plan(envelope, load_policy(path=None, env={}))

        self.assertIn("summary", plan.components)
        self.assertIn("heavy_structure", plan.reason_codes)

    def test_structure_weight_counts_numbered_items_and_ignores_fenced_code(self):
        numbered = "\n".join(f"{i}. item" for i in range(1, 11))
        fenced = "```python\n" + "\n".join(f"# comment {i}" for i in range(8)) + "\n```"

        self.assertEqual(structure_weight(numbered), 10)
        self.assertEqual(structure_weight(fenced), 0)

    def test_long_response_adds_summary_without_removing_details(self):
        response = "長い説明。" * 150
        envelope = HookEnvelope(
            schema_version=1,
            runtime="codex",
            runtime_version="",
            event="Stop",
            project_root="C:/repo",
            profile_id="",
            session_id="session",
            turn_id="turn",
            invocation_id="",
            user_message="調査結果を説明して",
            response_text=response,
            response_sha256="hash",
            transcript_path="",
            changed_paths=(),
            stop_hook_active=False,
            attempt=0,
            capabilities=frozenset({"can_continue"}),
            valid_for_state=True,
        )

        plan = compose_plan(envelope, load_policy(path=None, env={}))

        self.assertIn("summary", plan.components)
        self.assertIn("walkthrough", plan.components)
        self.assertIn("details", plan.components)

    def test_record_only_visual_does_not_force_decision(self):
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

    def test_summary_visual_and_decision_are_all_preserved(self):
        envelope = HookEnvelope(
            schema_version=1,
            runtime="hermes",
            runtime_version="",
            event="pre_llm_call",
            project_root="C:/repo",
            profile_id="",
            session_id="session",
            turn_id="turn",
            invocation_id="",
            user_message="調査結果を要約し、3案を図で比較して採用案を選びたい",
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

        self.assertTrue({"summary", "visual", "decision"}.issubset(plan.components))

    def test_visual_and_decision_are_composed_together(self):
        message = "3つの案を図で比較し、最後に採用案を選びたい"
        envelope = HookEnvelope(
            schema_version=1,
            runtime="codex",
            runtime_version="",
            event="UserPromptSubmit",
            project_root="C:/repo",
            profile_id="",
            session_id="session",
            turn_id="turn",
            invocation_id="",
            user_message=message,
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

        self.assertEqual(plan.audience, "project_novice")
        self.assertEqual(plan.depth, "deep")
        self.assertIn("visual", plan.components)
        self.assertIn("decision", plan.components)
        self.assertIn("walkthrough", plan.components)
        self.assertIn("evidence", plan.components)

    def test_environment_switch_is_auto_always_or_off(self):
        off = load_policy(path=None, env={branding.ENV_MODE: "off"})
        always = load_policy(path=None, env={branding.ENV_MODE: "always"})

        self.assertFalse(off.enabled)
        self.assertEqual(off.explain_mode, "off")
        self.assertTrue(always.enabled)
        self.assertEqual(always.explain_mode, "always")

    def test_component_controls_are_independent(self):
        controls = parse_controls(
            "[visual:off] [decision:on] [summary:on] [explain:deep]"
        )

        self.assertEqual(controls.depth, "deep")
        self.assertEqual(controls.add_components, frozenset({"decision", "summary"}))
        self.assertEqual(controls.remove_components, frozenset({"visual"}))

    def test_defaults_prioritize_project_novice_understanding(self):
        policy = load_policy(path=None, env={})

        self.assertTrue(policy.enabled)
        self.assertEqual(policy.default_audience, "project_novice")
        self.assertEqual(policy.default_depth, "deep")
        self.assertEqual(
            policy.default_components,
            (
                "overview",
                "walkthrough",
                "examples",
                "evidence",
                "glossary",
                "details",
            ),
        )
        self.assertEqual(policy.publish, "never")
        self.assertEqual(policy.min_chars, 700)
        self.assertEqual(policy.min_blocks, 8)


    @unittest.skipIf(
        branding.LEGACY_ENV_MIN is None or branding.LEGACY_ENV_BLOCKS is None,
        "この配布では旧い環境変数名を読まない（branding.LEGACY_* が None）",
    )
    def test_legacy_visual_aliases_override_json_and_are_recorded(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "policy.json"
            path.write_text(
                json.dumps(
                    {
                        "min_chars": 900,
                        "min_blocks": 10,
                        "explain_mode": "always",
                    }
                ),
                encoding="utf-8",
            )

            policy = load_policy(
                path=path,
                env={
                    branding.LEGACY_ENV_MIN: "321",
                    branding.LEGACY_ENV_BLOCKS: "12",
                },
            )

        self.assertEqual(policy.min_chars, 321)
        self.assertEqual(policy.min_blocks, 12)
        self.assertIn(branding.LEGACY_ENV_MIN, policy.deprecated_aliases)
        self.assertIn(branding.LEGACY_ENV_BLOCKS, policy.deprecated_aliases)

    @unittest.skipIf(
        branding.LEGACY_ENV_OFF is None
        or branding.LEGACY_ENV_MIN is None
        or branding.LEGACY_ENV_BLOCKS is None,
        "この配布では旧い環境変数名を読まない（branding.LEGACY_* が None）",
    )
    def test_explain_alias_has_priority_over_legacy_off_alias(self):
        explicit = load_policy(
            path=None,
            env={branding.ENV_MODE: "auto", branding.LEGACY_ENV_OFF: "1"},
        )
        legacy = load_policy(path=None, env={branding.LEGACY_ENV_OFF: "1"})
        invalid = load_policy(
            path=None,
            env={
                branding.LEGACY_ENV_OFF: "not-a-bool",
                branding.LEGACY_ENV_MIN: "not-an-int",
                branding.LEGACY_ENV_BLOCKS: "0",
            },
        )

        self.assertTrue(explicit.enabled)
        self.assertEqual(explicit.explain_mode, "auto")
        self.assertFalse(legacy.enabled)
        self.assertIn(branding.LEGACY_ENV_OFF, legacy.deprecated_aliases)
        self.assertTrue(invalid.enabled)
        self.assertEqual(invalid.min_chars, 700)
        self.assertEqual(invalid.min_blocks, 8)

    def test_always_mode_forces_summary_and_local_html_with_explicit_reason(self):
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
            user_message="説明して",
            response_text="",
            response_sha256="",
            transcript_path="",
            changed_paths=(),
            stop_hook_active=False,
            attempt=0,
            capabilities=frozenset({"can_context"}),
            valid_for_state=True,
        )

        auto = compose_plan(envelope, load_policy(path=None, env={branding.ENV_MODE: "auto"}))
        always = compose_plan(
            envelope, load_policy(path=None, env={branding.ENV_MODE: "always"})
        )

        self.assertNotEqual((auto.components, auto.delivery), (always.components, always.delivery))
        self.assertIn("summary", always.components)
        self.assertEqual(always.delivery, "local_html")
        always_context = build_preflight_context(
            envelope,
            policy=load_policy(path=None, env={branding.ENV_MODE: "always"}),
            html_output_path=Path(__file__).resolve().parents[2] / "html-output.md",
        )
        self.assertIn("explicit_always", always_context)


class ConversionOnlyRequestTests(unittest.TestCase):
    """2026-10-15（利用者の選択＝案9(b) の A）：速さの合図と変換の語の**両方**がある依頼だけに
    conversion_only_request の印を付ける。合図だけ・変換の語だけ・LaTeX 指定・頁を作る依頼には付けない。
    """

    def _plan(self, message, *, event="UserPromptSubmit", response=""):
        envelope = HookEnvelope(
            schema_version=1,
            runtime="claude",
            runtime_version="",
            event=event,
            project_root="C:/repo",
            profile_id="",
            session_id="session",
            turn_id="turn",
            invocation_id="",
            user_message=message,
            response_text=response,
            response_sha256="",
            transcript_path="",
            changed_paths=(),
            stop_hook_active=False,
            attempt=0,
            capabilities=frozenset({"can_context"} if event == "UserPromptSubmit" else {"can_continue"}),
            valid_for_state=True,
        )
        return compose_plan(envelope, load_policy(path=None, env={branding.ENV_MODE: "always"}))

    def test_quick_conversion_requests_are_marked(self):
        # 上の4つは 10/10〜14 の会話で実際に印が付いた依頼の形（免除の候補の実例）。
        for message in (
            "PDFにして　早く",
            "PDF化して　そのままでいい　早く",
            "このアーティファクトをPDFにして　爆速で",
            "とりあえず現状のものだけでいいから　とりあえずPDFに書き出して（仮）であることを明示して",
            "ＰＤＦ化して はやく",
            "とりあえずdocxにして",
            "ドキュメント化して　とりあえず",
            "この頁を印刷して、仮でいい",
        ):
            with self.subTest(message=message):
                self.assertTrue(conversion_signals(message))
                self.assertIn("conversion_only_request", self._plan(message).reason_codes)

    def test_other_requests_are_not_marked(self):
        for message in (
            "PDF 出力の作業のコミットして",
            "頁を作ってPDFにして早く",
            "もっと視覚的にわかりやすい　アーティファクト＆PDFにしてよ",
            "LaTeXでPDF化して",
            "これらのFBをLaTeXを使って、わかりやすくかつ詳細にPDF化して",
            "とりあえず既存のワークフローを確認して",
            "仮説の節をPDFにして",
            "3案を図で比較してPDFにして早く",
            "どれを採用するか決めてからPDFにして早く",
            "要約してPDFにして早く",
            "PDFにして早く" + "。" * 120,
            "",
        ):
            with self.subTest(message=message):
                self.assertEqual(conversion_signals(message), ())
                self.assertNotIn("conversion_only_request", self._plan(message).reason_codes)

    def test_the_matched_signals_are_returned(self):
        self.assertEqual(conversion_signals("PDFにして　早く"), ("早く", "pdfにして"))

    def test_the_mark_changes_nothing_else_in_the_plan(self):
        marked = self._plan("PDFにして　早く")
        plain = self._plan("PDFにして")

        self.assertEqual(marked.components, plain.components)
        self.assertEqual(marked.delivery, plain.delivery)
        self.assertEqual(marked.publish_policy, plain.publish_policy)
        self.assertEqual(
            [code for code in marked.reason_codes if code != "conversion_only_request"],
            list(plain.reason_codes),
        )

    def test_the_reply_alone_never_marks_a_turn(self):
        plan = self._plan("", event="Stop", response="PDFにして　早く")

        self.assertNotIn("conversion_only_request", plan.reason_codes)


if __name__ == "__main__":
    unittest.main()

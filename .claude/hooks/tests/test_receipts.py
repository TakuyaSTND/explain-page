from __future__ import annotations

import sys
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

HOOKS_DIR = Path(__file__).resolve().parents[1]
if str(HOOKS_DIR) not in sys.path:
    sys.path.insert(0, str(HOOKS_DIR))

from visual.contracts import ArtifactReceipt, GlossarySnapshot, HookEnvelope
from visual.glossary import GlossaryEntry
from visual.receipts import build_receipt, is_glossary_stale, validate_receipt
from visual.state import StateStore


class ArtifactReceiptTests(unittest.TestCase):
    def test_file_url_resource_is_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            html = root / "file-resource.html"
            html.write_text(
                '<img src="file:///C:/Users/example/private.png">',
                encoding="utf-8",
            )
            envelope = HookEnvelope(
                1, "hermes", "", "post_tool_call", "C:/repo", "",
                "session", "turn", "", "", "", "", "", (), False, 0,
                frozenset({"can_receipt"}), True,
            )
            glossary = GlossarySnapshot(
                "home", "shared.md", "shared", "shared", "project",
                "effective", 1, 0, 1, (), (), True,
            )

            with self.assertRaisesRegex(ValueError, "external dependency"):
                build_receipt(
                    html,
                    envelope=envelope,
                    glossary=glossary,
                    glossary_entries={"Hook": GlossaryEntry("Hook", "説明", "shared")},
                    local_root=root,
                )

    def test_relative_subresource_is_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            html = root / "relative-resource.html"
            html.write_text(
                '<img src="./private.png"><style>body{background:url(../other.png)}</style>',
                encoding="utf-8",
            )
            envelope = HookEnvelope(
                1, "hermes", "", "post_tool_call", "C:/repo", "",
                "session", "turn", "", "", "", "", "", (), False, 0,
                frozenset({"can_receipt"}), True,
            )
            glossary = GlossarySnapshot(
                "home", "shared.md", "shared", "shared", "project",
                "effective", 1, 0, 1, (), (), True,
            )

            with self.assertRaisesRegex(ValueError, "external dependency"):
                build_receipt(
                    html,
                    envelope=envelope,
                    glossary=glossary,
                    glossary_entries={},
                    local_root=root,
                )

    def test_active_html_event_handler_cannot_validate_receipt(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            html = root / "active.html"
            html.write_text(
                '<header data-component="overview"><img src="data:image/gif;base64,AA==" onerror="alert(1)"></header>',
                encoding="utf-8",
            )
            envelope = HookEnvelope(
                1, "hermes", "", "post_tool_call", "C:/repo", "",
                "session", "turn", "", "", "", "", "", (), False, 0,
                frozenset({"can_receipt"}), True,
            )
            glossary = GlossarySnapshot(
                "home", "shared.md", "shared", "shared", "project",
                "effective", 1, 0, 1, (), (), True,
            )
            receipt = build_receipt(
                html,
                envelope=envelope,
                glossary=glossary,
                glossary_entries={},
                local_root=root,
                previewed=True,
                required_components=(),
                visual_smoke_status="pass",
            )

            self.assertFalse(receipt.inspection_ok)
            self.assertFalse(
                validate_receipt(
                    receipt,
                    glossary,
                    local_root=root,
                    max_artifact_bytes=1024,
                    required_components=(),
                )
            )

    def test_protocol_relative_css_resource_is_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            html = root / "css-external.html"
            html.write_text(
                "<style>body{background:url(//evil.example/x.png)}</style>",
                encoding="utf-8",
            )
            envelope = HookEnvelope(
                1, "hermes", "", "post_tool_call", "C:/repo", "",
                "session", "turn", "", "", "", "", "", (), False, 0,
                frozenset({"can_receipt"}), True,
            )
            glossary = GlossarySnapshot(
                "home", "shared.md", "shared", "shared", "project",
                "effective", 1, 0, 1, (), (), True,
            )

            with self.assertRaisesRegex(ValueError, "external dependency"):
                build_receipt(
                    html,
                    envelope=envelope,
                    glossary=glossary,
                    glossary_entries={"Hook": GlossaryEntry("Hook", "説明", "shared")},
                    local_root=root,
                )

    def test_receipt_is_revalidated_against_current_file(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            html = root / "report.html"
            html.write_text("<p>original</p>", encoding="utf-8")
            envelope = HookEnvelope(
                1, "hermes", "", "post_tool_call", "C:/repo", "",
                "session", "turn", "", "", "", "", "", (), False, 0,
                frozenset({"can_receipt"}), True,
            )
            glossary = GlossarySnapshot(
                "home", "shared.md", "shared", "shared", "project",
                "effective", 1, 0, 1, (), (), True,
            )
            entries = {"Hook": GlossaryEntry("Hook", "説明", "shared")}
            receipt = build_receipt(
                html,
                envelope=envelope,
                glossary=glossary,
                glossary_entries=entries,
                local_root=root,
                previewed=True,
                visual_smoke_status="pass",
            )

            self.assertTrue(
                validate_receipt(
                    receipt, glossary, local_root=root, max_artifact_bytes=1024
                )
            )
            html.write_text("<p>changed</p>", encoding="utf-8")
            self.assertFalse(
                validate_receipt(
                    receipt, glossary, local_root=root, max_artifact_bytes=1024
                )
            )
            html.unlink()
            self.assertFalse(
                validate_receipt(
                    receipt, glossary, local_root=root, max_artifact_bytes=1024
                )
            )

    def test_receipt_is_invalid_after_glossary_change(self):
        from visual.contracts import ArtifactReceipt

        receipt = ArtifactReceipt(
            "hermes", "C:/repo", "session", "turn", "missing.html", "sha", 1,
            "now", "pass", "old", "home+project", "pass", True, "local",
        )
        current = GlossarySnapshot(
            "home", "shared.md", "shared", "shared", "project", "new",
            1, 0, 1, (), (), True,
        )

        self.assertFalse(
            validate_receipt(
                receipt, current, local_root=Path.cwd(), max_artifact_bytes=1024
            )
        )

    def test_external_resource_is_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            html = root / "external.html"
            html.write_text(
                '<script src="https://example.com/steal.js"></script>',
                encoding="utf-8",
            )
            envelope = HookEnvelope(
                1, "hermes", "", "post_tool_call", "C:/repo", "",
                "session", "turn", "", "", "", "", "", (), False, 0,
                frozenset({"can_receipt"}), True,
            )
            glossary = GlossarySnapshot(
                "home", "shared.md", "shared", "shared", "project",
                "effective", 1, 0, 1, (), (), True,
            )

            with self.assertRaisesRegex(ValueError, "external dependency"):
                build_receipt(
                    html,
                    envelope=envelope,
                    glossary=glossary,
                    glossary_entries={},
                    local_root=root,
                    max_artifact_bytes=1024,
                )

    def test_artifact_size_limit_is_enforced(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            html = root / "large.html"
            html.write_text("x" * 101, encoding="utf-8")
            envelope = HookEnvelope(
                1, "hermes", "", "post_tool_call", "C:/repo", "",
                "session", "turn", "", "", "", "", "", (), False, 0,
                frozenset({"can_receipt"}), True,
            )
            glossary = GlossarySnapshot(
                "home", "shared.md", "shared", "shared", "project",
                "effective", 1, 0, 1, (), (), True,
            )

            with self.assertRaisesRegex(ValueError, "size limit"):
                build_receipt(
                    html,
                    envelope=envelope,
                    glossary=glossary,
                    glossary_entries={},
                    local_root=root,
                    max_artifact_bytes=100,
                )

    def test_missing_glossary_cannot_pass(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            html = root / "report.html"
            html.write_text("<p>説明</p>", encoding="utf-8")
            envelope = HookEnvelope(
                1, "hermes", "", "post_tool_call", "C:/repo", "",
                "session", "turn", "", "", "", "", "", (), False, 0,
                frozenset({"can_receipt"}), True,
            )
            glossary = GlossarySnapshot(
                "missing", "", "", "", "", "", 0, 0, 0, (), (), False,
            )

            receipt = build_receipt(
                html,
                envelope=envelope,
                glossary=glossary,
                glossary_entries={},
                local_root=root,
                max_artifact_bytes=1024,
            )

        self.assertEqual(receipt.gloss_check, "fail")

    def test_receipt_records_failed_glossary_check(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            html = root / "bad.html"
            html.write_text(
                '<span class="t" data-d="誤った説明">Hook</span>',
                encoding="utf-8",
            )
            envelope = HookEnvelope(
                1, "hermes", "", "post_tool_call", "C:/repo", "",
                "session", "turn", "", "", "", "", "", (), False, 0,
                frozenset({"can_receipt"}), True,
            )
            glossary = GlossarySnapshot(
                "home", "shared.md", "shared", "shared", "project",
                "effective", 1, 0, 1, (), (), True,
            )
            entries = {"Hook": GlossaryEntry("Hook", "正しい説明", "shared")}

            receipt = build_receipt(
                html,
                envelope=envelope,
                glossary=glossary,
                glossary_entries=entries,
                local_root=root,
            )

        self.assertEqual(receipt.gloss_check, "fail")

    def test_changed_effective_glossary_marks_receipt_stale(self):
        from visual.contracts import ArtifactReceipt

        receipt = ArtifactReceipt(
            runtime="hermes",
            project_root="C:/repo",
            session_id="session",
            turn_id="turn",
            path="report.html",
            sha256="file",
            bytes=10,
            created_at="now",
            gloss_check="pass",
            glossary_sha256="old",
            glossary_source="home+project",
            visual_smoke="pass",
            previewed=True,
            visibility="local",
        )
        current = GlossarySnapshot(
            shared_source="home",
            shared_path="shared.md",
            shared_sha256="shared",
            mirror_sha256="shared",
            project_sha256="project",
            effective_sha256="new",
            shared_count=1,
            project_count=1,
            effective_count=2,
            project_overrides=(),
            same_file_duplicates=(),
            mirror_matches_home=True,
        )

        self.assertTrue(is_glossary_stale(receipt, current))

    def test_local_html_receipt_contains_file_and_glossary_hashes(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            html = root / "report.html"
            html.write_text("<!doctype html><title>Report</title><p>説明</p>", encoding="utf-8")
            envelope = HookEnvelope(
                schema_version=1,
                runtime="hermes",
                runtime_version="",
                event="post_tool_call",
                project_root="C:/repo",
                profile_id="",
                session_id="session",
                turn_id="turn",
                invocation_id="tool-call",
                user_message="",
                response_text="",
                response_sha256="",
                transcript_path="",
                changed_paths=(str(html),),
                stop_hook_active=False,
                attempt=0,
                capabilities=frozenset({"can_receipt"}),
                valid_for_state=True,
            )
            glossary = GlossarySnapshot(
                shared_source="home",
                shared_path="shared.md",
                shared_sha256="shared",
                mirror_sha256="shared",
                project_sha256="project",
                effective_sha256="effective-glossary",
                shared_count=1,
                project_count=1,
                effective_count=2,
                project_overrides=(),
                same_file_duplicates=(),
                mirror_matches_home=True,
            )

            receipt = build_receipt(
                html,
                envelope=envelope,
                glossary=glossary,
                local_root=root,
            )

        self.assertEqual(receipt.path, str(html.resolve()))
        self.assertEqual(len(receipt.sha256), 64)
        self.assertEqual(receipt.glossary_sha256, "effective-glossary")
        self.assertEqual(receipt.glossary_source, "home+project")
        self.assertEqual(receipt.visibility, "local")
        self.assertGreater(receipt.bytes, 0)

    def test_receipt_persists_v3_semantic_inspection_results(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            html = root / "report.html"
            html.write_text("<p>説明</p>", encoding="utf-8")
            envelope = HookEnvelope(
                1, "hermes", "", "post_tool_call", "C:/repo", "",
                "session", "turn", "", "", "", "", "", (), False, 0,
                frozenset({"can_receipt"}), True,
            )
            glossary = GlossarySnapshot(
                "home", "shared.md", "shared", "shared", "project",
                "effective", 1, 0, 1, (), (), True,
            )
            inspection = {
                "present_components": ["overview", "decision"],
                "missing_components": [],
                "missing_decision_parts": [],
                "unwrapped_identifiers": [],
                "unknown_identifiers": [],
                "missing_evidence_sources": [],
                "inspection_errors": [],
                "ok": True,
            }

            with patch(
                "visual.receipts.inspect_artifact_html",
                return_value=inspection,
                create=True,
            ):
                receipt = build_receipt(
                    html,
                    envelope=envelope,
                    glossary=glossary,
                    glossary_entries={"Hook": GlossaryEntry("Hook", "説明", "shared")},
                    local_root=root,
                    previewed=True,
                    required_components=("overview", "decision"),
                    visual_smoke_status="pass",
                )
                valid = validate_receipt(
                    receipt,
                    glossary,
                    local_root=root,
                    max_artifact_bytes=1024,
                    required_components=("overview", "decision"),
                )

        self.assertEqual(receipt.required_components, ("overview", "decision"))
        self.assertEqual(receipt.present_components, ("overview", "decision"))
        self.assertEqual(receipt.inspection_errors, ())
        self.assertTrue(receipt.inspection_ok)
        self.assertTrue(valid)

    def test_receipt_validation_requires_current_plan_components_and_pass_smoke(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            html = root / "report.html"
            html.write_text("<p>説明</p>", encoding="utf-8")
            receipt = ArtifactReceipt(
                "hermes", "C:/repo", "session", "turn", str(html), "sha", 1,
                "now", "pass", "effective", "home+project", "not_run", True, "local",
                ("overview", "decision"), ("overview",), ("decision",),
                ("input",), (), (), ("source",), (), False, (),
            )
            glossary = GlossarySnapshot(
                "home", "shared.md", "shared", "shared", "project",
                "effective", 1, 0, 1, (), (), True,
            )

            self.assertFalse(
                validate_receipt(
                    receipt,
                    glossary,
                    local_root=root,
                    max_artifact_bytes=1024,
                    required_components=("overview", "decision"),
                )
            )

    def test_preview_receipt_without_smoke_result_is_not_run(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            html = root / "report.html"
            html.write_text("<p>説明</p>", encoding="utf-8")
            envelope = HookEnvelope(
                1, "hermes", "", "post_tool_call", "C:/repo", "",
                "session", "turn", "", "", "", "", "", (), False, 0,
                frozenset({"can_receipt"}), True,
            )
            glossary = GlossarySnapshot(
                "home", "shared.md", "shared", "shared", "project",
                "effective", 1, 0, 1, (), (), True,
            )
            receipt = build_receipt(
                html,
                envelope=envelope,
                glossary=glossary,
                glossary_entries={"Hook": GlossaryEntry("Hook", "説明", "shared")},
                local_root=root,
                previewed=True,
            )

        self.assertEqual(receipt.visual_smoke, "not_run")

    def test_existing_v2_receipts_are_migrated_without_removing_v2(self):
        with tempfile.TemporaryDirectory() as td:
            db = Path(td) / "state.db"
            store = StateStore(db)
            connection = sqlite3.connect(db)
            try:
                connection.execute(
                    """
                    INSERT INTO artifact_receipts_v2 (
                        runtime, project_hash, session_id, turn_id,
                        project_root, path, sha256, bytes, created_at_text,
                        gloss_check, glossary_sha256, glossary_source,
                        visual_smoke, previewed, visibility, expires_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        "codex", "project", "session", "turn", "C:/repo",
                        "C:/tmp/report.html", "sha", 10, "now", "pass",
                        "gloss", "home+project", "pass", 1, "local", 200,
                    ),
                )
                connection.commit()
            finally:
                connection.close()
            migrated = StateStore(db)
            loaded = migrated.load_receipt(
                runtime="codex",
                project_hash="project",
                session_id="session",
                turn_id="turn",
                now=100,
            )
            connection = sqlite3.connect(db)
            try:
                v2_count = connection.execute(
                    "SELECT COUNT(*) FROM artifact_receipts_v2"
                ).fetchone()[0]
                v3_count = connection.execute(
                    "SELECT COUNT(*) FROM artifact_receipts_v3"
                ).fetchone()[0]
            finally:
                connection.close()

        self.assertEqual(loaded.path, "C:/tmp/report.html")
        self.assertEqual(v2_count, 1)
        self.assertEqual(v3_count, 1)


if __name__ == "__main__":
    unittest.main()

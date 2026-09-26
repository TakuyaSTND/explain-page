from __future__ import annotations

import sys
import sqlite3
import tempfile
import unittest
from pathlib import Path

HOOKS_DIR = Path(__file__).resolve().parents[1]
if str(HOOKS_DIR) not in sys.path:
    sys.path.insert(0, str(HOOKS_DIR))

from visual.state import StateStore
from visual.contracts import ArtifactReceipt, ExplanationPlan, SubagentDigest


class StateStoreTests(unittest.TestCase):
    def test_digest_is_scoped_by_runtime_profile_and_session(self):
        digest = SubagentDigest(
            "parent", "child", "調査", "結果", (), "low", "", "success", 10
        )
        with tempfile.TemporaryDirectory() as td:
            store = StateStore(Path(td) / "state.db")
            store.save_digest(
                runtime="claude",
                profile_id="default",
                session_id="session-a",
                project_hash="project",
                digest=digest,
                ttl_seconds=60,
                now=100.0,
            )
            same = store.load_digests(
                runtime="claude",
                profile_id="default",
                session_id="session-a",
                project_hash="project",
                parent_turn_id="parent",
                now=101.0,
            )
            other = store.load_digests(
                runtime="codex",
                profile_id="default",
                session_id="session-b",
                project_hash="project",
                parent_turn_id="parent",
                now=101.0,
            )

        self.assertEqual(same, (digest,))
        self.assertEqual(other, ())

    def test_expired_digest_rows_are_deleted(self):
        digest = SubagentDigest(
            "parent", "child", "調査", "結果", (), "low", "", "success", 10
        )
        with tempfile.TemporaryDirectory() as td:
            db = Path(td) / "state.db"
            store = StateStore(db)
            store.save_digest(
                runtime="hermes",
                profile_id="default",
                session_id="session",
                project_hash="project",
                digest=digest,
                ttl_seconds=1,
                now=100.0,
            )
            loaded = store.load_digests(
                runtime="hermes",
                profile_id="default",
                session_id="session",
                project_hash="project",
                parent_turn_id="parent",
                now=102.0,
            )
            connection = sqlite3.connect(db)
            count = connection.execute("SELECT COUNT(*) FROM subagent_digests_v2").fetchone()[0]
            connection.close()

        self.assertEqual(loaded, ())
        self.assertEqual(count, 0)

    def test_multiple_artifact_receipts_are_kept_for_one_turn(self):
        first = ArtifactReceipt(
            "hermes", "C:/repo", "session", "turn", "C:/temp/a.html", "a", 10,
            "first", "pass", "gloss", "home+project", "pass", True, "local",
        )
        second = ArtifactReceipt(
            "hermes", "C:/repo", "session", "turn", "C:/temp/b.html", "b", 20,
            "second", "pass", "gloss", "home+project", "pass", True, "local",
        )
        with tempfile.TemporaryDirectory() as td:
            store = StateStore(Path(td) / "state.db")
            store.save_receipt(project_hash="project", receipt=first, ttl_seconds=60, now=100.0)
            store.save_receipt(project_hash="project", receipt=second, ttl_seconds=60, now=101.0)
            loaded = store.load_receipts(
                runtime="hermes",
                project_hash="project",
                session_id="session",
                turn_id="turn",
                now=102.0,
            )

        self.assertEqual({item.path for item in loaded}, {first.path, second.path})

    def test_subagent_digest_is_upserted_and_loaded_for_parent_turn(self):
        first = SubagentDigest(
            parent_turn_id="parent",
            child_session_id="child",
            goal="調査",
            result="途中結果",
            evidence=("a",),
            risk="low",
            needs_human="",
            status="success",
            duration_ms=10,
        )
        updated = SubagentDigest(
            parent_turn_id="parent",
            child_session_id="child",
            goal="調査",
            result="更新結果",
            evidence=("a", "b"),
            risk="high",
            needs_human="確認",
            status="success",
            duration_ms=20,
        )
        with tempfile.TemporaryDirectory() as td:
            store = StateStore(Path(td) / "state.db")
            store.save_digest(
                runtime="hermes", profile_id="default", session_id="session",
                project_hash="project", digest=first, ttl_seconds=60, now=100.0,
            )
            store.save_digest(
                runtime="hermes", profile_id="default", session_id="session",
                project_hash="project", digest=updated, ttl_seconds=60, now=101.0,
            )
            loaded = store.load_digests(
                runtime="hermes", profile_id="default", session_id="session",
                project_hash="project", parent_turn_id="parent", now=102.0,
            )

        self.assertEqual(loaded, (updated,))

    def test_artifact_receipt_round_trips_by_runtime_session_and_turn(self):
        receipt = ArtifactReceipt(
            runtime="hermes",
            project_root="C:/repo",
            session_id="session",
            turn_id="turn",
            path="C:/temp/report.html",
            sha256="file-hash",
            bytes=100,
            created_at="now",
            gloss_check="pass",
            glossary_sha256="glossary-hash",
            glossary_source="home+project",
            visual_smoke="pass",
            previewed=True,
            visibility="local",
        )
        with tempfile.TemporaryDirectory() as td:
            store = StateStore(Path(td) / "state.db")
            store.save_receipt(
                project_hash="project",
                receipt=receipt,
                ttl_seconds=60,
                now=100.0,
            )
            loaded = store.load_receipt(
                runtime="hermes",
                project_hash="project",
                session_id="session",
                turn_id="turn",
                now=101.0,
            )

        self.assertEqual(loaded, receipt)

    def test_preflight_plan_round_trips_without_prompt_text(self):
        plan = ExplanationPlan(
            audience="project_novice",
            depth="guided",
            components=("overview", "walkthrough", "visual", "decision"),
            reason_codes=("visual_comparison", "decision_required"),
            provisional=True,
            should_continue=False,
            delivery="local_html",
            publish_policy="never",
        )
        with tempfile.TemporaryDirectory() as td:
            store = StateStore(Path(td) / "state.db")
            store.save_plan(
                runtime="codex",
                project_hash="project",
                session_id="session",
                turn_id="turn",
                plan=plan,
                ttl_seconds=60,
                now=100.0,
            )
            loaded = store.load_plan(
                runtime="codex",
                project_hash="project",
                session_id="session",
                turn_id="turn",
                now=101.0,
            )

        self.assertEqual(loaded, plan)

    def test_same_response_is_claimed_once_but_changed_response_is_allowed(self):
        with tempfile.TemporaryDirectory() as td:
            store = StateStore(Path(td) / "state.db")

            first = store.claim_response(
                runtime="codex",
                project_hash="project",
                session_id="session",
                turn_id="turn",
                response_sha256="hash-a",
                ttl_seconds=60,
                now=100.0,
            )
            duplicate = store.claim_response(
                runtime="codex",
                project_hash="project",
                session_id="session",
                turn_id="turn",
                response_sha256="hash-a",
                ttl_seconds=60,
                now=101.0,
            )
            changed = store.claim_response(
                runtime="codex",
                project_hash="project",
                session_id="session",
                turn_id="turn",
                response_sha256="hash-b",
                ttl_seconds=60,
                now=102.0,
            )

        self.assertTrue(first)
        self.assertFalse(duplicate)
        self.assertTrue(changed)


if __name__ == "__main__":
    unittest.main()

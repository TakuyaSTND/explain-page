"""回答集めのシートだけの回は、停止で差し戻さない（2026-10-08・ユーザー裁定）。

裁定＝2026-09-01 の「尋問の回答集めだけの回でも報告の頁を要求する」を**反転**した。
赤ペン（akapen）・尋問（grilling-viz）のシートは人に答えてもらう入力票で、部品の目印
（data-component）を持たない＝検品証にならない。それを理由に差し戻さない。

⚠️免除が成り立つのは全部がそろったときだけ。1つでも欠ければ従来どおり差し戻す。
  ・頁が要る回で、この回の検品証が1件も無い
  ・依頼時の計画があり、その時刻より後に承認済みの置き場の下へ書かれたシートがある
  ・この回に置き場の外へ書いて見送られた頁が無い
"""
from __future__ import annotations

import os
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

HOOKS_DIR = Path(__file__).resolve().parents[1]
if str(HOOKS_DIR) not in sys.path:
    sys.path.insert(0, str(HOOKS_DIR))

from visual.contracts import ExplanationPlan
from visual.entrypoint import _project_hash, handle_event
from visual.policy import load_policy
from visual.sheets import (
    answer_sheet_kind,
    answer_sheet_kind_of_path,
    is_under,
    sheets_written_since,
)
from visual.state import StateStore

HTML_OUTPUT = Path(__file__).resolve().parents[2] / "html-output.md"
REPO = "C:/repo"
SESSION = "session"
TURN = "turn"
PROMPT = "3案を図で比較して選びたい"

AKAPEN_SHEET = (
    "<!DOCTYPE html><html lang=\"ja\"><head><meta charset=\"utf-8\">"
    "<!-- akapen-format: v3 --><title>案の比較</title></head>"
    "<body><form id=\"akForm\"><input type=\"radio\" name=\"q1\"></form>"
    "<script>var lines = [\"【赤ペン回答】\" + DOC];</script></body></html>"
)
SHITEKI_SHEET = (
    "<!DOCTYPE html><html><head><title>指摘</title></head>"
    "<body data-shiteki=\"1\"><p>原稿</p></body></html>"
)
TENSAKU_SHEET = (
    "<!DOCTYPE html><html><head><title>添削</title></head>"
    "<body><p>本文</p><script>var head = '【赤ペン回答】';</script></body></html>"
)
GV_SHEET = (
    "<!DOCTYPE html><html><head><title>尋問</title></head>"
    "<body class=\"gv\"><script type=\"application/json\" id=\"gv-data\">{}</script>"
    "</body></html>"
)
RENDERER_PAGE_WITH_QUOTE = (
    "<!DOCTYPE html><html><head><title>報告</title></head><body>"
    "<header data-component=\"overview\"><p>回答文の頭は【赤ペン回答】で始まる。</p></header>"
    "</body></html>"
)
LONG_RESPONSE = "図で比較しました。" + "選択肢を並べて説明します。" * 60


class SheetFlowCase(unittest.TestCase):
    """一時フォルダを承認済みの置き場にして、依頼→（書き込み）→停止を流す共通の土台。"""

    def setUp(self):
        self._root_dir = tempfile.TemporaryDirectory()
        self._other_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self._root_dir.cleanup)
        self.addCleanup(self._other_dir.cleanup)
        self.root = Path(self._root_dir.name)
        self.other = Path(self._other_dir.name)
        self.policy = load_policy(path=None, env={})
        self.state = StateStore(self.root / "state.db")
        shared = self.root / "shared.md"
        mirror = self.root / "mirror.md"
        project = self.root / "project.md"
        shared.write_text("| 用語 | 説明 |\n|---|---|\n| Hook | 説明 |\n", encoding="utf-8")
        mirror.write_bytes(shared.read_bytes())
        project.write_text("# project\n", encoding="utf-8")
        self.glossary = (shared, mirror, project)
        self.common = {"cwd": REPO, "session_id": SESSION, "turn_id": TURN}

    # -- 流れの部品 --------------------------------------------------------
    def prompt(self, text: str = PROMPT) -> dict:
        return handle_event(
            {**self.common, "hook_event_name": "UserPromptSubmit", "prompt": text},
            runtime="codex", project_root=REPO, policy=self.policy,
            html_output_path=HTML_OUTPUT, state_store=self.state,
        )

    def post(self, path) -> dict:
        return handle_event(
            {**self.common, "hook_event_name": "PostToolUse", "tool_name": "Write",
             "tool_input": {"file_path": str(path)}},
            runtime="codex", project_root=REPO, policy=self.policy,
            html_output_path=HTML_OUTPUT, state_store=self.state,
            glossary_paths=self.glossary, local_artifact_root=self.root,
        )

    def stop(self, message: str = "シートを書きました。") -> dict:
        return handle_event(
            {**self.common, "hook_event_name": "Stop",
             "last_assistant_message": message, "stop_hook_active": False},
            runtime="codex", project_root=REPO, policy=self.policy,
            html_output_path=HTML_OUTPUT, state_store=self.state,
            glossary_paths=self.glossary, local_artifact_root=self.root,
        )

    def write(self, directory: Path, name: str, text: str, *, age: float = 0.0) -> Path:
        """シェルで書いたのと同じ（フックを通らない）。age 秒だけ更新時刻を古くする（sleep しない）。"""
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / name
        path.write_bytes(text.encode("utf-8"))
        stamp = time.time() - age
        os.utime(path, (stamp, stamp))
        return path

    def receipts(self):
        return self.state.load_receipts(
            runtime="codex", project_hash=_project_hash(REPO),
            session_id=SESSION, turn_id=TURN,
        )


class SheetOnlyTurnIsNotBlockedTests(SheetFlowCase):
    def test_akapen_sheet_under_the_approved_root_is_not_blocked(self):
        self.prompt()
        self.write(self.root / "akapen", "案-01.html", AKAPEN_SHEET)

        result = self.stop()

        self.assertNotIn("decision", result)
        self.assertIn("[sheet_only_turn]", result.get("systemMessage", ""))
        self.assertIn("akapen: 案-01.html", result["systemMessage"])

    def _assert_sheet_passes(self, name: str, text: str) -> None:
        self.prompt()
        self.write(self.root / "akapen", name, text)

        result = self.stop()

        self.assertNotIn("decision", result)
        self.assertIn("akapen: " + name, result.get("systemMessage", ""))

    def test_the_standard_mode_sheet_passes(self):
        self._assert_sheet_passes("standard.html", AKAPEN_SHEET)

    def test_the_pointing_mode_sheet_passes(self):
        self._assert_sheet_passes("shiteki.html", SHITEKI_SHEET)

    def test_the_editing_mode_sheet_passes(self):
        self._assert_sheet_passes("tensaku.html", TENSAKU_SHEET)

    def test_grilling_viz_sheet_in_the_root_is_not_blocked(self):
        self.prompt()
        self.write(self.root, "grill-01.html", GV_SHEET)

        result = self.stop()

        self.assertNotIn("decision", result)
        self.assertIn("grilling-viz: grill-01.html", result.get("systemMessage", ""))

    def test_a_sheet_written_by_the_write_tool_is_not_blocked_either(self):
        self.prompt()
        sheet = self.write(self.root / "akapen", "x.html", AKAPEN_SHEET)

        self.post(sheet)
        result = self.stop()

        self.assertNotIn("decision", result)

    def test_the_message_names_how_many_more_sheets(self):
        self.prompt()
        self.write(self.root / "akapen", "one.html", AKAPEN_SHEET)
        self.write(self.root / "akapen", "two.html", SHITEKI_SHEET)

        result = self.stop()

        self.assertIn("ほか1件", result.get("systemMessage", ""))

    def test_no_url_scheme_or_personal_name_in_the_message(self):
        self.prompt()
        self.write(self.root / "akapen", "x.html", AKAPEN_SHEET)

        message = self.stop()["systemMessage"]

        for banned in ("http://", "https://", "file://"):
            self.assertNotIn(banned, message)


class TheExemptionStaysClosedTests(SheetFlowCase):
    def test_a_sheet_outside_the_root_still_blocks(self):
        self.prompt()
        self.write(self.other, "outside.html", AKAPEN_SHEET)

        result = self.stop()

        self.assertEqual(result.get("decision"), "block")

    def test_a_sheet_older_than_the_turn_still_blocks(self):
        self.prompt()
        self.write(self.root / "akapen", "old.html", AKAPEN_SHEET, age=100.0)

        result = self.stop()

        self.assertEqual(result.get("decision"), "block")
        self.assertIn("[receipt_missing]", result["reason"])

    def test_a_renderer_page_that_quotes_the_marker_is_not_a_sheet(self):
        self.prompt()
        self.write(self.root / "akapen", "report.html", RENDERER_PAGE_WITH_QUOTE)

        result = self.stop()

        self.assertEqual(result.get("decision"), "block")
        self.assertIn("[receipt_missing]", result["reason"])

    def test_one_grilling_viz_marker_alone_is_not_a_sheet(self):
        self.prompt()
        self.write(self.root, "half.html", '<html><body class="gv"><p>引用</p></body></html>')

        result = self.stop()

        self.assertEqual(result.get("decision"), "block")

    def test_a_failing_renderer_page_with_the_sheet_still_blocks(self):
        self.prompt()
        self.write(self.root / "akapen", "sheet.html", AKAPEN_SHEET)
        report = self.write(self.root, "report.html", '<header data-component="overview"><p>本文</p></header>')
        self.post(report)
        self.assertNotEqual(len(self.receipts()), 0)

        result = self.stop()

        self.assertEqual(result.get("decision"), "block")
        self.assertIn("[receipt_not_valid]", result["reason"])

    def test_a_report_page_written_outside_the_root_with_the_sheet_still_blocks(self):
        self.prompt()
        self.write(self.root / "akapen", "sheet.html", AKAPEN_SHEET)
        outside = self.write(self.other, "report.html", "<html><body><p>手書きの報告</p></body></html>")
        self.post(outside)

        result = self.stop()

        self.assertEqual(result.get("decision"), "block")

    def test_without_a_saved_plan_it_still_blocks(self):
        # 依頼時の計画が無い＝回の開始時刻が分からない＝免除しない（fail-closed）。
        self.write(self.root / "akapen", "sheet.html", AKAPEN_SHEET)

        result = self.stop(LONG_RESPONSE)

        self.assertEqual(result.get("decision"), "block")

    def test_when_the_start_time_is_unavailable_it_still_blocks(self):
        # 期限切れ・読めない＝回の開始時刻が None＝免除しない（fail-closed）。
        self.prompt()
        self.write(self.root / "akapen", "sheet.html", AKAPEN_SHEET)

        with patch.object(self.state, "load_plan_created_at", return_value=None):
            result = self.stop()

        self.assertEqual(result.get("decision"), "block")

    def _hermes(self, event: str, turn: str, extra: dict) -> dict:
        return handle_event(
            {"cwd": REPO, "session_id": SESSION, "hook_event_name": event,
             "extra": {"turn_id": turn, **extra}},
            runtime="hermes", project_root=REPO, policy=self.policy,
            html_output_path=HTML_OUTPUT, state_store=self.state,
            glossary_paths=self.glossary, local_artifact_root=self.root,
        )

    def test_hermes_control_without_a_sheet_continues(self):
        self._hermes("pre_llm_call", "h1", {"user_message": PROMPT})

        control = self._hermes(
            "pre_verify", "h1",
            {"final_response": "シートを書きました。", "coding": True, "attempt": 0},
        )

        self.assertEqual(control.get("action"), "continue")

    def test_hermes_exemption_returns_nothing(self):
        # Hermes の pre_verify に message だけを返したときの扱いは未確認＝何も返さない。
        self._hermes("pre_llm_call", "h2", {"user_message": PROMPT})
        self.write(self.root / "akapen", "sheet.html", AKAPEN_SHEET)

        exempt = self._hermes(
            "pre_verify", "h2",
            {"final_response": "シートを書きました。", "coding": True, "attempt": 0},
        )

        self.assertEqual(exempt, {})


class PostToolUseSheetTests(SheetFlowCase):
    def test_republishing_an_old_sheet_counts_it_for_this_turn(self):
        # 2026-10-08（本物の会話で見つけた）：知らせが割り込んで回の始まりが公開の後ろへずれても、
        #   返事の直前にシートを公開し直せば（PostToolUse が更新時刻を今にする）停止で通る。
        self.prompt()
        sheet = self.write(self.root / "akapen", "old.html", AKAPEN_SHEET, age=100.0)
        before = sheet.stat().st_mtime

        self.post(sheet)
        result = self.stop()

        self.assertGreater(sheet.stat().st_mtime, before + 50)
        self.assertNotIn("decision", result)
        self.assertIn("[sheet_only_turn]", result.get("systemMessage", ""))

    def test_a_plain_page_outside_the_root_is_not_touched(self):
        self.prompt()
        page = self.write(self.other, "plain.html", "<html><body>x</body></html>", age=100.0)
        before = page.stat().st_mtime

        self.post(page)

        self.assertEqual(page.stat().st_mtime, before)

    def test_a_sheet_in_the_root_makes_no_receipt_and_no_skip_record(self):
        self.prompt()
        sheet = self.write(self.root / "akapen", "x.html", AKAPEN_SHEET)

        result = self.post(sheet)

        self.assertIn("[回答集めのシート]", result.get("systemMessage", ""))
        self.assertIn("akapen", result["systemMessage"])
        self.assertEqual(len(self.receipts()), 0)
        self.assertEqual(self.state.load_receipt_skip_tally(project_hash=_project_hash(REPO), days=1), ())
        self.assertEqual(self.state.load_receipt_skips(project_hash=_project_hash(REPO)), ())

    def test_a_sheet_outside_the_root_keeps_the_skip_path_and_says_where_to_write(self):
        self.prompt()
        sheet = self.write(self.other, "x.html", AKAPEN_SHEET)

        result = self.post(sheet)

        message = result.get("systemMessage", "")
        self.assertIn("[検品証なし]", message)
        self.assertIn("の下に書けば差し戻されない", message)
        self.assertIn(str(self.root / "akapen"), message)
        self.assertIn("akapen", message)
        self.assertEqual(len(self.receipts()), 0)
        tally = self.state.load_receipt_skip_tally(project_hash=_project_hash(REPO), days=1)
        self.assertEqual(tally[0][1], 1)

    def test_a_plain_page_outside_the_root_gets_no_sheet_hint(self):
        self.prompt()
        page = self.write(self.other, "plain.html", "<html><body><p>手書き</p></body></html>")

        message = self.post(page).get("systemMessage", "")

        self.assertIn("[検品証なし]", message)
        self.assertNotIn("回答集めのシート", message)

    def test_a_renderer_page_in_the_root_is_still_inspected(self):
        self.prompt()
        page = self.write(self.root, "report.html", RENDERER_PAGE_WITH_QUOTE)

        result = self.post(page)

        self.assertNotIn("[回答集めのシート]", str(result))
        self.assertEqual(len(self.receipts()), 1)

    def test_the_hermes_wire_shape_is_a_plain_message(self):
        sheet = self.write(self.root / "akapen", "x.html", AKAPEN_SHEET)

        result = handle_event(
            {"cwd": REPO, "session_id": SESSION, "hook_event_name": "post_tool_call",
             "tool_name": "write_file", "tool_input": {"path": str(sheet)},
             "extra": {"turn_id": TURN}},
            runtime="hermes", project_root=REPO, policy=self.policy,
            html_output_path=HTML_OUTPUT, state_store=self.state,
            glossary_paths=self.glossary, local_artifact_root=self.root,
        )

        self.assertEqual(list(result), ["message"])
        self.assertIn("[回答集めのシート]", result["message"])


class MessagesTellTheNewWayTests(SheetFlowCase):
    def test_receipt_missing_says_where_a_sheet_would_pass(self):
        self.prompt()

        reason = self.stop(LONG_RESPONSE)["reason"]

        self.assertIn("[receipt_missing]", reason)
        self.assertIn("回答集めのシートだけの回なら", reason)
        self.assertIn(str(self.root / "akapen"), reason)
        self.assertLess(len(reason), 2500)

    def test_receipt_not_valid_keeps_the_report_page_requirement(self):
        self.prompt()
        report = self.write(self.root, "report.html", '<header data-component="overview"><p>本文</p></header>')
        self.post(report)

        reason = self.stop(LONG_RESPONSE)["reason"]

        self.assertIn("[receipt_not_valid]", reason)
        self.assertIn("報告と判断の頁を別にレンダラーで作る", reason)
        self.assertLess(len(reason), 2500)


class PlanCreatedAtTests(unittest.TestCase):
    def _plan(self):
        return ExplanationPlan(
            audience="project_novice", depth="deep", components=("overview",),
            reason_codes=(), provisional=False, should_continue=False,
            delivery="local_html", publish_policy="never",
        )

    def test_it_returns_the_saved_time_and_none_after_expiry(self):
        with tempfile.TemporaryDirectory() as td:
            store = StateStore(Path(td) / "state.db")
            store.save_plan(
                runtime="codex", project_hash="p", session_id="s", turn_id="t",
                plan=self._plan(), ttl_seconds=60, now=100.0,
            )
            key = dict(runtime="codex", project_hash="p", session_id="s", turn_id="t")

            self.assertEqual(store.load_plan_created_at(**key, now=120.0), 100.0)
            self.assertIsNone(store.load_plan_created_at(**key, now=161.0))
            self.assertIsNone(store.load_plan_created_at(**{**key, "turn_id": "other"}, now=120.0))

    def test_the_plan_itself_is_unchanged(self):
        with tempfile.TemporaryDirectory() as td:
            store = StateStore(Path(td) / "state.db")
            store.save_plan(
                runtime="codex", project_hash="p", session_id="s", turn_id="t",
                plan=self._plan(), ttl_seconds=60, now=100.0,
            )
            plan = store.load_plan(
                runtime="codex", project_hash="p", session_id="s", turn_id="t", now=120.0
            )

        self.assertEqual(plan, self._plan())

    def test_skips_can_be_cut_by_a_start_time(self):
        with tempfile.TemporaryDirectory() as td:
            store = StateStore(Path(td) / "state.db")
            for stamp, name in ((100.0, "old.html"), (200.0, "new.html")):
                store.save_receipt_skip(
                    runtime="codex", project_hash="p", session_id="s", turn_id="t",
                    path=name, reason="r", ttl_seconds=1000, now=stamp,
                )
            both = store.load_receipt_skips(project_hash="p", session_id="s", now=300.0)
            recent = store.load_receipt_skips(project_hash="p", session_id="s", now=300.0, since=150.0)

        self.assertEqual(len(both), 2)
        self.assertEqual([path for path, _ in recent], ["new.html"])


class AnswerSheetKindTests(unittest.TestCase):
    def test_each_akapen_marker_alone_is_enough(self):
        self.assertEqual(answer_sheet_kind(AKAPEN_SHEET), "akapen")
        self.assertEqual(answer_sheet_kind("<!-- akapen-format: v3 --><p>x</p>"), "akapen")
        self.assertEqual(answer_sheet_kind("<p>【赤ペン回答】</p>"), "akapen")
        self.assertEqual(answer_sheet_kind(SHITEKI_SHEET), "akapen")

    def test_grilling_viz_needs_both_markers(self):
        self.assertEqual(answer_sheet_kind(GV_SHEET), "grilling-viz")
        self.assertIsNone(answer_sheet_kind('<body class="gv"><p>x</p>'))
        self.assertIsNone(answer_sheet_kind('<script id="gv-data">{}</script>'))

    def test_a_renderer_page_is_never_a_sheet(self):
        self.assertIsNone(answer_sheet_kind(RENDERER_PAGE_WITH_QUOTE))
        self.assertIsNone(answer_sheet_kind(AKAPEN_SHEET + '<header data-component="overview">'))

    def test_other_text_is_not_a_sheet(self):
        for value in ("", "<html><body><p>手書き</p></body></html>", None, 123, b"bytes"):
            with self.subTest(value=value):
                self.assertIsNone(answer_sheet_kind(value))

    def test_path_version_reads_the_file_and_never_raises(self):
        with tempfile.TemporaryDirectory() as td:
            sheet = Path(td) / "s.html"
            sheet.write_bytes(AKAPEN_SHEET.encode("utf-8"))
            text_file = Path(td) / "s.txt"
            text_file.write_bytes(AKAPEN_SHEET.encode("utf-8"))

            self.assertEqual(answer_sheet_kind_of_path(sheet), "akapen")
            self.assertIsNone(answer_sheet_kind_of_path(text_file))
            self.assertIsNone(answer_sheet_kind_of_path(Path(td) / "missing.html"))
            self.assertIsNone(answer_sheet_kind_of_path(td))
            self.assertIsNone(answer_sheet_kind_of_path(None))
            self.assertIsNone(answer_sheet_kind_of_path("bad\0name.html"))

    def test_a_marker_after_a_large_body_is_still_found(self):
        # 添削モードは記事の全文を抱える＝回答文の印が後ろにあっても見つける。
        with tempfile.TemporaryDirectory() as td:
            sheet = Path(td) / "big.html"
            body = "<html><body>" + "あ" * 1000 + "</body><script>【赤ペン回答】</script></html>"
            sheet.write_bytes(body.encode("utf-8"))

            self.assertEqual(answer_sheet_kind_of_path(sheet, max_bytes=500), "akapen")


class SheetsWrittenSinceTests(unittest.TestCase):
    def _put(self, path: Path, text: str, stamp: float) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(text.encode("utf-8"))
        os.utime(path, (stamp, stamp))

    def test_only_recent_sheets_come_back_newest_first(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            self._put(root / "akapen" / "new.html", AKAPEN_SHEET, 1000.0)
            self._put(root / "newer.html", GV_SHEET, 1010.0)
            self._put(root / "akapen" / "old.html", AKAPEN_SHEET, 500.0)
            self._put(root / "note.txt", AKAPEN_SHEET, 1000.0)
            self._put(root / "plain.html", "<p>手書き</p>", 1000.0)

            found = sheets_written_since(root, 900.0)

        self.assertEqual([(Path(p).name, kind) for p, kind in found],
                         [("newer.html", "grilling-viz"), ("new.html", "akapen")])

    def test_the_tolerance_is_two_seconds(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            self._put(root / "inside.html", AKAPEN_SHEET, 998.5)
            self._put(root / "outside.html", AKAPEN_SHEET, 997.0)

            found = sheets_written_since(root, 1000.0)

        self.assertEqual([Path(p).name for p, _ in found], ["inside.html"])

    def test_it_goes_three_levels_down_and_no_further(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            self._put(root / "a" / "b" / "c" / "three.html", AKAPEN_SHEET, 1000.0)
            self._put(root / "a" / "b" / "c" / "d" / "four.html", AKAPEN_SHEET, 1000.0)

            found = sheets_written_since(root, 900.0)

        self.assertEqual([Path(p).name for p, _ in found], ["three.html"])

    def test_turn_markers_and_caches_are_skipped(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            self._put(root / "current-turn" / "x.html", AKAPEN_SHEET, 1000.0)
            self._put(root / "__pycache__" / "y.html", AKAPEN_SHEET, 1000.0)

            self.assertEqual(sheets_written_since(root, 900.0), ())

    def test_failures_come_back_as_empty(self):
        with tempfile.TemporaryDirectory() as td:
            self.assertEqual(sheets_written_since(Path(td) / "missing", 0.0), ())
            self.assertEqual(sheets_written_since(td, "not a number"), ())  # type: ignore[arg-type]
            self.assertEqual(sheets_written_since(None, 0.0), ())

    def test_the_read_count_is_capped(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            for index in range(5):
                self._put(root / ("s%d.html" % index), AKAPEN_SHEET, 1000.0)

            self.assertEqual(len(sheets_written_since(root, 900.0, max_files=2)), 2)


class IsUnderTests(unittest.TestCase):
    def test_inside_outside_and_lookalike_siblings(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "root"
            lookalike = Path(td) / "root-other"
            root.mkdir()
            lookalike.mkdir()

            self.assertTrue(is_under(root / "akapen" / "x.html", root))
            self.assertTrue(is_under(root, root))
            self.assertFalse(is_under(lookalike / "x.html", root))
            self.assertFalse(is_under(Path(td) / "x.html", root))
            self.assertFalse(is_under(None, root))
            self.assertFalse(is_under(root / "x.html", None))


if __name__ == "__main__":
    unittest.main()

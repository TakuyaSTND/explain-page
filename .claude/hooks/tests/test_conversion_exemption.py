"""変換だけの回は、停止で差し戻さない（2026-10-15・利用者の選択＝案9(b) の A）。

裁定＝依頼に速さの合図（早く・はやく・爆速・そのまま・とりあえず・仮）と変換の語（PDFにして・PDF化・
docxにして…）の**両方**がある回は、変換の短い報告で終われば頁を求めない。合図だけ・変換の語だけ・
LaTeX 指定（速さの合図の無い変換）は免除しない。

⚠️免除が成り立つのは全部がそろったときだけ。1つでも欠ければ従来どおり差し戻す（fail-closed）。
  ・依頼時の計画があり、その reason に conversion_only_request がある
  ・頁が要る回で、この回に道具を使い、検品証が1件も無い
  ・回の開始時刻が分かり、それより後に置き場の外へ書いて見送られた頁が無い
  ・応答が短い（min_chars 未満）・構造が重くない（min_blocks 未満）・確定した計画に decision が無い
⚠️応答の図の合図は見ない（計画からの変更・2026-10-15）＝変換の報告は「図と文字が崩れていない」のように
  出来上がりを説明し、置き場のパスにも visual の文字が入る。過去の会話の再生で、免除の対象になり得た
  2回とも、図の合図だけで免除されなかった。
⚠️印つきの回を差し戻すときは、欠けた条件を [conversion_not_exempt] の1行で添える（要求は緩めない）。
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

from visual import branding
from visual.entrypoint import _project_hash, handle_event
from visual.policy import load_policy
from visual.state import StateStore

HTML_OUTPUT = Path(__file__).resolve().parents[2] / "html-output.md"
REPO = "C:/repo"
SESSION = "session"
TURN = "turn"
PROMPT = "PDFにして　早く"
SHORT_REPLY = "PDFにしました。15頁で、ダウンロードの置き場に保存してあります。"
FIGURE_REPLY = (
    "PDFにして送りました（A4・27ページ）。保存先は一時フォルダの report-visual の下です。"
    "冒頭の3ページを画像にして、図と文字が崩れていないことを確かめました。"
)
LONG_REPLY = "PDFにしました。" + "中身を順に説明します。" * 80
DECISION_REPLY = "PDFにしました。次はどれにしますか。案Aを採用するかも決めてください。"
HEAVY_REPLY = "PDFにしました。\n" + "\n".join("- 項目%d" % index for index in range(1, 9))
RENDERER_PAGE = '<header data-component="overview"><p>本文</p></header>'


class ConversionFlowCase(unittest.TestCase):
    """一時フォルダを承認済みの置き場にして、依頼→（書き込み）→停止を流す共通の土台。

    ⚠️方針は explain_mode=always（このリポジトリと同じ）＝道具を使った回は常に頁が要る。
    """

    def setUp(self):
        self._root_dir = tempfile.TemporaryDirectory()
        self._other_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self._root_dir.cleanup)
        self.addCleanup(self._other_dir.cleanup)
        self.root = Path(self._root_dir.name)
        self.other = Path(self._other_dir.name)
        self.policy = load_policy(path=None, env={branding.ENV_MODE: "always"})
        self.state = StateStore(self.root / "state.db")
        shared = self.root / "shared.md"
        mirror = self.root / "mirror.md"
        project = self.root / "project.md"
        shared.write_text("| 用語 | 説明 |\n|---|---|\n| Hook | 説明 |\n", encoding="utf-8")
        mirror.write_bytes(shared.read_bytes())
        project.write_text("# project\n", encoding="utf-8")
        self.glossary = (shared, mirror, project)
        self.common = {"cwd": REPO, "session_id": SESSION, "turn_id": TURN}

    def prompt(self, text: str = PROMPT, policy=None) -> dict:
        return handle_event(
            {**self.common, "hook_event_name": "UserPromptSubmit", "prompt": text},
            runtime="codex", project_root=REPO, policy=policy or self.policy,
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

    def stop(self, message: str = SHORT_REPLY, policy=None) -> dict:
        return handle_event(
            {**self.common, "hook_event_name": "Stop",
             "last_assistant_message": message, "stop_hook_active": False},
            runtime="codex", project_root=REPO, policy=policy or self.policy,
            html_output_path=HTML_OUTPUT, state_store=self.state,
            glossary_paths=self.glossary, local_artifact_root=self.root,
        )

    def write(self, directory: Path, name: str, text: str) -> Path:
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / name
        path.write_bytes(text.encode("utf-8"))
        stamp = time.time()
        os.utime(path, (stamp, stamp))
        return path

    def receipts(self):
        return self.state.load_receipts(
            runtime="codex", project_hash=_project_hash(REPO),
            session_id=SESSION, turn_id=TURN,
        )


class ConversionOnlyTurnIsNotBlockedTests(ConversionFlowCase):
    def test_a_quick_conversion_with_a_short_reply_is_not_blocked(self):
        self.prompt()

        result = self.stop()

        self.assertNotIn("decision", result)
        message = result.get("systemMessage", "")
        self.assertIn("[conversion_only_turn]", message)
        self.assertIn("応答%d字" % len(SHORT_REPLY), message)

    def test_each_marked_request_shape_passes(self):
        for index, text in enumerate((
            "PDF化して　そのままでいい　早く",
            "このアーティファクトをPDFにして　爆速で",
            "とりあえず現状のものだけでいいから　とりあえずPDFに書き出して（仮）であることを明示して",
        )):
            with self.subTest(text=text):
                self.common["turn_id"] = "turn-pass-%d" % index
                self.prompt(text)
                result = self.stop()
                self.assertNotIn("decision", result)
                self.assertIn("[conversion_only_turn]", result.get("systemMessage", ""))

    def test_a_reply_that_describes_figures_and_a_visual_path_still_passes(self):
        # 計画からの変更＝応答の図の合図は見ない（変換の報告は出来上がりの図に触れる）。
        self.prompt()

        result = self.stop(FIGURE_REPLY)

        self.assertNotIn("decision", result)
        self.assertIn("[conversion_only_turn]", result.get("systemMessage", ""))

    def test_no_url_scheme_in_the_message(self):
        self.prompt()

        message = self.stop()["systemMessage"]

        for banned in ("http://", "https://", "file://"):
            self.assertNotIn(banned, message)


class TheExemptionStaysClosedTests(ConversionFlowCase):
    def test_a_long_reply_still_blocks_and_says_why(self):
        self.prompt()

        result = self.stop(LONG_REPLY)

        self.assertEqual(result.get("decision"), "block")
        reason = result["reason"]
        self.assertIn("[receipt_missing]", reason)
        self.assertIn("[conversion_not_exempt]", reason)
        self.assertIn("応答が%d字（700字未満なら免除）" % len(LONG_REPLY), reason)
        self.assertLess(len(reason), 2500)

    def test_a_reply_with_a_decision_signal_still_blocks(self):
        self.prompt()

        result = self.stop(DECISION_REPLY)

        self.assertEqual(result.get("decision"), "block")
        self.assertIn("応答に判断の合図がある", result["reason"])

    def test_a_reply_with_heavy_structure_still_blocks(self):
        self.prompt()

        result = self.stop(HEAVY_REPLY)

        self.assertEqual(result.get("decision"), "block")
        self.assertIn("応答の見出し・箇条・表の行が8個（8個未満なら免除）", result["reason"])

    def test_requests_without_both_signals_still_block(self):
        # ⚠️回ごとに番号を変える＝同じ回で同じ応答を2度差し戻さない仕組み（claim_response）に当てない。
        for index, text in enumerate((
            "LaTeXでPDF化して",
            "とりあえず確認して",
            "頁を作ってPDFにして早く",
            "PDF 出力の作業のコミットして",
        )):
            with self.subTest(text=text):
                self.common["turn_id"] = "turn-block-%d" % index
                self.prompt(text)
                result = self.stop()
                self.assertEqual(result.get("decision"), "block")
                self.assertNotIn("[conversion_only_turn]", str(result))
                self.assertNotIn("[conversion_not_exempt]", str(result))

    def test_a_turn_with_a_failing_page_still_blocks(self):
        self.prompt()
        page = self.write(self.root, "report.html", RENDERER_PAGE)
        self.post(page)
        self.assertNotEqual(len(self.receipts()), 0)

        result = self.stop()

        self.assertEqual(result.get("decision"), "block")
        self.assertIn("[receipt_not_valid]", result["reason"])
        self.assertIn("この回に頁を出した", result["reason"])

    def test_a_page_written_outside_the_root_still_blocks(self):
        self.prompt()
        outside = self.write(self.other, "report.html", "<html><body><p>手書きの報告</p></body></html>")
        self.post(outside)

        result = self.stop()

        self.assertEqual(result.get("decision"), "block")
        self.assertIn("承認済みの置き場の外へ頁を書いた", result["reason"])

    def test_without_a_saved_plan_it_still_blocks(self):
        # 依頼時の計画が無い＝依頼の合図が分からない＝免除しない（fail-closed）。
        result = self.stop()

        self.assertEqual(result.get("decision"), "block")
        self.assertNotIn("[conversion_not_exempt]", result["reason"])

    def test_when_the_start_time_is_unavailable_it_still_blocks(self):
        self.prompt()

        with patch.object(self.state, "load_plan_created_at", return_value=None):
            result = self.stop()

        self.assertEqual(result.get("decision"), "block")
        self.assertIn("回の始まりの時刻が分からない", result["reason"])

    def test_in_auto_mode_nothing_is_said_when_no_page_is_needed(self):
        # 頁が要らない回（auto の短い依頼）は従来どおり黙って通す＝免除の1行は出さない。
        auto = load_policy(path=None, env={branding.ENV_MODE: "auto"})
        self.prompt(policy=auto)

        result = self.stop(policy=auto)

        self.assertEqual(result, {})

    def _hermes(self, event: str, turn: str, extra: dict) -> dict:
        return handle_event(
            {"cwd": REPO, "session_id": SESSION, "hook_event_name": event,
             "extra": {"turn_id": turn, **extra}},
            runtime="hermes", project_root=REPO, policy=self.policy,
            html_output_path=HTML_OUTPUT, state_store=self.state,
            glossary_paths=self.glossary, local_artifact_root=self.root,
        )

    def test_hermes_control_without_the_signals_continues(self):
        self._hermes("pre_llm_call", "h1", {"user_message": "LaTeXでPDF化して"})

        control = self._hermes(
            "pre_verify", "h1",
            {"final_response": SHORT_REPLY, "coding": True, "attempt": 0},
        )

        self.assertEqual(control.get("action"), "continue")

    def test_hermes_exemption_returns_nothing(self):
        # Hermes の pre_verify に message だけを返したときの扱いは未確認＝何も返さない（シートの免除と同じ）。
        self._hermes("pre_llm_call", "h2", {"user_message": PROMPT})

        exempt = self._hermes(
            "pre_verify", "h2",
            {"final_response": SHORT_REPLY, "coding": True, "attempt": 0},
        )

        self.assertEqual(exempt, {})


if __name__ == "__main__":
    unittest.main()

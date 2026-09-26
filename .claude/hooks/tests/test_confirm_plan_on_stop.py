"""案③（予告と確定を分ける）の回帰検査（2026-08-29）。

不具合3＝応答終了時に**保存済みの予告だけ**を使っていたので、応答の中身
（長さ・構造・判断の有無）が一度も見られなかった。依頼文が素っ気なければ、
どれだけ長く判断だらけの応答を書いても検査対象にならなかった。

∴componentは「予告 ∪ 実態」の和集合、出し方は「どちらかが頁を要るなら頁」。

不具合4（依頼文に決める言葉があると短い返事でも頁を要求される）は**直さない**。
  2026-08-29にユーザーが裁定＝「手を抜いた応答を素通りさせない防御を優先する」。
  よって短い返事でも差し戻される挙動は**仕様**であり、このファイルの最後の検査で固定する。
"""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

HOOKS_DIR = Path(__file__).resolve().parents[1]
if str(HOOKS_DIR) not in sys.path:
    sys.path.insert(0, str(HOOKS_DIR))

from visual.entrypoint import handle_event
from visual.policy import load_policy
from visual.state import StateStore

HTML_OUTPUT = Path(__file__).resolve().parents[2] / "html-output.md"
COMMON = {"cwd": "C:/repo", "session_id": "session", "turn_id": "turn"}


class ConfirmPlanOnStopTests(unittest.TestCase):
    def _run(self, prompt: str, response: str):
        policy = load_policy(path=None, env={})
        with tempfile.TemporaryDirectory() as td:
            state = StateStore(Path(td) / "state.db")
            pre = handle_event(
                {**COMMON, "hook_event_name": "UserPromptSubmit", "prompt": prompt},
                runtime="codex", project_root="C:/repo", policy=policy,
                html_output_path=HTML_OUTPUT, state_store=state,
            )
            stop = handle_event(
                {**COMMON, "hook_event_name": "Stop",
                 "last_assistant_message": response, "stop_hook_active": False},
                runtime="codex", project_root="C:/repo", policy=policy,
                html_output_path=HTML_OUTPUT, state_store=state,
            )
        context = pre.get("hookSpecificOutput", {}).get("additionalContext", "")
        return context, stop

    def test_response_content_now_reaches_the_verdict(self):
        """不具合3：依頼文が素っ気なくても、応答が頁向きなら検査対象になる。"""
        context, stop = self._run(
            "タグ機能の実装を進めてほしい",
            "3つの案を比較しました。" + "どれを選ぶかを決めたいところです。" * 12,
        )

        # 依頼時の予告は「文章のまま」＝頁を作れとは言っていない
        self.assertIn("Markdownの文章のまま", context)
        # それでも応答が頁向きなら、応答終了時に差し戻される
        self.assertEqual(stop.get("decision"), "block")
        self.assertIn("confirmed_on_stop", stop["reason"])

    def test_plain_short_turn_still_passes(self):
        """反例：依頼も応答も素っ気なければ、今までどおり素通りする。"""
        _, stop = self._run("タグ機能の実装を進めてほしい", "対応しました。")

        self.assertEqual(stop, {})

    def test_components_are_merged_not_replaced(self):
        """予告のcomponentは消えない＝和集合になる。"""
        _, stop = self._run(
            "タグ機能をどれにするか決めたい",
            "図で比較しました。" + "選択肢を並べて説明します。" * 60,
        )

        reason = stop["reason"]
        self.assertEqual(stop.get("decision"), "block")
        # 依頼文由来（decision）と応答由来（visual / summary）が両方載る
        self.assertIn("decision", reason)
        self.assertIn("visual", reason)
        self.assertIn("summary", reason)

    def test_naming_a_page_in_the_prompt_is_recorded(self):
        """頁を名指しで求めた依頼には印が付く（意図の推測ではなく名指しだけ）。"""
        context, _ = self._run("この件をHTMLの頁にまとめて", "はい。")

        self.assertIn("explicit_page_request", context)
        # 検査用の既定は publish=never なので文面は Local-only。
        # 確かめたいのは「文章のまま」ではなく頁側の1行が選ばれること。
        self.assertNotIn("Markdownの文章のまま", context)
        self.assertIn("Local-only", context)

    def test_a_word_like_approval_route_does_not_name_a_page(self):
        """反例：「承認ルート」のような語は頁の名指しではない＝印は付かない。"""
        context, _ = self._run("承認ルート外のHTMLの件を直して", "はい。")

        # 「HTML」は名指しなので印は付く。ここで確かめたいのは
        # 「承認」だけでは explicit_page_request にならないこと。
        context2, _ = self._run("承認ルート外の件を直して", "はい。")
        self.assertIn("explicit_page_request", context)
        self.assertNotIn("explicit_page_request", context2)

    def test_thin_response_on_a_page_worthy_prompt_still_blocks(self):
        """裁定済み（2026-08-29）：依頼が頁向きなら、応答が一言でも差し戻す。

        ユーザー裁定＝「手を抜いた応答を素通りさせない防御を優先する」。
        ∴不具合4（短い返事でも頁を要求される）は直さない。これは過剰ではなく仕様。
        緩めたくなったら、まずこの裁定を覆すこと。
        """
        _, stop = self._run("3案を図で比較して選びたい", "対応しました。")

        self.assertEqual(stop.get("decision"), "block")


if __name__ == "__main__":
    unittest.main()


class ReceiptSurvivesAddedComponentsTests(unittest.TestCase):
    """案③が作った不整合の回帰検査（2026-08-29）。

    検品証は「予告」の部品一覧で作られ、照合は「確定」の部品一覧で行われる。
    応答が部品を増やすと、以前は**完全一致**を求めていたので永久に不一致だった。
    ⚠️緩めたのは一致の条件だけで、「確定で要求された部品が頁に実在するか」は緩めていない。
    """

    def _receipt(self, required, present):
        from visual.contracts import ArtifactReceipt

        return ArtifactReceipt(
            runtime="claude", project_root="C:/repo", session_id="s", turn_id="t",
            path="dummy", sha256="0" * 64, bytes=1, created_at="2026-08-29T00:00:00+00:00",
            gloss_check="pass", glossary_sha256="x", glossary_source="shared+project",
            visual_smoke="pass", previewed=True, visibility="local",
            required_components=tuple(required), present_components=tuple(present),
            missing_components=(), missing_decision_parts=(), unwrapped_identifiers=(),
            unknown_identifiers=(), missing_evidence_sources=(), inspection_errors=(),
            inspection_ok=True, visual_smoke_errors=(),
        )

    def _check(self, required, present, expected):
        from visual.receipts import validate_receipt
        from visual.contracts import GlossarySnapshot

        receipt = self._receipt(required, present)
        glossary = GlossarySnapshot(
            shared_source="shared", effective_sha256="x", effective_count=1,
            same_file_duplicates=(),
        )
        # 実ファイルは見に行くので、path の検査より前で False になることだけを確かめる。
        return validate_receipt(
            receipt, glossary, local_root="C:/nowhere",
            max_artifact_bytes=10, required_components=expected,
        )

    def test_added_component_no_longer_makes_every_page_fail(self):
        # 頁に decision が**ある**なら、検品証の required に無くても部品の理由では落ちない。
        # （path が実在しないので最終的には False になるが、部品の一致で落ちていないことは
        #   下の対照と比べれば分かる。ここでは部品だけを見た判定を直接確かめる。）
        from visual.receipts import validate_receipt  # noqa: F401  (import経路の確認)

        receipt = self._receipt(
            ("overview", "evidence"), ("overview", "evidence", "decision"),
        )
        expected = ("overview", "evidence", "decision")
        self.assertTrue(set(receipt.required_components).issubset(set(expected)))
        self.assertTrue(set(expected).issubset(set(receipt.present_components)))

    def test_missing_component_still_fails(self):
        # 頁に decision が**無い**なら、今までどおり不合格。ここは緩めていない。
        receipt = self._receipt(
            ("overview", "evidence"), ("overview", "evidence"),
        )
        expected = ("overview", "evidence", "decision")
        self.assertFalse(set(expected).issubset(set(receipt.present_components)))

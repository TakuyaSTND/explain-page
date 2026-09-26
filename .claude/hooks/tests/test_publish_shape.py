"""公開しようとした時点で中身を見る検査（2026-09-01 ユーザー裁定）。

⚠️それまでは、承認済みの置き場の外に出した頁には「検品証を作れませんでした」しか出ず、
   **何が足りないのか**が分からなかった。∴手書きの頁がそのまま公開され続けた
   （別セッションが実際にそうしていた）。

∴置き場の外でも**中身は見る**。⚠️止めはしない＝作業は続行できる。
"""
from __future__ import annotations

import io
import sys
import tempfile
import unittest
from pathlib import Path

HOOKS_DIR = Path(__file__).resolve().parents[1]
if str(HOOKS_DIR) not in sys.path:
    sys.path.insert(0, str(HOOKS_DIR))

from visual.contracts import ExplanationPlan
from visual.entrypoint import _describe_shape
from visual.render_components import render_components

NL = chr(10)
NEEDED = ("overview", "walkthrough")


def _write(td, name, body):
    path = Path(td) / name
    io.open(path, "w", encoding="utf-8", newline=NL).write(body)
    return str(path)


class HandWrittenPagesAreDescribedTests(unittest.TestCase):
    def test_a_page_without_markers_is_called_out(self):
        with tempfile.TemporaryDirectory() as td:
            path = _write(td, "hand.html",
                          "<!doctype html><html><body><h1>手書き</h1><p>本文</p></body></html>")
            note = _describe_shape(path, {}, NEEDED)

        self.assertIn("部品の目印=0個", note)
        self.assertIn("道具で組んでいない頁に見える", note)
        self.assertIn("足りない部品=", note)

    def test_a_renderer_page_is_described_without_the_warning(self):
        plan = ExplanationPlan(
            audience="project_novice", depth="deep", components=NEEDED,
            reason_codes=(), provisional=False, should_continue=False,
            delivery="local_html", publish_policy="never",
        )
        html = render_components(
            plan, title="題", content={"overview": "本文", "walkthrough": "見出し：本文"},
        )
        with tempfile.TemporaryDirectory() as td:
            note = _describe_shape(_write(td, "built.html", html), {}, NEEDED)

        # 3個＝求めた2つ＋頁末の出所（レンダラーが必ず付ける）。
        self.assertIn("部品の目印=3個", note)
        self.assertNotIn("道具で組んでいない", note)
        self.assertNotIn("足りない部品=", note)


class ItNeverBreaksTheTurnTests(unittest.TestCase):
    """⚠️ここが効かないと、作業そのものを止めてしまう。"""

    def test_a_missing_file_is_silent(self):
        self.assertEqual(_describe_shape("C:/no/such/file.html", {}, NEEDED), "")

    def test_a_directory_is_silent(self):
        with tempfile.TemporaryDirectory() as td:
            self.assertEqual(_describe_shape(td, {}, NEEDED), "")

    def test_garbage_is_still_described_without_raising(self):
        with tempfile.TemporaryDirectory() as td:
            note = _describe_shape(_write(td, "junk.html", "<<<>>> not html at all"), {}, NEEDED)

        self.assertIn("部品の目印=0個", note)


if __name__ == "__main__":
    unittest.main()


class TheBlockSaysWhyTests(unittest.TestCase):
    """2026-09-01 ユーザー裁定＝**割引採用**への対応。

    裁定＝「回答集めだけのターンでも報告の頁を要求してよい」＝割引採用。
    ⚠️割引の中身＝**なぜ差し戻されたのかが伝わらない**こと。
      検品証はあるのに1つも通らない、という状態は読み手に見えなかった。
      ∴理由を1行添える。要求そのものは変えない（頁は要る）。
    """

    def test_the_entrypoint_explains_a_failing_receipt(self):
        source = (HOOKS_DIR / "visual" / "entrypoint.py").read_text(encoding="utf-8")

        self.assertIn("if receipts and not receipt_is_valid:", source)
        self.assertIn("[receipt_not_valid]", source)
        # ⚠️典型例（尋問の回答集め）を名指しする＝名前だけでは何をすればよいか分からない。
        # 2026-09-26：道具の名前は branding.QA_PAGE_TOOL から取る（公開版では持たない人が使う）。
        self.assertIn("QA_PAGE_TOOL", source)
        self.assertIn("報告と判断の頁を別にレンダラーで作る", source)

    def test_the_requirement_itself_is_unchanged(self):
        """⚠️割引は「説明を足す」だけ＝要求を緩めていないことを固定する。"""
        source = (HOOKS_DIR / "visual" / "entrypoint.py").read_text(encoding="utf-8")
        gate = source[source.index("if (") : source.index("[receipt_not_valid]")]

        # 通す条件は3つのまま（頁でない／検品証が有効／道具を使っていない）。
        self.assertIn('plan.delivery != "local_html"', gate)
        self.assertIn("or receipt_is_valid", gate)
        self.assertIn("or not envelope.turn_has_tool_use", gate)

"""文中の [[pic:鍵]]＝資料の画像をホバーで出す印の回帰検査（2026-10-31・利用者の指摘「スクショは基本的にホバーに移して」）。

頁の hover_images に登録した画像だけを、頁の末尾に1枚ずつ埋める。本文には画像を並べず、語に印を付ける。
登録の無い鍵は語だけ出す（壊れた印を出さない）。同じ画像を何度指しても、埋めるのは1回。
"""
from __future__ import annotations

import base64
import sys
import tempfile
import unittest
from pathlib import Path

HOOKS_DIR = Path(__file__).resolve().parents[1]
if str(HOOKS_DIR) not in sys.path:
    sys.path.insert(0, str(HOOKS_DIR))

from visual.artifact_inspection import inspect_artifact_html
from visual.contracts import ExplanationPlan
from visual.render_components import render_components

# 1×1 の PNG（白）
PNG_1PX = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAIAAACQd1PeAAAADElEQVR4nGP4//8/AAX+Av4N70a4AAAAAElFTkSuQmCC"
)


def _plan(*components: str) -> ExplanationPlan:
    return ExplanationPlan(
        audience="project_novice",
        depth="deep",
        components=tuple(components),
        reason_codes=(),
        provisional=False,
        should_continue=False,
        delivery="local_html",
        publish_policy="never",
    )


class HoverImageTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.png = Path(self.tmp.name) / "slide-4.png"
        self.png.write_bytes(PNG_1PX)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _render(self, text: str) -> str:
        return render_components(
            _plan("walkthrough"),
            title="画像のホバー",
            content={
                "hover_images": {"s4": {"path": str(self.png), "caption": "資料のスライド4"}},
                "walkthrough": text,
            },
        )

    def test_marks_the_word_and_embeds_the_image_once_at_the_end(self):
        html = self._render("根拠は [[pic:s4:p.4]] と [[pic:s4:p4]] にある。")
        self.assertEqual(html.count('class="hv"'), 2)
        self.assertIn('data-hv="s4"', html)
        self.assertEqual(html.count('class="hv-item"'), 1, "同じ画像は1回だけ埋める")
        self.assertIn('data-hv-img="s4"', html)
        self.assertIn("data:image/", html)
        # 本文の節の中には画像を並べない（末尾の置き場だけ）
        body = html.split('<div class="hv-store"', 1)[0]
        self.assertNotIn("<img", body)

    def test_unknown_key_prints_only_the_word(self):
        html = self._render("根拠は [[pic:s9:p.9]] にある。")
        self.assertNotIn('class="hv"', html)
        self.assertNotIn('<div class="hv-store"', html)
        self.assertIn("p.9", html)

    def test_page_without_marks_has_no_store(self):
        html = self._render("画像の印は無い。")
        self.assertNotIn('<div class="hv-store"', html)

    def test_page_with_marks_passes_inspection(self):
        html = self._render("根拠は [[pic:s4:p.4]] にある。")
        result = inspect_artifact_html(html, required_components=("walkthrough",), glossary_entries={})
        self.assertEqual(result.missing_components, ())
        self.assertEqual(result.errors, ())


if __name__ == "__main__":
    unittest.main()

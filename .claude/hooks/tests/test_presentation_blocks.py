"""手書きのHTMLとの比べから足した見せ方の部品の試験（2026-10-01・ユーザー承認の P1〜P7・P9）。

試験する物＝
  文中の [[pin:N]]（画像の点の番号と同じ印）
  表の stack（積み上げ棒）・frac（薄い分母）・groups（行の区切り）・row_head（行見出し）
  stats（大きい数字）・steps（横並びの手順）・chips（語の札の束）・headline（結論の見出し）
  images.py：小さい画像を引き伸ばさない・marks の点の印と色・番号の大きさ
  screenshots.py：撮ってよい先の決まり・手元の頁を撮って貼る（Playwright がある機械だけ）
"""
from __future__ import annotations

import os
import re
import sys
import tempfile
import unittest
from pathlib import Path

HOOKS_DIR = Path(__file__).resolve().parents[1]
CLAUDE_DIR = HOOKS_DIR.parent
SCRIPTS_DIR = CLAUDE_DIR / "scripts"
for _entry in (str(HOOKS_DIR), str(SCRIPTS_DIR)):
    if _entry not in sys.path:
        sys.path.insert(0, _entry)

from visual.contracts import ExplanationPlan  # noqa: E402
from visual.render_components import render_components  # noqa: E402
from visual import screenshots  # noqa: E402

NL = chr(10)

try:
    from PIL import Image  # noqa: F401
    HAVE_PIL = True
except Exception:  # pragma: no cover
    HAVE_PIL = False


def _plan(*components):
    return ExplanationPlan(
        audience="project_novice",
        depth="deep",
        components=tuple(components) or ("overview",),
        reason_codes=("project_novice_default",),
        provisional=False,
        should_continue=False,
        delivery="local_html",
        publish_policy="never",
    )


def _render_block(block, title="題", **extra):
    content = {"sections": [{"component": "examples", "label": "例", "content": [block]}]}
    content.update(extra)
    return render_components(_plan("examples"), title=title, content=content)


def _body(html):
    start = html.find("<body>")
    return html[start:] if start >= 0 else html


class PinTests(unittest.TestCase):
    def test_pin_number_and_tone(self):
        html = _body(_render_block({"text": "[[pin:3]] 部屋の幅 [[pin:4:good]]"}))
        self.assertIn('<span class="pin" data-tone="acc">3</span>', html)
        self.assertIn('<span class="pin" data-tone="good">4</span>', html)

    def test_badge_still_works(self):
        html = _body(_render_block({"text": "[[good:合格]]"}))
        self.assertIn('<span class="badge b-good">合格</span>', html)


class TableTests(unittest.TestCase):
    def _table(self, **table):
        return _body(_render_block({"table": table}))

    def test_stack_cell_shows_first_over_total_and_segments(self):
        html = self._table(
            head=["読み取り", "書かれている項目"],
            rows=[["A", "62,3,0"]],
            stack=[1],
            stack_labels=["正解", "見落とし", "誤り"],
        )
        self.assertIn('<span class="v">62<span class="of">/65</span></span>', html)
        self.assertIn('aria-label="正解 62・見落とし 3・誤り 0"', html)
        self.assertEqual(len(re.findall(r'<i data-tone="(good|warn|bad)" style="flex-grow', html)), 2)
        self.assertIn('class="stack-legend"', html)
        self.assertIn("見落とし</span>", html)

    def test_stack_with_text_falls_back_to_a_plain_cell(self):
        html = self._table(head=["a", "b"], rows=[["A", "まだ無い"]], stack=[1])
        self.assertNotIn('class="stack"', html)
        self.assertNotIn("stack-legend", html)

    def test_frac_dims_the_denominator_and_keeps_the_note(self):
        html = self._table(head=["a", "b"], rows=[["A", "62/65" + NL + "見落とし 3"]], frac=[1])
        self.assertIn('<span class="v">62<span class="of">/65</span></span>', html)
        self.assertIn('<span class="cell-note">見落とし 3</span>', html)

    def test_groups_and_row_head(self):
        html = self._table(
            head=["名", "値"], rows=[["A", "1"], ["B", "2"], ["C", "3"]], groups=[0, 2], row_head=True
        )
        self.assertEqual(html.count('<tr class="grp">'), 1)
        self.assertIn('<th scope="row" data-label="名">C</th>', html)


class NewBlockTests(unittest.TestCase):
    def test_stats(self):
        html = _body(_render_block({"stats": [
            {"value": "38", "unit": "/ 38項目", "label": "紙のシート", "text": "すべて正しい", "tone": "good"}
        ]}))
        self.assertIn('class="stats"', html)
        self.assertIn('<div class="stat-num">38<small>/ 38項目</small></div>', html)
        self.assertIn('data-tone="good"', html)

    def test_steps(self):
        html = _body(_render_block({"steps": ["決める：項目を決める", {"title": "採点する", "text": "分ける"}]}))
        self.assertIn('<ol class="hsteps">', html)
        self.assertEqual(html.count("<li><b>"), 2)

    def test_chips_plain_and_grouped(self):
        plain = _body(_render_block({"chips": ["幅", "奥行"]}))
        self.assertIn('<ul class="chips"><li>幅</li><li>奥行</li></ul>', plain)
        grouped = _body(_render_block({"chips": [{"title": "共通", "items": ["幅", "奥行", "天井高"]}]}))
        self.assertIn('<span class="cnt">3</span>', grouped)

    def test_headline_at_the_top_of_the_spec_also_works(self):
        import render_page as rp
        spec = {"title": "題", "headline": "結論", "content": {"overview": "本文"}}
        self.assertEqual(rp.content_of(spec)["headline"], "結論")
        self.assertNotIn("headline", spec["content"])
        inner = {"title": "題", "headline": "外", "content": {"headline": "中"}}
        self.assertEqual(rp.content_of(inner)["headline"], "中")

    def test_headline_moves_the_title_to_the_eyebrow(self):
        html = _render_block({"text": "本文"}, title="短い題", headline="結論はこうだった")
        self.assertIn("<title>短い題", html)
        self.assertIn('<p class="eyebrow">短い題</p>', html)
        self.assertIn("<h1>結論はこうだった</h1>", html)

    def test_without_headline_the_header_is_unchanged(self):
        html = _render_block({"text": "本文"}, title="短い題")
        self.assertIn("UNDERSTANDING COMPOSER / PROJECT NOVICE", html)
        self.assertIn("<h1>短い題</h1>", html)


@unittest.skipUnless(HAVE_PIL, "Pillow が無い")
class ImageTests(unittest.TestCase):
    def _png(self, td, width, height):
        from PIL import Image

        path = Path(td) / ("img-%d.png" % width)
        Image.new("RGB", (width, height), (240, 240, 240)).save(path)
        return str(path)

    def test_small_image_is_not_stretched(self):
        with tempfile.TemporaryDirectory() as td:
            html = _body(_render_block({"image": {"path": self._png(td, 300, 120)}}))
        self.assertRegex(html, r'<div class="img-frame"[^>]* style="max-width:300px"')

    def test_explicit_width_still_wins(self):
        with tempfile.TemporaryDirectory() as td:
            html = _body(_render_block({"image": {"path": self._png(td, 300, 120), "width": 200}}))
        self.assertIn('style="max-width:200px"', html)

    def test_pin_marks_are_html_circles_that_do_not_shrink(self):
        with tempfile.TemporaryDirectory() as td:
            html = _body(_render_block({"image": {"path": self._png(td, 1200, 600), "marks": [
                {"x": 600, "y": 150, "style": "pin"},
                {"x": 300, "y": 300, "w": 50, "h": 40, "tone": "good"},
            ]}}))
        self.assertIn('class="img-pin" data-style="pin" data-tone="acc"', html)
        self.assertIn('left:clamp(.75rem,50.00%,calc(100% - .75rem));top:clamp(.75rem,25.00%,calc(100% - .75rem))', html)
        self.assertIn('class="img-pin" data-style="box" data-tone="good"', html)
        self.assertIn('stroke="var(--pass)"', html)
        self.assertNotIn("<circle", html.split("<script>")[0])

    def test_pin_only_marks_need_no_svg(self):
        with tempfile.TemporaryDirectory() as td:
            html = _body(_render_block({"image": {"path": self._png(td, 400, 200), "marks": [
                {"x": 10, "y": 10, "style": "pin"}]}}))
        self.assertNotIn('<svg class="marks"', html)
        self.assertIn('class="img-pin"', html)


class ScreenshotTargetTests(unittest.TestCase):
    def test_external_pages_are_refused(self):
        url, reason = screenshots.resolve_target("https://example.com/")
        self.assertIsNone(url)
        self.assertIn("外部の頁は撮らない", reason)

    def test_local_hosts_are_allowed(self):
        for target in ("http://localhost:3000/", "http://127.0.0.1:8000/x", "http://app.localhost/", "http://site.test/"):
            self.assertEqual(screenshots.resolve_target(target)[0], target)

    def test_local_file_becomes_a_file_url(self):
        with tempfile.TemporaryDirectory() as td:
            page = Path(td) / "p.html"
            page.write_text("<p>x</p>", encoding="utf-8")
            url, _ = screenshots.resolve_target(str(page))
        self.assertTrue(url.startswith("file:"))

    def test_missing_file_is_refused(self):
        url, reason = screenshots.resolve_target("C:/no/such/file.html")
        self.assertIsNone(url)
        self.assertIn("見つからない", reason)

    def test_refused_target_becomes_a_warning_note(self):
        html = _body(_render_block({"screenshot": {"target": "https://example.com/"}}))
        self.assertIn("画面を撮れなかった", html)
        self.assertNotIn('class="img-figure"', html)
        from visual.receipts import external_dependency_reason

        self.assertIsNone(external_dependency_reason(html.split("<script>")[0]))


def _playwright_available():
    try:
        from visual.visual_smoke import _resolve_playwright

        return _resolve_playwright()[0] is not None
    except Exception:
        return False


@unittest.skipUnless(HAVE_PIL and _playwright_available(), "Playwright か Pillow が無い")
class ScreenshotCaptureTests(unittest.TestCase):
    def test_capture_a_local_page_and_embed_it(self):
        with tempfile.TemporaryDirectory() as td:
            page = Path(td) / "p.html"
            page.write_text(
                "<!doctype html><meta charset=utf-8><body style='margin:0;background:#fff'>"
                "<div id=box style='width:200px;height:80px;background:#2f5d8a'></div></body>",
                encoding="utf-8",
            )
            html = _body(_render_block(
                {"screenshot": {"target": str(page), "viewport": [400, 300], "selector": "#box", "caption": "箱"}},
            ))
        self.assertIn('class="img-figure"', html)
        self.assertIn('style="max-width:200px"', html)
        self.assertIn("実測：画面の写真＝p.html（幅400px・#box）", html)
        # 頁の文字に file:// が入ると検品が外部の読み込みとみなすので、場所は素の形で書く。
        self.assertNotIn("file:", html)
        from visual.receipts import external_dependency_reason

        self.assertIsNone(external_dependency_reason(html))


class DensityTests(unittest.TestCase):
    def test_new_blocks_are_counted(self):
        import render_page as rp

        html = render_components(_plan("examples"), title="題", content={"sections": [
            {"component": "examples", "label": "例", "content": [
                {"stats": [{"value": "1"}]},
                {"steps": ["a：b"]},
                {"chips": ["x"]},
                {"table": {"head": ["a", "b"], "rows": [["A", "1,2"]], "stack": [1]}},
            ]}
        ]})
        counts = dict(rp.density(html))
        self.assertEqual(counts["大きい数字"], 1)
        self.assertEqual(counts["横並びの手順"], 1)
        self.assertEqual(counts["語の札"], 1)
        self.assertGreaterEqual(counts["積み上げ棒"], 1)


if __name__ == "__main__":
    unittest.main()

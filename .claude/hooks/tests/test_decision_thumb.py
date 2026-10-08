"""判断の選択肢の横に添える小さな絵（thumb）の検査（2026-10-08・赤ペン流の判断の頁）。

方針＝生のHTMLは受け取らない。SVGは許可リストで組み直し、画像は幅320・120KB以下に縮めて
data: URI で埋める。取り込めないときは止めずに「絵を取り込めなかった」の1行で知らせる。
"""
from __future__ import annotations

import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

HOOKS_DIR = Path(__file__).resolve().parents[1]
if str(HOOKS_DIR) not in sys.path:
    sys.path.insert(0, str(HOOKS_DIR))

from visual import render_components as rc
from visual.artifact_inspection import inspect_artifact_html
from visual.contracts import ExplanationPlan
from visual.images import ImageResult
from visual.receipts import external_dependency_reason
from visual.render_components import render_components

try:
    from PIL import Image

    _PIL_AVAILABLE = True
except Exception:  # pragma: no cover
    _PIL_AVAILABLE = False


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


SVG_WITH_TRAPS = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 120 80">'
    '<rect x="4" y="4" width="112" height="72" fill="#e3ecf4" onclick="alert(1)"/>'
    "<script>alert(2)</script>"
    '<text x="60" y="44" font-size="10">A案</text></svg>'
)


def _page(options, *, evidence: bool = False) -> str:
    content: dict = {"decision": {"groups": [{"legend": "配置", "kind": "radio", "options": options}]}}
    components = ["decision"]
    if evidence:
        content["evidence"] = "実測：見本を組んだ｜この試験"
        components.append("evidence")
    return render_components(_plan(*components), title="判断", content=content)


class SvgThumbTests(unittest.TestCase):
    def test_svg_thumb_is_rebuilt_with_the_allow_list(self):
        html = _page([{"label": "案A", "thumb": {"svg": SVG_WITH_TRAPS, "alt": "左に一覧"}}])

        start = html.index('<span class="thumb">')
        thumb = html[start : html.index("</svg>", start) + len("</svg>")]
        self.assertIn('class="svg-in"', thumb)
        self.assertIn('role="img" aria-label="左に一覧"', thumb)
        self.assertNotIn("<script", thumb)
        self.assertNotIn("onclick", thumb)
        self.assertIn("A案", thumb)

    def test_dropped_parts_are_reported_in_the_missing_style_not_silently(self):
        html = _page([{"label": "案A", "thumb": {"svg": SVG_WITH_TRAPS}}])

        self.assertIn('<span class="thumb-missing">外したもの：', html)
        self.assertIn("script", html[html.index("外したもの：") :][:80])

    def test_thumb_sits_after_the_text_span_inside_the_label(self):
        html = _page([{"label": "案A", "thumb": {"svg": SVG_WITH_TRAPS}}])

        label_start = html.index('<label class="choice has-thumb">')
        label_end = html.index("</label>", label_start)
        label = html[label_start:label_end]
        self.assertLess(label.index("案A"), label.index('<span class="thumb">'))
        self.assertNotIn("<figure", label)

    def test_svg_string_is_taken_as_svg(self):
        html = _page([{"label": "案A", "thumb": SVG_WITH_TRAPS}])

        self.assertIn('class="svg-in"', html)

    def test_broken_svg_becomes_the_missing_line(self):
        html = _page([{"label": "案A", "thumb": {"svg": "<svg><rect></svg>"}}])

        self.assertIn('class="thumb thumb-missing"', html)
        self.assertNotIn('class="choice has-thumb"', html)

    def test_page_with_svg_thumb_has_no_external_dependency_and_passes_the_gate(self):
        html = _page([{"label": "案A", "thumb": {"svg": SVG_WITH_TRAPS}}])

        self.assertIsNone(external_dependency_reason(html))
        self.assertNotIn("http://", html)
        inspection = inspect_artifact_html(
            html, required_components=("decision",), glossary_entries={}
        )
        self.assertEqual(inspection.missing_decision_parts, ())
        self.assertEqual(inspection.errors, ())


@unittest.skipUnless(_PIL_AVAILABLE, "Pillow が無い＝試験用の画像を作れない")
class ImageThumbTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="thumb_test_"))
        self.addCleanup(shutil.rmtree, self.tmp, True)

    def _png(self, width=64, height=40, name="a.png") -> Path:
        path = self.tmp / name
        Image.new("RGB", (width, height), (40, 90, 140)).save(path)
        return path

    def test_png_thumb_becomes_a_data_uri_img_without_a_figure(self):
        path = self._png()
        html = _page([{"label": "案A", "thumb": {"path": str(path), "alt": "青い箱"}}])

        label_start = html.index('<label class="choice has-thumb">')
        label_end = html.index("</label>", label_start)
        label = html[label_start:label_end]
        self.assertIn('<span class="thumb"><img src="data:image/', label)
        self.assertIn('alt="青い箱"', label)
        self.assertNotIn("<figure", label)
        self.assertNotIn("<figcaption", label)
        self.assertIsNone(external_dependency_reason(html))

    def test_large_image_is_shrunk_to_320_wide(self):
        path = self._png(width=900, height=500, name="big.png")
        html = _page([{"label": "案A", "thumb": {"path": str(path)}}])

        self.assertIn('width="320"', html)
        self.assertNotIn('width="900"', html)

    def test_path_string_is_taken_as_an_image_path(self):
        path = self._png()
        html = _page([{"label": "案A", "thumb": str(path)}])

        self.assertIn('<span class="thumb"><img src="data:image/', html)

    def test_default_alt_names_the_option(self):
        path = self._png()
        html = _page([{"label": "案A", "thumb": {"path": str(path)}}])

        self.assertIn('alt="案Aの絵"', html)

    def test_missing_file_is_reported_without_the_path(self):
        path = self.tmp / "none.png"
        html = _page([{"label": "案A", "pros": "利点", "thumb": {"path": str(path)}}])

        self.assertIn('class="thumb thumb-missing"', html)
        self.assertIn("画像のファイルが見つからない", html)
        self.assertNotIn(str(path), html)
        self.assertNotIn('class="choice has-thumb"', html)

    def test_not_an_image_is_rejected(self):
        path = self.tmp / "fake.png"
        path.write_bytes(b"this is not an image")
        html = _page([{"label": "案A", "thumb": {"path": str(path)}}])

        self.assertIn('class="thumb thumb-missing"', html)
        self.assertIn("画像ではない形式", html)

    def test_oversized_embed_is_refused(self):
        path = self._png()
        fake = ImageResult(
            html='<figure class="img-figure"><div class="img-frame"><img src="data:image/png;base64,AAAA" alt="x" width="1" height="1"></div></figure>',
            sha256="0" * 64,
            source_line="実測：画像＝big.png・原本・000000000000｜big.png",
            bytes=rc._THUMB_MAX_BYTES + 1,
            width=1,
            height=1,
            warnings=[],
        )
        with mock.patch.object(rc, "embed_image", return_value=fake):
            html = _page([{"label": "案A", "thumb": {"path": str(path)}}])

        self.assertIn("画像が大きすぎる", html)
        self.assertNotIn("data:image/png;base64,AAAA", html)

    def test_image_source_line_goes_to_the_evidence_section(self):
        path = self._png()
        html = _page([{"label": "案A", "thumb": {"path": str(path)}}], evidence=True)

        self.assertIn('data-evidence="image-1"', html)

    def test_thumb_embeds_with_the_small_limits(self):
        path = self._png()
        with mock.patch.object(rc, "embed_image", wraps=rc.embed_image) as spy:
            _page([{"label": "案A", "thumb": {"path": str(path)}}])

        _, kwargs = spy.call_args
        self.assertEqual(kwargs.get("max_width"), 320)
        self.assertEqual(kwargs.get("max_bytes"), 120_000)


class RejectedFormsTests(unittest.TestCase):
    def test_raw_html_string_is_not_accepted(self):
        html = _page([{"label": "案A", "thumb": "<div onclick=alert(1)>x</div>"}])

        self.assertIn('class="thumb thumb-missing"', html)
        self.assertNotIn("onclick", html)

    def test_mapping_without_svg_or_path_is_not_accepted(self):
        html = _page([{"label": "案A", "thumb": {"html": "<b>x</b>"}}])

        self.assertIn('class="thumb thumb-missing"', html)
        self.assertNotIn("<b>x</b>", html)

    def test_number_is_not_accepted(self):
        html = _page([{"label": "案A", "thumb": 42}])

        self.assertIn('class="thumb thumb-missing"', html)

    def test_scheme_text_in_alt_is_removed(self):
        html = _page([{"label": "案A", "thumb": {"svg": SVG_WITH_TRAPS, "alt": "見本 http://example.test/a"}}])

        self.assertNotIn("http://", html)
        self.assertNotIn("https://", html)
        self.assertNotIn("file://", html)

    def test_no_thumb_keeps_the_option_without_extra_markup(self):
        html = _page([{"label": "案A", "thumb": None}, {"label": "案B", "thumb": ""}])

        self.assertNotIn('<span class="thumb', html)
        self.assertNotIn('class="choice has-thumb"', html)


class ThumbCssTests(unittest.TestCase):
    def test_css_has_the_side_column_and_the_narrow_screen_branch(self):
        html = _page([{"label": "案A", "thumb": {"svg": SVG_WITH_TRAPS}}])

        self.assertIn(".choice .thumb{", html)
        self.assertIn(".choice.has-thumb{", html)
        self.assertIn("@media(max-width:600px){.choice.has-thumb{", html)
        self.assertIn(".thumb-missing{", html)

    def test_thumb_css_uses_theme_variables_for_colors(self):
        html = _page([{"label": "案A", "thumb": {"svg": SVG_WITH_TRAPS}}])
        start = html.index(".choice.has-thumb{")
        end = html.index("\n.q-note{", start)

        self.assertNotIn("#", html[start:end])


if __name__ == "__main__":
    unittest.main()

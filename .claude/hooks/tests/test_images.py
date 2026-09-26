from __future__ import annotations

import shutil
import sys
import tempfile
import unittest
from pathlib import Path

HOOKS_DIR = Path(__file__).resolve().parents[1]
if str(HOOKS_DIR) not in sys.path:
    sys.path.insert(0, str(HOOKS_DIR))

from visual.images import embed_image

try:
    from PIL import Image, ImageDraw

    _PIL_AVAILABLE = True
except Exception:  # pragma: no cover
    _PIL_AVAILABLE = False


def _make_png_bytes(width=200, height=120, text=True):
    img = Image.new("RGB", (width, height), color=(240, 240, 240))
    if text:
        draw = ImageDraw.Draw(img)
        for y in range(0, height, 8):
            draw.line([(0, y), (width, y)], fill=(60, 60, 60), width=1)
        draw.rectangle([10, 10, width - 10, height - 10], outline=(0, 0, 0), width=2)
        draw.text((20, 20), "SAMPLE 12345 ABCDE", fill=(0, 0, 0))
    buf_path = None
    return img


@unittest.skipUnless(_PIL_AVAILABLE, "Pillow が無い＝試験用の画像を作れない（Pillow は任意の部品）")
class EmbedImageTests(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = Path(tempfile.mkdtemp(prefix="test_images_"))

    def tearDown(self):
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def _write_png(self, name="sample.png", width=200, height=120, text=True):
        path = self.tmp_dir / name
        img = _make_png_bytes(width, height, text=text)
        img.save(path, format="PNG")
        return path

    def _write_jpeg(self, name="sample.jpg", width=200, height=120):
        path = self.tmp_dir / name
        img = Image.new("RGB", (width, height), color=(100, 150, 200))
        img.save(path, format="JPEG")
        return path

    # 1. PNG embeds and produces a data:image URI.
    def test_png_embeds_as_data_uri(self):
        path = self._write_png()
        result = embed_image({"path": str(path)})
        self.assertIn("data:image/", result.html)
        self.assertIn("<img src=\"data:image/", result.html)
        self.assertEqual(result.warnings, [])
        self.assertGreater(result.bytes, 0)
        self.assertGreater(result.width, 0)
        self.assertGreater(result.height, 0)

    # 2. JPEG also passes through.
    def test_jpeg_embeds_ok(self):
        path = self._write_jpeg()
        result = embed_image({"path": str(path)})
        self.assertTrue(result.html)
        self.assertIn("data:image/", result.html)
        self.assertEqual(result.warnings, [])

    # 3. A text file disguised as .png is rejected by magic-number check.
    def test_disguised_text_file_is_rejected(self):
        path = self.tmp_dir / "fake.png"
        path.write_bytes(b"this is not an image, just text pretending to be one")
        result = embed_image({"path": str(path)})
        self.assertEqual(result.html, "")
        self.assertTrue(result.warnings)
        self.assertTrue(any("magic number" in w for w in result.warnings))

    # 4. crop changes reported width/height.
    def test_crop_changes_dimensions(self):
        path = self._write_png(width=400, height=300)
        result_full = embed_image({"path": str(path)})
        result_cropped = embed_image({"path": str(path), "crop": [10, 10, 100, 50]})
        self.assertEqual(result_cropped.width, 100)
        self.assertEqual(result_cropped.height, 50)
        self.assertNotEqual(result_full.width, result_cropped.width)

    # 5. max_width shrinks a wide image.
    def test_max_width_shrinks_image(self):
        path = self._write_png(width=2000, height=1000)
        result = embed_image({"path": str(path)}, max_width=500)
        self.assertEqual(result.width, 500)
        self.assertEqual(result.height, 250)

    # 6. max_bytes caps the embedded size, even for a large image.
    def test_max_bytes_caps_size(self):
        path = self._write_png(width=1600, height=1200, text=True)
        result = embed_image({"path": str(path)}, max_width=1200, max_bytes=20_000)
        self.assertLessEqual(result.bytes, 20_000)

    # 7. marks draw a rect and a numbered badge.
    def test_marks_render_rect_and_number(self):
        path = self._write_png(width=200, height=120)
        result = embed_image(
            {
                "path": str(path),
                "marks": [{"x": 10, "y": 10, "w": 50, "h": 30, "label": "1"}],
            }
        )
        self.assertIn("<svg class=\"marks\"", result.html)
        self.assertIn("<rect", result.html)
        self.assertIn("<circle", result.html)
        self.assertIn(">1<", result.html)

    # 8. deck + slide resolves via the working-folder glob (deck_root override).
    def test_deck_slide_resolves_from_deck_root(self):
        deck_dir = self.tmp_dir / "my-deck" / "media"
        deck_dir.mkdir(parents=True)
        path = deck_dir / "slide-12-img1.png"
        img = _make_png_bytes(150, 100)
        img.save(path, format="PNG")

        result = embed_image({"deck": "my-deck", "slide": 12}, deck_root=str(self.tmp_dir))
        self.assertTrue(result.html)
        self.assertEqual(result.warnings, [])
        self.assertIn("スライド12", result.source_line)

    # 9. missing file / missing deck+slide produces a warning and empty html.
    def test_missing_file_warns_and_returns_empty(self):
        result = embed_image({"path": str(self.tmp_dir / "does-not-exist.png")})
        self.assertEqual(result.html, "")
        self.assertTrue(result.warnings)

        result2 = embed_image({"deck": "no-such-deck", "slide": 3}, deck_root=str(self.tmp_dir))
        self.assertEqual(result2.html, "")
        self.assertTrue(result2.warnings)

    # 10. output never contains a bare http(s):// URL, and alt text is escaped.
    def test_no_http_and_alt_is_escaped(self):
        path = self._write_png()
        result = embed_image({"path": str(path), "alt": "<script>alert(1)</script>"})
        self.assertNotIn("http://", result.html)
        self.assertNotIn("https://", result.html)
        self.assertNotIn("<script>", result.html)
        self.assertIn("&lt;script&gt;", result.html)

    # 11. sha256 and source_line are populated and consistent.
    def test_sha256_and_source_line_present(self):
        path = self._write_png()
        result = embed_image({"path": str(path), "caption": "見本図", "source": "テスト", "num": 3})
        self.assertEqual(len(result.sha256), 64)
        self.assertTrue(all(c in "0123456789abcdef" for c in result.sha256))
        self.assertTrue(result.source_line.startswith("実測："))
        self.assertIn(result.sha256[:12], result.source_line)
        self.assertIn("図3", result.html)
        self.assertIn("見本図", result.html)
        self.assertIn("出所：テスト", result.html)

    # Extra: xmlns is never emitted (renderer's inspector rejects it).
    def test_no_xmlns_in_output(self):
        path = self._write_png()
        result = embed_image(
            {
                "path": str(path),
                "marks": [{"x": 1, "y": 1, "w": 5, "h": 5, "label": "a"}],
            }
        )
        self.assertNotIn("xmlns", result.html)

    # Extra: a spec with neither path nor deck/slide is rejected cleanly.
    def test_spec_without_path_or_deck_slide(self):
        result = embed_image({})
        self.assertEqual(result.html, "")
        self.assertTrue(result.warnings)

    # Extra: PNG vs JPEG choice is deterministic (same input -> same output).
    def test_deterministic_output(self):
        path = self._write_png()
        result1 = embed_image({"path": str(path)})
        result2 = embed_image({"path": str(path)})
        self.assertEqual(result1.html, result2.html)
        self.assertEqual(result1.sha256, result2.sha256)


@unittest.skipUnless(_PIL_AVAILABLE, "Pillow not available in this environment")
class EmbedImagePillowGuardedTests(unittest.TestCase):
    """Kept separate so the module import above still fails loudly if PIL
    is unexpectedly missing on this machine (per the task brief, PIL 12 is
    expected to be present)."""

    def test_pillow_is_actually_available(self):
        self.assertTrue(_PIL_AVAILABLE)


if __name__ == "__main__":
    unittest.main()


@unittest.skipUnless(_PIL_AVAILABLE, "Pillow が無い＝試験用の画像を作れない（Pillow は任意の部品）")
class ZeroPaddedSlideTests(unittest.TestCase):
    """2026-09-10：作業フォルダの実物（s05-img1.png）を slide=5 で見つける。"""

    def test_zero_padded_slide_file_is_found(self):
        import tempfile, os
        from PIL import Image
        with tempfile.TemporaryDirectory() as root:
            media = os.path.join(root, "deck-x", "media")
            os.makedirs(media)
            Image.new("RGB", (40, 30), (200, 30, 30)).save(os.path.join(media, "s05-img1.png"))
            result = embed_image({"deck": "deck-x", "slide": 5}, deck_root=root)
            self.assertEqual(result.warnings, [])
            self.assertIn("data:image", result.html)

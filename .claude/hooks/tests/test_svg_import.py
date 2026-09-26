from __future__ import annotations

import sys
import unittest
from pathlib import Path

HOOKS_DIR = Path(__file__).resolve().parents[1]
if str(HOOKS_DIR) not in sys.path:
    sys.path.insert(0, str(HOOKS_DIR))

from visual.svg_import import sanitize_svg


class SvgImportTests(unittest.TestCase):
    # 1: 基本の path/rect/text が保たれる
    def test_basic_shapes_and_text_are_kept(self):
        src = (
            '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100">'
            '<rect x="1" y="2" width="10" height="20" fill="#f00"/>'
            '<path d="M0 0 L10 10" stroke="black"/>'
            '<text x="5" y="5" font-size="12">hello</text>'
            "</svg>"
        )
        result = sanitize_svg(src)
        self.assertEqual(result.dropped, [])
        self.assertIn("<rect", result.svg)
        self.assertIn('fill="#f00"', result.svg)
        self.assertIn("<path", result.svg)
        self.assertIn('d="M0 0 L10 10"', result.svg)
        self.assertIn("<text", result.svg)
        self.assertIn(">hello<", result.svg)

    # 2: 勾配・マスク・clipPath・marker・use(#) が保たれる
    def test_gradients_mask_clippath_marker_use_are_kept(self):
        src = (
            '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100">'
            "<defs>"
            '<linearGradient id="g1" x1="0" y1="0" x2="1" y2="1">'
            '<stop offset="0" stop-color="#fff"/>'
            '<stop offset="1" stop-color="#000"/>'
            "</linearGradient>"
            '<clipPath id="c1"><rect width="10" height="10"/></clipPath>'
            '<mask id="m1"><rect width="10" height="10" fill="white"/></mask>'
            '<marker id="mk1" markerWidth="6" markerHeight="6">'
            '<path d="M0 0 L6 3 L0 6 Z"/>'
            "</marker>"
            "</defs>"
            '<rect width="10" height="10" fill="url(#g1)" clip-path="url(#c1)" '
            'mask="url(#m1)"/>'
            '<use href="#c1"/>'
            "</svg>"
        )
        result = sanitize_svg(src)
        self.assertEqual(result.dropped, [])
        for needle in (
            "<linearGradient",
            '<stop offset="0"',
            "<clipPath",
            "<mask",
            "<marker",
            'fill="url(#g1)"',
            'clip-path="url(#c1)"',
            'mask="url(#m1)"',
            '<use href="#c1"',
        ):
            self.assertIn(needle, result.svg, msg=needle)

    # 3: script が落ち dropped に入る
    def test_script_element_is_dropped(self):
        src = (
            '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 10 10">'
            "<script>alert(1)</script>"
            '<rect width="1" height="1"/>'
            "</svg>"
        )
        result = sanitize_svg(src)
        self.assertIn("script", result.dropped)
        self.assertNotIn("<script", result.svg)
        self.assertNotIn("alert(1)", result.svg)

    # 4: onclick が落ちる
    def test_onclick_attribute_is_dropped(self):
        src = (
            '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 10 10">'
            '<rect width="1" height="1" onclick="alert(1)"/>'
            "</svg>"
        )
        result = sanitize_svg(src)
        self.assertIn("onclick", result.dropped)
        self.assertNotIn("onclick", result.svg)

    # 5: href が外部URLなら落ち、#id は残る
    def test_external_href_dropped_same_doc_href_kept(self):
        src = (
            '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 10 10">'
            '<defs><path id="p1" d="M0 0 L1 1"/></defs>'
            '<use href="#p1"/>'
            '<use href="https://evil.example/x.svg#y"/>'
            "</svg>"
        )
        result = sanitize_svg(src)
        self.assertIn("href", result.dropped)
        self.assertIn('href="#p1"', result.svg)
        self.assertNotIn("evil.example", result.svg)

    # 6: image の href が data:image/png なら残り、外部URLなら落ちる
    def test_image_href_data_uri_kept_external_dropped(self):
        good = (
            '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 10 10">'
            '<image href="data:image/png;base64,AAAA" width="10" height="10"/>'
            "</svg>"
        )
        result_good = sanitize_svg(good)
        self.assertIn("data:image/png;base64,AAAA", result_good.svg)
        self.assertNotIn("href", result_good.dropped)

        bad = (
            '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 10 10">'
            '<image href="https://evil.example/x.png" width="10" height="10"/>'
            "</svg>"
        )
        result_bad = sanitize_svg(bad)
        self.assertIn("href", result_bad.dropped)
        self.assertNotIn("evil.example", result_bad.svg)

    # 7: <!DOCTYPE を含む入力は拒否
    def test_doctype_is_rejected(self):
        src = (
            '<?xml version="1.0"?>'
            '<!DOCTYPE svg [<!ENTITY xxe SYSTEM "file:///etc/passwd">]>'
            '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 10 10">'
            "&xxe;"
            "</svg>"
        )
        result = sanitize_svg(src)
        self.assertEqual(result.svg, "")
        self.assertTrue(any("DTD" in w or "ENTITY" in w for w in result.warnings))

    # 8: style属性の fill:red;background:url(x) は fill だけ残る
    def test_style_attribute_is_filtered(self):
        src = (
            '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 10 10">'
            '<rect width="1" height="1" style="fill:red;background:url(x)"/>'
            "</svg>"
        )
        result = sanitize_svg(src)
        self.assertIn('style="fill:red"', result.svg)
        self.assertNotIn("background", result.svg)
        self.assertNotIn("url(x)", result.svg)
        self.assertIn("style:background", result.dropped)

    # 9: xmlns が出力に現れない
    def test_xmlns_does_not_appear_in_output(self):
        src = (
            '<svg xmlns="http://www.w3.org/2000/svg" '
            'xmlns:xlink="http://www.w3.org/1999/xlink" viewBox="0 0 10 10">'
            '<use xlink:href="#p1"/>'
            "</svg>"
        )
        result = sanitize_svg(src)
        self.assertNotIn("xmlns", result.svg)

    # 10: 文字に<script>を入れても &lt;script&gt; になる
    def test_text_content_is_escaped(self):
        src = (
            '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 10 10">'
            "<text>&lt;script&gt;alert(1)&lt;/script&gt;</text>"
            "</svg>"
        )
        result = sanitize_svg(src)
        self.assertIn("&lt;script&gt;", result.svg)
        self.assertNotIn("<script>", result.svg)

    # 11: width/height が viewBox に写る
    def test_width_height_are_copied_into_viewbox(self):
        src = (
            '<svg xmlns="http://www.w3.org/2000/svg" width="200px" height="100">'
            '<rect width="1" height="1"/>'
            "</svg>"
        )
        result = sanitize_svg(src)
        self.assertIn('viewBox="0 0 200 100"', result.svg)
        self.assertNotIn('width="200px"', result.svg)
        # svg要素自体にはもう width/height 属性が無い（先頭のsvgタグのみ確認）
        svg_tag_end = result.svg.index(">")
        self.assertNotIn("width=", result.svg[:svg_tag_end])
        self.assertNotIn("height=", result.svg[:svg_tag_end])
        self.assertEqual(result.width, 200.0)
        self.assertEqual(result.height, 100.0)

    # 12: 名前空間付きタグ（xmlns宣言ありの入力）が正しく解析される
    def test_namespaced_tags_are_parsed_by_local_name(self):
        src = (
            '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 10 10">'
            '<g><circle cx="5" cy="5" r="2" fill="blue"/></g>'
            "</svg>"
        )
        result = sanitize_svg(src)
        self.assertEqual(result.dropped, [])
        self.assertIn("<g><circle", result.svg)
        self.assertIn('fill="blue"', result.svg)

    # 追加: viewBoxが無くwidth/heightも無ければwarning
    def test_no_viewbox_no_size_warns(self):
        src = '<svg xmlns="http://www.w3.org/2000/svg"><rect width="1" height="1"/></svg>'
        result = sanitize_svg(src)
        self.assertTrue(any("size is undetermined" in w for w in result.warnings))
        self.assertIsNone(result.width)
        self.assertIsNone(result.height)

    # 追加: 空文字・不正なXMLは例外にせず空結果
    def test_empty_and_malformed_input_never_raises(self):
        result_empty = sanitize_svg("")
        self.assertEqual(result_empty.svg, "")
        self.assertTrue(result_empty.warnings)

        result_malformed = sanitize_svg("<svg><rect></svg>")
        self.assertEqual(result_malformed.svg, "")
        self.assertTrue(result_malformed.warnings)

    # 追加: foreignObject / animate / iframe / object / embed も落ちる
    def test_other_dangerous_elements_are_dropped(self):
        src = (
            '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 10 10">'
            "<foreignObject><div>x</div></foreignObject>"
            '<rect width="1" height="1"><animate attributeName="x" to="1"/></rect>'
            "<iframe></iframe>"
            "<object></object>"
            "<embed/>"
            "</svg>"
        )
        result = sanitize_svg(src)
        for name in ("foreignObject", "animate", "iframe", "object", "embed"):
            self.assertIn(name, result.dropped)
        for needle in ("foreignObject", "<animate", "<iframe", "<object", "<embed"):
            self.assertNotIn(needle, result.svg)

    # 追加: 出力ルートに class="svg-in" が付く
    def test_root_gets_svg_in_class(self):
        src = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 10 10"></svg>'
        result = sanitize_svg(src)
        self.assertIn('class="svg-in"', result.svg)

    # 追加: xmlns:xlink 宣言が無くても xlink:href は拒否されず解析される
    def test_missing_xlink_declaration_is_supplied(self):
        src = (
            '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 10 10">'
            '<use xlink:href="#a"/>'
            "</svg>"
        )
        result = sanitize_svg(src)
        self.assertNotEqual(result.svg, "")
        self.assertTrue(
            ('href="#a"' in result.svg) or ('xlink:href="#a"' in result.svg)
        )
        self.assertNotIn("http", result.svg)

    # 追加: <!DOCTYPE/<!ENTITY を含まない SYSTEM/PUBLIC はただの語として通る
    def test_bare_system_public_words_are_not_rejected(self):
        src = (
            '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 10 10">'
            "<text>public system</text>"
            "</svg>"
        )
        result = sanitize_svg(src)
        self.assertNotEqual(result.svg, "")
        self.assertIn("public system", result.svg)

    # 追加: 決定論（同じ入力→同じ出力）
    def test_deterministic(self):
        src = (
            '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 10 10">'
            '<rect width="1" height="1" fill="red"/>'
            "</svg>"
        )
        r1 = sanitize_svg(src)
        r2 = sanitize_svg(src)
        self.assertEqual(r1.svg, r2.svg)
        self.assertEqual(r1.dropped, r2.dropped)


if __name__ == "__main__":
    unittest.main()

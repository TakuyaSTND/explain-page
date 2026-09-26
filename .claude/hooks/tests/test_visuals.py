"""Unit tests for ``.claude/hooks/visual/visuals.py``.

Run directly (uses only stdlib unittest):

    PYTHONUTF8=1 python -m unittest \
        .claude.hooks.tests.test_visuals -v

or via the repo's usual pytest/unittest discovery from ``.claude/hooks``.
"""

from __future__ import annotations

import os
import re
import sys
import unittest

_HOOKS_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _HOOKS_DIR not in sys.path:
    sys.path.insert(0, _HOOKS_DIR)

from visual import visuals as v  # noqa: E402


_SVG_FUNCS = {
    "timeline_svg": lambda: v.timeline_svg(
        {"title": "t", "events": [{"when": "2024", "label": "x"}]}
    ),
    "quadrant_svg": lambda: v.quadrant_svg(
        {"x": ["低", "高"], "y": ["低", "高"], "items": [{"label": "a", "x": 0.2, "y": 0.8}]}
    ),
    "venn_svg": lambda: v.venn_svg(
        {"sets": [{"label": "A", "items": ["a1"]}, {"label": "B", "items": ["b1"]}]}
    ),
    "flow_svg": lambda: v.flow_svg(
        {
            "nodes": [{"id": "a", "label": "A"}, {"id": "b", "label": "B"}],
            "links": [{"from": "a", "to": "b", "value": 5}],
        }
    ),
    "callout_badge_svg": lambda: v.callout_badge_svg(1, "good"),
    "score_grid_svg": lambda: v.score_grid_svg(
        {"axes": [{"name": "内因性", "level": 1}], "max": 3}
    ),
    "sparkline_svg": lambda: v.sparkline_svg([1, 2, 3]),
}


class TestBasicShape(unittest.TestCase):
    """Each function's basic output carries the expected structural markers."""

    def test_timeline_basic_elements(self):
        out = v.timeline_svg(
            {
                "title": "制度年表",
                "events": [
                    {"when": "2024-04", "label": "施行", "tone": "good"},
                    {"when": "2025-01", "label": "見直し", "text": "附則3年後", "tone": "warn"},
                ],
                "caption": "出所: 官報",
            }
        )
        self.assertIn('class="tl"', out)
        self.assertIn("<svg", out)
        self.assertIn("viewBox=", out)
        self.assertIn("制度年表", out)
        self.assertIn("施行", out)
        self.assertEqual(out.count("<circle"), 2)

    def test_quadrant_basic_elements(self):
        out = v.quadrant_svg(
            {
                "x": ["低", "高"],
                "y": ["低", "高"],
                "x_label": "内因性",
                "y_label": "重要性",
                "items": [{"label": "A案", "x": 0.3, "y": 0.7, "tone": "good"}],
            }
        )
        self.assertIn('class="quad"', out)
        self.assertIn("内因性", out)
        self.assertIn("重要性", out)
        self.assertEqual(out.count("<circle"), 1)

    def test_venn_basic_elements_two_sets(self):
        out = v.venn_svg(
            {"sets": [{"label": "集合A", "items": ["x"]}, {"label": "集合B", "items": ["y"]}]}
        )
        self.assertIn('class="venn"', out)
        self.assertEqual(out.count("<circle"), 2)
        self.assertIn("集合A", out)
        self.assertIn("集合B", out)

    def test_venn_basic_elements_three_sets(self):
        out = v.venn_svg(
            {
                "sets": [
                    {"label": "A", "items": ["a1"]},
                    {"label": "B", "items": ["b1"]},
                    {"label": "C", "items": ["c1"]},
                ],
                "overlaps": [{"of": [0, 1], "items": ["ab1"]}],
            }
        )
        self.assertEqual(out.count("<circle"), 3)
        self.assertIn("ab1", out)

    def test_flow_basic_elements(self):
        out = v.flow_svg(
            {
                "nodes": [
                    {"id": "a", "label": "入力A"},
                    {"id": "b", "label": "入力B"},
                    {"id": "c", "label": "出力C"},
                ],
                "links": [
                    {"from": "a", "to": "c", "value": 10},
                    {"from": "b", "to": "c", "value": 30},
                ],
            }
        )
        self.assertIn('class="flow"', out)
        self.assertEqual(out.count("<path"), 2)
        self.assertEqual(out.count("<rect"), 3)

    def test_score_grid_basic_elements(self):
        out = v.score_grid_svg(
            {"axes": [{"name": "内因性", "level": 2, "note": "備考"}], "max": 3}
        )
        self.assertIn('class="score"', out)
        self.assertIn("内因性", out)
        self.assertIn("備考", out)
        self.assertEqual(out.count("<rect"), 4)  # max=3 -> 0..3 cells

    def test_sparkline_basic_elements(self):
        out = v.sparkline_svg([1, 5, 3, 9, 2], width=100, height=20)
        self.assertIn('class="spark"', out)
        self.assertIn("<polyline", out)
        self.assertIn('viewBox="0 0 100 20"', out)

    def test_callout_badge_and_legend(self):
        badge = v.callout_badge_svg(3, "warn")
        self.assertIn('class="badge"', badge)
        self.assertIn(">3<", badge)
        legend = v.callout_legend_html([{"n": 1, "text": "注1"}, {"n": 2, "text": "注2"}])
        self.assertIn('class="callout-legend"', legend)
        self.assertEqual(legend.count("<li"), 2)
        self.assertIn("注1", legend)
        self.assertIn("注2", legend)

    def test_compare_basic_elements(self):
        out = v.compare_html("<p>前案</p>", "<p>後案</p>", ("前", "後"))
        self.assertIn('class="compare"', out)
        self.assertIn("<p>前案</p>", out)
        self.assertIn("<p>後案</p>", out)
        self.assertEqual(out.count('type="radio"'), 2)
        self.assertIn(":checked", out)

    def test_heat_color_basic(self):
        out = v.heat_color(50, 0, 100)
        self.assertTrue(out.startswith("color-mix(in srgb, var(--accent)"))
        self.assertIn("22%", out)  # 2026-09-10：上限45%に抑えたので中間値は22%


class TestEscaping(unittest.TestCase):
    """Every piece of caller-supplied text must come back html-escaped."""

    def test_timeline_escapes_script(self):
        out = v.timeline_svg(
            {"events": [{"when": "2024", "label": "<script>alert(1)</script>"}]}
        )
        self.assertNotIn("<script>", out)
        self.assertIn("&lt;script&gt;", out)

    def test_quadrant_escapes_label(self):
        out = v.quadrant_svg({"items": [{"label": "<b>x</b>", "x": 0.5, "y": 0.5}]})
        self.assertNotIn("<b>x</b>", out)
        self.assertIn("&lt;b&gt;", out)

    def test_venn_escapes_set_label_and_items(self):
        out = v.venn_svg(
            {"sets": [{"label": "<i>A</i>", "items": ["<u>z</u>"]}, {"label": "B", "items": []}]}
        )
        self.assertNotIn("<i>A</i>", out)
        self.assertIn("&lt;i&gt;", out)
        self.assertNotIn("<u>z</u>", out)

    def test_flow_escapes_node_label(self):
        out = v.flow_svg(
            {
                "nodes": [{"id": "a", "label": "<script>x</script>"}, {"id": "b", "label": "b"}],
                "links": [{"from": "a", "to": "b", "value": 1}],
            }
        )
        self.assertNotIn("<script>x</script>", out)
        self.assertIn("&lt;script&gt;", out)

    def test_score_grid_escapes_name_and_note(self):
        out = v.score_grid_svg({"axes": [{"name": "<x>n</x>", "note": "<y>note</y>", "level": 1}]})
        self.assertNotIn("<x>n</x>", out)
        self.assertNotIn("<y>note</y>", out)

    def test_callout_legend_escapes_text(self):
        out = v.callout_legend_html([{"n": 1, "text": "<script>bad()</script>"}])
        self.assertNotIn("<script>bad()</script>", out)
        self.assertIn("&lt;script&gt;", out)

    def test_compare_labels_are_escaped(self):
        out = v.compare_html("a", "b", ("<i>前</i>", "後"))
        self.assertNotIn("<i>前</i>", out)
        self.assertIn("&lt;i&gt;", out)


class TestNoXmlns(unittest.TestCase):
    """No SVG here declares an xmlns (the renderer's inspector treats that
    as an external-URL reference and fails the receipt)."""

    def test_no_xmlns_in_any_svg_component(self):
        for name, factory in _SVG_FUNCS.items():
            out = factory()
            with self.subTest(component=name):
                self.assertNotIn("xmlns", out)

    def test_no_xmlns_in_compare_or_legend(self):
        out = v.compare_html("<p>a</p>", "<p>b</p>")
        self.assertNotIn("xmlns", out)
        legend = v.callout_legend_html([{"n": 1, "text": "x"}])
        self.assertNotIn("xmlns", legend)


class TestTimelineLayoutSwitch(unittest.TestCase):
    def test_seven_events_stay_horizontal(self):
        events = [{"when": "20%02d" % i, "label": "項目%d" % i} for i in range(7)]
        out = v.timeline_svg({"events": events})
        m = re.search(r'<line x1="([0-9.]+)" y1="([0-9.]+)" x2="([0-9.]+)" y2="([0-9.]+)"', out)
        self.assertIsNotNone(m)
        x1, y1, x2, y2 = (float(g) for g in m.groups())
        self.assertNotEqual(x1, x2)  # horizontal axis: x varies, y constant
        self.assertEqual(y1, y2)

    def test_eight_events_switch_to_vertical(self):
        events = [{"when": "20%02d" % i, "label": "項目%d" % i} for i in range(8)]
        out = v.timeline_svg({"events": events})
        m = re.search(r'<line x1="([0-9.]+)" y1="([0-9.]+)" x2="([0-9.]+)" y2="([0-9.]+)"', out)
        self.assertIsNotNone(m)
        x1, y1, x2, y2 = (float(g) for g in m.groups())
        self.assertEqual(x1, x2)  # vertical axis: x constant, y varies
        self.assertNotEqual(y1, y2)
        self.assertEqual(out.count("<circle"), 8)


class TestQuadrantDeconflict(unittest.TestCase):
    def test_identical_coordinates_are_pushed_apart(self):
        out = v.quadrant_svg(
            {"items": [{"label": "A", "x": 0.5, "y": 0.5}, {"label": "B", "x": 0.5, "y": 0.5}]}
        )
        coords = re.findall(r'<circle cx="([0-9.]+)" cy="([0-9.]+)"', out)
        self.assertEqual(len(coords), 2)
        self.assertNotEqual(coords[0], coords[1])

    def test_distinct_coordinates_are_left_alone_ish(self):
        out = v.quadrant_svg(
            {"items": [{"label": "A", "x": 0.1, "y": 0.1}, {"label": "B", "x": 0.9, "y": 0.9}]}
        )
        coords = re.findall(r'<circle cx="([0-9.]+)" cy="([0-9.]+)"', out)
        self.assertEqual(len(coords), 2)
        self.assertNotEqual(coords[0], coords[1])


class TestQuadrantLabelDeconflict(unittest.TestCase):
    """Dots at identical coordinates get pushed apart by _deconflict, but a
    label is far wider than the 26px dot-nudge distance -- two labels on
    coincident points used to render on top of each other (garbled,
    unreadable text). Labels must now clear each other too."""

    def test_identical_coordinate_labels_do_not_share_a_line(self):
        out = v.quadrant_svg(
            {
                "items": [
                    {"label": "AAA案", "x": 0.5, "y": 0.5},
                    {"label": "BBB案", "x": 0.5, "y": 0.5},
                ]
            }
        )
        rows = re.findall(
            r'<text x="([0-9.]+)" y="([0-9.]+)" text-anchor="[a-z]+" '
            r'fill="var\(--ink\)" font-size="12">([^<]*)</text>',
            out,
        )
        by_text = {text: float(y) for _x, y, text in rows if text in ("AAA案", "BBB案")}
        self.assertEqual(set(by_text), {"AAA案", "BBB案"})
        self.assertGreaterEqual(abs(by_text["AAA案"] - by_text["BBB案"]), 10.0)


class TestFlowBandProportionality(unittest.TestCase):
    def test_band_width_scales_with_value(self):
        out = v.flow_svg(
            {
                "nodes": [{"id": "a"}, {"id": "b"}, {"id": "c"}],
                "links": [
                    {"from": "a", "to": "c", "value": 10},
                    {"from": "b", "to": "c", "value": 30},
                ],
            }
        )
        widths = [float(w) for w in re.findall(r'<path[^>]*stroke-width="([0-9.]+)"', out)]
        self.assertEqual(len(widths), 2)
        ratio = max(widths) / min(widths)
        self.assertAlmostEqual(ratio, 3.0, places=1)

    def test_zero_value_link_still_renders_a_visible_band(self):
        out = v.flow_svg(
            {
                "nodes": [{"id": "a"}, {"id": "b"}],
                "links": [{"from": "a", "to": "b", "value": 0}],
            }
        )
        widths = [float(w) for w in re.findall(r'<path[^>]*stroke-width="([0-9.]+)"', out)]
        self.assertEqual(len(widths), 1)
        self.assertGreater(widths[0], 0.0)


class TestScoreGridColors(unittest.TestCase):
    def test_lv0_and_lv_max_use_different_colors(self):
        lv0 = v.score_grid_svg({"axes": [{"name": "a", "level": 0}], "max": 3})
        lv3 = v.score_grid_svg({"axes": [{"name": "a", "level": 3}], "max": 3})
        self.assertIn("var(--fail)", lv0)
        self.assertIn("var(--pass)", lv3)
        self.assertNotEqual(lv0, lv3)

    def test_mid_level_uses_warn_color(self):
        lv1 = v.score_grid_svg({"axes": [{"name": "a", "level": 1}], "max": 3})
        self.assertIn("var(--warn)", lv1)


class TestCompareNoNetworkWords(unittest.TestCase):
    def test_no_network_vocabulary(self):
        out = v.compare_html("<p>a</p>", "<p>b</p>")
        lowered = out.lower()
        for banned in ("fetch", "xhr", "xmlhttprequest", "websocket", "<script"):
            with self.subTest(banned=banned):
                self.assertNotIn(banned, lowered)


class TestFontSizeFloor(unittest.TestCase):
    """No emitted text may render below 12px (readability floor)."""

    _FONT_SIZE_RE = re.compile(r'font-size[=:]"?(\d+)(?:px)?"?')

    def _assert_all_sizes_at_least_12(self, out, where, require_any=True):
        sizes = [int(n) for n in self._FONT_SIZE_RE.findall(out)]
        if require_any:
            self.assertTrue(sizes, "no font-size found in %s output" % where)
        for size in sizes:
            with self.subTest(where=where, size=size):
                self.assertGreaterEqual(size, 12)

    def test_timeline_horizontal_with_secondary_text(self):
        out = v.timeline_svg(
            {
                "title": "t",
                "events": [
                    {"when": "2024", "label": "施行", "text": "附則3年後に見直し"},
                    {"when": "2025", "label": "見直し", "text": "附則3年後に見直し"},
                ],
                "caption": "出所: 官報",
            }
        )
        self._assert_all_sizes_at_least_12(out, "timeline_horizontal")

    def test_timeline_vertical_with_secondary_text(self):
        events = [
            {"when": "20%02d" % i, "label": "項目%d" % i, "text": "補足説明のテキスト"}
            for i in range(8)
        ]
        out = v.timeline_svg({"events": events, "caption": "出所: 官報"})
        self._assert_all_sizes_at_least_12(out, "timeline_vertical")

    def test_all_svg_components(self):
        for name, factory in _SVG_FUNCS.items():
            out = factory()
            # sparkline_svg emits no text at all, so its font-size list is
            # legitimately empty; every other component draws labels.
            self._assert_all_sizes_at_least_12(
                out, name, require_any=(name != "sparkline_svg")
            )

    def test_compare_html_style_block(self):
        out = v.compare_html("<p>前案</p>", "<p>後案</p>", ("前", "後"))
        self._assert_all_sizes_at_least_12(out, "compare_html")


class TestHeatColor(unittest.TestCase):
    def test_returns_color_mix(self):
        self.assertIn("color-mix(", v.heat_color(35, 0, 100))

    def test_clamped_to_0_100_percent(self):
        self.assertIn("45%", v.heat_color(999, 0, 100))  # 2026-09-10：上限45%（濃い地に文字が沈むため）
        self.assertIn("0%", v.heat_color(-999, 0, 100))

    def test_flat_range_does_not_raise(self):
        out = v.heat_color(5, 5, 5)
        self.assertIn("color-mix(", out)


class TestDeterminism(unittest.TestCase):
    """Same input -> same output, for every public function."""

    def test_all_components_are_deterministic(self):
        specs = [
            (v.timeline_svg, ({"events": [{"when": "2024", "label": "x", "text": "y"}]},)),
            (v.quadrant_svg, ({"items": [{"label": "a", "x": 0.4, "y": 0.6}]},)),
            (v.venn_svg, ({"sets": [{"label": "A", "items": ["1"]}, {"label": "B"}]},)),
            (
                v.flow_svg,
                ({"nodes": [{"id": "a"}, {"id": "b"}], "links": [{"from": "a", "to": "b", "value": 4}]},),
            ),
            (v.score_grid_svg, ({"axes": [{"name": "x", "level": 2}], "max": 3},)),
            (v.sparkline_svg, ([1, 2, 3],)),
            (v.callout_badge_svg, (2, "bad")),
            (v.callout_legend_html, ([{"n": 1, "text": "t"}],)),
            (v.compare_html, ("<p>a</p>", "<p>b</p>")),
            (v.heat_color, (30, 0, 100)),
        ]
        for func, args in specs:
            with self.subTest(func=func.__name__):
                self.assertEqual(func(*args), func(*args))


class TestExceptionSafety(unittest.TestCase):
    """Malformed input must degrade to a safe placeholder, never raise."""

    def test_none_and_garbage_inputs_do_not_raise(self):
        garbage = [None, 123, "not-a-dict", [], object()]
        for g in garbage:
            with self.subTest(value=repr(g)):
                self.assertTrue(v.timeline_svg(g).startswith("<svg"))
                self.assertTrue(v.quadrant_svg(g).startswith("<svg"))
                self.assertTrue(v.venn_svg(g).startswith("<svg"))
                self.assertTrue(v.flow_svg(g).startswith("<svg"))
                self.assertTrue(v.score_grid_svg(g).startswith("<svg"))

    def test_sparkline_and_heat_color_with_garbage(self):
        self.assertTrue(v.sparkline_svg(None).startswith("<svg"))
        self.assertTrue(v.sparkline_svg("nope").startswith("<svg"))
        self.assertIsInstance(v.heat_color("nope", "x", None), str)

    def test_callout_helpers_with_garbage(self):
        self.assertTrue(v.callout_badge_svg("nope", "not-a-tone").startswith("<svg"))
        self.assertTrue(v.callout_legend_html(None).startswith("<ul"))
        self.assertTrue(v.callout_legend_html([None, 5, {"n": "x", "text": "ok"}]).startswith("<ul"))

    def test_compare_html_with_non_string_bodies(self):
        out = v.compare_html(None, 123, labels="not-a-pair")
        self.assertTrue(out.startswith("<div"))
        self.assertIn("前", out)
        self.assertIn("後", out)


if __name__ == "__main__":
    unittest.main()

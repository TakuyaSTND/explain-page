from __future__ import annotations

import math
import re
import sys
import unittest
from pathlib import Path

HOOKS_DIR = Path(__file__).resolve().parents[1]
if str(HOOKS_DIR) not in sys.path:
    sys.path.insert(0, str(HOOKS_DIR))

from visual.charts import render_chart, _text_width_px


class ChartRenderTests(unittest.TestCase):
    def test_line_chart_basic(self):
        spec = {
            "kind": "line",
            "title": "コスト・便益の年次推移",
            "labels": ["2024", "2025", "2026"],
            "series": [
                {"name": "費用", "values": [10, 12, 9]},
                {"name": "便益", "values": [5, 8, 11]},
            ],
            "unit": "億円",
        }
        svg = render_chart(spec)

        self.assertTrue(svg.startswith("<svg"))
        self.assertTrue(svg.endswith("</svg>"))
        self.assertIn('viewBox="0 0 640 360"', svg)
        self.assertIn('class="chart"', svg)
        self.assertEqual(svg.count("<polyline"), 2)
        self.assertEqual(svg.count("<circle"), 6)  # 3 points x 2 series
        self.assertIn("費用", svg)
        self.assertIn("便益", svg)
        self.assertIn("億円", svg)
        self.assertIn("var(--accent)", svg)
        self.assertNotIn("<script", svg)
        self.assertNotIn("foreignObject", svg)
        self.assertNotIn("url(", svg)

    def test_bar_chart_basic(self):
        spec = {
            "kind": "bar",
            "title": "候補の比較",
            "labels": ["A案", "B案"],
            "series": [
                {"name": "費用", "values": [3, 5]},
                {"name": "便益", "values": [6, 4]},
            ],
            "unit": "",
        }
        svg = render_chart(spec)

        self.assertTrue(svg.startswith("<svg"))
        # 2 legend swatches + 2 labels x 2 series bars = 6 rects total.
        self.assertEqual(svg.count("<rect"), 6)
        self.assertIn("A案", svg)
        self.assertIn("B案", svg)

    def test_non_numeric_value_raises_value_error(self):
        base = {
            "kind": "line",
            "title": "t",
            "labels": ["a", "b", "c"],
        }
        with self.assertRaises(ValueError):
            render_chart({**base, "series": [{"name": "s", "values": [1, "x", 3]}]})
        with self.assertRaises(ValueError):
            # bool must not silently pass as a number even though bool is
            # an int subclass in Python.
            render_chart({**base, "series": [{"name": "s", "values": [1, True, 3]}]})

    def test_length_mismatch_raises_value_error(self):
        spec = {
            "kind": "line",
            "title": "t",
            "labels": ["a", "b", "c"],
            "series": [{"name": "s", "values": [1, 2]}],
        }
        with self.assertRaises(ValueError):
            render_chart(spec)

    def test_empty_series_raises_value_error(self):
        spec = {
            "kind": "bar",
            "title": "t",
            "labels": ["a", "b"],
            "series": [],
        }
        with self.assertRaises(ValueError):
            render_chart(spec)

    def test_label_and_name_are_escaped(self):
        spec = {
            "kind": "line",
            "title": "<script>alert(1)</script>",
            "labels": ["<script>x</script>", "b"],
            "series": [{"name": "<script>y</script>", "values": [1, 2]}],
        }
        svg = render_chart(spec)

        self.assertNotIn("<script", svg)
        self.assertIn("&lt;script&gt;", svg)

    def test_all_values_equal_does_not_raise(self):
        spec = {
            "kind": "line",
            "title": "一定値",
            "labels": ["a", "b", "c"],
            "series": [{"name": "s", "values": [5, 5, 5]}],
        }
        svg = render_chart(spec)
        self.assertTrue(svg.startswith("<svg"))
        self.assertEqual(svg.count("<circle"), 3)

        zero_spec = {
            "kind": "bar",
            "title": "全部ゼロ",
            "labels": ["a", "b"],
            "series": [{"name": "s", "values": [0, 0]}],
        }
        svg_zero = render_chart(zero_spec)
        self.assertTrue(svg_zero.startswith("<svg"))

    def test_negative_values_draw_zero_line(self):
        spec = {
            "kind": "bar",
            "title": "増減",
            "labels": ["a", "b"],
            "series": [{"name": "s", "values": [-4, 6]}],
        }
        svg = render_chart(spec)
        self.assertIn('stroke-width="1.5"', svg)

        # A chart whose data never crosses zero should not draw the
        # dedicated zero-reference line.
        positive_spec = {
            "kind": "bar",
            "title": "増加のみ",
            "labels": ["a", "b"],
            "series": [{"name": "s", "values": [4, 6]}],
        }
        svg_positive = render_chart(positive_spec)
        self.assertNotIn('stroke-width="1.5"', svg_positive)

    def test_deterministic_output(self):
        spec = {
            "kind": "line",
            "title": "再現性",
            "labels": ["a", "b"],
            "series": [{"name": "s", "values": [1, 2]}],
            "unit": "件",
        }
        self.assertEqual(render_chart(spec), render_chart(spec))

    def test_legend_items_do_not_overlap(self):
        # Real-world regression: two Japanese legend names of unequal
        # length used to be spaced by a flat per-character estimate that
        # under-counts CJK width, so the second item's swatch could start
        # before the first item's text finished rendering (overlap).
        name1 = "当たり件数"
        name2 = "うち誤爆（判定）"
        spec = {
            "kind": "line",
            "title": "凡例の重なり確認",
            "labels": ["2024", "2025"],
            "series": [
                {"name": name1, "values": [1, 2]},
                {"name": name2, "values": [3, 4]},
            ],
        }
        svg = render_chart(spec)

        # kind="line" means every <rect> in the output is a legend swatch.
        rect_xs = [float(m) for m in re.findall(r'<rect x="([\-0-9.]+)"', svg)]
        self.assertEqual(len(rect_xs), 2)
        swatch1_x, swatch2_x = rect_xs

        legend_font_size = 11
        swatch_w = 11.0
        swatch_gap = 5.0
        item1_text_width = _text_width_px(name1, legend_font_size)

        if swatch2_x > swatch1_x:
            # Same legend row: item2's swatch must start at/after item1's
            # text actually ends, not at some fixed flat offset.
            self.assertGreaterEqual(
                swatch2_x, swatch1_x + swatch_w + swatch_gap + item1_text_width - 0.5
            )
        else:
            # Wrapped to its own row instead -- also an acceptable, and
            # by construction non-overlapping, layout.
            self.assertNotEqual(swatch2_x, swatch1_x)

    def test_y_axis_ticks_are_nice_numbers(self):
        spec = {
            "kind": "bar",
            "title": "目盛の桁確認",
            "labels": ["A", "B"],
            "series": [{"name": "s", "values": [0, 299]}],
        }
        svg = render_chart(spec)

        tick_texts = re.findall(
            r'<text x="[\-0-9.]+" y="[\-0-9.]+" text-anchor="end" fill="var\(--ink-2\)" '
            r'font-size="[0-9.]+">([\-0-9.]+)</text>',
            svg,
        )
        self.assertGreaterEqual(len(tick_texts), 4)
        values = [float(t) for t in tick_texts]
        diffs = sorted(set(round(b - a, 6) for a, b in zip(values, values[1:])))
        self.assertEqual(len(diffs), 1, "tick steps must be uniform, got %r" % (diffs,))
        step = diffs[0]
        # A "nice" step is 1, 2, or 5 times a power of ten -- never a
        # noisy fraction like the 74.75 a naive 4-way linspace produces.
        exponent = round(math.log10(step), 6)
        mantissa = round(step / (10 ** math.floor(exponent + 1e-9)), 6)
        self.assertIn(round(mantissa), (1, 2, 5))

    def test_bar_values_get_readable_labels(self):
        spec = {
            "kind": "bar",
            "title": "値ラベル確認",
            "labels": ["A案", "B案"],
            "series": [{"name": "件数", "values": [7, 42]}],
            "unit": "件",
        }
        svg = render_chart(spec)

        self.assertEqual(svg.count('class="chart-value-label"'), 2)
        self.assertIn(">7件<", svg)
        self.assertIn(">42件<", svg)

    def test_zero_value_bar_gets_a_visible_marker(self):
        zero_spec = {
            "kind": "bar",
            "title": "ゼロの棒",
            "labels": ["A", "B"],
            "series": [{"name": "s", "values": [0, 5]}],
        }
        svg = render_chart(zero_spec)
        self.assertEqual(svg.count('class="chart-zero-mark"'), 1)

        nonzero_spec = {
            "kind": "bar",
            "title": "ゼロなし",
            "labels": ["A", "B"],
            "series": [{"name": "s", "values": [3, 5]}],
        }
        svg_nonzero = render_chart(nonzero_spec)
        self.assertEqual(svg_nonzero.count('class="chart-zero-mark"'), 0)

    def test_long_x_label_wraps_to_two_lines(self):
        long_label = "あ" * 40
        spec = {
            "kind": "bar",
            "title": "長いラベルの折り返し",
            "labels": [long_label, "b"],
            "series": [{"name": "s", "values": [1, 2]}],
        }
        svg = render_chart(spec)
        # Wrap mode applies per-axis (both labels render as two <tspan>
        # lines), never rotated; the long label's full text must survive
        # the split across its two lines.
        self.assertGreaterEqual(svg.count("<tspan"), 2)
        self.assertNotIn('transform="rotate(', svg)
        self.assertEqual(svg.count("あ"), 40)  # "あ" x40, none dropped

    def test_many_x_labels_rotate(self):
        labels = [str(2000 + i) for i in range(12)]
        spec = {
            "kind": "line",
            "title": "多いラベルの回転",
            "labels": labels,
            "series": [{"name": "s", "values": list(range(12))}],
        }
        svg = render_chart(spec)
        self.assertIn('transform="rotate(-30', svg)
        self.assertEqual(svg.count("<tspan"), 0)


if __name__ == "__main__":
    unittest.main()

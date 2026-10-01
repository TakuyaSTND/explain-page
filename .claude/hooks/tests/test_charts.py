from __future__ import annotations

import html
import math
import re
import sys
import unittest
from pathlib import Path

HOOKS_DIR = Path(__file__).resolve().parents[1]
if str(HOOKS_DIR) not in sys.path:
    sys.path.insert(0, str(HOOKS_DIR))

from visual.charts import render_chart, _text_width_px


def _tick_values(svg):
    """Y-axis tick labels, bottom to top (they are emitted in ascending order)."""
    texts = re.findall(
        r'<text x="[\-0-9.]+" y="[\-0-9.]+" text-anchor="end" fill="var\(--ink-2\)" '
        r'font-size="[0-9.]+">([\-0-9.]+)</text>',
        svg,
    )
    return [float(t) for t in texts]


def _bar_heights(svg):
    """Heights of the data bars (legend swatches carry rx= and are skipped)."""
    return [
        float(h)
        for h in re.findall(
            r'<rect x="[\-0-9.]+" y="[\-0-9.]+" width="[\-0-9.]+" height="([\-0-9.]+)" fill=', svg
        )
    ]


# Text boxes are estimated from the font size: the fallback chain the page
# uses (Zen Kaku Gothic New ...) measured at most 1.02em above and 0.31em
# below the baseline in Chromium, and 0.90-1.13x the estimated width, so the
# estimate is taken slightly larger.
_ASCENT_EM = 1.05
_DESCENT_EM = 0.32
_WIDTH_SLACK = 1.15


def _text_box(x, y, lines, font_size, line_gap=0.0):
    width = max(_text_width_px(line, font_size) for line in lines) * _WIDTH_SLACK
    return (x - width / 2, y - _ASCENT_EM * font_size,
            x + width / 2, y + _DESCENT_EM * font_size + line_gap * (len(lines) - 1))


def _value_label_boxes(svg):
    return [
        _text_box(float(x), float(y), [html.unescape(t)], float(fs))
        for x, y, fs, t in re.findall(
            r'<text class="chart-value-label" x="([\-0-9.]+)" y="([\-0-9.]+)"[^>]*font-size="([0-9.]+)">([^<]*)</text>',
            svg,
        )
    ]


def _x_label_boxes(svg):
    boxes = []
    for x, y, inner in re.findall(
        r'<text x="([\-0-9.]+)" y="([\-0-9.]+)" text-anchor="middle" fill="var\(--ink-2\)" font-size="11">(.*?)</text>',
        svg,
    ):
        lines = re.findall(r"<tspan[^>]*>(.*?)</tspan>", inner) or [inner]
        boxes.append(_text_box(float(x), float(y), [html.unescape(s) for s in lines], 11, line_gap=12))
    return boxes


def _boxes_overlap(a, b):
    return a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]


def _gridline_ys(svg):
    return [float(y) for y in re.findall(r'<line x1="[\-0-9.]+" y1="([\-0-9.]+)" x2="[\-0-9.]+" y2="[\-0-9.]+" stroke="var\(--rule\)"', svg)]


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

    # Value axis range -----------------------------------------------------
    # Real-world regression (2026-09-29): an all-positive bar chart took the
    # axis floor from the smallest value (1155 -> 1000), so the 1155 bar was
    # drawn at about 1/10 of the 2501 bar when the real ratio is about 1/2.
    _REPORTED_BAR = {
        "kind": "bar",
        "labels": ["ありがとう", "関数の動きを説明して", "頁を作って"],
        "series": [
            {"name": "直す前", "values": [2501, 2501, 3577]},
            {"name": "直した後", "values": [1155, 1155, 3577]},
        ],
        "unit": "字",
    }

    def test_bar_axis_starts_at_zero_for_positive_values(self):
        svg = render_chart(self._REPORTED_BAR)
        ticks = _tick_values(svg)
        self.assertEqual(ticks[0], 0.0)
        self.assertGreaterEqual(ticks[-1], 3577)

        # Bar length must be proportional to the value itself. Bars are
        # emitted category by category, series by series: 2501, 1155, ...
        heights = _bar_heights(svg)
        self.assertEqual(len(heights), 6)
        self.assertAlmostEqual(heights[1] / heights[0], 1155 / 2501, delta=0.01)
        self.assertAlmostEqual(heights[0] / heights[4], 2501 / 3577, delta=0.01)

    def test_bar_axis_includes_zero_for_negative_values(self):
        spec = {
            "kind": "bar",
            "title": "減少のみ",
            "labels": ["a", "b"],
            "series": [{"name": "s", "values": [-5, -3]}],
        }
        ticks = _tick_values(render_chart(spec))
        self.assertEqual(ticks[-1], 0.0)
        self.assertLessEqual(ticks[0], -5)

    def test_bar_axis_includes_zero_even_with_explicit_y_min(self):
        # A caller-supplied floor above zero would truncate the bars the
        # same way, so the zero rule wins for bars.
        spec = {**self._REPORTED_BAR, "y_min": 1000}
        self.assertEqual(_tick_values(render_chart(spec))[0], 0.0)

    def test_all_zero_bar_axis_floor_is_zero(self):
        spec = {
            "kind": "bar",
            "title": "全部ゼロ",
            "labels": ["a", "b"],
            "series": [{"name": "s", "values": [0, 0]}],
        }
        svg = render_chart(spec)
        self.assertEqual(_tick_values(svg)[0], 0.0)
        self.assertEqual(svg.count('class="chart-zero-mark"'), 2)

    # Negative value labels ------------------------------------------------
    # Real-world regression (2026-09-29): a negative bar that reaches the
    # bottom of the axis put its value label (12px below the bar end) on top
    # of the x-axis label, e.g. "-4億円" over "2024".
    _NEGATIVE_CASES = {
        "mixed": {
            "kind": "bar", "title": "収支", "labels": ["2024", "2025", "2026"],
            "series": [{"name": "収支", "values": [-4, 6, 2]}], "unit": "億円",
        },
        "negative_only": {
            "kind": "bar", "title": "前年からの増減", "labels": ["A市", "B市", "C市"],
            "series": [{"name": "増減", "values": [-10, -5, -8]}], "unit": "件",
        },
        "wrapped_labels": {
            "kind": "bar", "title": "折り返す項目名",
            "labels": ["長い項目名の" * 4, "b", "c"],
            "series": [{"name": "今年", "values": [-20, 5, 12]}, {"name": "前年", "values": [-12, 8, -20]}],
            "unit": "億円",
        },
    }

    def test_negative_value_labels_stay_clear_of_x_labels(self):
        for name, spec in self._NEGATIVE_CASES.items():
            with self.subTest(name):
                svg = render_chart(spec)
                x_boxes = _x_label_boxes(svg)
                self.assertEqual(len(x_boxes), len(spec["labels"]))
                for value_box in _value_label_boxes(svg):
                    for x_box in x_boxes:
                        self.assertFalse(
                            _boxes_overlap(value_box, x_box),
                            "value label %r overlaps x label %r" % (value_box, x_box),
                        )

    def test_room_for_negative_labels_keeps_ticks_and_proportions(self):
        # The fix only raises the plot's bottom edge: the axis keeps its
        # ticks, and bar lengths stay proportional to the values.
        svg = render_chart(self._NEGATIVE_CASES["mixed"])
        self.assertEqual(_tick_values(svg), [-4.0, -2.0, 0.0, 2.0, 4.0, 6.0])
        heights = _bar_heights(svg)
        self.assertAlmostEqual(heights[0] / heights[1], 4 / 6, delta=0.01)
        self.assertAlmostEqual(heights[2] / heights[1], 2 / 6, delta=0.01)

    def test_no_room_is_reserved_when_labels_already_fit(self):
        # Charts whose labels already fit keep the default plot bottom (312).
        fits = {
            "kind": "bar", "title": "減少のみ", "labels": ["A市", "B市", "C市"],
            "series": [{"name": "増減", "values": [-12, -4, -7]}], "unit": "件",
        }
        positive = {**fits, "series": [{"name": "件数", "values": [12, 4, 7]}]}
        for spec in (fits, positive):
            with self.subTest(spec["series"][0]["values"]):
                self.assertEqual(max(_gridline_ys(render_chart(spec))), 312.0)

    def test_line_axis_still_fits_the_data(self):
        # A line encodes change by position, not length, so it keeps
        # auto-scaling to the data range (the floor stays at 1000 here).
        spec = {**self._REPORTED_BAR, "kind": "line"}
        ticks = _tick_values(render_chart(spec))
        self.assertEqual(ticks[0], 1000.0)
        self.assertEqual(ticks[-1], 4000.0)


if __name__ == "__main__":
    unittest.main()

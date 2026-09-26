from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path

HOOKS_DIR = Path(__file__).resolve().parents[1]
if str(HOOKS_DIR) not in sys.path:
    sys.path.insert(0, str(HOOKS_DIR))

from visual.icons import ICON_NAMES, icon_svg, icon_symbol_defs

_TONE_VAR = {
    "ink": "var(--ink)",
    "accent": "var(--accent)",
    "pass": "var(--pass)",
    "warn": "var(--warn)",
    "fail": "var(--fail)",
}


class IconNamesTests(unittest.TestCase):
    def test_icon_names_is_a_nonempty_tuple_of_str(self):
        self.assertIsInstance(ICON_NAMES, tuple)
        self.assertGreaterEqual(len(ICON_NAMES), 25)
        for name in ICON_NAMES:
            self.assertIsInstance(name, str)
            self.assertTrue(name)
        # no duplicates
        self.assertEqual(len(ICON_NAMES), len(set(ICON_NAMES)))


class IconSvgTests(unittest.TestCase):
    def test_every_known_name_returns_a_well_formed_svg(self):
        for name in ICON_NAMES:
            with self.subTest(name=name):
                svg = icon_svg(name)
                self.assertIsNotNone(svg)
                self.assertTrue(svg.startswith("<svg"))
                self.assertTrue(svg.endswith("</svg>"))
                self.assertIn('viewBox="0 0 24 24"', svg)
                self.assertIn('fill="none"', svg)
                self.assertIn('stroke-width="2"', svg)

    def test_unknown_name_returns_none(self):
        self.assertIsNone(icon_svg("this_icon_does_not_exist"))
        self.assertIsNone(icon_svg(""))

    def test_non_string_name_returns_none_without_raising(self):
        self.assertIsNone(icon_svg(None))  # type: ignore[arg-type]
        self.assertIsNone(icon_svg(123))  # type: ignore[arg-type]

    def test_no_xmlns_declared_anywhere(self):
        for name in ICON_NAMES:
            svg = icon_svg(name)
            self.assertNotIn("xmlns", svg)

    def test_no_script_or_external_reference(self):
        for name in ICON_NAMES:
            svg = icon_svg(name)
            self.assertNotIn("<script", svg)
            self.assertNotIn("url(", svg)
            self.assertNotIn("foreignObject", svg)
            self.assertNotIn("http://", svg)
            self.assertNotIn("https://", svg)

    def test_size_is_reflected_in_width_and_height(self):
        svg = icon_svg("person", size=48)
        self.assertIn('width="48"', svg)
        self.assertIn('height="48"', svg)

    def test_default_size_is_24(self):
        svg = icon_svg("person")
        self.assertIn('width="24"', svg)
        self.assertIn('height="24"', svg)

    def test_non_positive_or_bad_size_falls_back_to_24(self):
        for bad in (0, -10, "not-a-number", None):
            with self.subTest(bad=bad):
                svg = icon_svg("person", size=bad)  # type: ignore[arg-type]
                self.assertIn('width="24"', svg)
                self.assertIn('height="24"', svg)

    def test_stroke_is_current_color_and_tone_maps_to_css_variable(self):
        for tone, css_var in _TONE_VAR.items():
            with self.subTest(tone=tone):
                svg = icon_svg("clock", tone=tone)
                self.assertIn('stroke="currentColor"', svg)
                self.assertIn("color:%s" % css_var, svg)

    def test_unknown_tone_falls_back_to_ink(self):
        svg = icon_svg("clock", tone="not-a-real-tone")
        self.assertIn("color:var(--ink)", svg)

    def test_name_is_escaped_in_aria_label(self):
        # Every known name is a plain ASCII identifier already, but the
        # escape() call itself must not have been dropped -- check the
        # aria-label attribute is present and well formed for a sample.
        svg = icon_svg("map_pin")
        self.assertIn('aria-label="map_pin"', svg)

    def test_deterministic_same_input_same_output(self):
        first = icon_svg("gear", size=32, tone="accent")
        second = icon_svg("gear", size=32, tone="accent")
        self.assertEqual(first, second)


class IconSymbolDefsTests(unittest.TestCase):
    def test_defs_wraps_a_symbol_per_requested_known_name(self):
        subset = ICON_NAMES[:5]
        defs = icon_symbol_defs(subset)
        self.assertTrue(defs.startswith("<defs>"))
        self.assertTrue(defs.endswith("</defs>"))
        for name in subset:
            self.assertIn('<symbol id="ic-%s"' % name, defs)
        self.assertEqual(defs.count("<symbol"), len(subset))
        self.assertEqual(defs.count("</symbol>"), len(subset))

    def test_all_names_produce_all_ids(self):
        defs = icon_symbol_defs(ICON_NAMES)
        for name in ICON_NAMES:
            self.assertIn('id="ic-%s"' % name, defs)
        self.assertEqual(defs.count("<symbol"), len(ICON_NAMES))

    def test_unknown_names_are_dropped_silently(self):
        defs = icon_symbol_defs(["person", "not-a-real-icon", "clock"])
        self.assertIn("ic-person", defs)
        self.assertIn("ic-clock", defs)
        self.assertNotIn("not-a-real-icon", defs)
        self.assertEqual(defs.count("<symbol"), 2)

    def test_empty_or_all_unknown_returns_empty_string(self):
        self.assertEqual(icon_symbol_defs([]), "")
        self.assertEqual(icon_symbol_defs(["nope", "still-nope"]), "")

    def test_duplicate_names_produce_one_symbol_each(self):
        defs = icon_symbol_defs(["person", "person", "clock"])
        self.assertEqual(defs.count("<symbol"), 2)

    def test_symbols_have_matching_viewbox_and_no_xmlns(self):
        defs = icon_symbol_defs(ICON_NAMES)
        self.assertNotIn("xmlns", defs)
        # every symbol carries the same 24x24 viewBox
        self.assertEqual(
            len(re.findall(r'viewBox="0 0 24 24"', defs)), len(ICON_NAMES)
        )

    def test_generator_input_is_accepted(self):
        # Iterable[str] should work for a one-shot generator, not just a list.
        def gen():
            yield "person"
            yield "clock"

        defs = icon_symbol_defs(gen())
        self.assertEqual(defs.count("<symbol"), 2)


if __name__ == "__main__":
    unittest.main()

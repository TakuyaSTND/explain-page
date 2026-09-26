from __future__ import annotations

import sys
import unittest
from pathlib import Path

HOOKS_DIR = Path(__file__).resolve().parents[1]
if str(HOOKS_DIR) not in sys.path:
    sys.path.insert(0, str(HOOKS_DIR))

from visual.formula import tex_to_mathml


class FormulaMathMLTests(unittest.TestCase):
    def _assert_math(self, result: str) -> None:
        self.assertIsNotNone(result)
        self.assertTrue(
            result.startswith(
                '<math display="block">'
            )
        )
        self.assertTrue(result.endswith("</math>"))

    def test_simple_sum_and_equals(self):
        result = tex_to_mathml("a+b=c")
        self._assert_math(result)
        self.assertIn("<mi>a</mi>", result)
        self.assertIn("<mo>+</mo>", result)
        self.assertIn("<mi>b</mi>", result)
        self.assertIn("<mo>=</mo>", result)
        self.assertIn("<mi>c</mi>", result)

    def test_frac(self):
        result = tex_to_mathml(r"\frac{a}{b}")
        self._assert_math(result)
        self.assertIn("<mfrac><mi>a</mi><mi>b</mi></mfrac>", result)

    def test_sup_and_sub_combined(self):
        result = tex_to_mathml("x^{2}_{i}")
        self._assert_math(result)
        self.assertIn("<msubsup><mi>x</mi><mi>i</mi><mn>2</mn></msubsup>", result)

    def test_sum_with_bounds_and_trailing_subscript(self):
        result = tex_to_mathml(r"\sum_{i=1}^{n} x_i")
        self._assert_math(result)
        self.assertIn("<munderover><mo>∑</mo>", result)
        self.assertIn("<mi>i</mi><mo>=</mo><mn>1</mn>", result)
        self.assertIn("<mi>n</mi></munderover>", result)
        self.assertIn("<msub><mi>x</mi><mi>i</mi></msub>", result)

    def test_sqrt(self):
        result = tex_to_mathml(r"\sqrt{2}")
        self._assert_math(result)
        self.assertIn("<msqrt><mn>2</mn></msqrt>", result)

    def test_greek_and_times(self):
        result = tex_to_mathml(r"\alpha \times \beta")
        self._assert_math(result)
        self.assertIn("<mi>α</mi>", result)
        self.assertIn("<mo>×</mo>", result)
        self.assertIn("<mi>β</mi>", result)

    def test_text_with_japanese_and_number(self):
        result = tex_to_mathml(r"\text{費用} \times 1.5")
        self._assert_math(result)
        self.assertIn("<mtext>費用</mtext>", result)
        self.assertIn("<mo>×</mo>", result)
        self.assertIn("<mn>1.5</mn>", result)

    def test_unsupported_command_returns_none(self):
        result = tex_to_mathml(r"\mathfrak{A}")
        self.assertIsNone(result)

    def test_script_injection_inside_text_is_escaped(self):
        result = tex_to_mathml(r"\text{<script>alert(1)</script>}")
        self.assertIsNotNone(result)
        self.assertNotIn("<script", result)
        self.assertIn("&lt;", result)
        self.assertIn(
            "&lt;script&gt;alert(1)&lt;/script&gt;",
            result,
        )

    def test_unclosed_brace_returns_none(self):
        result = tex_to_mathml(r"\frac{a}{b")
        self.assertIsNone(result)

    def test_stray_closing_brace_returns_none(self):
        result = tex_to_mathml("a}")
        self.assertIsNone(result)

    def test_percent_and_comparisons(self):
        result = tex_to_mathml(r"a \le b \ge c \ne d \approx 5\%")
        self._assert_math(result)
        self.assertIn("<mo>≤</mo>", result)
        self.assertIn("<mo>≥</mo>", result)
        self.assertIn("<mo>≠</mo>", result)
        self.assertIn("<mo>≈</mo>", result)
        self.assertIn("<mo>%</mo>", result)

    def test_comma_and_decimal_number(self):
        result = tex_to_mathml("1,234.56")
        self._assert_math(result)
        self.assertIn("<mn>1,234.56</mn>", result)

    def test_left_right_and_quad(self):
        result = tex_to_mathml(r"\left( a \right) \quad b")
        self._assert_math(result)
        self.assertIn("<mo>(</mo>", result)
        self.assertIn("<mo>)</mo>", result)
        self.assertIn('<mspace width="1em"/>', result)

    def test_non_string_input_returns_none(self):
        self.assertIsNone(tex_to_mathml(None))  # type: ignore[arg-type]


if __name__ == "__main__":
    unittest.main()

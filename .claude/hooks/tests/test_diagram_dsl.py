"""1行記法から `diagram` の宣言辞書へ変換する parse_diagram_text の検査（担当F）。

観点＝矢印・線・両向き・破線・ラベル・箱の定義（題＋本文複数行）・属性
（icon/tone/col/row）・連鎖の展開・未定義idの自動生成・不正行のwarnings化。
例外を投げないこと、決定論的であることも確かめる。
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

HOOKS_DIR = Path(__file__).resolve().parents[1]
if str(HOOKS_DIR) not in sys.path:
    sys.path.insert(0, str(HOOKS_DIR))

from visual.diagram_dsl import parse_diagram_text

NL = chr(10)


def _node(result: dict, node_id: str) -> dict:
    for node in result["nodes"]:
        if node["id"] == node_id:
            return node
    raise AssertionError("node %r not found in %r" % (node_id, result["nodes"]))


class TestParseDiagramText(unittest.TestCase):
    def test_arrow(self):
        result = parse_diagram_text("A -> B")
        self.assertEqual(result["edges"], [{"from": "A", "to": "B", "label": "", "kind": "arrow"}])
        self.assertEqual([n["id"] for n in result["nodes"]], ["A", "B"])
        self.assertEqual(result["warnings"], [])

    def test_line(self):
        result = parse_diagram_text("A -- B")
        self.assertEqual(result["edges"], [{"from": "A", "to": "B", "label": "", "kind": "line"}])

    def test_biarrow(self):
        result = parse_diagram_text("A <-> B")
        self.assertEqual(result["edges"], [{"from": "A", "to": "B", "label": "", "kind": "biarrow"}])

    def test_dashed(self):
        result = parse_diagram_text("A -.-> B")
        self.assertEqual(result["edges"], [{"from": "A", "to": "B", "label": "", "kind": "dashed"}])

    def test_label_after_colon(self):
        result = parse_diagram_text("A -> B : 条件が満たされた時")
        self.assertEqual(
            result["edges"],
            [{"from": "A", "to": "B", "label": "条件が満たされた時", "kind": "arrow"}],
        )

    def test_node_definition_title_and_two_body_lines(self):
        result = parse_diagram_text("A: 題 | 本文1行目 / 本文2行目")
        node = _node(result, "A")
        self.assertEqual(node["title"], "題")
        self.assertEqual(node["text"], "本文1行目" + NL + "本文2行目")

    def test_node_definition_title_only(self):
        result = parse_diagram_text("A: 題だけ")
        node = _node(result, "A")
        self.assertEqual(node["title"], "題だけ")
        self.assertEqual(node["text"], "")

    def test_attribute_icon_paren(self):
        result = parse_diagram_text("A(icon=person)")
        node = _node(result, "A")
        self.assertEqual(node["icon"], "person")

    def test_attribute_tone_bracket(self):
        result = parse_diagram_text("A[tone=warn]")
        node = _node(result, "A")
        self.assertEqual(node["tone"], "warn")

    def test_attribute_col_row_are_ints(self):
        result = parse_diagram_text("A(col=2, row=1)")
        node = _node(result, "A")
        self.assertEqual(node["col"], 2)
        self.assertEqual(node["row"], 1)

    def test_chain_expands_to_two_edges(self):
        result = parse_diagram_text("A -> B -> C")
        self.assertEqual(
            result["edges"],
            [
                {"from": "A", "to": "B", "label": "", "kind": "arrow"},
                {"from": "B", "to": "C", "label": "", "kind": "arrow"},
            ],
        )
        self.assertEqual([n["id"] for n in result["nodes"]], ["A", "B", "C"])

    def test_undefined_id_referenced_only_is_auto_created(self):
        result = parse_diagram_text("A -> B")
        node = _node(result, "B")
        self.assertEqual(node["title"], "B")
        self.assertEqual(node["text"], "")

    def test_definition_after_reference_still_applies(self):
        text = NL.join(["A -> B", "B: 後から付けた題"])
        result = parse_diagram_text(text)
        node = _node(result, "B")
        self.assertEqual(node["title"], "後から付けた題")

    def test_blank_lines_and_comments_are_ignored(self):
        text = NL.join(["", "# これはコメント", "A -> B", "   ", "# もう一つ"])
        result = parse_diagram_text(text)
        self.assertEqual(len(result["edges"]), 1)
        self.assertEqual(result["warnings"], [])

    def test_invalid_line_goes_to_warnings_with_line_number(self):
        text = NL.join(["A -> B", "これは記法として不正な行です"])
        result = parse_diagram_text(text)
        self.assertEqual(len(result["edges"]), 1)
        self.assertEqual(len(result["warnings"]), 1)
        self.assertTrue(result["warnings"][0].startswith("2行目"))

    def test_invalid_edge_id_goes_to_warnings(self):
        result = parse_diagram_text("A -> not-valid")
        self.assertEqual(result["edges"], [])
        self.assertEqual(len(result["warnings"]), 1)
        self.assertIn("not-valid", result["warnings"][0])

    def test_dangling_arrow_is_invalid(self):
        result = parse_diagram_text("A ->")
        self.assertEqual(result["edges"], [])
        self.assertEqual(len(result["warnings"]), 1)

    def test_does_not_raise_on_garbage_input(self):
        garbage = NL.join(
            [
                "->",
                "::::",
                "A(",
                "A[tone=]",
                "()",
                "A -> -> B",
            ]
        )
        try:
            result = parse_diagram_text(garbage)
        except Exception as exc:  # noqa: BLE001 - 例外を投げないことそのものを確かめる
            self.fail("parse_diagram_text raised %r" % (exc,))
        self.assertIsInstance(result, dict)
        self.assertIn("nodes", result)
        self.assertIn("edges", result)
        self.assertIn("warnings", result)

    def test_deterministic_same_input_same_output(self):
        text = NL.join(["A: 題 | 本文", "A -> B : ラベル", "B(tone=warn)"])
        first = parse_diagram_text(text)
        second = parse_diagram_text(text)
        self.assertEqual(first, second)

    def test_empty_text_returns_empty_shape(self):
        result = parse_diagram_text("")
        self.assertEqual(result, {"nodes": [], "edges": [], "warnings": []})

    def test_none_text_does_not_raise(self):
        result = parse_diagram_text(None)  # type: ignore[arg-type]
        self.assertEqual(result, {"nodes": [], "edges": [], "warnings": []})


if __name__ == "__main__":
    unittest.main()


class JapaneseIdTests(unittest.TestCase):
    """2026-09-10：id に日本語を許す（読み手の言葉で箱を書けるように）。"""

    def test_japanese_ids_are_accepted(self):
        result = parse_diagram_text("資料: 元資料 | スライド画像\n資料 -> 頁 : 切り出して貼る")
        self.assertEqual(result["warnings"], [])
        self.assertEqual([n["id"] for n in result["nodes"]], ["資料", "頁"])
        self.assertEqual(result["edges"][0]["label"], "切り出して貼る")

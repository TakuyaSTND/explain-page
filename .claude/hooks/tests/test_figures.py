"""Mermaid の読み取りと、新しい図の型の形の計算の試験（2026-11-04・利用者が選んだ A6・A4）。

決めたこと（赤ペン diagram-skills-impl-01 の回答）：A6＝流れ図・やりとり・状態を自前で読む（Q11 B）・鍵 mermaid（Q12 A）。
A4＝魚の骨・滝の図・ダンベルの3型（Q13 A）・HTML と PDF の両方（Q14 A）・審査結果の頁には組み込まない（Q15 A）。
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.dont_write_bytecode = True

HOOKS_DIR = Path(__file__).resolve().parents[1]
if str(HOOKS_DIR) not in sys.path:
    sys.path.insert(0, str(HOOKS_DIR))

from visual import figures  # noqa: E402
from visual.contracts import ExplanationPlan  # noqa: E402
from visual.render_components import render_components  # noqa: E402

NL = chr(10)


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


class MermaidFlowchartTests(unittest.TestCase):
    def test_nodes_edges_labels_and_kinds(self):
        parsed = figures.parse_mermaid(NL.join([
            "flowchart LR",
            "A[申請] -->|書類| B{審査}",
            "B -- 不備 --> C(差し戻し)",
            "B ==> D([交付])",
            "C -.-> A",
            "A & D --> E",
            "A --- D",
            "%% 注記の行は読まない",
        ]))
        self.assertEqual(parsed["kind"], "flowchart")
        self.assertEqual(parsed["direction"], "horizontal")
        self.assertEqual([(n["id"], n["title"]) for n in parsed["nodes"]],
                         [("A", "申請"), ("B", "審査"), ("C", "差し戻し"), ("D", "交付"), ("E", "E")])
        self.assertEqual([(e["from"], e["to"], e["label"], e["kind"]) for e in parsed["edges"]], [
            ("A", "B", "書類", "arrow"), ("B", "C", "不備", "arrow"), ("B", "D", "", "arrow"),
            ("C", "A", "", "dashed"), ("A", "E", "", "arrow"), ("D", "E", "", "arrow"), ("A", "D", "", "line"),
        ])
        self.assertEqual(parsed["warnings"], [])

    def test_chain_and_vertical_direction(self):
        parsed = figures.parse_mermaid("graph TD" + NL + "A --> B --> C")
        self.assertEqual(parsed["direction"], "vertical")
        self.assertEqual([(e["from"], e["to"]) for e in parsed["edges"]], [("A", "B"), ("B", "C")])

    def test_subgraph_is_warned_but_inner_edges_are_kept(self):
        parsed = figures.parse_mermaid(NL.join(["flowchart TD", "subgraph 自治体", "A --> B", "end"]))
        self.assertEqual(len(parsed["edges"]), 1)
        self.assertTrue(any("subgraph" in w for w in parsed["warnings"]))

    def test_unknown_kind_is_warned(self):
        parsed = figures.parse_mermaid("pie" + NL + '"A" : 1')
        self.assertEqual(parsed["kind"], "unknown")
        self.assertTrue(parsed["warnings"])


class MermaidStateAndSequenceTests(unittest.TestCase):
    def test_state_start_end_alias_and_label(self):
        parsed = figures.parse_mermaid(NL.join([
            "stateDiagram-v2", "[*] --> 申請中", "申請中 --> 審査中 : 提出", 'state "交付済み（確定）" as 交付',
            "審査中 --> 交付 : 承認", "交付 --> [*]",
        ]))
        diagram = figures.mermaid_to_diagram(parsed)
        titles = {n["id"]: n["title"] for n in diagram["nodes"]}
        self.assertEqual(titles["__start__"], "開始")
        self.assertEqual(titles["__end__"], "終了")
        self.assertEqual(titles["交付"], "交付済み（確定）")
        tones = {n["id"]: n.get("tone") for n in diagram["nodes"]}
        self.assertEqual((tones["__start__"], tones["__end__"]), ("good", "bad"))
        self.assertIn(("申請中", "審査中", "提出"), [(e["from"], e["to"], e["label"]) for e in diagram["edges"]])

    def test_sequence_participants_messages_and_notes(self):
        parsed = figures.parse_mermaid(NL.join([
            "sequenceDiagram", "participant J as 住民", "actor S as 市役所", "J->>S: 申請書を出す", "S-->>J: 通知",
            "S->S: 確認", "alt 不備", "S->>J: 差し戻し", "end", "Note over J,S: 30日以内",
        ]))
        self.assertEqual([(p["id"], p["title"]) for p in parsed["participants"]], [("J", "住民"), ("S", "市役所")])
        messages = [i for i in parsed["items"] if i["type"] == "message"]
        self.assertEqual([(m["from"], m["to"], m["dash"], m["arrow"]) for m in messages],
                         [("J", "S", False, True), ("S", "J", True, True), ("S", "S", False, False), ("S", "J", False, True)])
        self.assertEqual([i["text"] for i in parsed["items"] if i["type"] == "note"], ["30日以内"])
        self.assertTrue(any("枠" in w for w in parsed["warnings"]))
        geom = figures.sequence_shapes(parsed)
        lifelines = [s for s in geom["shapes"] if s["t"] == "line" and s["dash"] and s["stroke"] == "muted"]
        self.assertEqual(len(lifelines), 2)
        self.assertGreater(geom["width"], 0)
        self.assertGreater(geom["height"], 0)


class ShapeTypeTests(unittest.TestCase):
    def test_waterfall_last_bar_is_the_running_total(self):
        geom = figures.waterfall_shapes({
            "start": {"label": "便益", "value": 120}, "unit": "億円",
            "steps": [{"label": "人件費", "value": -40}, {"label": "削減", "value": 10}, {"label": "壊れた", "value": "x"}],
        })
        texts = [s["text"] for s in geom["shapes"] if s["t"] == "text"]
        self.assertIn("90億円", texts)  # 120 − 40 + 10
        self.assertIn("+10億円", texts)
        self.assertTrue(any("壊れた" in w for w in geom["warnings"]))

    def test_dumbbell_draws_only_rows_with_both_numbers(self):
        geom = figures.dumbbell_shapes({"rows": [
            {"label": "給付", "before": 3.6, "after": 9.5}, {"label": "割合", "before": 4.5},
        ]})
        self.assertEqual(sum(1 for s in geom["shapes"] if s["t"] == "circle"), 2 + 2)  # 凡例の2つ＋描いた1行の2つ
        self.assertTrue(any("割合" in w for w in geom["warnings"]))

    def test_fishbone_needs_causes(self):
        self.assertTrue(figures.fishbone_shapes({"effect": "結果"})["warnings"])
        geom = figures.fishbone_shapes({"effect": "結果", "causes": [{"label": "制度", "items": ["要件"]}, {"label": "人"}]})
        self.assertIn("結果", [s["text"] for s in geom["shapes"] if s["t"] == "text"])

    def test_svg_escapes_text_and_uses_role_colors_only(self):
        geom = figures.fishbone_shapes({"effect": "<script>alert(1)</script>", "causes": [{"label": "a\"b", "tone": "#f00"}]})
        svg = figures.shapes_svg(geom, "<題>")
        self.assertNotIn("<script", svg)
        self.assertIn("&lt;script&gt;", svg)
        self.assertNotIn("#f00", svg)

    def test_kinsoku_in_figure_wrap(self):
        lines = figures.wrap("見直しを始め、対象を拡大する", 6 * 13 + 1, 13)
        self.assertTrue(all(not line.startswith("、") for line in lines), lines)


class RenderedFigureTests(unittest.TestCase):
    def _render(self, block: dict) -> str:
        return render_components(_plan("visual"), title="図", content={"sections": [{"component": "visual", "label": "図", "content": [block]}]})

    def test_flowchart_becomes_a_box_and_arrow_diagram(self):
        html = self._render({"mermaid": "flowchart LR" + NL + "A[申請] --> B[審査]"})
        self.assertIn('class="dia"', html)
        self.assertIn("申請", html)

    def test_sequence_and_new_types_are_drawn_as_shapes(self):
        html = self._render({"mermaid": NL.join(["sequenceDiagram", "J->>S: 申請"])})
        self.assertIn("fig-shapes seq", html)
        for key, value in (("fishbone", {"effect": "結果", "causes": [{"label": "制度"}]}),
                           ("waterfall", {"start": {"value": 1}, "steps": [{"label": "足す", "value": 2}]}),
                           ("dumbbell", {"rows": [{"label": "行", "before": 1, "after": 2}]})):
            self.assertIn("fig-shapes " + key, self._render({key: value}))

    def test_warnings_are_shown_and_escaped(self):
        html = self._render({"mermaid": NL.join(["flowchart TD", "A --> B", "<b>???"])})
        self.assertIn("dia-warn", html)
        self.assertNotIn("<b>???", html)


if __name__ == "__main__":
    unittest.main()

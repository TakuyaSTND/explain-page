"""図の禁則・線とラベルの後処理・描いた後の点検の試験（2026-11-04・利用者が選んだ A1・A2・A3）。

決めたこと（赤ペン diagram-skills-impl-01 の回答）：
- A1＝行の頭に句読点・中黒・閉じ括弧を置かない、行の末尾に開き括弧を置かない（Q3 A）。直し方は追い出し（Q1 A）。
  箱と矢印の図（diagram_layout.py）と、年表などの図（visuals.py）の両方（Q2 A）。
- A2＝同じ箱の同じ点に出入りする線の端を12pxずつずらす（Q5 A）。ラベルは重なる時だけ動かし、
  置き場が無ければ重なりの少ない所（Q4 A）。両側に同じ段の箱がある箱の迂回は、段の上下の隙間を通る。
- A3＝描いた後の実寸の点検は警告だけ（Q3 A）・表示検査と撮影の道具の両方（Q6 A）・箱と矢印の図だけ（Q7 A）。
"""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.dont_write_bytecode = True

HOOKS_DIR = Path(__file__).resolve().parents[1]
if str(HOOKS_DIR) not in sys.path:
    sys.path.insert(0, str(HOOKS_DIR))

from visual import diagram_check, diagram_layout, visual_smoke  # noqa: E402
from visual.contracts import ExplanationPlan  # noqa: E402
from visual.render_components import render_components  # noqa: E402
from visual.visuals import _wrap as visuals_wrap  # noqa: E402


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


def _node(title: str) -> dict:
    return {"title": title, "text": "本文の行です。少し長めに書く", "note": ""}


def _edge(a: int, b: int, label: str = "") -> dict:
    return {"from": a, "to": b, "label": label, "kind": "arrow", "curve": False}


# 審査結果の図（就労の資料）を小さくした形＝上の段3箱・中の段1箱・下の段3箱・最後に1箱。
# 直す前は、M2→B の迂回が M1 の裏と A の裏を通り、3本の矢印が L の同じ点に入っていた（実測）。
NODES = [_node(t) for t in ("M1", "M2", "M3", "M4", "A", "B", "C", "L")]
EDGES = [
    _edge(0, 4, "成立"), _edge(1, 5, "漏れ"), _edge(2, 6, "漏れ"), _edge(3, 5),
    _edge(4, 7, "漏れ"), _edge(5, 7, "漏れ"), _edge(6, 7, "成立"),
]


def _layout():
    return diagram_layout.layout_diagram(
        json.loads(json.dumps(NODES)), json.loads(json.dumps(EDGES)),
        max_cols=3, direction="auto", font_px=14, max_width=720,
    )


class KinsokuTests(unittest.TestCase):
    def test_comma_is_not_left_at_the_head_of_a_line(self):
        lines = diagram_layout._wrap("離脱できなくても積立が失われず、使い道を限って先に使える", 5)
        self.assertTrue(all(not line.startswith("、") for line in lines), lines)
        self.assertIn("ず、使い道", lines)  # 追い出し＝前の行の「ず」を次の行へ送った

    def test_opening_bracket_is_not_left_at_the_end_of_a_line(self):
        self.assertEqual(diagram_layout._wrap("計算式の照合（N04）", 9), ["計算式の照合", "（N04）"])

    def test_width_based_wrap_also_keeps_the_rule(self):
        lines = diagram_layout._wrap_to_width("保護世帯の自立が続き、社会保障費が抑えられる", 9 * 13, 13)
        self.assertTrue(all(not line.startswith("、") for line in lines), lines)

    def test_unfixable_run_of_punctuation_still_makes_progress(self):
        # 送っても直らない（全部が句読点）ときは送らない＝行は増やさず、必ず終わる
        self.assertEqual(diagram_layout._wrap("、、、、、、", 2), ["、、", "、、", "、、"])

    def test_small_kana_may_start_a_line(self):
        # Q3 A＝小さい仮名と長音は対象外
        self.assertEqual(diagram_layout._wrap("申請をチェックする", 5), ["申請をチェ", "ックする"])

    def test_timeline_wrap_keeps_the_rule(self):
        lines = visuals_wrap("見直しを始め、対象を拡大する", 6 * 12 * 0.95 + 1, 12, 3)
        self.assertTrue(all(not line.startswith("、") for line in lines), lines)


class RouteTidyTests(unittest.TestCase):
    def setUp(self):
        self.layout = _layout()
        self.boxes = [{"x": b.x, "y": b.y, "w": b.w, "h": b.h} for b in self.layout.boxes]

    def test_no_route_passes_behind_another_box(self):
        for route in self.layout.routes:
            self.assertFalse(
                diagram_layout._route_hits_other_box(route.points, route.control, self.boxes, route.from_index, route.to_index),
                (route.from_index, route.to_index, route.points),
            )

    def test_arrows_into_the_same_box_enter_at_different_points(self):
        ends = [(r.to_index, round(r.points[-1][0]), round(r.points[-1][1])) for r in self.layout.routes]
        self.assertEqual(len(ends), len(set(ends)), ends)

    def test_spread_is_twelve_pixels(self):
        into_last = sorted(r.points[-1][0] for r in self.layout.routes if r.to_index == 7)
        self.assertEqual(len(into_last), 3)
        self.assertAlmostEqual(into_last[1] - into_last[0], diagram_layout.PORT_SPREAD, places=3)

    def test_labels_do_not_sit_on_other_routes_or_labels(self):
        routes = self.layout.routes
        samples = [diagram_layout._route_samples(r) for r in routes]
        rects = {i: diagram_layout._label_rect(r.label_x, r.label_y, r.label) for i, r in enumerate(routes) if r.label}
        for i, rect in rects.items():
            for j, pts in enumerate(samples):
                if j != i:
                    self.assertFalse(diagram_layout._points_inside(rect, pts), (routes[i].label, i, j))
            for j, other in rects.items():
                if j != i:
                    self.assertFalse(diagram_layout._rects_overlap(rect, other), (i, j))

    def test_label_without_conflict_is_not_moved(self):
        layout = diagram_layout.layout_diagram(
            [_node("A"), _node("B")], [_edge(0, 1, "条件")], max_cols=3, direction="auto", font_px=14, max_width=720,
        )
        route = layout.routes[0]
        expected = diagram_layout._label_anchor_layered(route.points, route.control)
        self.assertAlmostEqual(route.label_x, expected[0], places=3)
        self.assertAlmostEqual(route.label_y, expected[1], places=3)


class RenderedRouteNumberTests(unittest.TestCase):
    def test_route_and_its_label_share_a_number(self):
        html = render_components(_plan("diagram"), title="図", content={"diagram": {
            "nodes": [{"id": "a", "label": "前"}, {"id": "b", "label": "後"}],
            "edges": [{"from": "a", "to": "b", "label": "条件"}],
        }})
        self.assertIn('data-r="0"></path>', html)
        self.assertIn('data-r="0">条件</text>', html)


class DiagramCheckTests(unittest.TestCase):
    def test_describe_makes_one_line_per_finding(self):
        lines = diagram_check.describe([
            {"fig": 1, "title": "図の題", "kind": "label-crossed", "text": "漏れ"},
            {"fig": 1, "title": "図の題", "kind": "label-crossed", "text": "漏れ"},
            {"fig": 2, "title": "", "kind": "routes-stacked", "text": "24px"},
            {"fig": 3, "title": "", "kind": "unknown", "text": "x"},
            "not a dict",
        ])
        self.assertEqual(lines, [
            "図1（図の題）：ラベル「漏れ」に別の線が通る",
            "図2：2本の線が同じ縦線・横線の上で重なる（24px）",
        ])

    def test_check_script_is_a_single_function_expression(self):
        source = diagram_check.DIAGRAM_CHECK_JS.strip()
        self.assertTrue(source.startswith("() => {"))
        self.assertTrue(source.endswith("}"))
        self.assertIn("svg.dia", source)

    def test_visual_smoke_passes_the_check_to_the_runner_and_keeps_findings_out_of_errors(self):
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        path = Path(temp_dir.name) / "page.html"
        path.write_text("<!doctype html><html><body><p>fixture</p></body></html>", encoding="utf-8")
        payload = {
            "status": "pass",
            "errors": [],
            "metrics": {"diagramChecks": [{"fig": 1, "title": "", "kind": "label-crossed", "text": "漏れ"}]},
        }
        completed = subprocess.CompletedProcess(args=["node"], returncode=0, stdout=json.dumps(payload), stderr="")
        with patch.object(visual_smoke, "_resolve_playwright", return_value=("C:/playwright/index.js", None)), \
                patch.object(visual_smoke, "_run_node", return_value=completed) as runner:
            result = visual_smoke.run_visual_smoke(path)
        command = runner.call_args.args[0]
        self.assertEqual(command[-1], diagram_check.DIAGRAM_CHECK_JS)
        self.assertEqual(result.status, "pass")
        self.assertEqual(result.errors, ())
        self.assertEqual(len(result.metrics["diagramChecks"]), 1)


class DiagramBudgetTests(unittest.TestCase):
    """A5（利用者の回答 Q9 A）＝箱9・矢印12を超える図だけを知らせる。色の数は数えない。"""

    def _content(self, nodes: int, edges: int) -> dict:
        node_list = [{"id": "n%d" % i, "label": "箱%d" % i, "tone": "warn"} for i in range(nodes)]
        edge_list = [{"from": "n0", "to": "n%d" % (1 + i % (nodes - 1))} for i in range(edges)]
        return {"sections": [{"component": "visual", "content": [{"diagram": {"nodes": node_list, "edges": edge_list}}]}]}

    def test_over_budget_diagram_is_reported(self):
        from visual import page_lint

        warnings = page_lint.diagram_budget_warnings(self._content(10, 13))
        self.assertEqual(len(warnings), 1)
        self.assertIn("箱が10個（9個まで）", warnings[0])
        self.assertIn("矢印が13本（12本まで）", warnings[0])

    def test_within_budget_is_quiet_even_with_many_colors(self):
        from visual import page_lint

        self.assertEqual(page_lint.diagram_budget_warnings(self._content(9, 12)), [])

    def test_one_line_notation_is_counted_after_parsing(self):
        from visual import page_lint

        text = chr(10).join("n0 -> n%d" % i for i in range(1, 11))
        warnings = page_lint.diagram_budget_warnings({"sections": [{"content": [{"diagram_text": text}]}]})
        self.assertEqual(len(warnings), 1)
        self.assertIn("箱が11個", warnings[0])


if __name__ == "__main__":
    unittest.main()

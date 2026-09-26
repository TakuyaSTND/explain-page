"""矢印付きの図（SVG）の回帰検査（2026-08-29 ユーザー依頼）。

⚠️この部品の設計上いちばん大事なのは「**生のSVGを受け取らない**」こと。
   レンダラーの安全性は「渡された文字は必ずエスケープする」で成り立っており、
   生のマークアップを通すとそこから任意のHTMLが入る道ができる。
   ∴受け取るのは箱と矢印の宣言だけで、SVGはこちらで組み立てる。
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

HOOKS_DIR = Path(__file__).resolve().parents[1]
if str(HOOKS_DIR) not in sys.path:
    sys.path.insert(0, str(HOOKS_DIR))

from visual.artifact_inspection import inspect_artifact_html
from visual.contracts import ExplanationPlan
from visual.glossary import GlossaryEntry
from visual.receipts import _has_external_dependency
from visual.render_components import render_components

NL = chr(10)

DIAGRAM = {
    "title": "依頼からフックまで",
    "caption": "左から右へ読む",
    "nodes": [
        {"id": "a", "label": "あなたの依頼", "col": 0, "row": 0, "hover": {
            "label": "入力",
            "title": "依頼の内容",
            "text": "利用者が実現してほしい結果を示す。",
            "role": "処理の始点",
            "evidence": "依頼本文",
            "status": "確認済みの入力として読む",
        }},
        {"id": "b", "label": "フック", "col": 1, "row": 0, "tone": "warn"},
        {"id": "c", "label": "差し戻し", "col": 1, "row": 1, "tone": "bad"},
        {"id": "d", "label": "頁が出る", "col": 2, "row": 0, "tone": "good"},
    ],
    "edges": [
        {"from": "a", "to": "b", "label": "注入"},
        {"from": "b", "to": "c"},
        {"from": "c", "to": "d", "label": "作り直す", "dashed": True},
    ],
}


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


class DiagramShapeTests(unittest.TestCase):
    def setUp(self):
        self.html = render_components(
            _plan("diagram"), title="図", content={"diagram": DIAGRAM}
        )

    def test_boxes_arrows_and_labels_are_drawn(self):
        self.assertIn("<svg", self.html)
        self.assertEqual(self.html.count("<rect"), 4)
        # 矢印3本＋矢じりの定義1つ
        self.assertEqual(self.html.count("marker-end="), 3)
        self.assertIn('id="dia-arrow', self.html)  # 2026-09-12：矢じりは辺の色ごとの id（dia-arrow-accent 等）
        self.assertIn("あなたの依頼", self.html)
        self.assertIn("注入", self.html)

    def test_paths_are_behind_boxes_and_labels_are_above_boxes(self):
        """線は箱の文字を横切らず、注記は箱に隠れない描画順にする。"""
        route_path = self.html.index('fill="none"')
        first_box = self.html.index("<rect")
        edge_label = self.html.index(">注入</text>")
        self.assertLess(route_path, first_box)
        self.assertGreater(edge_label, first_box)

    def test_dashed_edge_is_dashed(self):
        self.assertIn("stroke-dasharray=", self.html)

    def test_tones_use_theme_variables_so_both_themes_work(self):
        self.assertIn("var(--warn)", self.html)
        self.assertIn("var(--fail)", self.html)
        self.assertIn("var(--pass)", self.html)
        self.assertIn("var(--surface)", self.html)
        # 生の色コードを直に書かない（明暗どちらかで読めなくなるため）
        self.assertNotIn('stroke="#', self.html)

    def test_accessible_name_and_caption(self):
        self.assertIn('role="img"', self.html)
        self.assertIn('aria-label="依頼からフックまで"', self.html)
        self.assertIn("<title>依頼からフックまで</title>", self.html)
        self.assertIn('class="cap"', self.html)
        self.assertIn("左から右へ読む", self.html)

    def test_node_detail_is_available_by_hover_focus_and_tap(self):
        self.assertIn('class="dia-node"', self.html)
        self.assertIn('data-hover="true"', self.html)
        self.assertIn('tabindex="0"', self.html)
        self.assertIn('data-hover-role="処理の始点"', self.html)
        self.assertIn('data-hover-evidence="依頼本文"', self.html)
        self.assertIn("tip.id='dia-node-tip'", self.html)
        self.assertIn("pointerenter", self.html)
        self.assertIn("addEventListener('focus'", self.html)
        self.assertIn("addEventListener('click'", self.html)
        self.assertIn("Tabキーで選ぶ", self.html)

    def test_node_detail_has_a_readable_accessible_fallback(self):
        self.assertIn(
            'aria-label="依頼の内容。利用者が実現してほしい結果を示す。図での役割：処理の始点。根拠：依頼本文。読み方：確認済みの入力として読む"',
            self.html,
        )
        self.assertIn(
            '<title>依頼の内容。利用者が実現してほしい結果を示す。図での役割：処理の始点。根拠：依頼本文。読み方：確認済みの入力として読む</title>',
            self.html,
        )

    def test_viewbox_grows_with_content(self):
        small = render_components(
            _plan("diagram"),
            title="図",
            content={"diagram": {"nodes": [{"id": "a", "label": "短い"}]}},
        )
        wide = render_components(
            _plan("diagram"),
            title="図",
            content={"diagram": {"nodes": [
                {"id": "a", "label": "とても長い名前をつけた箱です", "col": 0},
                {"id": "b", "label": "こちらも長い名前の箱", "col": 1},
            ]}},
        )

        def width(html):
            start = html.find('viewBox="0 0 ') + len('viewBox="0 0 ')
            return float(html[start:html.find('"', start)].split()[0])

        self.assertGreater(width(wide), width(small))


class DiagramSafetyTests(unittest.TestCase):
    """生のマークアップが素通りしないこと。"""

    def test_markup_in_labels_is_escaped(self):
        html = render_components(
            _plan("diagram"),
            title="図",
            content={"diagram": {"nodes": [
                {"id": "a", "label": '<script>bad()</script>'},
            ]}},
        )

        self.assertIn("&lt;script&gt;", html)
        self.assertNotIn("<script>bad()", html)

    def test_raw_string_is_not_accepted_as_svg(self):
        # 文字列を渡しても図解にはならない＝生のSVGを流し込む道が無い
        html = render_components(
            _plan("diagram"),
            title="図",
            content={"diagram": '<svg onload="bad()"></svg>'},
        )

        self.assertNotIn("<svg", html)
        self.assertNotIn("onload", html)

    def test_markup_in_node_hover_detail_is_escaped(self):
        html = render_components(
            _plan("diagram"),
            title="図",
            content={"diagram": {"nodes": [{
                "id": "a",
                "label": "安全な箱",
                "hover": {
                    "text": '<img src=x onerror="bad()">',
                    "role": '<script>bad()</script>',
                },
            }]}},
        )

        self.assertIn("&lt;img src=x onerror=&quot;bad()&quot;&gt;", html)
        self.assertIn("&lt;script&gt;bad()&lt;/script&gt;", html)
        self.assertNotIn("<img src=x", html)
        self.assertNotIn("<script>bad()", html)

    def test_diagram_passes_both_gates(self):
        html = render_components(
            _plan("diagram"), title="図", content={"diagram": DIAGRAM}
        )

        # 検品証を作れなくする「外部依存」と判定されない（url(#…) は自分の中の参照）
        self.assertFalse(_has_external_dependency(html))
        inspection = inspect_artifact_html(
            html, required_components=("diagram",), glossary_entries={}
        )
        self.assertEqual(inspection.errors, ())
        self.assertEqual(inspection.missing_components, ())

    def test_terms_inside_the_figure_are_not_demanded_to_be_wrapped(self):
        entries = {
            "検品証": GlossaryEntry(
                term="検品証", description="機械が調べて残す記録", provenance="p"
            )
        }
        html = render_components(
            _plan("diagram"),
            title="図",
            content={"diagram": {"nodes": [{"id": "a", "label": "検品証が残る"}]}},
            glossary_entries=entries,
        )

        inspection = inspect_artifact_html(
            html, required_components=("diagram",), glossary_entries=entries
        )

        self.assertEqual(inspection.unwrapped_identifiers, ())


class DiagramWiringTests(unittest.TestCase):
    def test_visual_accepts_a_mapping_and_draws_the_figure(self):
        html = render_components(
            _plan("visual"), title="図", content={"visual": DIAGRAM}
        )

        self.assertIn("<svg", html)
        self.assertIn('data-component="visual"', html)

    def test_visual_string_still_makes_the_old_flow(self):
        html = render_components(
            _plan("visual"), title="図", content={"visual": "依頼" + NL + "↓" + NL + "結果"}
        )

        self.assertNotIn("<svg", html)
        self.assertIn('class="flow-step"', html)

    def test_details_can_hold_a_diagram(self):
        html = render_components(
            _plan("details"),
            title="詳細",
            content={"details": [{"summary": "図で見る", "diagram": DIAGRAM}]},
        )

        self.assertIn("<details>", html)
        self.assertIn("<svg", html)


if __name__ == "__main__":
    unittest.main()

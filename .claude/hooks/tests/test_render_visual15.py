"""担当Bの配線（2026-09-10）の検査＝箱と矢印の根治＋10個の新しいブロック鍵。

対象＝`render_components.py` の `_diagram_block`（配置と経路を
`visual/diagram_layout.py:layout_diagram` に委ねた新しい経路）と、
svg／image／timeline／quadrant／venn／flow／score／compare／callouts／
diagram_text の配線、表の heat／bars。

⚠️このファイルは担当Bの持ち場（render_components.py・render_page.py・この
テスト）だけを検査する＝他の担当のモジュール（diagram_layout・svg_import・
images・visuals・diagram_dsl・icons）自体の単体検査は、それぞれの
test_diagram_layout.py 等が別に持つ。
"""
from __future__ import annotations

import io
import sys
import tempfile
import unittest
from pathlib import Path

HOOKS_DIR = Path(__file__).resolve().parents[1]
if str(HOOKS_DIR) not in sys.path:
    sys.path.insert(0, str(HOOKS_DIR))

import visual.render_components as rc
from visual.contracts import ExplanationPlan
from visual.diagram_layout import Box, Layout, Route
from visual.glossary import GlossaryEntry
from visual.receipts import _has_external_dependency
from visual.render_components import render_components

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


def _viewbox_dims(html: str) -> tuple[float, float]:
    start = html.find('viewBox="0 0 ') + len('viewBox="0 0 ')
    chunk = html[start:html.find('"', start)]
    w, h = chunk.split()
    return float(w), float(h)


try:
    import PIL  # noqa: F401
    _PIL_AVAILABLE = True
except Exception:  # Pillow は任意の部品
    _PIL_AVAILABLE = False


def _make_png(path: Path, size=(40, 24)) -> None:
    from PIL import Image

    img = Image.new("RGB", size, (30, 90, 160))
    img.save(path, format="PNG")


class NumberedAndIdEdgeTests(unittest.TestCase):
    """崩れ①の根治＝辺の from/to を番号で書いても、宣言した id でも矢印が結び付く。"""

    def test_index_edges_draw_a_path(self):
        html = render_components(
            _plan("diagram"),
            title="図",
            content={"diagram": {
                "nodes": [{"label": "はじめ"}, {"label": "つぎ"}],
                "edges": [{"from": 0, "to": 1}],
            }},
        )
        self.assertIn("<path", html)
        self.assertIn("marker-end=", html)

    def test_id_edges_draw_a_path(self):
        html = render_components(
            _plan("diagram"),
            title="図",
            content={"diagram": {
                "nodes": [{"id": "a", "label": "はじめ"}, {"id": "b", "label": "つぎ"}],
                "edges": [{"from": "a", "to": "b"}],
            }},
        )
        self.assertIn("<path", html)
        self.assertIn("marker-end=", html)


class ChainViewboxTests(unittest.TestCase):
    """崩れ②の根治＝6箱の鎖でも、viewBoxの幅が高さの4倍を超えない（層に折り返す）。"""

    def test_six_box_chain_is_not_squashed_into_one_row(self):
        nodes = [{"id": "n%d" % i, "label": "箱%d" % i} for i in range(6)]
        edges = [{"from": "n%d" % i, "to": "n%d" % (i + 1)} for i in range(5)]
        html = render_components(
            _plan("diagram"), title="図", content={"diagram": {"nodes": nodes, "edges": edges}}
        )
        width, height = _viewbox_dims(html)
        self.assertLess(width / height, 4.0)


class UnknownEdgeReferenceTests(unittest.TestCase):
    """崩れ③の根治＝解決できない参照は黙って捨てず、注意書きに出す。"""

    def test_unknown_reference_becomes_a_warning_note(self):
        html = render_components(
            _plan("diagram"),
            title="図",
            content={"diagram": {
                "nodes": [{"id": "a", "label": "はじめ"}],
                "edges": [{"from": "a", "to": "does-not-exist"}],
            }},
        )
        self.assertIn('class="dia-warn"', html)
        self.assertIn("見つからない", html)


class SvgImportTests(unittest.TestCase):
    def test_script_is_removed_and_noted(self):
        raw = (
            '<svg viewBox="0 0 100 60" xmlns="http://www.w3.org/2000/svg">'
            '<script>alert(1)</script><circle cx="10" cy="10" r="4"/></svg>'
        )
        html = render_components(
            _plan("details"),
            title="題",
            content={"details": [{"summary": "図", "svg": raw}]},
        )
        figure_start = html.find("<details>")
        figure = html[figure_start:html.find("</details>", figure_start)]
        self.assertNotIn("<script", figure)
        self.assertIn("<circle", figure)
        self.assertIn('class="dia-warn"', figure)
        self.assertIn("script", figure)

    def test_xlink_without_declared_namespace_still_renders(self):
        raw = (
            '<svg viewBox="0 0 40 40">'
            '<defs><path id="p1" d="M0 0 L40 40"/></defs>'
            '<use xlink:href="#p1"/></svg>'
        )
        html = render_components(
            _plan("details"),
            title="題",
            content={"details": [{"summary": "図", "svg": raw}]},
        )
        self.assertIn("<use", html)
        self.assertNotIn("xmlns", html)


@unittest.skipUnless(_PIL_AVAILABLE, "Pillow が無い＝試験用の画像を作れない")
class ImageBlockTests(unittest.TestCase):
    def test_image_embeds_and_feeds_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            png_path = Path(tmp) / "slide.png"
            _make_png(png_path)
            html = render_components(
                _plan("evidence", "details"),
                title="題",
                content={
                    "evidence": "実測：既存の根拠｜どこか",
                    "details": [{"summary": "画像", "image": {"path": str(png_path), "num": "1"}}],
                },
            )
            self.assertIn("data:image/", html)
            self.assertIn('data-zoom="1"', html)
            # B2＝画像の実測行が evidence 節の表へ足される。
            evidence_start = html.find('<section data-component="evidence"')
            evidence_end = html.find("</section>", evidence_start)
            self.assertGreaterEqual(evidence_start, 0)
            self.assertIn("画像＝", html[evidence_start:evidence_end])


class AuxiliaryFigureTests(unittest.TestCase):
    """③時間軸・四象限・集合・流れ・採点格子＝それぞれSVGが出る。"""

    def _svg_for(self, key, spec):
        html = render_components(
            _plan("details"), title="題", content={"details": [{"summary": "図", key: spec}]}
        )
        return html

    def test_timeline(self):
        html = self._svg_for("timeline", {"events": [{"when": "2026", "label": "開始"}]})
        self.assertIn('<svg class="tl"', html)

    def test_quadrant(self):
        html = self._svg_for("quadrant", {"items": [{"x": 0.2, "y": 0.8, "label": "A"}]})
        self.assertIn('<svg class="quad"', html)

    def test_venn(self):
        html = self._svg_for("venn", {"sets": [{"label": "A"}, {"label": "B"}]})
        self.assertIn('<svg class="venn"', html)

    def test_flow(self):
        html = self._svg_for(
            "flow", {"nodes": [{"id": "a"}, {"id": "b"}], "links": [{"from": "a", "to": "b", "value": 3}]}
        )
        self.assertIn('<svg class="flow"', html)

    def test_score(self):
        html = self._svg_for("score", {"axes": [{"name": "軸1", "level": 2}]})
        self.assertIn('<svg class="score"', html)


class CompareBlockTests(unittest.TestCase):
    def test_compare_has_two_panels_and_radios(self):
        html = render_components(
            _plan("details"),
            title="題",
            content={"details": [{"summary": "比較", "compare": {
                "before": "前の文章", "after": "後の文章", "labels": ["旧", "新"],
            }}]},
        )
        self.assertEqual(html.count("<input type=\"radio\""), 2)
        self.assertIn('class="compare-panel compare-before"', html)
        self.assertIn('class="compare-panel compare-after"', html)
        self.assertIn("前の文章", html)
        self.assertIn("後の文章", html)


class CalloutsBlockTests(unittest.TestCase):
    def test_callouts_lists_numbers(self):
        html = render_components(
            _plan("details"),
            title="題",
            content={"details": [{"summary": "凡例", "callouts": [
                {"n": 1, "text": "最初の注記"},
                {"n": 2, "text": "次の注記"},
            ]}]},
        )
        self.assertIn('class="callout-legend"', html)
        self.assertEqual(html.count('class="callout-item"'), 2)
        self.assertIn("最初の注記", html)


class DiagramTextTests(unittest.TestCase):
    def test_one_line_notation_makes_a_diagram(self):
        html = render_components(
            _plan("details"),
            title="題",
            content={"details": [{"summary": "図", "diagram_text": "A -> B : 条件" + NL + "A: 題 | 本文"}]},
        )
        self.assertIn("<svg", html)
        self.assertIn("marker-end=", html)
        self.assertIn("本文", html)


class TableHeatAndBarsTests(unittest.TestCase):
    def test_heat_column_uses_color_mix(self):
        html = render_components(
            _plan("table"),
            title="題",
            content={"table": {
                "head": ["項目", "値"],
                "rows": [["A", "10"], ["B", "90"]],
                "heat": [1],
            }},
        )
        self.assertIn("color-mix(in srgb", html)

    def test_bars_column_draws_a_bar(self):
        html = render_components(
            _plan("table"),
            title="題",
            content={"table": {
                "head": ["項目", "値"],
                "rows": [["A", "10"], ["B", "90"]],
                "bars": [1],
            }},
        )
        self.assertIn('class="cell-bar"', html)
        self.assertIn('class="cell-bar-fill"', html)


@unittest.skipUnless(_PIL_AVAILABLE, "Pillow が無い＝試験用の画像を作れない")
class NoExternalDependencyTests(unittest.TestCase):
    """出力全体に http・xmlns が無い（検品器が拒む形を混ぜない）。"""

    def test_everything_together_has_no_http_or_xmlns(self):
        with tempfile.TemporaryDirectory() as tmp:
            png_path = Path(tmp) / "slide.png"
            _make_png(png_path)
            html = render_components(
                _plan("overview", "summary", "walkthrough", "examples", "progress",
                      "visual", "decision", "evidence", "glossary", "details"),
                title="全部入り",
                content={
                    "overview": "概要。",
                    "summary": "Goal：確かめる。",
                    "walkthrough": "手順：やる。",
                    "examples": "例：これ。",
                    "progress": "現在：進行中。",
                    "visual": {"nodes": [{"id": "a", "label": "箱"}]},
                    "decision": {"options": ["案A"]},
                    "evidence": "実測：内容｜どこか",
                    "glossary": "語：説明",
                    "details": [
                        {"summary": "図の取り込み", "svg": '<svg viewBox="0 0 10 10">'
                                                         '<circle cx="5" cy="5" r="4"/></svg>'},
                        {"summary": "画像", "image": {"path": str(png_path)}},
                        {"summary": "時系列", "timeline": {"events": [{"label": "A"}]}},
                        {"summary": "比較", "compare": {"before": "前", "after": "後"}},
                        {"summary": "凡例", "callouts": [{"n": 1, "text": "注記"}]},
                        {"summary": "1行記法", "diagram_text": "A -> B"},
                        {"summary": "表", "table": {
                            "head": ["a", "b"], "rows": [["1", "2"]], "heat": [1], "bars": [1],
                        }},
                    ],
                },
            )
            self.assertFalse(_has_external_dependency(html))
            self.assertNotIn("xmlns", html)
            lowered = html.lower()
            self.assertNotIn("http://", lowered)
            self.assertNotIn("https://", lowered)


class GlossaryHoverInDiagramTests(unittest.TestCase):
    """⑦図の中の用語ホバー＝箱の題・本文に用語集の語があれば title と下線が付く。"""

    def test_box_with_glossary_term_gets_a_title_and_underline(self):
        entries = {
            "検品証": GlossaryEntry(term="検品証", description="機械が調べて残す記録", provenance="p")
        }
        html = render_components(
            _plan("diagram"),
            title="図",
            content={"diagram": {"nodes": [{"id": "a", "label": "検品証が残る"}]}},
            glossary_entries=entries,
        )
        self.assertIn("<title>検品証：機械が調べて残す記録</title>", html)
        self.assertIn("stroke-dasharray=\"2 3\"", html)


def _find_svg_style(html: str) -> str:
    """`<svg>` の中に書かれた `<style>` 全文を取り出す（頁全体のCSS）。"""
    start = html.find("<style>") + len("<style>")
    end = html.find("</style>", start)
    return html[start:end]


def _find_route_path(html: str) -> str:
    """辺の経路の `<path d="...">` の `d` 値だけを取り出す。

    ⚠️`<defs>` の矢じり用 `<path>`（塗りつぶし・`fill="none"` を持たない）と
    取り違えない＝辺の経路は必ず `fill="none"` を持つ。
    """
    cursor = 0
    while True:
        start = html.find('<path d="', cursor)
        if start < 0:
            raise AssertionError("辺の経路 <path> が見つからない：" + html[:200])
        tag_end = html.find(">", start)
        if 'fill="none"' in html[start:tag_end]:
            value_start = start + len('<path d="')
            value_end = html.find('"', value_start)
            return html[value_start:value_end]
        cursor = start + 1


class _FakeLayoutDiagram:
    """`layout_diagram` を差し替える偽物＝H2（diagram_layout.py）の実装を待たず、
    `_diagram_block_layout` の描画側だけを直接検査する（Routeを直に組み立てて渡す）。

    `max_width` など H2 が足す予定のキーワードもそのまま受け止める（**kwargs）＝
    実装前でも TypeError にならない、実装後もそのまま動く。
    """

    def __init__(self, layout: Layout) -> None:
        self.layout = layout
        self.calls: list[dict] = []

    def __call__(self, nodes, edges, *, max_cols=3, direction="auto", font_px=14, **kwargs):
        self.calls.append(
            {"max_cols": max_cols, "direction": direction, "font_px": font_px, **kwargs}
        )
        return self.layout


class DiagramLayoutMaxWidthWiringTests(unittest.TestCase):
    """①⚠️列幅（約720px）を超えた横スクロールの根治＝計算側に max_width=720 を渡す。"""

    def test_short_chain_viewbox_width_fits_the_column(self):
        # 短い題（1〜2文字）にする＝H2 の max_width 実装が無くても、鎖4箱が
        # 自然に720px以内へ収まる書き方で組む（実装のタイミングに依らず通る）。
        nodes = [{"id": "n%d" % i, "label": "箱%d" % i} for i in range(4)]
        edges = [{"from": "n%d" % i, "to": "n%d" % (i + 1)} for i in range(3)]
        html = render_components(
            _plan("diagram"), title="図", content={"diagram": {"nodes": nodes, "edges": edges}}
        )
        width, _height = _viewbox_dims(html)
        self.assertLessEqual(width, 720.0)

    def test_layout_diagram_is_called_with_max_width_720(self):
        fake = _FakeLayoutDiagram(
            Layout(width=200.0, height=80.0, boxes=[], routes=[], warnings=[])
        )
        original = rc.layout_diagram
        rc.layout_diagram = fake
        try:
            render_components(
                _plan("diagram"),
                title="図",
                content={"diagram": {
                    "nodes": [{"label": "はじめ"}, {"label": "つぎ"}],
                    "edges": [{"from": 0, "to": 1}],
                }},
            )
        finally:
            rc.layout_diagram = original
        self.assertEqual(len(fake.calls), 1)
        self.assertEqual(fake.calls[0].get("max_width"), 720)


class DiagramSvgWidthAndCssTests(unittest.TestCase):
    """②SVGは width 属性を持ち、CSS側は max-width:100%;height:auto で縮み方を決める。"""

    def test_svg_has_width_attribute_and_css_caps_it(self):
        html = render_components(
            _plan("diagram"),
            title="図",
            content={"diagram": {"nodes": [{"id": "a", "label": "箱"}]}},
        )
        svg_start = html.find('<svg class="dia"')
        svg_tag_end = html.find(">", svg_start)
        svg_open_tag = html[svg_start:svg_tag_end]
        self.assertIn("width=", svg_open_tag)
        css = _find_svg_style(html)
        self.assertIn(
            'svg.dia{display:block;max-width:100%;height:auto', css.replace(" ", "")
        )


class RouteControlPathTests(unittest.TestCase):
    """③④経路の描き方＝三次(4要素)のcontrolは`C`、制御点の無い折れ線は角を丸める。"""

    def _render_with_fake_route(self, route: Route) -> str:
        boxes = [
            Box(
                x=10.0, y=10.0, w=80.0, h=40.0,
                title_lines=["A"], body_lines=[], note_lines=[],
                num="", tone="neutral", icon="", node_index=0,
            ),
            Box(
                x=300.0, y=10.0, w=80.0, h=40.0,
                title_lines=["B"], body_lines=[], note_lines=[],
                num="", tone="neutral", icon="", node_index=1,
            ),
        ]
        layout = Layout(width=420.0, height=100.0, boxes=boxes, routes=[route], warnings=[])
        fake = _FakeLayoutDiagram(layout)
        original = rc.layout_diagram
        rc.layout_diagram = fake
        try:
            return render_components(
                _plan("diagram"),
                title="図",
                content={"diagram": {
                    "nodes": [{"label": "A"}, {"label": "B"}],
                    "edges": [{"from": 0, "to": 1}],
                }},
            )
        finally:
            rc.layout_diagram = original

    def test_cubic_four_element_control_draws_a_c_command(self):
        # 4要素＝((c1x,c1y),(c2x,c2y))。ネストの2点として来ても三次と読めるかを見る。
        route = Route(
            points=[(90.0, 30.0), (300.0, 30.0)],
            label="", label_x=195.0, label_y=30.0, kind="arrow",
            from_index=0, to_index=1,
            control=((150.0, -10.0), (250.0, 70.0)),
        )
        html = self._render_with_fake_route(route)
        path_d = _find_route_path(html)
        self.assertIn(" C ", path_d)

    def test_no_control_polyline_rounds_the_corner(self):
        # 制御点なし＝3点の折れ線（L字）。直角のLだけで終わらせず、角を丸める。
        route = Route(
            points=[(90.0, 30.0), (90.0, 90.0), (300.0, 90.0)],
            label="", label_x=195.0, label_y=90.0, kind="arrow",
            from_index=0, to_index=1,
            control=None,
        )
        html = self._render_with_fake_route(route)
        path_d = _find_route_path(html)
        self.assertIn(" Q ", path_d)
        self.assertNotEqual(path_d.count("L"), 0)  # 直線区間そのものは残る
        self.assertTrue(path_d.startswith("M "))


class DashedEdgeAndLabelStyleTests(unittest.TestCase):
    """⑤破線の辺は stroke-dasharray を持つ／⑥辺のラベルは白抜きの縁（paint-order）を持つ。"""

    def test_dashed_edge_has_stroke_dasharray(self):
        html = render_components(
            _plan("diagram"),
            title="図",
            content={"diagram": {
                "nodes": [{"id": "a", "label": "はじめ"}, {"id": "b", "label": "つぎ"}],
                "edges": [{"from": "a", "to": "b", "dashed": True}],
            }},
        )
        self.assertIn('stroke-dasharray="5 4"', html)

    def test_edge_label_has_paint_order_halo(self):
        html = render_components(
            _plan("diagram"),
            title="図",
            content={"diagram": {
                "nodes": [{"id": "a", "label": "はじめ"}, {"id": "b", "label": "つぎ"}],
                "edges": [{"from": "a", "to": "b", "label": "条件"}],
            }},
        )
        self.assertIn('paint-order="stroke"', html)
        self.assertIn("条件", html)


if __name__ == "__main__":
    unittest.main()

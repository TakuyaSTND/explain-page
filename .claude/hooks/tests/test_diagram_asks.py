"""図の箱の問いの番号の札（asks）の検査（2026-10-09・指摘と添削の作り込み）。

`diagram` の箱に `"asks": [1, 2]`（`1`・`"Q1"`・`"1/2"` も可）と書くと、箱の右上に赤い丸の「Q1」が付く。
押すと判断欄のその問い（`#q-1`）へ飛ぶ。1行記法でも `A(asks=1/2)` と書ける。

配置係（diagram_layout）は札の数だけ箱の幅を広げる＝題と札が重ならない。描画（render_components）は札を
箱の `<g>` の外・最前面に置く（箱の吹き出しの押下と混ざらない）。帯・軸・箱幅の強制を使う旧い図には
札を出せない＝黙って捨てず、図の下に1行知らせる。
ブラウザの試験は Playwright と node があるときだけ走る（無い環境では飛ばす）。
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HOOKS_DIR = Path(__file__).resolve().parents[1]
if str(HOOKS_DIR) not in sys.path:
    sys.path.insert(0, str(HOOKS_DIR))

from visual import diagram_layout as dl
from visual import visual_smoke
from visual.artifact_inspection import inspect_artifact_html
from visual.contracts import ExplanationPlan
from visual.diagram_dsl import parse_diagram_text
from visual.diagram_layout import layout_diagram
from visual.receipts import external_dependency_reason
from visual.render_components import DIA_Q_CSS, _question_numbers, render_components

DECISION = {
    "groups": [
        {"legend": "一つ目", "kind": "radio", "options": [{"label": "案A"}, {"label": "案B"}]},
        {"legend": "二つ目", "kind": "radio", "options": [{"label": "案C"}, {"label": "案D"}]},
        {"legend": "三つ目", "kind": "radio", "options": [{"label": "案E"}, {"label": "案F"}]},
    ]
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


def _page(diagram: dict | None = None, *, diagram_text: str | None = None, with_decision: bool = True) -> str:
    sections = []
    if diagram is not None:
        sections.append({"component": "visual", "label": "図で見る", "content": diagram})
    if diagram_text is not None:
        sections.append({"component": "visual", "label": "1行記法", "content": {"diagram_text": diagram_text}})
    if with_decision:
        sections.append({"component": "decision", "label": "選ぶこと", "content": DECISION})
    return render_components(_plan("visual", "decision"), title="札の見本", content={"sections": sections})


def _body(html: str) -> str:
    return html[html.index("<body>") : html.index("<script>")]


def _badges(html: str) -> list[int]:
    return [int(n) for n in re.findall(r'<a class="dia-q" href="#q-(\d+)"', html)]


# 長い題・記号・番号・中央揃え・英単語・札の数の違い（0〜3）を全部含む図。
RICH = {
    "nodes": [
        {"id": "a", "title": "とても長い題をもつ箱の見本です", "text": "本文が二行にわたる\nとても長い説明の文章", "asks": [1, 2, 3], "num": "①", "icon": "person"},
        {"id": "b", "title": "中央揃えの題の見本箱", "text": "中央に置く本文", "asks": "1/2", "align": "center"},
        {"id": "c", "title": "Short", "text": "x", "asks": 3},
        {"id": "d", "title": "札なし", "text": "札がない箱"},
        {"id": "e", "title": "English title which is long enough", "text": "body", "asks": ["Q1", "Q2"], "tone": "warn"},
    ],
    "edges": [
        {"from": "a", "to": "b", "label": "次へ"},
        {"from": "b", "to": "c"},
        {"from": "a", "to": "d"},
        {"from": "d", "to": "e"},
        {"from": "c", "to": "e"},
    ],
}


class QuestionNumbersTests(unittest.TestCase):
    def test_slash_separated_strings_give_several_numbers(self):
        self.assertEqual(_question_numbers("1/2"), [1, 2])
        self.assertEqual(_question_numbers("Q1/Q2"), [1, 2])
        self.assertEqual(_question_numbers(" 1 / 2 "), [1, 2])
        self.assertEqual(_question_numbers("1／3"), [1, 3])
        self.assertEqual(_question_numbers("1/x/3/0"), [1, 3])
        self.assertEqual(_question_numbers(["1/2", 2, "Q3"]), [1, 2, 3])

    def test_old_forms_still_work(self):
        self.assertEqual(_question_numbers([1, "1", "Q1", "q1"]), [1])
        self.assertEqual(_question_numbers(["Q3", 1, "2"]), [3, 1, 2])
        self.assertEqual(_question_numbers("x"), [])
        self.assertEqual(_question_numbers(None), [])
        self.assertEqual(_question_numbers(True), [])


class RenderTests(unittest.TestCase):
    def _badges_for(self, asks) -> list[int]:
        html = _page({"nodes": [{"id": "a", "title": "読む", "text": "開く", "asks": asks}, {"id": "b", "title": "指す", "text": "押す"}], "edges": [{"from": "a", "to": "b"}]})
        return _badges(_body(html))

    def test_every_way_of_writing_asks_gives_the_same_badges(self):
        self.assertEqual(self._badges_for([1, 2]), [1, 2])
        self.assertEqual(self._badges_for(1), [1])
        self.assertEqual(self._badges_for("Q1"), [1])
        self.assertEqual(self._badges_for("1/2"), [1, 2])
        # 札は番号の小さい順に左から並ぶ（書いた順ではない・2026-10-09 の撮影で直した）。
        self.assertEqual(self._badges_for(["Q2", 1]), [1, 2])
        self.assertEqual(self._badges_for([2, "2", "Q2"]), [2])

    def test_unreadable_asks_give_no_badge(self):
        for asks in (None, [], "", "x", [0, -1, True, "q", None, 1.5], {"a": 1}):
            self.assertEqual(self._badges_for(asks), [], repr(asks))

    def test_badges_are_spaced_by_the_width_the_layout_reserves_for_each(self):
        body = _body(self._page_with([1, 2, 3]))
        centers = [float(x) for x in re.findall(r'<circle class="dia-q-dot" cx="([0-9.]+)"', body)]

        self.assertEqual(len(centers), 3)
        # 左から Q1・Q2・Q3（DOM の順も同じ＝キーボードでも Q1 から）。
        self.assertAlmostEqual(centers[1] - centers[0], dl.Q_BADGE_W, places=1)
        self.assertAlmostEqual(centers[2] - centers[1], dl.Q_BADGE_W, places=1)

    def _page_with(self, asks) -> str:
        return _page({"nodes": [{"id": "a", "title": "読む", "text": "開く", "asks": asks}, {"id": "b", "title": "指す", "text": "押す"}], "edges": [{"from": "a", "to": "b"}]})

    def test_the_key_ask_is_accepted_too(self):
        html = _page({"nodes": [{"title": "読む", "text": "開く", "ask": 2}, {"title": "指す", "text": "押す"}], "edges": [{"from": 0, "to": 1}]})

        self.assertEqual(_badges(_body(html)), [2])

    def test_badge_markup_has_a_link_a_label_and_no_namespace(self):
        html = _page({"nodes": [{"id": "a", "title": "読む", "text": "開く", "asks": [1]}, {"id": "b", "title": "指す"}], "edges": [{"from": "a", "to": "b"}]})
        body = _body(html)

        self.assertIn('<a class="dia-q" href="#q-1" aria-label="Q1 へ移動"><title>Q1 へ移動</title>', body)
        self.assertIn('<circle class="dia-q-dot"', body)
        self.assertIn('stroke="var(--fail)"', body)
        self.assertIn(">Q1</text>", body)
        self.assertNotIn("w3.org", html)
        self.assertNotIn("xmlns", body)
        self.assertIsNone(external_dependency_reason(html))

    def test_badges_are_drawn_after_the_boxes_and_outside_the_hover_groups(self):
        diagram = {
            "nodes": [
                {"id": "a", "title": "読む", "text": "開く", "asks": [1], "hover": "説明"},
                {"id": "b", "title": "指す", "text": "押す"},
            ],
            "edges": [{"from": "a", "to": "b"}],
        }
        body = _body(_page(diagram))
        svg = body[body.index('<svg class="dia"') : body.index("</svg>", body.index('<svg class="dia"'))]

        self.assertLess(svg.rindex("<rect"), svg.index('<a class="dia-q"'))
        group_end = svg.index("</g>")
        self.assertGreater(svg.index('<a class="dia-q"'), group_end)
        self.assertNotIn("dia-q", svg[: svg.index("</g>")])

    def test_css_is_added_only_for_pages_with_badges(self):
        with_badge = _page({"nodes": [{"title": "読む", "asks": [1]}, {"title": "指す"}], "edges": [{"from": 0, "to": 1}]})
        without = _page({"nodes": [{"title": "読む"}, {"title": "指す"}], "edges": [{"from": 0, "to": 1}]})

        self.assertIn(DIA_Q_CSS, with_badge)
        self.assertNotIn(".dia-q", without)
        for forbidden in ("#", "rgb(", "rgba(", "hsl("):
            self.assertNotIn(forbidden, DIA_Q_CSS, forbidden)

    def test_the_page_with_badges_passes_the_gate(self):
        html = _page(RICH)
        inspection = inspect_artifact_html(html, required_components=("visual", "decision"), glossary_entries={})

        self.assertEqual(inspection.errors, ())
        self.assertTrue(inspection.ok, inspection)

    def test_each_badge_links_to_an_existing_question(self):
        html = _page(RICH)

        for number in set(_badges(_body(html))):
            self.assertIn('<fieldset id="q-%d">' % number, html)


class OneLineNotationTests(unittest.TestCase):
    TEXT = "A: 読む | 頁を開く\nB: 指す | 単位を押す\nC: 直す | 文を書く\nA -> B -> C\nA(asks=1/2)\nB(asks=3)\nC[asks=1]"

    def test_the_parser_passes_the_attribute_through(self):
        parsed = parse_diagram_text(self.TEXT)
        by_id = {node["id"]: node for node in parsed["nodes"]}

        self.assertEqual(by_id["A"]["asks"], "1/2")
        self.assertEqual(by_id["B"]["asks"], "3")
        self.assertEqual(by_id["C"]["asks"], "1")
        self.assertEqual(parsed["warnings"], [])

    def test_the_renderer_draws_a_badge_per_number(self):
        html = _page(diagram_text=self.TEXT)

        # 箱 A＝Q1・Q2、箱 B＝Q3、箱 C＝Q1（箱の並び順）。
        self.assertEqual(_badges(_body(html)), [1, 2, 3, 1])

    def test_a_single_number_and_the_long_attribute_list_work(self):
        html = _page(diagram_text="A: 読む\nB: 指す\nA -> B\nA(asks=2, tone=warn)\nB(icon=person, asks=1)")

        self.assertEqual(_badges(_body(html)), [2, 1])


class LayoutTests(unittest.TestCase):
    def test_boxes_carry_their_asks_and_grow_by_the_badge_width(self):
        plain = [{"title": "読む", "text": "開く"}, {"title": "指す", "text": "押す"}]
        marked = [dict(plain[0], asks=[1, 2]), dict(plain[1], asks=[3])]
        edges = [{"from": 0, "to": 1}]

        base = layout_diagram(plain, edges, max_width=720)
        with_asks = layout_diagram(marked, edges, max_width=720)

        self.assertEqual([b.asks for b in base.boxes], [[], []])
        self.assertEqual([b.asks for b in with_asks.boxes], [[1, 2], [3]])
        # 層の箱の幅は最小幅（160）で揃うので、札を足しても小さい箱の幅は変わらない＝はみ出さない。
        for b0, b1 in zip(base.boxes, with_asks.boxes):
            self.assertGreaterEqual(b1.w, b0.w)

    def test_without_the_layered_engine_the_box_grows_by_exactly_the_badges(self):
        nodes = [{"title": "題の文字は十字ほどある", "text": "開く"}]  # 最小幅（64px）に引っかからない長さ
        grown = layout_diagram([dict(nodes[0], asks=[1, 2, 3])], [])
        base = layout_diagram(nodes, [])

        self.assertAlmostEqual(grown.boxes[0].w - base.boxes[0].w, 3 * dl.Q_BADGE_W, places=3)
        centered = layout_diagram([dict(nodes[0], asks=[1, 2], align="center")], [])
        self.assertAlmostEqual(centered.boxes[0].w - base.boxes[0].w, 2 * 2 * dl.Q_BADGE_W, places=3)

    def test_no_asks_means_the_layout_is_unchanged(self):
        nodes = [{"title": "読む", "text": "開く"}, {"title": "指す", "text": "押す"}]
        edges = [{"from": 0, "to": 1, "label": "押す"}]
        a = layout_diagram(nodes, edges, max_width=720)
        b = layout_diagram([dict(n, asks=[]) for n in nodes], edges, max_width=720)

        self.assertEqual([(x.x, x.y, x.w, x.h) for x in a.boxes], [(x.x, x.y, x.w, x.h) for x in b.boxes])
        self.assertEqual((a.width, a.height), (b.width, b.height))

    def test_the_estimated_title_never_reaches_the_badges(self):
        # 札は箱の右端から内側へ 24px ずつ（直径 20px）。左端の札の左の縁＝x + w - 22 - 24 * (n - 1)。
        for max_width in (None, 720):
            layout = layout_diagram(RICH["nodes"], RICH["edges"], max_width=max_width)
            for box in layout.boxes:
                asks = [n for n in box.asks]
                if not asks:
                    continue
                badge_left = box.x + box.w - 22 - dl.Q_BADGE_W * (len(asks) - 1)
                title_px = max((dl._line_em_width(line) * 14 for line in box.title_lines), default=0)
                indent = dl.ICON_INDENT if box.icon else 0.0
                if box.num:
                    indent += dl._line_em_width(box.num) * 14 + 8
                title_right = box.x + dl.PAD_X + indent + title_px
                if box.title_lines:
                    self.assertLessEqual(title_right, badge_left + 0.5, (max_width, box.title_lines, asks))

    def test_a_narrow_cap_refolds_the_title_and_still_keeps_clear_of_the_badges(self):
        nodes = [{"title": "とてもとても長い題をもつ箱の見本の文章です" * 2, "text": "本文", "asks": [1, 2, 3]}, {"title": "次", "text": "x"}]
        layout = layout_diagram(nodes, [{"from": 0, "to": 1}], max_width=720)
        box = layout.boxes[0]
        badge_left = box.x + box.w - 22 - dl.Q_BADGE_W * 2
        title_px = max(dl._line_em_width(line) * 14 for line in box.title_lines)

        self.assertLessEqual(box.w, dl.LAYERED_MAX_BOX_W + 0.5)
        self.assertLessEqual(box.x + dl.PAD_X + title_px, badge_left + 0.5)

    def test_bad_asks_are_ignored_by_the_layout(self):
        layout = layout_diagram([{"title": "読む", "asks": [0, -2, True, "1", None, 2.5, 3, 3]}], [])

        self.assertEqual(layout.boxes[0].asks, [3])


class LegacyDiagramTests(unittest.TestCase):
    def test_legacy_diagram_draws_no_badge_and_says_so(self):
        for key, extra in (("box_width", 160), ("bands", [{"col": 0, "label": "帯", "w": 150}])):
            diagram = {"nodes": [{"title": "読む", "col": 0, "row": 0, "asks": [1]}, {"title": "指す", "col": 1, "row": 0}], "edges": [{"from": 0, "to": 1}], key: extra}
            html = _page(diagram)
            body = _body(html)

            self.assertEqual(_badges(body), [], key)
            self.assertIn("箱の asks（Q 番号の札）は、帯・軸・箱幅を使う図では出せない", body, key)
            self.assertNotIn(".dia-q", html.split("</style>")[0], key)

    def test_legacy_diagram_without_asks_has_no_warning(self):
        diagram = {"nodes": [{"title": "読む", "col": 0, "row": 0}, {"title": "指す", "col": 1, "row": 0}], "edges": [{"from": 0, "to": 1}], "box_width": 160}

        self.assertNotIn("asks", _body(_page(diagram)))


_RUNNER = r"""
const { pathToFileURL } = require('url');
const { chromium } = require(process.argv[1]);
const htmlPath = process.argv[2];
const ops = JSON.parse(process.argv[3]);
(async () => {
  let browser;
  try {
    browser = await chromium.launch({headless:true});
  } catch (error) {
    console.log(JSON.stringify({skip:String(error).slice(0,200)}));
    return;
  }
  try {
    const page = await browser.newPage({viewport:{width:1280,height:900}});
    const errors = [];
    page.on('pageerror', e => errors.push(String(e).slice(0,200)));
    await page.goto(pathToFileURL(htmlPath).href, {waitUntil:'load', timeout:8000});
    const out = [];
    for (const op of ops) {
      if (op.eval !== undefined) out.push(await page.evaluate(op.eval));
      else if (op.viewport) { await page.setViewportSize({width: op.viewport[0], height: op.viewport[1]}); out.push(null); }
      else if (op.click) { await page.locator(op.click).nth(op.nth || 0).click(); out.push(null); }
    }
    console.log(JSON.stringify({out, errors}));
  } finally {
    await browser.close();
  }
})().catch(error => { console.log(JSON.stringify({fail:String(error).slice(0,300)})); process.exitCode = 1; });
"""


def _run(html: str, ops: list[dict]) -> dict:
    playwright_path, reason = visual_smoke._resolve_playwright()
    if not playwright_path or not shutil.which("node"):
        raise unittest.SkipTest("Playwright か node が無い: %s" % (reason or ""))
    with tempfile.TemporaryDirectory(prefix="diagram_asks_") as tmp:
        page_path = Path(tmp) / "page.html"
        page_path.write_text(html, encoding="utf-8")
        completed = subprocess.run(
            ["node", "-e", _RUNNER, str(playwright_path), str(page_path), json.dumps(ops)],
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=90,
            check=False,
        )
    try:
        result = json.loads(completed.stdout.strip().splitlines()[-1])
    except (IndexError, ValueError):
        raise AssertionError("browser run gave no JSON: %r %r" % (completed.stdout[-300:], completed.stderr[-300:]))
    if "skip" in result:
        raise unittest.SkipTest("ブラウザを起動できない: %s" % result["skip"])
    if "fail" in result:
        raise AssertionError(result["fail"])
    return result


# 実際の字形で、札の丸が箱の文字（題・本文・注記）と重ならないか・箱の中に収まるか・札どうしが重ならないかを測る。
_GEOMETRY_JS = """
(() => {
  const svg = document.querySelector('svg.dia');
  const rects = [...svg.querySelectorAll('rect')].map(r => r.getBBox());
  const texts = [...svg.querySelectorAll('text')].filter(t => !t.closest('a.dia-q')).map(t => ({b: t.getBBox(), s: t.textContent}));
  const dots = [...svg.querySelectorAll('a.dia-q .dia-q-dot')].map(d => d.getBBox());
  const hit = (a, b) => a.x < b.x + b.width && b.x < a.x + a.width && a.y < b.y + b.height && b.y < a.y + a.height;
  const overlapsText = dots.map((d, i) => texts.filter(t => hit(d, t.b)).map(t => t.s));
  const inBox = dots.map(d => rects.some(r => d.x >= r.x - 0.5 && d.y >= r.y - 0.5 && d.x + d.width <= r.x + r.width + 0.5 && d.y + d.height <= r.y + r.height + 0.5));
  let dotOverlap = 0;
  for (let i = 0; i < dots.length; i++) for (let j = i + 1; j < dots.length; j++) if (hit(dots[i], dots[j])) dotOverlap++;
  const textOutside = texts.filter(t => !rects.some(r => t.b.x >= r.x - 1 && t.b.x + t.b.width <= r.x + r.width + 1 && t.b.y >= r.y - 1 && t.b.y + t.b.height <= r.y + r.height + 1) && t.s.length > 0).map(t => t.s);
  return {count: dots.length, overlapsText, inBox, dotOverlap, textOutside};
})()
"""


class BrowserTests(unittest.TestCase):
    def test_badges_do_not_touch_the_box_text_and_stay_inside_their_box(self):
        result = _run(_page(RICH), [{"eval": _GEOMETRY_JS}])

        geometry = result["out"][0]
        self.assertEqual(result["errors"], [])
        self.assertEqual(geometry["count"], 3 + 2 + 1 + 2)
        self.assertEqual(geometry["overlapsText"], [[]] * geometry["count"])
        self.assertTrue(all(geometry["inBox"]), geometry["inBox"])
        self.assertEqual(geometry["dotOverlap"], 0)

    def test_the_one_line_notation_badges_are_clear_of_the_text_too(self):
        result = _run(_page(diagram_text=OneLineNotationTests.TEXT), [{"eval": _GEOMETRY_JS}])

        geometry = result["out"][0]
        self.assertEqual(geometry["count"], 4)
        self.assertEqual(geometry["overlapsText"], [[]] * 4)
        self.assertEqual(geometry["dotOverlap"], 0)

    def test_clicking_a_badge_jumps_to_the_question(self):
        result = _run(
            _page(RICH),
            [
                {"eval": "[...document.querySelectorAll('a.dia-q')].map(a => a.getAttribute('href'))"},
                {"click": "a.dia-q[href='#q-2']", "nth": 0},
                {"eval": "location.hash"},
                {"eval": "document.querySelector('fieldset:target') && document.querySelector('fieldset:target').id"},
            ],
        )

        self.assertEqual(result["errors"], [])
        self.assertIn("#q-1", result["out"][0])
        self.assertEqual(result["out"][2], "#q-2")
        self.assertEqual(result["out"][3], "q-2")

    def test_a_badge_can_take_keyboard_focus(self):
        result = _run(
            _page(RICH),
            [{"eval": "(() => { const a = document.querySelector('a.dia-q'); a.focus(); return document.activeElement === a; })()"}],
        )

        self.assertTrue(result["out"][0])

    def test_the_badge_stays_readable_on_a_phone(self):
        result = _run(
            _page(RICH),
            [
                {"viewport": [390, 844]},
                {"eval": "(() => { const d = document.querySelector('a.dia-q .dia-q-dot').getBoundingClientRect(); return {w: d.width, h: d.height}; })()"},
                {"eval": "document.documentElement.scrollWidth - document.documentElement.clientWidth"},
            ],
        )

        size = result["out"][1]
        self.assertGreaterEqual(size["w"], 16)
        self.assertGreaterEqual(size["h"], 16)
        # 図は自分の枠の中で横にだけ動く＝頁全体は横にはみ出さない。
        self.assertEqual(result["out"][2], 0)


if __name__ == "__main__":
    unittest.main()

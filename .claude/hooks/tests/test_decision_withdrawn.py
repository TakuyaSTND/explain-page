"""取り下げた選択肢（withdrawn）の検査（2026-10-09・指摘と添削の作り込み）。

選択肢の辞書に `"withdrawn": true` か `"withdrawn": "理由"` を書くと、その案は <input> の無い
`<div class="choice withdrawn" data-withdrawn="1">` になる。案の文は取り消し線で残り、「取り下げ」の札と
理由が付く。選べず、`data-req` が無いので推奨のまとめ選択・入力の消去・見た判定・回答文のどれにも出ない。
選べる行が1つも無い問い（全部取り下げ）は問いの番号を取らない（回答文の Q 番号と同じ規則）。

ブラウザの試験は Playwright と node があるときだけ走る（無い環境では飛ばす）。
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HOOKS_DIR = Path(__file__).resolve().parents[1]
if str(HOOKS_DIR) not in sys.path:
    sys.path.insert(0, str(HOOKS_DIR))

from visual import visual_smoke
from visual.artifact_inspection import inspect_artifact_html
from visual.contracts import ExplanationPlan
from visual.render_components import WITHDRAWN_CSS, _withdrawn_info, render_components

SVG = '<svg viewBox="0 0 40 20"><rect x="1" y="1" width="30" height="14" fill="#c33"/></svg>'
UNSEEN_REC = "(見ていない＝推奨で進めるが、大事なら会話で確かめる)"
UNSEEN_NOREC = "(見ていない・推奨なし＝会話で確かめる)"


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


def _page(groups: list[dict], title: str = "取り下げの見本") -> str:
    return render_components(_plan("decision"), title=title, content={"decision": {"groups": groups}})


def _group(legend: str = "配置はどれにするか", options: list | None = None, kind: str = "radio") -> dict:
    return {
        "legend": legend,
        "kind": kind,
        "options": options
        if options is not None
        else [
            {"label": "案A", "recommended": True, "pros": "安い", "cons": "狭い"},
            {"label": "案B", "withdrawn": "案Aと見分けがつかなかった", "pros": "確実", "thumb": {"svg": SVG, "alt": "絵"}},
            {"label": "案C", "withdrawn": True, "recommended": True},
        ],
    }


class WithdrawnInfoTests(unittest.TestCase):
    def test_true_and_reason_strings_withdraw(self):
        self.assertEqual(_withdrawn_info(True), (True, ""))
        self.assertEqual(_withdrawn_info("理由です"), (True, "理由です"))
        self.assertEqual(_withdrawn_info("  理由です  "), (True, "理由です"))
        self.assertEqual(_withdrawn_info("true"), (True, ""))
        self.assertEqual(_withdrawn_info(1), (True, ""))

    def test_false_like_values_do_not_withdraw(self):
        for value in (None, False, "", "  ", "false", "False", "0", "no", "off", 0):
            self.assertEqual(_withdrawn_info(value), (False, ""), repr(value))


class MarkupTests(unittest.TestCase):
    def test_withdrawn_option_has_no_input_and_no_request_markers(self):
        html = _page([_group()])
        start = html.index('<div class="choice withdrawn')
        end = html.index("</fieldset>", start)
        withdrawn_part = html[start:end]

        self.assertEqual(withdrawn_part.count('data-withdrawn="1"'), 2)
        self.assertNotIn("<input", withdrawn_part.replace('<input type="text" class="q-note"', ""))
        self.assertNotIn("data-req", withdrawn_part)
        self.assertNotIn("data-rec", withdrawn_part)
        self.assertNotIn("recommendation", withdrawn_part)
        # 生きている案は今までどおり（script の中にも同じ語があるので、頁の本文だけを数える）。
        body = html.split("<script>")[0]
        self.assertEqual(body.count('data-req="1"'), 1)
        self.assertEqual(body.count('data-rec="1"'), 1)

    def test_withdrawn_option_keeps_the_text_struck_through_with_badge_and_reason(self):
        html = _page([_group()])

        self.assertIn('<span class="badge b-bad">取り下げ</span> <s>案B</s>', html)
        self.assertIn('<span class="why wd-reason">取り下げの理由：案Aと見分けがつかなかった</span>', html)
        self.assertIn('<b class="pro">利点</b> 確実', html)
        self.assertIn("<s>案C</s>", html)
        self.assertEqual(html.count("取り下げの理由："), 1)  # 案C は理由なし

    def test_withdrawn_option_keeps_its_thumb_beside_the_text(self):
        html = _page([_group()])
        start = html.index('<div class="choice withdrawn has-thumb"')
        part = html[start : html.index("</div>", start)]

        self.assertIn('<span class="thumb">', part)
        self.assertLess(part.index("案B"), part.index('<span class="thumb">'))

    def test_false_like_values_render_a_normal_choice(self):
        html = _page([_group(options=[{"label": "案A", "withdrawn": False}, {"label": "案B", "withdrawn": "false"}])])

        self.assertNotIn("withdrawn", html.split("</style>")[1])
        self.assertEqual(html.count('data-req="1"'), 2)

    def test_checkbox_group_withdraws_too(self):
        html = _page([_group(kind="checkbox", options=[{"label": "X"}, {"label": "Y", "withdrawn": True}])])

        self.assertEqual(html.count('type="checkbox" name="decision"'), 1)
        self.assertIn("<s>Y</s>", html)

    def test_all_withdrawn_group_is_not_a_question(self):
        html = _page(
            [
                _group(legend="全部取り下げ", options=[{"label": "案A", "withdrawn": True}, {"label": "案B", "withdrawn": "x"}]),
                _group(legend="生きた問い", options=[{"label": "案C"}, {"label": "案D"}]),
            ]
        )

        self.assertEqual(html.count('class="q-note"'), 1)
        self.assertEqual(html.count('<fieldset id="q-'), 1)
        self.assertIn('<fieldset id="q-1"><legend><span class="q-no">Q1</span>生きた問い', html)
        self.assertNotIn("Q2", html.split("</style>")[1].split("<script>")[0])

    def test_partly_withdrawn_group_keeps_its_number_and_note(self):
        html = _page([_group(), _group(legend="次の問い", options=[{"label": "案E"}, {"label": "案F"}])])

        self.assertIn('<fieldset id="q-1"><legend><span class="q-no">Q1</span>配置はどれにするか', html)
        self.assertIn('<fieldset id="q-2"><legend><span class="q-no">Q2</span>次の問い', html)
        self.assertEqual(html.count('class="q-note"'), 2)

    def test_css_is_added_only_for_pages_that_use_it(self):
        with_withdrawn = _page([_group()])
        without = _page([_group(options=[{"label": "案A"}, {"label": "案B"}])])

        self.assertIn(WITHDRAWN_CSS, with_withdrawn)
        self.assertNotIn(".choice.withdrawn", without)
        self.assertIn("grayscale", WITHDRAWN_CSS)
        self.assertIn("dashed", WITHDRAWN_CSS)

    def test_withdrawn_css_uses_only_tokens_for_colors(self):
        # 明暗どちらでも読めるよう、色は var(--…) のトークンだけ（固定色を書かない）。
        for forbidden in ("#", "rgb(", "rgba(", "hsl("):
            self.assertNotIn(forbidden, WITHDRAWN_CSS, forbidden)

    def test_page_with_withdrawn_options_passes_the_gate(self):
        inspection = inspect_artifact_html(
            _page([_group()]), required_components=("decision",), glossary_entries={}
        )

        self.assertEqual(inspection.errors, ())
        self.assertEqual(inspection.missing_decision_parts, ())
        self.assertTrue(inspection.ok)


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
      else if (op.scheme) { await page.emulateMedia({colorScheme: op.scheme}); out.push(null); }
      else if (op.click) { await page.locator(op.click).nth(op.nth || 0).click(); out.push(null); }
      else if (op.jsclick) { await page.locator(op.jsclick).nth(op.nth || 0).evaluate(el => el.click()); out.push(null); }
      else if (op.check) { await page.locator(op.check).nth(op.nth || 0).check(); out.push(null); }
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
    with tempfile.TemporaryDirectory(prefix="withdrawn_") as tmp:
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


_CONTRAST_JS = """
(() => {
  const lin = v => { v /= 255; return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4); };
  const lum = css => { const [r, g, b] = css.match(/[\\d.]+/g).slice(0, 3).map(Number).map(lin); return 0.2126 * r + 0.7152 * g + 0.0722 * b; };
  const ratio = (a, b) => { const x = lum(a), y = lum(b); return (Math.max(x, y) + 0.05) / (Math.min(x, y) + 0.05); };
  const bg = getComputedStyle(document.body).backgroundColor;
  const pick = sel => { const el = document.querySelector(sel); return ratio(getComputedStyle(el).color, bg); };
  return {
    label: pick('.choice.withdrawn s'),
    reason: pick('.choice.withdrawn .wd-reason'),
    marker: pick('.choice.withdrawn .wd-x'),
    proscons: pick('.choice.withdrawn .pros-cons'),
  };
})()
"""


class BrowserTests(unittest.TestCase):
    def test_withdrawn_options_are_not_controls_and_never_reach_the_reply(self):
        result = _run(
            _page([_group(), _group(legend="次の問い", options=[{"label": "案E", "recommended": True}, {"label": "案F"}])]),
            [
                {"eval": "document.querySelectorAll('.choice.withdrawn input, .choice.withdrawn [data-req]').length"},
                {"eval": "document.querySelectorAll('[data-req]').length"},
                {"eval": "document.getElementById('decision-prompt').textContent"},
                {"click": "#recommend-decision"},
                {"eval": "document.getElementById('decision-prompt').textContent"},
                {"jsclick": ".choice.withdrawn", "nth": 0},
                {"eval": "document.getElementById('decision-prompt').textContent"},
                {"click": "#forget-decision"},
                {"eval": "document.getElementById('decision-prompt').textContent"},
            ],
        )

        self.assertEqual(result["errors"], [])
        self.assertEqual(result["out"][0], 0)
        self.assertEqual(result["out"][1], 3)  # 生きた選択肢だけ＝案A・案E・案F
        initial = result["out"][2].split("\n")
        # 問いは2つ（取り下げは数えない）＝Q1・Q2 の行だけ。
        self.assertEqual(initial[1], "Q1. 配置はどれにするか: " + UNSEEN_REC)
        self.assertEqual(initial[2], "Q2. 次の問い: " + UNSEEN_REC)
        self.assertTrue(all("案B" not in line and "案C" not in line for line in initial))
        # 推奨のまとめ選択は、取り下げた案C（recommended:true と書いた）を選ばない。
        recommended = result["out"][4].split("\n")
        self.assertEqual(recommended[1], "Q1. 配置はどれにするか: 案A")
        self.assertEqual(recommended[2], "Q2. 次の問い: 案E")
        self.assertTrue(all("案B" not in line and "案C" not in line for line in recommended))
        # 取り下げた案を押しても何も変わらない。
        self.assertEqual(result["out"][6], result["out"][4])
        # 入力の消去で元に戻る。
        self.assertEqual(result["out"][8].split("\n")[1], "Q1. 配置はどれにするか: " + UNSEEN_REC)

    def test_all_withdrawn_group_does_not_appear_in_the_reply_either(self):
        result = _run(
            _page(
                [
                    _group(legend="全部取り下げ", options=[{"label": "案A", "withdrawn": True}, {"label": "案B", "withdrawn": "x"}]),
                    _group(legend="生きた問い", options=[{"label": "案C"}, {"label": "案D"}]),
                ]
            ),
            [{"eval": "document.getElementById('decision-prompt').textContent"}],
        )

        lines = result["out"][0].split("\n")
        self.assertEqual(lines[1], "Q1. 生きた問い: " + UNSEEN_NOREC)
        self.assertFalse(any("全部取り下げ" in line for line in lines))
        self.assertEqual(result["errors"], [])

    def test_withdrawn_option_is_drawn_struck_through_dashed_and_readable_in_both_schemes(self):
        for scheme in ("light", "dark"):
            result = _run(
                _page([_group()]),
                [
                    {"scheme": scheme},
                    {
                        "eval": "(() => { const box = document.querySelector('.choice.withdrawn');"
                        " const s = box.querySelector('s'); const thumb = box.querySelector('.thumb');"
                        " return {line: getComputedStyle(s).textDecorationLine, border: getComputedStyle(box).borderStyle,"
                        " cursor: getComputedStyle(box).cursor, filter: thumb ? getComputedStyle(thumb).filter : ''}; })()"
                    },
                    {"eval": _CONTRAST_JS},
                ],
            )

            style, contrast = result["out"][1], result["out"][2]
            self.assertIn("line-through", style["line"], scheme)
            self.assertEqual(style["border"], "dashed", scheme)
            self.assertEqual(style["cursor"], "default", scheme)
            self.assertIn("grayscale", style["filter"], scheme)
            # 案の文と理由は本文並みに読める（4.5 以上）。補助の文字（利点・マーク）は 3 以上。
            self.assertGreaterEqual(contrast["label"], 4.5, (scheme, contrast))
            self.assertGreaterEqual(contrast["reason"], 4.5, (scheme, contrast))
            self.assertGreaterEqual(contrast["proscons"], 4.0, (scheme, contrast))
            self.assertGreaterEqual(contrast["marker"], 3.0, (scheme, contrast))
            self.assertEqual(result["errors"], [])


if __name__ == "__main__":
    unittest.main()

"""案のカード自身の「これを選ぶ」枠の検査（2026-10-19・利用者の指摘）。

何を守るか＝
  ・案のカード（proposals）の番号で始まる判断欄の選択肢には、カードの側にも枠（label for）が付く。
    枠は判断欄の同じ入力を指すので、押すと判断欄の選択と回答文がそのまま変わる（script は足さない）。
  ・選んだ印は :has() で入力の状態から出す。明暗どちらでも読める（色はトークンだけ）。
  ・番号に合う選択肢が無い・取り下げた選択肢・カードに pick:false のときは、枠を付けない。
  ・id は英数字・「-」「_」だけ（CSS の選び方に使うため）。
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

from visual import page_lint as pl
from visual import visual_smoke
from visual.contracts import ExplanationPlan
from visual.render_components import _pick_css, _safe_pick_id, render_components

SVG = '<svg viewBox="0 0 40 20"><rect x="1" y="1" width="30" height="14" fill="#c33"/></svg>'


def _plan() -> ExplanationPlan:
    return ExplanationPlan(
        audience="project_novice",
        depth="deep",
        components=("examples", "decision"),
        reason_codes=(),
        provisional=False,
        should_continue=False,
        delivery="local_html",
        publish_policy="never",
    )


def _cards():
    return [
        {"no": "R1", "title": "全文を保存する", "recommended": True, "claim": "説明1", "pros": "安全", "cons": "手間", "exhibit": {"svg": SVG}},
        {"no": "R2", "title": "規則へ移す", "claim": "説明2", "pros": "軽い", "cons": "付かない場面", "exhibit": {"svg": SVG}},
        {"no": "R3", "title": "取り下げる案", "claim": "説明3", "pros": "x", "cons": "y", "exhibit": {"svg": SVG}},
    ]


def _content(options=None, cards=None, groups=None):
    options = options if options is not None else [{"label": "R1"}, {"label": "R2"}]
    return {
        "sections": [
            {"component": "examples", "label": "案", "content": [{"proposals": cards if cards is not None else _cards()}]},
            {
                "component": "decision",
                "label": "判断",
                "content": {
                    "groups": groups
                    if groups is not None
                    else [{"legend": "作る案", "kind": "checkbox", "options": options}]
                },
            },
        ]
    }


def _render(content) -> str:
    linked, _notes = pl.link_proposals(content)
    return render_components(_plan(), title="選ぶ枠の見本", content=linked)


class LinkTests(unittest.TestCase):
    def test_matched_option_and_card_share_one_id_and_the_question_number(self):
        new, notes = pl.link_proposals(_content())
        options = new["sections"][1]["content"]["groups"][0]["options"]
        cards = new["sections"][0]["content"][0]["proposals"]

        self.assertEqual(options[0]["pick_id"], "pk-R1")
        self.assertEqual(options[1]["pick_id"], "pk-R2")
        self.assertEqual((cards[0]["pick"], cards[0]["pick_q"]), ("pk-R1", 1))
        self.assertEqual((cards[1]["pick"], cards[1]["pick_q"]), ("pk-R2", 1))
        self.assertNotIn("pick", cards[2])  # 結ぶ選択肢が無いカードには付けない
        self.assertTrue(any("「これを選ぶ」枠" in line for line in notes))

    def test_question_number_skips_free_groups_and_counts_earlier_live_ones(self):
        groups = [
            {"legend": "自由記述", "kind": "free"},
            {"legend": "先の問い", "kind": "radio", "options": [{"label": "A"}, {"label": "B"}]},
            {"legend": "作る案", "kind": "checkbox", "options": [{"label": "R1"}]},
        ]
        new, _ = pl.link_proposals(_content(groups=groups))
        self.assertEqual(new["sections"][0]["content"][0]["proposals"][0]["pick_q"], 2)

    def test_a_card_can_opt_out_and_withdrawn_options_get_no_frame(self):
        cards = _cards()
        cards[0]["pick"] = False
        options = [{"label": "R1"}, {"label": "R2", "withdrawn": "前の版で取り下げた"}]
        new, _ = pl.link_proposals(_content(options=options, cards=cards))
        got = new["sections"][0]["content"][0]["proposals"]

        self.assertIs(got[0]["pick"], False)
        self.assertNotIn("pick", got[1])
        self.assertNotIn("pick_id", new["sections"][1]["content"]["groups"][0]["options"][0])
        self.assertNotIn("pick_id", new["sections"][1]["content"]["groups"][0]["options"][1])

    def test_only_the_first_option_with_the_same_number_is_linked(self):
        groups = [
            {"legend": "案", "kind": "checkbox", "options": [{"label": "R1 先"}, {"label": "R1 後"}]},
        ]
        new, _ = pl.link_proposals(_content(groups=groups))
        options = new["sections"][1]["content"]["groups"][0]["options"]
        self.assertEqual(options[0]["pick_id"], "pk-R1")
        self.assertNotIn("pick_id", options[1])

    def test_idempotent_and_does_not_change_the_input(self):
        content = _content()
        before = json.dumps(content, ensure_ascii=False, sort_keys=True)
        once, _ = pl.link_proposals(content)
        twice, notes = pl.link_proposals(once)

        self.assertEqual(json.dumps(content, ensure_ascii=False, sort_keys=True), before)
        self.assertEqual(once, twice)
        self.assertEqual(notes, [])

    def test_a_writers_own_pick_id_is_kept(self):
        new, _ = pl.link_proposals(_content(options=[{"label": "R1", "pick_id": "mine"}, {"label": "R2"}]))
        options = new["sections"][1]["content"]["groups"][0]["options"]
        self.assertEqual(options[0]["pick_id"], "mine")


class MarkupTests(unittest.TestCase):
    def test_card_gets_a_label_that_points_at_the_decision_input(self):
        html = _render(_content())

        self.assertIn('<label class="prop-pick" for="pk-R1">', html)
        self.assertIn('<label class="prop-pick" for="pk-R2">', html)
        self.assertEqual(html.count('class="prop-pick"'), 2)  # R3 は結ぶ先が無い
        self.assertIn('name="decision" id="pk-R1" data-req="1"', html)
        self.assertIn('name="decision" id="pk-R2" data-req="1"', html)
        self.assertIn("判断欄 Q1 と同じ選択", html)
        self.assertIn("☐ これを選ぶ", html)
        self.assertIn("☑ 選んだ", html)
        # 選んだ印は入力の状態から出す（頁ごとに1本ずつ）
        self.assertIn("body:has(#pk-R1:checked) label.prop-pick", html)
        self.assertIn('.prop:has(label[for="pk-R2"])', html)
        # 枠のための script は足さない（判断欄の script は共通の1本のまま）
        self.assertEqual(html.count("<script>"), 2)  # 判断欄と表示の script（2026-10-31）の2本

    def test_without_a_link_there_is_no_frame_and_no_extra_rule(self):
        html = render_components(_plan(), title="見本", content=_content(options=[{"label": "別の案"}, {"label": "もう1つ"}]))

        self.assertNotIn('class="prop-pick" for=', html)
        self.assertNotIn("body:has(#pk-", html)

    def test_only_safe_ids_are_used(self):
        self.assertEqual(_safe_pick_id("pk-R1"), "pk-R1")
        for bad in ("a b", 'x"y', "x]y", "", None, False, "z" * 41, "日本語"):
            self.assertEqual(_safe_pick_id(bad), "", repr(bad))
        self.assertEqual(_pick_css('<label class="prop-pick" for="pk-Z9">'), _pick_css('<label class="prop-pick" for="pk-Z9">'))
        self.assertEqual(_pick_css('<label class="prop-pick" for="a b">'), "")

    def test_selected_look_uses_tokens_only(self):
        css = _pick_css('<label class="prop-pick" for="pk-R1">')
        for forbidden in ("#fff", "#000", "rgb(", "white", "black"):
            self.assertNotIn(forbidden, css, forbidden)
        self.assertIn("var(--on-accent)", css)


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
      else if (op.uncheck) { await page.locator(op.uncheck).nth(op.nth || 0).uncheck(); out.push(null); }
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
    with tempfile.TemporaryDirectory(prefix="pick_") as tmp:
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


_STATE = """
(() => {
  const lab = document.querySelector('label.prop-pick[for="pk-R1"]');
  return {
    checked: document.getElementById('pk-R1').checked,
    off: getComputedStyle(lab.querySelector('.pk-off')).display,
    on: getComputedStyle(lab.querySelector('.pk-on')).display,
    prompt: document.getElementById('decision-prompt').textContent,
  };
})()
"""


class BrowserTests(unittest.TestCase):
    def test_pressing_the_card_frame_selects_the_same_option_in_the_decision_form(self):
        result = _run(
            _render(_content()),
            [
                {"eval": _STATE},
                {"click": 'label.prop-pick[for="pk-R1"]'},
                {"eval": _STATE},
                {"uncheck": "#pk-R1"},
                {"eval": _STATE},
                {"click": 'label.prop-pick[for="pk-R1"]'},
                {"click": "#forget-decision"},
                {"eval": _STATE},
            ],
        )
        before, picked, unpicked, forgotten = (result["out"][i] for i in (0, 2, 4, 7))

        self.assertEqual(result["errors"], [])
        self.assertFalse(before["checked"])
        self.assertEqual((before["off"] != "none", before["on"] != "none"), (True, False))
        self.assertTrue(picked["checked"])
        self.assertEqual((picked["off"] != "none", picked["on"] != "none"), (False, True))
        self.assertIn("全文を保存する", picked["prompt"])  # 選んだ案が、貼り返す回答文に入る
        self.assertFalse(unpicked["checked"])
        self.assertEqual((unpicked["off"] != "none", unpicked["on"] != "none"), (True, False))
        self.assertNotIn("全文を保存する", unpicked["prompt"])
        self.assertFalse(forgotten["checked"])  # 「入力を消す」で、枠の印も戻る
        self.assertEqual((forgotten["off"] != "none", forgotten["on"] != "none"), (True, False))

    def test_recommended_bulk_select_marks_the_recommended_card(self):
        result = _run(
            _render(_content()),
            [
                {"click": "#recommend-decision"},
                {"eval": "[...document.querySelectorAll('label.prop-pick')].map(l => [l.getAttribute('for'), getComputedStyle(l.querySelector('.pk-on')).display !== 'none'])"},
            ],
        )
        self.assertEqual(result["out"][1], [["pk-R1", True], ["pk-R2", False]])

    def test_selected_frame_is_readable_in_light_and_dark(self):
        contrast = """
        (() => {
          const lin = v => { v /= 255; return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4); };
          const lum = css => { const [r, g, b] = css.match(/[0-9.]+/g).slice(0, 3).map(Number).map(lin); return 0.2126 * r + 0.7152 * g + 0.0722 * b; };
          const lab = document.querySelector('label.prop-pick[for="pk-R1"]');
          const s = getComputedStyle(lab);
          const x = lum(s.color), y = lum(s.backgroundColor);
          return (Math.max(x, y) + 0.05) / (Math.min(x, y) + 0.05);
        })()
        """
        result = _run(
            _render(_content()),
            [
                {"scheme": "light"},
                {"click": 'label.prop-pick[for="pk-R1"]'},
                {"eval": contrast},
                {"scheme": "dark"},
                {"eval": contrast},
            ],
        )
        self.assertGreaterEqual(result["out"][2], 4.5)
        self.assertGreaterEqual(result["out"][4], 4.5)


if __name__ == "__main__":
    unittest.main()

"""指摘と添削の画面（visual/review_scripts.py）を本物のブラウザで動かす検査（2026-10-09）。

頁は試験が自分で組む：単位（data-blk）を持つ最小の頁に、契約どおりの window.pageReply の代用
（判断欄の script が作る本物の窓口と同じ形）を1本目に置き、そのあとに指摘・添削の script と CSS を並べる。
判断欄の本物の script と組み合わせる統合の試験は最後の1本（window.pageReply が無い版では飛ばす）。

確かめること：
  指摘…単位を押して札とひとことを付ける／文字をなぞって引用する／再読み込みで戻り「入力を消す」で消える／
        判断欄の無い頁の「貼り付ける文章を作る」が全文を出す／原稿の頁では最初から入っていて原稿のブロックだけが的
  添削…説明の頁で単位を直す・消す・段落を足す／原稿の頁で直す・足す・消す・完成形・差分・ソース全体
  共通…帯の切り替えが排他／Esc で切れる／390px で板・引き出し・編集欄を開いても横にはみ出さない
どの試験も、頁の script が投げた例外（pageerror）と console の error が0であることを確かめる。

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

from visual import review_scripts as rs
from visual import visual_smoke

try:
    from visual import markdown_lite
except ImportError:  # 原稿の頁の部品が無い環境
    markdown_lite = None  # type: ignore[assignment]

CLOSING = "上の回答を反映して作業を続けてください。お任せの項目は推奨案で確定してください。"

_TOKENS = (
    ":root{--ground:#F5F3EC;--surface:#FDFCF8;--surface-2:#F0EDE2;--ink:#242B33;--ink-2:#5B6470;--ink-3:#646B73;"
    "--on-accent:#FFFFFF;--rule:#D9D3C4;--rule-soft:#E7E2D6;--accent:#2F5D8A;--accent-2:#234869;--accent-soft:#E3ECF4;"
    "--pass:#2C774B;--fail:#A63A42;--fail-soft:#F6E2E3;--warn:#8E610E}"
    "@media(prefers-color-scheme:dark){:root:not([data-theme=\"light\"]){--ground:#14171C;--surface:#1C2128;"
    "--surface-2:#23272E;--ink:#E9E6DE;--ink-2:#9AA3AD;--ink-3:#88909A;--on-accent:#14171C;--rule:#363D47;"
    "--rule-soft:#2A303A;--accent:#85AED6;--accent-2:#A9C7E6;--accent-soft:#243447;--pass:#6CC092;--fail:#E18A90;"
    "--fail-soft:#452227;--warn:#D8A84E}}"
)
_BASE_CSS = _TOKENS + (
    "*{box-sizing:border-box}body{margin:0;background:var(--ground);color:var(--ink);font:16px/1.8 system-ui,sans-serif}"
    ".wrap{max-width:56rem;margin:0 auto;padding:2rem 1.1rem 5rem;display:flex;flex-direction:column;gap:1.5rem}"
    "section{display:flex;flex-direction:column;gap:.95rem}p{margin:0}"
    ".card{background:var(--surface);border:1px solid var(--rule);border-left:3px solid var(--accent);padding:.9rem 1.05rem}"
    ".scroll{overflow-x:auto;border:1px solid var(--rule)}table{border-collapse:collapse;width:100%}"
    "th,td{padding:.55rem .7rem;text-align:left}"
    "button{min-height:44px;padding:.65rem 1rem;border:1px solid var(--accent-2);background:var(--accent);color:var(--on-accent)}"
    "ol.steps{list-style:none;margin:0;padding:0;display:flex;flex-direction:column;gap:.7rem}"
    "ol.steps li{display:grid;grid-template-columns:1.9rem 1fr;gap:.85rem;border:1px solid var(--rule);padding:.85rem 1rem}"
    "ul.bullets{margin:0;padding-left:1.2rem;display:flex;flex-direction:column;gap:.3rem}"
    "pre{margin:0;white-space:pre-wrap;overflow-wrap:anywhere}"
    ".ms{display:flex;flex-direction:column;gap:.5rem}.ms-blk{min-width:0;overflow-wrap:anywhere}.ms-blk[hidden]{display:none}"
)

# window.pageReply の代用（判断欄の script が作る本物と同じ契約）。
_REPLY_STUB = r"""window.pageReply={extras:[],compose:function(){const L=['【頁の回答】'+document.title,'自由記述: (なし)'];
[['shiteki','## 指摘'],['tensaku','## 添削']].forEach(r=>{const ls=[];this.extras.filter(e=>e.role===r[0]).forEach(e=>e.lines().forEach(l=>ls.push(l)));if(ls.length){L.push(r[1]);ls.forEach(l=>L.push(l));}});
L.push('---');L.push('上の回答を反映して作業を続けてください。お任せの項目は推奨案で確定してください。');return L;},
rebuild:function(){const p=document.getElementById('decision-prompt');if(p)p.textContent=this.compose().join('\n');},
copy:function(){}};
const f=document.getElementById('forget-decision');if(f)f.addEventListener('click',()=>{window.pageReply.extras.forEach(e=>e.forget());window.pageReply.rebuild();});
window.pageReply.rebuild();"""

_UNITS = (
    '<section data-component="summary"><h2>要点</h2>'
    '<div class="card" data-blk="1"><h3>案A</h3><p>安くて速いが、後から直しにくい。</p></div>'
    '<p class="body-copy" data-blk="2">本文の段落です。ここをなぞって引用できます。二つ目の文もあります。</p>'
    '<div class="scroll"><table><thead><tr><th>項目</th><th>値</th></tr></thead><tbody>'
    '<tr data-blk="3"><td>速度</td><td>速い</td></tr><tr data-blk="4"><td>費用</td><td>安い</td></tr></tbody></table></div>'
    '<ol class="steps"><li data-blk="5"><div><b>手順1</b><p>まず準備する。</p></div></li>'
    '<li data-blk="6"><div><b>手順2</b><p>次に実行する。</p></div></li></ol>'
    '<ul class="bullets"><li data-blk="7">箇条書きの一つ目</li><li data-blk="8">箇条書きの二つ目</li></ul>'
    "</section>"
)
_DECISION = (
    '<section data-component="decision"><h2>選ぶこと</h2><pre id="decision-prompt"></pre>'
    '<button id="forget-decision" type="button">入力を消す</button></section>'
)

_MD = """# 小さな記事

導入の段落です。[公式の案内](https://example.com/guide)を読んでください。

## 手順

```bash
set -euo pipefail
echo "https://example.com/run"
```

| 項目 | 値 |
| --- | --- |
| 速度 | 速い |
| 費用 | 安い |

> 引用の文です。

<!-- meta: note -->

最後の段落です。
"""

_OVERFLOW = "(()=>({sw:document.documentElement.scrollWidth,iw:innerWidth}))()"
_PROMPT = "document.getElementById('decision-prompt').textContent"


def _page(body: str = _UNITS + _DECISION, title: str = "指摘の見本", roles=("shiteki", "tensaku"), reply: bool = True) -> str:
    scripts = ([_REPLY_STUB] if reply else []) + [rs.ROLE_SCRIPTS[role] for role in roles]
    return (
        '<!doctype html><html lang="ja"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        "<title>%s</title><style>%s%s</style></head><body><div class=\"wrap\">%s</div>%s</body></html>"
        % (title, _BASE_CSS, rs.review_css(roles), body, "".join("<script>%s</script>" % s for s in scripts))
    )


def _manuscript_page(mode: str, md: str = _MD, roles=None, extra: str = "") -> str:
    section = (
        '<section data-component="manuscript" data-review-mode="%s"><h2>原稿</h2>%s%s</section>'
        % (
            mode,
            markdown_lite.render_markdown(md),
            markdown_lite.source_textarea(md, label="intro-01", path="docs/intro.md", sha="abcdef12", eol="lf"),
        )
    )
    return _page(body=extra + section + _DECISION, title="原稿の見本", roles=roles or (mode,))


_RUNNER = r"""
const { pathToFileURL } = require('url');
const { chromium } = require(process.argv[1]);
const htmlPath = process.argv[2];
const steps = JSON.parse(require('fs').readFileSync(process.argv[3], 'utf8'));
const opts = JSON.parse(process.argv[4] || '{}');
(async () => {
  let browser;
  try { browser = await chromium.launch({headless:true}); }
  catch (error) { console.log(JSON.stringify({skip:String(error).slice(0,200)})); return; }
  try {
    const ctx = await browser.newContext({viewport:{width:opts.width||1280,height:opts.height||900}, colorScheme: opts.scheme||'light'});
    const page = await ctx.newPage();
    const errors = [];
    page.on('pageerror', e => errors.push(String(e).slice(0,300)));
    page.on('console', m => { if (m.type() === 'error') errors.push('console: ' + m.text().slice(0,200)); });
    page.on('dialog', d => d.accept());
    await page.goto(pathToFileURL(htmlPath).href, {waitUntil:'load', timeout:8000});
    const out = {};
    for (const step of steps) {
      const loc = step.sel ? page.locator(step.sel).nth(step.nth || 0) : null;
      if (step.op === 'click') await loc.click({timeout: 4000});
      else if (step.op === 'fill') await loc.fill(step.value);
      else if (step.op === 'press') { if (loc) await loc.press(step.key); else await page.keyboard.press(step.key); }
      else if (step.op === 'reload') await page.reload({waitUntil:'load'});
      else if (step.op === 'wait') await page.waitForTimeout(step.ms || 100);
      else if (step.op === 'select') {
        await loc.evaluate((el, n) => { const t = el.firstChild; const s = t.nodeValue.indexOf(n); const r = document.createRange(); r.setStart(t, s); r.setEnd(t, s + n.length); const sel = getSelection(); sel.removeAllRanges(); sel.addRange(r); }, step.value);
      }
      else if (step.op === 'eval') out[step.as] = await page.evaluate(step.js);
      else if (step.op === 'shot') await page.screenshot({path: step.path, fullPage: !!step.full});
    }
    out.errors = errors;
    console.log(JSON.stringify(out));
  } finally { await browser.close(); }
})().catch(error => { console.log(JSON.stringify({fail:String(error).slice(0,400)})); process.exitCode = 1; });
"""


def _run(html: str, steps: list[dict], width: int = 1280, height: int = 900, scheme: str = "light") -> dict:
    playwright_path, reason = visual_smoke._resolve_playwright()
    if not playwright_path or not shutil.which("node"):
        raise unittest.SkipTest("Playwright か node が無い: %s" % (reason or ""))
    with tempfile.TemporaryDirectory(prefix="review_browser_") as tmp:
        page_path = Path(tmp) / "page.html"
        steps_path = Path(tmp) / "steps.json"
        page_path.write_text(html, encoding="utf-8")
        steps_path.write_text(json.dumps(steps, ensure_ascii=False), encoding="utf-8")
        completed = subprocess.run(
            [
                "node",
                "-e",
                _RUNNER,
                str(playwright_path),
                str(page_path),
                str(steps_path),
                json.dumps({"width": width, "height": height, "scheme": scheme}),
            ],
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


def _lines(text: str) -> list[str]:
    return text.split("\n")


class _BrowserCase(unittest.TestCase):
    def assertClean(self, result: dict) -> None:
        self.assertEqual(result["errors"], [], result["errors"])


class ShitekiBrowserTests(_BrowserCase):
    def test_pressing_a_unit_with_a_chip_and_a_note_writes_the_fixed_line(self):
        steps = [
            {"op": "eval", "as": "bar0", "js": "document.getElementById('rv-bar').innerText.replace(/\\s+/g,' ')"},
            {"op": "click", "sel": "#rv-shiteki"},
            {"op": "eval", "as": "mode", "js": "document.body.dataset.rv"},
            {"op": "click", "sel": ".card"},
            {"op": "eval", "as": "target", "js": "document.querySelector('.rv-target').textContent"},
            {"op": "eval", "as": "chips", "js": "[...document.querySelectorAll('.rv-chip')].map(b=>b.textContent)"},
            {"op": "click", "sel": ".rv-chip", "nth": 1},
            {"op": "fill", "sel": ".rv-sheet textarea", "value": "ひとこと"},
            {"op": "click", "sel": ".rv-sheet .rv-main"},
            {"op": "eval", "as": "prompt", "js": _PROMPT},
            {"op": "eval", "as": "pin", "js": "document.querySelector('.card').getAttribute('data-rv-p')"},
            {"op": "eval", "as": "count", "js": "document.getElementById('rv-s-count').innerText"},
            {"op": "eval", "as": "sheet_hidden", "js": "document.querySelector('.rv-sheet').hidden"},
        ]
        result = _run(_page(), steps)

        self.assertClean(result)
        self.assertIn("指摘する", result["bar0"])
        self.assertEqual(result["mode"], "shiteki")
        self.assertTrue(result["target"].startswith("#1 "))
        self.assertIn("案A", result["target"])
        self.assertEqual(result["chips"], list(rs.CHIPS))
        lines = _lines(result["prompt"])
        self.assertEqual(lines[0], "【頁の回答】指摘の見本")
        self.assertEqual(lines[lines.index("## 指摘") + 1], "#1 [短くする] ひとこと")
        self.assertEqual(lines[-2:], ["---", CLOSING])
        self.assertEqual(result["pin"], "#1")
        self.assertEqual(result["count"], "指摘 1 件")
        self.assertTrue(result["sheet_hidden"])

    def test_nothing_happens_when_the_mode_is_not_on(self):
        steps = [
            {"op": "click", "sel": ".card"},
            {"op": "eval", "as": "sheet_hidden", "js": "document.querySelector('.rv-sheet').hidden"},
            {"op": "eval", "as": "tabindex", "js": "document.querySelectorAll('[data-rv-tab]').length"},
        ]
        result = _run(_page(), steps)

        self.assertClean(result)
        self.assertTrue(result["sheet_hidden"])
        self.assertEqual(result["tabindex"], 0)

    def test_a_chip_alone_is_a_line_and_an_empty_save_is_refused(self):
        steps = [
            {"op": "click", "sel": "#rv-shiteki"},
            {"op": "click", "sel": "tr[data-blk='3']"},
            {"op": "click", "sel": ".rv-sheet .rv-main"},
            {"op": "eval", "as": "msg", "js": "document.querySelector('.rv-msg').textContent"},
            {"op": "click", "sel": ".rv-chip", "nth": 6},
            {"op": "click", "sel": ".rv-sheet .rv-main"},
            {"op": "eval", "as": "prompt", "js": _PROMPT},
            {"op": "eval", "as": "pin", "js": "document.querySelector('tr[data-blk=\"3\"] td').getAttribute('data-rv-p')"},
        ]
        result = _run(_page(), steps)

        self.assertClean(result)
        self.assertIn("札を選ぶか", result["msg"])
        self.assertIn("#3 [ここは良い]", _lines(result["prompt"]))
        self.assertEqual(result["pin"], "#3")  # 表の行の印は先頭のセルに置く

    def test_selecting_text_quotes_it_up_to_forty_characters(self):
        steps = [
            {"op": "click", "sel": "#rv-shiteki"},
            {"op": "select", "sel": "p.body-copy", "value": "ここをなぞって引用できます"},
            {"op": "wait", "ms": 300},
            {"op": "eval", "as": "visible", "js": "!document.querySelector('.rv-sel').hidden"},
            {"op": "click", "sel": ".rv-sel"},
            {"op": "eval", "as": "target", "js": "document.querySelector('.rv-target').textContent"},
            {"op": "click", "sel": ".rv-chip", "nth": 3},
            {"op": "click", "sel": ".rv-sheet .rv-main"},
            {"op": "eval", "as": "prompt", "js": _PROMPT},
        ]
        result = _run(_page(), steps)

        self.assertClean(result)
        self.assertTrue(result["visible"])
        self.assertIn("選択", result["target"])
        self.assertIn("#2 [事実を確認] 「ここをなぞって引用できます」", _lines(result["prompt"]))

    def test_a_long_selection_is_cut_at_forty_characters_with_an_ellipsis(self):
        long_text = "あ" * 60
        body = _UNITS.replace("本文の段落です。ここをなぞって引用できます。二つ目の文もあります。", long_text) + _DECISION
        steps = [
            {"op": "click", "sel": "#rv-shiteki"},
            {"op": "select", "sel": "p.body-copy", "value": long_text},
            {"op": "wait", "ms": 300},
            {"op": "click", "sel": ".rv-sel"},
            {"op": "click", "sel": ".rv-chip", "nth": 0},
            {"op": "click", "sel": ".rv-sheet .rv-main"},
            {"op": "eval", "as": "prompt", "js": _PROMPT},
        ]
        result = _run(_page(body=body), steps)

        self.assertClean(result)
        self.assertIn("#2 [削る] 「" + "あ" * 40 + "…」", _lines(result["prompt"]))

    def test_marks_survive_a_reload_and_the_forget_button_clears_them(self):
        steps = [
            {"op": "click", "sel": "#rv-shiteki"},
            {"op": "click", "sel": ".card"},
            {"op": "click", "sel": ".rv-chip", "nth": 0},
            {"op": "fill", "sel": ".rv-sheet textarea", "value": "削りたい"},
            {"op": "click", "sel": ".rv-sheet .rv-main"},
            {"op": "reload"},
            {"op": "eval", "as": "after_reload", "js": _PROMPT},
            {"op": "eval", "as": "pin", "js": "document.querySelector('.card').getAttribute('data-rv-p')"},
            {"op": "eval", "as": "mode", "js": "document.body.dataset.rv||''"},
            {"op": "click", "sel": "#forget-decision"},
            {"op": "eval", "as": "after_forget", "js": _PROMPT},
            {"op": "eval", "as": "pin_after", "js": "document.querySelector('.card').hasAttribute('data-rv-p')"},
            {"op": "reload"},
            {"op": "eval", "as": "after_forget_reload", "js": _PROMPT},
        ]
        result = _run(_page(), steps)

        self.assertClean(result)
        self.assertIn("#1 [削る] 削りたい", _lines(result["after_reload"]))
        self.assertEqual(result["pin"], "#1")
        self.assertEqual(result["mode"], "")  # 入れたままにはしない（読むために押した所で板が開かない）
        self.assertNotIn("## 指摘", result["after_forget"])
        self.assertFalse(result["pin_after"])
        self.assertNotIn("## 指摘", result["after_forget_reload"])

    def test_marks_made_on_another_version_of_the_page_are_dropped_not_misapplied(self):
        # 同じ題で組み直した頁（番号の指す中身が変わった）に、前の頁の赤を載せない。
        scramble = (
            "(()=>{const k='uc-shiteki:'+document.title;const o=JSON.parse(localStorage.getItem(k));"
            "o.annos.forEach(a=>{a.g='別の中身'});localStorage.setItem(k,JSON.stringify(o));})()"
        )
        steps = [
            {"op": "click", "sel": "#rv-shiteki"},
            {"op": "click", "sel": ".card"},
            {"op": "click", "sel": ".rv-chip", "nth": 0},
            {"op": "click", "sel": ".rv-sheet .rv-main"},
            {"op": "eval", "as": "saved", "js": "localStorage.getItem('uc-shiteki:'+document.title).length>0"},
            {"op": "eval", "as": "scrambled", "js": scramble},
            {"op": "reload"},
            {"op": "eval", "as": "prompt", "js": _PROMPT},
            {"op": "eval", "as": "pin", "js": "document.querySelectorAll('[data-rv-p]').length"},
        ]
        result = _run(_page(), steps)

        self.assertClean(result)
        self.assertTrue(result["saved"])
        self.assertNotIn("## 指摘", result["prompt"])
        self.assertEqual(result["pin"], 0)

    def test_editing_and_deleting_from_the_list_drawer(self):
        steps = [
            {"op": "click", "sel": "#rv-shiteki"},
            {"op": "click", "sel": ".card"},
            {"op": "click", "sel": ".rv-chip", "nth": 0},
            {"op": "click", "sel": ".rv-sheet .rv-main"},
            {"op": "click", "sel": "p.body-copy"},
            {"op": "click", "sel": ".rv-chip", "nth": 1},
            {"op": "click", "sel": ".rv-sheet .rv-main"},
            {"op": "click", "sel": "#rv-s-count"},
            {"op": "eval", "as": "items", "js": "document.querySelectorAll('.rv-drawer .rv-item').length"},
            {"op": "click", "sel": ".rv-drawer .rv-item .rv-link", "nth": 2},
            {"op": "eval", "as": "after_delete", "js": _PROMPT},
            {"op": "eval", "as": "items2", "js": "document.querySelectorAll('.rv-drawer .rv-item').length"},
        ]
        result = _run(_page(), steps)

        self.assertClean(result)
        self.assertEqual(result["items"], 2)
        self.assertEqual(result["items2"], 1)
        lines = _lines(result["after_delete"])
        self.assertNotIn("#1 [削る]", lines)
        self.assertIn("#2 [短くする]", lines)

    def test_a_page_without_a_decision_prompt_has_a_compose_button_that_shows_the_whole_text(self):
        steps = [
            {"op": "eval", "as": "has_prompt", "js": "!!document.getElementById('decision-prompt')"},
            {"op": "click", "sel": "#rv-shiteki"},
            {"op": "click", "sel": ".card"},
            {"op": "click", "sel": ".rv-chip", "nth": 2},
            {"op": "fill", "sel": ".rv-sheet textarea", "value": "言い換えたい"},
            {"op": "click", "sel": ".rv-sheet .rv-main"},
            {"op": "eval", "as": "buttons", "js": "[...document.querySelectorAll('button')].filter(b=>b.textContent==='貼り付ける文章を作る'&&b.getClientRects().length>0).length"},
            {"op": "click", "sel": "#rv-compose"},
            {"op": "eval", "as": "text", "js": "document.querySelector('#rv-out textarea').value"},
            {"op": "eval", "as": "readonly", "js": "document.querySelector('#rv-out textarea').readOnly"},
            {"op": "click", "sel": "#rv-s-count"},
            {"op": "eval", "as": "drawer_buttons", "js": "[...document.querySelectorAll('.rv-drawer button')].filter(b=>b.textContent==='貼り付ける文章を作る'&&b.getClientRects().length>0).length"},
        ]
        result = _run(_page(body=_UNITS), steps)

        self.assertClean(result)
        self.assertFalse(result["has_prompt"])
        self.assertEqual(result["buttons"], 1)  # 指摘と添削の両方の script が載っても釦は1つ
        lines = _lines(result["text"])
        self.assertEqual(lines[0], "【頁の回答】指摘の見本")
        self.assertIn("#1 [言い換える] 言い換えたい", lines)
        self.assertEqual(lines[-2:], ["---", CLOSING])
        self.assertTrue(result["readonly"])
        self.assertEqual(result["drawer_buttons"], 1)

    def test_the_output_panel_follows_changes_while_it_is_open(self):
        steps = [
            {"op": "click", "sel": "#rv-shiteki"},
            {"op": "click", "sel": ".card"},
            {"op": "click", "sel": ".rv-chip", "nth": 0},
            {"op": "click", "sel": ".rv-sheet .rv-main"},
            {"op": "click", "sel": "#rv-compose"},
            {"op": "eval", "as": "first", "js": "document.querySelector('#rv-out textarea').value"},
            {"op": "eval", "as": "second", "js": "(()=>{document.querySelector('p.body-copy').click();document.querySelectorAll('.rv-chip')[1].click();document.querySelector('.rv-sheet .rv-main').click();return document.querySelector('#rv-out textarea').value})()"},
            {"op": "press", "key": "Escape"},
            {"op": "eval", "as": "out_hidden", "js": "document.getElementById('rv-out').hidden+'|'+document.body.dataset.rv"},
            {"op": "press", "key": "Escape"},
            {"op": "eval", "as": "mode_after", "js": "document.body.dataset.rv||''"},
        ]
        result = _run(_page(body=_UNITS), steps)

        self.assertClean(result)
        self.assertIn("#1 [削る]", _lines(result["first"]))
        self.assertNotIn("#2 [短くする]", _lines(result["first"]))
        self.assertIn("#2 [短くする]", _lines(result["second"]))  # 開いている間に付けた指摘が、欄の文に追い付く
        self.assertEqual(result["out_hidden"], "true|shiteki")  # 出力の欄を閉じる Esc は、赤ペンの状態を切らない
        self.assertEqual(result["mode_after"], "")

    def test_a_tensaku_only_page_without_a_decision_prompt_still_has_its_compose_button(self):
        steps = [
            {"op": "click", "sel": "#rv-tensaku"},
            {"op": "click", "sel": "p.body-copy"},
            {"op": "fill", "sel": ".rv-ed textarea", "value": "直した本文"},
            {"op": "click", "sel": ".rv-ed .rv-main"},
            {"op": "eval", "as": "buttons", "js": "[...document.querySelectorAll('button')].filter(b=>b.textContent==='貼り付ける文章を作る'&&b.getClientRects().length>0).length"},
            {"op": "click", "sel": "#rv-compose"},
            {"op": "eval", "as": "text", "js": "document.querySelector('#rv-out textarea').value"},
        ]
        result = _run(_page(body=_UNITS, roles=("tensaku",)), steps)

        self.assertClean(result)
        self.assertEqual(result["buttons"], 1)
        self.assertIn("## 添削", _lines(result["text"]))
        self.assertTrue(any(line.startswith("- 段落 2: ") for line in _lines(result["text"])))


@unittest.skipUnless(markdown_lite is not None, "markdown_lite が無い")
class ManuscriptShitekiBrowserTests(_BrowserCase):
    def test_a_manuscript_page_is_on_from_the_start_and_only_its_blocks_are_targets(self):
        extra = '<div class="card" id="outside">原稿の外のカード</div>'
        steps = [
            {"op": "eval", "as": "toggle", "js": "!!document.getElementById('rv-shiteki')"},
            {"op": "click", "sel": "#outside"},
            {"op": "eval", "as": "outside_open", "js": "!document.querySelector('.rv-sheet').hidden"},
            {"op": "click", "sel": ".ms-blk[data-ms='2']"},
            {"op": "eval", "as": "target", "js": "document.querySelector('.rv-target').textContent"},
            {"op": "click", "sel": ".rv-chip", "nth": 1},
            {"op": "fill", "sel": ".rv-sheet textarea", "value": "短く"},
            {"op": "click", "sel": ".rv-sheet .rv-main"},
            {"op": "eval", "as": "prompt", "js": _PROMPT},
            {"op": "eval", "as": "units", "js": "[...document.querySelectorAll('[data-blk]')].map(e=>e.dataset.blk).join(',')"},
        ]
        result = _run(_manuscript_page("shiteki", extra=extra), steps)

        self.assertClean(result)
        self.assertFalse(result["toggle"])  # 最初から入っているので切り替えの釦は無い
        self.assertFalse(result["outside_open"])
        self.assertTrue(result["target"].startswith("#2 "))
        self.assertIn("#2 [短くする] 短く", _lines(result["prompt"]))
        self.assertEqual(result["units"], "1,2,3,4,5,6,7,8")

    def test_escape_does_not_turn_off_a_manuscript_page(self):
        steps = [
            {"op": "press", "key": "Escape"},
            {"op": "click", "sel": ".ms-blk[data-ms='1']"},
            {"op": "eval", "as": "open", "js": "!document.querySelector('.rv-sheet').hidden"},
        ]
        result = _run(_manuscript_page("shiteki"), steps)

        self.assertClean(result)
        self.assertTrue(result["open"])


class TensakuPageBrowserTests(_BrowserCase):
    def test_editing_deleting_and_adding_on_an_explanation_page(self):
        steps = [
            {"op": "click", "sel": "#rv-tensaku"},
            {"op": "click", "sel": ".card"},
            {"op": "eval", "as": "initial", "js": "document.querySelector('.rv-ed textarea').value"},
            {"op": "fill", "sel": ".rv-ed textarea", "value": "案A 安くて速いが、後から直しにくい。要注意。"},
            {"op": "eval", "as": "live_diff", "js": "document.querySelector('.rv-ed .rv-diff ins')?document.querySelector('.rv-ed .rv-diff ins').textContent:''"},
            {"op": "click", "sel": ".rv-ed .rv-main"},
            {"op": "eval", "as": "mark", "js": "document.querySelector('.card').getAttribute('data-rv-t')"},
            {"op": "click", "sel": "tr[data-blk='3']"},
            {"op": "click", "sel": ".rv-ed .rv-danger"},
            {"op": "eval", "as": "row_mark", "js": "document.querySelector('tr[data-blk=\"3\"]').getAttribute('data-rv-t')"},
            {"op": "click", "sel": "ol.steps li", "nth": 0},
            {"op": "click", "sel": ".rv-ed .rv-btn", "nth": 2},
            {"op": "fill", "sel": ".rv-ed textarea", "value": "手順1の後に足す段落"},
            {"op": "click", "sel": ".rv-ed .rv-main"},
            {"op": "eval", "as": "prompt", "js": _PROMPT},
            {"op": "eval", "as": "count", "js": "document.getElementById('rv-t-count').innerText"},
            {"op": "eval", "as": "li_tags", "js": "[...document.querySelectorAll('ol.steps > li')].length"},
        ]
        result = _run(_page(), steps)

        self.assertClean(result)
        self.assertEqual(result["initial"], "案A 安くて速いが、後から直しにくい。")
        self.assertIn("要注意", result["live_diff"])
        self.assertEqual(result["mark"], "c")
        self.assertEqual(result["row_mark"], "d")
        lines = _lines(result["prompt"])
        start = lines.index("## 添削")
        edit_line = lines[start + 1]
        self.assertTrue(edit_line.startswith("- 段落 1: 「"), edit_line)
        self.assertIn("」→「", edit_line)
        self.assertIn("要注意", edit_line)
        self.assertEqual(lines[start + 2], "- 段落 3: (削除)")
        self.assertEqual(lines[start + 3], "- 段落 5 の後: (追加) 「手順1の後に足す段落」")
        self.assertEqual(lines[start + 4], "（説明の頁の添削＝完成形は無し。#N は文字だけの版の行の番号）")
        self.assertEqual(lines[-2:], ["---", CLOSING])
        self.assertEqual(result["count"], "直し 3 件")
        self.assertEqual(result["li_tags"], 2)  # 足した段落を li にしない（番号の数え直しを防ぐ）

    def test_restoring_and_cancelling(self):
        steps = [
            {"op": "click", "sel": "#rv-tensaku"},
            {"op": "click", "sel": "p.body-copy"},
            {"op": "fill", "sel": ".rv-ed textarea", "value": "書き換えた"},
            {"op": "press", "key": "Escape"},
            {"op": "eval", "as": "after_cancel", "js": _PROMPT},
            {"op": "click", "sel": "p.body-copy"},
            {"op": "fill", "sel": ".rv-ed textarea", "value": "書き換えた"},
            {"op": "press", "sel": ".rv-ed textarea", "key": "Control+Enter"},
            {"op": "eval", "as": "after_commit", "js": _PROMPT},
            {"op": "click", "sel": ".rv-sumrow .rv-btn", "nth": 1},
            {"op": "eval", "as": "after_restore", "js": _PROMPT},
            {"op": "eval", "as": "wrappers", "js": "document.querySelectorAll('.rv-x').length"},
        ]
        result = _run(_page(), steps)

        self.assertClean(result)
        self.assertNotIn("## 添削", result["after_cancel"])
        self.assertIn("- 段落 2: ", result["after_commit"])
        self.assertNotIn("## 添削", result["after_restore"])
        self.assertEqual(result["wrappers"], 0)

    def test_edits_made_on_another_version_of_the_page_are_dropped_not_misapplied(self):
        scramble = (
            "(()=>{const k='uc-tensaku:'+document.title+':page';const o=JSON.parse(localStorage.getItem(k));"
            "Object.keys(o.g).forEach(n=>{o.g[n]='別の中身'});localStorage.setItem(k,JSON.stringify(o));})()"
        )
        steps = [
            {"op": "click", "sel": "#rv-tensaku"},
            {"op": "click", "sel": "ul.bullets li"},
            {"op": "fill", "sel": ".rv-ed textarea", "value": "箇条書きを直した"},
            {"op": "click", "sel": ".rv-ed .rv-main"},
            {"op": "eval", "as": "scrambled", "js": scramble},
            {"op": "reload"},
            {"op": "eval", "as": "prompt", "js": _PROMPT},
            {"op": "eval", "as": "wrappers", "js": "document.querySelectorAll('.rv-x').length"},
        ]
        result = _run(_page(), steps)

        self.assertClean(result)
        self.assertNotIn("## 添削", result["prompt"])
        self.assertEqual(result["wrappers"], 0)

    def test_edits_survive_a_reload_and_forget_clears_them(self):
        steps = [
            {"op": "click", "sel": "#rv-tensaku"},
            {"op": "click", "sel": "ul.bullets li"},
            {"op": "fill", "sel": ".rv-ed textarea", "value": "箇条書きを直した"},
            {"op": "click", "sel": ".rv-ed .rv-main"},
            {"op": "reload"},
            {"op": "eval", "as": "after_reload", "js": _PROMPT},
            {"op": "eval", "as": "mark", "js": "document.querySelector('ul.bullets li').getAttribute('data-rv-t')"},
            {"op": "click", "sel": "#forget-decision"},
            {"op": "eval", "as": "after_forget", "js": _PROMPT},
            {"op": "eval", "as": "mark_after", "js": "document.querySelector('ul.bullets li').hasAttribute('data-rv-t')"},
        ]
        result = _run(_page(), steps)

        self.assertClean(result)
        self.assertIn("- 段落 7: ", result["after_reload"])
        self.assertEqual(result["mark"], "c")
        self.assertNotIn("## 添削", result["after_forget"])
        self.assertFalse(result["mark_after"])


@unittest.skipUnless(markdown_lite is not None, "markdown_lite が無い")
class ManuscriptTensakuBrowserTests(_BrowserCase):
    NEW_2 = "導入の段落です。[公式の案内](https://example.com/guide)をよく読んでください。"

    def _expected_final(self) -> str:
        return _MD.replace("導入の段落です。[公式の案内](https://example.com/guide)を読んでください。", self.NEW_2)

    def test_editing_paragraph_two_gives_a_diff_line_and_a_verbatim_final_text(self):
        steps = [
            {"op": "eval", "as": "no_change", "js": _PROMPT},
            {"op": "click", "sel": ".ms-blk[data-ms='2']"},
            {"op": "eval", "as": "initial", "js": "document.querySelector('.rv-editing .rv-edta').value"},
            {"op": "fill", "sel": ".rv-editing .rv-edta", "value": self.NEW_2},
            {"op": "click", "sel": ".rv-editing [data-act='commit']"},
            {"op": "eval", "as": "prompt", "js": _PROMPT},
            {"op": "eval", "as": "link", "js": "document.querySelector('.ms-blk[data-ms=\"2\"] .ms-link').textContent+'|'+document.querySelector('.ms-blk[data-ms=\"2\"] .ms-url').textContent"},
            {"op": "eval", "as": "diff_marks", "js": "document.querySelectorAll('.ms-blk[data-ms=\"2\"] ins, .ms-blk[data-ms=\"2\"] del').length"},
            {"op": "eval", "as": "count", "js": "document.getElementById('rv-t-count').innerText"},
            {"op": "eval", "as": "bar_buttons", "js": "[...document.querySelectorAll('button')].filter(b=>b.textContent==='貼り付ける文章を作る').length"},
        ]
        result = _run(_manuscript_page("tensaku"), steps)

        self.assertClean(result)
        self.assertEqual(_lines(result["no_change"])[2:4], ["## 添削", "- 変更なし"])
        self.assertEqual(result["initial"], "導入の段落です。[公式の案内](https://example.com/guide)を読んでください。")
        lines = _lines(result["prompt"])
        start = lines.index("## 添削")
        self.assertTrue(lines[start + 1].startswith("- 段落 2: 「"), lines[start + 1])
        self.assertIn("」→「", lines[start + 1])
        # 完成形は、本文に ``` があるので 4 つの ` で囲む。他の段落は1字も変わらない。
        fenced = "````markdown\n" + self._expected_final().rstrip() + "\n````"
        self.assertIn(fenced, result["prompt"])
        self.assertEqual(lines[-2:], ["---", CLOSING])
        self.assertEqual(result["link"], "公式の案内|（example.com/guide）")  # 押せない・scheme を外す
        self.assertGreaterEqual(result["diff_marks"], 1)
        self.assertEqual(result["count"], "直し 1 件")
        self.assertEqual(result["bar_buttons"], 0)  # 判断欄があるので「貼り付ける文章を作る」は出ない

    def test_adding_and_deleting_paragraphs(self):
        steps = [
            {"op": "click", "sel": ".ms-blk[data-ms='8']"},
            {"op": "click", "sel": ".rv-editing [data-act='addbelow']"},
            {"op": "fill", "sel": ".rv-editing .rv-edta", "value": "足した段落です。"},
            {"op": "click", "sel": ".rv-editing [data-act='commit']"},
            {"op": "click", "sel": ".ms-blk[data-ms='6']"},
            {"op": "click", "sel": ".rv-editing [data-act='delete']"},
            {"op": "eval", "as": "prompt", "js": _PROMPT},
            {"op": "eval", "as": "deleted_row", "js": "document.querySelectorAll('.rv-delrow').length"},
            {"op": "click", "sel": ".rv-delrow [data-act='undelete']"},
            {"op": "eval", "as": "after_undo", "js": _PROMPT},
        ]
        result = _run(_manuscript_page("tensaku"), steps)

        self.assertClean(result)
        lines = _lines(result["prompt"])
        self.assertIn("- 段落 6: (削除)", lines)
        self.assertIn("- 段落 8: (追加) 「足した段落です。」", lines)  # 完成形での位置（削除した引用の分だけ前へ詰まる）
        final_part = result["prompt"].split("````markdown\n", 1)[1].split("\n````", 1)[0]
        self.assertNotIn("引用の文です。", final_part)
        self.assertTrue(final_part.endswith("最後の段落です。\n\n足した段落です。"))
        self.assertEqual(result["deleted_row"], 1)
        after_undo = _lines(result["after_undo"])
        self.assertNotIn("- 段落 6: (削除)", after_undo)
        self.assertIn("引用の文です。", result["after_undo"])

    def test_tabs_final_diff_and_source(self):
        steps = [
            {"op": "click", "sel": ".ms-blk[data-ms='2']"},
            {"op": "fill", "sel": ".rv-editing .rv-edta", "value": self.NEW_2},
            {"op": "click", "sel": ".rv-editing [data-act='commit']"},
            {"op": "click", "sel": ".rv-tab", "nth": 1},
            {"op": "eval", "as": "final_text", "js": "document.querySelector('.rv-panel:not([hidden]) .ms').innerText"},
            {"op": "eval", "as": "visible_panels", "js": "[...document.querySelectorAll('.rv-panel')].filter(p=>!p.hidden).length+'|'+document.querySelector('article.ms').hidden"},
            {"op": "click", "sel": ".rv-finhead .rv-btn", "nth": 1},
            {"op": "eval", "as": "draft_text", "js": "document.querySelector('.rv-panel:not([hidden]) .ms').innerText"},
            {"op": "click", "sel": ".rv-tab", "nth": 2},
            {"op": "eval", "as": "diff_items", "js": "document.querySelectorAll('.rv-ditem').length"},
            {"op": "eval", "as": "diff_marks", "js": "document.querySelectorAll('.rv-panel:not([hidden]) .ms ins').length"},
            {"op": "click", "sel": ".rv-tab", "nth": 3},
            {"op": "eval", "as": "source", "js": "document.querySelector('.rv-srcall').value"},
            {"op": "fill", "sel": ".rv-srcall", "value": self._expected_final().replace("最後の段落です。", "最後の段落です。\n\n末尾に足した段落です。")},
            {"op": "click", "sel": ".rv-panel:not([hidden]) .rv-main"},
            {"op": "eval", "as": "status", "js": "document.querySelector('.rv-panel:not([hidden]) .rv-st').textContent"},
            {"op": "eval", "as": "prompt", "js": _PROMPT},
            {"op": "click", "sel": ".rv-tab", "nth": 0},
            {"op": "eval", "as": "edit_blocks", "js": "document.querySelectorAll('article.ms > .ms-blk').length"},
        ]
        result = _run(_manuscript_page("tensaku"), steps)

        self.assertClean(result)
        self.assertIn("よく読んで", result["final_text"])
        self.assertEqual(result["visible_panels"], "1|true")
        self.assertIn("を読んで", result["draft_text"])
        self.assertNotIn("よく読んで", result["draft_text"])
        self.assertGreaterEqual(result["diff_items"], 1)
        self.assertGreaterEqual(result["diff_marks"], 1)
        self.assertEqual(result["source"], self._expected_final())
        self.assertIn("反映しました", result["status"])
        self.assertIn("- 段落 9: (追加) 「末尾に足した段落です。」", _lines(result["prompt"]))
        self.assertEqual(result["edit_blocks"], 9)  # 元の8（隠れたコメントを含む）＋足した1

    def test_edits_survive_a_reload_and_forget_returns_to_no_change(self):
        steps = [
            {"op": "click", "sel": ".ms-blk[data-ms='2']"},
            {"op": "fill", "sel": ".rv-editing .rv-edta", "value": self.NEW_2},
            {"op": "click", "sel": ".rv-editing [data-act='commit']"},
            {"op": "reload"},
            {"op": "eval", "as": "after_reload", "js": _PROMPT},
            {"op": "eval", "as": "shown", "js": "document.querySelector('.ms-blk[data-ms=\"2\"]').innerText"},
            {"op": "click", "sel": "#forget-decision"},
            {"op": "eval", "as": "after_forget", "js": _PROMPT},
            {"op": "eval", "as": "shown_after", "js": "document.querySelector('.ms-blk[data-ms=\"2\"]').innerText"},
            {"op": "reload"},
            {"op": "eval", "as": "after_forget_reload", "js": _PROMPT},
        ]
        result = _run(_manuscript_page("tensaku"), steps)

        self.assertClean(result)
        self.assertIn("- 段落 2: ", result["after_reload"])
        self.assertIn("よく読んで", result["shown"])
        self.assertIn("- 変更なし", result["after_forget"])
        self.assertNotIn("よく読んで", result["shown_after"])
        self.assertIn("- 変更なし", result["after_forget_reload"])

    def test_the_manuscript_blocks_keep_their_numbers_and_python_html_is_reused(self):
        steps = [
            {"op": "eval", "as": "numbers", "js": "[...document.querySelectorAll('article.ms > .ms-blk')].map(e=>e.dataset.ms+':'+e.dataset.blk+':'+e.dataset.msType).join(',')"},
            {"op": "eval", "as": "link", "js": "document.querySelector('.ms-blk[data-ms=\"2\"] .ms-url').textContent"},
            {"op": "eval", "as": "hidden_comment", "js": "document.querySelector('.ms-blk[data-ms=\"7\"]').hidden"},
        ]
        result = _run(_manuscript_page("tensaku"), steps)

        self.assertClean(result)
        self.assertEqual(
            result["numbers"],
            "1:1:heading,2:2:paragraph,3:3:heading,4:4:code,5:5:table,6:6:quote,7:7:comment,8:8:paragraph",
        )
        self.assertEqual(result["link"], "（example.com/guide）")
        self.assertTrue(result["hidden_comment"])


@unittest.skipUnless(markdown_lite is not None, "markdown_lite が無い")
class ManuscriptSafetyBrowserTests(_BrowserCase):
    def test_raw_html_in_the_manuscript_is_text_even_after_the_script_redraws_a_block(self):
        md = (
            "# 題\n\n"
            '<img src=x onerror="window.__xss=1"> と <script>window.__xss=2</script> を含む段落。\n\n'
            "次の段落。\n"
        )
        steps = [
            {"op": "click", "sel": ".ms-blk[data-ms='2']"},
            {"op": "fill", "sel": ".rv-editing .rv-edta", "value": "<img src=x onerror=\"window.__xss=3\"> を直した段落。"},
            {"op": "click", "sel": ".rv-editing [data-act='commit']"},
            {"op": "click", "sel": ".rv-tab", "nth": 1},
            {"op": "click", "sel": ".rv-tab", "nth": 2},
            {"op": "wait", "ms": 200},
            {"op": "eval", "as": "xss", "js": "String(window.__xss)"},
            {"op": "eval", "as": "imgs", "js": "document.querySelectorAll('article.ms img, .rv-panel img').length"},
            {"op": "eval", "as": "shown", "js": "document.querySelector('.rv-panel:not([hidden]) .ms').innerText"},
        ]
        result = _run(_manuscript_page("tensaku", md=md), steps)

        self.assertClean(result)
        self.assertEqual(result["xss"], "undefined")
        self.assertEqual(result["imgs"], 0)
        self.assertIn("<img src=x", result["shown"])


class ModeAndLayoutBrowserTests(_BrowserCase):
    def test_the_two_modes_are_exclusive_and_escape_turns_the_mode_off(self):
        steps = [
            {"op": "click", "sel": "#rv-shiteki"},
            {"op": "eval", "as": "a", "js": "[document.body.dataset.rv, document.getElementById('rv-shiteki').getAttribute('aria-pressed'), document.getElementById('rv-tensaku').getAttribute('aria-pressed'), document.body.classList.contains('rv-s'), document.body.classList.contains('rv-t')]"},
            {"op": "click", "sel": "#rv-tensaku"},
            {"op": "eval", "as": "b", "js": "[document.body.dataset.rv, document.getElementById('rv-shiteki').getAttribute('aria-pressed'), document.getElementById('rv-tensaku').getAttribute('aria-pressed'), document.body.classList.contains('rv-s'), document.body.classList.contains('rv-t')]"},
            {"op": "click", "sel": ".card"},
            {"op": "eval", "as": "ed_open", "js": "document.querySelectorAll('.rv-ed').length+'|'+document.querySelector('.rv-sheet').hidden"},
            {"op": "press", "key": "Escape"},
            {"op": "eval", "as": "after_first_esc", "js": "document.body.dataset.rv+'|'+document.querySelectorAll('.rv-ed').length"},
            {"op": "press", "key": "Escape"},
            {"op": "eval", "as": "after_second_esc", "js": "(document.body.dataset.rv||'')+'|'+document.getElementById('rv-tensaku').getAttribute('aria-pressed')"},
            {"op": "click", "sel": "#rv-shiteki"},
            {"op": "click", "sel": ".card"},
            {"op": "press", "key": "Escape"},
            {"op": "eval", "as": "esc_closes_sheet_only", "js": "document.body.dataset.rv+'|'+document.querySelector('.rv-sheet').hidden"},
            {"op": "press", "key": "Escape"},
            {"op": "eval", "as": "esc_turns_off", "js": "document.body.dataset.rv||''"},
            {"op": "click", "sel": "#rv-shiteki"},
            {"op": "click", "sel": "#rv-shiteki"},
            {"op": "eval", "as": "toggled_off", "js": "document.body.dataset.rv||''"},
        ]
        result = _run(_page(), steps)

        self.assertClean(result)
        self.assertEqual(result["a"], ["shiteki", "true", "false", True, False])
        self.assertEqual(result["b"], ["tensaku", "false", "true", False, True])
        self.assertEqual(result["ed_open"], "1|true")  # 直すの最中に指摘の板は開かない
        self.assertEqual(result["after_first_esc"], "tensaku|0")  # 1回目の Esc は編集欄だけ閉じる
        self.assertEqual(result["after_second_esc"], "|false")
        self.assertEqual(result["esc_closes_sheet_only"], "shiteki|true")
        self.assertEqual(result["esc_turns_off"], "")
        self.assertEqual(result["toggled_off"], "")

    def test_units_become_keyboard_reachable_only_while_a_mode_is_on(self):
        steps = [
            {"op": "eval", "as": "off", "js": "document.querySelectorAll('[data-blk][tabindex]').length"},
            {"op": "click", "sel": "#rv-shiteki"},
            {"op": "eval", "as": "on", "js": "document.querySelectorAll('[data-blk][tabindex]').length"},
            {"op": "eval", "as": "focus", "js": "(()=>{const u=document.querySelector('[data-blk=\"2\"]');u.focus();return document.activeElement===u})()"},
            {"op": "press", "key": "Enter"},
            {"op": "eval", "as": "sheet", "js": "!document.querySelector('.rv-sheet').hidden && document.querySelector('.rv-target').textContent.startsWith('#2')"},
            {"op": "press", "key": "Escape"},
            {"op": "press", "key": "Escape"},
            {"op": "eval", "as": "off_again", "js": "document.querySelectorAll('[data-blk][tabindex]').length"},
        ]
        result = _run(_page(), steps)

        self.assertClean(result)
        self.assertEqual(result["off"], 0)
        self.assertEqual(result["on"], 8)
        self.assertTrue(result["focus"])
        self.assertTrue(result["sheet"])
        self.assertEqual(result["off_again"], 0)

    def test_nothing_overflows_sideways_at_390px_even_with_every_panel_open(self):
        steps = [
            {"op": "eval", "as": "o0", "js": _OVERFLOW},
            {"op": "click", "sel": "#rv-shiteki"},
            {"op": "click", "sel": ".card"},
            {"op": "eval", "as": "o1", "js": _OVERFLOW},
            {"op": "click", "sel": ".rv-chip", "nth": 5},
            {"op": "click", "sel": ".rv-sheet .rv-main"},
            {"op": "click", "sel": "#rv-s-count"},
            {"op": "eval", "as": "o2", "js": _OVERFLOW},
            {"op": "click", "sel": ".rv-drawer .rv-dfoot .rv-btn"},
            {"op": "eval", "as": "o3", "js": _OVERFLOW},
            {"op": "press", "key": "Escape"},
            {"op": "click", "sel": "#rv-tensaku"},
            {"op": "click", "sel": "tr[data-blk='3']"},
            {"op": "eval", "as": "o4", "js": _OVERFLOW},
            {"op": "fill", "sel": ".rv-ed textarea", "value": "速度 とても速い"},
            {"op": "click", "sel": ".rv-ed .rv-main"},
            {"op": "click", "sel": "#rv-t-count"},
            {"op": "eval", "as": "o5", "js": _OVERFLOW},
            {"op": "eval", "as": "bar", "js": "(()=>{const r=document.getElementById('rv-bar').getBoundingClientRect();return [r.left>=0, r.right<=innerWidth]})()"},
        ]
        result = _run(_page(body=_UNITS), steps, width=390, height=844)

        self.assertClean(result)
        for key in ("o0", "o1", "o2", "o3", "o4", "o5"):
            self.assertLessEqual(result[key]["sw"], result[key]["iw"], key)
        self.assertEqual(result["bar"], [True, True])

    @unittest.skipUnless(markdown_lite is not None, "markdown_lite が無い")
    def test_the_manuscript_editor_does_not_overflow_at_390px(self):
        steps = [
            {"op": "click", "sel": ".ms-blk[data-ms='5']"},
            {"op": "eval", "as": "o1", "js": _OVERFLOW},
            {"op": "click", "sel": ".rv-editing [data-act='commit']"},
            {"op": "click", "sel": ".rv-tab", "nth": 3},
            {"op": "eval", "as": "o2", "js": _OVERFLOW},
            {"op": "click", "sel": ".rv-tab", "nth": 2},
            {"op": "eval", "as": "o3", "js": _OVERFLOW},
        ]
        result = _run(_manuscript_page("tensaku"), steps, width=390, height=844)

        self.assertClean(result)
        for key in ("o1", "o2", "o3"):
            self.assertLessEqual(result[key]["sw"], result[key]["iw"], key)

    def test_dark_scheme_keeps_the_ui_readable(self):
        steps = [
            {"op": "click", "sel": "#rv-shiteki"},
            {"op": "eval", "as": "colors", "js": "(()=>{const s=getComputedStyle(document.getElementById('rv-shiteki'));const b=getComputedStyle(document.getElementById('rv-bar'));return [s.color,s.backgroundColor,b.backgroundColor]})()"},
        ]
        result = _run(_page(), steps, scheme="dark")

        self.assertClean(result)
        color, background, bar = result["colors"]
        self.assertNotEqual(color, background)
        self.assertNotEqual(bar, "rgba(0, 0, 0, 0)")  # 帯の背景は頁のトークンから来る（透けて読めなくならない）


class IntegrationWithTheRealDecisionScriptTests(_BrowserCase):
    """判断欄の本物の script（window.pageReply を作る版）と組み合わせる。作る版が無ければ飛ばす。"""

    def _real_page(self) -> str:
        from visual.contracts import ExplanationPlan
        from visual.render_components import DECISION_SCRIPT, render_components

        if "window.pageReply" not in DECISION_SCRIPT:
            self.skipTest("判断欄の script がまだ window.pageReply を作っていない")
        plan = ExplanationPlan(
            audience="project_novice",
            depth="deep",
            components=("overview", "summary", "decision"),
            reason_codes=(),
            provisional=False,
            should_continue=False,
            delivery="local_html",
            publish_policy="never",
        )
        content = {
            "review": "both",
            "overview": "全体の説明です。",
            "summary": {"cards": [{"title": "案A", "body": "安くて速い。"}]},
            "decision": {
                "groups": [
                    {
                        "legend": "どれにするか",
                        "kind": "radio",
                        "options": [{"label": "案A", "recommended": True}, {"label": "案B"}],
                    }
                ]
            },
        }
        html = render_components(plan, title="統合の見本", content=content)
        if html.count("<script>") < 3:
            self.skipTest("頁に指摘と添削の script がまだ載らない")
        return html

    def test_shiteki_and_tensaku_lines_reach_the_real_prompt_and_forget_clears_them(self):
        html = self._real_page()
        steps = [
            {"op": "click", "sel": "#rv-shiteki"},
            {"op": "click", "sel": "[data-blk]"},
            {"op": "click", "sel": ".rv-chip", "nth": 0},
            {"op": "fill", "sel": ".rv-sheet textarea", "value": "実機の指摘"},
            {"op": "click", "sel": ".rv-sheet .rv-main"},
            {"op": "click", "sel": "#rv-tensaku"},
            {"op": "click", "sel": "[data-blk]", "nth": 1},
            {"op": "fill", "sel": ".rv-ed textarea", "value": "実機の直し"},
            {"op": "click", "sel": ".rv-ed .rv-main"},
            {"op": "eval", "as": "prompt", "js": _PROMPT},
            {"op": "reload"},
            {"op": "eval", "as": "after_reload", "js": _PROMPT},
            {"op": "click", "sel": "#forget-decision"},
            {"op": "eval", "as": "after_forget", "js": _PROMPT},
        ]
        result = _run(html, steps)

        self.assertClean(result)
        lines = _lines(result["prompt"])
        self.assertIn("## 指摘", lines)
        self.assertIn("## 添削", lines)
        self.assertLess(lines.index("## 指摘"), lines.index("## 添削"))
        self.assertIn("#1 [削る] 実機の指摘", lines)
        self.assertEqual(lines[-2], "---")
        self.assertIn("## 指摘", _lines(result["after_reload"]))
        self.assertNotIn("## 指摘", result["after_forget"])
        self.assertNotIn("## 添削", result["after_forget"])


if __name__ == "__main__":
    unittest.main()

"""頁の回答の組み立ての窓口 `window.pageReply` の検査（2026-10-09・指摘と添削の作り込み）。

契約（判断欄の script＝DECISION_SCRIPT が作り、指摘・添削の script が使う）：
  window.pageReply = {
    extras: [],              // 要素＝{role:'shiteki'|'tensaku', lines: () => string[], forget: () => void}
    compose: () => string[], // 回答文の全行（1行目【頁の回答】題 … 最後は '---' と締めの1文）
    rebuild: () => void,     // compose() を #decision-prompt があればそこへ書く（無ければ何もしない）
    copy:    () => void      // compose() の全文を写す（失敗時は選択状態にする）
  }
  compose の並び＝【頁の回答】題 → Q 行 → 異議 → 自由記述 → 役割の順（shiteki→tensaku）に、行が1つ以上ある
  extras の節（見出し「## 指摘」「## 添削」は DECISION_SCRIPT が足す）→ '---' → 締めの文。
  判断欄の無い頁でも compose() は回答文を返す。「入力を消す」は全 extras の forget() も呼ぶ。

⚠️DECISION_SCRIPT は全頁共通の唯一の script＝構文の誤りで全頁の判断欄が黙って死ぬ。
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
from visual.contracts import ExplanationPlan
from visual.render_components import DECISION_SCRIPT, render_components

CLOSING = "上の回答を反映して作業を続けてください。お任せの項目は推奨案で確定してください。"
UNSEEN_REC = "(見ていない＝推奨で進めるが、大事なら会話で確かめる)"


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


DECISION = {
    "groups": [
        {
            "legend": "配置はどれにするか",
            "kind": "radio",
            "options": [{"label": "案A", "recommended": True}, {"label": "案B"}],
        }
    ]
}


def _page_with_decision(title: str = "窓口の見本") -> str:
    return render_components(_plan("decision"), title=title, content={"decision": DECISION})


def _page_without_decision(title: str = "判断欄なしの見本") -> str:
    return render_components(
        _plan("overview"), title=title, content={"overview": "判断欄の無い頁です。"}
    )


# 試験用に script の後ろへ足す script。指摘・添削の script が使うのと同じ口（pageReply.extras）に登録する。
_EXTRA_SCRIPT = """
window.__s = []; window.__t = []; window.__forgot = {s: 0, t: 0};
window.pageReply.extras.push({role: 'tensaku', lines: () => window.__t, forget: () => { window.__forgot.t++; }});
window.pageReply.extras.push({role: 'shiteki', lines: () => window.__s, forget: () => { window.__forgot.s++; }});
"""


def _with_extras(html: str, script: str = _EXTRA_SCRIPT) -> str:
    marker = "</script></body></html>"
    assert html.count(marker) == 1
    return html.replace(marker, "</script><script>" + script + "</script></body></html>")


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
      else if (op.click) { await page.locator(op.click).nth(op.nth || 0).click(); out.push(null); }
      else if (op.check) { await page.locator(op.check).nth(op.nth || 0).check(); out.push(null); }
      else if (op.fill) { await page.locator(op.fill).nth(op.nth || 0).fill(op.value); out.push(null); }
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
    with tempfile.TemporaryDirectory(prefix="reply_api_") as tmp:
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


class ScriptTextTests(unittest.TestCase):
    def test_script_publishes_the_contract_names(self):
        for part in ("window.pageReply", "extras", "compose", "rebuild", "copy", "## 指摘", "## 添削"):
            self.assertIn(part, DECISION_SCRIPT, part)

    def test_script_keeps_the_fixed_reply_parts(self):
        for part in ("【頁の回答】", "'---'", CLOSING, "異議. ", "自由記述: "):
            self.assertIn(part, DECISION_SCRIPT, part)

    def test_new_part_has_no_comments_and_the_script_has_no_forbidden_words(self):
        # 注釈は Python 側に置く（毎回の頁のバイトを増やさない）。receipts の判定に当たる語も書かない。
        start = DECISION_SCRIPT.index("function compose()")
        end = DECISION_SCRIPT.index("const theme=")
        self.assertNotIn("//", DECISION_SCRIPT[start:end])
        for word in ("fetch(", "XMLHttpRequest", "WebSocket", "EventSource", "sendBeacon", "javascript:", "</script", "http://", "https://"):
            self.assertNotIn(word, DECISION_SCRIPT, word)

    @unittest.skipUnless(shutil.which("node"), "node が無い")
    def test_script_passes_node_check(self):
        with tempfile.TemporaryDirectory(prefix="reply_api_js_") as tmp:
            path = Path(tmp) / "script.js"
            path.write_text(DECISION_SCRIPT, encoding="utf-8")
            completed = subprocess.run(
                ["node", "--check", str(path)], capture_output=True, text=True, encoding="utf-8", timeout=30, check=False
            )
        self.assertEqual(completed.returncode, 0, completed.stderr)


class ComposeContractTests(unittest.TestCase):
    def test_window_page_reply_has_the_four_members(self):
        result = _run(
            _page_with_decision(),
            [
                {
                    "eval": "({extras: Array.isArray(window.pageReply.extras), compose: typeof window.pageReply.compose,"
                    " rebuild: typeof window.pageReply.rebuild, copy: typeof window.pageReply.copy})"
                }
            ],
        )

        self.assertEqual(result["errors"], [])
        self.assertEqual(
            result["out"][0], {"extras": True, "compose": "function", "rebuild": "function", "copy": "function"}
        )

    def test_compose_without_extras_matches_the_prompt_and_the_old_shape(self):
        result = _run(
            _page_with_decision(),
            [
                {"eval": "window.pageReply.compose()"},
                {"eval": "document.getElementById('decision-prompt').textContent"},
            ],
        )

        lines, prompt = result["out"]
        self.assertEqual(lines[0], "【頁の回答】窓口の見本")
        self.assertEqual(lines[1], "Q1. 配置はどれにするか: " + UNSEEN_REC)
        self.assertEqual(lines[-3:], ["自由記述: (なし)", "---", CLOSING])
        self.assertEqual("\n".join(lines), prompt)
        self.assertFalse(any(line.startswith("## ") for line in lines))
        self.assertEqual(result["errors"], [])

    def test_extras_sections_come_after_free_text_and_before_the_rule_in_role_order(self):
        # 登録の順は tensaku → shiteki だが、回答文では shiteki → tensaku の順に並ぶ。
        result = _run(
            _with_extras(_page_with_decision()),
            [
                {"eval": "(() => { window.__s = ['#1 [削る] 「冗長」 短く', '#4 [ここは良い]']; window.__t = ['- 段落 2: 「旧」→「新」']; window.pageReply.rebuild(); })()"},
                {"eval": "window.pageReply.compose()"},
                {"eval": "document.getElementById('decision-prompt').textContent"},
            ],
        )

        lines, prompt = result["out"][1], result["out"][2]
        free = lines.index("自由記述: (なし)")
        shiteki = lines.index("## 指摘")
        tensaku = lines.index("## 添削")
        rule = lines.index("---")
        self.assertTrue(free < shiteki < tensaku < rule)
        self.assertEqual(lines[shiteki + 1 : tensaku], ["#1 [削る] 「冗長」 短く", "#4 [ここは良い]"])
        self.assertEqual(lines[tensaku + 1 : rule], ["- 段落 2: 「旧」→「新」"])
        self.assertEqual(lines[rule:], ["---", CLOSING])
        self.assertEqual("\n".join(lines), prompt)
        self.assertEqual(result["errors"], [])

    def test_empty_lines_make_no_section(self):
        result = _run(
            _with_extras(_page_with_decision()),
            [
                {"eval": "(() => { window.__t = ['- 変更なし']; window.pageReply.rebuild(); })()"},
                {"eval": "window.pageReply.compose()"},
            ],
        )

        lines = result["out"][1]
        self.assertNotIn("## 指摘", lines)
        self.assertIn("## 添削", lines)
        self.assertEqual(lines[lines.index("## 添削") + 1], "- 変更なし")

    def test_lines_are_read_every_time_and_the_section_goes_away_when_emptied(self):
        result = _run(
            _with_extras(_page_with_decision()),
            [
                {"eval": "(() => { window.__s = ['#2 [言い換える]']; return window.pageReply.compose().includes('## 指摘'); })()"},
                {"eval": "(() => { window.__s = []; return window.pageReply.compose().includes('## 指摘'); })()"},
            ],
        )

        self.assertEqual(result["out"], [True, False])

    def test_a_throwing_extra_does_not_break_the_reply(self):
        script = (
            "window.pageReply.extras.push({role: 'shiteki', lines: () => { throw new Error('x'); }, forget: () => { throw new Error('y'); }});"
            "window.pageReply.extras.push({role: 'tensaku', lines: () => ['- 変更なし'], forget: () => {}});"
        )
        result = _run(
            _with_extras(_page_with_decision(), script),
            [
                {"eval": "window.pageReply.compose()"},
                {"click": "#forget-decision"},
                {"eval": "document.getElementById('forget-decision').textContent"},
            ],
        )

        lines = result["out"][0]
        self.assertNotIn("## 指摘", lines)
        self.assertEqual(lines[lines.index("## 添削") + 1], "- 変更なし")
        self.assertEqual(result["out"][2], "消しました")

    def test_forget_button_calls_every_extra_forget_and_clears_the_inputs(self):
        result = _run(
            _with_extras(_page_with_decision()),
            [
                {"check": "input[name=decision]", "nth": 0},
                {"eval": "window.pageReply.compose()[1]"},
                {"click": "#forget-decision"},
                {"eval": "window.__forgot"},
                {"eval": "window.pageReply.compose()[1]"},
            ],
        )

        self.assertIn("案A", result["out"][1])
        self.assertEqual(result["out"][3], {"s": 1, "t": 1})
        self.assertEqual(result["out"][4], "Q1. 配置はどれにするか: " + UNSEEN_REC)
        self.assertEqual(result["errors"], [])

    def test_page_without_a_decision_section_still_composes(self):
        result = _run(
            _with_extras(_page_without_decision()),
            [
                {"eval": "document.getElementById('decision-prompt') === null"},
                {"eval": "window.pageReply.compose()"},
                {"eval": "(() => { window.__s = ['#3 [削る]']; return window.pageReply.compose(); })()"},
                {"eval": "(() => { window.pageReply.rebuild(); return 'ok'; })()"},
            ],
        )

        self.assertTrue(result["out"][0])
        self.assertEqual(
            result["out"][1],
            ["【頁の回答】判断欄なしの見本", "自由記述: (なし)", "---", CLOSING],
        )
        self.assertEqual(
            result["out"][2],
            ["【頁の回答】判断欄なしの見本", "自由記述: (なし)", "## 指摘", "#3 [削る]", "---", CLOSING],
        )
        self.assertEqual(result["out"][3], "ok")
        self.assertEqual(result["errors"], [])

    def test_copy_resolves_without_error_and_leaves_the_prompt_selected_when_the_clipboard_fails(self):
        result = _run(
            _with_extras(_page_with_decision()),
            [
                {"eval": "(async () => { window.__s = ['#1 [削る]']; const ok = await window.pageReply.copy(); return typeof ok; })()"},
                {"eval": "document.getElementById('decision-prompt').textContent.includes('## 指摘')"},
            ],
        )

        self.assertEqual(result["out"][0], "boolean")
        self.assertTrue(result["out"][1])
        self.assertEqual(result["errors"], [])


if __name__ == "__main__":
    unittest.main()

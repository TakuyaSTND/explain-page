"""判断の頁が組む「回答文」の固定形の検査（2026-10-08・赤ペン流の判断の頁）。

固定形（頁ごとに同じ形・1通りに読める）：
  【頁の回答】<document.title>
  Q1. <問い>: <選んだ選択肢>、<選んだ選択肢> / 補足: <補足>
  Q2. <問い>: (未選択 = お任せ＝推奨で進める)
  Q3-1. <段階評価の項目>: <選んだ段階>      ← 段階評価は群の番号に枝番
  Q4. <問い>: <数の名前>=<値><単位>、…
  異議. <対象>: <理由 or （未記入）>          ← 押した分だけ
  自由記述: <本文 or (なし)>                  ← 常に1行
  ---
  上の回答を反映して作業を続けてください。お任せの項目は推奨案で確定してください。

⚠️DECISION_SCRIPT は全頁共通の唯一の script＝構文の誤りで全頁の判断欄が黙って死ぬ。
だから node --check と、本物のブラウザで押して確かめる試験の両方を置く（無い環境では飛ばす）。
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
from visual.render_components import DECISION_SCRIPT, render_components

NONE_TEXT = "(未選択 = お任せ＝推奨で進める)"
CLOSING = "上の回答を反映して作業を続けてください。お任せの項目は推奨案で確定してください。"


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
            "options": [
                {"label": "案A", "recommended": True, "pros": "安い"},
                {"label": "案B", "pros": "確実"},
            ],
        },
        {
            "legend": "足すもの",
            "kind": "checkbox",
            "options": [{"label": "利点の欄", "recommended": True}, {"label": "補足の欄"}],
        },
        {
            "legend": "個別の裁定",
            "kind": "scale",
            "items": [
                {"title": "主体の断絶", "recommended": "採用"},
                {"title": "上限の単位", "recommended": "割引採用"},
            ],
        },
        {
            "legend": "数を決める",
            "kind": "number",
            "options": [{"label": "巡数", "unit": "回", "min": 1, "max": 5}],
        },
        {"legend": "自由記述", "kind": "free", "placeholder": "自由に"},
    ],
    "judgments": ["判定1は違う"],
}


def _page(decision=DECISION, title="判断の見本") -> str:
    return render_components(_plan("decision"), title=title, content={"decision": decision})


class ScriptTextTests(unittest.TestCase):
    def test_script_contains_the_fixed_reply_parts(self):
        for part in (
            "【頁の回答】",
            NONE_TEXT,
            "'---'",
            CLOSING,
            "q-note",
            "異議. ",
            "自由記述: ",
            "(なし)",
        ):
            self.assertIn(part, DECISION_SCRIPT, part)

    def test_script_no_longer_uses_the_old_empty_message(self):
        self.assertNotIn("選択してください", DECISION_SCRIPT)

    def test_script_is_embedded_once_and_unchanged(self):
        html = _page()

        self.assertEqual(html.count("<script>"), 1)
        start = html.index("<script>") + len("<script>")
        end = html.index("</script>")
        self.assertEqual(html[start:end].strip(), DECISION_SCRIPT.strip())

    def test_script_stays_the_only_approved_script_for_the_gate(self):
        inspection = inspect_artifact_html(
            _page(), required_components=("decision",), glossary_entries={}
        )

        self.assertEqual(inspection.errors, ())
        self.assertEqual(inspection.missing_decision_parts, ())

    def test_script_does_not_name_the_scale_row_class(self):
        # 道具の「部品の濃さ」は頁の本文に scale-row の語がいくつあるかで段階評価を数える。
        # script がその語を持つと全部の頁で1と数えられてしまう。
        self.assertNotIn("scale-row", DECISION_SCRIPT)


class QNoteMarkupTests(unittest.TestCase):
    def test_every_question_fieldset_gets_one_q_note_and_free_and_objections_get_none(self):
        html = _page()

        # radio・checkbox・scale・number の4群に1つずつ。自由記述の群と異議の群には付けない。
        self.assertEqual(html.count('<input type="text" class="q-note"'), 4)
        self.assertIn('data-q="1" placeholder="補足（任意）" aria-label="配置はどれにするか の補足"', html)
        self.assertIn('aria-label="個別の裁定 の補足"', html)
        free_start = html.index('id="decision-objection"')
        self.assertNotIn("q-note", html[free_start : free_start + 400])

    def test_q_note_is_not_a_choice_control_for_the_gate(self):
        # 補足欄は input[type=text]＝「選ぶ部品」とは数えない（既存の .obj-why と同じ扱い）。
        html = (
            '<section data-component="decision"><h2>選ぶこと</h2>'
            '<input type="text" class="q-note" aria-label="補足"></section>'
        )
        inspection = inspect_artifact_html(
            html, required_components=("decision",), glossary_entries={}
        )

        self.assertIn("choice_control", inspection.missing_decision_parts)

    def test_empty_scale_group_gets_no_q_note(self):
        html = render_components(
            _plan("decision"),
            title="題",
            content={"decision": {"groups": [{"legend": "空の群", "kind": "scale", "items": []}]}},
        )

        self.assertNotIn('class="q-note"', html)


class NodeSyntaxTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which("node"), "node が無い")
    def test_script_passes_node_check(self):
        with tempfile.TemporaryDirectory(prefix="decision_script_") as tmp:
            path = Path(tmp) / "decision-script.js"
            path.write_text(DECISION_SCRIPT, encoding="utf-8")
            completed = subprocess.run(
                ["node", "--check", str(path)],
                capture_output=True,
                text=True,
                encoding="utf-8",
                timeout=30,
                check=False,
            )

        self.assertEqual(completed.returncode, 0, completed.stderr)


_BROWSER_SCRIPT = r"""
const { pathToFileURL } = require('url');
const { chromium } = require(process.argv[1]);
const htmlPath = process.argv[2];
const steps = JSON.parse(process.argv[3]);
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
    const prompt = page.locator('#decision-prompt').first();
    const initial = await prompt.textContent();
    for (const step of steps) {
      const loc = page.locator(step.sel).nth(step.nth || 0);
      if (step.op === 'check') await loc.check();
      else if (step.op === 'fill') await loc.fill(step.value);
      else if (step.op === 'click') await loc.click();
    }
    const answered = await prompt.textContent();
    await page.reload({waitUntil:'load'});
    const recalled = await prompt.textContent();
    await page.locator('#forget-decision').first().click();
    const forgotten = await prompt.textContent();
    console.log(JSON.stringify({initial, answered, recalled, forgotten, errors}));
  } finally {
    await browser.close();
  }
})().catch(error => { console.log(JSON.stringify({fail:String(error).slice(0,300)})); process.exitCode = 1; });
"""


def _run_in_browser(html: str, steps: list[dict]) -> dict:
    playwright_path, reason = visual_smoke._resolve_playwright()
    if not playwright_path or not shutil.which("node"):
        raise unittest.SkipTest("Playwright か node が無い: %s" % (reason or ""))
    with tempfile.TemporaryDirectory(prefix="decision_reply_") as tmp:
        page_path = Path(tmp) / "page.html"
        page_path.write_text(html, encoding="utf-8")
        completed = subprocess.run(
            ["node", "-e", _BROWSER_SCRIPT, str(playwright_path), str(page_path), json.dumps(steps)],
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


class BrowserReplyTests(unittest.TestCase):
    def test_initial_text_lists_every_question_as_unselected(self):
        result = _run_in_browser(_page(), [])

        lines = result["initial"].split("\n")
        self.assertEqual(lines[0], "【頁の回答】判断の見本")
        self.assertEqual(lines[1], "Q1. 配置はどれにするか: " + NONE_TEXT)
        self.assertEqual(lines[2], "Q2. 足すもの: " + NONE_TEXT)
        self.assertEqual(lines[3], "Q3-1. 主体の断絶: " + NONE_TEXT)
        self.assertEqual(lines[4], "Q3-2. 上限の単位: " + NONE_TEXT)
        self.assertEqual(lines[5], "Q4. 数を決める: " + NONE_TEXT)
        self.assertEqual(lines[6], "自由記述: (なし)")
        self.assertEqual(lines[-2:], ["---", CLOSING])
        self.assertEqual(result["errors"], [])

    def test_answers_notes_objection_and_free_text_make_the_fixed_form(self):
        steps = [
            {"op": "check", "sel": "input[name=decision]", "nth": 0},
            {"op": "fill", "sel": "input.q-note", "nth": 0, "value": "絵は小さくてよい"},
            {"op": "check", "sel": "input[name=decision-2]", "nth": 0},
            {"op": "check", "sel": "input[name=decision-2]", "nth": 1},
            {"op": "check", "sel": "input[name=decision-3-1]", "nth": 0},
            {"op": "fill", "sel": "input[type=number]", "nth": 0, "value": "2"},
            {"op": "check", "sel": "input[name=objection]", "nth": 0},
            {"op": "fill", "sel": ".obj-why", "nth": 0, "value": "前提が違う"},
            {"op": "fill", "sel": "#decision-objection", "nth": 0, "value": "全体として問題なし"},
            {"op": "click", "sel": "#copy-decision", "nth": 0},
        ]
        result = _run_in_browser(_page(), steps)

        self.assertEqual(
            result["answered"].split("\n"),
            [
                "【頁の回答】判断の見本",
                "Q1. 配置はどれにするか: 案A / 補足: 絵は小さくてよい",
                "Q2. 足すもの: 利点の欄、補足の欄",
                "Q3-1. 主体の断絶: 採用",
                "Q3-2. 上限の単位: " + NONE_TEXT,
                "Q4. 数を決める: 巡数=2回",
                "異議. 判定1は違う: 前提が違う",
                "自由記述: 全体として問題なし",
                "---",
                CLOSING,
            ],
        )
        self.assertEqual(result["errors"], [])

    def test_objection_without_a_reason_says_not_filled(self):
        result = _run_in_browser(_page(), [{"op": "check", "sel": "input[name=objection]", "nth": 0}])

        self.assertIn("異議. 判定1は違う: （未記入）", result["answered"])

    def test_q_note_alone_is_attached_after_the_scale_rows(self):
        result = _run_in_browser(
            _page(), [{"op": "fill", "sel": "input.q-note", "nth": 2, "value": "2件目は保留"}]
        )

        self.assertIn("Q3 補足. 個別の裁定: 2件目は保留", result["answered"])

    def test_answers_come_back_after_reload_and_clear_with_forget(self):
        steps = [
            {"op": "check", "sel": "input[name=decision]", "nth": 1},
            {"op": "fill", "sel": "input.q-note", "nth": 0, "value": "保存の確認"},
        ]
        result = _run_in_browser(_page(), steps)

        self.assertIn("Q1. 配置はどれにするか: 案B / 補足: 保存の確認", result["recalled"])
        self.assertIn("Q1. 配置はどれにするか: " + NONE_TEXT, result["forgotten"])
        self.assertNotIn("保存の確認", result["forgotten"])

    def test_question_numbers_run_through_the_whole_page_when_there_are_two_decision_sections(self):
        first = {"groups": [{"legend": "最初の問い", "kind": "radio", "options": ["甲", "乙"]}]}
        second = {"groups": [{"legend": "あとの問い", "kind": "checkbox", "options": ["丙", "丁"]}]}
        html = render_components(
            _plan("decision"),
            title="二つの節",
            content={
                "sections": [
                    {"component": "decision", "label": "選ぶこと その1", "content": first},
                    {"component": "decision", "label": "選ぶこと その2", "content": second},
                ]
            },
        )
        result = _run_in_browser(html, [{"op": "check", "sel": "input[type=checkbox]", "nth": 1}])

        self.assertIn("Q1. 最初の問い: " + NONE_TEXT, result["answered"])
        self.assertIn("Q2. あとの問い: 丁", result["answered"])


if __name__ == "__main__":
    unittest.main()

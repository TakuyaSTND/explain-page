"""判断の頁が組む「回答文」の固定形の検査（2026-10-08・赤ペン流の判断の頁／2026-10-09・見た・見ていない）。

固定形（頁ごとに同じ形・1通りに読める）：
  【頁の回答】<document.title>
  Q1. <問い>: <選んだ選択肢>、<選んだ選択肢> / 補足: <補足>
  Q2. <問い>: <未回答の4種のどれか>              ← 下の「未回答の4種」
  Q3-1. <段階評価の項目>: <選んだ段階>             ← 段階評価は群の番号に枝番
  Q4. <問い>: <数の名前>=<値><単位>、…
  異議. <対象>: <理由 or （未記入）>               ← 押した分だけ
  自由記述: <本文 or (なし)>                       ← 常に1行
  ---
  上の回答を反映して作業を続けてください。お任せの項目は推奨案で確定してください。

未回答の4種（問いを「見た」かどうか × 推奨があるかどうか）：
  (見たうえで推奨のまま) / (見ていない＝推奨で進めるが、大事なら会話で確かめる)
  (見たうえで未選択＝任せる) / (見ていない・推奨なし＝会話で確かめる)
「見た」＝問いが表示域の高さの半分以上に1秒出ていた、または問いの中を触った。

⚠️DECISION_SCRIPT は全頁共通の唯一の script＝構文の誤りで全頁の判断欄が黙って死ぬ。
だから node --check と、本物のブラウザで押して確かめる試験の両方を置く（無い環境では飛ばす）。
ブラウザの試験は時計を止めて（page.clock）進める＝「1秒」の前後を実時間に頼らず決められる。
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

SEEN_REC = "(見たうえで推奨のまま)"
UNSEEN_REC = "(見ていない＝推奨で進めるが、大事なら会話で確かめる)"
SEEN_NOREC = "(見たうえで未選択＝任せる)"
UNSEEN_NOREC = "(見ていない・推奨なし＝会話で確かめる)"
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
            SEEN_REC,
            UNSEEN_REC,
            SEEN_NOREC,
            UNSEEN_NOREC,
            "'---'",
            CLOSING,
            "q-note",
            "q-no",
            "IntersectionObserver",
            "異議. ",
            "自由記述: ",
            "(なし)",
        ):
            self.assertIn(part, DECISION_SCRIPT, part)

    def test_script_no_longer_has_the_old_unselected_text(self):
        self.assertNotIn("(未選択", DECISION_SCRIPT)

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
const height = Number(process.argv[4] || 900);
(async () => {
  let browser;
  try {
    browser = await chromium.launch({headless:true});
  } catch (error) {
    console.log(JSON.stringify({skip:String(error).slice(0,200)}));
    return;
  }
  try {
    const page = await browser.newPage({viewport:{width:1280,height}});
    const errors = [];
    page.on('pageerror', e => errors.push(String(e).slice(0,200)));
    // 時計を止めておく＝「1秒」の前後を実時間に頼らず決める。tick で進めた分だけ時間が経つ。
    const clock = !!page.clock;
    if (clock) {
      await page.clock.install({time:1000});
      await page.clock.pauseAt(2000);
    }
    await page.goto(pathToFileURL(htmlPath).href, {waitUntil:'load', timeout:8000});
    const prompt = page.locator('#decision-prompt').first();
    const initial = await prompt.textContent();
    const reads = {};
    for (const step of steps) {
      if (step.op === 'tick') {
        if (clock) await page.clock.runFor(step.ms); else await page.waitForTimeout(step.ms);
        continue;
      }
      if (step.op === 'read') { reads[step.key] = await prompt.textContent(); continue; }
      if (step.op === 'wait') { await page.waitForTimeout(step.ms); continue; }
      const loc = page.locator(step.sel).nth(step.nth || 0);
      if (step.op === 'check') await loc.check();
      else if (step.op === 'fill') await loc.fill(step.value);
      else if (step.op === 'click') await loc.click();
      else if (step.op === 'focus') await loc.focus();
      else if (step.op === 'jsclick') await loc.evaluate(el => el.click());  // 画面を動かさずに押す
      else if (step.op === 'scroll') {
        await loc.evaluate(el => el.scrollIntoView({block:'start'}));
        await page.waitForTimeout(200);
      }
    }
    const answered = await prompt.textContent();
    await page.reload({waitUntil:'load'});
    const recalled = await prompt.textContent();
    await page.locator('#forget-decision').first().click();
    const forgotten = await prompt.textContent();
    console.log(JSON.stringify({initial, answered, recalled, forgotten, reads, errors, clock}));
  } finally {
    await browser.close();
  }
})().catch(error => { console.log(JSON.stringify({fail:String(error).slice(0,300)})); process.exitCode = 1; });
"""


def _run_in_browser(html: str, steps: list[dict], height: int = 900) -> dict:
    playwright_path, reason = visual_smoke._resolve_playwright()
    if not playwright_path or not shutil.which("node"):
        raise unittest.SkipTest("Playwright か node が無い: %s" % (reason or ""))
    with tempfile.TemporaryDirectory(prefix="decision_reply_") as tmp:
        page_path = Path(tmp) / "page.html"
        page_path.write_text(html, encoding="utf-8")
        completed = subprocess.run(
            [
                "node",
                "-e",
                _BROWSER_SCRIPT,
                str(playwright_path),
                str(page_path),
                json.dumps(steps),
                str(height),
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
    if not result.get("clock"):
        # 「1秒」の前後を決めるので、時計を止められない版（Playwright 1.45 未満）では確かめられない。
        raise unittest.SkipTest("この Playwright には page.clock が無い")
    return result


def _pushed_down(html: str) -> str:
    """判断の節を下へ 3000px 押し下げる＝読み込み直後は問いが1つも表示域に入らない。"""
    marker = '<section data-component="decision"'
    return html.replace(marker, '<div style="height:3000px"></div>' + marker, 1)


def _lines(text: str) -> dict:
    """回答文を「Q1. 問い」→「答え」の辞書にする（問いの文は頁の legend のまま）。"""
    return {
        line.split(": ", 1)[0]: line.split(": ", 1)[1]
        for line in text.split("\n")
        if ": " in line
    }


class BrowserReplyTests(unittest.TestCase):
    def test_initial_text_lists_every_question_as_not_seen(self):
        result = _run_in_browser(_page(), [])

        lines = result["initial"].split("\n")
        self.assertEqual(lines[0], "【頁の回答】判断の見本")
        # 推奨のある問いは「推奨で進める」の文、推奨の無い問い（数）は「会話で確かめる」の文。
        self.assertEqual(lines[1], "Q1. 配置はどれにするか: " + UNSEEN_REC)
        self.assertEqual(lines[2], "Q2. 足すもの: " + UNSEEN_REC)
        self.assertEqual(lines[3], "Q3-1. 主体の断絶: " + UNSEEN_REC)
        self.assertEqual(lines[4], "Q3-2. 上限の単位: " + UNSEEN_REC)
        self.assertEqual(lines[5], "Q4. 数を決める: " + UNSEEN_NOREC)
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
                # 1行目を選んだので Q3 の問い全体は「見た」＝2行目は推奨があるまま「見たうえで」。
                "Q3-2. 上限の単位: " + SEEN_REC,
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

    def test_the_question_number_is_not_doubled_by_the_legend_badge(self):
        result = _run_in_browser(_page(), [])

        # legend の中の「Q1」の札は回答文の Q 番号と重ねない（「Q1. Q1配置…」にしない）。
        self.assertNotIn("Q1. Q1", result["initial"])
        self.assertNotIn("Q2. Q2", result["initial"])

    def test_answers_come_back_after_reload_and_clear_with_forget(self):
        steps = [
            {"op": "check", "sel": "input[name=decision]", "nth": 1},
            {"op": "fill", "sel": "input.q-note", "nth": 0, "value": "保存の確認"},
        ]
        result = _run_in_browser(_page(), steps)

        self.assertIn("Q1. 配置はどれにするか: 案B / 補足: 保存の確認", result["recalled"])
        self.assertIn("Q1. 配置はどれにするか: " + UNSEEN_REC, result["forgotten"])
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

        # 推奨の無い問い＝未回答は「任せる」でなく「会話で確かめる」側の文になる。
        self.assertIn("Q1. 最初の問い: " + UNSEEN_NOREC, result["answered"])
        self.assertIn("Q2. あとの問い: 丁", result["answered"])


class BrowserSeenTests(unittest.TestCase):
    """「見た」の判定＝表示域の半分以上に1秒、または問いの中を触った。"""

    def test_nothing_is_seen_while_the_questions_stay_below_the_fold(self):
        result = _run_in_browser(
            _pushed_down(_page()),
            [{"op": "tick", "ms": 1500}, {"op": "read", "key": "late"}],
            height=360,
        )

        for text in (result["initial"], result["reads"]["late"]):
            lines = _lines(text)
            self.assertEqual(lines["Q1. 配置はどれにするか"], UNSEEN_REC)
            self.assertEqual(lines["Q4. 数を決める"], UNSEEN_NOREC)
        self.assertEqual(result["errors"], [])

    def test_a_question_half_on_screen_for_one_second_becomes_seen_and_only_that_one(self):
        steps = [
            {"op": "scroll", "sel": "#q-1"},
            {"op": "tick", "ms": 1100},
            {"op": "read", "key": "after"},
        ]
        result = _run_in_browser(_pushed_down(_page()), steps, height=360)

        lines = _lines(result["reads"]["after"])
        self.assertEqual(lines["Q1. 配置はどれにするか"], SEEN_REC)
        # 下の問いは見え始めているだけ（半分に届かない）＝見たことにしない。
        self.assertEqual(lines["Q2. 足すもの"], UNSEEN_REC)
        self.assertEqual(lines["Q3-1. 主体の断絶"], UNSEEN_REC)
        self.assertEqual(lines["Q4. 数を決める"], UNSEEN_NOREC)

    def test_nine_hundred_milliseconds_is_not_enough(self):
        steps = [
            {"op": "scroll", "sel": "#q-1"},
            {"op": "tick", "ms": 900},
            {"op": "read", "key": "early"},
            {"op": "tick", "ms": 200},
            {"op": "read", "key": "late"},
        ]
        result = _run_in_browser(_pushed_down(_page()), steps, height=360)

        self.assertEqual(_lines(result["reads"]["early"])["Q1. 配置はどれにするか"], UNSEEN_REC)
        self.assertEqual(_lines(result["reads"]["late"])["Q1. 配置はどれにするか"], SEEN_REC)

    def test_scrolling_away_before_one_second_cancels_the_count(self):
        steps = [
            {"op": "scroll", "sel": "#q-1"},
            {"op": "tick", "ms": 600},
            {"op": "scroll", "sel": "header"},
            {"op": "tick", "ms": 1500},
            {"op": "read", "key": "after"},
        ]
        result = _run_in_browser(_pushed_down(_page()), steps, height=360)

        self.assertEqual(_lines(result["reads"]["after"])["Q1. 配置はどれにするか"], UNSEEN_REC)

    def test_touching_a_question_makes_it_seen_at_once_without_waiting(self):
        steps = [
            {"op": "focus", "sel": "input.q-note", "nth": 1},
            {"op": "focus", "sel": "input[type=number]", "nth": 0},
            {"op": "read", "key": "now"},
        ]
        result = _run_in_browser(_pushed_down(_page()), steps, height=900)

        lines = _lines(result["reads"]["now"])
        self.assertEqual(lines["Q2. 足すもの"], SEEN_REC)
        # 数の問いは推奨を持てない＝見ても「会話で確かめる」でなく「任せる」。
        self.assertEqual(lines["Q4. 数を決める"], SEEN_NOREC)
        self.assertEqual(lines["Q1. 配置はどれにするか"], UNSEEN_REC)

    def test_seen_comes_back_after_reload_and_forget_clears_it(self):
        steps = [
            {"op": "scroll", "sel": "#q-1"},
            {"op": "tick", "ms": 1100},
        ]
        result = _run_in_browser(_pushed_down(_page()), steps, height=360)

        self.assertEqual(_lines(result["recalled"])["Q1. 配置はどれにするか"], SEEN_REC)
        self.assertEqual(_lines(result["recalled"])["Q2. 足すもの"], UNSEEN_REC)
        self.assertEqual(_lines(result["forgotten"])["Q1. 配置はどれにするか"], UNSEEN_REC)

    def test_forget_cancels_a_count_that_is_already_running(self):
        steps = [
            {"op": "scroll", "sel": "#q-1"},
            {"op": "tick", "ms": 600},
            {"op": "jsclick", "sel": "#forget-decision"},
            {"op": "tick", "ms": 600},
            {"op": "read", "key": "after"},
        ]
        result = _run_in_browser(_pushed_down(_page()), steps, height=360)

        self.assertEqual(_lines(result["reads"]["after"])["Q1. 配置はどれにするか"], UNSEEN_REC)

    def test_forget_starts_counting_again_for_a_question_still_on_screen(self):
        steps = [
            {"op": "scroll", "sel": "#q-1"},
            {"op": "tick", "ms": 1100},
            {"op": "jsclick", "sel": "#forget-decision"},
            {"op": "read", "key": "right_after"},
            {"op": "wait", "ms": 300},
            {"op": "tick", "ms": 1100},
            {"op": "read", "key": "later"},
        ]
        result = _run_in_browser(_pushed_down(_page()), steps, height=360)

        self.assertEqual(_lines(result["reads"]["right_after"])["Q1. 配置はどれにするか"], UNSEEN_REC)
        self.assertEqual(_lines(result["reads"]["later"])["Q1. 配置はどれにするか"], SEEN_REC)

    def test_select_all_recommended_does_not_count_as_seeing(self):
        result = _run_in_browser(_page(), [{"op": "click", "sel": "#recommend-decision"}])

        self.assertEqual(
            result["answered"].split("\n")[:6],
            [
                "【頁の回答】判断の見本",
                "Q1. 配置はどれにするか: 案A",
                "Q2. 足すもの: 利点の欄",
                "Q3-1. 主体の断絶: 採用",
                "Q3-2. 上限の単位: 割引採用",
                # 推奨の無い問い（数）は選ばれない＝見たことにもならない。
                "Q4. 数を決める: " + UNSEEN_NOREC,
            ],
        )


class QuestionNumberingTests(unittest.TestCase):
    def test_every_answerable_group_gets_an_anchor_and_a_number_in_its_legend(self):
        html = _page()

        self.assertIn('<fieldset id="q-1"><legend><span class="q-no">Q1</span>配置はどれにするか</legend>', html)
        self.assertIn('<fieldset id="q-2"><legend><span class="q-no">Q2</span>足すもの</legend>', html)
        self.assertIn('<fieldset id="q-3"><legend><span class="q-no">Q3</span>個別の裁定</legend>', html)
        self.assertIn('<fieldset id="q-4"><legend><span class="q-no">Q4</span>数を決める</legend>', html)
        # 自由記述と異議の群には付けない。
        self.assertNotIn('id="q-5"', html)

    def test_two_decision_sections_number_their_questions_through_the_page(self):
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

        self.assertEqual(html.count('id="q-1"'), 1)
        self.assertEqual(html.count('id="q-2"'), 1)
        self.assertLess(html.index('id="q-1"'), html.index('id="q-2"'))
        self.assertIn('<span class="q-no">Q2</span>あとの問い', html)


if __name__ == "__main__":
    unittest.main()

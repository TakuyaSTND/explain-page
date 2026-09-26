"""ラベル側の用語と、説明の吹き出しの検査（2026-08-31 他セッションの報告から）。

別セッション（session-15）が頁5枚中4枚で差し戻され、原因を2つ報告してきた。
こちらで両方**再現してから**直した。

**穴(a)＝ラベルは `escape()` だけを通り、用語の包装をすり抜けていた。**
   ∴用語集の語の**初出がラベル側**にあると「未包装」で検品証が落ちる。
   ⚠️こちらも同じ穴で2回止まっており、「ラベルに用語集の語を使わない」という
   **書く側の約束**で回避していた＝道具側の穴を人の規律で埋めていた。

**穴(b)＝吹き出しが、用語が右端に来ると頁の外まで伸びる。**
   実測（1280x900・用語の右端 x=919）＝ホバー中に15px溢れ、吹き出しを消すと0pxに戻った。
   ⚠️静止状態では `display:none` なので溢れない＝**触った時だけ**出る。
   ∴静止状態だけを測る検査では永久に見つからない。
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
from visual.render_components import render_components

NL = chr(10)
TERM = "検品証"
DESC = "出したHTMLが条件を満たしているか機械が調べて残す記録。"
ENTRIES = {TERM: GlossaryEntry(term=TERM, description=DESC, provenance="test")}


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


def _render(components, content):
    return render_components(
        _plan(*components), title="題", content=content, glossary_entries=ENTRIES
    )


class LabelsGetWrappedTests(unittest.TestCase):
    """5つのラベルの置き場すべてで、用語の初出が包まれる。"""

    def test_the_item_row_label_is_wrapped(self):
        html = _render(("progress",), {"progress": TERM + "：残っているもの。"})

        self.assertIn('class="item-label">', html)
        self.assertIn('<span class="t"', html)
        self.assertIn(DESC, html)

    def test_the_signboard_label_is_wrapped(self):
        html = _render(("summary",), {"summary": TERM + "：目的。"})

        self.assertIn('class="gnc"', html)
        self.assertIn('<span class="t"', html)

    def test_the_step_title_is_wrapped(self):
        html = _render(("walkthrough",), {"walkthrough": TERM + "：本文。"})

        self.assertIn('class="ttl"', html)
        self.assertIn('<span class="t"', html)

    def test_the_glossary_term_is_wrapped(self):
        html = _render(("glossary",), {"glossary": TERM + "：" + DESC})

        self.assertIn("<dt>", html)
        self.assertIn('<span class="t"', html)

    def test_a_term_that_only_appears_in_a_label_still_passes_inspection(self):
        # ⚠️これが実際に落ちていた形＝本文には出さず、ラベルにだけ用語を置く。
        html = _render(
            ("summary", "progress"),
            {"summary": "Goal：目的。", "progress": "未" + TERM + "：残り。"},
        )
        inspection = inspect_artifact_html(
            html, required_components=("summary", "progress"), glossary_entries=ENTRIES
        )

        self.assertEqual(list(inspection.unwrapped_identifiers), [])
        self.assertEqual(inspection.errors, ())

    def test_the_term_is_still_wrapped_only_once(self):
        html = _render(
            ("progress", "walkthrough"),
            {"progress": TERM + "：一度目。", "walkthrough": "見出し：二度目の" + TERM + "。"},
        )

        self.assertEqual(html.count('<span class="t"'), 1)


class TooltipStaysInsideThePageTests(unittest.TestCase):
    """穴(b)＝吹き出しが頁の外へ出ないようにする仕掛けが載っている。"""

    def setUp(self):
        self.html = _render(("walkthrough",), {"walkthrough": "見出し：本文の" + TERM + "。"})

    def test_the_flip_rule_exists_and_is_desktop_only(self):
        # ⚠️狭い画面の指定（position:fixed で左右1remに固定）を上書きしてはいけない。
        self.assertIn("@media(min-width:601px)", self.html)
        self.assertIn('.t[data-flip]::after{left:auto;right:0}', self.html)

    def test_the_script_measures_the_fragments_not_the_bounding_box(self):
        # ⚠️行をまたぐ用語では合併した矩形の left が吹き出しの起点と一致しない。
        self.assertIn("getClientRects()", self.html)
        self.assertIn("data-flip", self.html)

    def test_no_extra_script_is_added(self):
        self.assertEqual(self.html.count("<script>"), 1)

    def test_the_tooltip_is_hidden_until_touched(self):
        # 静止状態で場所を取ると、それだけで横溢れになる（2026-08-29に直した件）。
        self.assertIn("box-shadow:0 6px 20px rgba(0,0,0,.22);display:none", self.html)
        self.assertIn(".t:hover::after,.t:focus::after{display:block}", self.html)

class NonProsePlacesAreNotWrappedTests(unittest.TestCase):
    """2026-09-01 ユーザー裁定＝**既定を「包まない」にし、本文だけ包む**。

    ⚠️それまでは「包む場所」を列挙して潰していた＝**列挙漏れがそのまま穴**になり、
      9回直した末に10箇所目（色札の中）が出た。∴向きを逆にした。
      検査器が包装を求めるのは `<p>` `<li>` `<blockquote>` の中だけで、
      表の欄・出所欄・色札・コード書きは対象外＝取りこぼしても穴にならない。

    ⚠️この組は**以前と逆のことを固定している**。前の版は「出所欄も包む」を固定していた。
      裁定で方針が反転したので、検査も反転させた（古い方針の検査を残すと裁定に逆らう）。
    """

    def test_a_path_in_the_source_column_is_left_alone(self):
        html = _render(("evidence",), {"evidence": "実測：内容｜notes/" + TERM + "-a.md"})
        source = html[html.index('class="source"'):]
        source = source[: source.index("</td>")]

        self.assertNotIn('<span class="t"', source)
        # ⚠️機械が読む属性は元の道筋のまま（ここは前から変えていない）。
        self.assertIn('data-source="notes/' + TERM + '-a.md"', html)

    def test_the_evidence_kind_cell_is_left_alone(self):
        html = _render(("evidence",), {"evidence": TERM + "：内容｜notes/a.md"})
        cell = html[html.index('data-label="種類"'):]
        cell = cell[: cell.index("</td>")]

        self.assertNotIn('<span class="t"', cell)

    def test_a_term_inside_a_code_span_is_left_alone(self):
        backtick = chr(96)
        html = _render(
            ("walkthrough",),
            {"walkthrough": "見出し：道具は " + backtick + "lib/" + TERM + ".py" + backtick + " を使う。"},
        )

        self.assertIn("<code>lib/" + TERM + ".py</code>", html)

    def test_a_code_span_that_is_exactly_a_term_is_still_wrapped(self):
        # 丸ごと一致するときだけは包む＝説明が的を外さないため。
        backtick = chr(96)
        html = _render(("walkthrough",), {"walkthrough": "見出し：" + backtick + TERM + backtick + "。"})

        self.assertIn("<code>", html)
        self.assertEqual(html.count('<span class="t"'), 1)

    def test_the_inspector_does_not_ask_for_wrapping_outside_prose(self):
        """⚠️ここが裁定の核心＝包まなくても検品が落ちない。"""
        html = _render(
            ("evidence", "details"),
            {
                "evidence": TERM + "：内容｜notes/" + TERM + "-a.md",
                "details": [{"summary": TERM + "の細部", "table": {"head": [TERM], "rows": [[TERM]]}}],
            },
        )
        inspection = inspect_artifact_html(
            html, required_components=("evidence", "details"), glossary_entries=ENTRIES
        )

        self.assertEqual(list(inspection.unwrapped_identifiers), [])
        self.assertEqual(inspection.errors, ())

    def test_the_inspector_still_asks_for_wrapping_in_prose(self):
        """⚠️本文では今までどおり求める＝**緩めただけ**にしないための対の検査。"""
        html = _render(("walkthrough",), {"walkthrough": "見出し：本文に" + TERM + "を書く。"})
        stripped = html.replace(
            '<span class="t" tabindex="0" data-d="' + DESC + '" aria-label="'
            + TERM + "：" + DESC + '">' + TERM + "</span>",
            TERM,
        )
        inspection = inspect_artifact_html(
            stripped, required_components=("walkthrough",), glossary_entries=ENTRIES
        )

        self.assertEqual(list(inspection.unwrapped_identifiers), [TERM])


class TheSmokeTestLooksAtOpenTooltipsTests(unittest.TestCase):
    """検出の穴＝溢れを触る前だけ測っていた（2026-08-31）。

    ⚠️吹き出しは触った時にだけ出るので、開いた状態の溢れを一度も見ていなかった。
      逆に以前 `visibility:hidden` だった頃は静止状態で溢れたのでここで捕まっていた
      ＝どちらの作りでも捕まるように、開いた状態でも測るようにした。
    """

    def test_the_runner_hovers_the_riskiest_terms_and_remeasures(self):
        source = (HOOKS_DIR / "visual" / "visual_smoke.py").read_text(encoding="utf-8")

        self.assertIn("tooltip-overflow", source)
        self.assertIn("getClientRects()", source)
        # ⚠️全部触ると実行器が落ちた（実測）。数を絞る指定が消えていないか見る。
        self.assertIn("slice(0, 6)", source)
        self.assertIn("width >= 601", source)



if __name__ == "__main__":
    unittest.main()

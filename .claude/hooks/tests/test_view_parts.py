"""見せ方の部品の検査（2026-10-31・利用者の思想＝認知負荷を下げる二重構造・案V1〜V9）。

本質は図と強調で一目に、詳細は文章で全部読める頁にするための部品：
中心メッセージ（カードの key）・強調の役割（[[num:…]]・[[risk:…]]）・ⓘ（[[info:…]]）・横の段組み・
タブ（tabs）・根拠と用語の折りたたみ・上部の操作バーと表示の script（VIEW_SCRIPT）・点検（page_lint）。
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

HOOKS_DIR = Path(__file__).resolve().parents[1]
if str(HOOKS_DIR) not in sys.path:
    sys.path.insert(0, str(HOOKS_DIR))

from visual import page_lint
from visual.artifact_inspection import APPROVED_SCRIPTS, inspect_artifact_html
from visual.contracts import ExplanationPlan
from visual.render_components import DECISION_SCRIPT, VIEW_SCRIPT, render_components


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


def _page(content, *components):
    return render_components(_plan(*components), title="題", content=content)


class KeyMessageTests(unittest.TestCase):
    """案V1：1カード1メッセージ。"""

    def test_card_key_is_rendered_above_the_body(self):
        html = _page({"visual": [{"cards": [{"title": "問い", "key": "中心の1行", "text": "詳細の文章"}]}]}, "visual")
        self.assertIn('<p class="card-key">中心の1行</p><p class="card-body">詳細の文章</p>', html)

    def test_card_without_key_keeps_the_body(self):
        html = _page({"visual": [{"cards": [{"title": "問い", "text": "詳細の文章"}]}]}, "visual")
        self.assertIn('<p class="card-body">詳細の文章</p>', html)
        self.assertNotIn('class="card-key"', html)

    def test_full_span_card(self):
        html = _page({"visual": [{"cards": [{"title": "広い", "text": "本文", "span": "full"}]}]}, "visual")
        self.assertIn('data-span="full"', html)


class EmphasisRoleTests(unittest.TestCase):
    """案V2・V5：数・リスク・ⓘ の印。"""

    def test_num_risk_and_info_markup(self):
        html = _page({"walkthrough": "費用：[[num:6.8万]]円で[[risk:増える]]。[[info:1件だけで測った]]"}, "walkthrough")
        self.assertIn('<b class="em-num">6.8万</b>', html)
        self.assertIn('<b class="em-risk">増える</b>', html)
        self.assertIn('class="ii" tabindex="0" role="note" aria-label="補足：1件だけで測った" data-info="1件だけで測った">i</span>', html)

    def test_dim_markup_is_muted_and_escaped(self):
        # G1（2026-11-06）：[[dim:…]] は文を薄く出す（色だけ・中身は残す・中の文字はエスケープ）。
        html = _page({"walkthrough": "趨勢：[[dim:要約だけで<書いた>文]]。"}, "walkthrough")
        self.assertIn('<span class="em-dim">要約だけで&lt;書いた&gt;文</span>', html)
        self.assertIn(".em-dim{color:var(--ink-3)}", html)

    def test_info_text_is_escaped(self):
        html = _page({"walkthrough": "a：[[info:<b>危ない\"文</b>]]"}, "walkthrough")
        self.assertNotIn("<b>危ない", html)
        self.assertIn("&lt;b&gt;危ない&quot;文&lt;/b&gt;", html)


class TabsAndFoldTests(unittest.TestCase):
    """案V7：タブ。案V4：根拠と用語は初めは畳む。"""

    def test_tabs_render_buttons_and_panels_with_titles(self):
        html = _page({"visual": [{"tabs": [
            {"label": "資料1", "content": [{"cards": [{"title": "甲", "text": "一"}]}]},
            {"label": "資料2", "content": "本文2"},
        ]}]}, "visual")
        self.assertIn('<div class="tabs" data-tabs><div class="tab-list" role="tablist">', html)
        self.assertIn('<button type="button" role="tab" class="tab" aria-selected="true" data-tab="0">資料1</button>', html)
        self.assertIn('<div class="tab-panel on" role="tabpanel" data-panel="0"><h3 class="tab-title">資料1</h3>', html)
        self.assertIn('<div class="tab-panel" role="tabpanel" data-panel="1"><h3 class="tab-title">資料2</h3>', html)

    def test_evidence_and_glossary_are_folded_with_counts(self):
        html = _page({
            "evidence": ["実測：一｜a.py", "確認済み：二｜b.py"],
            "glossary": "甲：説明\n乙：説明",
        }, "evidence", "glossary")
        self.assertIn('<details class="fold" data-fold><summary>開いて読む（2行）</summary>', html)
        self.assertIn('<details class="fold" data-fold><summary>開いて読む（2語）</summary>', html)


class ViewBarAndScriptTests(unittest.TestCase):
    """案V6・V7：上部の操作バーと、表示の script（全頁共通の2本目）。"""

    def test_view_bar_and_script_are_on_every_page(self):
        html = _page({"walkthrough": "a：b"}, "walkthrough")
        self.assertIn('<nav id="view-bar" class="view-bar"', html)
        self.assertIn('id="vb-mode"', html)
        self.assertNotIn('class="vb-go"', html, "判断欄の無い頁には「判断へ」を出さない")
        self.assertLess(html.index(DECISION_SCRIPT), html.index(VIEW_SCRIPT))

    def test_decision_page_has_jump_link(self):
        html = _page({"decision": {"options": ["案A", "案B"]}}, "decision")
        self.assertIn('<a class="vb-go" href="#q-1">判断へ</a>', html)

    def test_view_script_is_approved_second_and_page_passes_inspection(self):
        self.assertEqual([role for role, _ in APPROVED_SCRIPTS][:2], ["decision", "view"])
        self.assertNotIn("onclick", VIEW_SCRIPT)
        html = _page({"walkthrough": "a：b", "evidence": ["実測：一｜a.py"]}, "walkthrough", "evidence")
        result = inspect_artifact_html(html, required_components=("walkthrough", "evidence"), glossary_entries={})
        self.assertEqual(result.errors, ())
        self.assertEqual(result.missing_evidence_sources, ())

    def test_print_and_key_view_css_present(self):
        html = _page({"walkthrough": "a：b"}, "walkthrough")
        self.assertIn('html[data-view="key"] .card:has(.card-key)>.card-body', html)
        self.assertIn('.tab-panel{display:flex !important}', html)
        # カードは横に2列まで（2026-10-31 利用者のレビュー）＝列の最小幅を半分以上にする。
        self.assertIn('minmax(max(19rem,calc((100% - .8rem)/2)),1fr)', html)
        # 絵の無い案のカードと、判断欄の選択肢も、広い画面では2列（2026-10-31）。
        self.assertIn('section .props{display:grid;grid-template-columns:repeat(auto-fit,minmax(max(19rem,calc((100% - 1rem)/2)),1fr))}', html)
        self.assertIn('fieldset:has(>label.choice+label.choice){display:grid;grid-template-columns:repeat(2,minmax(0,1fr))', html)
        # 図を含む段組みは 1000px 未満で縦に積む（図の縮みは1割まで）。
        self.assertIn('@media(max-width:999px){.cols[data-cols]:has(svg.svg-in', html)


class LinkWalkSideTests(unittest.TestCase):
    """案M1（図の箱と本文をつなぐ）・M4（同じ図で一段ずつ）・M2 の窓（縦のタブ）。2026-10-31。"""

    DIAGRAM = {"diagram": {
        "nodes": [{"id": "a", "label": "取り込み", "ref": "s1"}, {"id": "b", "label": "批評", "ref": "s2"}],
        "edges": [{"from": "a", "to": "b"}],
        "walk": [{"ref": "s1", "title": "取り込み", "text": "資料を読む"}, {"ref": "s2", "title": "批評", "text": "指摘を出す"}],
    }}

    def test_boxes_and_blocks_carry_the_same_ref(self):
        html = _page({"visual": [self.DIAGRAM, {"ref": "s1", "text": "取り込みの説明"}]}, "visual")
        self.assertIn('data-ref="s1"', html.split("<svg", 1)[1].split("</svg>", 1)[0])
        self.assertIn('<div class="ref-blk" data-ref="s1">', html)

    def test_walk_has_one_button_per_step_and_all(self):
        html = _page({"visual": [self.DIAGRAM]}, "visual")
        self.assertIn('<div class="walk" data-walk>', html)
        self.assertIn('<button type="button" aria-pressed="true">全部</button>', html)
        self.assertEqual(html.count('class="walk-step"'), 2)
        self.assertIn('<li class="walk-step" data-ref="s2"><b>批評</b>：指摘を出す</li>', html)

    def test_unsafe_ref_is_dropped(self):
        html = _page({"visual": [{"ref": 'x" onclick="a', "text": "本文"}]}, "visual")
        self.assertNotIn("onclick", html.split("<script>", 1)[0])
        self.assertNotIn('class="ref-blk"', html)

    def test_side_tabs_mark_the_layout(self):
        html = _page({"visual": [{"tabs": [{"label": "指摘1", "content": "本文"}, {"label": "指摘2", "content": "本文"}], "layout": "side"}]}, "visual")
        self.assertIn('<div class="tabs" data-tabs data-layout="side">', html)
        self.assertIn('.tabs[data-layout="side"]{display:grid', html)

    def test_a_block_with_fold_starts_closed(self):
        # 2026-10-31（K4）：塊の `fold` は初めは畳む（開けば全部読める）。
        html = _page({"visual": [{"fold": "記録の表を開く（2行）", "table": {"head": ["欄", "内容"], "rows": [["a", "b"], ["c", "d"]]}}]}, "visual")
        self.assertIn('<details class="fold" data-fold><summary>記録の表を開く（2行）</summary>', html)

    def test_view_script_links_refs_and_walks(self):
        for needle in ("refOn", "[data-walk]", "ArrowDown"):
            self.assertIn(needle, VIEW_SCRIPT)


class LintTests(unittest.TestCase):
    """案V9：思想を機械で守る点検（止めはしない）。"""

    def test_card_without_key_is_reported(self):
        content = {"sections": [{"component": "visual", "content": [{"cards": [{"title": "t", "text": "あ" * 130}]}]}]}
        self.assertTrue(page_lint.card_key_warnings(content))
        content["sections"][0]["content"][0]["cards"][0]["key"] = "中心"
        self.assertEqual(page_lint.card_key_warnings(content), [])

    def test_plain_long_text_is_reported(self):
        self.assertTrue(page_lint.plain_text_warnings({"overview": "あ" * 220}))
        self.assertEqual(page_lint.plain_text_warnings({"overview": "**中心。**" + "あ" * 220}), [])

    def test_long_aside_is_reported(self):
        self.assertTrue(page_lint.long_aside_warnings({"overview": "本文（" + "補" * 45 + "）。"}))
        self.assertEqual(page_lint.long_aside_warnings({"overview": "本文（短い）。"}), [])


if __name__ == "__main__":
    unittest.main()

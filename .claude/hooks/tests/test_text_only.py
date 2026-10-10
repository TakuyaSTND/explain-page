"""文字だけの版（<name>-text.txt）の試験（2026-10-09・試問の費用を下げる Q1）。

何を守るか＝判断の頁の試問は、頁を読むのに掛かる費用が大きい（画像の data: 、図の svg、script、
style が頁の大半）。そこで頁を組む道具が、画像・図・script・style・釦・回答文の欄を外した
本文だけの版を、完全版の隣へ書く。試問の読み手にはそれを読ませる。
外すものは外れ、読む手掛かり（見出し・表の行・選択肢の記号・用語の印・画像の説明）は残ること。
この試験の手書きの頁は render_components に頼らない（組む側が変わっても、この検査は動く）。
"""
from __future__ import annotations

import contextlib
import io
import json
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch

HOOKS_DIR = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = HOOKS_DIR.parent / "scripts"
for _entry in (str(HOOKS_DIR), str(SCRIPTS_DIR)):
    if _entry not in sys.path:
        sys.path.insert(0, _entry)

import render_page as rp  # noqa: E402

BIG_IMAGE = "data:image/png;base64," + "QUJD" * 2000

PAGE = (
    "<!doctype html><html><head><meta charset=\"utf-8\"><title>見本の頁</title>"
    "<style>.x{color:red}.dia{margin:0}</style></head><body>"
    "<div class=\"wrap\"><header data-component=\"overview\">"
    "<div class=\"head-row\"><p class=\"eyebrow\">小さい行</p>"
    "<button id=\"theme-toggle\" type=\"button\">明暗を切り替える</button></div>"
    "<h1>結論の1文</h1><p class=\"lede\">要点は<span class=\"t\" tabindex=\"0\" data-d=\"説明の文\" "
    "aria-label=\"語：説明の文\">検品証</span>が通ること。</p></header>"
    "<main class=\"flow\">"
    "<section data-component=\"summary\" id=\"sec-1\"><h2><span class=\"sec-no\">零</span>3行でいうと</h2>"
    "<div class=\"item-row\"><strong class=\"item-label\">Goal</strong>"
    "<span class=\"item-copy\">目的の文</span></div></section>"
    "<section data-component=\"visual\" id=\"sec-2\"><h2>図と画像</h2>"
    "<div class=\"dia-wrap\"><svg class=\"dia\" viewBox=\"0 0 10 10\" role=\"img\" aria-label=\"図の題の代わり\">"
    "<title>流れの図</title><path d=\"M 0 0 L 5 5\"></path>"
    "<g><title>用語：箱の説明</title><rect x=\"1\" y=\"1\" width=\"3\" height=\"3\"></rect>"
    "<text x=\"1\" y=\"1\"><tspan>受け取る</tspan></text>"
    "<text x=\"1\" y=\"2\"><tspan>調べる</tspan></text></g></svg></div>"
    "<figure class=\"img-figure\"><div class=\"img-frame\" data-zoom=\"1\">"
    "<img src=\"" + BIG_IMAGE + "\" alt=\"画面の見本\" width=\"10\" height=\"10\">"
    "<svg class=\"marks\" viewBox=\"0 0 10 10\"><circle cx=\"1\" cy=\"1\" r=\"2\"></circle>"
    "<text x=\"1\" y=\"1\">1</text></svg></div>"
    "<figcaption>図1｜画面の見本｜出所：撮影</figcaption></figure></section>"
    "<section data-component=\"evidence\" id=\"sec-3\"><h2>根拠</h2>"
    "<div class=\"scroll\"><table><caption>表の題</caption>"
    "<thead><tr><th>種類</th><th>内容</th><th>出所</th></tr></thead>"
    "<tbody><tr><td data-label=\"種類\"><span class=\"src s-m\">実測</span></td>"
    "<td data-label=\"内容\">試験が合格<br><span class=\"badge b-good\">完了</span></td>"
    "<td data-label=\"出所\"><code>a/b.py</code></td></tr></tbody></table></div></section>"
    "<section data-component=\"decision\" id=\"sec-4\"><h2>選ぶこと</h2>"
    "<fieldset><legend><span class=\"q-no\">Q1</span>配置はどれにするか</legend>"
    "<label class=\"choice\"><input type=\"radio\" name=\"decision\" data-req=\"1\" data-label=\"案A\" data-rec=\"1\">"
    "<span><span class=\"badge b-good recommendation\">推奨</span> 案A 左に一覧"
    "<span class=\"pros-cons\"><b class=\"pro\">利点</b> 速い<br><b class=\"con\">代償</b> 狭い</span></span></label>"
    "<label class=\"choice\"><input type=\"radio\" name=\"decision\" data-req=\"1\" data-label=\"案B\">"
    "<span>案B 上に帯</span></label>"
    "<input type=\"text\" class=\"q-note\" data-q=\"1\" placeholder=\"補足（任意）\" aria-label=\"補足\"></fieldset>"
    "<fieldset><legend>足すもの</legend><label class=\"choice\"><input type=\"checkbox\" name=\"decision-2\" "
    "data-req=\"1\" data-label=\"甲\"><span>甲の欄</span></label>"
    "<label class=\"choice number-row\"><span>巡数</span><input type=\"number\" name=\"decision-number\" "
    "data-req=\"1\" data-label=\"試問の巡数\"><span class=\"unit\">回</span></label></fieldset>"
    "<fieldset><legend>自由記述</legend><label class=\"objection-freeform\" for=\"decision-objection\">追加条件</label>"
    "<textarea id=\"decision-objection\" name=\"objection\" rows=\"4\">下書きの文</textarea></fieldset>"
    "<pre id=\"decision-prompt\" aria-live=\"polite\">選択してください。</pre>"
    "<div class=\"decision-actions\"><button id=\"copy-decision\" type=\"button\">依頼文をコピー</button></div>"
    "</section>"
    "<section data-component=\"details\" id=\"sec-5\"><h2>詳細</h2><details><summary>折りたたみ</summary>"
    "<ul><li>一つ目<ul><li>入れ子の二つ目</li></ul></li><li>三つ目</li></ul>"
    "<blockquote>引用の文</blockquote></details></section>"
    "</main></div>"
    "<script>const secret = 'スクリプトの中の文'; if (a < b) { x = '<p>'; }</script>"
    "</body></html>"
)


def _text(page=PAGE, name="sample"):
    return rp.text_only(page, name)


class WhatIsRemovedTests(unittest.TestCase):
    def test_no_angle_bracket_and_no_data_uri_remains(self):
        text = _text()

        self.assertNotIn("<", text)
        self.assertNotIn(">", text.replace("> 引用の文", ""))
        self.assertNotIn("data:", text)
        self.assertNotIn("base64", text)

    def test_script_style_and_buttons_are_gone(self):
        text = _text()

        self.assertNotIn("スクリプトの中の文", text)
        self.assertNotIn("color:red", text)
        self.assertNotIn("明暗を切り替える", text)
        self.assertNotIn("依頼文をコピー", text)

    def test_the_reply_box_and_the_action_row_are_gone(self):
        text = _text()

        self.assertNotIn("選択してください。", text)

    def test_explanation_text_of_terms_is_not_carried(self):
        text = _text()

        self.assertNotIn("説明の文", text)
        self.assertIn("検品証〔用語〕が通ること", text)

    def test_the_head_and_title_elements_are_not_read(self):
        text = _text()

        self.assertNotIn("見本の頁", text.replace("元の頁: sample.html", ""))

    def test_much_smaller_than_the_full_page(self):
        text = _text()

        self.assertLess(len(text.encode("utf-8")) * 3, len(PAGE.encode("utf-8")))


class WhatIsKeptTests(unittest.TestCase):
    def test_header_line_comes_first_and_names_the_original(self):
        text = _text()

        first = text.splitlines()[0]
        self.assertEqual(
            first,
            "（文字だけの版＝画像・図・script・style を外した本文。〔用語〕はホバーで説明の付く語。"
            "元の頁: sample.html）",
        )

    def test_headings_get_hash_marks_and_the_section_number_is_bracketed(self):
        text = _text()

        self.assertIn("\n# 結論の1文\n", text)
        self.assertIn("\n## [零] 3行でいうと\n", text)
        self.assertIn("\n## 選ぶこと\n", text)

    def test_terms_are_marked(self):
        self.assertIn("検品証〔用語〕", _text())

    def test_item_rows_keep_label_and_copy_on_one_line(self):
        self.assertIn("\nGoal：目的の文\n", _text())

    def test_svg_keeps_its_title_and_inner_text(self):
        text = _text()

        self.assertIn("[図: 流れの図｜文字: 受け取る／調べる]", text)
        self.assertNotIn("箱の説明", text)

    def test_image_keeps_only_its_alt_and_the_marks_numbers(self):
        text = _text()

        self.assertIn("[画像: 画面の見本]", text)
        self.assertIn("[画像の印: 1]", text)
        self.assertIn("図1｜画面の見本｜出所：撮影", text)

    def test_a_table_row_is_one_line_with_cells_joined(self):
        text = _text()

        self.assertIn("\n種類｜内容｜出所\n", text)
        self.assertIn("\n実測｜試験が合格 [完了]｜a/b.py\n", text)
        self.assertIn("\n表の題\n", text)

    def test_choices_use_radio_and_checkbox_marks_and_keep_pros_and_cons_on_the_line(self):
        text = _text()

        self.assertIn("[Q1] 配置はどれにするか", text)
        self.assertIn("( ) [推奨] 案A 左に一覧 利点： 速い ／ 代償： 狭い", text)
        self.assertIn("\n( ) 案B 上に帯\n", text)
        self.assertIn("[ ] 甲の欄", text)

    def test_number_note_and_free_text_boxes_are_marked(self):
        text = _text()

        self.assertIn("[補足欄]", text)
        self.assertIn("[数: 試問の巡数]", text)
        self.assertIn("[自由記述欄]", text)
        self.assertNotIn("下書きの文", text)

    def test_nested_lists_and_quotes(self):
        text = _text()

        self.assertIn("\n- 一つ目\n", text)
        self.assertIn("\n- 入れ子の二つ目\n", text)
        self.assertIn("\n- 三つ目\n", text)
        self.assertIn("\n> 引用の文\n", text)
        self.assertIn("\n折りたたみ\n", text)

    def test_no_run_of_blank_lines_and_a_single_trailing_newline(self):
        text = _text()

        self.assertNotIn("\n\n\n", text)
        self.assertTrue(text.endswith("\n"))
        self.assertFalse(text.endswith("\n\n"))

    def test_only_lf_line_endings(self):
        self.assertNotIn("\r", _text())

    def test_a_fragment_without_a_body_tag_still_reads(self):
        text = rp.text_only("<h2>見出し</h2><p>本文</p>")

        self.assertIn("## 見出し", text)
        self.assertIn("本文", text)
        self.assertNotIn("元の頁", text)

    def test_one_br_inside_a_pros_cons_stays_on_the_choice_line(self):
        page = (
            '<label><input type="radio"><span>案<span class="pros-cons"><b class="pro">利点</b> 良い<br>'
            '<b class="con">代償</b> 悪い</span></span></label><label><input type="radio"><span>次</span></label>'
        )

        text = rp.text_only(page)

        self.assertIn("( ) 案 利点： 良い ／ 代償： 悪い\n( ) 次", text)

    def test_a_bold_label_followed_by_a_span_gets_a_space(self):
        text = rp.text_only("<div><b>GOAL</b><span>目的</span></div><div><b>NOW</b><span>現在</span></div>")

        self.assertIn("GOAL 目的\nNOW 現在", text)

    def test_text_inside_pre_and_code_is_kept_as_written(self):
        text = rp.text_only("<pre class=\"log\">一行目\n二行目 a &lt; b</pre><p><code>x.py</code></p>")

        self.assertIn("一行目 二行目 a < b", text)
        self.assertIn("x.py", text)


class FilesAndMainTests(unittest.TestCase):
    def test_the_text_file_sits_beside_the_page_with_the_text_suffix(self):
        with tempfile.TemporaryDirectory() as td:
            full = Path(td) / "my-page.html"
            full.write_text(PAGE, encoding="utf-8")

            path = rp.write_text_only(str(full))

            self.assertEqual(Path(path), Path(td) / "my-page-text.txt")
            self.assertEqual(rp.text_path_for(str(full)), path)
            raw = Path(path).read_bytes()
            self.assertNotIn(b"\r", raw)
            body = raw.decode("utf-8")
            self.assertIn("元の頁: my-page.html", body)
            self.assertLess(len(raw), full.stat().st_size)

    def test_main_writes_a_text_file_next_to_the_page_and_names_it_in_the_output(self):
        spec = {
            "name": "text-only-check",
            "title": "文字だけの版の確認",
            "components": list(rp.ALL_COMPONENTS),
            "reasons": ["project_novice_default"],
            "publish": "never",
            "content": {
                "overview": "文字だけの版の確認用の頁である。",
                "summary": "Goal：確かめる。\nNow：試験中である。",
                "walkthrough": "手順一：試験のための本文である。",
                "examples": "例一：試験のための本文である。",
                "progress": "現在地：試験中である。",
                "visual": "図の見本：試験のための本文である。",
                "decision": {"groups": [{"legend": "進め方", "kind": "radio", "options": [
                    {"label": "案A", "recommended": True, "pros": "速い"},
                    {"label": "案B", "pros": "丁寧"},
                ]}]},
                "evidence": "実測：試験のための値である｜.claude/hooks/tests/test_text_only.py",
                "glossary": "用語一：試験のための説明である。",
                "details": "記録：試験のための詳細である。",
            },
        }
        fake_smoke = types.SimpleNamespace(status="pass", errors=(), metrics={})
        with tempfile.TemporaryDirectory() as td:
            spec_path = Path(td) / "spec.json"
            spec_path.write_text(json.dumps(spec, ensure_ascii=False), encoding="utf-8")
            out_root = Path(td) / "root"
            buffer = io.StringIO()
            with patch.object(rp, "run_visual_smoke", return_value=fake_smoke), \
                 patch.object(rp, "_approved_root_for", return_value=str(out_root)), \
                 contextlib.redirect_stdout(buffer):
                code = rp.main(["render_page.py", str(spec_path)])
            names = sorted(item.name for item in out_root.iterdir())
            text_file = out_root / "text-only-check-text.txt"
            full_size = (out_root / "text-only-check.html").stat().st_size
            body = text_file.read_text(encoding="utf-8")
            text_size = text_file.stat().st_size
            self.assertIn(str(text_file), buffer.getvalue())

        self.assertIn(code, (0, 1))
        self.assertEqual(names, ["text-only-check-artifact.html", "text-only-check-text.txt", "text-only-check.html"])
        self.assertIn("  文字だけの版 (試問用): ", buffer.getvalue())
        self.assertLess(text_size, full_size)
        self.assertIn("## 選ぶこと", body)
        self.assertIn("( ) [推奨] 案A", body)
        self.assertNotIn("<script", body)
        self.assertNotIn("<", body)

    def test_a_failed_write_does_not_stop_the_page_and_is_reported(self):
        spec = {
            "name": "text-only-failed",
            "title": "書けなかったときの確認",
            "components": ["overview"],
            "reasons": ["project_novice_default"],
            "publish": "never",
            "content": {"overview": "書けなかったときの確認用の頁である。"},
        }
        fake_smoke = types.SimpleNamespace(status="pass", errors=(), metrics={})
        with tempfile.TemporaryDirectory() as td:
            spec_path = Path(td) / "spec.json"
            spec_path.write_text(json.dumps(spec, ensure_ascii=False), encoding="utf-8")
            out_root = Path(td) / "root"
            buffer = io.StringIO()
            with patch.object(rp, "run_visual_smoke", return_value=fake_smoke), \
                 patch.object(rp, "_approved_root_for", return_value=str(out_root)), \
                 patch.object(rp, "write_text_only", side_effect=OSError("書き込めない")), \
                 contextlib.redirect_stdout(buffer):
                code = rp.main(["render_page.py", str(spec_path)])
            built = (out_root / "text-only-failed.html").is_file()

        out = buffer.getvalue()
        self.assertIn(code, (0, 1))
        self.assertTrue(built)
        self.assertIn("ⓘ 文字だけの版は書けなかった（書き込めない）", out)
        self.assertNotIn("文字だけの版 (試問用)", out)


class NumberedUnitsAndWithdrawnTests(unittest.TestCase):
    """data-blk の単位の行頭に「#N 」、取り下げた選択肢の行頭に「[取り下げ] 」、原稿の正本の textarea は黙って捨てる。

    2026-10-09（指摘と添削の作り込み）：試問の読み手が、回答文の番号（#N）で頁の行を指せるようにする。
    """

    def test_the_first_line_of_a_numbered_unit_carries_the_number_and_the_rest_do_not(self):
        text = rp.text_only(
            '<body><div class="card" data-blk="1"><h3>見出し</h3><p>本文の文。</p></div>'
            '<ul><li data-blk="2">一つ目<ul><li>入れ子</li></ul></li><li data-blk="3">二つ目</li></ul></body>'
        )

        self.assertIn("#1 ### 見出し\n本文の文。", text)
        self.assertIn("#2 - 一つ目", text)
        self.assertIn("- 入れ子", text)
        self.assertNotIn("#2 - 入れ子", text)
        self.assertIn("#3 - 二つ目", text)

    def test_a_table_row_unit_numbers_its_row_line(self):
        text = rp.text_only(
            "<body><table><thead><tr><th>列A</th><th>列B</th></tr></thead><tbody>"
            '<tr data-blk="4"><td>甲</td><td>乙</td></tr><tr data-blk="5"><td>丙</td><td>丁</td></tr>'
            "</tbody></table></body>"
        )

        self.assertIn("列A｜列B\n#4 甲｜乙\n#5 丙｜丁", text)

    def test_nested_same_tag_inside_a_unit_does_not_end_the_unit_early(self):
        text = rp.text_only(
            '<body><div data-blk="7"><div><p>内側の段落</p></div><p>外側の続き</p></div><p>単位の外</p></body>'
        )

        self.assertIn("#7 内側の段落\n外側の続き\n単位の外", text)

    def test_an_empty_hidden_unit_gives_no_line_and_does_not_leak_its_number(self):
        text = rp.text_only('<body><div data-blk="1" hidden></div><div data-blk="2"><p>本文</p></div></body>')

        self.assertNotIn("#1 ", text)
        self.assertIn("#2 本文", text)

    def test_the_header_explains_the_numbers_only_when_there_are_numbers(self):
        self.assertIn("行頭の #N は番号つきの単位", rp.text_only('<body><p data-blk="1">本文</p></body>'))
        self.assertNotIn("行頭の #N", rp.text_only("<body><p>本文</p></body>"))

    def test_a_code_unit_of_a_manuscript_keeps_line_breaks_and_indentation(self):
        text = rp.text_only(
            '<body><div data-blk="5" data-ms-type="code"><pre><code>a: 1\n  b: 2\n\nc: 3</code></pre></div>'
            '<div data-blk="6"><p>次</p></div></body>'
        )

        self.assertIn("#5 a: 1\n  b: 2\n\nc: 3\n#6 次", text)

    def test_a_pre_outside_a_manuscript_unit_is_still_collapsed(self):
        text = rp.text_only('<body><div data-blk="5"><pre class="log">一行目\n二行目</pre></div></body>')

        self.assertIn("#5 一行目 二行目", text)

    def test_the_source_textarea_is_dropped_silently_but_other_textareas_are_marked(self):
        text = rp.text_only(
            '<body><textarea id="ms-source" class="ms-source" hidden>\n原稿の全文\n</textarea>'
            '<textarea id="decision-objection">下書き</textarea></body>'
        )

        self.assertNotIn("原稿の全文", text)
        self.assertEqual(text.count("[自由記述欄]"), 1)

    def test_a_withdrawn_choice_gets_the_mark_once_and_a_plain_choice_does_not(self):
        text = rp.text_only(
            '<body><label class="choice"><input type="radio" data-req="1"><span>生きた案</span></label>'
            '<div class="choice withdrawn" data-withdrawn="1"><s>取り下げた案</s>'
            '<span class="why">理由の文</span></div></body>'
        )

        self.assertIn("( ) 生きた案", text)
        self.assertIn("[取り下げ] 取り下げた案 理由の文", text)
        self.assertEqual(text.count("[取り下げ]"), 1)

    def test_a_withdrawn_badge_is_not_doubled(self):
        text = rp.text_only(
            '<body><div class="choice withdrawn"><span class="badge b-bad">取り下げ</span> <s>案</s></div></body>'
        )

        self.assertEqual(text.count("[取り下げ]"), 1)


class QuestionBadgeInDiagramTests(unittest.TestCase):
    """図の箱の角の問いの番号札（a.dia-q）は、文字だけの版で箱の題の後ろの「[Q1]」になる（2026-10-09）。

    札は箱の外（図の末尾）に並ぶので、円の中心が入る枠で箱に結び付ける。結び付かない札は最後に1項目。
    手書きの図で試す（組む側が変わっても、この検査は動く）。
    """

    @staticmethod
    def _badge(number, cx, cy):
        return (
            '<a class="dia-q" href="#q-%d" aria-label="Q%d へ移動"><title>Q%d へ移動</title>'
            '<circle cx="%s" cy="%s" r="12" fill="transparent"></circle>'
            '<circle class="dia-q-dot" cx="%s" cy="%s" r="10"></circle>'
            '<text x="%s" y="%s" text-anchor="middle">Q%d</text></a>'
            % (number, number, number, cx, cy, cx, cy, cx, cy, number)
        )

    def _page(self, *badges, title="<title>図</title>"):
        return (
            '<body><svg class="dia" viewBox="0 0 400 100" role="img" aria-label="図">' + title
            + '<g><rect x="10" y="10" width="160" height="60"></rect><text x="20" y="30">計画</text>'
            '<text x="20" y="50">本文一</text></g>'
            '<g><rect x="200" y="10" width="160" height="60"></rect><text x="210" y="30">実行</text></g>'
            + "".join(badges) + "</svg></body>"
        )

    def test_a_badge_inside_a_box_follows_that_boxs_title(self):
        text = rp.text_only(self._page(self._badge(1, 160, 24), self._badge(2, 136, 24), self._badge(2, 350, 24)))

        self.assertIn("[図: 図｜文字: 計画 [Q1][Q2]／本文一／実行 [Q2]]", text)

    def test_the_badge_label_does_not_pile_up_at_the_end(self):
        text = rp.text_only(self._page(self._badge(1, 160, 24), self._badge(2, 350, 24)))

        self.assertNotRegex(text, r"／Q\d")
        self.assertNotIn("Q1 Q2", text)

    def test_a_badge_outside_every_box_is_gathered_in_one_trailing_item(self):
        text = rp.text_only(self._page(self._badge(3, 390, 95), self._badge(4, 395, 98)))

        self.assertIn("実行／問い Q3・Q4]", text)

    def test_the_badge_move_title_is_not_taken_as_the_figure_title(self):
        # 図に題が無いとき、札の「Q1 へ移動」を図の題にしない。
        text = rp.text_only(self._page(self._badge(1, 160, 24), title=""))

        self.assertNotIn("へ移動", text)
        self.assertIn("計画 [Q1]", text)

    def test_a_figure_without_badges_is_unchanged(self):
        text = rp.text_only(self._page())

        self.assertIn("[図: 図｜文字: 計画／本文一／実行]", text)

    def test_the_real_renderer_output_puts_the_badges_on_the_box_titles(self):
        from visual import render_components as rc

        plan = types.SimpleNamespace(
            components=("overview", "visual"), reason_codes=(), audience="p", depth="d",
            provisional=False, should_continue=False, delivery="x", publish_policy="never",
        )
        content = {"overview": "概要", "visual": {
            "nodes": [
                {"id": "a", "title": "計画", "text": "本文一", "asks": [1, 2]},
                {"id": "b", "title": "実行", "asks": "Q2"},
                {"id": "c", "title": "確認"},
            ],
            "edges": [{"from": "a", "to": "b"}, {"from": "b", "to": "c"}],
        }}
        page = rc.render_components(plan, title="t", content=content, glossary_entries={})
        if "dia-q" not in page:
            self.skipTest("図の箱の問いの番号札を、組む側がまだ描かない")

        text = rp.text_only(page)

        self.assertIn("計画 [Q1][Q2]", text)
        self.assertIn("実行 [Q2]", text)
        self.assertNotIn("へ移動", text)
        self.assertNotRegex(text, r"確認／?Q\d")


if __name__ == "__main__":
    unittest.main()

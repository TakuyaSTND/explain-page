"""組む前と組んだ後の機械検査の試験（2026-10-09・試問の費用を下げる Q1）。

何を守るか＝試問の読み手に読ませると費用ばかり掛かる「機械で数えられる誤り」を、頁を組む道具
（render_page.py）が先に済ませる。
  組む前（定義を見る）＝不明な図の記号（組み立てを止める＝唯一）・図番号の重複・対の無い **・
                       asks の形・asks の案内（全部止めない）
  組んだ後（HTMLを見る）＝図の下の注意・絵の欠け・空の強調・本文に残った **・飛び先切れ（全部止めない）
この試験は一時フォルダの置き場にだけ書く。置き場の実測の数は試験に埋め込まない（実測の報告に書く）。
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


def _diagram(*boxes, **extra):
    nodes = [dict({"id": "n%d" % index, "title": "箱%d" % index}, **box) for index, box in enumerate(boxes)]
    return dict({"nodes": nodes}, **extra)


def _section(component, content, label="", **extra):
    entry = {"component": component, "content": content}
    if label:
        entry["label"] = label
    entry.update(extra)
    return entry


def _spec(content, reasons=("project_novice_default",)):
    base = {
        "overview": "検査用の頁である。",
        "summary": "Goal：検査する。\nNow：試験中である。",
        "walkthrough": "手順一：試験のための本文である。",
        "examples": "例一：試験のための本文である。",
        "progress": "現在地：試験中である。",
        "visual": "図の見本：試験のための本文である。",
        "decision": {"groups": [{"legend": "進め方", "kind": "radio", "options": [
            {"label": "案A", "recommended": True, "pros": "速い"},
            {"label": "案B", "pros": "丁寧"},
        ]}]},
        "evidence": "実測：試験のための値である｜.claude/hooks/tests/test_page_checks.py",
        "glossary": "用語一：試験のための説明である。",
        "details": "記録：試験のための詳細である。",
    }
    base.update(content)
    return {
        "name": "page-checks",
        "title": "検査の確認",
        "components": list(rp.ALL_COMPONENTS),
        "reasons": list(reasons),
        "publish": "never",
        "content": base,
    }


def _run_main(spec, *, patches=()):
    """main() を一時フォルダの置き場で走らせる。返るもの＝(終了コード, 出力, 書き出した名前と中身の辞書)。"""
    fake_smoke = types.SimpleNamespace(status="pass", errors=(), metrics={})
    with tempfile.TemporaryDirectory() as td:
        spec_path = Path(td) / "spec.json"
        spec_path.write_text(json.dumps(spec, ensure_ascii=False), encoding="utf-8")
        out_root = Path(td) / "root"
        buffer = io.StringIO()
        with contextlib.ExitStack() as stack:
            stack.enter_context(patch.object(rp, "run_visual_smoke", return_value=fake_smoke))
            stack.enter_context(patch.object(rp, "_approved_root_for", return_value=str(out_root)))
            for entry in patches:
                stack.enter_context(entry)
            stack.enter_context(contextlib.redirect_stdout(buffer))
            code = rp.main(["render_page.py", str(spec_path)])
        files = {}
        if out_root.is_dir():
            files = {item.name: item.read_bytes() for item in out_root.iterdir() if item.is_file()}
        return code, buffer.getvalue(), files


class UnknownIconTests(unittest.TestCase):
    def test_an_icon_that_does_not_exist_is_found_with_its_place(self):
        content = {"sections": [_section("visual", _diagram({"icon": "doc", "title": "計画"}), label="流れの図")]}

        lines = rp.unknown_icons(content)

        self.assertEqual(lines, ["「流れの図」の diagram の箱「計画」の icon 'doc'"])

    def test_names_in_the_icon_list_pass(self):
        content = {"visual": _diagram({"icon": "person"}, {"icon": "document"}, {"icon": "magnifier"})}

        self.assertEqual(rp.unknown_icons(content), [])

    def test_every_listed_name_passes_and_a_neighbour_does_not(self):
        names = tuple(rp._ICON_NAMES)
        self.assertGreaterEqual(len(names), 31)
        content = {"visual": _diagram(*[{"icon": name} for name in names])}
        self.assertEqual(rp.unknown_icons(content), [])
        content = {"visual": _diagram({"icon": "search"}, {"icon": "doc"})}
        self.assertEqual(len(rp.unknown_icons(content)), 2)

    def test_boxes_without_an_icon_are_left_alone(self):
        content = {"visual": _diagram({}, {"icon": ""}, {"icon": None})}

        self.assertEqual(rp.unknown_icons(content), [])

    def test_the_diagram_key_inside_a_block_is_checked(self):
        content = {"details": [{"summary": "詳細", "diagram": _diagram({"icon": "doc", "title": "題"})}]}

        lines = rp.unknown_icons(content)

        self.assertEqual(len(lines), 1)
        self.assertIn("icon 'doc'", lines[0])

    def test_one_line_notation_icon_is_checked(self):
        text = "A: 受け取る | 本文\nB: 調べる | 本文\nA(icon=search)\nB(icon=person)\nA -> B"
        content = {"sections": [_section("visual", {"diagram_text": text}, label="1行記法の図")]}

        lines = rp.unknown_icons(content)

        self.assertEqual(lines, ["「1行記法の図」の diagram_text の箱「受け取る」の icon 'search'"])

    def test_one_line_notation_with_known_icon_passes(self):
        content = {"visual": {"diagram_text": "A(icon=person)\nA -> B"}}

        self.assertEqual(rp.unknown_icons(content), [])

    def test_flow_nodes_are_not_diagram_boxes(self):
        content = {"visual": {"flow": {"nodes": [{"id": "a", "label": "甲", "icon": "doc"}], "links": []}}}

        self.assertEqual(rp.unknown_icons(content), [])

    def test_when_the_icon_list_cannot_be_imported_the_check_is_skipped(self):
        content = {"visual": _diagram({"icon": "doc"})}

        with patch.object(rp, "_ICON_NAMES", None):
            self.assertEqual(rp.unknown_icons(content), [])

    def test_an_explicit_name_list_can_be_passed(self):
        content = {"visual": _diagram({"icon": "person"})}

        self.assertEqual(len(rp.unknown_icons(content, icon_names=("box",))), 1)

    def test_non_dict_shapes_do_not_raise(self):
        for content in ({}, {"visual": "文字列"}, {"visual": {"nodes": "x"}}, {"visual": {"nodes": ["a", 1]}},
                        {"sections": "x"}, "x", None):
            self.assertEqual(rp.unknown_icons(content), [])


class UnknownIconStopsTheBuildTests(unittest.TestCase):
    def test_main_returns_2_and_does_not_build(self):
        spec = _spec({"visual": _diagram({"icon": "doc", "title": "計画"})})

        with patch.object(rp, "build") as builder:
            code, out, _files = _run_main(spec)

        self.assertEqual(code, 2)
        builder.assert_not_called()
        self.assertIn("⚠️図の記号が無い＝組み立てを止めた", out)
        self.assertIn("icon 'doc'", out)
        self.assertIn("使える記号（全%d個）" % len(rp._ICON_NAMES), out)
        self.assertNotIn("書き出した:", out)

    def test_the_list_of_usable_names_is_printed(self):
        spec = _spec({"visual": _diagram({"icon": "search"})})

        _code, out, _files = _run_main(spec, patches=[patch.object(rp, "build")])

        self.assertIn("person", out)
        self.assertIn("magnifier", out)

    def test_a_good_icon_still_builds(self):
        spec = _spec({"visual": _diagram({"icon": "person", "title": "人"})})

        code, out, files = _run_main(spec)

        self.assertIn(code, (0, 1))
        self.assertNotIn("図の記号が無い", out)
        self.assertIn("page-checks.html", files)

    def test_a_broken_checker_does_not_stop_the_build(self):
        spec = _spec({})

        with patch.object(rp, "unknown_icons", side_effect=RuntimeError("壊れた")):
            code, out, files = _run_main(spec)

        self.assertIn(code, (0, 1))
        self.assertIn("図の記号の検査は走らなかった", out)
        self.assertIn("page-checks.html", files)


class DuplicateFigureNumberTests(unittest.TestCase):
    def test_diagram_figure_1_and_image_1_are_the_same_figure(self):
        content = {"visual": [
            {"diagram": _diagram({}, num="図1")},
            {"image": {"path": "a.png", "num": "1"}},
        ]}

        lines = rp.duplicate_figure_numbers(content)

        self.assertEqual(lines, ["⚠️図番号の重複（止めはしない）: 「図1」が diagram と image で2回"])

    def test_the_same_kind_twice_is_one_line_naming_the_kind_once(self):
        content = {"visual": [{"diagram": _diagram({}, num="図2")}, {"diagram": _diagram({}, num="2")}]}

        lines = rp.duplicate_figure_numbers(content)

        self.assertEqual(lines, ["⚠️図番号の重複（止めはしない）: 「図2」が diagram で2回"])

    def test_screenshot_is_counted(self):
        content = {"visual": [
            {"screenshot": {"target": "page.html", "num": "3"}},
            {"image": {"path": "a.png", "num": "図3"}},
        ]}

        lines = rp.duplicate_figure_numbers(content)

        self.assertEqual(len(lines), 1)
        self.assertIn("screenshot と image", lines[0])

    def test_the_figure_kinds_each_count(self):
        content = {"visual": [
            {"timeline": {"events": [], "num": "図5"}},
            {"quadrant": {"items": [], "num": "5"}},
            {"venn": {"sets": [], "num": "5"}},
            {"flow": {"nodes": [], "num": "5"}},
            {"score": {"axes": [], "num": "5"}},
            {"chart": {"kind": "line", "num": "5"}},
            {"svg": {"svg": "<svg></svg>", "num": "5"}},
        ]}

        lines = rp.duplicate_figure_numbers(content)

        self.assertEqual(len(lines), 1)
        self.assertIn("7回", lines[0])

    def test_section_numbers_and_box_numbers_are_not_figure_numbers(self):
        content = {"sections": [
            _section("visual", _diagram({"num": "1"}, {"num": "1"}), num="1"),
            _section("walkthrough", "手順：本文", num="1"),
        ]}

        self.assertEqual(rp.duplicate_figure_numbers(content), [])

    def test_different_numbers_and_empty_numbers_are_fine(self):
        content = {"visual": [
            {"diagram": _diagram({}, num="図1")},
            {"diagram": _diagram({}, num="図2")},
            {"diagram": _diagram({})},
            {"image": {"path": "a.png", "num": ""}},
            {"image": {"path": "b.png"}},
        ]}

        self.assertEqual(rp.duplicate_figure_numbers(content), [])

    def test_a_diagram_given_directly_as_the_visual_section_is_counted(self):
        content = {"sections": [
            _section("visual", _diagram({}, num="図1")),
            _section("examples", [{"image": {"path": "a.png", "num": "1"}}]),
        ]}

        self.assertEqual(len(rp.duplicate_figure_numbers(content)), 1)

    def test_the_output_is_capped_at_ten_lines_plus_a_remainder(self):
        content = {"visual": [
            {"diagram": _diagram({}, num=str(n))} for n in range(12) for _ in range(2)
        ]}

        lines = rp.duplicate_figure_numbers(content)

        self.assertEqual(len(lines), 11)
        self.assertIn("ほか2件", lines[-1])

    def test_main_prints_it_before_building_and_still_builds(self):
        spec = _spec({"visual": [{"diagram": _diagram({}, num="図1")}, {"image": {"path": "x", "num": "1"}}]})
        # 画像の実ファイルは無くてよい＝組む側が「取り込めなかった」と出す。組む前の警告だけを見る。
        code, out, files = _run_main(spec)

        self.assertIn("図番号の重複（止めはしない）", out)
        self.assertLess(out.index("図番号の重複"), out.index("書き出した:"))
        self.assertIn(code, (0, 1))
        self.assertIn("page-checks.html", files)


class UnbalancedEmphasisTests(unittest.TestCase):
    def test_an_odd_number_of_double_stars_is_a_warning_with_place_and_excerpt(self):
        content = {"sections": [_section("walkthrough", "手順：ここは**太字にしたい文である", label="進め方")]}

        lines = rp.unbalanced_emphasis(content)

        self.assertEqual(len(lines), 1)
        self.assertIn("対になっていない ** がある（止めはしない）", lines[0])
        self.assertIn("「進め方」", lines[0])
        self.assertIn("**太字にしたい", lines[0])

    def test_balanced_pairs_are_fine(self):
        content = {"overview": "これは**太字**で、これも**太字**です。", "walkthrough": "手順：**重要**"}

        self.assertEqual(rp.unbalanced_emphasis(content), [])

    def test_triple_stars_in_a_balanced_pair_are_fine(self):
        self.assertEqual(rp.unbalanced_emphasis({"overview": "***強調***の文"}), [])

    def test_double_stars_inside_backticks_are_skipped(self):
        content = {"overview": "記号は `**` と書く。ほかに `a**b` もある。"}

        self.assertEqual(rp.unbalanced_emphasis(content), [])

    def test_an_unclosed_backtick_does_not_hide_the_stars(self):
        content = {"overview": "閉じない ` の後に **太字の文"}

        self.assertEqual(len(rp.unbalanced_emphasis(content)), 1)

    def test_log_diff_and_code_like_keys_are_skipped(self):
        content = {"details": [{
            "summary": "詳細",
            "log": "**始まるだけのログ行",
            "diff": ["+ a **b", "- c"],
            "formula": {"tex": "a**b", "reading": "べき乗"},
            "svg": "<svg><text>**</text></svg>",
            "image": {"path": "dir/**name.png", "deck": "x**y.pptx"},
            "screenshot": {"target": "a**b.html", "selector": "div**x"},
        }]}

        self.assertEqual(rp.unbalanced_emphasis(content), [])

    def test_a_single_star_is_never_a_warning(self):
        content = {"overview": "3*4 と 5*6 の式。*弱い強調* や 2つの * もある。"}

        self.assertEqual(rp.unbalanced_emphasis(content), [])

    def test_the_path_names_the_place_inside_a_block(self):
        content = {"details": [{"summary": "詳細", "items": ["良い行", "悪い**行"]}]}

        lines = rp.unbalanced_emphasis(content)

        self.assertEqual(len(lines), 1)
        self.assertIn("items[1]", lines[0])

    def test_long_text_is_cut_to_an_excerpt(self):
        content = {"overview": "あ" * 200 + "**い" + "う" * 200}

        line = rp.unbalanced_emphasis(content)[0]

        self.assertNotIn("あ" * 30, line)
        self.assertNotIn("う" * 50, line)
        self.assertIn("**", line)

    def test_warning_text_has_no_forbidden_scheme(self):
        line = rp.unbalanced_emphasis({"overview": "**だけ"})[0]

        for needle in ("http://", "https://", "file://"):
            self.assertNotIn(needle, line)


class AsksTests(unittest.TestCase):
    def test_well_formed_asks_give_no_warning(self):
        content = {"sections": [
            _section("walkthrough", "手順：本文", asks=[1, "2", "Q3", "q4"]),
            _section("evidence", "実測：内容｜出所", asks=[]),
        ]}

        self.assertEqual(rp.asks_format_warnings(content), [])

    def test_a_non_list_asks_is_one_warning(self):
        content = {"sections": [_section("walkthrough", "手順：本文", label="進め方", asks="1")]}

        lines = rp.asks_format_warnings(content)

        self.assertEqual(len(lines), 1)
        self.assertIn("asks が配列でない（止めはしない）", lines[0])
        self.assertIn("「進め方」", lines[0])

    def test_unreadable_elements_are_named_one_by_one(self):
        content = {"sections": [_section("walkthrough", "手順：本文", asks=[1, "x", 0, -2, 1.5, True, None, "Q"])]}

        lines = rp.asks_format_warnings(content)

        # 読めない要素＝"x"・0・-2・1.5・True・None・"Q" の7つ。1だけが読める。
        self.assertEqual(len(lines), 7)
        self.assertTrue(all("読めない値がある（止めはしない）" in line for line in lines))
        self.assertIn("'x'", lines[0])

    def test_sections_without_asks_and_pages_without_sections_are_quiet(self):
        self.assertEqual(rp.asks_format_warnings({"sections": [_section("walkthrough", "手順：本文")]}), [])
        self.assertEqual(rp.asks_format_warnings({"overview": "本文"}), [])
        self.assertEqual(rp.asks_format_warnings({"sections": "x"}), [])

    def test_the_number_reader_matches_the_documented_forms(self):
        for value, expected in ((1, 1), ("1", 1), ("Q1", 1), ("q12", 12), ("Q", None), ("1a", None),
                                (0, None), ("0", None), (True, None), (2.0, None), (None, None), ([1], None)):
            self.assertEqual(rp._asks_number(value), expected, value)

    def test_hint_appears_for_a_decision_page_with_no_asks(self):
        spec = _spec({}, reasons=("project_novice_default", "decision_required"))

        hint = rp.asks_hint(spec["content"], spec["reasons"])

        self.assertEqual(hint, "ⓘ 問いに関わる節には \"asks\":[1] を書くと見出しに「→ Q1」の飛び先が付く")

    def test_hint_is_quiet_when_some_section_has_readable_asks(self):
        spec = _spec({"sections": [_section("walkthrough", "手順：本文", asks=["Q1"])]},
                     reasons=("decision_required",))

        self.assertEqual(rp.asks_hint(spec["content"], spec["reasons"]), "")

    def test_hint_still_shows_when_the_only_asks_are_unreadable(self):
        spec = _spec({"sections": [_section("walkthrough", "手順：本文", asks=["x"])]},
                     reasons=("decision_required",))

        self.assertNotEqual(rp.asks_hint(spec["content"], spec["reasons"]), "")

    def test_hint_is_quiet_without_decision_required_or_without_questions(self):
        spec = _spec({})
        self.assertEqual(rp.asks_hint(spec["content"], spec["reasons"]), "")
        no_question = _spec({"decision": {"groups": [{"legend": "自由記述", "kind": "free"}]}},
                            reasons=("decision_required",))
        self.assertEqual(rp.asks_hint(no_question["content"], no_question["reasons"]), "")

    def test_question_count_follows_the_reply_numbering(self):
        content = {"decision": {"groups": [
            {"legend": "自由", "kind": "free"},
            {"legend": "空", "kind": "radio", "options": []},
            {"legend": "段階", "kind": "scale", "items": [{"title": "安全"}]},
            {"legend": "段階の空", "kind": "scale", "items": []},
            {"legend": "数", "kind": "number", "options": [{"label": "件数"}]},
            {"legend": "選択", "kind": "radio", "options": [{"label": "甲"}]},
        ]}}

        self.assertEqual(rp._question_count(content), 3)

    def test_main_prints_the_hint_once_for_a_decision_page(self):
        spec = _spec({}, reasons=("project_novice_default", "decision_required"))

        _code, out, _files = _run_main(spec)

        self.assertEqual(out.count("ⓘ 問いに関わる節には"), 1)
        self.assertLess(out.index("ⓘ 問いに関わる節には"), out.index("書き出した:"))

    def test_main_warns_about_a_bad_asks_and_still_builds(self):
        spec = _spec({"sections": [_section("walkthrough", "手順：本文", asks="1")]})

        code, out, files = _run_main(spec)

        self.assertIn("asks が配列でない", out)
        self.assertIn(code, (0, 1))
        self.assertIn("page-checks.html", files)


class RenderedWarningsTests(unittest.TestCase):
    BASE = '<!doctype html><html><head><title>t</title><style>.thumb-missing{}.dia-warn{}</style></head><body>%s%s</body></html>'

    def _page(self, body, tail='<script>const x="**";</script>'):
        return self.BASE % (body, tail)

    def test_a_clean_page_has_no_warning(self):
        page = self._page('<h2 id="x">節</h2><p>本文 <strong>強調</strong> と <em>弱い強調</em></p>')

        self.assertEqual(rp.rendered_warnings(page), [])

    def test_dia_warn_items_are_listed(self):
        page = self._page(
            '<ul class="dia-warn"><li>diagram: 不明な記号 &#x27;doc&#x27; は無視した</li>'
            '<li>辺が1本見つからない</li></ul>'
        )

        lines = rp.rendered_warnings(page)

        self.assertEqual(len(lines), 2)
        self.assertIn("図の下に警告が出ている（止めはしない）", lines[0])
        self.assertIn("不明な記号 'doc'", lines[0])
        self.assertIn("辺が1本見つからない", lines[1])

    def test_thumb_missing_both_forms_are_listed(self):
        page = self._page(
            '<label><span class="thumb thumb-missing">絵を取り込めなかった：形式が違う</span></label>'
            '<label><span class="thumb-missing">外したもの：script</span></label>'
        )

        lines = rp.rendered_warnings(page)

        self.assertEqual(len(lines), 2)
        self.assertTrue(all("選択肢の絵が頁に載っていない（止めはしない）" in line for line in lines))
        self.assertIn("形式が違う", lines[0])
        self.assertIn("外したもの：script", lines[1])

    def test_the_word_thumb_missing_in_prose_is_not_a_warning(self):
        page = self._page('<p>説明で thumb-missing という名前を書く</p><code>thumb-missing</code>')

        self.assertEqual(rp.rendered_warnings(page), [])

    def test_empty_emphasis_is_counted(self):
        page = self._page("<p>文<em></em>の続き<em></em></p><p><strong></strong></p>")

        lines = rp.rendered_warnings(page)

        self.assertEqual(len(lines), 1)
        self.assertIn("空の強調が頁に出ている（止めはしない）", lines[0])
        self.assertIn("<em></em> が2個", lines[0])
        self.assertIn("<strong></strong> が1個", lines[0])

    def test_a_visible_double_star_in_text_is_found(self):
        page = self._page("<p>この文に**消えない記号がある</p>")

        lines = rp.rendered_warnings(page)

        self.assertEqual(len(lines), 1)
        self.assertIn("頁の本文に ** がそのまま出ている（止めはしない）: 1 か所", lines[0])
        self.assertIn("**消えない記号", lines[0])

    def test_double_stars_in_attributes_code_pre_and_script_are_not_found(self):
        page = self._page(
            '<p><span class="t" data-d="説明に**強調**がある" aria-label="語：**x**">語</span></p>'
            "<p>記号は <code>**</code> と書く</p>"
            "<pre>**ログの行</pre>"
            "<pre><code>a ** b</code></pre>"
            '<textarea placeholder="**"></textarea>',
            tail='<script>const s="**";</script>',
        )

        self.assertEqual(rp.rendered_warnings(page), [])

    def test_a_dangling_question_link_is_found_once(self):
        page = self._page(
            '<h2>節<a class="q-ref" href="#q-9">→ Q9</a><a class="q-ref" href="#q-9">→ Q9</a>'
            '<a class="q-ref" href="#q-1">→ Q1</a></h2>'
            '<fieldset id="q-1"><legend>問い</legend></fieldset>'
        )

        lines = rp.rendered_warnings(page)

        self.assertEqual(len(lines), 1)
        self.assertIn("見出しや図の「Q9」の飛び先（#q-9）が頁に無い（止めはしない）", lines[0])

    def test_a_link_to_an_existing_anchor_is_fine(self):
        page = self._page(
            '<h2>節<a class="q-ref" href="#q-12">→ Q12</a></h2><fieldset id="q-12"><legend>問い</legend></fieldset>'
        )

        self.assertEqual(rp.rendered_warnings(page), [])

    def test_only_the_body_before_the_first_script_is_read(self):
        page = (
            "<html><head><style>.x{content:'**'}</style></head><body><p>本文</p>"
            "<script>x = '<em></em>**';</script><p>**あと</p></body></html>"
        )

        self.assertEqual(rp.rendered_warnings(page), [])

    def test_warning_text_has_no_forbidden_scheme(self):
        page = self._page('<ul class="dia-warn"><li>一行</li></ul><p>**</p><p><em></em></p>')

        for line in rp.rendered_warnings(page):
            for needle in ("http://", "https://", "file://"):
                self.assertNotIn(needle, line)

    def test_output_is_capped_at_ten_lines_plus_a_remainder(self):
        items = "".join("<li>注意%d</li>" % n for n in range(12))
        page = self._page('<ul class="dia-warn">%s</ul>' % items)

        lines = rp.rendered_warnings(page)

        self.assertEqual(len(lines), 11)
        self.assertIn("ほか2件", lines[-1])

    def test_main_prints_the_rendered_warnings_after_the_check_results(self):
        spec = _spec({"details": [{"summary": "詳細", "text": "本文に**は閉じない太字がある"}]})

        code, out, _files = _run_main(spec)

        # 組む側は対の無い ** を空の強調にするので、組む前（定義）と組んだ後（HTML）の両方で出る。
        self.assertIn("対になっていない ** がある（止めはしない）", out)
        self.assertIn(code, (0, 1))
        self.assertLess(out.index("書き出した:"), out.index("部品の濃さ:"))
        after = out[out.index("書き出した:"):out.index("部品の濃さ:")]
        # 組んだ後の警告は、検査の結果の行と濃さの行の間に出る（空の強調か、本文に残った **）。
        self.assertTrue(
            "空の強調が頁に出ている（止めはしない）" in after
            or "頁の本文に ** がそのまま出ている（止めはしない）" in after
        )


class OptionWarningNumberingTests(unittest.TestCase):
    def test_a_group_without_rows_does_not_take_a_question_number(self):
        content = {"decision": {"groups": [
            {"legend": "空", "kind": "radio", "options": []},
            {"legend": "実在", "kind": "radio", "options": [
                {"label": "甲", "recommended": True}, {"label": "乙"},
            ]},
        ]}}

        lines = rp.decision_option_warnings(content)

        self.assertEqual(len(lines), 1)
        self.assertIn("Q1「実在」の「乙」", lines[0])


class BoxAsksTests(unittest.TestCase):
    """図の箱の asks（箱の角の問いの番号札・2026-10-09）の書き方の警告。"""

    def test_readable_forms_give_no_warning(self):
        content = {"visual": _diagram(
            {"asks": 1}, {"asks": "Q2"}, {"asks": "1/2"}, {"asks": "Q1／Q3"}, {"asks": [1, "Q2", "3/4"]},
            {"ask": "5"}, {},
        )}

        self.assertEqual(rp.asks_format_warnings(content), [])

    def test_unreadable_pieces_are_named_one_by_one_with_the_place(self):
        content = {"sections": [_section(
            "visual", _diagram({"asks": "x", "title": "計画"}, {"asks": [0, True]}, {"asks": "1/y"}), label="流れの図",
        )]}

        lines = rp.asks_format_warnings(content)

        self.assertEqual(len(lines), 4)
        self.assertTrue(all("図の箱の asks に問いの番号として読めない値がある（止めはしない）" in line for line in lines))
        self.assertIn("「流れの図」の diagram の箱「計画」の asks 'x'", lines[0])
        self.assertIn("0", lines[1])
        self.assertIn("True", lines[2])
        self.assertIn("'y'", lines[3])

    def test_the_one_line_notation_is_checked_too(self):
        text = "A(asks=1/2)\nB[asks=x]\nA -> B"
        content = {"details": [{"summary": "詳細", "diagram_text": text}]}

        lines = rp.asks_format_warnings(content)

        self.assertEqual(len(lines), 1)
        self.assertIn("diagram_text の箱「B」の asks 'x'", lines[0])

    def test_box_warnings_come_before_the_section_ones_and_are_capped(self):
        boxes = [{"asks": "bad%d" % index} for index in range(12)]
        content = {"visual": _diagram(*boxes), "sections": [_section("walkthrough", "手順：本文", asks="1")]}

        lines = rp.asks_format_warnings(content)

        self.assertEqual(len(lines), 11)
        self.assertIn("ほか", lines[-1])

    def test_flow_nodes_are_not_diagram_boxes(self):
        content = {"flow": {"nodes": [{"id": "a", "asks": "x"}], "links": []}}

        self.assertEqual(rp.asks_format_warnings(content), [])

    def test_main_prints_the_box_warning_and_still_builds(self):
        spec = _spec({"visual": _diagram({"asks": "x", "title": "計画"})})

        code, out, files = _run_main(spec)

        self.assertIn("図の箱の asks に問いの番号として読めない値がある", out)
        self.assertIn(code, (0, 1))
        self.assertIn("page-checks.html", files)


class ManuscriptSectionIsLeftOutTests(unittest.TestCase):
    """原稿の節（利用者の文章）は、部品の濃さ・空の強調・本文に残った ** の検査に混ぜない（2026-10-09）。"""

    def test_a_manuscript_with_a_lone_double_star_gives_no_post_build_warning(self):
        page = (
            "<html><head><title>t</title></head><body><p>本文</p>"
            '<section data-component="manuscript"><article class="ms" data-prose="raw">'
            '<div class="ms-blk"><p>**閉じない <em></em> の文</p></div></article></section>'
            "<script>x</script></body></html>"
        )

        self.assertEqual(rp.rendered_warnings(page), [])

    def test_the_same_text_outside_the_manuscript_is_still_warned(self):
        page = "<html><body><p>**閉じない</p><script>x</script></body></html>"

        self.assertEqual(len(rp.rendered_warnings(page)), 1)

    def test_the_markdown_text_of_a_resolved_manuscript_is_not_walked_by_the_definition_checks(self):
        content = {"sections": [_section("manuscript", {
            "markdown": "対の無い ** がある\n```\ncode\n```\n", "label": "l", "mode": "shiteki",
            "source_path": "a.md", "sha256": "0" * 64, "eol": "lf",
        })]}

        self.assertEqual(rp.unbalanced_emphasis(content), [])
        self.assertEqual(rp.duplicate_figure_numbers(content), [])
        self.assertEqual(rp.unknown_icons(content), [])


if __name__ == "__main__":
    unittest.main()

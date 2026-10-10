"""説明の頁の「単位」の番号（visual/blocks.py の number_blocks）と、赤ペンの script・CSS の差し込みの検査
（2026-10-09・指摘と添削の作り込み）。

number_blocks(html) は、読み手が「ここ」と指したい塊（カード・表の行・箇条・段落・図・注意書き…）に
頁の先頭から通しで data-blk="N" を足す。判断欄・側柱・header（導入文は除く）・footer の中は数えない。
入れ子は外側だけ。既に data-blk の付いた頁（原稿の頁）には何もしない。

render_components は、定義の review が none でないときだけこれを通し、判断欄の script の後ろに
役割の順（shiteki → tensaku）で script を並べ、CSS を既存の1つの <style> の末尾へ足す。
review を書かない定義（none）の出力は今までと同じ。原稿の節（manuscript）があれば、その mode の役割は
review が none でも載せる。⚠️赤ペンの script の正本（review_scripts）は別の担当＝ここでは差し替えの偽物で
差し込みの規則を確かめ、本物があれば最後に1本だけ本物でも確かめる。
"""
from __future__ import annotations

import re
import sys
import time
import types
import unittest
from html.parser import HTMLParser
from pathlib import Path

HOOKS_DIR = Path(__file__).resolve().parents[1]
if str(HOOKS_DIR) not in sys.path:
    sys.path.insert(0, str(HOOKS_DIR))

from visual import blocks
from visual import render_components as rc
from visual.blocks import UNIT_RULES, BlockInfo, number_blocks
from visual.contracts import ExplanationPlan
from visual.render_components import DECISION_SCRIPT, render_components

try:
    from visual import review_scripts as real_review_scripts
except ImportError:  # 相手の担当がまだ作っていない
    real_review_scripts = None


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


class _Walker(HTMLParser):
    """出力の HTML を読み直し、data-blk の付いた要素と、その祖先の一覧を集める。"""

    VOID = {"br", "hr", "img", "input", "meta", "link", "col", "wbr"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.stack: list[tuple[str, frozenset[str], str]] = []
        self.numbered: list[dict] = []

    def handle_starttag(self, tag, attrs):
        d = dict(attrs)
        classes = frozenset((d.get("class") or "").split())
        if "data-blk" in d:
            self.numbered.append(
                {
                    "blk": int(d["data-blk"]),
                    "tag": tag,
                    "classes": classes,
                    "ancestors": list(self.stack),
                }
            )
        if tag not in self.VOID:
            self.stack.append((tag, classes, d.get("data-component", "")))

    def handle_endtag(self, tag):
        for i in range(len(self.stack) - 1, -1, -1):
            if self.stack[i][0] == tag:
                del self.stack[i:]
                return


def _walk(html: str) -> list[dict]:
    walker = _Walker()
    walker.feed(html)
    return walker.numbered


# 規則ごとの最小の見本（種類 → 数えられる HTML 断片と、その要素が持つ data-blk の数）。
SNIPPETS = {
    "card": '<div class="card-stack"><div class="card"><h3>見出し</h3><p>本文</p></div></div>',
    "tile": '<div class="tiles"><div class="tile"><b>題</b><span>説明</span></div></div>',
    "stat": '<div class="stats"><div class="stat"><div class="stat-num">38</div></div></div>',
    "note": '<div class="note warn"><h3>注意</h3><p>ここは大事</p></div>',
    "row": '<div class="item-stack"><div class="item-row"><strong class="item-label">状態</strong><span class="item-copy">作業中</span></div></div>',
    "step": '<ol class="steps"><li><div class="body"><span class="ttl">手順</span><p>読む</p></div></li></ol>',
    "bullet": '<ul class="bullets"><li>箇条</li></ul>',
    "numbered": '<ol class="numbered"><li>順</li></ol>',
    "pair": '<dl class="pairs"><dt>語</dt><dd>説明</dd></dl>',
    "term": '<dl class="gl"><dt>語</dt><dd>説明</dd></dl>',
    "quote": '<blockquote><p class="q-original">original</p><p class="q-ja">訳</p></blockquote>',
    "figure": '<div class="dia-wrap"><svg><text>図の字</text></svg></div>',
    "formula": '<div class="formula"><math display="block"><mi>a</mi></math></div>',
    "log": '<pre class="log">line</pre>',
    "compare": '<div class="compare"><div class="compare-panel"><div class="in">前</div></div></div>',
    "callout": '<ul class="callout-legend"><li class="callout-item"><span class="callout-text">吹き出し</span></li></ul>',
    "flow": '<div class="flow-map"><div class="flow-step">一歩</div></div>',
    "summary": '<div class="gnc"><div><b>目的</b><span>直す</span></div></div>',
    "chips": '<div class="chip-groups"><div class="chip-group"><h4 class="chip-head">札</h4><ul class="chips"><li>a</li></ul></div></div>',
    "paragraph": '<p class="body-copy">本文</p>',
    "caption": '<p class="cap">図の説明</p>',
    "detail": '<details><summary>もっと</summary><div class="in">詳しい説明</div></details>',
}


def _wrap_in_section(fragment: str, component: str = "examples", label: str = "具体例", sid: str = "sec-1") -> str:
    return '<div class="wrap"><section data-component="%s" id="%s"><h2>%s</h2>%s</section></div>' % (
        component, sid, label, fragment
    )


class RuleTests(unittest.TestCase):
    def test_every_kind_in_the_rules_has_a_snippet_that_gets_numbered(self):
        kinds = {rule.kind for rule in UNIT_RULES} - {"lede", "row"}
        for kind in sorted(kinds):
            self.assertIn(kind, SNIPPETS, kind)
        for kind, fragment in SNIPPETS.items():
            html, infos = number_blocks(_wrap_in_section(fragment))
            self.assertEqual(len(infos), 1, (kind, [i.kind for i in infos]))
            self.assertEqual(infos[0].kind, kind)
            self.assertEqual(html.count("data-blk="), 1, kind)
            self.assertEqual(infos[0].number, 1)

    def test_table_rows_and_labelled_rows_are_units_but_head_rows_are_not(self):
        fragment = (
            '<div class="scroll"><table><thead><tr><th>案</th><th>利点</th></tr></thead>'
            "<tbody><tr><td>A</td><td>安い</td></tr><tr><td>B</td><td>広い</td></tr></tbody></table></div>"
        )
        html, infos = number_blocks(_wrap_in_section(fragment, "table", "比べる"))

        self.assertEqual([(i.number, i.kind) for i in infos], [(1, "row"), (2, "row")])
        self.assertNotIn("<thead><tr data-blk", html)
        self.assertEqual([i.excerpt40 for i in infos], ["A 安い", "B 広い"])

    def test_the_lede_in_the_header_is_a_unit_and_nothing_else_in_the_header_is(self):
        html = (
            '<div class="wrap"><header data-component="overview"><div class="head-row"><p class="eyebrow">E</p>'
            '<button id="theme-toggle" type="button">明暗</button></div><h1>題</h1><p class="lede">導入です。</p>'
            '<div class="note"><p>ヘッダーの中の囲み</p></div></header></div>'
        )
        out, infos = number_blocks(html)

        self.assertEqual([(i.kind, i.component, i.excerpt40) for i in infos], [("lede", "overview", "導入です。")])
        self.assertEqual(out.count("data-blk="), 1)

    def test_lede_is_numbered_first_even_when_sections_follow(self):
        html = (
            '<div class="wrap"><header data-component="overview"><h1>題</h1><p class="lede">導入。</p></header>'
            + _wrap_in_section(SNIPPETS["card"])[len('<div class="wrap">') : -len("</div>")]
            + "</div>"
        )
        _, infos = number_blocks(html)

        self.assertEqual([(i.number, i.kind) for i in infos], [(1, "lede"), (2, "card")])


class CountingRuleTests(unittest.TestCase):
    def test_nested_units_count_only_the_outer_one(self):
        fragment = (
            '<div class="card"><h3>見出し</h3><p class="body-copy">中の段落</p><ul class="bullets"><li>中の箇条</li></ul>'
            '<div class="note"><p>中の囲み</p></div></div>'
            '<div class="note"><div class="card"><p>囲みの中のカード</p></div></div>'
        )
        html, infos = number_blocks(_wrap_in_section(fragment))

        self.assertEqual([(i.number, i.kind) for i in infos], [(1, "card"), (2, "note")])
        self.assertEqual(html.count("data-blk="), 2)

    def test_numbers_follow_document_order_and_are_consecutive(self):
        fragment = (
            '<p class="body-copy">一</p><div class="card"><p>二</p></div><ul class="bullets"><li>三</li><li>四</li></ul>'
            '<div class="dia-wrap"><svg><text>五</text></svg></div>'
        )
        html, infos = number_blocks(_wrap_in_section(fragment))

        self.assertEqual([i.number for i in infos], [1, 2, 3, 4, 5])
        self.assertEqual([n["blk"] for n in _walk(html)], [1, 2, 3, 4, 5])
        self.assertEqual([i.excerpt40 for i in infos][:4], ["一", "二", "三", "四"])

    def test_decision_rail_footer_and_navigation_are_not_counted(self):
        html = (
            '<div class="wrap">'
            + _wrap_in_section(SNIPPETS["card"])[len('<div class="wrap">') : -len("</div>")]
            + '<section data-component="decision" id="sec-2"><h2>選ぶこと</h2><fieldset id="q-1"><legend>問い</legend>'
            '<p class="intro">導入</p><div class="note"><p>判断欄の中の囲み</p></div><ul class="bullets"><li>判断欄の箇条</li></ul></fieldset>'
            '<pre id="decision-prompt">x</pre></section>'
            '<aside class="rail"><p class="rail-head">目次</p><nav class="toc"><ol><li><a href="#sec-1">節</a></li></ol></nav>'
            '<div class="note"><p>側柱の囲み</p></div><ul class="bullets"><li>側柱の箇条</li></ul></aside>'
            '<footer data-component="provenance"><div class="provenance-items"><p class="body-copy">出所</p></div></footer></div>'
        )
        out, infos = number_blocks(html)

        self.assertEqual([i.kind for i in infos], ["card"])
        self.assertEqual(out.count("data-blk="), 1)

    def test_units_after_a_skipped_region_are_numbered_again(self):
        html = (
            '<div class="wrap"><section data-component="decision" id="sec-1"><h2>選ぶこと</h2>'
            '<fieldset><div class="note"><p>数えない</p></div></fieldset></section>'
            '<section data-component="evidence" id="sec-2"><h2>根拠</h2><div class="note"><p>数える</p></div></section></div>'
        )
        _, infos = number_blocks(html)

        self.assertEqual([(i.number, i.section_id, i.component) for i in infos], [(1, "sec-2", "evidence")])

    def test_script_style_comment_and_textarea_text_never_makes_a_unit(self):
        html = (
            '<div class="wrap"><section data-component="details" id="sec-1"><h2>詳細</h2>'
            '<!-- <div class="card">コメントの中</div> -->'
            '<textarea hidden>&lt;div class="card"&gt;x&lt;/div&gt;</textarea>'
            "<p class=\"body-copy\">本文</p></section></div>"
            "<script>const html = '<div class=\"card\">script の中</div>';</script>"
            '<style>.card{color:red}</style>'
        )
        out, infos = number_blocks(html)

        self.assertEqual([i.kind for i in infos], ["paragraph"])
        self.assertEqual(out.count("data-blk="), 1)
        self.assertIn("<script>const html = '<div class=\"card\">script の中</div>';</script>", out)

    def test_a_page_that_already_has_numbers_is_returned_as_it_is(self):
        html = (
            '<div class="wrap"><section data-component="manuscript" id="sec-1"><h2>原稿</h2>'
            '<article class="ms" data-prose="raw"><div class="ms-blk" data-ms="1" data-blk="1" data-ms-type="paragraph"><p>文</p></div></article></section>'
            + SNIPPETS["card"]
            + "</div>"
        )
        out, infos = number_blocks(html)

        self.assertEqual(out, html)
        self.assertEqual(infos, [])

    def test_the_word_data_blk_inside_a_script_is_not_an_existing_number(self):
        html = _wrap_in_section(SNIPPETS["card"]) + "<script>document.querySelectorAll('[data-blk]');</script>"
        out, infos = number_blocks(html)

        self.assertEqual(len(infos), 1)
        self.assertEqual(out.count('<div data-blk="1" class="card">'), 1)

    def test_numbering_twice_changes_nothing_more(self):
        once, infos = number_blocks(_wrap_in_section(SNIPPETS["card"] + SNIPPETS["bullet"]))
        twice, infos_again = number_blocks(once)

        self.assertEqual(len(infos), 2)
        self.assertEqual(twice, once)
        self.assertEqual(infos_again, [])

    def test_a_page_without_units_is_returned_as_it_is(self):
        html = '<div class="wrap"><section data-component="x" id="sec-1"><h2>節</h2><div class="plain">x</div></section></div>'

        self.assertEqual(number_blocks(html), (html, []))
        self.assertEqual(number_blocks(""), ("", []))
        self.assertEqual(number_blocks("文字だけ"), ("文字だけ", []))


class PositionTests(unittest.TestCase):
    def test_multiline_markup_with_multibyte_text_gets_the_attribute_at_the_right_place(self):
        html = (
            '<div class="wrap">\n'
            '<section data-component="examples" id="sec-1">\n'
            "<h2>具体例　日本語の見出し</h2>\n"
            "\n"
            '<div\n   class="card"\n   data-tone="good">\n<h3>カード</h3>\n</div>\n'
            '<UL class="bullets">\n<li>\n箇条\n</li>\n</UL>\n'
            "<p class='body-copy'>シングルクオート</p>\n"
            "</section>\n</div>\n"
        )
        out, infos = number_blocks(html)

        self.assertEqual([i.kind for i in infos], ["card", "bullet", "paragraph"])
        self.assertIn('<div data-blk="1"\n   class="card"\n   data-tone="good">', out)
        self.assertIn('<li data-blk="2">', out)
        self.assertIn("<p data-blk=\"3\" class='body-copy'>", out)
        # 足した属性以外は1字も変えない。
        self.assertEqual(re.sub(r' data-blk="\d+"', "", out), html)

    def test_crlf_text_still_places_the_attribute_correctly(self):
        html = '<div class="wrap">\r\n<section data-component="x" id="sec-1">\r\n<h2>節</h2>\r\n<div class="card">\r\n本文\r\n</div>\r\n</section>\r\n</div>'
        out, infos = number_blocks(html)

        self.assertEqual(len(infos), 1)
        self.assertEqual(re.sub(r' data-blk="\d+"', "", out), html)
        self.assertIn('<div data-blk="1" class="card">', out)

    def test_a_tag_name_inside_text_before_the_unit_does_not_confuse_the_position(self):
        html = _wrap_in_section('<p class="body-copy">&lt;div class="card"&gt; と書く</p><div class="card"><p>本物</p></div>')
        out, infos = number_blocks(html)

        self.assertEqual([i.kind for i in infos], ["paragraph", "card"])
        self.assertIn('<div data-blk="2" class="card">', out)

    def test_output_reparses_to_exactly_the_numbered_elements(self):
        fragment = "".join(SNIPPETS[k] for k in ("card", "tile", "bullet", "quote", "log", "paragraph"))
        out, infos = number_blocks(_wrap_in_section(fragment))
        walked = _walk(out)

        self.assertEqual([w["blk"] for w in walked], [i.number for i in infos])
        self.assertEqual(len(walked), len(infos))


class InfoTests(unittest.TestCase):
    def test_info_records_the_section_label_without_the_number_chip_and_question_link(self):
        html = (
            '<div class="wrap"><section data-component="examples" id="sec-3">'
            '<h2><span class="sec-no">2</span>具体例<a class="q-ref" href="#q-1" aria-label="Q1 へ移動">→ Q1</a></h2>'
            + SNIPPETS["card"]
            + "</section></div>"
        )
        _, infos = number_blocks(html)

        self.assertEqual(
            infos[0],
            BlockInfo(
                number=1,
                section_id="sec-3",
                section_label="具体例",
                component="examples",
                kind="card",
                excerpt40="見出し 本文",
            ),
        )

    def test_excerpt_is_collapsed_whitespace_cut_at_40_characters(self):
        long_text = "あ" * 30 + "\n\n   " + "い" * 30
        _, infos = number_blocks(_wrap_in_section('<p class="body-copy">%s</p>' % long_text))

        self.assertEqual(len(infos[0].excerpt40), 40)
        self.assertEqual(infos[0].excerpt40, "あ" * 30 + " " + "い" * 9)

    def test_excerpt_keeps_a_space_between_blocks_but_not_inside_a_word(self):
        fragment = '<div class="card"><h3>題</h3><p>本文の<span class="t">用語</span>です</p></div>'
        _, infos = number_blocks(_wrap_in_section(fragment))

        self.assertEqual(infos[0].excerpt40, "題 本文の用語です")

    def test_figure_excerpt_uses_the_svg_text_but_not_its_title(self):
        fragment = '<div class="dia-wrap"><svg><title>タイトル</title><text>箱の題</text><text>本文</text></svg></div>'
        _, infos = number_blocks(_wrap_in_section(fragment, "visual", "図で見る"))

        self.assertEqual(infos[0].excerpt40, "箱の題 本文")


class RealPartsTests(unittest.TestCase):
    """レンダラーが実際に出す部品が、どれも番号を取れるか（class の名前が変わったら気づくため）。"""

    def _page(self, blocks_list: list[dict], extra_sections: list[dict] | None = None, **extra) -> str:
        sections = [{"component": "examples", "label": "部品", "content": blocks_list}]
        sections += extra_sections or []
        content = {"overview": "導入文です。", "sections": sections, **extra}
        return render_components(_plan("overview", "examples"), title="見本", content=content)

    def test_the_real_parts_all_get_numbers(self):
        html = self._page(
            [
                {"cards": [{"title": "カード", "text": "本文"}]},
                {"tiles": [{"title": "タイル", "text": "説明"}]},
                {"stats": [{"value": "38", "unit": "件", "label": "検査"}]},
                {"steps": ["決める：項目"]},
                {"chips": [{"title": "札", "items": ["a"]}]},
                {"items": ["箇条"]},
                {"ordered": ["順"]},
                {"pairs": ["語：説明"]},
                {"note": {"title": "注意", "text": "ここ", "tone": "warn"}},
                {"quote": {"original": "orig", "ja": "訳", "source": "出所"}},
                {"log": "line"},
                {"diff": "+追加\n-削除"},
                {"formula": {"tex": "a+b"}},
                {"timeline": [{"label": "1月", "text": "始め"}, {"label": "2月", "text": "終わり"}]},
                {"callouts": [{"n": 1, "text": "吹き出し"}]},
                {"compare": {"before": {"title": "前", "text": "古い"}, "after": {"title": "後", "text": "新しい"}}},
                {"table": {"head": ["案", "利点"], "rows": [["A", "安い"]]}},
                {"diagram_text": "A -> B"},
                {"caption": "図の説明"},
            ],
            [
                {"component": "walkthrough", "label": "順番", "content": "手順：読む"},
                {"component": "progress", "label": "現在地", "content": "状態：作業中"},
                {"component": "evidence", "label": "根拠", "content": ["実測：x｜tests/a.py"]},
                {"component": "glossary", "label": "用語", "content": "指摘：人が入れる赤"},
                {"component": "details", "label": "詳細", "content": [{"summary": "もっと", "text": "詳しい説明"}]},
            ],
        )
        body = html[html.index("<body>") : html.index("<script>")]
        out, infos = number_blocks(body)
        kinds = {i.kind for i in infos}

        for expected in (
            "lede", "card", "tile", "stat", "step", "chips", "bullet", "numbered", "pair", "note", "quote",
            "log", "formula", "figure", "callout", "compare", "row", "caption", "term", "detail",
        ):
            self.assertIn(expected, kinds, (expected, sorted(kinds)))
        self.assertEqual([n["blk"] for n in _walk(out)], list(range(1, len(infos) + 1)))

    def test_the_decision_section_of_a_real_page_is_not_numbered(self):
        html = self._page(
            [{"items": ["箇条"]}],
            [
                {
                    "component": "decision",
                    "label": "選ぶこと",
                    "content": {"groups": [{"legend": "どれ", "kind": "radio", "options": [{"label": "A", "why": "理由", "pros": "利点"}, {"label": "B"}]}]},
                }
            ],
            rail=[{"heading": "目次", "toc": True}, {"heading": "メモ", "items": ["側柱の箇条"]}],
        )
        body = html[html.index("<body>") : html.index("<script>")]
        out, infos = number_blocks(body)
        for item in _walk(out):
            names = [a[0] + "." + ".".join(sorted(a[1])) + "#" + a[2] for a in item["ancestors"]]
            self.assertFalse(any("decision" in n for n in names), names)
            self.assertFalse(any(".rail" in n or ".rail." in n for n in names), names)
            self.assertFalse(any(n.startswith("footer") for n in names), names)
        self.assertEqual(sorted(i.kind for i in infos), ["bullet", "lede"])


class SpeedTests(unittest.TestCase):
    def test_a_big_page_is_numbered_within_a_second(self):
        section = (
            '<section data-component="examples" id="sec-%d"><h2>節%d</h2>'
            '<div class="card-stack"><div class="card"><h3>カード</h3><p>本文の文章がここに入る。' + "文" * 60 + "</p></div></div>"
            '<ul class="bullets"><li>箇条一</li><li>箇条二</li><li>箇条三</li></ul>'
            '<div class="scroll"><table><thead><tr><th>a</th><th>b</th></tr></thead><tbody>'
            "<tr><td>1</td><td>2</td></tr><tr><td>3</td><td>4</td></tr></tbody></table></div>"
            '<p class="body-copy">本文</p></section>'
        )
        html = '<div class="wrap">' + "".join(section % (i, i) for i in range(1, 400)) + "</div>"
        # 画像（data: の長い属性）を含む大きい頁でも遅くならない。
        html += '<div class="img-figure"><div class="img-frame"><img src="data:image/png;base64,' + "A" * 1_500_000 + '" alt="画像"></div></div>'

        started = time.perf_counter()
        out, infos = number_blocks(html)
        elapsed = time.perf_counter() - started

        self.assertGreater(len(html), 1_000_000)
        self.assertEqual(len(infos), 399 * (1 + 3 + 2 + 1) + 1)
        self.assertLess(elapsed, 1.0, "number_blocks took %.2f s" % elapsed)
        self.assertEqual(out.count("data-blk="), len(infos))


def _fake_review(**overrides):
    modes = {"none": (), "shiteki": ("shiteki",), "tensaku": ("tensaku",), "both": ("shiteki", "tensaku")}

    def normalize_mode(value):
        text = str(value or "").strip().lower()
        return text if text in modes else "none"

    values = {
        "normalize_mode": normalize_mode,
        "roles_for_mode": lambda mode: modes[mode],
        "SHITEKI_SCRIPT": "window.__shiteki = 1;",
        "TENSAKU_SCRIPT": "window.__tensaku = 1;",
        "REVIEW_CSS_SHITEKI": ".rv-shiteki{color:var(--ink)}",
        "REVIEW_CSS_TENSAKU": ".rv-tensaku{color:var(--ink)}",
        "ROLE_ORDER": ("decision", "shiteki", "tensaku"),
    }
    values.update(overrides)
    return types.SimpleNamespace(**values)


SECTIONS = [
    {"component": "examples", "label": "具体例", "content": [{"cards": [{"title": "カード", "text": "本文"}]}, {"items": ["箇条"]}]},
    {"component": "decision", "label": "選ぶこと", "content": {"groups": [{"legend": "どれ", "kind": "radio", "options": [{"label": "A"}, {"label": "B"}]}]}},
]


def _render(review=None, sections=None, **extra) -> str:
    content = {"overview": "導入文です。", "sections": sections or SECTIONS, **extra}
    if review is not None:
        content["review"] = review
    return render_components(_plan("overview", "examples", "decision"), title="見本", content=content)


def _scripts(html: str) -> list[str]:
    return [m.strip() for m in re.findall(r"<script>(.*?)</script>", html, flags=re.S)]


class WiringTests(unittest.TestCase):
    def setUp(self):
        self._saved = rc._review_scripts
        rc._review_scripts = _fake_review()

    def tearDown(self):
        rc._review_scripts = self._saved

    def test_without_review_the_page_is_what_it_was(self):
        html = _render()

        self.assertEqual(_scripts(html), [DECISION_SCRIPT.strip()])
        self.assertNotIn("data-blk", html)
        self.assertNotIn("rv-shiteki", html)
        self.assertNotIn("data-review-mode", html)
        self.assertEqual(html.count("<style>"), 1)

    def test_review_none_and_unknown_values_are_the_same_as_not_writing_it(self):
        base = _render()

        for value in ("none", "", "unknown", None, 5, {"mode": "bogus"}):
            self.assertEqual(_render(review=value), base, repr(value))

    def test_shiteki_adds_one_script_after_the_decision_script_one_css_and_numbers(self):
        html = _render(review="shiteki")

        self.assertEqual(_scripts(html), [DECISION_SCRIPT.strip(), "window.__shiteki = 1;"])
        self.assertEqual(html.count("<style>"), 1)
        style = html[html.index("<style>") : html.index("</style>")]
        self.assertIn(".rv-shiteki{color:var(--ink)}", style)
        self.assertNotIn(".rv-tensaku", html)
        self.assertEqual([n["blk"] for n in _walk(html)], list(range(1, 1 + html.count("data-blk="))))
        self.assertGreaterEqual(html.count("data-blk="), 3)  # 導入文・カード・箇条
        self.assertTrue(html.rstrip().endswith("</script></body></html>"))

    def test_both_puts_shiteki_then_tensaku_after_the_decision_script(self):
        html = _render(review="both")

        self.assertEqual(_scripts(html), [DECISION_SCRIPT.strip(), "window.__shiteki = 1;", "window.__tensaku = 1;"])
        style = html[html.index("<style>") : html.index("</style>")]
        self.assertLess(style.index(".rv-shiteki"), style.index(".rv-tensaku"))

    def test_review_can_be_written_as_a_mapping_and_in_other_cases(self):
        self.assertEqual(_scripts(_render(review={"mode": "tensaku"})), [DECISION_SCRIPT.strip(), "window.__tensaku = 1;"])
        self.assertEqual(_scripts(_render(review="BOTH"))[1:], ["window.__shiteki = 1;", "window.__tensaku = 1;"])

    def test_the_scripts_are_laid_out_like_the_decision_script(self):
        html = _render(review="both")

        self.assertIn("</script>\n<script>\nwindow.__shiteki = 1;\n</script>\n<script>\nwindow.__tensaku = 1;\n</script></body>", html)

    def test_numbering_skips_the_decision_section_and_counts_the_lede(self):
        html = _render(review="shiteki")
        kinds = {n["tag"] + "." + ".".join(sorted(n["classes"])) for n in _walk(html)}

        self.assertIn("p.lede", kinds)
        self.assertIn("div.card", kinds)
        self.assertFalse(any("fieldset" in n["ancestors"][i][0] for n in _walk(html) for i in range(len(n["ancestors"]))))

    def test_a_missing_review_module_means_no_script_no_css_no_numbers(self):
        rc._review_scripts = None
        html = _render(review="both")

        self.assertEqual(_scripts(html), [DECISION_SCRIPT.strip()])
        self.assertNotIn("data-blk", html)

    def test_a_broken_review_module_does_not_break_the_page(self):
        def boom(value):
            raise RuntimeError("x")

        rc._review_scripts = _fake_review(normalize_mode=boom)

        self.assertEqual(_scripts(_render(review="both")), [DECISION_SCRIPT.strip()])


MANUSCRIPT = {
    "markdown": "# 見出し\n\n本文の段落です。\n\n- 箇条\n",
    "label": "intro-01",
    "mode": "tensaku",
    "source_path": "docs/intro.md",
    "sha256": "0" * 64,
    "eol": "lf",
}


def _manuscript_sections(value=None) -> list[dict]:
    return [{"component": "manuscript", "label": "原稿", "content": value if value is not None else dict(MANUSCRIPT)}] + SECTIONS


class ManuscriptSectionTests(unittest.TestCase):
    def setUp(self):
        self._saved = rc._review_scripts
        rc._review_scripts = _fake_review()

    def tearDown(self):
        rc._review_scripts = self._saved

    def test_the_label_is_the_manuscript_label(self):
        self.assertEqual(rc.LABELS["manuscript"], "原稿")

    def test_manuscript_section_has_its_mode_and_loads_its_role_even_when_review_is_none(self):
        html = _render(sections=_manuscript_sections())

        self.assertEqual(_scripts(html), [DECISION_SCRIPT.strip(), "window.__tensaku = 1;"])
        self.assertIn('<section data-component="manuscript" id="sec-1" data-review-mode="tensaku"><h2>原稿</h2>', html)
        self.assertEqual(html.count("data-review-mode="), 1)
        style = html[html.index("<style>") : html.index("</style>")]
        self.assertIn(".rv-tensaku", style)
        self.assertIn(".ms-blk", style)
        self.assertNotIn(".rv-shiteki", style)

    def test_manuscript_blocks_are_numbered_by_the_manuscript_and_other_units_are_left_alone(self):
        html = _render(review="both", sections=_manuscript_sections())

        walked = _walk(html)
        self.assertTrue(all("ms-blk" in w["classes"] for w in walked), [w["classes"] for w in walked])
        self.assertEqual([w["blk"] for w in walked], [1, 2, 3])
        self.assertEqual(_scripts(html), [DECISION_SCRIPT.strip(), "window.__shiteki = 1;", "window.__tensaku = 1;"])

    def test_the_manuscript_text_and_the_source_textarea_are_in_the_section(self):
        html = _render(sections=_manuscript_sections())
        start = html.index('data-component="manuscript"')
        section = html[start : html.index("</section>", start)]

        self.assertIn('<article class="ms" data-prose="raw">', section)
        self.assertIn("本文の段落です。", section)
        self.assertIn('<textarea id="ms-source"', section)
        self.assertIn('data-label="intro-01"', section)
        self.assertIn('data-path="docs/intro.md"', section)

    def test_mode_follows_the_section_then_the_page_review_then_shiteki(self):
        shiteki = dict(MANUSCRIPT, mode="shiteki")
        no_mode = {k: v for k, v in MANUSCRIPT.items() if k != "mode"}
        bad_mode = dict(MANUSCRIPT, mode="bogus")

        self.assertIn('data-review-mode="shiteki"', _render(sections=_manuscript_sections(shiteki)))
        self.assertIn('data-review-mode="shiteki"', _render(sections=_manuscript_sections(no_mode)))
        self.assertIn('data-review-mode="tensaku"', _render(review="tensaku", sections=_manuscript_sections(no_mode)))
        self.assertIn('data-review-mode="shiteki"', _render(review="both", sections=_manuscript_sections(bad_mode)))
        self.assertEqual(
            _scripts(_render(sections=_manuscript_sections(shiteki))),
            [DECISION_SCRIPT.strip(), "window.__shiteki = 1;"],
        )

    def test_manuscript_without_the_markdown_module_falls_back_to_an_escaped_pre(self):
        saved = (rc._render_markdown, rc._source_textarea)
        rc._render_markdown = None
        rc._source_textarea = None
        try:
            html = _render(sections=_manuscript_sections(dict(MANUSCRIPT, markdown="<b>生の HTML</b> & 記号\n")))
        finally:
            rc._render_markdown, rc._source_textarea = saved

        self.assertIn('<pre class="ms-fallback">&lt;b&gt;生の HTML&lt;/b&gt; &amp; 記号\n</pre>', html)
        self.assertNotIn("<b>生の HTML</b>", html)

    def test_a_manuscript_given_as_a_plain_string_is_still_shown(self):
        html = _render(sections=_manuscript_sections("ただの文字列の原稿です。"))

        self.assertIn("ただの文字列の原稿です。", html)
        self.assertIn('data-review-mode="shiteki"', html)

    def test_manuscript_css_is_only_on_pages_with_a_manuscript(self):
        self.assertNotIn(".ms-blk", _render())
        self.assertNotIn(".ms-blk", _render(review="both"))
        self.assertIn(".ms-blk", _render(sections=_manuscript_sections()))

    def test_the_manuscript_section_is_in_the_table_of_contents(self):
        html = _render(
            sections=_manuscript_sections(),
            rail=[{"heading": "目次", "toc": True}],
        )

        self.assertIn('<a href="#sec-1">原稿</a>', html)


@unittest.skipIf(real_review_scripts is None, "review_scripts がまだ無い")
class RealReviewScriptsTests(unittest.TestCase):
    def test_pages_with_the_real_scripts_have_them_in_role_order(self):
        for review, roles in (
            ("shiteki", ("SHITEKI_SCRIPT",)),
            ("tensaku", ("TENSAKU_SCRIPT",)),
            ("both", ("SHITEKI_SCRIPT", "TENSAKU_SCRIPT")),
        ):
            html = _render(review=review)
            self.assertEqual(
                _scripts(html),
                [DECISION_SCRIPT.strip()] + [getattr(real_review_scripts, name).strip() for name in roles],
                review,
            )
            self.assertEqual(html.count("<style>"), 1)

    def test_none_stays_a_single_script_page(self):
        self.assertEqual(_scripts(_render()), [DECISION_SCRIPT.strip()])


if __name__ == "__main__":
    unittest.main()

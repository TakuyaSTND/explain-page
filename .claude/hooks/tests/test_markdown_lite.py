"""原稿をブロックに分けて頁へ組む部品（visual/markdown_lite.py）の試験（2026-10-09・指摘と添削の作り込み）。

何を守るか＝
  ①ブロックの分け方が akapen 0.2.0（MIT）の添削の雛形の parseBlocks と同じ規則であること
    （同じ原稿で同じブロック数・同じ番号・同じ型・同じ区切り）。復元（先頭＋各ブロックの本文と区切り）は
    原文と1字も違わない。akapen が手元に入っている環境では、その JS を node で走らせて乱数の原稿で突き合わせる。
  ②生の HTML は全部エスケープされ、頁の文字に http・https・file の scheme が残らない
    （検品の外部依存の判定で落ちないように）。
  ③出力のタグの入れ子が崩れない（検品は入れ子の崩れを errors にする）。
  ④hidden の textarea の中身が、ブラウザの value で原文と逐語一致する形で組まれる。
"""
from __future__ import annotations

import html
import random
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from html.parser import HTMLParser
from pathlib import Path

HOOKS_DIR = Path(__file__).resolve().parents[1]
if str(HOOKS_DIR) not in sys.path:
    sys.path.insert(0, str(HOOKS_DIR))

from visual import markdown_lite as ml  # noqa: E402

README = """<!-- badges: build=ok -->
# Sample Tool

[![build](https://img.example.com/badge.svg)](https://example.com/ci) **Sample Tool** は、_小さな_ README です。\
詳しくは [公式](https://example.com/docs "t") と <https://example.com/auto> と https://example.com/bare. を見る。

## Install

```bash
curl -fsSL https://example.com/install.sh | sh
npm install sample_tool
```

1. `init` を実行する
2. `config.yml` を編集する
   - `api_key` を入れる
   - `mode` を選ぶ
3. 実行する

| Option | Default | 説明 |
|:--|:-:|--:|
| `--fast` | off | 速い |
| `--url` | https://example.com | 行き先 |

> **注意**: 本番では使わない。
> 詳細は [注意書き](https://example.com/warn)。

---

最後の段落。
改行つき。
"""

README_TYPES = [
    "comment", "heading", "paragraph", "heading", "code", "list", "table", "quote", "hr", "paragraph",
]

SCHEMES = ("http://", "https://", "file://")


class _Balance(HTMLParser):
    """タグの入れ子が崩れていないかを見る（閉じ忘れ・順序違いを数える）。"""

    VOID = {"br", "hr", "img", "input", "meta", "link"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.stack = []
        self.problems = []

    def handle_starttag(self, tag, attrs):
        if tag not in self.VOID:
            self.stack.append(tag)

    def handle_endtag(self, tag):
        if tag in self.VOID:
            return
        if not self.stack or self.stack[-1] != tag:
            self.problems.append("</%s> と %s" % (tag, self.stack[-1:] or "なし"))
            if tag in self.stack:
                while self.stack and self.stack.pop() != tag:
                    pass
            return
        self.stack.pop()


def _problems(fragment):
    parser = _Balance()
    parser.feed(fragment)
    parser.close()
    return parser.problems + ["閉じていない: %s" % parser.stack] * bool(parser.stack)


def _blocks(md):
    return [(b.type, b.md) for b in ml.parse_blocks(md).items]


class ParseBlocksTests(unittest.TestCase):
    def test_restore_is_verbatim_for_many_shapes(self):
        cases = [
            "", "\n", "\n\n", "a", "a\n", "a\n\n", "\n\na", "# t\n\n\n\nb\n\n", README,
            "   \n\n  x  \n\t\n", "\ufeff# bom\n", "a\n```\ncode with no close", "<!-- 1\n2\n3 -->\nx\n",
            "x\r\ny\r\n", "|a|b|\n|-|-|\n|1|2|\n", "- a\n- b\n\n\n- c\n", "\u3000\n\n本文\n",
        ]
        for md in cases:
            with self.subTest(md=md[:20]):
                self.assertEqual(ml.restore(ml.parse_blocks(md)), md)

    def test_types_and_numbers_of_a_readme(self):
        parsed = ml.parse_blocks(README)

        self.assertEqual([b.type for b in parsed.items], README_TYPES)
        self.assertEqual(ml.count_blocks(README), len(README_TYPES))

    def test_each_type_is_recognised(self):
        md = (
            "# 見出し\n\n本文\n\n- 項目\n\n| a | b |\n|---|---|\n| 1 | 2 |\n\n> 引用\n\n```\ncode\n```\n\n---\n\n<!-- c -->\n"
        )

        self.assertEqual(
            [b.type for b in ml.parse_blocks(md).items],
            ["heading", "paragraph", "list", "table", "quote", "code", "hr", "comment"],
        )

    def test_blank_lines_split_blocks_but_a_fence_keeps_blank_lines_inside(self):
        md = "```\na\n\nb\n```\n\nafter\n"

        self.assertEqual([t for t, _m in _blocks(md)], ["code", "paragraph"])
        self.assertEqual(_blocks(md)[0][1], "```\na\n\nb\n```")

    def test_a_longer_fence_needs_an_equal_or_longer_close(self):
        md = "````\n```\ninner\n```\n````\nnext\n"

        self.assertEqual(_blocks(md)[0], ("code", "````\n```\ninner\n```\n````"))

    def test_a_multi_line_comment_is_one_block(self):
        md = "<!-- a\nb\n-->\n\ntext"

        self.assertEqual([t for t, _m in _blocks(md)], ["comment", "paragraph"])

    def test_leading_blank_lines_go_to_head_and_gaps_keep_the_blank_lines(self):
        parsed = ml.parse_blocks("\n\nA\n\n\nB\n")

        self.assertEqual(parsed.head, "\n\n")
        self.assertEqual([b.gap for b in parsed.items], ["\n\n\n", "\n"])

    def test_a_document_without_blocks_has_zero_items_and_restores(self):
        for md in ("", "\n", "  \n \n", "\ufeff\n"):
            with self.subTest(md=md):
                parsed = ml.parse_blocks(md)
                self.assertEqual(parsed.items, [])
                self.assertEqual(ml.restore(parsed), md)

    def test_the_js_whitespace_set_is_used(self):
        # JS の trim は U+FEFF（BOM）と U+3000 を空白にし、U+0085 は空白にしない。
        self.assertEqual(ml.count_blocks("\ufeff\n\u3000\nx"), 1)
        self.assertEqual(ml.count_blocks("\x85\n\nx"), 2)

    def test_crlf_lines_are_normalised_by_render_not_by_parse(self):
        md = "# a\r\n\r\ntext\r\n"

        self.assertEqual(ml.restore(ml.parse_blocks(md)), md)
        self.assertEqual(ml.count_blocks(md), 2)
        self.assertEqual(ml.normalize_newlines("a\r\nb\rc\n"), "a\nb\nc\n")

    def test_a_fence_in_crlf_text_is_still_a_code_block_after_normalising(self):
        md = "```\r\ncode\r\n```\r\n\r\ntext\r\n"

        self.assertEqual(
            [b.type for b in ml.parse_blocks(ml.normalize_newlines(md)).items], ["code", "paragraph"]
        )


class DifferentialWithTheOriginalTests(unittest.TestCase):
    """akapen の添削の雛形の parseBlocks（JS）と、乱数の原稿 1500 本で同じ結果になること。

    akapen が入っていない環境（公開版の自動試験など）では飛ばす。移植元は読むだけ（書き換えない）。
    """

    TEMPLATE = Path.home() / ".claude" / "skills" / "akapen" / "assets" / "tensaku" / "template.html"

    FRAGMENTS = [
        "# 見出し", "## h2 ##", "#", "####### x", "text line", "もう一行", "- item", "* item", "+ item",
        "1. one", "2) two", "  - nested", "    deep", "> quote", ">quote2", "```", "```js", "~~~", "````",
        "---", "***", "- - -", "___", "| a | b |", "|---|---|", "| 1 | 2 |", "a | b", "-|-", "<!-- c -->",
        "<!--", "-->", "", "", "", "   ", "\u3000", "\ufeff", "\u00a0", "text\u2028x", "  ```",
        "\ue000x\ue001", "<b>x</b>", "[l](u)", "    ", "\t- tab item", "- [ ] todo", "10) ten", "a|b", ":--|--:",
    ]

    def _js_source(self):
        if not self.TEMPLATE.is_file() or not shutil.which("node"):
            self.skipTest("akapen の添削の雛形か node が無い")
        text = self.TEMPLATE.read_text(encoding="utf-8")
        start = text.find("const SENT_RE")
        end_marker = "const reconstruct"
        end = text.find(end_marker)
        if start < 0 or end < 0:
            self.skipTest("雛形の形が違う（SENT_RE か reconstruct が見つからない）")
        end = text.find("\n", end)
        return "const D0='\\uE000',D1='\\uE001',I0='\\uE002',I1='\\uE003';\n" + text[start:end]

    def test_same_blocks_gaps_head_on_random_documents(self):
        source = self._js_source()
        rng = random.Random(7)
        docs = []
        for _ in range(1500):
            lines = [rng.choice(self.FRAGMENTS) for _ in range(rng.randint(0, 14))]
            doc = "\n".join(lines)
            if rng.random() < 0.5:
                doc += "\n"
            if rng.random() < 0.15:
                doc = "\n" + doc
            docs.append(doc)
        docs += ["", "\n", "\n\n", "a", "a\n", "a\n\n", "\n\na", "# t\n\n\n\nb\n\n"]
        import json

        with tempfile.TemporaryDirectory(prefix="mdlite_") as tmp:
            tmp_path = Path(tmp)
            (tmp_path / "docs.json").write_text(json.dumps(docs, ensure_ascii=False), encoding="utf-8")
            (tmp_path / "run.js").write_text(
                source
                + "\nconst fs=require('fs');const docs=JSON.parse(fs.readFileSync(process.argv[2],'utf8'));"
                "fs.writeFileSync(process.argv[3],JSON.stringify(docs.map(d=>{const p=parseBlocks(d);"
                "return {head:p.head,items:p.items,endsNL:p.endsNL};})));\n",
                encoding="utf-8",
            )
            done = subprocess.run(
                ["node", str(tmp_path / "run.js"), str(tmp_path / "docs.json"), str(tmp_path / "out.json")],
                capture_output=True, text=True, encoding="utf-8", timeout=60, check=False,
            )
            self.assertEqual(done.returncode, 0, done.stderr[-300:])
            expected = json.loads((tmp_path / "out.json").read_text(encoding="utf-8"))
        bad = []
        for doc, reference in zip(docs, expected):
            ours = ml.parse_blocks(doc)
            same_items = [(b.type, b.md, b.gap) for b in ours.items] == [
                (b["type"], b["md"], b["gap"]) for b in reference["items"]
            ]
            same_head = (not ours.items) or ours.head == reference["head"]
            if not (same_items and same_head and ours.ends_nl == reference["endsNL"]
                    and ml.restore(ours) == doc):
                bad.append(doc)
        self.assertEqual(bad[:3], [], "移植元と食い違った原稿が %d 本" % len(bad))


class RenderTests(unittest.TestCase):
    def _render(self, md):
        return ml.render_markdown(md)

    def _blk_attrs(self, rendered):
        return re.findall(r'<div class="ms-blk" data-ms="(\d+)" data-blk="(\d+)" data-ms-type="([a-z]+)"', rendered)

    def test_the_article_wraps_every_block_with_one_based_numbers_and_types(self):
        rendered = self._render(README)

        self.assertTrue(rendered.startswith('<article class="ms" data-prose="raw">'))
        self.assertTrue(rendered.endswith("</article>"))
        attrs = self._blk_attrs(rendered)
        self.assertEqual([a[0] for a in attrs], [str(i) for i in range(1, len(README_TYPES) + 1)])
        self.assertTrue(all(a[0] == a[1] for a in attrs))
        self.assertEqual([a[2] for a in attrs], README_TYPES)

    def test_a_comment_keeps_its_place_as_a_hidden_empty_div_and_is_counted(self):
        rendered = self._render("<!-- メモ -->\n\n本文\n")

        self.assertIn('<div class="ms-blk" data-ms="1" data-blk="1" data-ms-type="comment" hidden></div>', rendered)
        self.assertIn('data-blk="2" data-ms-type="paragraph"', rendered)
        self.assertNotIn("メモ", rendered)

    def test_raw_html_is_always_escaped(self):
        md = (
            "<script>alert(1)</script>\n\n<img src=x onerror=alert(2)>\n\n"
            "`<b>code</b>`\n\n| <i>h</i> |\n|---|\n| <u>c</u> |\n\n> <div>q</div>\n"
        )
        rendered = self._render(md)

        for raw in ("<script", "<img", "<i>", "<u>", "<div>", "<b>"):
            self.assertNotIn(raw, rendered)
        self.assertIn("&lt;script&gt;alert(1)&lt;/script&gt;", rendered)
        self.assertIn("&lt;b&gt;code&lt;/b&gt;", rendered)

    def test_no_scheme_text_survives_anywhere_in_the_page_text(self):
        for md in (README, "a https://x.example/y b\n", "`https://c.example`\n", "HTTPS://UP.example\n",
                   "```\nfile:///etc/hosts\nHttp://mixed.example\n```\n", "[t](file:///a/b)\n"):
            with self.subTest(md=md[:24]):
                rendered = self._render(md)
                for needle in SCHEMES:
                    self.assertNotIn(needle, rendered.lower())

    def test_protocol_relative_attribute_text_is_split_too(self):
        rendered = self._render("`src=//cdn.example/x.js` と href=//a.example\n")

        self.assertNotRegex(rendered, r"(?i)(?:src|href|action|formaction)\s*=\s*[\"']?//")

    def test_the_browser_text_of_a_code_block_is_the_original_text(self):
        rendered = self._render("```\ncurl https://example.com/x | sh\n```\n")

        self.assertIn("curl &#104;ttps://example.com/x | sh", rendered)
        self.assertEqual(html.unescape(rendered).count("https://example.com/x"), 1)

    def test_links_are_words_plus_a_faint_destination_and_never_anchors(self):
        rendered = self._render("[公式サイト](https://example.com/docs/start?x=1 \"題\") と <https://example.com/auto>\n")

        self.assertNotIn("<a ", rendered)
        self.assertNotIn("href", rendered)
        self.assertIn('<span class="ms-link">公式サイト</span><span class="ms-url">（example.com/docs/start?x=1）</span>', rendered)
        self.assertIn('<span class="ms-link">example.com/auto</span>', rendered)

    def test_a_bare_url_loses_the_trailing_punctuation_to_the_text(self):
        rendered = self._render("見る https://example.com/bare. 終わり\n")

        self.assertIn('<span class="ms-link">example.com/bare</span>. 終わり', rendered)

    def test_an_image_becomes_a_bracketed_note_with_its_alt(self):
        rendered = self._render("![図の説明](pics/a.png) と ![](b.png)\n")

        self.assertNotIn("<img", rendered)
        self.assertIn('<span class="ms-img">[画像: 図の説明]</span>', rendered)
        self.assertIn('<span class="ms-img">[画像]</span>', rendered)

    def test_inline_code_strong_and_emphasis(self):
        rendered = self._render("**太字** と _弱い_ と `code` と *強調* と __太字2__\n")

        self.assertIn("<strong>太字</strong>", rendered)
        self.assertIn("<em>弱い</em>", rendered)
        self.assertIn("<code>code</code>", rendered)
        self.assertIn("<em>強調</em>", rendered)
        self.assertIn("<strong>太字2</strong>", rendered)

    def test_a_hard_break_becomes_br_and_a_soft_break_stays_a_newline(self):
        rendered = self._render("一行目  \n二行目\n三行目\n")

        self.assertIn("一行目<br>二行目\n三行目", rendered)

    def test_headings_keep_their_levels_and_drop_closing_hashes(self):
        rendered = self._render("# 一 ##\n\n### 三\n\n###### 六\n\n####### 七つは見出しでない\n")

        self.assertIn("<h1>一</h1>", rendered)
        self.assertIn("<h3>三</h3>", rendered)
        self.assertIn("<h6>六</h6>", rendered)
        self.assertIn("<p>####### 七つは見出しでない</p>", rendered)

    def test_code_block_language_class_and_unclosed_fence(self):
        rendered = self._render("```python\nprint(1)\n```\n\n```\n閉じない\n")

        self.assertIn('<pre><code class="lang-python">print(1)</code></pre>', rendered)
        self.assertIn("<pre><code>閉じない</code></pre>", rendered)

    def test_nested_and_ordered_lists(self):
        rendered = self._render("3. 三\n4. 四\n   - 入れ子 a\n   - 入れ子 b\n5. 五\n")

        self.assertIn('<ol start="3">', rendered)
        self.assertIn("<li>四<ul><li>入れ子 a</li><li>入れ子 b</li></ul></li>", rendered)

    def test_a_list_that_dedents_below_its_first_indent_keeps_every_item(self):
        rendered = self._render("  - 深い\n- 浅い\n")

        self.assertIn("深い", rendered)
        self.assertIn("浅い", rendered)

    def test_list_continuation_lines_join_the_item(self):
        rendered = self._render("- 一行目\n  続きの行\n- 次\n")

        self.assertIn("<li>一行目\n続きの行</li>", rendered)

    def test_table_alignment_cells_and_escaped_pipes(self):
        rendered = self._render("| 左 | 中 | 右 |\n|:--|:-:|--:|\n| a \\| b | c | d |\n| 短い |\n")

        self.assertIn('<th style="text-align:left">左</th>', rendered)
        self.assertIn('<th style="text-align:center">中</th>', rendered)
        self.assertIn('<th style="text-align:right">右</th>', rendered)
        self.assertIn('<td style="text-align:left">a | b</td>', rendered)
        self.assertIn('<td style="text-align:center"></td>', rendered)  # 足りないセルは空

    def test_a_quote_renders_its_inner_blocks(self):
        rendered = self._render("> # 引用の見出し\n>\n> 引用の本文\n")

        self.assertIn("<blockquote><h1>引用の見出し</h1><p>引用の本文</p></blockquote>", rendered)
        self.assertEqual(len(self._blk_attrs(rendered)), 1)  # 入れ子のブロックに番号は振らない

    def test_crlf_and_lf_render_the_same(self):
        self.assertEqual(self._render(README.replace("\n", "\r\n")), self._render(README))

    def test_the_output_tags_always_nest(self):
        nasty = [
            README,
            "**a *b** c*\n",
            "*a **b* c**\n",
            "__a _b__ c_\n",
            "`**x` y** z\n",
            "[**a](u) b**\n",
            "[a *b](u) c*\n",
            "![**x](y)\n",
            "**\n\n*\n\n_\n\n__\n",
            "> > > 深い\n> 浅い\n",
            "- a\n  - b\n    - c\n  - d\n- e\n",
            "|a|b|\n|-|-|\n|**x|y**|\n",
            "<<<>>> & &amp; &#104; &lt;\n",
            "# **#\n\n## `\n",
        ]
        for md in nasty:
            with self.subTest(md=md[:24]):
                self.assertEqual(_problems(self._render(md)), [])

    def test_an_astronomically_long_paragraph_is_still_escaped_and_cheap(self):
        rendered = self._render("`" + "あ`" * 12000 + "\n")

        self.assertNotIn("<script", rendered)
        self.assertIn('data-blk="1"', rendered)


class SourceTextareaTests(unittest.TestCase):
    def _textarea(self, md, **kw):
        args = dict(label="intro-01", path="docs/intro.md", sha="a" * 64, eol="lf")
        args.update(kw)
        return ml.source_textarea(md, **args)

    def _value(self, fragment):
        """HTML の決まり（textarea の直後の改行を1つ捨てる→文字参照を戻す）で value を再現する。"""
        start = fragment.index(">") + 1
        end = fragment.rindex("</textarea>")
        body = fragment[start:end]
        self.assertTrue(body.startswith("\n"))
        return html.unescape(body[1:])

    def test_the_shape_and_attributes(self):
        fragment = self._textarea("本文\n", label='a"b', path="d/x.md", sha="f" * 64, eol="crlf")

        self.assertTrue(fragment.startswith('<textarea id="ms-source" class="ms-source" hidden readonly aria-hidden="true" '))
        self.assertIn('data-label="a&quot;b"', fragment)
        self.assertIn('data-path="d/x.md"', fragment)
        self.assertIn('data-sha="%s"' % ("f" * 64), fragment)
        self.assertIn('data-eol="crlf"', fragment)
        self.assertTrue(fragment.endswith("</textarea>"))

    def test_an_unknown_eol_falls_back_to_lf(self):
        self.assertIn('data-eol="lf"', self._textarea("x", eol="cr"))

    def test_value_is_the_original_text_for_hostile_content(self):
        for md in (
            "\n先頭が改行\n", "</textarea><script>alert(1)</script>", "& &amp; &lt; &#104;ttps://x &",
            README, "a\r\nb\rc\n", "引用 \"q\" 'a'\n",
        ):
            with self.subTest(md=md[:20]):
                self.assertEqual(self._value(self._textarea(md)), ml.normalize_newlines(md))

    def test_the_first_newline_is_one_so_a_leading_blank_line_survives(self):
        fragment = self._textarea("\nA\n")

        self.assertIn(">\n\nA\n</textarea>", fragment)

    def test_no_scheme_text_and_no_angle_bracket_survive(self):
        fragment = self._textarea(README + "\nfile:///x HTTP://Y src=//z\n")

        for needle in SCHEMES:
            self.assertNotIn(needle, fragment.lower())
        self.assertNotRegex(fragment, r"(?i)(?:src|href|action|formaction)\s*=\s*[\"']?//")
        inner = fragment[fragment.index(">") + 1:fragment.rindex("</textarea>")]
        self.assertNotIn("<", inner)

    def test_defang_is_idempotent_and_keeps_the_display(self):
        once = ml.defang_urls("https://a.example と file://b と src=//c")

        self.assertEqual(ml.defang_urls(once), once)
        self.assertEqual(html.unescape(once), "https://a.example と file://b と src=//c")


class ModuleHygieneTests(unittest.TestCase):
    def test_the_source_line_is_in_the_docstring_and_nothing_private_is_written(self):
        text = Path(ml.__file__).read_text(encoding="utf-8")

        self.assertIn("ブロックの分け方は akapen 0.2.0（MIT）の添削の雛形の parseBlocks と同じ規則", ml.__doc__)
        lowered = text.lower()
        # 公開版の書き出しの検査に当たらないよう、禁じる語はここでも組み立てて書く。
        for forbidden in ("taki" + "moto", "tak" + "uy", "c:/" + "users/", "c:" + chr(92) + "users", "app" + "data"):
            self.assertNotIn(forbidden, lowered, forbidden)
        self.assertIsNone(re.search(r"[a-z0-9._-]+" + chr(64) + r"[a-z0-9-]+[.][a-z]+", lowered))

    def test_the_file_uses_lf_line_endings(self):
        self.assertNotIn(b"\r", Path(ml.__file__).read_bytes())


if __name__ == "__main__":
    unittest.main()

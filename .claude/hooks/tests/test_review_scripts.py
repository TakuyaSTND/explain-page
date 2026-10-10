"""指摘と添削の script・CSS（visual/review_scripts.py）の静的な検査（2026-10-09）。

見るもの：
  - 3本の script（判断欄・指摘・添削）が node の構文検査を通る
  - 検品の外部依存の判定（receipts.py）に当たる文字が script にも CSS にも無い
  - 札（CHIPS）が akapen の指摘 kit と同じ7種（kit の写しが手元にある環境だけ）
  - 大きさの上限（毎回の説明の頁に載るので、増えたら気づけるようにする）
  - normalize_mode・roles_for_mode・review_css
  - 添削の script の「ブロックの分け方」と「Markdown の描き方」が Python 側（markdown_lite）と
    1字も違わない（node で JS の部分を動かして比べる）

⚠️script は全頁共通＝構文の誤りで全部の頁の赤ペンが黙って死ぬ。だから構文検査と本物のブラウザの試験
（test_review_browser.py）の両方を置く。
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HOOKS_DIR = Path(__file__).resolve().parents[1]
if str(HOOKS_DIR) not in sys.path:
    sys.path.insert(0, str(HOOKS_DIR))

from visual import receipts
from visual import review_scripts as rs

try:
    from visual import markdown_lite
except ImportError:  # 原稿の頁の部品が無い環境
    markdown_lite = None  # type: ignore[assignment]

AKAPEN_KIT = Path.home() / ".claude" / "skills" / "akapen" / "assets" / "shiteki" / "kit-template.html"

# 実測（2026-10-09）に1割の余裕を足した上限。増やすときは、毎回の頁に載る重さが増えることを承知で上げる。
MAX_SHITEKI_SCRIPT = 11_500
MAX_TENSAKU_SCRIPT = 48_000
MAX_CSS_BOTH = 13_500


def _node_check(text: str) -> subprocess.CompletedProcess:
    with tempfile.TemporaryDirectory(prefix="review_script_") as tmp:
        path = Path(tmp) / "script.js"
        path.write_text(text, encoding="utf-8")
        return subprocess.run(
            ["node", "--check", str(path)],
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=30,
            check=False,
        )


class NodeSyntaxTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which("node"), "node が無い")
    def test_every_approved_script_passes_node_check(self):
        scripts = {"shiteki": rs.SHITEKI_SCRIPT, "tensaku": rs.TENSAKU_SCRIPT}
        try:
            from visual.render_components import DECISION_SCRIPT

            scripts["decision"] = DECISION_SCRIPT
        except ImportError:
            pass
        for name, text in scripts.items():
            completed = _node_check(text)
            self.assertEqual(completed.returncode, 0, "%s: %s" % (name, completed.stderr))

    def test_role_scripts_map_matches_the_constants(self):
        self.assertIs(rs.ROLE_SCRIPTS["shiteki"], rs.SHITEKI_SCRIPT)
        self.assertIs(rs.ROLE_SCRIPTS["tensaku"], rs.TENSAKU_SCRIPT)
        self.assertEqual(rs.ROLE_ORDER, ("decision", "shiteki", "tensaku"))


class ForbiddenStringTests(unittest.TestCase):
    TEXTS = {
        "SHITEKI_SCRIPT": rs.SHITEKI_SCRIPT,
        "TENSAKU_SCRIPT": rs.TENSAKU_SCRIPT,
        "REVIEW_CSS_SHITEKI": rs.REVIEW_CSS_SHITEKI,
        "REVIEW_CSS_TENSAKU": rs.REVIEW_CSS_TENSAKU,
    }

    def test_receipts_patterns_do_not_match_the_raw_text(self):
        # 検品の判定は地の文を除いた部分にだけ走るが、ここでは文字列にそのまま当てる＝より厳しい。
        for name, text in self.TEXTS.items():
            for label, pattern in (
                ("外部の URL", receipts.EXTERNAL_URL),
                ("通信のコード", receipts.NETWORK_CODE),
                ("読み込みの属性", receipts.RESOURCE_ATTRIBUTE),
                ("CSS の url()", receipts.CSS_URL),
                ("CSS の @import", receipts.CSS_IMPORT),
            ):
                found = pattern.search(text)
                self.assertIsNone(found, "%s に %s: %r" % (name, label, found and found.group(0)))

    def test_the_gate_style_check_finds_no_external_dependency(self):
        for name, text in self.TEXTS.items():
            tag = "script" if name.endswith("SCRIPT") else "style"
            wrapped = "<%s>%s</%s>" % (tag, text, tag)
            self.assertIsNone(receipts.external_dependency_reason(wrapped), name)

    def test_no_markup_that_breaks_out_of_the_script_element(self):
        for name in ("SHITEKI_SCRIPT", "TENSAKU_SCRIPT"):
            text = self.TEXTS[name]
            self.assertNotIn("</script", text.lower(), name)
            # ブラウザの「script data escaped」の状態に入る組み合わせを避ける。
            self.assertNotIn("<" + "!--", text, name)
            self.assertNotIn("--" + ">", text, name)
            self.assertNotIn("javascript:", text.lower(), name)

    def test_scripts_do_not_use_what_the_contract_forbids(self):
        for name in ("SHITEKI_SCRIPT", "TENSAKU_SCRIPT"):
            text = self.TEXTS[name]
            self.assertNotIn("randomUUID", text, name)
            self.assertNotIn("data-shiteki", text, name)
            self.assertNotIn("createObjectURL", text, name)
            self.assertNotIn("document.write", text, name)
            self.assertNotIn("eval(", text, name)

    def test_files_carry_no_personal_marks(self):
        source = (HOOKS_DIR / "visual" / "review_scripts.py").read_text(encoding="utf-8")
        # 試験のファイルにも個人の名前・機械のパスを書かない（公開版の書き出しの検査で止まる）ので、断片をつなぐ。
        for needle in ("takimo" + "to", "tak" + "uy", "C:/" + "Users/", "App" + "Data", "@temp" + "estai", "https" + "://", "http" + "://"):
            self.assertNotIn(needle, source, needle)
        self.assertIn("akapen 0.2.0（MIT）", source)


class CssTests(unittest.TestCase):
    def test_colors_come_only_from_the_page_tokens(self):
        for name in ("REVIEW_CSS_SHITEKI", "REVIEW_CSS_TENSAKU"):
            css = getattr(rs, name)
            self.assertIsNone(re.search(r"#[0-9a-fA-F]{3,8}\b(?![\w-])", css), name)
            self.assertIsNone(re.search(r"\b(?:rgb|rgba|hsl|hsla)\s*\(", css), name)
            self.assertIsNone(re.search(r"(?<![\w-])(?:white|black|red|blue|green)(?![\w-])", css), name)
            used = set(re.findall(r"var\(--([a-z0-9-]+)", css))
            allowed = {"fail", "fail-soft", "accent", "accent-soft", "surface", "surface-2", "ink", "ink-2", "ink-3",
                       "rule", "on-accent", "warn", "pass"}
            self.assertLessEqual(used, allowed, name)

    def test_floating_parts_sit_above_page_content_and_hide_in_print(self):
        css = rs.REVIEW_CSS_SHITEKI
        fixed_blocks = [body for body in re.findall(r"\{([^{}]*)\}", css) if "position:fixed" in body]
        self.assertGreaterEqual(len(fixed_blocks), 4)
        # 固定の板・帯・引き出しは全部 1200 以上。2 の z-index は印の丸（本文の中）だけ。
        for body in fixed_blocks:
            found = re.search(r"z-index:(\d+)", body)
            self.assertIsNotNone(found, body[:60])
            self.assertGreaterEqual(int(found.group(1)), 1200, body[:60])
        self.assertIn("@media print", css)
        printed = css[css.index("@media print") :]
        for selector in ("#rv-bar", ".rv-sheet", ".rv-drawer", ".rv-out"):
            self.assertIn(selector, printed)

    def test_review_css_includes_the_shared_part_once(self):
        both = rs.review_css(("shiteki", "tensaku"))
        self.assertEqual(both.count("#rv-bar{position:fixed"), 1)
        self.assertIn(".rv-sheet{", both)
        self.assertIn(".rv-tabs{", both)
        self.assertEqual(rs.review_css(()), "")
        self.assertEqual(rs.review_css(("decision",)), "")
        only = rs.review_css(("tensaku",))
        self.assertIn("#rv-bar{", only)
        self.assertNotIn(".rv-sheet{", only)
        self.assertLess(len(both.encode("utf-8")), len(rs.REVIEW_CSS_SHITEKI.encode("utf-8")) + len(rs.REVIEW_CSS_TENSAKU.encode("utf-8")))


class ChipsAndContractTests(unittest.TestCase):
    def test_chips_are_the_seven_of_the_akapen_kit_in_order(self):
        self.assertEqual(
            rs.CHIPS,
            ("削る", "短くする", "言い換える", "事実を確認", "図を直す", "順序を入れ替える", "ここは良い"),
        )
        self.assertIn("[" + ",".join('"%s"' % c for c in rs.CHIPS) + "]", rs.SHITEKI_SCRIPT)

    @unittest.skipUnless(AKAPEN_KIT.exists(), "akapen の kit の写しが手元に無い")
    def test_chips_match_the_akapen_kit_file(self):
        text = AKAPEN_KIT.read_text(encoding="utf-8")
        found = re.search(r"var CHIPS=\[([^\]]*)\]", text)
        self.assertIsNotNone(found)
        kit_chips = tuple(re.findall(r'"([^"]+)"', found.group(1)))
        self.assertEqual(rs.CHIPS, kit_chips)

    def test_fixed_contract_words_are_in_the_scripts(self):
        for needle in ("window.pageReply", "rv:mode", "rv-bar", "uc-shiteki:", "貼り付ける文章を作る", "rv-compose"):
            self.assertIn(needle, rs.SHITEKI_SCRIPT, needle)
        for needle in ("window.pageReply", "rv:mode", "rv-bar", "uc-tensaku:", "ms-source", "貼り付ける文章を作る"):
            self.assertIn(needle, rs.TENSAKU_SCRIPT, needle)
        for needle in ("(削除)", "(追加)", "- 変更なし", "markdown", "説明の頁の添削＝完成形は無し"):
            self.assertIn(needle, rs.TENSAKU_SCRIPT, needle)
        for tab in ("直す", "完成形", "差分", "ソース全体"):
            self.assertIn(tab, rs.TENSAKU_SCRIPT, tab)


class SizeTests(unittest.TestCase):
    def test_sizes_stay_under_the_limits(self):
        self.assertLessEqual(len(rs.SHITEKI_SCRIPT.encode("utf-8")), MAX_SHITEKI_SCRIPT)
        self.assertLessEqual(len(rs.TENSAKU_SCRIPT.encode("utf-8")), MAX_TENSAKU_SCRIPT)
        self.assertLessEqual(len(rs.review_css(("shiteki", "tensaku")).encode("utf-8")), MAX_CSS_BOTH)


class ModeTests(unittest.TestCase):
    def test_normalize_mode(self):
        for value, expected in (
            ("none", "none"),
            ("shiteki", "shiteki"),
            ("tensaku", "tensaku"),
            ("both", "both"),
            (" Both ", "both"),
            ({"mode": "tensaku"}, "tensaku"),
            ({"mode": "both", "x": 1}, "both"),
            (True, "both"),
            (False, "none"),
            (None, "none"),
            ("", "none"),
            ("zzz", "none"),
            ({"mode": "zzz"}, "none"),
            ({}, "none"),
            (3, "none"),
        ):
            self.assertEqual(rs.normalize_mode(value), expected, repr(value))

    def test_roles_for_mode(self):
        self.assertEqual(rs.roles_for_mode("both"), ("shiteki", "tensaku"))
        self.assertEqual(rs.roles_for_mode("none"), ())
        self.assertEqual(rs.roles_for_mode("shiteki"), ("shiteki",))
        self.assertEqual(rs.roles_for_mode("tensaku"), ("tensaku",))
        self.assertEqual(rs.roles_for_mode({"mode": "both"}), ("shiteki", "tensaku"))
        self.assertEqual(rs.roles_for_mode(True), ("shiteki", "tensaku"))
        self.assertEqual(rs.roles_for_mode("zzz"), ())
        # 並びは ROLE_ORDER の順で、判断欄は含めない。
        order = [r for r in rs.ROLE_ORDER if r in rs.roles_for_mode("both")]
        self.assertEqual(tuple(order), rs.roles_for_mode("both"))


_PARITY_CORPUS = [
    "一行だけ",
    "# 見出し\n\n本文です。\n続きの行。\n\n- 項目1\n- 項目2\n  - 入れ子\n- 項目3\n\n1. 一\n2. 二\n",
    "```py\nprint(1)\n\n\nprint(2)\n```\n\n文章\n",
    "| a | b |\n| - | - |\n| 1 | 2 |\n| 3 | 4 |\n\n後ろの段落\n",
    "> 引用1\n> 引用2\n\n<!-- コメント\n複数行 -->\n\n段落\n",
    "\n\n\n先頭に空行\n\n\n\n途中に多い空行\n\n\n",
    "末尾に改行なし\n\n次",
    "---\n\n***\n\n___\n",
    "段落\n- 箇条書きに続く\n段落に戻る\n",
    "~~~\nfence tilde\n~~~\n\n````\n```\nnested\n```\n````\n",
    "# H1\n## H2 ##\n### H3\n本文\n",
    "文[リンク](https://example.com/x \"title\")と ![図](a.png) と <https://example.com/y> と https://example.com/z。\n",
    "1) 括弧の番号\n2) 次\n\n* 星\n+ プラス\n",
    "|表|だけ|\n|---|---|\n|x|y|\n\n|区切りなし|\n|テキスト|\n",
    "強調 **太字** と *斜体* と `コード` と __太__ と _斜_ 。\n",
    "段落の途中  \nハードブレーク\n",
    "- a\n  - b\n    - c\n- d\n\n10. 十\n11. 十一\n",
    "<div>生の HTML</div> と <script>alert(1)</script> と a < b && c > d\n",
]

_PARITY_JS = (
    "const MS=null,$=()=>null,MODE='';const cut=(s,n)=>s.length>n?s.slice(0,n)+'…':s;\n"
    + rs._TENSAKU_CORE_JS
    + rs._TENSAKU_MD_JS
    + """
const corpus=JSON.parse(require('fs').readFileSync(process.argv[2],'utf8'));
const out=corpus.map(md=>{const p=parseBlocks(md);return {head:p.head,items:p.items.map(b=>({type:b.type,md:b.md,gap:b.gap})),html:p.items.map(b=>renderBlock(b))};});
console.log(JSON.stringify(out));
"""
)


@unittest.skipUnless(shutil.which("node") and markdown_lite is not None, "node か markdown_lite が無い")
class ParityWithPythonTests(unittest.TestCase):
    """添削の script の parseBlocks／renderBlock は、Python 側と同じ番号・同じ HTML を作る（頁と回答の番号がずれない）。"""

    @classmethod
    def setUpClass(cls):
        with tempfile.TemporaryDirectory(prefix="review_parity_") as tmp:
            script = Path(tmp) / "parity.js"
            corpus = Path(tmp) / "corpus.json"
            script.write_text(_PARITY_JS, encoding="utf-8")
            corpus.write_text(json.dumps(_PARITY_CORPUS, ensure_ascii=False), encoding="utf-8")
            completed = subprocess.run(
                ["node", str(script), str(corpus)],
                capture_output=True,
                text=True,
                encoding="utf-8",
                timeout=60,
                check=False,
            )
        if completed.returncode != 0:
            raise AssertionError(completed.stderr[-800:])
        cls.results = json.loads(completed.stdout)

    def test_block_split_matches_python(self):
        for md, got in zip(_PARITY_CORPUS, self.results):
            parsed = markdown_lite.parse_blocks(markdown_lite.normalize_newlines(md))
            expected = [{"type": b.type, "md": b.md, "gap": b.gap} for b in parsed.items]
            self.assertEqual(got["items"], expected, repr(md))
            self.assertEqual(got["head"], parsed.head, repr(md))

    def test_rendered_html_matches_python(self):
        for md, got in zip(_PARITY_CORPUS, self.results):
            parsed = markdown_lite.parse_blocks(markdown_lite.normalize_newlines(md))
            expected = [markdown_lite._render_block(b) for b in parsed.items]
            self.assertEqual(got["html"], expected, repr(md))

    def test_the_js_html_never_contains_a_raw_tag_from_the_source(self):
        # 生の HTML は全部エスケープされる（原稿の <script> が動かない）。
        index = len(_PARITY_CORPUS) - 1
        joined = "".join(self.results[index]["html"])
        self.assertNotIn("<script", joined)
        self.assertNotIn("<div>", joined)
        self.assertIn("&lt;script&gt;", joined)


if __name__ == "__main__":
    unittest.main()

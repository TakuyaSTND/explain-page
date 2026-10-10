"""原稿の頁（部品 manuscript）を render_page.py で組む試験（2026-10-09・指摘と添削の作り込み）。

何を守るか＝
  ①README 風の原稿（外部のリンク・コードブロック・表・引用・HTML コメント・CRLF）を渡すと、完全版・器用・
    文字だけの版の3つが書かれ、検品が通り、外部依存の判定（receipts）に当たらない。
  ②定義で欠けた部品は短い既定で足され、足したものが1行ずつ知らされる。overview だけは足さず強く警告する。
  ③文字だけの版の各行の頭に原稿のブロック番号 #N が付く（試問の読み手が番号で指せる）。
  ④頁の hidden の textarea（#ms-source）の value が、ブラウザで原文と逐語一致する（改行は LF）。
  ⑤赤ペンの役割（review）：説明の頁は両方・原稿の頁は原稿の mode の役割だけ（足りなければ足す）。
  ⑥原稿が読めないときは組み立てを止める（終了コード2）。
相手の包み（頁の組み立て・赤ペンの script）がまだ無い環境では、それが要る試験だけ飛ばす。
"""
from __future__ import annotations

import contextlib
import copy
import io
import json
import re
import shutil
import subprocess
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
from visual import markdown_lite as ml  # noqa: E402
from visual import render_components as rc  # noqa: E402
from visual import visual_smoke  # noqa: E402
from visual.receipts import external_dependency_reason  # noqa: E402

try:
    from visual import review_scripts  # noqa: E402
except ImportError:  # pragma: no cover
    review_scripts = None

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

最後の段落。href=//cdn.example.com/x.js のような形もある。
改行つき。
"""


CRLF = chr(13) + chr(10)


def _write(path, text, newline=""):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline=newline) as handle:
        handle.write(text)


def _spec(manuscript, *, name="ms-page", overview="原稿に指摘を打つ頁である。", extra=None):
    content = {
        "overview": overview,
        "sections": [{"component": "manuscript", "label": "原稿", "content": manuscript}],
    }
    content.update(extra or {})
    return {
        "name": name,
        "title": "原稿の確認",
        "components": list(rp.ALL_COMPONENTS),
        "reasons": ["project_novice_default"],
        "publish": "never",
        "content": content,
    }


class _Project:
    """一時フォルダの小さなプロジェクト（policy・原稿・書き出し先）。"""

    def __init__(self, td):
        self.root = Path(td) / "proj"
        self.out = Path(td) / "out"
        (self.root / ".claude").mkdir(parents=True)
        (self.root / ".claude" / "visual-hook-policy.json").write_text(
            json.dumps({"schema_version": 1, "enabled": True, "local_artifact_root": str(self.out)}),
            encoding="utf-8",
        )

    def doc(self, name, text, newline=""):
        _write(self.root / "docs" / name, text, newline)
        return "docs/" + name

    def run(self, spec, *, real_smoke=False):
        """main() を走らせる。返るもの＝(終了コード, 出力, 書き出した名前→バイト)。"""
        spec_path = self.root / "spec.json"
        spec_path.write_text(json.dumps(spec, ensure_ascii=False), encoding="utf-8")
        buffer = io.StringIO()
        fake_smoke = types.SimpleNamespace(status="pass", errors=(), metrics={})
        with contextlib.ExitStack() as stack:
            if not real_smoke:
                stack.enter_context(patch.object(rp, "run_visual_smoke", return_value=fake_smoke))
            stack.enter_context(patch.object(rp, "_approved_root_for", return_value=str(self.out)))
            stack.enter_context(contextlib.redirect_stdout(buffer))
            code = rp.main(["render_page.py", str(spec_path), "--project-root", str(self.root)])
        files = {}
        if self.out.is_dir():
            files = {item.name: item.read_bytes() for item in self.out.iterdir() if item.is_file()}
        return code, buffer.getvalue(), files


def _browser_eval(html_path, expression):
    """頁を実ブラウザで開き、expression（JS の式）の値を JSON で返す。pageerror の一覧も添える。"""
    playwright_path, reason = visual_smoke._resolve_playwright()
    if not playwright_path or not shutil.which("node"):
        raise unittest.SkipTest("Playwright か node が無い: %s" % (reason or ""))
    script = r"""
const { pathToFileURL } = require('url');
const { chromium } = require(process.argv[1]);
(async () => {
  let browser;
  try { browser = await chromium.launch({headless:true}); }
  catch (error) { console.log(JSON.stringify({skip:String(error).slice(0,200)})); return; }
  try {
    const page = await browser.newPage({viewport:{width:1280,height:900}});
    const errors = [];
    page.on('pageerror', e => errors.push(String(e).slice(0,200)));
    await page.goto(pathToFileURL(process.argv[2]).href, {waitUntil:'load', timeout:10000});
    const value = await page.evaluate(process.argv[3]);
    console.log(JSON.stringify({value, errors}));
  } finally { await browser.close(); }
})().catch(error => { console.log(JSON.stringify({fail:String(error).slice(0,300)})); process.exitCode = 1; });
"""
    done = subprocess.run(
        ["node", "-e", script, str(playwright_path), str(html_path), expression],
        capture_output=True, text=True, encoding="utf-8", timeout=90, check=False,
    )
    try:
        result = json.loads(done.stdout.strip().splitlines()[-1])
    except (IndexError, ValueError):
        raise AssertionError("browser run gave no JSON: %r %r" % (done.stdout[-300:], done.stderr[-300:]))
    if "skip" in result:
        raise unittest.SkipTest("ブラウザを起動できない: %s" % result["skip"])
    if "fail" in result:
        raise AssertionError(result["fail"])
    return result


class _NeedsRenderer(unittest.TestCase):
    def setUp(self):
        if getattr(rc, "_render_markdown", None) is None or getattr(rc, "_source_textarea", None) is None:
            self.skipTest("頁の組み立て側（render_components）が原稿の節をまだ組めない")
        self._td = tempfile.TemporaryDirectory(prefix="mspage_")
        self.addCleanup(self._td.cleanup)
        self.project = _Project(self._td.name)

    def build(self, manuscript_text, *, newline="", mode=None, **kw):
        path = self.project.doc("intro.md", manuscript_text, newline)
        manuscript = {"path": path, "label": "intro-01"}
        if mode:
            manuscript["mode"] = mode
        return self.project.run(_spec(manuscript, **kw))


class ReadmePageTests(_NeedsRenderer):
    def test_the_three_files_are_written_and_the_inspection_passes(self):
        code, out, files = self.build(README, newline="\r\n")

        self.assertEqual(code, 0, out)
        self.assertEqual(sorted(files), ["ms-page-artifact.html", "ms-page-text.txt", "ms-page.html"])
        self.assertEqual(out.count("合格=True"), 2, out)
        self.assertNotIn("合格=False", out)

    def test_no_external_dependency_is_found_in_either_page(self):
        _code, _out, files = self.build(README, newline="\r\n")

        for name in ("ms-page.html", "ms-page-artifact.html"):
            text = files[name].decode("utf-8")
            self.assertIsNone(external_dependency_reason(text), name)
            for needle in ("http://", "https://", "file://"):
                self.assertNotIn(needle, text.lower(), name)

    def test_the_inspection_itself_is_ok_and_names_nothing_unwrapped_or_unknown(self):
        self.build(README, newline=CRLF)
        html_path = self.project.out / "ms-page.html"

        with patch.object(rp, "run_visual_smoke", return_value=types.SimpleNamespace(
                status="pass", errors=(), metrics={})):
            result = rp.check(str(html_path), list(rp.ALL_COMPONENTS), str(self.project.root))

        self.assertTrue(result["inspection_ok"], result)
        self.assertEqual(result["unwrapped"], [])
        self.assertEqual(result["unknown"], [])
        self.assertEqual(result["errors"], [])
        self.assertEqual(result["missing_components"], [])

    def test_blocks_and_attributes_on_the_page(self):
        _code, _out, files = self.build(README, newline="\r\n")
        text = files["ms-page.html"].decode("utf-8")

        count = ml.count_blocks(README)
        numbers = re.findall(r'<div class="ms-blk" data-ms="(\d+)" data-blk="(\d+)"', text)
        self.assertEqual([n for n, _b in numbers], [str(i) for i in range(1, count + 1)])
        self.assertEqual(text.count('id="ms-source"'), 1)
        self.assertIn('data-eol="crlf"', text)
        self.assertIn('data-label="intro-01"', text)
        self.assertIn('data-path="docs/intro.md"', text)
        self.assertEqual(text.count('<section data-component="manuscript"'), 1)
        self.assertIn('data-review-mode="shiteki"', text)

    def test_the_text_only_file_numbers_the_blocks_and_keeps_the_code_lines(self):
        _code, _out, files = self.build(README, newline="\r\n")
        lines = files["ms-page-text.txt"].decode("utf-8").split("\n")

        self.assertIn("行頭の #N は番号つきの単位", lines[0])
        blocks = ml.parse_blocks(ml.normalize_newlines(README)).items
        for number, block in enumerate(blocks, start=1):
            starts = [line for line in lines if line.startswith("#%d " % number)]
            if block.type in ("comment", "hr"):
                self.assertEqual(starts, [], "コメントと区切り線は行にならない")
            else:
                self.assertEqual(len(starts), 1, "ブロック %d の行が1つだけ" % number)
        code_at = next(i for i, line in enumerate(lines) if line.startswith("#5 curl"))
        self.assertEqual(lines[code_at + 1], "npm install sample_tool")
        self.assertNotIn("&lt;", "\n".join(lines))
        self.assertNotIn("textarea", "\n".join(lines).lower())

    def test_the_source_textarea_is_not_in_the_text_only_file(self):
        _code, _out, files = self.build("# 見出し\n\n本文の1段落。\n")
        text = files["ms-page-text.txt"].decode("utf-8")

        # 本文の段落は1回だけ（見せる版の1回。textarea の正本は捨てられる）。
        self.assertEqual(text.count("本文の1段落。"), 1)

    def test_the_textarea_value_in_a_real_browser_is_the_original_text(self):
        _code, _out, files = self.build(README, newline="\r\n")
        path = self.project.out / "ms-page.html"

        result = _browser_eval(path, "document.getElementById('ms-source').value")

        self.assertEqual(result["value"], ml.normalize_newlines(README))
        self.assertEqual(result["errors"], [])

    def test_a_hostile_manuscript_keeps_its_exact_text_in_a_real_browser(self):
        hostile = "# <b>x</b> & &amp; &#104;ttps://x\n\n</textarea><script>alert(1)</script>\n\n\ufeff前 後\n\n```\nfile:///etc/hosts\n"
        _code, out, files = self.build(hostile)
        path = self.project.out / "ms-page.html"

        result = _browser_eval(path, "document.getElementById('ms-source').value")

        self.assertEqual(result["value"], hostile)
        self.assertEqual(result["errors"], [])
        self.assertNotIn("alert(1)</script>", files["ms-page.html"].decode("utf-8").split('id="ms-source"')[0])

    def test_the_rendered_block_count_in_a_real_browser(self):
        _code, _out, _files = self.build(README, newline="\r\n")
        path = self.project.out / "ms-page.html"

        result = _browser_eval(
            path,
            "({blocks: document.querySelectorAll('.ms-blk').length, hidden: document.querySelectorAll('.ms-blk[hidden]').length,"
            " mode: document.querySelector('section[data-component=manuscript]').dataset.reviewMode})",
        )

        self.assertEqual(result["value"]["blocks"], ml.count_blocks(README))
        self.assertEqual(result["value"]["hidden"], 1)
        self.assertEqual(result["value"]["mode"], "shiteki")

    def test_the_real_browser_check_passes_when_playwright_is_available(self):
        if not visual_smoke._resolve_playwright()[0] or not shutil.which("node"):
            self.skipTest("Playwright か node が無い")
        path = self.project.doc("intro.md", README, CRLF)

        code, out, _files = self.project.run(_spec({"path": path, "label": "intro-01"}), real_smoke=True)

        self.assertEqual(code, 0, out)
        self.assertEqual(out.count("合格=True"), 2, out)

    def test_an_absolute_path_outside_the_project_shows_only_the_file_name(self):
        with tempfile.TemporaryDirectory(prefix="msout_") as other:
            outside = Path(other) / "secret-dir" / "outside.md"
            _write(outside, "# 外の原稿\n\n本文。\n")
            code, out, files = self.project.run(_spec({"path": str(outside)}))

        text = files["ms-page.html"].decode("utf-8")
        self.assertEqual(code, 0, out)
        self.assertIn('data-path="outside.md"', text)
        self.assertNotIn("secret-dir", text)
        self.assertNotIn("secret-dir", out)

    def test_a_relative_path_is_taken_from_the_project_root(self):
        self.project.doc("a.md", "# 相対\n\n本文。\n")
        code, _out, files = self.project.run(_spec({"path": "docs/a.md"}))

        self.assertEqual(code, 0)
        self.assertIn('data-path="docs/a.md"', files["ms-page.html"].decode("utf-8"))

    def test_the_label_defaults_to_the_file_stem(self):
        self.project.doc("my-article.md", "# 題\n\n本文。\n")
        _code, _out, files = self.project.run(_spec({"path": "docs/my-article.md"}))

        self.assertIn('data-label="my-article"', files["ms-page.html"].decode("utf-8"))

    def test_lf_manuscripts_say_lf(self):
        _code, _out, files = self.build("# 題\n\n本文。\n")

        self.assertIn('data-eol="lf"', files["ms-page.html"].decode("utf-8"))

    def test_the_sha_is_the_hash_of_the_file_bytes(self):
        import hashlib

        self.build(README, newline="\r\n")
        expected = hashlib.sha256((self.project.root / "docs" / "intro.md").read_bytes()).hexdigest()
        text = (self.project.out / "ms-page.html").read_text(encoding="utf-8")

        self.assertIn('data-sha="%s"' % expected, text)

    def test_the_default_frame_names_the_file_in_the_evidence_and_the_details(self):
        _code, _out, files = self.build(README, newline="\r\n")
        text = files["ms-page.html"].decode("utf-8")

        self.assertIn("docs/intro.md", text)
        self.assertRegex(text, r"原稿 \d+ 行 \d+ 文字 \d+ ブロック")


class FrameDefaultsTests(_NeedsRenderer):
    PARTS = ("summary", "walkthrough", "examples", "progress", "visual", "details", "glossary", "evidence", "decision")

    def test_every_missing_part_is_added_and_announced_one_line_each(self):
        code, out, _files = self.build("# 題\n\n本文。\n")

        self.assertEqual(code, 0, out)
        for name in self.PARTS:
            self.assertIn("ⓘ 原稿の頁の既定で足した: %s（" % name, out)
        self.assertNotIn("既定で足した: overview", out)

    def test_a_part_the_author_wrote_is_not_replaced(self):
        extra = {"walkthrough": "自分の手順：本文である。", "evidence": "実測：自分の根拠である｜docs/intro.md"}
        _code, out, files = self.build("# 題\n\n本文。\n", extra=extra)
        text = files["ms-page.html"].decode("utf-8")

        self.assertNotIn("既定で足した: walkthrough", out)
        self.assertNotIn("既定で足した: evidence", out)
        self.assertIn("自分の手順", text)
        self.assertIn("自分の根拠", text)
        self.assertIn("既定で足した: summary", out)

    def test_a_part_listed_in_sections_is_not_added_again(self):
        spec = _spec({"path": self.project.doc("intro.md", "# 題\n\n本文。\n")})
        spec["content"]["sections"].append(
            {"component": "summary", "label": "自分の要約", "content": "Goal：自分で書く。\nNow：書いた。"}
        )
        code, out, files = self.project.run(spec)

        self.assertEqual(code, 0, out)
        self.assertNotIn("既定で足した: summary", out)
        self.assertIn("自分の要約", files["ms-page.html"].decode("utf-8"))

    def test_the_overview_is_never_added_and_the_missing_one_is_warned_loudly(self):
        path = self.project.doc("intro.md", "# 題\n\n本文。\n")
        spec = _spec({"path": path})
        del spec["content"]["overview"]
        code, out, _files = self.project.run(spec)

        self.assertIn("⚠️overview（一言でいうと）が無い＝書き手が書く部品で、この道具は足さない", out)
        self.assertEqual(code, 1)  # overview が要る検品は落ちる

    def test_a_definition_without_a_manuscript_is_left_alone(self):
        spec = {"name": "x", "title": "t", "components": ["overview"], "content": {"overview": "本文"}}

        new_spec, notes = rp._manuscript_frame_defaults(spec)

        self.assertIs(new_spec, spec)
        self.assertEqual(notes, [])

    def test_the_default_decision_has_two_options_with_pros_and_cons_and_a_free_box(self):
        manuscript = {
            "markdown": "# 題\n", "label": "l", "mode": "shiteki", "source_path": "a.md",
            "sha256": "0" * 64, "eol": "lf",
        }

        decision = rp._manuscript_defaults(manuscript)["decision"]

        options = decision["groups"][0]["options"]
        self.assertEqual([o["label"] for o in options], ["反映して続ける", "もう一往復見せる"])
        self.assertTrue(options[0]["recommended"])
        self.assertTrue(all(o["pros"] and o["cons"] for o in options))
        self.assertEqual(decision["groups"][1]["kind"], "free")
        self.assertEqual(rp.decision_option_warnings({"decision": decision}), [])

    def test_a_manuscript_page_gets_no_thin_page_advice(self):
        _code, out, _files = self.build("# 題\n\n本文。\n")

        self.assertNotIn("薄い頁に見える", out)
        self.assertIn("部品の濃さ:", out)


class ErrorTests(_NeedsRenderer):
    def _run(self, manuscript):
        return self.project.run(_spec(manuscript))

    def test_a_missing_file_stops_the_build_with_one_reason(self):
        code, out, files = self._run({"path": "docs/nothing.md"})

        self.assertEqual(code, 2)
        self.assertIn("⚠️原稿を読めない＝組み立てを止めた: 原稿が見つからない: docs/nothing.md", out)
        self.assertEqual(files, {})

    def test_a_non_utf8_file_stops_the_build(self):
        (self.project.root / "docs").mkdir(exist_ok=True)
        (self.project.root / "docs" / "sjis.md").write_bytes("日本語の原稿".encode("cp932"))

        code, out, _files = self._run({"path": "docs/sjis.md"})

        self.assertEqual(code, 2)
        self.assertIn("UTF-8 として読めない", out)

    def test_an_empty_or_blank_file_stops_the_build(self):
        for text in ("", "\n\n  \n"):
            with self.subTest(text=text):
                path = self.project.doc("blank.md", text)
                code, out, _files = self._run({"path": path})
                self.assertEqual(code, 2)
                self.assertIn("ブロックが無い", out)

    def test_a_nul_byte_stops_the_build(self):
        (self.project.root / "docs").mkdir(exist_ok=True)
        (self.project.root / "docs" / "bin.md").write_bytes(b"a\x00b\n")

        code, out, _files = self._run({"path": "docs/bin.md"})

        self.assertEqual(code, 2)
        self.assertIn("NUL", out)

    def test_a_too_large_file_stops_the_build(self):
        with patch.object(rp, "MANUSCRIPT_MAX_BYTES", 100):
            path = self.project.doc("big.md", "あ" * 200)
            code, out, _files = self._run({"path": path})

        self.assertEqual(code, 2)
        self.assertIn("大きすぎる", out)

    def test_a_section_without_a_path_stops_the_build(self):
        code, out, _files = self._run({"label": "x"})

        self.assertEqual(code, 2)
        self.assertIn("path が無い", out)

    def test_an_unknown_mode_stops_the_build_and_japanese_aliases_work(self):
        path = self.project.doc("intro.md", "# 題\n\n本文。\n")
        code, out, _files = self._run({"path": path, "mode": "bogus"})
        self.assertEqual(code, 2)
        self.assertIn("mode は shiteki（指摘）か tensaku（添削）", out)

        resolved = rp.resolve_manuscripts(_spec({"path": path, "mode": "添削"}), str(self.project.root))
        self.assertEqual(rp._manuscript_of(resolved["content"])["mode"], "tensaku")

    def test_two_manuscript_sections_stop_the_build(self):
        path = self.project.doc("intro.md", "# 題\n\n本文。\n")
        spec = _spec({"path": path})
        spec["content"]["sections"].append({"component": "manuscript", "label": "原稿2", "content": {"path": path}})

        code, out, _files = self.project.run(spec)

        self.assertEqual(code, 2)
        self.assertIn("原稿の節は1頁に1つだけ", out)


class ReviewDefaultTests(unittest.TestCase):
    def _ms(self, mode):
        return {"markdown": "# a\n", "label": "l", "mode": mode, "source_path": "a.md",
                "sha256": "0" * 64, "eol": "lf"}

    def _spec(self, review=rp._MISSING, mode=None):
        content = {"overview": "x"}
        if mode:
            content["sections"] = [{"component": "manuscript", "content": self._ms(mode)}]
        if review is not rp._MISSING:
            content["review"] = review
        return {"name": "n", "title": "t", "components": ["overview"], "content": content}

    def test_the_default_for_an_explanation_page_is_both(self):
        self.assertEqual(rp.REVIEW_DEFAULT, "both")

        spec = rp.apply_review_default(self._spec())

        self.assertEqual(spec["content"]["review"], "both")

    def test_an_explicit_review_is_kept_for_an_explanation_page(self):
        for value in ("none", "shiteki", "tensaku", "both"):
            with self.subTest(value=value):
                spec = self._spec(value)
                self.assertIs(rp.apply_review_default(spec), spec)

    def test_the_mode_dict_form_is_kept(self):
        spec = self._spec({"mode": "none"})

        self.assertIs(rp.apply_review_default(spec), spec)

    def test_a_manuscript_page_gets_only_the_role_of_its_mode_by_default(self):
        self.assertEqual(rp.apply_review_default(self._spec(mode="shiteki"))["content"]["review"], "shiteki")
        self.assertEqual(rp.apply_review_default(self._spec(mode="tensaku"))["content"]["review"], "tensaku")

    def test_a_missing_role_is_added_for_a_manuscript_page(self):
        cases = [
            ("none", "tensaku", "tensaku"),
            ("shiteki", "tensaku", "both"),
            ("tensaku", "shiteki", "both"),
            ({"mode": "shiteki", "x": 1}, "tensaku", {"mode": "both", "x": 1}),
        ]
        for review, mode, expected in cases:
            with self.subTest(review=review, mode=mode):
                self.assertEqual(rp.apply_review_default(self._spec(review, mode))["content"]["review"], expected)

    def test_an_existing_role_is_not_touched(self):
        for review, mode in (("both", "shiteki"), ("both", "tensaku"), ("shiteki", "shiteki"), ("tensaku", "tensaku")):
            with self.subTest(review=review, mode=mode):
                spec = self._spec(review, mode)
                self.assertIs(rp.apply_review_default(spec), spec)

    def test_a_definition_without_content_is_returned_as_is(self):
        spec = {"name": "n"}

        self.assertIs(rp.apply_review_default(spec), spec)

    def test_the_input_definition_is_never_changed(self):
        spec = self._spec(mode="tensaku")
        before = copy.deepcopy(spec)

        rp.apply_review_default(spec)

        self.assertEqual(spec, before)


class PrepareSpecTests(_NeedsRenderer):
    def test_prepare_is_idempotent_and_does_not_touch_the_input(self):
        path = self.project.doc("intro.md", README, "\r\n")
        spec = _spec({"path": path, "label": "intro-01", "mode": "tensaku"})
        before = copy.deepcopy(spec)

        once, notes = rp.prepare_spec(spec, str(self.project.root))
        twice, notes_again = rp.prepare_spec(once, str(self.project.root))

        self.assertEqual(spec, before)
        self.assertEqual(once, twice)
        self.assertTrue(notes)
        self.assertTrue(any("原稿の頁: 「intro-01」" in note for note in notes))
        self.assertEqual(once["content"]["review"], "tensaku")
        self.assertFalse([n for n in notes_again if "既定で足した" in n])

    def test_the_resolved_section_has_the_agreed_keys(self):
        path = self.project.doc("intro.md", README, "\r\n")

        resolved = rp.resolve_manuscripts(_spec({"path": path}), str(self.project.root))
        value = rp._manuscript_of(resolved["content"])

        self.assertEqual(sorted(value), ["eol", "label", "markdown", "mode", "sha256", "source_path"])
        self.assertEqual(value["eol"], "crlf")
        self.assertEqual(value["mode"], "shiteki")
        self.assertNotIn("\r", value["markdown"])
        self.assertEqual(len(value["sha256"]), 64)

    def test_a_flat_definition_with_a_top_level_manuscript_key_is_supported(self):
        path = self.project.doc("intro.md", "# 題\n\n本文。\n")
        spec = {"name": "flat", "title": "t", "components": ["overview"],
                "content": {"overview": "x", "manuscript": {"path": path}}}

        resolved = rp.resolve_manuscripts(spec, str(self.project.root))

        self.assertIn("manuscript", resolved["components"])
        self.assertIsNotNone(rp._manuscript_of(resolved["content"]))


class TextOnlyAndShapeTests(unittest.TestCase):
    def test_to_artifact_shape_keeps_every_script_in_order_and_one_style(self):
        html = (
            '<!doctype html><html><head><meta charset="utf-8"><title>t</title><style>.a{}</style></head>'
            "<body><p>本文</p><script>const one=1;</script>\n<script>const two=2;</script>"
            "<script>const three=3;</script></body></html>"
        )

        shaped = rp.to_artifact_shape(html)

        self.assertEqual(shaped.count("<script>"), 3)
        self.assertLess(shaped.index("const one"), shaped.index("const two"))
        self.assertLess(shaped.index("const two"), shaped.index("const three"))
        self.assertEqual(shaped.count("<style>"), 1)

    def test_without_manuscript_cuts_the_section_even_when_sections_nest(self):
        page = (
            '<body><section data-component="summary"><h2>要約</h2></section>'
            '<section data-component="manuscript" id="s2"><h2>原稿</h2><section><p>入れ子</p></section>'
            "<table><tr><td>x</td></tr></table></section>"
            '<section data-component="evidence"><table></table></section></body>'
        )

        cut = rp.without_manuscript(page)

        self.assertNotIn("manuscript", cut)
        self.assertNotIn("入れ子", cut)
        self.assertIn('data-component="summary"', cut)
        self.assertIn('data-component="evidence"', cut)
        self.assertEqual(rp.without_manuscript("<body><p>x</p></body>"), "<body><p>x</p></body>")

    def test_density_does_not_count_the_manuscript_table_or_quote(self):
        page = (
            "<body>"
            '<section data-component="manuscript"><table><tr><td>x</td></tr></table>'
            "<blockquote>q</blockquote><pre class=\"log\">l</pre></section>"
            '<section data-component="evidence"><table></table></section></body>'
        )

        counts = dict(rp.density(page))

        self.assertEqual(counts["表"], 1)
        self.assertEqual(counts["引用"], 0)

    def test_rendered_warnings_ignore_double_stars_inside_the_manuscript(self):
        page = (
            "<html><body>"
            '<section data-component="manuscript"><article data-prose="raw"><p>**閉じない太字と <em></em></p></article></section>'
            "<p>本文</p></body></html>"
        )

        self.assertEqual(rp.rendered_warnings(page), [])


class CheckGlossLeavesTheManuscriptOutTests(unittest.TestCase):
    """用語ホバーの点検（check_gloss.py）の③参考に、原稿の語を混ぜない（原稿は包む対象ではない）。"""

    def setUp(self):
        import check_gloss

        self.module = check_gloss
        glossary = check_gloss.load_glossary()
        terms = sorted((t for t in glossary if len(t) >= 3 and t.isascii() is False), key=len)
        if not terms:
            self.skipTest("用語集に使える語が無い")
        self.term = terms[0]

    def _run(self, html):
        with tempfile.TemporaryDirectory(prefix="gloss_") as tmp:
            path = Path(tmp) / "page.html"
            path.write_text(html, encoding="utf-8")
            done = subprocess.run(
                [sys.executable, str(SCRIPTS_DIR / "check_gloss.py"), str(path)],
                capture_output=True, text=True, encoding="utf-8", timeout=60, check=False,
                env=dict(__import__("os").environ, PYTHONUTF8="1"),
            )
        return done.returncode, done.stdout

    def test_without_manuscript_cuts_only_the_manuscript_section(self):
        page = (
            '<body><section data-component="walkthrough"><p>前</p></section>'
            '<section data-component="manuscript"><section><p>入れ子</p></section><p>原稿</p></section>'
            '<section data-component="evidence"><p>後</p></section></body>'
        )

        cut = self.module.without_manuscript(page)

        self.assertNotIn("原稿", cut)
        self.assertNotIn("入れ子", cut)
        self.assertIn("前", cut)
        self.assertIn("後", cut)
        self.assertEqual(self.module.without_manuscript("<p>x</p>"), "<p>x</p>")

    def test_a_glossary_word_only_in_the_manuscript_is_not_listed(self):
        page = (
            '<body><section data-component="manuscript"><article data-prose="raw"><p>%s を原稿に書いた</p>'
            "</article></section><p>別の本文</p></body>" % self.term
        )

        code, out = self._run(page)

        self.assertEqual(code, 0, out)
        self.assertIn("本文に出ているが包んでいない語 0件", out)

    def test_the_same_word_outside_the_manuscript_is_still_listed(self):
        page = "<body><p>%s を本文に書いた</p></body>" % self.term

        code, out = self._run(page)

        self.assertEqual(code, 0, out)
        self.assertNotIn("本文に出ているが包んでいない語 0件", out)


@unittest.skipIf(review_scripts is None, "review_scripts がまだ無い")
class SharedBlockRuleWithTheScriptTests(unittest.TestCase):
    """頁の番号（Python）と回答の番号（指摘・添削の script の JS）が同じブロック分けになること。"""

    SAMPLES = (
        README,
        "",
        "# 見出しだけ\n",
        "段落1\n\n\n段落2  \n続き\n\n- a\n- b\n\n| a | b |\n|---|---|\n| 1 | 2 |\n\n> q\n\n```\nx\n\ny\n```\n\n<!--\nc\n-->\n\n---\n",
        "\n\n先頭に空行\n",
        "```\n閉じない\n\nまだコード\n",
        "- 深い\n    - もっと\n- 戻る\n\n1. 一\n2) 二\n",
    )

    def _extract(self):
        script = review_scripts.TENSAKU_SCRIPT
        start = script.find("const RE_HEADING")
        end_marker = "endsNL:endsNL};}"
        end = script.find(end_marker, start)
        if start < 0 or end < 0:
            self.skipTest("添削の script から parseBlocks を取り出せない（書き方が変わった）")
        return (
            "const SENT_RE=/[\\uE000-\\uE003]/g;const clean=s=>s.replace(SENT_RE,'');"
            "const isSent=c=>c>='\\uE000'&&c<='\\uE003';\n" + script[start:end + len(end_marker)]
        )

    def test_same_blocks_as_the_python_side(self):
        if not shutil.which("node"):
            self.skipTest("node が無い")
        code = self._extract()
        with tempfile.TemporaryDirectory(prefix="msjs_") as tmp:
            tmp_path = Path(tmp)
            (tmp_path / "docs.json").write_text(json.dumps(list(self.SAMPLES), ensure_ascii=False), encoding="utf-8")
            (tmp_path / "run.js").write_text(
                code + "\nconst fs=require('fs');const docs=JSON.parse(fs.readFileSync(process.argv[2],'utf8'));"
                "fs.writeFileSync(process.argv[3],JSON.stringify(docs.map(d=>parseBlocks(d).items)));\n",
                encoding="utf-8",
            )
            done = subprocess.run(
                ["node", str(tmp_path / "run.js"), str(tmp_path / "docs.json"), str(tmp_path / "out.json")],
                capture_output=True, text=True, encoding="utf-8", timeout=60, check=False,
            )
            self.assertEqual(done.returncode, 0, done.stderr[-300:])
            expected = json.loads((tmp_path / "out.json").read_text(encoding="utf-8"))
        for sample, reference in zip(self.SAMPLES, expected):
            ours = ml.parse_blocks(ml.normalize_newlines(sample)).items
            self.assertEqual(
                [(b.type, b.md, b.gap) for b in ours],
                [(i["type"], i["md"], i["gap"]) for i in reference],
                sample[:30],
            )


@unittest.skipIf(review_scripts is None, "review_scripts がまだ無い")
class ScriptsOnTheBuiltPageTests(_NeedsRenderer):
    def _scripts(self, files, name="ms-page.html"):
        text = files[name].decode("utf-8")
        return re.findall(r"<script>(.*?)</script>", text, re.S)

    def test_a_shiteki_page_carries_the_decision_and_shiteki_scripts_only(self):
        _code, _out, files = self.build("# 題\n\n本文。\n", mode="shiteki")
        scripts = [s.strip() for s in self._scripts(files)]

        self.assertEqual(scripts, [rc.DECISION_SCRIPT.strip(), review_scripts.SHITEKI_SCRIPT.strip()])

    def test_a_tensaku_page_carries_the_decision_and_tensaku_scripts_only(self):
        _code, _out, files = self.build("# 題\n\n本文。\n", mode="tensaku")
        scripts = [s.strip() for s in self._scripts(files)]

        self.assertEqual(scripts, [rc.DECISION_SCRIPT.strip(), review_scripts.TENSAKU_SCRIPT.strip()])
        self.assertIn('data-review-mode="tensaku"', files["ms-page.html"].decode("utf-8"))

    def test_the_artifact_shape_keeps_the_same_scripts(self):
        _code, _out, files = self.build("# 題\n\n本文。\n", mode="tensaku")

        self.assertEqual(self._scripts(files, "ms-page-artifact.html"), self._scripts(files))

    def test_an_explanation_page_carries_both_by_default(self):
        spec = {
            "name": "plain", "title": "説明", "components": list(rp.ALL_COMPONENTS),
            "reasons": ["project_novice_default"], "publish": "never",
            "content": {
                "overview": "本文である。", "summary": "Goal：目的。\nNow：今。", "walkthrough": "手順：本文。",
                "examples": "例：本文。", "progress": "現在地：本文。", "visual": "図：本文。",
                "decision": {"options": [{"label": "案", "recommended": True, "pros": "利点", "cons": "代償"}]},
                "evidence": "実測：値｜docs/a.md", "glossary": "語：説明。", "details": "詳細：本文。",
            },
        }
        code, out, files = self.project.run(spec)
        scripts = [s.strip() for s in self._scripts(files, "plain.html")]

        self.assertIn(code, (0, 1), out)
        self.assertEqual(
            scripts,
            [rc.DECISION_SCRIPT.strip(), review_scripts.SHITEKI_SCRIPT.strip(), review_scripts.TENSAKU_SCRIPT.strip()],
        )


if __name__ == "__main__":
    unittest.main()

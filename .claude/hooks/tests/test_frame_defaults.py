"""欠けた部品を短い「該当なし」の既定で足す（2026-10-15・利用者の選択＝案9(a) の A）。

何を守るか＝
  ①原稿でない頁でも、欠けた部品を既定で足し、足した部品を1つずつ「ⓘ 既定で足した: …」で知らせる
    （黙ってやらない＝2026-08-29 の利用者の条件）。足した頁は10部品の検品に通る。
  ②--no-fill を付けると従来どおり（警告だけ・定義は変えない）。
  ③overview と、reasons が名指しで求める部品（decision_required の decision など）は足さず、強く警告する
    （「該当なし」で中身の無さを隠さない）。
  ④何度かけても同じ結果・元の定義を変えない・10部品そろった定義はそのまま返す。
  ⑤原稿の頁は従来の原稿の既定のまま。
  ⑥既定の判断欄は、表示検査が求める「最初の群の選ぶ欄」を持つ（自由記述だけの群だと
    decision-controls-missing で落ちた＝2026-10-15 実測）。
"""
from __future__ import annotations

import contextlib
import copy
import io
import json
import shutil
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
from visual import visual_smoke  # noqa: E402

FILLED = ("summary", "examples", "progress", "visual", "decision", "glossary", "details")
FAKE_SMOKE = types.SimpleNamespace(status="pass", errors=(), metrics={})


def _partial_spec(name="fill-page", reasons=("project_novice_default",), extra=None):
    """部品を3つ（overview・walkthrough・evidence）だけ書いた定義。"""
    content = {
        "overview": "部品を3つだけ書いた頁で、残りを道具が足すかを確かめる。",
        "walkthrough": "準備：定義を書く\n組む：道具に渡す",
        "evidence": "実測：部品3つの定義を組んだ｜この試験",
    }
    content.update(extra or {})
    return {
        "name": name,
        "title": "補完の確かめ",
        "components": ["overview", "walkthrough", "evidence"],
        "reasons": list(reasons),
        "publish": "never",
        "content": content,
    }


def _filled_lines(notes):
    return [note for note in notes if note.startswith("ⓘ 既定で足した: ")]


def _filled_names(notes):
    return [note[len("ⓘ 既定で足した: "):].split("（", 1)[0] for note in _filled_lines(notes)]


class _Project:
    """一時フォルダの小さなプロジェクト（policy と書き出し先）。"""

    def __init__(self, td):
        self.root = Path(td) / "proj"
        self.out = Path(td) / "out"
        (self.root / ".claude").mkdir(parents=True)
        (self.root / ".claude" / "visual-hook-policy.json").write_text(
            json.dumps({"schema_version": 1, "enabled": True, "local_artifact_root": str(self.out)}),
            encoding="utf-8",
        )

    def run(self, spec, *extra_args):
        """main() を走らせる（表示検査は偽物）。返るもの＝(終了コード, 出力)。"""
        spec_path = self.root / "spec.json"
        spec_path.write_text(json.dumps(spec, ensure_ascii=False), encoding="utf-8")
        buffer = io.StringIO()
        with patch.object(rp, "run_visual_smoke", return_value=FAKE_SMOKE), \
             patch.object(rp, "_approved_root_for", return_value=str(self.out)), \
             contextlib.redirect_stdout(buffer):
            code = rp.main(["render_page.py", str(spec_path), "--project-root", str(self.root), *extra_args])
        return code, buffer.getvalue()

    def check_all_ten(self, name):
        with patch.object(rp, "run_visual_smoke", return_value=FAKE_SMOKE):
            return rp.check(str(self.out / (name + ".html")), list(rp.ALL_COMPONENTS), str(self.root))


class FrameDefaultsTests(unittest.TestCase):
    def test_seven_missing_parts_are_filled_and_each_is_announced(self):
        spec = _partial_spec()

        new_spec, notes = rp._frame_defaults(spec)

        self.assertEqual(sorted(new_spec["components"]), sorted(rp.ALL_COMPONENTS))
        self.assertEqual(sorted(_filled_names(notes)), sorted(FILLED))
        for name in FILLED:
            line = "ⓘ 既定で足した: %s（%s）＝" % (name, rp.COMPONENT_LABELS[name])
            self.assertTrue(any(note.startswith(line) for note in notes), name)
            self.assertIn(name, new_spec["content"])
        self.assertIn("ⓘ 既定で足した部品は 7 個（足したくないときは --no-fill を付ける）", notes)
        for name in ("overview", "walkthrough", "evidence"):
            self.assertEqual(new_spec["content"][name], spec["content"][name])

    def test_the_input_is_not_changed_and_a_second_pass_changes_nothing(self):
        spec = _partial_spec()
        before = copy.deepcopy(spec)

        once, _notes = rp._frame_defaults(spec)
        twice, notes_again = rp._frame_defaults(once)

        self.assertEqual(spec, before)
        self.assertIs(twice, once)
        self.assertEqual(notes_again, [])

    def test_a_complete_definition_is_returned_as_is(self):
        content = dict(rp._general_defaults({"title": "t"}), overview="本文")
        spec = {"name": "n", "title": "t", "components": list(rp.ALL_COMPONENTS), "content": content}

        new_spec, notes = rp._frame_defaults(spec)

        self.assertIs(new_spec, spec)
        self.assertEqual(notes, [])

    def test_overview_is_never_added_and_its_absence_is_warned(self):
        spec = _partial_spec()
        del spec["content"]["overview"]
        spec["components"].remove("overview")

        new_spec, notes = rp._frame_defaults(spec)

        self.assertNotIn("overview", new_spec["components"])
        self.assertNotIn("overview", new_spec["content"])
        self.assertTrue(any(note.startswith("⚠️overview（一言でいうと）が無い") for note in notes))

    def test_parts_named_by_the_reasons_are_not_faked(self):
        for name, reason in sorted(rp.REASON_FOR_COMPONENT.items()):
            with self.subTest(name=name):
                spec = _partial_spec(reasons=("project_novice_default", reason))

                new_spec, notes = rp._frame_defaults(spec)

                self.assertNotIn(name, new_spec["components"])
                self.assertNotIn(name, new_spec["content"])
                self.assertNotIn(name, _filled_names(notes))
                warning = [note for note in notes if note.startswith("⚠️%s（" % name)]
                self.assertEqual(len(warning), 1)
                self.assertIn(reason, warning[0])
                self.assertEqual(len(_filled_names(notes)), 6)

    def test_a_reason_given_as_one_string_is_read_too(self):
        spec = _partial_spec()
        spec["reasons"] = "decision_required"

        new_spec, _notes = rp._frame_defaults(spec)

        self.assertNotIn("decision", new_spec["components"])

    def test_a_part_placed_in_sections_is_listed_and_not_overwritten(self):
        spec = _partial_spec()
        spec["content"]["sections"] = [
            {"component": "examples", "label": "例", "content": "例：書き手が書いた例"},
        ]

        new_spec, notes = rp._frame_defaults(spec)

        self.assertIn("examples", new_spec["components"])
        self.assertNotIn("examples", new_spec["content"])
        self.assertNotIn("examples", _filled_names(notes))
        self.assertIn("ⓘ examples（具体例）は節の一覧にあるので components に載せた", notes)

    def test_a_part_in_content_but_not_in_components_is_listed(self):
        spec = _partial_spec(extra={"details": "補足：書き手が書いた補足"})

        new_spec, notes = rp._frame_defaults(spec)

        self.assertIn("details", new_spec["components"])
        self.assertEqual(new_spec["content"]["details"], "補足：書き手が書いた補足")
        self.assertIn("ⓘ details（詳細）は content の欄にあるので components に載せた", notes)

    def test_manuscript_pages_keep_their_own_defaults(self):
        manuscript = {
            "markdown": "# 題\n\n本文。\n", "label": "l", "mode": "shiteki", "source_path": "a.md",
            "sha256": "0" * 64, "eol": "lf",
        }
        spec = {
            "name": "m", "title": "t", "components": ["overview"],
            "content": {"overview": "原稿の頁", "sections": [{"component": "manuscript", "content": manuscript}]},
        }

        self.assertEqual(rp._frame_defaults(spec), rp._manuscript_frame_defaults(spec))
        _spec, notes = rp._frame_defaults(spec)
        self.assertTrue(any(note.startswith("ⓘ 原稿の頁の既定で足した: ") for note in notes))
        self.assertEqual(_filled_lines(notes), [])

    def test_prepare_spec_fills_by_default_and_not_with_fill_false(self):
        spec = _partial_spec()

        filled, notes = rp.prepare_spec(spec)
        kept, kept_notes = rp.prepare_spec(spec, fill=False)

        self.assertEqual(len(filled["components"]), 10)
        self.assertEqual(len(_filled_lines(notes)), 7)
        self.assertEqual(kept["components"], spec["components"])
        self.assertEqual(kept_notes, [])

    def test_the_default_decision_starts_with_a_choice_and_has_reasons_for_both(self):
        decision = rp._general_defaults({"title": "t"})["decision"]
        first = decision["groups"][0]

        self.assertEqual(first["kind"], "radio")
        self.assertEqual(sum(1 for option in first["options"] if option.get("recommended")), 1)
        for option in first["options"]:
            self.assertTrue(option.get("pros"), option["label"])
            self.assertTrue(option.get("cons"), option["label"])
        self.assertEqual(rp.decision_option_warnings({"decision": decision}), [])

    def test_the_summary_default_names_the_title(self):
        summary = rp._general_defaults({"title": "補完の確かめ"})["summary"]

        self.assertTrue(summary.startswith("Goal：補完の確かめ"))
        self.assertEqual(rp._general_defaults({})["summary"].split("\n")[0], "Goal：この頁")


class MainFillTests(unittest.TestCase):
    def setUp(self):
        self._td = tempfile.TemporaryDirectory(prefix="framedefaults_")
        self.addCleanup(self._td.cleanup)
        self.project = _Project(self._td.name)

    def test_main_fills_and_the_page_passes_the_ten_part_inspection(self):
        code, out = self.project.run(_partial_spec(name="filled"))

        self.assertEqual(code, 0, out)
        self.assertEqual(out.count("ⓘ 既定で足した: "), 7, out)
        self.assertEqual(out.count("合格=True"), 2, out)
        self.assertNotIn("⚠️部品が欠けている", out)
        result = self.project.check_all_ten("filled")
        self.assertTrue(result["ok"], result)
        self.assertEqual(result["missing_components"], [])
        self.assertEqual(result["missing_decision_parts"], [])
        self.assertEqual(result["errors"], [])

    def test_no_fill_keeps_the_old_warning_and_the_old_page(self):
        code, out = self.project.run(_partial_spec(name="kept"), "--no-fill")

        self.assertEqual(code, 0, out)
        self.assertNotIn("ⓘ 既定で足した", out)
        self.assertIn("⚠️部品が欠けている: " + ",".join(FILLED), out)
        self.assertIn("--no-fill を外すと", out)
        result = self.project.check_all_ten("kept")
        self.assertEqual(sorted(result["missing_components"]), sorted(FILLED))

    def test_the_no_fill_flag_works_before_the_definition_path_too(self):
        spec_path = self.project.root / "first.json"
        spec_path.write_text(json.dumps(_partial_spec(name="flag-first"), ensure_ascii=False), encoding="utf-8")
        buffer = io.StringIO()
        with patch.object(rp, "run_visual_smoke", return_value=FAKE_SMOKE), \
             patch.object(rp, "_approved_root_for", return_value=str(self.project.out)), \
             contextlib.redirect_stdout(buffer):
            code = rp.main(["render_page.py", "--no-fill", str(spec_path), "--project-root", str(self.project.root)])

        out = buffer.getvalue()
        self.assertEqual(code, 0, out)
        self.assertTrue((self.project.out / "flag-first.html").is_file())
        self.assertNotIn("ⓘ 既定で足した", out)
        self.assertIn("⚠️部品が欠けている: ", out)

    def test_a_decision_page_without_a_decision_still_fails_and_says_why(self):
        spec = _partial_spec(name="decision-missing", reasons=("project_novice_default", "decision_required"))

        code, out = self.project.run(spec)

        self.assertIn("⚠️decision（選ぶこと）が無い＝reasons の decision_required が求める部品", out)
        self.assertIn("⚠️部品が欠けている: decision", out)
        result = self.project.check_all_ten("decision-missing")
        self.assertIn("decision", result["missing_components"])
        self.assertIn(code, (0, 1))

    def test_the_filled_page_passes_rp_check_with_the_real_browser(self):
        # 2026-10-15（リードの注意＝担当 B2 の実測と同じ型）：判断欄が自由記述の群だけだと、表示検査が
        #   decision-controls-missing で落ちる。補完した頁を、偽物でない表示検査つきの rp.check に
        #   完全版・器用の両方で通す（10部品を全部求める）。
        playwright_path, reason = visual_smoke._resolve_playwright()
        if not playwright_path or not shutil.which("node"):
            self.skipTest("Playwright か node が無い: %s" % (reason or ""))
        self.project.run(_partial_spec(name="real-smoke"))
        environment = ("visual smoke runner failed", "visual smoke timed out", "visual smoke runner could not start")

        for name in ("real-smoke.html", "real-smoke-artifact.html"):
            with self.subTest(page=name):
                result = rp.check(str(self.project.out / name), list(rp.ALL_COMPONENTS), str(self.project.root))

                if result["smoke"] == "not_run" or any(e in environment for e in result["smoke_errors"]):
                    self.skipTest("表示検査を走らせられない環境: %s" % (result["smoke_errors"],))
                self.assertNotIn("decision-controls-missing", " ".join(result["smoke_errors"]))
                self.assertEqual(result["smoke"], "pass", result["smoke_errors"])
                self.assertTrue(result["ok"], result)
                self.assertEqual(result["missing_components"], [])
                self.assertEqual(result["missing_decision_parts"], [])
                self.assertEqual(result["external_dependency"], [])


if __name__ == "__main__":
    unittest.main()

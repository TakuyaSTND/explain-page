from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.dont_write_bytecode = True

HOOKS_DIR = Path(__file__).resolve().parents[1]
if str(HOOKS_DIR) not in sys.path:
    sys.path.insert(0, str(HOOKS_DIR))

from visual import visual_smoke


class VisualSmokeTests(unittest.TestCase):
    def _artifact(self) -> tuple[tempfile.TemporaryDirectory[str], Path]:
        temp_dir = tempfile.TemporaryDirectory()
        path = Path(temp_dir.name) / "日本語 artifact.html"
        path.write_text("<!doctype html><html><body><p>fixture</p></body></html>", encoding="utf-8")
        return temp_dir, path

    def test_missing_playwright_is_not_run_and_not_pass(self):
        temp_dir, path = self._artifact()
        self.addCleanup(temp_dir.cleanup)

        with patch.object(
            visual_smoke,
            "_resolve_playwright",
            return_value=(None, "Playwright is not installed"),
        ):
            result = visual_smoke.run_visual_smoke(path)

        self.assertEqual(result.status, "not_run")
        self.assertIn("Playwright is not installed", result.errors)
        self.assertEqual(result.metrics, {})

    def test_pass_result_is_parsed_and_runner_receives_path_as_argument(self):
        temp_dir, path = self._artifact()
        self.addCleanup(temp_dir.cleanup)
        payload = {
            "status": "pass",
            "errors": [],
            "metrics": {"viewports": {"1280x900": {"overflow": False}}},
        }
        completed = subprocess.CompletedProcess(
            args=["node"], returncode=0, stdout=json.dumps(payload), stderr=""
        )

        with patch.object(
            visual_smoke,
            "_resolve_playwright",
            return_value=("C:/playwright/index.js", None),
        ), patch.object(visual_smoke, "_run_node", return_value=completed) as runner:
            result = visual_smoke.run_visual_smoke(path, timeout_seconds=7)

        self.assertEqual(result.status, "pass")
        self.assertEqual(result.errors, ())
        self.assertEqual(result.metrics, payload["metrics"])
        command = runner.call_args.args[0]
        self.assertIn("-e", command)
        # macOS の一時フォルダは /var が /private/var の別名＝道具が実体のパスに直して渡してもよい
        self.assertTrue(
            str(path) in command or str(Path(path).resolve()) in command,
            command[-1],
        )
        self.assertIn("C:/playwright/index.js", command)
        self.assertEqual(runner.call_args.kwargs["timeout_seconds"], 7)

    def test_runner_failure_is_returned_without_exposing_stderr(self):
        temp_dir, path = self._artifact()
        self.addCleanup(temp_dir.cleanup)
        completed = subprocess.CompletedProcess(
            args=["node"], returncode=1, stdout="", stderr="SECRET SHOULD NOT LEAK"
        )

        with patch.object(
            visual_smoke,
            "_resolve_playwright",
            return_value=("C:/playwright/index.js", None),
        ), patch.object(visual_smoke, "_run_node", return_value=completed):
            result = visual_smoke.run_visual_smoke(path)

        self.assertEqual(result.status, "fail")
        self.assertTrue(result.errors)
        self.assertNotIn("SECRET", " ".join(result.errors))

    def test_nonzero_runner_cannot_override_failure_with_pass_json(self):
        temp_dir, path = self._artifact()
        self.addCleanup(temp_dir.cleanup)
        completed = subprocess.CompletedProcess(
            args=["node"],
            returncode=1,
            stdout=json.dumps({"status": "pass", "errors": [], "metrics": {}}),
            stderr="",
        )

        with patch.object(
            visual_smoke,
            "_resolve_playwright",
            return_value=("C:/playwright/index.js", None),
        ), patch.object(visual_smoke, "_run_node", return_value=completed):
            result = visual_smoke.run_visual_smoke(path)

        self.assertEqual(result.status, "fail")
        self.assertTrue(result.errors)

    def test_timeout_is_a_fail_not_an_unverified_pass(self):
        temp_dir, path = self._artifact()
        self.addCleanup(temp_dir.cleanup)

        with patch.object(
            visual_smoke,
            "_resolve_playwright",
            return_value=("C:/playwright/index.js", None),
        ), patch.object(
            visual_smoke,
            "_run_node",
            side_effect=subprocess.TimeoutExpired("node", 12),
        ):
            result = visual_smoke.run_visual_smoke(path)

        self.assertEqual(result.status, "fail")
        self.assertTrue(any("timed out" in error for error in result.errors))

    def test_malformed_runner_output_is_a_fail(self):
        temp_dir, path = self._artifact()
        self.addCleanup(temp_dir.cleanup)
        completed = subprocess.CompletedProcess(
            args=["node"], returncode=0, stdout="not json", stderr=""
        )

        with patch.object(
            visual_smoke,
            "_resolve_playwright",
            return_value=("C:/playwright/index.js", None),
        ), patch.object(visual_smoke, "_run_node", return_value=completed):
            result = visual_smoke.run_visual_smoke(path)

        self.assertEqual(result.status, "fail")
        self.assertTrue(any("malformed" in error for error in result.errors))

    def test_missing_artifact_path_fails_before_runner(self):
        with patch.object(visual_smoke, "_run_node") as runner:
            result = visual_smoke.run_visual_smoke("C:/does/not/exist.html")

        self.assertEqual(result.status, "fail")
        self.assertTrue(result.errors)
        runner.assert_not_called()

    def test_node_script_contains_real_viewports_and_runtime_guards(self):
        script = visual_smoke.NODE_SMOKE_SCRIPT

        self.assertIn("1280", script)
        self.assertIn("900", script)
        self.assertIn("390", script)
        self.assertIn("844", script)
        self.assertIn("pageerror", script)
        self.assertIn("console", script)
        self.assertIn("pathToFileURL", script)
        self.assertIn("scrollWidth", script)
        self.assertIn("route.abort", script)
        self.assertIn("url === artifactUrl", script)
        # 2026-08-29：選択肢は radio と checkbox の両方がありうる（複数選べる形）
        self.assertIn("input[name=decision]", script)
        # ⚠️吹き出しは display で隠す。visibility を見ると隠れていても合格してしまう
        self.assertIn("'::after').display !== 'none'", script)
        self.assertIn("name=objection", script)


class ResolvePlaywrightFallbackTests(unittest.TestCase):
    """既定の置き場に無いときは npm 自身に聞いた置き場を探す（2026-09-25）。

    実測＝GitHub の Windows の実行環境は npm のキャッシュを設定ファイルで別の場所に
    しており、Playwright を入れても「無い」と判定されて表示検査の試験が飛ばされた。
    """

    def test_falls_back_to_the_npm_config_cache(self):
        with tempfile.TemporaryDirectory() as empty, tempfile.TemporaryDirectory() as other:
            playwright_dir = Path(other) / "_npx" / "abc123" / "node_modules" / "playwright"
            playwright_dir.mkdir(parents=True)
            not_found = subprocess.CompletedProcess(args=[], returncode=1, stdout="", stderr="")
            with patch.object(visual_smoke.subprocess, "run", return_value=not_found), patch.object(
                visual_smoke, "_default_npx_cache_root", return_value=Path(empty) / "_npx"
            ), patch.object(
                visual_smoke, "_npm_config_cache_root", return_value=Path(other) / "_npx"
            ), patch.object(visual_smoke, "_browser_installed_for", return_value=True):
                found, error = visual_smoke._resolve_playwright()
        self.assertIsNone(error)
        self.assertEqual(Path(found), playwright_dir)

    def test_reports_missing_when_neither_place_has_it(self):
        with tempfile.TemporaryDirectory() as empty:
            not_found = subprocess.CompletedProcess(args=[], returncode=1, stdout="", stderr="")
            with patch.object(visual_smoke.subprocess, "run", return_value=not_found), patch.object(
                visual_smoke, "_default_npx_cache_root", return_value=Path(empty) / "_npx"
            ), patch.object(visual_smoke, "_npm_config_cache_root", return_value=None):
                found, error = visual_smoke._resolve_playwright()
        self.assertIsNone(found)
        self.assertEqual(error, "Playwright is not installed")

    def test_npm_config_cache_root_uses_npm_answer(self):
        answer = subprocess.CompletedProcess(args=[], returncode=0, stdout="C:/npm/cache\n", stderr="")
        with patch.object(visual_smoke.shutil, "which", return_value="npm"), patch.object(
            visual_smoke.subprocess, "run", return_value=answer
        ):
            self.assertEqual(visual_smoke._npm_config_cache_root(), Path("C:/npm/cache") / "_npx")
        with patch.object(visual_smoke.shutil, "which", return_value=None):
            self.assertIsNone(visual_smoke._npm_config_cache_root())


if __name__ == "__main__":
    unittest.main()

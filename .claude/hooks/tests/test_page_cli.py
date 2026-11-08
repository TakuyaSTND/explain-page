"""共通の命令 page.py（status・check・enable・install）の試験。

標準ライブラリだけ・実ブラウザは使わない（check は無い頁を渡したときの誤り終了だけ見る）。
"""
import json
import os
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
PAGE_PY = os.path.normpath(os.path.join(HERE, "..", "..", "scripts", "page.py"))


def run(*args, cwd=None, env=None):
    merged = dict(os.environ)
    merged.pop("CLAUDE_PROJECT_DIR", None)
    merged.pop("CODEX_SESSION_ID", None)
    merged.pop("CODEX_THREAD_ID", None)
    merged["PYTHONUTF8"] = "1"
    if env:
        merged.update(env)
    return subprocess.run(
        [sys.executable, PAGE_PY] + list(args), cwd=cwd, env=merged,
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )


class StatusTests(unittest.TestCase):
    def test_without_policy_says_not_active(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = run("status", "--project-root", tmp)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("動かない", result.stdout)

    def test_with_policy_shows_mode(self):
        with tempfile.TemporaryDirectory() as tmp:
            os.makedirs(os.path.join(tmp, ".claude"))
            with open(os.path.join(tmp, ".claude", "visual-hook-policy.json"), "w", encoding="utf-8") as handle:
                json.dump({"explain_mode": "auto", "publish": "always"}, handle)
            result = run("status", "--project-root", tmp)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("auto", result.stdout)
            self.assertIn("結論", result.stdout)

    def test_direct_wiring_is_reported(self):
        with tempfile.TemporaryDirectory() as tmp:
            os.makedirs(os.path.join(tmp, ".claude"))
            with open(os.path.join(tmp, ".claude", "visual-hook-policy.json"), "w", encoding="utf-8") as handle:
                json.dump({"explain_mode": "always"}, handle)
            with open(os.path.join(tmp, ".claude", "settings.json"), "w", encoding="utf-8") as handle:
                handle.write('{"hooks": "understanding-composer.py"}')
            result = run("status", "--project-root", tmp)
            self.assertIn("Claude あり", result.stdout)


class CheckTests(unittest.TestCase):
    def test_missing_page_is_usage_error(self):
        result = run("check", os.path.join(tempfile.gettempdir(), "no-such-page-xyz.html"))
        self.assertEqual(result.returncode, 2)


class InstallTests(unittest.TestCase):
    def test_dry_run_writes_nothing(self):
        with tempfile.TemporaryDirectory() as home:
            result = run("install", "--home", home)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("まだ書いていない", result.stdout)
            self.assertFalse(os.path.exists(os.path.join(home, ".claude")))

    def test_write_places_skill_for_claude_and_codex_and_commands(self):
        with tempfile.TemporaryDirectory() as home:
            result = run("install", "--write", "--home", home)
            self.assertEqual(result.returncode, 0, result.stderr)
            for rel in (
                (".claude", "skills", "explain-page", "SKILL.md"),
                (".agents", "skills", "explain-page", "SKILL.md"),
                (".claude", "commands", "page-status.md"),
                (".claude", "commands", "page-check.md"),
                (".claude", "commands", "page-enable.md"),
            ):
                path = os.path.join(home, *rel)
                self.assertTrue(os.path.isfile(path), path)
                text = open(path, encoding="utf-8").read()
                self.assertNotIn("{PAGE_PY}", text)
                self.assertNotIn("{PYTHON}", text)
                self.assertIn("page.py", text)

    def test_second_run_changes_nothing(self):
        with tempfile.TemporaryDirectory() as home:
            run("install", "--write", "--home", home)
            result = run("install", "--write", "--home", home)
            self.assertIn("変更 0 件", result.stdout)

    def test_changed_file_is_backed_up(self):
        with tempfile.TemporaryDirectory() as home:
            run("install", "--write", "--home", home)
            target = os.path.join(home, ".claude", "commands", "page-status.md")
            with open(target, "w", encoding="utf-8") as handle:
                handle.write("手で直した")
            run("install", "--write", "--home", home)
            self.assertTrue(os.path.isfile(target + ".bak-explain-page"))
            self.assertEqual(open(target + ".bak-explain-page", encoding="utf-8").read(), "手で直した")


class EnableTests(unittest.TestCase):
    def test_dry_run_does_not_create_policy(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = run("enable", tmp)
            if "install_adapter.py が見つからない" in result.stderr:
                self.skipTest("install_adapter.py が無い配置")
            self.assertFalse(os.path.exists(os.path.join(tmp, ".claude", "visual-hook-policy.json")))


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import io
import json
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCRIPTS_DIR = HERE.parents[1] / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import install_adapter as ia  # noqa: E402


def _run(argv):
    buf = io.StringIO()
    with redirect_stdout(buf):
        code = ia.main(argv)
    return code, buf.getvalue()


class InstallAdapterTests(unittest.TestCase):
    def test_fill_template_leaves_no_placeholders(self):
        with tempfile.TemporaryDirectory() as project:
            filled = ia.fill_template(
                "{{EXPLAIN_PAGE_ROOT}} {{PROJECT_ROOT}} {{PYTHON}}", project
            )
            self.assertNotIn("{{", filled)
            self.assertIn(ia._to_slash(sys.executable), filled)

    def test_codex_dry_run_previews_without_writing(self):
        with tempfile.TemporaryDirectory() as project:
            code, out = _run(["--runtime", "codex", "--project-root", project])
            self.assertEqual(code, 0)
            self.assertIn("understanding-composer.py", out)
            self.assertFalse(os.path.isfile(os.path.join(project, ".codex", "hooks.json")))

    def test_codex_write_creates_file(self):
        with tempfile.TemporaryDirectory() as project:
            code, _ = _run(
                ["--runtime", "codex", "--project-root", project, "--write"]
            )
            self.assertEqual(code, 0)
            dest = os.path.join(project, ".codex", "hooks.json")
            self.assertTrue(os.path.isfile(dest))
            text = io.open(dest, encoding="utf-8").read()
            self.assertNotIn("{{", text)

    def test_codex_write_refuses_to_overwrite_differing_file(self):
        with tempfile.TemporaryDirectory() as project:
            dest = os.path.join(project, ".codex", "hooks.json")
            os.makedirs(os.path.dirname(dest))
            io.open(dest, "w", encoding="utf-8").write("{}")
            code, out = _run(
                ["--runtime", "codex", "--project-root", project, "--write"]
            )
            self.assertEqual(code, 1)
            self.assertIn("上書きしない", out)
            self.assertEqual(io.open(dest, encoding="utf-8").read(), "{}")

    def test_codex_write_is_noop_when_identical(self):
        with tempfile.TemporaryDirectory() as project:
            code, _ = _run(["--runtime", "codex", "--project-root", project, "--write"])
            self.assertEqual(code, 0)
            code2, out2 = _run(
                ["--runtime", "codex", "--project-root", project, "--write"]
            )
            self.assertEqual(code2, 0)
            self.assertIn("一致", out2)

    def test_hermes_prints_yaml_and_never_writes(self):
        with tempfile.TemporaryDirectory() as project:
            before = set(os.listdir(project))
            code, out = _run(["--runtime", "hermes", "--project-root", project])
            self.assertEqual(code, 0)
            self.assertIn("understanding-composer.py", out)
            self.assertIn("--runtime hermes", out)
            after = set(os.listdir(project))
            self.assertEqual(before, after)


def _read_json(path):
    return json.loads(io.open(path, encoding="utf-8").read())


class UserScopeTests(unittest.TestCase):
    """2026-09-28：利用者単位の配線（--scope user）と、リポジトリを有効にする印。"""

    def test_claude_preview_never_writes(self):
        with tempfile.TemporaryDirectory() as home:
            code, out = _run(["--runtime", "claude", "--scope", "user", "--home", home])
            self.assertEqual(code, 0)
            self.assertIn("--runtime claude --shared", out)
            self.assertFalse(os.path.exists(os.path.join(home, ".claude", "settings.json")))

    def test_claude_write_keeps_other_settings_and_backs_up(self):
        with tempfile.TemporaryDirectory() as home:
            dest = os.path.join(home, ".claude", "settings.json")
            os.makedirs(os.path.dirname(dest))
            original = {
                "enabledPlugins": {"x@y": True},
                "hooks": {"Stop": [{"hooks": [{"type": "command", "command": "echo mine"}]}]},
            }
            io.open(dest, "w", encoding="utf-8").write(json.dumps(original))
            code, out = _run(
                ["--runtime", "claude", "--scope", "user", "--home", home, "--write"]
            )
            self.assertEqual(code, 0, out)
            merged = _read_json(dest)
            self.assertEqual(merged["enabledPlugins"], {"x@y": True})
            stop_commands = [
                h["command"] for g in merged["hooks"]["Stop"] for h in g["hooks"]
            ]
            self.assertIn("echo mine", stop_commands)
            self.assertTrue(any("--shared" in c for c in stop_commands))
            self.assertIn("UserPromptSubmit", merged["hooks"])
            self.assertEqual(_read_json(dest + ia.BACKUP_SUFFIX), original)
            self.assertNotIn("{{", io.open(dest, encoding="utf-8").read())

    def test_claude_second_write_changes_nothing(self):
        with tempfile.TemporaryDirectory() as home:
            args = ["--runtime", "claude", "--scope", "user", "--home", home, "--write"]
            self.assertEqual(_run(args)[0], 0)
            before = io.open(os.path.join(home, ".claude", "settings.json"), encoding="utf-8").read()
            code, out = _run(args)
            self.assertEqual(code, 0)
            self.assertIn("変更なし", out)
            after = io.open(os.path.join(home, ".claude", "settings.json"), encoding="utf-8").read()
            self.assertEqual(before, after)

    def test_remove_takes_out_only_our_lines(self):
        with tempfile.TemporaryDirectory() as home:
            dest = os.path.join(home, ".claude", "settings.json")
            os.makedirs(os.path.dirname(dest))
            io.open(dest, "w", encoding="utf-8").write(json.dumps(
                {"hooks": {"Stop": [{"hooks": [{"type": "command", "command": "echo mine"}]}]}}
            ))
            _run(["--runtime", "claude", "--scope", "user", "--home", home, "--write"])
            code, _ = _run(
                ["--runtime", "claude", "--scope", "user", "--home", home, "--remove", "--write"]
            )
            self.assertEqual(code, 0)
            self.assertEqual(
                _read_json(dest),
                {"hooks": {"Stop": [{"hooks": [{"type": "command", "command": "echo mine"}]}]}},
            )

    def test_codex_write_creates_the_user_hooks_file(self):
        with tempfile.TemporaryDirectory() as home:
            code, out = _run(
                ["--runtime", "codex", "--scope", "user", "--home", home, "--write"]
            )
            self.assertEqual(code, 0, out)
            dest = os.path.join(home, ".codex", "hooks.json")
            text = io.open(dest, encoding="utf-8").read()
            self.assertNotIn("{{", text)
            data = json.loads(text)
            self.assertEqual(
                set(data["hooks"]), {"UserPromptSubmit", "PostToolUse", "SubagentStop", "Stop"}
            )
            first = data["hooks"]["UserPromptSubmit"][0]["hooks"][0]
            self.assertIn("--runtime codex --shared", first["command"])
            self.assertIn("--runtime codex --shared", first["commandWindows"])

    def test_broken_json_is_never_overwritten(self):
        with tempfile.TemporaryDirectory() as home:
            dest = os.path.join(home, ".codex", "hooks.json")
            os.makedirs(os.path.dirname(dest))
            io.open(dest, "w", encoding="utf-8").write("{not json")
            code, _ = _run(
                ["--runtime", "codex", "--scope", "user", "--home", home, "--write"]
            )
            self.assertEqual(code, 1)
            self.assertEqual(io.open(dest, encoding="utf-8").read(), "{not json")

    def test_enable_project_writes_an_auto_marker_without_overwriting(self):
        with tempfile.TemporaryDirectory() as project:
            code, _ = _run(["--enable-project", project])
            self.assertEqual(code, 0)
            marker = os.path.join(project, ".claude", "visual-hook-policy.json")
            self.assertFalse(os.path.exists(marker))
            code, _ = _run(["--enable-project", project, "--write"])
            self.assertEqual(code, 0)
            self.assertEqual(_read_json(marker)["explain_mode"], "auto")
            self.assertTrue(os.path.isfile(os.path.join(project, ".claude", "glossary.md")))
            io.open(marker, "w", encoding="utf-8").write('{"explain_mode": "always"}')
            code, out = _run(["--enable-project", project, "--write"])
            self.assertEqual(code, 0)
            self.assertIn("既にある", out)
            self.assertEqual(_read_json(marker), {"explain_mode": "always"})


if __name__ == "__main__":
    unittest.main()

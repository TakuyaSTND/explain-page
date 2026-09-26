from __future__ import annotations

import io
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


if __name__ == "__main__":
    unittest.main()

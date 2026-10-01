"""利用者単位の配線（understanding-composer.py の `--shared`）の試験（2026-09-28 新設）。

試験する物＝
  `--shared` の安全の掟2つ（印が無ければ何もしない・直接の配線があれば何もしない）
  会話の場所から上へ辿って印を見つけること（CLAUDE_PROJECT_DIR を先に使う）
  道具の置き場とプロジェクトが違うときは、頁を組む道具の絶対の場所を伝えること
  `visual/paths.py` の読みやすさ規則の探し方（台本の根の直下にもあれば使う）

⚠️本物の承認済みの置き場の state.db は汚さない＝全て `--state-path` で一時フォルダへ逃がす。
⚠️この試験は Claude の会話の中から走ることがある＝子プロセスの環境から
  CLAUDE_PROJECT_DIR を消してから走らせる（残っていると、このリポジトリから印を探してしまう）。
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HOOKS_DIR = Path(__file__).resolve().parents[1]
CLAUDE_DIR = HOOKS_DIR.parent
REPO_ROOT = CLAUDE_DIR.parent
if str(HOOKS_DIR) not in sys.path:
    sys.path.insert(0, str(HOOKS_DIR))

from visual.paths import readability_rules_path, render_page_tool_location  # noqa: E402

UNDERSTANDING_COMPOSER = HOOKS_DIR / "understanding-composer.py"
ABSOLUTE_TOOL = (Path(os.path.abspath(str(CLAUDE_DIR))) / "scripts" / "render_page.py").as_posix()


def _env(project_dir=None):
    env = dict(os.environ)
    env["PYTHONUTF8"] = "1"
    env.pop("CLAUDE_PROJECT_DIR", None)
    if project_dir is not None:
        env["CLAUDE_PROJECT_DIR"] = str(project_dir)
    return env


def _run(args, payload, project_dir=None):
    return subprocess.run(
        [sys.executable, str(UNDERSTANDING_COMPOSER)] + [str(a) for a in args],
        input=json.dumps(payload, ensure_ascii=False),
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=_env(project_dir),
    )


def _prompt(cwd, session_id="s-shared", turn_id="t1"):
    return {
        "hook_event_name": "UserPromptSubmit",
        "cwd": str(cwd),
        "session_id": session_id,
        "turn_id": turn_id,
        "prompt": "これをhtmlの1枚にしてください。",
    }


def _directive(stdout):
    """出力のどこかにある additionalContext を取り出す（Claude・Codex で包み方が違う）。"""
    def find(node):
        if isinstance(node, dict):
            for key, value in node.items():
                if key == "additionalContext" and isinstance(value, str):
                    return value
                found = find(value)
                if found:
                    return found
        return None

    return find(json.loads(stdout)) or ""


def _enable(project):
    """このリポジトリの印を写して、試験用のプロジェクトを有効にする。"""
    claude_dir = project / ".claude"
    claude_dir.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(CLAUDE_DIR / "visual-hook-policy.json", claude_dir / "visual-hook-policy.json")


def _direct_wiring_text():
    return json.dumps(
        {"hooks": {"Stop": [{"hooks": [{"type": "command",
            "command": "python .claude/hooks/understanding-composer.py --runtime x --project-root ."}]}]}}
    )


class SharedSafetyGateTests(unittest.TestCase):
    """① 印が無い ② 直接の配線がある、のどちらでも何もしない。"""

    def test_no_marker_means_no_output_for_claude_and_codex(self):
        with tempfile.TemporaryDirectory() as td:
            project = Path(td) / "plain"
            project.mkdir()
            for runtime in ("claude", "codex"):
                result = _run(
                    ["--runtime", runtime, "--shared", "--state-path", Path(td) / "state.db"],
                    _prompt(project),
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(result.stdout, "", runtime)

    def test_claude_direct_wiring_means_no_output(self):
        with tempfile.TemporaryDirectory() as td:
            project = Path(td) / "wired"
            _enable(project)
            (project / ".claude" / "settings.json").write_text(_direct_wiring_text(), encoding="utf-8")
            result = _run(
                ["--runtime", "claude", "--shared", "--state-path", Path(td) / "state.db"],
                _prompt(project),
            )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, "")

    def test_codex_direct_wiring_stops_codex_but_not_claude(self):
        with tempfile.TemporaryDirectory() as td:
            project = Path(td) / "codexwired"
            _enable(project)
            (project / ".codex").mkdir()
            (project / ".codex" / "hooks.json").write_text(_direct_wiring_text(), encoding="utf-8")
            codex = _run(
                ["--runtime", "codex", "--shared", "--state-path", Path(td) / "state.db"],
                _prompt(project, session_id="s-codex"),
            )
            claude = _run(
                ["--runtime", "claude", "--shared", "--state-path", Path(td) / "state.db"],
                _prompt(project, session_id="s-claude"),
            )
        self.assertEqual(codex.returncode, 0, codex.stderr)
        self.assertEqual(codex.stdout, "")
        self.assertEqual(claude.returncode, 0, claude.stderr)
        self.assertNotEqual(claude.stdout, "")

    @unittest.skipUnless(
        (CLAUDE_DIR / "settings.json").is_file()
        and "understanding-composer.py"
        in (CLAUDE_DIR / "settings.json").read_text(encoding="utf-8", errors="replace"),
        "直接の配線があるリポジトリ（開発元）でだけ確かめる",
    )
    def test_this_repository_is_left_to_its_direct_wiring(self):
        """このリポジトリには直接の配線がある＝利用者単位の配線は二重に走らない。"""
        with tempfile.TemporaryDirectory() as td:
            for runtime in ("claude", "codex"):
                result = _run(
                    ["--runtime", runtime, "--shared", "--state-path", Path(td) / "state.db"],
                    _prompt(REPO_ROOT, session_id="s-" + runtime),
                    project_dir=REPO_ROOT if runtime == "claude" else None,
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(result.stdout, "", runtime)


class SharedEnabledProjectTests(unittest.TestCase):
    """③ 印のあるプロジェクトでは指示文が出て、道具の絶対の場所が入る。"""

    def test_marker_in_a_parent_folder_is_found_from_a_subfolder(self):
        with tempfile.TemporaryDirectory() as td:
            project = Path(td) / "enabled"
            _enable(project)
            deep = project / "src" / "deep"
            deep.mkdir(parents=True)
            for runtime in ("claude", "codex"):
                result = _run(
                    ["--runtime", runtime, "--shared", "--state-path", Path(td) / "state.db"],
                    _prompt(deep, session_id="s-" + runtime),
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertNotEqual(result.stdout, "", runtime)
                self.assertIn(ABSOLUTE_TOOL, _directive(result.stdout), runtime)

    def test_claude_prefers_claude_project_dir_over_cwd(self):
        """会話の根（外側・有効）の中で、直接の配線がある内側のフォルダへ cd した場合。
        cwd から探すと内側で止まって何も出ないが、CLAUDE_PROJECT_DIR を先に使えば外側で動く。
        """
        with tempfile.TemporaryDirectory() as td:
            outer = Path(td) / "outer"
            _enable(outer)
            inner = outer / "vendor" / "inner"
            _enable(inner)
            (inner / ".claude" / "settings.json").write_text(_direct_wiring_text(), encoding="utf-8")
            with_env = _run(
                ["--runtime", "claude", "--shared", "--state-path", Path(td) / "state.db"],
                _prompt(inner, session_id="s-env"),
                project_dir=outer,
            )
            without_env = _run(
                ["--runtime", "claude", "--shared", "--state-path", Path(td) / "state.db"],
                _prompt(inner, session_id="s-noenv"),
            )
        self.assertEqual(with_env.returncode, 0, with_env.stderr)
        self.assertNotEqual(with_env.stdout, "")
        self.assertEqual(without_env.returncode, 0, without_env.stderr)
        self.assertEqual(without_env.stdout, "")

    def test_direct_wiring_to_another_project_also_gets_the_absolute_tool(self):
        """install_adapter.py で別のリポジトリへ書いた Codex の配線（--project-root 固定）。"""
        with tempfile.TemporaryDirectory() as td:
            project = Path(td) / "other"
            _enable(project)
            result = _run(
                ["--runtime", "codex", "--project-root", project,
                 "--state-path", Path(td) / "state.db"],
                _prompt(project),
            )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(ABSOLUTE_TOOL, _directive(result.stdout))

    def test_project_root_is_required_without_shared(self):
        with tempfile.TemporaryDirectory() as td:
            result = _run(
                ["--runtime", "claude", "--state-path", Path(td) / "state.db"],
                _prompt(td),
            )
        self.assertEqual(result.returncode, 2)


class PathsForSharedWiringTests(unittest.TestCase):
    """④ paths.py：同じ場所なら従来の相対・違えば絶対・読みやすさ規則の探し方。"""

    def test_same_place_keeps_the_relative_tool(self):
        self.assertEqual(
            render_page_tool_location(plugin=False, script_root=CLAUDE_DIR, project_root=REPO_ROOT),
            ".claude/scripts/render_page.py",
        )

    def test_without_roots_keeps_the_relative_tool(self):
        self.assertEqual(render_page_tool_location(plugin=False), ".claude/scripts/render_page.py")

    def test_different_place_gives_the_absolute_tool(self):
        with tempfile.TemporaryDirectory() as td:
            self.assertEqual(
                render_page_tool_location(plugin=False, script_root=CLAUDE_DIR, project_root=td),
                ABSOLUTE_TOOL,
            )

    def test_plugin_keeps_the_token(self):
        with tempfile.TemporaryDirectory() as td:
            self.assertEqual(
                render_page_tool_location(plugin=True, script_root=CLAUDE_DIR, project_root=td),
                "${CLAUDE_PLUGIN_ROOT}/scripts/render_page.py",
            )

    def test_readability_rules_fall_back_to_the_script_root(self):
        with tempfile.TemporaryDirectory() as td:
            project = Path(td) / "p"
            (project / ".claude").mkdir(parents=True)
            shared_root = Path(td) / "shared" / ".claude"
            shared_root.mkdir(parents=True)
            (shared_root / "readability-rules.md").write_text("x", encoding="utf-8")
            self.assertEqual(
                readability_rules_path(project, shared_root), shared_root / "readability-rules.md"
            )
            plugin_root = Path(td) / "plugin"
            plugin_root.mkdir()
            self.assertEqual(
                readability_rules_path(project, plugin_root),
                plugin_root / "templates" / "readability-rules.md",
            )


if __name__ == "__main__":
    unittest.main()

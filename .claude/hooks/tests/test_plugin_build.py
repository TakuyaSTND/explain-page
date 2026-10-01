"""説明の頁の仕組みをClaude Codeのプラグインにまとめる一式の試験（2026-09-25 新設）。

試験する物＝
  `.claude/scripts/build_plugin.py`（正本から `plugins/<配布の名前>/` を組む道具）
  `.claude/hooks/understanding-composer.py` の `--plugin` 安全の掟4つ
  `.claude/hooks/visual/paths.py`（composerとrender_page.pyが同じ場所を見る保証）

⚠️本物の承認済みの置き場（一時フォルダの下）の state.db は汚さない＝全て
  `--state-path` で一時フォルダへ逃がす。プラグイン本体も `bp.build(out_dir=...)`
  で一時フォルダへ生成し、実物の `plugins/<配布の名前>/` は書き換えない。
⚠️`render_page.py` の承認済みの置き場（html出力）だけは設計上動かせないので、
  検査で作った2ファイルは試験の終わりに消す（tearDownで掃除）。
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HOOKS_DIR = Path(__file__).resolve().parents[1]
CLAUDE_DIR = HOOKS_DIR.parent
REPO_ROOT = CLAUDE_DIR.parent
SCRIPTS_DIR = CLAUDE_DIR / "scripts"
for _entry in (str(HOOKS_DIR), str(SCRIPTS_DIR)):
    if _entry not in sys.path:
        sys.path.insert(0, _entry)

import build_plugin as bp  # noqa: E402
from visual import branding  # noqa: E402
from visual.paths import artifact_root, glossary_paths, render_page_tool_location  # noqa: E402

UNDERSTANDING_COMPOSER = CLAUDE_DIR / "hooks" / "understanding-composer.py"

_SUBPROCESS_ENV = dict(os.environ)
_SUBPROCESS_ENV["PYTHONUTF8"] = "1"

_MODULE_TMP = None
PLUGIN_BUILD_ROOT = None


def setUpModule():
    """全クラスで使い回す、一時フォルダへの1回きりのプラグイン生成。"""
    global _MODULE_TMP, PLUGIN_BUILD_ROOT
    _MODULE_TMP = tempfile.TemporaryDirectory()
    PLUGIN_BUILD_ROOT = Path(_MODULE_TMP.name) / "plugin-build"
    code = bp.build(out_dir=str(PLUGIN_BUILD_ROOT))
    assert code == 0


def tearDownModule():
    if _MODULE_TMP is not None:
        _MODULE_TMP.cleanup()


def _run(args, input_text=None):
    """`python <args[0]> <args[1:]>` を1本の子プロセスとして走らせる。"""
    return subprocess.run(
        [sys.executable] + [str(a) for a in args],
        input=input_text,
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=_SUBPROCESS_ENV,
    )


def _components_from_directive(directive):
    """指示文の `components=a,b,c` 行から、要求された部品名の並びを取り出す。"""
    for line in directive.splitlines():
        if line.startswith("components="):
            return [name for name in line[len("components="):].split(",") if name]
    return []


def _content_for(components):
    """どの部品名が来ても検査を通る、試験専用の中身を返す
    （`.claude/hooks/tests/test_codex_self_receipt.py` と同じ考え方）。
    """
    content = {}
    for name in components:
        if name == "evidence":
            content[name] = (
                "実測：試験のために作った値である"
                "｜.claude/hooks/tests/test_plugin_build.py"
            )
        elif name == "decision":
            content[name] = {
                "options": ["案A"],
                "judgments": ["これは試験用の判定である"],
            }
        else:
            content[name] = "見出し一：これは試験のためだけに書いた本文である。"
    return content


def _user_prompt_submit(project, session_id="s1", turn_id="t1"):
    return json.dumps(
        {
            "hook_event_name": "UserPromptSubmit",
            "cwd": str(project),
            "session_id": session_id,
            "turn_id": turn_id,
            "prompt": "これをhtmlの1枚にしてください。",
        },
        ensure_ascii=False,
    )


class BuildGeneratesRequiredFilesTests(unittest.TestCase):
    """① build_plugin.py が一時フォルダに生成し、必須のファイルが揃う。"""

    def test_required_files_are_present(self):
        required = (
            "hooks/understanding-composer.py",
            "hooks/run-python.sh",
            "hooks/hooks.json",
            "hooks/visual/entrypoint.py",
            "hooks/visual/instructions.py",
            "hooks/visual/paths.py",
            "hooks/visual/render_components.py",
            "scripts/render_page.py",
            "scripts/check_gloss.py",
            "scripts/init_project.py",
            "glossary-shared.md",
            "templates/visual-hook-policy.json",
            "templates/glossary.md",
            "templates/readability-rules.md",
            ".claude-plugin/plugin.json",
            "README.md",
        )
        for rel in required:
            with self.subTest(rel=rel):
                self.assertTrue(
                    (PLUGIN_BUILD_ROOT / rel).is_file(), rel + " が生成されていない"
                )

    def test_tests_and_pycache_are_not_bundled(self):
        self.assertFalse((PLUGIN_BUILD_ROOT / "hooks" / "tests").exists())
        for dirpath, dirnames, _filenames in os.walk(PLUGIN_BUILD_ROOT):
            self.assertNotIn("__pycache__", dirnames)

    def test_out_dir_build_does_not_touch_the_real_marketplace_file(self):
        marketplace = REPO_ROOT / ".claude-plugin" / "marketplace.json"
        before = marketplace.read_bytes() if marketplace.is_file() else None
        with tempfile.TemporaryDirectory() as td:
            bp.build(out_dir=str(Path(td) / "another-build"))
        after = marketplace.read_bytes() if marketplace.is_file() else None
        self.assertEqual(before, after)


class HooksJsonShapeTests(unittest.TestCase):
    """② hooks.json がJSONとして正しく、全コマンドに --plugin と ${CLAUDE_PLUGIN_ROOT} がある。"""

    def test_hooks_json_is_valid_json_with_five_wired_commands(self):
        data = json.loads(
            (PLUGIN_BUILD_ROOT / "hooks" / "hooks.json").read_text(encoding="utf-8")
        )
        commands = [
            hook["command"]
            for groups in data["hooks"].values()
            for group in groups
            for hook in group.get("hooks", [])
        ]
        self.assertEqual(len(commands), 5)
        self.assertEqual(
            sorted(data["hooks"]),
            ["PostToolUse", "Stop", "StopFailure", "SubagentStop", "UserPromptSubmit"],
        )
        for command in commands:
            with self.subTest(command=command[:60]):
                self.assertIn("--plugin", command)
                self.assertIn("${CLAUDE_PLUGIN_ROOT}", command)
                self.assertIn("${CLAUDE_PROJECT_DIR}", command)
                self.assertIn("understanding-composer.py", command)

    def test_commands_run_through_run_python_sh(self):
        # 2026-09-25：入口をrun-python.sh経由に変えた（Macはpython3、Windowsはpython
        # を選ぶ・PYTHONUTF8=1はrun-python.shの中で付ける）。
        data = json.loads(
            (PLUGIN_BUILD_ROOT / "hooks" / "hooks.json").read_text(encoding="utf-8")
        )
        commands = [
            hook["command"]
            for groups in data["hooks"].values()
            for group in groups
            for hook in group.get("hooks", [])
        ]
        for command in commands:
            with self.subTest(command=command[:60]):
                self.assertIn("run-python.sh", command)
                self.assertTrue(command.startswith("sh "), command)
        run_python_sh = PLUGIN_BUILD_ROOT / "hooks" / "run-python.sh"
        self.assertTrue(run_python_sh.is_file())
        text = run_python_sh.read_text(encoding="utf-8")
        self.assertIn("PYTHONUTF8=1", text)
        self.assertIn("python3", text)

    def test_agmsg_inbox_hook_is_not_bundled(self):
        # ⚠️伝言確認(agmsg)の分は入れない＝機械ごとの道具なので（決めごと③）。
        text = (PLUGIN_BUILD_ROOT / "hooks" / "hooks.json").read_text(encoding="utf-8")
        self.assertNotIn("agmsg_inbox.py", text)

    def test_plugin_manifest_has_a_name(self):
        data = json.loads(
            (PLUGIN_BUILD_ROOT / ".claude-plugin" / "plugin.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(data["name"], branding.PRODUCT_NAME)

    def test_plugin_manifest_has_no_version(self):
        # 2026-10-01（利用者の選択）：version を書くと、作者が変えるまで入れた人に更新が
        #   届かない（Claude Code は版の番号で更新を見分ける）＝書かずにコミットの番号を版にする。
        data = json.loads(
            (PLUGIN_BUILD_ROOT / ".claude-plugin" / "plugin.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertNotIn("version", data)


class CheckDetectsDriftTests(unittest.TestCase):
    """③ --check が一致なら0、正本を1バイト変えた写しに対しては1。"""

    def test_check_matches_a_freshly_built_copy(self):
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "plugin-out"
            self.assertEqual(bp.build(out_dir=str(out)), 0)
            self.assertEqual(bp.check(out_dir=str(out)), 0)

    def test_check_fails_after_a_single_byte_change(self):
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "plugin-out"
            bp.build(out_dir=str(out))
            target = out / "hooks" / "hooks.json"
            target.write_bytes(target.read_bytes() + b" ")
            self.assertEqual(bp.check(out_dir=str(out)), 1)

    def test_check_fails_on_a_missing_file(self):
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "plugin-out"
            bp.build(out_dir=str(out))
            (out / "README.md").unlink()
            self.assertEqual(bp.check(out_dir=str(out)), 1)

    def test_the_real_plugin_directory_matches_the_source(self):
        # 実際に repo に生成してある plugins/<配布の名前> も正本と一致するはず
        # （このテストの前に `python .claude/scripts/build_plugin.py` を走らせてある）。
        self.assertEqual(bp.check(), 0)


class PluginSafetyGateTests(unittest.TestCase):
    """④⑤ --plugin の安全の掟：設定が無い／直接の配線があるプロジェクトでは何もしない。"""

    def test_missing_policy_file_means_no_output_and_exit_zero(self):
        with tempfile.TemporaryDirectory() as td:
            project = Path(td) / "proj"
            (project / ".claude").mkdir(parents=True)
            result = _run(
                [
                    UNDERSTANDING_COMPOSER,
                    "--runtime", "claude", "--plugin",
                    "--project-root", project,
                    "--state-path", Path(td) / "state.db",
                ],
                input_text=_user_prompt_submit(project),
            )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, "")

    def test_direct_wiring_in_settings_json_means_no_output(self):
        with tempfile.TemporaryDirectory() as td:
            project = Path(td) / "proj"
            claude_dir = project / ".claude"
            claude_dir.mkdir(parents=True)
            (claude_dir / "visual-hook-policy.json").write_text("{}", encoding="utf-8")
            (claude_dir / "settings.json").write_text(
                json.dumps(
                    {
                        "hooks": {
                            "UserPromptSubmit": [
                                {
                                    "hooks": [
                                        {
                                            "type": "command",
                                            "command": (
                                                "python .claude/hooks/"
                                                "understanding-composer.py --runtime "
                                                "claude --project-root ."
                                            ),
                                        }
                                    ]
                                }
                            ]
                        }
                    }
                ),
                encoding="utf-8",
            )
            result = _run(
                [
                    UNDERSTANDING_COMPOSER,
                    "--runtime", "claude", "--plugin",
                    "--project-root", project,
                    "--state-path", Path(td) / "state.db",
                ],
                input_text=_user_prompt_submit(project),
            )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, "")

    def test_direct_wiring_in_settings_local_json_also_means_no_output(self):
        with tempfile.TemporaryDirectory() as td:
            project = Path(td) / "proj"
            claude_dir = project / ".claude"
            claude_dir.mkdir(parents=True)
            (claude_dir / "visual-hook-policy.json").write_text("{}", encoding="utf-8")
            (claude_dir / "settings.local.json").write_text(
                json.dumps({"hooks": {"Stop": [{"hooks": [{"type": "command",
                    "command": "python .claude/hooks/understanding-composer.py --runtime claude --project-root ."}]}]}}),
                encoding="utf-8",
            )
            result = _run(
                [
                    UNDERSTANDING_COMPOSER,
                    "--runtime", "claude", "--plugin",
                    "--project-root", project,
                    "--state-path", Path(td) / "state.db",
                ],
                input_text=_user_prompt_submit(project),
            )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, "")


class PluginEnabledProjectTests(unittest.TestCase):
    """⑥ init_project.py で有効にしたプロジェクトでは、指示文が出て、
    その中の道具の場所がプラグインの場所になる。
    """

    def test_init_project_then_prompt_submit_shows_the_plugin_tool_path(self):
        with tempfile.TemporaryDirectory() as td:
            project = Path(td) / "proj"
            project.mkdir()
            init_result = _run(
                [PLUGIN_BUILD_ROOT / "scripts" / "init_project.py", project]
            )
            self.assertEqual(init_result.returncode, 0, init_result.stderr)
            self.assertTrue((project / ".claude" / "visual-hook-policy.json").is_file())
            self.assertTrue((project / ".claude" / "glossary.md").is_file())
            self.assertTrue((project / ".claude" / "readability-rules.md").is_file())

            result = _run(
                [
                    PLUGIN_BUILD_ROOT / "hooks" / "understanding-composer.py",
                    "--runtime", "claude", "--plugin",
                    "--project-root", project,
                    "--state-path", Path(td) / "state.db",
                ],
                input_text=_user_prompt_submit(project),
            )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotEqual(result.stdout, "")
        payload = json.loads(result.stdout)
        directive = payload["hookSpecificOutput"]["additionalContext"]
        self.assertIn(render_page_tool_location(plugin=True), directive)
        self.assertIn("${CLAUDE_PLUGIN_ROOT}/scripts/render_page.py", directive)
        self.assertNotIn(".claude/scripts/render_page.py", directive)
        # 2026-09-25：部品ごとの説明文（html-output.md）が同梱されて、有効にしたプロジェクトでも出る
        self.assertIn("[walkthrough]", directive)
        self.assertTrue((PLUGIN_BUILD_ROOT / "html-output.md").is_file())

    def test_init_project_does_not_overwrite_existing_files(self):
        with tempfile.TemporaryDirectory() as td:
            project = Path(td) / "proj"
            claude_dir = project / ".claude"
            claude_dir.mkdir(parents=True)
            marker = "既存の中身（消えてはいけない）"
            (claude_dir / "glossary.md").write_text(marker, encoding="utf-8")

            result = _run([PLUGIN_BUILD_ROOT / "scripts" / "init_project.py", project])

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(
                (claude_dir / "glossary.md").read_text(encoding="utf-8"), marker
            )
            # 既存が無かった分（policy・readability）は書かれている。
            self.assertTrue((claude_dir / "visual-hook-policy.json").is_file())
            self.assertTrue((claude_dir / "readability-rules.md").is_file())


class DirectModeUnchangedTests(unittest.TestCase):
    """⑦ --plugin が無い時の挙動は今と1バイトも変わらない（このリポジトリで確かめる）。"""

    def test_no_plugin_flag_keeps_the_relative_render_page_path(self):
        with tempfile.TemporaryDirectory() as td:
            result = _run(
                [
                    UNDERSTANDING_COMPOSER,
                    "--runtime", "claude",
                    "--project-root", REPO_ROOT,
                    "--state-path", Path(td) / "state.db",
                ],
                input_text=_user_prompt_submit(
                    REPO_ROOT, session_id="s-direct-mode", turn_id="t-direct-mode"
                ),
            )
        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        directive = payload["hookSpecificOutput"]["additionalContext"]
        self.assertIn(".claude/scripts/render_page.py", directive)
        self.assertNotIn("${CLAUDE_PLUGIN_ROOT}", directive)


def _playwright_available() -> bool:
    """表示検査（visual_smoke）が使う Playwright が、この機械で見つかるか。"""
    try:
        from visual.visual_smoke import _resolve_playwright

        return _resolve_playwright()[0] is not None
    except Exception:
        return False


class PathsConsistencyTests(unittest.TestCase):
    """⑧ paths.py が返す用語集のパスが composer と render_page.py で同じ。"""

    def test_render_page_py_uses_the_shared_paths_function(self):
        import render_page as rp

        self.assertIs(rp._glossary_paths_for, glossary_paths)

    def test_understanding_composer_source_calls_the_shared_paths_module(self):
        text = UNDERSTANDING_COMPOSER.read_text(encoding="utf-8")
        self.assertIn("from visual import paths as visual_paths", text)
        self.assertIn("visual_paths.glossary_paths(root, script_root)", text)
        self.assertIn("visual_paths.readability_rules_path(root, script_root)", text)

    @unittest.skipUnless(
        _playwright_available(),
        "Playwright が無い＝表示検査が走らず、検品の記録が合格にならない"
    )
    def test_a_receipt_built_by_render_page_validates_through_the_composer(self):
        """往復での実証＝render_page.py（プラグイン）が作った検品証を、
        同じプラグインの understanding-composer.py（Stop）が有効と認める。
        2つの道具が別々の規則で用語集のパスを決めていたら、ここでハッシュが
        食い違い、Stopが差し戻す（stdoutが空にならない）。
        """
        approved_root = artifact_root(None)
        page_name = "plugin-paths-consistency-check"
        made_paths = [
            approved_root / (page_name + ".html"),
            approved_root / (page_name + "-artifact.html"),
        ]

        def _cleanup():
            for made in made_paths:
                try:
                    made.unlink()
                except OSError:
                    pass

        self.addCleanup(_cleanup)

        with tempfile.TemporaryDirectory() as td:
            project = Path(td) / "proj"
            project.mkdir()
            init = _run([PLUGIN_BUILD_ROOT / "scripts" / "init_project.py", project])
            self.assertEqual(init.returncode, 0, init.stderr)

            state_path = Path(td) / "state.db"
            session_id, turn_id = "sess-consistency", "turn-consistency"

            pre = _run(
                [
                    PLUGIN_BUILD_ROOT / "hooks" / "understanding-composer.py",
                    "--runtime", "claude", "--plugin",
                    "--project-root", project,
                    "--state-path", state_path,
                ],
                input_text=_user_prompt_submit(
                    project, session_id=session_id, turn_id=turn_id
                ),
            )
            self.assertEqual(pre.returncode, 0, pre.stderr)
            self.assertNotEqual(pre.stdout, "")
            pre_payload = json.loads(pre.stdout)
            pre_directive = pre_payload["hookSpecificOutput"]["additionalContext"]
            # ⚠️Stopは「予告(pre)∪実態」の和集合を要求するので、実際に必要な部品を
            #   指示文から読み取って過不足なく満たす（さもないと部品不足で差し戻り、
            #   このテストが確かめたい「用語集パスの整合」とは別の理由で落ちる）。
            required_components = _components_from_directive(pre_directive)
            self.assertTrue(required_components)

            spec_path = Path(td) / "spec.json"
            spec = {
                "name": page_name,
                "title": "整合性確認用の頁",
                "components": required_components,
                "reasons": ["project_novice_default"],
                "publish": "never",
                "content": _content_for(required_components),
            }
            spec_path.write_text(json.dumps(spec, ensure_ascii=False), encoding="utf-8")

            render = _run(
                [
                    PLUGIN_BUILD_ROOT / "scripts" / "render_page.py",
                    spec_path,
                    "--project-root", project,
                ]
            )
            self.assertEqual(render.returncode, 0, render.stdout + render.stderr)
            self.assertTrue(made_paths[1].is_file())

            post = _run(
                [
                    PLUGIN_BUILD_ROOT / "hooks" / "understanding-composer.py",
                    "--runtime", "claude", "--plugin",
                    "--project-root", project,
                    "--state-path", state_path,
                ],
                input_text=json.dumps(
                    {
                        "hook_event_name": "PostToolUse",
                        "cwd": str(project),
                        "session_id": session_id,
                        "turn_id": turn_id,
                        "tool_name": "Artifact",
                        "tool_input": {"file_path": str(made_paths[0])},
                    },
                    ensure_ascii=False,
                ),
            )
            self.assertEqual(post.returncode, 0, post.stderr)

            stop = _run(
                [
                    PLUGIN_BUILD_ROOT / "hooks" / "understanding-composer.py",
                    "--runtime", "claude", "--plugin",
                    "--project-root", project,
                    "--state-path", state_path,
                ],
                input_text=json.dumps(
                    {
                        "hook_event_name": "Stop",
                        "cwd": str(project),
                        "session_id": session_id,
                        "turn_id": turn_id,
                        "last_assistant_message": "対応しました。",
                        "stop_hook_active": False,
                    },
                    ensure_ascii=False,
                ),
            )
        self.assertEqual(stop.returncode, 0, stop.stderr)
        self.assertEqual(
            stop.stdout,
            "",
            "Stopが差し戻した＝composerとrender_page.pyの用語集パスがずれている: "
            + stop.stdout,
        )


if __name__ == "__main__":
    unittest.main()

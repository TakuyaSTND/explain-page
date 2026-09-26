"""公開版（explain-page）への持ち出しを見越した試験（2026-09-25 新設）。

試験する物＝
  ①`.claude/hooks/visual/paths.py` の `artifact_root()`（%TEMP%・$TMPDIR・${TMPDIR}・
    $TEMP・~・None の展開）
  ②TEMP・TMPを環境から抜いても、render_page.py と understanding-composer.py が
    同じ承認済みの置き場に合意する（以前はrender_page.py側が `os.environ.get("TEMP","")`
    を直書きしていたので、ここが食い違いうる穴だった＝2026-09-25 の直しで塞いだ）
  ③`.claude/hooks/visual/branding.py` の LEGACY_* を None にした配布では、
    `visual/policy.py` が旧い環境変数名を読まない・deprecated_aliasesにも入れない
  ④`.claude/hooks/run-python.sh`（shが見つかる環境でだけ走らせる）

⚠️実物の state.db・承認済みの置き場は汚さない＝全て一時フォルダへ逃がす
  （②はcomposerが実際に書く印だけ、一意なセッションIDでaddCleanupして消す）。
"""
from __future__ import annotations

import importlib
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
SCRIPTS_DIR = CLAUDE_DIR / "scripts"
for _entry in (str(HOOKS_DIR), str(SCRIPTS_DIR)):
    if _entry not in sys.path:
        sys.path.insert(0, _entry)

from visual import branding  # noqa: E402
from visual.entrypoint import _project_hash  # noqa: E402
from visual.paths import artifact_root  # noqa: E402
from visual.turn_marker import _session_marker_path  # noqa: E402

UNDERSTANDING_COMPOSER = HOOKS_DIR / "understanding-composer.py"
RUN_PYTHON_SH = HOOKS_DIR / "run-python.sh"

# ②で使う、TEMP・TMP・TMPDIRを抜いたsubprocess環境。
_ENV_WITHOUT_TEMP = {
    key: value
    for key, value in os.environ.items()
    if key.upper() not in ("TEMP", "TMP", "TMPDIR")
}
_ENV_WITHOUT_TEMP["PYTHONUTF8"] = "1"


class ArtifactRootExpansionTests(unittest.TestCase):
    """① artifact_root() の展開。"""

    def test_none_falls_back_to_the_default_under_the_temp_dir(self):
        self.assertEqual(
            artifact_root(None),
            Path(tempfile.gettempdir()) / branding.ARTIFACT_DIR_NAME,
        )

    def test_blank_string_also_falls_back_to_the_default(self):
        self.assertEqual(artifact_root("   "), artifact_root(None))

    def test_percent_temp_token_is_case_insensitive(self):
        for token in ("%TEMP%/x", "%temp%/x", "%TeMp%/x"):
            with self.subTest(token=token):
                self.assertEqual(
                    artifact_root(token), Path(tempfile.gettempdir()) / "x"
                )

    def test_dollar_style_tokens_expand_to_the_temp_dir(self):
        for token in ("$TMPDIR/x", "${TMPDIR}/x", "$TEMP/x"):
            with self.subTest(token=token):
                self.assertEqual(
                    artifact_root(token), Path(tempfile.gettempdir()) / "x"
                )

    def test_tilde_expands_to_home(self):
        self.assertEqual(artifact_root("~/x"), Path.home() / "x")


class RenderPageAndComposerAgreeWithoutTempEnvTests(unittest.TestCase):
    """② TEMP・TMPが無い環境でも、render_page.py と composer が同じ置き場に合意する。"""

    def test_composer_writes_its_turn_marker_under_the_root_render_page_reports(self):
        probe = subprocess.run(
            [
                sys.executable,
                "-c",
                "import sys;sys.path.insert(0,sys.argv[1]);"
                "sys.path.insert(0,sys.argv[2]);import render_page as rp;"
                "print(rp._approved_root_for(sys.argv[3]))",
                str(SCRIPTS_DIR),
                str(HOOKS_DIR),
                str(REPO_ROOT),
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            env=_ENV_WITHOUT_TEMP,
            check=False,
        )
        self.assertEqual(probe.returncode, 0, probe.stderr)
        reported_root = Path(probe.stdout.strip())

        session_id = "branding-portability-session"
        turn_id = "branding-portability-turn"
        project_hash = _project_hash(str(REPO_ROOT))
        marker_path = _session_marker_path(
            reported_root, "codex", project_hash, session_id
        )
        self.addCleanup(lambda: marker_path.unlink(missing_ok=True))

        with tempfile.TemporaryDirectory() as td:
            state_path = Path(td) / "state.db"
            payload = json.dumps(
                {
                    "hook_event_name": "UserPromptSubmit",
                    "cwd": str(REPO_ROOT),
                    "session_id": session_id,
                    "turn_id": turn_id,
                    "prompt": "これをhtmlの1枚にしてください。",
                },
                ensure_ascii=False,
            )
            result = subprocess.run(
                [
                    sys.executable,
                    str(UNDERSTANDING_COMPOSER),
                    "--runtime", "codex",
                    "--project-root", str(REPO_ROOT),
                    "--state-path", str(state_path),
                ],
                input=payload,
                capture_output=True,
                text=True,
                encoding="utf-8",
                env=_ENV_WITHOUT_TEMP,
                check=False,
            )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(
            marker_path.is_file(),
            "composerが書いた印の場所が、render_page.pyの報告した置き場と食い違う: "
            + str(marker_path),
        )


class LegacyAliasesDisabledWhenBrandingIsNoneTests(unittest.TestCase):
    """③ branding.LEGACY_* を None にした配布では、policy が旧い環境変数名を
    読まない・deprecated_aliasesにも入れない（importlib.reload + モンキーパッチ）。
    """

    def test_reloaded_policy_ignores_the_legacy_names_when_branding_is_none(self):
        import visual.policy as policy_module

        original = (
            branding.LEGACY_ENV_OFF,
            branding.LEGACY_ENV_MIN,
            branding.LEGACY_ENV_BLOCKS,
        )
        # 旧い名前は branding から取る（公開版では元から None なので、代わりの名前を使う）
        # ＝この試験ファイル自体に固有の名前を直書きしない（公開版にもそのまま写すため）。
        old_off, old_min, old_blocks = (
            name if name is not None else fallback
            for name, fallback in zip(
                original, ("OLD_EXPLAIN_OFF", "OLD_EXPLAIN_MIN", "OLD_EXPLAIN_BLOCKS")
            )
        )
        branding.LEGACY_ENV_OFF = None
        branding.LEGACY_ENV_MIN = None
        branding.LEGACY_ENV_BLOCKS = None
        try:
            reloaded = importlib.reload(policy_module)
            self.assertEqual(reloaded.LEGACY_ALIAS_NAMES, ())

            policy = reloaded.load_policy(
                path=None,
                env={old_off: "1", old_min: "321", old_blocks: "12"},
            )
            # 旧い名前はここではただの無関係な環境変数の1つ＝policyのどこにも効かない。
            self.assertEqual(policy.deprecated_aliases, ())
            self.assertEqual(policy.min_chars, 700)
            self.assertEqual(policy.min_blocks, 8)
            self.assertTrue(policy.enabled)
            self.assertEqual(
                policy.local_artifact_root, "%TEMP%/" + branding.ARTIFACT_DIR_NAME
            )
        finally:
            (
                branding.LEGACY_ENV_OFF,
                branding.LEGACY_ENV_MIN,
                branding.LEGACY_ENV_BLOCKS,
            ) = original
            importlib.reload(policy_module)

    def test_real_os_environ_does_not_crash_when_branding_is_none(self):
        """env を渡さない＝実運用の既定（os.environ）でも落ちない（2026-09-25 実測の是正）。

        以前は os.environ.get(None) が TypeError を出し、公開版では render_page.py の
        読み込みも composer の起動も必ず落ちていた。env={} の試験では素の dict なので
        見えなかった＝ここでは本物の os.environ を通す。
        """
        from unittest import mock

        import visual.policy as policy_module

        original = (
            branding.LEGACY_ENV_OFF,
            branding.LEGACY_ENV_MIN,
            branding.LEGACY_ENV_BLOCKS,
        )
        branding.LEGACY_ENV_OFF = None
        branding.LEGACY_ENV_MIN = None
        branding.LEGACY_ENV_BLOCKS = None
        try:
            reloaded = importlib.reload(policy_module)
            with mock.patch.dict(os.environ, {branding.ENV_MODE: "always"}):
                policy = reloaded.load_policy(path=None)
            self.assertEqual(policy.explain_mode, "always")
            self.assertEqual(policy.deprecated_aliases, ())
            with mock.patch.dict(os.environ, {}, clear=False):
                os.environ.pop(branding.ENV_MODE, None)
                policy = reloaded.load_policy(path=None)
            self.assertEqual(policy.min_chars, 700)
            self.assertEqual(policy.min_blocks, 8)
        finally:
            (
                branding.LEGACY_ENV_OFF,
                branding.LEGACY_ENV_MIN,
                branding.LEGACY_ENV_BLOCKS,
            ) = original
            importlib.reload(policy_module)


class RunPythonShTests(unittest.TestCase):
    """④ run-python.sh（shが見つかる環境でだけ走らせる）。"""

    @unittest.skipUnless(shutil.which("sh"), "shが見つからない環境")
    def test_execs_python_and_can_run_code(self):
        result = subprocess.run(
            ["sh", str(RUN_PYTHON_SH), "-c", "import sys;print(sys.executable)"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(result.stdout.strip())

    @unittest.skipUnless(shutil.which("sh"), "shが見つからない環境")
    def test_sets_pythonutf8(self):
        result = subprocess.run(
            ["sh", str(RUN_PYTHON_SH), "-c",
             "import os;print(os.environ.get('PYTHONUTF8'))"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), "1")


if __name__ == "__main__":
    unittest.main()

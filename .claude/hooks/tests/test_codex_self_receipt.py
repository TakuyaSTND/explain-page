"""Codexの自己申告の検品証（2026-09-25）。

背景＝Codexには「頁を公開した」道具の合図（PostToolUse）が無いので、検品の記録
（state.db の artifact_receipts_v3）が過去0件だった。∴依頼の受付（UserPromptSubmit）
で「いまの会話とその回」の印を残し（`visual/turn_marker.py`）、`render_page.py` が
`--runtime codex` の時にその印を読んで、道具自身が代わりに検品の記録を書く。

⚠️安全の掟＝`--runtime codex` を明示した時だけ動く（環境変数だけを見て自動で
  記録することはしない）。Claude・Hermesの経路には影響しない。

この試験は一時フォルダの state と置き場だけを使う＝本物の承認済みの置き場
（一時フォルダの下）の state.db には触れない。頁のHTML自体は一時フォルダの
「置き場」に書く。
"""
from __future__ import annotations

import sys
import tempfile
import time
import types
import unittest
from pathlib import Path
from unittest.mock import patch

HOOKS_DIR = Path(__file__).resolve().parents[1]
CLAUDE_DIR = HOOKS_DIR.parent
SCRIPTS_DIR = CLAUDE_DIR / "scripts"
for _entry in (str(HOOKS_DIR), str(SCRIPTS_DIR)):
    if _entry not in sys.path:
        sys.path.insert(0, _entry)

from visual import paths as visual_paths  # noqa: E402
from visual.entrypoint import _project_hash, handle_event  # noqa: E402
from visual.policy import load_policy  # noqa: E402
from visual.render_components import render_components  # noqa: E402
from visual.contracts import ExplanationPlan  # noqa: E402
from visual.instructions import compile_directive  # noqa: E402
from visual.state import StateStore  # noqa: E402
from visual import turn_marker as tm  # noqa: E402

import render_page as rp  # noqa: E402

HTML_OUTPUT = CLAUDE_DIR / "html-output.md"
PROJECT_ROOT = "C:/repo"
COMMON = {"cwd": PROJECT_ROOT, "session_id": "session-crx", "turn_id": "turn-crx"}
# ⚠️「html」だけを入れる＝EXPLICIT_PAGE_SIGNALSにだけ当たり、
#   VISUAL/DECISION/SUMMARY/PROGRESS/PRIVATEのどの合図語とも重ならない
#   （「図解」は「図」とかぶるので使わない＝composer.pyのVISUAL_SIGNALS参照）。
PAGE_PROMPT = "これをhtmlの1枚にしてください。"
PLAIN_RESPONSE = "対応しました。"


def _content_for(components):
    """どの部品名が来ても検査を通る、試験専用の中身を返す。"""
    content = {}
    for name in components:
        if name == "evidence":
            content[name] = (
                "実測：試験のために作った値である"
                "｜.claude/hooks/tests/test_codex_self_receipt.py"
            )
        elif name == "decision":
            content[name] = {
                "options": ["案A"],
                "judgments": ["これは試験用の判定である"],
            }
        else:
            content[name] = "見出し一：これは試験のためだけに書いた本文である。"
    return content


def _write_page(dest_dir, name, components, content=None):
    """一時の置き場に、指定した部品だけを持つ頁を1枚書く。返るもの＝pathのstr。"""
    plan = ExplanationPlan(
        audience="project_novice",
        depth="deep",
        components=tuple(components),
        reason_codes=("project_novice_default",),
        provisional=False,
        should_continue=False,
        delivery="local_html",
        publish_policy="never",
    )
    _, entries = rp._glossary()
    body = content if content is not None else _content_for(components)
    html = render_components(
        plan, title="検査用の頁", content=body, glossary_entries=entries
    )
    dest_dir = Path(dest_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)
    path = dest_dir / (name + ".html")
    path.write_text(html, encoding="utf-8", newline="\n")
    return str(path)


class TurnMarkerWritingTests(unittest.TestCase):
    """① codex の依頼の受付で印が書かれる／② claude では書かれない。"""

    def test_codex_user_prompt_submit_writes_a_marker(self):
        policy = load_policy(path=None, env={})
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "local-root"
            state = StateStore(Path(td) / "state.db")
            handle_event(
                {**COMMON, "hook_event_name": "UserPromptSubmit", "prompt": PAGE_PROMPT},
                runtime="codex",
                project_root=PROJECT_ROOT,
                policy=policy,
                html_output_path=HTML_OUTPUT,
                state_store=state,
                local_artifact_root=root,
            )
            project_hash = _project_hash(PROJECT_ROOT)
            marker = tm.read_turn_marker(
                root, "codex", project_hash, session_id=COMMON["session_id"]
            )
            latest = tm.read_turn_marker(root, "codex", project_hash)

        self.assertIsNotNone(marker)
        self.assertEqual(marker["turn_id"], COMMON["turn_id"])
        self.assertIsNotNone(latest)
        self.assertEqual(latest["session_id"], COMMON["session_id"])

    def test_claude_user_prompt_submit_writes_no_marker(self):
        policy = load_policy(path=None, env={})
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "local-root"
            state = StateStore(Path(td) / "state.db")
            handle_event(
                {**COMMON, "hook_event_name": "UserPromptSubmit", "prompt": PAGE_PROMPT},
                runtime="claude",
                project_root=PROJECT_ROOT,
                policy=policy,
                html_output_path=HTML_OUTPUT,
                state_store=state,
                local_artifact_root=root,
            )
            project_hash = _project_hash(PROJECT_ROOT)
            marker = tm.read_turn_marker(
                root, "claude", project_hash, session_id=COMMON["session_id"]
            )

        self.assertIsNone(marker)
        # 置き場そのものが作られない（claudeでは何も書かないので current-turn も無い）。
        self.assertFalse((Path(td) / "local-root" / "current-turn").exists())


class TurnMarkerAgeTests(unittest.TestCase):
    """③ 古い印は読まれない。"""

    def test_a_stale_marker_is_not_read(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "local-root"
            project_hash = "hash-for-age-test"
            old_payload = {
                "runtime": "codex",
                "project_hash": project_hash,
                "session_id": "sess-old",
                "turn_id": "turn-old",
                "saved_at": time.time() - 999999,
            }
            tm._atomic_write_json(
                tm._session_marker_path(root, "codex", project_hash, "sess-old"),
                old_payload,
            )
            tm._atomic_write_json(
                tm._latest_marker_path(root, "codex", project_hash), old_payload
            )

            by_session = tm.read_turn_marker(
                root, "codex", project_hash, session_id="sess-old"
            )
            latest = tm.read_turn_marker(root, "codex", project_hash)

        self.assertIsNone(by_session)
        self.assertIsNone(latest)


class RecordCodexReceiptTests(unittest.TestCase):
    """④ 印があるとき記録が1件残り、Stopの照合が有効と判定する。
    ⑤ --runtime を付けないと記録しない。
    ⑥ CODEX_SESSION_ID があれば latest ではなくその会話の印を使う。
    """

    def test_marker_present_receipt_recorded_and_validated_at_stop(self):
        policy = load_policy(path=None, env={})
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "local-root"
            state_path = Path(td) / "state.db"
            state = StateStore(state_path)

            pre = handle_event(
                {**COMMON, "hook_event_name": "UserPromptSubmit", "prompt": PAGE_PROMPT},
                runtime="codex",
                project_root=PROJECT_ROOT,
                policy=policy,
                html_output_path=HTML_OUTPUT,
                state_store=state,
                local_artifact_root=root,
            )
            self.assertIn("hookSpecificOutput", pre)

            project_hash = _project_hash(PROJECT_ROOT)
            saved_plan = state.load_plan(
                runtime="codex",
                project_hash=project_hash,
                session_id=COMMON["session_id"],
                turn_id=COMMON["turn_id"],
            )
            self.assertIsNotNone(saved_plan)

            page_path = _write_page(root, "codex-self-receipt", saved_plan.components)

            note = rp.record_codex_receipt(
                page_path,
                saved_plan.components,
                "pass",
                [],
                PROJECT_ROOT,
                state_path,
                local_root=root,
            )
            self.assertIn("検品の記録", note)
            self.assertIn("に残した", note)
            self.assertIn("合格=True", note)

            # フック側（composer）と同じ関数で用語集の場所を決める＝道具の記録と照合が
            # 同じ用語集を見る（試験を別のリポジトリの中から走らせても結果が変わらない）。
            glossary_paths = visual_paths.glossary_paths(PROJECT_ROOT, CLAUDE_DIR)
            stop = handle_event(
                {
                    **COMMON,
                    "hook_event_name": "Stop",
                    "last_assistant_message": PLAIN_RESPONSE,
                    "stop_hook_active": False,
                },
                runtime="codex",
                project_root=PROJECT_ROOT,
                policy=policy,
                html_output_path=HTML_OUTPUT,
                state_store=state,
                glossary_paths=glossary_paths,
                local_artifact_root=root,
            )

        # 記録が有効と判定された＝Stopは差し戻さない。
        self.assertEqual(stop, {})

    def test_without_runtime_flag_no_receipt_is_recorded(self):
        with tempfile.TemporaryDirectory() as td:
            spec_path = Path(td) / "flag-off-spec.json"
            spec_path.write_text(
                (
                    '{"name": "codex-self-receipt-flagoff", "title": "検査専用", '
                    '"components": ["overview"], "reasons": ["project_novice_default"], '
                    '"publish": "never", '
                    '"content": {"overview": "検査専用の本文である。"}}'
                ),
                encoding="utf-8",
            )
            fake_smoke = types.SimpleNamespace(status="pass", errors=())
            with patch.object(rp, "run_visual_smoke", return_value=fake_smoke), \
                 patch.object(rp, "record_codex_receipt") as recorder:
                rp.main(["render_page.py", str(spec_path)])

        recorder.assert_not_called()

    def test_env_session_id_wins_over_latest_marker(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "local-root"
            state_path = Path(td) / "state.db"
            project_hash = _project_hash(PROJECT_ROOT)

            # sess-A を先に書き、sess-B を後に書く＝latestはsess-Bになる。
            tm.write_turn_marker(root, "codex", project_hash, "sess-A", "turn-A")
            tm.write_turn_marker(root, "codex", project_hash, "sess-B", "turn-B")

            page_path = _write_page(root, "codex-self-receipt-env", ("overview",))

            with patch.dict("os.environ", {"CODEX_SESSION_ID": "sess-A"}, clear=False):
                note = rp.record_codex_receipt(
                    page_path,
                    ("overview",),
                    "pass",
                    [],
                    PROJECT_ROOT,
                    state_path,
                    local_root=root,
                )

        self.assertIn("turn-A", note)
        self.assertNotIn("turn-B", note)
        self.assertNotIn("環境変数が無いので", note)


class CodexOnlyInstructionLineTests(unittest.TestCase):
    """⑦ codex の指示文に新しい1行があり、claude の指示文には無い。"""

    def _plan(self):
        return ExplanationPlan(
            audience="project_novice",
            depth="deep",
            components=("overview", "evidence"),
            reason_codes=("explicit_always",),
            provisional=False,
            should_continue=False,
            delivery="local_html",
            publish_policy="always",
        )

    def test_codex_gets_the_extra_line(self):
        directive = compile_directive(self._plan(), HTML_OUTPUT, runtime="codex")

        self.assertIn("--runtime codex", directive)

    def test_claude_does_not_get_the_extra_line(self):
        directive = compile_directive(self._plan(), HTML_OUTPUT, runtime="claude")

        self.assertNotIn("--runtime codex", directive)

    def test_default_runtime_does_not_get_the_extra_line(self):
        directive = compile_directive(self._plan(), HTML_OUTPUT)

        self.assertNotIn("--runtime codex", directive)


if __name__ == "__main__":
    unittest.main()

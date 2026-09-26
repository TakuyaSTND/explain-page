"""作業の実体が無いターンの検品証免除（2026-08-28・ユーザー委任）。

通知への応答・現状維持の確認のように、ターン内に tool_use が1つも無い応答は
Stop で差し戻さない。判定できない時は従来どおり差し戻す（fail-closed）。
経緯＝claims/claude-code-hook-noop-20260828.md。
"""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

HOOKS_DIR = Path(__file__).resolve().parents[1]
if str(HOOKS_DIR) not in sys.path:
    sys.path.insert(0, str(HOOKS_DIR))

from visual.adapters import _claude_turn_tool_activity, _jsonl_tail_records
from visual.entrypoint import handle_event
from visual.policy import load_policy
from visual.state import StateStore

HTML_OUTPUT = Path(__file__).resolve().parents[2] / "html-output.md"
CWD = "C:/repo"
SESSION = "session"


def _user_record(text: str, session: str = SESSION) -> dict:
    return {
        "type": "user",
        "sessionId": session,
        "cwd": CWD,
        "message": {"role": "user", "content": [{"type": "text", "text": text}]},
    }


def _assistant_record(blocks: list, session: str = SESSION) -> dict:
    return {
        "type": "assistant",
        "sessionId": session,
        "cwd": CWD,
        "message": {"role": "assistant", "content": blocks},
    }


def _tool_result_record(session: str = SESSION) -> dict:
    return {
        "type": "user",
        "sessionId": session,
        "cwd": CWD,
        "message": {
            "role": "user",
            "content": [{"type": "tool_result", "tool_use_id": "t1", "content": "ok"}],
        },
    }


def _write_transcript(directory: Path, records: list) -> str:
    path = directory / "transcript.jsonl"
    payload = "\n".join(json.dumps(r, ensure_ascii=False) for r in records) + "\n"
    path.write_text(payload, encoding="utf-8", newline="\n")
    return str(path)


def _run_stop(state: StateStore, transcript_path: str) -> dict:
    policy = load_policy(path=None, env={})
    common = {"cwd": CWD, "session_id": SESSION, "prompt_id": "turn"}
    handle_event(
        {**common, "hook_event_name": "UserPromptSubmit", "prompt": "3案を図で比較して"},
        runtime="claude",
        project_root=CWD,
        policy=policy,
        html_output_path=HTML_OUTPUT,
        state_store=state,
    )
    return handle_event(
        {
            **common,
            "hook_event_name": "Stop",
            "transcript_path": transcript_path,
            "stop_hook_active": False,
        },
        runtime="claude",
        project_root=CWD,
        policy=policy,
        html_output_path=HTML_OUTPUT,
        state_store=state,
    )


class NoopTurnExemptionTests(unittest.TestCase):
    def test_stop_without_tool_use_is_exempt(self):
        with tempfile.TemporaryDirectory() as td:
            transcript = _write_transcript(
                Path(td),
                [
                    _user_record("通知が来ました"),
                    _assistant_record([{"type": "text", "text": "状態は変わっていません。"}]),
                ],
            )
            result = _run_stop(StateStore(Path(td) / "state.db"), transcript)
        self.assertEqual(result, {})

    def test_stop_with_tool_use_still_blocks(self):
        with tempfile.TemporaryDirectory() as td:
            transcript = _write_transcript(
                Path(td),
                [
                    _user_record("3案を図で比較して"),
                    _assistant_record(
                        [
                            {"type": "text", "text": "調べます"},
                            {"type": "tool_use", "id": "t1", "name": "Bash", "input": {}},
                        ]
                    ),
                    _tool_result_record(),
                    _assistant_record([{"type": "text", "text": "結果はこうです"}]),
                ],
            )
            result = _run_stop(StateStore(Path(td) / "state.db"), transcript)
        self.assertEqual(result.get("decision"), "block")

    def test_unreadable_transcript_still_blocks(self):
        # 転写が読めない＝判定不能。fail-closed で従来どおり差し戻す。
        with tempfile.TemporaryDirectory() as td:
            result = _run_stop(
                StateStore(Path(td) / "state.db"), str(Path(td) / "missing.jsonl")
            )
        self.assertEqual(result.get("decision"), "block")

    def test_foreign_session_records_still_block(self):
        # 別セッションの記録が混ざる＝判定不能扱い（tool_use が無くても免除しない）。
        with tempfile.TemporaryDirectory() as td:
            transcript = _write_transcript(
                Path(td),
                [
                    _user_record("通知が来ました", session="other-session"),
                    _assistant_record(
                        [{"type": "text", "text": "変化なし"}], session="other-session"
                    ),
                ],
            )
            result = _run_stop(StateStore(Path(td) / "state.db"), transcript)
        self.assertEqual(result.get("decision"), "block")

    def test_tool_result_only_user_record_is_not_a_turn_anchor(self):
        # tool_result だけの user record（道具の返り）はターンの起点ではない＝
        # その後に tool_use が無くても、起点はさらに前の生ユーザー発話になる。
        records = [
            _user_record("直して"),
            _assistant_record([{"type": "tool_use", "id": "t1", "name": "Edit", "input": {}}]),
            _tool_result_record(),
            _assistant_record([{"type": "text", "text": "直しました"}]),
        ]
        self.assertIs(_claude_turn_tool_activity(tuple(records), SESSION), True)

    def test_activity_is_none_without_user_anchor(self):
        records = [_assistant_record([{"type": "text", "text": "文だけ"}])]
        self.assertIs(_claude_turn_tool_activity(tuple(records), SESSION), None)

    def test_tail_reader_drops_partial_first_line(self):
        # 末尾読みは途中の欠けた行を捨てる＝巨大な転写でも現在ターンだけが読める。
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "big.jsonl"
            filler = json.dumps(_user_record("古いターン" * 50), ensure_ascii=False)
            tail_user = json.dumps(_user_record("いまのターン"), ensure_ascii=False)
            tail_asst = json.dumps(
                _assistant_record([{"type": "text", "text": "返答"}]), ensure_ascii=False
            )
            body = "\n".join([filler] * 200 + [tail_user, tail_asst]) + "\n"
            path.write_text(body, encoding="utf-8", newline="\n")
            limit = len(tail_user.encode("utf-8")) + len(tail_asst.encode("utf-8")) + 10
            records = _jsonl_tail_records(str(path), limit)
        self.assertTrue(records)
        texts = json.dumps(
            [r.get("message", {}).get("content") for r in records], ensure_ascii=False
        )
        self.assertIn("いまのターン", texts)
        self.assertNotIn("古いターン", texts)


if __name__ == "__main__":
    unittest.main()

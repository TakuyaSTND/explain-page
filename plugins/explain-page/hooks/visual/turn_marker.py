from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any

# Codexには「頁を公開した」道具の合図（PostToolUse）が無いので、依頼の受付
# （UserPromptSubmit）で「いまの会話とその回」の印を残し、`render_page.py` が
# その印を読んで自分の代わりに検品の記録を書く（2026-09-25）。
#
# ⚠️安全側の設計＝この印は「印が要ること」の材料でしかない。記録そのものを
#   作ってよいかどうかは呼び出し側（render_page.py の --runtime codex）が決める。
#   ここでは例外を外へ投げない＝書けない・読めない場合は黙って諦める
#   （フックの本体処理を止めないため。既存の describe_skip 等と同じ思想）。

DEFAULT_MAX_AGE_SECONDS = 21600
_UNSAFE_CHARS = "/\\:*?\"<>|\r\n\t "


def _safe_component(value: Any) -> str:
    text = str(value) if value is not None else ""
    cleaned = "".join("_" if ch in _UNSAFE_CHARS else ch for ch in text)
    return cleaned or "unknown"


def _current_dir(root: str | Path) -> Path:
    return Path(root) / "current-turn"


def _session_marker_path(root: str | Path, runtime: str, project_hash: str, session_id: str) -> Path:
    name = "%s-%s-%s.json" % (
        _safe_component(runtime),
        _safe_component(project_hash),
        _safe_component(session_id),
    )
    return _current_dir(root) / name


def _latest_marker_path(root: str | Path, runtime: str, project_hash: str) -> Path:
    name = "%s-%s-latest.json" % (_safe_component(runtime), _safe_component(project_hash))
    return _current_dir(root) / name


def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.parent / (path.name + ".tmp-" + str(os.getpid()) + "-" + str(time.time_ns()))
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    handle = open(tmp_path, "wb")
    try:
        handle.write(data)
        handle.flush()
        os.fsync(handle.fileno())
    finally:
        handle.close()
    os.replace(tmp_path, path)


def write_turn_marker(
    root: str | Path,
    runtime: str,
    project_hash: str,
    session_id: str,
    turn_id: str,
) -> bool:
    """「いまの会話とその回」の印を残す。返るもの＝書けたら True、書けなければ False。

    入れるもの＝置き場の根・runtime・project の識別子・会話の識別子・回の識別子。
    書く先＝2つ（そのものの会話用と、最新用）。原子的（一時ファイル→置き換え）に書く。
    ⚠️例外を外へ投げない＝書けなくても処理は止めない（呼び出し側の既定の振る舞い）。
    """
    try:
        payload = {
            "runtime": str(runtime),
            "project_hash": str(project_hash),
            "session_id": str(session_id),
            "turn_id": str(turn_id),
            "saved_at": time.time(),
        }
        _atomic_write_json(
            _session_marker_path(root, runtime, project_hash, session_id), payload
        )
        _atomic_write_json(_latest_marker_path(root, runtime, project_hash), payload)
        return True
    except (OSError, ValueError, TypeError):
        return False


def read_turn_marker(
    root: str | Path,
    runtime: str,
    project_hash: str,
    session_id: str | None = None,
    max_age_seconds: int = DEFAULT_MAX_AGE_SECONDS,
) -> dict[str, Any] | None:
    """印を読む。session_id があればその会話の印、無ければ最新の印。

    返すもの＝{runtime, project_hash, session_id, turn_id, saved_at} の辞書。
    古い（max_age_seconds を超える）・壊れている・無いなら None。
    ⚠️例外を外へ投げない。
    """
    try:
        path = (
            _session_marker_path(root, runtime, project_hash, session_id)
            if session_id
            else _latest_marker_path(root, runtime, project_hash)
        )
        raw = path.read_bytes()
        payload = json.loads(raw.decode("utf-8"))
    except (OSError, ValueError, TypeError, UnicodeDecodeError):
        return None
    if not isinstance(payload, dict):
        return None
    required_keys = ("runtime", "project_hash", "session_id", "turn_id", "saved_at")
    if not all(key in payload for key in required_keys):
        return None
    for key in ("runtime", "project_hash", "session_id", "turn_id"):
        value = payload.get(key)
        if not isinstance(value, str) or not value:
            return None
    try:
        saved_at = float(payload.get("saved_at"))
    except (TypeError, ValueError):
        return None
    try:
        age_limit = float(max_age_seconds)
    except (TypeError, ValueError):
        age_limit = float(DEFAULT_MAX_AGE_SECONDS)
    if time.time() - saved_at > age_limit:
        return None
    return payload

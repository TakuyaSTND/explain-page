from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any, Callable, Iterable

from .contracts import HookEnvelope

DEFAULT_MAX_TRANSCRIPT_BYTES = 2 * 1024 * 1024
CODEX_SESSION_SEARCH_LIMIT = 8


def _text(value: Any) -> str:
    return value if isinstance(value, str) else ""


def _safe_int(value: Any) -> int:
    if isinstance(value, bool):
        return 0
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _safe_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"true", "1", "yes", "on"}
    return bool(value) if isinstance(value, (int, float)) else False


def _safe_limit(value: Any) -> int:
    if isinstance(value, bool):
        return DEFAULT_MAX_TRANSCRIPT_BYTES
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return DEFAULT_MAX_TRANSCRIPT_BYTES
    return parsed if parsed > 0 else DEFAULT_MAX_TRANSCRIPT_BYTES


def _is_in_scope(cwd: str, project_root: str) -> bool:
    if not cwd or not project_root:
        return False
    try:
        current = os.path.normcase(os.path.realpath(os.path.abspath(cwd)))
        root = os.path.normcase(os.path.realpath(os.path.abspath(project_root)))
        return os.path.commonpath((current, root)) == root
    except (OSError, ValueError):
        return False


def _same_path(left: str, right: str) -> bool:
    if not left or not right:
        return False
    try:
        normalized_left = os.path.normcase(os.path.realpath(os.path.abspath(left)))
        normalized_right = os.path.normcase(os.path.realpath(os.path.abspath(right)))
        return normalized_left == normalized_right
    except (OSError, ValueError):
        return os.path.normcase(left) == os.path.normcase(right)


def _capabilities(event: str, runtime: str = "") -> frozenset[str]:
    values: set[str] = set()
    if event in {"Stop", "SubagentStop"}:
        values.add("can_continue")
    if event == "UserPromptSubmit":
        values.add("can_context")
    if event == "PostToolUse":
        values.add("can_receipt")
    if event == "SubagentStop":
        values.add("can_subagent")
    if event == "pre_llm_call":
        values.add("can_context")
    if event == "pre_verify":
        values.add("can_continue")
    if event == "post_tool_call":
        values.add("can_receipt")
    if event == "subagent_stop":
        values.add("can_subagent")
    # StopFailure is a Claude Code official diagnostic event. Codex does not
    # expose this hook, so the same event name must not grant a capability there.
    if runtime == "claude" and event == "StopFailure":
        values.add("can_diagnostic")
    return frozenset(values)


def _direct_response(data: dict[str, Any], *extra_fields: str) -> str:
    fields = ("last_assistant_message", "final_response", *extra_fields)
    for field in fields:
        value = data.get(field)
        if isinstance(value, str) and value:
            return value
    return ""


def _bounded_bytes(path: str, max_bytes: int) -> bytes:
    if not path:
        return b""
    try:
        with Path(path).open("rb") as stream:
            return stream.read(_safe_limit(max_bytes))
    except (OSError, ValueError):
        return b""


def _parse_jsonl_payload(payload: bytes) -> tuple[dict[str, Any], ...]:
    if not payload:
        return ()
    records: list[dict[str, Any]] = []
    try:
        text = payload.decode("utf-8", errors="replace")
        for line in text.splitlines():
            try:
                value = json.loads(line)
            except (TypeError, ValueError, json.JSONDecodeError):
                continue
            if isinstance(value, dict):
                records.append(value)
    except (UnicodeError, ValueError):
        return ()
    return tuple(records)


def _jsonl_records(path: str, max_bytes: int) -> tuple[dict[str, Any], ...]:
    return _parse_jsonl_payload(_bounded_bytes(path, max_bytes))


def _jsonl_tail_records(path: str, max_bytes: int) -> tuple[dict[str, Any], ...]:
    """末尾からの有界読み（2026-08-28）。

    _jsonl_records は先頭からの有界読みなので、上限（既定2MB）を超える長い記録では
    **Stopしたターン（常にファイル末尾にある）が1行も読めない**。ターン内の tool_use の
    有無を見る用途では末尾だけが要るので、こちらを使う。途中から読むと最初の行は
    欠けている可能性がある＝最初の改行までを捨てる。
    """
    if not path:
        return ()
    limit = _safe_limit(max_bytes)
    try:
        target = Path(path)
        size = target.stat().st_size
        with target.open("rb") as stream:
            if size > limit:
                stream.seek(size - limit)
                payload = stream.read(limit)
                cut = payload.find(b"\n")
                payload = payload[cut + 1:] if cut >= 0 else b""
            else:
                payload = stream.read(limit)
    except (OSError, ValueError):
        return ()
    return _parse_jsonl_payload(payload)


def _claude_turn_tool_activity(
    records: tuple[dict[str, Any], ...], expected_session_id: str
) -> bool | None:
    """Stopしたターン（最後の生ユーザー発話より後）に tool_use があったかを返す。

    2026-08-28（ユーザー委任）：「作業の実体が無いターン（通知への応答・現状維持の確認）は
    検品証を要求しない」例外の判定材料。判定できない時（ユーザー発話が見つからない・
    別セッションの記録が混ざる）は None を返し、呼び元は「作業あり」として扱う（fail-closed）。

    ⚠️「生ユーザー発話」＝type=user かつ isMeta でなく、text を持ち tool_result を持たない record。
    背景タスクの通知もここに含まれる＝通知で始まったターンはその通知が起点になる（turn_id の切れ目と同じ）。
    """
    last_user = None
    for idx, record in enumerate(records):
        session = record.get("sessionId")
        if isinstance(session, str) and session and expected_session_id and session != expected_session_id:
            return None
        if record.get("type") != "user" and record.get("role") != "user":
            continue
        if record.get("isMeta"):
            continue
        message = record.get("message") if isinstance(record.get("message"), dict) else record
        content = message.get("content")
        if isinstance(content, str):
            if content.strip():
                last_user = idx
            continue
        if not isinstance(content, list):
            continue
        has_text = False
        has_tool_result = False
        for block in content:
            if not isinstance(block, dict):
                continue
            block_type = block.get("type")
            if block_type == "tool_result":
                has_tool_result = True
            elif block_type == "text":
                text = block.get("text")
                if isinstance(text, str) and text.strip():
                    has_text = True
        if has_text and not has_tool_result:
            last_user = idx
    if last_user is None:
        return None
    for record in records[last_user + 1:]:
        if record.get("type") != "assistant" and record.get("role") != "assistant":
            continue
        message = record.get("message") if isinstance(record.get("message"), dict) else record
        content = message.get("content")
        if not isinstance(content, list):
            continue
        for block in content:
            if isinstance(block, dict) and block.get("type") == "tool_use":
                return True
    return False


def _text_blocks(content: Any, *, allowed_types: set[str]) -> str:
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return ""
    parts: list[str] = []
    for block in content:
        if not isinstance(block, dict):
            continue
        block_type = block.get("type")
        if block_type not in allowed_types:
            continue
        text = block.get("text")
        if isinstance(text, str) and text:
            parts.append(text)
    return "".join(parts)


def _claude_assistant_text(record: dict[str, Any]) -> str:
    # Claude JSONL records have a top-level assistant type/role and a nested
    # message content list. Deliberately do not accept Codex response_item
    # envelopes here.
    if record.get("type") != "assistant" and record.get("role") != "assistant":
        return ""
    message = record.get("message")
    if isinstance(message, dict):
        content = message.get("content")
    else:
        content = record.get("content")
    return _text_blocks(content, allowed_types={"text"})


def _codex_assistant_text(record: dict[str, Any]) -> str:
    # Codex session logs wrap assistant responses in response_item/payload.
    # Keeping this shape narrow prevents a Claude transcript from being
    # interpreted as a Codex transcript merely because it has role=assistant.
    if record.get("type") != "response_item":
        return ""
    payload = record.get("payload")
    if not isinstance(payload, dict):
        return ""
    if payload.get("type") != "message" or payload.get("role") != "assistant":
        return ""
    return _text_blocks(payload.get("content"), allowed_types={"output_text"})


def _last_text(
    records: Iterable[dict[str, Any]], parser: Callable[[dict[str, Any]], str]
) -> str:
    result = ""
    for record in records:
        text = parser(record)
        if text:
            result = text
    return result


def _metadata_sources(record: dict[str, Any]) -> tuple[dict[str, Any], ...]:
    sources: list[dict[str, Any]] = []
    queue: list[dict[str, Any]] = [record]
    while queue and len(sources) < 16:
        source = queue.pop(0)
        sources.append(source)
        for key in ("payload", "metadata", "context", "turn_context", "session"):
            child = source.get(key)
            if isinstance(child, dict) and child not in sources and child not in queue:
                queue.append(child)
    return tuple(sources)


def _metadata_cwds(record: dict[str, Any]) -> tuple[str, ...]:
    if record.get("type") not in {
        "session_meta",
        "session_start",
        "session",
        "turn_context",
    }:
        return ()
    values: list[str] = []
    for source in _metadata_sources(record):
        for key in ("cwd", "working_directory", "project_root", "project_dir"):
            value = source.get(key)
            if isinstance(value, str) and value:
                values.append(value)
    return tuple(values)


def _metadata_session_ids(record: dict[str, Any]) -> tuple[str, ...]:
    if record.get("type") not in {
        "session_meta",
        "session_start",
        "session",
        "turn_context",
    }:
        return ()
    values: list[str] = []
    for source in _metadata_sources(record):
        for key in ("session_id", "id"):
            value = source.get(key)
            if isinstance(value, str) and value:
                values.append(value)
    return tuple(values)


def _direct_transcript_matches(
    records: Iterable[dict[str, Any]], cwd: str, expected_session_id: str
) -> bool:
    records = tuple(records)
    metadata_cwds = tuple(
        candidate for record in records for candidate in _metadata_cwds(record)
    )
    metadata_session_ids = tuple(
        candidate for record in records for candidate in _metadata_session_ids(record)
    )
    if metadata_cwds and not all(_same_path(candidate, cwd) for candidate in metadata_cwds):
        return False
    if (
        metadata_session_ids
        and expected_session_id
        and any(candidate != expected_session_id for candidate in metadata_session_ids)
    ):
        return False
    return True


def _codex_session_matches(
    records: Iterable[dict[str, Any]], cwd: str, expected_session_id: str = ""
) -> bool:
    if not cwd:
        return False
    records = tuple(records)
    metadata_cwds = tuple(
        candidate for record in records for candidate in _metadata_cwds(record)
    )
    if not metadata_cwds or not all(
        _same_path(candidate, cwd) for candidate in metadata_cwds
    ):
        return False
    metadata_session_ids = tuple(
        candidate for record in records for candidate in _metadata_session_ids(record)
    )
    if expected_session_id and metadata_session_ids and any(
        candidate != expected_session_id for candidate in metadata_session_ids
    ):
        return False
    return True


def _codex_discovery_paths() -> tuple[Path, ...]:
    root = Path.home() / ".codex" / "sessions"
    try:
        candidates = [path for path in root.rglob("*.jsonl") if path.is_file()]
    except OSError:
        return ()
    ranked: list[tuple[float, str, Path]] = []
    for path in candidates:
        try:
            stat = path.stat()
        except OSError:
            continue
        ranked.append((stat.st_mtime, str(path), path))
    ranked.sort(key=lambda item: (item[0], item[1]), reverse=True)
    return tuple(item[2] for item in ranked[:CODEX_SESSION_SEARCH_LIMIT])


def _codex_response(
    data: dict[str, Any],
    *,
    max_transcript_bytes: int,
    project_root: str,
    event: str,
    expected_session_id: str = "",
) -> str:
    direct = _direct_response(data)
    if direct:
        return direct
    if event not in {"Stop", "SubagentStop"}:
        return ""

    limit = _safe_limit(max_transcript_bytes)
    transcript_path = _text(data.get("transcript_path"))
    if transcript_path:
        records = _jsonl_records(transcript_path, limit)
        if _direct_transcript_matches(
            records, _text(data.get("cwd")), expected_session_id
        ):
            response = _last_text(records, _codex_assistant_text)
            if response:
                return response

    cwd = _text(data.get("cwd"))
    if not cwd:
        return ""
    for candidate in _codex_discovery_paths():
        records = _jsonl_records(str(candidate), limit)
        if _codex_session_matches(records, cwd, expected_session_id):
            response = _last_text(records, _codex_assistant_text)
            if response:
                return response
    return ""


def from_claude(
    data: dict[str, Any],
    project_root: str,
    *,
    max_transcript_bytes: int = DEFAULT_MAX_TRANSCRIPT_BYTES,
) -> HookEnvelope:
    event = _text(data.get("hook_event_name") or data.get("event"))
    response = _direct_response(data)
    turn_has_tool_use = True
    if not response and event in {"Stop", "SubagentStop"}:
        records = _jsonl_records(
            _text(data.get("transcript_path")), _safe_limit(max_transcript_bytes)
        )
        if _direct_transcript_matches(
            records, _text(data.get("cwd")), _text(data.get("session_id"))
        ):
            response = _last_text(records, _claude_assistant_text)
    if event == "Stop":
        # 2026-08-28：ターン内の tool_use の有無は**末尾**読みで判定する（長い記録では
        # 先頭読みに現在ターンが入らない）。foreign metadata の拒否は先頭読みと同じ関門を通す。
        tail_records = _jsonl_tail_records(
            _text(data.get("transcript_path")), _safe_limit(max_transcript_bytes)
        )
        if tail_records and _direct_transcript_matches(
            tail_records, _text(data.get("cwd")), _text(data.get("session_id"))
        ):
            activity = _claude_turn_tool_activity(
                tail_records, _text(data.get("session_id"))
            )
            if activity is not None:
                turn_has_tool_use = activity
    session_id = _text(data.get("session_id"))
    turn_id = _text(data.get("prompt_id") or data.get("turn_id"))
    digest = hashlib.sha256(response.encode("utf-8")).hexdigest()
    return HookEnvelope(
        schema_version=1,
        runtime="claude",
        runtime_version="",
        event=event,
        project_root=project_root,
        profile_id="",
        session_id=session_id,
        turn_id=turn_id,
        invocation_id=_text(data.get("prompt_id") or data.get("tool_use_id")),
        user_message=_text(data.get("prompt")),
        response_text=response,
        response_sha256=digest,
        transcript_path=_text(data.get("transcript_path")),
        changed_paths=(),
        stop_hook_active=_safe_bool(data.get("stop_hook_active")),
        attempt=_safe_int(data.get("attempt")),
        capabilities=_capabilities(event, "claude"),
        valid_for_state=bool(
            session_id and turn_id and _is_in_scope(_text(data.get("cwd")), project_root)
        ),
        turn_has_tool_use=turn_has_tool_use,
    )


def from_hermes(data: dict[str, Any], project_root: str) -> HookEnvelope:
    extra = data.get("extra") if isinstance(data.get("extra"), dict) else {}
    event = _text(data.get("hook_event_name") or data.get("event"))
    session_id = _text(data.get("session_id"))
    turn_id = _text(extra.get("turn_id") or extra.get("parent_turn_id"))
    response = _direct_response(
        extra,
        "assistant_response",
        "response_text",
    )
    changed = extra.get("changed_paths")
    changed_paths = tuple(str(item) for item in changed) if isinstance(changed, list) else ()
    digest = hashlib.sha256(response.encode("utf-8")).hexdigest()
    return HookEnvelope(
        schema_version=1,
        runtime="hermes",
        runtime_version=_text(extra.get("model")),
        event=event,
        project_root=project_root,
        profile_id=_text(data.get("profile_id") or extra.get("profile_id")),
        session_id=session_id,
        turn_id=turn_id,
        invocation_id=_text(extra.get("tool_call_id") or extra.get("task_id")),
        user_message=_text(extra.get("user_message")),
        response_text=response,
        response_sha256=digest,
        transcript_path="",
        changed_paths=changed_paths,
        stop_hook_active=_safe_bool(extra.get("stop_hook_active")),
        attempt=_safe_int(extra.get("attempt")),
        capabilities=_capabilities(event, "hermes"),
        valid_for_state=bool(
            session_id and turn_id and _is_in_scope(_text(data.get("cwd")), project_root)
        ),
        coding=_safe_bool(extra.get("coding")),
    )


def from_codex(
    data: dict[str, Any],
    project_root: str,
    *,
    max_transcript_bytes: int = DEFAULT_MAX_TRANSCRIPT_BYTES,
) -> HookEnvelope:
    event = _text(data.get("hook_event_name") or data.get("event"))
    session_id = _text(data.get("session_id"))
    response = _codex_response(
        data,
        max_transcript_bytes=max_transcript_bytes,
        project_root=project_root,
        event=event,
        expected_session_id=session_id,
    )
    turn_id = _text(data.get("turn_id") or data.get("prompt_id"))
    changed = data.get("changed_paths")
    changed_paths = tuple(str(item) for item in changed) if isinstance(changed, list) else ()
    digest = hashlib.sha256(response.encode("utf-8")).hexdigest()
    valid_for_state = bool(
        session_id and turn_id and _is_in_scope(_text(data.get("cwd")), project_root)
    )
    return HookEnvelope(
        schema_version=1,
        runtime="codex",
        runtime_version=_text(data.get("model")),
        event=event,
        project_root=project_root,
        profile_id="",
        session_id=session_id,
        turn_id=turn_id,
        invocation_id=_text(data.get("tool_use_id") or data.get("prompt_id")),
        user_message=_text(data.get("prompt")),
        response_text=response,
        response_sha256=digest,
        transcript_path=_text(data.get("transcript_path")),
        changed_paths=changed_paths,
        stop_hook_active=_safe_bool(data.get("stop_hook_active")),
        attempt=_safe_int(data.get("attempt")),
        capabilities=_capabilities(event, "codex"),
        valid_for_state=valid_for_state,
    )

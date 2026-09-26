from __future__ import annotations

import json
import re
from typing import Any

from .contracts import SubagentDigest


def _text(value: Any) -> str:
    return value if isinstance(value, str) else ""


SECRET_VALUE = re.compile(
    r"(?i)\b(token|api[_-]?key|password|passwd|secret)\s*[:=]\s*[^\s,;]+"
)
SECRET_MARKER = re.compile(r"\bSECRET(?:[-_][A-Z0-9]+)+\b", re.I)


def _bounded(value: Any, limit: int) -> str:
    text = _text(value)
    text = SECRET_VALUE.sub(lambda match: f"{match.group(1)}=[REDACTED]", text)
    text = SECRET_MARKER.sub("[REDACTED]", text)
    return text[:limit]


def _evidence(value: Any) -> tuple[str, ...]:
    if not isinstance(value, list):
        return ()
    return tuple(_bounded(item, 300) for item in value[:10])


def _safe_int(value: Any) -> int:
    try:
        parsed = int(value or 0)
    except (TypeError, ValueError):
        return 0
    return min(max(parsed, 0), 86_400_000)


def _summary_object(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if not isinstance(value, str):
        return {}
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return {"result": value}
    return parsed if isinstance(parsed, dict) else {"result": value}


# 出所の分からない記録に付ける印（2026-08-31）。
#
# ⚠️**なぜ要るか＝ユーザーの言葉に見える文が、こちらの記録に混ざっていた。**
#    `subagent_digests_v2` に「作り直さないでいい」「止めず指示文で促すだけにする」といった
#    行があり、別セッションがそれを見て「ユーザーの承認が記録されている」と読みかけた
#    （その場では承認として扱わず照会してきた＝正しい判断だった）。
#
# 正体＝子の最後の発言をそのまま `result` に入れていたもので、どの子かを示す `agent_type` も
# 宣言された `goal` も空だった。∴**誰の言葉か分からない**。にもかかわらずこの記録は
# 次のターンの指示文に `[subagent_digests]` としてそのまま差し込まれていた
# ＝**届いていない発言が、確定した結果として読める形で入る**。
#
# ∴出所が分からないものには印を付け、指示文には**内容を渡さない**（件数だけ知らせる）。
UNATTRIBUTED = "unattributed"


def digest_from_payload(runtime: str, data: dict[str, Any]) -> SubagentDigest:
    """フックに届いた中身から、子の作業の要約を1件作る。

    入れるもの＝フックの生の中身。返るもの＝要約1件。
    ⚠️出所（`goal` か `agent_type`）が分からないものは `unattributed` の印を付ける。
    """
    if runtime == "hermes":
        extra = data.get("extra") if isinstance(data.get("extra"), dict) else {}
        summary = _summary_object(extra.get("child_summary"))
        goal = _bounded(summary.get("goal"), 200) or _bounded(extra.get("child_role"), 200)
        status = _bounded(extra.get("child_status"), 40) or "unknown"
        return SubagentDigest(
            parent_turn_id=_text(extra.get("parent_turn_id")),
            child_session_id=_text(extra.get("child_session_id")),
            goal=goal or UNATTRIBUTED,
            result=_bounded(summary.get("result"), 1000),
            evidence=_evidence(summary.get("evidence")),
            risk=_bounded(summary.get("risk"), 200) or "unknown",
            needs_human=_bounded(summary.get("needs_human"), 300),
            status=status if goal else UNATTRIBUTED,
            duration_ms=_safe_int(extra.get("duration_ms")),
        )
    if runtime in {"claude", "codex"}:
        summary = _summary_object(data.get("last_assistant_message"))
        parent_turn_id = (
            _text(data.get("prompt_id") or data.get("turn_id"))
            if runtime == "claude"
            else _text(data.get("turn_id") or data.get("prompt_id"))
        )
        goal = _bounded(summary.get("goal"), 200) or _bounded(data.get("agent_type"), 200)
        status = _bounded(data.get("status"), 40) or "success"
        return SubagentDigest(
            parent_turn_id=parent_turn_id,
            child_session_id=_text(data.get("agent_id")),
            goal=goal or UNATTRIBUTED,
            result=_bounded(summary.get("result"), 1000),
            evidence=_evidence(summary.get("evidence")),
            risk=_bounded(summary.get("risk"), 200) or "unknown",
            needs_human=_bounded(summary.get("needs_human"), 300),
            # ⚠️出所が分からないものを success と記録すると「確定した結果」に見える。
            status=status if goal else UNATTRIBUTED,
            duration_ms=_safe_int(data.get("duration_ms")),
        )
    raise ValueError(f"unsupported runtime: {runtime}")


def is_unattributed(digest: SubagentDigest) -> bool:
    """出所が分からない記録か。⚠️これが真のものは**内容を指示文に渡さない**。"""
    return digest.goal == UNATTRIBUTED or digest.status == UNATTRIBUTED

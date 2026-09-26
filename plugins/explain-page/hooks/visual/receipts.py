from __future__ import annotations

import hashlib
import re
from collections.abc import Iterable
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Mapping

from .contracts import ArtifactReceipt, GlossarySnapshot, HookEnvelope
from .glossary import GlossaryEntry
from .glossary_check import check_html

try:
    from .artifact_inspection import inspect_artifact_html
except ImportError:  # Agent C may add this module after this integration lands.
    inspect_artifact_html = None  # type: ignore[assignment]

EXTERNAL_URL = re.compile(
    r"https?://[^\s\"'<>]+|file://|(?:src|href|action|formaction)\s*=\s*[\"']?//",
    re.I,
)
RESOURCE_ATTRIBUTE = re.compile(
    r"(?:src|href|action|formaction)\s*=\s*(?:\"([^\"]*)\"|'([^']*)'|([^\s>]+))",
    re.I,
)
CSS_URL = re.compile(r"url\s*\(\s*([^)]*?)\s*\)", re.I)
CSS_IMPORT = re.compile(r"@import\b", re.I)
NETWORK_CODE = re.compile(r"\b(?:fetch|XMLHttpRequest|WebSocket|EventSource|sendBeacon)\s*\(?", re.I)
SECRET_VALUE = re.compile(
    r"(?i)\b(token|api[_-]?key|password|passwd|secret)\s*[:=]\s*[^\s,;]+"
)
SECRET_MARKER = re.compile(r"\bSECRET(?:[-_][A-Z0-9]+)+\b", re.I)

# 2026-08-29（ユーザー承認＝不具合1）：検品証を作れなかった理由を、人が読める1行にする。
# ⚠️build_receipt は理由ごとに違う ValueError を投げるのに、呼び出し側は
#   except (OSError, ValueError): return {} で**全部を握り潰していた**。
#   その結果、承認済みの置き場の外へ頁を書くと検品証が0枚のまま、警告もログも出なかった
#   （実測：2026-08-29に公開した2枚が0枚。記録上の最後の検品証は08-28）。
#   これは fail-open と同じ「失敗が沈黙として現れる」型なので、理由を文字にして外へ出す。
SKIP_REASONS = {
    "artifact path is outside the approved local root":
        "承認済みの置き場の外にHTMLを書いたので、検品証を作れませんでした",
    "artifact must be an existing .html file":
        "指定されたpathにHTMLが見つからないので、検品証を作れませんでした",
    "artifact exceeds configured size limit":
        "HTMLが上限より大きいので、検品証を作れませんでした",
    "artifact contains an external dependency":
        "HTMLが外部のもの（外部のURL・通信のコード・読み込み）に頼っているので、検品証を作れませんでした",
}
SKIP_FALLBACK = "検品証を作れませんでした"


def describe_skip(path: Any, error: BaseException, local_root: Any = "") -> str:
    """検品証を作れなかった理由を、そのまま画面に出せる日本語1行にする。

    入れるもの＝対象のpath・例外・承認済みの置き場。返るもの＝1行の説明。
    ⚠️例外の英文をそのまま出さない。読むのは人なので、次に何をすればよいかまで書く。
    """
    key = str(error).strip()
    # 2026-09-26（見やすさ V6）：理由の後ろに「: 当たった箇所」が付くことがある＝前方一致で引く。
    known = next((k for k in SKIP_REASONS if key == k or key.startswith(k + ":")), None)
    body = SKIP_REASONS.get(known, SKIP_FALLBACK) if known else SKIP_FALLBACK
    parts = ["[検品証なし] " + body]
    if known and key != known:
        parts.append("当たった箇所=" + key[len(known) + 1:].strip()[:120])
    parts.append("対象=" + str(path))
    if local_root:
        parts.append("承認済みの置き場=" + str(local_root))
    if known is None:
        parts.append("理由=" + (key[:120] if key else type(error).__name__))
    return " ／ ".join(parts)


# These fields are metadata, not a second copy of the artifact. Keep malformed
# third-party diagnostics bounded and redact obvious credential-shaped values.
def _safe_text(value: Any, limit: int = 500) -> str:
    if not isinstance(value, str):
        return ""
    value = SECRET_VALUE.sub(
        lambda match: f"{match.group(1)}=[REDACTED]", value
    )
    value = SECRET_MARKER.sub("[REDACTED]", value)
    return value[:limit]


def _values(value: Any, *, limit: int = 100) -> tuple[str, ...]:
    if isinstance(value, str):
        value = (value,)
    elif isinstance(value, (set, frozenset)):
        value = tuple(sorted(value, key=str))
    if not isinstance(value, (list, tuple)):
        return ()
    return tuple(
        text
        for text in (_safe_text(item, 300) for item in value[:limit])
        if text
    )


def _contained(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def is_glossary_stale(
    receipt: ArtifactReceipt, current: GlossarySnapshot
) -> bool:
    return receipt.glossary_sha256 != current.effective_sha256


class _MarkupOnly(HTMLParser):
    """頁から地の文（タグの外の文字）を取り除き、タグ・属性・script と style の中身だけを残す。

    2026-09-26（実害＝報告の頁の記録の欄に「git fetch」と書いただけで、公開時に
    「外部の依存あり」と判定され検品の記録が作られなかった）：利用者の本文はエスケープ
    されて地の文になるので、そこにある単語は通信にも読み込みにもならない。動くもの
    （script の中身・on で始まる属性・javascript: の値）と読み込むもの（src 等の属性・
    style の中身・style 属性）は、どれもタグか script／style の中にある＝ここに残る。
    """

    # 属性のうち、動く・読み込むものだけを残す（ほかの属性＝data-*・aria-label・title・alt 等には
    # 利用者の本文がエスケープされて入るが、動きも読み込みもしない＝実測で写しの釦の data-copy に
    # 記録の欄の文が入り「git fetch」を拾っていた）。
    LOADING_ATTRS = frozenset(
        {"src", "href", "xlink:href", "action", "formaction", "srcset", "poster",
         "background", "data", "codebase", "style", "srcdoc", "manifest", "ping"}
    )

    def __init__(self) -> None:
        super().__init__(convert_charrefs=False)
        self.parts: list[str] = []
        self._raw_depth = 0

    def _tag(self, tag, attrs) -> str:  # noqa: ANN001
        kept = []
        for name, value in attrs:
            name = (name or "").lower()
            text = "" if value is None else str(value)
            lowered = text.lower()
            if (
                name.startswith("on")
                or name in self.LOADING_ATTRS
                or "url(" in lowered
                or "javascript:" in lowered
            ):
                kept.append('%s="%s"' % (name, text.replace('"', "'")))
        return "<%s %s>" % (tag, " ".join(kept)) if kept else "<%s>" % tag

    def handle_starttag(self, tag, attrs):  # noqa: ANN001
        self.parts.append(self._tag(tag, attrs))
        if tag in ("script", "style"):
            self._raw_depth += 1

    def handle_startendtag(self, tag, attrs):  # noqa: ANN001
        self.parts.append(self._tag(tag, attrs))

    def handle_endtag(self, tag):  # noqa: ANN001
        self.parts.append("</%s>" % tag)
        if tag in ("script", "style") and self._raw_depth:
            self._raw_depth -= 1

    def handle_data(self, data):  # noqa: ANN001
        if self._raw_depth:
            self.parts.append(data)
        else:
            self.parts.append(" ")


def _markup_only(text: str) -> str:
    """`_MarkupOnly` の結果。読み取りに失敗したら全文を返す（安全側＝緩めない）。"""
    try:
        parser = _MarkupOnly()
        parser.feed(text)
        parser.close()
        return "".join(parser.parts)
    except Exception:
        return text


def external_dependency_reason(text: str) -> str | None:
    """頁が外部の何かに頼っていれば、その理由を1行で返す。頼っていなければ None。

    ・外部のURL（https:// 等・file://・// で始まる属性）＝全文で調べる（従来どおり）。
    ・通信のコード（fetch・XMLHttpRequest・WebSocket 等）・@import・CSS の url()・
      読み込みの属性（src／href／action／formaction）＝地の文を除いた部分
      （`_markup_only`）で調べる。script の中では fetch は呼び出しの形でなくても止める。
    """
    match = EXTERNAL_URL.search(text)
    if match:
        return "外部のURL: " + match.group(0)[:60]
    markup = _markup_only(text)
    match = NETWORK_CODE.search(markup)
    if match:
        return "通信のコード: " + match.group(0)[:60]
    if CSS_IMPORT.search(markup):
        return "CSS の @import"
    for match in RESOURCE_ATTRIBUTE.finditer(markup):
        value = next((group for group in match.groups() if group is not None), "").strip()
        if value and not value.lower().startswith("data:") and not value.startswith("#"):
            return "読み込みの属性: " + match.group(0)[:60]
    for match in CSS_URL.finditer(markup):
        value = match.group(1).strip().strip("\"'").strip()
        if value and not value.lower().startswith("data:") and not value.startswith("#"):
            return "CSS の url(): " + match.group(0)[:60]
    return None


def _has_external_dependency(text: str) -> bool:
    return external_dependency_reason(text) is not None


def _inspection_value(result: Any, key: str, default: Any = None) -> Any:
    if isinstance(result, Mapping):
        return result.get(key, default)
    return getattr(result, key, default)


def _inspect(
    text: str,
    *,
    required_components: tuple[str, ...],
    glossary_entries: Mapping[str, GlossaryEntry] | None,
) -> dict[str, Any]:
    empty: dict[str, Any] = {
        "present_components": (),
        "missing_components": (),
        "missing_decision_parts": (),
        "unwrapped_identifiers": (),
        "unknown_identifiers": (),
        "missing_evidence_sources": (),
        "inspection_errors": (),
        "ok": True,
    }
    if inspect_artifact_html is None:
        return {
            **empty,
            "missing_components": required_components,
            "inspection_errors": ("artifact inspection unavailable",),
            "ok": False,
        }
    try:
        result = inspect_artifact_html(
            text,
            required_components=required_components,
            glossary_entries=glossary_entries,
        )
    except Exception as exc:  # a bad inspection must block, never crash hooks
        return {
            **empty,
            "missing_components": required_components,
            "inspection_errors": (
                _safe_text(f"artifact inspection error: {type(exc).__name__}"),
            ),
            "ok": False,
        }
    inspected = {
        "present_components": _values(_inspection_value(result, "present_components")),
        "missing_components": _values(_inspection_value(result, "missing_components")),
        "missing_decision_parts": _values(
            _inspection_value(result, "missing_decision_parts")
        ),
        "unwrapped_identifiers": _values(
            _inspection_value(result, "unwrapped_identifiers")
        ),
        "unknown_identifiers": _values(_inspection_value(result, "unknown_identifiers")),
        "missing_evidence_sources": _values(
            _inspection_value(result, "missing_evidence_sources")
        ),
        "inspection_errors": _values(
            _inspection_value(result, "inspection_errors")
            or _inspection_value(result, "errors")
        ),
        "ok": bool(_inspection_value(result, "ok", False)),
    }
    if not inspected["ok"] and not inspected["inspection_errors"]:
        inspected["inspection_errors"] = ("artifact inspection failed",)
    return inspected


def _smoke_fields(
    *,
    previewed: bool,
    status: str | None,
    errors: Iterable[str] = (),
    result: Any = None,
) -> tuple[str, tuple[str, ...]]:
    if not previewed:
        return "not_run", ()
    if result is not None:
        status = _inspection_value(result, "status", status)
        errors = _inspection_value(result, "errors", errors)
    normalized = status.strip().lower() if isinstance(status, str) else "not_run"
    if normalized not in {"pass", "fail", "not_run"}:
        normalized = "fail"
    error_values = (errors,) if isinstance(errors, str) else errors
    return normalized, _values(error_values if error_values is not None else ())


def _listed(values: Iterable[str], limit: int = 5) -> str:
    items = [str(v) for v in values]
    head = "・".join(items[:limit])
    return head + ("ほか%d件" % (len(items) - limit) if len(items) > limit else "")


def receipt_problems(
    receipt: ArtifactReceipt,
    current_glossary: GlossarySnapshot,
    *,
    local_root: str | Path,
    max_artifact_bytes: int,
    required_components: Iterable[str] | None = None,
) -> list[str]:
    """検品証が照合に通らない理由を、日本語の短い文の一覧で返す（通るなら空の一覧）。

    2026-09-26（見やすさ V4）：照合は以前、合格か否かの1つの真偽値しか返さず、差し戻しの
    文にも「どれも条件を満たしていない」としか書けなかった。いちばん多かった理由
    （公開のあとで要る部品が変わった＝公開し直せば通る）も、読み手には見えなかった。
    ⚠️条件は validate_receipt と同じ＝validate_receipt はこの一覧が空かどうかだけを見る。
    """
    expected_components = (
        _values(tuple(required_components)) if required_components is not None else receipt.required_components
    )
    problems: list[str] = []
    if receipt.visibility != "local":
        problems.append("公開の範囲がローカルでない")
    if receipt.gloss_check != "pass":
        problems.append("用語の検査が不合格")
    if not receipt.previewed or receipt.visual_smoke != "pass" or receipt.visual_smoke_errors:
        detail = _listed(receipt.visual_smoke_errors, 2) if receipt.visual_smoke_errors else receipt.visual_smoke
        problems.append("表示検査が不合格（%s）" % detail)
    if not receipt.inspection_ok or receipt.inspection_errors:
        detail = _listed(receipt.inspection_errors, 2) if receipt.inspection_errors else "不合格"
        problems.append("中身の検査が不合格（%s）" % detail)
    if receipt.missing_components:
        problems.append("頁に無い部品: " + _listed(receipt.missing_components))
    if receipt.missing_decision_parts:
        problems.append("判断の欄に足りない部品: " + _listed(receipt.missing_decision_parts))
    if receipt.unwrapped_identifiers:
        problems.append("用語の説明を付けていない識別子: " + _listed(receipt.unwrapped_identifiers))
    if receipt.unknown_identifiers:
        problems.append("用語集に無い識別子: " + _listed(receipt.unknown_identifiers))
    if receipt.missing_evidence_sources:
        problems.append("根拠の出所が空の行: " + _listed(receipt.missing_evidence_sources))
    # 2026-08-29：ここは以前 required の**完全一致**を求めていた。
    # ⚠️同日に入れた案③（応答終了時に予告と実態を突き合わせて確定する）以降、
    #   検品証は「予告」の部品一覧で作られ、照合は「確定」の部品一覧で行われるため、
    #   応答が部品を1つでも増やすと**どんな頁でも永久に不一致**になる。
    #   ∴一致ではなく「検品証が求めた分を確定が含んでいるか」に緩める。
    #   実質の検査は下の行が担う＝**確定で要求された部品が実際に頁にあるか**。ここは緩めない。
    if not set(receipt.required_components).issubset(set(expected_components)):
        problems.append(
            "公開のあとで要る部品が変わった（公開時: %s／確定: %s）＝最後の返事の直前に公開し直すと通る"
            % (",".join(receipt.required_components), ",".join(expected_components))
        )
    missing_now = [c for c in expected_components if c not in set(receipt.present_components)]
    if missing_now:
        problems.append("確定で要る部品が頁に無い: " + _listed(missing_now))
    if is_glossary_stale(receipt, current_glossary):
        problems.append("公開のあとで用語集が変わった＝公開し直すと通る")
    if problems:
        return problems
    candidate = Path(receipt.path).resolve()
    root = Path(local_root).resolve()
    if not _contained(candidate, root):
        return ["頁が承認済みの置き場の外にある"]
    if not candidate.is_file() or candidate.suffix.lower() != ".html":
        return ["頁のファイルが見つからない"]
    try:
        content = candidate.read_bytes()
    except OSError:
        return ["頁のファイルを読めない"]
    if len(content) > max_artifact_bytes:
        return ["頁が大きさの上限を超えている"]
    if len(content) != receipt.bytes or hashlib.sha256(content).hexdigest() != receipt.sha256:
        return ["公開のあとで頁のファイルが書き換わった＝公開し直すと通る"]
    reason = external_dependency_reason(content.decode("utf-8", errors="replace"))
    if reason:
        return ["外部の依存がある（%s）" % reason]
    return []


def validate_receipt(
    receipt: ArtifactReceipt,
    current_glossary: GlossarySnapshot,
    *,
    local_root: str | Path,
    max_artifact_bytes: int,
    required_components: Iterable[str] | None = None,
) -> bool:
    return not receipt_problems(
        receipt,
        current_glossary,
        local_root=local_root,
        max_artifact_bytes=max_artifact_bytes,
        required_components=required_components,
    )


def build_receipt(
    path: str | Path,
    *,
    envelope: HookEnvelope,
    glossary: GlossarySnapshot,
    glossary_entries: Mapping[str, GlossaryEntry] | None = None,
    local_root: str | Path,
    previewed: bool = False,
    max_artifact_bytes: int = 2_097_152,
    required_components: Iterable[str] = (),
    visual_smoke_status: str | None = None,
    visual_smoke_errors: Iterable[str] = (),
    visual_smoke_result: Any = None,
) -> ArtifactReceipt:
    candidate = Path(path).resolve()
    root = Path(local_root).resolve()
    if not _contained(candidate, root):
        raise ValueError("artifact path is outside the approved local root")
    if not candidate.is_file() or candidate.suffix.lower() != ".html":
        raise ValueError("artifact must be an existing .html file")
    content = candidate.read_bytes()
    if len(content) > max_artifact_bytes:
        raise ValueError("artifact exceeds configured size limit")
    text = content.decode("utf-8", errors="replace")
    external = external_dependency_reason(text)
    if external:
        # 2026-09-26（見やすさ V6）：当たった箇所を添える＝describe_skip が画面に出す。
        raise ValueError("artifact contains an external dependency: " + external)
    required = _values(tuple(required_components))
    inspection = _inspect(
        text,
        required_components=required,
        glossary_entries=glossary_entries,
    )
    source = f"{glossary.shared_source}+project"
    gloss_check = "not_run"
    if glossary_entries is not None:
        result = check_html(text, glossary_entries)
        failed = bool(
            glossary.shared_source == "missing"
            or glossary.effective_count <= 0
            or not glossary_entries
            or result.mismatches
            or result.unresolved
            or result.accessibility_errors
            or glossary.same_file_duplicates
        )
        gloss_check = "fail" if failed else "pass"
    visual_smoke, smoke_errors = _smoke_fields(
        previewed=previewed,
        status=visual_smoke_status,
        errors=visual_smoke_errors,
        result=visual_smoke_result,
    )
    return ArtifactReceipt(
        runtime=envelope.runtime,
        project_root=envelope.project_root,
        session_id=envelope.session_id,
        turn_id=envelope.turn_id,
        path=str(candidate),
        sha256=hashlib.sha256(content).hexdigest(),
        bytes=len(content),
        created_at=datetime.now(timezone.utc).isoformat(),
        gloss_check=gloss_check,
        glossary_sha256=glossary.effective_sha256,
        glossary_source=source,
        visual_smoke=visual_smoke,
        previewed=previewed,
        visibility="local",
        required_components=required,
        present_components=inspection["present_components"],
        missing_components=inspection["missing_components"],
        missing_decision_parts=inspection["missing_decision_parts"],
        unwrapped_identifiers=inspection["unwrapped_identifiers"],
        unknown_identifiers=inspection["unknown_identifiers"],
        missing_evidence_sources=inspection["missing_evidence_sources"],
        inspection_errors=inspection["inspection_errors"],
        inspection_ok=bool(inspection["ok"]),
        visual_smoke_errors=smoke_errors,
    )

from __future__ import annotations

import re
from dataclasses import dataclass
from html.parser import HTMLParser
from typing import Mapping, Sequence

from .glossary import GlossaryEntry
from .render_components import DECISION_SCRIPT


_VOID_TAGS = {
    "area",
    "base",
    "br",
    "col",
    "embed",
    "hr",
    "img",
    "input",
    "link",
    "meta",
    "param",
    "source",
    "track",
    "wbr",
}
_EXCLUDED_VISIBLE_TAGS = {
    "script",
    "style",
    # 2026-08-29：pre は機械の出力をそのまま貼る場所。用語ホバーで飾ると
    # 出力そのものが変わるので、未包装の検査から外す（ログにたまたま用語が
    # 出ただけで頁が落ちるのを防ぐ）。
    "pre",
    # 2026-08-29：図（svg）の中の文字も同じ理由で外す。SVGの中に用語ホバーの
    # span は置けない（HTMLの要素なので描画されない）ので、包めない語を
    # 「包んでいない」と叱ることになってしまう。図の語は本文側で説明する。
    "svg",
    "text",
    "h1",
    "h2",
    "h3",
    "h4",
    "h5",
    "h6",
    "th",
    "dt",
}

# 本文とみなすタグ。⚠️**ここに無いものは検査しない**＝既定が「包まない」なので、
#   取りこぼしは穴にならない（列挙漏れが穴になる向きを、2026-09-01に逆にした）。
_PROSE_TAGS = frozenset({"p", "li", "blockquote"})
_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_.-]*$")
_ASCII_WORD = re.compile(r"[A-Za-z0-9_]")


@dataclass(frozen=True)
class ArtifactInspection:
    present_components: tuple[str, ...]
    missing_components: tuple[str, ...]
    missing_decision_parts: tuple[str, ...]
    unwrapped_identifiers: tuple[str, ...]
    unknown_identifiers: tuple[str, ...]
    missing_evidence_sources: tuple[str, ...]
    errors: tuple[str, ...]

    @property
    def ok(self) -> bool:
        return not any(
            (
                self.missing_components,
                self.missing_decision_parts,
                self.unwrapped_identifiers,
                self.unknown_identifiers,
                self.missing_evidence_sources,
                self.errors,
            )
        )


def _normal_term(value: str) -> str:
    return value.strip().strip("`").strip()


def _looks_like_identifier(value: str, known: set[str]) -> bool:
    if not value or value not in known and not _IDENTIFIER.fullmatch(value):
        return False
    if any(mark in value for mark in ("/", "\\", "://", ":")) or any(
        char.isspace() for char in value
    ):
        return False
    return (
        value in known
        or "_" in value
        or (any(char.islower() for char in value) and any(char.isupper() for char in value))
        or (len(value) > 1 and value.isupper())
    )


def _contains_term(text: str, term: str) -> bool:
    start = 0
    while True:
        index = text.find(term, start)
        if index < 0:
            return False
        before = text[index - 1] if index else ""
        after_index = index + len(term)
        after = text[after_index] if after_index < len(text) else ""
        if not (_ASCII_WORD.fullmatch(before) or _ASCII_WORD.fullmatch(after)):
            return True
        start = index + 1


def _is_placeholder_source(value: str) -> bool:
    normalized = re.sub(r"\s+", "", value.casefold())
    return normalized in {
        "",
        "未提示",
        "未確認",
        "不明",
        "missing",
        "unpresented",
        "n/a",
        "na",
        "tbd",
        "todo",
        "unknown",
        "none",
        "null",
        "pending",
        "-",
        "—",
    }


class _ArtifactParser(HTMLParser):
    def __init__(self, known_identifiers: set[str]):
        super().__init__(convert_charrefs=True)
        self.known_identifiers = known_identifiers
        self.stack: list[dict[str, object]] = []
        self.present_components: list[str] = []
        self.errors: list[str] = []
        self.ids: set[str] = set()
        self.describedby: list[str] = []
        self.decision_parts = {
            "choice_control": False,
            "pre": False,
            "copy_button": False,
            "select_all": False,
            "objection": False,
        }
        self.code_stack: list[dict[str, object]] = []
        self.script_stack: list[list[str]] = []
        self.scripts: list[str] = []
        self.code_identifiers: list[tuple[str, bool]] = []
        self.wrapped_identifiers: set[str] = set()
        self.seen_identifiers: set[str] = set()
        self.unwrapped_identifiers: list[str] = []
        self.visible_text: list[str] = []
        self.evidence_rows: list[dict[str, object]] = []
        self.current_evidence: dict[str, object] | None = None

    def _inside(self, predicate) -> bool:
        return any(predicate(item) for item in self.stack)

    def _add_component(self, name: str) -> None:
        if name not in self.present_components:
            self.present_components.append(name)

    def _record_known_identifiers(self, text: str, *, wrapped: bool) -> None:
        for term in sorted(self.known_identifiers, key=lambda value: (-len(value), value)):
            if not _contains_term(text, term) or term in self.seen_identifiers:
                continue
            self.seen_identifiers.add(term)
            if not wrapped:
                self.unwrapped_identifiers.append(term)

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = {key: (value or "") for key, value in attrs}
        for key, value in values.items():
            lowered_key = key.lower()
            lowered_value = value.strip().lower()
            if lowered_key.startswith("on") and lowered_value:
                self.errors.append(f"active event handler is not allowed: {lowered_key}")
            if lowered_key in {"href", "src", "action", "formaction"} and lowered_value.startswith(
                "javascript:"
            ):
                self.errors.append(f"javascript URL is not allowed: {lowered_key}")
        classes = set(values.get("class", "").split())
        component = values.get("data-component", "").strip()
        style = values.get("style", "").lower()
        item: dict[str, object] = {
            "tag": tag,
            "component": component,
            "classes": classes,
            "tooltip": "t" in classes
            and bool(values.get("data-d"))
            and values.get("tabindex") == "0",
            "source": (
                "source" in classes
                or "evidence-source" in classes
                or "data-source" in values
                or values.get("data-label", "").strip() == "どこで確かめたか"
            ),
            "source_missing": (
                values.get("data-missing-source", "").strip().lower() == "true"
                or ("data-source" in values and not values.get("data-source", "").strip())
            ),
            "hidden": (
                "hidden" in values
                or values.get("aria-hidden", "").strip().lower() == "true"
                or bool(re.search(r"(?:display|visibility)\s*:\s*(?:none|hidden)", style))
                or bool(re.search(r"opacity\s*:\s*0(?:\D|$)", style))
            ),
            "text": [],
        }
        self.stack.append(item)

        element_id = values.get("id", "").strip()
        if element_id:
            self.ids.add(element_id)
        ref = values.get("aria-describedby", "").strip()
        if ref:
            self.describedby.extend(part for part in ref.split() if part)

        if component == "overview":
            if tag == "header":
                self._add_component("overview")
            else:
                self.errors.append("overview must be represented by a header")
        elif component == "summary":
            if tag == "section" or "summary-note" in classes:
                self._add_component("summary")
            else:
                self.errors.append("summary must be an explicit section or summary-note")
        elif component == "provenance":
            if tag == "footer":
                self._add_component("provenance")
            else:
                self.errors.append("provenance must be represented by a footer")
        elif component:
            if tag == "section":
                self._add_component(component)
            else:
                self.errors.append(f"{component} must be represented by a section")

        inside_decision = self._inside(
            lambda stack_item: stack_item.get("component") == "decision"
        )
        if inside_decision and tag == "input" and values.get("type", "").lower() in {
            "radio",
            "checkbox",
            "number",
        }:
            self.decision_parts["choice_control"] = True
        if (
            inside_decision
            and tag == "input"
            and values.get("name", "").lower() == "objection"
        ):
            self.decision_parts["objection"] = True
        if inside_decision and tag == "textarea" and "objection" in (
            values.get("name", "") + " " + values.get("id", "")
        ).lower():
            self.decision_parts["objection"] = True
        if inside_decision and tag == "pre":
            self.decision_parts["pre"] = True
        if inside_decision and tag == "button":
            identity = (values.get("id", "") + " " + values.get("data-role", "")).lower()
            if "copy" in identity:
                self.decision_parts["copy_button"] = True
            if "select-all" in identity or "select-decision" in identity:
                self.decision_parts["select_all"] = True

        inside_evidence = self._inside(
            lambda stack_item: stack_item.get("component") == "evidence"
        )
        inside_table_head = self._inside(lambda stack_item: stack_item.get("tag") == "thead")
        if tag == "tr" and inside_evidence and not inside_table_head:
            self.current_evidence = {
                "id": values.get("data-evidence") or f"row-{len(self.evidence_rows) + 1}",
                "cell_count": 0,
                "source_cell_count": 0,
                "source_cell_indexes": [],
                "source_attr": False,
                "source_attr_text": "",
                "source_text": [],
                "source_depths": set(),
            }
            self.evidence_rows.append(self.current_evidence)
        elif self.current_evidence is not None:
            if tag == "td":
                self.current_evidence["cell_count"] = int(
                    self.current_evidence.get("cell_count", 0)
                ) + 1
                if item["source"]:
                    self.current_evidence["source_cell_count"] = int(
                        self.current_evidence.get("source_cell_count", 0)
                    ) + 1
                    source_cell_indexes = self.current_evidence["source_cell_indexes"]
                    assert isinstance(source_cell_indexes, list)
                    source_cell_indexes.append(self.current_evidence["cell_count"])
                    if values.get("data-source", "").strip():
                        self.current_evidence["source_attr"] = True
                        self.current_evidence["source_attr_text"] = values[
                            "data-source"
                        ].strip()
                    if not item["source_missing"] and not self._inside(
                        lambda stack_item: bool(stack_item.get("hidden"))
                    ):
                        depths = self.current_evidence["source_depths"]
                        assert isinstance(depths, set)
                        depths.add(len(self.stack))

        if tag == "code":
            frame = {
                "text": [],
                "tooltip": bool(item["tooltip"]),
                "depth": len(self.stack),
            }
            self.code_stack.append(frame)
        elif self.code_stack and item["tooltip"]:
            self.code_stack[-1]["tooltip"] = True
        if tag == "script":
            if values.get("src", "").strip():
                self.errors.append("external script source is not allowed")
            self.script_stack.append([])

        if tag in _VOID_TAGS:
            self.stack.pop()

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)
        if self.stack and self.stack[-1].get("tag") == tag:
            self.stack.pop()

    def handle_data(self, data: str) -> None:
        for item in self.stack:
            if item.get("tooltip"):
                tooltip_text = item.get("text")
                if isinstance(tooltip_text, list):
                    tooltip_text.append(data)
        if self.code_stack:
            text = self.code_stack[-1]["text"]
            assert isinstance(text, list)
            text.append(data)
        if self.script_stack:
            self.script_stack[-1].append(data)

        if self.current_evidence is not None and data.strip():
            depths = self.current_evidence["source_depths"]
            assert isinstance(depths, set)
            if not self._inside(lambda item: bool(item.get("hidden"))) and any(
                depth <= len(self.stack) for depth in depths
            ):
                source_text = self.current_evidence["source_text"]
                assert isinstance(source_text, list)
                source_text.append(data)

        if not data.strip():
            return
        if self._inside(lambda item: bool(item.get("hidden"))):
            return
        if self._inside(lambda item: item.get("tag") in _EXCLUDED_VISIBLE_TAGS):
            return
        if self._inside(lambda item: bool(item.get("tooltip"))):
            return
        if self._inside(lambda item: item.get("tag") == "code"):
            return
        # ⚠️用語の包装を求めるのは**本文だけ**（2026-09-01のユーザー裁定）。
        #   ラベル・表の欄・色札・出所欄などは対象外＝取りこぼしても穴にならない側に倒す。
        if self._inside(lambda item: item.get("tag") in _PROSE_TAGS):
            self._record_known_identifiers(data, wrapped=False)
        self.visible_text.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag == "script" and self.script_stack:
            self.scripts.append("".join(self.script_stack.pop()).strip())
        if tag == "code" and self.code_stack:
            frame = self.code_stack.pop()
            text = "".join(str(part) for part in frame["text"]).strip()
            self.code_identifiers.append((text, bool(frame["tooltip"])))
            # ⚠️2026-09-01の裁定＝コード書きの中は本文ではないので**包装を求めない**。
            #   （以前はここで求めており、道筋に用語が混ざるだけで検品が落ちていた。）
        if tag == "tr" and self.current_evidence is not None:
            self.current_evidence = None

        if not self.stack:
            self.errors.append(f"mismatched closing tag </{tag}>")
            return
        if self.stack[-1].get("tag") == tag:
            item = self.stack.pop()
            self._record_closed_item(item)
            return
        tags = [str(item.get("tag")) for item in self.stack]
        if tag not in tags:
            self.errors.append(f"mismatched closing tag </{tag}>")
            return
        self.errors.append(f"mismatched nesting before </{tag}>")
        while self.stack:
            item = self.stack.pop()
            self._record_closed_item(item)
            if item.get("tag") == tag:
                break

    def _record_closed_item(self, item: dict[str, object]) -> None:
        if not item.get("tooltip"):
            return
        text = item.get("text")
        if isinstance(text, list):
            normalized = "".join(str(part) for part in text).strip()
            if normalized:
                self.wrapped_identifiers.add(normalized)
                self._record_known_identifiers(normalized, wrapped=True)

    def finish(self) -> None:
        remaining = [str(item.get("tag")) for item in self.stack if item.get("tag") not in _VOID_TAGS]
        if remaining:
            self.errors.append("unclosed tags: " + ", ".join(remaining))
        for ref in self.describedby:
            if ref not in self.ids:
                self.errors.append(f"aria-describedby target is missing: {ref}")
        if len(self.scripts) > 1:
            self.errors.append("multiple inline scripts are not allowed")
        for script in self.scripts:
            if script != DECISION_SCRIPT.strip():
                self.errors.append("unapproved inline script is not allowed")


def inspect_artifact_html(
    text: str,
    *,
    required_components: Sequence[str],
    glossary_entries: Mapping[str, GlossaryEntry],
) -> ArtifactInspection:
    normalized_entries = {
        _normal_term(key): entry
        for key, entry in glossary_entries.items()
        if _normal_term(key)
    }
    known_identifiers = {
        term
        for term in normalized_entries
        if _looks_like_identifier(term, set(normalized_entries))
    }
    parser = _ArtifactParser(known_identifiers)
    try:
        parser.feed(text)
        parser.close()
    except Exception as error:  # HTMLParser errors must not break a hook.
        parser.errors.append(f"html parse failed: {type(error).__name__}")
    parser.finish()

    required = tuple(dict.fromkeys(str(item) for item in required_components if item))
    present = tuple(parser.present_components)
    missing_components = tuple(item for item in required if item not in present)

    decision_order = ("choice_control", "pre", "copy_button", "select_all", "objection")
    missing_decision_parts = (
        tuple(name for name in decision_order if not parser.decision_parts[name])
        if "decision" in required
        else ()
    )

    unwrapped: list[str] = list(parser.unwrapped_identifiers)
    unknown: list[str] = []
    for value, wrapped in parser.code_identifiers:
        if not _looks_like_identifier(value, set(normalized_entries)):
            continue
        # ⚠️包装は求めない（本文だけ包む方針）。⚠️「知らない語」の報告だけは残す
        #   ＝用語集に無い識別子を見つける役目は別なので、そこは弱めない。
        if value not in normalized_entries and value not in unknown:
            unknown.append(value)

    missing_source_rows: list[str] = []
    for row in parser.evidence_rows:
        row_id = str(row["id"])
        cell_count = int(row.get("cell_count", 0))
        source_cell_count = int(row.get("source_cell_count", 0))
        source_cell_indexes_value = row.get("source_cell_indexes", [])
        source_cell_indexes = (
            [int(index) for index in source_cell_indexes_value]
            if isinstance(source_cell_indexes_value, list)
            else []
        )
        source_text_value = row.get("source_text", [])
        source_attr_text = str(row.get("source_attr_text", "")).strip()
        source_text = (
            " ".join(str(part).strip() for part in source_text_value if str(part).strip())
            if isinstance(source_text_value, list)
            else ""
        )
        source_valid = (
            cell_count == 3
            and source_cell_count == 1
            and source_cell_indexes == [3]
            and bool(row.get("source_attr"))
            and not _is_placeholder_source(source_attr_text)
            and not _is_placeholder_source(source_text)
        )
        if cell_count != 3:
            parser.errors.append(
                f"evidence row {row_id} must have exactly 3 cells (found {cell_count})"
            )
        if not source_valid:
            missing_source_rows.append(row_id)
    missing_sources = tuple(missing_source_rows)
    if "evidence" in required and not parser.evidence_rows:
        missing_sources = ("evidence-table",)

    errors = list(dict.fromkeys(parser.errors))
    return ArtifactInspection(
        present_components=present,
        missing_components=missing_components,
        missing_decision_parts=missing_decision_parts,
        unwrapped_identifiers=tuple(unwrapped),
        unknown_identifiers=tuple(unknown),
        missing_evidence_sources=missing_sources,
        errors=tuple(errors),
    )

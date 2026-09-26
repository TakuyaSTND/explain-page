from __future__ import annotations

from dataclasses import dataclass
from html.parser import HTMLParser
from typing import Mapping

from .glossary import GlossaryEntry


@dataclass(frozen=True)
class Mismatch:
    term: str
    occurrence: int
    actual: str
    expected: str


@dataclass(frozen=True)
class GlossaryCheckResult:
    mismatches: tuple[Mismatch, ...]
    extensions: tuple[str, ...]
    new_terms: tuple[str, ...]
    unresolved: int
    accessibility_errors: tuple[str, ...]


def _norm(value: str) -> str:
    return value.replace("**", "").replace("`", "").strip()


class _TooltipParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.active: dict[str, object] | None = None
        self.occurrences: list[tuple[str, str, bool, str]] = []
        self.ids: set[str] = set()
        self.unresolved = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        element_id = values.get("id")
        if element_id:
            self.ids.add(element_id)
        if self.active is not None:
            self.active["nested"] = True
        if "data-d" in values:
            if self.active is not None:
                self.unresolved += 1
            self.active = {
                "tag": tag,
                "description": values.get("data-d") or "",
                "text": [],
                "nested": False,
                "focusable": (
                    "tabindex" in values
                    or tag in {"a", "button", "input", "select", "textarea"}
                ),
                "describedby": values.get("aria-describedby") or "",
            }

    def handle_data(self, data: str) -> None:
        if self.active is not None:
            text = self.active["text"]
            if isinstance(text, list):
                text.append(data)

    def handle_endtag(self, tag: str) -> None:
        if self.active is None or self.active.get("tag") != tag:
            return
        text_value = "".join(str(item) for item in self.active["text"]).strip()
        description = str(self.active["description"]).strip()
        if text_value and description and not self.active.get("nested"):
            self.occurrences.append(
                (
                    text_value,
                    description,
                    bool(self.active.get("focusable")),
                    str(self.active.get("describedby") or ""),
                )
            )
        else:
            self.unresolved += 1
        self.active = None

    def close(self) -> None:
        super().close()
        if self.active is not None:
            self.unresolved += 1
            self.active = None


def check_html(
    html: str,
    entries: Mapping[str, GlossaryEntry],
) -> GlossaryCheckResult:
    parser = _TooltipParser()
    parser.feed(html)
    parser.close()
    counts: dict[str, int] = {}
    mismatches: list[Mismatch] = []
    extensions: list[str] = []
    new_terms: list[str] = []
    accessibility_errors: list[str] = []
    for term, description, focusable, describedby in parser.occurrences:
        counts[term] = counts.get(term, 0) + 1
        if describedby and describedby not in parser.ids:
            accessibility_errors.append(
                f"{term} occurrence {counts[term]} references missing aria-describedby target {describedby}"
            )
        elif not focusable and not describedby:
            accessibility_errors.append(
                f"{term} occurrence {counts[term]} has no tabindex or aria-describedby"
            )
        entry = entries.get(term)
        if entry is None:
            new_terms.append(term)
            continue
        actual = _norm(description)
        expected = _norm(entry.description)
        if actual == expected:
            continue
        if actual.startswith(expected):
            extensions.append(term)
            continue
        mismatches.append(
            Mismatch(
                term=term,
                occurrence=counts[term],
                actual=description,
                expected=entry.description,
            )
        )
    return GlossaryCheckResult(
        mismatches=tuple(mismatches),
        extensions=tuple(extensions),
        new_terms=tuple(new_terms),
        unresolved=parser.unresolved,
        accessibility_errors=tuple(accessibility_errors),
    )

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path

from .contracts import GlossarySnapshot

ROW = re.compile(r"^\|\s*(.*?)\s*\|\s*(.*?)\s*\|$")


@dataclass(frozen=True)
class GlossaryEntry:
    term: str
    description: str
    provenance: str


def _normalized(value: str) -> str:
    return value.replace("**", "").replace("`", "").strip()


def _sha256(path: Path) -> str:
    if not path.is_file():
        return ""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _rows(path: Path) -> tuple[dict[str, str], tuple[str, ...]]:
    values: dict[str, str] = {}
    duplicates: set[str] = set()
    if not path.is_file():
        return values, ()
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        match = ROW.match(line.strip())
        if not match:
            continue
        term = _normalized(match.group(1))
        description = match.group(2).strip()
        if not term or not description or term in {"用語", "関門"}:
            continue
        if set(term) <= {"-", ":", " "}:
            continue
        if term in values and _normalized(values[term]) != _normalized(description):
            duplicates.add(term)
        values[term] = description
    return values, tuple(sorted(duplicates))


def load_glossary_snapshot(
    home_shared: str | Path,
    mirror: str | Path,
    project: str | Path,
) -> tuple[GlossarySnapshot, dict[str, GlossaryEntry]]:
    home_path = Path(home_shared)
    mirror_path = Path(mirror)
    project_path = Path(project)
    if home_path.is_file():
        shared_source = "home"
        shared_path = home_path
    elif mirror_path.is_file():
        shared_source = "mirror"
        shared_path = mirror_path
    else:
        shared_source = "missing"
        shared_path = home_path

    shared, shared_duplicates = _rows(shared_path)
    project_values, project_duplicates = _rows(project_path)
    entries = {
        term: GlossaryEntry(term, description, "shared")
        for term, description in shared.items()
    }
    overrides: list[str] = []
    for term, description in project_values.items():
        previous = entries.get(term)
        if previous is not None and _normalized(previous.description) != _normalized(description):
            overrides.append(term)
        entries[term] = GlossaryEntry(term, description, "project")

    effective_payload = [
        (term, _normalized(entry.description), entry.provenance)
        for term, entry in sorted(entries.items())
    ]
    effective_sha = hashlib.sha256(
        json.dumps(effective_payload, ensure_ascii=False, separators=(",", ":")).encode(
            "utf-8"
        )
    ).hexdigest()
    snapshot = GlossarySnapshot(
        shared_source=shared_source,
        shared_path=str(shared_path),
        shared_sha256=_sha256(home_path),
        mirror_sha256=_sha256(mirror_path),
        project_sha256=_sha256(project_path),
        effective_sha256=effective_sha,
        shared_count=len(shared),
        project_count=len(project_values),
        effective_count=len(entries),
        project_overrides=tuple(sorted(overrides)),
        same_file_duplicates=tuple(
            sorted(set(shared_duplicates) | set(project_duplicates))
        ),
        mirror_matches_home=(
            home_path.is_file()
            and mirror_path.is_file()
            and home_path.read_bytes() == mirror_path.read_bytes()
        ),
    )
    return snapshot, entries

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, replace
from pathlib import Path

from .contracts import GlossarySnapshot

ROW = re.compile(r"^\|\s*(.*?)\s*\|\s*(.*?)\s*\|$")

# 2026-10-18：普通の言葉としても使う語の規則表。プロジェクトの用語集（glossary.md）の隣に置く。
CONTEXT_FILENAME = "glossary-context.json"


@dataclass(frozen=True)
class GlossaryEntry:
    term: str
    description: str
    provenance: str
    # 規則表の手がかりの語。None＝規則なし（今までどおり）／()＝自動では包まない／
    # 非空＝その語の前後 CUE_WINDOW 字に手がかりの語があるときだけ包む（term_boundary.find_term の cues）。
    cues: tuple[str, ...] | None = None


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


def load_context_rules(
    path: str | Path,
) -> tuple[dict[str, tuple[str, ...]], tuple[str, ...], str]:
    """規則表（glossary-context.json）を読む。

    入れるもの＝規則表のpath。返るもの＝(語→手がかりの語の並び, 問題の一覧, ファイルの sha256)。
    形＝{"語": {"cues": ["手がかりの語", ...], "note": "…"}, ...}。語の値は手がかりの並びだけでもよい。
    cues が空の語は「自動では包まない」。_ で始まる鍵に文字を入れたものは注釈で、読み飛ばす。
    ⚠️ファイルが無ければ ({}, (), "")。壊れていても例外を投げない＝その行だけ飛ばして問題に書く
      （規則表の不具合で、頁を組む仕組み・フックを止めない）。
    """
    file = Path(path)
    if not file.is_file():
        return {}, (), ""
    try:
        raw = file.read_bytes()
    except OSError as error:
        return {}, ("規則表を読めない（%s）" % type(error).__name__,), ""
    digest = hashlib.sha256(raw).hexdigest()
    try:
        data = json.loads(raw.decode("utf-8-sig"))
    except (UnicodeDecodeError, ValueError):
        return {}, ("規則表が JSON として読めない",), digest
    if not isinstance(data, dict):
        return {}, ("規則表の一番外側は、語を鍵にした辞書で書く",), digest
    rules: dict[str, tuple[str, ...]] = {}
    problems: list[str] = []
    for raw_term, value in data.items():
        term = _normalized(str(raw_term))
        if not term or (term.startswith("_") and isinstance(value, str)):
            continue
        cues_value = value.get("cues") if isinstance(value, dict) else value
        if not isinstance(cues_value, list):
            problems.append("%s: cues は手がかりの語の並びで書く" % term)
            continue
        cues: list[str] = []
        skipped = False
        for item in cues_value:
            if not isinstance(item, str):
                skipped = True
                continue
            cue = item.strip()
            if cue and cue not in cues:
                cues.append(cue)
        if skipped:
            problems.append("%s: 文字でない手がかりの語は飛ばした" % term)
        rules[term] = tuple(cues)
    return rules, tuple(problems), digest


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

    # 2026-10-18：規則表（プロジェクトの用語集の隣）を、共通・固有をまとめた有効な語に当てる。
    context_path = project_path.with_name(CONTEXT_FILENAME)
    context_rules, context_problems, context_sha = load_context_rules(context_path)
    applied: dict[str, tuple[str, ...]] = {}
    problems = list(context_problems)
    for term, cues in context_rules.items():
        entry = entries.get(term)
        if entry is None:
            problems.append("%s: 用語集に無い語の規則は使わない" % term)
            continue
        entries[term] = replace(entry, cues=cues)
        applied[term] = cues

    effective_payload = [
        (term, _normalized(entry.description), entry.provenance)
        for term, entry in sorted(entries.items())
    ]
    if applied:
        # ⚠️規則表が無い（または何も当たらない）プロジェクトは、ハッシュが1バイトも変わらない
        #   ＝既存の検品証が無効にならない。規則が変われば、頁の包み方が変わるのでハッシュも変わる。
        effective_payload.append(
            ("\u0000context", [[term, list(cues)] for term, cues in sorted(applied.items())])
        )
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
        context_path=str(context_path) if (context_sha or context_problems) else "",
        context_sha256=context_sha,
        context_count=len(applied),
        context_problems=tuple(problems),
    )
    return snapshot, entries

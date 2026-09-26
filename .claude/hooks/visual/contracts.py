from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class HookEnvelope:
    schema_version: int
    runtime: str
    runtime_version: str
    event: str
    project_root: str
    profile_id: str
    session_id: str
    turn_id: str
    invocation_id: str
    user_message: str
    response_text: str
    response_sha256: str
    transcript_path: str
    changed_paths: tuple[str, ...]
    stop_hook_active: bool
    attempt: int
    capabilities: frozenset[str]
    valid_for_state: bool
    coding: bool = False
    # 2026-08-28：Stopしたターンの中に tool_use が1つでもあったか。
    # 既定 True＝「作業あり」として従来どおり検品証を要求する（fail-closed）。
    # False になるのは、転写の末尾を実際に読めて・セッションが一致し・tool_use ゼロを確認できた時だけ。
    turn_has_tool_use: bool = True


@dataclass(frozen=True)
class ExplanationPlan:
    audience: str
    depth: str
    components: tuple[str, ...]
    reason_codes: tuple[str, ...]
    provisional: bool
    should_continue: bool
    delivery: str
    publish_policy: str
    deprecated_aliases: tuple[str, ...] = ()


@dataclass(frozen=True)
class GlossarySnapshot:
    shared_source: str
    shared_path: str
    shared_sha256: str
    mirror_sha256: str
    project_sha256: str
    effective_sha256: str
    shared_count: int
    project_count: int
    effective_count: int
    project_overrides: tuple[str, ...]
    same_file_duplicates: tuple[str, ...]
    mirror_matches_home: bool


@dataclass(frozen=True)
class ArtifactReceipt:
    runtime: str
    project_root: str
    session_id: str
    turn_id: str
    path: str
    sha256: str
    bytes: int
    created_at: str
    gloss_check: str
    glossary_sha256: str
    glossary_source: str
    visual_smoke: str
    previewed: bool
    visibility: str
    required_components: tuple[str, ...] = ()
    present_components: tuple[str, ...] = ()
    missing_components: tuple[str, ...] = ()
    missing_decision_parts: tuple[str, ...] = ()
    unwrapped_identifiers: tuple[str, ...] = ()
    unknown_identifiers: tuple[str, ...] = ()
    missing_evidence_sources: tuple[str, ...] = ()
    inspection_errors: tuple[str, ...] = ()
    inspection_ok: bool = True
    visual_smoke_errors: tuple[str, ...] = ()


@dataclass(frozen=True)
class SubagentDigest:
    parent_turn_id: str
    child_session_id: str
    goal: str
    result: str
    evidence: tuple[str, ...]
    risk: str
    needs_human: str
    status: str
    duration_ms: int

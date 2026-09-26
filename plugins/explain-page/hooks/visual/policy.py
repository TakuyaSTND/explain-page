from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

from . import branding

DEFAULT_COMPONENTS = (
    "overview",
    "walkthrough",
    "examples",
    "evidence",
    "glossary",
    "details",
)
DEFAULT_MAX_TRANSCRIPT_BYTES = 2 * 1024 * 1024
DEFAULT_VISUAL_SMOKE_TIMEOUT_SECONDS = 12
DEFAULT_LOCAL_ARTIFACT_ROOT = "%TEMP%/" + branding.ARTIFACT_DIR_NAME
# 2026-09-25：名前は branding から取る。branding.LEGACY_* が None の配布
# （公開版）では、その名前を読まない・deprecated_aliases にも入れない。
# ⚠️None を os.environ にそのまま渡すと `in` も `.get` も TypeError で落ちる
# （素の dict なら落ちない＝env={} を渡す試験では見えなかった・2026-09-25 実測）。
# ∴下の各所で None を明示に外す。
LEGACY_ALIAS_NAMES = tuple(
    name
    for name in (
        branding.LEGACY_ENV_OFF,
        branding.LEGACY_ENV_MIN,
        branding.LEGACY_ENV_BLOCKS,
    )
    if name is not None
)


@dataclass(frozen=True)
class Policy:
    enabled: bool = True
    explain_mode: str = "auto"
    scope: str = "project"
    publish: str = "never"
    default_audience: str = "project_novice"
    default_depth: str = "deep"
    default_components: tuple[str, ...] = DEFAULT_COMPONENTS
    min_chars: int = 700
    min_blocks: int = 8
    state_ttl_seconds: int = 86400
    max_artifact_bytes: int = 2097152
    local_artifact_root: str = DEFAULT_LOCAL_ARTIFACT_ROOT
    max_transcript_bytes: int = DEFAULT_MAX_TRANSCRIPT_BYTES
    visual_smoke_timeout_seconds: int = DEFAULT_VISUAL_SMOKE_TIMEOUT_SECONDS
    deprecated_aliases: tuple[str, ...] = ()
    # 読みやすさ関門（使ってはいけない言い回し・否定側）＝off|shadow|enforce。
    # 新設はshadowから（.claude/readability-rules.md・2026-09-08）。
    readability: str = "shadow"


@dataclass(frozen=True)
class ExplicitControls:
    depth: str | None
    add_components: frozenset[str]
    remove_components: frozenset[str]


def parse_controls(text: str) -> ExplicitControls:
    choices: dict[str, bool] = {}
    for component, value in re.findall(
        r"\[(visual|decision|summary):(on|off)\]", text, flags=re.IGNORECASE
    ):
        choices[component.lower()] = value.lower() == "on"
    depths = re.findall(r"\[explain:(deep|guided|brief)\]", text, flags=re.IGNORECASE)
    depth = depths[-1].lower() if depths else None
    return ExplicitControls(
        depth=depth,
        add_components=frozenset(name for name, enabled in choices.items() if enabled),
        remove_components=frozenset(name for name, enabled in choices.items() if not enabled),
    )


def _bool_value(value: object, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "1", "yes", "on"}:
            return True
        if normalized in {"false", "0", "no", "off"}:
            return False
    return default


def _choice(value: object, allowed: set[str], default: str) -> str:
    normalized = value.strip().lower() if isinstance(value, str) else ""
    return normalized if normalized in allowed else default


def _positive_int(value: object, default: int) -> int:
    if isinstance(value, bool):
        return default
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return parsed if parsed > 0 else default


def _components(value: object) -> tuple[str, ...]:
    if not isinstance(value, (list, tuple)):
        return DEFAULT_COMPONENTS
    parsed = tuple(item for item in value if isinstance(item, str) and item.strip())
    return parsed or DEFAULT_COMPONENTS


def _env_positive_int(
    effective_env: Mapping[str, str], key: str | None, configured: object, default: int
) -> int:
    configured_value = _positive_int(configured, default)
    if key is None or key not in effective_env:
        return configured_value
    # A malformed legacy value must not erase a valid JSON value. If JSON is
    # malformed too, _positive_int has already returned the safe default.
    return _positive_int(effective_env.get(key), configured_value)


def load_policy(
    path: str | Path | None,
    env: Mapping[str, str] | None = None,
) -> Policy:
    values: dict[str, object] = {}
    if path is not None:
        policy_path = Path(path)
        if policy_path.is_file():
            try:
                loaded = json.loads(policy_path.read_text(encoding="utf-8"))
            except (OSError, UnicodeError, json.JSONDecodeError):
                loaded = {}
            if isinstance(loaded, dict):
                values = loaded
    effective_env = os.environ if env is None else env
    deprecated_aliases = tuple(
        name for name in LEGACY_ALIAS_NAMES if name in effective_env
    )

    # The new switch is authoritative even when it contains an invalid value.
    # In that case _choice safely falls back to auto; do not let the old off
    # alias unexpectedly win.
    if branding.ENV_MODE in effective_env:
        explain_mode = _choice(
            effective_env.get(branding.ENV_MODE),
            {"auto", "always", "off"},
            "auto",
        )
    elif branding.LEGACY_ENV_OFF is not None and _bool_value(
        effective_env.get(branding.LEGACY_ENV_OFF), False
    ):
        explain_mode = "off"
    else:
        explain_mode = _choice(
            values.get("explain_mode", "auto"),
            {"auto", "always", "off"},
            "auto",
        )

    default_components = _components(
        values.get("default_components", DEFAULT_COMPONENTS)
    )
    if explain_mode == "always" and "summary" not in default_components:
        default_components = (*default_components, "summary")

    return Policy(
        enabled=_bool_value(values.get("enabled", True), True) and explain_mode != "off",
        explain_mode=explain_mode,
        scope=_choice(values.get("scope", "project"), {"project"}, "project"),
        publish=_choice(
            values.get("publish", "never"), {"never", "ask", "always"}, "never"
        ),
        default_audience=_choice(
            values.get("default_audience", "project_novice"),
            {"project_novice"},
            "project_novice",
        ),
        default_depth=_choice(
            values.get("default_depth", "deep"),
            {"deep", "guided", "brief"},
            "deep",
        ),
        default_components=default_components,
        min_chars=_env_positive_int(
            effective_env, branding.LEGACY_ENV_MIN, values.get("min_chars", 700), 700
        ),
        min_blocks=_env_positive_int(
            effective_env, branding.LEGACY_ENV_BLOCKS, values.get("min_blocks", 8), 8
        ),
        state_ttl_seconds=_positive_int(
            values.get("state_ttl_seconds", 86400), 86400
        ),
        max_artifact_bytes=_positive_int(
            values.get("max_artifact_bytes", 2097152), 2097152
        ),
        local_artifact_root=(
            values["local_artifact_root"]
            if isinstance(values.get("local_artifact_root"), str)
            and str(values["local_artifact_root"]).strip()
            else DEFAULT_LOCAL_ARTIFACT_ROOT
        ),
        max_transcript_bytes=_positive_int(
            values.get("max_transcript_bytes", DEFAULT_MAX_TRANSCRIPT_BYTES),
            DEFAULT_MAX_TRANSCRIPT_BYTES,
        ),
        visual_smoke_timeout_seconds=_positive_int(
            values.get(
                "visual_smoke_timeout_seconds", DEFAULT_VISUAL_SMOKE_TIMEOUT_SECONDS
            ),
            DEFAULT_VISUAL_SMOKE_TIMEOUT_SECONDS,
        ),
        deprecated_aliases=deprecated_aliases,
        readability=_choice(
            values.get("readability", "shadow"),
            {"off", "shadow", "enforce"},
            "shadow",
        ),
    )

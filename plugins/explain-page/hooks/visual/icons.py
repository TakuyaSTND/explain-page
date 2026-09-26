"""Deterministic line-art icon symbols for the visual renderer.

Policy-analysis pages need recurring figures (person, household, building,
government office, ...) drawn as simple line-art glyphs instead of emoji.
This module is the single source of those glyphs: every icon is an
original, hand-drawn 24x24 outline (no vendor icon-set path data is
copied), stroke-only (``fill="none"``), stroke width 2, referenced by a
short ASCII name.

Two entry points cover the two ways ``render_components.py`` needs an
icon:

``icon_svg(name, size=24, tone="ink")``
    A standalone ``<svg>...</svg>`` string sized to ``size`` px, tinted by
    mapping ``tone`` to one of the renderer's fixed CSS color variables
    (``ink`` / ``accent`` / ``pass`` / ``warn`` / ``fail``). Returns
    ``None`` for an unknown name instead of raising.

``icon_symbol_defs(names)``
    A single ``<defs>...</defs>`` block holding one ``<symbol id="ic-...">``
    per requested (known) name, for a diagram to place once and then draw
    many ``<use href="#ic-...">`` references against.

Every glyph body is built only from ``<path>`` / ``<line>`` / ``<circle>``
/ ``<rect>`` primitives -- no ``<script>``, no external URLs, no
``url()`` references, no ``foreignObject``, and no ``xmlns`` declaration
(an inline SVG in HTML5 does not need one; writing the w3.org namespace
URL here has previously been misread by the receipt inspector as an
external reference). This module never raises: unknown names and odd
``size``/``tone`` inputs degrade to ``None`` / a default rather than an
exception.
"""

from __future__ import annotations

from html import escape
from typing import Dict, Iterable, Tuple

__all__ = ["ICON_NAMES", "icon_svg", "icon_symbol_defs"]

_VIEWBOX = "0 0 24 24"

# tone -> the renderer's fixed CSS custom property (render_components.py
# defines these under :root / [data-theme] for both light and dark).
_TONE_VARS: Dict[str, str] = {
    "ink": "var(--ink)",
    "accent": "var(--accent)",
    "pass": "var(--pass)",
    "warn": "var(--warn)",
    "fail": "var(--fail)",
}
_DEFAULT_TONE = "ink"
_DEFAULT_SIZE = 24

# Each body is inner markup only (no wrapping <svg>/<symbol>, no style or
# stroke attributes -- those are applied once at the <svg>/<symbol> root
# and inherited by every child shape, per SVG's normal presentation-
# attribute inheritance). Geometry is plain, original, and deliberately
# simple so it reads at small sizes.
_ICON_BODY: Dict[str, str] = {
    "person": (
        '<circle cx="12" cy="7" r="3.4"/>'
        '<path d="M5 21c0-4.4 3.1-7.6 7-7.6s7 3.2 7 7.6"/>'
    ),
    "household": (
        '<path d="M4 11 12 4l8 7"/>'
        '<path d="M6 10v9h12v-9"/>'
        '<path d="M10 19v-5h4v5"/>'
    ),
    "building": (
        '<rect x="5" y="3" width="14" height="18" rx="1"/>'
        '<rect x="8" y="6" width="2" height="2"/>'
        '<rect x="14" y="6" width="2" height="2"/>'
        '<rect x="8" y="11" width="2" height="2"/>'
        '<rect x="14" y="11" width="2" height="2"/>'
        '<rect x="8" y="16" width="2" height="2"/>'
        '<rect x="14" y="16" width="2" height="2"/>'
    ),
    "government": (
        '<path d="M4 9 12 4l8 5"/>'
        '<line x1="4" y1="9" x2="20" y2="9"/>'
        '<line x1="6" y1="9" x2="6" y2="18"/>'
        '<line x1="10" y1="9" x2="10" y2="18"/>'
        '<line x1="14" y1="9" x2="14" y2="18"/>'
        '<line x1="18" y1="9" x2="18" y2="18"/>'
        '<line x1="4" y1="20" x2="20" y2="20"/>'
    ),
    "school": (
        '<path d="M2 9l10-4 10 4-10 4-10-4z"/>'
        '<path d="M6 11v5c0 1.5 2.5 3 6 3s6-1.5 6-3v-5"/>'
        '<line x1="22" y1="9" x2="22" y2="15"/>'
    ),
    "hospital": (
        '<rect x="4" y="4" width="16" height="16" rx="1"/>'
        '<line x1="12" y1="8" x2="12" y2="16"/>'
        '<line x1="8" y1="12" x2="16" y2="12"/>'
    ),
    "company": (
        '<rect x="3" y="8" width="18" height="12" rx="1"/>'
        '<path d="M8 8V6c0-1.1.9-2 2-2h4c1.1 0 2 .9 2 2v2"/>'
        '<line x1="3" y1="13" x2="21" y2="13"/>'
    ),
    "money": (
        '<circle cx="12" cy="12" r="8.4"/>'
        '<path d="M9 6.5l3 5 3-5"/>'
        '<line x1="12" y1="11" x2="12" y2="17.5"/>'
        '<line x1="9" y1="13" x2="15" y2="13"/>'
        '<line x1="9" y1="16" x2="15" y2="16"/>'
    ),
    "document": (
        '<path d="M6 3h9l5 5v13H6z"/>'
        '<path d="M15 3v5h5"/>'
        '<line x1="9" y1="12" x2="17" y2="12"/>'
        '<line x1="9" y1="15" x2="17" y2="15"/>'
        '<line x1="9" y1="18" x2="14" y2="18"/>'
    ),
    "scales": (
        '<line x1="12" y1="3" x2="12" y2="21"/>'
        '<line x1="5" y1="6" x2="19" y2="6"/>'
        '<path d="M5 6l-3 7c0 2 1.8 3 3 3s3-1 3-3z"/>'
        '<path d="M19 6l-3 7c0 2 1.8 3 3 3s3-1 3-3z"/>'
        '<line x1="8" y1="21" x2="16" y2="21"/>'
    ),
    "arrow": (
        '<line x1="4" y1="12" x2="18" y2="12"/>'
        '<polyline points="13 6 19 12 13 18"/>'
    ),
    "clock": (
        '<circle cx="12" cy="12" r="9"/>'
        '<line x1="12" y1="12" x2="12" y2="7"/>'
        '<line x1="12" y1="12" x2="16" y2="14"/>'
    ),
    "calendar": (
        '<rect x="4" y="5" width="16" height="15" rx="1"/>'
        '<line x1="4" y1="10" x2="20" y2="10"/>'
        '<line x1="8" y1="3" x2="8" y2="7"/>'
        '<line x1="16" y1="3" x2="16" y2="7"/>'
    ),
    "warning": (
        '<path d="M12 3l10 18H2z"/>'
        '<line x1="12" y1="10" x2="12" y2="14"/>'
        '<line x1="12" y1="17" x2="12" y2="17.02"/>'
    ),
    "check": ('<polyline points="4 13 9 18 20 6"/>'),
    "prohibit": (
        '<circle cx="12" cy="12" r="9"/>'
        '<line x1="6" y1="18" x2="18" y2="6"/>'
    ),
    "map_pin": (
        '<path d="M12 21s7-7.5 7-12a7 7 0 0 0-14 0c0 4.5 7 12 7 12z"/>'
        '<circle cx="12" cy="9" r="2.4"/>'
    ),
    "graph": (
        '<line x1="4" y1="20" x2="20" y2="20"/>'
        '<line x1="7" y1="20" x2="7" y2="12"/>'
        '<line x1="12" y1="20" x2="12" y2="7"/>'
        '<line x1="17" y1="20" x2="17" y2="15"/>'
    ),
    "gear": (
        '<circle cx="12" cy="12" r="3.5"/>'
        '<circle cx="12" cy="12" r="7.5"/>'
        '<line x1="19" y1="12" x2="21" y2="12"/>'
        '<line x1="16.95" y1="7.05" x2="18.36" y2="5.64"/>'
        '<line x1="12" y1="5" x2="12" y2="3"/>'
        '<line x1="7.05" y1="7.05" x2="5.64" y2="5.64"/>'
        '<line x1="5" y1="12" x2="3" y2="12"/>'
        '<line x1="7.05" y1="16.95" x2="5.64" y2="18.36"/>'
        '<line x1="12" y1="19" x2="12" y2="21"/>'
        '<line x1="16.95" y1="16.95" x2="18.36" y2="18.36"/>'
    ),
    "chain": (
        '<rect x="2" y="9" width="9" height="6" rx="3" '
        'transform="rotate(-20 6.5 12)"/>'
        '<rect x="13" y="9" width="9" height="6" rx="3" '
        'transform="rotate(-20 17.5 12)"/>'
    ),
    "key": (
        '<circle cx="7" cy="7" r="4"/>'
        '<line x1="10" y1="10" x2="20" y2="20"/>'
        '<line x1="15" y1="15" x2="17" y2="13"/>'
        '<line x1="17" y1="17" x2="19" y2="15"/>'
    ),
    "eye": (
        '<path d="M2 12s4-7 10-7 10 7 10 7-4 7-10 7-10-7-10-7z"/>'
        '<circle cx="12" cy="12" r="3"/>'
    ),
    "magnifier": (
        '<circle cx="10" cy="10" r="6"/>'
        '<line x1="15" y1="15" x2="21" y2="21"/>'
    ),
    "bulb": (
        '<path d="M12 3a7 7 0 0 0-4 12.7c.6.5 1 1.3 1 2.3h6c0-1 .4-1.8 '
        '1-2.3A7 7 0 0 0 12 3z"/>'
        '<line x1="9" y1="18" x2="15" y2="18"/>'
        '<line x1="10" y1="21" x2="14" y2="21"/>'
    ),
    "flag": (
        '<line x1="5" y1="3" x2="5" y2="21"/>'
        '<path d="M5 4h13l-4 4 4 4H5z"/>'
    ),
    "box": (
        '<path d="M3 8l9-5 9 5-9 5-9-5z"/>'
        '<path d="M3 8v9l9 5 9-5V8"/>'
        '<line x1="12" y1="13" x2="12" y2="22"/>'
    ),
    "truck": (
        '<rect x="2" y="9" width="12" height="8"/>'
        '<path d="M14 12h4l3 3v2h-7z"/>'
        '<circle cx="6" cy="19" r="1.6"/>'
        '<circle cx="17" cy="19" r="1.6"/>'
    ),
    "bridge": (
        '<line x1="2" y1="15" x2="22" y2="15"/>'
        '<path d="M3 15c3-8 15-8 18 0"/>'
        '<line x1="7" y1="15" x2="7" y2="10"/>'
        '<line x1="12" y1="15" x2="12" y2="8"/>'
        '<line x1="17" y1="15" x2="17" y2="10"/>'
        '<line x1="6" y1="15" x2="6" y2="19"/>'
        '<line x1="18" y1="15" x2="18" y2="19"/>'
    ),
    "tree": (
        '<line x1="12" y1="14" x2="12" y2="21"/>'
        '<path d="M12 3c-3 0-5 2-5 4.5 0 1 .4 1.8 1 2.4-1.6.4-2.8 '
        '1.8-2.8 3.6 0 2 1.7 3.5 3.8 3.5h6c2.1 0 3.8-1.5 3.8-3.5 '
        '0-1.8-1.2-3.2-2.8-3.6.6-.6 1-1.4 1-2.4C17 5 15 3 12 3z"/>'
    ),
    "droplet": ('<path d="M12 3s7 8 7 13a7 7 0 0 1-14 0c0-5 7-13 7-13z"/>'),
    "flame": (
        '<path d="M12 3c4 5 6 9 6 12a6 6 0 0 1-12 0c0-3 2-7 6-12z"/>'
        '<path d="M12 10c1 2 2 3.2 2 5a2 2 0 0 1-4 0c0-1.2.6-2.1 1-3"/>'
    ),
}

ICON_NAMES: Tuple[str, ...] = tuple(sorted(_ICON_BODY))


def _stringify(value: object) -> str:
    if isinstance(value, str):
        return value
    try:
        return str(value)
    except Exception:
        return ""


def _coerce_size(size: object) -> int:
    try:
        size_int = int(size)  # rejects non-numeric without raising outward
    except (TypeError, ValueError):
        return _DEFAULT_SIZE
    if size_int <= 0:
        return _DEFAULT_SIZE
    return size_int


def icon_svg(name: str, size: int = 24, tone: str = "ink") -> str | None:
    """Render one icon as a standalone ``<svg>...</svg>`` string.

    Returns ``None`` for an unknown ``name`` instead of raising. ``size``
    sets both ``width`` and ``height`` (falls back to 24 for anything
    non-positive or non-numeric). ``tone`` maps to a fixed CSS color
    variable (``ink``/``accent``/``pass``/``warn``/``fail``); an unknown
    tone falls back to ``ink``. Never raises.
    """
    if not isinstance(name, str):
        return None
    body = _ICON_BODY.get(name)
    if body is None:
        return None

    size_px = _coerce_size(size)
    color_var = _TONE_VARS.get(_stringify(tone).strip().lower(), _TONE_VARS[_DEFAULT_TONE])
    label = escape(name, quote=True)

    return (
        '<svg width="%d" height="%d" viewBox="%s" fill="none" '
        'stroke="currentColor" stroke-width="2" stroke-linecap="round" '
        'stroke-linejoin="round" style="color:%s" role="img" '
        'aria-label="%s">%s</svg>'
    ) % (size_px, size_px, _VIEWBOX, color_var, label, body)


def icon_symbol_defs(names: Iterable[str]) -> str:
    """Build one ``<defs>`` block holding a ``<symbol>`` per known name.

    Unknown names and duplicates are dropped silently (order-preserving,
    first occurrence wins). An empty/all-unknown ``names`` yields an
    empty string rather than an empty ``<defs></defs>`` pair, so callers
    can safely concatenate the result unconditionally. Never raises.
    """
    ordered: list[str] = []
    seen: set[str] = set()
    try:
        candidates = list(names)
    except TypeError:
        candidates = []
    for raw in candidates:
        if not isinstance(raw, str):
            continue
        if raw not in _ICON_BODY or raw in seen:
            continue
        seen.add(raw)
        ordered.append(raw)

    if not ordered:
        return ""

    parts = ["<defs>"]
    for name in ordered:
        symbol_id = "ic-%s" % escape(name, quote=True)
        parts.append(
            '<symbol id="%s" viewBox="%s" fill="none" stroke="currentColor" '
            'stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
            '%s</symbol>' % (symbol_id, _VIEWBOX, _ICON_BODY[name])
        )
    parts.append("</defs>")
    return "".join(parts)

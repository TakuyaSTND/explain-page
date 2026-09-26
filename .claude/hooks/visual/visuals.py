"""Deterministic "readability" component library for the visual renderer.

Every public function here is a pure function: same input -> same output
string, no randomness, no clock reads, no external libraries (stdlib only),
and no exception ever escapes to the caller (malformed input degrades to a
minimal, still-valid placeholder instead of raising). ``render_components.py``
(owned separately) is the only caller; it wires these strings into the page.

Contract summary (see the calling skill's task note for the full spec):

    timeline_svg(spec)            -> "<svg class=\"tl\" ...>"
    quadrant_svg(spec)             -> "<svg class=\"quad\" ...>"
    venn_svg(spec)                 -> "<svg class=\"venn\" ...>"
    flow_svg(spec)                 -> "<svg class=\"flow\" ...>"
    callout_badge_svg(n, tone)     -> "<svg class=\"badge\" ...>"
    callout_legend_html(items)     -> "<ul class=\"callout-legend\">...</ul>"
    compare_html(before, after, labels=("前","後")) -> "<div class=\"compare\">...</div>"
    score_grid_svg(spec)          -> "<svg class=\"score\" ...>"
    heat_color(value, lo, hi)      -> "color-mix(in srgb, var(--accent) NN%, transparent)"
    sparkline_svg(values, ...)     -> "<svg class=\"spark\" ...>"

Every piece of caller-supplied text is passed through ``html.escape(...,
quote=True)`` before being embedded. Colors are drawn only from the fixed
CSS-variable palette the renderer already exposes (``--accent`` /
``--accent-2`` / ``--accent-soft`` / ``--pass`` / ``--pass-soft`` /
``--warn`` / ``--warn-soft`` / ``--fail`` / ``--fail-soft`` / ``--ink`` /
``--ink-2`` / ``--ink-3`` / ``--rule`` / ``--rule-soft`` / ``--surface`` /
``--surface-2``). No ``xmlns`` declaration, no external URL, no ``url(...)``
reference, and no ``<script>`` tag is ever emitted -- ``compare_html`` swaps
its two panels with a plain ``:checked`` sibling-selector CSS trick, not
JavaScript.
"""

from __future__ import annotations

import hashlib
import math
from html import escape as _html_escape
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

__all__ = [
    "timeline_svg",
    "quadrant_svg",
    "venn_svg",
    "flow_svg",
    "callout_badge_svg",
    "callout_legend_html",
    "compare_html",
    "score_grid_svg",
    "heat_color",
    "sparkline_svg",
]

# ---------------------------------------------------------------------------
# Shared palette / small helpers
# ---------------------------------------------------------------------------

_TONE_COLOR: Dict[str, str] = {
    "good": "var(--pass)",
    "warn": "var(--warn)",
    "bad": "var(--fail)",
    "acc": "var(--accent)",
}
_TONE_SOFT: Dict[str, str] = {
    "good": "var(--pass-soft)",
    "warn": "var(--warn-soft)",
    "bad": "var(--fail-soft)",
    "acc": "var(--accent-soft)",
}
_DEFAULT_TONE = "acc"


def _tone_color(tone: Any) -> str:
    if tone in _TONE_COLOR:
        return _TONE_COLOR[tone]
    return _TONE_COLOR[_DEFAULT_TONE]


def _tone_soft(tone: Any) -> str:
    if tone in _TONE_SOFT:
        return _TONE_SOFT[tone]
    return _TONE_SOFT[_DEFAULT_TONE]


def _esc(value: Any) -> str:
    return _html_escape(str(value), quote=True)


def _clip(value: float, lo: float, hi: float) -> float:
    if value < lo:
        return lo
    if value > hi:
        return hi
    return value


def _clip_int(value: int, lo: int, hi: int) -> int:
    if value < lo:
        return lo
    if value > hi:
        return hi
    return value


def _is_number(value: Any) -> bool:
    if isinstance(value, bool):
        return False
    if not isinstance(value, (int, float)):
        return False
    return math.isfinite(float(value))


def _char_w(ch: str, font_px: float) -> float:
    # 日本語1字は概ね全角なので約0.95em、英数は約0.55em という粗い見積もり。
    return font_px * (0.95 if ord(ch) > 127 else 0.55)


def _wrap(text: str, max_width: float, font_px: float, max_lines: int = 3) -> List[str]:
    """Greedy character-wrap text to ``max_width`` px at ``font_px``.

    Returns at most ``max_lines`` lines; the last line is ellipsized with
    "…" when the text does not fit. Never raises.
    """
    if not text:
        return []
    if max_width <= 0 or font_px <= 0 or max_lines <= 0:
        return []
    lines: List[str] = []
    cur = ""
    cur_w = 0.0
    for ch in text:
        w = _char_w(ch, font_px)
        if cur and cur_w + w > max_width:
            lines.append(cur)
            cur = ch
            cur_w = w
        else:
            cur += ch
            cur_w += w
        if len(lines) >= max_lines:
            break
    if cur and len(lines) < max_lines:
        lines.append(cur)
    if len(lines) > max_lines:
        lines = lines[:max_lines]
    # If input still has un-consumed text past what we kept, mark truncation.
    consumed = sum(len(ln) for ln in lines)
    if consumed < len(text) or len(lines) == max_lines and cur and lines[-1] != cur:
        last = lines[-1] if lines else ""
        if last:
            lines[-1] = (last[:-1] if len(last) > 1 else last) + "…"
        else:
            lines[-1] = "…"
    return lines


def _deconflict(
    points: Sequence[Tuple[float, float]],
    min_dist: float,
    bounds: Optional[Tuple[float, float, float, float]] = None,
) -> List[Tuple[float, float]]:
    """Nudge duplicate/near-duplicate points apart, deterministically.

    Tries a fixed, expanding ring of offsets (in a stable order) for each
    point in turn until it clears every already-placed point by
    ``min_dist``; falls back to the original point if none clears. Optional
    ``bounds`` = (x0, x1, y0, y1) clamps the final position onto the canvas.
    """
    offsets: Tuple[Tuple[float, float], ...] = (
        (0.0, 0.0),
        (28.0, 0.0),
        (-28.0, 0.0),
        (0.0, 24.0),
        (0.0, -24.0),
        (28.0, 24.0),
        (-28.0, 24.0),
        (28.0, -24.0),
        (-28.0, -24.0),
        (56.0, 0.0),
        (-56.0, 0.0),
        (0.0, 48.0),
        (0.0, -48.0),
        (56.0, 24.0),
        (-56.0, -24.0),
    )
    placed: List[Tuple[float, float]] = []
    out: List[Tuple[float, float]] = []
    for (x, y) in points:
        chosen = None
        for dx, dy in offsets:
            cx, cy = x + dx, y + dy
            ok = True
            for px, py in placed:
                if (cx - px) ** 2 + (cy - py) ** 2 < min_dist * min_dist:
                    ok = False
                    break
            if ok:
                chosen = (cx, cy)
                break
        if chosen is None:
            chosen = (x, y)
        if bounds is not None:
            bx0, bx1, by0, by1 = bounds
            chosen = (_clip(chosen[0], bx0, bx1), _clip(chosen[1], by0, by1))
        placed.append(chosen)
        out.append(chosen)
    return out


def _lines_block(
    content: Sequence[Tuple[str, int, bool, str]],
    x: float,
    y0: float,
    line_h: float,
    anchor: str = "middle",
) -> List[str]:
    """Render a stack of (text, font_px, bold, fill) tuples as <text> lines."""
    parts: List[str] = []
    for i, (txt, font_px, bold, fill) in enumerate(content):
        if not txt:
            continue
        w_attr = ' font-weight="700"' if bold else ""
        parts.append(
            '<text x="%.1f" y="%.1f" text-anchor="%s" fill="%s" font-size="%d"%s>%s</text>'
            % (x, y0 + i * line_h, anchor, fill, font_px, w_attr, _esc(txt))
        )
    return parts


# ---------------------------------------------------------------------------
# 1. timeline_svg
# ---------------------------------------------------------------------------

def _normalize_events(raw: Any) -> List[Dict[str, str]]:
    events: List[Dict[str, str]] = []
    if not isinstance(raw, list):
        return events
    for e in raw:
        if not isinstance(e, Mapping):
            continue
        when = str(e.get("when", "") or "")
        label = str(e.get("label", "") or "")
        text_val = e.get("text")
        text = str(text_val) if text_val is not None else ""
        tone = e.get("tone") if e.get("tone") in _TONE_COLOR else None
        events.append({"when": when, "label": label, "text": text, "tone": tone})
    return events


def _timeline_horizontal(title: str, events: List[Dict[str, str]], caption: str) -> str:
    width = 720
    margin_x = 80.0
    axis_y = 190.0
    height = 360 if caption else 330
    n = len(events)
    slot_w = (width - 2 * margin_x) / (n - 1) if n > 1 else 0.0
    label_w = min(170.0, max(90.0, slot_w * 0.85)) if n > 1 else 260.0
    line_h = 15.0

    parts: List[str] = []
    if title:
        parts.append(
            '<text x="%.1f" y="26" text-anchor="middle" fill="var(--ink)" '
            'font-size="15" font-weight="600">%s</text>' % (width / 2.0, _esc(title))
        )
    parts.append(
        '<line x1="%.1f" y1="%.1f" x2="%.1f" y2="%.1f" stroke="var(--rule)" '
        'stroke-width="2"></line>' % (margin_x, axis_y, width - margin_x, axis_y)
    )

    for i, ev in enumerate(events):
        x = margin_x + i * slot_w if n > 1 else width / 2.0
        color = _tone_color(ev["tone"])
        up = (i % 2 == 0)

        content: List[Tuple[str, int, bool, str]] = []
        if ev["when"]:
            content.append((ev["when"], 12, True, "var(--accent-2)"))
        for ln in _wrap(ev["label"], label_w, 13, max_lines=2):
            content.append((ln, 13, False, "var(--ink)"))
        if ev["text"]:
            for ln in _wrap(ev["text"], label_w, 12, max_lines=1):
                content.append((ln, 12, False, "var(--ink-3)"))
        if not content:
            content = [("", 13, False, "var(--ink)")]
        total = len(content)

        parts.append(
            '<circle cx="%.1f" cy="%.1f" r="5" fill="%s" stroke="var(--surface)" '
            'stroke-width="1.2"></circle>' % (x, axis_y, color)
        )
        if up:
            parts.append(
                '<line x1="%.1f" y1="%.1f" x2="%.1f" y2="%.1f" stroke="var(--rule-soft)">'
                "</line>" % (x, axis_y - 5, x, axis_y - 16)
            )
            y0 = axis_y - 16 - (total - 1) * line_h
        else:
            parts.append(
                '<line x1="%.1f" y1="%.1f" x2="%.1f" y2="%.1f" stroke="var(--rule-soft)">'
                "</line>" % (x, axis_y + 5, x, axis_y + 16)
            )
            y0 = axis_y + 16 + line_h
        parts.extend(_lines_block(content, x, y0, line_h, anchor="middle"))

    if caption:
        cap_lines = _wrap(caption, width - 2 * margin_x, 12, max_lines=2)
        base_y = height - 14 - (len(cap_lines) - 1) * 14
        for li, ln in enumerate(cap_lines):
            parts.append(
                '<text x="%.1f" y="%.1f" text-anchor="middle" fill="var(--ink-3)" '
                'font-size="12">%s</text>' % (width / 2.0, base_y + li * 14, _esc(ln))
            )

    aria = _esc(title) if title else "timeline"
    return '<svg class="tl" viewBox="0 0 %d %d" role="img" aria-label="%s">%s</svg>' % (
        width,
        height,
        aria,
        "".join(parts),
    )


def _timeline_vertical(title: str, events: List[Dict[str, str]], caption: str) -> str:
    width = 720
    axis_x = 110.0
    text_x = 150.0
    row_h = 54.0
    top = 50.0
    n = len(events)
    content_max_w = width - text_x - 40
    line_h = 15.0
    height = top + (n - 1) * row_h + 40 + (30 if caption else 0)

    parts: List[str] = []
    if title:
        parts.append(
            '<text x="24" y="26" fill="var(--ink)" font-size="15" font-weight="600">%s</text>'
            % _esc(title)
        )
    axis_top = top
    axis_bottom = top + (n - 1) * row_h
    parts.append(
        '<line x1="%.1f" y1="%.1f" x2="%.1f" y2="%.1f" stroke="var(--rule)" '
        'stroke-width="2"></line>' % (axis_x, axis_top, axis_x, axis_bottom)
    )

    for i, ev in enumerate(events):
        y = top + i * row_h
        color = _tone_color(ev["tone"])
        parts.append(
            '<circle cx="%.1f" cy="%.1f" r="5" fill="%s" stroke="var(--surface)" '
            'stroke-width="1.2"></circle>' % (axis_x, y, color)
        )
        parts.append(
            '<line x1="%.1f" y1="%.1f" x2="%.1f" y2="%.1f" stroke="var(--rule-soft)">'
            "</line>" % (axis_x + 6, y, text_x - 6, y)
        )
        content: List[Tuple[str, int, bool, str]] = []
        if ev["when"]:
            content.append((ev["when"], 12, True, "var(--accent-2)"))
        for ln in _wrap(ev["label"], content_max_w, 13, max_lines=1):
            content.append((ln, 13, False, "var(--ink)"))
        if ev["text"]:
            for ln in _wrap(ev["text"], content_max_w, 12, max_lines=1):
                content.append((ln, 12, False, "var(--ink-3)"))
        if not content:
            content = [("", 13, False, "var(--ink)")]
        total = len(content)
        y0 = y + 4 - ((total - 1) * line_h) / 2.0
        parts.extend(_lines_block(content, text_x, y0, line_h, anchor="start"))

    if caption:
        cap_lines = _wrap(caption, width - 48, 12, max_lines=2)
        base_y = height - 14 - (len(cap_lines) - 1) * 14
        for li, ln in enumerate(cap_lines):
            parts.append(
                '<text x="24" y="%.1f" fill="var(--ink-3)" font-size="12">%s</text>'
                % (base_y + li * 14, _esc(ln))
            )

    aria = _esc(title) if title else "timeline"
    return '<svg class="tl" viewBox="0 0 %d %.1f" role="img" aria-label="%s">%s</svg>' % (
        width,
        height,
        aria,
        "".join(parts),
    )


def timeline_svg(spec: Any) -> str:
    try:
        if not isinstance(spec, Mapping):
            spec = {}
        title = str(spec.get("title", "") or "")
        caption = str(spec.get("caption", "") or "")
        events = _normalize_events(spec.get("events"))
        if not events:
            return (
                '<svg class="tl" viewBox="0 0 720 120" role="img" aria-label="%s">'
                '<text x="480" y="60" text-anchor="middle" fill="var(--ink-2)" '
                'font-size="13">%s</text></svg>'
            ) % (_esc(title) if title else "timeline", _esc("データなし"))
        if len(events) <= 7:
            return _timeline_horizontal(title, events, caption)
        return _timeline_vertical(title, events, caption)
    except Exception:
        return '<svg class="tl" viewBox="0 0 720 120" role="img" aria-label="timeline"></svg>'


# ---------------------------------------------------------------------------
# 2. quadrant_svg
# ---------------------------------------------------------------------------

def quadrant_svg(spec: Any) -> str:
    width, height = 560, 560
    try:
        if not isinstance(spec, Mapping):
            spec = {}
        x_ticks = spec.get("x") if isinstance(spec.get("x"), list) else []
        y_ticks = spec.get("y") if isinstance(spec.get("y"), list) else []
        x_label = str(spec.get("x_label", "") or "")
        y_label = str(spec.get("y_label", "") or "")
        xt0 = str(x_ticks[0]) if len(x_ticks) > 0 else "低"
        xt1 = str(x_ticks[1]) if len(x_ticks) > 1 else "高"
        yt0 = str(y_ticks[0]) if len(y_ticks) > 0 else "低"
        yt1 = str(y_ticks[1]) if len(y_ticks) > 1 else "高"

        items: List[Dict[str, Any]] = []
        raw_items = spec.get("items")
        if isinstance(raw_items, list):
            for it in raw_items:
                if not isinstance(it, Mapping):
                    continue
                ix_raw = it.get("x", 0.5)
                iy_raw = it.get("y", 0.5)
                if not (_is_number(ix_raw) and _is_number(iy_raw)):
                    continue
                ix = _clip(float(ix_raw), 0.0, 1.0)
                iy = _clip(float(iy_raw), 0.0, 1.0)
                label = str(it.get("label", "") or "")
                tone = it.get("tone") if it.get("tone") in _TONE_COLOR else None
                items.append({"x": ix, "y": iy, "label": label, "tone": tone})

        plot_l, plot_r = 90.0, 520.0
        plot_t, plot_b = 60.0, 470.0
        plot_w = plot_r - plot_l
        plot_h = plot_b - plot_t
        mid_x = (plot_l + plot_r) / 2.0
        mid_y = (plot_t + plot_b) / 2.0

        parts: List[str] = [
            '<rect x="%.1f" y="%.1f" width="%.1f" height="%.1f" fill="none" '
            'stroke="var(--rule)"></rect>' % (plot_l, plot_t, plot_w, plot_h),
            '<line x1="%.1f" y1="%.1f" x2="%.1f" y2="%.1f" stroke="var(--rule-soft)">'
            "</line>" % (mid_x, plot_t, mid_x, plot_b),
            '<line x1="%.1f" y1="%.1f" x2="%.1f" y2="%.1f" stroke="var(--rule-soft)">'
            "</line>" % (plot_l, mid_y, plot_r, mid_y),
            '<text x="%.1f" y="%.1f" text-anchor="start" fill="var(--ink-2)" '
            'font-size="12">%s</text>' % (plot_l, plot_b + 20, _esc(xt0)),
            '<text x="%.1f" y="%.1f" text-anchor="end" fill="var(--ink-2)" '
            'font-size="12">%s</text>' % (plot_r, plot_b + 20, _esc(xt1)),
            '<text x="%.1f" y="%.1f" text-anchor="end" fill="var(--ink-2)" '
            'font-size="12">%s</text>' % (plot_l - 8, plot_t + 8, _esc(yt1)),
            '<text x="%.1f" y="%.1f" text-anchor="end" fill="var(--ink-2)" '
            'font-size="12">%s</text>' % (plot_l - 8, plot_b, _esc(yt0)),
        ]
        if x_label:
            parts.append(
                '<text x="%.1f" y="%.1f" text-anchor="middle" fill="var(--ink)" '
                'font-size="13" font-weight="600">%s</text>' % (mid_x, height - 14, _esc(x_label))
            )
        if y_label:
            parts.append(
                '<text x="16" y="%.1f" text-anchor="middle" fill="var(--ink)" font-size="13" '
                'font-weight="600" transform="rotate(-90 16 %.1f)">%s</text>'
                % (mid_y, mid_y, _esc(y_label))
            )

        raw_points = [
            (plot_l + it["x"] * plot_w, plot_b - it["y"] * plot_h) for it in items
        ]
        bounds = (plot_l + 8, plot_r - 8, plot_t + 8, plot_b - 8)
        placed = _deconflict(raw_points, min_dist=26, bounds=bounds)

        # Dots that started at (near-)identical coordinates end up only
        # ``min_dist``=26px apart, which is far narrower than a label (up to
        # 140px wide). Deconflicting the dots alone is not enough to keep
        # their labels legible, so label boxes get their own pass: each new
        # label is nudged vertically (by whole line-heights) until it clears
        # every previously-placed label's bounding box.
        label_rects: List[Tuple[float, float, float, float]] = []
        label_dy_options = (0.0, 15.0, -15.0, 30.0, -30.0, 45.0, -45.0, 60.0, -60.0)

        for it, (cx, cy) in zip(items, placed):
            color = _tone_color(it["tone"]) if it["tone"] else "var(--accent)"
            parts.append(
                '<circle cx="%.1f" cy="%.1f" r="5" fill="%s" stroke="var(--surface)" '
                'stroke-width="1.2"></circle>' % (cx, cy, color)
            )
            label_lines = _wrap(it["label"], 140, 12, max_lines=2)
            if not label_lines:
                continue
            near_right_edge = cx > plot_r - 150
            anchor = "end" if near_right_edge else "start"
            tx = cx - 9 if near_right_edge else cx + 9
            line_w = max((sum(_char_w(ch, 12) for ch in ln) for ln in label_lines), default=0.0)
            lx0, lx1 = (tx - line_w, tx) if anchor == "end" else (tx, tx + line_w)
            base_ly0 = cy - ((len(label_lines) - 1) * 13) / 2.0 + 4

            chosen_ly0 = base_ly0
            for dy in label_dy_options:
                cand_ly0 = base_ly0 + dy
                top = cand_ly0 - 10.0
                bottom = cand_ly0 + (len(label_lines) - 1) * 13 + 4.0
                if all(
                    not (lx0 < rx1 and lx1 > rx0 and top < ry1 and bottom > ry0)
                    for (rx0, rx1, ry0, ry1) in label_rects
                ):
                    chosen_ly0 = cand_ly0
                    break
            top = chosen_ly0 - 10.0
            bottom = chosen_ly0 + (len(label_lines) - 1) * 13 + 4.0
            label_rects.append((lx0, lx1, top, bottom))

            for li, ln in enumerate(label_lines):
                parts.append(
                    '<text x="%.1f" y="%.1f" text-anchor="%s" fill="var(--ink)" '
                    'font-size="12">%s</text>' % (tx, chosen_ly0 + li * 13, anchor, _esc(ln))
                )

        aria = _esc(x_label) if x_label else "quadrant"
        return '<svg class="quad" viewBox="0 0 %d %d" role="img" aria-label="%s">%s</svg>' % (
            width,
            height,
            aria,
            "".join(parts),
        )
    except Exception:
        return '<svg class="quad" viewBox="0 0 %d %d" role="img" aria-label="quadrant"></svg>' % (
            width,
            height,
        )


# ---------------------------------------------------------------------------
# 3. venn_svg
# ---------------------------------------------------------------------------

_SET_COLORS = ("var(--accent)", "var(--pass)", "var(--warn)")
_SET_SOFT = ("var(--accent-soft)", "var(--pass-soft)", "var(--warn-soft)")


def venn_svg(spec: Any) -> str:
    width, height = 640, 480
    try:
        if not isinstance(spec, Mapping):
            spec = {}
        sets: List[Dict[str, Any]] = []
        raw_sets = spec.get("sets")
        if isinstance(raw_sets, list):
            for s in raw_sets:
                if not isinstance(s, Mapping):
                    continue
                label = str(s.get("label", "") or "")
                raw_items = s.get("items")
                sitems = [str(x) for x in raw_items] if isinstance(raw_items, list) else []
                sets.append({"label": label, "items": sitems})
        sets = sets[:3]
        while len(sets) < 2:
            sets.append({"label": "", "items": []})
        n = len(sets)

        if n == 2:
            centers = [(260.0, 240.0), (380.0, 240.0)]
            r = 130.0
        else:
            centers = [(260.0, 190.0), (380.0, 190.0), (320.0, 300.0)]
            r = 120.0

        cx_all = sum(c[0] for c in centers) / len(centers)
        cy_all = sum(c[1] for c in centers) / len(centers)

        parts: List[str] = []
        for i, (cx, cy) in enumerate(centers):
            parts.append(
                '<circle cx="%.1f" cy="%.1f" r="%.1f" fill="%s" fill-opacity="0.55" '
                'stroke="%s" stroke-width="1.5"></circle>'
                % (cx, cy, r, _SET_SOFT[i % 3], _SET_COLORS[i % 3])
            )

        for i, (cx, cy) in enumerate(centers):
            dx, dy = cx - cx_all, cy - cy_all
            dist = math.hypot(dx, dy) or 1.0
            ux, uy = dx / dist, dy / dist
            label_x = _clip(cx + ux * (r + 22), 40.0, width - 40.0)
            label_y = _clip(cy + uy * (r + 22), 18.0, height - 8.0)
            label = sets[i]["label"]
            if label:
                parts.append(
                    '<text x="%.1f" y="%.1f" text-anchor="middle" fill="%s" '
                    'font-size="13" font-weight="600">%s</text>'
                    % (label_x, label_y, _SET_COLORS[i % 3], _esc(label))
                )
            own_x, own_y = cx + ux * r * 0.5, cy + uy * r * 0.5
            items_text = "・".join(sets[i]["items"])
            lines = _wrap(items_text, r * 1.1, 12, max_lines=3) if items_text else []
            y0 = own_y - ((len(lines) - 1) * 13) / 2.0
            for li, ln in enumerate(lines):
                parts.append(
                    '<text x="%.1f" y="%.1f" text-anchor="middle" fill="var(--ink)" '
                    'font-size="12">%s</text>' % (own_x, y0 + li * 13, _esc(ln))
                )

        raw_overlaps = spec.get("overlaps")
        if isinstance(raw_overlaps, list):
            for ov in raw_overlaps:
                if not isinstance(ov, Mapping):
                    continue
                of = ov.get("of")
                if not isinstance(of, list):
                    continue
                idxs = [i for i in of if isinstance(i, int) and 0 <= i < n]
                if not idxs:
                    continue
                ox = sum(centers[i][0] for i in idxs) / len(idxs)
                oy = sum(centers[i][1] for i in idxs) / len(idxs)
                raw_ov_items = ov.get("items")
                oitems = [str(x) for x in raw_ov_items] if isinstance(raw_ov_items, list) else []
                text = "・".join(oitems)
                lines = _wrap(text, r * 0.9, 12, max_lines=3) if text else []
                y0 = oy - ((len(lines) - 1) * 13) / 2.0
                for li, ln in enumerate(lines):
                    parts.append(
                        '<text x="%.1f" y="%.1f" text-anchor="middle" fill="var(--ink)" '
                        'font-size="12" font-weight="600">%s</text>' % (ox, y0 + li * 13, _esc(ln))
                    )

        return '<svg class="venn" viewBox="0 0 %d %d" role="img" aria-label="venn">%s</svg>' % (
            width,
            height,
            "".join(parts),
        )
    except Exception:
        return '<svg class="venn" viewBox="0 0 %d %d" role="img" aria-label="venn"></svg>' % (
            width,
            height,
        )


# ---------------------------------------------------------------------------
# 4. flow_svg (simplified weighted sankey)
# ---------------------------------------------------------------------------

def flow_svg(spec: Any) -> str:
    fallback_w, fallback_h = 720, 300
    try:
        if not isinstance(spec, Mapping):
            spec = {}
        nodes: List[Dict[str, str]] = []
        seen: set = set()
        raw_nodes = spec.get("nodes")
        if isinstance(raw_nodes, list):
            for nd in raw_nodes:
                if not isinstance(nd, Mapping):
                    continue
                nid = str(nd.get("id", "") or "")
                if not nid or nid in seen:
                    continue
                seen.add(nid)
                nodes.append({"id": nid, "label": str(nd.get("label", nid) or nid)})

        links: List[Dict[str, Any]] = []
        raw_links = spec.get("links")
        if isinstance(raw_links, list):
            for lk in raw_links:
                if not isinstance(lk, Mapping):
                    continue
                src = str(lk.get("from", "") or "")
                dst = str(lk.get("to", "") or "")
                if not src or not dst:
                    continue
                val_raw = lk.get("value", 0)
                val = float(val_raw) if _is_number(val_raw) else 0.0
                if val < 0:
                    val = 0.0
                label_raw = lk.get("label")
                links.append(
                    {"from": src, "to": dst, "value": val, "label": str(label_raw) if label_raw else ""}
                )

        for lk in links:
            for k in ("from", "to"):
                if lk[k] not in seen:
                    seen.add(lk[k])
                    nodes.append({"id": lk[k], "label": lk[k]})

        if not nodes:
            return (
                '<svg class="flow" viewBox="0 0 %d %d" role="img" aria-label="flow"></svg>'
                % (fallback_w, fallback_h)
            )

        order = [nd["id"] for nd in nodes]
        incoming: Dict[str, List[str]] = {nid: [] for nid in order}
        for lk in links:
            if lk["to"] in incoming:
                incoming[lk["to"]].append(lk["from"])

        layer: Dict[str, Optional[int]] = {nid: (0 if not incoming[nid] else None) for nid in order}
        changed = True
        rounds = 0
        while changed and rounds < len(order) + 2:
            changed = False
            rounds += 1
            for nid in order:
                preds = incoming[nid]
                if not preds:
                    if layer[nid] is None:
                        layer[nid] = 0
                        changed = True
                    continue
                pred_layers = [layer[p] for p in preds if layer.get(p) is not None]
                if pred_layers:
                    new_layer = min(2, max(pred_layers) + 1)
                    if layer.get(nid) != new_layer:
                        layer[nid] = new_layer
                        changed = True
        for nid in order:
            if layer.get(nid) is None:
                layer[nid] = 0

        cols: Dict[int, List[str]] = {}
        for nid in order:
            cols.setdefault(layer[nid], []).append(nid)
        col_indices = sorted(cols.keys())
        num_cols = len(col_indices)

        node_w, node_h, row_gap = 150.0, 34.0, 20.0
        width = 720
        if num_cols <= 1:
            xs = [(width - node_w) / 2.0]
        elif num_cols == 2:
            xs = [70.0, width - 70.0 - node_w]
        else:
            xs = [60.0, (width - node_w) / 2.0, width - 60.0 - node_w]
        col_x_map = {c: (xs[idx] if idx < len(xs) else xs[-1]) for idx, c in enumerate(col_indices)}

        max_rows = max((len(v) for v in cols.values()), default=1)
        height = 60 + max_rows * (node_h + row_gap) + 30

        positions: Dict[str, Tuple[float, float]] = {}
        for c in col_indices:
            ids_in_col = cols[c]
            total_h = len(ids_in_col) * (node_h + row_gap) - row_gap
            start_y = (height - total_h) / 2.0
            for i, nid in enumerate(ids_in_col):
                positions[nid] = (col_x_map[c], start_y + i * (node_h + row_gap))

        parts: List[str] = []
        max_val = max((lk["value"] for lk in links), default=0.0)
        max_band = 26.0
        for lk in links:
            if lk["from"] not in positions or lk["to"] not in positions:
                continue
            sx, sy = positions[lk["from"]]
            ex, ey = positions[lk["to"]]
            sy_c, ey_c = sy + node_h / 2.0, ey + node_h / 2.0
            sx_e = sx + node_w
            band = max(1.5, (lk["value"] / max_val * max_band) if max_val > 0 else 1.5)
            dxp = (ex - sx_e) / 2.0
            path = "M%.1f,%.1f C%.1f,%.1f %.1f,%.1f %.1f,%.1f" % (
                sx_e,
                sy_c,
                sx_e + dxp,
                sy_c,
                ex - dxp,
                ey_c,
                ex,
                ey_c,
            )
            parts.append(
                '<path d="%s" fill="none" stroke="var(--accent)" stroke-width="%.2f" '
                'stroke-opacity="0.32"></path>' % (path, band)
            )
            if lk["label"]:
                mx, my = (sx_e + ex) / 2.0, (sy_c + ey_c) / 2.0
                parts.append(
                    '<text x="%.1f" y="%.1f" text-anchor="middle" fill="var(--ink-3)" '
                    'font-size="12">%s</text>' % (mx, my - 4, _esc(lk["label"]))
                )

        label_by_id = {nd["id"]: nd["label"] for nd in nodes}
        for nid, (x, y) in positions.items():
            parts.append(
                '<rect x="%.1f" y="%.1f" width="%.1f" height="%.1f" rx="4" '
                'fill="var(--surface-2)" stroke="var(--rule)"></rect>' % (x, y, node_w, node_h)
            )
            lines = _wrap(label_by_id.get(nid, nid), node_w - 16, 12, max_lines=2)
            line_h = 13.0
            y0 = y + node_h / 2.0 - ((len(lines) - 1) * line_h) / 2.0 + 4
            for li, ln in enumerate(lines):
                parts.append(
                    '<text x="%.1f" y="%.1f" text-anchor="middle" fill="var(--ink)" '
                    'font-size="12">%s</text>' % (x + node_w / 2.0, y0 + li * line_h, _esc(ln))
                )

        return '<svg class="flow" viewBox="0 0 %d %.1f" role="img" aria-label="flow">%s</svg>' % (
            width,
            height,
            "".join(parts),
        )
    except Exception:
        return (
            '<svg class="flow" viewBox="0 0 %d %d" role="img" aria-label="flow"></svg>'
            % (fallback_w, fallback_h)
        )


# ---------------------------------------------------------------------------
# 5. callout badges / legend
# ---------------------------------------------------------------------------

def callout_badge_svg(n: Any, tone: Any = None) -> str:
    try:
        num = int(n)
    except Exception:
        num = 0
    color = _tone_color(tone) if tone in _TONE_COLOR else "var(--accent)"
    label = _esc(num)
    return (
        '<svg class="badge" viewBox="0 0 22 22" role="img" aria-label="%s">'
        '<circle cx="11" cy="11" r="10" fill="%s"></circle>'
        '<text x="11" y="15" text-anchor="middle" fill="var(--surface)" '
        'font-size="12" font-weight="700">%s</text></svg>'
    ) % (label, color, label)


def callout_legend_html(items: Any) -> str:
    try:
        rows: List[str] = []
        if isinstance(items, list):
            for it in items:
                if not isinstance(it, Mapping):
                    continue
                n = it.get("n", 0)
                text = it.get("text", "")
                badge = callout_badge_svg(n, it.get("tone"))
                rows.append(
                    '<li class="callout-item">%s<span class="callout-text">%s</span></li>'
                    % (badge, _esc(text))
                )
        return '<ul class="callout-legend">%s</ul>' % "".join(rows)
    except Exception:
        return '<ul class="callout-legend"></ul>'


# ---------------------------------------------------------------------------
# 6. compare_html (radio + :checked toggle, no JS)
# ---------------------------------------------------------------------------

def compare_html(before_html: Any, after_html: Any, labels: Any = ("前", "後")) -> str:
    try:
        if isinstance(labels, (list, tuple)) and len(labels) >= 2:
            b_label, a_label = str(labels[0]), str(labels[1])
        else:
            b_label, a_label = "前", "後"
        before_str = before_html if isinstance(before_html, str) else str(before_html)
        after_str = after_html if isinstance(after_html, str) else str(after_html)

        digest_src = "\x00".join([before_str, after_str, b_label, a_label]).encode("utf-8", "ignore")
        cid = "cmp-%s" % hashlib.sha1(digest_src).hexdigest()[:10]
        rid_b, rid_a = "%s-b" % cid, "%s-a" % cid
        esc_b, esc_a = _esc(b_label), _esc(a_label)

        style = (
            "#{cid} .compare-panel{{display:none}}"
            "#{cid} #{rb}:checked ~ .compare-panel.compare-before{{display:block}}"
            "#{cid} #{ra}:checked ~ .compare-panel.compare-after{{display:block}}"
            "#{cid} input{{position:absolute;opacity:0;width:1px;height:1px;overflow:hidden}}"
            "#{cid} .compare-tabs{{display:flex;gap:.4rem;margin-bottom:.5rem}}"
            "#{cid} .compare-tabs label{{padding:.3rem .8rem;border:1px solid var(--rule);"
            "border-radius:999px;font-size:13px;color:var(--ink-2);cursor:pointer;"
            "user-select:none}}"
            "#{cid} #{rb}:checked ~ .compare-tabs label[for={rb}]{{background:var(--accent-soft);"
            "color:var(--accent-2);border-color:var(--accent)}}"
            "#{cid} #{ra}:checked ~ .compare-tabs label[for={ra}]{{background:var(--accent-soft);"
            "color:var(--accent-2);border-color:var(--accent)}}"
        ).format(cid=cid, rb=rid_b, ra=rid_a)

        return (
            '<div class="compare" id="{cid}"><style>{style}</style>'
            '<input type="radio" name="{cid}-g" id="{rb}" checked>'
            '<input type="radio" name="{cid}-g" id="{ra}">'
            '<div class="compare-tabs"><label for="{rb}">{lb}</label>'
            '<label for="{ra}">{la}</label></div>'
            '<div class="compare-panel compare-before">{before}</div>'
            '<div class="compare-panel compare-after">{after}</div>'
            "</div>"
        ).format(
            cid=cid,
            style=style,
            rb=rid_b,
            ra=rid_a,
            lb=esc_b,
            la=esc_a,
            before=before_str,
            after=after_str,
        )
    except Exception:
        return '<div class="compare"></div>'


# ---------------------------------------------------------------------------
# 7. score_grid_svg
# ---------------------------------------------------------------------------

def score_grid_svg(spec: Any) -> str:
    fallback_w, fallback_h = 400, 100
    try:
        if not isinstance(spec, Mapping):
            spec = {}
        max_raw = spec.get("max", 3)
        max_level = int(max_raw) if _is_number(max_raw) else 3
        if max_level < 1:
            max_level = 1

        axes: List[Dict[str, Any]] = []
        raw_axes = spec.get("axes")
        if isinstance(raw_axes, list):
            for ax in raw_axes:
                if not isinstance(ax, Mapping):
                    continue
                name = str(ax.get("name", "") or "")
                level_raw = ax.get("level", 0)
                level = int(level_raw) if _is_number(level_raw) else 0
                level = _clip_int(level, 0, max_level)
                note_raw = ax.get("note")
                axes.append({"name": name, "level": level, "note": str(note_raw) if note_raw else ""})
        if not axes:
            axes = [{"name": "", "level": 0, "note": ""}]

        label_w = 170.0
        cell = 28.0
        gap = 5.0
        width = label_w + (max_level + 1) * (cell + gap) + 30
        row_h_base = 42.0
        note_extra = 15.0

        rows_h = [row_h_base + (note_extra if ax["note"] else 0.0) for ax in axes]
        height = 16.0 + sum(rows_h) + 10.0

        parts: List[str] = []
        y_cursor = 16.0
        for ax, rh in zip(axes, rows_h):
            has_note = bool(ax["note"])
            row_center = y_cursor + row_h_base / 2.0 - (note_extra / 2.0 if has_note else 0.0)
            if ax["level"] <= 0:
                active_color = "var(--fail)"
            elif ax["level"] >= max_level:
                active_color = "var(--pass)"
            else:
                active_color = "var(--warn)"

            name_lines = _wrap(ax["name"], label_w - 14, 13, max_lines=2)
            ny0 = row_center - ((len(name_lines) - 1) * 14) / 2.0 + 4
            for li, ln in enumerate(name_lines):
                parts.append(
                    '<text x="10" y="%.1f" fill="var(--ink)" font-size="13">%s</text>'
                    % (ny0 + li * 14, _esc(ln))
                )
            if has_note:
                for ln in _wrap(ax["note"], label_w - 14, 12, max_lines=1):
                    parts.append(
                        '<text x="10" y="%.1f" fill="var(--ink-3)" font-size="12">%s</text>'
                        % (row_center + 16, _esc(ln))
                    )

            for j in range(max_level + 1):
                cx = label_w + j * (cell + gap)
                cy = row_center - cell / 2.0
                fill = active_color if j <= ax["level"] else "var(--surface-2)"
                parts.append(
                    '<rect x="%.1f" y="%.1f" width="%.1f" height="%.1f" rx="3" fill="%s" '
                    'stroke="var(--rule)"></rect>' % (cx, cy, cell, cell, fill)
                )
                if j == ax["level"]:
                    parts.append(
                        '<text x="%.1f" y="%.1f" text-anchor="middle" fill="var(--surface)" '
                        'font-size="12" font-weight="700">%d</text>'
                        % (cx + cell / 2.0, cy + cell / 2.0 + 4, j)
                    )
            y_cursor += rh

        return '<svg class="score" viewBox="0 0 %.1f %.1f" role="img" aria-label="score">%s</svg>' % (
            width,
            height,
            "".join(parts),
        )
    except Exception:
        return (
            '<svg class="score" viewBox="0 0 %d %d" role="img" aria-label="score"></svg>'
            % (fallback_w, fallback_h)
        )


# ---------------------------------------------------------------------------
# 8. heat_color / sparkline_svg
# ---------------------------------------------------------------------------

def heat_color(value: Any, lo: Any, hi: Any) -> str:
    try:
        v = float(value)
        l = float(lo)
        h = float(hi)
        if not (math.isfinite(v) and math.isfinite(l) and math.isfinite(h)):
            raise ValueError("non-finite")
        frac = 0.5 if h == l else (v - l) / (h - l)
        frac = _clip(frac, 0.0, 1.0)
        # 2026-09-10（撮影で確認）：100%まで濃くすると濃い地に濃い文字が乗って数字が読めない。
        # 上限を45%に抑え、濃淡の差は保ちながら文字（--ink）の可読性を守る。
        pct = int(round(frac * 45))
        return "color-mix(in srgb, var(--accent) %d%%, transparent)" % pct
    except Exception:
        return "color-mix(in srgb, var(--accent) 0%, transparent)"


def sparkline_svg(values: Any, width: int = 120, height: int = 24) -> str:
    try:
        w = int(width) if _is_number(width) else 120
        h = int(height) if _is_number(height) else 24
        if w <= 0:
            w = 120
        if h <= 0:
            h = 24
        vals: List[float] = []
        if isinstance(values, Sequence) and not isinstance(values, (str, bytes)):
            for v in values:
                if _is_number(v):
                    vals.append(float(v))
        if not vals:
            return '<svg class="spark" viewBox="0 0 %d %d" role="img" aria-label="sparkline"></svg>' % (
                w,
                h,
            )
        lo, hi = min(vals), max(vals)
        span = (hi - lo) or 1.0
        n = len(vals)
        pad = 2.0
        pts: List[str] = []
        for i, v in enumerate(vals):
            x = pad + (w - 2 * pad) * (i / (n - 1) if n > 1 else 0.5)
            y = h - pad - (h - 2 * pad) * ((v - lo) / span)
            pts.append("%.1f,%.1f" % (x, y))
        last_x, last_y = pts[-1].split(",")
        return (
            '<svg class="spark" viewBox="0 0 %d %d" role="img" aria-label="sparkline">'
            '<polyline points="%s" fill="none" stroke="var(--accent)" stroke-width="1.6" '
            'stroke-linejoin="round" stroke-linecap="round"></polyline>'
            '<circle cx="%s" cy="%s" r="2" fill="var(--accent)"></circle></svg>'
        ) % (w, h, " ".join(pts), last_x, last_y)
    except Exception:
        return '<svg class="spark" viewBox="0 0 %d %d" role="img" aria-label="sparkline"></svg>' % (
            120,
            24,
        )

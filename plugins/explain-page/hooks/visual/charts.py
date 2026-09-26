"""Deterministic SVG chart rendering for the visual renderer.

``render_chart`` is a pure function: same input -> same output string, no
randomness, no clock reads, no external libraries (stdlib only). It is used
by ``render_components.py`` to draw numeric figures (line / grouped bar)
for policy-analysis use cases such as sensitivity ranges, year-over-year
cost/benefit series, and candidate comparisons.

Output is a single ``<svg ...>...</svg>`` string. No ``<script>`` tags, no
external URLs, no ``url()`` references, no ``foreignObject``, and no raw
(unescaped) HTML are ever emitted: every piece of caller-supplied text
(title / labels / series names / unit) is passed through
``html.escape(..., quote=True)`` before being embedded.

Layout notes (readability fixes):
  * The legend measures each item's rendered width (CJK characters are
    wider than ASCII) and wraps to additional rows above the plot instead
    of letting items overlap.
  * Y-axis ticks snap to "nice" numbers (1/2/5 x 10^n steps) instead of a
    naive linspace, so labels never show noisy fractions like 99.75.
  * Bars and line points carry a small value label so the exact number is
    readable without hovering; line labels thin out when there are many
    points.
  * A bar whose value lands exactly on the baseline (typically zero) still
    draws a short, thick "zero mark" so the reader can tell the value is
    zero rather than missing.
  * Long or numerous X-axis labels wrap onto two lines, or rotate, instead
    of colliding with their neighbors.
"""

from __future__ import annotations

import math
from html import escape
from typing import Any, List, Mapping, NamedTuple, Sequence, Tuple

__all__ = ["render_chart"]

# Canvas geometry -------------------------------------------------------------
# The overall canvas size is a fixed part of the contract (callers/tests rely
# on the exact viewBox). Only the internal margins flex per-spec, to make
# room for a wrapped legend or wrapped/rotated X-axis labels.

_WIDTH = 640
_HEIGHT = 360
_MARGIN_LEFT = 55.0
_MARGIN_RIGHT = 20.0

_TITLE_AREA_HEIGHT = 26.0
_LEGEND_ROW_HEIGHT = 16.0
_LEGEND_TOP_PAD = 10.0
_LEGEND_FONT_SIZE = 11
_LEGEND_SWATCH = 11.0
_LEGEND_SWATCH_GAP = 5.0
_LEGEND_ITEM_GAP = 18.0

_XLABEL_FONT_SIZE = 10
_XLABEL_BASE_BOTTOM = 48.0
_XLABEL_WRAP_EXTRA = 12.0
_XLABEL_ROTATE_EXTRA = 28.0

_TICK_COUNT = 5
_ZERO_EPS = 1e-9

# Colors must stay within the fixed CSS-variable palette the renderer
# already exposes -- charts never introduce a new color.
_COLOR_VARS: Tuple[str, ...] = (
    "var(--accent)",
    "var(--pass)",
    "var(--warn)",
    "var(--fail)",
    "var(--ink)",
    "var(--ink-2)",
)

_VALID_KINDS = ("line", "bar")


class _Series:
    __slots__ = ("name", "values", "color_index")

    def __init__(self, name: str, values: List[float]) -> None:
        self.name = name
        self.values = values
        self.color_index = 0


class _Layout(NamedTuple):
    """Plot-area bounds for one render, in SVG user units."""

    left: float
    right: float
    top: float
    bottom: float

    @property
    def width(self) -> float:
        return self.right - self.left

    @property
    def height(self) -> float:
        return self.bottom - self.top


def _fmt_num(value: float) -> str:
    """Format a number for on-chart display without noisy float tails."""
    if isinstance(value, float) and math.isnan(value):
        # unreachable in practice (validation rejects NaN) but kept safe.
        return "NaN"
    rounded = round(float(value), 4)
    if rounded == int(rounded):
        return str(int(rounded))
    text = ("%.4f" % rounded).rstrip("0").rstrip(".")
    return text if text else "0"


def _is_number(value: Any) -> bool:
    if isinstance(value, bool):
        return False
    if not isinstance(value, (int, float)):
        return False
    return math.isfinite(float(value))


# Text-width estimation -------------------------------------------------------
# No font metrics are available at render time (pure stdlib, no layout
# engine), so widths are estimated from character class: a full-width /
# Japanese character is taken as ~0.95em, everything else (ASCII letters,
# digits, punctuation) as ~0.55em. This is enough to stop legend items and
# axis labels from overlapping without needing a real text-measurement pass.
def _char_width_em(ch: str) -> float:
    code = ord(ch)
    if code >= 0x3000:
        # Hiragana/Katakana/CJK ideographs/CJK punctuation/fullwidth forms.
        return 0.95
    return 0.55


def _text_width_px(text: str, font_size: float) -> float:
    if not text:
        return 0.0
    return sum(_char_width_em(ch) for ch in text) * font_size


def _validate(spec: Mapping[str, Any]) -> Tuple[str, str, List[str], List[_Series], str, float, float]:
    if not isinstance(spec, Mapping):
        raise ValueError("chart spec must be a mapping")

    kind = spec.get("kind")
    if kind not in _VALID_KINDS:
        raise ValueError("chart kind must be 'line' or 'bar', got %r" % (kind,))

    title = spec.get("title", "")
    if not isinstance(title, str):
        raise ValueError("chart title must be a string")

    labels = spec.get("labels")
    if not isinstance(labels, Sequence) or isinstance(labels, (str, bytes)):
        raise ValueError("chart labels must be a list of strings")
    labels = list(labels)
    if not labels:
        raise ValueError("chart labels must not be empty")
    for label in labels:
        if not isinstance(label, str):
            raise ValueError("chart labels must all be strings")

    raw_series = spec.get("series")
    if not isinstance(raw_series, Sequence) or isinstance(raw_series, (str, bytes)):
        raise ValueError("chart series must be a list")
    if not raw_series:
        raise ValueError("chart series must not be empty")

    series: List[_Series] = []
    for entry in raw_series:
        if not isinstance(entry, Mapping):
            raise ValueError("each series entry must be a mapping")
        name = entry.get("name", "")
        if not isinstance(name, str):
            raise ValueError("series name must be a string")
        values = entry.get("values")
        if not isinstance(values, Sequence) or isinstance(values, (str, bytes)):
            raise ValueError("series values must be a list of numbers")
        values = list(values)
        if len(values) != len(labels):
            raise ValueError(
                "series %r has %d values but there are %d labels"
                % (name, len(values), len(labels))
            )
        clean_values: List[float] = []
        for v in values:
            if not _is_number(v):
                raise ValueError("series %r contains a non-numeric value: %r" % (name, v))
            clean_values.append(float(v))
        series.append(_Series(name=name, values=clean_values))

    unit = spec.get("unit", "")
    if not isinstance(unit, str):
        raise ValueError("chart unit must be a string")

    y_min = spec.get("y_min")
    y_max = spec.get("y_max")
    if y_min is not None and not _is_number(y_min):
        raise ValueError("y_min must be a number")
    if y_max is not None and not _is_number(y_max):
        raise ValueError("y_max must be a number")

    all_values = [v for s in series for v in s.values]
    data_min = min(all_values)
    data_max = max(all_values)

    resolved_min = float(y_min) if y_min is not None else data_min
    resolved_max = float(y_max) if y_max is not None else data_max

    if resolved_min > resolved_max:
        resolved_min, resolved_max = resolved_max, resolved_min

    if resolved_min == resolved_max:
        # Keep zero on the axis when the flat value is zero; otherwise pad
        # symmetrically so a single repeated value still renders sanely.
        pad = 1.0 if resolved_min == 0 else abs(resolved_min) * 0.1 or 1.0
        resolved_min -= pad
        resolved_max += pad

    return kind, title, labels, series, unit, resolved_min, resolved_max


# "Nice number" axis ticks ----------------------------------------------------
# Standard nice-number tick algorithm (Sparks/Heckbert style): snap the tick
# step to a 1 / 2 / 5 x 10^n value so labels read cleanly (0, 50, 100, ...)
# instead of the noisy quarters a naive linspace produces.
def _nice_num(value: float, round_: bool) -> float:
    if value <= 0:
        return 0.0
    exp = math.floor(math.log10(value))
    fraction = value / (10 ** exp)
    if round_:
        if fraction < 1.5:
            nice_fraction = 1.0
        elif fraction < 3.0:
            nice_fraction = 2.0
        elif fraction < 7.0:
            nice_fraction = 5.0
        else:
            nice_fraction = 10.0
    else:
        if fraction <= 1.0:
            nice_fraction = 1.0
        elif fraction <= 2.0:
            nice_fraction = 2.0
        elif fraction <= 5.0:
            nice_fraction = 5.0
        else:
            nice_fraction = 10.0
    return nice_fraction * (10 ** exp)


def _nice_ticks(data_min: float, data_max: float, tick_count: int = _TICK_COUNT) -> Tuple[float, float, List[float]]:
    if data_min == data_max:
        data_min -= 1.0
        data_max += 1.0

    raw_range = _nice_num(data_max - data_min, False)
    tick_spacing = _nice_num(raw_range / max(tick_count - 1, 1), True)
    if tick_spacing <= 0:
        tick_spacing = 1.0

    nice_min = math.floor(data_min / tick_spacing) * tick_spacing
    nice_max = math.ceil(data_max / tick_spacing) * tick_spacing

    count = int(round((nice_max - nice_min) / tick_spacing)) + 1
    ticks = [nice_min + i * tick_spacing for i in range(max(count, 1))]

    # Keep the label count readable (target ~4-6) even when the raw nice
    # step produces more steps than that; resample evenly rather than
    # dropping the min/max endpoints.
    if len(ticks) > 6:
        stride = math.ceil(len(ticks) / 6)
        ticks = ticks[::stride]
        if abs(ticks[-1] - nice_max) > _ZERO_EPS:
            ticks.append(nice_max)

    return nice_min, nice_max, ticks


def _y_to_px(value: float, y_min: float, y_max: float, layout: _Layout) -> float:
    span = y_max - y_min
    if span == 0:
        proportion = 0.5
    else:
        proportion = (value - y_min) / span
    return layout.bottom - proportion * layout.height


def _category_x(index: int, count: int, layout: _Layout) -> float:
    step = layout.width / count
    return layout.left + (index + 0.5) * step


# Legend layout ---------------------------------------------------------------
def _legend_item_width(name: str) -> float:
    return _LEGEND_SWATCH + _LEGEND_SWATCH_GAP + _text_width_px(name, _LEGEND_FONT_SIZE)


def _layout_legend(series: List[_Series], available_width: float) -> List[List[Tuple[_Series, float, float]]]:
    rows: List[List[Tuple[_Series, float, float]]] = [[]]
    cursor = 0.0
    for s in series:
        w = _legend_item_width(s.name)
        if cursor > 0 and cursor + w > available_width:
            rows.append([])
            cursor = 0.0
        rows[-1].append((s, cursor, w))
        cursor += w + _LEGEND_ITEM_GAP
    return rows


def _render_legend(rows: List[List[Tuple[_Series, float, float]]], layout: _Layout) -> List[str]:
    parts: List[str] = []
    for row_idx, row in enumerate(rows):
        baseline = _TITLE_AREA_HEIGHT + row_idx * _LEGEND_ROW_HEIGHT + 12.0
        for s, x_off, _w in row:
            color = _COLOR_VARS[s.color_index % len(_COLOR_VARS)]
            swatch_x = layout.left + x_off
            text_x = swatch_x + _LEGEND_SWATCH + _LEGEND_SWATCH_GAP
            parts.append(
                '<rect x="%.1f" y="%.1f" width="11" height="11" rx="2" fill="%s"></rect>'
                % (swatch_x, baseline - 10.0, color)
            )
            parts.append(
                '<text x="%.1f" y="%.1f" fill="var(--ink-2)" font-size="12">%s</text>'
                % (text_x, baseline, escape(s.name, quote=True))
            )
    return parts


# X-axis label layout ----------------------------------------------------------
def _x_label_mode(labels: List[str], layout: _Layout) -> str:
    n = len(labels)
    if n == 0:
        return "normal"
    step = layout.width / n
    max_w = max(_text_width_px(label, _XLABEL_FONT_SIZE) for label in labels)
    if n > 10 or max_w > step * 1.8:
        return "rotate"
    if max_w > step * 1.05:
        return "wrap"
    return "normal"


def _wrap_label_two_lines(label: str) -> Tuple[str, str]:
    if len(label) <= 1:
        return label, ""
    stripped = label.strip()
    if " " in stripped:
        words = stripped.split(" ")
        if len(words) >= 2:
            best: Any = None
            for i in range(1, len(words)):
                line1 = " ".join(words[:i])
                line2 = " ".join(words[i:])
                diff = abs(
                    _text_width_px(line1, _XLABEL_FONT_SIZE) - _text_width_px(line2, _XLABEL_FONT_SIZE)
                )
                if best is None or diff < best[0]:
                    best = (diff, line1, line2)
            return best[1], best[2]

    total = _text_width_px(label, _XLABEL_FONT_SIZE)
    cum = 0.0
    split_idx = len(label) // 2
    for i, ch in enumerate(label):
        cum += _char_width_em(ch) * _XLABEL_FONT_SIZE
        if cum >= total / 2.0:
            split_idx = i + 1
            break
    split_idx = max(1, min(split_idx, len(label) - 1))
    return label[:split_idx], label[split_idx:]


def _render_x_labels(labels: List[str], layout: _Layout, mode: str) -> List[str]:
    parts: List[str] = []
    n = len(labels)
    baseline_y = layout.bottom + 18.0
    for i, label in enumerate(labels):
        x = _category_x(i, n, layout)
        if mode == "rotate":
            parts.append(
                '<text x="%.1f" y="%.1f" text-anchor="end" fill="var(--ink-2)" '
                'font-size="11" transform="rotate(-30 %.1f %.1f)">%s</text>'
                % (x, baseline_y, x, baseline_y, escape(label, quote=True))
            )
        elif mode == "wrap":
            line1, line2 = _wrap_label_two_lines(label)
            parts.append(
                '<text x="%.1f" y="%.1f" text-anchor="middle" fill="var(--ink-2)" font-size="11">'
                '<tspan x="%.1f" dy="0">%s</tspan><tspan x="%.1f" dy="12">%s</tspan></text>'
                % (x, baseline_y, x, escape(line1, quote=True), x, escape(line2, quote=True))
            )
        else:
            parts.append(
                '<text x="%.1f" y="%.1f" text-anchor="middle" fill="var(--ink-2)" '
                'font-size="11">%s</text>' % (x, baseline_y, escape(label, quote=True))
            )
    return parts


def _render_frame(
    title: str,
    unit: str,
    ticks: List[float],
    layout: _Layout,
    legend_rows: List[List[Tuple[_Series, float, float]]],
    y_min: float,
    y_max: float,
    x_label_parts: List[str],
) -> Tuple[List[str], List[str]]:
    """Build the shared chrome: title, legend, gridlines, axis labels, zero
    line. Returns (background_svg_parts, foreground_svg_parts) so callers
    can slot the data marks (lines/bars) between the two.
    """
    parts: List[str] = []

    esc_title = escape(title, quote=True)
    if title:
        parts.append(
            '<text x="%.1f" y="20" text-anchor="middle" fill="var(--ink)" '
            'font-size="15" font-weight="600">%s</text>' % (_WIDTH / 2.0, esc_title)
        )

    esc_unit = escape(unit, quote=True)
    if unit:
        parts.append(
            '<text x="%.1f" y="%.1f" text-anchor="end" fill="var(--ink-2)" '
            'font-size="12">(%s)</text>' % (layout.right, layout.top - 10, esc_unit)
        )

    parts.extend(_render_legend(legend_rows, layout))

    # Y gridlines + tick labels.
    for tick in ticks:
        y = _y_to_px(tick, y_min, y_max, layout)
        parts.append(
            '<line x1="%.1f" y1="%.1f" x2="%.1f" y2="%.1f" stroke="var(--rule)" '
            'stroke-width="1"></line>' % (layout.left, y, layout.right, y)
        )
        parts.append(
            '<text x="%.1f" y="%.1f" text-anchor="end" fill="var(--ink-2)" '
            'font-size="11">%s</text>' % (layout.left - 8, y + 3.5, escape(_fmt_num(tick), quote=True))
        )

    # Zero reference line, only when zero is strictly inside the range
    # (i.e. the data actually crosses zero) so negative values are legible.
    foreground: List[str] = []
    if y_min < 0 < y_max:
        zero_y = _y_to_px(0.0, y_min, y_max, layout)
        foreground.append(
            '<line x1="%.1f" y1="%.1f" x2="%.1f" y2="%.1f" stroke="var(--ink-2)" '
            'stroke-width="1.5"></line>' % (layout.left, zero_y, layout.right, zero_y)
        )

    parts.extend(x_label_parts)

    return parts, foreground


def _label_indices(n: int, max_labels: int = 6) -> List[int]:
    if n <= max_labels:
        return list(range(n))
    stride = math.ceil(n / max_labels)
    idxs = list(range(0, n, stride))
    if idxs[-1] != n - 1:
        idxs.append(n - 1)
    return idxs


def _render_line_marks(
    labels: List[str],
    series: List[_Series],
    y_min: float,
    y_max: float,
    unit: str,
    layout: _Layout,
) -> List[str]:
    n = len(labels)
    marks: List[str] = []
    label_idxs = set(_label_indices(n))
    for i, s in enumerate(series):
        color = _COLOR_VARS[i % len(_COLOR_VARS)]
        points = []
        for idx in range(n):
            x = _category_x(idx, n, layout)
            y = _y_to_px(s.values[idx], y_min, y_max, layout)
            points.append("%.1f,%.1f" % (x, y))
        marks.append(
            '<polyline points="%s" fill="none" stroke="%s" stroke-width="2" '
            'stroke-linejoin="round" stroke-linecap="round"></polyline>'
            % (" ".join(points), color)
        )
        for idx in range(n):
            x = _category_x(idx, n, layout)
            y = _y_to_px(s.values[idx], y_min, y_max, layout)
            marks.append('<circle cx="%.1f" cy="%.1f" r="3" fill="%s"></circle>' % (x, y, color))
            if idx in label_idxs:
                label_y = max(y - 8.0, layout.top - 2.0)
                text = escape(_fmt_num(s.values[idx]) + unit, quote=True)
                marks.append(
                    '<text class="chart-value-label" x="%.1f" y="%.1f" text-anchor="middle" '
                    'fill="%s" font-size="10.5">%s</text>' % (x, label_y, color, text)
                )
    return marks


def _render_bar_marks(
    labels: List[str],
    series: List[_Series],
    y_min: float,
    y_max: float,
    unit: str,
    layout: _Layout,
) -> List[str]:
    n = len(labels)
    step = layout.width / n
    num_series = len(series)
    band_usable = step * 0.8
    bar_w = band_usable / num_series
    gap_ratio = 0.85  # leave a small visible gap between bars in a group

    if y_min <= 0 <= y_max:
        baseline_value = 0.0
    elif y_min > 0:
        baseline_value = y_min
    else:
        baseline_value = y_max
    baseline_px = _y_to_px(baseline_value, y_min, y_max, layout)

    marks: List[str] = []
    for idx in range(n):
        center = _category_x(idx, n, layout)
        group_left = center - band_usable / 2.0
        for s_idx, s in enumerate(series):
            color = _COLOR_VARS[s_idx % len(_COLOR_VARS)]
            value = s.values[idx]
            value_px = _y_to_px(value, y_min, y_max, layout)
            drawn_w = bar_w * gap_ratio
            bar_x = group_left + s_idx * bar_w + (bar_w - drawn_w) / 2.0
            # A *value* of zero is the case callers actually care about
            # ("is there data here at all"); a bar whose height merely
            # collapses to zero because it lands on a non-zero baseline
            # (e.g. an all-positive series where the axis starts above 0)
            # is a different, purely geometric edge case handled below.
            is_true_zero = abs(value) < _ZERO_EPS

            if is_true_zero:
                # No rect would be visible at all here (zero height), so
                # draw a short, thick tick at the real zero line instead,
                # to make "this is zero" legible rather than reading as a
                # gap or missing data.
                marks.append(
                    '<line class="chart-zero-mark" x1="%.1f" y1="%.1f" x2="%.1f" y2="%.1f" '
                    'stroke="%s" stroke-width="3" stroke-linecap="round"></line>'
                    % (bar_x, value_px, bar_x + drawn_w, value_px, color)
                )
            else:
                bar_top = min(value_px, baseline_px)
                bar_height = abs(baseline_px - value_px)
                if bar_height <= 0:
                    bar_height = 0.6  # keep a hairline visible for a zero-height bar
                    bar_top = baseline_px - bar_height / 2.0
                marks.append(
                    '<rect x="%.1f" y="%.1f" width="%.1f" height="%.1f" fill="%s"></rect>'
                    % (bar_x, bar_top, drawn_w, bar_height, color)
                )

            label_x = bar_x + drawn_w / 2.0
            if value_px <= baseline_px:
                label_y = value_px - 4.0
            else:
                label_y = value_px + 12.0
            label_y = max(label_y, layout.top - 2.0)
            text = escape(_fmt_num(value) + unit, quote=True)
            marks.append(
                '<text class="chart-value-label" x="%.1f" y="%.1f" text-anchor="middle" '
                'fill="var(--ink-2)" font-size="10.5">%s</text>' % (label_x, label_y, text)
            )
    return marks


def render_chart(spec: Mapping[str, Any]) -> str:
    """Render ``spec`` to a single ``<svg>...</svg>`` string.

    See module docstring for the contract. Raises ``ValueError`` on any
    malformed input (non-numeric values, mismatched lengths, empty series).
    """
    kind, title, labels, series, unit, data_min, data_max = _validate(spec)

    for i, s in enumerate(series):
        s.color_index = i % len(_COLOR_VARS)

    y_min, y_max, ticks = _nice_ticks(data_min, data_max)

    legend_available = _WIDTH - _MARGIN_RIGHT - _MARGIN_LEFT
    legend_rows = _layout_legend(series, legend_available)
    margin_top = _TITLE_AREA_HEIGHT + len(legend_rows) * _LEGEND_ROW_HEIGHT + _LEGEND_TOP_PAD

    # X-axis label mode needs a layout to measure against; the mode only
    # affects the bottom margin, not the left/right/top bounds, so a
    # provisional layout (bottom margin not yet known) is enough to pick it.
    provisional = _Layout(
        left=_MARGIN_LEFT,
        right=_WIDTH - _MARGIN_RIGHT,
        top=margin_top,
        bottom=_HEIGHT - _XLABEL_BASE_BOTTOM,
    )
    mode = _x_label_mode(labels, provisional)
    margin_bottom = _XLABEL_BASE_BOTTOM
    if mode == "wrap":
        margin_bottom += _XLABEL_WRAP_EXTRA
    elif mode == "rotate":
        margin_bottom += _XLABEL_ROTATE_EXTRA

    layout = _Layout(
        left=_MARGIN_LEFT,
        right=_WIDTH - _MARGIN_RIGHT,
        top=margin_top,
        bottom=_HEIGHT - margin_bottom,
    )

    x_label_parts = _render_x_labels(labels, layout, mode)
    background, foreground_frame = _render_frame(
        title, unit, ticks, layout, legend_rows, y_min, y_max, x_label_parts
    )

    if kind == "line":
        data_marks = _render_line_marks(labels, series, y_min, y_max, unit, layout)
    else:
        data_marks = _render_bar_marks(labels, series, y_min, y_max, unit, layout)

    body = "".join(background) + "".join(foreground_frame) + "".join(data_marks)

    aria_label = escape(title, quote=True) if title else "chart"
    svg = (
        '<svg class="chart" viewBox="0 0 %d %d" role="img" aria-label="%s" '
        '>%s</svg>'
    ) % (_WIDTH, _HEIGHT, aria_label, body)
    return svg

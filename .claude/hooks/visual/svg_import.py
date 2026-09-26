"""手書きSVGの取り込み器（許可リスト方式のサニタイザ）。

方針＝生のSVG文字列を**解析し直して**、許可した要素・属性だけで新しいツリーを
組み立て、標準ライブラリの xml.etree.ElementTree でシリアライズし直す。
元の文字列の断片を出力へ直接連結する経路は一切持たない＝ET.tostring() が
テキスト・属性値を自動でエスケープするので、html.escape 相当の安全性は
「文字列連結をしない」という設計そのもので担保する。

defusedxml は入っていない（外部ライブラリ禁止）ので、DTD・実体参照・外部参照は
**解析前に生文字列でリジェクト**する（xml.etree 単体は billion-laughs 等に
弱いことがある。解析に入る前に落とすのが最も確実）。

決定論・例外を外に投げない：不正な入力は常に空の svg + warnings を返す。
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass


@dataclass
class SvgResult:
    svg: str
    dropped: list[str]
    warnings: list[str]
    width: float | None
    height: float | None


# ---------------------------------------------------------------------------
# 許可リスト（担当Bの契約どおり「広く」許可する）
# ---------------------------------------------------------------------------

ELEMENTS_ALLOWED = {
    "svg", "g", "path", "rect", "circle", "ellipse", "line", "polyline",
    "polygon", "text", "tspan", "textPath", "defs", "symbol", "use",
    "marker", "title", "desc", "clipPath", "mask", "linearGradient",
    "radialGradient", "stop", "pattern", "switch", "image",
}
# 許可リストに無い要素は script/foreignObject/animate*/set/iframe/object/embed/
# video/audio/style（CSS要素）を含め、すべて既定拒否＝サブツリーごと落ちる。

_ATTRS_SHAPE = {
    "d", "x", "y", "x1", "y1", "x2", "y2", "cx", "cy", "r", "rx", "ry",
    "width", "height", "points", "viewBox", "preserveAspectRatio", "pathLength",
}
_ATTRS_PAINT = {
    "fill", "fill-opacity", "fill-rule", "stroke", "stroke-width",
    "stroke-opacity", "stroke-linecap", "stroke-linejoin", "stroke-dasharray",
    "stroke-dashoffset", "stroke-miterlimit", "opacity", "paint-order",
    "vector-effect", "shape-rendering",
}
_ATTRS_TEXT = {
    "font-family", "font-size", "font-weight", "font-style", "text-anchor",
    "dominant-baseline", "letter-spacing", "word-spacing", "text-decoration",
    "dx", "dy", "rotate", "textLength", "lengthAdjust", "startOffset",
}
_ATTRS_STRUCTURE = {
    "id", "class", "transform", "transform-origin", "clip-path", "mask",
    "marker-start", "marker-mid", "marker-end", "display", "visibility",
}
_ATTRS_GRADIENT = {
    "offset", "stop-color", "stop-opacity", "gradientUnits",
    "gradientTransform", "spreadMethod", "fx", "fy", "fr", "patternUnits",
    "patternContentUnits", "patternTransform",
}
_ATTRS_ARIA = {"role", "aria-label", "aria-hidden"}
# 2026-09-09：契約書の属性リストには無いが、<marker> は要素として許可されている
# のに、これらが無いと矢印が既定サイズ(3x3)・既定向き(0度)から動かせず、
# 「矢印を含む手書きSVGで見た目が同じ」という必須の目視確認を満たせない。
# 図形サイズだけの純粋な幾何属性（注入面が無い＝gradientUnits/patternUnits と
# 同種）なので、marker専用の幾何属性として広げた。
_ATTRS_MARKER_GEOMETRY = {
    "markerWidth", "markerHeight", "markerUnits", "refX", "refY", "orient",
}

ATTRS_ALLOWED = (
    _ATTRS_SHAPE
    | _ATTRS_PAINT
    | _ATTRS_TEXT
    | _ATTRS_STRUCTURE
    | _ATTRS_GRADIENT
    | _ATTRS_ARIA
    | _ATTRS_MARKER_GEOMETRY
)
# href / xlink:href と style は上の集合に入れず、個別に検査する（下記参照）。
# xmlns* は ElementTree の名前空間解決で attrib に現れない＝出力にも出ない。

# SYSTEM/PUBLIC は <!DOCTYPE …> や <!ENTITY …> の内側でのみ意味を持つ字句であり、
# その外側（本文・属性値など）に同じ綴りが出ても危険ではない。<!DOCTYPE と
# <!ENTITY 自体は常に拒否するので、その2語だけをマーカーにすれば
# 「SYSTEM/PUBLICは<!DOCTYPE/<!ENTITY構文の中に現れた時だけ拒否根拠にする」を
# 満たす（構文の外に出た SYSTEM/PUBLIC 単体では、もう拒否されない）。
_DTD_MARKERS = ("<!DOCTYPE", "<!ENTITY")

_LENGTH_RE = re.compile(r"^\s*(-?\d+(?:\.\d+)?)")

_XLINK_NS = "http://www.w3.org/1999/xlink"
_SVG_OPEN_TAG_RE = re.compile(r"<svg(?=[\s/>])")


def _has_dtd_marker(text: str) -> bool:
    return any(marker in text for marker in _DTD_MARKERS)


def _ensure_xlink_declaration(text: str) -> str:
    """`xlink:` 接頭辞を使っているのに `xmlns:xlink` 宣言が無ければ補う。

    標準ライブラリの解析器は unbound prefix（宣言の無い名前空間接頭辞）を
    見つけると丸ごと拒否する。ここで先頭の `<svg` タグへ宣言を足しておけば、
    解析自体は通る。補った宣言は既存の xmlns 除去の仕組みでそのまま消える
    （要素の再構築は local name だけを見るので、xmlns:* は attrib に現れず
    出力には一切残らない）。
    """
    if "xlink:" not in text or "xmlns:xlink" in text:
        return text
    match = _SVG_OPEN_TAG_RE.search(text)
    if not match:
        return text
    insert_at = match.end()
    return f'{text[:insert_at]} xmlns:xlink="{_XLINK_NS}"{text[insert_at:]}'


def _local_name(tag: str) -> str:
    if tag.startswith("{"):
        return tag.split("}", 1)[1]
    if ":" in tag:
        return tag.split(":", 1)[1]
    return tag


def _has_disallowed_url(value: str) -> bool:
    """`url(...)` を含み、かつ `url(#...)`（同一文書参照）でない値なら True。"""
    lowered = value.lower()
    idx = 0
    while True:
        pos = lowered.find("url(", idx)
        if pos == -1:
            return False
        after = value[pos + 4 : pos + 5]
        if after != "#":
            return True
        idx = pos + 4


def _has_javascript_scheme(value: str) -> bool:
    return "javascript:" in value.lower()


def _record_drop(dropped: list[str], seen: set[str], name: str) -> None:
    if name in seen:
        return
    seen.add(name)
    dropped.append(name)


def _filter_style(value: str, dropped: list[str], seen: set[str]) -> str | None:
    """style属性の中身を、許可した属性名に対応するCSSプロパティだけに絞る。"""
    kept: list[str] = []
    for decl in value.split(";"):
        decl = decl.strip()
        if not decl or ":" not in decl:
            continue
        prop, _, val = decl.partition(":")
        prop = prop.strip()
        val = val.strip()
        if prop not in ATTRS_ALLOWED:
            _record_drop(dropped, seen, f"style:{prop}")
            continue
        if _has_disallowed_url(val) or _has_javascript_scheme(val):
            _record_drop(dropped, seen, f"style:{prop}")
            continue
        kept.append(f"{prop}:{val}")
    if not kept:
        return None
    return ";".join(kept)


def _append_text(parent: ET.Element, text: str | None) -> None:
    """dropした子要素の直後にあった地の文（tail）を、直前の要素かparentへ吸収する。"""
    if not text:
        return
    children = list(parent)
    if children:
        last = children[-1]
        last.tail = (last.tail or "") + text
    else:
        parent.text = (parent.text or "") + text


def _process_element(
    elem: ET.Element, dropped: list[str], seen: set[str]
) -> ET.Element | None:
    local = _local_name(elem.tag)
    if local not in ELEMENTS_ALLOWED:
        _record_drop(dropped, seen, local)
        return None

    new_elem = ET.Element(local)

    for key, value in elem.attrib.items():
        akey = _local_name(key)

        if akey == "href":
            if value.startswith("#"):
                new_elem.set("href", value)
            elif local == "image" and value.startswith("data:image/"):
                new_elem.set("href", value)
            else:
                _record_drop(dropped, seen, "href")
            continue

        if akey == "style":
            filtered = _filter_style(value, dropped, seen)
            if filtered:
                new_elem.set("style", filtered)
            continue

        if akey not in ATTRS_ALLOWED:
            _record_drop(dropped, seen, akey)
            continue

        if _has_disallowed_url(value) or _has_javascript_scheme(value):
            _record_drop(dropped, seen, akey)
            continue

        new_elem.set(akey, value)

    _append_text(new_elem, elem.text)

    for child in elem:
        new_child = _process_element(child, dropped, seen)
        if new_child is not None:
            new_elem.append(new_child)
            new_child.tail = child.tail
        else:
            _append_text(new_elem, child.tail)

    return new_elem


def _parse_length(value: str) -> float | None:
    match = _LENGTH_RE.match(value)
    if not match:
        return None
    try:
        return float(match.group(1))
    except ValueError:
        return None


def _fmt_num(value: float) -> str:
    if value == int(value):
        return str(int(value))
    return repr(value)


def _empty_result(warning: str, dropped: list[str] | None = None) -> SvgResult:
    return SvgResult(
        svg="", dropped=dropped or [], warnings=[warning], width=None, height=None
    )


def sanitize_svg(text: str) -> SvgResult:
    """手書きSVG文字列を解析し、許可リストだけで組み直した新しいSVGを返す。

    生のまま通す口は無い＝壊れた入力・危険な入力は常に空のsvgとwarningsで返す
    （例外は外に投げない）。
    """
    try:
        if not text or not text.strip():
            return _empty_result("empty input")

        if _has_dtd_marker(text):
            return _empty_result(
                "DTD/entity declarations are not allowed "
                "(<!DOCTYPE / <!ENTITY / SYSTEM / PUBLIC)"
            )

        text = _ensure_xlink_declaration(text)

        try:
            root = ET.fromstring(text)
        except ET.ParseError as exc:
            return _empty_result(f"invalid XML: {exc}")

        if _local_name(root.tag) != "svg":
            return _empty_result("root element is not <svg>")

        dropped: list[str] = []
        seen: set[str] = set()
        new_root = _process_element(root, dropped, seen)
        if new_root is None:
            return _empty_result("root <svg> element was rejected", dropped)

        warnings: list[str] = []

        existing_class = new_root.get("class")
        if existing_class:
            classes = existing_class.split()
            if "svg-in" not in classes:
                classes.append("svg-in")
            new_root.set("class", " ".join(classes))
        else:
            new_root.set("class", "svg-in")

        width_val: float | None = None
        height_val: float | None = None

        view_box = new_root.get("viewBox")
        raw_width = new_root.attrib.pop("width", None)
        raw_height = new_root.attrib.pop("height", None)

        if view_box:
            parts = view_box.split()
            if len(parts) == 4:
                try:
                    width_val = float(parts[2])
                    height_val = float(parts[3])
                except ValueError:
                    warnings.append("viewBox values could not be parsed")
            else:
                warnings.append("viewBox does not have 4 values")
        elif raw_width is not None and raw_height is not None:
            w = _parse_length(raw_width)
            h = _parse_length(raw_height)
            if w is not None and h is not None:
                new_root.set("viewBox", f"0 0 {_fmt_num(w)} {_fmt_num(h)}")
                width_val, height_val = w, h
            else:
                warnings.append("width/height could not be parsed into a viewBox")
        else:
            warnings.append(
                "no viewBox and no width/height on <svg>; size is undetermined"
            )

        svg_str = ET.tostring(new_root, encoding="unicode")
        return SvgResult(
            svg=svg_str,
            dropped=dropped,
            warnings=warnings,
            width=width_val,
            height=height_val,
        )
    except Exception as exc:  # noqa: BLE001 - 契約により例外を外に投げない
        return _empty_result(f"internal error: {exc}")

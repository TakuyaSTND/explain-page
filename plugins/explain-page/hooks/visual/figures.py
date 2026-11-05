"""Mermaid の読み取りと、新しい図の型の形の計算（2026-11-04・利用者が選んだ A6・A4）。

なぜ1か所か＝HTML の頁（SVG）と PDF（LaTeX の TikZ）で同じ配置の図にするため。図の形は「四角・線・円・文字」の
部品（shapes）の座標の一覧として、ここだけで計算する。HTML は `shapes_svg()` が、PDF は render_pdf.py の
r_shapes が、同じ一覧を描く。⚠️PDF 側（スキルの scripts/figures.py）はこの写し＝
試験が中身の一致を確かめる（diagram_layout.py と同じやり方）。

決めたこと（赤ペン diagram-skills-impl-01 の回答）：
- A6＝Mermaid の流れ図に加えて、やりとりの図（sequence）と状態の図（state）も自前で読む（Q11 B）。頁の定義の
  新しい鍵 mermaid に書く（Q12 A）。流れ図と状態の図は、いまの箱と矢印の図（diagram）に変えて、配置の計算
  （diagram_layout.py）に任せる。やりとりの図は、ここで形を計算する。読めない書き方は捨てて warnings に積む。
- A4＝魚の骨（原因の分類）・滝の図（足し引きの内訳）・ダンベル（いま→施策後）の3型（Q13 A）。HTML と PDF の
  両方で描く（Q14 A）。審査結果の頁には組み込まない（Q15 A＝部品だけ）。

契約＝標準ライブラリのみ・決定論・例外を外に投げない（不正な入力は warnings に書いて捨てる）。
色は役割の名前（ink・muted・acc・good・warn・bad）で持ち、描く側が自分の色に直す。
"""

from __future__ import annotations

import math
import re
from html import escape as _escape
from typing import Any

# ---------------------------------------------------------------------------
# 共通
# ---------------------------------------------------------------------------

TONES = ("ink", "muted", "acc", "good", "warn", "bad", "none")
FONT = 13.0          # 本文の字の大きさ（px）
SMALL = 12.0         # ラベル・目盛りの字の大きさ（px）
MAX_WIDTH = 720.0    # 頁の本文の幅（箱と矢印の図と同じ）


def _s(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    try:
        return str(value)
    except Exception:
        return ""


def _num(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)) and math.isfinite(float(value)):
        return float(value)
    text = _s(value).strip().replace(",", "")
    try:
        number = float(text)
    except ValueError:
        return None
    return number if math.isfinite(number) else None


def _tone(value: Any, default: str = "acc") -> str:
    tone = _s(value).strip().lower()
    aliases = {"neutral": "acc", "accent": "acc", "risk": "bad", "info": "acc", "new": "acc"}
    tone = aliases.get(tone, tone)
    return tone if tone in TONES else default


def text_width(text: str, size: float = FONT) -> float:
    """字の幅の見積もり（全角＝1字1em・半角＝0.58em。配置の計算の実測と同じ向きに少し大きめ）。"""
    return sum(size * (1.0 if ord(ch) > 127 else 0.58) for ch in _s(text))


def wrap(text: str, max_px: float, size: float = FONT) -> list[str]:
    """幅で折る（禁則つき＝行の頭に「、」などを置かない・行末に開き括弧を置かない）。"""
    head = set("、。，．・：；？！）］｝」』】〕〉》’”,.:;?!)]}")
    tail = set("（［｛「『【〔〈《‘“([{")
    out: list[str] = []
    for seg in _s(text).split(chr(10)):
        cur = ""
        for ch in seg:
            if cur and text_width(cur + ch, size) > max_px:
                carry = ""
                if (ch in head or cur[-1] in tail) and len(cur) > 1 and cur[-1] not in head and cur[-2] not in tail:
                    carry, cur = cur[-1], cur[:-1]
                out.append(cur)
                cur = carry + ch
            else:
                cur += ch
        if cur:
            out.append(cur)
    return out


def _text(x: float, y: float, text: str, size: float = FONT, anchor: str = "start", weight: str = "normal", color: str = "ink") -> dict:
    return {"t": "text", "x": round(x, 1), "y": round(y, 1), "text": _s(text), "size": size,
            "anchor": anchor, "weight": weight, "color": _tone(color, "ink")}


def _rect(x: float, y: float, w: float, h: float, stroke: str = "acc", fill: str = "none", rx: float = 6.0, dash: bool = False) -> dict:
    return {"t": "rect", "x": round(x, 1), "y": round(y, 1), "w": round(w, 1), "h": round(h, 1),
            "stroke": _tone(stroke), "fill": _tone(fill, "none"), "rx": rx, "dash": bool(dash)}


def _line(points: list, stroke: str = "acc", width: float = 1.6, dash: bool = False, arrow: str = "none") -> dict:
    return {"t": "line", "points": [[round(float(x), 1), round(float(y), 1)] for x, y in points],
            "stroke": _tone(stroke), "width": width, "dash": bool(dash), "arrow": arrow if arrow in ("none", "end", "both") else "none"}


def _circle(cx: float, cy: float, r: float, fill: str = "acc", stroke: str = "acc") -> dict:
    return {"t": "circle", "cx": round(cx, 1), "cy": round(cy, 1), "r": r, "fill": _tone(fill), "stroke": _tone(stroke)}


# ---------------------------------------------------------------------------
# Mermaid の読み取り（A6）
# ---------------------------------------------------------------------------

_ID = r"[A-Za-z0-9_぀-ヿ㐀-鿿０-ｚ]+"
# 箱の形（中の文字だけ使う。形の違いは描かない）＝長い記法から先に試す
_SHAPES = (
    (r"\[\[", r"\]\]"), (r"\[\(", r"\)\]"), (r"\(\[", r"\]\)"), (r"\(\(\(", r"\)\)\)"), (r"\(\(", r"\)\)"),
    (r"\{\{", r"\}\}"), (r"\[/", r"/\]"), (r"\[\\", r"\\\]"), (r"\[", r"\]"), (r"\(", r"\)"), (r"\{", r"\}"), (r">", r"\]"),
)
_NODE_RE = re.compile(r"\s*(" + _ID + r")(?:" + "|".join(r"%s(.*?)%s" % pair for pair in _SHAPES) + r")?")
# 矢印（長い記法から先に試す）。種類は箱と矢印の図の kind に直す。
_EDGE_OPS = (
    ("<-->", "biarrow"), ("<==>", "biarrow"), ("-.->", "dashed"), ("-.-", "line"), ("==>", "arrow"), ("===", "line"),
    ("-->", "arrow"), ("---", "line"), ("--o", "arrow"), ("--x", "arrow"),
)
_MID_LABEL_RE = re.compile(r"\s*(--|==|-\.)\s+(.+?)\s+(-->|==>|\.->|---|===|-\.-)")


def _clean_label(text: str) -> str:
    text = _s(text).strip()
    if len(text) >= 2 and text[0] == text[-1] and text[0] in "\"'":
        text = text[1:-1]
    return re.sub(r"<br\s*/?>", chr(10), text, flags=re.I).strip()


def _lines(text: str) -> list[tuple[int, str]]:
    """%% の注記と空行を外した (行番号, 行)。"""
    out = []
    for number, raw in enumerate(_s(text).replace(chr(13), "").split(chr(10)), start=1):
        line = raw.split("%%", 1)[0].strip()
        if line:
            out.append((number, line))
    return out


def parse_mermaid(text: str) -> dict:
    """Mermaid の文字を読む。返り値＝{"kind", "direction", "nodes", "edges", "participants", "items", "warnings"}。

    kind は flowchart（graph も）・state・sequence・unknown のどれか。
    """
    result = {"kind": "unknown", "direction": "auto", "nodes": [], "edges": [], "participants": [], "items": [], "warnings": []}
    lines = _lines(text)
    if not lines:
        result["warnings"].append("Mermaid の文字が空")
        return result
    header = lines[0][1]
    word = header.split()[0] if header.split() else ""
    if word in ("flowchart", "graph"):
        result["kind"] = "flowchart"
        parts = header.split()
        if len(parts) > 1:
            result["direction"] = "horizontal" if parts[1].upper() in ("LR", "RL") else "vertical"
        _parse_flowchart(lines[1:], result)
    elif word.startswith("stateDiagram"):
        result["kind"] = "state"
        _parse_state(lines[1:], result)
    elif word == "sequenceDiagram":
        result["kind"] = "sequence"
        _parse_sequence(lines[1:], result)
    else:
        result["warnings"].append("1行目「%s」は読めない種類の図（読めるのは flowchart・graph・stateDiagram・sequenceDiagram）" % header[:40])
    return result


def _node_index(result: dict, node_id: str, label: str = "") -> None:
    for node in result["nodes"]:
        if node["id"] == node_id:
            if label and node["title"] == node_id:
                node["title"] = label
            return
    result["nodes"].append({"id": node_id, "title": label or node_id})


def _read_nodes(text: str, pos: int, result: dict) -> tuple[list[str], int]:
    """pos から「箱（& 箱）*」を読む。返り値＝(箱の id の一覧, 読み終えた位置)。読めなければ ([], pos)。"""
    ids: list[str] = []
    while True:
        m = _NODE_RE.match(text, pos)
        if not m:
            return ids, pos
        node_id = m.group(1)
        label = next((g for g in m.groups()[1:] if g is not None), "")
        _node_index(result, node_id, _clean_label(label))
        ids.append(node_id)
        pos = m.end()
        amp = re.match(r"\s*&\s*", text[pos:])
        if not amp:
            return ids, pos
        pos += amp.end()


def _read_edge(text: str, pos: int) -> tuple[str, str, int] | None:
    """pos から矢印を読む。返り値＝(kind, ラベル, 読み終えた位置)。"""
    m = _MID_LABEL_RE.match(text, pos)
    if m:
        closing = m.group(3)
        kind = "line" if closing in ("---", "===", "-.-") else ("dashed" if closing == ".->" else "arrow")
        return kind, _clean_label(m.group(2)), m.end()
    rest = text[pos:]
    stripped = rest.lstrip()
    offset = len(rest) - len(stripped)
    for op, kind in _EDGE_OPS:
        if stripped.startswith(op):
            end = pos + offset + len(op)
            label = ""
            lab = re.match(r"\s*\|([^|]*)\|", text[end:])
            if lab:
                label = _clean_label(lab.group(1))
                end += lab.end()
            return kind, label, end
    return None


_FLOW_SKIP = ("classDef", "class ", "style ", "linkStyle", "click ", "direction ")


def _parse_flowchart(lines: list[tuple[int, str]], result: dict) -> None:
    warned_subgraph = False
    for number, line in lines:
        if line.startswith(_FLOW_SKIP):
            continue
        if line.startswith("subgraph") or line == "end":
            if not warned_subgraph:
                result["warnings"].append("%d行目: subgraph（囲み）は描かない（中の箱と矢印は描く）" % number)
                warned_subgraph = True
            continue
        pos = 0
        left, pos = _read_nodes(line, pos, result)
        if not left:
            result["warnings"].append("%d行目: 読めない行を捨てた: %s" % (number, line[:60]))
            continue
        while pos < len(line):
            edge = _read_edge(line, pos)
            if edge is None:
                if line[pos:].strip() and line[pos:].strip() != ";":
                    result["warnings"].append("%d行目: 矢印の後ろが読めない: %s" % (number, line[pos:][:40]))
                break
            kind, label, pos = edge
            right, pos = _read_nodes(line, pos, result)
            if not right:
                result["warnings"].append("%d行目: 矢印の先の箱が読めない: %s" % (number, line[:60]))
                break
            for a in left:
                for b in right:
                    result["edges"].append({"from": a, "to": b, "label": label, "kind": kind})
            left = right
            if line[pos:].strip() in ("", ";"):
                break


_STATE_EDGE = re.compile(r"^(\[\*\]|" + _ID + r")\s*-->\s*(\[\*\]|" + _ID + r")\s*(?::\s*(.*))?$")
_STATE_ALIAS = re.compile(r'^state\s+"([^"]+)"\s+as\s+(' + _ID + r")\s*$")
_STATE_DESC = re.compile(r"^(" + _ID + r")\s*:\s*(.+)$")


def _parse_state(lines: list[tuple[int, str]], result: dict) -> None:
    warned = False
    for number, line in lines:
        m = _STATE_EDGE.match(line)
        if m:
            src, dst, label = m.group(1), m.group(2), _clean_label(m.group(3) or "")
            if src == "[*]":
                src = "__start__"
                _node_index(result, src, "開始")
            else:
                _node_index(result, src)
            if dst == "[*]":
                dst = "__end__"
                _node_index(result, dst, "終了")
            else:
                _node_index(result, dst)
            result["edges"].append({"from": src, "to": dst, "label": label, "kind": "arrow"})
            continue
        m = _STATE_ALIAS.match(line)
        if m:
            _node_index(result, m.group(2), _clean_label(m.group(1)))
            continue
        if line.startswith(("state ", "note ", "}", "--", "direction ", "classDef", "class ")) or line.endswith("{"):
            if not warned:
                result["warnings"].append("%d行目: 入れ子の状態・注記・並行の区切りは描かない" % number)
                warned = True
            continue
        m = _STATE_DESC.match(line)
        if m:
            _node_index(result, m.group(1))
            for node in result["nodes"]:
                if node["id"] == m.group(1):
                    node["text"] = (node.get("text", "") + chr(10) + _clean_label(m.group(2))).strip()
            continue
        if re.fullmatch(_ID, line):
            _node_index(result, line)
            continue
        result["warnings"].append("%d行目: 読めない行を捨てた: %s" % (number, line[:60]))


_SEQ_PART = re.compile(r"^(participant|actor)\s+(" + _ID + r")(?:\s+as\s+(.+))?$")
_SEQ_MSG = re.compile(r"^(" + _ID + r")\s*(-->>|->>|-->|->|--x|-x|--\)|-\))\s*[+-]?\s*(" + _ID + r")\s*:\s*(.*)$")
_SEQ_NOTE = re.compile(r"^[Nn]ote\s+(left of|right of|over)\s+(" + _ID + r")(?:\s*,\s*(" + _ID + r"))?\s*:\s*(.*)$")
_SEQ_BLOCK = ("alt", "else", "opt", "loop", "par", "and", "end", "rect", "critical", "break", "option")
_SEQ_SKIP = ("autonumber", "activate", "deactivate", "title", "box", "create", "destroy")


def _participant(result: dict, pid: str, label: str = "") -> None:
    for part in result["participants"]:
        if part["id"] == pid:
            if label:
                part["title"] = label
            return
    result["participants"].append({"id": pid, "title": label or pid})


def _parse_sequence(lines: list[tuple[int, str]], result: dict) -> None:
    warned_block = False
    for number, line in lines:
        first = line.split()[0] if line.split() else ""
        m = _SEQ_PART.match(line)
        if m:
            _participant(result, m.group(2), _clean_label(m.group(3) or ""))
            continue
        m = _SEQ_MSG.match(line)
        if m:
            src, op, dst, text = m.group(1), m.group(2), m.group(3), _clean_label(m.group(4))
            _participant(result, src)
            _participant(result, dst)
            result["items"].append({"type": "message", "from": src, "to": dst, "text": text,
                                    "dash": op.startswith("--"), "arrow": op not in ("->", "-->")})
            continue
        m = _SEQ_NOTE.match(line)
        if m:
            _participant(result, m.group(2))
            if m.group(3):
                _participant(result, m.group(3))
            result["items"].append({"type": "note", "where": m.group(1), "a": m.group(2), "b": m.group(3) or "",
                                    "text": _clean_label(m.group(4))})
            continue
        if first in _SEQ_BLOCK:
            if not warned_block:
                result["warnings"].append("%d行目: alt・loop などの枠は描かない（中のやりとりは描く）" % number)
                warned_block = True
            continue
        if first in _SEQ_SKIP:
            continue
        result["warnings"].append("%d行目: 読めない行を捨てた: %s" % (number, line[:60]))


def mermaid_to_diagram(parsed: dict) -> dict:
    """流れ図・状態の図を、箱と矢印の図（diagram の定義）に変える。開始と終了の箱は色を付ける。"""
    nodes = []
    for node in parsed.get("nodes") or []:
        item = {"id": node["id"], "title": node.get("title") or node["id"]}
        if node.get("text"):
            item["text"] = node["text"]
        if node["id"] == "__start__":
            item["tone"] = "good"
        elif node["id"] == "__end__":
            item["tone"] = "bad"
        nodes.append(item)
    edges = [dict(edge) for edge in parsed.get("edges") or []]
    return {"nodes": nodes, "edges": edges, "direction": parsed.get("direction") or "auto"}


# ---------------------------------------------------------------------------
# やりとりの図（A6・Q11 B）
# ---------------------------------------------------------------------------

def sequence_shapes(parsed: dict) -> dict:
    """やりとりの図の形。登場する人ごとの列（上に名前の箱・下へ縦の点線）と、行ごとのやりとりの矢印。"""
    parts = list(parsed.get("participants") or [])
    items = list(parsed.get("items") or [])
    shapes: list[dict] = []
    if not parts:
        return {"width": 0.0, "height": 0.0, "shapes": [], "warnings": ["やりとりの図に登場する人がいない"]}
    margin, gap, head_h, row_h = 12.0, 36.0, 0.0, 44.0
    col_w = [min(200.0, max(110.0, text_width(p["title"], FONT) + 28.0)) for p in parts]
    title_lines = [wrap(p["title"], w - 20.0, FONT) for p, w in zip(parts, col_w)]
    head_h = 20.0 + 18.0 * max(len(lines) for lines in title_lines)
    # 長いやりとりの文に合わせて列の間を広げる（隣どうしの文が列の間に収まるように）
    index = {p["id"]: i for i, p in enumerate(parts)}
    centers: list[float] = []
    x = margin
    for i, w in enumerate(col_w):
        centers.append(x + w / 2.0)
        x += w + gap
    for item in items:
        if item["type"] != "message":
            continue
        a, b = index.get(item["from"]), index.get(item["to"])
        if a is None or b is None or a == b:
            continue
        lo, hi = min(a, b), max(a, b)
        need = min(text_width(item["text"], SMALL) + 24.0, 360.0)
        have = centers[hi] - centers[lo]
        if need > have:
            push = (need - have) / (hi - lo)
            for k in range(lo + 1, len(centers)):
                centers[k] += push * (k - lo) if k <= hi else push * (hi - lo)
    width = centers[-1] + col_w[-1] / 2.0 + margin + 40.0
    y0 = margin
    for p, cx, w, lines in zip(parts, centers, col_w, title_lines):
        shapes.append(_rect(cx - w / 2.0, y0, w, head_h, stroke="acc", fill="none"))
        for k, line in enumerate(lines):
            shapes.append(_text(cx, y0 + 25.0 + 18.0 * k, line, FONT, "middle", "bold"))
    y = y0 + head_h + 30.0
    body: list[dict] = []
    for item in items:
        if item["type"] == "message":
            a, b = index.get(item["from"]), index.get(item["to"])
            if a is None or b is None:
                continue
            arrow = "end" if item["arrow"] else "none"
            if a == b:
                cx = centers[a]
                body.append(_line([(cx, y - 8), (cx + 34, y - 8), (cx + 34, y + 10), (cx + 2, y + 10)], "acc", 1.4, item["dash"], arrow))
                body.append(_text(cx + 40, y + 5, item["text"], SMALL, "start", "normal", "ink"))
                y += row_h + 6.0
                continue
            x1, x2 = centers[a], centers[b]
            body.append(_line([(x1, y), (x2 + (-3 if x2 > x1 else 3), y)], "acc", 1.4, item["dash"], arrow))
            for k, line in enumerate(wrap(item["text"], abs(x2 - x1) - 12.0, SMALL)[:3][::-1]):
                body.append(_text((x1 + x2) / 2.0, y - 7.0 - 15.0 * k, line, SMALL, "middle", "normal", "ink"))
            y += row_h
        else:
            a = index.get(item["a"])
            b = index.get(item["b"]) if item["b"] else a
            if a is None or b is None:
                continue
            lo, hi = min(centers[a], centers[b]), max(centers[a], centers[b])
            if item["where"] == "left of":
                lo, hi = centers[a] - 150.0, centers[a] - 10.0
            elif item["where"] == "right of":
                lo, hi = centers[a] + 10.0, centers[a] + 150.0
            else:
                lo, hi = lo - 60.0, hi + 60.0
            lines = wrap(item["text"], hi - lo - 16.0, SMALL)[:4]
            h = 12.0 + 16.0 * len(lines)
            body.append(_rect(lo, y - 14.0, hi - lo, h, stroke="warn", fill="warn", rx=3.0))
            for k, line in enumerate(lines):
                body.append(_text(lo + 8.0, y + 2.0 + 16.0 * k, line, SMALL, "start", "normal", "ink"))
            y += h + 18.0
    bottom = y
    for cx in centers:
        shapes.append(_line([(cx, y0 + head_h), (cx, bottom)], "muted", 1.0, True, "none"))
    shapes.extend(body)
    left, right = _x_extent(shapes)
    if left < margin:
        _translate(shapes, margin - left, 0.0)
        left, right = _x_extent(shapes)
    return {"width": round(max(right + margin, width, 120.0), 1), "height": round(bottom + margin, 1), "shapes": shapes, "warnings": []}


def _x_extent(shapes: list[dict]) -> tuple[float, float]:
    """形の一覧の左端と右端（文字は見積もりの幅を含める）。"""
    lefts, rights = [], []
    for s in shapes:
        if s["t"] == "rect":
            lefts.append(s["x"])
            rights.append(s["x"] + s["w"])
        elif s["t"] == "circle":
            lefts.append(s["cx"] - s["r"])
            rights.append(s["cx"] + s["r"])
        elif s["t"] == "line":
            lefts.extend(p[0] for p in s["points"])
            rights.extend(p[0] for p in s["points"])
        elif s["t"] == "text":
            w = text_width(s["text"], s["size"])
            x0 = s["x"] - (w if s["anchor"] == "end" else (w / 2.0 if s["anchor"] == "middle" else 0.0))
            lefts.append(x0)
            rights.append(x0 + w)
    return (min(lefts) if lefts else 0.0, max(rights) if rights else 0.0)


def _translate(shapes: list[dict], dx: float, dy: float) -> None:
    for s in shapes:
        if s["t"] in ("rect", "text"):
            s["x"] = round(s["x"] + dx, 1)
            s["y"] = round(s["y"] + dy, 1)
        elif s["t"] == "circle":
            s["cx"] = round(s["cx"] + dx, 1)
            s["cy"] = round(s["cy"] + dy, 1)
        elif s["t"] == "line":
            s["points"] = [[round(p[0] + dx, 1), round(p[1] + dy, 1)] for p in s["points"]]


# ---------------------------------------------------------------------------
# 魚の骨（A4）：結果を右の頭に、原因の分類を上下の骨に
# ---------------------------------------------------------------------------

def fishbone_shapes(spec: Any) -> dict:
    """入れるもの＝{"effect": "結果", "causes": [{"label": "分類", "items": ["原因", …], "tone": …}, …]}。"""
    spec = spec if isinstance(spec, dict) else {}
    warnings: list[str] = []
    effect = _s(spec.get("effect")).strip() or "結果"
    causes = [c for c in spec.get("causes") or [] if isinstance(c, dict) and _s(c.get("label")).strip()]
    if not causes:
        return {"width": 0.0, "height": 0.0, "shapes": [], "warnings": ["魚の骨に原因の分類（causes）が無い"]}
    if len(causes) > 8:
        warnings.append("原因の分類は8つまで描く（%d個のうち後ろを捨てた）" % len(causes))
        causes = causes[:8]
    top = causes[0::2]
    under = causes[1::2]
    slots = max(len(top), len(under))
    bone_w = 170.0
    head_w = min(180.0, max(110.0, text_width(effect, FONT) + 24.0))
    head_lines = wrap(effect, head_w - 20.0, FONT)
    spine_x0, spine_y = 16.0, 0.0
    item_lines = [[ln for item in (c.get("items") or [])[:6] for ln in wrap("・" + _s(item), bone_w - 30.0, SMALL)] for c in causes]
    max_items = max([len(lines) for lines in item_lines] + [1])
    arm = 46.0 + 15.0 * max_items
    spine_y = 20.0 + arm
    spine_x1 = spine_x0 + bone_w * slots + 30.0
    shapes: list[dict] = []
    shapes.append(_line([(spine_x0, spine_y), (spine_x1, spine_y)], "ink", 2.4, False, "end"))
    head_h = max(44.0, 16.0 + 18.0 * len(head_lines))
    shapes.append(_rect(spine_x1 + 4.0, spine_y - head_h / 2.0, head_w, head_h, stroke="bad", fill="none"))
    for k, line in enumerate(head_lines):
        shapes.append(_text(spine_x1 + 4.0 + head_w / 2.0, spine_y - head_h / 2.0 + 25.0 + 18.0 * k, line, FONT, "middle", "bold"))
    for row, group in ((-1, top), (1, under)):
        for k, cause in enumerate(group):
            lines = item_lines[causes.index(cause)]
            join_x = spine_x0 + bone_w * (k + 1)
            end_x, end_y = join_x - 40.0, spine_y + row * arm
            tone = _tone(cause.get("tone"), "acc")
            shapes.append(_line([(end_x, end_y), (join_x, spine_y)], tone, 1.8, False, "none"))
            label_y = end_y - 8.0 if row < 0 else end_y + 16.0
            shapes.append(_text(end_x - 6.0, label_y, _s(cause.get("label")), FONT, "start", "bold", tone))
            for j, line in enumerate(lines):
                frac = (j + 1.0) / (len(lines) + 1.0)
                ly = end_y + (spine_y - end_y) * frac
                lx = end_x + (join_x - end_x) * frac
                shapes.append(_text(lx - 8.0, ly + 4.0, line, SMALL, "end", "normal", "ink"))
    xs = [s["x"] for s in shapes if s["t"] == "text" and s["anchor"] == "end"]
    widths = [text_width(s["text"], s["size"]) for s in shapes if s["t"] == "text" and s["anchor"] == "end"]
    left = min([x - w for x, w in zip(xs, widths)] + [spine_x0]) - 8.0
    if left < 0:
        _translate(shapes, -left, 0.0)
        spine_x1 -= left
    width = spine_x1 + 4.0 + head_w + 12.0
    height = spine_y + arm + 30.0
    return {"width": round(width, 1), "height": round(height, 1), "shapes": shapes, "warnings": warnings}


# ---------------------------------------------------------------------------
# 滝の図（A4）：出発の量から、足し引きで最後の量へ
# ---------------------------------------------------------------------------

def _fmt(value: float) -> str:
    if abs(value - round(value)) < 1e-9:
        return "{:,}".format(int(round(value)))
    return "{:,.2f}".format(value).rstrip("0").rstrip(".")


def waterfall_shapes(spec: Any) -> dict:
    """入れるもの＝{"start": {"label", "value"}, "steps": [{"label", "value"（正＝足す・負＝引く）}, …],
    "end": {"label"}（無ければ「合計」）, "unit": "億円"}。最後の棒は道具が足し引きして出す。"""
    spec = spec if isinstance(spec, dict) else {}
    warnings: list[str] = []
    start = spec.get("start") if isinstance(spec.get("start"), dict) else {}
    start_value = _num(start.get("value"))
    if start_value is None:
        start_value = 0.0
        if spec.get("start") is not None:
            warnings.append("滝の図の出発の値（start.value）が数でないので0にした")
    steps = []
    for step in spec.get("steps") or []:
        value = _num(step.get("value")) if isinstance(step, dict) else None
        if value is None:
            warnings.append("滝の図の段「%s」の値が数でないので捨てた" % (_s(step.get("label")) if isinstance(step, dict) else _s(step))[:20])
            continue
        steps.append((_s(step.get("label")), value))
    if not steps:
        return {"width": 0.0, "height": 0.0, "shapes": [], "warnings": warnings + ["滝の図に足し引きの段（steps）が無い"]}
    unit = _s(spec.get("unit"))
    end = spec.get("end") if isinstance(spec.get("end"), dict) else {}
    bars = [(_s(start.get("label")) or "出発", 0.0, start_value, "acc")]
    total = start_value
    for label, value in steps:
        bars.append((label, total, total + value, "good" if value >= 0 else "bad"))
        total += value
    bars.append((_s(end.get("label")) or "合計", 0.0, total, "acc"))
    lo = min([0.0] + [min(a, b) for _, a, b, _ in bars])
    hi = max([0.0] + [max(a, b) for _, a, b, _ in bars])
    span = hi - lo or 1.0
    plot_h, top, left = 220.0, 24.0, 16.0
    bar_w = max(36.0, min(64.0, (MAX_WIDTH - 40.0) / len(bars) - 24.0))
    step_w = bar_w + 24.0
    y_of = lambda v: top + (hi - v) / span * plot_h  # noqa: E731
    shapes: list[dict] = [_line([(left, y_of(0.0)), (left + step_w * len(bars), y_of(0.0))], "muted", 1.0)]
    label_lines_max = 1
    for k, (label, a, b, tone) in enumerate(bars):
        x = left + 12.0 + step_w * k
        y1, y2 = y_of(max(a, b)), y_of(min(a, b))
        shapes.append(_rect(x, y1, bar_w, max(1.5, y2 - y1), stroke=tone, fill=tone, rx=2.0))
        value = b - a if 0 < k < len(bars) - 1 else b
        sign = "+" if (0 < k < len(bars) - 1 and value > 0) else ""
        shapes.append(_text(x + bar_w / 2.0, y1 - 6.0, sign + _fmt(value) + unit, SMALL, "middle", "bold", tone))
        if 0 < k < len(bars):
            prev_x = left + 12.0 + step_w * (k - 1) + bar_w
            shapes.append(_line([(prev_x, y_of(a if k < len(bars) - 1 else b)), (x, y_of(a if k < len(bars) - 1 else b))], "muted", 1.0, True))
        lines = wrap(label, step_w - 4.0, SMALL)[:3]
        label_lines_max = max(label_lines_max, len(lines))
        for j, line in enumerate(lines):
            shapes.append(_text(x + bar_w / 2.0, top + plot_h + 18.0 + 15.0 * j, line, SMALL, "middle", "normal", "ink"))
    width = left + step_w * len(bars) + 16.0
    height = top + plot_h + 18.0 + 15.0 * label_lines_max + 8.0
    return {"width": round(width, 1), "height": round(height, 1), "shapes": shapes, "warnings": warnings}


# ---------------------------------------------------------------------------
# ダンベル（A4）：いまの値と施策後の値を1本の棒でつなぐ
# ---------------------------------------------------------------------------

def dumbbell_shapes(spec: Any) -> dict:
    """入れるもの＝{"rows": [{"label", "before", "after"}, …], "unit", "labels": ["いま", "施策後"]}。
    両方が数の行だけを描く（片方しか無い行は捨てて warnings に書く＝値を作らない）。"""
    spec = spec if isinstance(spec, dict) else {}
    warnings: list[str] = []
    rows = []
    for row in spec.get("rows") or []:
        if not isinstance(row, dict):
            continue
        before, after = _num(row.get("before")), _num(row.get("after"))
        if before is None or after is None:
            warnings.append("ダンベルの行「%s」は両方の数が無いので描かない" % _s(row.get("label"))[:20])
            continue
        rows.append((_s(row.get("label")), before, after))
    if not rows:
        return {"width": 0.0, "height": 0.0, "shapes": [], "warnings": warnings + ["ダンベルに描ける行（before と after の両方が数）が無い"]}
    unit = _s(spec.get("unit"))
    labels = spec.get("labels") if isinstance(spec.get("labels"), list) and len(spec.get("labels")) >= 2 else ["いま", "施策後"]
    lo = min(min(b, a) for _, b, a in rows)
    hi = max(max(b, a) for _, b, a in rows)
    if lo > 0 and lo < hi * 0.5:
        lo = 0.0
    span = hi - lo or 1.0
    label_w = min(220.0, max(80.0, max(text_width(label, SMALL) for label, _, _ in rows) + 12.0))
    plot_x0, plot_x1 = 16.0 + label_w, MAX_WIDTH - 90.0
    row_h, top = 34.0, 40.0
    x_of = lambda v: plot_x0 + (v - lo) / span * (plot_x1 - plot_x0)  # noqa: E731
    shapes: list[dict] = []
    shapes.append(_circle(plot_x0, 16.0, 5.0, "muted", "muted"))
    shapes.append(_text(plot_x0 + 10.0, 20.0, _s(labels[0]), SMALL, "start", "normal", "muted"))
    shapes.append(_circle(plot_x0 + 110.0, 16.0, 5.0, "acc", "acc"))
    shapes.append(_text(plot_x0 + 120.0, 20.0, _s(labels[1]), SMALL, "start", "normal", "acc"))
    for k, (label, before, after) in enumerate(rows):
        y = top + row_h * k + 10.0
        shapes.append(_text(plot_x0 - 10.0, y + 4.0, label, SMALL, "end", "normal", "ink"))
        tone = "good" if after >= before else "bad"
        shapes.append(_line([(x_of(before), y), (x_of(after), y)], tone, 3.0))
        shapes.append(_circle(x_of(before), y, 5.5, "muted", "muted"))
        shapes.append(_circle(x_of(after), y, 5.5, "acc", "acc"))
        right = max(x_of(before), x_of(after))
        shapes.append(_text(right + 10.0, y + 4.0, "%s → %s%s" % (_fmt(before), _fmt(after), unit), SMALL, "start", "normal", "muted"))
    # 値の文字が右へはみ出す分だけ幅を足す
    width = max([MAX_WIDTH] + [s["x"] + text_width(s["text"], s["size"]) + 8.0 for s in shapes if s["t"] == "text" and s["anchor"] == "start"])
    height = top + row_h * len(rows) + 6.0
    return {"width": round(width, 1), "height": round(height, 1), "shapes": shapes, "warnings": warnings}


# ---------------------------------------------------------------------------
# 形の一覧 → SVG（HTML の頁）
# ---------------------------------------------------------------------------

_SVG_COLOR = {"ink": "var(--ink)", "muted": "var(--ink-3)", "acc": "var(--accent)", "good": "var(--pass)",
              "warn": "var(--warn)", "bad": "var(--fail)", "none": "none"}
_SVG_FILL = {"acc": "var(--accent-soft)", "good": "var(--pass-soft)", "warn": "var(--warn-soft)", "bad": "var(--fail-soft)",
             "muted": "var(--ink-3)", "ink": "var(--ink)", "none": "var(--surface)"}


def shapes_svg(geom: dict, title: str = "図", css_class: str = "fig-shapes") -> str:
    """形の一覧を SVG にする。文字は必ずエスケープし、色は役割の名前を頁の色の変数に直す（生の値は入らない）。"""
    if not isinstance(geom, dict) or not geom.get("shapes"):
        return ""
    width, height = float(geom.get("width") or 1.0), float(geom.get("height") or 1.0)
    parts: list[str] = []
    for s in geom["shapes"]:
        kind = s.get("t")
        if kind == "rect":
            dash = ' stroke-dasharray="5 4"' if s.get("dash") else ""
            fill = _SVG_FILL.get(s.get("fill"), "var(--surface)") if s.get("fill") != "none" else "var(--surface)"
            parts.append('<rect x="%.1f" y="%.1f" width="%.1f" height="%.1f" rx="%.1f" fill="%s" stroke="%s" stroke-width="1.5"%s></rect>'
                         % (s["x"], s["y"], s["w"], s["h"], float(s.get("rx") or 0), fill, _SVG_COLOR.get(s.get("stroke"), "var(--accent)"), dash))
        elif kind == "line":
            pts = s.get("points") or []
            if len(pts) < 2:
                continue
            d = "M " + " L ".join("%.1f %.1f" % (p[0], p[1]) for p in pts)
            color = _SVG_COLOR.get(s.get("stroke"), "var(--accent)")
            dash = ' stroke-dasharray="5 4"' if s.get("dash") else ""
            arrow = s.get("arrow")
            marker = ""
            if arrow in ("end", "both"):
                marker += ' marker-end="url(#fs-arrow-%s)"' % s.get("stroke", "acc")
            if arrow == "both":
                marker += ' marker-start="url(#fs-arrow-%s)"' % s.get("stroke", "acc")
            parts.append('<path d="%s" fill="none" stroke="%s" stroke-width="%.1f"%s%s></path>' % (d, color, float(s.get("width") or 1.6), dash, marker))
        elif kind == "circle":
            parts.append('<circle cx="%.1f" cy="%.1f" r="%.1f" fill="%s" stroke="%s"></circle>'
                         % (s["cx"], s["cy"], float(s.get("r") or 4), _SVG_COLOR.get(s.get("fill"), "var(--accent)"), _SVG_COLOR.get(s.get("stroke"), "var(--accent)")))
        elif kind == "text":
            anchor = {"middle": "middle", "end": "end"}.get(s.get("anchor"), "start")
            weight = ' font-weight="700"' if s.get("weight") == "bold" else ""
            parts.append('<text x="%.1f" y="%.1f" font-size="%.1f" text-anchor="%s" fill="%s"%s>%s</text>'
                         % (s["x"], s["y"], float(s.get("size") or FONT), anchor, _SVG_COLOR.get(s.get("color"), "var(--ink)"), weight, _escape(_s(s.get("text")))))
    used = sorted({s.get("stroke", "acc") for s in geom["shapes"] if s.get("t") == "line" and s.get("arrow") in ("end", "both")})
    markers = "".join(
        '<marker id="fs-arrow-%s" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">'
        '<path d="M 0 0 L 10 5 L 0 10 z" fill="%s"></path></marker>' % (tone, _SVG_COLOR.get(tone, "var(--accent)"))
        for tone in used if tone in _SVG_COLOR
    )
    # 幅の縮みの下限（style）は、載せる側（render_components.py の _figure_svg_block）が付ける。
    return ('<svg class="%s" viewBox="0 0 %.0f %.0f" width="%.0f" height="%.0f" role="img" aria-label="%s">'
            '<title>%s</title><defs>%s</defs>%s</svg>'
            % (_escape(_s(css_class), quote=True), width, height, width, height, _escape(_s(title), quote=True), _escape(_s(title)), markers, "".join(parts)))

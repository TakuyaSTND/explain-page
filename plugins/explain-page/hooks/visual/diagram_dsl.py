"""箱と矢印の図を1行記法で書くための変換器（担当F）。

目的＝JSONで `diagram` の宣言を書くと長い。1行1文の短い記法から、既存の
`diagram` 部品が読む辞書（`{"nodes":[...], "edges":[...]}`）へ決定論的に
変換する純関数を提供する。副作用・例外なし＝壊れた行は捨てずに warnings
へ行番号つきで積み、処理は続ける。

記法（1行1文。空行と行頭が `#` の行は無視）:
    A -> B                  矢印
    A -- B                  線（矢印なし）
    A <-> B                 両向き矢印
    A -.-> B                破線矢印
    A -> B : 条件が満たされた時   ラベル（コロンの後）
    A: 題 | 本文1行目 / 本文2行目  箱の定義（`|` で題と本文、本文は `/` で改行）
    A(icon=person)          属性（icon・tone・col・row。丸括弧でも角括弧でも可）
    A[tone=warn]            属性（複数は `A(icon=person, tone=warn)` のようにまとめてよい）
    A -> B -> C             連鎖は `A -> B` と `B -> C` の2本に展開

契約:
    def parse_diagram_text(text: str) -> dict
      返り値 = {"nodes": [...], "edges": [...], "warnings": [...]}
      nodes の要素 = {"id", "title", "text", 任意で "icon"/"tone"/"col"/"row"}
      edges の要素 = {"from", "to", "label", "kind"}
        kind は "arrow"（->）/ "line"（--）/ "biarrow"（<->）/ "dashed"（-.->）
      定義の無い id を参照した箱は自動生成（題＝id・本文なし）。
      不正な行は例外を投げず、warnings に "N行目: 理由: 元の行" を積んで読み飛ばす。
"""

from __future__ import annotations

import re

# 2026-09-10：id に日本語を許す（\w は漢字・かな・英数・_ を含み、ハイフンや記号は含まない）。
_ID_RE = re.compile(r"^\w+$")
_ATTR_LINE_RE = re.compile(r"^(\w+)((?:\s*[\(\[][^\)\]]*[\)\]])+)\s*$")
_ATTR_GROUP_RE = re.compile(r"[\(\[]([^\)\]]*)[\)\]]")

# 判定順が大事＝"-.->" と "<->" はどちらも部分文字列として "->" を含む。
# 先に長い（より具体的な）記法を確かめてから、素の矢印・線に落ちる。
_EDGE_OPS = ("-.->", "<->", "->", "--")
_EDGE_KIND = {
    "-.->": "dashed",
    "<->": "biarrow",
    "->": "arrow",
    "--": "line",
}

_ATTR_KEYS = ("icon", "tone", "col", "row")


def _valid_id(token: str) -> bool:
    return bool(_ID_RE.match(token))


def _ensure_node(nodes: dict, order: list, node_id: str) -> dict:
    """id の箱が無ければ既定値（題＝id・本文なし）で作って返す。"""
    if node_id not in nodes:
        nodes[node_id] = {"id": node_id, "title": node_id, "text": ""}
        order.append(node_id)
    return nodes[node_id]


def _parse_attr_pairs(group_text: str) -> list:
    pairs = []
    for chunk in group_text.split(","):
        chunk = chunk.strip()
        if not chunk or "=" not in chunk:
            continue
        key, _sep, value = chunk.partition("=")
        pairs.append((key.strip().lower(), value.strip()))
    return pairs


def _find_edge_op(line: str) -> str:
    for op in _EDGE_OPS:
        if op in line:
            return op
    return ""


def _handle_edge_line(line: str, line_no: int, nodes: dict, order: list, edges: list, warnings: list) -> None:
    op = _find_edge_op(line)
    chain_part, has_colon, label_part = line.partition(":")
    label = label_part.strip() if has_colon else ""
    chain_part = chain_part.strip()
    hops = [seg.strip() for seg in chain_part.split(op)]
    if len(hops) < 2 or any(not seg for seg in hops):
        warnings.append("%d行目: 不正な辺の記法です: %s" % (line_no, line))
        return
    bad_ids = [seg for seg in hops if not _valid_id(seg)]
    if bad_ids:
        warnings.append(
            "%d行目: 不正な id です（%s）: %s" % (line_no, ", ".join(bad_ids), line)
        )
        return
    kind = _EDGE_KIND[op]
    for left, right in zip(hops, hops[1:]):
        _ensure_node(nodes, order, left)
        _ensure_node(nodes, order, right)
        edges.append({"from": left, "to": right, "label": label, "kind": kind})


def _handle_attr_line(line: str, line_no: int, nodes: dict, order: list, warnings: list) -> bool:
    match = _ATTR_LINE_RE.match(line)
    if not match:
        return False
    node_id = match.group(1)
    if not _valid_id(node_id):
        warnings.append("%d行目: 不正な id です: %s" % (line_no, line))
        return True
    node = _ensure_node(nodes, order, node_id)
    groups_text = match.group(2)
    any_pair = False
    for group in _ATTR_GROUP_RE.finditer(groups_text):
        for key, value in _parse_attr_pairs(group.group(1)):
            any_pair = True
            if key in ("col", "row"):
                try:
                    node[key] = int(value)
                except ValueError:
                    warnings.append(
                        "%d行目: %s の値が数字ではありません: %s" % (line_no, key, value)
                    )
            elif key in _ATTR_KEYS:
                node[key] = value
            else:
                node[key] = value
    if not any_pair:
        warnings.append("%d行目: 属性が読み取れません: %s" % (line_no, line))
    return True


def _handle_definition_line(line: str, line_no: int, nodes: dict, order: list, warnings: list) -> bool:
    if ":" not in line:
        return False
    id_part, _sep, rest = line.partition(":")
    node_id = id_part.strip()
    if not _valid_id(node_id):
        warnings.append("%d行目: 不正な id です: %s" % (line_no, line))
        return True
    title_part, has_body, body_part = rest.partition("|")
    title = title_part.strip()
    text = ""
    if has_body:
        body_lines = [seg.strip() for seg in body_part.split("/")]
        body_lines = [seg for seg in body_lines if seg]
        text = "\n".join(body_lines)
    if not title and not text:
        warnings.append("%d行目: 題も本文も空です: %s" % (line_no, line))
        return True
    node = _ensure_node(nodes, order, node_id)
    node["title"] = title or node_id
    node["text"] = text
    return True


def parse_diagram_text(text: str) -> dict:
    """1行記法の文字列を `diagram` 部品の辞書に変換する。例外は投げない。"""
    nodes: dict = {}
    order: list = []
    edges: list = []
    warnings: list = []

    lines = (text or "").split("\n")
    for line_no, raw_line in enumerate(lines, start=1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue

        op = _find_edge_op(line)
        if op:
            _handle_edge_line(line, line_no, nodes, order, edges, warnings)
            continue

        if _handle_attr_line(line, line_no, nodes, order, warnings):
            continue

        if _handle_definition_line(line, line_no, nodes, order, warnings):
            continue

        warnings.append("%d行目: 認識できない記法です: %s" % (line_no, line))

    node_list = [nodes[node_id] for node_id in order]
    return {"nodes": node_list, "edges": edges, "warnings": warnings}

"""箱と矢印の図の「配置と経路の計算」だけを行う純関数（2026-09-09 新設・担当H）。

⚠️描画（SVG化）はここでは行わない＝担当Bが render_components.py の中で、
   この模块が返す座標だけを見てSVGを組む。生のSVGはどこにも受け取らない
   （安全性はレンダラー側の「渡された文字は必ずエスケープする」で保つ）。

きっかけ＝いまの矢印付き図（_diagram_block）は、辺の関係を無視して箱が
1行に並ぶ・SVGが幅に合わせて縮んで文字が潰れる・辺の from/to を番号で
書くと結び付かず矢印が1本も描かれない、という崩れが実測された。
見やすさが目的なので、まず「どこに置くか・どう線を引くか」を
テストできる形に切り出す。

契約＝`layout_diagram(nodes, edges, *, max_cols=3, direction="auto",
font_px=14, max_width=None) -> Layout`。標準ライブラリのみ・決定論・例外を投げない
（不正な入力は warnings に書いて捨てる。捨てても図そのものは作る）。

2026-09-12（担当H2・列幅720pxのはみ出しと層崩れの是正）：`max_width` を足した。
None なら従来どおり（既存の呼び出し・既存14本のテストの挙動は変えない）。
値を渡すと、辺のある図は「層（辺の向きからの深さ）を横に並べて幅に収まるなら横
（LR）、収まらなければ縦に並べて層ごとに積む（TB・はみ出す層は2段に折る）」の
専用エンジン（`_place_layered_fit` 以下）に切り替わる。循環を作る辺（戻る辺）は
層の計算からは外し、経路だけ盤面の外側を回る迂回に強制する。`Route.control` は
二次（`(cx, cy)`）に加え三次（`((c1x,c1y),(c2x,c2y))`）を返せるようにした＝
描画側は「入れ子なら三次・そうでなければ二次」で見分ける。
"""
from __future__ import annotations

import math
from collections import deque
from dataclasses import dataclass, field
from typing import Mapping, Optional, Sequence

# ---------------------------------------------------------------------------
# 見積りの定数（レンダラー側の DIAGRAM_* と役割は同じだが、この模块は独立に持つ）
# ---------------------------------------------------------------------------

TITLE_MAX_CHARS = 16
BODY_MAX_CHARS = 22

PAD_X = 14.0
PAD_Y = 12.0
LINE_H_TITLE = 20.0
LINE_H_BODY = 17.0
LINE_H_NOTE = 15.0
MIN_BOX_W = 64.0
MIN_BOX_H = 40.0
GAP_X = 54.0
GAP_Y = 30.0
MARGIN = 16.0

# 題・本文・注記の大きさ（font_px を基準にした比率）。
# 2026-09-26（実測で是正）：描く側（render_components.py の DIAGRAM_LAYOUT_TITLE／BODY／NOTE＝
# 14／13／12px・font_px=14 で呼ぶ）と同じ大きさで見積もる。以前は 1.02／0.88／0.75
# （＝14.3／12.3／10.5px）で、本文は5%、注記は12%小さく見積もっていた。
TITLE_SCALE = 14.0 / 14.0
BODY_SCALE = 13.0 / 14.0
NOTE_SCALE = 12.0 / 14.0

# 1字の幅（em）。2026-09-26（Chromium の getBBox で実測）：全角は13pxの本文で1字13.0px・
# 14pxの題で1字14.0px＝ちょうど1em（以前の見積もりは0.95em＝日本語の本文を約1割小さく
# 見積もり、箱の右の縁から最大40px はみ出していた）。英大文字は約0.67em、小文字は約0.47em
# （0.55em のままにして、小文字は少し大きめに見積もる＝はみ出す側に倒さない）。
CHAR_EM_ASCII = 0.55
CHAR_EM_ASCII_UPPER = 0.68
CHAR_EM_WIDE = 1.0
# 箱に記号（icon）があるとき、描く側は本文を 22px 右へずらす（render_components.py の text_indent）。
ICON_INDENT = 22.0

DEFAULT_MAX_COLS = 3
DEFAULT_FONT_PX = 14

# --- 2026-09-12 追加：列幅に収める専用エンジン（_place_layered_fit 以下）の定数 ---
# 既存の MARGIN/GAP_X/GAP_Y は「max_width 未指定」の旧経路専用のまま触らない
# （触ると既存14本の数値が変わる恐れがある）。新エンジンはこちらだけを使う。
PAGE_MARGIN = 12.0
LAYER_GAP_TB = 44.0
# 2026-09-12（担当H3・撮影で確認＝辺のラベルが箱の縁に触れる）：ラベルが乗る
# 層間だけは、ラベル1行ぶん＋余白が入るよう隙間を広げる。ラベルの無い層間は
# 従来どおり LAYER_GAP_TB のまま。
LABEL_LAYER_GAP_TB = 60.0
BOX_GAP = 24.0
# 2026-09-12（担当H3・撮影で確認＝折り返した段が層間と同じ隙間で、層の境目が
# 分かりにくい）：同じ層が2段以上に折り返したときの段内の隙間は、層間より
# 明らかに狭い BOX_GAP（横の箱どうしの隙間と同じ値）にする。
WRAP_ROW_GAP = BOX_GAP
LABEL_OFFSET = 10.0
LABEL_STAGGER = 12.0
LAYERED_MIN_BOX_W = 160.0
LAYERED_MAX_BOX_W = 260.0
# 2026-09-12（担当H3・撮影で確認＝折り返した段への辺が別の箱の裏を通る）：
# 経路が箱を突っ切っていないかの安全網の検査で、箱の矩形に足す余白。
BOX_SAFETY_PAD = 4.0
# 2026-09-12（担当H4・リードの実測＝迂回する辺が箱の上下中央から出入りし、
# 順方向の辺と出入口を共有して短い区間で重なる／層間の隙間を横に2回横切る）：
# 迂回する辺が同じ縦線（side_x）を複数本通るときに、外側へこの幅ずつずらして
# 重ねない。
DETOUR_SIDE_STAGGER = 14.0
# 2026-09-25：図の左端・上端の余白の下限。箱・経路・ラベルの見積り矩形のどれかが
# これより左（上）にあれば、`_compute_bounds` が図全体をずらす（viewBox の原点は0固定）。
VIEW_PAD = 2.0
# 辺のラベル（12px・縁取り付き）の見積り矩形の半高。
LABEL_HALF_H = 10.0
# 2026-09-25：1行の図（LR）の戻る辺は行の下を U 字に回る。出入口を箱の中心から
# ずらす幅と、2本目以降の横線を下へずらす幅（ラベルの高さ＋余白＝線とラベルが重ならない）。
UNDER_ROW_PORT = 10.0
UNDER_ROW_STAGGER = 24.0
# 2026-09-28：上の横線のラベル（線の12px下）と下の横線が横に重なるとき、下の横線をさらに
# 下げる幅＝ラベルから自分の線まで12px・下の線まで24px（どちらの線のラベルか読める）。
UNDER_ROW_LABEL_EXTRA = 12.0
# 2026-09-26：組み上がりが max_width を超えたときに、層の箱の幅の上限を下げて組み直す回数と、
# 1回に下げる幅の最小（行の中央揃えで、箱を少し狭めても全体の幅が同じだけは縮まないため）。
FIT_RETRIES = 6
FIT_MIN_STEP = 16.0


@dataclass
class Box:
    x: float
    y: float
    w: float
    h: float
    title_lines: list[str]
    body_lines: list[str]
    note_lines: list[str]
    num: str
    tone: str
    icon: str
    node_index: int


@dataclass
class Route:
    points: list[tuple[float, float]]
    label: str
    label_x: float
    label_y: float
    kind: str
    from_index: int
    to_index: int
    # None＝直線／折れ線（points がそのまま経路）。
    # (cx, cy)＝二次曲線の制御点が1つ（従来の curve=True の辺）。
    # ((c1x, c1y), (c2x, c2y))＝三次曲線（S字）の制御点が2つ（2026-09-12 追加・
    # max_width を渡した新エンジンが層をまたぐ斜めの辺に使う）。
    # 描画側は control[0] が tuple かどうかで二次／三次を見分ける。
    control: Optional[tuple] = None


@dataclass
class Layout:
    width: float
    height: float
    boxes: list[Box]
    routes: list[Route] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    font_px: int = DEFAULT_FONT_PX
    # "LR"（層を横一列）／"TB"（層を縦に積む）／"grid"（格子）／"free"（col/row 指定）。
    # 2026-09-12 追加・情報用（描画側の分岐には使っていない）。
    orientation: str = "grid"


def _empty_layout(warnings: list[str], font_px: int) -> Layout:
    return Layout(
        width=MARGIN * 2,
        height=MARGIN * 2,
        boxes=[],
        routes=[],
        warnings=warnings,
        font_px=font_px,
    )


def _safe_int(value: object, default: int) -> int:
    try:
        if isinstance(value, bool):
            return default
        v = int(value)  # type: ignore[arg-type]
        return v if v >= 1 else default
    except Exception:
        return default


def _safe_font_px(value: object) -> int:
    try:
        if isinstance(value, bool):
            return DEFAULT_FONT_PX
        v = float(value)  # type: ignore[arg-type]
        if v <= 0:
            return DEFAULT_FONT_PX
        return int(round(v))
    except Exception:
        return DEFAULT_FONT_PX


def _is_number(value: object) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _stringify(value: object) -> str:
    if value is None:
        return ""
    return str(value)


def _char_em(ch: str) -> float:
    if not ch.isascii():
        return CHAR_EM_WIDE
    return CHAR_EM_ASCII_UPPER if ch.isupper() else CHAR_EM_ASCII


def _line_em_width(line: str) -> float:
    if not line:
        return 0.0
    return sum(_char_em(ch) for ch in line)


def _is_word_char(ch: str) -> bool:
    """英数の連なり（折ってはいけない「単語」）を作る文字かどうか。"""
    return ch.isascii() and (ch.isalnum() or ch in "_-")


def _tokenize_for_wrap(seg: str) -> list[str]:
    """英数の連なりは1つの塊（単語）に、それ以外は1文字ずつのトークンに分ける。

    2026-09-12（撮影で確認＝「Herm／es」のように英単語が途中で割れた）：
    日本語は従来どおり字数で折ってよいが、英数の連なりだけは単語の切れ目
    （空白・記号・和文との境目）でしか折らない。1単語が上限文字数を超える
    ときだけ、やむを得ず字で割る。
    """
    tokens: list[str] = []
    i = 0
    n = len(seg)
    while i < n:
        ch = seg[i]
        if _is_word_char(ch):
            j = i + 1
            while j < n and _is_word_char(seg[j]):
                j += 1
            tokens.append(seg[i:j])
            i = j
        else:
            tokens.append(ch)
            i += 1
    return tokens


def _wrap(text: str, max_chars: int) -> list[str]:
    """改行は尊重し、それぞれの行を max_chars 文字で機械的に折る。切れは出さない。

    英数の連なり（単語）は、単語自体が limit を超えない限り途中で割らない。
    """
    lines: list[str] = []
    limit = max(1, int(max_chars))
    for seg in _stringify(text).split(chr(10)):
        if seg == "":
            continue
        cur = ""
        for tok in _tokenize_for_wrap(seg):
            if cur == "":
                if len(tok) <= limit:
                    cur = tok
                else:
                    # 1語が上限を超える＝やむを得ず字で折る
                    for start in range(0, len(tok), limit):
                        piece = tok[start:start + limit]
                        if start + limit >= len(tok):
                            cur = piece
                        else:
                            lines.append(piece)
                continue
            if len(cur) + len(tok) <= limit:
                cur += tok
            else:
                lines.append(cur)
                if len(tok) <= limit:
                    cur = tok
                else:
                    for start in range(0, len(tok), limit):
                        piece = tok[start:start + limit]
                        if start + limit >= len(tok):
                            cur = piece
                        else:
                            lines.append(piece)
        if cur != "":
            lines.append(cur)
    return lines


def _wrap_to_width(text: str, max_px: float, px_per_em: float) -> list[str]:
    """改行は尊重し、各行を見積もりの幅（px）で折る（2026-09-26 新設）。

    `_wrap` と同じく英数の連なり（単語）は切れ目でだけ折り、1語が幅を超えるときだけ
    字で割る。層の箱の幅を上限（LAYERED_MAX_BOX_W）で切ったとき、字数で折った行が
    その幅に入らない（実測＝22字の日本語の行が 284px・箱は 260px）のを防ぐために使う。
    """
    budget = max(px_per_em, float(max_px))
    lines: list[str] = []

    def width_of(s: str) -> float:
        return _line_em_width(s) * px_per_em

    for seg in _stringify(text).split(chr(10)):
        if seg == "":
            continue
        cur = ""
        for tok in _tokenize_for_wrap(seg):
            if width_of(cur + tok) <= budget:
                cur += tok
                continue
            if cur:
                lines.append(cur)
                cur = ""
            if width_of(tok) <= budget:
                cur = tok
                continue
            # 1語が幅を超える＝やむを得ず字で割る
            for ch in tok:
                if cur and width_of(cur + ch) > budget:
                    lines.append(cur)
                    cur = ""
                cur += ch
        if cur:
            lines.append(cur)
    return lines


def _refit_to_width(box: dict, width: float) -> None:
    """箱の幅を width に決めたあと、題・本文・注記をその幅に入るよう折り直し、高さを測り直す。"""
    font_px = float(box.get("_font_px", DEFAULT_FONT_PX))
    extra = ICON_INDENT if box.get("icon") else 0.0
    content_w = width - PAD_X * 2 - extra
    num = box.get("num") or ""
    title_budget = content_w - (_line_em_width(num) * font_px * TITLE_SCALE + 8.0 if num else 0.0)
    box["title_lines"] = _wrap_to_width(box.get("_raw_title", ""), title_budget, font_px * TITLE_SCALE)
    box["body_lines"] = _wrap_to_width(box.get("_raw_text", ""), content_w, font_px * BODY_SCALE)
    box["note_lines"] = _wrap_to_width(box.get("_raw_note", ""), content_w, font_px * NOTE_SCALE)
    _, height = _measure(
        box["title_lines"], box["body_lines"], box["note_lines"], num, box.get("icon", ""), font_px
    )
    box["w"] = width
    box["h"] = height


def _measure(
    title_lines: Sequence[str],
    body_lines: Sequence[str],
    note_lines: Sequence[str],
    num: str,
    icon: str,
    font_px: float,
) -> tuple[float, float]:
    title_size = font_px * TITLE_SCALE
    body_size = font_px * BODY_SCALE
    note_size = font_px * NOTE_SCALE
    widths = [_line_em_width(line) * title_size for line in title_lines]
    widths += [_line_em_width(line) * body_size for line in body_lines]
    widths += [_line_em_width(line) * note_size for line in note_lines]
    extra = 0.0
    if num:
        extra += _line_em_width(num) * title_size + 8.0
    if icon:
        extra += ICON_INDENT
    content_w = max(widths) if widths else 0.0
    width = max(content_w + extra + PAD_X * 2, MIN_BOX_W)
    height = (
        PAD_Y * 2
        + len(title_lines) * LINE_H_TITLE
        + len(body_lines) * LINE_H_BODY
        + len(note_lines) * LINE_H_NOTE
    )
    height = max(height, MIN_BOX_H)
    return width, height


# ---------------------------------------------------------------------------
# 箱の下ごしらえ
# ---------------------------------------------------------------------------

def _prepare_nodes(nodes: Sequence[object], font_px: float) -> tuple[list[dict], dict[str, int]]:
    """入力の nodes を、置き場所を決める前の下ごしらえ（大きさ・行）に直す。

    ⚠️ここではノードを一切間引かない＝辺の from/to は「入力順の0始まり索引」
       を参照するので、間引くと索引がずれて別の箱に矢印が刺さる事故になる。
    """
    prepared: list[dict] = []
    id_map: dict[str, int] = {}
    for index, raw in enumerate(nodes or []):
        item = raw if isinstance(raw, Mapping) else {"title": _stringify(raw)}
        given_id = item.get("id")
        if given_id is not None and _stringify(given_id) != "":
            id_map[_stringify(given_id)] = index
        title = _stringify(item.get("title"))
        text = _stringify(item.get("text"))
        note = _stringify(item.get("note"))
        num = _stringify(item.get("num"))
        icon = _stringify(item.get("icon"))
        tone = _stringify(item.get("tone") or "neutral").lower()
        title_lines = _wrap(title, TITLE_MAX_CHARS)
        body_lines = _wrap(text, BODY_MAX_CHARS)
        note_lines = _wrap(note, BODY_MAX_CHARS)
        width, height = _measure(title_lines, body_lines, note_lines, num, icon, font_px)
        prepared.append(
            {
                "index": index,
                "id": _stringify(given_id) if given_id is not None else "",
                "num": num,
                "title_lines": title_lines,
                "body_lines": body_lines,
                "note_lines": note_lines,
                "tone": tone,
                "icon": icon,
                "w": width,
                "h": height,
                "x": 0.0,
                "y": 0.0,
                # 2026-09-26：幅を上限で切った箱を折り直すための元の文（`_refit_to_width`）。
                "_raw_title": title,
                "_raw_text": text,
                "_raw_note": note,
                "_font_px": font_px,
            }
        )
    return prepared, id_map


def _resolve_index(ref: object, n: int, id_map: Mapping[str, int]) -> Optional[int]:
    if isinstance(ref, bool):
        return None
    if isinstance(ref, int):
        return ref if 0 <= ref < n else None
    if isinstance(ref, str):
        if ref in id_map:
            return id_map[ref]
        stripped = ref.strip()
        if stripped.lstrip("-").isdigit():
            v = int(stripped)
            if 0 <= v < n:
                return v
        return None
    return None


def _resolve_edges(
    edges: Sequence[object], n: int, id_map: Mapping[str, int], warnings: list[str]
) -> list[dict]:
    resolved: list[dict] = []
    for i, raw in enumerate(edges or []):
        if not isinstance(raw, Mapping):
            warnings.append("edges[%d]: 形式が辞書でないため捨てた" % i)
            continue
        from_ref = raw.get("from")
        to_ref = raw.get("to")
        from_index = _resolve_index(from_ref, n, id_map)
        to_index = _resolve_index(to_ref, n, id_map)
        if from_index is None or to_index is None:
            warnings.append(
                "edges[%d]: from=%r to=%r の参照先が見つからないため捨てた"
                % (i, from_ref, to_ref)
            )
            continue
        resolved.append(
            {
                "from_index": from_index,
                "to_index": to_index,
                "label": _stringify(raw.get("label")),
                "kind": _stringify(raw.get("kind") or "arrow").lower(),
                "curve": bool(raw.get("curve")),
            }
        )
    return resolved


# ---------------------------------------------------------------------------
# 配置（グリッド・自由配置・鎖1行・層配置）
# ---------------------------------------------------------------------------

def _apply_grid_positions(boxes: list[dict], col_of: Sequence[int], row_of: Sequence[int]) -> None:
    n = len(boxes)
    cols = sorted(set(col_of))
    rows = sorted(set(row_of))
    col_w = {c: max([boxes[i]["w"] for i in range(n) if col_of[i] == c], default=MIN_BOX_W) for c in cols}
    row_h = {r: max([boxes[i]["h"] for i in range(n) if row_of[i] == r], default=MIN_BOX_H) for r in rows}
    x_of: dict[int, float] = {}
    cursor = MARGIN
    for c in cols:
        x_of[c] = cursor
        cursor += col_w[c] + GAP_X
    y_of: dict[int, float] = {}
    cursor = MARGIN
    for r in rows:
        y_of[r] = cursor
        cursor += row_h[r] + GAP_Y
    for i in range(n):
        c, r = col_of[i], row_of[i]
        boxes[i]["x"] = x_of[c] + (col_w[c] - boxes[i]["w"]) / 2.0
        boxes[i]["y"] = y_of[r] + (row_h[r] - boxes[i]["h"]) / 2.0
        # 経路が「間の層を飛ばす辺」を避けられるように、置いた場所の行・列も覚えておく
        # （x/y の中心が揃っているだけでは、間に別の箱が挟まっているかどうか分からない）。
        boxes[i]["_row"] = r
        boxes[i]["_col"] = c


def _has_explicit_placement(raw_nodes: Sequence[object]) -> bool:
    for raw in raw_nodes or []:
        if isinstance(raw, Mapping):
            for key in ("col", "row", "x", "y"):
                if raw.get(key) is not None:
                    return True
    return False


def _place_grid(boxes: list[dict], max_cols: int) -> None:
    n = len(boxes)
    cols = _safe_int(max_cols, DEFAULT_MAX_COLS)
    col_of = [i % cols for i in range(n)]
    row_of = [i // cols for i in range(n)]
    _apply_grid_positions(boxes, col_of, row_of)


def _place_single_row(boxes: list[dict], order: Sequence[int]) -> None:
    n = len(boxes)
    pos_of = {node: i for i, node in enumerate(order)}
    col_of = [pos_of.get(i, i) for i in range(n)]
    row_of = [0] * n
    _apply_grid_positions(boxes, col_of, row_of)


def _place_single_column(boxes: list[dict]) -> None:
    n = len(boxes)
    col_of = [0] * n
    row_of = list(range(n))
    _apply_grid_positions(boxes, col_of, row_of)


def _place_free(boxes: list[dict], raw_nodes: Sequence[object]) -> None:
    n = len(boxes)
    col_of: list[int] = []
    row_of: list[int] = []
    raws = list(raw_nodes or [])
    for i in range(n):
        raw = raws[i] if i < len(raws) and isinstance(raws[i], Mapping) else {}
        c = raw.get("col")
        r = raw.get("row")
        col_of.append(int(c) if _is_number(c) else i)
        row_of.append(int(r) if _is_number(r) else 0)
    _apply_grid_positions(boxes, col_of, row_of)
    for i in range(n):
        raw = raws[i] if i < len(raws) and isinstance(raws[i], Mapping) else {}
        xv = raw.get("x")
        yv = raw.get("y")
        if _is_number(xv):
            boxes[i]["x"] = float(xv)  # type: ignore[arg-type]
        if _is_number(yv):
            boxes[i]["y"] = float(yv)  # type: ignore[arg-type]


def _assign_layers(n: int, edges: Sequence[dict]) -> list[int]:
    """辺の向きから層を決める（最長経路の考え方＝Kahn法の応用）。循環があっても止まらない。"""
    indeg = [0] * n
    out_adj: list[list[int]] = [[] for _ in range(n)]
    for e in edges:
        a, b = e["from_index"], e["to_index"]
        if a == b:
            continue
        out_adj[a].append(b)
        indeg[b] += 1
    layer = [0] * n
    work_indeg = indeg[:]
    processed = [False] * n
    queue: deque[int] = deque(i for i in range(n) if work_indeg[i] == 0)
    while queue:
        u = queue.popleft()
        if processed[u]:
            continue
        processed[u] = True
        for v in out_adj[u]:
            if layer[v] < layer[u] + 1:
                layer[v] = layer[u] + 1
            work_indeg[v] -= 1
            if work_indeg[v] == 0 and not processed[v]:
                queue.append(v)
    remaining = [i for i in range(n) if not processed[i]]
    if remaining:
        # 循環などで抜けきらなかった箱は、そこまでの最大層のもう1つ下にまとめて置く
        cur_max = max(layer) if n else 0
        cur_max += 1
        for i in remaining:
            layer[i] = cur_max
    return layer


def _reorder_layers(layers: dict[int, list[int]], edges: Sequence[dict]) -> dict[int, list[int]]:
    """交差を減らすための重心並べ替え（前の層との対応だけを見る簡易版）。"""
    preds: dict[int, list[int]] = {}
    for e in edges:
        preds.setdefault(e["to_index"], []).append(e["from_index"])
    keys = sorted(layers.keys())
    for idx in range(1, len(keys)):
        prev_key = keys[idx - 1]
        cur_key = keys[idx]
        pos = {node: order for order, node in enumerate(layers[prev_key])}
        members = layers[cur_key]
        member_pos = {node: order for order, node in enumerate(members)}

        def sort_key(node: int, _pos=pos, _member_pos=member_pos) -> tuple[int, float]:
            ps = [_pos[p] for p in preds.get(node, []) if p in _pos]
            if ps:
                return (0, sum(ps) / len(ps))
            return (1, float(_member_pos[node]))

        layers[cur_key] = sorted(members, key=sort_key)
    return layers


def _place_layered(boxes: list[dict], edges: Sequence[dict], max_cols: int) -> None:
    n = len(boxes)
    cols = _safe_int(max_cols, DEFAULT_MAX_COLS)
    layer_of = _assign_layers(n, edges)
    layers: dict[int, list[int]] = {}
    for i in range(n):
        layers.setdefault(layer_of[i], []).append(i)
    layers = _reorder_layers(layers, edges)
    col_of = [0] * n
    row_of = [0] * n
    phys_row = 0
    for layer_key in sorted(layers.keys()):
        members = layers[layer_key]
        for start in range(0, len(members), cols):
            chunk = members[start:start + cols]
            for col_idx, node_i in enumerate(chunk):
                col_of[node_i] = col_idx
                row_of[node_i] = phys_row
            phys_row += 1
    _apply_grid_positions(boxes, col_of, row_of)


def _detect_chain(
    n: int, edges: Sequence[dict], directed_edges: Optional[Sequence[dict]] = None
) -> Optional[list[int]]:
    """辺が『枝分かれの無い一本の鎖』で、しかも辺の向きが揃っている（A→B→C）なら
    その順番を返す。それ以外は None。

    2026-09-28（実測＝1つの箱から2つへ広がる形 A→B・A→C を、向きを無視して B–A–C の
    鎖と見て横一列に並べた。真ん中の A から矢印が左右へ外向きに出て、390px では右端の
    箱が横スクロールの先に隠れた）：向きを無視した隣り合いで一本道になることに加え、
    隣どうしのすべての組に「並べる順の向き」の辺が1本以上あることを求める。
    広がる形（A→B・A→C）と集まる形（B→A・C→A）はどちらの順でも満たさない＝None。

    directed_edges＝向きを確かめる辺（既定＝edges 全部）。列幅に収める組み方は「戻る辺を
    除いた辺」を渡す＝層の計算と同じ辺で向きを見る（戻る辺 old→anyone を足しただけで
    old→anyone→pub を鎖と見て、根の anyone が真ん中に来るのを防ぐ）。戻る辺は隣どうしの
    組にある限り残してよい（行の下を回して描く）。
    """
    if n == 0:
        return None
    if n == 1:
        return [0]
    adj: dict[int, set[int]] = {i: set() for i in range(n)}
    for e in edges:
        a, b = e["from_index"], e["to_index"]
        if a == b:
            continue
        adj[a].add(b)
        adj[b].add(a)
    if any(len(adj[i]) == 0 for i in range(n)):
        return None
    if any(len(adj[i]) > 2 for i in range(n)):
        return None
    endpoints = [i for i in range(n) if len(adj[i]) == 1]
    if len(endpoints) != 2:
        return None
    start = endpoints[0]
    order = [start]
    visited = {start}
    prev: Optional[int] = None
    current = start
    while len(order) < n:
        nxt = None
        for cand in adj[current]:
            if cand != prev and cand not in visited:
                nxt = cand
                break
        if nxt is None:
            return None
        order.append(nxt)
        visited.add(nxt)
        prev, current = current, nxt
    if len(order) != n:
        return None
    pool = edges if directed_edges is None else directed_edges
    directed = {(e["from_index"], e["to_index"]) for e in pool}
    # 見つけた順（小さい番号の端から）を先に試し、駄目なら逆順を試す＝向きの揃った
    # 鎖では従来と同じ順を返す。
    for candidate in (order, order[::-1]):
        if all((candidate[k], candidate[k + 1]) in directed for k in range(n - 1)):
            return candidate
    return None


def _find_back_edge_indices(n: int, edges: Sequence[dict]) -> set[int]:
    """DFSで「戻る辺」（循環を作る辺・自己ループ含む）の索引集合を返す。

    層（辺の向きからの深さ）はこの索引を除いた辺だけで計算する（②の要件＝
    戻る辺は層の計算では無視する）。再帰は使わない（大きい図で深さ制限に
    当たらないため・この模块全体の「例外を外に投げない」という前提を守るため）。
    """
    adj: list[list[tuple[int, int]]] = [[] for _ in range(n)]
    for idx, e in enumerate(edges):
        a, b = e["from_index"], e["to_index"]
        adj[a].append((b, idx))
    color = [0] * n  # 0=white 1=gray 2=black
    back: set[int] = set()
    for start in range(n):
        if color[start] != 0:
            continue
        color[start] = 1
        stack: list[tuple[int, "list[tuple[int,int]]", int]] = [(start, adj[start], 0)]
        while stack:
            node, out, pos = stack[-1]
            advanced = False
            while pos < len(out):
                v, idx = out[pos]
                pos += 1
                if v == node:
                    back.add(idx)  # 自己ループ
                    continue
                if color[v] == 1:
                    back.add(idx)
                elif color[v] == 0:
                    color[v] = 1
                    stack[-1] = (node, out, pos)
                    stack.append((v, adj[v], 0))
                    advanced = True
                    break
            if not advanced:
                if pos >= len(out):
                    color[node] = 2
                    stack.pop()
                else:
                    stack[-1] = (node, out, pos)
    return back


# ---------------------------------------------------------------------------
# 経路（辺の折れ線）
# ---------------------------------------------------------------------------

def _detour_vertical(
    source: Mapping[str, object],
    target: Mapping[str, object],
    scx: float,
    scy: float,
    tcx: float,
    tcy: float,
    side_x: float,
    curve: bool,
) -> tuple[list[tuple[float, float]], Optional[tuple]]:
    """層を縦に2つ以上飛ばす辺（または戻る辺）の迂回経路＝盤面の右側（side_x）を回る。

    2026-09-12（担当H4・リードが実測＝箱の上下中央から出入りする旧経路は、
    順方向の辺（同じ上下中央の出入口を使う）と短い区間で重なり、かつ横線が
    層間の隙間を2回横切ってラベルに接近していた）：迂回する辺は箱の「上下
    中央」ではなく「右側面の中点」から出て「右側面の中点」へ入る。
    経路＝出発の右側面中点→（右へ）→迂回の縦線（side_x）→（下向きまたは
    上向き）→到着の右側面中点（左向きに入る＝side_x が常にどの箱の右端
    よりも右にあるので、最後の一区間は必ず左向きになる）。
    scx・tcx（呼び出し側が渡す箱の中心x）はこの経路では使わない＝
    scy・tcy がそのまま箱の上下中央のy（呼び出し側の実測どおり）なので、
    そのまま端点のyとして使う。
    """
    s_right = source["x"] + source["w"]
    t_right = target["x"] + target["w"]
    start = (s_right, scy)
    end = (t_right, tcy)
    if curve:
        return [start, end], (side_x, (scy + tcy) / 2.0)
    points = [start, (side_x, scy), (side_x, tcy), end]
    return points, None


def _detour_under_row(
    source: Mapping[str, object],
    target: Mapping[str, object],
    scx: float,
    tcx: float,
    bottom_y: float,
    curve: bool,
    s_slot: int = 0,
    t_slot: int = 0,
) -> tuple[list[tuple[float, float]], Optional[tuple]]:
    """全部の箱が1行に並ぶ図（LR）の戻る辺＝行の下を U 字に回る（2026-09-25 新設）。

    撮影で確認＝右側面を回る迂回（`_detour_vertical`）は箱が縦に積まれる前提なので、
    1行の図では最後の区間が同じ行の箱を横に突っ切り、ラベルが箱の見出しに重なった
    （例＝「本棚の画面」が「本棚の画像を返す」に見えた）。
    経路＝出発の箱の下辺→（下へ）→行の下の横線（bottom_y）→到着の箱の下辺（上向きに入る）。
    出入口は箱の中心から UNDER_ROW_PORT だけずらす＝同じ箱が「戻る辺の到着点」と
    「別の戻る辺の出発点」を兼ねるとき、2本の縦線が重ならず、横線とも交わらない
    （左へ戻る辺は出発を中心の左・到着を中心の右に置く）。

    2026-09-28（横1行の明示で、右へ間の箱を飛ばす辺もここを通るようになった。実測＝右へ
    飛ばす辺の出口と、左へ戻る辺の入口が同じ点になり縦の線が重なった）：中心からの距離を
    UNDER_ROW_PORT の倍数で分ける＝左へ戻る辺は奇数倍（1・3・5…）、右へ飛ばす辺は偶数倍
    （2・4・6…）。同じ箱の同じ側に出入口が2つ以上あるときは s_slot／t_slot（0始まり）で
    さらに外へずらす。s_slot＝t_slot＝0 の左へ戻る辺は従来と同じ位置。箱の縁から
    BOX_SAFETY_PAD より外へは出さない。
    """
    leftward = tcx < scx
    base = 1 if leftward else 2
    s_unit = min(UNDER_ROW_PORT, float(source["w"]) / 4.0)
    t_unit = min(UNDER_ROW_PORT, float(target["w"]) / 4.0)
    s_port = min(s_unit * (base + 2 * s_slot), float(source["w"]) / 2.0 - BOX_SAFETY_PAD)
    t_port = min(t_unit * (base + 2 * t_slot), float(target["w"]) / 2.0 - BOX_SAFETY_PAD)
    sx = scx - s_port if leftward else scx + s_port
    tx = tcx + t_port if leftward else tcx - t_port
    start = (sx, source["y"] + source["h"])
    end = (tx, target["y"] + target["h"])
    if curve:
        return [start, end], ((sx + tx) / 2.0, bottom_y)
    return [start, (sx, bottom_y), (tx, bottom_y), end], None


def _route_points_row_primary(
    source: Mapping[str, object],
    target: Mapping[str, object],
    curve: bool,
    side_x: float,
    bottom_y: float,
    smooth: bool = False,
    force_far: bool = False,
    under_row: bool = False,
    port_slots: tuple[int, int] = (0, 0),
) -> tuple[list[tuple[float, float]], Optional[tuple]]:
    """2つの箱を結ぶ経路（_row を「層＝主軸」とみなす向き）。

    port_slots＝行の下を回るときの (出発, 到着) の出入口の番号（`_detour_under_row`）。

    under_row＝True（2026-09-25・全部の箱が1行に並ぶ LR の図の戻る辺）のときは、
    右側面を回る迂回の代わりに、行の下を U 字に回る（`_detour_under_row`）。行・列が隣り合っていれば
    直線／小さな折れ線で足りるが、層を2つ以上飛ばす辺は、間の層に別の箱がある恐れが
    あるので盤面の外側（side_x／bottom_y）を、行間・列間の隙間だけを通って迂回する
    （隙間には箱が無いことが置き方の前提なので、必ず避けられる）。

    smooth＝True のときは「隣どうしの層をまたぐが列がずれる」対角線のケースを、
    直角の折れ線でなく三次ベジェのS字にする（2026-09-12・max_width指定時の新エンジン
    専用。控えめに、既存の smooth=False の呼び出しでは今までどおり）。

    force_far＝True のときは行・列の実際の近さに関わらず必ず側面へ迂回する
    （2026-09-12・戻る辺（循環を作る辺）は隣の層どうしでも必ず迂回で描く）。
    """
    scx = source["x"] + source["w"] / 2.0
    scy = source["y"] + source["h"] / 2.0
    tcx = target["x"] + target["w"] / 2.0
    tcy = target["y"] + target["h"] / 2.0

    if force_far:
        if under_row:
            return _detour_under_row(
                source, target, scx, tcx, bottom_y, curve, port_slots[0], port_slots[1]
            )
        return _detour_vertical(source, target, scx, scy, tcx, tcy, side_x, curve)

    s_row, s_col = source.get("_row", 0), source.get("_col", 0)
    t_row, t_col = target.get("_row", 0), target.get("_col", 0)
    row_gap = abs(s_row - t_row)
    col_gap = abs(s_col - t_col)
    same_row = s_row == t_row
    same_col = s_col == t_col

    if same_row and col_gap <= 1:
        if tcx >= scx:
            start = (source["x"] + source["w"], scy)
            end = (target["x"], tcy)
        else:
            start = (source["x"], scy)
            end = (target["x"] + target["w"], tcy)
        return [start, end], None

    if same_col and row_gap <= 1:
        if tcy >= scy:
            start = (scx, source["y"] + source["h"])
            end = (tcx, target["y"])
        else:
            start = (scx, source["y"])
            end = (tcx, target["y"] + target["h"])
        return [start, end], None

    if not same_row and not same_col and row_gap <= 1:
        # 隣どうしの層をまたぐだけ＝行間の隙間を通せば箱には当たらない
        if tcy >= scy:
            start = (scx, source["y"] + source["h"])
            end = (tcx, target["y"])
        else:
            start = (scx, source["y"])
            end = (tcx, target["y"] + target["h"])
        mid_y = (start[1] + end[1]) / 2.0
        if smooth:
            control = ((start[0], mid_y), (end[0], mid_y))
            return [start, end], control
        if curve:
            return [start, end], (end[0], start[1])
        return [start, (start[0], mid_y), (end[0], mid_y), end], None

    if row_gap > 1:
        # 2層以上を飛ばす＝同じ列（またはその途中）に別の箱が挟まっている恐れ。
        return _detour_vertical(source, target, scx, scy, tcx, tcy, side_x, curve)

    # 残るのは「同じ行のまま列を2つ以上飛ばす」まれなケース＝盤面の下（bottom_y）を迂回する。
    # 2026-09-12（担当H4・_detour_vertical と対称の直し＝LR の主軸である左右中央を
    # 順方向の辺（same_row and col_gap<=1）と共有すると同じ穴が起きるため）：
    # 出発の箱の下辺中点から下へ出て、到着の箱の下辺中点へ上向きに入る。
    start = (scx, source["y"] + source["h"])
    end = (tcx, target["y"] + target["h"])
    if curve:
        return [start, end], ((scx + tcx) / 2.0, bottom_y)
    points = [start, (scx, bottom_y), (tcx, bottom_y), end]
    return points, None


def _label_anchor(
    points: Sequence[tuple[float, float]], offset: bool = False
) -> tuple[float, float]:
    """折れ線のいちばん長い区間の中点。点が1つ以下なら先頭（または原点）。

    offset＝True のときは、その区間と垂直な向きに少しずらす（2026-09-12・
    「線の上に載せず脇に置く」＝縦の線なら右側、横の線なら上側）。
    """
    if not points:
        return (0.0, 0.0)
    if len(points) == 1:
        return points[0]
    best = (points[0], points[1])
    best_len = -1.0
    for a, b in zip(points, points[1:]):
        seg = abs(b[0] - a[0]) + abs(b[1] - a[1])
        if seg > best_len:
            best_len = seg
            best = (a, b)
    mx = (best[0][0] + best[1][0]) / 2.0
    my = (best[0][1] + best[1][1]) / 2.0
    if not offset:
        return (mx, my)
    dx = best[1][0] - best[0][0]
    dy = best[1][1] - best[0][1]
    if abs(dy) >= abs(dx):
        return (mx + LABEL_OFFSET, my)
    return (mx, my - LABEL_OFFSET)


# ---------------------------------------------------------------------------
# 2026-09-12（担当H3）：ラベルの置き場所（層をまたぐ辺専用）・経路の安全網
# ---------------------------------------------------------------------------
#
# 撮影で確認された残りの粗＝①辺のラベルが出発点の箱の縁に触れる
# ②折り返した段への辺が別の箱の裏を通る③折り返しの段の隙間が層間と同じで
# 層の境目が分かりにくい、の是正。①②はここの関数群、③は WRAP_ROW_GAP の
# 値そのもの（上の定数の節）で直した。


def _perp_offset(
    mx: float, my: float, dx: float, dy: float, amount: float = LABEL_OFFSET
) -> tuple[float, float]:
    """点(mx,my)から、向き(dx,dy)と垂直な方向に amount だけ離した点を返す。

    垂直な向きは (dy, -dx) を正規化したもの（時計回りに90度）。縦の線
    （dx=0）では従来どおり右に、横の線（dy=0）では従来どおり上にずれる
    ＝符号の向きは既存の `_label_anchor` の offset=True と合わせてある
    （既存テストの期待値を変えないため）。
    """
    norm = math.hypot(dx, dy)
    if norm < 1e-9:
        return (mx + amount, my)
    px, py = dy / norm, -dx / norm
    return (mx + px * amount, my + py * amount)


def _bezier_point(
    p0: tuple[float, float],
    c1: tuple[float, float],
    c2: tuple[float, float],
    p3: tuple[float, float],
    t: float,
) -> tuple[float, float]:
    mt = 1.0 - t
    x = (
        (mt ** 3) * p0[0]
        + 3 * (mt ** 2) * t * c1[0]
        + 3 * mt * (t ** 2) * c2[0]
        + (t ** 3) * p3[0]
    )
    y = (
        (mt ** 3) * p0[1]
        + 3 * (mt ** 2) * t * c1[1]
        + 3 * mt * (t ** 2) * c2[1]
        + (t ** 3) * p3[1]
    )
    return (x, y)


def _bezier_tangent(
    p0: tuple[float, float],
    c1: tuple[float, float],
    c2: tuple[float, float],
    p3: tuple[float, float],
    t: float,
) -> tuple[float, float]:
    mt = 1.0 - t
    dx = 3 * (mt ** 2) * (c1[0] - p0[0]) + 6 * mt * t * (c2[0] - c1[0]) + 3 * (t ** 2) * (p3[0] - c2[0])
    dy = 3 * (mt ** 2) * (c1[1] - p0[1]) + 6 * mt * t * (c2[1] - c1[1]) + 3 * (t ** 2) * (p3[1] - c2[1])
    return (dx, dy)


def _bezier_sample(
    p0: tuple[float, float],
    c1: tuple[float, float],
    c2: tuple[float, float],
    p3: tuple[float, float],
    n: int = 16,
) -> list[tuple[float, float]]:
    if n < 2:
        n = 2
    return [_bezier_point(p0, c1, c2, p3, i / (n - 1)) for i in range(n)]


def _label_anchor_layered(
    points: Sequence[tuple[float, float]], control: Optional[tuple]
) -> tuple[float, float]:
    """層配置エンジン（max_width指定時）専用のラベル置き場所。

    ・直線（2点・control無し）＝2点のちょうど真ん中（＝層間の隙間の縦の
      中点。始点・終点がそれぞれ箱の下辺・上辺なので、真ん中は必ず隙間の
      中）から、線と垂直な向きにだけ LABEL_OFFSET 離す。
    ・S字（三次曲線の control）＝曲線の t=0.5 の点から、その点の接線と
      垂直な向きに離す。
    ・それ以外（迂回の折れ線など）＝従来どおり「いちばん長い区間の中点
      から離す」（`_label_anchor` の offset=True）。
    """
    if control is not None and isinstance(control[0], tuple) and len(points) >= 2:
        p0, p3 = points[0], points[-1]
        c1, c2 = control
        mx, my = _bezier_point(p0, c1, c2, p3, 0.5)
        dx, dy = _bezier_tangent(p0, c1, c2, p3, 0.5)
        return _perp_offset(mx, my, dx, dy)
    if control is None and len(points) == 2:
        (x0, y0), (x1, y1) = points
        mx, my = (x0 + x1) / 2.0, (y0 + y1) / 2.0
        return _perp_offset(mx, my, x1 - x0, y1 - y0)
    return _label_anchor(points, offset=True)


def _point_in_rect(x: float, y: float, rx: float, ry: float, rw: float, rh: float) -> bool:
    return rx <= x <= rx + rw and ry <= y <= ry + rh


def _cross(o: tuple[float, float], a: tuple[float, float], b: tuple[float, float]) -> float:
    return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])


def _on_segment(
    p: tuple[float, float], q: tuple[float, float], r: tuple[float, float]
) -> bool:
    return (
        min(p[0], r[0]) - 1e-9 <= q[0] <= max(p[0], r[0]) + 1e-9
        and min(p[1], r[1]) - 1e-9 <= q[1] <= max(p[1], r[1]) + 1e-9
    )


def _segments_intersect(
    p1: tuple[float, float],
    p2: tuple[float, float],
    p3: tuple[float, float],
    p4: tuple[float, float],
) -> bool:
    """線分 p1-p2 と p3-p4 が交わるか（斜めの線分にも対応する一般判定）。"""
    d1 = _cross(p3, p4, p1)
    d2 = _cross(p3, p4, p2)
    d3 = _cross(p1, p2, p3)
    d4 = _cross(p1, p2, p4)
    if ((d1 > 0) != (d2 > 0)) and ((d3 > 0) != (d4 > 0)) and d1 != 0 and d2 != 0:
        return True
    if d1 == 0 and _on_segment(p3, p1, p4):
        return True
    if d2 == 0 and _on_segment(p3, p2, p4):
        return True
    if d3 == 0 and _on_segment(p1, p3, p2):
        return True
    if d4 == 0 and _on_segment(p1, p4, p2):
        return True
    return False


def _segment_overlaps_rect(
    p1: tuple[float, float],
    p2: tuple[float, float],
    rx: float,
    ry: float,
    rw: float,
    rh: float,
) -> bool:
    """線分 p1-p2 が矩形(rx,ry,rw,rh)と交わるか（斜めの直線もそのまま判定する
    一般判定＝軸並行の外接矩形どうしの重なりだけを見る簡易判定だと、斜めの
    直線が実際には矩形の外を通っていても「交わった」と誤判定するため）。"""
    if _point_in_rect(p1[0], p1[1], rx, ry, rw, rh) or _point_in_rect(
        p2[0], p2[1], rx, ry, rw, rh
    ):
        return True
    corners = [(rx, ry), (rx + rw, ry), (rx + rw, ry + rh), (rx, ry + rh)]
    edges = list(zip(corners, corners[1:] + corners[:1]))
    for a, b in edges:
        if _segments_intersect(p1, p2, a, b):
            return True
    return False


def _route_hits_other_box(
    points: Sequence[tuple[float, float]],
    control: Optional[tuple],
    boxes: Sequence[Mapping[str, object]],
    from_index: int,
    to_index: int,
    pad: float = BOX_SAFETY_PAD,
) -> bool:
    """2026-09-12（担当H3・撮影で確認＝折り返した段への辺が別の箱の裏を通る）：
    出来上がった経路（直線・折れ線はそのまま、曲線は16点にサンプリング）が、
    出発・到着以外の箱の矩形（余白 pad を足す）と交わるかを幾何で判定する。
    全ての辺に対してこの検査を最後に必ず通す（安全網）。
    """
    if control is not None and isinstance(control[0], tuple) and len(points) >= 2:
        p0, p3 = points[0], points[-1]
        c1, c2 = control
        sampled = _bezier_sample(p0, c1, c2, p3, 16)
        segments = list(zip(sampled, sampled[1:]))
    else:
        segments = list(zip(points, points[1:]))
    for idx, box in enumerate(boxes):
        if idx == from_index or idx == to_index:
            continue
        rx = box["x"] - pad  # type: ignore[operator]
        ry = box["y"] - pad  # type: ignore[operator]
        rw = box["w"] + 2 * pad  # type: ignore[operator]
        rh = box["h"] + 2 * pad  # type: ignore[operator]
        for a, b in segments:
            if _segment_overlaps_rect(a, b, rx, ry, rw, rh):  # type: ignore[arg-type]
                return True
    return False


def _free_horizontal_side(box: Mapping[str, object], boxes: Sequence[Mapping[str, object]]) -> str:
    """同じ段の別の箱を横切らずに外へ出られる側を返す。

    左右とも空いている場合は盤面の中央から遠い側を選ぶ。層を飛ばす辺を単純に
    右側へ回すと、位置を指定した図（2026-09-23 の実例）のように同じ段の右隣の箱を横切るため、
    出発点と到着点ごとに空いている側を選ぶ。
    """
    box_top = float(box["y"])
    box_bottom = box_top + float(box["h"])
    same_row = [
        candidate
        for candidate in boxes
        if candidate is not box
        and min(box_bottom, float(candidate["y"]) + float(candidate["h"]))
        > max(box_top, float(candidate["y"]))
    ]
    left_clear = not any(candidate["x"] < box["x"] for candidate in same_row)
    right_clear = not any(candidate["x"] > box["x"] for candidate in same_row)
    if left_clear and not right_clear:
        return "left"
    if right_clear and not left_clear:
        return "right"
    board_center = (
        min(candidate["x"] for candidate in boxes)
        + max(candidate["x"] + candidate["w"] for candidate in boxes)
    ) / 2.0
    box_center = box["x"] + box["w"] / 2.0
    return "left" if box_center <= board_center else "right"


def _outer_perimeter_route(
    source: Mapping[str, object],
    target: Mapping[str, object],
    boxes: Sequence[Mapping[str, object]],
    left_x: float,
    right_x: float,
    bottom_y: float,
    source_port_offset: float = 0.0,
    target_port_offset: float = 0.0,
) -> list[tuple[float, float]]:
    """箱群の外周を回り、同じ段の兄弟箱を横切らない折れ線を作る。"""
    source_side = _free_horizontal_side(source, boxes)
    target_side = _free_horizontal_side(target, boxes)
    source_limit = max(0.0, float(source["h"]) / 2.0 - 8.0)
    target_limit = max(0.0, float(target["h"]) / 2.0 - 8.0)
    source_offset = max(-source_limit, min(source_limit, source_port_offset))
    target_offset = max(-target_limit, min(target_limit, target_port_offset))
    source_y = source["y"] + source["h"] / 2.0 + source_offset
    target_y = target["y"] + target["h"] / 2.0 + target_offset
    source_edge_x = source["x"] if source_side == "left" else source["x"] + source["w"]
    target_edge_x = target["x"] if target_side == "left" else target["x"] + target["w"]
    source_lane_x = left_x if source_side == "left" else right_x
    target_lane_x = left_x if target_side == "left" else right_x
    if source_lane_x == target_lane_x:
        # 同じ外側を使えるときは下端まで往復しない。盤面の外側をそのまま縦に進む。
        points = [
            (source_edge_x, source_y),
            (source_lane_x, source_y),
            (target_lane_x, target_y),
            (target_edge_x, target_y),
        ]
    else:
        points = [
            (source_edge_x, source_y),
            (source_lane_x, source_y),
            (source_lane_x, bottom_y),
            (target_lane_x, bottom_y),
            (target_lane_x, target_y),
            (target_edge_x, target_y),
        ]
    compact: list[tuple[float, float]] = []
    for point in points:
        if not compact or point != compact[-1]:
            compact.append(point)
    return compact


def _perimeter_port_offset(order: int, height: float) -> float:
    """同じ箱へ集まる外周経路の矢じりを、箱の側面で少しずつ分ける。"""
    if order <= 0:
        return 0.0
    step = min(10.0, max(4.0, (height - 16.0) / 3.0))
    magnitude = ((order + 1) // 2) * step
    return magnitude if order % 2 else -magnitude


def _label_rect_hits_box(
    x: float,
    y: float,
    label: str,
    boxes: Sequence[Mapping[str, object]],
    pad: float = 2.0,
) -> bool:
    """12pxの辺ラベルの見積り矩形が、いずれかの箱と重なるか。"""
    width = max(20.0, sum(8.0 if ch.isascii() else 13.0 for ch in label))
    height = 16.0
    left, top = x - width / 2.0, y - height / 2.0
    right, bottom = left + width, top + height
    for box in boxes:
        box_left = float(box["x"]) - pad
        box_top = float(box["y"]) - pad
        box_right = float(box["x"]) + float(box["w"]) + pad
        box_bottom = float(box["y"]) + float(box["h"]) + pad
        if left < box_right and right > box_left and top < box_bottom and bottom > box_top:
            return True
    return False


def _safe_label_anchor(
    points: Sequence[tuple[float, float]],
    control: Optional[tuple],
    label: str,
    boxes: Sequence[Mapping[str, object]],
) -> tuple[float, float]:
    """線から離し、箱にも重ならないラベル位置を折れ線上の候補から選ぶ。"""
    initial = _label_anchor_layered(points, control)
    if not label or not _label_rect_hits_box(initial[0], initial[1], label, boxes):
        return initial

    segments = sorted(
        zip(points, points[1:]),
        key=lambda pair: -math.hypot(pair[1][0] - pair[0][0], pair[1][1] - pair[0][1]),
    )
    candidates: list[tuple[float, float]] = []
    for a, b in segments:
        dx, dy = b[0] - a[0], b[1] - a[1]
        if math.hypot(dx, dy) < 1e-6:
            continue
        for fraction in (0.30, 0.70, 0.20, 0.80, 0.50):
            mx = a[0] + dx * fraction
            my = a[1] + dy * fraction
            candidates.append(_perp_offset(mx, my, dx, dy, LABEL_OFFSET))
            candidates.append(_perp_offset(mx, my, dx, dy, -LABEL_OFFSET))
    candidates.sort(key=lambda point: math.hypot(point[0] - initial[0], point[1] - initial[1]))
    for candidate in candidates:
        if candidate[0] < 2.0 or candidate[1] < 8.0:
            continue
        if not _label_rect_hits_box(candidate[0], candidate[1], label, boxes):
            return candidate
    return initial


def _build_routes(boxes: list[dict], edges: Sequence[dict]) -> list[Route]:
    if boxes:
        left_x = max(2.0, min(b["x"] for b in boxes) - MARGIN)
        side_x = max(b["x"] + b["w"] for b in boxes) + GAP_X / 2.0
        bottom_y = max(b["y"] + b["h"] for b in boxes) + GAP_Y / 2.0
    else:
        left_x = MARGIN
        side_x = MARGIN
        bottom_y = MARGIN
    routes: list[Route] = []
    anchor_seen: dict[tuple[int, int, int], int] = {}
    perimeter_source_seen: dict[int, int] = {}
    perimeter_target_seen: dict[int, int] = {}
    detour_count = 0
    for e in edges:
        source = boxes[e["from_index"]]
        target = boxes[e["to_index"]]
        points, control = _route_points_row_primary(source, target, e["curve"], side_x, bottom_y)
        if _route_hits_other_box(points, control, boxes, e["from_index"], e["to_index"]):
            source_order = perimeter_source_seen.get(e["from_index"], 0)
            target_order = perimeter_target_seen.get(e["to_index"], 0)
            perimeter_source_seen[e["from_index"]] = source_order + 1
            perimeter_target_seen[e["to_index"]] = target_order + 1
            points = _outer_perimeter_route(
                source,
                target,
                boxes,
                left_x,
                side_x + DETOUR_SIDE_STAGGER * detour_count,
                bottom_y + DETOUR_SIDE_STAGGER * detour_count,
                source_port_offset=_perimeter_port_offset(source_order, source["h"]),
                target_port_offset=_perimeter_port_offset(target_order, target["h"]),
            )
            control = None
            detour_count += 1
        # ラベルは線そのものから10px離す。描画側はこの座標を文字の中心として扱う。
        label_x, label_y = _safe_label_anchor(points, control, e["label"], boxes)
        key = (round(label_x / 24.0), round(label_y / 24.0), e["to_index"])
        order = anchor_seen.get(key, 0)
        anchor_seen[key] = order + 1
        if order > 0 and e["label"]:
            label_x += LABEL_STAGGER * order
        routes.append(
            Route(
                points=points,
                label=e["label"],
                label_x=label_x,
                label_y=label_y,
                kind=e["kind"],
                from_index=e["from_index"],
                to_index=e["to_index"],
                control=control,
            )
        )
    return routes


def _under_row_plan(
    boxes: Sequence[dict], edges: Sequence[dict], back_edges: set[int]
) -> tuple[dict[int, float], dict[int, tuple[int, int]]]:
    """全部の箱が1行に並ぶ図で、行の下を回す辺の「横線の深さ」と「出入口の番号」を決める
    （2026-09-28 新設）。戻り値＝(辺の索引→行の下の横線（bottom_y）からの深さ px,
    辺の索引→(出発の番号, 到着の番号))。

    行の下を回すのは、戻る辺と、間の箱を飛ばす辺（横1行の明示でだけできる）。
    ・段＝飛ばす箱の数が少ない辺ほど浅い。同じなら右向きの辺を先に（右向きの出入口は
      中心から遠いので、同じ2箱を結ぶ左向きの辺の内側に収まる）、それも同じなら辺の順。
      戻る辺だけの図（隣どうし・全部左向き）では、従来どおり辺の順に1段ずつ下がる。
    ・深さ＝1段ごとに UNDER_ROW_STAGGER。ただし上の段にラベルがあり、すぐ下の段と横の
      範囲（両端の箱の中心の間）が重なるときは、さらに UNDER_ROW_LABEL_EXTRA 下げる
      （撮影で確認＝同じ2箱を結ぶ2本が入れ子になると、上の段のラベルが自分の線と下の
      線のちょうど真ん中に来て、どちらのラベルか読めなかった）。範囲が端で接するだけの
      図（戻る辺が隣どうしに1本ずつ）は従来と同じ深さ。
    ・出入口＝同じ箱の同じ側（出発／到着×左向き／右向き）に2本以上あれば、深い段の辺
      ほど中心寄り（番号0）にする。浅い段の横線の範囲の外で深い段の線が下りるので、
      2本が入れ子になり、交わらない。
    """
    under: list[int] = []
    span: dict[int, int] = {}
    leftward: dict[int, bool] = {}
    for i, e in enumerate(edges):
        s, t = boxes[e["from_index"]], boxes[e["to_index"]]
        gap = abs(s.get("_col", 0) - t.get("_col", 0))
        if i in back_edges or gap > 1:
            under.append(i)
            span[i] = gap
            leftward[i] = t["x"] + t["w"] / 2.0 < s["x"] + s["w"] / 2.0
    ordered = sorted(under, key=lambda i: (span[i], leftward[i], i))
    lanes = {i: k for k, i in enumerate(ordered)}

    def reach(i: int) -> tuple[float, float]:
        s, t = boxes[edges[i]["from_index"]], boxes[edges[i]["to_index"]]
        cs, ct = s["x"] + s["w"] / 2.0, t["x"] + t["w"] / 2.0
        return min(cs, ct), max(cs, ct)

    depth: dict[int, float] = {}
    y = 0.0
    for k, i in enumerate(ordered):
        depth[i] = y
        if k + 1 < len(ordered):
            y += UNDER_ROW_STAGGER
            (lo_a, hi_a), (lo_b, hi_b) = reach(i), reach(ordered[k + 1])
            if edges[i].get("label") and min(hi_a, hi_b) - max(lo_a, lo_b) > 0.0:
                y += UNDER_ROW_LABEL_EXTRA
    groups: dict[tuple[int, str, bool], list[int]] = {}
    for i in under:
        e = edges[i]
        groups.setdefault((e["from_index"], "out", leftward[i]), []).append(i)
        groups.setdefault((e["to_index"], "in", leftward[i]), []).append(i)
    s_slot: dict[int, int] = {}
    t_slot: dict[int, int] = {}
    for (_box, end, _left), members in groups.items():
        target_map = s_slot if end == "out" else t_slot
        for k, i in enumerate(sorted(members, key=lambda i: (-lanes[i], i))):
            target_map[i] = k
    slots = {i: (s_slot.get(i, 0), t_slot.get(i, 0)) for i in under}
    return depth, slots


def _build_routes_layered(
    boxes: list[dict], edges: Sequence[dict], back_edges: set[int]
) -> list[Route]:
    """2026-09-12 新設：max_width 指定時の専用エンジン（LR／TB）が使う経路の組み立て。

    ・辺のラベルは線の脇に置く（`_label_anchor_layered`＝直線は2点の真ん中、
      S字は曲線の t=0.5 の点から、それぞれ垂直な向きに離す）。
    ・同じあたりに複数のラベルが来るときは少しずつずらす。
    ・戻る辺（back_edges に索引がある辺）は force_far=True＝隣の層どうしでも必ず迂回。
    ・（担当H3・2026-09-12）出来上がった経路が出発・到着以外の箱を突っ切って
      いないかを最後に必ず確認し、突っ切っていれば側面を回る迂回に切り替える
      （安全網＝折り返した段への辺が別の箱の裏を通った実例の是正）。
    ・（担当H4・2026-09-12）迂回する辺（戻る辺・層を2つ以上飛ばす辺・安全網で
      切り替わった辺）が2本以上あるときは、同じ縦線（side_x）を重ねて通らない
      よう1本ごとに DETOUR_SIDE_STAGGER ずつ外側へずらす。
    """
    if boxes:
        # 2026-09-25（撮影で確認＝層0を2段に折った図で、左端の箱から出る辺が箱の縁から
        # 6pxの所を回り、そのラベルが図の左の外へ出て「来事ごと」と切れた）：左の迂回線も
        # 右（side_x）と同じだけ箱から離す＝ラベルが線と箱の間に収まる。負になっても
        # `_compute_bounds` が図全体を右へずらして見える範囲に入れる。
        left_x = min(b["x"] for b in boxes) - GAP_X / 2.0
        side_x = max(b["x"] + b["w"] for b in boxes) + GAP_X / 2.0
        bottom_y = max(b["y"] + b["h"] for b in boxes) + GAP_Y / 2.0
    else:
        left_x = PAGE_MARGIN / 2.0
        side_x = PAGE_MARGIN
        bottom_y = PAGE_MARGIN
    routes: list[Route] = []
    anchor_seen: dict[tuple[int, int], int] = {}
    detour_count = 0
    # 2026-09-25：全部の箱が1行に並ぶ図（LR）では、戻る辺を行の下へ U 字に回す。
    single_row = len({b.get("_row", 0) for b in boxes}) == 1
    lane_depth, slots = _under_row_plan(boxes, edges, back_edges) if single_row else ({}, {})
    for i, e in enumerate(edges):
        source = boxes[e["from_index"]]
        target = boxes[e["to_index"]]
        is_back = i in back_edges
        # force_far（戻る辺）または row_gap>1（層を2つ以上飛ばす）のときだけ
        # _route_points_row_primary は内部で _detour_vertical に入る（他の分岐は
        # すべて row_gap<=1 が前提のため）＝ここで先読みして side_x をずらせる。
        row_gap = abs(source.get("_row", 0) - target.get("_row", 0))
        expects_detour = is_back or row_gap > 1
        under_row = i in lane_depth
        route_side_x = side_x + DETOUR_SIDE_STAGGER * detour_count if expects_detour else side_x
        route_bottom_y = bottom_y + lane_depth[i] if under_row else bottom_y
        points, control = _route_points_row_primary(
            source,
            target,
            e["curve"],
            route_side_x,
            route_bottom_y,
            smooth=True,
            force_far=is_back or under_row,
            under_row=under_row,
            port_slots=slots.get(i, (0, 0)),
        )
        if not under_row and expects_detour:
            detour_count += 1
        if _route_hits_other_box(points, control, boxes, e["from_index"], e["to_index"]):
            fallback_left_x = left_x - DETOUR_SIDE_STAGGER * detour_count
            fallback_right_x = side_x + DETOUR_SIDE_STAGGER * detour_count
            fallback_bottom_y = bottom_y + DETOUR_SIDE_STAGGER * detour_count
            points = _outer_perimeter_route(
                source,
                target,
                boxes,
                fallback_left_x,
                fallback_right_x,
                fallback_bottom_y,
            )
            control = None
            detour_count += 1
            under_row = False
        label_x, label_y = _label_anchor_layered(points, control)
        if under_row and control is None and len(points) == 4:
            # 行の下の横線の中点の、さらに下＝箱とも他の横線とも重ならない側。
            label_x = (points[1][0] + points[2][0]) / 2.0
            label_y = points[1][1] + LABEL_OFFSET + 2.0
        # 2026-09-12（担当H3・撮影で確認＝一本の鎖に戻る辺を足した図で、無関係な
        # 辺のラベルまで一緒にずらされてキャンバスの外に出た）：同じ列どうしの
        # 辺でも、ラベルの高さが離れていれば重ならないので段違いとは扱わない
        # ＝ラベルのy位置も鍵に含める（真に同じあたりに来る場合だけずらす）。
        key = (
            round(source["x"] / 40.0),
            round(target["x"] / 40.0),
            round(label_y / 40.0),
        )
        order = anchor_seen.get(key, 0)
        anchor_seen[key] = order + 1
        if order > 0 and e["label"]:
            label_x += LABEL_STAGGER * order
        routes.append(
            Route(
                points=points,
                label=e["label"],
                label_x=label_x,
                label_y=label_y,
                kind=e["kind"],
                from_index=e["from_index"],
                to_index=e["to_index"],
                control=control,
            )
        )
    return routes


def _compute_bounds(
    boxes: Sequence[dict],
    routes: Sequence[Route],
    margin: float = MARGIN,
    label_font_px: Optional[float] = None,
) -> tuple[float, float]:
    """`label_font_px`＝None（既定・旧経路）なら従来どおり箱と経路の点・制御点
    だけで測る（既存14本・max_width=None の挙動を変えないため）。値を渡すと
    （2026-09-12・担当H3・撮影で確認＝右端近くの辺のラベルがキャンバスの外に
    はみ出す）、ラベルの見積り幅の半分も測る対象に含める。

    2026-09-25（撮影で確認＝左外側を回る辺のラベルの x が負になり「来事ごと」と
    左が切れた。右だけ測っていた）：左と上も測る。描画側の viewBox は原点が
    0 に固定なので、箱・経路・ラベルのどれかが VIEW_PAD より左（上）にはみ出して
    いれば、**図全体をその分だけ右（下）へずらしてから**右端と下端を測る
    （＝boxes と routes をその場で書き換える）。はみ出していなければ何も動かさない。
    """
    if not boxes:
        return margin * 2, margin * 2
    min_x, min_y, _, _ = _extents(boxes, routes, label_font_px)
    dx = max(0.0, VIEW_PAD - min_x)
    dy = max(0.0, VIEW_PAD - min_y)
    if dx > 0.0 or dy > 0.0:
        _translate(boxes, routes, dx, dy)
    _, _, max_x, max_y = _extents(boxes, routes, label_font_px)
    return max_x + margin, max_y + margin


def _label_half_extent(label: str, label_font_px: float) -> tuple[float, float]:
    """辺のラベルの見積り矩形の半幅・半高（label_x, label_y が中心）。

    幅は2026-09-12からの見積り（本文の文字幅×BODY_SCALE＋左右6px）のまま。
    高さは描画側の12px文字＋縁取り（stroke-width 5）を覆う LABEL_HALF_H。
    """
    return (
        _line_em_width(label) * label_font_px * BODY_SCALE / 2.0 + 6.0,
        LABEL_HALF_H,
    )


def _extents(
    boxes: Sequence[dict],
    routes: Sequence[Route],
    label_font_px: Optional[float],
) -> tuple[float, float, float, float]:
    """箱・経路の点・制御点（・label_font_px があればラベルの見積り矩形）の外接範囲。"""
    min_x = min(b["x"] for b in boxes)
    min_y = min(b["y"] for b in boxes)
    max_x = max(b["x"] + b["w"] for b in boxes)
    max_y = max(b["y"] + b["h"] for b in boxes)
    # 層を飛ばす辺は盤面の外側（left_x／side_x／bottom_y）を回るので、経路の点も含めて測る
    for route in routes:
        points = list(route.points)
        if route.control is not None:
            # (cx, cy)＝二次の制御点1つ、((c1x,c1y),(c2x,c2y))＝三次の制御点2つ。
            control_points = route.control if isinstance(route.control[0], tuple) else [route.control]
            points.extend(control_points)  # type: ignore[arg-type]
        for px, py in points:
            min_x = min(min_x, px)
            min_y = min(min_y, py)
            max_x = max(max_x, px)
            max_y = max(max_y, py)
        if label_font_px is not None and route.label:
            half_w, half_h = _label_half_extent(route.label, label_font_px)
            min_x = min(min_x, route.label_x - half_w)
            min_y = min(min_y, route.label_y - half_h)
            max_x = max(max_x, route.label_x + half_w)
            max_y = max(max_y, route.label_y + half_h)
    return min_x, min_y, max_x, max_y


def _translate(boxes: Sequence[dict], routes: Sequence[Route], dx: float, dy: float) -> None:
    """箱・経路・制御点・ラベルを (dx, dy) だけ平行移動する（その場で書き換える）。"""
    for b in boxes:
        b["x"] += dx
        b["y"] += dy
    for route in routes:
        route.points = [(px + dx, py + dy) for px, py in route.points]
        if route.control is not None:
            if isinstance(route.control[0], tuple):
                route.control = tuple((cx + dx, cy + dy) for cx, cy in route.control)
            else:
                cx, cy = route.control
                route.control = (cx + dx, cy + dy)
        route.label_x += dx
        route.label_y += dy


# ---------------------------------------------------------------------------
# 列幅（max_width）に収める専用エンジン（2026-09-12 新設）
# ---------------------------------------------------------------------------
#
# 方針＝①辺が「枝分かれの無い一本の鎖」で向きが揃っている（_detect_chain・A→B→C。
#   広がる形 A→B・A→C は鎖ではない＝2026-09-28）なら、横1行（LR）に並べた幅が
#   max_width に収まるかを試す。収まればそれを使う。
#   明示の向き（direction="vertical"／"horizontal"）があれば、それを優先する（2026-09-28）。
# ②収まらない、または枝分かれ（扇状・合流・DAG）があるなら、層（辺の向きから
#   の深さ・戻る辺は除いて計算）を縦に積む（TB）。1つの層の横幅が max_width を
#   超えるならその層を2段以上に折る。層の中の箱は共通の中心線で中央揃えする
#   （＝どの層も同じ中心 x に揃うので、親と子の中心が自然に一致する）。
#
# 箱の大きさ＝同じ層（LRなら「その箱1個だけの層」）の箱は同じ幅にそろえ、
# 160〜260px にクランプする。


def _lr_chain_width(chain_order: Sequence[int], boxes: list[dict]) -> float:
    if not chain_order:
        return PAGE_MARGIN * 2
    total = sum(boxes[i]["w"] for i in chain_order) + GAP_X * (len(chain_order) - 1)
    return total + PAGE_MARGIN * 2


def _apply_lr_chain_positions(boxes: list[dict], chain_order: Sequence[int]) -> None:
    if not chain_order:
        return
    max_h = max(boxes[i]["h"] for i in chain_order)
    x = PAGE_MARGIN
    for pos, i in enumerate(chain_order):
        boxes[i]["x"] = x
        boxes[i]["y"] = PAGE_MARGIN + (max_h - boxes[i]["h"]) / 2.0
        boxes[i]["_col"] = pos
        boxes[i]["_row"] = 0
        x += boxes[i]["w"] + GAP_X


def _apply_tb_positions(
    boxes: list[dict],
    layers: Mapping[int, list[int]],
    layer_keys: Sequence[int],
    layer_w: Mapping[int, float],
    max_width: Optional[float],
    label_gap_after: Optional[set] = None,
) -> None:
    label_gap_after = label_gap_after or set()
    inner_max = (max_width - PAGE_MARGIN * 2) if max_width is not None else float("inf")
    if layer_keys:
        inner_max = max(inner_max, layer_w[layer_keys[0]])

    layer_rows: dict[int, list[list[int]]] = {}
    overall_w = 0.0
    for lk in layer_keys:
        members = layers[lk]
        w = layer_w[lk]
        rows: list[list[int]] = []
        cur: list[int] = []
        cur_w = 0.0
        for i in members:
            add = w if not cur else w + BOX_GAP
            if cur and cur_w + add > inner_max:
                rows.append(cur)
                cur = [i]
                cur_w = w
            else:
                cur.append(i)
                cur_w += add
        if cur:
            rows.append(cur)
        layer_rows[lk] = rows
        for row in rows:
            row_w = len(row) * w + (len(row) - 1) * BOX_GAP
            overall_w = max(overall_w, row_w)

    center_x = PAGE_MARGIN + overall_w / 2.0
    y_cursor = PAGE_MARGIN
    phys_row = 0
    for lk in layer_keys:
        w = layer_w[lk]
        rows = layer_rows[lk]
        for ridx, row in enumerate(rows):
            row_w = len(row) * w + (len(row) - 1) * BOX_GAP
            x = center_x - row_w / 2.0
            row_h = max(boxes[i]["h"] for i in row)
            for cidx, i in enumerate(row):
                boxes[i]["x"] = x
                boxes[i]["y"] = y_cursor
                # 2026-09-12（撮影で確認＝1つの層が折り返した2段目への辺が、間に挟まった
                # 別の層の箱を突っ切って描かれた）：_row は「層の番号」ではなく「実際に
                # 積んだ段」を1つずつ増やす通し番号にする＝経路の隣接判定（row_gap）が
                # 折り返しをまたぐ辺も「2段以上飛ばす辺」として正しく検出し、迂回させる。
                boxes[i]["_row"] = phys_row
                boxes[i]["_col"] = cidx
                x += w + BOX_GAP
            if ridx < len(rows) - 1:
                y_cursor += row_h + WRAP_ROW_GAP
            else:
                y_cursor += row_h
            phys_row += 1
        # 2026-09-12（担当H3・撮影で確認＝ラベルが箱の縁に触れる）：ラベルが
        # 乗る層間だけは隙間を広げる（60px）。ラベルの無い層間は従来どおり。
        y_cursor += LABEL_LAYER_GAP_TB if lk in label_gap_after else LAYER_GAP_TB


def _layers_needing_wide_gap(
    forward_edges: Sequence[dict], layer_of: Sequence[int]
) -> set[int]:
    """ラベル付きの辺が隣の層をまたぐとき、その層間の隙間を広げる対象（＝手前
    の層の番号）を返す（2026-09-12・担当H3）。ラベルは層間の隙間の中に置く
    ので、ラベル1行ぶん＋余白（60px）が要る。ラベルの無い層間・層を2つ以上
    飛ばす辺（迂回で描かれ、隙間の中には置かない）は対象にしない。
    """
    result: set[int] = set()
    for e in forward_edges:
        if not e.get("label"):
            continue
        a, b = e["from_index"], e["to_index"]
        la, lb = layer_of[a], layer_of[b]
        if lb == la + 1:
            result.add(la)
    return result


def _place_layered_fit(
    boxes: list[dict],
    edges: Sequence[dict],
    max_width: float,
    max_box_w: float = LAYERED_MAX_BOX_W,
    direction: str = "auto",
) -> tuple[str, set[int]]:
    """max_width に収める配置。戻り値＝(orientation, 戻る辺の索引集合)。

    max_box_w＝層の箱の幅の上限（既定 LAYERED_MAX_BOX_W）。組み上がりが max_width を
    超えたとき、呼び出し側がこれを下げて組み直す（2026-09-26）。

    direction（2026-09-28・それまでは受け取らず、明示の向きが黙って無視された）：
    "vertical"＝鎖でも横1行にせず、層を縦に積む。"horizontal"＝必ず横1行に並べる
    （層の順＝戻る辺以外の矢印は左から右。間の箱を飛ばす辺は行の下を回す。max_width を
    超えても1行のまま＝狭い画面では横スクロール）。それ以外＝従来どおり「向きの揃った
    鎖で max_width に収まるなら横1行、そうでなければ縦」。向きの揃った鎖では、鎖の順と
    層の順は同じになる（i 番目の箱が i 番目の層）。
    """
    n = len(boxes)
    back = _find_back_edge_indices(n, edges)
    forward = [e for i, e in enumerate(edges) if i not in back]

    layer_of = _assign_layers(n, forward)
    layers: dict[int, list[int]] = {}
    for i in range(n):
        layers.setdefault(layer_of[i], []).append(i)
    layers = _reorder_layers(layers, forward)
    layer_keys = sorted(layers.keys())
    label_gap_after = _layers_needing_wide_gap(forward, layer_of)

    for lk in layer_keys:
        members = layers[lk]
        natural = max((boxes[i]["w"] for i in members), default=LAYERED_MIN_BOX_W)
        w = max(LAYERED_MIN_BOX_W, min(max_box_w, natural))
        for i in members:
            if boxes[i]["w"] > w:
                # 2026-09-26：上限で切った箱は、字数で折った行が幅に入らない＝幅で折り直す。
                _refit_to_width(boxes[i], w)
            boxes[i]["w"] = w
    layer_w = {lk: boxes[layers[lk][0]]["w"] for lk in layer_keys}

    if direction != "vertical":
        chain = _detect_chain(n, edges, forward)
        if direction == "horizontal" or (
            chain is not None and _lr_chain_width(chain, boxes) <= max_width
        ):
            order = chain if chain is not None else [i for lk in layer_keys for i in layers[lk]]
            _apply_lr_chain_positions(boxes, order)
            return "LR", back

    _apply_tb_positions(boxes, layers, layer_keys, layer_w, max_width, label_gap_after)
    return "TB", back


# ---------------------------------------------------------------------------
# 公開関数
# ---------------------------------------------------------------------------

def layout_diagram(
    nodes: list[dict],
    edges: list[dict],
    *,
    max_cols: int = 3,
    direction: str = "auto",
    font_px: int = 14,
    max_width: Optional[float] = None,
) -> Layout:
    """箱と矢印の配置・経路だけを計算する（描画はしない）。標準ライブラリのみ・決定論・例外を投げない。

    max_width＝None（既定）なら従来どおりの配置。値を渡すと、辺のある図は
    出来上がりの幅がそれを超えないよう、層を横（LR）または縦（TB）に並べ直す。
    """
    try:
        return _layout_diagram_impl(nodes, edges, max_cols, direction, font_px, max_width)
    except Exception as exc:  # 最後の砦＝ここに来る手前の各所も個別に守っているはず
        return _empty_layout(
            ["layout_diagram: 予期しない例外を捨てて空の図にした：%r" % (exc,)],
            _safe_font_px(font_px),
        )


def _layout_diagram_impl(
    nodes: object,
    edges: object,
    max_cols: object,
    direction: object,
    font_px: object,
    max_width: object = None,
) -> Layout:
    """2026-09-10（撮影で確認）：辺のラベルが箱の縁に重なった。

    列の間隔（GAP_X）を、いちばん長いラベルの幅＋余白まで広げる。GAP_X は配置と経路の
    両方が参照する定数なので、この呼び出しの間だけ差し替えて必ず元に戻す（単一プロセス・
    決定論の前提。例外時も finally で戻る）。ラベルの無い図では従来の間隔のまま。
    """
    global GAP_X
    saved = GAP_X
    try:
        font = float(_safe_font_px(font_px))
        widest = 0.0
        for e in list(edges or []):
            if isinstance(e, dict) and e.get("label"):
                widest = max(widest, _line_em_width(str(e.get("label"))) * font * 0.9)
        GAP_X = max(saved, widest + 28.0)
        return _layout_diagram_core(nodes, edges, max_cols, direction, font_px, max_width)
    finally:
        GAP_X = saved

def _layout_diagram_core(
    nodes: object,
    edges: object,
    max_cols: object,
    direction: object,
    font_px: object,
    max_width: object = None,
) -> Layout:
    warnings: list[str] = []
    font_px_num = _safe_font_px(font_px)
    node_list = list(nodes or [])

    boxes, id_map = _prepare_nodes(node_list, float(font_px_num))
    n = len(boxes)
    if n == 0:
        return _empty_layout(warnings, font_px_num)

    resolved_edges = _resolve_edges(list(edges or []), n, id_map, warnings)

    direction_norm = _stringify(direction or "auto").strip().lower()
    explicit_free = _has_explicit_placement(node_list)

    max_width_num: Optional[float] = None
    if max_width is not None and not isinstance(max_width, bool):
        try:
            mw = float(max_width)  # type: ignore[arg-type]
            if mw > 0:
                max_width_num = mw
        except Exception:
            max_width_num = None

    use_fit_engine = (
        max_width_num is not None
        and bool(resolved_edges)
        and not explicit_free
        and direction_norm != "grid"
    )

    if use_fit_engine:
        # 2026-09-26（実測＝箱の幅の見積もりを実寸に合わせたら、外側を回る迂回線の分で
        # 722px になる図が出た。層の箱は720pxに収めていたが、迂回線の分を見込んでいない）：
        # 組み上がりが max_width を超えたら、層の箱の幅の上限を超えた分だけ下げて組み直す
        # （下げた箱は `_refit_to_width` が幅で折り直す＝文字は箱からはみ出さない）。
        cap = LAYERED_MAX_BOX_W
        best = None
        for _attempt in range(FIT_RETRIES):
            if _attempt:
                # 前の試みで並べた箱は捨て、下ごしらえからやり直す（並べていない箱を返さない）。
                boxes, id_map = _prepare_nodes(node_list, float(font_px_num))
            orientation, back_edges = _place_layered_fit(  # type: ignore[arg-type]
                boxes, resolved_edges, max_width_num, max_box_w=cap, direction=direction_norm
            )
            routes = _build_routes_layered(boxes, resolved_edges, back_edges)
            width, height = _compute_bounds(
                boxes, routes, margin=PAGE_MARGIN, label_font_px=float(font_px_num)
            )
            if best is None or width < best[0]:
                best = (width, height, boxes, routes, orientation)
            excess = width - max_width_num  # type: ignore[operator]
            widest = max(b["w"] for b in boxes)
            if excess <= 0.5 or widest <= LAYERED_MIN_BOX_W:
                break
            cap = max(LAYERED_MIN_BOX_W, min(cap, widest) - max(excess, FIT_MIN_STEP) - 1.0)
        # どの試みでも収まらなければ、いちばん幅の小さかった配置を使う。
        width, height, boxes, routes, orientation = best  # type: ignore[misc]
    else:
        if explicit_free:
            _place_free(boxes, node_list)
            orientation = "free"
        elif direction_norm == "grid":
            _place_grid(boxes, max_cols)  # type: ignore[arg-type]
            orientation = "grid"
        elif direction_norm == "horizontal":
            chain = _detect_chain(n, resolved_edges) if resolved_edges else None
            _place_single_row(boxes, chain if chain is not None else list(range(n)))
            orientation = "LR"
        elif direction_norm == "vertical":
            if resolved_edges:
                _place_layered(boxes, resolved_edges, max_cols)  # type: ignore[arg-type]
            else:
                _place_single_column(boxes)
            orientation = "TB"
        else:
            if not resolved_edges:
                _place_grid(boxes, max_cols)  # type: ignore[arg-type]
                orientation = "grid"
            else:
                chain = _detect_chain(n, resolved_edges)
                if chain is not None and n <= 4:
                    _place_single_row(boxes, chain)
                    orientation = "LR"
                else:
                    _place_layered(boxes, resolved_edges, max_cols)  # type: ignore[arg-type]
                    orientation = "TB"

        routes = _build_routes(boxes, resolved_edges)
        # 2026-09-25：旧経路（位置を指定した図・格子）でも、左の外周を回る辺の長いラベルが
        # 図の左の外へ出た（実測＝左端が -23px）＝ラベルの見積り矩形も境界に含める。
        width, height = _compute_bounds(
            boxes, routes, label_font_px=float(font_px_num)
        )

    out_boxes = [
        Box(
            x=b["x"],
            y=b["y"],
            w=b["w"],
            h=b["h"],
            title_lines=b["title_lines"],
            body_lines=b["body_lines"],
            note_lines=b["note_lines"],
            num=b["num"],
            tone=b["tone"],
            icon=b["icon"],
            node_index=b["index"],
        )
        for b in boxes
    ]
    return Layout(
        width=width,
        height=height,
        boxes=out_boxes,
        routes=routes,
        warnings=warnings,
        font_px=font_px_num,
        orientation=orientation,
    )

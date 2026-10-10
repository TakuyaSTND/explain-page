"""説明の頁の「単位」に番号（data-blk）を振る（2026-10-09・指摘と添削の作り込み）。

読み手が「ここ」と指したい塊（カード・表の行・箇条・段落・図・注意書き・数字の札…）に、
頁の先頭から通しで 1・2・3… の番号を `data-blk="N"` として足す。指摘と添削の画面（review_scripts）が
この番号で「どこへの赤か」を言い、文字だけの版（`<name>-text.txt`）の行頭の `#N ` も同じ番号になる。

規則
  - 番号は DOM の順（頁の読む順）。入れ子の単位は外側だけ数える（カードの中の段落は別に数えない）。
  - 判断欄（section[data-component="decision"]）・側柱（.rail）・目次（nav）・header・footer の中は数えない。
    ただし header の中の導入文（p.lede）だけは単位にする。
  - 既に data-blk の付いた頁（原稿の頁＝markdown_lite が原稿のブロックに番号を付けている）には何もしない。
  - 番号を振る位置は HTMLParser の getpos() と行の開始位置の表で求める＝複数行の HTML でも動く。

⚠️単位の規則（UNIT_RULES）は render_components.py が実際に出す class に合わせてある。
  存在しない class の規則は書かない。部品を足したら、ここへ規則を足す（試験 test_review_blocks.py が
  いくつかの部品を実際に組んで、番号が付くことを確かめている）。
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from html.parser import HTMLParser

_VOID_TAGS = frozenset(
    {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"}
)

# 抜き書き（excerpt40）で、ここを境に1つ空白を入れる要素（日本語は空白なしで続くので、塊の境目だけ空ける）。
_BREAK_TAGS = frozenset(
    {"div", "p", "li", "tr", "td", "th", "dt", "dd", "h1", "h2", "h3", "h4", "ul", "ol", "table",
     "blockquote", "figure", "figcaption", "pre", "text", "br", "b", "strong"}
)

# 中に単位を作らない場所（開始タグ → 理由）。header は p.lede だけ別扱い。
_SKIP_TAGS = frozenset({"script", "style", "svg", "textarea", "button", "nav", "footer", "fieldset"})


@dataclass(frozen=True)
class UnitRule:
    """単位の規則。tag・cls が None なら問わない。parent_* は直接の親（ol.steps > li の「ol.steps」）。"""

    kind: str
    tag: str | None = None
    cls: str | None = None
    parent_tag: str | None = None
    parent_cls: str | None = None


UNIT_RULES: tuple[UnitRule, ...] = (
    UnitRule("card", cls="card"),
    UnitRule("tile", cls="tile"),
    UnitRule("stat", cls="stat"),
    UnitRule("note", cls="note"),
    UnitRule("row", cls="item-row"),
    UnitRule("step", tag="li", parent_tag="ol", parent_cls="steps"),
    UnitRule("step", tag="li", parent_tag="ol", parent_cls="hsteps"),
    UnitRule("bullet", tag="li", parent_tag="ul", parent_cls="bullets"),
    UnitRule("numbered", tag="li", parent_tag="ol", parent_cls="numbered"),
    UnitRule("callout", tag="li", cls="callout-item"),
    UnitRule("pair", tag="dd", parent_tag="dl", parent_cls="pairs"),
    UnitRule("term", tag="dd", parent_tag="dl", parent_cls="gl"),
    UnitRule("quote", tag="blockquote"),
    UnitRule("figure", cls="dia-wrap"),
    UnitRule("figure", cls="chart-wrap"),
    UnitRule("figure", cls="img-figure"),
    UnitRule("formula", cls="formula"),
    UnitRule("log", tag="pre", cls="log"),
    UnitRule("compare", cls="compare"),
    UnitRule("flow", cls="flow-step"),
    UnitRule("flow", cls="flow-cell"),
    UnitRule("summary", tag="div", parent_tag="div", parent_cls="gnc"),
    UnitRule("chips", cls="chip-group"),
    UnitRule("row", tag="tr", parent_tag="tbody"),
    UnitRule("paragraph", tag="p", cls="body-copy"),
    UnitRule("paragraph", tag="p", cls="lead-copy"),
    UnitRule("lede", tag="p", cls="lede"),
    UnitRule("caption", tag="p", cls="cap"),
    UnitRule("detail", tag="div", cls="in"),
)


@dataclass(frozen=True)
class BlockInfo:
    number: int
    section_id: str
    section_label: str
    component: str
    kind: str
    excerpt40: str


def _classes(attrs: list[tuple[str, str | None]]) -> frozenset[str]:
    for name, value in attrs:
        if name == "class" and value:
            return frozenset(value.split())
    return frozenset()


def _attr(attrs: list[tuple[str, str | None]], key: str) -> str:
    for name, value in attrs:
        if name == key:
            return value or ""
    return ""


def _match_rule(
    tag: str,
    classes: frozenset[str],
    parent_tag: str,
    parent_classes: frozenset[str],
) -> UnitRule | None:
    for rule in UNIT_RULES:
        if rule.tag is not None and rule.tag != tag:
            continue
        if rule.cls is not None and rule.cls not in classes:
            continue
        if rule.parent_tag is not None and rule.parent_tag != parent_tag:
            continue
        if rule.parent_cls is not None and rule.parent_cls not in parent_classes:
            continue
        return rule
    return None


class _Frame:
    __slots__ = ("tag", "classes", "unit", "skip")

    def __init__(self, tag: str, classes: frozenset[str]):
        self.tag = tag
        self.classes = classes
        self.unit: int | None = None  # この要素が単位の根なら infos の添字
        self.skip = False  # この要素の中は数えない


class _Numberer(HTMLParser):
    def __init__(self, text: str):
        super().__init__(convert_charrefs=True)
        self.text = text
        starts = [0]
        for match in re.finditer("\n", text):
            starts.append(match.end())
        self.line_starts = starts
        self.stack: list[_Frame] = []
        self.skip_depth = 0
        self.unit_depth = 0
        self.header_depth = 0
        self.inserts: list[int] = []
        self.infos: list[dict] = []
        self.already_numbered = False
        self.section_id = ""
        self.section_label = ""
        self.component = ""
        self.h2_label: list[str] | None = None
        self.label_skip = 0
        self.open_units: list[int] = []

    # --- 位置 ---
    def _tag_start(self, tag: str) -> int | None:
        line, offset = self.getpos()
        index = self.line_starts[line - 1] + offset
        if self.text[index : index + 1 + len(tag)].lower() == "<" + tag:
            return index
        return None

    # --- 構文 ---
    def _mark_break(self) -> None:
        if self.open_units:
            info = self.infos[self.open_units[-1]]
            if info["text"] and not info["text"][-1].endswith(" "):
                info["text"].append(" ")

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if any(name == "data-blk" for name, _ in attrs):
            self.already_numbered = True
        if tag in _BREAK_TAGS and tag not in ("b", "strong"):
            self._mark_break()
        if tag in _VOID_TAGS:
            return
        classes = _classes(attrs)
        parent = self.stack[-1] if self.stack else None
        frame = _Frame(tag, classes)
        in_header = self.header_depth > 0
        # この要素の中は数えない場所か。
        skip_here = (
            tag in _SKIP_TAGS
            or (tag == "section" and _attr(attrs, "data-component") == "decision")
            or "rail" in classes
        )
        if tag == "header":
            self.header_depth += 1
        # 単位の判定（スキップ中・単位の中では作らない）
        if self.skip_depth == 0 and self.unit_depth == 0 and not skip_here:
            rule = _match_rule(
                tag,
                classes,
                parent.tag if parent else "",
                parent.classes if parent else frozenset(),
            )
            if rule is not None and (not in_header or rule.kind == "lede"):
                position = self._tag_start(tag)
                if position is not None:
                    frame.unit = len(self.infos)
                    self.infos.append(
                        {
                            "number": len(self.infos) + 1,
                            "section_id": self.section_id,
                            "section_label": self.section_label,
                            "component": self.component,
                            "kind": rule.kind,
                            "text": [],
                            "length": 0,
                            "insert_at": position + 1 + len(tag),
                        }
                    )
                    self.unit_depth += 1
                    self.open_units.append(frame.unit)
        if skip_here:
            frame.skip = True
            self.skip_depth += 1
        if tag == "section":
            self.section_id = _attr(attrs, "id")
            self.component = _attr(attrs, "data-component")
            self.section_label = ""
        elif tag == "header" and _attr(attrs, "data-component"):
            self.component = _attr(attrs, "data-component")
            self.section_id = ""
            self.section_label = ""
        if tag == "h2" and self.skip_depth == 0:
            self.h2_label = []
        if self.h2_label is not None and (
            "sec-no" in classes or "q-ref" in classes
        ):
            self.label_skip += 1
        self.stack.append(frame)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if any(name == "data-blk" for name, _ in attrs):
            self.already_numbered = True

    def handle_endtag(self, tag: str) -> None:
        if tag in _BREAK_TAGS:
            self._mark_break()
        if tag in _VOID_TAGS:
            return
        for depth in range(len(self.stack) - 1, -1, -1):
            if self.stack[depth].tag == tag:
                break
        else:
            return
        while len(self.stack) > depth:
            frame = self.stack.pop()
            if frame.unit is not None:
                self.unit_depth -= 1
                if self.open_units and self.open_units[-1] == frame.unit:
                    self.open_units.pop()
            if frame.skip:
                self.skip_depth -= 1
            if frame.tag == "header":
                self.header_depth -= 1
            if frame.tag == "h2" and self.h2_label is not None:
                self.section_label = "".join(self.h2_label).strip()
                self.h2_label = None
            if self.h2_label is not None and (
                "sec-no" in frame.classes or "q-ref" in frame.classes
            ):
                self.label_skip -= 1

    def handle_data(self, data: str) -> None:
        if self.h2_label is not None and self.label_skip == 0:
            self.h2_label.append(data)
        if self.open_units and self.skip_depth == 0:
            info = self.infos[self.open_units[-1]]
            if info["length"] < 120:
                collapsed = re.sub(r"\s+", " ", data)
                if collapsed.strip():
                    info["text"].append(collapsed)
                    info["length"] += len(collapsed)
        elif self.open_units:
            # svg の中の文字（図の箱の題など）だけは抜き書きに使う。script・style は使わない。
            tops = [f.tag for f in self.stack]
            if "svg" in tops and "script" not in tops and "style" not in tops and "title" not in tops:
                info = self.infos[self.open_units[-1]]
                if info["length"] < 120:
                    collapsed = re.sub(r"\s+", " ", data)
                    if collapsed.strip():
                        info["text"].append(collapsed)
                        info["length"] += len(collapsed)


def number_blocks(html: str) -> tuple[str, list[BlockInfo]]:
    """頁の単位に data-blk を振る。返るもの＝(番号を足した HTML, 単位の情報の一覧)。

    既に data-blk の付いた頁・単位が1つも無い頁は HTML をそのまま返す（情報の一覧は空）。
    """
    if not html or "<" not in html:
        return html, []
    parser = _Numberer(html)
    try:
        parser.feed(html)
        parser.close()
    except Exception:
        return html, []
    if parser.already_numbered or not parser.infos:
        return html, []
    pieces: list[str] = []
    cursor = 0
    infos: list[BlockInfo] = []
    for entry in parser.infos:
        at = entry["insert_at"]
        pieces.append(html[cursor:at])
        pieces.append(' data-blk="%d"' % entry["number"])
        cursor = at
        excerpt = re.sub(r"\s+", " ", "".join(entry["text"])).strip()[:40]
        infos.append(
            BlockInfo(
                number=entry["number"],
                section_id=entry["section_id"],
                section_label=entry["section_label"],
                component=entry["component"],
                kind=entry["kind"],
                excerpt40=excerpt,
            )
        )
    pieces.append(html[cursor:])
    return "".join(pieces), infos

"""原稿（Markdown）をブロックに分け、頁へ組む（2026-10-09・指摘と添削の作り込み）。

出所：ブロックの分け方は akapen 0.2.0（MIT）の添削の雛形の parseBlocks と同じ規則。

何のための部品か＝原稿の頁（部品 manuscript）で、利用者が原稿そのものに指摘を打つ・直す。
頁には原稿が2通りで入る。
  ① 見せる版＝render_markdown が組む `<article class="ms" data-prose="raw">`。ブロックごとに
     `<div class="ms-blk" data-ms="N" data-blk="N" data-ms-type="型">` で包む（N は1起算の通し番号）。
  ② 正本＝source_textarea が組む hidden の textarea（id="ms-source"）。頁の script はこの value を
     読んで同じ規則でブロックに分け、直した完成形を書き戻す。value は原文と逐語一致（改行は LF）。

⚠️ブロックの分け方（parse_blocks）は JS 側（指摘と添削の script）と**同じ規則**でなければ、
   番号が頁と回答でずれる。ここは akapen の parseBlocks の移植で、空行区切り・型（heading／
   paragraph／list／table／quote／code／hr／comment）・先頭の余白（head）・直後の区切り（gap）まで
   同じにしてある。復元（head ＋ 各ブロックの md ＋ gap）は原文と1字も違わない。
   JS と数字の食い違いが出うる所は2つだけ＝①JS の `\\s`・trim は Unicode の空白のうち一部だけを
   空白とみなす（Python の str.strip とは違う）ので、空白の集合を JS と同じに固定してある
   ②JS の `.` は \\n・\\r・\\u2028・\\u2029 を含まないので、同じ文字の集合に置き換えてある。
   ⚠️改行は LF にそろえてから分ける（render_markdown がそろえる。textarea の value も LF）。
   CRLF のまま分けると、JS も Python も fence の行が fence と読めない。
⚠️ブロックの無い原稿（空・空白だけ）は、復元のために head に原文全体を入れる（JS の移植元は
   この場合に改行が1つ増える）。ブロックの数は0で JS と同じ。

安全＝生の HTML は全部エスケープする。リンクは押せる形にしない（行き先は scheme を外して薄く添える）。
頁の文字に `http://`・`https://`・`file://` が残ると検品の外部依存の判定で落ちるので、
本文・コード・textarea の文字は先頭の1字を文字参照にして割る（ブラウザが描く文字と textarea の value は
原文のまま）。
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

__all__ = [
    "Block",
    "Parsed",
    "count_blocks",
    "defang_urls",
    "normalize_newlines",
    "parse_blocks",
    "render_markdown",
    "restore",
    "source_textarea",
]

# --- JS と同じ「空白」「任意の1字」 -------------------------------------------------------------
# JS の \s と trim が空白とみなす文字（Python の \s や str.strip とは集合が違う）。
_JS_SPACE = (
    "\t\n\x0b\x0c\r            "
    "      　﻿"
)
_S = "[" + _JS_SPACE + "]"
_NS = "[^" + _JS_SPACE + "]"
# JS の `.` は行の終わりの文字を含まない。
_DOT = "[^\n\r  ]"

# 差分の印に使う私用領域の4文字（移植元が構造の検出の前に外す）。原稿に混じっていても検出は無視する。
_SENT = re.compile("[-]")

RE_HEADING = re.compile("^(#{1,6})(" + _S + "+|\\Z)")
RE_FENCE = re.compile("^" + _S + "{0,3}(`{3,}|~{3,})(" + _DOT + "*)\\Z")
RE_HR = re.compile(
    "^" + _S + "{0,3}(?:(?:-" + _S + "*){3,}|(?:\\*" + _S + "*){3,}|(?:_" + _S + "*){3,})\\Z"
)
RE_QUOTE = re.compile("^" + _S + "{0,3}>")
RE_ITEM = re.compile("^(" + _S + "*)([-*+]|[0-9]{1,9}[.)])(" + _S + "+)(" + _DOT + "*)\\Z")
RE_TSEP = re.compile(
    "^" + _S + "*\\|?" + _S + "*:?-+:?" + _S + "*(?:\\|" + _S + "*:?-+:?" + _S + "*)*\\|?" + _S + "*\\Z"
)
RE_COMMENT = re.compile("^" + _S + "{0,3}<!--")
RE_FENCE_CLOSE = re.compile("^(`{3,}|~{3,})" + _S + "*\\Z")
_RE_QUOTE_MARK = re.compile("^" + _S + "{0,3}>" + _S + "?")

TYPES = ("heading", "paragraph", "list", "table", "quote", "code", "hr", "comment")


@dataclass
class Block:
    """原稿の1ブロック。type は TYPES のどれか・md は原文のまま・gap は次のブロックまでの区切り。"""

    type: str
    md: str
    gap: str = ""


@dataclass
class Parsed:
    """parse_blocks の結果。head は先頭の空行・items はブロック・ends_nl は原文が改行で終わるか。"""

    head: str
    items: list[Block] = field(default_factory=list)
    ends_nl: bool = False


def _clean(text: str) -> str:
    return _SENT.sub("", text)


def _is_blank(line: str) -> bool:
    return _clean(line).strip(_JS_SPACE) == ""


def normalize_newlines(text: str) -> str:
    """CRLF と単独の CR を LF にそろえる（ブラウザの textarea の value と同じ規則）。"""
    return text.replace("\r\n", "\n").replace("\r", "\n")


def _line_type(cl: str, nxt: str | None) -> str:
    if RE_COMMENT.match(cl):
        return "comment"
    if RE_FENCE.match(cl):
        return "code"
    if RE_HEADING.match(cl):
        return "heading"
    if RE_HR.match(cl):
        return "hr"
    if RE_QUOTE.match(cl):
        return "quote"
    if RE_ITEM.match(cl):
        return "list"
    if "|" in cl and nxt is not None:
        cn = _clean(nxt)
        if "|" in cn and RE_TSEP.match(cn):
            return "table"
    return "paragraph"


def parse_blocks(md: str) -> Parsed:
    """原稿を、空行区切りを基本に型付きのブロックへ分ける。復元は restore(parse_blocks(md)) == md。"""
    ends_nl = md.endswith("\n")
    lines = md.split("\n")
    if ends_nl:
        lines.pop()
    n = len(lines)
    items: list[Block] = []
    head = ""
    blanks: list[str] = []
    i = 0
    while i < n:
        if _is_blank(lines[i]):
            blanks.append(lines[i])
            i += 1
            continue
        if not items:
            head = "".join(b + "\n" for b in blanks)
        else:
            items[-1].gap = "".join("\n" + b for b in blanks) + "\n"
        blanks = []
        cl = _clean(lines[i])
        kind = _line_type(cl, lines[i + 1] if i + 1 < n else None)
        j = i + 1
        if kind == "code":
            fence = RE_FENCE.match(cl).group(1)
            while j < n:
                closing = RE_FENCE_CLOSE.match(_clean(lines[j]).strip(_JS_SPACE))
                j += 1
                if closing and closing.group(1)[0] == fence[0] and len(closing.group(1)) >= len(fence):
                    break
        elif kind == "comment":
            if "-->" not in cl:
                while j < n:
                    c = _clean(lines[j])
                    j += 1
                    if "-->" in c:
                        break
        elif kind in ("heading", "hr"):
            pass
        elif kind == "table":
            while j < n and not _is_blank(lines[j]) and "|" in _clean(lines[j]):
                j += 1
        elif kind == "quote":
            while j < n and not _is_blank(lines[j]) and RE_QUOTE.match(_clean(lines[j])):
                j += 1
        elif kind == "list":
            while j < n and not _is_blank(lines[j]):
                t = _line_type(_clean(lines[j]), lines[j + 1] if j + 1 < n else None)
                if t in ("list", "paragraph"):
                    j += 1
                else:
                    break
        else:
            while j < n and not _is_blank(lines[j]):
                t = _line_type(_clean(lines[j]), lines[j + 1] if j + 1 < n else None)
                if t == "paragraph":
                    j += 1
                else:
                    break
        items.append(Block(kind, "\n".join(lines[i:j]), ""))
        i = j
    tail = "".join("\n" + b for b in blanks) + ("\n" if ends_nl else "")
    if items:
        items[-1].gap = tail
    else:
        head = md
    return Parsed(head, items, ends_nl)


def restore(parsed: Parsed) -> str:
    """parse_blocks の結果から原文を復元する（head ＋ 各ブロックの md ＋ gap）。"""
    return parsed.head + "".join(block.md + block.gap for block in parsed.items)


def count_blocks(md: str) -> int:
    """原稿のブロック数（頁の data-blk の最大値）。"""
    return len(parse_blocks(normalize_newlines(md)).items)


# --- 文字の安全（頁に URL の形を残さない） -----------------------------------------------------

_SCHEME_TEXT = re.compile(r"(?i)(?:https?|file)://")
_PROTOCOL_RELATIVE_ATTR = re.compile(
    "(?i)((?:src|href|action|formaction)\\s*)=(\\s*[\"']?//)"
)


def defang_urls(escaped: str) -> str:
    """エスケープ済みの文字から、検品の外部依存の判定に当たる形を割る。ブラウザが描く文字は変わらない。

    `https://`・`http://`・`file://` は先頭の1字を文字参照にする。`src=//…` のような
    プロトコル相対の属性の形は `=` を文字参照にする。2度かけても同じ（べき等）。
    """

    def _scheme(match: re.Match) -> str:
        text = match.group(0)
        return "&#%d;%s" % (ord(text[0]), text[1:])

    escaped = _SCHEME_TEXT.sub(_scheme, escaped)
    return _PROTOCOL_RELATIVE_ATTR.sub(lambda m: m.group(1) + "&#61;" + m.group(2), escaped)


def _esc(text: str) -> str:
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&#39;")
    )


# --- インライン ---------------------------------------------------------------------------------

_PH_OPEN = ""
_PH_CLOSE = ""
_PH_RESTORE = re.compile(_PH_OPEN + "([0-9]+)" + _PH_CLOSE)
_INLINE_LIMIT = 20000

_RE_CODE = re.compile("(`+)(?!`)([\\s\\S]*?[^`])\\1(?!`)")
_RE_IMAGE = re.compile("!\\[([^\\]]*)\\]\\(([^)" + _JS_SPACE + "]+)(?:" + _S + "+\"[^\"]*\")?\\)")
_RE_LINK = re.compile("\\[([^\\]]+)\\]\\(([^)" + _JS_SPACE + "]+)(?:" + _S + "+\"[^\"]*\")?\\)")
_RE_AUTOLINK = re.compile("<(https?://[^" + _JS_SPACE + "<>]+)>")
_RE_BARE_URL = re.compile(
    "(^|[^A-Za-z0-9" + _PH_OPEN + _PH_CLOSE + "])(https?://[^" + _JS_SPACE + "<>" + _PH_OPEN + _PH_CLOSE + "]+)"
)
_RE_URL_TAIL = re.compile("[.,;:!?)）」』。、]+\\Z")
_RE_URL_SCHEME = re.compile("(?i)^(?:https?|file):/{2,3}")
_RE_PAD_CODE = re.compile("^ (" + _DOT + "+) $")
_RE_STRONG_STAR = re.compile("\\*\\*(?=" + _NS + ")([\\s\\S]*?" + _NS + ")\\*\\*")
_RE_STRONG_UNDER = re.compile("__(?=" + _NS + ")([\\s\\S]*?" + _NS + ")__")
_RE_EM_STAR = re.compile("(^|[^*A-Za-z0-9_])\\*(?=" + _NS + ")([^*\\n]*?" + _NS + ")\\*(?![A-Za-z0-9_])")
_RE_EM_UNDER = re.compile("(^|[^_A-Za-z0-9])_(?=" + _NS + ")([^_\\n]*?" + _NS + ")_(?![A-Za-z0-9_])")
_RE_HARD_BREAK = re.compile(" {2,}\\n")


def _url_shown(url: str) -> str:
    """リンクの行き先の見せ方。scheme を外す（頁に URL の形を残さない・押せるリンクにしない）。"""
    return _RE_URL_SCHEME.sub("", url)


def _link_html(inner_html: str, url: str) -> str:
    return (
        '<span class="ms-link">%s</span><span class="ms-url">（%s）</span>'
        % (inner_html, _esc(_url_shown(url)))
    )


def _emphasis(text: str, put) -> str:
    """強調（** __ * _）。⚠️一致した区間を丸ごと置き場の印に替えるので、タグの入れ子が崩れない。"""

    def _em_only(inner: str) -> str:
        inner = _RE_EM_STAR.sub(lambda m: m.group(1) + put("<em>" + m.group(2) + "</em>"), inner)
        return _RE_EM_UNDER.sub(lambda m: m.group(1) + put("<em>" + m.group(2) + "</em>"), inner)

    text = _RE_STRONG_STAR.sub(lambda m: put("<strong>" + _em_only(m.group(1)) + "</strong>"), text)
    text = _RE_STRONG_UNDER.sub(lambda m: put("<strong>" + _em_only(m.group(1)) + "</strong>"), text)
    return _em_only(text)


def _inline(text: str) -> str:
    """1ブロックの文を、インラインの HTML にする。生の HTML は全部エスケープされる。"""
    if len(text) > _INLINE_LIMIT:
        return defang_urls(_esc(text))
    placeholders: list[str] = []

    def put(html: str) -> str:
        placeholders.append(html)
        return _PH_OPEN + str(len(placeholders) - 1) + _PH_CLOSE

    s = _RE_CODE.sub(
        lambda m: put("<code>" + _esc(_RE_PAD_CODE.sub(lambda p: p.group(1), m.group(2))) + "</code>"), text
    )
    s = _RE_IMAGE.sub(
        lambda m: put('<span class="ms-img">[画像%s]</span>' % ((": " + _esc(m.group(1))) if m.group(1) else "")),
        s,
    )
    s = _RE_LINK.sub(
        lambda m: put(_link_html(_emphasis(_esc(m.group(1)), put), m.group(2))), s
    )
    s = _RE_AUTOLINK.sub(
        lambda m: put('<span class="ms-link">%s</span>' % _esc(_url_shown(m.group(1)))), s
    )

    def _bare(m: re.Match) -> str:
        url = m.group(2)
        shown = _RE_URL_TAIL.sub("", url)
        return m.group(1) + put('<span class="ms-link">%s</span>' % _esc(_url_shown(shown))) + url[len(shown):]

    s = _RE_BARE_URL.sub(_bare, s)
    s = _emphasis(_esc(s), put)
    s = _RE_HARD_BREAK.sub("<br>", s)
    out = s
    for _ in range(8):
        if _PH_OPEN not in out:
            break
        out = _PH_RESTORE.sub(lambda m: placeholders[int(m.group(1))], out)
    return defang_urls(out)


# --- ブロックごとの描画 --------------------------------------------------------------------------


def _split_row(raw: str) -> list[str]:
    s = raw.lstrip(" \t")
    if s[:1] == "|":
        s = s[1:]
    s = s.rstrip(" \t")
    if s[-1:] == "|":
        s = s[:-1]
    return [c.strip(_JS_SPACE).replace("", "|") for c in s.replace("\\|", "").split("|")]


def _render_table(lines: list[str]) -> str:
    head = _split_row(lines[0])
    seps = [c.strip(_JS_SPACE) for c in _split_row(lines[1])]
    align = []
    for c in seps:
        if re.fullmatch(":-+:", c):
            align.append("center")
        elif re.fullmatch("-+:", c):
            align.append("right")
        elif re.fullmatch(":-+", c):
            align.append("left")
        else:
            align.append("")
    cols = len(head)

    def cell(tag: str, text: str, col: int) -> str:
        style = ' style="text-align:%s"' % align[col] if col < len(align) and align[col] else ""
        return "<%s%s>%s</%s>" % (tag, style, _inline(text), tag)

    out = ['<div class="scroll"><table><thead><tr>']
    out.extend(cell("th", head[c], c) for c in range(cols))
    out.append("</tr></thead><tbody>")
    for r in range(2, len(lines)):
        row = _split_row(lines[r])
        out.append("<tr>")
        out.extend(cell("td", row[c] if c < len(row) else "", c) for c in range(cols))
        out.append("</tr>")
    out.append("</tbody></table></div>")
    return "".join(out)


def _render_list(lines: list[str]) -> str:
    """箇条書き。入れ子はインデントの深さで決める。⚠️移植元は浅い行に戻ると先の項目を捨てるので、
    ここでは最上位の並びが続くかぎり全部を順に出す（原稿の文字を黙って消さない）。"""
    stack: list[dict] = []
    roots: list[dict] = []
    last_item: dict | None = None
    for raw in lines:
        m = RE_ITEM.match(raw)
        if not m:
            if last_item is not None:
                last_item["text"].append(raw.lstrip(" ") if raw.strip() else raw)
            continue
        indent = len(m.group(1))
        ordered = any(ch.isdigit() for ch in m.group(2))
        start = int(re.match("[0-9]+", m.group(2)).group(0)) if ordered else 1
        content = raw[len(m.group(1)) + len(m.group(2)) + len(m.group(3)):]
        while stack and indent < stack[-1]["indent"]:
            stack.pop()
        if not stack:
            level = {"indent": indent, "ordered": ordered, "start": start, "items": []}
            roots.append(level)
            stack.append(level)
        elif indent > stack[-1]["indent"] and stack[-1]["items"]:
            level = {"indent": indent, "ordered": ordered, "start": start, "items": []}
            stack[-1]["items"][-1]["sub"].append(level)
            stack.append(level)
        else:
            level = stack[-1]
        last_item = {"text": [content], "sub": []}
        level["items"].append(last_item)

    def render_level(level: dict) -> str:
        tag = "ol" if level["ordered"] else "ul"
        attr = ' start="%d"' % level["start"] if level["ordered"] and level["start"] != 1 else ""
        body = "".join(
            "<li>" + _inline("\n".join(item["text"])) + "".join(render_level(s) for s in item["sub"]) + "</li>"
            for item in level["items"]
        )
        return "<%s%s>%s</%s>" % (tag, attr, body, tag)

    return "".join(render_level(root) for root in roots)


def _render_block(block: Block) -> str:
    lines = _clean(block.md).split("\n")
    kind = block.type
    if kind == "heading":
        m = RE_HEADING.match(lines[0])
        level = len(m.group(1))
        content = re.sub(_S + "+#+" + _S + "*\\Z", "", lines[0][m.end():])
        return "<h%d>%s</h%d>" % (level, _inline(content), level)
    if kind == "hr":
        return "<hr>"
    if kind == "comment":
        return ""
    if kind == "code":
        fm = RE_FENCE.match(lines[0])
        lang = (fm.group(2).strip(_JS_SPACE).split() or [""])[0] if fm else ""
        end = len(lines)
        if len(lines) > 1:
            closing = RE_FENCE_CLOSE.match(lines[-1].strip(_JS_SPACE))
            if closing and fm and closing.group(1)[0] == fm.group(1)[0] and len(closing.group(1)) >= len(fm.group(1)):
                end = len(lines) - 1
        cls = ' class="lang-%s"' % _esc(lang) if lang else ""
        return "<pre><code%s>%s</code></pre>" % (cls, defang_urls(_esc("\n".join(lines[1:end]))))
    if kind == "quote":
        stripped = []
        for line in lines:
            m = _RE_QUOTE_MARK.match(line)
            stripped.append(line[m.end():] if m else line)
        return "<blockquote>" + _render_blocks("\n".join(stripped)) + "</blockquote>"
    if kind == "table":
        return _render_table(lines)
    if kind == "list":
        return _render_list(lines)
    return "<p>" + _inline("\n".join(line.lstrip(" ") for line in lines)) + "</p>"


def _render_blocks(md: str) -> str:
    """入れ子（引用の中）用。外側のブロックの枠（ms-blk）は付けない。"""
    return "".join(_render_block(block) for block in parse_blocks(md).items)


def render_markdown(md: str) -> str:
    """原稿を、頁に載せる見せる版の HTML にする。

    返るもの＝`<article class="ms" data-prose="raw">` の中に、ブロックごとの
    `<div class="ms-blk" data-ms="N" data-blk="N" data-ms-type="型">…</div>`（N は1起算）。
    HTML コメントのブロックは hidden の空の div で位置だけ残す（番号は数える）。
    ⚠️data-prose="raw" の中は、検品が用語の包装を求めない（原稿の語を勝手に包まないため）。
    """
    parsed = parse_blocks(normalize_newlines(md))
    out = ['<article class="ms" data-prose="raw">']
    for number, block in enumerate(parsed.items, start=1):
        hidden = " hidden" if block.type == "comment" else ""
        out.append(
            '<div class="ms-blk" data-ms="%d" data-blk="%d" data-ms-type="%s"%s>%s</div>'
            % (number, number, block.type, hidden, _render_block(block))
        )
    out.append("</article>")
    return "\n".join(out)


def source_textarea(md: str, *, label: str, path: str, sha: str, eol: str) -> str:
    """原稿の正本を入れる hidden の textarea を組む。

    ブラウザの textarea.value は原文と逐語一致（改行は LF）。HTML の決まりで textarea の直後の
    改行は1つ捨てられるので、`<textarea …>` の直後に改行を1つ入れる（原稿の先頭が改行でも保たれる）。
    中身はエスケープし、`https://` などは先頭の1字を文字参照にして頁の文字に残さない。
    eol は元のファイルの改行（lf か crlf）＝script が書き戻すときに使う。
    """
    body = defang_urls(_esc_text(normalize_newlines(md)))
    attrs = (
        'id="ms-source" class="ms-source" hidden readonly aria-hidden="true" '
        'data-label="%s" data-path="%s" data-sha="%s" data-eol="%s"'
        % (_esc(label), _esc(path), _esc(sha), "crlf" if eol == "crlf" else "lf")
    )
    return "<textarea %s>\n%s</textarea>" % (attrs, body)


def _esc_text(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

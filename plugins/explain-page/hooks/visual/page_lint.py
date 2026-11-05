#!/usr/bin/env python3
"""頁を組む前後の、機械の点検と補い（2026-10-19・利用者が選んだ H2・H3・H5）。

何のために＝試問（文脈ゼロのAIが頁を読む点検）が見つける指摘の多くは、機械で見つけられる型だった
（数字が根拠の表に無い・用語が説明されていない・判断欄の選択肢に絵が無い・単位が略されている）。
試問は1巡で約11万トークンかかる。機械の点検を先に走らせ、手前の掃除を0トークンで済ませる。

ここにあるもの
  link_proposals(content)        H2 案のカード（proposals）から、判断欄の選択肢へ絵・利点・代償・推奨を補う。
  number_source_warnings(c)      H3 本文の数字が、根拠・表・図表・詳細のどこにも無いときの警告。
  abbreviated_unit_warnings(c)   H3 「4.7M」「110k」のように略した単位の警告。
  mixed_thumb_warnings(c)        H3 判断欄の選択肢の絵が、一部にしか無い群の警告。
  unexplained_ascii_warnings(h)  H3 組んだ頁で、英字の語が用語集にも吹き出しにも無いときの警告。
  tool_version(script_dir)       H5 この頁を作った仕組みの版（本線・作業場・公開版・プラグイン＋コミット番号）。

決まり
  ・警告は全部「止めはしない」。意味が通じるかは機械では見られない＝この点検は手前の掃除で、通ることの保証ではない。
  ・入力の定義は書き換えない（link_proposals は写しを返す）。何度かけても同じ結果。
  ・個人の名前・自分の機械のパスは出さない（版は種類とコミット番号だけ）。
"""
from __future__ import annotations

import copy
import html
import os
import re
import subprocess
from collections.abc import Mapping
from typing import Any

# ---------------------------------------------------------------- 共通の歩き方
_DEPTH_LIMIT = 40
# 数字の出所に数える場所（根拠・表・図表・詳細）。ここ以外の文字が「本文」。
_CORPUS_KEYS = frozenset(("rows", "head", "caption", "stats", "table", "evidence", "source"))
_CORPUS_COMPONENTS = frozenset(("evidence", "details", "glossary"))
_PROSE_KEYS = frozenset((
    "headline", "overview", "text", "claim", "pros", "cons", "title", "why", "pairs", "items",
    "ordered", "notes", "note", "summary", "label",
))
_SKIP_KEYS = frozenset(("svg", "path", "deck", "tex", "log", "diff", "target", "selector", "markdown", "thumb", "exhibit"))


def _walk(value, key="", ctx=(), depth=0):
    """(鍵名, 値, 文脈) を深さ優先で返す。文脈＝祖先の鍵名と、節の component 名の並び。"""
    yield key, value, ctx
    if depth >= _DEPTH_LIMIT:
        return
    if isinstance(value, Mapping):
        comp = str(value.get("component", "") or "")
        sub_ctx = ctx + ((("component:" + comp),) if comp else ())
        for name, child in value.items():
            name = str(name)
            if name in _SKIP_KEYS and not isinstance(child, Mapping):
                continue
            yield from _walk(child, name, sub_ctx + (name,), depth + 1)
    elif isinstance(value, (list, tuple)):
        for child in value:
            yield from _walk(child, key, ctx, depth + 1)


def _is_corpus(ctx):
    for item in ctx:
        if item in _CORPUS_KEYS:
            return True
        if item.startswith("component:") and item[len("component:"):] in _CORPUS_COMPONENTS:
            return True
    return False


def _texts(content):
    """本文の文字と、数字の出所の文字に分けて返す。"""
    prose, corpus = [], []
    for key, value, ctx in _walk(content):
        if isinstance(value, str) and value.strip():
            if _is_corpus(ctx):
                corpus.append(value)
            elif key in _PROSE_KEYS or key == "":
                prose.append((key or "本文", value))
        elif isinstance(value, (int, float)) and not isinstance(value, bool) and _is_corpus(ctx):
            corpus.append(str(value))
    return prose, corpus


# ---------------------------------------------------------------- H3 数字の出所
_NUM = re.compile(r"(?<![\w.])\d[\d,]*(?:\.\d+)?%?")


def _significant_numbers(text):
    out = []
    for match in _NUM.finditer(text):
        raw = match.group(0)
        digits = raw.replace(",", "").rstrip("%")
        if not digits:
            continue
        has_dot = "." in digits
        if not (len(digits.replace(".", "")) >= 4 or has_dot or raw.endswith("%")):
            continue
        if re.fullmatch(r"(19|20)\d\d", digits):  # 年は数えない
            continue
        out.append(digits)
    return out


# 2026-11-04（A5・利用者の回答＝赤ペン diagram-skills-impl-01 の Q9 A）：1枚の図の量の上限
#   （diagram-design の予算＝箱9・矢印12）。色の数は数えない（手元の図の色は判定の意味を持つ）。
#   実測（2026-11-04）＝重複を除いた既存の図165個のうち箱9超は5個・矢印12超は0個。
DIAGRAM_BUDGET_NODES = 9
DIAGRAM_BUDGET_EDGES = 12


def diagram_budget_warnings(content):
    """箱が9個を超える・矢印が12本を超える図を知らせる（止めはしない）。

    数えるのは diagram（箱と矢印）と diagram_text（1行記法を変換した後）と mermaid の流れ図（変換した後）。
    道具が作る頁（審査結果の頁）には呼び出し側が使わない（利用者の回答 Q10 A＝作る人が図を分けられない）。
    """
    found = []
    number = 0
    for key, value, _ctx in _walk(content):
        if key == "diagram" and isinstance(value, Mapping) and isinstance(value.get("nodes"), list):
            nodes, edges = value.get("nodes") or [], value.get("edges") or []
            title = str(value.get("num") or value.get("title") or value.get("caption") or "")
        elif key == "diagram_text" and isinstance(value, (str, Mapping)):
            try:
                from .diagram_dsl import parse_diagram_text
            except ImportError:
                continue
            text = value.get("text", "") if isinstance(value, Mapping) else value
            parsed = parse_diagram_text(str(text or ""))
            nodes, edges = parsed.get("nodes") or [], parsed.get("edges") or []
            title = str(value.get("num") or value.get("caption") or "") if isinstance(value, Mapping) else ""
        elif key == "mermaid" and isinstance(value, (str, Mapping)):
            try:
                from .figures import parse_mermaid
            except ImportError:
                continue
            text = value.get("text", "") if isinstance(value, Mapping) else value
            parsed = parse_mermaid(str(text or ""))
            if parsed.get("kind") not in ("flowchart", "state"):
                continue
            nodes, edges = parsed.get("nodes") or [], parsed.get("edges") or []
            title = str(value.get("num") or value.get("caption") or "") if isinstance(value, Mapping) else ""
        else:
            continue
        number += 1
        over = []
        if len(nodes) > DIAGRAM_BUDGET_NODES:
            over.append("箱が%d個（%d個まで）" % (len(nodes), DIAGRAM_BUDGET_NODES))
        if len(edges) > DIAGRAM_BUDGET_EDGES:
            over.append("矢印が%d本（%d本まで）" % (len(edges), DIAGRAM_BUDGET_EDGES))
        if over:
            name = "図%s" % (title if title else number)
            found.append("⚠️%s：%s＝全体の図と詳細の図の2枚に分けると読みやすい（止めはしない・diagram-design の上限）"
                         % (name, "・".join(over)))
    return found


def number_source_warnings(content, limit=6):
    """本文に出る数字（4桁以上・小数・%）が、根拠・表・図表・詳細の文字のどこにも無ければ警告する。"""
    prose, corpus = _texts(content)
    corpus_text = " ".join(corpus).replace(",", "")
    seen, missing = set(), []
    for key, text in prose:
        for digits in _significant_numbers(text):
            if digits in seen:
                continue
            seen.add(digits)
            if digits not in corpus_text:
                missing.append((digits, key))
    if not missing:
        return []
    shown = "・".join("%s（%s）" % item for item in missing[:limit])
    more = "" if len(missing) <= limit else "・ほか%d件" % (len(missing) - limit)
    return ["⚠️本文の数が、根拠・表・図表・詳細のどこにも無い（止めはしない）: %s%s＝出所の行か表を足す" % (shown, more)]


# ---------------------------------------------------------------- 2026-10-31 利用者の思想（認知負荷を下げる二重構造）の点検
# 案V9：書き留めた思想を機械で守る。全部「止めはしない」の知らせ（較正前＝数を見て強めるか決める）。
_EMPH = ("**", "==", "[[")
_LONG_ASIDE = re.compile(r"（[^（）]{40,}）")


def card_key_warnings(content, min_chars=120):
    """案V1：本文が長い（120字以上）のに、中心メッセージ（key）の無いカードを数える。"""
    count = 0
    for key, value, _ctx in _walk(content):
        if key != "cards" or not isinstance(value, (list, tuple)):
            continue
        for card in value:
            if not isinstance(card, Mapping):
                continue
            text = str(card.get("text", "") or "")
            if len(text) >= min_chars and not str(card.get("key", "") or "").strip():
                count += 1
    if not count:
        return []
    return ["⚠️中心メッセージの無い長いカードが %d 枚（止めはしない）＝カードに \"key\":\"1行の中心メッセージ\" を足す（1カード1メッセージ）" % count]


def plain_text_warnings(content, min_chars=200):
    """案V2：強調（**太字**・==ハイライト==・[[色札]]）が1つも無い長い文（200字以上）を数える。"""
    count = 0
    for key, value, ctx in _walk(content):
        if not isinstance(value, str) or len(value) < min_chars or _is_corpus(ctx):
            continue
        if key not in _PROSE_KEYS and key != "":
            continue
        if not any(mark in value for mark in _EMPH):
            count += 1
    if not count:
        return []
    return ["⚠️強調の無い長い文が %d か所（止めはしない）＝中心の1文を **太字**、但し書きを ==ハイライト==、数を [[num:…]]、リスクを [[risk:…]] にする" % count]


def long_aside_warnings(content):
    """案V5：本文の中の長い括弧の補足（40字以上）を数える＝ [[info:…]]（ⓘ）に逃がせる。"""
    count = 0
    for key, value, ctx in _walk(content):
        if not isinstance(value, str) or _is_corpus(ctx):
            continue
        if key not in _PROSE_KEYS and key != "":
            continue
        count += len(_LONG_ASIDE.findall(value))
    if not count:
        return []
    return ["ⓘ 本文の中の長い括弧の補足が %d か所（止めはしない）＝本質でない補足は [[info:…]]（ⓘ・ホバーで出る）にしまえる" % count]


# ---------------------------------------------------------------- H3 略した単位
_ABBREV = re.compile(r"(?<![A-Za-z0-9_.])(\d[\d,]*(?:\.\d+)?)\s?([MmKk])(?![A-Za-z0-9])")


def abbreviated_unit_warnings(content, limit=6):
    prose, _ = _texts(content)
    found = []
    for key, text in prose:
        for match in _ABBREV.finditer(text):
            token = match.group(0).replace(" ", "")
            if token not in [f for f, _ in found]:
                found.append((token, key))
    if not found:
        return []
    shown = "・".join("%s（%s）" % item for item in found[:limit])
    return ["⚠️単位が略されている（止めはしない）: %s＝「470万」「1,000」のように書く（初めて読む人は M や k を読めない）" % shown]


# ---------------------------------------------------------------- H3 選択肢の絵が一部だけ
def _decision_bodies(content):
    bodies = []
    emitted = False
    sections = content.get("sections")
    if isinstance(sections, (list, tuple)):
        for entry in sections:
            if isinstance(entry, Mapping) and str(entry.get("component", "")).strip() == "decision":
                body = entry.get("content")
                if body is None:
                    body = content.get("decision")
                if body is not None:
                    bodies.append(body)
                    emitted = True
    if not emitted and content.get("decision") is not None:
        bodies.append(content["decision"])
    return bodies


def _groups(body):
    if isinstance(body, Mapping) and isinstance(body.get("groups"), (list, tuple)):
        return [g for g in body["groups"] if isinstance(g, Mapping)]
    return []


def _withdrawn(option):
    if not isinstance(option, Mapping):
        return False
    value = option.get("withdrawn")
    return bool(value.strip()) if isinstance(value, str) else bool(value)


def _has_thumb(option):
    return isinstance(option, Mapping) and bool(option.get("thumb"))


def mixed_thumb_warnings(content):
    lines = []
    number = 0
    for body in _decision_bodies(content):
        for group in _groups(body):
            kind = str(group.get("kind", "radio") or "radio")
            if kind not in ("radio", "checkbox"):
                continue
            options = [o for o in (group.get("options") or ()) if not _withdrawn(o)]
            if not options:
                continue
            number += 1
            thumbs = sum(1 for o in options if _has_thumb(o))
            if 0 < thumbs < len(options):
                lines.append(
                    "⚠️選択肢の絵が一部にしか無い（止めはしない）: Q%d「%s」＝%d個中%d個に絵がある（絵を付けるなら全部に）"
                    % (number, " ".join(str(group.get("legend", "")).split())[:30], len(options), thumbs)
                )
    return lines


# ---------------------------------------------------------------- H2 案のカード→選択肢
_NO = re.compile(r"^\s*([A-Za-z]{1,4}\d{1,3})(?:[\s　・:：）)．.]|$)")


def _exhibit_svg(exhibit):
    """案のカードの図を、選択肢の絵（svg の文字列）へ。読めなければ None。"""
    if not exhibit:
        return None
    try:
        from .exhibits import exhibit_svg
    except ImportError:  # pragma: no cover - 単独で読んだとき
        try:
            from exhibits import exhibit_svg  # type: ignore
        except ImportError:
            exhibit_svg = None
    if isinstance(exhibit, Mapping):
        if exhibit.get("svg"):
            return str(exhibit["svg"])
        if exhibit.get("kind") and exhibit_svg:
            try:
                return exhibit_svg(str(exhibit["kind"]))
            except ValueError:
                return None
        return None
    text = str(exhibit).strip()
    if text.startswith("<svg"):
        return text
    if exhibit_svg:
        try:
            return exhibit_svg(text)
        except ValueError:
            return None
    return None


def _cards(content):
    cards = {}
    for key, value, _ctx in _walk(content):
        if key == "proposals" and isinstance(value, (list, tuple)):
            for card in value:
                if isinstance(card, Mapping) and str(card.get("no", "")).strip():
                    cards.setdefault(str(card["no"]).strip(), card)
    return cards


def _group_is_live(group):
    """判断欄の群が、問いの番号（Q1・Q2…）を持つか。レンダラーの数え方（render_components の live）と同じ。"""
    kind = str(group.get("kind", "radio") or "radio")
    if kind == "free":
        return False
    if kind in ("radio", "checkbox"):
        return any(not _withdrawn(o) for o in (group.get("options") or ()))
    if kind == "scale":
        return bool(group.get("items"))
    return bool(group.get("options"))


def _pick_id(no):
    """案の番号から、カードの枠と判断欄の入力を結ぶ id を作る（英数字・「-」「_」だけ）。"""
    safe = re.sub(r"[^A-Za-z0-9_-]", "", str(no))
    return "pk-" + safe if safe else ""


def link_proposals(content):
    """案のカード（proposals）の番号で始まる判断欄の選択肢へ、絵・利点・代償・推奨を補う。

    返るもの＝(写した content, 知らせの行の一覧)。補うのは、選択肢に無い項目だけ（書いてあればそのまま）。
    案のカードが無い・番号で始まる選択肢が無いときは、同じ content を返す。

    2026-10-19（利用者の指摘）：カード自身にも「これを選ぶ」の枠を付ける。結ぶ印は、選択肢の `pick_id` と
    カードの `pick`（同じ id）・`pick_q`（判断欄の問いの番号）。カードに `"pick": false` と書けば付けない。
    同じ番号の選択肢が複数あるときは、先の1つだけに結ぶ（id は頁で1つ）。
    """
    cards = _cards(content)
    if not cards or not isinstance(content, Mapping):
        return content, []
    new = copy.deepcopy(content)
    new_cards = _cards(new)
    notes = []
    matched_any = False
    has_group = False
    picked = []
    question = 0
    for body in _decision_bodies(new):
        for group in _groups(body):
            if _group_is_live(group):
                question += 1
            kind = str(group.get("kind", "radio") or "radio")
            if kind not in ("radio", "checkbox"):
                continue
            options = group.get("options")
            if not isinstance(options, list):
                continue
            has_group = True
            for index, option in enumerate(options):
                label = option if isinstance(option, str) else (option.get("label", "") if isinstance(option, Mapping) else "")
                match = _NO.match(str(label))
                if not match or match.group(1) not in cards:
                    continue
                no = match.group(1)
                card = cards[no]
                opt = {"label": option} if isinstance(option, str) else option
                filled = []
                if str(opt.get("label", "")).strip() == no and card.get("title"):
                    opt["label"] = "%s %s" % (no, card["title"])
                if not opt.get("thumb"):
                    svg = _exhibit_svg(card.get("exhibit"))
                    if svg:
                        opt["thumb"] = {"svg": svg}
                        filled.append("絵")
                for key, name in (("pros", "利点"), ("cons", "代償")):
                    if not str(opt.get(key, "") or "").strip() and str(card.get(key, "") or "").strip():
                        opt[key] = card[key]
                        filled.append(name)
                if "recommended" not in opt and card.get("recommended"):
                    opt["recommended"] = True
                    filled.append("推奨")
                target = new_cards.get(no, {})
                pid = _pick_id(no)
                if (
                    pid
                    and no not in picked
                    and target.get("pick") is not False
                    and not _withdrawn(opt)
                    and not str(opt.get("pick_id", "") or "").strip()
                ):
                    opt["pick_id"] = pid
                    target["pick"] = pid
                    target["pick_q"] = question
                    picked.append(no)
                    filled.append("カードの「これを選ぶ」枠")
                options[index] = opt
                matched_any = True
                if filled:
                    notes.append("ⓘ 案のカードから選択肢を補った: %s（%s）" % (no, "・".join(filled)))
    if has_group and not matched_any:
        notes.append(
            "ⓘ 案のカード（proposals）がある。判断欄の選択肢を案の番号で始める（例「%s …」）と、絵・利点・代償・推奨をカードから補う"
            % next(iter(cards))
        )
    return new, notes


# ---------------------------------------------------------------- H3 英字の語（組んだ頁）
_WORD = re.compile(r"(?<![\w./\\-])[A-Za-z]{3,}(?![\w./\\-])")
# 見出しの英語ラベルと、この作業場の会話で毎回出る名前（読み手は知っているものとして数えない）
_ASCII_OK = frozenset((
    "goal", "now", "changed", "risk", "decision", "json", "html", "pdf", "css", "url", "api", "cli", "gui", "ok",
    "claude", "code", "codex", "chatgpt", "github", "discord", "hermes", "skill", "skills",
))
_STRIP_BLOCKS = re.compile(
    r"<(script|style|svg|code|pre|details|header|footer)\b.*?</\1>|<span class=\"t\"[^>]*>.*?</span>|<!--.*?-->|<head\b.*?</head>",
    re.S,
)
_PARA = re.compile(r"<(p|li|blockquote)\b[^>]*>(.*?)</\1>", re.S)
_TAG = re.compile(r"<[^>]+>")
_GLOSSARY_BLOCK = re.compile(r"<(?:section|div|aside)[^>]*data-component=\"glossary\".*?(?=<(?:section|div|aside)[^>]*data-component=|$)", re.S)


def unexplained_ascii_warnings(built_html, limit=8):
    """組んだ頁の本文（p・li・blockquote）で、英字の語が、頁の用語集にも吹き出しにも無いものを知らせる。"""
    text = str(built_html)
    body_at = text.find("<body")
    body = text[body_at:] if body_at >= 0 else text
    glossary_text = ""
    for block in _GLOSSARY_BLOCK.findall(body):
        glossary_text += " " + html.unescape(_TAG.sub(" ", block)).lower()
    side = re.findall(r"<aside\b.*?</aside>", body, re.S)
    for block in side:  # 側柱の用語リストも、頁の用語集に数える
        glossary_text += " " + html.unescape(_TAG.sub(" ", block)).lower()
    cleaned = _STRIP_BLOCKS.sub(" ", body)
    counts: dict[str, int] = {}
    for _tag, inner in _PARA.findall(cleaned):
        plain = html.unescape(_TAG.sub(" ", inner))
        for word in _WORD.findall(plain):
            low = word.lower()
            if low in _ASCII_OK or low in glossary_text:
                continue
            counts[word] = counts.get(word, 0) + 1
    if not counts:
        return []
    ranked = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
    shown = "・".join("%s（%d）" % item for item in ranked[:limit])
    more = "" if len(ranked) <= limit else "・ほか%d語" % (len(ranked) - limit)
    return ["⚠️本文の英字の語が、用語集にも吹き出しにも無い（止めはしない）: %s%s＝日本語に言い換えるか、用語集に1行足す" % (shown, more)]


# ---------------------------------------------------------------- H5 仕組みの版
def _git(args, cwd):
    try:
        out = subprocess.run(["git", "-C", cwd] + list(args), capture_output=True, text=True, timeout=10, encoding="utf-8", errors="replace")
    except (OSError, subprocess.SubprocessError):
        return None
    return out.stdout.strip() if out.returncode == 0 else None


def classify_location(script_dir):
    """この道具が置かれている場所の種類。(種類, 作業場の名前) を返す。個人のパスは返さない。"""
    norm = str(script_dir).replace("\\", "/").lower()
    marker = "/.claude/worktrees/"
    if marker in norm:
        name = norm.split(marker, 1)[1].split("/", 1)[0]
        return "作業場", name
    if "/explain-page" in norm:
        return "公開版", ""
    if "/plugins/cache/" in norm or "/.claude/plugins/" in norm or "${claude_plugin_root}" in norm:
        return "プラグイン", ""
    return "本線", ""


def tool_version(script_dir):
    """「本線 7fa6b41e」のような版の文字列。git が使えなければ「版の記録なし」。"""
    kind, name = classify_location(script_dir)
    head = _git(["rev-parse", "--short", "HEAD"], str(script_dir))
    if not head:
        return "%s（版の記録なし）" % kind
    dirty = _git(["status", "--porcelain", "--", str(script_dir)], str(script_dir))
    parts = [kind]
    if name:
        parts.append(name)
    parts.append(head)
    text = " ".join(parts)
    if dirty:
        text += "（未コミットの変更あり）"
    return text


def stamp_version(content, script_dir):
    """provenance に「仕組みの版」を足した写しを返す（既にあれば、そのまま）。"""
    if not isinstance(content, Mapping):
        return content
    new = dict(content)
    prov = new.get("provenance")
    stamp = tool_version(script_dir)
    if isinstance(prov, Mapping):
        if "仕組みの版" in prov:
            return content
        merged = dict(prov)
        merged["仕組みの版"] = stamp
        new["provenance"] = merged
    elif prov is None:
        new["provenance"] = {"仕組みの版": stamp}
    else:
        new["provenance"] = {"出所": prov, "仕組みの版": stamp}
    return new

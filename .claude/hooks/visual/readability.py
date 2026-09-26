from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

# 正本＝ .claude/readability-rules.md（語リストと出所はそちらに書く。判定ロジックはここ）。
ROW = re.compile(r"^\|\s*(.*?)\s*\|\s*(.*?)\s*\|\s*(.*?)\s*\|$")
HEADER_TERMS = frozenset({"語", "term", "-", ""})

# B2型（mathbullet/skills ja-text-communication・原則B2）＝
# 「英単語に日本語助詞・活用を直接接続しない」を機械で拾うための語尾候補。
# 長い語尾から先に試す（「できる」を「でき」+「る」のように分割して取り逃さないため）。
# ⚠️2026-09-08の較正（実頁171枚）で「に」を外した＝「gitに」「jsonに」「pythonに」
#   のような技術用語・固有名詞への格助詞「に」の直結は、ただの名詞用法として頁の8割
#   （89/171枚・399件中319件）で当たってしまい、B2が狙う「英単語を形容動詞・動詞
#   として使う」誤りとは別物だった（「Workflow を」の「を」と同じ理由で対象外）。
#   本物のB2は「な」（形容動詞化）「する/した/して/できる/される」（動詞化）
#   「です/なら」（コピュラ）に絞る。
SUFFIXES: tuple[str, ...] = (
    "できる",
    "される",
    "した",
    "して",
    "する",
    "です",
    "なら",
    "な",
)

# 「な」は「など」「なので」「なのに」「なぜ」「なに」「なん」等、na形容詞の活用ではない
# 語の頭とも重なる。この続きが来た時は当たりにしない（2026-09-08較正＝
# implementation-result-deep.html の「decisionなど」を拾ってしまった実例で発見）。
_NA_FALSE_CONTINUATIONS: tuple[str, ...] = ("ど", "ので", "のに", "ぜ", "に", "ん")

# 英文の中でありふれた機能語＝これらは「generic な」のような造語より、
# ただの英文の一部（引用・URL・コード片の残り等）として出てくる方がずっと多い。
# 誤爆の元になりやすいので、この語だけは語尾が続いていても対象外にする。
ALLOW_CONTEXT_WORDS = frozenset(
    {
        "for", "the", "and", "is", "at", "in", "on", "to", "of", "or",
        "as", "by", "it", "be", "an", "a", "if", "this", "that", "with",
        "from", "was", "were", "are", "its", "but", "not", "can", "will",
        "may", "you", "your", "we", "our",
    }
)

_ASCII_WORD = re.compile(r"(?<![A-Za-z0-9])([a-z][A-Za-z]{2,})(?![A-Za-z0-9])")

_CODE_FENCE = re.compile(r"```.*?```", re.S)
_PRE_TAG = re.compile(r"<pre[^>]*>.*?</pre>", re.I | re.S)
_CODE_TAG = re.compile(r"<code[^>]*>.*?</code>", re.I | re.S)
_INLINE_BACKTICK = re.compile(r"`[^`\n]*`")


@dataclass(frozen=True)
class WordRule:
    term: str
    kind: str
    alternative: str


@dataclass(frozen=True)
class Rules:
    word_list: tuple[WordRule, ...] = ()


@dataclass(frozen=True)
class Hit:
    rule: str
    matched: str
    context: str


def load_rules(path: str | Path) -> Rules:
    """`.claude/readability-rules.md` の「語リスト」表を読む。無ければ空規則を返す。

    入れるもの＝正本ファイルのpath。返るもの＝Rules（word_listだけを持つ。
    機械規則＝B2型はこのファイルのコードが持つので、表からは読まない）。
    """
    file_path = Path(path)
    if not file_path.is_file():
        return Rules()
    rules: list[WordRule] = []
    try:
        text = file_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return Rules()
    # 2026-08-28（較正③）：表を読むのは「## 語リスト」の節だけ。
    # ⚠️以前はファイル中の全ての表を語リストとして読んでいたため、較正の記録を表で追記したら
    #   「種別」「自己言及」が禁止語になった（実測10件）。正本は人が育てる文書なので、節で区切る。
    in_section = False
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("## "):
            in_section = stripped[3:].strip().startswith("語リスト")
            continue
        if not in_section:
            continue
        match = ROW.match(stripped)
        if not match:
            continue
        term = match.group(1).strip().strip("`").strip()
        kind = match.group(2).strip()
        alternative = match.group(3).strip()
        if not term or term in HEADER_TERMS:
            continue
        if set(term) <= {"-", ":", " "}:
            continue
        rules.append(WordRule(term=term, kind=kind, alternative=alternative))
    return Rules(word_list=tuple(rules))


_TAG_ATTRS = re.compile(r"<([A-Za-z][A-Za-z0-9-]*)(?:\s[^<>]*)?>")


def strip_code(html_or_text: str) -> str:
    """コード片（`<code>`・`<pre>`・Markdownのバッククォート）を除いた文だけにする。

    識別子・関数名・オプション名は言い回しの対象外なので、判定にかける前にここで落とす。
    """
    text = html_or_text
    # 2026-08-28（較正③）：タグの**属性**は本文の複製（コピー釦の data-copy・表の data-label・
    # 読み上げ用の aria-label・用語ホバーの data-d）なので、判定前に落とす。
    # 落とさないと、code/pre に書いた例文が属性側で再び拾われ、自己言及の当たりが2重に出る（実測18件）。
    text = _TAG_ATTRS.sub(r"<\1>", text)
    text = _CODE_FENCE.sub(" ", text)
    text = _PRE_TAG.sub(" ", text)
    text = _CODE_TAG.sub(" ", text)
    text = _INLINE_BACKTICK.sub(" ", text)
    return text


def _context(text: str, start: int, end: int, radius: int = 20) -> str:
    left = max(0, start - radius)
    right = min(len(text), end + radius)
    return text[left:right]


def _b2_hits(text: str) -> list[Hit]:
    hits: list[Hit] = []
    for match in _ASCII_WORD.finditer(text):
        word = match.group(1)
        if word.lower() in ALLOW_CONTEXT_WORDS:
            continue
        tail = text[match.end():]
        for suffix in SUFFIXES:
            gap = 0
            if tail[:1].isspace():
                gap = 1
            if not tail[gap:].startswith(suffix):
                continue
            after_index = gap + len(suffix)
            after_char = tail[after_index:after_index + 1]
            if after_char.isalpha() and after_char.isascii():
                continue
            if suffix == "な" and any(
                tail[after_index:].startswith(cont) for cont in _NA_FALSE_CONTINUATIONS
            ):
                continue
            matched = text[match.start():match.end() + after_index]
            hits.append(
                Hit(
                    rule="b2_particle_on_english_word",
                    matched=matched,
                    context=_context(text, match.start(), match.end() + after_index),
                )
            )
            break
    return hits


def _word_list_hits(text: str, rules: Rules) -> list[Hit]:
    hits: list[Hit] = []
    for rule in rules.word_list:
        term = rule.term
        if not term:
            continue
        start = 0
        while True:
            index = text.find(term, start)
            if index < 0:
                break
            hits.append(
                Hit(
                    rule="word_list:" + term,
                    matched=term,
                    context=_context(text, index, index + len(term)),
                )
            )
            start = index + len(term)
    return hits


def check_text(text: str, rules: Rules) -> list[Hit]:
    """B2型の機械規則＋語リストを本文に掛け、当たった箇所を返す。

    入れるもの＝すでに strip_code を通した文とRules。返るもの＝Hitの一覧（無ければ空）。
    """
    if not text:
        return []
    return _b2_hits(text) + _word_list_hits(text, rules)

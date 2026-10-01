"""用語集の語を本文から探すときの「語の境目」の規則（レンダラーと検品器の共通の正本）。

2026-09-29：以前は部分一致に「前後が英数字なら別の語」を足しただけだったので、
  ①本文の「目盛り」の中の「盛り」に「数字を大きく見せる操作」の説明が付き、
  ②ファイル名「discord-feedback-skill-gap」の中の feedback に戻りの経路の説明が付いた。
  既存の頁144本を組み直して測ると、英字の語の誤りはハイフン・拡張子・URL・パスの途中の
  フォルダ名・斜線で始まるコマンド名に集中していた（例＝スキル名「…-issue-picker」の issue
  だけで22件）。
⚠️日本語は字種では決めない＝「前が漢字なら別の語」にすると、責任【主体】・前回【致命傷】・
  人間【較正】のような**正しい包装が約70件消える**（同じ測定で誤りは関【連言】及の1件だけ）。
  後ろが漢字（【致命傷】候補）・前が片仮名（ディスク【キャッシュ】）も同じく正しい方が多い。
  ∴日本語は語ごとの「別の語」の一覧（`_NOT_THIS_TERM`）で止める。
⚠️同じ測定で、英数字の境目の判定を日本語の語にも掛けていたせいで Claude【正本】・11【レンズ】・
  【罠】2件 が包まれていなかった。∴英数字の判定は「語の端が英数字の側」だけに掛ける。
⚠️レンダラー（包む側）と検品器（包装を求める側）は**必ずこの関数を使う**＝規則がずれると、
  包まなかった語を検品器が「未包装」と責めて頁が落ちる。
"""

from __future__ import annotations

# 語ごとの「この語の中に現れても、この用語ではない」別の語。
# ⚠️足すときは既存の頁で空振り（正しい包装を消していないか）を測ってから。
#   一覧は語ごとに分けてある＝「感度分析」を全部の語に効かせると、将来「分析」を
#   用語集に足した時に正しい「分析」まで止めてしまうため。
_NOT_THIS_TERM: dict[str, tuple[str, ...]] = {
    # 盛り＝数字を大きく見せる操作。目盛り・盛り込む は別の語。
    "盛り": (
        "目盛り", "山盛り", "大盛り", "花盛り", "手盛り",
        "盛り込", "盛り上", "盛り付", "盛り返", "盛り沢山", "盛りだくさん",
    ),
    # ポート＝通信を受け取るプログラムを区別する番号。サポート・エクスポート は別の語。
    "ポート": (
        "サポート", "レポート", "リポート", "エクスポート", "インポート", "パスポート",
        "トランスポート", "ビューポート", "ポートフォリオ", "ポートレート",
    ),
    # 連言＝全部そろわないと成立しない関係。「関連言及」は関連＋言及の境目をまたいでいる。
    "連言": ("関連言",),
    # 波＝上限を超えて分かれる回（2波目など）。波及・電波 は別の語。
    "波": (
        "波及", "電波", "波形", "波長", "余波", "津波", "周波", "波動", "波紋",
        "防波", "波乱", "波浪", "寒波", "熱波", "音波", "脳波",
    ),
    # 感度＝拾うべきものを拾えた割合。感度分析（前提を動かして結果の揺れを見る）は別の概念。
    "感度": ("感度分析", "感度解析", "好感度"),
}

# 英字のかたまり（URL・パス）の切れ目。日本語の文字もかたまりを切る。
_TOKEN_STOP = frozenset(" \t\r\n\"'`<>()[]{}|,;")


def _ascii_word(char: str) -> bool:
    return bool(char) and char.isascii() and (char.isalnum() or char == "_")


def _joined_ascii(text: str, index: int, step: int) -> bool:
    """語の英字の端の隣（index）が、英字の語と地続きか。step は外向き（前＝-1・後＝+1）。

    地続き＝英数字・`_`、または `-`・`.` を挟んでその先が英数字（issue-picker・feedback.md）。
    """
    if not 0 <= index < len(text):
        return False
    char = text[index]
    if _ascii_word(char):
        return True
    if char in "-.":
        beyond = index + step
        return 0 <= beyond < len(text) and _ascii_word(text[beyond])
    return False


def _ascii_token(text: str, start: int, end: int) -> tuple[int, int]:
    """語を含む英字のかたまり（空白・括弧・日本語の文字で切る）の範囲を返す。"""
    left = start
    while left > 0 and text[left - 1].isascii() and text[left - 1] not in _TOKEN_STOP:
        left -= 1
    right = end
    while right < len(text) and text[right].isascii() and text[right] not in _TOKEN_STOP:
        right += 1
    return left, right


def _inside_url(text: str, start: int, end: int) -> bool:
    left, _right = _ascii_token(text, start, end)
    return "://" in text[left:start]


def _folder_in_path(text: str, start: int, end: int) -> bool:
    """語が、ファイルのパスの途中のフォルダ名か（docs/ai-work/claims/… の claims）。

    ⚠️`/` だけでは決めない＝「P0/P1/P2」「data/ident/means_ends」のように「または」の
      意味で `/` を使う書き方が多い。∴語の直後が `/` か `\\` で、かたまりに `-` か `.`
      （ハイフン入りの名前・拡張子）がある時だけパスとみなす。
    """
    if end >= len(text) or text[end] not in "/\\":
        return False
    left, right = _ascii_token(text, start, end)
    token = text[left:right]
    return "-" in token or "." in token


def _after_leading_slash(text: str, start: int, end: int) -> bool:
    """語が、かたまりの先頭の `/` の直後か（/feedback のようなコマンド名・絶対パスの頭）。

    「P0/P1/P2」の P2 は `/` の前が「1」なので当たらない。
    """
    if start == 0 or text[start - 1] not in "/\\":
        return False
    left, _right = _ascii_token(text, start, end)
    return left == start - 1


def _inside_other_word(text: str, term: str, start: int) -> bool:
    for word in _NOT_THIS_TERM.get(term, ()):
        offset = word.find(term)
        while offset >= 0:
            origin = start - offset
            if origin >= 0 and text.startswith(word, origin):
                return True
            offset = word.find(term, offset + 1)
    return False


def _is_word_at(text: str, term: str, position: int) -> bool:
    end = position + len(term)
    head_ascii = _ascii_word(term[0])
    tail_ascii = _ascii_word(term[-1])
    if head_ascii and _joined_ascii(text, position - 1, -1):
        return False
    if tail_ascii and _joined_ascii(text, end, +1):
        return False
    if term.isascii() and (
        _inside_url(text, position, end)
        or _folder_in_path(text, position, end)
        or _after_leading_slash(text, position, end)
    ):
        return False
    return not _inside_other_word(text, term, position)


def find_term(text: str, term: str, start: int = 0) -> int:
    """text の start 以降で、term が「語として」現れる最初の位置を返す（無ければ -1）。

    入れるもの＝本文・用語集の語（表示の形）・探し始める位置。
    ⚠️start より前の文字も境目の判定には使う（包んだ語の直後から探し直す時も、
      直前の文字が見えるようにするため）。
    """
    if not term:
        return -1
    position = text.find(term, start)
    while position >= 0:
        if _is_word_at(text, term, position):
            return position
        position = text.find(term, position + 1)
    return -1


def contains_term(text: str, term: str) -> bool:
    """term が text の中に「語として」1回でも現れるか。"""
    return find_term(text, term) >= 0

"""見出しと中身のずれを機械で止める（2026-08-30 ユーザー選択）。

前回まで＝節の見出しを自由にした結果、**根拠の節に「まとめ」という見出し**を付けた頁を
作れるようになった。そこは「書く側の規律で防ぐ」と書いて機械では止めていなかった。
ユーザーが「見出しと中身のずれを機械で止める」を選んだので、止められる範囲を実装する。

⚠️**機械に分かるのは「言葉の持ち主」までで、意味の一致ではない。**
   見出しと中身が本当に噛み合っているかは読まないと分からない。ここで止めるのは
   ①別の部品が持つ言葉を見出しに借りた ②中身が空 ③見出しの重複 ④番号の重複 の4つだけ。
   ∴これは「ずれを全部止める」ではなく「**明らかなずれを止める**」である。
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence

# 部品ごとの「持ち主の言葉」。この語が別の部品の見出しに出たら、借用とみなして止める。
# ⚠️短い語（決め・図・表）は普通の文に出るので入れない＝空振りで作業を止めない側に倒す。
OWNED_WORDS: dict[str, tuple[str, ...]] = {
    "overview": ("一言でいうと",),
    "summary": ("見取り図", "案内板", "要約", "要旨", "3行でいうと"),
    "walkthrough": ("順を追って", "手順の説明"),
    "examples": ("実例", "具体例", "事例"),
    "progress": ("進捗", "現在地", "いまの状態", "作業の状況", "現況"),
    "visual": ("図で見る",),
    "diagram": ("流れ図", "矢印の図"),
    "table": ("対照表", "一覧表", "比較表"),
    "log": ("実行の記録", "生ログ"),
    "decision": ("決めてほしい", "裁定", "決定", "選んでほしい", "判断コンソール",
                 "承認してほしい", "決めどころ"),
    "evidence": ("根拠", "出所", "エビデンス", "裏取り", "一次資料"),
    "glossary": ("用語集", "使った言葉", "語の説明"),
    "details": ("付録", "細部", "畳んである", "おまけ"),
}

# 「まとめ」は summary の言葉に見えるが、普通の見出しにも出る。
# ⚠️入れると空振りが多いので持ち主の語には入れず、**summary以外で単独見出し**のときだけ助言する。
SOFT_WORDS: dict[str, tuple[str, ...]] = {
    "summary": ("まとめ", "全体像"),
}


def _label_of(entry: Mapping) -> str:
    return str(entry.get("label", "") or "")


def _component_of(entry: Mapping) -> str:
    return str(entry.get("component", "") or "")


def _borrowed(component: str, label: str) -> list[tuple[str, str]]:
    """見出しが借りている「別の部品の言葉」を返す。"""
    hits = []
    for owner, words in OWNED_WORDS.items():
        if owner == component:
            continue
        for word in words:
            if word in label:
                hits.append((word, owner))
    return hits


def _has_body(entry: Mapping, content: Mapping) -> bool:
    """節に出す中身があるか。⚠️空の節は見出しだけが残る＝ずれの一種。"""
    value = entry.get("content")
    if value is None:
        value = content.get(_component_of(entry))
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, tuple, dict)):
        return bool(value)
    return True


def check_sections(sections: Sequence[object], content: Mapping | None = None) -> list[str]:
    """節の一覧を検査する。返るもの＝止める理由の一覧（空なら合格）。

    入れるもの＝定義JSONの `sections` と、部品名の辞書 `content`。
    """
    body = content or {}
    problems: list[str] = []
    seen_labels: dict[str, str] = {}
    seen_nums: dict[str, str] = {}

    for index, raw in enumerate(sections or ()):
        if not isinstance(raw, Mapping):
            problems.append("%d番目の節が辞書ではない" % (index + 1))
            continue
        component = _component_of(raw)
        label = _label_of(raw)
        num = str(raw.get("num", "") or "")
        where = "%s番目の節（%s）" % (num or str(index + 1), component or "部品名なし")

        if not component:
            problems.append("%s に部品名が無い" % where)
            continue

        for word in _borrowed(component, label):
            problems.append(
                "%s の見出し「%s」に %s の言葉「%s」が入っている"
                % (where, label, word[1], word[0])
            )

        for owner, words in SOFT_WORDS.items():
            if component == owner:
                continue
            for word in words:
                if label.strip() == word:
                    problems.append(
                        "%s の見出しが「%s」だけになっている＝%s の見出しと見分けが付かない"
                        % (where, word, owner)
                    )

        if not _has_body(raw, body):
            problems.append("%s に中身が無い＝見出しだけの節になる" % where)

        if label:
            if label in seen_labels:
                problems.append(
                    "見出し「%s」が2回出ている（%s と %s）" % (label, seen_labels[label], where)
                )
            else:
                seen_labels[label] = where
        if num:
            if num in seen_nums:
                problems.append("番号「%s」が2回出ている" % num)
            else:
                seen_nums[num] = where

    return problems

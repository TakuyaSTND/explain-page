#!/usr/bin/env python3
"""案ごとの図（出力のイメージ・鎖・割合の帯・試算の欄・質問の吹き出し・前後の並び）を、小さい SVG で作る部品（2026-10-19）。

レンダラーの `proposals` ブロック（render_components.py の _proposals_block）が kind から呼ぶ。

なぜ要るか＝案の頁が「表と文」だけだと、各案を選ぶと出力がどう変わるかが頭に入りにくい（利用者の指摘）。
赤ペン先生（選択肢の横の絵）や html-plan（主張ごとに1つの実物の図）のように、案ごとに1枚の図を付けられるようにする。
render_page.py の定義 JSON に、そのまま入れられる形で返す（レンダラー本体・hooks/visual は触らない）。

使い方（定義 JSON を組む Python から）:
    import sys; sys.path.insert(0, ".claude/scripts")
    from proposal_exhibits import EXHIBITS, exhibit_svg, proposal_blocks, option_thumb
    blocks = proposal_blocks([{"no": "1", "title": "…", "claim": "…", "kind": "core_first", "rating": "+3／−1", "notes": ["…"]}])
    # blocks は節（visual など）の content にそのまま足せる（text と columns＝左に図・右に説明）
    option = {"label": "案1 …", "pros": "…", "cons": "…", "thumb": option_thumb("core_first")}

図の種類（kind）: core_first（中核を先頭に）・type（型の判定）・share（説明割合の帯）・estimate（試算の欄）・
reinforce（弱い矢印の補強）・questions（先回りの質問）・tidy（見せ方の整理）・gold（先輩のコメントで測る）・
dictionary（型の辞書を育てる）・homework（宿題カード）・delta（差分のFB）。

決まり: 色は中間の濃さ（明暗どちらの背景でも読める）。文字は currentColor（頁の文字色に従う）。
SVG は許可リスト（rect・line・text・g・path・circle・polygon）だけで書く。文字の大きさは 11px 以上。
バックスラッシュ・行またぎの文字列を書かない（生成コードの決まり）。
"""
from __future__ import annotations

from html import escape

GOOD = "#2e7d5b"
WARN = "#b8860b"
BAD = "#b23b3b"
ACC = "#2f5d8a"
GRAY = "#8a8a8a"
W, H = 420, 200


def _svg(body: str, w: int = W, h: int = H) -> str:
    return (
        '<svg viewBox="0 0 %d %d" width="%d" height="%d" role="img">%s</svg>' % (w, h, w, h, body)
    )


def _t(x, y, text, size=12, weight="400", anchor="start", fill="currentColor", opacity="1"):
    return (
        '<text x="%s" y="%s" font-size="%s" font-weight="%s" text-anchor="%s" fill="%s" fill-opacity="%s">%s</text>'
        % (x, y, size, weight, anchor, fill, opacity, escape(text))
    )


def _box(x, y, w, h, color=GRAY, fill_opacity=".10", rx=4, sw=1.4, dash=None):
    d = ' stroke-dasharray="%s"' % dash if dash else ""
    return (
        '<rect x="%s" y="%s" width="%s" height="%s" rx="%s" fill="%s" fill-opacity="%s" stroke="%s" stroke-width="%s"%s/>'
        % (x, y, w, h, rx, color, fill_opacity, color, sw, d)
    )


def _line(x1, y1, x2, y2, color=GRAY, sw=1.6, arrow=False):
    s = '<line x1="%s" y1="%s" x2="%s" y2="%s" stroke="%s" stroke-width="%s"/>' % (x1, y1, x2, y2, color, sw)
    if arrow:
        # 矢じり（x2,y2 が先端。下向きと右向きだけ使う）
        if abs(x2 - x1) < 0.5:
            s += '<polygon points="%s,%s %s,%s %s,%s" fill="%s"/>' % (x2 - 4, y2 - 7, x2 + 4, y2 - 7, x2, y2, color)
        else:
            s += '<polygon points="%s,%s %s,%s %s,%s" fill="%s"/>' % (x2 - 7, y2 - 4, x2 - 7, y2 + 4, x2, y2, color)
    return s


def _bars(x, y, w, n, color=GRAY, gap=9, h=4):
    """文の行を表す細い横棒を n 本。最後の1本だけ短くする。"""
    out = []
    for i in range(n):
        ww = w if i < n - 1 else int(w * 0.6)
        out.append('<rect x="%s" y="%s" width="%s" height="%s" rx="2" fill="%s" fill-opacity=".35"/>' % (x, y + i * gap, ww, h, color))
    return "".join(out)


def ex_core_first() -> str:
    left = _t(70, 18, "いまの出力", 12, "700", "middle") + _box(14, 28, 112, 140, GRAY, ".05")
    for i in range(6):
        left += _box(20, 34 + i * 21, 100, 17, GRAY, ".12", 3, 1)
    left += _t(70, 188, "カードが26件", 11, "400", "middle", GRAY)
    right = _t(290, 18, "新しい出力", 12, "700", "middle")
    right += _box(170, 28, 240, 74, ACC, ".14", 5, 2)
    right += _t(180, 46, "中核のFB（一番重い1点）", 12, "700", "start", ACC)
    right += _bars(180, 56, 215, 4, ACC)
    right += _t(290, 117, "ここから下は、これまでのカード", 11, "400", "middle", GRAY)
    for i in range(4):
        right += _box(170, 124 + i * 15, 240, 12, GRAY, ".10", 3, 1)
    arrow = _line(132, 100, 164, 100, GRAY, 2, True)
    return _svg(left + arrow + right)


def ex_type() -> str:
    b = _box(20, 18, 150, 30, WARN, ".16", 15, 1.8) + _t(95, 38, "型：評価の制度化", 12, "700", "middle", WARN)
    b += _t(185, 38, "→ 標準の問い3つを必ず当てる", 12, "400", "start")
    qs = ["① 鎖の各矢印は起きると言えるか", "② 律速はどれくらいを説明するか", "③ 効果は費用に見合うか（試算）"]
    for i, q in enumerate(qs):
        y = 70 + i * 40
        b += _box(20, y, 380, 30, ACC, ".10", 5, 1.4) + _t(34, y + 20, q, 12)
    b += _t(20, 192, "型が曖昧なときは、警告を出さない", 11, "400", "start", GRAY)
    return _svg(b)


def ex_share() -> str:
    b = _t(20, 20, "評価の欠如は、目的が達成されない原因のどれくらいを説明するか", 12, "700")
    x0, x1, y = 30, 390, 70
    b += _line(x0, y, x1, y, GRAY, 2)
    for p in (0, 25, 50, 75, 100):
        x = x0 + (x1 - x0) * p / 100
        b += _line(x, y - 4, x, y + 4, GRAY, 1.2) + _t(x, y + 20, "%d%%" % p, 11, "400", "middle", GRAY)
    lo, hi = 30, 60
    b += _box(x0 + (x1 - x0) * lo / 100, y - 12, (x1 - x0) * (hi - lo) / 100, 24, ACC, ".30", 3, 1.8)
    b += _t(x0 + (x1 - x0) * 0.45, y - 20, "30〜60%（幅で出す）", 12, "700", "middle", ACC)
    b += _box(20, 118, 188, 66, GOOD, ".10", 5, 1.4) + _t(30, 138, "出所の札：統計・資料", 12, "700", "start", GOOD)
    b += _t(30, 158, "出所があるときだけ幅を出す", 11) + _t(30, 174, "（仮定は「仮定」と表示）", 11)
    b += _box(222, 118, 178, 66, BAD, ".10", 5, 1.4, "4 3") + _t(232, 138, "見積もれない", 12, "700", "start", BAD)
    b += _t(232, 158, "出所が無ければ、数を作らず", 11) + _t(232, 174, "理由を書く", 11)
    return _svg(b)


def ex_estimate() -> str:
    rows = [
        ("効果の大きさ", "資料の数", GOOD, ".16"),
        ("対象の数", "統計", GOOD, ".16"),
        ("期間", "仮定", WARN, ".18"),
        ("費用", "◯（空欄）", BAD, ".14"),
    ]
    b = _t(20, 18, "試算の骨組み（効果×対象×期間÷費用）", 12, "700")
    for i, (name, src, color, fo) in enumerate(rows):
        y = 28 + i * 30
        b += _box(20, y, 150, 24, GRAY, ".08", 3, 1) + _t(30, y + 17, name, 12)
        b += _box(176, y, 120, 24, color, fo, 3, 1.4, "4 3" if color == BAD else None) + _t(236, y + 17, src, 12, "700", "middle", color)
    b += _line(300, 40, 330, 80, GRAY, 1.6) + _line(300, 130, 330, 100, GRAY, 1.6)
    b += _box(330, 62, 78, 56, ACC, ".14", 5, 1.8) + _t(369, 86, "採否", 12, "700", "middle", ACC) + _t(369, 104, "◯", 14, "700", "middle", ACC)
    b += _t(20, 168, "資料の数で埋まる欄と、空の欄を分けて見せる", 11, "400", "start", GRAY)
    b += _t(20, 186, "空の欄が埋まれば、採否まで行ける", 11, "400", "start", GRAY)
    return _svg(b)


def ex_reinforce() -> str:
    b = _box(18, 20, 60, 30, GOOD, ".14", 4, 1.6) + _t(48, 40, "手段", 12, "700", "middle")
    b += _line(78, 35, 130, 35, GOOD, 2, True)
    b += _box(130, 20, 70, 30, WARN, ".14", 4, 1.6) + _t(165, 40, "施策", 12, "700", "middle")
    b += _line(200, 35, 252, 35, BAD, 2.4, True)
    b += _t(226, 64, "根拠が弱い", 11, "700", "middle", BAD)
    b += _box(252, 20, 70, 30, BAD, ".14", 4, 1.6) + _t(287, 40, "目的", 12, "700", "middle")
    b += _t(20, 86, "この矢印に、どんな根拠をどこで探すか", 12, "700")
    b += _box(20, 94, 118, 24, ACC, ".10", 12, 1.2) + _t(79, 111, "先行研究", 11, "400", "middle")
    b += _box(146, 94, 84, 24, ACC, ".10", 12, 1.2) + _t(188, 111, "事例", 11, "400", "middle")
    b += _box(238, 94, 84, 24, ACC, ".10", 12, 1.2) + _t(280, 111, "統計", 11, "400", "middle")
    b += _box(20, 128, 190, 58, GRAY, ".08", 5, 1.2) + _t(30, 146, "候補1：論文（機関・年）", 11, "700") + _bars(30, 154, 170, 2, GRAY, 9, 4)
    b += _box(220, 128, 190, 58, GRAY, ".08", 5, 1.2) + _t(230, 146, "候補2：公的統計（機関・年）", 11, "700") + _bars(230, 154, 170, 2, GRAY, 9, 4)
    return _svg(b)


def ex_questions() -> str:
    b = _t(20, 18, "発表の前に答えを用意しておく質問", 12, "700")
    qs = ["「その矢印が起きる根拠は？」", "「最大の要因と言える？ どれくらい？」", "「費用に見合う？ 採否は？」"]
    for i, q in enumerate(qs):
        y = 34 + i * 50
        b += _box(30, y, 340, 38, ACC, ".10", 10, 1.5)
        b += '<polygon points="30,%s 18,%s 36,%s" fill="%s" fill-opacity=".10" stroke="%s" stroke-width="1.5"/>' % (y + 20, y + 28, y + 12, ACC, ACC)
        b += _t(44, y + 24, q, 12)
    return _svg(b)


def ex_tidy() -> str:
    b = _t(100, 18, "いま", 12, "700", "middle") + _t(320, 18, "整理後", 12, "700", "middle")
    names_before = ["稼働状況の表", "一次資料の照合", "論理図と成績表", "中核のFB"]
    names_after = ["中核のFB", "論理図と成績表", "一次資料の照合", "稼働状況の表"]
    for i, n in enumerate(names_before):
        y = 30 + i * 40
        c = ACC if n == "中核のFB" else GRAY
        b += _box(20, y, 160, 32, c, ".14" if c == ACC else ".08", 4, 1.6) + _t(100, y + 21, n, 12, "700" if c == ACC else "400", "middle")
    b += _line(190, 100, 232, 100, GRAY, 2, True)
    for i, n in enumerate(names_after):
        y = 30 + i * 40
        c = ACC if n == "中核のFB" else GRAY
        b += _box(240, y, 160, 32, c, ".14" if c == ACC else ".06", 4, 1.6) + _t(320, y + 21, n, 12, "700" if c == ACC else "400", "middle", c if c == ACC else GRAY)
    b += _t(20, 196, "前回の検査は残し、後ろに置く", 11, "400", "start", GRAY)
    return _svg(b)


def ex_gold() -> str:
    b = _box(14, 30, 92, 54, WARN, ".14", 5, 1.6) + _t(60, 52, "先輩の", 12, "700", "middle") + _t(60, 70, "コメント", 12, "700", "middle")
    b += _line(106, 57, 140, 57, GRAY, 2, True)
    b += _box(140, 30, 100, 54, GRAY, ".10", 5, 1.4) + _t(190, 52, "指摘を", 12, "700", "middle") + _t(190, 70, "点に分ける", 12, "700", "middle")
    b += _box(140, 112, 100, 54, ACC, ".14", 5, 1.6) + _t(190, 134, "AIのFB", 12, "700", "middle") + _t(190, 152, "（新しい出力）", 11, "400", "middle")
    b += _line(190, 84, 190, 112, GRAY, 2, True)
    b += _line(240, 57, 272, 57, GRAY, 2, True) + _line(240, 139, 272, 98, GRAY, 2)
    b += _box(272, 40, 134, 60, GOOD, ".14", 5, 1.8) + _t(339, 64, "同じ点を", 12, "700", "middle", GOOD) + _t(339, 82, "突けたか", 12, "700", "middle", GOOD)
    b += _t(339, 122, "例：5点中4点", 12, "400", "middle", GRAY) + _t(339, 140, "（点の数は例）", 11, "400", "middle", GRAY)
    return _svg(b)


def ex_dictionary() -> str:
    b = _t(20, 18, "型の辞書（先輩のコメントから育てる）", 12, "700")
    rows = [("評価の制度化", "鎖の根拠・律速の割合・試算"), ("補助金の新設", "対象の規模・費用対効果・既存との差"), ("規制の変更", "遵守の実態・執行・代替手段")]
    for i, (a, c) in enumerate(rows):
        y = 32 + i * 42
        b += _box(20, y, 130, 32, WARN, ".14", 16, 1.6) + _t(85, y + 21, a, 12, "700", "middle", WARN)
        b += _line(150, y + 16, 178, y + 16, GRAY, 2, True)
        b += _box(178, y, 222, 32, ACC, ".10", 4, 1.4) + _t(188, y + 21, c, 12)
    b += _box(20, 162, 380, 28, BAD, ".08", 4, 1.2, "4 3") + _t(30, 181, "辞書に使った例とは別の資料で測る（過学習を防ぐ）", 11)
    return _svg(b)


def ex_homework() -> str:
    b = _t(20, 18, "補強の宿題（優先順）", 12, "700")
    items = [("1", "鎖①→②の根拠を探す", "先行研究・事例", BAD), ("2", "律速の割合を出す", "公的な統計", WARN), ("3", "試算の空欄を埋める", "費用・対象の数", WARN)]
    for i, (n, a, c, col) in enumerate(items):
        y = 30 + i * 52
        b += _box(20, y, 380, 42, col, ".10", 5, 1.5)
        b += '<circle cx="42" cy="%s" r="12" fill="%s" fill-opacity=".25" stroke="%s" stroke-width="1.5"/>' % (y + 21, col, col) + _t(42, y + 26, n, 13, "700", "middle", col)
        b += _t(64, y + 19, a, 12, "700") + _t(64, y + 35, "探す場所：" + c, 11, "400", "start", GRAY)
    return _svg(b)


def ex_delta() -> str:
    b = _t(110, 18, "1回目のFB", 12, "700", "middle") + _t(320, 18, "補強材料を貼った後", 12, "700", "middle")
    for i, (c, lab) in enumerate([(BAD, "①→② 根拠なし"), (WARN, "②→③ 弱い"), (GOOD, "律速 幅あり")]):
        y = 30 + i * 44
        b += _box(20, y, 180, 34, c, ".14", 4, 1.6) + _t(110, y + 22, lab, 12, "700", "middle", c)
    b += _line(206, 100, 226, 100, GRAY, 2, True)
    for i, (c, lab) in enumerate([(WARN, "①→② 弱い（論文1件）"), (WARN, "②→③ 弱い"), (GOOD, "律速 幅あり")]):
        y = 30 + i * 44
        b += _box(232, y, 180, 34, c, ".14", 4, 1.6) + _t(322, y + 22, lab, 12, "700", "middle", c)
    b += _t(20, 178, "どの矢印が、どれだけ強くなったかだけを返す", 11, "400", "start", GRAY)
    return _svg(b)


EXHIBITS = {
    "core_first": ex_core_first,
    "type": ex_type,
    "share": ex_share,
    "estimate": ex_estimate,
    "reinforce": ex_reinforce,
    "questions": ex_questions,
    "tidy": ex_tidy,
    "gold": ex_gold,
    "dictionary": ex_dictionary,
    "homework": ex_homework,
    "delta": ex_delta,
}


def exhibit_svg(kind: str) -> str:
    """kind の図の SVG 文字列。知らない kind は ValueError。"""
    if kind not in EXHIBITS:
        raise ValueError("知らない図の種類: %s（%s）" % (kind, "・".join(EXHIBITS)))
    return EXHIBITS[kind]()


def option_thumb(kind: str) -> dict:
    """決定欄の選択肢の thumb（320px 以下・120KB 以下）。"""
    return {"svg": exhibit_svg(kind)}


def proposal_blocks(proposals: list[dict]) -> list[dict]:
    """案の一覧から、頁の節（visual など）に足す塊を作る。

    各案 = {"no","title","claim","kind","rating","notes":[…]}。
    返るもの = 案ごとに「見出しの文」と「左に図・右に説明」の2段組み。
    """
    blocks: list[dict] = []
    for p in proposals:
        head = "**案%s　%s**" % (p.get("no", ""), p.get("title", ""))
        if p.get("rating"):
            head += "（精度向上／コスト削減：%s）" % p["rating"]
        blocks.append({"text": head})
        right = {"text": p.get("claim", "")}
        if p.get("notes"):
            right["items"] = list(p["notes"])
        blocks.append({"columns": [{"svg": {"svg": exhibit_svg(p["kind"]), "caption": p.get("caption", "")}}, right]})
    return blocks


if __name__ == "__main__":
    for k in EXHIBITS:
        s = exhibit_svg(k)
        print(k, len(s.encode("utf-8")), "バイト")

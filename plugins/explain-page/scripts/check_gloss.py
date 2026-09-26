#!/usr/bin/env python3
"""公開前のHTMLで、用語ホバーが用語集と食い違っていないかを見る。

⚠️このスクリプトは**辞書を機械的に当てはめる道具ではない**。
ユーザーの明示的な要件＝「難しい用語には積極的に付けてほしいが、
辞書の単語に機械的に当てはめるだけにはしてほしくない」（2026-08-22）。
∴どの語を包むかは**書く側が判断する**。機械が見るのは次の4つだけ。

  ⓪ 取りこぼし（要修正）＝data-d はあるのに用語を切り出せなかった
     → その分は①を**受けていない**。ここを黙って捨てると検査が嘘をつく（2026-08-23の実事故）
  ① 一致（要修正）＝用語集にある語を包んだのに説明文が違う → 同じ語に違う説明を書かない
  ② 育ち（足す候補）＝包んだ語が用語集に無い → 新しい難語なので用語集に足す
  ③ 参考（強制しない）＝用語集にある語が本文に出ているのに一度も包んでいない
     ⚠️これは指摘ではない。包まない判断は正当（2回目以降・直前に言い換えた・見出しの中）。

使い方:
  PYTHONUTF8=1 python .claude/scripts/check_gloss.py <html>            # 3つ全部
  PYTHONUTF8=1 python .claude/scripts/check_gloss.py <html> --strict   # ①があれば終了コード2

正本＝.claude/html-output.md（基準）／.claude/glossary.md（言い回し）
"""
import io
import os
import sys

NL = chr(10)
Q2 = chr(34)
DUP = []
OVERRIDE = []
COUNTS = {}
HERE = os.path.dirname(os.path.abspath(__file__))
CLAUDE_DIR = os.path.dirname(HERE)
GLOSS = os.path.join(CLAUDE_DIR, 'glossary.md')
# 2階建て（2026-08-23）＝共通の正本はホームの下。無ければ repo の控えを使う。
#   なぜ2階建てか＝正本が1つだと「同じ名前で中身が違う語」が別プロジェクトと衝突する
#   （この repo の M は具体手段だが、別プロジェクトなら行列やモデル）。
SHARED_HOME = os.path.join(os.path.expanduser('~'), '.claude', 'glossary-shared.md')
SHARED_MIRROR = os.path.join(CLAUDE_DIR, 'glossary-shared.md')


def norm(x):
    """比べる前に**強調記号**を落とす。

    ⚠️用語集は Markdown なので `**強調**` が入るが、HTMLの data-d 属性の中では
    `**` は何の意味も持たないので書かない。文字列をそのまま比べると、
    **強調の有無だけで「相違」と誤検出する**（2026-08-22に6件中4件がこれだった）。
    """
    return x.replace('**', '').replace('`', '')


def _rows(path):
    """1ファイルから (用語, 説明) を出てきた順に返す。⚠️見出し行と区切り行は落とす。"""
    out = []
    if not os.path.isfile(path):
        return out
    with io.open(path, encoding='utf-8', errors='replace') as handle:
        lines = handle.read().split(NL)
    for ln in lines:
        if not ln.startswith('| '):
            continue
        cells = [c.strip() for c in ln.split('|')]
        if len(cells) < 4:
            continue
        term, desc = cells[1], cells[2]
        if not term or not desc:
            continue
        if term in ('用語', '関門') or set(term) <= set('-: '):
            continue
        # ⚠️**語そのものも正規化する**。用語集では変数名をバッククォートで囲んで書くが
        #   （| `claims` | …）、HTMLの中の語はバッククォートなしなので、
        #   そのまま比べると**別の語として扱われ「新語」に見える**（2026-08-22に24件が誤って
        #   新語扱いになった）。
        out.append((norm(term), desc))
    return out


def gloss_paths():
    """読む順＝共通→固有。**後から読んだ方が勝つ**（固有が共通を上書きする）。

    共通の正本はホームの下（どのプロジェクトからも見える）。無ければ repo の控えを使う。
    """
    shared = SHARED_HOME if os.path.isfile(SHARED_HOME) else SHARED_MIRROR
    return [('共通', shared), ('固有', GLOSS)]


def load_glossary():
    """共通と固有の表を読み、固有を勝たせた1つの辞書にする。

    ⚠️重複した語も返す＝辞書にすると1つが黙って消える（2026-08-22に実際に
    「転移可能性」が2節に書かれていて 109行→108語になっていた）。
    今日JSの返り値で直したのと同じ「last-wins で黙って消える」型なので必ず報告する。
    """
    d = {}
    global DUP, OVERRIDE, COUNTS
    DUP = []
    OVERRIDE = []
    COUNTS = {}
    for label, path in gloss_paths():
        one = {}
        for term, desc in _rows(path):
            # ⚠️重複と呼ぶのは**同じファイルの中**だけ。ファイルをまたいで同じ語が
            #   出るのは2階建ての狙いどおり（固有が共通を上書きする）なので、
            #   ここで重複扱いにすると正常動作を毎回叱ることになる。
            if term in one and norm(one[term]) != norm(desc):
                DUP.append(term)
            one[term] = desc
        COUNTS[label] = len(one)
        for term, desc in one.items():
            if term in d and norm(d[term]) != norm(desc):
                OVERRIDE.append(term)
            d[term] = desc
    return d


def tag_name_before(html, i):
    """位置 i（data-d の場所）を含む開始タグのタグ名を、直前の < から読み取る。

    ⚠️正規表現を使わず索引で切る。タグ名はASCIIの英数と - だけなので、
    空白や > に当たった時点で止めれば属性名を巻き込まない。
    """
    lt = html.rfind('<', 0, i)
    if lt < 0:
        return ''
    name = []
    p = lt + 1
    n = len(html)
    while p < n:
        c = html[p]
        if c.isascii() and (c.isalnum() or c == '-'):
            name.append(c)
            p += 1
            continue
        break
    return ''.join(name)


def hovered(html):
    """data-d を持つ要素を (用語, 説明) で拾う。⚠️正規表現を使わず索引で切る。

    返すのは (拾えた一覧, 拾えなかった件数)。

    ⚠️2026-08-23の実事故：**閉じタグを </span> に決め打ちしていた**。
      そのため 〈code class="t" data-d="…"〉claims〈/code〉 のように span 以外で包んだ語を
      1件も拾えず、①の一致検査を**素通り**させた（実際に1頁で6件が素通りした）。
      さらに悪いのは、拾えなかったことをどこにも報告しなかった点＝**検査が嘘をつく**形。
      「包んだ語 8件」と表示されるので、書いた側は検査されたと思い込む。
    ∴直しは2つで対になっている。
      ① 包んだ要素のタグ名を読み取り、**対応する閉じタグ**を探す（span 決め打ちをやめる）
      ② それでも取れなかった data-d は**件数を返して報告する**（沈黙をやめる）
      ②が無いと、次に別の取りこぼし方が出たときまた黙って通る。
    """
    out = []
    unresolved = 0
    i = 0
    key = 'data-d=' + Q2
    while True:
        i = html.find(key, i)
        if i < 0:
            break
        j = html.find(Q2, i + len(key))
        if j < 0:
            unresolved += 1
            break
        desc = html[i + len(key):j]
        term = ''
        name = tag_name_before(html, i)
        # 属性の終わりから > を探し、対応する閉じタグまでが用語
        k = html.find('>', j)
        m = html.find('</' + name + '>', k) if (name and k >= 0) else -1
        if k >= 0 and m >= 0:
            cand = html[k + 1:m]
            # 入れ子のタグが入っていたら用語として扱わない（安全側）
            if '<' not in cand:
                term = cand
        if term.strip():
            out.append((term.strip(), desc.strip()))
        else:
            unresolved += 1
        i = j + 1
    return out, unresolved


def strip_tags(html):
    """本文だけをざっくり取る（属性値の中を「本文に出た」と数えないため）。"""
    buf = []
    depth = 0
    skip = False
    i = 0
    n = len(html)
    while i < n:
        c = html[i]
        if c == '<':
            # script / style の中は本文でない
            low = html[i:i + 8].lower()
            if low.startswith('<script') or low.startswith('<style'):
                skip = True
            if low.startswith('</script') or low.startswith('</style'):
                skip = False
            depth += 1
        elif c == '>':
            if depth > 0:
                depth -= 1
        elif depth == 0 and not skip:
            buf.append(c)
        i += 1
    return ''.join(buf)


def main():
    args = [a for a in sys.argv[1:] if not a.startswith('--')]
    strict = '--strict' in sys.argv
    if not args:
        print(__doc__)
        return 2
    p = args[0]
    if not os.path.isfile(p):
        print('ファイルが無い: %s' % p)
        return 2
    with io.open(p, encoding='utf-8', errors='replace') as handle:
        html = handle.read()
    g = load_glossary()
    if not g:
        print('⚠️用語集が読めない（どちらも空）:')
        for label, path in gloss_paths():
            print('   %s … %s%s' % (label, path, '' if os.path.isfile(path) else '（無い）'))
        return 2
    hv, unresolved = hovered(html)

    mismatch, extended, newterm, seen = [], [], [], set()
    for term, desc in hv:
        seen.add(term)
        if term in g:
            if norm(desc) == norm(g[term]):
                continue
            # ⚠️用語集の説明で始まっていれば「その頁の文脈を足した」＝正当な拡張。
            #   ここを相違として叩くと、頁ごとの補足を書けなくなる＝機械的すぎる
            #   （2026-08-22の初版はこれで8件を誤って要修正にした）。
            if norm(desc).startswith(norm(g[term])):
                extended.append((term, norm(desc)[len(norm(g[term])):]))
            else:
                mismatch.append((term, desc, g[term]))
        else:
            newterm.append((term, desc))

    body = strip_tags(html)
    # ③参考＝用語集にあり本文に出ているが一度も包んでいない語。長い順に少しだけ。
    unwrapped = [t for t in g if len(t) >= 3 and t in body and t not in seen]
    unwrapped.sort(key=len, reverse=True)

    print('=' * 72)
    print('用語ホバーの点検: %s' % os.path.basename(p))
    print('  用語集 %d語（共通 %d ＋ 固有 %d）／ この頁で包んだ語 %d件'
          % (len(g), COUNTS.get('共通', 0), COUNTS.get('固有', 0), len(seen)))
    print('=' * 72)

    if OVERRIDE:
        # ⚠️これは正常動作の報告。**黙って上書きしない**＝どの語を固有で塗り替えたかは
        #   目に見えないと、共通側を直したのに効かない理由が分からなくなる。
        print('')
        print('ⓘ 固有が共通を上書きした語 %d件（**これは狙いどおり**）: %s'
              % (len(set(OVERRIDE)), ', '.join(sorted(set(OVERRIDE)))))

    if DUP:
        print('')
        print('⚠️用語集に**重複した語**がある（辞書にすると1つが黙って消える）: %s'
              % ', '.join(sorted(set(DUP))))
        print('  → どちらかを消すか統合する')

    if unresolved:
        print('')
        print('⓪ 取りこぼし（**要修正・検査の穴**）＝data-d はあるのに用語を切り出せなかった %d件'
              % unresolved)
        print('  この分は①の一致検査を**受けていない**＝「包んだ語」の数にも入っていない。')
        print('  よくある原因：包んだ要素の閉じタグが無い／中に別のタグが入っている／')
        print('  data-d の値の中に半角の二重引用符がある。')
        print('  → 該当箇所を1要素1語の形に直す（2026-08-23：span決め打ちで6件が黙って素通りした）')

    if extended:
        print('')
        print('①a 拡張（**正当・修正不要**）＝用語集の説明にその頁の文脈を足した %d件' % len(extended))
        for t, tail in extended:
            print('  ○ %s ＋「%s」' % (t, tail[:70]))

    if mismatch:
        print('')
        print('①b 相違（**要修正**）＝用語集と別の言い回しになっている %d件' % len(mismatch))
        for t, d, gd in mismatch:
            print('  ⚠️ %s' % t)
            print('     この頁: %s' % d[:110])
            print('     用語集: %s' % gd[:110])
            print('     → どちらかに揃える（用語集を直すなら1行直せば全頁に効く）')
    elif not extended:
        print('')
        print('① 一致：用語集にある語の説明はすべて一致している')

    if newterm:
        print('')
        print('② 育ち（**用語集に足す候補**）＝新しく包んだ語 %d件' % len(newterm))
        for t, d in newterm:
            print('  + | %s | %s |' % (t, d))
        print('  → この行を .claude/glossary.md に貼れば、次の頁から自動で言い回しが揃う')
    else:
        print('')
        print('② 育ち：包んだ語はすべて用語集にある（新語なし）')

    print('')
    print('③ 参考（**指摘ではない**）＝用語集にあり本文に出ているが包んでいない語 %d件'
          % len(unwrapped))
    if unwrapped:
        print('  ' + ' / '.join(unwrapped[:14]) + ('' if len(unwrapped) <= 14 else ' …'))
        print('  ⚠️包まない判断は正当（2回目以降・直前に言い換えた・見出しの中・その頁では易しい）。')
        print('    機械はここで止めない＝どれを包むかは書く側が決める。')

    print('')
    if mismatch or DUP or unresolved:
        print('→ ⓪か①bか重複があるので直すこと')
        return 2 if strict else 1
    print('→ 食い違いなし')
    return 0


if __name__ == '__main__':
    if sys.platform == 'win32':
        try:
            sys.stdout.reconfigure(encoding='utf-8')
        except Exception:  # noqa: BLE001
            pass
    sys.exit(main())

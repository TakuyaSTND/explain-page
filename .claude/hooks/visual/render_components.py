from __future__ import annotations

import math
import re
from html import escape, unescape
from typing import Mapping, Sequence

from .contracts import ExplanationPlan
from .glossary import GlossaryEntry
from .term_boundary import find_term

# 2026-09-08：担当Bのグラフ・担当Cの数式は並行作業なので、無い間もこのファイルが
# 動くよう遅延importにする（無ければ表・codeへ自動で落ちる＝黙って消さない）。
try:
    from .charts import render_chart
except ImportError:  # Agent B may add this module after this integration lands.
    render_chart = None  # type: ignore[assignment]

try:
    from .formula import tex_to_mathml
except ImportError:  # Agent C may add this module after this integration lands.
    tex_to_mathml = None  # type: ignore[assignment]

# 2026-09-09/10：箱と矢印の配置計算（担当H）・SVG取り込み／画像／時間軸類／記号／
# 1行記法（それぞれ別の担当）を配線する。どれも同じ流儀＝遅延import＋守り付き。
try:
    from .diagram_layout import layout_diagram
except ImportError:
    layout_diagram = None  # type: ignore[assignment]

try:
    from .svg_import import sanitize_svg
except ImportError:
    sanitize_svg = None  # type: ignore[assignment]

try:
    from .images import embed_image
except ImportError:
    embed_image = None  # type: ignore[assignment]
# 2026-10-01（ユーザー承認の P2）：画面を撮って貼る撮影係。同じ流儀＝遅延import＋守り付き。
try:
    from .screenshots import capture as capture_screenshot
except ImportError:
    capture_screenshot = None  # type: ignore[assignment]

try:
    from .visuals import (
        timeline_svg,
        quadrant_svg,
        venn_svg,
        flow_svg,
        score_grid_svg,
        heat_color,
        compare_html,
        callout_legend_html,
    )
except ImportError:
    timeline_svg = None  # type: ignore[assignment]
    quadrant_svg = None  # type: ignore[assignment]
    venn_svg = None  # type: ignore[assignment]
    flow_svg = None  # type: ignore[assignment]
    score_grid_svg = None  # type: ignore[assignment]
    heat_color = None  # type: ignore[assignment]
    compare_html = None  # type: ignore[assignment]
    callout_legend_html = None  # type: ignore[assignment]

try:
    from .diagram_dsl import parse_diagram_text
except ImportError:
    parse_diagram_text = None  # type: ignore[assignment]

try:
    from .icons import icon_svg as _render_icon_svg
except ImportError:
    _render_icon_svg = None  # type: ignore[assignment]

# 画像ブロックが積む「実測」行。evidence 節を描く時に末尾へ足す（B2）。
# ⚠️モジュール単位の状態＝この道具は1プロセスで1頁ずつ順に組むので安全
#   （render_components() の先頭で必ずクリアする）。
_IMAGE_EVIDENCE_LINES: list[str] = []
_PAGE_HAS_EVIDENCE_SECTION = False


NEWLINE = chr(10)

LABELS = {
    "overview": "一言でいうと",
    "summary": "全体像",
    "walkthrough": "順番に説明",
    "examples": "具体例",
    "progress": "現在地",
    "visual": "図で見る",
    "decision": "選ぶこと",
    "evidence": "根拠",
    "glossary": "用語",
    "details": "詳細",
    "caption": "補足",
    # 2026-08-29（ユーザー裁定 P1）：比較表とログを置けるようにした。
    # ⚠️これまで表は根拠の3列表しか作れず、比較表は本文へ文章で書き下していた。
    #   ログは pre が判断コンソール専用だったので、テスト出力を貼れなかった。
    "table": "比べる",
    "diagram": "図解",
    "log": "実行の記録",
}

DECISION_SCRIPT = r"""const prompt=document.getElementById('decision-prompt');
const fields=[...document.querySelectorAll('[data-req]')];
const objections=[...document.querySelectorAll('input[type="checkbox"][name="objection"]')];
const objection=document.getElementById('decision-objection');
const MEMORY_KEY='uc:'+document.title;
function whys(){return [...document.querySelectorAll('.obj-why')];}
function remember(){try{localStorage.setItem(MEMORY_KEY,JSON.stringify({v:fields.map(x=>x.type==='radio'||x.type==='checkbox'?x.checked:x.value),o:objections.map(x=>x.checked),w:whys().map(x=>x.value),f:objection?objection.value:''}));}catch(e){}}
function recall(){try{const raw=localStorage.getItem(MEMORY_KEY);if(!raw)return;const s=JSON.parse(raw);(s.v||[]).forEach((v,i)=>{const f=fields[i];if(!f)return;if(f.type==='radio'||f.type==='checkbox'){f.checked=!!v;}else{f.value=v;}});(s.o||[]).forEach((v,i)=>{if(objections[i])objections[i].checked=v;});const w=whys();(s.w||[]).forEach((v,i)=>{if(w[i])w[i].value=v;});if(objection&&typeof s.f==='string')objection.value=s.f;}catch(e){}}
function build(){if(!prompt)return;const lines=[];fields.forEach(f=>{if(f.type==='radio'||f.type==='checkbox'){if(f.checked)lines.push(f.dataset.label);}else if((f.value||'').trim()){lines.push(f.dataset.label+': '+f.value.trim());}});objections.filter(x=>x.checked).forEach(x=>{const row=x.closest('.obj-row')||x.closest('.obj');const w=row?row.querySelector('.obj-why'):null;const why=w&&w.value.trim()?w.value.trim():'（未記入）';lines.push('この判定は違う。理由＝'+why+' ／ 対象＝'+x.dataset.label);});if(objection&&objection.value.trim())lines.push('補足: '+objection.value.trim());prompt.textContent=lines.length?lines.join('\n'):'選択してください。';remember();}
fields.forEach(x=>x.addEventListener(x.type==='radio'||x.type==='checkbox'?'change':'input',build));
objections.forEach(x=>x.addEventListener('change',build));
if(objection)objection.addEventListener('input',build);
whys().forEach(x=>x.addEventListener('input',build));
const recommend=document.getElementById('recommend-decision');
if(recommend)recommend.addEventListener('click',()=>{fields.filter(x=>x.dataset.rec==='1').forEach(x=>{if(x.type==='radio'||x.type==='checkbox')x.checked=true;});build();recommend.textContent='推奨を入れました';});
const forget=document.getElementById('forget-decision');
if(forget)forget.addEventListener('click',()=>{try{localStorage.removeItem(MEMORY_KEY);}catch(e){}fields.forEach(x=>{if(x.type==='radio'||x.type==='checkbox'){x.checked=false;}else{x.value='';}});objections.forEach(x=>{x.checked=false;});whys().forEach(x=>{x.value='';});if(objection)objection.value='';build();forget.textContent='消しました';});
const copy=document.getElementById('copy-decision');
const select=document.getElementById('select-decision');
function selectPrompt(){if(!prompt)return;const range=document.createRange();range.selectNodeContents(prompt);const selection=window.getSelection();selection.removeAllRanges();selection.addRange(range);}
if(select)select.addEventListener('click',selectPrompt);
if(copy)copy.addEventListener('click',async()=>{build();try{if(!navigator.clipboard)throw new Error('clipboard unavailable');await navigator.clipboard.writeText(prompt.textContent);copy.textContent='コピー済み';}catch(error){selectPrompt();copy.textContent='全文を選択しました';}});
const theme=document.getElementById('theme-toggle');
if(theme)theme.addEventListener('click',()=>{const root=document.documentElement;const current=root.getAttribute('data-theme');const dark=current?current==='dark':(window.matchMedia&&window.matchMedia('(prefers-color-scheme: dark)').matches);root.setAttribute('data-theme',dark?'light':'dark');});
recall();build();
const tocLinks=[...document.querySelectorAll('.toc a')];
if(tocLinks.length){
const byId=new Map(tocLinks.map(a=>[a.getAttribute('href').slice(1),a]));
const secs=[...document.querySelectorAll('section[id]')].filter(s=>byId.has(s.id));
let current='',ticking=false;
function reveal(a){const rail=a.closest('.rail');if(!rail)return;if(rail.scrollHeight<=rail.clientHeight+1)return;const rr=rail.getBoundingClientRect(),ar=a.getBoundingClientRect();if(ar.top<rr.top||ar.bottom>rr.bottom){rail.scrollTop+=ar.top-rr.top-rail.clientHeight/2+ar.height/2;}}
function spy(){ticking=false;let id=secs.length?secs[0].id:'';for(const s of secs){if(s.getBoundingClientRect().top<=140){id=s.id;}else{break;}}if(secs.length&&innerHeight+scrollY>=document.documentElement.scrollHeight-2){id=secs[secs.length-1].id;}if(id===current)return;const was=byId.get(current);if(was)was.removeAttribute('aria-current');current=id;const now=byId.get(id);if(now){now.setAttribute('aria-current','true');reveal(now);}}
addEventListener('scroll',()=>{if(!ticking){ticking=true;requestAnimationFrame(spy);}},{passive:true});
spy();
}
// 用語の説明が頁の外へ出るのを防ぐ＝出そうなときだけ右端に寄せる。
// ⚠️CSSだけでは「用語がどこにあるか」が分からないので、触った時に測る。
document.querySelectorAll('.t').forEach(t=>{
const place=()=>{t.removeAttribute('data-flip');const rects=[...t.getClientRects()];if(!rects.length)return;const edge=Math.max(...rects.map(r=>r.right));const w=Math.min(384,innerWidth-48);if(edge+w>document.documentElement.clientWidth-8){t.setAttribute('data-flip','1');}};
t.addEventListener('pointerenter',place);
t.addEventListener('focus',place);
});
// 図の箱の詳説。本文を箱へ詰め込まず、hover・keyboard focus・tap で同じ説明を出す。
// ⚠️innerHTMLを使わず textContent だけで組む＝定義JSONの文字列をHTMLとして実行しない。
const diaNodes=[...document.querySelectorAll('.dia-node[data-hover]')];
if(diaNodes.length){
const tip=document.createElement('aside');
tip.className='dia-node-tip';tip.id='dia-node-tip';tip.setAttribute('role','tooltip');tip.hidden=true;
document.body.appendChild(tip);
let active=null;
const add=(tag,cls,text)=>{if(!text)return null;const el=document.createElement(tag);el.className=cls;el.textContent=text;tip.appendChild(el);return el;};
const row=(label,value)=>{if(!value)return;const wrap=document.createElement('div');wrap.className='dia-node-tip__row';const dt=document.createElement('b');dt.textContent=label;const dd=document.createElement('span');dd.textContent=value;wrap.append(dt,dd);tip.appendChild(wrap);};
const place=n=>{if(!n||tip.hidden)return;const a=n.getBoundingClientRect(),t=tip.getBoundingClientRect(),pad=12;let left=a.left+a.width/2-t.width/2;left=Math.max(pad,Math.min(left,innerWidth-t.width-pad));let top=a.top-t.height-pad;if(top<pad)top=a.bottom+pad;if(top+t.height>innerHeight-pad)top=Math.max(pad,innerHeight-t.height-pad);tip.style.left=`${left}px`;tip.style.top=`${top}px`;};
const show=n=>{active=n;tip.replaceChildren();add('span','dia-node-tip__label',n.dataset.hoverLabel);add('strong','dia-node-tip__title',n.dataset.hoverTitle);add('p','dia-node-tip__text',n.dataset.hoverText);row('図での役割',n.dataset.hoverRole);row('根拠',n.dataset.hoverEvidence);row('読み方',n.dataset.hoverStatus);tip.hidden=false;tip.setAttribute('data-open','1');n.setAttribute('aria-describedby',tip.id);place(n);};
const hide=()=>{if(active)active.removeAttribute('aria-describedby');active=null;tip.hidden=true;tip.removeAttribute('data-open');};
diaNodes.forEach(n=>{
n.addEventListener('pointerenter',()=>show(n));
n.addEventListener('pointerleave',()=>{if(document.activeElement!==n)hide();});
n.addEventListener('focus',()=>show(n));
n.addEventListener('blur',hide);
n.addEventListener('click',()=>show(n));
n.addEventListener('keydown',event=>{if(event.key==='Escape'){hide();n.blur();}else if(event.key==='Enter'||event.key===' '){event.preventDefault();show(n);}});
});
document.addEventListener('pointerdown',event=>{const target=event.target;if(active&&!(target instanceof Element&&target.closest('.dia-node[data-hover]')))hide();});
addEventListener('resize',()=>place(active),{passive:true});
addEventListener('scroll',()=>place(active),{passive:true});
}
// コピー釦の汎用化（2026-09-08）＝formula・log・diff に付く [data-copy] を1つの処理で扱う。
// ⚠️既存の copy-decision と同じ作り＝clipboardが使えなければ、直前の要素を選択状態にする。
document.querySelectorAll('[data-copy]').forEach(btn=>{
btn.addEventListener('click',async()=>{
const value=btn.dataset.copy||'';
try{
if(!navigator.clipboard)throw new Error('clipboard unavailable');
await navigator.clipboard.writeText(value);
btn.textContent='コピー済み';
}catch(error){
const target=btn.previousElementSibling;
if(target){
const range=document.createRange();
range.selectNodeContents(target);
const selection=window.getSelection();
selection.removeAllRanges();
selection.addRange(range);
}
btn.textContent='全文を選択しました';
}
});
});
// 画像の拡大表示（B4・2026-09-10）＝押すと画面いっぱいの重ね表示、Escか背景クリックで閉じる。
document.querySelectorAll('[data-zoom]').forEach(frame=>{
frame.addEventListener('click',()=>{
const overlay=document.createElement('div');
overlay.className='zoom-overlay';
const clone=frame.cloneNode(true);
clone.removeAttribute('data-zoom');
overlay.appendChild(clone);
overlay.addEventListener('click',()=>overlay.remove());
function onKey(e){if(e.key==='Escape'){overlay.remove();document.removeEventListener('keydown',onKey);}}
document.addEventListener('keydown',onKey);
document.body.appendChild(overlay);
});
});"""


LABELED_COMPONENTS = {
    "summary",
    "walkthrough",
    "examples",
    "progress",
    "evidence",
    "glossary",
    "details",
}


def _tone(label: str) -> str:
    normalized = label.strip().lower()
    if normalized in {"risk", "リスク", "困りごと", "未証明", "blocker"}:
        return "risk"
    if normalized in {"goal", "目的", "背景（変更前）", "背景"}:
        return "goal"
    if normalized in {"decision", "判断", "人待ち"}:
        return "decision"
    return "neutral"


def _find_term(text: str, term: str, start: int) -> int:
    # 2026-09-29：語の境目の規則は検品器と共通（term_boundary.py）。部分一致だったので
    #   「目盛り」の中の「盛り」やファイル名の中の feedback に説明が付いていた。
    return find_term(text, term, start)


def _count_term(text: str, term: str) -> int:
    """語が本文に何回現れるかを数える（境界の判定は `_find_term` と同じ）。

    側柱の用語リスト（③）が「2回以上現れた語だけ」を選ぶために使う。
    """
    if not term:
        return 0
    count = 0
    position = 0
    while True:
        found = _find_term(text, term, position)
        if found < 0:
            return count
        count += 1
        position = found + len(term)


BADGE_TONES = {
    "good": "good", "ok": "good", "済": "good", "完了": "good",
    "warn": "warn", "注意": "warn",
    "bad": "bad", "ng": "bad", "危険": "bad",
    "new": "new", "新": "new",
    "acc": "acc", "accent": "acc", "": "acc",
}


def _badge_tone(name: str) -> str:
    """色味の名前を、CSSの短い名前に直す。知らない名前は既定（accent）に倒す。"""
    return BADGE_TONES.get(_stringify(name).strip().lower(), "acc")

def _stringify(value: object) -> str:
    if value is None:
        return ""
    return str(value)


def _tooltip_markup(display: str, entry: GlossaryEntry) -> str:
    description = _stringify(entry.description)
    data_description = escape(description, quote=True)
    aria = escape(f"{display}：{description}", quote=True)
    return (
        f'<span class="t" tabindex="0" data-d="{data_description}" '
        f'aria-label="{aria}">{escape(display)}</span>'
    )


def _escape_with_tooltips(
    value: object,
    entries: Mapping[str, GlossaryEntry],
    seen: set[str],
) -> str:
    text = _stringify(value)
    position = 0
    output: list[str] = []
    candidates = sorted(
        (
            (key, key.strip("`"), entry)
            for key, entry in entries.items()
            if key.strip("`").strip()
        ),
        key=lambda item: len(item[1]),
        reverse=True,
    )
    while position < len(text):
        matches = []
        for key, display, entry in candidates:
            if key in seen:
                continue
            found = _find_term(text, display, position)
            if found >= 0:
                matches.append((found, -len(display), key, display, entry))
        if not matches:
            output.append(escape(text[position:]))
            break
        found, _negative_length, key, display, entry = min(matches)
        output.append(escape(text[position:found]))
        output.append(_tooltip_markup(display, entry))
        seen.add(key)
        position = found + len(display)
    return "".join(output)


def _code_markup(
    value: str,
    entries: Mapping[str, GlossaryEntry],
    seen: set[str],
) -> str:
    display = value.strip()
    match = next(
        (
            (key, entry)
            for key, entry in entries.items()
            if key.strip("`").strip() == display
        ),
        None,
    )
    if match is not None:
        key, entry = match
        seen.add(key)
        body = _tooltip_markup(display, entry)
    else:
        # ⚠️2026-09-01の裁定＝コード書きの中は**包まない**。丸ごと一致するときだけ包む。
        #   道筋の途中の文字に説明が付くと、その場の意味と合わない説明が出る実例があった。
        body = escape(value)
    return f"<code>{body}</code>"


def _render_inline(
    value: object,
    entries: Mapping[str, GlossaryEntry],
    seen: set[str],
) -> str:
    """Render the small safe inline subset used by local HTML artifacts."""
    text = _stringify(value)
    output: list[str] = []
    position = 0
    plain_start = 0
    while position < len(text):
        if text[position] == "`":
            end = text.find("`", position + 1)
            if end >= 0:
                output.append(
                    _escape_with_tooltips(text[plain_start:position], entries, seen)
                )
                output.append(_code_markup(text[position + 1 : end], entries, seen))
                position = end + 1
                plain_start = position
                continue
        if text.startswith("[[", position):
            # 2026-08-29：参照頁は本文と表のセルにバッジを64個置いていた。
            # ⚠️生のHTMLは通さないので、[[色味:文字]] という書き方だけを受ける。
            end = text.find("]]", position + 2)
            if end >= 0:
                inner = text[position + 2 : end]
                if inner.strip().lower() in {"br", "改行"}:
                    output.append(
                        _escape_with_tooltips(text[plain_start:position], entries, seen)
                    )
                    output.append("<br>")
                    position = end + 2
                    plain_start = position
                    continue
                tone, separator, label = inner.partition(":")
                if not separator:
                    tone, label = "", inner
                output.append(
                    _escape_with_tooltips(text[plain_start:position], entries, seen)
                )
                if tone.strip().lower() == "pin":
                    # 2026-10-01（ユーザー承認の P3）：[[pin:3]] / [[pin:3:good]]＝画像の点の印
                    # （marks の style "pin"）と同じ見た目の番号。表の行頭に置いて画像とつなぐ。
                    number, _, pin_tone = label.partition(":")
                    output.append(
                        '<span class="pin" data-tone="%s">%s</span>'
                        % (_badge_tone(pin_tone or "acc"), escape(number.strip()))
                    )
                else:
                    output.append(
                        '<span class="badge b-%s">%s</span>'
                        % (_badge_tone(tone), escape(label.strip()))
                    )
                position = end + 2
                plain_start = position
                continue
        if text.startswith("==", position):
            end = text.find("==", position + 2)
            if end >= 0:
                output.append(
                    _escape_with_tooltips(text[plain_start:position], entries, seen)
                )
                output.append(
                    "<mark>"
                    + _render_inline(text[position + 2 : end], entries, seen)
                    + "</mark>"
                )
                position = end + 2
                plain_start = position
                continue
        if text.startswith("**", position):
            end = text.find("**", position + 2)
            if end >= 0:
                output.append(
                    _escape_with_tooltips(text[plain_start:position], entries, seen)
                )
                output.append(
                    "<strong>"
                    + _render_inline(text[position + 2 : end], entries, seen)
                    + "</strong>"
                )
                position = end + 2
                plain_start = position
                continue
        if text[position] == "*":
            # ⚠️**太字** は上で処理済みなので、ここに来る * は弱い強調だけ。
            end = text.find("*", position + 1)
            if end >= 0:
                output.append(
                    _escape_with_tooltips(text[plain_start:position], entries, seen)
                )
                output.append(
                    "<em>"
                    + _render_inline(text[position + 1 : end], entries, seen)
                    + "</em>"
                )
                position = end + 1
                plain_start = position
                continue
        position += 1
    output.append(_escape_with_tooltips(text[plain_start:], entries, seen))
    return "".join(output)


def _labeled_block(
    value: object,
    glossary_entries: Mapping[str, GlossaryEntry],
    seen_terms: set[str],
) -> str:
    rows = []
    for raw_line in str(value or "").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        label, separator, copy = line.partition("：")
        if separator and len(label) <= 28:
            rows.append(
                f'<div class="item-row" data-tone="{_tone(label)}">'
                f'<strong class="item-label">'
                f'{_render_inline(label, glossary_entries, seen_terms)}'
                f'</strong>'
                f'<span class="item-copy">'
                f'{_render_inline(copy.strip(), glossary_entries, seen_terms)}'
                f'</span></div>'
            )
        else:
            rows.append(
                f'<p class="body-copy">'
                f'{_render_inline(line, glossary_entries, seen_terms)}</p>'
            )
    return '<div class="item-stack">' + "".join(rows) + "</div>"


def _inline_with_breaks(
    value: object,
    entries: Mapping[str, GlossaryEntry],
    seen: set[str],
) -> str:
    """本文と同じ書き方で、**改行だけは改行として出す**。

    2026-08-29：参照頁は表のセルの中で改行を18回使っていた。表のセルは1行に
    まとめて書くので、改行をそのまま捨てると「2つのことを1セルに書けない」。
    入れるもの＝文字列。返るもの＝改行が `br` になったHTML。
    """
    return _render_inline(value, entries, seen).replace(NEWLINE, "<br>")

def _cells(line: str) -> list[str]:
    """1行を縦棒で列に割る。全角の｜と半角の | の両方を受ける。"""
    separator = "｜" if "｜" in line else ("|" if "|" in line else "")
    if not separator:
        return [line]
    return [cell.strip() for cell in line.split(separator)]


def _visual_block(
    value: object,
    glossary_entries: Mapping[str, GlossaryEntry],
    seen_terms: set[str],
) -> str:
    """図を組む。縦積みの流れに加えて、**縦棒で区切った行は左右に並べる**。

    2026-08-29（ユーザー裁定 P2）：house style は「比較・関係・時系列・前後」を図で示せと
    要求しているのに、縦積みの流れ図しか出せなかった。⚠️新しい記法を足しただけで、
    これまでの書き方（1行1段＋矢印だけの行）はそのまま動く。

    2026-09-10（ユーザー指摘「この表が見にくい・普通の表にしてよ」）：縦棒の行が
    **2行以上続き、列数が同じ**なら、それは表のつもりで書かれている。1行ずつ箱の格子に
    割ると読めない（実例＝「項目｜前｜後」から7行が21個の箱になった）。∴その塊は
    1行目を見出しにした普通の表として組む。縦棒の行が1行だけなら従来どおり横並びの箱。
    """
    rows: list[str] = []
    arrows = {"↓", "↑", "→", "←", "↘", "↗", "⇩", "⇧"}
    pending: list[list[str]] = []

    def flush_pending() -> None:
        if not pending:
            return
        if len(pending) >= 2 and len({len(columns) for columns in pending}) == 1:
            rows.append(
                _one_table(
                    {"head": pending[0], "rows": pending[1:]},
                    glossary_entries,
                    seen_terms,
                )
            )
        else:
            for columns in pending:
                cells = "".join(
                    '<div class="flow-cell">'
                    + _render_inline(cell, glossary_entries, seen_terms)
                    + "</div>"
                    for cell in columns
                )
                rows.append(f'<div class="flow-cols">{cells}</div>')
        pending.clear()

    for raw_line in str(value or "").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line in arrows:
            flush_pending()
            rows.append(f'<div class="flow-arrow" aria-hidden="true">{escape(line)}</div>')
            continue
        columns = _cells(line)
        if len(columns) > 1:
            pending.append(columns)
            continue
        flush_pending()
        rows.append(
            '<div class="flow-step">'
            + _render_inline(line, glossary_entries, seen_terms)
            + "</div>"
        )
    flush_pending()
    return '<div class="flow-map">' + "".join(rows) + "</div>"


DIAGRAM_TONES = {
    "neutral": "--accent",
    "good": "--pass",
    "warn": "--warn",
    "bad": "--fail",
    "risk": "--fail",
    "new": "--new",
    "acc": "--accent",
}
# 文字の幅の見積り。SVGには折り返しが無いので、箱の大きさを自分で決める必要がある。
# 全角はほぼ1文字ぶん、半角は約0.56文字ぶんとして数える（実測ではなく通例の近似）。
DIAGRAM_TITLE = 13.5
DIAGRAM_BODY = 12.0
DIAGRAM_NOTE = 10.5
DIAGRAM_NUM = 15.0
DIAGRAM_PAD_X = 14
DIAGRAM_PAD_Y = 12
DIAGRAM_GAP_X = 54
DIAGRAM_GAP_Y = 30
DIAGRAM_MARGIN = 8
DIAGRAM_AXIS_W = 34

# 2026-09-12（担当B2＝列幅720pxに収める根治）：新しい経路（_diagram_block_layout）専用の
# 文字サイズ。旧経路（_diagram_block_legacy）が使う DIAGRAM_TITLE 等はそのまま触らない
# （担当Hが並行して diagram_layout.py を直しているのと同じ理由＝互いの持ち場を壊さない）。
DIAGRAM_LAYOUT_TITLE = 14.0
DIAGRAM_LAYOUT_BODY = 13.0
DIAGRAM_LAYOUT_NOTE = 12.0
DIAGRAM_LAYOUT_NUM = 15.0
# 列幅（約720px）に収める＝H2 の layout_diagram に max_width を渡す既定値。
DIAGRAM_LAYOUT_MAX_WIDTH = 720
# 折れ線の角を丸める半径（px）。
DIAGRAM_CORNER_RADIUS = 10.0


def _text_width(line: str, size: float = DIAGRAM_BODY) -> float:
    """1行の見た目の幅を文字数から見積もる。返るもの＝ピクセル数の目安。"""
    width = 0.0
    for char in line:
        width += 0.56 if char.isascii() else 1.0
    return width * size


def _diagram_lines(value: object) -> list[str]:
    return [line for line in _stringify(value).split(NEWLINE) if line.strip()]


def _diagram_nodes(raw_nodes: object) -> list[dict]:
    """箱の宣言を、描ける形（役割ごとの行と大きさ）に直す。"""
    nodes = []
    for index, item in enumerate(raw_nodes or []):
        if not isinstance(item, Mapping):
            item = {"label": _stringify(item)}
        label_lines = _diagram_lines(item.get("label", ""))
        title = _stringify(item.get("title", "")) or (label_lines[0] if label_lines else "")
        body = _diagram_lines(item.get("text", "")) or label_lines[1:]
        note = _diagram_lines(item.get("note", ""))
        num = _stringify(item.get("num", ""))
        if not title and not body:
            continue
        widths = [_text_width(title, DIAGRAM_TITLE)]
        widths += [_text_width(line, DIAGRAM_BODY) for line in body]
        widths += [_text_width(line, DIAGRAM_NOTE) for line in note]
        width = max(widths) + DIAGRAM_PAD_X * 2 + (_text_width(num, DIAGRAM_NUM) + 8 if num else 0)
        height = (
            DIAGRAM_PAD_Y * 2
            + (20 if title else 0)
            + len(body) * 17
            + len(note) * 15
        )
        nodes.append(
            {
                "id": _stringify(item.get("id", "n%d" % index)),
                "num": num,
                "title": title,
                "body": body,
                "note": note,
                "col": int(item.get("col", index)),
                "row": int(item.get("row", 0)),
                "tone": _stringify(item.get("tone", "neutral")).lower(),
                "align": _stringify(item.get("align", "left")).lower(),
                "width": width,
                "height": max(height, 40.0),
            }
        )
    return nodes


def _diagram_edge_path(source: dict, target: dict, curve: bool) -> str:
    """2つの箱を結ぶ線。同じ行なら横、同じ列なら縦、それ以外はL字か曲線。"""
    if source["row"] == target["row"]:
        if target["x"] >= source["x"]:
            start = (source["x"] + source["width"], source["y"] + source["height"] / 2)
            end = (target["x"], target["y"] + target["height"] / 2)
        else:
            start = (source["x"], source["y"] + source["height"] / 2)
            end = (target["x"] + target["width"], target["y"] + target["height"] / 2)
        return "M %.1f %.1f L %.1f %.1f" % (start[0], start[1], end[0], end[1])
    if source["col"] == target["col"]:
        if target["y"] >= source["y"]:
            start = (source["x"] + source["width"] / 2, source["y"] + source["height"])
            end = (target["x"] + target["width"] / 2, target["y"])
        else:
            start = (source["x"] + source["width"] / 2, source["y"])
            end = (target["x"] + target["width"] / 2, target["y"] + target["height"])
        return "M %.1f %.1f L %.1f %.1f" % (start[0], start[1], end[0], end[1])
    start = (source["x"] + source["width"], source["y"] + source["height"] / 2)
    end = (target["x"], target["y"] + target["height"] / 2)
    if target["x"] < source["x"]:
        start = (source["x"], source["y"] + source["height"] / 2)
        end = (target["x"] + target["width"], target["y"] + target["height"] / 2)
    if curve:
        # ⚠️手書き頁は回り込みに三次ベジェを使っていた。L字より流れが読みやすい。
        mid = (start[0] + end[0]) / 2
        return "M %.1f %.1f C %.1f %.1f %.1f %.1f %.1f %.1f" % (
            start[0], start[1], mid, start[1], mid, end[1], end[0], end[1]
        )
    corner_y = end[1]
    return "M %.1f %.1f L %.1f %.1f L %.1f %.1f" % (
        start[0], start[1], start[0], corner_y, end[0], corner_y
    )


def _diagram_block(
    value: object,
    glossary_entries: Mapping[str, GlossaryEntry],
    seen_terms: set[str],
) -> str:
    """矢印付きの図を組む（入り口）。

    ⚠️**生のSVGは受け取らない。** レンダラーの安全性は「渡された文字は必ずエスケープする」
    ことで成り立っており、生のマークアップを通す口を開けると任意のHTMLが入る道ができる。

    入れるもの＝`{"nodes":[…], "edges":[…], "num":…, "source":…, "caption":…}`。
    帯（`bands`）・軸（`axis`）・箱幅の強制（`box_width`）を使う図は、2026-08-29版の
    列/行グリッド描画（`_diagram_block_legacy`）のまま組む＝この3つは今回の配線対象
    （nodes/edges/num/source/caption/tone/dashed/curve）に入っていない。
    それ以外（ふつうの箱と矢印の図）は `visual/diagram_layout.py:layout_diagram` に
    配置と経路の計算を委ね、ここは Layout を SVG に描くだけにする（2026-09-10）。
    """
    if not isinstance(value, Mapping):
        return ""
    if value.get("bands") or value.get("axis") or value.get("box_width"):
        return _diagram_block_legacy(value, glossary_entries, seen_terms)
    if layout_diagram is None or not (value.get("nodes") or value.get("edges")):
        return _diagram_block_legacy(value, glossary_entries, seen_terms)
    return _diagram_block_layout(value, glossary_entries, seen_terms)


# ---------------------------------------------------------------------------
# 新しい経路（担当Hの layout_diagram に配置・経路の計算を委ねる版）
# ---------------------------------------------------------------------------

def _layout_id_map(raw_nodes: Sequence[object]) -> dict[str, int]:
    id_map: dict[str, int] = {}
    for index, item in enumerate(raw_nodes or []):
        if isinstance(item, Mapping):
            given = item.get("id")
            if given is not None and _stringify(given) != "":
                id_map[_stringify(given)] = index
    return id_map


def _layout_resolve_ref(ref: object, n: int, id_map: Mapping[str, int]) -> int | None:
    """`visual/diagram_layout.py:_resolve_index` と同じ規則で辺の参照先を探す。

    ⚠️独立した複製＝相手の私用関数（`_`始まり）に結合しないためにここへ同じ規則を書く。
    番号（整数・数字文字列）でも、宣言した id（文字列）でも結び付く＝これが直す崩れ③。
    """
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


def _prep_layout_nodes(raw_nodes: Sequence[object]) -> list[dict]:
    """既存の書き方（`label`／`title`＋`text`）を、layout_diagram の入力形に直す。"""
    prepared = []
    for item in raw_nodes or []:
        if not isinstance(item, Mapping):
            item = {"label": _stringify(item)}
        label_lines = _diagram_lines(item.get("label", ""))
        title = _stringify(item.get("title", "")) or (label_lines[0] if label_lines else "")
        body_lines = _diagram_lines(item.get("text", "")) or label_lines[1:]
        note_lines = _diagram_lines(item.get("note", ""))
        node: dict[str, object] = {
            "title": title,
            "text": NEWLINE.join(body_lines),
            "note": NEWLINE.join(note_lines),
            "num": _stringify(item.get("num", "")),
            "icon": _stringify(item.get("icon", "")),
            "tone": _stringify(item.get("tone", "neutral")).lower(),
        }
        for key in ("col", "row", "x", "y"):
            if item.get(key) is not None:
                node[key] = item.get(key)
        prepared.append(node)
    return prepared


def _prep_layout_edges(
    raw_edges: Sequence[object], n: int, id_map: Mapping[str, int]
) -> tuple[list[dict], list[str], list[str]]:
    """辺を layout_diagram の入力形へ直す。返るもの＝(辺の一覧, 色味の一覧, 注意書き)。

    ⚠️参照先が見つからない辺は**捨てて注意書きに積む**（黙って捨てない＝崩れ③の修理）。
    """
    edges: list[dict] = []
    tones: list[str] = []
    warnings: list[str] = []
    for index, edge in enumerate(raw_edges or []):
        if isinstance(edge, Mapping):
            source_ref = edge.get("from")
            target_ref = edge.get("to")
            label = _stringify(edge.get("label", ""))
            dashed = bool(edge.get("dashed"))
            curve = bool(edge.get("curve"))
            kind = _stringify(edge.get("kind", "")).lower() or ("dashed" if dashed else "arrow")
            tone = _stringify(edge.get("tone", "neutral")).lower()
        else:
            text = _stringify(edge)
            head, _separator, label = text.partition("｜")
            source_ref, _arrow, target_ref = head.partition("->")
            source_ref, target_ref, label = source_ref.strip(), target_ref.strip(), label.strip()
            kind, curve, tone = "arrow", False, "neutral"
        source_index = _layout_resolve_ref(source_ref, n, id_map)
        target_index = _layout_resolve_ref(target_ref, n, id_map)
        if source_index is None or target_index is None:
            warnings.append(
                "edges[%d]: from=%r to=%r の参照先が見つからないため描かなかった"
                % (index, source_ref, target_ref)
            )
            continue
        edges.append(
            {"from": source_index, "to": target_index, "label": label, "kind": kind, "curve": curve}
        )
        tones.append(tone)
    return edges, tones, warnings


def _figure_caption_html(
    num: str,
    caption: str,
    source: str,
    glossary_entries: Mapping[str, GlossaryEntry],
    seen_terms: set[str],
) -> str:
    """図の下の1行（`図1｜説明｜出所：…`）。num/source が無ければ caption だけ。"""
    if num or source:
        parts = [part for part in (num, caption) if part]
        if source:
            parts.append("出所：" + source)
        line = "｜".join(parts)
    else:
        line = caption
    if not line:
        return ""
    return '<p class="cap">' + _render_inline(line, glossary_entries, seen_terms) + "</p>"


def _is_number_like(value: object) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _as_xy(value: object) -> tuple[float, float] | None:
    """値が (x, y) の2要素として読めれば float の組を返す。文字列は点として読まない。"""
    if isinstance(value, (str, bytes)):
        return None
    try:
        x, y = value  # type: ignore[misc]
        if not _is_number_like(x) or not _is_number_like(y):
            return None
        return float(x), float(y)
    except (TypeError, ValueError):
        return None


def _control_points(control: object) -> tuple[str, tuple[float, ...]] | None:
    """Route.control の形を読む（H2＝diagram_layout.py の契約変更を吸収する守り）。

    来てよい形＝
    - None（折れ線＝制御点なし）
    - 2要素で両方が数＝二次ベジェの制御点1つ `(cx, cy)`
    - 2要素で両方が点＝三次ベジェの制御点2つ `((c1x,c1y), (c2x,c2y))`
    - 4要素の数＝三次ベジェの制御点2つを平坦にしたもの `(c1x,c1y,c2x,c2y)`
    どれでもないものは None（呼び出し側が折れ線として扱う＝例外を投げない）。
    """
    if control is None:
        return None
    try:
        items = list(control)  # type: ignore[arg-type]
    except TypeError:
        return None
    if len(items) == 4 and all(_is_number_like(v) for v in items):
        return "cubic", tuple(float(v) for v in items)
    if len(items) == 2:
        p0, p1 = _as_xy(items[0]), _as_xy(items[1])
        if p0 is not None and p1 is not None:
            return "cubic", (p0[0], p0[1], p1[0], p1[1])
        if _is_number_like(items[0]) and _is_number_like(items[1]):
            return "quad", (float(items[0]), float(items[1]))
    return None


def _shrink_toward(origin: tuple[float, float], toward: tuple[float, float], distance: float) -> tuple[float, float]:
    """origin から toward の向きに distance だけ進んだ点（隣の区間の半分は超えない）。"""
    dx, dy = toward[0] - origin[0], toward[1] - origin[1]
    length = math.sqrt(dx * dx + dy * dy)
    if length <= 1e-6:
        return origin
    t = min(distance, length / 2.0) / length
    return (origin[0] + dx * t, origin[1] + dy * t)


def _rounded_polyline_path(points: Sequence[tuple[float, float]]) -> str:
    """制御点の無い折れ線を、角を丸めた path にする（直角の `L` だけで終わらせない）。

    各折れ点の手前・先で `DIAGRAM_CORNER_RADIUS` だけ手前に止め、その間を二次曲線
    （`Q`）でつなぐ＝半径10pxの丸め。2点だけの直線はそのまま（丸める角が無い）。
    """
    points = list(points)
    if not points:
        return ""
    if len(points) < 3:
        segments = " L ".join("%.1f %.1f" % (x, y) for x, y in points)
        return "M " + segments
    parts = ["M %.1f %.1f" % points[0]]
    for i in range(1, len(points) - 1):
        prev_pt, corner, next_pt = points[i - 1], points[i], points[i + 1]
        p_in = _shrink_toward(corner, prev_pt, DIAGRAM_CORNER_RADIUS)
        p_out = _shrink_toward(corner, next_pt, DIAGRAM_CORNER_RADIUS)
        parts.append("L %.1f %.1f" % p_in)
        parts.append("Q %.1f %.1f %.1f %.1f" % (corner[0], corner[1], p_out[0], p_out[1]))
    parts.append("L %.1f %.1f" % points[-1])
    return " ".join(parts)


def _diagram_route_path(route: object) -> str:
    """Route の点を折れ線／曲線のパスに直す（2026-09-12＝H2 の新しい control 形に対応）。

    ⚠️`control` が三次（4要素）なら `C`、二次（2要素の数）なら `Q` で描く＝
    2026-08-29版の手書き頁の三次ベジェとは記法が変わる（旧・二次1点は `C` に
    合成していたが、新しい契約では真の `Q` で描く）。制御点が無い折れ線は
    `_rounded_polyline_path` で角を丸める。
    """
    points = list(route.points)
    if not points:
        return ""
    control = getattr(route, "control", None)
    parsed = _control_points(control)
    if parsed is not None:
        start, end = points[0], points[-1]
        kind, values = parsed
        if kind == "cubic":
            c1x, c1y, c2x, c2y = values
            return "M %.1f %.1f C %.1f %.1f %.1f %.1f %.1f %.1f" % (
                start[0], start[1], c1x, c1y, c2x, c2y, end[0], end[1]
            )
        cx, cy = values
        return "M %.1f %.1f Q %.1f %.1f %.1f %.1f" % (start[0], start[1], cx, cy, end[0], end[1])
    return _rounded_polyline_path(points)


def _diagram_box_glossary_match(
    box: object, glossary_entries: Mapping[str, GlossaryEntry], seen_terms: set[str]
) -> tuple[str, str] | None:
    """⑦箱の題・本文に用語集の語があれば `(表示, 説明)` を返す（無ければ None）。"""
    combined = NEWLINE.join([*box.title_lines, *box.body_lines, *box.note_lines])
    if not combined:
        return None
    for key, entry in glossary_entries.items():
        display = key.strip("`").strip()
        if not display:
            continue
        if _find_term(combined, display, 0) >= 0:
            seen_terms.add(key)
            return display, _stringify(entry.description)
    return None


def _diagram_node_hover(item: object, fallback_title: str) -> dict[str, str] | None:
    """Return the safe, labelled explanation attached to one diagram node.

    The page definition may provide ``hover`` as a plain string or as a mapping
    with ``label/title/text/role/evidence/status``.  Rendering still escapes every
    value; the mapping only gives the browser tooltip a readable structure.
    """
    if not isinstance(item, Mapping) or item.get("hover") is None:
        return None
    raw = item.get("hover")
    if isinstance(raw, Mapping):
        detail = {
            "label": _stringify(raw.get("label", "")).strip(),
            "title": _stringify(raw.get("title", "")).strip() or fallback_title,
            "text": _stringify(raw.get("text", "")).strip(),
            "role": _stringify(raw.get("role", "")).strip(),
            "evidence": _stringify(raw.get("evidence", "")).strip(),
            "status": _stringify(raw.get("status", "")).strip(),
        }
    else:
        detail = {
            "label": "",
            "title": fallback_title,
            "text": _stringify(raw).strip(),
            "role": "",
            "evidence": "",
            "status": "",
        }
    if not any(detail[key] for key in ("label", "text", "role", "evidence", "status")):
        return None
    return detail


def _diagram_hover_attributes(detail: Mapping[str, str]) -> tuple[str, str]:
    """Build escaped SVG attributes and a native-title fallback for one detail."""
    aria_parts = [detail.get("title", ""), detail.get("text", "")]
    for label, key in (("図での役割", "role"), ("根拠", "evidence"), ("読み方", "status")):
        value = detail.get(key, "")
        if value:
            aria_parts.append(label + "：" + value)
    aria = "。".join(part.strip("。 ") for part in aria_parts if part.strip("。 "))
    attrs = [
        'class="dia-node"',
        'data-hover="true"',
        'tabindex="0"',
        'role="img"',
        'aria-label="%s"' % escape(aria, quote=True),
    ]
    for key in ("label", "title", "text", "role", "evidence", "status"):
        value = detail.get(key, "")
        if value:
            attrs.append('data-hover-%s="%s"' % (key, escape(value, quote=True)))
    return " " + " ".join(attrs), "<title>%s</title>" % escape(aria)


def _diagram_block_layout(
    value: Mapping[str, object],
    glossary_entries: Mapping[str, GlossaryEntry],
    seen_terms: set[str],
) -> str:
    raw_nodes = list(value.get("nodes") or [])
    if not raw_nodes:
        return ""
    n = len(raw_nodes)
    id_map = _layout_id_map(raw_nodes)
    nodes_for_layout = _prep_layout_nodes(raw_nodes)
    edges_for_layout, edge_tones, edge_warnings = _prep_layout_edges(
        list(value.get("edges") or []), n, id_map
    )
    try:
        max_cols = int(value.get("max_cols", 3) or 3)
    except (TypeError, ValueError):
        max_cols = 3
    direction = _stringify(value.get("direction", "")).strip().lower() or "auto"
    # 2026-09-12（担当B2）：列幅（約720px）に収まる図を計算側に作らせる＝H2 が
    # max_width を配線中でも壊れないよう、無ければ渡さずに呼び直す（契約の過渡期の守り）。
    try:
        layout = layout_diagram(
            nodes_for_layout, edges_for_layout, max_cols=max_cols, direction=direction,
            font_px=14, max_width=DIAGRAM_LAYOUT_MAX_WIDTH,
        )
    except TypeError:
        layout = layout_diagram(
            nodes_for_layout, edges_for_layout, max_cols=max_cols, direction=direction, font_px=14
        )

    align_by_index = {
        index: _stringify(item.get("align", "left")).lower() if isinstance(item, Mapping) else "left"
        for index, item in enumerate(raw_nodes)
    }

    shapes: list[str] = []
    icon_warnings: list[str] = []
    hover_count = 0
    for box in layout.boxes:
        stroke = DIAGRAM_TONES.get(box.tone, "--accent")
        centered = align_by_index.get(box.node_index, "left") == "center"
        anchor = ' text-anchor="middle"' if centered else ""

        icon_html = ""
        text_indent = 0.0
        if box.icon:
            body = _render_icon_svg(box.icon, size=16, tone="ink") if _render_icon_svg else None
            if body:
                insert_at = body.find("<svg") + len("<svg")
                icon_html = (
                    body[:insert_at]
                    + ' x="%.1f" y="%.1f"' % (box.x + 4, box.y + 4)
                    + body[insert_at:]
                )
                text_indent = 22.0
            else:
                icon_warnings.append("diagram: 不明な記号 %r は無視した" % box.icon)

        match = _diagram_box_glossary_match(box, glossary_entries, seen_terms)
        raw_node = raw_nodes[box.node_index] if 0 <= box.node_index < len(raw_nodes) else None
        hover = _diagram_node_hover(raw_node, " ".join(box.title_lines).strip())
        group_attrs = ""
        if hover:
            group_attrs, title_tag = _diagram_hover_attributes(hover)
            hover_count += 1
        else:
            title_tag = (
                "<title>%s：%s</title>" % (escape(match[0]), escape(match[1])) if match else ""
            )
        underline = (
            '<line x1="%.1f" y1="%.1f" x2="%.1f" y2="%.1f" stroke="var(%s)" '
            'stroke-width="1" stroke-dasharray="2 3"></line>'
            % (box.x + 4, box.y + box.h - 3, box.x + box.w - 4, box.y + box.h - 3, stroke)
            if match
            else ""
        )

        rect = (
            '<rect x="%.1f" y="%.1f" width="%.1f" height="%.1f" rx="8" '
            'fill="var(--surface)" stroke="var(%s)" stroke-width="1.5"></rect>'
            % (box.x, box.y, box.w, box.h, stroke)
        )

        text_x = box.x + box.w / 2.0 if centered else box.x + DIAGRAM_PAD_X + text_indent
        cursor = box.y + DIAGRAM_PAD_Y + 13
        num_indent = 0.0
        text_parts: list[str] = []
        if box.num:
            text_parts.append(
                '<text x="%.1f" y="%.1f" fill="var(%s)" font-size="%.1f" '
                'font-weight="700">%s</text>'
                % (
                    box.x + DIAGRAM_PAD_X + text_indent, cursor, stroke,
                    DIAGRAM_LAYOUT_NUM, escape(box.num),
                )
            )
            num_indent = _text_width(box.num, DIAGRAM_LAYOUT_NUM) + 8
        # ⚠️題が2行以上でも本文がずれない＝ここで1行ずつ cursor を進めるので、
        #   本文・注記は「実際に置かれた題の行数ぶん下」から自然に始まる
        #   （固定オフセットで決め打ちしない＝計算側の title_lines の長さそのものを使う）。
        for line_index, line in enumerate(box.title_lines):
            text_parts.append(
                '<text x="%.1f" y="%.1f"%s fill="var(--ink)" font-size="%.1f" '
                'font-weight="700">%s</text>'
                % (
                    text_x + (num_indent if line_index == 0 and not centered else 0),
                    cursor, anchor, DIAGRAM_LAYOUT_TITLE, escape(line),
                )
            )
            cursor += 20
        for line in box.body_lines:
            text_parts.append(
                '<text x="%.1f" y="%.1f"%s fill="var(--ink-2)" font-size="%.1f">%s</text>'
                % (text_x, cursor, anchor, DIAGRAM_LAYOUT_BODY, escape(line))
            )
            cursor += 17
        for line in box.note_lines:
            text_parts.append(
                '<text x="%.1f" y="%.1f"%s fill="var(--ink-3)" font-size="%.1f">%s</text>'
                % (text_x, cursor, anchor, DIAGRAM_LAYOUT_NOTE, escape(line))
            )
            cursor += 15

        shapes.append(
            "<g%s>%s%s%s%s%s</g>"
            % (group_attrs, title_tag, rect, underline, icon_html, "".join(text_parts))
        )

    # ⚠️矢じりの色＝矢印線の色に揃える（2026-09-12）。以前は全部 var(--accent) 固定で、
    #   色味（tone）を付けた辺・破線の辺でも矢じりだけ既定色のままずれていた。
    #   使った色（DIAGRAM_TONES の値＝コード側の固定語だけ・利用者の生文字列は使わない）
    #   ごとに矢じりを1組だけ作る。
    route_paths_svg: list[str] = []
    route_labels_svg: list[str] = []
    used_strokes: dict[str, None] = {}
    for route, tone in zip(layout.routes, edge_tones):
        stroke = DIAGRAM_TONES.get(tone, "--accent")
        used_strokes[stroke] = None
        stroke_key = stroke.lstrip("-")
        dash = ' stroke-dasharray="5 4"' if route.kind == "dashed" else ""
        marker_start = (
            ' marker-start="url(#dia-arrow-start-%s)"' % stroke_key
            if route.kind == "biarrow"
            else ""
        )
        marker_end = (
            "" if route.kind == "line" else ' marker-end="url(#dia-arrow-%s)"' % stroke_key
        )
        route_paths_svg.append(
            '<path d="%s" fill="none" stroke="var(%s)" stroke-width="1.6"%s%s%s></path>'
            % (_diagram_route_path(route), stroke, dash, marker_start, marker_end)
        )
        if route.label:
            # ⚠️背景の矩形は付けない＝2026-08-29版の矢印ラベルと同じ「文字だけ」に揃える
            #   （箱の数=<rect>の数、という既存の検査がそのまま通る）。
            route_labels_svg.append(
                '<text x="%.1f" y="%.1f" fill="var(--ink-2)" font-size="12" '
                'paint-order="stroke" stroke="var(--ground)" stroke-width="5" stroke-linejoin="round" '
                'text-anchor="middle">%s</text>'
                # layout_diagram の label_y は文字の中心。SVG text の y は基線なので、
                # 12px文字の見かけの中心が label_y 付近になるよう6px下へ置く。
                % (route.label_x, route.label_y + 6, escape(route.label))
            )

    described = _stringify(value.get("title") or value.get("caption") or "図")
    marker_defs: list[str] = []
    for stroke in used_strokes:
        stroke_key = stroke.lstrip("-")
        marker_defs.append(
            '<marker id="dia-arrow-%s" viewBox="0 0 10 10" refX="9" refY="5" '
            'markerWidth="7" markerHeight="7" orient="auto-start-reverse">'
            '<path d="M 0 0 L 10 5 L 0 10 z" fill="var(%s)"></path></marker>'
            % (stroke_key, stroke)
        )
        marker_defs.append(
            '<marker id="dia-arrow-start-%s" viewBox="0 0 10 10" refX="1" refY="5" '
            'markerWidth="7" markerHeight="7" orient="auto-start-reverse">'
            '<path d="M 10 0 L 0 5 L 10 10 z" fill="var(%s)"></path></marker>'
            % (stroke_key, stroke)
        )
    marker = "<defs>" + "".join(marker_defs) + "</defs>"
    width = max(layout.width, 1.0)
    height = max(layout.height, 1.0)
    # ⚠️幅・高さを明示の属性で持たせる（viewBoxだけだとブラウザの既定サイズに丸められ、
    #   幅に合わせて縮む＝文字が潰れる崩れ②③の原因になる）。
    # 2026-09-12（担当B2）：`max_width` で計算側が列幅（約720px）に収めるので、
    #   CSS側（`svg.dia`）は `max-width:100%;height:auto` にして「1280px幅では縮まず・
    #   横スクロールも出ない」を実現する。ただし container がそれより狭い画面では、
    #   縮みを1割まで（viewBox幅の0.9倍）に抑え、それ以上は `.dia-wrap` の横スクロールへ
    #   委ねる＝この下限は図ごとに違うのでインラインの `min-width` で持たせる。
    min_width = max(round(width * 0.9), 1)
    svg = (
        '<svg class="dia" viewBox="0 0 %.0f %.0f" width="%.0f" height="%.0f" '
        'style="min-width:%dpx" role="img" aria-label="%s">'
        "<title>%s</title>%s%s%s%s</svg>"
        % (
            width, height, width, height, min_width,
            escape(described, quote=True),
            escape(described),
            marker,
            "".join(route_paths_svg),
            "".join(shapes),
            "".join(route_labels_svg),
        )
    )
    caption = _stringify(value.get("caption", ""))
    num = _stringify(value.get("num", ""))
    source = _stringify(value.get("source", ""))
    caption_html = _figure_caption_html(num, caption, source, glossary_entries, seen_terms)

    all_warnings = list(layout.warnings) + edge_warnings + icon_warnings
    warn_html = (
        '<ul class="dia-warn">'
        + "".join("<li>" + escape(w) + "</li>" for w in all_warnings)
        + "</ul>"
        if all_warnings
        else ""
    )
    hover_hint = (
        '<p class="dia-hover-hint"><span aria-hidden="true">ⓘ</span>'
        "箱にマウスを重ねる、Tabキーで選ぶ、またはタップすると詳しい説明を表示します。"
        "</p>"
        if hover_count
        else ""
    )
    return hover_hint + '<div class="dia-wrap">' + svg + "</div>" + caption_html + warn_html


# ---------------------------------------------------------------------------
# 旧い経路（帯・軸・箱幅の強制つきの図。2026-08-29版のまま）
# ---------------------------------------------------------------------------

def _diagram_block_legacy(
    value: object,
    glossary_entries: Mapping[str, GlossaryEntry],
    seen_terms: set[str],
) -> str:
    """帯・軸・箱幅の強制つきの図をSVGで組む（2026-08-29／帯・軸・曲線を追加）。

    ⚠️**生のSVGは受け取らない。** レンダラーの安全性は「渡された文字は必ずエスケープする」
    ことで成り立っており、生のマークアップを通す口を開けると任意のHTMLが入る道ができる。

    入れるもの＝`{"nodes":[…], "edges":[…], "bands":[…], "axis":{…},
    "box_width":数, "title":…, "caption":…}`。返るもの＝SVGと補足のHTML。
    """
    if not isinstance(value, Mapping):
        return ""
    nodes = _diagram_nodes(value.get("nodes"))
    bands = [b for b in (value.get("bands") or []) if isinstance(b, Mapping)]
    if not nodes and not bands:
        return ""
    axis = value.get("axis") if isinstance(value.get("axis"), Mapping) else None
    box_width = value.get("box_width")

    columns = sorted({node["col"] for node in nodes} | {int(b.get("col", 0)) for b in bands})
    rows = sorted({node["row"] for node in nodes}) or [0]
    column_width = {}
    for col in columns:
        in_col = [n["width"] for n in nodes if n["col"] == col]
        band_w = [float(b.get("w", 150)) for b in bands if int(b.get("col", 0)) == col]
        if box_width and in_col:
            column_width[col] = float(box_width)
        else:
            column_width[col] = max(in_col + band_w) if (in_col or band_w) else 150.0
    row_height = {
        row: max([n["height"] for n in nodes if n["row"] == row] or [40.0]) for row in rows
    }

    left = float(DIAGRAM_MARGIN + (DIAGRAM_AXIS_W if axis else 0))
    x_of = {}
    offset = left
    for col in columns:
        x_of[col] = offset
        offset += column_width[col] + DIAGRAM_GAP_X
    total_width = offset - DIAGRAM_GAP_X + DIAGRAM_MARGIN
    y_of = {}
    offset = float(DIAGRAM_MARGIN + (18 if axis else 0))
    for row in rows:
        y_of[row] = offset
        offset += row_height[row] + DIAGRAM_GAP_Y
    total_height = offset - DIAGRAM_GAP_Y + DIAGRAM_MARGIN + (18 if axis else 0)

    by_id = {}
    for node in nodes:
        node["x"] = x_of[node["col"]]
        node["y"] = y_of[node["row"]] + (row_height[node["row"]] - node["height"]) / 2
        if box_width:
            node["width"] = column_width[node["col"]]
        by_id[node["id"]] = node

    shapes = []
    # 帯は箱より先に描く＝背面に回す
    for band in bands:
        col = int(band.get("col", 0))
        tone = DIAGRAM_TONES.get(_stringify(band.get("tone", "acc")).lower(), "--accent")
        row_from = int(band.get("row_from", rows[0]))
        row_to = int(band.get("row_to", rows[-1]))
        bx = x_of.get(col, left)
        bw = column_width.get(col, 150.0)
        by = y_of.get(row_from, float(DIAGRAM_MARGIN)) - 10
        bottom = y_of.get(row_to, by) + row_height.get(row_to, 40.0) + 10
        shapes.append(
            '<rect x="%.1f" y="%.1f" width="%.1f" height="%.1f" rx="6" fill="none" '
            'stroke="var(%s)" stroke-width="1.3" stroke-dasharray="5 4"></rect>'
            % (bx, by, bw, bottom - by, tone)
        )
        center = bx + bw / 2
        cursor = by + 22
        label = _stringify(band.get("label", ""))
        if label:
            shapes.append(
                '<text x="%.1f" y="%.1f" text-anchor="middle" fill="var(%s)" '
                'font-size="12" font-weight="700">%s</text>'
                % (center, cursor, tone, escape(label))
            )
            cursor += 17
        note = _stringify(band.get("note", ""))
        if note:
            shapes.append(
                '<text x="%.1f" y="%.1f" text-anchor="middle" fill="var(%s)" '
                'font-size="10.5">%s</text>' % (center, cursor, tone, escape(note))
            )
            cursor += 20
        for entry in band.get("items", ()) or ():
            cursor += 18
            shapes.append(
                '<text x="%.1f" y="%.1f" text-anchor="middle" fill="var(--ink)" '
                'font-size="11.5">%s</text>' % (center, cursor, escape(_stringify(entry)))
            )

    if axis:
        axis_x = float(DIAGRAM_MARGIN + 12)
        shapes.append(
            '<line x1="%.1f" y1="%.1f" x2="%.1f" y2="%.1f" stroke="var(--rule)" '
            'stroke-width="2"></line>'
            % (axis_x, float(DIAGRAM_MARGIN + 22), axis_x, total_height - DIAGRAM_MARGIN - 20)
        )
        top = _stringify(axis.get("top", ""))
        bottom_label = _stringify(axis.get("bottom", ""))
        if top:
            shapes.append(
                '<text x="%.1f" y="%.1f" fill="var(--ink-3)" font-size="11">%s</text>'
                % (float(DIAGRAM_MARGIN), float(DIAGRAM_MARGIN + 12), escape(top))
            )
        if bottom_label:
            shapes.append(
                '<text x="%.1f" y="%.1f" fill="var(--ink-3)" font-size="11">%s</text>'
                % (float(DIAGRAM_MARGIN), total_height - DIAGRAM_MARGIN - 4, escape(bottom_label))
            )

    for node in nodes:
        stroke = DIAGRAM_TONES.get(node["tone"], "--accent")
        shapes.append(
            '<rect x="%.1f" y="%.1f" width="%.1f" height="%.1f" rx="6" '
            'fill="var(--surface)" stroke="var(%s)" stroke-width="1.5"></rect>'
            % (node["x"], node["y"], node["width"], node["height"], stroke)
        )
        centered = node["align"] == "center"
        text_x = node["x"] + (node["width"] / 2 if centered else DIAGRAM_PAD_X)
        anchor = ' text-anchor="middle"' if centered else ""
        cursor = node["y"] + DIAGRAM_PAD_Y + 13
        indent = 0.0
        if node["num"]:
            shapes.append(
                '<text x="%.1f" y="%.1f" fill="var(%s)" font-size="%.1f" '
                'font-weight="700">%s</text>'
                % (node["x"] + DIAGRAM_PAD_X, cursor, stroke, DIAGRAM_NUM, escape(node["num"]))
            )
            indent = _text_width(node["num"], DIAGRAM_NUM) + 8
        if node["title"]:
            shapes.append(
                '<text x="%.1f" y="%.1f"%s fill="var(--ink)" font-size="%.1f" '
                'font-weight="700">%s</text>'
                % (text_x + indent, cursor, anchor, DIAGRAM_TITLE, escape(node["title"]))
            )
            cursor += 20
        for line in node["body"]:
            shapes.append(
                '<text x="%.1f" y="%.1f"%s fill="var(--ink-2)" font-size="%.1f">%s</text>'
                % (text_x, cursor, anchor, DIAGRAM_BODY, escape(line))
            )
            cursor += 17
        for line in node["note"]:
            shapes.append(
                '<text x="%.1f" y="%.1f"%s fill="var(--ink-3)" font-size="%.1f">%s</text>'
                % (text_x, cursor, anchor, DIAGRAM_NOTE, escape(line))
            )
            cursor += 15

    arrows = []
    for edge in value.get("edges", []) or []:
        if isinstance(edge, Mapping):
            source_id = _stringify(edge.get("from", ""))
            target_id = _stringify(edge.get("to", ""))
            label = _stringify(edge.get("label", ""))
            dashed = bool(edge.get("dashed"))
            curve = bool(edge.get("curve"))
            tone = _stringify(edge.get("tone", "neutral")).lower()
        else:
            text = _stringify(edge)
            head, _separator, label = text.partition("｜")
            source_id, _arrow, target_id = head.partition("->")
            source_id, target_id, label = source_id.strip(), target_id.strip(), label.strip()
            dashed = False
            curve = False
            tone = "neutral"
        source = by_id.get(source_id)
        target = by_id.get(target_id)
        if source is None or target is None:
            continue
        stroke = DIAGRAM_TONES.get(tone, "--accent")
        dash = ' stroke-dasharray="5 4"' if dashed else ""
        arrows.append(
            '<path d="%s" fill="none" stroke="var(%s)" stroke-width="1.5"%s '
            'marker-end="url(#dia-arrow)"></path>'
            % (_diagram_edge_path(source, target, curve), stroke, dash)
        )
        if label:
            mid_x = (source["x"] + source["width"] / 2 + target["x"] + target["width"] / 2) / 2
            mid_y = (source["y"] + source["height"] / 2 + target["y"] + target["height"] / 2) / 2
            arrows.append(
                '<text x="%.1f" y="%.1f" fill="var(--ink-2)" font-size="11" '
                'text-anchor="middle">%s</text>' % (mid_x, mid_y - 6, escape(label))
            )

    described = _stringify(value.get("title") or value.get("caption") or "図")
    marker = (
        '<defs><marker id="dia-arrow" viewBox="0 0 10 10" refX="9" refY="5" '
        'markerWidth="7" markerHeight="7" orient="auto-start-reverse">'
        '<path d="M 0 0 L 10 5 L 0 10 z" fill="var(--accent)"></path></marker></defs>'
    )
    # ⚠️幅・高さを明示の属性で持たせる（2026-09-10）＝新しい経路（_diagram_block_layout）
    #   と同じ理由で、CSS側の width:100% を外したのでここも自前でネイティブの大きさを持つ。
    svg = (
        '<svg class="dia" viewBox="0 0 %.0f %.0f" width="%.0f" height="%.0f" role="img" '
        'aria-label="%s" preserveAspectRatio="xMidYMid meet">'
        "<title>%s</title>%s%s%s</svg>"
        % (
            total_width,
            total_height,
            total_width,
            total_height,
            escape(described, quote=True),
            escape(described),
            marker,
            "".join(shapes),
            "".join(arrows),
        )
    )
    caption = _stringify(value.get("caption", ""))
    # ⑤2026-09-08：num（例「図1」）と source（出所）があれば、既存の caption と
    #   合わせて figcaption 相当の1行「図1｜説明｜出所：…」にする。無ければ従来どおり。
    num = _stringify(value.get("num", ""))
    source = _stringify(value.get("source", ""))
    if num or source:
        line_parts = [part for part in (num, caption) if part]
        if source:
            line_parts.append("出所：" + source)
        caption_line = "｜".join(line_parts)
    else:
        caption_line = caption
    caption_html = (
        '<p class="cap">' + _render_inline(caption_line, glossary_entries, seen_terms) + "</p>"
        if caption_line
        else ""
    )
    return '<div class="dia-wrap">' + svg + "</div>" + caption_html


def _looks_safe_svg(svg: str) -> bool:
    """担当Bの `render_chart` が返したSVGへの最低限の目視代わり。

    ⚠️担当Bの純関数は信用してよい契約だが、モジュールが未完成／壊れている間に
      危険な文字列が紛れ込んでも黙って埋め込まない、という保険を1枚だけ足す。
    """
    lowered = svg.lower()
    if "<script" in lowered or "javascript:" in lowered:
        return False
    if re.search(r"\son\w+\s*=", lowered):
        return False
    return True


def _chart_table_fallback(
    spec: Mapping[str, object],
    glossary_entries: Mapping[str, GlossaryEntry],
    seen_terms: set[str],
) -> str:
    """⑥ render_chart が無い・失敗した時に、同じ数値を表へ落とす（黙って消さない）。"""
    labels = [_stringify(label) for label in (spec.get("labels") or [])]
    head = [_stringify(spec.get("title", "")) or "系列"] + labels
    rows = []
    for entry in spec.get("series", ()) or ():
        if not isinstance(entry, Mapping):
            continue
        name = _stringify(entry.get("name", ""))
        values = [_stringify(v) for v in (entry.get("values") or ())]
        rows.append([name] + values)
    caption_parts = []
    caption = _stringify(spec.get("caption", ""))
    if caption:
        caption_parts.append(caption)
    unit = _stringify(spec.get("unit", ""))
    if unit:
        caption_parts.append("単位：" + unit)
    source = _stringify(spec.get("source", ""))
    if source:
        caption_parts.append("出所：" + source)
    table_spec: dict[str, object] = {"head": head, "rows": rows}
    if caption_parts:
        table_spec["caption"] = "｜".join(caption_parts)
    return _one_table(table_spec, glossary_entries, seen_terms)


def _limit_svg_shrink(svg: str, ratio: float = 0.9, grow: float | None = None) -> str:
    """SVG に「幅は viewBox の幅まで・縮むのは ratio 倍まで」の指定を足す（2026-09-26）。

    それより狭い画面では、外側の `.dia-wrap` が横スクロールになる（文字が潰れない）。
    viewBox が読めなければ何もしない。
    """
    vb = re.search(r'viewBox="\s*[-\d.]+\s+[-\d.]+\s+([\d.]+)\s+([\d.]+)', svg)
    if not vb:
        return svg
    try:
        vb_w = float(vb.group(1))
    except ValueError:
        return svg
    if grow:
        # 枠が広ければ grow 倍まで拡大してよい（小さな字で描いた数値の図を、机の画面で読みやすくする）。
        style = 'style="width:100%%;max-width:%dpx;min-width:%dpx"' % (round(vb_w * grow), round(vb_w * ratio))
    else:
        style = 'style="width:min(100%%,%dpx);min-width:%dpx"' % (round(vb_w), round(vb_w * ratio))
    close = svg.find(">")
    if close <= 0:
        return svg
    return svg[:close] + " " + style + svg[close:]


def _chart_block(
    value: object,
    glossary_entries: Mapping[str, GlossaryEntry],
    seen_terms: set[str],
) -> str:
    """⑥ 数値の図。描画は担当Bの `visual/charts.py:render_chart`（無ければ表へ落ちる）。

    入れるもの＝`{"kind","title","labels","series":[{"name","values"}],"unit",
    "caption","source"}`。返るもの＝SVG（横スクロールの枠つき）か、同じ数値の表。
    """
    if not isinstance(value, Mapping):
        return ""
    svg = None
    if render_chart is not None:
        try:
            candidate = render_chart(value)
        except Exception:
            candidate = None
        if (
            isinstance(candidate, str)
            and candidate.strip().startswith("<svg")
            and _looks_safe_svg(candidate)
        ):
            svg = candidate
    if svg is not None:
        # 2026-09-26（見やすさ V2・実測＝390px の画面で数値の図の文字が 5px まで縮んで読めなかった。
        # 数値の図だけ幅の指定が無く、枠の幅いっぱいに縮んでいた）：ほかの図と同じく、
        # viewBox の幅を基準に置き、縮みは1割まで・それより狭い画面は枠の横スクロールに任せる。
        return '<div class="dia-wrap chart-wrap">' + _limit_svg_shrink(svg, grow=1.25) + "</div>"
    return (
        '<div class="chart-wrap chart-fallback">'
        + _chart_table_fallback(value, glossary_entries, seen_terms)
        + "</div>"
    )


def _formula_block(
    value: object,
    glossary_entries: Mapping[str, GlossaryEntry],
    seen_terms: set[str],
) -> str:
    """⑨ 数式。担当Cの `visual/formula.py:tex_to_mathml` が使えればMathML、

    使えない・None・例外・モジュール無しの時は原文を `<code>` で見せる（黙って消さない）。
    ⚠️`tex_to_mathml` は完全にエスケープ済みトークンだけから組む契約＝返り値は信用してよい。
    入れるもの＝`{"tex": "LaTeX原文", "reading": "読み方（任意）"}`。コピー釦が付く。
    """
    if isinstance(value, Mapping):
        tex = _stringify(value.get("tex", ""))
        reading = _stringify(value.get("reading", ""))
    else:
        tex = _stringify(value)
        reading = ""
    if not tex.strip():
        return ""
    mathml = None
    if tex_to_mathml is not None:
        try:
            mathml = tex_to_mathml(tex)
        except Exception:
            mathml = None
    body = mathml if isinstance(mathml, str) and mathml.strip() else f"<code>{escape(tex)}</code>"
    reading_html = (
        '<p class="formula-reading">'
        + _render_inline(reading, glossary_entries, seen_terms)
        + "</p>"
        if reading
        else ""
    )
    return '<div class="formula">' + body + _copy_button(tex) + reading_html + "</div>"


# 2026-10-01（ユーザー承認の P4・P5）：表のセルの積み上げ棒と薄い分母。
# 積み上げ棒の既定の色の順＝良い・注意・悪い（4つ目からは中立の色）。
STACK_DEFAULT_TONES = ("good", "warn", "bad")
TONE_NAMES = {"good": "良い", "warn": "注意", "bad": "悪い", "acc": "そのほか", "new": "新しい"}
_FRACTION = re.compile(r"^\s*([0-9][0-9,.]*)\s*/\s*([0-9][0-9,.]*)(.*)$")


def _int_list(value: object) -> list[int]:
    """列や行の番号の一覧を受ける（数でない物は捨てる）。"""
    if value is None:
        return []
    items = value if isinstance(value, (list, tuple)) else [value]
    numbers = []
    for item in items:
        try:
            numbers.append(int(item))
        except (TypeError, ValueError):
            continue
    return numbers


def _stack_values(text: str) -> list[tuple[str, float]] | None:
    """「62,3,0」（読点も可）を内訳の数の並びにする。2つ以上の0以上の数でなければ None。"""
    parts = [p.strip() for p in re.split(r"[,、]", text.strip()) if p.strip()]
    if len(parts) < 2:
        return None
    values = []
    for part in parts:
        try:
            number = float(part)
        except ValueError:
            return None
        if number < 0:
            return None
        values.append((part, number))
    return values


def _stack_tone(index: int, tones: Sequence[str]) -> str:
    if index < len(tones) and tones[index]:
        return tones[index]
    return STACK_DEFAULT_TONES[index] if index < len(STACK_DEFAULT_TONES) else "acc"


def _stack_label(index: int, labels: Sequence[str], tone: str) -> str:
    if index < len(labels) and labels[index]:
        return labels[index]
    return TONE_NAMES.get(tone, "区分%d" % (index + 1))


def _stack_html(
    values: Sequence[tuple[str, float]], labels: Sequence[str], tones: Sequence[str]
) -> str:
    """積み上げ棒のセル＝「1つ目/合計」の数と、内訳の割合で色分けした1本の棒。"""
    total = sum(number for _, number in values)
    total_text = (
        str(int(total)) if all(float(n).is_integer() for _, n in values) else ("%g" % total)
    )
    segments = []
    spoken = []
    for index, (shown, number) in enumerate(values):
        tone = _stack_tone(index, tones)
        label = _stack_label(index, labels, tone)
        spoken.append("%s %s" % (label, shown))
        if number > 0:
            segments.append(
                '<i data-tone="%s" style="flex-grow:%g" title="%s"></i>'
                % (escape(tone, quote=True), number, escape("%s %s" % (label, shown), quote=True))
            )
    return (
        '<span class="v">' + escape(values[0][0])
        + '<span class="of">/' + escape(total_text) + "</span></span>"
        + '<span class="stack" role="img" aria-label="%s">%s</span>'
        % (escape("・".join(spoken), quote=True), "".join(segments))
    )


def _stack_legend(labels: Sequence[str], tones: Sequence[str]) -> str:
    """積み上げ棒の色の凡例（表の上に1行）。"""
    count = max(len(labels), len(tones)) or len(STACK_DEFAULT_TONES)
    items = []
    for index in range(count):
        tone = _stack_tone(index, tones)
        items.append(
            '<span><i data-tone="%s"></i>%s</span>'
            % (escape(tone, quote=True), escape(_stack_label(index, labels, tone)))
        )
    return '<div class="stack-legend" aria-label="色の意味">' + "".join(items) + "</div>"


def _table_block(
    value: object,
    glossary_entries: Mapping[str, GlossaryEntry],
    seen_terms: set[str],
) -> str:
    # 2026-08-29：一覧で渡されたら何枚でも並べる（参照頁は1頁に14枚あった）。
    if isinstance(value, (list, tuple)) and not isinstance(value, str):
        return "".join(
            _one_table(item, glossary_entries, seen_terms) for item in value
        )
    return _one_table(value, glossary_entries, seen_terms)


def _one_table(
    value: object,
    glossary_entries: Mapping[str, GlossaryEntry],
    seen_terms: set[str],
) -> str:
    """任意の表を組む。1行目が見出し、縦棒で列を割る。

    入れるもの＝文字列（1行目が見出し行、`補足：…` の行があれば表の補足になる）か、
    `{"caption": …, "head": [...], "rows": [[...], ...]}` の辞書。
    返るもの＝横スクロールできる表のHTML。数値だけのセルは桁を揃える。
    """
    caption = ""
    heading = ""
    widths: list[str] = []
    head: list[str] = []
    body: list[list[str]] = []
    heat_cols: list[int] = []
    bar_cols: list[int] = []
    # 2026-10-01（ユーザー承認の P4・P5・P6）：積み上げ棒の列・薄い分母の列・行の区切り・
    # 行見出し。どれも指定が無ければ今までと同じ表になる。
    stack_cols: list[int] = []
    frac_cols: list[int] = []
    group_rows: set[int] = set()
    row_head = False
    stack_labels: list[str] = []
    stack_tones: list[str] = []
    if isinstance(value, Mapping):
        caption = _stringify(value.get("caption", ""))
        heading = _stringify(value.get("heading", ""))
        widths = [_stringify(w) for w in value.get("widths", [])]
        head = [_stringify(cell) for cell in value.get("head", [])]
        for row in value.get("rows", []):
            body.append([_stringify(cell) for cell in row])
        # ⑨2026-09-10：表の色付け（heat）と行内の棒（bars）＝列番号の一覧を受ける。
        for raw_index in value.get("heat", []) or []:
            try:
                heat_cols.append(int(raw_index))
            except (TypeError, ValueError):
                continue
        for raw_index in value.get("bars", []) or []:
            try:
                bar_cols.append(int(raw_index))
            except (TypeError, ValueError):
                continue
        stack_cols = _int_list(value.get("stack"))
        frac_cols = _int_list(value.get("frac"))
        group_rows = set(_int_list(value.get("groups")))
        row_head = _truthy(value.get("row_head"))
        stack_labels = [_stringify(x) for x in (value.get("stack_labels") or [])]
        stack_tones = [_badge_tone(_stringify(x)) for x in (value.get("stack_tones") or [])]
    else:
        for raw_line in str(value or "").splitlines():
            line = raw_line.strip()
            if not line:
                continue
            label, separator, rest = line.partition("：")
            if separator and label.strip() in {"補足", "caption"}:
                caption = rest.strip()
                continue
            columns = _cells(line)
            if not head:
                head = columns
            else:
                body.append(columns)
    if not head:
        return ""
    width = max([len(head)] + [len(row) for row in body]) if body else len(head)
    head = head + [""] * (width - len(head))
    header_cells = "".join(
        "<th%s>%s</th>" % (
            (' style="width:%s"' % escape(widths[index], quote=True))
            if index < len(widths) and widths[index]
            else "",
            escape(cell),
        )
        for index, cell in enumerate(head)
    )
    col_stats: dict[int, tuple[float, float]] = {}
    for col in set(heat_cols) | set(bar_cols):
        numeric_values = [
            v
            for v in (
                _numeric_value(row[col].partition(NEWLINE)[0]) if col < len(row) else None
                for row in body
            )
            if v is not None
        ]
        if numeric_values:
            col_stats[col] = (min(numeric_values), max(numeric_values))
    rows_html = []
    used_stack = False
    for row_index, row in enumerate(body):
        padded = row + [""] * (width - len(row))
        cell_parts = []
        for index, cell in enumerate(padded):
            style_bits: list[str] = []
            extra_html = ""
            # 2026-10-01（P5）：セルの1行目が本体、改行の後は小さい注記（cell-note）。
            first, newline, rest = cell.partition(NEWLINE)
            note_html = (
                '<span class="cell-note">'
                + _inline_with_breaks(rest, glossary_entries, seen_terms)
                + "</span>"
                if newline and rest.strip()
                else ""
            )
            stats = col_stats.get(index)
            numeric = _numeric_value(first)
            if index in heat_cols and stats and numeric is not None and heat_color is not None:
                lo, hi = stats
                style_bits.append("background:" + heat_color(numeric, lo, hi))
            if index in bar_cols and stats and numeric is not None:
                lo, hi = stats
                denom = hi if hi else 1.0
                frac = max(0.0, min(1.0, numeric / denom)) if denom else 0.0
                extra_html = (
                    '<span class="cell-bar"><span class="cell-bar-fill" '
                    'style="width:%.1f%%"></span></span>' % (frac * 100)
                )
            stack_values = _stack_values(first) if index in stack_cols else None
            classes: list[str] = []
            if stack_values is not None:
                used_stack = True
                main_html = _stack_html(stack_values, stack_labels, stack_tones)
                classes.append("stackcell")
            elif index in frac_cols and _FRACTION.match(first):
                match = _FRACTION.match(first)
                main_html = (
                    '<span class="v">' + escape(match.group(1))
                    + '<span class="of">/' + escape(match.group(2)) + "</span></span>"
                    + _render_inline(match.group(3), glossary_entries, seen_terms)
                )
                classes.append("num")
            else:
                main_html = _render_inline(first, glossary_entries, seen_terms)
                if _is_numeric(first):
                    classes.append("num")
            style_attr = ' style="%s"' % ";".join(style_bits) if style_bits else ""
            # 2026-10-01（P6）：行見出し＝1列目を th（scope=row）にして太くする。
            tag = "th" if row_head and index == 0 else "td"
            scope = ' scope="row"' if tag == "th" else ""
            cell_parts.append(
                '<%s%s data-label="%s"%s%s>%s%s%s</%s>'
                % (
                    tag,
                    scope,
                    escape(head[index], quote=True),
                    ' class="%s"' % " ".join(classes) if classes else "",
                    style_attr,
                    main_html,
                    extra_html,
                    note_html,
                    tag,
                )
            )
        row_class = ' class="grp"' if row_index in group_rows and row_index > 0 else ""
        rows_html.append("<tr%s>" % row_class + "".join(cell_parts) + "</tr>")
    caption_html = (
        f"<caption>{_render_inline(caption, glossary_entries, seen_terms)}</caption>"
        if caption
        else ""
    )
    heading_html = (
        "<h3>" + _render_inline(heading, glossary_entries, seen_terms) + "</h3>"
        if heading
        else ""
    )
    legend_html = _stack_legend(stack_labels, stack_tones) if used_stack else ""
    return (
        heading_html
        + legend_html
        + '<div class="scroll"><table>'
        + caption_html
        + f"<thead><tr>{header_cells}</tr></thead>"
        + f"<tbody>{''.join(rows_html)}</tbody></table></div>"
    )


def _copy_button(raw_text: str) -> str:
    """コピー釦（⑨・formula・log・diff の共通部品）。

    中身はそのままデータ属性へ持たせる（末尾scriptの `[data-copy]` が拾う）。
    ⚠️ここに fetch／XMLHttpRequest／WebSocket／EventSource／sendBeacon を書かない
      （検品器が通信コードとして拒否する）。外部URLも書かない。
    """
    return (
        '<button type="button" class="copy-btn" data-copy="%s">コピー</button>'
        % escape(raw_text, quote=True)
    )


def _log_block(
    value: object,
    glossary_entries: Mapping[str, GlossaryEntry],
    seen_terms: set[str],
) -> str:
    """実行の記録をそのまま貼る。⚠️中身は**エスケープだけ**して飾らない。

    入れるもの＝文字列か、その一覧。`見出し：` で始まる要素は小見出しが付く。
    返るもの＝`pre` のHTML（末尾にコピー釦が付く）。改行はそのまま残る。
    """
    items = value if isinstance(value, (list, tuple)) else [value]
    blocks = []
    for item in items:
        text = _stringify(item)
        if not text.strip():
            continue
        label, separator, rest = text.partition("：")
        if separator and NEWLINE not in label:
            heading = (
                "<h3>"
                + _render_inline(label.strip(), glossary_entries, seen_terms)
                + "</h3>"
            )
            body = rest.strip(NEWLINE)
        else:
            heading = ""
            body = text
        blocks.append(
            f'{heading}<pre class="log">{escape(body)}</pre>{_copy_button(body)}'
        )
    return "".join(blocks)


def _diff_lines(value: object) -> list[str]:
    if isinstance(value, (list, tuple)):
        lines: list[str] = []
        for item in value:
            lines.extend(_stringify(item).split(NEWLINE))
        return lines
    return _stringify(value).split(NEWLINE)


def _diff_block(value: object) -> str:
    """コード差分（④）。行頭 `+` は追加・`-` は削除・それ以外は文脈として塗り分ける。

    入れるもの＝文字列（行区切り）か行の一覧。返るもの＝`pre` のHTML＋コピー釦。
    ⚠️中身は**エスケープのみ**（飾らない）。色は既存の役割色（追加=pass系・削除=fail系）
      を使い、新しい色トークンは増やさない。
    """
    lines = _diff_lines(value)
    if not any(line.strip() for line in lines):
        return ""
    rows = []
    for line in lines:
        if line.startswith("+"):
            tone = "add"
        elif line.startswith("-"):
            tone = "del"
        else:
            tone = "ctx"
        rows.append('<span class="%s">%s</span>' % (tone, escape(line)))
    raw_text = NEWLINE.join(lines)
    return (
        '<pre class="log diff">' + NEWLINE.join(rows) + "</pre>" + _copy_button(raw_text)
    )


def _summary_records(value: object) -> list[tuple[str, object]]:
    if isinstance(value, Mapping):
        nested = next(
            (
                value.get(key)
                for key in ("entries", "items", "rows")
                if isinstance(value.get(key), (list, tuple))
            ),
            None,
        )
        if nested is not None:
            value = nested
        else:
            return [(str(key), item) for key, item in value.items()]
    if isinstance(value, (list, tuple)):
        records: list[tuple[str, object]] = []
        for item in value:
            if isinstance(item, Mapping):
                records.append(
                    (
                        _stringify(item.get("label", item.get("type", ""))),
                        item.get("content", item.get("value", "")),
                    )
                )
            else:
                records.extend(_summary_records(_stringify(item)))
        return records
    records = []
    for raw_line in _stringify(value).splitlines():
        line = raw_line.strip()
        if not line:
            continue
        label, separator, copy = line.partition("：")
        records.append((label.strip() if separator else "", copy.strip() if separator else line))
    return records


def _summary_grid(
    value: object,
    glossary_entries: Mapping[str, GlossaryEntry],
    seen_terms: set[str],
) -> str:
    cards = []
    for label, copy in _summary_records(value):
        if not label:
            continue
        cards.append(
            "<div><b>"
            + _render_inline(label.upper(), glossary_entries, seen_terms)
            + "</b><span>"
            + _render_inline(copy, glossary_entries, seen_terms)
            + "</span></div>"
        )
    return '<div class="gnc">' + "".join(cards) + "</div>" if cards else ""


def _summary_note(
    value: object,
    glossary_entries: Mapping[str, GlossaryEntry],
    seen_terms: set[str],
) -> str:
    rows = []
    for label, copy in _summary_records(value)[:3]:
        label_markup = (
            f"<strong>{_render_inline(label, glossary_entries, seen_terms)}</strong> "
            if label
            else ""
        )
        rows.append(
            f'<p class="summary-line">{label_markup}'
            f"{_render_inline(copy, glossary_entries, seen_terms)}</p>"
        )
    if not rows:
        return ""
    return (
        '<div class="note summary-note" data-summary-lines="3">'
        "<h3>3行でいうと</h3>"
        + "".join(rows)
        + "</div>"
    )


def _steps_block(
    value: object,
    glossary_entries: Mapping[str, GlossaryEntry],
    seen_terms: set[str],
) -> str:
    rows = []
    for raw_line in str(value or "").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        label, separator, copy = line.partition("：")
        title = label if separator else "Step"
        body = copy.strip() if separator else line
        rows.append(
            f'<li data-tone="{_tone(title)}"><div class="body"><span class="ttl">'
            + _render_inline(title, glossary_entries, seen_terms)
            + "</span><p>"
            + _render_inline(body, glossary_entries, seen_terms)
            + "</p></div></li>"
        )
    return '<ol class="steps">' + "".join(rows) + "</ol>"


def _evidence_values(value: object) -> list[object]:
    if isinstance(value, Mapping):
        for key in ("entries", "items", "rows"):
            nested = value.get(key)
            if isinstance(nested, (list, tuple)):
                return list(nested)
        if any(key in value for key in ("type", "content", "source")):
            return [value]
        return []
    if isinstance(value, (list, tuple)):
        return list(value)
    return [line for line in _stringify(value).splitlines() if line.strip()]


def _parse_evidence_line(value: str) -> tuple[str, str, str]:
    line = value.strip()
    left, separator, source = line.partition("｜")
    if not separator and "|" in left:
        left, separator, source = left.partition("|")
    label, colon, body = left.partition("：")
    if not colon:
        label, body = "確認済み", left
    return label.strip() or "確認済み", body.strip(), source.strip() if separator else ""


def _evidence_parts(value: object) -> tuple[str, object, str]:
    if isinstance(value, Mapping):
        label = value.get("type", value.get("kind", "確認済み"))
        body = value.get("content", value.get("body", ""))
        source = value.get("source", "")
        return _stringify(label).strip() or "確認済み", body, _stringify(source).strip()
    return _parse_evidence_line(_stringify(value))


def _evidence_id(value: object, index: int) -> str:
    if isinstance(value, Mapping):
        raw_id = value.get("id", value.get("key", ""))
        if _stringify(raw_id).strip():
            return _stringify(raw_id).strip()
    return f"evidence-{index}"


def _is_numeric(value: object) -> bool:
    if isinstance(value, bool):
        return False
    if isinstance(value, (int, float)):
        return True
    return bool(
        re.fullmatch(
            r"\s*[+-]?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?(?:[%％]|件|本|個|回|行)?\s*",
            _stringify(value),
        )
    )


def _numeric_value(cell: object) -> float | None:
    """表のセルの数を取り出す（heat／bars ⑨用）。桁区切り・単位の接尾辞は許す。"""
    text = _stringify(cell).strip().replace(",", "")
    match = re.match(r"^[+-]?\d+(?:\.\d+)?", text)
    if not match:
        return None
    try:
        return float(match.group(0))
    except ValueError:
        return None


def _looks_like_path(value: str) -> bool:
    return bool(
        re.search(
            r"[\\/]|\.(?:py|md|json|html|css|js|log|txt|ps1|yaml|yml)(?:$|\s)",
            value,
            flags=re.IGNORECASE,
        )
    )


def _source_cell(
    source: str,
    glossary_entries: Mapping[str, GlossaryEntry],
    seen_terms: set[str],
) -> str:
    if not source:
        return '<td class="source" data-label="どこで確かめたか" data-source="" data-missing-source="true">未提示</td>'
    if _looks_like_path(source):
        return (
            '<td class="source" data-label="どこで確かめたか" data-source="%s">'
            '<code>%s</code></td>'
            % (
                escape(source, quote=True),
                escape(source),
            )
        )
    return (
        f'<td class="source" data-label="どこで確かめたか" data-source="{escape(source, quote=True)}">'
        f"{_render_inline(source, glossary_entries, seen_terms)}</td>"
    )


def _evidence_block(
    value: object,
    glossary_entries: Mapping[str, GlossaryEntry],
    seen_terms: set[str],
) -> str:
    classes = {
        "実測": "s-m",
        "確認済み": "s-m",
        "仮定": "s-a",
        "推奨": "s-r",
        "一次": "s-r",
        "未検証": "s-x",
        "未証明": "s-x",
        "blocker": "s-x",
    }
    rows = []
    for index, raw_entry in enumerate(_evidence_values(value), start=1):
        label, body, source = _evidence_parts(raw_entry)
        css_class = classes.get(label.lower(), classes.get(label, "s-r"))
        numeric_class = ' class="num"' if _is_numeric(body) else ""
        rows.append(
            f'<tr data-evidence="{escape(_evidence_id(raw_entry, index), quote=True)}">'
            f'<td data-label="種類"><span class="src {css_class}">'
            f'{escape(label)}</span></td>'
            f'<td data-label="内容"{numeric_class}>{_render_inline(body, glossary_entries, seen_terms)}</td>'
            + _source_cell(source, glossary_entries, seen_terms)
            + "</tr>"
        )
    table = (
        '<div class="scroll"><table><thead><tr><th>種類</th><th>内容</th>'
        '<th>どこで確かめたか</th></tr></thead><tbody>'
        + "".join(rows)
        + "</tbody></table></div>"
    )
    caption = value.get("caption") if isinstance(value, Mapping) else None
    if caption is not None and _stringify(caption).strip():
        table += _caption_block(caption, glossary_entries, seen_terms)
    return table


def _glossary_block(
    value: object,
    glossary_entries: Mapping[str, GlossaryEntry],
    seen_terms: set[str],
) -> str:
    rows = []
    for raw_line in str(value or "").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        term, separator, description = line.partition("：")
        if not separator:
            continue
        rows.append(
            f"<dt>{_render_inline(term, glossary_entries, seen_terms)}</dt><dd>"
            f"{_render_inline(description.strip(), glossary_entries, seen_terms)}"
            "</dd>"
        )
    return '<dl class="gl">' + "".join(rows) + "</dl>"


def _bullets_block(
    value: object,
    glossary_entries: Mapping[str, GlossaryEntry],
    seen_terms: set[str],
) -> str:
    """箇条書き。入れるもの＝文字列の一覧か改行区切りの文字列。返るもの＝`ul` のHTML。"""
    items = value if isinstance(value, (list, tuple)) else str(value or "").splitlines()
    rows = [
        "<li>" + _render_inline(str(item).strip(), glossary_entries, seen_terms) + "</li>"
        for item in items
        if str(item).strip()
    ]
    return f'<ul class="bullets">{"".join(rows)}</ul>' if rows else ""


def _cards_block(
    value: object,
    glossary_entries: Mapping[str, GlossaryEntry],
    seen_terms: set[str],
) -> str:
    """カード（小見出し＋本文の箱）を並べる。

    2026-08-29：参照頁は16枚のカードで判定を1件ずつ見せていた。これまでの `examples` の
    note では、見出しに色味を付けた「1件＝1判定」の見せ方ができなかった。
    入れるもの＝`{"title","text","tone","badge"}` の一覧。返るもの＝カードの並び。
    """
    items = value if isinstance(value, (list, tuple)) else [value]
    cards = []
    for item in items:
        if not isinstance(item, Mapping):
            item = {"text": _stringify(item)}
        tone = _stringify(item.get("tone", "")).lower()
        badge = _stringify(item.get("badge", ""))
        title = _stringify(item.get("title", ""))
        head = ""
        if badge or title:
            badge_html = (
                '<span class="badge b-%s">%s</span> ' % (_badge_tone(tone), escape(badge))
                if badge
                else ""
            )
            right = _stringify(item.get("right", ""))
            right_html = (
                '<span class="scores"><span class="badge b-%s">%s</span></span>'
                % (_badge_tone(_stringify(item.get("right_tone", tone))), escape(right))
                if right
                else ""
            )
            head = (
                "<h3>"
                + badge_html
                + _render_inline(title, glossary_entries, seen_terms)
                + right_html
                + "</h3>"
            )
        body = item.get("text", "")
        body_html = (
            "<p>" + _inline_with_breaks(body, glossary_entries, seen_terms) + "</p>" if body else ""
        )
        extra = ""
        if item.get("items"):
            extra += _bullets_block(item["items"], glossary_entries, seen_terms)
        objection = item.get("objection")
        if objection:
            target = _stringify(objection if isinstance(objection, str) else (title or badge))
            label = escape(target, quote=True)
            extra += (
                '<div class="obj-row"><label class="choice objection">'
                '<input type="checkbox" name="objection" data-label="%s">'
                "<span><b>これは違う</b></span></label>"
                '<input type="text" class="obj-why" data-label="%s" '
                'aria-label="%s の理由" placeholder="理由（任意）"></div>' % (label, label, label)
            )
        cards.append(
            '<div class="card"%s>%s%s%s</div>'
            % (' data-tone="%s"' % escape(tone, quote=True) if tone else "", head, body_html, extra)
        )
    return '<div class="card-stack">' + "".join(cards) + "</div>"


def _blocks(
    value: object,
    glossary_entries: Mapping[str, GlossaryEntry],
    seen_terms: set[str],
    *,
    heading_key: str = "heading",
) -> str:
    """小見出し付きの塊を、いくつでも並べる。

    2026-08-29：参照頁は1つの節の中に**小見出し31個・表14個**を並べていた。
    レンダラーは component ごとに大見出し1つと本文1つしか出せず、
    「同じ節に表を2つ置く」ことすらできなかった。
    ∴どの component でも、一覧を渡せば塊をいくつでも並べられるようにする。

    入れるもの＝`{"heading","text","items","table","log","diagram","cards"}` の一覧。
    返るもの＝それらを順に並べたHTML。⚠️文字列を渡したときの動きは変えない。
    """
    items = value if isinstance(value, (list, tuple)) else [value]
    parts = []
    for item in items:
        if not isinstance(item, Mapping):
            parts.append(
                '<p class="body-copy">'
                + _render_inline(_stringify(item), glossary_entries, seen_terms)
                + "</p>"
            )
            continue
        heading = _stringify(item.get(heading_key, ""))
        if heading:
            parts.append(
                "<h3>" + _render_inline(heading, glossary_entries, seen_terms) + "</h3>"
            )
        parts.append(_details_body(item, glossary_entries, seen_terms))
    return "".join(parts)


def _ordered_block(
    value: object,
    glossary_entries: Mapping[str, GlossaryEntry],
    seen_terms: set[str],
) -> str:
    """番号付きの並び。手順でなく「順番のある一覧」に使う。"""
    items = value if isinstance(value, (list, tuple)) else str(value or "").splitlines()
    rows = [
        "<li>" + _inline_with_breaks(str(item).strip(), glossary_entries, seen_terms) + "</li>"
        for item in items
        if str(item).strip()
    ]
    return f'<ol class="numbered">{"".join(rows)}</ol>' if rows else ""


def _note_block(
    value: object,
    glossary_entries: Mapping[str, GlossaryEntry],
    seen_terms: set[str],
) -> str:
    """囲み。⚠️色味は意味に固定する＝確認済みは good、注意は warn、失敗は bad。

    入れるもの＝`{"tone","title","text"}` かその一覧。返るもの＝囲みのHTML。
    """
    items = value if isinstance(value, (list, tuple)) else [value]
    blocks = []
    for item in items:
        if not isinstance(item, Mapping):
            item = {"text": _stringify(item)}
        tone = _stringify(item.get("tone", "")).lower()
        css = "note" + ((" " + tone) if tone in {"good", "warn", "bad"} else "")
        title = _stringify(item.get("title", ""))
        head = (
            "<h3>" + _render_inline(title, glossary_entries, seen_terms) + "</h3>"
            if title
            else ""
        )
        body = _inline_with_breaks(item.get("text", ""), glossary_entries, seen_terms)
        blocks.append('<div class="%s">%s<p>%s</p></div>' % (css, head, body))
    return "".join(blocks)


def _quote_block(
    value: object,
    glossary_entries: Mapping[str, GlossaryEntry],
    seen_terms: set[str],
) -> str:
    """引用。原文をそのまま見せたいときに使う。

    ⑦2026-09-08：`{"original","ja","source"}` の辞書なら、原文と訳文を上下に
    同じ字の大きさで並べ、出所を小さく添える。文字列なら従来どおり。
    """
    if isinstance(value, Mapping):
        original = _stringify(value.get("original", ""))
        translation = _stringify(value.get("ja", ""))
        source = _stringify(value.get("source", ""))
        body = ""
        if original:
            body += (
                '<p class="q-original">'
                + _inline_with_breaks(original, glossary_entries, seen_terms)
                + "</p>"
            )
        if translation:
            body += (
                '<p class="q-ja">'
                + _inline_with_breaks(translation, glossary_entries, seen_terms)
                + "</p>"
            )
        if source:
            body += (
                '<footer class="q-source">'
                + _render_inline(source, glossary_entries, seen_terms)
                + "</footer>"
            )
        return "<blockquote>" + body + "</blockquote>"
    return (
        "<blockquote>"
        + _inline_with_breaks(value, glossary_entries, seen_terms)
        + "</blockquote>"
    )


def _pairs_block(
    value: object,
    glossary_entries: Mapping[str, GlossaryEntry],
    seen_terms: set[str],
) -> str:
    """語と説明の対。用語集以外の場所でも使える定義リスト。"""
    items = value if isinstance(value, (list, tuple)) else str(value or "").splitlines()
    rows = []
    for item in items:
        if isinstance(item, (list, tuple)) and len(item) >= 2:
            term, body = _stringify(item[0]), _stringify(item[1])
        else:
            term, separator, body = _stringify(item).partition("：")
            if not separator:
                continue
        rows.append(
            "<dt>" + _render_inline(term.strip(), glossary_entries, seen_terms) + "</dt>"
            + "<dd>" + _inline_with_breaks(body.strip(), glossary_entries, seen_terms) + "</dd>"
        )
    return f'<dl class="pairs">{"".join(rows)}</dl>' if rows else ""

def _toc_block(entries: Sequence[tuple[str, str, str]]) -> str:
    """節の見出しから目次を組む。返るもの＝飛び先付きの並び（節が無ければ空文字）。

    入れるもの＝`(節のid, 番号, 見出し)` の一覧。⚠️見出しは**節と同じ文字**を使う
    （手で書かせない）＝節を足したときに目次だけが古くなる事故を防ぐ。
    """
    rows = []
    for anchor, num, label in entries:
        num_html = '<span class="toc-no">' + escape(num) + "</span>" if num else ""
        rows.append(
            '<li><a href="#%s">%s%s</a></li>'
            % (escape(anchor, quote=True), num_html, escape(label))
        )
    return '<nav class="toc"><ol>' + "".join(rows) + "</ol></nav>" if rows else ""


def _rail_glossary_block(
    glossary_entries: Mapping[str, GlossaryEntry],
    seen_terms: set[str],
    counts: Mapping[str, int],
) -> str:
    """③ 側柱の用語リスト。本文で**2回以上**現れた用語ホバーの語だけを、

    正本の説明（glossary_entries）で「語：説明」の定義リストにする。
    1語も無ければ空文字を返す＝呼び側はこれを見て塊ごと出さない。
    """
    rows = []
    for key in sorted(seen_terms, key=lambda item: item.strip("`").strip()):
        if counts.get(key, 0) < 2:
            continue
        entry = glossary_entries.get(key)
        if entry is None:
            continue
        display = key.strip("`").strip()
        if not display:
            continue
        rows.append(
            "<dt>" + escape(display) + "</dt><dd>"
            + escape(_stringify(entry.description)) + "</dd>"
        )
    return '<dl class="gl">' + "".join(rows) + "</dl>" if rows else ""


def _rail_block(
    value: object,
    glossary_entries: Mapping[str, GlossaryEntry],
    seen_terms: set[str],
    toc_entries: Sequence[tuple[str, str, str]] = (),
    glossary_counts: Mapping[str, int] | None = None,
) -> str:
    """頁の脇に立てる側柱を組む（頁全体の2段組み）。

    入れるもの＝塊と同じ書き方（`heading` / `text` / `items` / `table` / `diagram` …）の一覧。
    返るもの＝`<aside class="rail">` のHTML。渡さなければ空文字＝1段組みのまま。

    ⚠️**側柱は節ではない**（`data-component` を持たない）。節を横に並べると読む順と
      部品の目印の順がずれるので、横に置いてよいのは「節ではない添え物」だけにしている。
    ⚠️狭い画面では本文の**後ろ**に回る＝画面の順もHTMLの順も変わらない。

    `{"heading": "目次", "toc": true}` を入れると、節の見出しから目次を自動で組む。
    `{"heading": "用語", "glossary": true}` を入れると、本文で2回以上使われた用語
    ホバーの語だけを正本の説明で並べる（③・2026-09-08）。⚠️**側柱は本文の後に組む**
    必要がある＝`seen_terms`／`glossary_counts` は呼び側（render_components）が
    本文の節を組み終えてから数える。1語も無ければ、この塊は見出しごと出さない。
    """
    counts = glossary_counts or {}
    items = value if isinstance(value, (list, tuple)) else [value]
    parts = []
    for item in items:
        if not isinstance(item, Mapping):
            item = {"text": _stringify(item)}
        if item.get("glossary"):
            glossary_body = _rail_glossary_block(glossary_entries, seen_terms, counts)
            if not glossary_body:
                continue
            heading = _stringify(item.get("heading", ""))
            if heading:
                parts.append(
                    '<p class="rail-head">'
                    + _render_inline(heading, glossary_entries, seen_terms)
                    + "</p>"
                )
            parts.append(glossary_body)
            continue
        heading = _stringify(item.get("heading", ""))
        if heading:
            parts.append(
                '<p class="rail-head">'
                + _render_inline(heading, glossary_entries, seen_terms)
                + "</p>"
            )
        if item.get("toc"):
            parts.append(_toc_block(toc_entries))
        parts.append(_details_body(item, glossary_entries, seen_terms))
    body = "".join(part for part in parts if part)
    return '<aside class="rail">' + body + "</aside>" if body else ""


def _columns_block(
    value: object,
    glossary_entries: Mapping[str, GlossaryEntry],
    seen_terms: set[str],
) -> str:
    """塊を横に並べる。2段組み・3段組みが書ける。

    入れるもの＝列の一覧。各列は塊と同じ書き方（`heading` / `text` / `table` / `items` …）。
    返るもの＝横並びのHTML。⚠️**狭い画面では自動で縦に積む**（横スクロールを出さない）。
    """
    items = value if isinstance(value, (list, tuple)) else [value]
    columns = []
    for item in items:
        if not isinstance(item, Mapping):
            item = {"text": _stringify(item)}
        heading = _stringify(item.get("heading", ""))
        head = (
            "<h3>" + _render_inline(heading, glossary_entries, seen_terms) + "</h3>"
            if heading
            else ""
        )
        columns.append(
            '<div class="col">'
            + head
            + _details_body(item, glossary_entries, seen_terms)
            + "</div>"
        )
    if not columns:
        return ""
    count = min(len(columns), 4)
    return '<div class="cols" data-cols="%d">%s</div>' % (count, "".join(columns))


def _tiles_block(
    value: object,
    glossary_entries: Mapping[str, GlossaryEntry],
    seen_terms: set[str],
) -> str:
    """小さい箱を敷き詰める。画面幅に応じて折り返す。

    入れるもの＝`{"title","text","tone"}` の一覧。返るもの＝タイルの並び。
    ⚠️数が多く1つ1つが短いものに使う。長い本文はカードのほうが読みやすい。
    """
    items = value if isinstance(value, (list, tuple)) else [value]
    tiles = []
    for item in items:
        if not isinstance(item, Mapping):
            item = {"title": _stringify(item)}
        tone = _stringify(item.get("tone", "")).lower()
        title = _stringify(item.get("title", ""))
        text = _stringify(item.get("text", ""))
        tiles.append(
            '<div class="tile"%s><b>%s</b>%s</div>'
            % (
                ' data-tone="%s"' % escape(tone, quote=True) if tone else "",
                _render_inline(title, glossary_entries, seen_terms),
                "<span>" + _inline_with_breaks(text, glossary_entries, seen_terms) + "</span>"
                if text
                else "",
            )
        )
    return '<div class="tiles">' + "".join(tiles) + "</div>" if tiles else ""


def _stats_block(
    value: object,
    glossary_entries: Mapping[str, GlossaryEntry],
    seen_terms: set[str],
) -> str:
    """大きい数字のタイル（2026-10-01・ユーザー承認の P7）。

    入れるもの＝`{"value","unit","label","text","tone"}` の一覧。返るもの＝大きい等幅の数字
    （単位は小さく）・名札・補足の並び。⚠️頁の頭の「主要な数字」に使う。多用しない。
    """
    items = value if isinstance(value, (list, tuple)) else [value]
    tiles = []
    for item in items:
        if not isinstance(item, Mapping):
            item = {"value": _stringify(item)}
        tone = _badge_tone(_stringify(item.get("tone", "")))
        number = _stringify(item.get("value", ""))
        unit = _stringify(item.get("unit", ""))
        label = _stringify(item.get("label", ""))
        text = _stringify(item.get("text", ""))
        tiles.append(
            '<div class="stat" data-tone="%s"><div class="stat-num">%s%s</div>%s%s</div>'
            % (
                escape(tone, quote=True),
                escape(number),
                "<small>" + escape(unit) + "</small>" if unit else "",
                '<div class="stat-label">' + _render_inline(label, glossary_entries, seen_terms) + "</div>"
                if label
                else "",
                '<p class="stat-sub">' + _inline_with_breaks(text, glossary_entries, seen_terms) + "</p>"
                if text
                else "",
            )
        )
    return '<div class="stats">' + "".join(tiles) + "</div>" if tiles else ""


def _hsteps_block(
    value: object,
    glossary_entries: Mapping[str, GlossaryEntry],
    seen_terms: set[str],
) -> str:
    """横に並ぶ番号つきの手順（2026-10-01・ユーザー承認の P9）。狭い画面では折り返す。

    入れるもの＝`{"title","text"}` か「題：本文」の文字列の一覧。
    """
    items = value if isinstance(value, (list, tuple)) else str(value or "").splitlines()
    rows = []
    for item in items:
        if isinstance(item, Mapping):
            title = _stringify(item.get("title", ""))
            text = _stringify(item.get("text", ""))
        else:
            line = _stringify(item).strip()
            if not line:
                continue
            title, separator, text = line.partition("：")
            if not separator:
                title, text = line, ""
        rows.append(
            "<li><b>" + _render_inline(title, glossary_entries, seen_terms) + "</b>"
            + ("<span>" + _inline_with_breaks(text, glossary_entries, seen_terms) + "</span>" if text else "")
            + "</li>"
        )
    return '<ol class="hsteps">' + "".join(rows) + "</ol>" if rows else ""


def _chips_block(
    value: object,
    glossary_entries: Mapping[str, GlossaryEntry],
    seen_terms: set[str],
) -> str:
    """短い語の札の束（2026-10-01・ユーザー承認の P9）。

    入れるもの＝語の一覧か、`{"title","items","note"}` の群の一覧。群の数は自動で数える。
    """
    groups = value if isinstance(value, (list, tuple)) else [value]
    if groups and not any(isinstance(g, Mapping) for g in groups):
        groups = [{"items": list(groups)}]
    blocks = []
    for group in groups:
        if not isinstance(group, Mapping):
            continue
        words = [
            _stringify(w).strip() for w in (group.get("items") or []) if _stringify(w).strip()
        ]
        if not words:
            continue
        title = _stringify(group.get("title", ""))
        note = _stringify(group.get("note", ""))
        head = ""
        if title:
            head = (
                '<h4 class="chip-head">' + _render_inline(title, glossary_entries, seen_terms)
                + '<span class="cnt">%d</span>' % len(words)
                + ('<span class="cnt-note">' + escape(note) + "</span>" if note else "")
                + "</h4>"
            )
        blocks.append(
            '<div class="chip-group">' + head + '<ul class="chips">'
            + "".join("<li>" + _render_inline(w, glossary_entries, seen_terms) + "</li>" for w in words)
            + "</ul></div>"
        )
    return '<div class="chip-groups">' + "".join(blocks) + "</div>" if blocks else ""


def _ensure_xlink_namespace(text: str) -> str:
    """`xlink:` を使うのに宣言が無いSVGへ、解析のためだけに宣言を補う。

    ⚠️`sanitize_svg` は ElementTree で解析し直すので、ここで足した宣言は
    出力には一切残らない（xmlns* は ET の名前空間解決で attrib に現れない）。
    """
    if "xlink:" in text and "xmlns:xlink" not in text:
        idx = text.find("<svg")
        if idx >= 0:
            insert_at = idx + len("<svg")
            return text[:insert_at] + ' xmlns:xlink="http://www.w3.org/1999/xlink"' + text[insert_at:]
    return text


def _svg_block(
    value: object,
    glossary_entries: Mapping[str, GlossaryEntry],
    seen_terms: set[str],
) -> str:
    """①手書きSVGの取り込み。`visual/svg_import.py:sanitize_svg` が許可リストで組み直す。

    入れるもの＝SVG文字列、または `{"svg":…, "num":…, "source":…, "caption":…}`。
    ⚠️外した要素・属性（`dropped`）と解析の注意（`warnings`）は黙って消さず、枠の下に列挙する。
    """
    if isinstance(value, Mapping):
        raw_svg = _stringify(value.get("svg", ""))
        num = _stringify(value.get("num", ""))
        source = _stringify(value.get("source", ""))
        caption = _stringify(value.get("caption", ""))
    else:
        raw_svg, num, source, caption = _stringify(value), "", "", ""
    if not raw_svg.strip():
        return ""
    if sanitize_svg is None:
        return '<div class="note warn"><p>SVGの取り込みは今使えない。</p></div>'
    result = sanitize_svg(_ensure_xlink_namespace(raw_svg))
    if not result.svg:
        note = "SVGを取り込めなかった" + (
            "：" + "、".join(result.warnings) if result.warnings else ""
        )
        return '<div class="note warn"><p>' + escape(note) + "</p></div>"
    caption_html = _figure_caption_html(num, caption, source, glossary_entries, seen_terms)
    extra: list[str] = []
    if result.dropped:
        extra.append("取り込み時に外したもの：" + "、".join(result.dropped))
    extra.extend(result.warnings)
    extra_html = (
        '<ul class="dia-warn">' + "".join("<li>" + escape(w) + "</li>" for w in extra) + "</ul>"
        if extra
        else ""
    )
    return '<div class="dia-wrap">' + result.svg + "</div>" + caption_html + extra_html


def _add_zoom_attribute(figure_html: str) -> str:
    marker = '<div class="img-frame"'
    idx = figure_html.find(marker)
    if idx < 0:
        return figure_html
    insert_at = idx + len(marker)
    return figure_html[:insert_at] + ' data-zoom="1"' + figure_html[insert_at:]


def _image_block(
    value: object,
    glossary_entries: Mapping[str, GlossaryEntry],
    seen_terms: set[str],
) -> str:
    """②スライド／任意の画像を data: URI で埋め込む（`visual/images.py:embed_image`）。

    入れるもの＝`{"path"|"deck"+"slide","crop","marks","caption","source","alt","width","num"}`。
    実測の1行（`source_line`）は評価証跡へ積む＝evidence 節があればそこへ、無ければ図の下に出す
    （B2）。拡大表示（B4）は `data-zoom` を付け、末尾scriptの重ね表示に任せる。
    """
    if embed_image is None:
        return '<div class="note warn"><p>画像の組み込みは今使えない。</p></div>'
    spec = value if isinstance(value, Mapping) else {}
    if not spec:
        return ""
    try:
        result = embed_image(spec)
    except Exception as exc:  # 契約は例外を投げない実装だが、ここでも一段守る。
        return '<div class="note warn"><p>画像を組み込めなかった：' + escape(str(exc)) + "</p></div>"
    if not result.html:
        note = "画像を組み込めなかった" + (
            "：" + "、".join(result.warnings) if result.warnings else ""
        )
        return '<div class="note warn"><p>' + escape(note) + "</p></div>"
    html = _add_zoom_attribute(result.html)
    if result.source_line:
        _IMAGE_EVIDENCE_LINES.append(result.source_line)
        if not _PAGE_HAS_EVIDENCE_SECTION:
            html += '<p class="cap img-src">' + escape(result.source_line) + "</p>"
    return html


# 頁の文字に http:// や file:// が残ると、検品（receipts.py の外部 URL の判定）が落とす。
_SCHEME = re.compile(r"(?i)\b(?:https?|file):/{2,3}")


def _screenshot_block(
    value: object,
    glossary_entries: Mapping[str, GlossaryEntry],
    seen_terms: set[str],
) -> str:
    """画面を撮って貼る（2026-10-01・ユーザー承認の P2）。

    入れるもの＝`{"target"（手元のファイルか localhost などの URL）,"viewport":[幅,高さ],
    "selector","full_page","wait_ms","crop","marks","caption","source","alt","width","num"}`。
    撮影は `visual/screenshots.py`、貼るのは image と同じ `embed_image`（縮小・圧縮）。
    根拠欄には「撮った先・幅・撮った時刻・ハッシュ」の1行が自動で足される。
    ⚠️外部の頁は撮らない（撮影係が断る）＝情報の持ち出しとログイン中の画面の写り込みを防ぐ。
    """
    import datetime
    import os
    import tempfile

    if capture_screenshot is None or embed_image is None:
        return '<div class="note warn"><p>画面の撮影は今使えない。</p></div>'
    spec = value if isinstance(value, Mapping) else {"target": _stringify(value)}
    shot = capture_screenshot(spec)
    if shot.png is None:
        return (
            '<div class="note warn"><p>画面を撮れなかった：'
            + escape(_SCHEME.sub("", "、".join(shot.warnings)) or "理由不明")
            + "</p></div>"
        )
    handle, temp_path = tempfile.mkstemp(prefix="shot-embed-", suffix=".png")
    try:
        with os.fdopen(handle, "wb") as out:
            out.write(shot.png)
        embed_spec = {
            key: spec[key]
            for key in ("crop", "marks", "caption", "alt", "width", "num")
            if key in spec
        }
        embed_spec["path"] = temp_path
        embed_spec["source"] = spec.get("source") or ("画面の写真：" + shot.label)
        result = embed_image(embed_spec)
    finally:
        try:
            os.remove(temp_path)
        except OSError:
            pass
    if not result.html:
        return (
            '<div class="note warn"><p>撮った画面を貼れなかった：'
            + escape(_SCHEME.sub("", "、".join(result.warnings)) or "理由不明")
            + "</p></div>"
        )
    html = _add_zoom_attribute(result.html)
    stamp = datetime.datetime.now().astimezone().strftime("%Y-%m-%d %H:%M")
    line = "実測：画面の写真＝%s・%s｜%s（撮影 %s）" % (
        shot.label, result.sha256[:12], shot.place or shot.label, stamp
    )
    _IMAGE_EVIDENCE_LINES.append(line)
    if not _PAGE_HAS_EVIDENCE_SECTION:
        html += '<p class="cap img-src">' + escape(line) + "</p>"
    return html


def _figure_svg_block(
    renderer,
    value: object,
    glossary_entries: Mapping[str, GlossaryEntry],
    seen_terms: set[str],
) -> str:
    """③時間軸・四象限・集合・流れ・採点格子（`visual/visuals.py`）の共通の組み方。"""
    if renderer is None:
        return '<div class="note warn"><p>この図は今使えない。</p></div>'
    spec = value if isinstance(value, Mapping) else {}
    svg = renderer(spec)
    if not isinstance(svg, str) or not svg.strip().startswith("<svg"):
        return ""
    num = _stringify(spec.get("num", "")) if isinstance(spec, Mapping) else ""
    source = _stringify(spec.get("source", "")) if isinstance(spec, Mapping) else ""
    caption = _stringify(spec.get("caption", "")) if isinstance(spec, Mapping) else ""
    caption_html = _figure_caption_html(num, caption, source, glossary_entries, seen_terms)
    # 2026-09-10（撮影で確認）：列幅いっぱいに縮めると 960 幅の図で文字が約9pxになった。
    # viewBox の幅を基準に置き、縮みは1割まで。それより狭い画面は .dia-wrap の横スクロールに任せる。
    vb = re.search(r'viewBox="\s*[-\d.]+\s+[-\d.]+\s+([\d.]+)\s+([\d.]+)', svg)
    if vb:
        try:
            vb_w = float(vb.group(1))
            style = 'style="width:min(100%%,%dpx);min-width:%dpx"' % (round(vb_w), round(vb_w * 0.9))
            close = svg.find(">")
            if close > 0:
                svg = svg[:close] + " " + style + svg[close:]
        except ValueError:
            pass
    return '<div class="dia-wrap">' + svg + "</div>" + caption_html


def _render_compare_side(
    spec: object,
    glossary_entries: Mapping[str, GlossaryEntry],
    seen_terms: set[str],
) -> str:
    if spec is None:
        return ""
    if isinstance(spec, Mapping):
        return _details_body(spec, glossary_entries, seen_terms)
    return '<p class="body-copy">' + _render_inline(spec, glossary_entries, seen_terms) + "</p>"


def _compare_block(
    value: object,
    glossary_entries: Mapping[str, GlossaryEntry],
    seen_terms: set[str],
) -> str:
    """④前後切り替え。入れるもの＝`{"before":…, "after":…, "labels":["前","後"]}`。

    `before`/`after` は塊と同じ書き方（文字列か `{"text","table",…}`）で受ける。
    """
    if not isinstance(value, Mapping):
        return ""
    before_html = _render_compare_side(value.get("before"), glossary_entries, seen_terms)
    after_html = _render_compare_side(value.get("after"), glossary_entries, seen_terms)
    labels = value.get("labels")
    labels = tuple(labels) if isinstance(labels, (list, tuple)) and len(labels) >= 2 else ("前", "後")
    if compare_html is None:
        return before_html + after_html
    return compare_html(before_html, after_html, labels)


def _callouts_block(
    value: object,
    glossary_entries: Mapping[str, GlossaryEntry],
    seen_terms: set[str],
) -> str:
    """⑤番号の吹き出し一覧。入れるもの＝`[{"n":1,"text":"…","tone":"good"}]`。"""
    items = value if isinstance(value, (list, tuple)) else [value]
    normalized = []
    for item in items:
        if isinstance(item, Mapping):
            normalized.append(
                {"n": item.get("n", 0), "text": _stringify(item.get("text", "")), "tone": item.get("tone")}
            )
    if callout_legend_html is None:
        return _bullets_block(
            ["%s：%s" % (_stringify(entry["n"]), entry["text"]) for entry in normalized],
            glossary_entries,
            seen_terms,
        )
    return callout_legend_html(normalized)


def _diagram_text_block(
    value: object,
    glossary_entries: Mapping[str, GlossaryEntry],
    seen_terms: set[str],
) -> str:
    """⑥1行記法（`visual/diagram_dsl.py:parse_diagram_text`）から図を組む。"""
    text = _stringify(value)
    if not text.strip():
        return ""
    if parse_diagram_text is None:
        return _log_block(text, glossary_entries, seen_terms)
    parsed = parse_diagram_text(text)
    spec = {"nodes": parsed.get("nodes", []), "edges": parsed.get("edges", [])}
    html = _diagram_block(spec, glossary_entries, seen_terms)
    warnings = parsed.get("warnings") or []
    if warnings:
        html += (
            '<ul class="dia-warn">'
            + "".join("<li>" + escape(w) + "</li>" for w in warnings)
            + "</ul>"
        )
    return html


def _details_body(
    item: Mapping[str, object],
    glossary_entries: Mapping[str, GlossaryEntry],
    seen_terms: set[str],
) -> str:
    """折りたたみ1つの中身を組む。表・ログ・箇条書き・本文を同時に入れられる。

    2026-08-29（ユーザー裁定 P4）：⚠️これまで中身は**1行の文字列だけ**で、
    表も箇条書きもログも入れられなかった。長い根拠を畳む場所なのに、
    畳めるのが1行しかないという食い違いがあった。
    """
    parts = []
    text = item.get("text", item.get("body", ""))
    if text:
        parts.append(
            '<div class="in">'
            + _render_inline(text, glossary_entries, seen_terms)
            + "</div>"
        )
    if item.get("items"):
        parts.append(_bullets_block(item["items"], glossary_entries, seen_terms))
    if item.get("cards"):
        parts.append(_cards_block(item["cards"], glossary_entries, seen_terms))
    if item.get("tiles"):
        parts.append(_tiles_block(item["tiles"], glossary_entries, seen_terms))
    # 2026-10-01（ユーザー承認の P7・P9）：大きい数字・横並びの手順・語の札の束。
    if item.get("stats"):
        parts.append(_stats_block(item["stats"], glossary_entries, seen_terms))
    if item.get("steps"):
        parts.append(_hsteps_block(item["steps"], glossary_entries, seen_terms))
    if item.get("chips"):
        parts.append(_chips_block(item["chips"], glossary_entries, seen_terms))
    if item.get("columns"):
        parts.append(_columns_block(item["columns"], glossary_entries, seen_terms))
    if item.get("ordered"):
        parts.append(_ordered_block(item["ordered"], glossary_entries, seen_terms))
    if item.get("pairs"):
        parts.append(_pairs_block(item["pairs"], glossary_entries, seen_terms))
    if item.get("quote"):
        parts.append(_quote_block(item["quote"], glossary_entries, seen_terms))
    if item.get("note"):
        parts.append(_note_block(item["note"], glossary_entries, seen_terms))
    if item.get("caption"):
        parts.append(
            '<p class="cap">'
            + _render_inline(item["caption"], glossary_entries, seen_terms)
            + "</p>"
        )
    if item.get("divider"):
        parts.append("<hr>")
    if item.get("diagram"):
        parts.append(_diagram_block(item["diagram"], glossary_entries, seen_terms))
    if item.get("chart"):
        parts.append(_chart_block(item["chart"], glossary_entries, seen_terms))
    if item.get("table"):
        parts.append(_table_block(item["table"], glossary_entries, seen_terms))
    if item.get("log"):
        parts.append(_log_block(item["log"], glossary_entries, seen_terms))
    if item.get("diff"):
        parts.append(_diff_block(item["diff"]))
    if item.get("formula"):
        parts.append(_formula_block(item["formula"], glossary_entries, seen_terms))
    if item.get("svg"):
        parts.append(_svg_block(item["svg"], glossary_entries, seen_terms))
    if item.get("image"):
        parts.append(_image_block(item["image"], glossary_entries, seen_terms))
    if item.get("screenshot"):
        parts.append(_screenshot_block(item["screenshot"], glossary_entries, seen_terms))
    if item.get("timeline"):
        parts.append(_figure_svg_block(timeline_svg, item["timeline"], glossary_entries, seen_terms))
    if item.get("quadrant"):
        parts.append(_figure_svg_block(quadrant_svg, item["quadrant"], glossary_entries, seen_terms))
    if item.get("venn"):
        parts.append(_figure_svg_block(venn_svg, item["venn"], glossary_entries, seen_terms))
    if item.get("flow"):
        parts.append(_figure_svg_block(flow_svg, item["flow"], glossary_entries, seen_terms))
    if item.get("score"):
        parts.append(_figure_svg_block(score_grid_svg, item["score"], glossary_entries, seen_terms))
    if item.get("compare"):
        parts.append(_compare_block(item["compare"], glossary_entries, seen_terms))
    if item.get("callouts"):
        parts.append(_callouts_block(item["callouts"], glossary_entries, seen_terms))
    if item.get("diagram_text"):
        parts.append(_diagram_text_block(item["diagram_text"], glossary_entries, seen_terms))
    return "".join(parts)


def _details_block(
    value: object,
    glossary_entries: Mapping[str, GlossaryEntry],
    seen_terms: set[str],
) -> str:
    if isinstance(value, Mapping):
        value = [value]
    if isinstance(value, (list, tuple)):
        rows = []
        for item in value:
            if not isinstance(item, Mapping):
                item = {"summary": "詳細", "text": _stringify(item)}
            summary = _stringify(item.get("summary", "詳細"))
            rows.append(
                "<details><summary>"
                + _render_inline(summary, glossary_entries, seen_terms)
                + "</summary>"
                + _details_body(item, glossary_entries, seen_terms)
                + "</details>"
            )
        return "".join(rows)
    rows = []
    for raw_line in str(value or "").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        label, separator, copy = line.partition("：")
        summary = label if separator else "詳細"
        body = copy.strip() if separator else line
        rows.append(
            "<details><summary>"
            # ⚠️見出しも用語ホバーの対象にする（2026-08-29 P3）。以前は escape するだけで、
            #   見出しに置いた用語が「未包装」と判定され、頁が落ちる原因になっていた。
            + _render_inline(summary, glossary_entries, seen_terms)
            + "</summary><div class=\"in\">"
            + _render_inline(body, glossary_entries, seen_terms)
            + "</div></details>"
        )
    return "".join(rows)


def _example_tone(label: str) -> str:
    normalized = label.strip().lower()
    if any(marker in normalized for marker in ("反例", "違う")):
        return "bad"
    if any(marker in normalized for marker in ("注意", "警告", "例外", "warning")):
        return "warn"
    if any(
        marker in normalized
        for marker in ("確認済み", "成功", "ok", "pass", "成功例")
    ):
        return "good"
    return ""


def _caption_block(
    value: object,
    glossary_entries: Mapping[str, GlossaryEntry],
    seen_terms: set[str],
) -> str:
    if isinstance(value, Mapping):
        value = value.get("content", value.get("text", ""))
    return f'<p class="cap">{_render_inline(value, glossary_entries, seen_terms)}</p>'


def _examples_block(
    value: object,
    glossary_entries: Mapping[str, GlossaryEntry],
    seen_terms: set[str],
) -> str:
    rows = []
    for raw_line in str(value or "").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        label, separator, copy = line.partition("：")
        title = label if separator else "例"
        body = copy.strip() if separator else line
        tone = _example_tone(title)
        note_class = "note" + (f" {tone}" if tone else "")
        rows.append(
            f'<div class="{note_class}"><div class="ex"><b>'
            + _render_inline(title, glossary_entries, seen_terms)
            + '。</b> '
            + _render_inline(body, glossary_entries, seen_terms)
            + "</div></div>"
        )
    return "".join(rows)


def _text_block(
    value: object,
    component: str,
    glossary_entries: Mapping[str, GlossaryEntry],
    seen_terms: set[str],
) -> str:
    # 2026-08-29：**辞書の一覧**で渡されたら「小見出し付きの塊」として並べる。
    # ⚠️合図を「辞書かどうか」にしているのは、文字列の一覧（根拠の行やログ）を
    #   これまでどおり扱うため。ここを「一覧かどうか」にすると既存の書き方が壊れる。
    if (
        component not in {"evidence", "log", "details", "table", "decision"}
        and isinstance(value, (list, tuple))
        and any(isinstance(item, Mapping) for item in value)
    ):
        return _blocks(value, glossary_entries, seen_terms)
    if component == "visual":
        # 辞書で渡されたら矢印付きの図として組む。文字列ならこれまでどおり縦積み。
        # 2026-09-10：`nodes`/`bands` の無い辞書（svg/image/timeline…）は塊として扱う
        #   （でないと "visual" コンポーネントの直下では新しい鍵が黙って消えていた）。
        if isinstance(value, Mapping):
            if "nodes" in value or "bands" in value:
                return _diagram_block(value, glossary_entries, seen_terms)
            return _details_body(value, glossary_entries, seen_terms)
        return _visual_block(value, glossary_entries, seen_terms)
    if component == "walkthrough":
        return _steps_block(value, glossary_entries, seen_terms)
    if component == "evidence":
        return _evidence_block(value, glossary_entries, seen_terms)
    if component == "glossary":
        return _glossary_block(value, glossary_entries, seen_terms)
    if component == "details":
        return _details_block(value, glossary_entries, seen_terms)
    if component == "examples":
        return _examples_block(value, glossary_entries, seen_terms)
    if component == "caption":
        return _caption_block(value, glossary_entries, seen_terms)
    if component == "table":
        return _table_block(value, glossary_entries, seen_terms)
    if component == "diagram":
        return _diagram_block(value, glossary_entries, seen_terms)
    if component == "log":
        return _log_block(value, glossary_entries, seen_terms)
    if component in LABELED_COMPONENTS:
        return _labeled_block(value, glossary_entries, seen_terms)
    text = _render_inline(value, glossary_entries, seen_terms).replace("\n", "<br>")
    css_class = "lead-copy" if component == "overview" else "body-copy"
    return f'<p class="{css_class}">{text}</p>'


def _truthy(value: object) -> bool:
    if isinstance(value, str):
        return value.strip().lower() in {"true", "1", "yes", "on", "推奨"}
    return bool(value)


def _decision_parts(value: object) -> tuple[str, bool]:
    if isinstance(value, Mapping):
        label = value.get("label", value.get("value", ""))
        return _stringify(label), _truthy(value.get("recommended", False))
    return _stringify(value), False


def _choice_input(
    kind: str,
    group: str,
    label_text: str,
    *,
    why: str = "",
    badge: str = "",
    tone: str = "",
    recommended: bool = False,
    glossary_entries: Mapping[str, GlossaryEntry] | None = None,
    seen_terms: set[str] | None = None,
) -> str:
    """選択肢を1つ組む。⚠️**理由（why）を必ず置けるようにする**のがこの関数の要点。

    2026-08-29：これまでは1行のラベルだけで、なぜその案なのか・何を失うのかを
    書けなかった。参照頁は選択肢ごとに理由を添えており、そこが密度の差の主因だった。
    """
    entries = glossary_entries or {}
    seen = seen_terms if seen_terms is not None else set()
    label = escape(label_text, quote=True)
    rec = ' data-rec="1"' if recommended else ""
    badge_html = (
        '<span class="badge b-%s%s">%s</span> '
        % (_badge_tone(tone or "good"), " recommendation" if recommended else "", escape(badge))
        if badge
        else ""
    )
    why_html = (
        '<span class="why">' + _inline_with_breaks(why, entries, seen) + "</span>"
        if why
        else ""
    )
    return (
        '<label class="choice"><input type="%s" name="%s" data-req="1" data-label="%s"%s>'
        "<span>%s%s%s</span></label>"
        % (
            kind,
            escape(group, quote=True),
            label,
            rec,
            badge_html,
            _render_inline(label_text, entries, seen),
            why_html,
        )
    )


def _scale_row(
    item: Mapping[str, object],
    group: str,
    glossary_entries: Mapping[str, GlossaryEntry],
    seen_terms: set[str],
) -> str:
    """1件の判定に、見出し・印・説明・段階の選択肢を並べる。

    2026-08-29：参照頁は判定1件ごとに「採用／割引採用／軽視／棄却」の4択を置いていた。
    ○×では表せない「どれくらい効くか」を人に裁定させる形である。
    """
    title = _stringify(item.get("title", ""))
    badge = _stringify(item.get("badge", ""))
    tone = _stringify(item.get("tone", "acc"))
    text = _stringify(item.get("text", ""))
    choices = item.get("choices") or ("採用", "割引採用", "軽視", "棄却")
    recommended = _stringify(item.get("recommended", ""))
    badge_html = (
        '<span class="badge b-%s">%s</span>' % (_badge_tone(tone), escape(badge))
        if badge
        else ""
    )
    head = (
        '<p class="scale-head"><strong>'
        + _render_inline(title, glossary_entries, seen_terms)
        + "</strong> "
        + badge_html
        + "</p>"
    )
    body = (
        '<p class="scale-body">'
        + _inline_with_breaks(text, glossary_entries, seen_terms)
        + "</p>"
        if text
        else ""
    )
    buttons = []
    for choice in choices:
        choice_text = _stringify(choice)
        full = (title + "＝" + choice_text) if title else choice_text
        buttons.append(
            '<label class="pick"><input type="radio" name="%s" data-req="1" '
            'data-label="%s"%s> %s</label>'
            % (
                escape(group, quote=True),
                escape(full, quote=True),
                ' data-rec="1"' if choice_text == recommended else "",
                escape(choice_text),
            )
        )
    return (
        '<div class="scale-row">'
        + head
        + body
        + '<div class="picks">'
        + "".join(buttons)
        + "</div></div>"
    )


def _decision_block(
    value: object,
    glossary_entries: Mapping[str, GlossaryEntry] | None = None,
    seen_terms: set[str] | None = None,
) -> str:
    """判断コンソール。質問群をいくつでも置ける。

    入れるもの＝`{"groups":[...], "judgments":[...], "note":"…"}`。
    群は `{"legend","intro","kind":"radio|checkbox|scale|number|free","options"|"items","note"}`。
    ⚠️これまでの書き方（options / judgments / multi / numbers）もそのまま動く。
    """
    entries = glossary_entries or {}
    seen = seen_terms if seen_terms is not None else set()
    groups: list = []
    judgments: Sequence[object] = ()
    note = ""
    if isinstance(value, Mapping):
        raw_groups = value.get("groups")
        raw_judgments = value.get("judgments", ()) or ()
        judgments = (
            raw_judgments
            if isinstance(raw_judgments, (list, tuple))
            else (raw_judgments,)
        )
        note = _stringify(value.get("note", ""))
        if isinstance(raw_groups, (list, tuple)) and raw_groups:
            groups = list(raw_groups)
        else:
            options = value.get("options", ())
            if not isinstance(options, (list, tuple)):
                options = (options,)
            if options:
                groups.append(
                    {
                        "legend": "選択肢",
                        "kind": "checkbox" if value.get("multi") else "radio",
                        "options": list(options),
                    }
                )
            numbers = value.get("numbers", ())
            if isinstance(numbers, (list, tuple)) and numbers:
                groups.append(
                    {"legend": "数を入れる", "kind": "number", "options": list(numbers)}
                )
    elif isinstance(value, (list, tuple)):
        groups = [{"legend": "選択肢", "kind": "radio", "options": list(value)}]
    else:
        groups = [{"legend": "選択肢", "kind": "radio", "options": [value]}]

    blocks = []
    for index, group in enumerate(groups, start=1):
        if not isinstance(group, Mapping):
            group = {"legend": "選択肢", "kind": "radio", "options": [group]}
        name = "decision" if index == 1 else "decision-%d" % index
        kind = _stringify(group.get("kind", "radio")).lower() or "radio"
        legend = _stringify(group.get("legend", "選択肢"))
        intro = _stringify(group.get("intro", ""))
        rows = []
        if kind == "free":
            placeholder = _stringify(group.get("placeholder", legend))
            rows.append(
                '<label class="objection-freeform" for="decision-objection">'
                + _render_inline(legend, entries, seen)
                + "</label>"
                + '<textarea id="decision-objection" name="objection" rows="4" '
                + 'aria-label="%s" placeholder="%s"></textarea>'
                % (escape(legend, quote=True), escape(placeholder, quote=True))
            )
        elif kind == "scale":
            for order, item in enumerate(group.get("items", ()) or (), start=1):
                if not isinstance(item, Mapping):
                    item = {"title": _stringify(item)}
                rows.append(_scale_row(item, "%s-%d" % (name, order), entries, seen))
        elif kind == "number":
            for entry in group.get("options", ()) or ():
                if not isinstance(entry, Mapping):
                    entry = {"label": _stringify(entry)}
                label_text = _stringify(entry.get("label", "数"))
                unit = _stringify(entry.get("unit", ""))
                bounds = ""
                for key in ("min", "max"):
                    raw = _stringify(entry.get(key, ""))
                    if raw:
                        bounds += ' %s="%s"' % (key, escape(raw, quote=True))
                rows.append(
                    '<label class="choice number-row"><span>%s</span>'
                    '<input type="number" name="decision-number" data-req="1" '
                    'data-label="%s"%s aria-label="%s">%s</label>'
                    % (
                        _render_inline(label_text, entries, seen),
                        escape(label_text, quote=True),
                        bounds,
                        escape(label_text, quote=True),
                        '<span class="unit">%s</span>' % escape(unit) if unit else "",
                    )
                )
        else:
            for option in group.get("options", ()) or ():
                if isinstance(option, Mapping):
                    label_text = _stringify(option.get("label", ""))
                    why = _stringify(option.get("why", ""))
                    badge = _stringify(option.get("badge", ""))
                    tone = _stringify(option.get("tone", ""))
                    recommended = bool(option.get("recommended"))
                else:
                    label_text, recommended = _decision_parts(option)
                    why, badge, tone = "", "", ""
                if recommended and not badge:
                    badge, tone = "推奨", "good"
                rows.append(
                    _choice_input(
                        "checkbox" if kind == "checkbox" else "radio",
                        name,
                        label_text,
                        why=why,
                        badge=badge,
                        tone=tone,
                        recommended=recommended,
                        glossary_entries=entries,
                        seen_terms=seen,
                    )
                )
        intro_html = (
            '<p class="intro">' + _inline_with_breaks(intro, entries, seen) + "</p>"
            if intro
            else ""
        )
        group_note = _stringify(group.get("note", ""))
        note_html = (
            '<span class="why">' + _inline_with_breaks(group_note, entries, seen) + "</span>"
            if group_note
            else ""
        )
        blocks.append(
            "<fieldset><legend>"
            + _render_inline(legend, entries, seen)
            + "</legend>"
            + intro_html
            + "".join(rows)
            + note_html
            + "</fieldset>"
        )

    objections = []
    for judgment in judgments:
        label_text, _recommended = _decision_parts(judgment)
        label = escape(label_text, quote=True)
        objections.append(
            '<div class="obj-row">'
            '<label class="choice objection"><input type="checkbox" '
            'name="objection" data-label="%s"><span>%s — '
            "<b>これは違う</b></span></label>"
            '<input type="text" class="obj-why" data-label="%s" '
            'aria-label="%s の理由" placeholder="理由（任意）">'
            "</div>" % (label, label, label, label)
        )
    if objections:
        blocks.append(
            '<fieldset class="objections"><legend>判定への異議</legend>'
            + "".join(objections)
            + "</fieldset>"
        )
    if not any('id="decision-objection"' in block for block in blocks):
        blocks.append(
            "<fieldset><legend>自由記述</legend>"
            '<label class="objection-freeform" for="decision-objection">'
            "これは違う／追加条件</label>"
            '<textarea id="decision-objection" name="objection" rows="4" '
            'aria-label="これは違う／追加条件" placeholder="これは違う／追加条件"></textarea>'
            "</fieldset>"
        )
    page_note = (
        '<p class="why">' + _inline_with_breaks(note, entries, seen) + "</p>"
        if note
        else ""
    )
    return (
        "".join(blocks)
        + page_note
        + '<pre id="decision-prompt" aria-live="polite">選択してください。</pre>'
        + '<div class="decision-actions">'
        + '<button id="recommend-decision" class="secondary" type="button">推奨をまとめて選択</button>'
        + '<button id="copy-decision" type="button">依頼文をコピー</button>'
        + '<button id="select-decision" class="secondary" type="button">全部選ぶ</button>'
        + '<button id="forget-decision" class="secondary" type="button">入力を消す</button>'
        + "</div>"
    )


def _provenance_value(
    key: str,
    value: object,
    glossary_entries: Mapping[str, GlossaryEntry],
    seen_terms: set[str],
) -> str:
    text = _stringify(value).strip()
    if _looks_like_path(text) or key.lower() in {"path", "file", "source", "artifact"}:
        return f"<code>{escape(text)}</code>"
    return _render_inline(text, glossary_entries, seen_terms)


def _provenance_block(
    value: object,
    *,
    title: str,
    plan: ExplanationPlan,
    glossary_entries: Mapping[str, GlossaryEntry],
    seen_terms: set[str],
) -> str:
    items: list[tuple[str, object]] = []
    if isinstance(value, Mapping):
        items = [
            (str(key), item)
            for key, item in value.items()
            if item is not None and _stringify(item).strip()
        ]
    elif _stringify(value).strip():
        items = [("provenance", value)]
    if not items:
        items = [
            ("title", title),
            ("audience", plan.audience),
            ("publish policy", plan.publish_policy),
        ]
    rendered = "".join(
        f'<span class="provenance-item"><strong>{escape(key)}</strong> '
        f"{_provenance_value(key, item, glossary_entries, seen_terms)}</span>"
        for key, item in items
    )
    return (
        '<footer data-component="provenance"><div class="provenance-items">'
        + rendered
        + "</div></footer>"
    )


def render_components(
    plan: ExplanationPlan,
    *,
    title: str,
    content: Mapping[str, object],
    glossary_entries: Mapping[str, GlossaryEntry] | None = None,
) -> str:
    sections = []
    entries = glossary_entries or {}
    seen_terms: set[str] = set()
    planned = set(plan.components)
    # 画像の実測行（B2）＝ここでクリアしてから積む。1頁1回のクリアなので
    # モジュール単位の状態でも安全（この道具は1プロセスで1頁ずつ順に組む）。
    global _PAGE_HAS_EVIDENCE_SECTION
    _IMAGE_EVIDENCE_LINES.clear()
    sections_probe = content.get("sections")
    sections_probe_components = {
        _stringify(entry.get("component", ""))
        for entry in (sections_probe or [])
        if isinstance(entry, Mapping)
    }
    _PAGE_HAS_EVIDENCE_SECTION = (
        "evidence" in sections_probe_components
        or bool(content.get("evidence"))  # 2026-09-10：根拠欄を上位の鍵で渡す頁（末尾へ自動で足される）も対象
        or "evidence" in planned
    )
    overview = ""
    overview_present = "overview" in planned and "overview" in content
    if overview_present:
        overview = _render_inline(content.get("overview", ""), entries, seen_terms)
    if "summary" in planned and "summary" in content and "summary" not in {
        _stringify(e.get("component", "")) for e in (content.get("sections") or [])
        if isinstance(e, Mapping)
    }:
        summary_value = content.get("summary", "")
        summary_body = _summary_grid(summary_value, entries, seen_terms)
        summary_body += _summary_note(summary_value, entries, seen_terms)
        sections.append(
            f'<section data-component="summary" id="sec-1">'
            f'<h2>{escape(LABELS["summary"])}'
            f"</h2>{summary_body}</section>"
        )
    # 目次の飛び先。⚠️**節を組むそばから溜める**＝目次を手で書かせないため。
    toc_entries: list[tuple[str, str, str]] = []
    if sections:
        toc_entries.append(("sec-1", "", LABELS["summary"]))

    def _one_section(component: str, body_value: object, label: str, num: str) -> str:
        """節を1つ組む。⚠️見出しは**呼び側が決められる**（部品名に縛られない）。"""
        body = (
            _decision_block(body_value, entries, seen_terms)
            if component == "decision"
            else _text_block(body_value, component, entries, seen_terms)
        )
        heading = _render_inline(label, entries, seen_terms)
        num_html = (
            '<span class="sec-no">' + escape(num) + "</span>" if num else ""
        )
        anchor = "sec-%d" % (len(sections) + 1)
        toc_entries.append((anchor, num, label))
        return (
            '<section data-component="%s" id="%s"><h2>%s%s</h2>%s</section>'
            % (escape(component, quote=True), escape(anchor, quote=True),
               num_html, heading, body)
        )

    # 2026-08-29（ユーザー要望）：節を一覧で書くと、**順番・見出し・番号・繰り返し**が自由になる。
    # ⚠️これまでの書き方（部品名の辞書だけ）もそのまま動く。
    raw_sections = content.get("sections")
    emitted: set[str] = set()
    if isinstance(raw_sections, (list, tuple)) and raw_sections:
        for entry in raw_sections:
            if not isinstance(entry, Mapping):
                continue
            component = _stringify(entry.get("component", "")).strip()
            if not component:
                continue
            body_value = entry.get("content")
            if body_value is None:
                body_value = content.get(component)
            if body_value is None:
                continue
            if component == "overview" and not overview_present:
                pass
            label = _stringify(entry.get("label", "")) or LABELS.get(component, component)
            sections.append(
                _one_section(component, body_value, label, _stringify(entry.get("num", "")))
            )
            emitted.add(component)
    for component in plan.components:
        if component in {"overview", "summary"} or component in emitted:
            continue
        if component not in content:
            continue
        sections.append(
            _one_section(component, content[component], LABELS.get(component, component), "")
        )
    # B2：画像の実測行を evidence 節の末尾へ足す（無ければこの一覧はもう捨てる＝
    # `_image_block` が「evidence が無い頁は図の下に出す」を自分で済ませている）。
    if _IMAGE_EVIDENCE_LINES and _PAGE_HAS_EVIDENCE_SECTION:
        for index, section_html in enumerate(sections):
            if 'data-component="evidence"' not in section_html:
                continue
            insert_at = section_html.rfind("</tbody>")
            if insert_at < 0:
                break
            extra_rows = []
            for row_index, line in enumerate(_IMAGE_EVIDENCE_LINES, start=1):
                row_label, row_body, row_source = _parse_evidence_line(line)
                css_class = "s-m" if row_label in {"実測", "確認済み"} else "s-r"
                extra_rows.append(
                    '<tr data-evidence="image-%d"><td data-label="種類"><span class="src %s">'
                    "%s</span></td>"
                    '<td data-label="内容">%s</td>'
                    % (
                        row_index,
                        css_class,
                        escape(row_label),
                        _render_inline(row_body, entries, seen_terms),
                    )
                    + _source_cell(row_source, entries, seen_terms)
                    + "</tr>"
                )
            sections[index] = (
                section_html[:insert_at] + "".join(extra_rows) + section_html[insert_at:]
            )
            break
    header_component = ' data-component="overview"' if overview_present else ""
    lede = f'<p class="lede">{overview}</p>' if overview_present else ""
    # 2026-10-01（ユーザー承認の P9）：結論の見出し。headline があれば h1 を結論の1文にし、
    # 短い題は見出しの上の小さい行へ回す（<title> と頁の一覧の名前は短い題のまま）。
    # ⚠️用語の説明は付けない＝本文の初出の包装（p・li の検品）とぶつけないため。
    headline = _stringify(content.get("headline", "")).strip()
    eyebrow_html = escape(title) if headline else "UNDERSTANDING COMPOSER / PROJECT NOVICE"
    h1_html = escape(headline) if headline else escape(title)
    # 2026-08-30（ユーザー裁定）：頁全体の2段組み。側柱があるときだけ2段になる。
    # 2026-09-08（③）：側柱の用語リストは本文の後でないと数えられない
    #   （seen_terms が確定してから、本文で2回以上現れた語だけを選ぶ）。
    rail_spec = content.get("rail")
    rail_items = (
        rail_spec if isinstance(rail_spec, (list, tuple)) else ([rail_spec] if rail_spec else [])
    )
    needs_glossary_counts = any(
        isinstance(item, Mapping) and item.get("glossary") for item in rail_items
    )
    glossary_counts: dict[str, int] = {}
    if needs_glossary_counts and seen_terms:
        body_plain = unescape(re.sub(r"<[^>]+>", " ", "".join(sections)))
        for key in seen_terms:
            display = key.strip("`").strip()
            if display:
                glossary_counts[key] = _count_term(body_plain, display)
    rail_html = _rail_block(
        rail_spec, entries, seen_terms, toc_entries, glossary_counts=glossary_counts
    )
    layout_attr = ' data-layout="rail"' if rail_html else ""
    flow_open = '<main class="flow">' if rail_html else ""
    flow_close = "</main>" if rail_html else ""
    provenance = _provenance_block(
        content.get("provenance"),
        title=title,
        plan=plan,
        glossary_entries=entries,
        seen_terms=seen_terms,
    )
    return f"""<!doctype html>
<html lang="ja">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="color-scheme" content="light dark">
<title>{escape(title)}</title>

<style>
:root{{--ground:#F5F3EC;--surface:#FDFCF8;--surface-2:#F0EDE2;--ink:#242B33;--ink-2:#5B6470;--ink-3:#646B73;--on-accent:#FFFFFF;--rule:#D9D3C4;--rule-soft:#E7E2D6;--accent:#2F5D8A;--accent-2:#234869;--accent-soft:#E3ECF4;--new:#6A4FA3;--new-soft:#ECE6F6;--pass:#2C774B;--pass-soft:#E2F0E7;--fail:#A63A42;--fail-soft:#F6E2E3;--warn:#8E610E;--warn-soft:#F6ECD7;--focus:#3898EC;--tip-bg:#242B33;--tip-ink:#F5F3EC}}
@media(prefers-color-scheme:dark){{:root:not([data-theme="light"]){{--ground:#14171C;--surface:#1C2128;--surface-2:#23272E;--ink:#E9E6DE;--ink-2:#9AA3AD;--ink-3:#88909A;--on-accent:#14171C;--rule:#363D47;--rule-soft:#2A303A;--accent:#85AED6;--accent-2:#A9C7E6;--accent-soft:#243447;--new:#B49EE0;--new-soft:#32294A;--pass:#6CC092;--pass-soft:#1F3A2C;--fail:#E18A90;--fail-soft:#452227;--warn:#D8A84E;--warn-soft:#3D310E;--tip-bg:#E9E6DE;--tip-ink:#14171C}}}}
:root[data-theme="light"]{{--ground:#F5F3EC;--surface:#FDFCF8;--surface-2:#F0EDE2;--ink:#242B33;--ink-2:#5B6470;--ink-3:#646B73;--on-accent:#FFFFFF;--rule:#D9D3C4;--rule-soft:#E7E2D6;--accent:#2F5D8A;--accent-2:#234869;--accent-soft:#E3ECF4;--new:#6A4FA3;--new-soft:#ECE6F6;--pass:#2C774B;--pass-soft:#E2F0E7;--fail:#A63A42;--fail-soft:#F6E2E3;--warn:#8E610E;--warn-soft:#F6ECD7;--focus:#3898EC;--tip-bg:#242B33;--tip-ink:#F5F3EC}}
:root[data-theme="dark"]{{--ground:#14171C;--surface:#1C2128;--surface-2:#23272E;--ink:#E9E6DE;--ink-2:#9AA3AD;--ink-3:#88909A;--on-accent:#14171C;--rule:#363D47;--rule-soft:#2A303A;--accent:#85AED6;--accent-2:#A9C7E6;--accent-soft:#243447;--new:#B49EE0;--new-soft:#32294A;--pass:#6CC092;--pass-soft:#1F3A2C;--fail:#E18A90;--fail-soft:#452227;--warn:#D8A84E;--warn-soft:#3D310E;--tip-bg:#E9E6DE;--tip-ink:#14171C}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--ground);color:var(--ink);font-family:"Zen Kaku Gothic New","Hiragino Kaku Gothic ProN","Yu Gothic",system-ui,sans-serif;font-size:16px;line-height:1.9;-webkit-font-smoothing:antialiased}}
.wrap{{max-width:56rem;margin:0 auto;padding:clamp(1.5rem,4vw,3.2rem) clamp(1.1rem,4vw,2.4rem) 5rem;display:flex;flex-direction:column;gap:clamp(2rem,4vw,2.9rem)}}header{{border-bottom:2px solid var(--ink);padding-bottom:1.5rem}}.eyebrow{{font-family:"IBM Plex Mono",Consolas,ui-monospace,monospace;font-size:.72rem;letter-spacing:.16em;text-transform:uppercase;color:var(--accent);margin:0}}h1{{font-family:"Zen Old Mincho","Yu Mincho","Hiragino Mincho ProN",serif;font-weight:700;font-size:clamp(1.8rem,5vw,2.7rem);line-height:1.32;margin:.5rem 0 0;text-wrap:balance}}.lede{{margin:.9rem 0 0;font-size:1.05rem;color:var(--ink-2);max-width:40em}}.gnc{{display:grid;grid-template-columns:repeat(auto-fit,minmax(11rem,1fr));gap:.6rem;margin-top:1.3rem}}.gnc div{{background:var(--surface);border:1px solid var(--rule);border-radius:2px;padding:.7rem .85rem}}.gnc b{{display:block;font-family:"IBM Plex Mono",Consolas,ui-monospace,monospace;font-size:.7rem;letter-spacing:.12em;color:var(--accent);margin-bottom:.25rem}}.gnc span{{font-size:.88rem;color:var(--ink-2)}}
section{{display:flex;flex-direction:column;gap:.95rem}}h2{{font-family:"Zen Old Mincho","Yu Mincho","Hiragino Mincho ProN",serif;font-size:1.3rem;font-weight:700;margin:0;padding-bottom:.5rem;border-bottom:1px solid var(--rule);text-wrap:balance}}h3{{font-size:.98rem;font-weight:700;margin:0}}p{{margin:0;max-width:42em}}.body-copy{{color:var(--ink-2)}}.cap{{font-size:.8rem;color:var(--ink-3);margin:0}}code{{font-family:"IBM Plex Mono",ui-monospace,monospace;font-size:.86em;background:var(--surface-2);padding:.08em .35em;border-radius:2px}}
.item-stack{{display:flex;flex-direction:column;gap:.7rem}}.item-row{{display:grid;grid-template-columns:minmax(7rem,9rem) 1fr;gap:.85rem;background:var(--surface);border:1px solid var(--rule);border-left:3px solid var(--accent);border-radius:2px;padding:.85rem 1rem}}.item-label{{font-family:"IBM Plex Mono",ui-monospace,monospace;font-size:.72rem;font-weight:600;letter-spacing:.04em;color:var(--accent)}}.item-copy{{font-size:.93rem;color:var(--ink-2)}}.item-row[data-tone="risk"]{{border-left-color:var(--fail)}}.item-row[data-tone="risk"] .item-label{{color:var(--fail)}}.item-row[data-tone="decision"]{{border-left-color:var(--pass)}}.item-row[data-tone="decision"] .item-label{{color:var(--pass)}}
ol.steps{{list-style:none;margin:0;padding:0;display:flex;flex-direction:column;gap:.7rem;counter-reset:st}}ol.steps li{{counter-increment:st;display:grid;grid-template-columns:1.9rem 1fr;gap:.85rem;background:var(--surface);border:1px solid var(--rule);border-left:3px solid var(--accent);border-radius:2px;padding:.85rem 1rem}}ol.steps li::before{{content:counter(st);font-family:"IBM Plex Mono",ui-monospace,monospace;font-size:1.05rem;color:var(--accent);text-align:center;font-weight:600}}ol.steps .body{{display:flex;flex-direction:column;gap:.3rem;min-width:0}}ol.steps .ttl{{font-weight:700;font-size:.97rem}}ol.steps p{{font-size:.91rem;color:var(--ink-2)}}
ol.steps li[data-tone="risk"]{{border-left-color:var(--fail)}}ol.steps li[data-tone="risk"]::before,ol.steps li[data-tone="risk"] .ttl{{color:var(--fail)}}ol.steps li[data-tone="decision"]{{border-left-color:var(--pass)}}ol.steps li[data-tone="decision"]::before,ol.steps li[data-tone="decision"] .ttl{{color:var(--pass)}}
.flow-map{{display:grid;justify-items:center;gap:.55rem}}.flow-step{{width:min(100%,42rem);padding:.75rem 1rem;border:1px solid var(--rule);border-left:3px solid var(--accent);border-radius:2px;background:var(--surface);color:var(--ink);font-weight:700;text-align:left}}.flow-arrow{{color:var(--accent);font:600 1.1rem/1 "IBM Plex Mono",monospace}}
.scroll{{overflow-x:auto;background:var(--surface);border:1px solid var(--rule);border-radius:2px}}table{{border-collapse:collapse;width:100%;font-size:.86rem}}th,td{{padding:.55rem .7rem;border-bottom:1px solid var(--rule-soft);text-align:left;vertical-align:top}}thead th{{font-family:"IBM Plex Mono",ui-monospace,monospace;font-size:.71rem;letter-spacing:.05em;color:var(--ink-2);font-weight:500;background:var(--surface-2);border-bottom:1px solid var(--rule);white-space:nowrap}}tbody tr:last-child td,tbody tr:last-child th{{border-bottom:none}}td.num,th.num{{font-family:"IBM Plex Mono",ui-monospace,monospace;font-variant-numeric:tabular-nums;white-space:nowrap;text-align:right}}td.ok{{color:var(--pass);font-weight:600}}td.ng{{background:var(--fail-soft);color:var(--fail);font-weight:600}}.src{{font-family:"IBM Plex Mono",ui-monospace,monospace;font-size:.68rem;letter-spacing:.08em;padding:.1rem .4rem;border-radius:2px;font-weight:500}}.s-m{{background:var(--pass-soft);color:var(--pass)}}.s-a{{background:var(--warn-soft);color:var(--warn)}}.s-r{{background:var(--accent-soft);color:var(--accent)}}.s-x{{background:var(--fail-soft);color:var(--fail)}}
dl.gl{{margin:0;display:grid;grid-template-columns:auto 1fr;gap:.4rem 1rem;font-size:.9rem}}dl.gl dt{{font-weight:700;color:var(--ink);white-space:nowrap}}dl.gl dd{{margin:0;color:var(--ink-2)}}
details{{background:var(--surface);border:1px solid var(--rule);border-radius:2px;padding:.7rem 1rem}}details summary{{cursor:pointer;font-weight:500;font-size:.93rem}}details[open] summary{{margin-bottom:.6rem;padding-bottom:.5rem;border-bottom:1px solid var(--rule-soft)}}details .in{{font-size:.9rem;color:var(--ink-2)}}footer{{border-top:1px solid var(--rule);padding-top:1.1rem;font-size:.8rem;color:var(--ink-3)}}.provenance-items{{display:flex;flex-wrap:wrap;gap:.35rem 1rem}}.provenance-item{{overflow-wrap:anywhere}}
.note{{background:var(--surface);border:1px solid var(--rule);border-top:3px solid var(--accent);border-radius:2px;padding:1rem}}.note.warn{{border-top-color:var(--warn)}}.note.warn h3{{color:var(--warn)}}.note.bad{{border-top-color:var(--fail)}}.note.bad h3{{color:var(--fail)}}.note.good{{border-top-color:var(--pass)}}.note.good h3{{color:var(--pass)}}.note h3{{color:var(--accent)}}.ex{{background:var(--surface-2);border-radius:2px;padding:.6rem .8rem;font-size:.88rem;color:var(--ink-2)}}.ex b{{color:var(--ink)}}
.t{{position:relative;border-bottom:1px dotted var(--accent);cursor:help;outline:none}}.t:hover,.t:focus{{background:var(--accent-soft)}}.t::after{{content:attr(data-d);position:absolute;left:0;top:calc(100% + .4rem);z-index:30;width:min(24rem,calc(100vw - 3rem));padding:.55rem .75rem;border-radius:3px;background:var(--tip-bg);color:var(--tip-ink);font:400 .82rem/1.65 "Zen Kaku Gothic New","Yu Gothic",system-ui,sans-serif;box-shadow:0 6px 20px rgba(0,0,0,.22);display:none;pointer-events:none}}.t:hover::after,.t:focus::after{{display:block}}
.dia-hover-hint{{display:flex;align-items:center;gap:.45rem;width:max-content;max-width:100%;padding:.35rem .65rem;border:1px solid var(--rule);border-radius:2px;background:var(--surface-2);color:var(--ink-2);font-size:.78rem;line-height:1.55}}.dia-hover-hint span{{color:var(--accent);font-weight:700}}svg.dia .dia-node[data-hover]{{cursor:help;outline:none}}svg.dia .dia-node[data-hover]>rect{{transition:fill .15s ease,stroke-width .15s ease}}svg.dia .dia-node[data-hover]:hover>rect,svg.dia .dia-node[data-hover]:focus>rect{{fill:var(--accent-soft);stroke-width:2.5}}.dia-node-tip{{position:fixed;z-index:90;width:min(27rem,calc(100vw - 2rem));padding:.85rem 1rem;border:1px solid color-mix(in srgb,var(--tip-ink) 22%,transparent);border-left:4px solid var(--accent);border-radius:4px;background:var(--tip-bg);color:var(--tip-ink);box-shadow:0 10px 34px rgba(0,0,0,.32);font:400 .84rem/1.65 "Zen Kaku Gothic New","Yu Gothic",system-ui,sans-serif;pointer-events:none;overflow-wrap:anywhere}}.dia-node-tip[hidden]{{display:none}}.dia-node-tip__label{{display:block;margin-bottom:.2rem;font:700 .68rem/1.5 "IBM Plex Mono",ui-monospace,monospace;letter-spacing:.08em;opacity:.72}}.dia-node-tip__title{{display:block;margin-bottom:.3rem;font-size:1rem;line-height:1.5}}.dia-node-tip__text{{margin:0 0 .55rem;max-width:none}}.dia-node-tip__row{{display:grid;grid-template-columns:5.2rem minmax(0,1fr);gap:.55rem;padding-top:.35rem;margin-top:.35rem;border-top:1px solid color-mix(in srgb,var(--tip-ink) 18%,transparent)}}.dia-node-tip__row b{{font:700 .7rem/1.65 "IBM Plex Mono",ui-monospace,monospace;opacity:.72}}.dia-node-tip__row span{{min-width:0}}
fieldset{{margin:0;padding:0;border:0}}legend{{font-family:"IBM Plex Mono",ui-monospace,monospace;font-size:.72rem;letter-spacing:.08em;color:var(--ink-2)}}.choice{{display:flex;min-height:48px;gap:.75rem;align-items:flex-start;padding:.75rem .9rem;margin:.55rem 0;border:1px solid var(--rule);border-radius:2px;background:var(--surface);cursor:pointer}}.choice:hover,.choice:has(input:checked){{border-color:var(--accent);background:var(--accent-soft)}}input[type="radio"]{{margin-top:.42rem;accent-color:var(--accent)}}
section,p,pre,.choice,span,.scroll,.flow-map,.flow-cols,details,ul.bullets{{min-width:0;overflow-wrap:anywhere}}pre{{white-space:pre-wrap;word-break:break-word;padding:.7rem 1rem;border:1px solid var(--rule);border-radius:2px;background:var(--surface-2);font:500 .86rem/1.7 "IBM Plex Mono",ui-monospace,monospace}}button{{min-height:44px;padding:.65rem 1rem;border:1px solid var(--accent-2);border-radius:2px;background:var(--accent);color:var(--on-accent);font-weight:700;cursor:pointer}}button:hover{{background:var(--accent-2)}}button:focus-visible,.choice:focus-within{{outline:3px solid color-mix(in srgb,var(--focus) 48%,transparent);outline-offset:2px}}
.recommendation{{display:inline-block;margin-left:.4rem;padding:.08rem .38rem;border-radius:2px;background:var(--pass-soft);color:var(--pass);font:600 .7rem/1.5 "IBM Plex Mono",ui-monospace,monospace;letter-spacing:.04em}}.objection-freeform{{display:block;margin:.8rem 0 .35rem;font-weight:700}}.objection-freeform+textarea{{display:block;width:100%;min-height:6rem;padding:.65rem .75rem;border:1px solid var(--rule);border-radius:2px;background:var(--surface);color:var(--ink);font:inherit;resize:vertical}}.decision-actions{{display:flex;flex-wrap:wrap;gap:.55rem}}button.secondary{{background:var(--surface);color:var(--accent);border-color:var(--accent)}}button.secondary:hover{{background:var(--accent-soft)}}
ol.numbered{{margin:0;padding-left:1.4rem;display:flex;flex-direction:column;gap:.35rem;font-size:.9rem;color:var(--ink-2)}}dl.pairs{{margin:0;display:grid;grid-template-columns:auto 1fr;gap:.35rem .9rem;font-size:.9rem}}dl.pairs dt{{font-weight:700;color:var(--ink);white-space:nowrap}}dl.pairs dd{{margin:0;color:var(--ink-2)}}blockquote{{margin:0;padding:.7rem 1rem;border-left:3px solid var(--rule);background:var(--surface-2);color:var(--ink-2);font-size:.92rem}}mark{{background:var(--warn-soft);color:var(--ink);padding:0 .15em;border-radius:2px}}em{{font-style:normal;font-weight:600;color:var(--ink)}}hr{{border:0;border-top:1px solid var(--rule);margin:.4rem 0}}.number-row{{align-items:center;gap:.6rem}}.number-row input[type="number"]{{width:8rem;padding:.45rem .6rem;border:1px solid var(--rule);border-radius:2px;background:var(--surface);color:var(--ink);font:inherit;font-variant-numeric:tabular-nums;text-align:right}}.number-row .unit{{color:var(--ink-3);font-size:.85rem}}input[type="checkbox"]{{margin-top:.42rem;accent-color:var(--accent)}}.badge{{display:inline-block;padding:.08rem .42rem;border-radius:2px;font:600 .72rem/1.6 "IBM Plex Mono",ui-monospace,monospace;letter-spacing:.03em;border:1px solid transparent;vertical-align:.05em;max-width:100%;overflow-wrap:anywhere}}.b-acc{{background:var(--accent-soft);color:var(--accent);border-color:var(--accent)}}.b-good{{background:var(--pass-soft);color:var(--pass);border-color:var(--pass)}}.b-warn{{background:var(--warn-soft);color:var(--warn);border-color:var(--warn)}}.b-bad{{background:var(--fail-soft);color:var(--fail);border-color:var(--fail)}}.b-new{{background:var(--new-soft);color:var(--new);border-color:var(--new)}}.cols{{display:grid;gap:1rem;min-width:0;align-items:start}}.cols[data-cols="2"]{{grid-template-columns:1fr 1fr}}.cols[data-cols="3"]{{grid-template-columns:1fr 1fr 1fr}}.cols[data-cols="4"]{{grid-template-columns:repeat(4,1fr)}}.col{{display:flex;flex-direction:column;gap:.6rem;min-width:0}}.tiles{{display:grid;grid-template-columns:repeat(auto-fit,minmax(11rem,1fr));gap:.6rem;min-width:0}}.tile{{background:var(--surface);border:1px solid var(--rule);border-top:3px solid var(--accent);border-radius:2px;padding:.6rem .75rem;display:flex;flex-direction:column;gap:.2rem;min-width:0}}.tile b{{font-size:.9rem}}.tile span{{font-size:.83rem;color:var(--ink-2);line-height:1.7}}.tile[data-tone="good"]{{border-top-color:var(--pass)}}.tile[data-tone="warn"]{{border-top-color:var(--warn)}}.tile[data-tone="bad"]{{border-top-color:var(--fail)}}.tile[data-tone="new"]{{border-top-color:var(--new)}}.sec-no{{display:inline-block;min-width:1.9rem;margin-right:.5rem;padding:.05rem .35rem;border-radius:2px;background:var(--accent-soft);color:var(--accent);font:700 .78rem/1.7 "IBM Plex Mono",ui-monospace,monospace;text-align:center;vertical-align:.16em}}.why{{display:block;margin-top:.3rem;font-size:.83rem;line-height:1.7;color:var(--ink-3)}}.intro{{font-size:.88rem;color:var(--ink-2);margin:.15rem 0 .5rem}}fieldset+fieldset{{margin-top:1.4rem}}.scale-row{{border-left:3px solid var(--rule);padding:.1rem 0 .5rem .9rem;margin:.9rem 0}}.scale-head{{font-size:.93rem;margin:0 0 .2rem}}.scale-body{{font-size:.85rem;color:var(--ink-2);margin:0 0 .45rem}}.picks{{display:flex;flex-wrap:wrap;gap:.2rem .9rem}}.pick{{display:inline-flex;align-items:center;gap:.3rem;font-size:.87rem;cursor:pointer;min-height:32px}}.pick input{{margin:0;accent-color:var(--accent)}}.card .obj-row{{margin-top:.5rem;padding-top:.5rem;border-top:1px solid var(--rule-soft)}}.card .choice{{min-height:auto;padding:.3rem .5rem;background:transparent;border:0}}.scores{{float:right;margin-left:.6rem}}.card-stack{{display:flex;flex-direction:column;gap:.8rem;min-width:0}}.card{{background:var(--surface);border:1px solid var(--rule);border-left:3px solid var(--accent);border-radius:2px;padding:.9rem 1.05rem;display:flex;flex-direction:column;gap:.45rem;min-width:0}}.card h3{{font-size:.97rem;line-height:1.6}}.card p{{font-size:.92rem;color:var(--ink-2)}}.card[data-tone="good"]{{border-left-color:var(--pass)}}.card[data-tone="warn"]{{border-left-color:var(--warn)}}.card[data-tone="bad"]{{border-left-color:var(--fail)}}.card[data-tone="new"]{{border-left-color:var(--new)}}.obj-row{{display:flex;flex-direction:column;gap:.3rem;margin:.55rem 0}}.obj-row .choice{{margin:0}}.obj-why{{width:100%;padding:.5rem .65rem;border:1px solid var(--rule);border-radius:2px;background:var(--surface);color:var(--ink);font:inherit;font-size:.88rem}}section h3{{margin-top:.5rem;color:var(--ink);letter-spacing:.01em}}.dia-wrap{{overflow-x:auto;min-width:0}}svg.dia{{display:block;max-width:100%;height:auto;font-family:"Zen Kaku Gothic New","Yu Gothic",system-ui,sans-serif}}svg.tl,svg.quad,svg.venn,svg.flow,svg.score,svg.svg-in{{display:block;width:100%;height:auto}}.flow-cols{{display:grid;grid-template-columns:repeat(auto-fit,minmax(9rem,1fr));gap:.55rem;width:min(100%,42rem)}}.flow-cell{{padding:.7rem .9rem;border:1px solid var(--rule);border-top:3px solid var(--accent);border-radius:2px;background:var(--surface);font-size:.92rem}}pre.log{{white-space:pre-wrap;word-break:break-word;padding:.7rem 1rem;border:1px solid var(--rule);border-radius:2px;background:var(--surface-2);font:500 .82rem/1.7 "IBM Plex Mono",ui-monospace,monospace;overflow-x:auto;margin:0}}caption{{caption-side:bottom;text-align:left;font-size:.8rem;color:var(--ink-3);padding:.5rem .7rem;border-top:1px solid var(--rule-soft)}}ul.bullets{{margin:0;padding-left:1.2rem;display:flex;flex-direction:column;gap:.3rem;font-size:.9rem;color:var(--ink-2)}}#theme-toggle{{min-height:auto;padding:.35rem .7rem;font:500 .74rem/1.5 "IBM Plex Mono",ui-monospace,monospace;background:var(--surface);color:var(--ink-2);border:1px solid var(--rule)}}#theme-toggle:hover{{background:var(--surface-2);color:var(--ink)}}.flow{{display:flex;flex-direction:column;gap:clamp(2rem,4vw,2.9rem);min-width:0}}.rail{{display:flex;flex-direction:column;gap:.7rem;min-width:0;background:var(--surface);border:1px solid var(--rule);border-top:3px solid var(--accent);border-radius:2px;padding:1rem 1.1rem}}.rail-head{{font-family:"IBM Plex Mono",ui-monospace,monospace;font-size:.72rem;letter-spacing:.1em;color:var(--accent);margin:0}}.rail .cap,.rail p{{font-size:.85rem}}.rail table{{font-size:.8rem}}.rail ul.bullets{{font-size:.85rem}}.wrap[data-layout="rail"]{{max-width:74rem}}.wrap[data-layout="rail"]>.rail{{order:-1}}@media(min-width:1000px){{.wrap[data-layout="rail"]{{display:grid;grid-template-columns:minmax(0,1fr) 19rem;column-gap:2.4rem;row-gap:clamp(2rem,4vw,2.9rem);align-items:start}}.wrap[data-layout="rail"]>header,.wrap[data-layout="rail"]>footer{{grid-column:1 / -1}}.wrap[data-layout="rail"]>.rail{{order:0;position:sticky;top:1.6rem;max-height:calc(100vh - 3.2rem);overflow:auto}}}}section{{scroll-margin-top:1.2rem}}.toc ol{{list-style:none;margin:0;padding:0;display:flex;flex-direction:column;gap:.1rem}}.toc a{{display:flex;gap:.45rem;align-items:baseline;padding:.25rem .35rem;border-radius:2px;color:var(--ink-2);text-decoration:none;font-size:.85rem;line-height:1.55}}.toc a:hover,.toc a:focus-visible{{background:var(--accent-soft);color:var(--accent)}}.toc-no{{font:600 .7rem/1.6 "IBM Plex Mono",ui-monospace,monospace;color:var(--accent);min-width:1.6rem;flex:none}}.toc a[aria-current]{{background:var(--accent-soft);color:var(--accent);font-weight:700}}.toc a[aria-current] .toc-no{{color:var(--accent-2)}}@media(min-width:601px){{.t[data-flip]::after{{left:auto;right:0}}}}.head-row{{display:flex;flex-wrap:wrap;gap:.6rem;align-items:center;justify-content:space-between}}
@media(prefers-reduced-motion:reduce){{*,*::before,*::after{{transition:none !important;animation:none !important}}}}
@media(max-width:600px){{.wrap{{padding-inline:1rem}}.cols[data-cols]{{grid-template-columns:1fr}}.item-row{{grid-template-columns:1fr;gap:.35rem}}dl.gl{{grid-template-columns:1fr}}dl.gl dt{{white-space:normal}}.t::after{{position:fixed;left:1rem;right:1rem;top:auto;bottom:1rem;width:auto;max-height:40vh;overflow:auto}}section[data-component="evidence"] .scroll{{border:0;background:transparent;overflow:visible}}section[data-component="evidence"] table,section[data-component="evidence"] tbody,section[data-component="evidence"] tr,section[data-component="evidence"] td{{display:block;width:100%}}section[data-component="evidence"] thead{{display:none}}section[data-component="evidence"] tbody{{display:grid;gap:.7rem}}section[data-component="evidence"] tr{{border:1px solid var(--rule);border-radius:2px;background:var(--surface)}}section[data-component="evidence"] td{{display:grid;grid-template-columns:minmax(7rem,35%) minmax(0,1fr);gap:.65rem;border-bottom:1px solid var(--rule-soft)}}section[data-component="evidence"] td:last-child{{border-bottom:0}}section[data-component="evidence"] td::before{{content:attr(data-label);font:500 .68rem/1.6 "IBM Plex Mono",ui-monospace,monospace;color:var(--ink-3)}}section[data-component="evidence"] td.num{{text-align:left;white-space:normal}}section[data-component="evidence"] .source code{{overflow-wrap:anywhere;word-break:break-word}}}}
@media(max-width:600px){{.dia-node-tip{{left:1rem !important;right:1rem;top:auto !important;bottom:1rem;width:auto;max-height:48vh;overflow:auto}}.dia-node-tip__row{{grid-template-columns:4.6rem minmax(0,1fr)}}}}
.rail dl.gl{{font-size:.82rem}}.copy-btn{{min-height:36px;padding:.35rem .75rem;font-size:.78rem;margin-top:.4rem}}
pre.log.diff{{padding:.7rem 0}}pre.log.diff span{{display:block;padding:0 1rem}}pre.log.diff span.add{{background:var(--pass-soft);color:var(--pass)}}pre.log.diff span.del{{background:var(--fail-soft);color:var(--fail)}}pre.log.diff span.ctx{{color:var(--ink-2)}}
.formula{{background:var(--surface);border:1px solid var(--rule);border-radius:2px;padding:.85rem 1rem;display:flex;flex-direction:column;gap:.5rem;overflow-x:auto}}.formula math{{font-size:1.05rem}}.formula-reading{{margin:0;font-size:.82rem;color:var(--ink-3)}}
.q-original,.q-ja{{margin:0;font-size:.92rem;color:var(--ink-2)}}.q-source{{margin-top:.4rem;font-size:.78rem;color:var(--ink-3)}}
.chart-wrap{{min-width:0}}
.dia-warn{{margin:0;padding-left:1.2rem;font-size:.78rem;color:var(--warn);display:flex;flex-direction:column;gap:.15rem}}
.img-figure{{margin:0;display:flex;flex-direction:column;gap:.4rem;min-width:0}}.img-frame{{position:relative;overflow:hidden;border:1px solid var(--rule);border-radius:2px;background:var(--surface-2);line-height:0}}.img-frame img{{display:block;width:100%;height:auto}}.img-frame[data-zoom]{{cursor:zoom-in}}.img-figure figcaption{{font-size:.8rem;color:var(--ink-3)}}.marks{{position:absolute;inset:0;width:100%;height:100%}}.cap.img-src{{margin-top:.2rem}}
.zoom-overlay{{position:fixed;inset:0;background:color-mix(in srgb,#000 82%,transparent);display:flex;align-items:center;justify-content:center;z-index:999;padding:2rem;cursor:zoom-out}}.zoom-overlay .img-frame{{cursor:zoom-out;max-width:min(92vw,1100px);max-height:92vh;border-color:var(--surface)}}.zoom-overlay img{{max-height:88vh;width:auto;max-width:100%}}
.cell-bar{{display:inline-block;width:3.4rem;height:.5rem;margin-left:.5rem;background:var(--surface-2);border:1px solid var(--rule);border-radius:2px;overflow:hidden;vertical-align:middle}}.cell-bar-fill{{display:block;height:100%;background:var(--accent)}}
.pin{{display:inline-grid;place-items:center;min-width:1.35rem;height:1.35rem;padding:0 .3rem;border-radius:999px;background:var(--accent);color:var(--on-accent);font:700 .72rem/1 "IBM Plex Mono",ui-monospace,monospace;vertical-align:.08em;margin-right:.35rem}}.pin[data-tone="good"]{{background:var(--pass)}}.pin[data-tone="warn"]{{background:var(--warn)}}.pin[data-tone="bad"]{{background:var(--fail)}}.pin[data-tone="new"]{{background:var(--new)}}.pin[data-tone="acc"]{{background:var(--accent)}}.of{{color:var(--ink-3)}}td.stackcell{{min-width:7.5rem}}td.stackcell .v{{display:block;font-family:"IBM Plex Mono",ui-monospace,monospace;font-variant-numeric:tabular-nums}}.stack{{display:flex;gap:2px;height:.5rem;width:7.5rem;max-width:100%;margin-top:.3rem;border-radius:2px;overflow:hidden;background:var(--surface-2)}}.stack i{{display:block;height:100%;min-width:3px}}.stack i[data-tone="good"],.stack-legend i[data-tone="good"]{{background:var(--pass)}}.stack i[data-tone="warn"],.stack-legend i[data-tone="warn"]{{background:var(--warn)}}.stack i[data-tone="bad"],.stack-legend i[data-tone="bad"]{{background:var(--fail)}}.stack i[data-tone="new"],.stack-legend i[data-tone="new"]{{background:var(--new)}}.stack i[data-tone="acc"],.stack-legend i[data-tone="acc"]{{background:var(--accent)}}.stack-legend{{display:flex;flex-wrap:wrap;gap:.3rem 1rem;font-size:.8rem;color:var(--ink-2);margin:.1rem 0 .45rem}}.stack-legend span{{display:inline-flex;align-items:center;gap:.35rem}}.stack-legend i{{display:inline-block;width:.7rem;height:.7rem;border-radius:2px}}.cell-note{{display:block;margin-top:.15rem;font-family:inherit;font-size:.76rem;line-height:1.55;color:var(--ink-3);white-space:normal;text-align:left}}td.num .cell-note{{font-family:"Zen Kaku Gothic New",system-ui,sans-serif}}tr.grp td,tr.grp th{{border-top:2px solid var(--rule)}}tbody th[scope="row"]{{font-weight:700;color:var(--ink);background:transparent}}tbody th[scope="row"]{{min-width:6.5rem}}@media(max-width:600px){{td.stackcell{{min-width:5.6rem}}.stack{{width:5.6rem}}}}.img-pin{{position:absolute;transform:translate(-50%,-50%);display:inline-grid;place-items:center;min-width:1.5rem;height:1.5rem;padding:0 .3rem;border-radius:999px;font:700 .76rem/1 "IBM Plex Mono",ui-monospace,monospace;background:var(--accent);color:var(--on-accent);box-shadow:0 0 0 2px var(--surface);pointer-events:none}}.img-pin[data-tone="good"]{{background:var(--pass)}}.img-pin[data-tone="warn"]{{background:var(--warn)}}.img-pin[data-tone="bad"]{{background:var(--fail)}}.img-pin[data-style="box"]{{transform:translate(-35%,-35%);background:var(--surface);color:var(--fail);border:1.5px solid var(--fail);box-shadow:none}}.img-pin[data-style="box"][data-tone="good"]{{color:var(--pass);border-color:var(--pass)}}.img-pin[data-style="box"][data-tone="warn"]{{color:var(--warn);border-color:var(--warn)}}.img-pin[data-style="box"][data-tone="acc"]{{color:var(--accent);border-color:var(--accent)}}.stats{{display:grid;grid-template-columns:repeat(auto-fit,minmax(13rem,1fr));gap:.7rem;min-width:0}}.stat{{background:var(--surface);border:1px solid var(--rule);border-top:3px solid var(--accent);border-radius:2px;padding:.9rem 1rem;display:flex;flex-direction:column;gap:.25rem;min-width:0}}.stat-num{{font:500 2rem/1.15 "IBM Plex Mono",ui-monospace,monospace;font-variant-numeric:tabular-nums;color:var(--ink);overflow-wrap:anywhere}}.stat-num small{{font:500 .85rem/1 "Zen Kaku Gothic New",system-ui,sans-serif;color:var(--ink-2);margin-left:.35rem}}.stat-label{{font-weight:700;font-size:.9rem}}.stat-sub{{margin:0;font-size:.83rem;line-height:1.7;color:var(--ink-2)}}.stat[data-tone="good"]{{border-top-color:var(--pass)}}.stat[data-tone="warn"]{{border-top-color:var(--warn)}}.stat[data-tone="bad"]{{border-top-color:var(--fail)}}.stat[data-tone="new"]{{border-top-color:var(--new)}}ol.hsteps{{list-style:none;margin:0;padding:0;counter-reset:hs;display:grid;grid-template-columns:repeat(auto-fit,minmax(10rem,1fr));gap:1rem;min-width:0}}ol.hsteps li{{counter-increment:hs;display:flex;flex-direction:column;gap:.25rem;border-top:2px solid var(--accent);padding-top:.55rem;min-width:0}}ol.hsteps li::before{{content:counter(hs);font:600 .78rem/1 "IBM Plex Mono",ui-monospace,monospace;color:var(--accent)}}ol.hsteps b{{font-size:.93rem}}ol.hsteps span{{font-size:.86rem;line-height:1.7;color:var(--ink-2)}}.chip-groups{{display:grid;grid-template-columns:repeat(auto-fit,minmax(15rem,1fr));gap:.9rem 1.4rem;min-width:0}}.chip-group{{display:flex;flex-direction:column;gap:.45rem;min-width:0}}.chip-head{{margin:0;font-size:.88rem;display:flex;align-items:baseline;gap:.45rem;flex-wrap:wrap}}.chip-head .cnt{{font:600 .8rem/1 "IBM Plex Mono",ui-monospace,monospace;color:var(--accent)}}.cnt-note{{font-size:.76rem;font-weight:400;color:var(--ink-3)}}ul.chips{{list-style:none;margin:0;padding:0;display:flex;flex-wrap:wrap;gap:.35rem}}ul.chips li{{font-size:.8rem;line-height:1.5;padding:.12rem .55rem;border:1px solid var(--rule);border-radius:999px;background:var(--surface);color:var(--ink-2)}}
.callout-legend{{list-style:none;margin:0;padding:0;display:flex;flex-direction:column;gap:.45rem}}.callout-item{{display:flex;align-items:center;gap:.55rem}}.callout-legend svg.badge{{width:1.4rem;height:1.4rem;padding:0;border:0;background:none;display:inline-block;vertical-align:middle;flex:none}}.callout-text{{font-size:.88rem;color:var(--ink-2)}}
.compare{{border:1px solid var(--rule);border-radius:2px;padding:1rem;background:var(--surface);min-width:0}}.compare-tabs label{{min-height:32px;display:inline-flex;align-items:center}}
@media print{{@page{{size:A4;margin:15mm}}#theme-toggle,.copy-btn,#copy-decision{{display:none !important}}.wrap[data-layout="rail"]{{display:block}}.wrap[data-layout="rail"]>.rail{{order:0;position:static;max-height:none;overflow:visible}}.card,.scroll,pre,.dia-wrap,.chart-wrap,details,.img-figure,.compare,.callout-legend{{break-inside:avoid;page-break-inside:avoid}}.t::after{{display:none !important}}.zoom-overlay,.dia-node-tip,.dia-hover-hint{{display:none !important}}}}
</style>
</head>
<body><div class="wrap"{layout_attr}><header{header_component}><div class="head-row"><p class="eyebrow">{eyebrow_html}</p><button id="theme-toggle" type="button">明暗を切り替える</button></div><h1>{h1_html}</h1>{lede}</header>{flow_open}{''.join(sections)}{flow_close}{rail_html}{provenance}</div>
<script>
{DECISION_SCRIPT}
</script></body></html>"""

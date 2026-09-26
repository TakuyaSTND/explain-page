from __future__ import annotations

import re
from pathlib import Path
from typing import Sequence

from . import branding
from .contracts import ExplanationPlan

MARKER = re.compile(
    r"<!--\s*HOOK_COMPONENT:([a-z_]+):START\s*-->(.*?)"
    r"<!--\s*HOOK_COMPONENT:\1:END\s*-->",
    flags=re.DOTALL,
)
STYLE_MARKER = re.compile(
    r"<!--\s*HOOK_STYLE:START\s*-->(.*?)<!--\s*HOOK_STYLE:END\s*-->",
    flags=re.DOTALL,
)


def load_fragments(path: str | Path) -> dict[str, str]:
    # 2026-09-25：プラグインとして他のリポジトリへ入れた時、そのプロジェクトに
    # `.claude/html-output.md`（部品ごとの説明の断片）が無いことがある
    # （プラグイン本体は同梱していない＝正本のこのファイルは配布物の一覧に無い）。
    # ⚠️以前は無条件で read_text していたので、無ければ例外でフック全体が落ちた。
    #   このリポジトリでは常に存在するので、既存の挙動は変えない（try節に入るだけ）。
    try:
        text = Path(path).read_text(encoding="utf-8")
    except OSError:
        return {}
    return {
        name: body.strip()
        for name, body in MARKER.findall(text)
        if body.strip()
    }


def load_style_fragment(path: str | Path) -> str:
    try:
        text = Path(path).read_text(encoding="utf-8")
    except OSError:
        return ""
    match = STYLE_MARKER.search(text)
    return match.group(1).strip() if match else ""


# 出し方の指示は policy の publish で決める（2026-08-26）。
# ⚠️以前は "Local-only。…" を直書きしていたので、visual-hook-policy.json の publish を
#   変えても文面が変わらなかった＝設定が効かない状態だった。値を素通しで保存するだけで
#   どこも分岐していなかったのが原因。
DELIVERY_LINES = {
    "never": "Local-only。用語検査と表示検査を通す。",
    "always": "Artifactで公開し、URLを本文に出す。用語検査と表示検査を通す。",
    "ask": "Artifactで公開してよいかを1行で尋ね、許可があれば公開する。用語検査と表示検査を通す。",
}
DELIVERY_FALLBACK = "Local-only。用語検査と表示検査を通す。"

# 2026-08-31（実害）：レンダラーの使い方が CLAUDE.md にしか書かれておらず、
#   規約を足す**前に始まったセッション**には永久に届かなかった（CLAUDE.md はセッション
#   開始時に1回だけ読まれる）。そこでは頁が手書きになり、目印が無いので検品証が必ず落ちる。
#   ⚠️指示文はターンごとに組み直されるので、ここに置けば古いセッションにも届く。
# 2026-09-25：道具の場所は固定文字列にしない＝直置きかプラグインかで変わる
#   （`visual/paths.py` の `render_page_tool_location`）。呼び出し側が渡さなければ
#   このリポジトリの従来どおりの相対パスに倒す＝出力は1バイトも変わらない。
def _renderer_line(render_page_path: str | None = None) -> str:
    tool = render_page_path or ".claude/scripts/render_page.py"
    approved_root = "%TEMP%/" + branding.ARTIFACT_DIR_NAME
    # 2026-09-26：回答集めの道具（branding.QA_PAGE_TOOL に名前を持つもの）は利用者の機械ごとの道具
    #   ＝公開版（branding.QA_PAGE_TOOL が None）では、この例外の文を出さない。
    qa_tool = getattr(branding, "QA_PAGE_TOOL", None)
    exception = (
        "⚠️例外は**尋問の回答集めだけ**＝それは `" + qa_tool + "` で"
        "作り、承認済みの置き場（`" + approved_root + "`）に書く。その出力は検品証を取らない"
        "（部品の目印が無いので検査は通らない＝それでよい）。"
    ) if qa_tool else ""
    return (
    "頁は手書きしない＝`" + tool + "` に定義JSONを渡して組む"
    "（手書きは検品証が落ちる）。" + exception + "報告と判断の頁は必ずレンダラーで作る。"
    "配置＝段組みは `columns`、タイルは `tiles`、"
    "頁全体の2段組みは `rail`（`toc` で節の目次、`glossary` で頁の用語リスト）。"
    "⚠️地の文だけ並べると殺風景になる＝中身に合う部品を使う："
    "`cards`（badge・right・objection付き）／`diagram`（箱と矢印。`num` で図番号・`source` で出所も添える）"
    "／`table`（head・rows・widths・caption。⚠️前後の比較や一覧は表で書く＝`visual` に縦棒の行を並べても表として組み直される）／`note`（warn・bad・good）／`items`／`ordered`／`pairs`"
    "／`quote`（`original`・`ja`・`source` の辞書で原文と訳文と出所を添える）／`log`"
    "／`diff`（コードの差分）／`chart`（数値の図＝折れ線・棒）／`formula`（数式＝`tex` と `reading`）"
    "／`svg`（手書きのSVGを許可リストで組み直して載せる）／`image`（元資料のスライド画像を切り出して貼る＝`deck`+`slide` か `path`、`crop`・`marks` で枠と番号）"
    "／`timeline`（時間軸）／`quadrant`（四象限）／`venn`（集合の重なり）／`flow`（重み付きの流れ）／`score`（採点の格子）"
    "／`compare`（前後の切り替え）／`callouts`（番号付き吹き出しの凡例）／`diagram_text`（1行記法 `A -> B : 条件` から図）"
    "／`table` の `heat`・`bars`（列の色付けと行内の棒）／`diagram` の箱に `icon`（線画の記号）、"
    "文中は `[[good:…]]` の色札・`==強調==`・`**太字**`・`` `コード` ``。"
    "判断は `groups`（radio／checkbox／scale／number／free）で組む。"
    "⚠️出所を書けない主張は根拠欄（`evidence`）の外に置かない"
    "＝断定を本文に書いたら、対応する行を「種類：内容｜どこで確かめたか」で必ず足す。"
)

# 2026-09-25：Codexには公開の道具（Artifact）が無いので、頁を書いた事実そのものが
#   検品の記録に残らない（過去0件）。render_page.py に --runtime codex を付けると、
#   道具が依頼の受付で残した印を読んで、自分の代わりに検品の記録を書く。
#   ⚠️Claude・Hermesの指示文には出さない＝この経路が要るのはCodexだけ。
CODEX_RENDERER_LINE = (
    "頁は render_page.py に --runtime codex を付けて組む"
    "（Codexには公開の道具が無いので、道具が検品の記録を代わりに書く）。"
)

# 2026-09-08：ja-text-communication（mathbullet/skills, MIT）のうち、
#   こちらの規約に無かった6項目を取り込む。既存の [glossary] 等と同じ体裁の節として
#   常に出す＝どのターンでも「どう書くか」を思い出せるようにする。
# ⚠️URLは書かない＝`https://` は検品器（visual smoke 等）が拒否する文字列なので、
#   指示文にそのまま入れると誤検知の芽になる。出所は名前だけで書く。
READABILITY_BODY = (
    "英語の術語は、定着した日本語訳→定着したカタカナ→略語のみ英語、の順で選ぶ。"
    "定訳があるかどうかは推測せず確認する。\n"
    "英単語に日本語の助詞や活用をそのまま接続しない"
    "（「genericな」「retrieveした」のような書き方はしない）。\n"
    "独自の造語や圧縮熟語を作らない。「〜に落とす」「〜を流す」のような俗語は、"
    "技術的な実体に言い換える。\n"
    "主語と目的語を省かない。体言止めの圧縮句で設計判断を表現しない。\n"
    "矢印連鎖（A→B→C）を使うときは、各矢印が前提とする条件を本文で先に説明する。\n"
    "確認質問や選択肢を出すときは、何が論点で、各選択肢を選ぶと何が変わるか"
    "（判断材料）を添える。\n"
    "出所：mathbullet/skills の ja-text-communication（MIT）B1・B2・B4・C2・C3・E7 を借用"
)
# 2026-08-29（ユーザー承認＝不具合2）：計画が markdown のターンで出す1行。
# ⚠️以前はここが無く、**delivery を一度も見ずに** publish だけで文面を決めていた。
#   そのため「頁は要らない」と決めたターンでも「Artifactで公開し…」と指示していた
#   （実測：記録66ターンのうち33ターンが markdown 計画）。指示と検査が食い違い、
#   受け取る側（AI）はどちらなのかを知る手段が無かった。
MARKDOWN_DELIVERY_LINE = (
    "Markdownの文章のまま答える。HTMLの頁は作らないので、公開も用語検査も表示検査も要らない。"
)


def delivery_line(publish_policy: str, delivery: str = "local_html") -> str:
    """「どう出すか」の1行を選ぶ。

    delivery が local_html 以外なら、publish の値によらず「文章のまま」に倒す
    （頁を作らないターンで公開を要求しないため）。local_html のときだけ publish を見る。
    知らない publish は Local-only に倒す。
    """
    if str(delivery).strip().lower() != "local_html":
        return MARKDOWN_DELIVERY_LINE
    return DELIVERY_LINES.get(str(publish_policy).strip().lower(), DELIVERY_FALLBACK)


def compile_stop_reminder(
    plan: ExplanationPlan,
    previous_components: Sequence[str],
    path: str | Path,
    *,
    runtime: str | None = None,
    render_page_path: str | None = None,
) -> str:
    """停止時の差し戻しの短い文（2026-09-26・見やすさ V4）。

    なぜ要るか＝以前は差し戻しのたびに依頼時と同じ指示文の全文（約4,000字）を繰り返し、
    差し戻した理由の1行はその末尾に埋もれていた（この会話で30回）。書き方の決まりは
    同じ回の依頼時に出ているので、ここでは①計画（要る部品）②直し方の1行③依頼時の
    計画に無かった＝後から増えた部品の書き方だけを出す。理由の行は呼び出し側が足す。
    ⚠️依頼時の計画が無いとき（previous_components が空で依頼時の指示が出ていない
      可能性がある）の判断は呼び出し側＝全文に倒す。
    """
    fragments = load_fragments(path)
    tool = render_page_path or ".claude/scripts/render_page.py"
    seen = set(previous_components)
    added = [component for component in plan.components if component not in seen]
    lines = [
        f"audience={plan.audience} depth={plan.depth}",
        "components=" + ",".join(plan.components),
        "reasons=" + ",".join(plan.reason_codes),
        "[差し戻し] この回は説明の頁が要る＝`" + tool + "` に定義JSONを渡して、"
        "上の components をすべて入れた頁を組み、器用のほうを公開する"
        "（最後の返事の直前に公開すると照合が通る）。"
        "書き方の決まりは、この回の依頼のときの指示文と同じ。",
    ]
    if runtime == "codex":
        lines.append(CODEX_RENDERER_LINE)
    for component in added:
        fragment = fragments.get(component)
        if fragment:
            lines.append(f"[{component}] {fragment}")
    return "\n".join(lines)


def compile_directive(
    plan: ExplanationPlan,
    path: str | Path,
    *,
    runtime: str | None = None,
    render_page_path: str | None = None,
) -> str:
    fragments = load_fragments(path)
    style_fragment = load_style_fragment(path)
    lines = [
        f"audience={plan.audience} depth={plan.depth}",
        "components=" + ",".join(plan.components),
        "reasons=" + ",".join(plan.reason_codes),
        "Project初心者に、背景・用語・理由・具体例を省略せず説明する。",
        "確認済み事実・仮定・推奨・未検証を分ける。",
        delivery_line(plan.publish_policy, plan.delivery),
    ]
    # ⚠️頁を作らないターンには出さない（Markdownで答えるだけのターンに雑音を足さない）。
    if str(plan.delivery).strip().lower() == "local_html":
        lines.append(_renderer_line(render_page_path))
        # 2026-09-25：Codexだけに向けた1行。既存の「頁は手書きしない」の行の直後に置く
        # （指示文の前のほう＝実測で効く場所）。Claude・Hermesには出さない。
        if runtime == "codex":
            lines.append(CODEX_RENDERER_LINE)
    # readability（B1/B2/B4/C2/C3/E7）は delivery を問わず常に出す＝
    # Markdownの地の文にも同じ書き方の規律をかける。
    lines.append(f"[readability] {READABILITY_BODY}")
    if style_fragment:
        lines.append("[visual_style] " + style_fragment)
    for component in plan.components:
        fragment = fragments.get(component)
        if fragment:
            lines.append(f"[{component}] {fragment}")
    return "\n".join(lines)

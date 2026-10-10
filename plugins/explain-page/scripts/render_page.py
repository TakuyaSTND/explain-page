#!/usr/bin/env python3
"""人に見せる頁を、正規レンダラーで組んで検査まで通す道具（2026-08-29 ユーザー裁定）。

なぜ要るか＝手書きの頁は**検査器の目印を持たない**ので、検品証が永久に落ちる。
2026-08-29に同じ内容で比べた実測：レンダラー版は検品ok=True・部品9個検出・未包装0、
手書き版は検品ok=False・部品0個検出・未包装13件だった。∴レンダラーを既定にする。

⚠️この道具が無いと毎回忘れる手順が2つある。
  ① レンダラーは**完全な1文書**を出すが、Artifactは publish 時に自前の器で包む。
     そのまま渡すと入れ子になるので、title・style・body・script だけに削る必要がある。
  ② 頁は**承認済みの置き場**（プロジェクトの policy の local_artifact_root。
     既定＝%TEMP%/<配布の名前>）に置かないと検品証が作られない。

使い方:
  PYTHONUTF8=1 python .claude/scripts/render_page.py <頁の定義.json>
  PYTHONUTF8=1 python .claude/scripts/render_page.py <頁の定義.json> --runtime codex

引数:
  --runtime {none,codex}  既定 none。codex を付けると、完全版の頁について
                          検品の記録（PostToolUseの代わり）を1件残す（2026-09-25）。
                          ⚠️Codexには公開の道具（Artifact）が無いので、頁を書いた
                          事実そのものが検品の記録に残らない。依頼の受付（Codexの
                          UserPromptSubmitフック）が残した「いまの会話とその回」の
                          印を読んで、この道具が代わりに記録する。印が無い・古い時は
                          記録せず、理由を1行出す（安全側＝環境変数だけを見て自動で
                          記録することはしない。--runtime codex を明示した時だけ動く）。
  --state-path PATH       既定＝承認済みの置き場（上記）の下の state.db。検品の記録の保存先。
  --project-root PATH     既定＝環境変数 CLAUDE_PROJECT_DIR、無ければ今の作業フォルダから
                          上へ辿って `.claude/visual-hook-policy.json` がある場所、それも
                          無ければ従来どおり（この道具の置き場の親の親）。用語集3つの
                          パスを決めるのに使う（2026-09-25・`visual/paths.py` 参照）。
                          ⚠️プラグインとして他のリポジトリに入れた時は、この引数で
                          そのプロジェクトの根を指す＝Claude Codeが `${CLAUDE_PROJECT_DIR}`
                          を渡す。

定義ファイルの形（JSON・UTF-8）:
  {
    "name": "書き出すファイル名の頭",
    "title": "頁の題",
    "components": ["overview", "summary", ...],
    "reasons": ["project_novice_default", ...],
    "publish": "always",
    "content": {
      "overview": "本文",
      "summary": "Goal：…\nNow：…",
      "walkthrough": "見出し：本文\n見出し：本文",
      "evidence": "実測：内容｜どこで確かめたか",
      "decision": {"options": ["案A"], "judgments": ["これは私の判定"]},
      "provenance": {"source": "path/to/file.py", "owner": "local"},
      "sections": [
        {"component": "walkthrough", "num": "壱", "label": "自分で付けた見出し",
         "content": "背景：本文", "asks": [1]}
      ],
      "rail": [{"heading": "用語", "glossary": true}]
    }
  }

節（sections）の塊や側柱（rail）の塊は、以下の追加の「塊のキー」も受ける
（2026-09-08 実装。詳しくは render_components.py の docstring を見る）:
  - "diff": "行" か行の一覧（行頭 + 追加／- 削除／それ以外は文脈）。コピー釦つき。
  - "chart": {"kind":"line","title":"…","labels":[...],
             "series":[{"name":"…","values":[数,…]}],"unit":"…","source":"…"}
             （描画係が無い・失敗した時は同じ数値を表に落とす＝黙って消さない）
  - "formula": {"tex": "LaTeX原文", "reading": "読み方（任意）"}（対応外は code 表示）
  - "quote": 文字列（従来どおり）か {"original":"…","ja":"…","source":"…"}
  - "diagram" は任意欄 "num"（例「図1」）と "source"（出所）を受ける
    （既存の caption と合わせて図の下に1行で出す）。矢印付きの図は配置と経路の計算を
    `visual/diagram_layout.py` に委ねる（2026-09-10）＝番号でも宣言した id でも辺が結び付き、
    箱の数に応じて層に折り返すので、6箱の鎖でも幅だけに縮んで文字が潰れない。
  - "svg": SVG文字列、または {"svg":…,"num":…,"source":…,"caption":…}
    （許可リストで組み直す＝生のSVGは受け取らない。外した要素・属性は枠の下に列挙する）
  - "image": {"path"|"deck"+"slide","crop","marks","caption","source","alt","width","num"}
    （data:URIで埋め込み。押すと拡大表示。実測の1行は根拠欄へ自動で足す＝
    根拠の節が無ければ図の下に出す）
  - "timeline"/"quadrant"/"venn"/"flow"/"score": `visual/visuals.py` の各SVG
    （spec の形は同モジュールのdocstringを見る。num/source/caption は図と同じ書き方）
  - "compare": {"before":…,"after":…,"labels":["前","後"]}（前後を切り替えて見る。JSは使わない）
  - "callouts": [{"n":1,"text":"…"}]（番号の吹き出し一覧）
  - "diagram_text": "A -> B : 条件" のような1行記法（`visual/diagram_dsl.py`）から図を組む
  - "table" の "heat":[列番号,…] は数値セルの背景を段階的な濃さにし、
    "bars":[列番号,…] は数字の右に値/最大の細い棒を置く
  - 2026-10-01（手書きのHTMLとの比べから足した部品）：
    "image" は画面の写真（スクショ）もそのまま貼れる。小さい画像は元の幅より引き伸ばさない。
      "marks" の各印に "style":"pin"（枠なしの点の番号）と "tone"（acc／good／warn／bad）
    "screenshot": {"target":"手元のファイル か http://localhost…","viewport":[1280,800],
      "selector","full_page","wait_ms","crop","marks","caption","source","width","num"}
      （組むときに撮って image と同じに貼る。外部の頁は撮らない）
    文中の "[[pin:3]]" / "[[pin:3:good]]" は画像の点の番号と同じ見た目の印（表の行頭に置く）
    "table" の "stack":[列番号] はセル「62,3,0」を「62/65」と内訳の積み上げ棒にする
      （"stack_labels":["正解","見落とし","誤り"]・"stack_tones":["good","warn","bad"]・凡例は表の上）
      "frac":[列番号] は「62/65」の分母を薄く、"groups":[行番号] はその行の上に区切り線、
      "row_head":true は1列目を行見出しにする。セルの改行の後は小さい注記になる
    "stats": [{"value":"38","unit":"/ 38項目","label":"…","text":"…","tone":"good"}]（大きい数字）
    "steps": [{"title":"…","text":"…"}] か「題：本文」の一覧（横並びの番号つき手順）
    "chips": 語の一覧か [{"title":"…","items":[…],"note":"…"}]（短い語の札の束・数は自動）
    content の "headline" は h1 を結論の1文にする（短い題は上の小さい行へ・<title> は題のまま）
  - 2026-10-08（判断の頁を赤ペン流に寄せた）：判断の選択肢（"decision" の groups の options の辞書）は
    "pros":"利点"（配列なら「／」で結合）・"cons":"代償"・"thumb" を受ける。
    ⚠️非推奨の選択肢に利点が無い問いは、組む前に「実質1択の恐れ」と警告する（止めはしない）。
    "pros"：その案を選ぶ利点。推奨でない案にも1行書く（why に「利点：」と書いても同じ扱い）
    "cons"：その案の代償。選ぶと何を諦めるか
    "thumb"：選択肢の小さな絵＝{"svg":"<svg…>"}（許可リストで組み直す）か
      {"path":"…png","alt":"…","crop":[…]}（画像）。文字列なら「<svg」で始まれば svg・他は画像の path
    頁の定義の上の段の "preflight":{"reader":"読者宣言の1行","allowed":["語",…]} は、
    判断の頁（reasons に decision_required）で出す試問の文に使う（無ければ既定の読者・許可語なし）
  - 側柱の {"heading": "用語", "glossary": true} は、本文の用語ホバーのうち
    **本文で2回以上現れた語だけ**を正本の説明で並べる（1語も無ければ塊ごと出さない）

節を一覧（sections）で書くと、**見出し・番号・順番・同じ部品の繰り返し**が自由になる。
書き忘れた部品は末尾に自動で足すので、検品証は落ちない。
2026-10-09：節の項目に "asks":[1, "Q2"] を書くと、その節の見出しに「→ Q1」「→ Q2」の飛び先が付く
（判断の節の問いの番号＝上から数えた通し番号。1・"1"・"Q1" のどれでも書ける。sections の一覧の
形でだけ効く）。

2026-10-09（試問の費用を下げる）：機械で済む検査はこの道具が先に済ませる。
  組む前＝図の記号が無い（icon が記号の正本に無い）箱は**組み立てを止める**（終了コード2）。
         図番号の重複・対の無い **・asks の形は警告だけ（止めはしない）。
  組んだ後＝図の下の注意・絵の欠け・空の強調・本文に残った **・飛び先切れを警告だけで知らせる。
  書き出し＝<name>.html・<name>-artifact.html のほかに、画像・図・script・style を外した
         <name>-text.txt（文字だけの版）を同じ置き場へ書く。判断の頁の試問はこの文字だけの版を読ませる。

2026-10-09（指摘と添削の作り込み）：
  - 原稿の頁＝sections に部品 "manuscript" を置くと、原稿（Markdown）を頁に載せ、利用者がその上に
    指摘を打つ・直す。path は定義の置き場でなく**プロジェクトの根からの相対**（絶対でもよい）。
      {"component":"manuscript","label":"原稿",
       "content":{"path":"docs/intro.md","label":"intro-01","mode":"shiteki"}}
    mode は "shiteki"（指摘＝既定）か "tensaku"（添削）。原稿は UTF-8・800KB まで・節は1頁に1つ。
    読めなければ組み立てを止める（終了コード2）。頁の番号 #N は原稿のブロック（空行区切り・見出し・
    表・コードなど）の通し番号で、回答文の番号と同じ。文字だけの版の行頭にも同じ #N が付く。
    原稿の頁で欠けた部品（要約・手順・具体例・現在地・図・詳細・用語・根拠・判断）は、短い既定で
    この道具が足して1行ずつ知らせる。⚠️overview（一言でいうと）だけは書き手の責任＝足さない。
  - "review"（content の欄）＝頁に載せる赤ペンの script："none"｜"shiteki"｜"tensaku"｜"both"。
    説明の頁の既定は "both"（指摘と添削の両方・REVIEW_DEFAULT）＝読むために押した所で板は開かず、
    画面の右下の帯で「指摘する」「直す」を入れたときだけ動く。{"mode":"both"} の書き方でもよい。
    原稿の頁は書かなければ原稿の mode の役割だけ（足りない役割は必ず足す）。
  - 判断の選択肢に "withdrawn": true か "withdrawn": "理由" を書くと、選べない取り消し線の行として
    残る（案を取り下げた経緯を見せる）。取り下げは「実質1択」「文字だけ」の数から外れ、
    生きた選択肢が1つになると「取り下げで残り1つ」と警告する（止めはしない）。
  - 図の箱に "asks":[1,2]（1・"Q1"・"1/2" も可）を書くと、箱の角に赤い「Q1」の番号札が付く
    （押すと判断欄の問いへ飛ぶ）。1行記法なら A(asks=1/2)。読めない値は警告する。

側柱（頁全体の2段組み）＝content に `"rail": [ {塊}, … ]` を足すと、
広い画面（1100px以上）で本文の右に添え物が立つ。⚠️**側柱は節ではない**
（部品の目印を持たない）＝節そのものは横に並べない、という裁定を守るための形。

見出しが**別の部品の言葉**を借りていたら組み立てを止める（`visual/section_labels.py`）。
止まるのは借用・空の節・見出しの重複・番号の重複の4つだけで、意味の一致は見ていない。

componentごとの書き方＝どれも「見出し：本文」を改行で並べるだけ。
evidenceだけ「種類：内容｜出所」の3つ組にする（出所を空にすると検査で落ちる）。
"""
import hashlib
import io
import json
import os
import sys
from collections.abc import Mapping
from html import unescape
from html.parser import HTMLParser

NL = chr(10)
HERE = os.path.dirname(os.path.abspath(__file__))
CLAUDE_DIR = os.path.dirname(HERE)
HOOKS_DIR = os.path.join(CLAUDE_DIR, "hooks")
if HOOKS_DIR not in sys.path:
    sys.path.insert(0, HOOKS_DIR)

from visual.artifact_inspection import inspect_artifact_html  # noqa: E402
from visual.contracts import ExplanationPlan, HookEnvelope  # noqa: E402
from visual.entrypoint import _project_hash as project_hash_of  # noqa: E402
from visual.glossary import load_glossary_snapshot  # noqa: E402
from visual.paths import artifact_root as _artifact_root_for  # noqa: E402
from visual.paths import glossary_paths as _glossary_paths_for  # noqa: E402
from visual.policy import load_policy as _load_policy  # noqa: E402
from visual.receipts import (  # noqa: E402
    build_receipt,
    describe_skip,
    external_dependency_reason,
    validate_receipt,
)
from visual.render_components import LABELS as COMPONENT_LABELS  # noqa: E402
from visual.render_components import render_components  # noqa: E402
from visual.section_labels import check_sections  # noqa: E402
from visual.state import StateStore  # noqa: E402
from visual.turn_marker import read_turn_marker  # noqa: E402
from visual.visual_smoke import run_visual_smoke  # noqa: E402

# 2026-10-09：記号の正本は visual.icons の ICON_NAMES。取り込めなかったときは記号の検査だけ飛ばす
# （検査の道具の不具合で頁が組めなくならないように）。1行記法の変換器も同じ扱い。
try:
    from visual.icons import ICON_NAMES as _ICON_NAMES  # noqa: E402
except Exception:  # noqa: BLE001
    _ICON_NAMES = None
try:
    from visual.diagram_dsl import parse_diagram_text as _parse_diagram_text  # noqa: E402
except Exception:  # noqa: BLE001
    _parse_diagram_text = None
# 2026-10-09（指摘と添削の作り込み）：原稿の頁の分割・描画は visual/markdown_lite.py。赤ペンの script の
# 正本は visual/review_scripts.py（まだ無い環境では、役割の正規化だけこの道具の控えを使う）。
from visual.markdown_lite import count_blocks as _count_blocks  # noqa: E402
from visual.markdown_lite import normalize_newlines as _normalize_newlines  # noqa: E402

try:
    from visual.review_scripts import normalize_mode as _review_normalize_mode  # noqa: E402
except ImportError:
    _review_normalize_mode = None

# 2026-09-25：Codexの依頼の受付が残す印は、この時間より古ければ使わない
# （visual/turn_marker.py の既定と揃える）。
CODEX_TURN_MAX_AGE_SECONDS = 21600
# 検品の記録に使う上限バイト数。Policy既定（2097152）と揃える＝
# render_page.py はPolicyを読まないのでここに複製する。
RECEIPT_MAX_ARTIFACT_BYTES = 2_097_152
RECEIPT_TTL_SECONDS = 86400

# 2026-10-09（利用者の選択＝説明の頁の既定は指摘と添削の両方）：定義に review が無いときに入れる値。
# "none"｜"shiteki"｜"tensaku"｜"both"。レンダラー（render_components）の既定は none のまま＝
# 既存の試験と頁を変えない。この道具だけが既定を入れる。原稿の頁は原稿の mode の役割だけ。
REVIEW_DEFAULT = "both"
REVIEW_MODES = ("none", "shiteki", "tensaku", "both")
MANUSCRIPT_MODES = ("shiteki", "tensaku")
# 頁には原稿が2通り（見せる版と textarea）入る。記号の多い原稿で約3.4倍＝800KB でも頁は 3MB に収まる（上限 4MB）。
MANUSCRIPT_MAX_BYTES = 800_000

# 応答の言葉で後から要求されうる部品の全部。頁は既定でこれを全部入れる。
ALL_COMPONENTS = ("overview", "summary", "walkthrough", "examples", "progress",
                  "visual", "decision", "evidence", "glossary", "details")


def _default_project_root():
    """`--project-root` が無い時の既定値（2026-09-25）。

    優先順位＝①環境変数 CLAUDE_PROJECT_DIR（フック経由で走っている時に付く）
    ②今の作業フォルダから上へ辿って `.claude/visual-hook-policy.json` がある場所
    ③従来どおり＝この道具の置き場（`.claude/scripts`）の親の親。
    ⚠️③まで落ちた場合、CLAUDE_DIR の親を返すので、直置きのこのリポジトリで
      引数なしで走らせた時の結果は今と1バイトも変わらない。
    """
    env_root = os.environ.get("CLAUDE_PROJECT_DIR")
    if env_root and os.path.isdir(env_root):
        return os.path.abspath(env_root)
    current = os.path.abspath(os.getcwd())
    while True:
        candidate = os.path.join(current, ".claude", "visual-hook-policy.json")
        if os.path.isfile(candidate):
            return current
        parent = os.path.dirname(current)
        if parent == current:
            break
        current = parent
    return os.path.dirname(CLAUDE_DIR)


def _approved_root_for(project_root=None):
    """検品証を作ってよい置き場（承認済みの置き場）を、プロジェクトのpolicyから決める
    （2026-09-25）。

    入れるもの＝project_root（省くと `_default_project_root()`）。返すもの＝Pathの文字列。
    プロジェクトの `.claude/visual-hook-policy.json` の `local_artifact_root`
    （無ければ既定＝`%TEMP%/<branding.ARTIFACT_DIR_NAME>`）を
    `visual/paths.py` の `artifact_root()` で実際の場所へ展開する。
    ⚠️このリポジトリの policy は `local_artifact_root` に既定と同じ値
      （`%TEMP%/<branding.ARTIFACT_DIR_NAME>`）を明示しているので、
      結果はこのリポジトリでの従来どおりの場所と1バイトも変わらない
      （試験 `test_branding_portability.py` で確かめる）。
    """
    root = project_root if project_root is not None else _default_project_root()
    policy_path = os.path.join(str(root), ".claude", "visual-hook-policy.json")
    policy = _load_policy(policy_path)
    return str(_artifact_root_for(policy.local_artifact_root))


# 検品証を作ってよい置き場。ここ以外に書くとフックが黙って検査を見送る。
# ⚠️モジュール読み込み時の既定値（stress_page.py 等、project_root を渡さずに
#   `rp.APPROVED_ROOT` を直接参照する既存コードとの後方互換のためだけに残す）。
#   project_root ごとに変わりうる値が要る場所は、必ず `_approved_root_for(project_root)`
#   を呼び直す（`build()`・`record_codex_receipt()`・`main()` はそうしている）。
APPROVED_ROOT = _approved_root_for(None)


def _glossary(project_root=None):
    """用語集を読む。project_root を省くと、このリポジトリでの従来どおりの
    3パス（`~/.claude/glossary-shared.md`・`CLAUDE_DIR/glossary-shared.md`・
    `CLAUDE_DIR/glossary.md`）を使う＝呼び出し側の後方互換を保つ。
    """
    root = project_root if project_root is not None else _default_project_root()
    home_shared, mirror, project_specific = _glossary_paths_for(root, CLAUDE_DIR)
    return load_glossary_snapshot(home_shared, mirror, project_specific)


def _between(text, start, end):
    """索引で切り出す。⚠️正規表現を使わない（この repo の決まり）。"""
    i = text.find(start)
    j = text.find(end, i + len(start))
    if i < 0 or j < 0:
        raise ValueError("見つからない: " + start)
    return text[i:j + len(end)]


def to_artifact_shape(html):
    """完全な1文書を、Artifactの器に入る形（title・style・本文・script）へ削る。

    入れるもの＝レンダラーの出力。返るもの＝publishにそのまま渡せる文字列。
    ⚠️目印（data-component 等）は body の中にあるので、検査に効く部分は失われない。
    """
    # Artifact用HTMLをローカルHTTPでも直接開けるようにする。配信側が
    # text/html だけを返す場合、宣言を落とすと日本語が誤って解釈される。
    charset = '<meta charset="utf-8">'
    if charset not in html:
        raise ValueError("UTF-8の宣言が見つからない")
    title = _between(html, "<title>", "</title>")
    style = _between(html, "<style>", "</style>")
    body_start = html.find("<body>")
    body_end = html.rfind("</body>")
    if body_start < 0 or body_end < 0:
        raise ValueError("body が見つからない")
    body = html[body_start + len("<body>"):body_end]
    return NL.join([charset, title, style, body, ""])


def content_of(spec):
    """定義の content を返す。結論の見出し（headline）は content の中の欄。

    2026-10-01：⚠️title と並べて定義の上の段に書いても効くようにする
    （撮影で確かめたら、上の段に書いた見出しが黙って無視されていた）。
    """
    content = spec["content"]
    if spec.get("headline") and isinstance(content, dict) and not content.get("headline"):
        content = dict(content, headline=spec["headline"])
    return content


# ---------------------------------------------------------------------------
# 2026-10-09（指摘と添削の作り込み）：原稿の頁と赤ペンの script の既定。
# 定義の中の原稿の節（component が manuscript）を読み込んで辞書に置き換え、欠けた部品を短い既定で足し、
# 赤ペンの役割（review）を決める。⚠️どれも定義の写しを返す（元の定義の辞書は変えない）。
# ---------------------------------------------------------------------------
class ManuscriptError(ValueError):
    """原稿を読めない・使えないときの理由（1行）。main が止める理由として出す。"""


_MISSING = object()
_MODE_ALIASES = {"指摘": "shiteki", "添削": "tensaku", "両方": "both", "なし": "none"}
_MODE_WORDS = {"shiteki": "指摘", "tensaku": "添削"}


def _manuscript_entries(content):
    """原稿の節の置き場を返す。返るもの＝(sections の添字の一覧, 上位の鍵 manuscript があるか)。"""
    indexes = []
    sections = content.get("sections")
    if isinstance(sections, (list, tuple)):
        for index, entry in enumerate(sections):
            if isinstance(entry, Mapping) and str(entry.get("component", "")).strip() == "manuscript":
                indexes.append(index)
    return indexes, content.get("manuscript") is not None


def _manuscript_mode(value):
    """原稿の mode を shiteki か tensaku にする（日本語の別名も可・無ければ shiteki）。"""
    if value is None or str(value).strip() == "":
        return "shiteki"
    text = _MODE_ALIASES.get(str(value).strip(), str(value).strip().lower())
    if text not in MANUSCRIPT_MODES:
        raise ManuscriptError("原稿の mode は shiteki（指摘）か tensaku（添削）: %r" % (value,))
    return text


def _shown_path(path, project_root):
    """頁に書く原稿の場所。プロジェクトの中なら相対（/ 区切り）・外ならファイル名だけ
    （公開した頁に利用者の机の絶対パスを残さない）。"""
    absolute = os.path.abspath(path)
    root = os.path.abspath(str(project_root)) if project_root else ""
    if root:
        try:
            if os.path.commonpath([absolute, root]) == root:
                return os.path.relpath(absolute, root).replace(os.sep, "/")
        except ValueError:
            pass
    return os.path.basename(absolute)


def _read_manuscript(spec_value, project_root):
    """原稿の節の中身（path・label・mode）を読み、約束の辞書にする。読めなければ ManuscriptError。

    返るもの＝{"markdown","label","mode","source_path","sha256","eol"}。markdown は LF にそろえた全文、
    sha256 は元のファイルのバイトの値、eol は元のファイルの改行（lf か crlf）。
    """
    if isinstance(spec_value, Mapping) and isinstance(spec_value.get("markdown"), str):
        return dict(spec_value)  # 読み込み済み（2度目の呼び出し）
    if isinstance(spec_value, str):
        spec_value = {"path": spec_value}
    if not isinstance(spec_value, Mapping) or not str(spec_value.get("path", "") or "").strip():
        raise ManuscriptError("原稿の節に path が無い（content に {\"path\":\"docs/intro.md\"} を書く）")
    given = str(spec_value["path"]).strip()
    candidates = [given] if os.path.isabs(given) else [
        os.path.join(str(project_root or ""), given), os.path.join(os.getcwd(), given),
    ]
    found = next((c for c in candidates if os.path.isfile(c)), None)
    if found is None:
        raise ManuscriptError("原稿が見つからない: %s（プロジェクトの根からの相対か絶対で書く）" % given)
    size = os.path.getsize(found)
    if size > MANUSCRIPT_MAX_BYTES:
        raise ManuscriptError("原稿が大きすぎる: %d バイト（上限 %d）" % (size, MANUSCRIPT_MAX_BYTES))
    with io.open(found, "rb") as handle:
        raw = handle.read()
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        raise ManuscriptError("原稿を UTF-8 として読めない: %s" % given) from None
    if "\x00" in text:
        raise ManuscriptError("原稿に NUL 文字がある＝テキストの原稿ではない: %s" % given)
    crlf = text.count("\r\n")
    eol = "crlf" if crlf and crlf >= text.count("\n") - crlf else "lf"
    markdown = _normalize_newlines(text)
    if _count_blocks(markdown) == 0:
        raise ManuscriptError("原稿にブロックが無い（空か空白だけ）: %s" % given)
    label = str(spec_value.get("label", "") or "").strip() or os.path.splitext(os.path.basename(found))[0]
    return {
        "markdown": markdown,
        "label": label,
        "mode": _manuscript_mode(spec_value.get("mode")),
        "source_path": _shown_path(found, project_root),
        "sha256": hashlib.sha256(raw).hexdigest(),
        "eol": eol,
    }


def resolve_manuscripts(spec, project_root=None):
    """定義の原稿の節を読み込み、辞書に置き換えた**定義の写し**を返す（無ければ spec をそのまま返す）。

    原稿の節＝sections の component が manuscript の項目（content が無ければ content["manuscript"]）。
    ⚠️原稿の節は1頁に1つ（textarea の id が重なるため）。読み込み済みの定義に何度かけても同じ。
    """
    content = spec.get("content") if isinstance(spec, Mapping) else None
    if not isinstance(content, Mapping):
        return spec
    indexes, top_level = _manuscript_entries(content)
    if not indexes and not top_level:
        return spec
    if len(indexes) > 1:
        raise ManuscriptError("原稿の節は1頁に1つだけ（%d 個ある）" % len(indexes))
    content2 = dict(content)
    if indexes:
        sections = list(content["sections"])
        entry = dict(sections[indexes[0]])
        value = entry.get("content")
        if value is None:
            value = content.get("manuscript")
        entry["content"] = _read_manuscript(value, project_root)
        sections[indexes[0]] = entry
        content2["sections"] = sections
        if content2.get("manuscript") is not None:
            content2["manuscript"] = entry["content"]
    else:
        content2["manuscript"] = _read_manuscript(content["manuscript"], project_root)
    spec2 = dict(spec)
    spec2["content"] = content2
    components = list(spec.get("components", ()))
    if not indexes and "manuscript" not in components:
        components.append("manuscript")
        spec2["components"] = components
    return spec2


def _manuscript_of(content):
    """読み込み済みの原稿の辞書を返す（無ければ None）。"""
    if not isinstance(content, Mapping):
        return None
    sections = content.get("sections")
    if isinstance(sections, (list, tuple)):
        for entry in sections:
            if isinstance(entry, Mapping) and str(entry.get("component", "")).strip() == "manuscript":
                value = entry.get("content")
                if value is None:
                    value = content.get("manuscript")
                if isinstance(value, Mapping) and isinstance(value.get("markdown"), str):
                    return value
    value = content.get("manuscript")
    if isinstance(value, Mapping) and isinstance(value.get("markdown"), str):
        return value
    return None


def _manuscript_stats(manuscript):
    """原稿の行数・文字数・ブロック数（頁の要約・根拠・詳細に書く実測）。"""
    text = manuscript["markdown"]
    lines = text.count("\n") + (0 if (not text or text.endswith("\n")) else 1)
    return lines, len(text), _count_blocks(text)


def _manuscript_defaults(manuscript):
    """原稿の頁で欠けた部品の既定の中身（短く）。返るもの＝{部品名: 中身}。"""
    lines, chars, blocks = _manuscript_stats(manuscript)
    mode = manuscript["mode"]
    word = _MODE_WORDS[mode]
    label = manuscript["label"]
    path = manuscript["source_path"]
    sha8 = manuscript["sha256"][:8]
    verb = "指摘を打つ" if mode == "shiteki" else "直す"
    paste = "画面の回答文を会話へ貼り付ける" if mode == "shiteki" else "画面の回答文（完成形つき）を会話へ貼り付ける"
    if mode == "shiteki":
        walk = (
            "読む：原稿を上から読む。行頭の番号 #N が回答に出るブロックの番号\n"
            "指摘する：気になるブロックを押し、札とひとことを付ける\n"
            "貼る：" + paste
        )
        examples = (
            "指摘の例：ブロック 3 に札「短くする」を付け、ひとことで「1文にする」と書く\n"
            "良い所の例：ブロック 5 に札「ここは良い」を付け、残してよい所も伝える"
        )
        glossary = (
            "ブロック：原稿を空行などで区切った1かたまり。頁の番号 #N はその順番\n"
            "札：指摘の種類を表す短い印（削る・短くする・言い換える など）"
        )
    else:
        walk = (
            "読む：原稿を上から読む。段落の番号は回答に出る番号と同じ\n"
            "直す：段落を押して書き換える。差分と完成形のタブで確かめる\n"
            "貼る：" + paste
        )
        examples = (
            "直しの例：段落 3 の「と思われる」を「である」に書き換える\n"
            "削除の例：段落 7 を削除する（取り消し線で残る）"
        )
        glossary = (
            "ブロック：原稿を空行などで区切った1かたまり。頁の番号 #N はその順番\n"
            "完成形：直した後の原稿の全文（添削の回答に入る）"
        )
    return {
        "summary": (
            "Goal：原稿「%s」を読んで、%s\n"
            "Now：原稿 %d 行・%d 文字・%d ブロックを頁に載せた\n"
            "Next：%sを入れて、画面の回答文を会話へ貼り付ける" % (label, verb, lines, chars, blocks, word)
        ),
        "walkthrough": walk,
        "examples": examples,
        "progress": (
            "いま：原稿を読み込んだ（%d ブロック）\n次：あなたが%sを入れて回答文を貼る" % (blocks, word)
        ),
        "visual": {
            "diagram_text": (
                "原稿 -> %s : 気になるブロックを押す\n%s -> 回答文 : 札や書き換えが集まる\n"
                "回答文 -> 会話 : 貼り付ける" % (word, word)
            )
        },
        "details": [{
            "summary": "原稿のファイル情報",
            "text": "場所：%s ／ 行数：%d ／ 文字数：%d ／ ハッシュの先頭8桁：%s ／ モード：%s"
                    % (path, lines, chars, sha8, word),
        }],
        "glossary": glossary,
        "evidence": "実測：原稿 %d 行 %d 文字 %d ブロック｜%s" % (lines, chars, blocks, path),
        "decision": {"groups": [
            {"legend": "直した後の扱い", "kind": "radio", "options": [
                {"label": "反映して続ける", "recommended": True,
                 "pros": "入れた%sをそのまま原稿に反映し、次の作業へ進める" % word,
                 "cons": "反映の結果をもう一度見ずに進む"},
                {"label": "もう一往復見せる",
                 "pros": "反映した原稿を見て、もう一度%sを入れられる" % word,
                 "cons": "確認の往復が1回増える"},
            ]},
            {"legend": "自由記述", "kind": "free", "placeholder": "直しの方針・追加の条件など"},
        ]},
    }


def _manuscript_frame_defaults(spec):
    """原稿の頁で欠けた部品を短い既定で埋める。返るもの＝(定義の写し, 知らせの行の一覧)。止めない。

    対象＝summary・walkthrough・examples・progress・visual・details・glossary・evidence・decision。
    部品が「節の一覧にある」か「content にあり components に載っている」なら足さない。
    ⚠️overview（一言でいうと）は書き手の責任＝足さず、無ければ強く警告する（無いと検品で落ちる）。
    ⚠️原稿の無い定義は何もしない（そのまま返す）。
    """
    content = spec.get("content") if isinstance(spec, Mapping) else None
    manuscript = _manuscript_of(content)
    if manuscript is None:
        return spec, []
    components = list(spec.get("components", ()))
    content2 = dict(content)
    placed = set()
    sections = content.get("sections")
    if isinstance(sections, (list, tuple)):
        for entry in sections:
            if not isinstance(entry, Mapping):
                continue
            name = str(entry.get("component", "")).strip()
            value = entry.get("content")
            if value is None:
                value = content.get(name)
            if name and value is not None:
                placed.add(name)
    notes = []
    defaults = _manuscript_defaults(manuscript)
    for name in ALL_COMPONENTS:
        if name == "overview":
            if "overview" not in placed and not content.get("overview"):
                notes.append(
                    "⚠️overview（%s）が無い＝書き手が書く部品で、この道具は足さない。"
                    "無いと検品で落ちる・差し戻される" % COMPONENT_LABELS["overview"]
                )
            continue
        if name in placed:
            continue
        existing = content2.get(name)
        if existing and name in components:
            continue
        label = COMPONENT_LABELS.get(name, name)
        if existing:
            components.append(name)
            notes.append("ⓘ 原稿の頁＝%s（%s）が components に無かったので足した" % (name, label))
            continue
        content2[name] = defaults[name]
        if name not in components:
            components.append(name)
        notes.append("ⓘ 原稿の頁の既定で足した: %s（%s）" % (name, label))
    spec2 = dict(spec)
    spec2["content"] = content2
    spec2["components"] = components
    return spec2, notes


def _review_mode_of(value):
    """content["review"]（文字列か {"mode": …}）を none｜shiteki｜tensaku｜both にする。読めなければ none。"""
    if isinstance(value, Mapping):
        value = value.get("mode")
    if _review_normalize_mode is not None:
        try:
            return _review_normalize_mode(value)
        except Exception:  # noqa: BLE001 - 相手の不具合で頁が組めなくならないように
            pass
    text = "" if value is None else str(value).strip()
    text = _MODE_ALIASES.get(text, text.lower())
    return text if text in REVIEW_MODES else "none"


def _roles_of(mode):
    return {"shiteki": ("shiteki",), "tensaku": ("tensaku",), "both": ("shiteki", "tensaku")}.get(mode, ())


def _mode_of_roles(roles):
    if "shiteki" in roles and "tensaku" in roles:
        return "both"
    return "shiteki" if "shiteki" in roles else ("tensaku" if "tensaku" in roles else "none")


def apply_review_default(spec):
    """content に review を決めて入れる。返るもの＝定義の写し（変えないときは同じ定義）。

    review が無い＝説明の頁は REVIEW_DEFAULT（both）・原稿の頁は原稿の mode の役割だけ。
    あるとき＝その値のまま。ただし原稿の頁で原稿の mode の役割が欠けていたら足す（必ず含める）。
    """
    content = spec.get("content") if isinstance(spec, Mapping) else None
    if not isinstance(content, Mapping):
        return spec
    manuscript = _manuscript_of(content)
    current = content.get("review", _MISSING)
    if current is _MISSING:
        new = manuscript["mode"] if manuscript else REVIEW_DEFAULT
    else:
        mode = _review_mode_of(current)
        roles = set(_roles_of(mode))
        if manuscript:
            roles.add(manuscript["mode"])
        new_mode = _mode_of_roles(roles)
        if new_mode == mode:
            return spec
        new = dict(current, mode=new_mode) if isinstance(current, Mapping) else new_mode
    content2 = dict(content)
    content2["review"] = new
    spec2 = dict(spec)
    spec2["content"] = content2
    return spec2


def prepare_spec(spec, project_root=None):
    """定義を組む前の下ごしらえ。返るもの＝(定義の写し, 知らせの行の一覧)。

    順＝原稿の読み込み → 欠けた部品の既定 → 赤ペンの役割。原稿が読めなければ ManuscriptError。
    何度かけても同じ結果（build からも呼ぶ）。
    """
    spec = resolve_manuscripts(spec, project_root)
    spec, notes = _manuscript_frame_defaults(spec)
    spec = apply_review_default(spec)
    manuscript = _manuscript_of(spec.get("content"))
    if manuscript is not None:
        notes.append(
            "ⓘ 原稿の頁: 「%s」（%s・%s）の赤ペンは %s" % (
                manuscript["label"], manuscript["source_path"], _MODE_WORDS[manuscript["mode"]],
                _review_mode_of(spec["content"].get("review")),
            )
        )
    return spec, notes


def build(spec, project_root=None):
    """定義から頁を組み、承認済みの置き場へ2つ書き出す。返るもの＝(完全版, 器用) のpath。"""
    # 2026-10-09：原稿の節の読み込みと赤ペンの既定（main が先に済ませていれば何も変わらない）。
    spec = resolve_manuscripts(spec, project_root)
    spec = apply_review_default(spec)
    plan = ExplanationPlan(
        audience="project_novice",
        depth=spec.get("depth", "deep"),
        components=tuple(spec["components"]),
        reason_codes=tuple(spec.get("reasons", ())),
        provisional=False,
        should_continue=False,
        delivery="local_html",
        publish_policy=spec.get("publish", "always"),
    )
    _, entries = _glossary(project_root)
    content = content_of(spec)
    html = render_components(
        plan, title=spec["title"], content=content, glossary_entries=entries
    )
    approved_root = _approved_root_for(project_root)
    os.makedirs(approved_root, exist_ok=True)
    full = os.path.join(approved_root, spec["name"] + ".html")
    shaped = os.path.join(approved_root, spec["name"] + "-artifact.html")
    io.open(full, "w", encoding="utf-8", newline=NL).write(html)
    io.open(shaped, "w", encoding="utf-8", newline=NL).write(to_artifact_shape(html))
    return full, shaped


def check(path, components, project_root=None):
    """頁を検査する。返るもの＝結果の辞書（合格なら ok=True）。"""
    _, entries = _glossary(project_root)
    text = io.open(path, encoding="utf-8", errors="replace").read()
    ins = inspect_artifact_html(
        text, required_components=tuple(components), glossary_entries=entries
    )
    smoke = run_visual_smoke(path, timeout_seconds=40)
    # 2026-09-26：公開時の検品の記録（receipts.build_receipt）と同じ「外部の依存」の判定を
    # 合否に含める。以前はここに無く、この道具が合格と言った頁が、公開すると記録を作れなかった。
    external = external_dependency_reason(text)
    # 2026-09-26（見やすさ V1）：表示検査が数えたコントラスト不足（止めはしない＝知らせるだけ）。
    viewports = (getattr(smoke, "metrics", None) or {}).get("viewports") or {}
    low_contrast = max((int(v.get("lowContrast") or 0) for v in viewports.values() if isinstance(v, dict)), default=0)
    min_contrast = min((float(v.get("minContrast")) for v in viewports.values()
                        if isinstance(v, dict) and v.get("minContrast") is not None), default=None)
    return {
        "low_contrast": low_contrast,
        "min_contrast": min_contrast,
        "path": path,
        "bytes": len(text.encode("utf-8")),
        "ok": bool(ins.ok) and smoke.status == "pass" and external is None,
        "external_dependency": [external] if external else [],
        "inspection_ok": bool(ins.ok),
        "missing_components": list(ins.missing_components),
        "missing_decision_parts": list(ins.missing_decision_parts),
        "unwrapped": list(ins.unwrapped_identifiers),
        "unknown": list(ins.unknown_identifiers),
        "missing_sources": list(ins.missing_evidence_sources),
        "errors": list(ins.errors),
        "smoke": smoke.status,
        "smoke_errors": list(smoke.errors),
    }


def _codex_env_session_id():
    """CODEX_SESSION_ID／CODEX_THREAD_ID があれば返す。無ければ空文字。"""
    for key in ("CODEX_SESSION_ID", "CODEX_THREAD_ID"):
        value = os.environ.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def record_codex_receipt(
    path,
    components,
    smoke_status,
    smoke_errors,
    project_root,
    state_path,
    local_root=None,
):
    """`--runtime codex` の時だけ呼ぶ。完全版の頁について検品の記録を1件残す。

    入れるもの＝完全版のpath・要る部品・自分で走らせた表示検査の結果
    （status・errors）・プロジェクトの根・stateの保存先・置き場
    （既定＝`_approved_root_for(project_root)`）。
    返るもの＝人に見せる1行（残せた／残さなかった、どちらも）。

    ⚠️安全の掟＝この関数を呼ぶかどうかは呼び出し側（main の --runtime codex）だけで
      決める。ここは「印があれば記録する」だけで、環境変数の有無だけを見て自動で
      記録を作る経路は持たない（--runtime codex が無いターンからは呼ばれない）。
    """
    root = local_root if local_root is not None else _approved_root_for(project_root)
    project_hash = project_hash_of(os.path.abspath(str(project_root)))
    env_session_id = _codex_env_session_id()
    marker = read_turn_marker(
        root,
        "codex",
        project_hash,
        session_id=env_session_id or None,
        max_age_seconds=CODEX_TURN_MAX_AGE_SECONDS,
    )
    if marker is None:
        which = ("環境変数のセッション(%s)" % env_session_id) if env_session_id else "最新"
        return "検品の記録: 残さなかった（%sの印が無い、または古い）" % which
    session_id = str(marker.get("session_id", ""))
    turn_id = str(marker.get("turn_id", ""))
    state = StateStore(state_path)
    saved_plan = state.load_plan(
        runtime="codex",
        project_hash=project_hash,
        session_id=session_id,
        turn_id=turn_id,
    )
    required_components = (
        tuple(saved_plan.components) if saved_plan is not None else tuple(components)
    )
    # 2026-09-25：受け取った project_root の用語集を使う（以前は今の作業フォルダから
    # 辿った既定の根＝--project-root と作業フォルダが違うと、フック側の用語集とずれて
    # 記録が無効になった。公開版の試験を別のリポジトリの中から走らせて発見）。
    glossary, entries = _glossary(project_root)
    envelope = HookEnvelope(
        schema_version=1,
        runtime="codex",
        runtime_version="",
        event="PostToolUse",
        project_root=str(project_root),
        profile_id="",
        session_id=session_id,
        turn_id=turn_id,
        invocation_id="",
        user_message="",
        response_text="",
        response_sha256="",
        transcript_path="",
        changed_paths=(),
        stop_hook_active=False,
        attempt=0,
        capabilities=frozenset({"can_receipt"}),
        valid_for_state=True,
    )
    try:
        receipt = build_receipt(
            path,
            envelope=envelope,
            glossary=glossary,
            glossary_entries=entries,
            local_root=root,
            previewed=True,
            max_artifact_bytes=RECEIPT_MAX_ARTIFACT_BYTES,
            required_components=required_components,
            visual_smoke_result={"status": smoke_status, "errors": list(smoke_errors)},
        )
    except (OSError, ValueError) as exc:
        return describe_skip(path, exc, root)
    state.save_receipt(
        project_hash=project_hash, receipt=receipt, ttl_seconds=RECEIPT_TTL_SECONDS
    )
    passed = validate_receipt(
        receipt,
        glossary,
        local_root=root,
        max_artifact_bytes=RECEIPT_MAX_ARTIFACT_BYTES,
        required_components=required_components,
    )
    prefix = "" if env_session_id else "環境変数が無いので最新の印を使った ／ "
    return "%s検品の記録: codex の会話 %s の回 %s に残した（合格=%s）" % (
        prefix, session_id[:8], turn_id[:8], passed,
    )


def without_manuscript(text):
    """頁のHTMLから、原稿の節（`<section data-component="manuscript"…>` から対の閉じまで）を外す。

    2026-10-09：原稿は利用者の文章そのもの＝部品の濃さ・空の強調・本文に残った ** の検査の対象ではない。
    入れ子の section があっても、開きと閉じを数えて対の閉じまでを外す。節が無ければそのまま返す。
    """
    start = text.find('<section data-component="manuscript"')
    if start < 0:
        return text
    depth = 0
    position = start
    while True:
        opened = text.find("<section", position)
        closed = text.find("</section>", position)
        if closed < 0:
            return text[:start]
        if 0 <= opened < closed:
            depth += 1
            position = opened + len("<section")
        else:
            depth -= 1
            position = closed + len("</section>")
            if depth <= 0:
                return text[:start] + text[position:]


def density(text):
    """組み上がった頁で、どの部品がいくつ使われたかを数える。

    入れるもの＝完全版のHTML。返るもの＝`(部品名, 個数)` の並び。
    ⚠️CSSの定義に同じ語が出るので、本文（`<body>` 以降）だけを数える。
    ⚠️原稿の節（部品 manuscript）は数えない（利用者の原稿の表や引用が部品の濃さに混ざらないように）。
    """
    start = text.find("<body>")
    body = without_manuscript(text[start:] if start >= 0 else text)
    marks = (
        ("図解", "dia-wrap"),
        ("カード", "card-stack"),
        ("段組み", 'class="cols"'),
        ("タイル", 'class="tiles"'),
        ("色札", 'class="badge'),
        ("注意書き", 'class="note'),
        ("表", "<table>"),
        ("目次", 'class="toc"'),
        ("段階の判定", "scale-row"),
        # 2026-09-08：担当A追加の4部品（差分・数値の図・数式・引用）の計数。
        ("差分", 'class="log diff"'),
        ("数値の図", "chart-wrap"),
        ("数式", 'class="formula"'),
        ("引用", "<blockquote>"),
        # 2026-09-10（担当B）：箱と矢印の図の根治とあわせて配線した9個の新しい部品。
        ("取り込みSVG", "svg-in"),
        ("画像", 'class="img-figure"'),
        ("時間軸", 'class="tl"'),
        ("四象限", 'class="quad"'),
        ("集合", 'class="venn"'),
        ("流れ", 'svg class="flow"'),
        ("採点格子", 'class="score"'),
        ("前後切替", 'class="compare"'),
        ("吹き出し", 'class="callout-legend"'),
        # 2026-10-01（ユーザー承認の P2・P4・P7・P9）：手書きのHTMLとの比べから足した部品。
        ("積み上げ棒", 'class="stack"'),
        ("大きい数字", 'class="stats"'),
        ("横並びの手順", 'class="hsteps"'),
        ("語の札", 'class="chip-groups"'),
    )
    return [(name, body.count(needle)) for name, needle in marks]


def advise_density(counts, body_bytes):
    """薄い頁に助言を返す。返るもの＝助言の行の並び（濃ければ空）。

    ⚠️止めない＝密度の正しさは中身次第で、機械には決められない。
    ⚠️目安は実測から取った＝濃い頁は色札25〜45・図解1・表5〜10、
      薄い頁は色札4〜8・図解0・目次0だった。
    """
    got = dict(counts)
    lines = []
    if body_bytes < 8000:
        return lines  # 短い頁に濃さを求めない
    if got["図解"] == 0:
        lines.append(
            "図解が0＝関係や流れがあるなら "
            '"diagram":{"nodes":[{"id":"a","num":"1","title":"名","col":0,"row":0,'
            '"text":"説明","tone":"acc"}],"edges":[{"from":"a","to":"b","label":"矢印の字"}]}'
        )
    if got["色札"] < 10:
        lines.append(
            "色札が%d個＝本文や表の判定に [[good:短い語]] [[bad:短い語]] [[warn:短い語]]。"
            "⚠️長い文を入れない（狭い画面で溢れる）" % got["色札"]
        )
    if got["表"] == 0:
        lines.append(
            "表が0＝比べるものがあるなら "
            '"table":{"head":["列A","列B"],"widths":["120px",""],'
            '"rows":[["値","値"]],"caption":"どう測ったか"}'
        )
    if got["カード"] + got["タイル"] + got["段組み"] == 0:
        lines.append(
            "カード・タイル・段組みが全部0＝どれかで塊を作る："
            '"cards":[{"badge":"印","tone":"good","title":"見出し","text":"本文",'
            '"objection":"この判定"}] / "tiles":[{"title":"名","text":"説明","tone":"warn"}]'
            ' / "columns":[{"heading":"左","text":"…"},{"heading":"右","text":"…"}]'
        )
    if got["目次"] == 0:
        lines.append("目次が0＝節が多いなら `rail` に `{\"toc\": true}` を置く")
    # 2026-09-08：担当A追加の4部品（差分・数値の図・数式・引用）の書き方の例。
    # ⚠️これ単独では「薄い頁」の判定材料にしない＝既に何か助言が出た頁でだけ添える。
    #   単独で `==0` を条件にすると、濃い頁（色札25個等）でも必ず0になるので空振りする
    #   （2026-09-01の学び＝空振りは作業を止める最悪の失敗）。
    if lines:
        if got["数値の図"] == 0:
            lines.append(
                "数値の図が0＝数の推移や比較があるなら "
                '"chart":{"kind":"line","title":"…","labels":["A","B"],'
                '"series":[{"name":"…","values":[1,2]}],"unit":"…","source":"…"}'
                "（描画係が無い・失敗した時は同じ数値を表に落とす）"
            )
        if got["数式"] == 0:
            lines.append(
                "数式が0＝定義や公式があるなら "
                '"formula":{"tex":"x^2+y^2=z^2","reading":"三平方の定理"}'
                "（対応外は原文をcodeで見せる）"
            )
        if got["差分"] == 0:
            lines.append(
                "差分が0＝コードの前後の比較があるなら "
                '"diff": "-旧い行" + NL + "+新しい行" + NL + " 変わらない行"'
            )
        # 2026-09-10（担当B）：箱と矢印の図の根治とあわせて配線した9個の新しい部品の書き方。
        # ⚠️上と同じ理由で「既に何か助言が出た頁でだけ添える」（単独では判定材料にしない）。
        if got["取り込みSVG"] == 0:
            lines.append(
                '取り込みSVGが0＝手描きのSVGがあるなら "svg":"<svg viewBox=\'0 0 100 60\'>…</svg>"'
                "（許可リストで組み直す＝scriptやonclickは自動で外れる）"
            )
        if got["画像"] == 0:
            lines.append(
                "画像が0＝スライド・写真・画面の写真があるなら "
                '"image":{"path":"…png","caption":"…","source":"…","num":"1"}'
                "（data:URIで埋め込み・実測行が根拠欄へ自動で足される）。画面をその場で撮るなら "
                '"screenshot":{"target":"http://localhost:3000","viewport":[1280,800]}'
            )
        if got["大きい数字"] == 0:
            lines.append(
                "大きい数字が0＝頁の頭に主要な数字があるなら "
                '"stats":[{"value":"38","unit":"/ 38項目","label":"名札","text":"補足","tone":"good"}]'
            )
        if got["時間軸"] == 0:
            lines.append(
                "時間軸が0＝経過や年表があるなら "
                '"timeline":{"events":[{"when":"2026","label":"…"}]}'
            )
        if got["四象限"] == 0:
            lines.append(
                "四象限が0＝2軸で位置づけるものがあるなら "
                '"quadrant":{"x_label":"…","y_label":"…","items":[{"x":0.2,"y":0.8,"label":"…"}]}'
            )
        if got["集合"] == 0:
            lines.append(
                "集合が0＝重なりや包含関係があるなら "
                '"venn":{"sets":[{"label":"A","items":["…"]},{"label":"B","items":["…"]}]}'
            )
        if got["流れ"] == 0:
            lines.append(
                "流れが0＝量を伴う流れ（人・金・件数）があるなら "
                '"flow":{"nodes":[{"id":"a","label":"…"}],"links":[{"from":"a","to":"b","value":3}]}'
            )
        if got["採点格子"] == 0:
            lines.append(
                "採点格子が0＝段階評価の一覧があるなら "
                '"score":{"max":3,"axes":[{"name":"…","level":2,"note":"…"}]}'
            )
        if got["前後切替"] == 0:
            lines.append(
                "前後切替が0＝改善の前後を並べたいなら "
                '"compare":{"before":"…","after":"…","labels":["前","後"]}'
            )
        if got["吹き出し"] == 0:
            lines.append(
                "吹き出しが0＝図や画像に注記番号を振るなら "
                '"callouts":[{"n":1,"text":"…"}]'
            )
    return lines


# 2026-10-08（判断の頁を赤ペン流に寄せた・案1）：実質1択の恐れを、組む前に知らせる。
# ⚠️止めない＝選択肢に利点があるかどうかの意味は機械には決められない。
#   ここで見るのは「推奨があるのに、推奨でない案に利点の欄も「利点」の語も無い」という形だけ。
#   利用者の実際の定義は利点／代償を why の中に「利点：…／代償：…」で書いているので、
#   why に「利点」を含む案は警告しない（pros が無くても書いた扱い）。
WARNING_LIMIT = 10
WARNING_NAME_WIDTH = 30


def _has_text(value):
    """文字列か文字列の配列に、空白以外の字が1つでもあるか。"""
    if isinstance(value, (list, tuple)):
        return any(_has_text(item) for item in value)
    return value is not None and bool(str(value).strip())


def _short(value):
    """警告の文に入れる名前。改行を畳み、長ければ切る。"""
    text = " ".join(str(value if value is not None else "").split())
    if len(text) > WARNING_NAME_WIDTH:
        return text[:WARNING_NAME_WIDTH - 1] + "…"
    return text


def _decision_bodies(content):
    """頁に出る判断の中身を、頁の文書順で返す（render_components の節の組み方に合わせる）。

    節の一覧（sections）に component が decision の節があればその content（無ければ
    content の "decision"）を順に、一覧に無ければ content の "decision" を1つ。
    """
    bodies = []
    emitted = False
    sections = content.get("sections")
    if isinstance(sections, (list, tuple)):
        for entry in sections:
            if not isinstance(entry, Mapping):
                continue
            if str(entry.get("component", "")).strip() != "decision":
                continue
            body = entry.get("content")
            if body is None:
                body = content.get("decision")
            if body is None:
                continue
            bodies.append(body)
            emitted = True
    if not emitted and content.get("decision") is not None:
        bodies.append(content["decision"])
    return bodies


def _decision_groups(value):
    """判断の中身を群の一覧に直す。⚠️render_components._decision_block と同じ規則
    （groups／旧形式の options・multi・numbers／配列・単独の値）。"""
    groups = []
    if isinstance(value, Mapping):
        raw_groups = value.get("groups")
        if isinstance(raw_groups, (list, tuple)) and raw_groups:
            groups = list(raw_groups)
        else:
            options = value.get("options", ())
            if not isinstance(options, (list, tuple)):
                options = (options,)
            if options:
                groups.append({"legend": "選択肢",
                               "kind": "checkbox" if value.get("multi") else "radio",
                               "options": list(options)})
            numbers = value.get("numbers", ())
            if isinstance(numbers, (list, tuple)) and numbers:
                groups.append({"legend": "数を入れる", "kind": "number", "options": list(numbers)})
    elif isinstance(value, (list, tuple)):
        groups = [{"legend": "選択肢", "kind": "radio", "options": list(value)}]
    else:
        groups = [{"legend": "選択肢", "kind": "radio", "options": [value]}]
    return [
        group if isinstance(group, Mapping)
        else {"legend": "選択肢", "kind": "radio", "options": [group]}
        for group in groups
    ]


def _group_rows(group, kind):
    """その群が頁に出す行（選択肢・items・options）の中身。空なら問いの番号を取らない。

    ⚠️render_components._decision_block の rows と同じ見方＝scale は items・それ以外は options。
    行が1つも無い群は <fieldset> に入力欄が無く、回答文の問いにも数えられない
    （2026-10-09：以前はここだけ数えていて、空の群があると番号が1つずれた）。
    """
    rows = group.get("items", ()) if kind == "scale" else group.get("options", ())
    if kind in ("radio", "checkbox") and isinstance(rows, (list, tuple)):
        # 2026-10-09：取り下げた選択肢（withdrawn）は選べない行＝問いの番号にも行の数にも数えない。
        rows = [row for row in rows if not _is_withdrawn(row)]
    return rows


def _is_withdrawn(option):
    """判断の選択肢が取り下げ済みか（"withdrawn": true か、理由の文字列）。辞書の選択肢だけ。"""
    if not isinstance(option, Mapping):
        return False
    value = option.get("withdrawn")
    if isinstance(value, str):
        return bool(value.strip())
    return bool(value)


def decision_option_warnings(content):
    """判断の問いが実質1択になっていないかを見て、警告の行の一覧を返す（空なら問題なし）。

    入れるもの＝頁の定義の content。見る場所＝content["decision"]（groups か旧形式の
    options）と、content["sections"] のうち component が decision の節の content。
    対象＝kind が radio／checkbox（既定 radio）の群のうち、辞書の選択肢に recommended が
    真のものが1つでもある群。その群の recommended でない選択肢で、pros が空で、
    かつ why に「利点」を含まないものを1行ずつ（文字列の選択肢は利点を書けないので必ず数える）。
    選択肢が2つ以上あって全部が文字列の群は、群ごとに1行（推奨の印も利点も付かない形）。
    scale・number・free は対象外。
    2026-10-09：取り下げた選択肢（withdrawn）は数えない（利点の有無も見ない）。生きた選択肢が1つに
    なった問いは「取り下げで残り1つ」と1行警告する（実質1択）。
    ⚠️2026-10-08（リード）：計画では文字列だけの群を対象外にしていたが、置き場の定義47本を
      測ると選択の群78のうち76が文字列だけで、警告が1件も出ない＝案1が効かない形だった。
      文字列の選択肢は render_components._decision_parts で推奨にならない（「推奨を入れる」の
      釦も効かない）ので、辞書の形へ寄せる指摘として数える。止めはしない。
    ⚠️問いの番号 Q は頁全体の通し（free の群と、選択肢・items・options が空の群は数えない
      ＝回答文の番号と同じ）。
    10行で打ち切り、残りは「ほかN件」の1行にまとめる。
    """
    lines = []
    number = 0
    for body in _decision_bodies(content):
        for group in _decision_groups(body):
            kind = (str(group.get("kind", "radio") or "radio")).lower()
            if kind == "free":
                continue
            if not _group_rows(group, kind):
                continue
            number += 1
            if kind in ("scale", "number"):
                continue
            all_options = group.get("options", ())
            if not isinstance(all_options, (list, tuple)):
                continue
            options = [o for o in all_options if not _is_withdrawn(o)]
            if len(options) == 1 and len(all_options) > 1:
                lines.append(
                    "⚠️取り下げで残り1つ（止めはしない）: Q%d「%s」＝生きた選択肢が「%s」だけ"
                    "＝実質1択。問いにする意味があるか見直す"
                    % (number, _short(group.get("legend", "選択肢")),
                       _short(options[0].get("label", "") if isinstance(options[0], Mapping) else options[0]))
                )
            dicts = [o for o in options if isinstance(o, Mapping)]
            if len(options) >= 2 and not dicts:
                lines.append(
                    "⚠️選択肢が文字だけ（止めはしない）: Q%d「%s」＝推奨の印も利点も付かない"
                    "＝label・recommended・pros・cons の辞書で書く"
                    % (number, _short(group.get("legend", "選択肢")))
                )
                continue
            if not any(bool(o.get("recommended")) for o in dicts):
                continue
            for option in options:
                if isinstance(option, Mapping):
                    if bool(option.get("recommended")):
                        continue
                    if _has_text(option.get("pros")) or "利点" in str(option.get("why", "") or ""):
                        continue
                    label = option.get("label", "")
                else:
                    label = option
                lines.append(
                    "⚠️実質1択の恐れ（止めはしない）: Q%d「%s」の「%s」に利点（pros）が無い"
                    "＝非推奨でも選ぶ理由を1行書く"
                    % (number, _short(group.get("legend", "選択肢")), _short(label))
                )
    if len(lines) > WARNING_LIMIT:
        rest = len(lines) - WARNING_LIMIT
        lines = lines[:WARNING_LIMIT] + ["   ほか%d件" % rest]
    return lines


# ---------------------------------------------------------------------------
# 2026-10-09（試問の費用を下げる・Q1）：機械で済む検査は、人に見せる前にこの道具が先に済ませる。
# 試問のサブエージェントに「空の強調」「存在しない記号」「図番号の重複」「問いへの飛び先切れ」を
# 読ませると、頁を読む費用だけが掛かって見つかるのは機械で数えられる誤りだった（置き場の定義51本
# で測り直した）。∴組む前の検査（定義を見る）と、組んだ後の検査（HTMLを見る）に分ける。
# ⚠️止めるのは「不明な図の記号」だけ＝実測した3本とも本物の誤り（doc・search は無い記号）で、
#   描かれずに箱だけ残る。ほかは全部警告（止めはしない）。単独の * は誤爆が多いので見ない。
# ⚠️定義の中を歩くときは正規表現でなく索引と再帰で切り出す（この repo の決まり）。
# ---------------------------------------------------------------------------
# 文字列を見ない鍵＝中身が散文でなく、** や図番号を探す対象でないもの。
# 2026-10-09：markdown＝原稿の頁の原稿そのもの（読み込み後）。原稿の ** や図の番号は検査の対象にしない。
TEXT_SKIP_KEYS = frozenset(("log", "diff", "tex", "svg", "path", "deck", "target", "selector", "markdown"))
# 図番号（num）を持つ図の鍵。節の num と箱の num は数えない。
FIGURE_KEYS = ("diagram", "svg", "image", "screenshot", "timeline", "quadrant", "venn", "flow",
               "score", "chart")
_WALK_DEPTH_LIMIT = 40
_EXCERPT_WIDTH = 40


def _limit_lines(lines):
    """警告が多いときは10行で打ち切り、残りを「ほかN件」の1行にまとめる。"""
    if len(lines) > WARNING_LIMIT:
        rest = len(lines) - WARNING_LIMIT
        return lines[:WARNING_LIMIT] + ["   ほか%d件" % rest]
    return lines


def _section_places(content):
    """検査で見る場所を、頁の文書順に近い形で返す。返るもの＝(節の見出し, 部品名, 値) の一覧。

    節の一覧（sections）の各項目（content が無ければ content の同名の鍵）→ 一覧に無い部品名の鍵
    → 側柱（rail）の順。⚠️組む側（render_components）と同じ規則だが、検査用なので細部がずれても
    困らない（一覧に出した部品は、同名の上位の鍵を二重に見ない）。
    """
    if not isinstance(content, Mapping):
        return []
    places = []
    emitted = set()
    sections = content.get("sections")
    if isinstance(sections, (list, tuple)):
        for entry in sections:
            if not isinstance(entry, Mapping):
                continue
            component = str(entry.get("component", "") or "").strip()
            if not component:
                continue
            value = entry.get("content")
            if value is None:
                value = content.get(component)
            if value is None:
                continue
            label = str(entry.get("label", "") or "").strip() or COMPONENT_LABELS.get(component, component)
            places.append((label, component, value))
            emitted.add(component)
    for key, value in content.items():
        if key in ("sections", "rail", "headline", "provenance") or key in emitted or value is None:
            continue
        places.append((COMPONENT_LABELS.get(key, key), key, value))
    if content.get("rail") is not None:
        places.append(("側柱", "rail", content["rail"]))
    return places


def _nodes(value, path="", key="", depth=0):
    """値を深さ優先で歩く。返るもの＝(道筋, 鍵名, 値) を1つずつ（自分自身が先）。

    ⚠️TEXT_SKIP_KEYS の鍵の下は、辞書でなければ歩かない（辞書の形の svg＝{"svg":…,"num":…}
    のときだけ中へ入る）。一覧の要素は親の鍵名を引き継ぐ。
    """
    yield path, key, value
    if depth >= _WALK_DEPTH_LIMIT:
        return
    if isinstance(value, Mapping):
        for name, child in value.items():
            name = str(name)
            if name in TEXT_SKIP_KEYS and not isinstance(child, Mapping):
                continue
            yield from _nodes(child, path + "." + name if path else name, name, depth + 1)
    elif isinstance(value, (list, tuple)):
        for index, child in enumerate(value):
            yield from _nodes(child, "%s[%d]" % (path, index), key, depth + 1)


def _excerpt(text, around=0):
    """警告の文に入れる抜粋。改行を畳み、around の少し前から40字で切る。"""
    start = max(0, around - 12)
    return " ".join(text[start:start + _EXCERPT_WIDTH].split())


def _icon_problems(boxes, heading, kind, names, found):
    for box in boxes:
        if not isinstance(box, Mapping):
            continue
        icon = box.get("icon")
        icon = "" if icon is None else str(icon)
        if not icon or icon in names:
            continue
        title = box.get("title") or box.get("label") or box.get("id") or ""
        found.append("「%s」の %s の箱「%s」の icon %r" % (heading, kind, _short(title), icon))


def unknown_icons(content, icon_names=None):
    """図の箱に書いた記号（icon）のうち、記号の正本（visual.icons の ICON_NAMES）に無いものを返す。

    入れるもの＝頁の content。見る場所＝diagram の nodes の各 icon（flow の nodes は見ない）と、
    diagram_text（1行記法）の A(icon=NAME)。返るもの＝「見出し」の diagram の箱「題」の icon 'doc'
    のような行の一覧（空なら問題なし）。
    ⚠️記号の正本が取り込めなかった（_ICON_NAMES が None）ときは検査を飛ばして空を返す。
    ⚠️組む側は不明な記号を黙って捨て、箱だけ描いて頁の図の下に小さく注意を出す＝見落とされる。
    ∴組む前に止める（main が return 2）。
    """
    names = _ICON_NAMES if icon_names is None else icon_names
    if names is None:
        return []
    names = frozenset(names)
    found = []
    for heading, component, value in _section_places(content):
        for _path, key, node in _nodes(value, "", component):
            if isinstance(node, Mapping) and key != "flow" and isinstance(node.get("nodes"), (list, tuple)):
                _icon_problems(node["nodes"], heading, "diagram", names, found)
            elif key == "diagram_text" and isinstance(node, str) and _parse_diagram_text is not None:
                try:
                    parsed = _parse_diagram_text(node)
                except Exception:  # noqa: BLE001 - 1行記法の不具合は記号の検査の外
                    continue
                _icon_problems(parsed.get("nodes", ()), heading, "diagram_text", names, found)
    return found


def _figure_kind(key, node):
    """辞書 node が図なら、その種類（FIGURE_KEYS の鍵名）を返す。図でなければ空文字。"""
    if not isinstance(node, Mapping):
        return ""
    if key in FIGURE_KEYS:
        return key
    if key == "visual" and ("nodes" in node or "bands" in node):
        return "diagram"
    return ""


def _figure_label(num):
    """図番号を比べる形にする。先頭の「図」と空白を外す（「図1」と「1」は同じ番号）。"""
    text = "" if num is None else str(num).strip()
    if text.startswith("図"):
        text = text[1:].strip()
    return text


def duplicate_figure_numbers(content):
    """図の num が頁の中で重なっていないかを見て、警告の行の一覧を返す（空なら問題なし）。

    数えるのは FIGURE_KEYS の辞書が持つ自分の num だけ（節の num と箱の num は数えない）。
    組む側は diagram の num をそのまま、image・screenshot は「図」を前置して出す
    （既に「図」で始まれば前置しない）ので、diagram の「図1」と image の「1」は同じ「図1」になる。
    """
    kinds_by_label = {}
    for _heading, component, value in _section_places(content):
        for _path, key, node in _nodes(value, "", component):
            kind = _figure_kind(key, node)
            if not kind:
                continue
            label = _figure_label(node.get("num"))
            if label:
                kinds_by_label.setdefault(label, []).append(kind)
    lines = []
    for label, kinds in kinds_by_label.items():
        if len(kinds) < 2:
            continue
        names = []
        for kind in kinds:
            if kind not in names:
                names.append(kind)
        lines.append("⚠️図番号の重複（止めはしない）: 「図%s」が %s で%d回" % (label, " と ".join(names), len(kinds)))
    return _limit_lines(lines)


def _without_code(text):
    """バッククォートで囲んだ区間（組む側がコード書きにする所）を外す。閉じの無い ` はそのまま残す。"""
    out = []
    position = 0
    while position < len(text):
        if text[position] == "`":
            end = text.find("`", position + 1)
            if end >= 0:
                position = end + 1
                continue
        out.append(text[position])
        position += 1
    return "".join(out)


def unbalanced_emphasis(content):
    """対になっていない ** がある文字列を見つけて、警告の行の一覧を返す（空なら問題なし）。

    組む側（_render_inline）は対の無い ** を空の <em></em> にして文字を消す＝強調するつもりの
    文が壊れる。バッククォートの区間と TEXT_SKIP_KEYS の鍵は見ない。単独の * は見ない
    （「3*4 and 5*6」のような式が真の強調と区別できず、実測で全部誤爆だった）。
    """
    lines = []
    for heading, component, value in _section_places(content):
        for path, _key, node in _nodes(value, "", component):
            if not isinstance(node, str) or "**" not in node:
                continue
            plain = _without_code(node)
            if plain.count("**") % 2 == 0:
                continue
            lines.append(
                "⚠️対になっていない ** がある（止めはしない）: 「%s」の %s 「%s」"
                "＝太字にするなら閉じる・記号を見せたいなら言葉で書く"
                % (_short(heading), path or component, _excerpt(plain, plain.rfind("**")))
            )
    return _limit_lines(lines)


def _asks_number(item):
    """asks の要素を問いの番号（1以上の整数）にする。読めなければ None。

    ⚠️render_components 側の正規化と同じ規則＝整数はそのまま・文字列は先頭の Q／q を外して
    数字だけなら整数・それ以外（真偽値・小数・0以下）は読めない。
    """
    if isinstance(item, bool):
        return None
    if isinstance(item, int):
        number = item
    elif isinstance(item, str):
        text = item[1:] if item[:1] in ("Q", "q") else item
        if not text.isdigit():
            return None
        number = int(text)
    else:
        return None
    return number if number > 0 else None


def _box_asks_unreadable(value):
    """図の箱の asks（1・"Q1"・"1/2"・それらの配列）のうち、問いの番号として読めない要素を返す。"""
    items = value if isinstance(value, (list, tuple)) else [value]
    bad = []
    for item in items:
        pieces = [item]
        if isinstance(item, str):
            pieces = [part for part in item.replace("／", "/").split("/")]
        for piece in pieces:
            if _asks_number(piece.strip() if isinstance(piece, str) else piece) is None:
                bad.append(piece)
    return bad


def _box_asks_warnings(content):
    """図の箱に書いた asks の読めない値を警告する（止めはしない）。

    2026-10-09：箱の角に問いの番号札（Q1）が付く。diagram の nodes と、1行記法 diagram_text の
    A(asks=1/2) を見る。読めない要素は組む側が黙って捨てるので、ここで知らせる。
    """
    lines = []

    def check(boxes, heading, kind):
        for box in boxes:
            if not isinstance(box, Mapping):
                continue
            for key in ("asks", "ask"):
                if key not in box:
                    continue
                for piece in _box_asks_unreadable(box[key]):
                    title = box.get("title") or box.get("label") or box.get("id") or ""
                    lines.append(
                        "⚠️図の箱の %s に問いの番号として読めない値がある（止めはしない）: 「%s」の %s の箱「%s」の %s %s"
                        "＝1・\"Q1\"・\"1/2\" のように1以上の整数で書く（読めない値は捨てられる）"
                        % (key, _short(heading), kind, _short(title), key, _short(repr(piece)))
                    )

    for heading, component, value in _section_places(content):
        for _path, key, node in _nodes(value, "", component):
            if isinstance(node, Mapping) and key != "flow" and isinstance(node.get("nodes"), (list, tuple)):
                check(node["nodes"], heading, "diagram")
            elif key == "diagram_text" and isinstance(node, str) and _parse_diagram_text is not None:
                try:
                    parsed = _parse_diagram_text(node)
                except Exception:  # noqa: BLE001 - 1行記法の不具合は asks の検査の外
                    continue
                check(parsed.get("nodes", ()), heading, "diagram_text")
    return lines


def asks_format_warnings(content):
    """asks（問いの番号）の形を見て、警告の一覧を返す。

    見る場所＝sections の各項目の asks（その節に関わる問いの番号の配列）と、
    図の箱の asks（2026-10-09・1・"Q1"・"1/2"・それらの配列）。
    ⚠️sections の asks は sections の一覧の形でだけ効く。配列でない・読めない要素は組む側が
    黙って捨てるので、ここで知らせる（止めはしない）。
    """
    lines = _box_asks_warnings(content) if isinstance(content, Mapping) else []
    sections = content.get("sections") if isinstance(content, Mapping) else None
    if not isinstance(sections, (list, tuple)):
        return _limit_lines(lines)
    for entry in sections:
        if not isinstance(entry, Mapping) or "asks" not in entry:
            continue
        component = str(entry.get("component", "") or "").strip()
        label = str(entry.get("label", "") or "").strip() or COMPONENT_LABELS.get(component, component)
        asks = entry["asks"]
        if not isinstance(asks, (list, tuple)):
            lines.append(
                "⚠️asks が配列でない（止めはしない）: 「%s」の asks は [1, 2] のような配列で書く"
                "＝配列でないと見出しに「→ Q」の飛び先が付かない" % _short(label)
            )
            continue
        for item in asks:
            if _asks_number(item) is None:
                lines.append(
                    "⚠️asks に問いの番号として読めない値がある（止めはしない）: 「%s」の asks の %s"
                    "＝1・\"1\"・\"Q1\" のように1以上の整数で書く（読めない値は捨てられる）"
                    % (_short(label), _short(repr(item)))
                )
    return _limit_lines(lines)


def _question_count(content):
    """頁の問いの数＝回答文の番号と同じ数え方（free と、行の無い群は数えない）。"""
    count = 0
    for body in _decision_bodies(content):
        for group in _decision_groups(body):
            kind = (str(group.get("kind", "radio") or "radio")).lower()
            if kind != "free" and _group_rows(group, kind):
                count += 1
    return count


def asks_hint(content, reasons=()):
    """判断の頁で asks を1つも書いていないときだけ、書き方の案内を1行返す（要らなければ空文字）。

    判断の頁＝reasons に decision_required。問いが1つも無い頁には出さない。
    """
    if "decision_required" not in tuple(reasons or ()):
        return ""
    if not isinstance(content, Mapping) or _question_count(content) == 0:
        return ""
    sections = content.get("sections")
    if isinstance(sections, (list, tuple)):
        for entry in sections:
            if isinstance(entry, Mapping) and isinstance(entry.get("asks"), (list, tuple)):
                if any(_asks_number(item) is not None for item in entry["asks"]):
                    return ""
    return "ⓘ 問いに関わる節には \"asks\":[1] を書くと見出しに「→ Q1」の飛び先が付く"


# --- 組んだ後の検査（HTMLを見る・全部警告） ---------------------------------

def _all_between(text, start, end):
    """start と end に挟まれた区間を全部、順に返す（索引で切り出す）。"""
    found = []
    position = 0
    while True:
        i = text.find(start, position)
        if i < 0:
            break
        j = text.find(end, i + len(start))
        if j < 0:
            break
        found.append(text[i + len(start):j])
        position = j + len(end)
    return found


def _strip_tags(text):
    """<…> を外す（索引で切り出す）。属性の中の > は組む側が &gt; にするので、素直に探してよい。"""
    out = []
    position = 0
    while position < len(text):
        if text[position] == "<":
            end = text.find(">", position)
            if end >= 0:
                position = end + 1
                continue
        out.append(text[position])
        position += 1
    return "".join(out)


class _VisibleText(HTMLParser):
    """タグの外の文字だけを集める。pre・code・script・style・textarea の中は除く。"""

    _SKIP = ("script", "style", "pre", "code", "textarea")

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []
        self._depth = 0

    def handle_starttag(self, tag, attrs):
        if tag in self._SKIP:
            self._depth += 1

    def handle_endtag(self, tag):
        if tag in self._SKIP and self._depth:
            self._depth -= 1

    def handle_data(self, data):
        if not self._depth:
            self.parts.append(data)


def rendered_warnings(html):
    """組んだ頁（完全版のHTML）を見て、警告の行の一覧を返す（空なら問題なし・全部止めはしない）。

    見る範囲＝<body> 以降で最初の <script> より前。見るもの＝①図の下の注意（dia-warn）の各行
    ②選択肢の絵を載せられなかった印（thumb-missing）③空の強調（<em></em>・<strong></strong>）
    ④タグの外・pre/code の外に残った **（属性の中は見ない）⑤飛び先（#q-N）に対する id="q-N" が無い。
    """
    start = html.find("<body")
    body = html[start:] if start >= 0 else html
    cut = body.find("<script")
    if cut >= 0:
        body = body[:cut]
    # 2026-10-09：原稿の節（利用者の文章そのもの）は、**・空の強調・図の下の注意の検査から外す。
    body = without_manuscript(body)
    lines = []
    for block in _all_between(body, '<ul class="dia-warn">', "</ul>"):
        for item in _all_between(block, "<li>", "</li>"):
            lines.append("⚠️図の下に警告が出ている（止めはしない）: " + _short(unescape(_strip_tags(item))))
    for marker in ('<span class="thumb thumb-missing">', '<span class="thumb-missing">'):
        for item in _all_between(body, marker, "</span>"):
            lines.append("⚠️選択肢の絵が頁に載っていない（止めはしない）: " + _short(unescape(_strip_tags(item))))
    empty_em = body.count("<em></em>")
    empty_strong = body.count("<strong></strong>")
    if empty_em or empty_strong:
        lines.append(
            "⚠️空の強調が頁に出ている（止めはしない）: <em></em> が%d個・<strong></strong> が%d個"
            "＝対の無い * や ** が文字を消した（定義の文を見直す）" % (empty_em, empty_strong)
        )
    visible = _VisibleText()
    visible.feed(body)
    visible.close()
    flat = " ".join(visible.parts)
    stray = chr(0).join(visible.parts).count("**")
    if stray:
        lines.append(
            "⚠️頁の本文に ** がそのまま出ている（止めはしない）: %d か所 「%s」"
            "＝太字になっていない（対が閉じていないか、** が効かない場所に書いてある）"
            % (stray, _excerpt(flat, flat.find("**")))
        )
    marker = 'href="#q-'
    position = 0
    missing = []
    while True:
        i = body.find(marker, position)
        if i < 0:
            break
        digits = ""
        for ch in body[i + len(marker):]:
            if not ch.isdigit():
                break
            digits += ch
        position = i + len(marker)
        if digits and digits not in missing and 'id="q-%s"' % digits not in html:
            missing.append(digits)
    for digits in missing:
        lines.append(
            "⚠️見出しや図の「Q%s」の飛び先（#q-%s）が頁に無い（止めはしない）"
            "＝asks の番号が問いの数を超えている" % (digits, digits)
        )
    return _limit_lines(lines)


# --- 文字だけの版（試問のサブエージェントが読む・完全版より小さい） ---------

def _join_wrapped(chunks):
    """折り返された行の断片をつなぐ。英数字どうしが隣り合うときだけ空白を入れる。"""
    out = ""
    for chunk in chunks:
        piece = " ".join(chunk.split())
        if not piece:
            continue
        if out and out[-1].isascii() and out[-1].isalnum() and piece[0].isascii() and piece[0].isalnum():
            out += " "
        out += piece
    return out


class _TextOnly(HTMLParser):
    """頁のHTMLから、画像・図・script・style・釦・回答文の欄を外した本文を行にする。

    ⚠️行の区切りは「ブロックの要素の始まりと終わり」で付ける（行にする要素を列挙すると、列挙に
    無い入れ物の中の文字が1行に溶ける）。表の行は「｜」でセルをつなぐ。
    """

    HEADINGS = ("h1", "h2", "h3", "h4", "h5", "h6")
    BLOCK = frozenset((
        "div", "section", "header", "main", "aside", "nav", "footer", "article", "p", "ul", "ol",
        "li", "table", "thead", "tbody", "tfoot", "caption", "h1", "h2", "h3", "h4", "h5", "h6",
        "legend", "label", "fieldset", "figure", "figcaption", "details", "summary", "blockquote",
        "pre", "dl", "dt", "dd", "form",
    ))
    VOID = frozenset((
        "area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "source",
        "track", "wbr",
    ))
    DROP = frozenset(("script", "style", "button", "template", "noscript", "title"))

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.lines = []
        self.buf = []
        self.prefix = ""
        self.stack = []
        self.drop_tag = ""
        self.drop_depth = 0
        self.svg = None
        self.in_row = False
        self.cells = 0
        self.in_pc = 0
        self.after_bold = False
        # 2026-10-09：data-blk の要素（原稿のブロック・説明の頁の単位）の最初の行に「#N 」を付け、
        # 取り下げた選択肢（class withdrawn）の行頭に「[取り下げ] 」を付ける。
        self.blks = []
        self.saw_blk = False
        self.withdrawn_pending = False
        # 原稿のコードブロック（data-ms-type="code"）だけは、行と字下げをそのまま残す。
        self.code_text = ""

    def _emit_code_lines(self):
        """溜めたコードの文字を、行ごと・字下げのまま出す（最初の空でない行へ「#N 」を付ける）。"""
        text, self.code_text = self.code_text, ""
        for line in text.split(NL):
            line = line.rstrip()
            prefix = ""
            if line:
                for blk in self.blks:
                    if not blk["used"]:
                        blk["used"] = True
                        prefix = "#%s " % blk["n"]
                        break
            self.lines.append(prefix + line)

    # 行の組み立て
    def _flush(self):
        if self.code_text:
            self._emit_code_lines()
        text = " ".join("".join(self.buf).split())
        self.buf = []
        if not text:
            return
        prefix = self.prefix
        if self.withdrawn_pending:
            self.withdrawn_pending = False
            if not text.startswith("[取り下げ]"):
                prefix = "[取り下げ] " + prefix
        for blk in self.blks:
            if not blk["used"]:
                blk["used"] = True
                prefix = "#%s " % blk["n"] + prefix
                break
        self.lines.append(prefix + text)
        self.prefix = ""

    def _blank(self):
        if self.lines and self.lines[-1] != "":
            self.lines.append("")

    def _break(self):
        if self.in_row:
            self.buf.append(" ")
        else:
            self._flush()

    def finish(self):
        self._flush()
        if self.code_text:
            self._emit_code_lines()

    @staticmethod
    def _input_marker(attrs, classes):
        kind = (attrs.get("type") or "text").lower()
        if kind == "radio":
            return "( ) "
        if kind == "checkbox":
            return "[ ] "
        if kind == "number":
            label = " ".join((attrs.get("data-label") or attrs.get("aria-label") or "").split())
            return "[数: %s] " % label if label else "[数] "
        if kind in ("hidden", "submit", "button"):
            return ""
        if "q-note" in classes:
            return "[補足欄]"
        hint = " ".join((attrs.get("placeholder") or "").split())
        return "[記入欄: %s]" % hint if hint else "[記入欄]"

    # svg は中身を捨てて、題と文字だけにする
    @staticmethod
    def _number(value):
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    def _svg_start(self, tag, attrs):
        svg = self.svg
        svg["depth"] += 1
        attrs = dict(attrs)
        classes = set((attrs.get("class") or "").split())
        # 2026-10-09：図の箱の角の問いの番号札（<a class="dia-q">）は、題や文字に混ぜず別に溜める。
        # 札は箱の外に並ぶので、円の中心がどの箱の枠に入るかで箱の題に結び付ける（_emit_svg）。
        if tag == "a" and "dia-q" in classes:
            svg["badge"] = {"depth": svg["depth"], "label": "", "cx": None, "cy": None}
            return
        badge = svg["badge"]
        if tag == "circle" and badge is not None and "dia-q-dot" in classes:
            badge["cx"] = self._number(attrs.get("cx"))
            badge["cy"] = self._number(attrs.get("cy"))
            return
        if tag == "rect":
            svg["rects"].append({
                "x": self._number(attrs.get("x")), "y": self._number(attrs.get("y")),
                "w": self._number(attrs.get("width")), "h": self._number(attrs.get("height")),
                "text_at": len(svg["texts"]),
            })
        if tag == "title" and not svg["title"] and badge is None:
            svg["in_title"] = True
            svg["title_chunks"] = []
        elif tag == "text":
            svg["chunks"] = []

    def _svg_data(self, data):
        svg = self.svg
        if svg["in_title"]:
            svg["title_chunks"].append(data)
        elif svg["chunks"] is not None:
            svg["chunks"].append(data)

    def _svg_end(self, tag):
        svg = self.svg
        if tag == "title" and svg["in_title"]:
            svg["in_title"] = False
            svg["title"] = _join_wrapped(svg["title_chunks"])
        elif tag == "text" and svg["chunks"] is not None:
            text = _join_wrapped(svg["chunks"])
            svg["chunks"] = None
            if text and svg["badge"] is not None:
                svg["badge"]["label"] = text
            elif text:
                svg["texts"].append(text)
        elif tag == "a" and svg["badge"] is not None and svg["badge"]["depth"] == svg["depth"]:
            svg["badges"].append(svg["badge"])
            svg["badge"] = None
        svg["depth"] -= 1
        if svg["depth"] == 0:
            self._emit_svg()
            self.svg = None

    @staticmethod
    def _with_question_badges(svg):
        """箱の題の後ろへ「[Q1]」を付けた文字の一覧を返す（読み手が図と問いの対応を追えるように）。

        札の円の中心が入る枠（いちばん小さいもの）を箱とみなし、その枠の次の文字（箱の題）に付ける。
        どの箱にも結び付かない札は、最後に「問い Q1・Q2」の1項目にまとめる。
        """
        texts = list(svg["texts"])
        rects = svg["rects"]
        notes = {}
        loose = []
        for badge in svg["badges"]:
            label = badge["label"]
            if not label:
                continue
            host = None
            cx, cy = badge["cx"], badge["cy"]
            if cx is not None and cy is not None:
                best = None
                for index, rect in enumerate(rects):
                    x, y, w, h = rect["x"], rect["y"], rect["w"], rect["h"]
                    if None in (x, y, w, h) or not (x <= cx <= x + w and y <= cy <= y + h):
                        continue
                    if best is None or w * h < best[0]:
                        best = (w * h, index)
                if best is not None:
                    host = best[1]
            title_at = None
            if host is not None:
                start = rects[host]["text_at"]
                stop = rects[host + 1]["text_at"] if host + 1 < len(rects) else len(texts)
                if start < stop and start < len(texts):
                    title_at = start
            if title_at is None:
                loose.append(label)
            else:
                notes.setdefault(title_at, []).append(label)
        for index, labels in notes.items():
            texts[index] = texts[index] + " " + "".join("[%s]" % label for label in labels)
        if loose:
            texts.append("問い " + "・".join(loose))
        return texts

    def _emit_svg(self):
        svg = self.svg
        texts = svg["texts"]
        if "marks" in svg["classes"]:
            if texts:
                self.buf.append(" [画像の印: %s] " % "／".join(texts))
            return
        texts = self._with_question_badges(svg)
        title = svg["title"] or " ".join(svg["label"].split())
        body = "／".join(texts)
        if len(body) > 400:
            body = body[:399] + "…"
        parts = []
        if title:
            parts.append(title)
        if body:
            parts.append("文字: " + body)
        self.buf.append(" [図: %s] " % "｜".join(parts) if parts else " [図] ")

    def handle_starttag(self, tag, attrs):
        if self.drop_depth:
            if tag == self.drop_tag and tag not in self.VOID:
                self.drop_depth += 1
            return
        if self.svg is not None:
            self._svg_start(tag, attrs)
            return
        attrs = dict(attrs)
        classes = set((attrs.get("class") or "").split())
        # 番号つきの単位の始まり。前の行を先に出し、この要素の最初の行へ「#N 」を付ける。
        blk_number = (attrs.get("data-blk") or "").strip()
        if blk_number:
            self._flush()
            self.blks.append({
                "n": blk_number, "tag": tag, "depth": 1, "used": False,
                "code": (attrs.get("data-ms-type") or "") == "code",
            })
            self.saw_blk = True
        elif self.blks and tag == self.blks[-1]["tag"]:
            self.blks[-1]["depth"] += 1
        if "withdrawn" in classes:
            self._flush()
            self.withdrawn_pending = True
        # 太字の見出し語の直後の span は、空白なしで続くと語と溶ける（<b>GOAL</b><span>…）。
        if self.after_bold and tag == "span":
            self.buf.append(" ")
        self.after_bold = False
        if tag == "svg":
            self.svg = {
                "depth": 1, "title": "", "title_chunks": [], "in_title": False,
                "label": attrs.get("aria-label") or "", "classes": classes,
                "texts": [], "chunks": None,
                "rects": [], "badges": [], "badge": None,
            }
            return
        if (tag in self.DROP or tag == "textarea" or attrs.get("id") == "decision-prompt"
                or "decision-actions" in classes):
            if tag == "textarea" and "ms-source" not in classes:
                self.buf.append("[自由記述欄]")
            self.drop_tag = tag
            self.drop_depth = 1
            return
        if tag == "img":
            alt = " ".join((attrs.get("alt") or "").split())
            self.buf.append(" [画像: %s] " % alt if alt else " [画像] ")
            return
        if tag == "input":
            self.buf.append(self._input_marker(attrs, classes))
            return
        if tag == "br" and self.in_pc:
            self.buf.append(" ／ ")
            return
        if tag in ("br", "hr"):
            self._break()
            return
        if tag in self.VOID:
            return
        suffix = ""
        kind = ""
        if tag == "tr":
            self._flush()
            self.in_row = True
            self.cells = 0
        elif tag in ("td", "th"):
            if self.cells:
                self.buf.append("｜")
            self.cells += 1
        elif tag in self.BLOCK or "provenance-item" in classes:
            if tag not in self.BLOCK:
                kind = "pi"
            self._break()
            if not self.in_row:
                if tag in self.HEADINGS:
                    if tag in ("h1", "h2", "h3"):
                        self._blank()
                    self.prefix = "#" * min(int(tag[1]), 4) + " "
                elif tag == "li":
                    self.prefix = "- "
                elif tag == "blockquote":
                    self.prefix = "> "
        elif tag == "span" and "t" in classes:
            suffix = "〔用語〕"
        elif "badge" in classes or "pin" in classes:
            self.buf.append("[")
            suffix = "]"
        elif "sec-no" in classes or "q-no" in classes or "toc-no" in classes:
            self.buf.append("[")
            suffix = "] "
        elif "item-label" in classes or "pro" in classes or "con" in classes:
            suffix = "："
        elif "pros-cons" in classes:
            self.buf.append(" ")
            self.in_pc += 1
            kind = "pc"
        elif "q-ref" in classes or "why" in classes:
            self.buf.append(" ")
        self.stack.append((tag, suffix, kind))

    def handle_endtag(self, tag):
        skipped = bool(self.drop_depth) or self.svg is not None
        self._end_tag(tag)
        if not skipped and self.blks and tag == self.blks[-1]["tag"]:
            self.blks[-1]["depth"] -= 1
            if self.blks[-1]["depth"] <= 0:
                self.blks.pop()

    def _end_tag(self, tag):
        if self.drop_depth:
            if tag == self.drop_tag:
                self.drop_depth -= 1
            return
        if self.svg is not None:
            self._svg_end(tag)
            return
        if tag in self.VOID:
            return
        suffix = None
        kind = ""
        for index in range(len(self.stack) - 1, -1, -1):
            if self.stack[index][0] == tag:
                suffix = self.stack[index][1]
                kind = self.stack[index][2]
                if kind == "pc":
                    self.in_pc -= 1
                del self.stack[index:]
                break
        if suffix is None:
            return
        if suffix:
            self.buf.append(suffix)
        if tag in ("b", "strong") and not suffix:
            self.after_bold = True
        if tag == "tr":
            self._flush()
            self.in_row = False
        elif tag in ("td", "th"):
            return
        elif tag in self.BLOCK or kind == "pi":
            if not self.in_row and (tag in self.HEADINGS or tag in ("li", "blockquote")):
                self._flush()
                self.prefix = ""
            else:
                self._break()

    def handle_data(self, data):
        if self.drop_depth:
            return
        if self.svg is not None:
            self._svg_data(data)
            return
        self.after_bold = False
        if self.blks and self.blks[-1]["code"]:
            self.code_text += data
            return
        self.buf.append(data)


def text_only(html, name=""):
    """頁のHTML（完全版）から、文字だけの版の本文を返す。

    入れるもの＝完全版のHTMLと、元の頁の名前（拡張子なし）。返るもの＝UTF-8のテキスト。
    外すもの＝script・style・釦・回答文の欄（#decision-prompt・.decision-actions）・画像の本体
    （data: の画像も）。図（svg）は題と中の文字だけ、画像は alt だけを角括弧で残す。
    ⚠️用語の説明（data-d）は載せない＝語の後ろに〔用語〕を付けるだけ（頁の「用語」の節に説明がある）。
    """
    start = html.find("<body")
    source = html[start:] if start >= 0 else html
    parser = _TextOnly()
    parser.feed(source)
    parser.close()
    parser.finish()
    lines = []
    for line in parser.lines:
        if line == "" and (not lines or lines[-1] == ""):
            continue
        lines.append(line)
    while lines and lines[-1] == "":
        lines.pop()
    origin = "。元の頁: %s.html" % name if name else ""
    numbered = "。行頭の #N は番号つきの単位（原稿のブロックなど）＝回答の指摘の番号と同じ" if parser.saw_blk else ""
    header = "（文字だけの版＝画像・図・script・style を外した本文。〔用語〕はホバーで説明の付く語%s%s）" % (origin, numbered)
    return header + NL + NL + NL.join(lines) + NL


def text_path_for(full_path):
    """完全版のpathから、文字だけの版のpath（同じ置き場の <name>-text.txt）を決める。"""
    base, _ext = os.path.splitext(full_path)
    return base + "-text.txt"


def write_text_only(full_path):
    """完全版の隣に文字だけの版（<name>-text.txt）を書き、そのpathを返す。

    ⚠️.html でないのでフックは触らない（フックが見るのは .html だけ）。
    失敗しても頁の組み立ては止めない（呼び出し側が例外を受けて1行で知らせる）。
    """
    with io.open(full_path, encoding="utf-8", errors="replace") as handle:
        html = handle.read()
    name = os.path.splitext(os.path.basename(full_path))[0]
    path = text_path_for(full_path)
    with io.open(path, "w", encoding="utf-8", newline=NL) as handle:
        handle.write(text_only(html, name))
    return path


# 2026-10-08（判断の頁を赤ペン流に寄せた・案5）：判断の頁だけ、人に見せる前に
# 文脈ゼロのサブエージェントに読ませる試問の文を出す。
# ⚠️判断の頁（reasons に decision_required）以外では出さない＝毎回の費用を判断の回に限る。
# ⚠️節の見出しはレンダラーが実際に出す文字に合わせる（LABELS と、節の一覧で自分で付けた見出し）。
PREFLIGHT_DEFAULT_READER = "このプロジェクトを初めて読む人"


def _heading_text(spec, component):
    """頁に実際に出る節の見出しを「」で囲んで返す（節が複数ならそれぞれ）。"""
    default = COMPONENT_LABELS.get(component, component)
    labels = []
    content = spec.get("content")
    sections = content.get("sections") if isinstance(content, Mapping) else None
    if isinstance(sections, (list, tuple)):
        for entry in sections:
            if isinstance(entry, Mapping) and str(entry.get("component", "")).strip() == component:
                label = str(entry.get("label", "") or "").strip() or default
                if label not in labels:
                    labels.append(label)
    return "".join("「%s」" % label for label in (labels or [default]))


def preflight_prompt(spec, page_path, text_path=None):
    """判断の頁の試問の文を返す（貼り付け用の本文は「ここから」〜「ここまで」の間）。

    入れるもの＝頁の定義と、組んだ完全版の頁のpath、文字だけの版のpath（text_path・任意）。
    任意の spec["preflight"] は {"reader":"読者宣言の1行","allowed":["語",…]}
    （無ければ既定の読者・許可語なし）。
    2026-10-09：text_path があれば、試問の読み手にはその文字だけの版を読ませる（画像・図・script・
    style を外した本文＝完全版より小さく、読むのに掛かる費用が減る）。完全版は見た目の確認だけに使う。
    機械で済ませた検査（空の強調・図の記号・図番号の重複・問いへの飛び先）は読み手に求めない。
    """
    preflight = spec.get("preflight")
    preflight = preflight if isinstance(preflight, Mapping) else {}
    reader = str(preflight.get("reader", "") or "").strip().rstrip("。") or PREFLIGHT_DEFAULT_READER
    allowed = preflight.get("allowed")
    if isinstance(allowed, str):
        allowed = [allowed]
    allowed = [str(word).strip() for word in (allowed or ()) if str(word).strip()]
    allowed_text = ("は " + "、".join(allowed) + " だけ") if allowed else "は無い"
    decision = _heading_text(spec, "decision")
    evidence = _heading_text(spec, "evidence")
    glossary = _heading_text(spec, "glossary")
    if text_path:
        page_lines = [
            "頁（文字だけの版）: %s（Read で開く。画像・図・script・style を外した本文。"
            "〔用語〕はホバーで説明の付く語）" % text_path,
            "元の頁（見た目の確認だけに使う）: %s" % page_path,
        ]
    else:
        page_lines = ["頁: %s（Read で開く）" % page_path]
    page_lines.append("機械で済ませた検査（空の強調・図の記号・図番号の重複・問いへの飛び先）は見なくてよい。")
    return NL.join([
        "[試問] この頁は判断を求める（reasons に decision_required）＝人に見せる前に、"
        "下の文を文脈ゼロのサブエージェント（Claude Code なら general-purpose）にそのまま渡し、"
        "同期で結果を待つ（background にしない・結果を読まずに応答を終えない）。"
        "1〜3 で落ちた問いは絵を足す／問いを落とす／言い換える。4 は文をほどく。"
        "5 が3語以上なら言い換える。計2巡で打ち切る。"
        "上の合格が False の頁は先に直す。サブエージェントを使えない環境では省き、省いたと応答に1行書く。",
        "---- ここから ----",
        "次の HTML は、人に判断を求める頁です。"
        "あなたは何も知らない読者として読み、5 つの問いに答えてください。",
        *page_lines,
        "読者宣言: %s。説明なしで使ってよい語%s（頁の%sの節とホバーで説明の付いた語は除く）"
        % (reader, allowed_text, glossary),
        "1. %sの節の各問について、それぞれの選択肢を選んだ場合に何が変わるかを、"
        "この頁だけから説明してください。説明できない問いは「説明不能」と書いてください。"
        "続けて、%sの節の入力欄だけを見て（上の本文を見ずに）、各選択肢の違いが分かるか答えてください。"
        "見た目が違うのに絵が無い選択肢があれば、その問いを挙げてください。"
        "節の見出しの「→ Q1」は、その節がどの問いに関わるかの印です。" % (decision, decision),
        "2. 頁の断定（本文・判定・推奨）に、%sの節の表の行が対応していますか。"
        "対応する行が無い断定を挙げてください。" % evidence,
        "3. 推奨でない選択肢を選ぶ理由（利点）が読み取れますか。"
        "読み取れない問いを挙げてください（その問いは実質1択です）。",
        "4. 音読して不自然な文、意味の取れない文を逐語で挙げてください。"
        "次に、この頁の趣旨を 30 秒で 3 文で言ってください。",
        "5. 読者宣言の許可語の外で、説明なしに使われている語や初見の造語を列挙してください。",
        "出力は問いごとに「通過 / 落ちた問いと理由」で。頁を直す提案は不要です。",
        "---- ここまで ----",
    ])


def _parse_argv(argv):
    """位置引数（定義JSONのpath）と任意の --runtime／--state-path／--project-root を取り出す。

    後方互換＝`rp.main([prog, path])`（stress_page.py・既存の呼び出し）はそのまま動く。
    返るもの＝(positional の並び, runtime, state_path, project_root)。
    """
    positional = []
    runtime = "none"
    state_path = None
    project_root = None
    index = 1
    while index < len(argv):
        token = argv[index]
        if token == "--runtime" and index + 1 < len(argv):
            index += 1
            runtime = argv[index]
        elif token == "--state-path" and index + 1 < len(argv):
            index += 1
            state_path = argv[index]
        elif token == "--project-root" and index + 1 < len(argv):
            index += 1
            project_root = argv[index]
        else:
            positional.append(token)
        index += 1
    return positional, runtime, state_path, project_root


def main(argv):
    positional, runtime, state_path, project_root_arg = _parse_argv(argv)
    # 2026-09-25：既定は環境変数／上へ辿る探索／従来どおりの順（_default_project_root）。
    # ⚠️このリポジトリで引数なしで走らせた時は、従来どおりの場所に落ち着く（後方互換）。
    project_root = project_root_arg or _default_project_root()
    if len(positional) != 1 or runtime not in ("none", "codex"):
        print(__doc__)
        return 2
    spec = json.loads(io.open(positional[0], encoding="utf-8").read())
    # 2026-10-09（指摘と添削の作り込み）：原稿の節を読み、欠けた部品の既定を足し、赤ペンの役割を決める。
    # 原稿が読めなければ組み立てを止める（唯一の止める理由＝原稿が無いと頁の中身が無い）。
    try:
        spec, prepare_notes = prepare_spec(spec, project_root)
    except ManuscriptError as exc:
        print("⚠️原稿を読めない＝組み立てを止めた: " + str(exc))
        return 2
    for note in prepare_notes:
        print(note)
    # ⚠️頁を作り終えてから応答を書くので、応答の言葉で要求部品が**後から増える**。
    #   7部品で作った頁が、応答に「比較」「決めて」が出ただけで差し戻された実例あり
    #   （2026-08-29）。∴既定は9部品すべて。欠けていたら助言だけ出す（止めはしない）。
    # 節を一覧で書いた場合も、部品の網羅は components で見る（節は見出しの自由化）。
    missing = [name for name in ALL_COMPONENTS if name not in spec["components"]]
    if missing:
        print("⚠️部品が欠けている: " + ",".join(missing)
              + "  応答の言葉で後から要求されると差し戻される")
    # 2026-08-29（ユーザー裁定＝割引採用）：末尾に自動で足す安全網は残すが、**黙ってやらない**。
    # ⚠️「意図せぬ節が末尾に出る」副作用があるので、どれが自動追加かを必ず知らせる。
    listed = {
        str(entry.get("component", ""))
        for entry in (spec["content"].get("sections") or [])
        if isinstance(entry, dict)
    }
    if listed:
        auto = [
            name
            for name in spec["components"]
            if name not in listed and name not in {"overview"} and name in spec["content"]
        ]
        if auto:
            print("ⓘ 節の一覧に無いので末尾へ自動で足す: " + ",".join(auto))
    # 2026-08-30（ユーザー選択＝見出しと中身のずれを機械で止める）。
    # ⚠️止められるのは**明らかなずれ**だけ＝別の部品が持つ言葉の借用・空の節・重複。
    #   意味が噛み合っているかは読まないと分からない。ここは網であって保証ではない。
    problems = check_sections(spec["content"].get("sections"), spec["content"])
    if problems:
        print("⚠️見出しと中身がずれている＝組み立てを止めた")
        for problem in problems:
            print("   ・" + problem)
        return 2
    # 2026-10-09（試問の費用を下げる・Q1）：存在しない図の記号は、組む前に止める（唯一の「止める」検査）。
    # ⚠️組む側は不明な記号を黙って捨てて箱だけ描く＝頁を読むまで気づけない。実測で本物の誤りだけだった。
    #   この検査の道具が壊れているとき（記号の正本が取り込めない・例外）は止めずに続ける。
    try:
        bad_icons = unknown_icons(spec["content"])
    except Exception as exc:  # noqa: BLE001 - 検査の不具合で頁が組めなくならないように
        bad_icons = []
        print("ⓘ 図の記号の検査は走らなかった（%s）" % exc)
    if bad_icons:
        print("⚠️図の記号が無い＝組み立てを止めた")
        for item in bad_icons:
            print("   ・" + item)
        names = tuple(_ICON_NAMES or ())
        print("   使える記号（全%d個）: %s" % (len(names), ", ".join(names)))
        return 2
    # 2026-10-09：ほかの組む前の検査（図番号の重複・対の無い **・asks の形・asks の案内）＝全部止めない。
    for check_fn in (duplicate_figure_numbers, unbalanced_emphasis, asks_format_warnings):
        try:
            for warning in check_fn(spec["content"]):
                print(warning)
        except Exception as exc:  # noqa: BLE001 - 助言の検査なので頁の組み立てを止めない
            print("ⓘ %s は走らなかった（%s）" % (check_fn.__name__, exc))
    try:
        hint = asks_hint(spec["content"], spec.get("reasons", ()))
        if hint:
            print(hint)
    except Exception as exc:  # noqa: BLE001
        print("ⓘ asks の案内は出せなかった（%s）" % exc)
    # 2026-10-08（判断の頁を赤ペン流に寄せた・案1）：推奨があるのに非推奨の案に利点が無い問いを知らせる。
    # ⚠️止めない（知らせるだけ）。この検査の不具合で頁が組めなくならないよう、落ちても続ける。
    try:
        for warning in decision_option_warnings(spec["content"]):
            print(warning)
    except Exception as exc:  # noqa: BLE001 - 助言の検査なので頁の組み立てを止めない
        print("ⓘ 実質1択の検査は走らなかった（%s）" % exc)
    full, shaped = build(spec, project_root)
    # 2026-10-09（試問の費用を下げる・Q1）：試問の読み手に渡す文字だけの版を、完全版の隣へ書く。
    # ⚠️失敗しても止めない（試問が完全版を読むだけに戻る）。
    text_path = None
    text_note = ""
    try:
        text_path = write_text_only(full)
    except Exception as exc:  # noqa: BLE001 - 試問の補助なので頁の組み立てを止めない
        text_note = "ⓘ 文字だけの版は書けなかった（%s）" % exc
    lines = ["書き出した:", "  完全版 (検品証用): " + full, "  器用 (publish用) : " + shaped]
    if text_path:
        lines.append("  文字だけの版 (試問用): " + text_path)
    if text_note:
        lines.append(text_note)
    lines.append("")
    bad = 0
    full_check = None
    for label, path in (("完全版", full), ("器用", shaped)):
        result = check(path, spec["components"], project_root)
        if label == "完全版":
            full_check = result
        lines.append("%s  %d バイト  合格=%s" % (label, result["bytes"], result["ok"]))
        for key in ("missing_components", "missing_decision_parts", "unwrapped",
                    "unknown", "missing_sources", "errors", "smoke_errors",
                    "external_dependency"):
            if result[key]:
                lines.append("   %-22s %s" % (key, str(result[key])[:150]))
        if result.get("low_contrast"):
            lines.append(
                "   ⚠️薄い字（止めはしない）: 背景とのコントラストが基準（小さな字は4.5）に届かない文字が"
                " %d か所（最小の比 %s）" % (result["low_contrast"], result.get("min_contrast"))
            )
        if not result["ok"]:
            bad += 1
    # 2026-09-01（ユーザー指摘）：組み上がりの濃さを必ず出す。
    # ⚠️指示文に書いただけでは効かなかった（別セッションの頁で実測）。
    #   ∴その人が実際に走らせるこの道具の出力で言う。
    built = io.open(full, encoding="utf-8", errors="replace").read()
    # 2026-10-09（試問の費用を下げる・Q1）：組んだ後の検査（空の強調・図の下の注意・絵の欠け・飛び先切れ）。
    # ⚠️全部止めない。この検査の不具合で結果の表示が欠けないよう、落ちても続ける。
    try:
        rendered = rendered_warnings(built)
    except Exception as exc:  # noqa: BLE001
        rendered = ["ⓘ 組んだ後の検査は走らなかった（%s）" % exc]
    if rendered:
        lines.append("")
        lines.extend(rendered)
    counts = density(built)
    body_bytes = len(without_manuscript(built).encode("utf-8"))
    lines.append("")
    lines.append("部品の濃さ: " + " ".join("%s=%d" % (n, c) for n, c in counts))
    # 2026-10-09：原稿の頁の濃さは原稿が決める（既定で足した枠は薄くてよい）＝助言は出さない。
    advice = [] if _manuscript_of(spec.get("content")) is not None else advise_density(counts, body_bytes)
    if advice:
        lines.append("⚠️薄い頁に見える（止めはしない）:")
        for item in advice:
            lines.append("   ・" + item)
    lines.append("")
    lines.append("⚠️publish には**器用**のほうを渡す（完全版はそのまま渡すと入れ子になる）")
    # 2026-10-08（判断の頁を赤ペン流に寄せた・案5）：判断を求める頁の回だけ、試問の文を出す。
    if "decision_required" in tuple(spec.get("reasons", ()) or ()):
        lines.append("")
        try:
            lines.append(preflight_prompt(spec, full, text_path))
        except Exception as exc:  # noqa: BLE001 - 助言なので頁の組み立ての結果は変えない
            lines.append("ⓘ 試問の文は組めなかった（%s）" % exc)
    # 2026-09-25：--runtime codex の時だけ、完全版について検品の記録を1件残す。
    # ⚠️安全の掟＝--runtime codex が無い（既定 none）ときは、この分岐そのものに入らない
    #   ＝環境変数だけを見て自動で記録することはしない。
    if runtime == "codex":
        state_path_value = state_path or os.path.join(
            _approved_root_for(project_root), "state.db"
        )
        note = record_codex_receipt(
            full,
            spec["components"],
            full_check["smoke"],
            full_check["smoke_errors"],
            project_root,
            state_path_value,
        )
        lines.append("")
        lines.append(note)
    print(NL.join(lines))
    return 1 if bad else 0


if __name__ == "__main__":
    if sys.platform == "win32":
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass
    raise SystemExit(main(sys.argv))

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
         "content": "背景：本文"}
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

側柱（頁全体の2段組み）＝content に `"rail": [ {塊}, … ]` を足すと、
広い画面（1100px以上）で本文の右に添え物が立つ。⚠️**側柱は節ではない**
（部品の目印を持たない）＝節そのものは横に並べない、という裁定を守るための形。

見出しが**別の部品の言葉**を借りていたら組み立てを止める（`visual/section_labels.py`）。
止まるのは借用・空の節・見出しの重複・番号の重複の4つだけで、意味の一致は見ていない。

componentごとの書き方＝どれも「見出し：本文」を改行で並べるだけ。
evidenceだけ「種類：内容｜出所」の3つ組にする（出所を空にすると検査で落ちる）。
"""
import io
import json
import os
import sys
from collections.abc import Mapping

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

# 2026-09-25：Codexの依頼の受付が残す印は、この時間より古ければ使わない
# （visual/turn_marker.py の既定と揃える）。
CODEX_TURN_MAX_AGE_SECONDS = 21600
# 検品の記録に使う上限バイト数。Policy既定（2097152）と揃える＝
# render_page.py はPolicyを読まないのでここに複製する。
RECEIPT_MAX_ARTIFACT_BYTES = 2_097_152
RECEIPT_TTL_SECONDS = 86400

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


def build(spec, project_root=None):
    """定義から頁を組み、承認済みの置き場へ2つ書き出す。返るもの＝(完全版, 器用) のpath。"""
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


def density(text):
    """組み上がった頁で、どの部品がいくつ使われたかを数える。

    入れるもの＝完全版のHTML。返るもの＝`(部品名, 個数)` の並び。
    ⚠️CSSの定義に同じ語が出るので、本文（`<body>` 以降）だけを数える。
    """
    start = text.find("<body>")
    body = text[start:] if start >= 0 else text
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


def decision_option_warnings(content):
    """判断の問いが実質1択になっていないかを見て、警告の行の一覧を返す（空なら問題なし）。

    入れるもの＝頁の定義の content。見る場所＝content["decision"]（groups か旧形式の
    options）と、content["sections"] のうち component が decision の節の content。
    対象＝kind が radio／checkbox（既定 radio）の群のうち、辞書の選択肢に recommended が
    真のものが1つでもある群。その群の recommended でない選択肢で、pros が空で、
    かつ why に「利点」を含まないものを1行ずつ（文字列の選択肢は利点を書けないので必ず数える）。
    選択肢が2つ以上あって全部が文字列の群は、群ごとに1行（推奨の印も利点も付かない形）。
    scale・number・free は対象外。
    ⚠️2026-10-08（リード）：計画では文字列だけの群を対象外にしていたが、置き場の定義47本を
      測ると選択の群78のうち76が文字列だけで、警告が1件も出ない＝案1が効かない形だった。
      文字列の選択肢は render_components._decision_parts で推奨にならない（「推奨を入れる」の
      釦も効かない）ので、辞書の形へ寄せる指摘として数える。止めはしない。
    ⚠️問いの番号 Q は頁全体の通し（free の群は数えない＝回答文の番号と同じ）。
    10行で打ち切り、残りは「ほかN件」の1行にまとめる。
    """
    lines = []
    number = 0
    for body in _decision_bodies(content):
        for group in _decision_groups(body):
            kind = (str(group.get("kind", "radio") or "radio")).lower()
            if kind == "free":
                continue
            number += 1
            if kind in ("scale", "number"):
                continue
            options = group.get("options", ())
            if not isinstance(options, (list, tuple)):
                continue
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


def preflight_prompt(spec, page_path):
    """判断の頁の試問の文を返す（貼り付け用の本文は「ここから」〜「ここまで」の間）。

    入れるもの＝頁の定義と、組んだ完全版の頁のpath。任意の spec["preflight"] は
    {"reader":"読者宣言の1行","allowed":["語",…]}（無ければ既定の読者・許可語なし）。
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
        "頁: %s（Read で開く）" % page_path,
        "読者宣言: %s。説明なしで使ってよい語%s（頁の%sの節とホバーで説明の付いた語は除く）"
        % (reader, allowed_text, glossary),
        "1. %sの節の各問について、それぞれの選択肢を選んだ場合に何が変わるかを、"
        "この頁だけから説明してください。説明できない問いは「説明不能」と書いてください。"
        "続けて、%sの節の入力欄だけを見て（上の本文を見ずに）、各選択肢の違いが分かるか答えてください。"
        "見た目が違うのに絵が無い選択肢があれば、その問いを挙げてください。" % (decision, decision),
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
    # 2026-10-08（判断の頁を赤ペン流に寄せた・案1）：推奨があるのに非推奨の案に利点が無い問いを知らせる。
    # ⚠️止めない（知らせるだけ）。この検査の不具合で頁が組めなくならないよう、落ちても続ける。
    try:
        for warning in decision_option_warnings(spec["content"]):
            print(warning)
    except Exception as exc:  # noqa: BLE001 - 助言の検査なので頁の組み立てを止めない
        print("ⓘ 実質1択の検査は走らなかった（%s）" % exc)
    full, shaped = build(spec, project_root)
    lines = ["書き出した:", "  完全版 (検品証用): " + full, "  器用 (publish用) : " + shaped, ""]
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
    counts = density(built)
    body_bytes = len(built.encode("utf-8"))
    lines.append("")
    lines.append("部品の濃さ: " + " ".join("%s=%d" % (n, c) for n, c in counts))
    advice = advise_density(counts, body_bytes)
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
            lines.append(preflight_prompt(spec, full))
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

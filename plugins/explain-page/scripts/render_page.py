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
    html = render_components(
        plan, title=spec["title"], content=spec["content"], glossary_entries=entries
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
                "画像が0＝スライドや写真があるなら "
                '"image":{"path":"…png","caption":"…","source":"…","num":"1"}'
                "（data:URIで埋め込み・実測行が根拠欄へ自動で足される）"
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

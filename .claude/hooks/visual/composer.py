from __future__ import annotations

import re
import unicodedata

from .contracts import ExplanationPlan, HookEnvelope
from .policy import Policy, parse_controls

COMPONENT_ORDER = (
    "overview",
    "summary",
    "walkthrough",
    "examples",
    "progress",
    "visual",
    "decision",
    "evidence",
    "glossary",
    "details",
)

VISUAL_SIGNALS = (
    "図",
    "比較",
    "フロー",
    "流れ",
    "構成",
    "関係",
    "タイムライン",
    "architecture",
    "visual",
)
DECISION_SIGNALS = (
    "選び",
    "選ぶ",
    "決め",
    "採用",
    "承認",
    "判断",
    "どれ",
    "decision",
)
NO_DECISION_SIGNALS = (
    "判断は不要",
    "判断不要",
    "選択は不要",
    "選択不要",
    "承認は不要",
    "承認不要",
    "決めることはない",
    "記録用",
)
SUMMARY_SIGNALS = ("要約", "まとめ", "summary")
# 2026-08-29（ユーザー承認＝案③）：**依頼文で頁そのものを名指しで求めた**ときの語。
# ⚠️DECISION_SIGNALS 等との違いは「意図の推測ではなく名指しである」こと。
#   「承認ルート」の1語で頁を要求してしまった誤爆（2026-08-29に実発生）を繰り返さないため、
#   ここには“頁が欲しい”以外に読みようのない語だけを入れる。増やすときは同じ基準で。
EXPLICIT_PAGE_SIGNALS = ("頁", "ページ", "html", "artifact", "アーティファクト", "図解")
PROGRESS_SIGNALS = ("subagent", "進捗", "作業中", "人待ち", "複数agent")
PRIVATE_SIGNALS = ("private", "秘密", "機密", "非公開", "外部公開しない")
# 2026-10-15（利用者の選択＝案9(b) の A）：**変換だけの依頼**の印（reason conversion_only_request）。
# 付けるのは、速さの合図と変換の語の**両方**があるときだけ（合図だけ・変換の語だけでは付けない）。
# ⚠️LaTeX 指定など、速さの合図の無い変換には付けない（丁寧版の作業中は判断の頁が要ることがある）。
# ⚠️判断・図・要約の合図がある依頼、120字を超える依頼、頁を作る依頼（頁を名指しする語が変換の対象
#   「<語>を pdf…」の形でなく出る）にも付けない。
# ⚠️この印は依頼時の計画に残すだけ。差し戻さないかは停止の照合（entrypoint.py の conversion_only_turn）が
#   応答の長さ・検品証の有無と合わせて決める。
# 実測（2026-10-15）＝10/10〜14 の利用者の依頼文 65 件に当てて、印が付いたのは5件（どれも PDF への
#   速い変換の依頼）・付けてはいけない依頼への印は0件（65件を目で確認）。
SPEED_SIGNALS = ("早く", "はやく", "爆速", "そのまま", "とりあえず", "仮")
CONVERSION_SIGNALS = (
    "pdfにして",
    "pdf化",
    "pdfに書き出",
    "docxにして",
    "wordにして",
    "ドキュメント化",
    "印刷して",
)
CONVERSION_PROMPT_MAX_CHARS = 120
# 頁を名指しする語のすぐ後に「を」とこの語が続くなら、その頁は変換の対象（頁を作る依頼ではない）。
PAGE_OBJECT_TARGETS = ("pdf", "docx", "word", "印刷")
# 「仮」は熟語の頭（仮説・仮定・仮発表 など）では速さの合図ではない＝次の字が漢字なら数えない。
_KANJI_FIRST = chr(0x4E00)
_KANJI_LAST = chr(0x9FFF)


def _ordered(values: set[str]) -> tuple[str, ...]:
    return tuple(name for name in COMPONENT_ORDER if name in values)


def _compact(text: str) -> str:
    """全角と半角をそろえ（NFKC）、小文字にして、空白を全部除く（「PDF 化」「ＰＤＦ化」も同じに読む）。"""
    folded = unicodedata.normalize("NFKC", text or "").lower()
    return "".join(ch for ch in folded if not ch.isspace())


def _speed_hits(compact: str) -> tuple[str, ...]:
    hits = []
    for word in SPEED_SIGNALS:
        if word != "仮":
            if word in compact:
                hits.append(word)
            continue
        index = compact.find(word)
        while index >= 0:
            following = compact[index + 1:index + 2]
            if not (following and _KANJI_FIRST <= following <= _KANJI_LAST):
                hits.append(word)
                break
            index = compact.find(word, index + 1)
    return tuple(hits)


def _page_words_only_as_object(compact: str) -> bool:
    """頁を名指しする語が、どれも「<語>を pdf…」（変換の対象）の形でしか出ないなら True。

    ⚠️「頁を作ってPDFにして」「アーティファクト＆PDFにして」は頁を作る依頼＝False（印を付けない）。
    """
    for word in EXPLICIT_PAGE_SIGNALS:
        index = compact.find(word)
        while index >= 0:
            rest = compact[index + len(word):]
            if not (rest.startswith("を") and rest[1:].startswith(PAGE_OBJECT_TARGETS)):
                return False
            index = compact.find(word, index + 1)
    return True


def conversion_signals(prompt: str) -> tuple[str, ...]:
    """変換だけの依頼なら、当たった合図（速さの合図・変換の語）を返す。そうでなければ空。

    条件＝速さの合図と変換の語の両方がある ∧ 判断・図・要約の合図が無い ∧ 120字以内
         ∧ 頁を名指しする語は変換の対象としてだけ出る。依頼文だけを見る（応答は見ない）。
    """
    text = (prompt or "").strip()
    if not text or len(text) > CONVERSION_PROMPT_MAX_CHARS:
        return ()
    compact = _compact(text)
    speed = _speed_hits(compact)
    conversion = tuple(word for word in CONVERSION_SIGNALS if word in compact)
    if not speed or not conversion:
        return ()
    if any(word in compact for word in DECISION_SIGNALS + VISUAL_SIGNALS + SUMMARY_SIGNALS):
        return ()
    if not _page_words_only_as_object(compact):
        return ()
    return speed + conversion


def structure_weight(text: str) -> int:
    count = 0
    in_fence = False
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("```") or stripped.startswith("~~~"):
            in_fence = not in_fence
            continue
        if in_fence or not stripped:
            continue
        if stripped.startswith("|") and stripped.count("|") >= 2:
            if set(stripped.replace("|", "").replace(":", "").strip()) <= {"-"}:
                continue
            count += 1
        elif stripped.startswith("#"):
            count += 1
        elif re.match(r"^(?:[-*+]\s+|\d+[.)]\s+)", stripped):
            count += 1
    return count


def compose_plan(envelope: HookEnvelope, policy: Policy) -> ExplanationPlan:
    if not policy.enabled:
        return ExplanationPlan(
            audience=policy.default_audience,
            depth=policy.default_depth,
            components=(),
            reason_codes=("explicit_off",),
            provisional=envelope.event in {"UserPromptSubmit", "pre_llm_call"},
            should_continue=False,
            delivery="markdown",
            publish_policy=policy.publish,
        )

    text = "\n".join(
        part for part in (envelope.user_message, envelope.response_text) if part
    ).lower()
    # ⚠️「頁を名指しで求めたか」は**依頼文だけ**を見る。応答側は見ない＝私が本文で
    #   「HTML」と書いただけで頁が必須になるのを避ける（応答が終わった時点の判定では
    #   user_message は空なので、この印は予告の reason_codes に載せて持ち回す）。
    prompt_text = (envelope.user_message or "").lower()
    explicit_page = any(signal in prompt_text for signal in EXPLICIT_PAGE_SIGNALS)
    controls = parse_controls(text)
    components = set(policy.default_components)
    reasons = ["project_novice_default"]

    if any(signal in text for signal in VISUAL_SIGNALS):
        components.add("visual")
        reasons.append("visual_comparison")
    no_decision = any(signal in text for signal in NO_DECISION_SIGNALS)
    if any(signal in text for signal in DECISION_SIGNALS) and not no_decision:
        components.add("decision")
        reasons.append("decision_required")
    elif no_decision:
        reasons.append("decision_not_required")
    if any(signal in text for signal in SUMMARY_SIGNALS):
        components.add("summary")
        reasons.append("summary_requested")
    if any(signal in text for signal in PROGRESS_SIGNALS):
        components.add("progress")
        reasons.append("multi_agent_review")
    private = any(signal in text for signal in PRIVATE_SIGNALS)
    if private:
        reasons.append("private_local_only")
    if len(envelope.response_text) >= policy.min_chars:
        components.add("summary")
        reasons.append("long_prose")
    if structure_weight(envelope.response_text) >= policy.min_blocks:
        components.add("summary")
        reasons.append("heavy_structure")

    if explicit_page:
        reasons.append("explicit_page_request")
    # 2026-10-15（案9(b)）：変換だけの依頼の印。依頼文だけを見る（応答が終わった時点では依頼文が空なので、
    #   この印は依頼時の計画の reason_codes に載せて持ち回す＝explicit_page_request と同じ）。
    if conversion_signals(envelope.user_message or ""):
        reasons.append("conversion_only_request")
    components.update(controls.add_components)
    components.difference_update(controls.remove_components)
    depth = controls.depth or policy.default_depth
    delivery = (
        "local_html"
        if private or explicit_page or {"visual", "decision", "summary"} & components
        else "markdown"
    )

    return ExplanationPlan(
        audience=policy.default_audience,
        depth=depth,
        components=_ordered(components),
        reason_codes=tuple(dict.fromkeys(reasons)),
        provisional=envelope.event in {"UserPromptSubmit", "pre_llm_call"},
        should_continue=False,
        delivery=delivery,
        publish_policy="never" if private else policy.publish,
    )

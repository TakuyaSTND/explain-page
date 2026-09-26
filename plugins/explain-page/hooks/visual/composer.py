from __future__ import annotations

import re

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


def _ordered(values: set[str]) -> tuple[str, ...]:
    return tuple(name for name in COMPONENT_ORDER if name in values)


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

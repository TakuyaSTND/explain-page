from __future__ import annotations

import hashlib
import json
import os
from dataclasses import replace
from pathlib import Path
from typing import Any

from .adapters import from_claude, from_codex, from_hermes
from .artifact_inspection import inspect_artifact_html
from .composer import COMPONENT_ORDER, compose_plan
from .contracts import HookEnvelope
from .glossary import load_glossary_snapshot
from . import branding
from .instructions import compile_directive, compile_stop_reminder
from .policy import Policy
from .receipts import build_receipt, describe_skip, receipt_problems, validate_receipt
from .state import StateStore
from .subagents import digest_from_payload, is_unattributed
from .turn_marker import write_turn_marker

try:
    from .visual_smoke import run_visual_smoke
except ImportError:  # Agent C's smoke module may be added after this seam.
    run_visual_smoke = None  # type: ignore[assignment]

try:
    from .readability import Hit, Rules, check_text, load_rules, strip_code
except ImportError:  # readability module may not be present in older checkouts.
    Hit = Rules = None  # type: ignore[assignment]
    check_text = load_rules = strip_code = None  # type: ignore[assignment]


DIAGNOSTIC_ERROR_TYPES = frozenset(
    {
        "rate_limit",
        "overloaded",
        "authentication_failed",
        "oauth_org_not_allowed",
        "billing_error",
        "invalid_request",
        "model_not_found",
        "server_error",
        "max_output_tokens",
        "unknown",
    }
)


def _in_project_scope(cwd: object, project_root: str) -> bool:
    if not isinstance(cwd, str) or not cwd or not project_root:
        return False
    try:
        current = os.path.normcase(os.path.realpath(os.path.abspath(cwd)))
        root = os.path.normcase(os.path.realpath(os.path.abspath(project_root)))
        return os.path.commonpath((current, root)) == root
    except (OSError, ValueError):
        return False


def _diagnostic_type(data: dict[str, Any]) -> str:
    raw = data.get("error_type")
    if not isinstance(raw, str):
        error = data.get("error")
        raw = error.get("type") if isinstance(error, dict) else ""
    normalized = raw.strip().lower() if isinstance(raw, str) else ""
    return normalized if normalized in DIAGNOSTIC_ERROR_TYPES else "unknown"


def _stop_failure_result(data: dict[str, Any], project_root: str) -> dict[str, str]:
    if not _in_project_scope(data.get("cwd"), project_root):
        return {}
    # Claude ignores JSON diagnostics for StopFailure. terminalSequence is the
    # only supported wire field, so include only a fixed, allowlisted class.
    diagnostic_type = _diagnostic_type(data)
    return {
        "terminalSequence": (
            "\x1b]0;Understanding Composer StopFailure: "
            f"{diagnostic_type}\x07"
        )[:256]
    }


def _normalize_plan(plan: Any, policy: Policy):
    components = set(plan.components)
    reasons = list(plan.reason_codes)
    if policy.explain_mode == "always":
        components.add("summary")
        reasons.append("explicit_always")
    known = tuple(name for name in COMPONENT_ORDER if name in components)
    unknown = tuple(name for name in plan.components if name not in COMPONENT_ORDER)
    return replace(
        plan,
        components=tuple(dict.fromkeys((*known, *unknown))),
        reason_codes=tuple(dict.fromkeys(reasons)),
        delivery=("local_html" if policy.explain_mode == "always" else plan.delivery),
        deprecated_aliases=policy.deprecated_aliases,
    )


def _confirm_plan(saved: Any, live: Any) -> Any:
    """依頼時の「予告」と、応答の実態から作った計画を突き合わせて確定する。

    2026-08-29（ユーザー承認＝案③）。⚠️これまでは保存済みの予告をそのまま確定として
    使っていたため、次の2つが同時に起きていた。
      不具合3＝応答の実態（長さ・構造・判断の有無）が**一度も見られない**。
               依頼文が素っ気なければ、どれだけ長く判断だらけの応答を書いても検査されない。
      不具合4＝逆に依頼文へ「決めたい」と書くと、6文字の返事のターンでも頁を要求される。
    ∴componentは「予告 ∪ 実態」の和集合にし、**出し方は実態で決める**。
      ただし依頼文で頁を名指しで求めていた場合（explicit_page_request）だけは予告を優先する
      ＝人が明示的に頁を求めたのに、私が短く答えて逃げる経路を残さないため。

    入れるもの＝予告（無ければ None）と実態。返るもの＝確定した1つの計画。
    """
    if saved is None:
        return live
    merged = set(saved.components) | set(live.components)
    known = tuple(name for name in COMPONENT_ORDER if name in merged)
    unknown = tuple(
        name for name in (*saved.components, *live.components)
        if name not in COMPONENT_ORDER
    )
    # ⚠️出し方は「予告か実態のどちらかが頁を要るなら頁」＝緩む側に倒さない。
    #   案③の原案は「実態だけで決める」だったが、それだと
    #   〈依頼＝3案を図で比較して選びたい／応答＝説明文だけでArtifactはありません〉のような
    #   **手を抜いた応答が検査を素通りする**。これは2026-08-28までに置かれた12件の防御
    #   （test_entrypoint.py・test_noop_turn_exemption.py）が明示的に禁じている挙動なので、
    #   独断で外さない。∴不具合4（短い返事でも頁を要求される）はここでは直らない。
    #   どちらを取るかは人の裁定が要る＝2026-08-29時点で未裁定。
    delivery = (
        "local_html"
        if "local_html" in {saved.delivery, live.delivery}
        else live.delivery
    )
    # 非公開の合図はどちらか一方で出ていれば守る（緩む側に倒さない）。
    publish = (
        "never"
        if "never" in {saved.publish_policy, live.publish_policy}
        else live.publish_policy
    )
    return replace(
        saved,
        components=tuple(dict.fromkeys((*known, *unknown))),
        reason_codes=tuple(
            dict.fromkeys((*saved.reason_codes, *live.reason_codes, "confirmed_on_stop"))
        ),
        delivery=delivery,
        publish_policy=publish,
    )


def _compile_plan(
    plan: Any,
    html_output_path: str | Path,
    *,
    runtime: str | None = None,
    render_page_path: str | None = None,
) -> str:
    directive = compile_directive(
        plan, html_output_path, runtime=runtime, render_page_path=render_page_path
    )
    if plan.deprecated_aliases:
        directive += "\n[deprecated_aliases] " + ",".join(plan.deprecated_aliases)
    return directive


def build_preflight_context(
    envelope: HookEnvelope,
    *,
    policy: Policy,
    html_output_path: str | Path,
    render_page_path: str | None = None,
) -> str:
    if not policy.enabled or "can_context" not in envelope.capabilities:
        return ""
    plan = _normalize_plan(compose_plan(envelope, policy), policy)
    return _compile_plan(
        plan, html_output_path, runtime=envelope.runtime, render_page_path=render_page_path
    )


def _project_hash(project_root: str) -> str:
    normalized = os.path.normcase(os.path.abspath(project_root))
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def _describe_shape(
    path: str,
    glossary_entries: Any,
    required_components: tuple[str, ...],
) -> str:
    """公開しようとしたHTMLの形を一行で述べる。返るもの＝追記する文（無理なら空文字）。

    ⚠️検品証を作れない置き場でも中身は見る（2026-09-01のユーザー裁定）。
      これが無いと「検品証が無い」しか出ず、**何が足りないのか**が分からなかった。
    ⚠️止めはしない＝読めない・大きすぎる等はすべて黙って諦める（作業を妨げない）。
    """
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as handle:
            body = handle.read(400_000)
    except OSError:
        return ""
    try:
        inspection = inspect_artifact_html(
            body,
            required_components=required_components,
            glossary_entries=glossary_entries or {},
        )
    except Exception:  # 検査で落ちても作業は止めない
        return ""
    parts = []
    present = len(inspection.present_components)
    parts.append("部品の目印=%d個" % present)
    if inspection.missing_components:
        parts.append("足りない部品=" + ",".join(inspection.missing_components[:4]))
    if inspection.unwrapped_identifiers:
        parts.append("未包装=" + ",".join(inspection.unwrapped_identifiers[:3]))
    if inspection.errors:
        parts.append("誤り=" + inspection.errors[0][:60])
    if present == 0:
        parts.append("⚠️目印が1つも無い＝道具で組んでいない頁に見える")
    return " ／ 中身を見た: " + " / ".join(parts)


def _readability_hits_from_text(text: str, rules_path: Any) -> tuple[Any, ...]:
    """本文（すでにcode/pre除去済み想定でなくても良い＝ここでstrip_codeを掛ける）に
    読みやすさ規則を掛け、当たり（Hit）を返す。返せない・規則が無ければ空タプル。

    ⚠️止めはしない＝読めない・規則ファイルが無い等はすべて黙って空を返す。
    """
    if check_text is None or load_rules is None or strip_code is None or not rules_path:
        return ()
    try:
        rules = load_rules(rules_path)
        return tuple(check_text(strip_code(text), rules))
    except Exception:  # 読みやすさ判定の失敗で本体の検品証処理を止めない
        return ()


def _readability_note(hits: tuple[Any, ...], *, label: str) -> str:
    if not hits:
        return ""
    shown = "、".join(f"{hit.rule}:{hit.matched}" for hit in hits[:5])
    return "[読みやすさ・%s] 当たり%d件：%s" % (label, len(hits), shown)


def _readability_note_for_path(
    path: str, rules_path: Any, *, label: str
) -> str:
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as handle:
            body = handle.read(400_000)
    except OSError:
        return ""
    hits = _readability_hits_from_text(body, rules_path)
    return _readability_note(hits, label=label)


def handle_event(
    data: dict[str, Any],
    *,
    runtime: str,
    project_root: str,
    policy: Policy,
    html_output_path: str | Path,
    state_store: StateStore | None = None,
    glossary_paths: tuple[str | Path, str | Path, str | Path] | None = None,
    local_artifact_root: str | Path | None = None,
    readability_rules_path: str | Path | None = None,
    render_page_path: str | None = None,
) -> dict[str, Any]:
    adapters = {
        "claude": from_claude,
        "codex": from_codex,
        "hermes": from_hermes,
    }
    adapter = adapters.get(runtime)
    if adapter is None:
        return {}
    if not policy.enabled:
        return {}
    if runtime in {"claude", "codex"}:
        envelope = adapter(
            data,
            project_root,
            max_transcript_bytes=policy.max_transcript_bytes,
        )
    else:
        envelope = adapter(data, project_root)
    if "can_diagnostic" in envelope.capabilities:
        return _stop_failure_result(data, project_root)
    if not envelope.valid_for_state:
        return {}
    project_key = _project_hash(project_root)
    if "can_context" in envelope.capabilities:
        plan = _normalize_plan(compose_plan(envelope, policy), policy)
        if state_store is not None:
            state_store.save_plan(
                runtime=runtime,
                project_hash=project_key,
                session_id=envelope.session_id,
                turn_id=envelope.turn_id,
                plan=plan,
                ttl_seconds=policy.state_ttl_seconds,
            )
        # 2026-09-25：Codexには「頁を公開した」道具の合図（PostToolUse）が無いので、
        # ここ（依頼の受付）で「いまの会話とその回」の印を残す。render_page.py が
        # --runtime codex のときにこの印を読んで、自分の代わりに検品の記録を書く。
        # ⚠️Claude・Hermesでは書かない＝印が要るのはCodexだけ。書けなくても止めない
        #   （write_turn_marker は例外を外へ投げず bool を返すだけ）。
        if runtime == "codex" and local_artifact_root is not None:
            write_turn_marker(
                local_artifact_root,
                runtime,
                project_key,
                envelope.session_id,
                envelope.turn_id,
            )
        context = _compile_plan(
            plan, html_output_path, runtime=runtime, render_page_path=render_page_path
        )
        if runtime == "hermes":
            return {"context": context}
        return {
            "hookSpecificOutput": {
                "hookEventName": envelope.event,
                "additionalContext": context,
            }
        }

    if "can_subagent" in envelope.capabilities:
        if state_store is None:
            return {}
        try:
            digest = digest_from_payload(runtime, data)
        except ValueError:
            return {}
        state_store.save_digest(
            runtime=envelope.runtime,
            profile_id=envelope.profile_id,
            session_id=envelope.session_id,
            project_hash=project_key,
            digest=digest,
            ttl_seconds=policy.state_ttl_seconds,
        )
        return {}

    if "can_receipt" in envelope.capabilities:
        if state_store is None or glossary_paths is None or local_artifact_root is None:
            return {}
        tool_input = data.get("tool_input") if isinstance(data.get("tool_input"), dict) else {}
        tool_name = str(data.get("tool_name") or "").lower()
        preview_event = tool_name in {"open_preview", "artifact", "preview"}
        raw_path = tool_input.get("file_path") or tool_input.get("path") or tool_input.get("url")
        if not isinstance(raw_path, str) or not raw_path.lower().endswith(".html"):
            return {}
        glossary, glossary_entries = load_glossary_snapshot(*glossary_paths)
        saved_plan = state_store.load_plan(
            runtime=runtime,
            project_hash=project_key,
            session_id=envelope.session_id,
            turn_id=envelope.turn_id,
        )
        required_components = (
            _normalize_plan(saved_plan, policy).components
            if saved_plan is not None
            else _normalize_plan(compose_plan(envelope, policy), policy).components
        )
        smoke_result: Any = {"status": "not_run", "errors": []}
        if preview_event:
            if run_visual_smoke is None:
                smoke_result = {
                    "status": "fail",
                    "errors": ["visual smoke unavailable"],
                }
            else:
                try:
                    smoke_result = run_visual_smoke(
                        raw_path,
                        timeout_seconds=policy.visual_smoke_timeout_seconds,
                    )
                except Exception as exc:  # smoke failure must block, not crash
                    smoke_result = {
                        "status": "fail",
                        "errors": [f"visual smoke error: {type(exc).__name__}"],
                    }
        try:
            receipt = build_receipt(
                raw_path,
                envelope=envelope,
                glossary=glossary,
                glossary_entries=glossary_entries,
                local_root=local_artifact_root,
                previewed=preview_event,
                max_artifact_bytes=policy.max_artifact_bytes,
                required_components=required_components,
                visual_smoke_result=smoke_result,
            )
        except (OSError, ValueError) as exc:
            # 2026-08-29（ユーザー承認＝不具合1）：ここは以前 return {} で**黙って降りていた**。
            # 承認済みの置き場の外へ頁を書くと検品証が1枚も作られないのに、警告もログも
            # 出なかった（実測：08-29に公開した2枚が0枚。記録上の最後の検品証は08-28）。
            # fail-open と同じ「失敗が沈黙として現れる」型なので、①数えられる場所に残し
            # ②その場でも文字にして返す。⚠️止めはしない＝作業は続行できる。
            note = describe_skip(raw_path, exc, local_artifact_root)
            state_store.save_receipt_skip(
                runtime=envelope.runtime,
                project_hash=project_key,
                session_id=envelope.session_id,
                turn_id=envelope.turn_id,
                path=str(raw_path),
                reason=note,
                ttl_seconds=policy.state_ttl_seconds,
            )
            # 2026-08-31：今日これで何回目かを添える。
            # ⚠️中身は24時間で消えるが回数は残る＝**その場で気づける**ようにする。
            #   この件で「起きなかった」と「記録が消えた」を区別できず丸一日を使った。
            tally = state_store.load_receipt_skip_tally(project_hash=project_key, days=1)
            if tally:
                note += " ／ 今日これで %d 回目" % tally[0][1]
            # 2026-09-01（ユーザー裁定＝公開しようとした時点で見る）：
            # 検品証を作れない置き場でも、**中身は見る**。⚠️これが無いと、手書きの頁は
            #   「検品証が無い」しか言われず、**何が足りないのか**が分からなかった。
            # ⚠️止めはしない＝作業は続行できる（今までと同じ）。読めなければ黙って諦める。
            note += _describe_shape(raw_path, glossary_entries, required_components)
            # 2026-09-08：読みやすさ関門（否定側の言い回し）。offなら何もしない。
            #   PostToolUseはenforceでも「知らせるだけ」（差し戻しはStopの側だけで行う）。
            if policy.readability != "off":
                extra = _readability_note_for_path(
                    raw_path, readability_rules_path, label=policy.readability
                )
                if extra:
                    note += " ／ " + extra
            if runtime == "hermes":
                return {"message": note}
            return {
                "systemMessage": note,
                "hookSpecificOutput": {
                    "hookEventName": envelope.event,
                    "additionalContext": note,
                },
            }
        state_store.save_receipt(
            project_hash=project_key,
            receipt=receipt,
            ttl_seconds=policy.state_ttl_seconds,
        )
        # 2026-09-08：検品証を作れた頁でも、読みやすさの当たりがあれば知らせる（offなら何もしない）。
        if policy.readability != "off":
            success_note = _readability_note_for_path(
                raw_path, readability_rules_path, label=policy.readability
            )
            if success_note:
                if runtime == "hermes":
                    return {"message": success_note}
                return {
                    "hookSpecificOutput": {
                        "hookEventName": envelope.event,
                        "additionalContext": success_note,
                    }
                }
        return {}

    if runtime == "hermes" and envelope.event == "pre_verify" and not envelope.coding:
        return {}
    if "can_continue" not in envelope.capabilities:
        return {}
    if envelope.stop_hook_active or envelope.attempt:
        return {}
    saved_plan = None
    if state_store is not None:
        saved_plan = state_store.load_plan(
            runtime=runtime,
            project_hash=project_key,
            session_id=envelope.session_id,
            turn_id=envelope.turn_id,
        )
    # 予告（依頼時）と実態（応答）を突き合わせて確定する。予告が無ければ実態がそのまま確定。
    plan = _confirm_plan(saved_plan, compose_plan(envelope, policy))
    plan = _normalize_plan(plan, policy)
    receipts = ()
    if state_store is not None:
        receipts = state_store.load_receipts(
            runtime=runtime,
            project_hash=project_key,
            session_id=envelope.session_id,
            turn_id=envelope.turn_id,
        )
    receipt_is_valid = False
    if (
        receipts
        and glossary_paths is not None
        and local_artifact_root is not None
    ):
        current_glossary, _ = load_glossary_snapshot(*glossary_paths)
        receipt_is_valid = any(
            validate_receipt(
                receipt,
                current_glossary,
                local_root=local_artifact_root,
                max_artifact_bytes=policy.max_artifact_bytes,
                required_components=plan.components,
            )
            for receipt in receipts
        )
    # 2026-09-08：読みやすさ関門（否定側の言い回し）。response_textは長い転写の末尾から
    #   組み立てられるため、古い・別ターンの断片が残っている可能性がある（既知の課題）。
    #   ⚠️shadowはここでblockを新設しない（数えて知らせるだけ）＝enforceだけが下の早期
    #   returnを上書きする。すでに頁不足でblockする場合は、この当たりを理由に併記してよい。
    readability_hits: tuple[Any, ...] = ()
    if policy.readability != "off":
        readability_hits = _readability_hits_from_text(
            envelope.response_text, readability_rules_path
        )
    if (
        plan.delivery != "local_html"
        or receipt_is_valid
        # 2026-08-28（ユーザー委任＝claims/claude-code-hook-noop-20260828.md）：
        # **作業の実体が無いターンは検品証を要求しない**＝通知への応答・現状維持の確認のような、
        # ターン内に tool_use が1つも無い応答にまで頁の再公開を強いない。
        # 判定は転写の**末尾**読み（adapters._claude_turn_tool_activity）。判定できない時は
        # turn_has_tool_use=True の既定に落ちて従来どおり差し戻す（fail-closed）。
        or not envelope.turn_has_tool_use
    ):
        if policy.readability == "enforce" and readability_hits:
            reason = _readability_note(readability_hits, label="enforce")
            if runtime == "hermes":
                return {"action": "continue", "message": reason}
            return {"decision": "block", "reason": reason}
        return {}
    if state_store is not None and not state_store.claim_response(
        runtime=runtime,
        project_hash=project_key,
        session_id=envelope.session_id,
        turn_id=envelope.turn_id,
        response_sha256=envelope.response_sha256,
        ttl_seconds=policy.state_ttl_seconds,
    ):
        return {}
    # 2026-09-26（見やすさ V4）：依頼時の計画が残っていれば、書き方の決まりはその回の依頼時に
    # 出ている＝全文を繰り返さず、計画・直し方・後から増えた部品の書き方だけにする。
    # 依頼時の計画が無ければ（依頼時の指示が出ていない恐れ）従来どおり全文に倒す。
    if saved_plan is not None:
        reason = compile_stop_reminder(
            plan,
            tuple(saved_plan.components),
            html_output_path,
            runtime=runtime,
            render_page_path=render_page_path,
        )
        if plan.deprecated_aliases:
            reason += "\n[deprecated_aliases] " + ",".join(plan.deprecated_aliases)
    else:
        reason = _compile_plan(
            plan, html_output_path, runtime=runtime, render_page_path=render_page_path
        )
    # 2026-09-01（ユーザー裁定＝割引採用）：検品証はあるのに1つも通らなかったときは、
    # **なぜ差し戻したか**を1行添える。⚠️要求そのものは変えない（頁は要る）。
    #   この形になる典型＝尋問の回答集め（branding.QA_PAGE_TOOL の道具）のHTMLだけを出した回。
    #   その出力は部品の目印を持たないので検品証にならない＝報告の頁を別に作る必要がある。
    # 2026-09-26（見やすさ V4）：いちばん新しい検品証が通らない理由を具体的に添える
    #   （最も多かった「公開のあとで要る部品が変わった」も、それと分かる）。
    if receipts and not receipt_is_valid:
        qa_tool = getattr(branding, "QA_PAGE_TOOL", None)
        line = "[receipt_not_valid] このターンの検品証は %d 件あるが、どれも条件を満たしていない。" % len(receipts)
        if glossary_paths is not None and local_artifact_root is not None:
            current_glossary, _ = load_glossary_snapshot(*glossary_paths)
            problems = receipt_problems(
                receipts[-1],
                current_glossary,
                local_root=local_artifact_root,
                max_artifact_bytes=policy.max_artifact_bytes,
                required_components=plan.components,
            )
            if problems:
                line += "いちばん新しい頁の理由＝" + "／".join(problems[:3]) + "。"
        if qa_tool:
            line += (
                "⚠️尋問の回答集め（" + qa_tool + "）のHTMLは部品の目印を持たないので検品証にならない"
                "＝報告と判断の頁を別にレンダラーで作る。"
            )
        else:
            line += "報告と判断の頁を別にレンダラーで作る。"
        reason += chr(10) + line
    elif not receipts:
        reason += chr(10) + (
            "[receipt_missing] このターンに検品証が1件も無い"
            "（頁を公開していない、または承認済みの置き場の外に書いた）。"
        )
    if readability_hits:
        # すでにblockするこのターンに、読みやすさの当たりを併記する（shadow/enforceどちらでも
        # 併記してよい＝2026-09-08。新たにblockを引き起こすのはenforceの早期return側だけ）。
        reason += chr(10) + _readability_note(readability_hits, label=policy.readability)
    if state_store is not None:
        digests = state_store.load_digests(
            runtime=envelope.runtime,
            profile_id=envelope.profile_id,
            session_id=envelope.session_id,
            project_hash=project_key,
            parent_turn_id=envelope.turn_id,
        )
        # 2026-08-31（別セッションからの照会で発覚）：出所の分からない記録の内容は渡さない。
        # ⚠️「作り直さないでいい」のような、ユーザーの言葉に見える文が混ざっていた。
        #   それを status=success の結果として差し込むと、届いていない発言が
        #   確定した承認として読める。∴内容は落とし、件数だけ知らせる（沈黙にはしない）。
        named = [item for item in digests if not is_unattributed(item)]
        dropped = len(digests) - len(named)
        if named:
            digest_payload = [
                {
                    "goal": item.goal,
                    "result": item.result,
                    "evidence": list(item.evidence),
                    "risk": item.risk,
                    "needs_human": item.needs_human,
                    "status": item.status,
                }
                for item in named
            ]
            reason += "\n[subagent_digests]\n" + json.dumps(
                digest_payload, ensure_ascii=False
            )
        if dropped:
            reason += (
                "\n[subagent_digests_dropped] n=%d"
                " 出所が分からないので内容は渡さない（ユーザーの発言ではない）" % dropped
            )
    if runtime == "hermes":
        return {
            "action": "continue",
            "message": reason,
        }
    return {
        "decision": "block",
        "reason": reason,
    }

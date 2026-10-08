from __future__ import annotations

import sys
import unittest
from pathlib import Path

HOOKS_DIR = Path(__file__).resolve().parents[1]
if str(HOOKS_DIR) not in sys.path:
    sys.path.insert(0, str(HOOKS_DIR))

from visual.contracts import ExplanationPlan
from visual.glossary import GlossaryEntry
from visual.glossary_check import check_html
from visual.render_components import render_components


class ComponentRendererTests(unittest.TestCase):
    def test_mobile_tooltip_uses_viewport_fixed_panel(self):
        plan = ExplanationPlan(
            audience="project_novice",
            depth="deep",
            components=("overview",),
            reason_codes=(),
            provisional=False,
            should_continue=False,
            delivery="local_html",
            publish_policy="never",
        )

        html = render_components(plan, title="用語", content={"overview": "説明"})

        self.assertIn(".t::after{position:fixed", html)
        self.assertIn("bottom:1rem", html)

    def test_decision_builder_keeps_newline_escape_inside_javascript(self):
        plan = ExplanationPlan(
            audience="project_novice",
            depth="deep",
            components=("decision",),
            reason_codes=(),
            provisional=False,
            should_continue=False,
            delivery="local_html",
            publish_policy="never",
        )

        html = render_components(
            plan,
            title="判断",
            content={"decision": ["案A"]},
        )

        self.assertIn("lines.join('\\n')", html)

    def test_mobile_glossary_switches_to_one_column(self):
        plan = ExplanationPlan(
            audience="project_novice",
            depth="deep",
            components=("glossary",),
            reason_codes=(),
            provisional=False,
            should_continue=False,
            delivery="local_html",
            publish_policy="never",
        )

        html = render_components(
            plan,
            title="用語",
            content={"glossary": "長い用語：長い説明。"},
        )

        self.assertIn("dl.gl{grid-template-columns:1fr}", html)
        self.assertIn("dl.gl dt{white-space:normal}", html)

    def test_decision_can_render_per_judgment_objections(self):
        plan = ExplanationPlan(
            audience="project_novice",
            depth="deep",
            components=("decision",),
            reason_codes=(),
            provisional=False,
            should_continue=False,
            delivery="local_html",
            publish_policy="never",
        )

        html = render_components(
            plan,
            title="判定",
            content={
                "decision": {
                    "options": ["このまま進める"],
                    "judgments": ["致命傷：根拠が不足"],
                }
            },
        )

        self.assertIn('name="objection"', html)
        self.assertIn("これは違う", html)
        # 2026-10-08：回答文の固定形に合わせ、異議の行は「異議. 対象: 理由」になった。
        self.assertIn("'異議. '", html)

    def test_decision_has_select_all_fallback(self):
        plan = ExplanationPlan(
            audience="project_novice",
            depth="deep",
            components=("decision",),
            reason_codes=(),
            provisional=False,
            should_continue=False,
            delivery="local_html",
            publish_policy="never",
        )

        html = render_components(
            plan,
            title="判断",
            content={"decision": ["案A", "案B"]},
        )

        self.assertIn('id="select-decision"', html)
        self.assertIn("全部選ぶ", html)
        self.assertIn("selectNodeContents", html)
        self.assertIn("catch", html)

    def test_examples_render_as_callouts_with_counterexamples(self):
        plan = ExplanationPlan(
            audience="project_novice",
            depth="deep",
            components=("examples",),
            reason_codes=(),
            provisional=False,
            should_continue=False,
            delivery="local_html",
            publish_policy="never",
        )

        html = render_components(
            plan,
            title="具体例",
            content={"examples": "例：正しい使い方。\n反例：この場合は違う。"},
        )

        self.assertIn('class="note"', html)
        self.assertIn('class="ex"', html)
        self.assertIn('class="note bad"', html)

    def test_details_component_renders_as_collapsible_sections(self):
        plan = ExplanationPlan(
            audience="project_novice",
            depth="deep",
            components=("details",),
            reason_codes=(),
            provisional=False,
            should_continue=False,
            delivery="local_html",
            publish_policy="never",
        )

        html = render_components(
            plan,
            title="細かい記録",
            content={"details": "変更file：90件の内訳。\n検査：全件PASS。"},
        )

        self.assertEqual(html.count("<details>"), 2)
        self.assertIn("<summary>変更file</summary>", html)
        self.assertIn('<div class="in">90件の内訳。</div>', html)

    def test_glossary_component_renders_as_definition_list(self):
        plan = ExplanationPlan(
            audience="project_novice",
            depth="deep",
            components=("glossary",),
            reason_codes=(),
            provisional=False,
            should_continue=False,
            delivery="local_html",
            publish_policy="never",
        )

        html = render_components(
            plan,
            title="用語",
            content={"glossary": "Hook：応答の節目で走る処理。\nReceipt：検品証。"},
        )

        self.assertIn('<dl class="gl">', html)
        self.assertIn("<dt>Hook</dt>", html)
        self.assertIn("<dd>応答の節目で走る処理。</dd>", html)

    def test_evidence_renders_as_typed_table(self):
        plan = ExplanationPlan(
            audience="project_novice",
            depth="deep",
            components=("evidence",),
            reason_codes=(),
            provisional=False,
            should_continue=False,
            delivery="local_html",
            publish_policy="never",
        )

        html = render_components(
            plan,
            title="根拠",
            content={"evidence": "実測：51件PASS。\n仮定：人の評価は未確認。"},
        )

        self.assertIn("<table>", html)
        self.assertIn("<th>種類</th>", html)
        self.assertIn('class="src s-m">実測</span>', html)
        self.assertIn('class="src s-a">仮定</span>', html)

    def test_walkthrough_renders_as_numbered_steps(self):
        plan = ExplanationPlan(
            audience="project_novice",
            depth="deep",
            components=("walkthrough",),
            reason_codes=(),
            provisional=False,
            should_continue=False,
            delivery="local_html",
            publish_policy="never",
        )

        html = render_components(
            plan,
            title="順を追って",
            content={"walkthrough": "背景：変更前の話。\n測り方：実際に試す。"},
        )

        self.assertIn('<ol class="steps">', html)
        self.assertIn('<span class="ttl">背景</span>', html)
        self.assertEqual(html.count("<li data-tone="), 2)

    def test_summary_becomes_reference_style_status_grid(self):
        plan = ExplanationPlan(
            audience="project_novice",
            depth="deep",
            components=("overview", "summary"),
            reason_codes=(),
            provisional=False,
            should_continue=False,
            delivery="local_html",
            publish_policy="never",
        )

        html = render_components(
            plan,
            title="いま何がどこまで来たか",
            content={
                "overview": "初めて見る人向けの案内です。",
                "summary": "Goal：理解できる。\nNow：作業中。\nChanged：変更あり。\nRisk：未確認。\nDecision：判断待ち。",
            },
        )

        self.assertIn('class="wrap"', html)
        self.assertIn('class="gnc"', html)
        self.assertIn("<b>GOAL</b>", html)
        self.assertIn("<b>DECISION</b>", html)
        self.assertIn("--ground:#F5F3EC", html)
        self.assertIn("max-width:56rem", html)
        self.assertIn("border-radius:2px", html)
        self.assertIn("Zen Old Mincho", html)
        self.assertIn("Zen Kaku Gothic New", html)
        self.assertIn("IBM Plex Mono", html)

    def test_selected_glossary_terms_render_as_keyboard_tooltips(self):
        plan = ExplanationPlan(
            audience="project_novice",
            depth="deep",
            components=("overview",),
            reason_codes=(),
            provisional=False,
            should_continue=False,
            delivery="local_html",
            publish_policy="never",
        )
        entries = {
            "ArtifactReceipt": GlossaryEntry(
                "ArtifactReceipt",
                "HTMLを作成・検査・previewした証拠",
                "project",
            )
        }

        html = render_components(
            plan,
            title="用語ホバー",
            content={"overview": "ArtifactReceiptを保存します。ArtifactReceiptは再利用します。"},
            glossary_entries=entries,
        )
        checked = check_html(html, entries)

        self.assertEqual(html.count('class="t"'), 1)
        self.assertIn('tabindex="0"', html)
        self.assertIn('data-d="HTMLを作成・検査・previewした証拠"', html)
        self.assertIn('aria-label="ArtifactReceipt：HTMLを作成・検査・previewした証拠"', html)
        self.assertIn(".t:hover::after", html)
        self.assertEqual(checked.mismatches, ())
        self.assertEqual(checked.unresolved, 0)
        self.assertEqual(checked.accessibility_errors, ())

    def test_labeled_content_uses_typographic_and_color_hierarchy(self):
        plan = ExplanationPlan(
            audience="project_novice",
            depth="deep",
            components=("summary", "walkthrough", "visual"),
            reason_codes=(),
            provisional=False,
            should_continue=False,
            delivery="local_html",
            publish_policy="never",
        )

        html = render_components(
            plan,
            title="理解結果",
            content={
                "summary": "Goal：全体を追えるようにする。",
                "walkthrough": "Risk：人の確認が必要。",
                "visual": "依頼\n↓\n結果",
            },
        )

        self.assertIn("<b>GOAL</b>", html)
        self.assertIn('<span class="ttl">Risk</span>', html)
        self.assertIn('data-tone="risk"', html)
        self.assertIn('class="flow-step"', html)
        # 2026-08-29：配色を参照頁のトンマナ（温かい紙色＋紺）に合わせた
        self.assertIn("--accent:#2F5D8A", html)
        self.assertIn('font-family:"Zen Old Mincho"', html)

    def test_long_paths_are_allowed_to_wrap_on_mobile(self):
        plan = ExplanationPlan(
            audience="project_novice",
            depth="deep",
            components=("details",),
            reason_codes=(),
            provisional=False,
            should_continue=False,
            delivery="local_html",
            publish_policy="never",
        )

        html = render_components(
            plan,
            title="詳細",
            content={"details": "C:/Users/example/a-very-long-project-path/file.html"},
        )

        self.assertIn("overflow-wrap:anywhere", html)

    def test_visual_and_decision_render_in_one_local_html(self):
        plan = ExplanationPlan(
            audience="project_novice",
            depth="guided",
            components=("overview", "walkthrough", "visual", "decision", "evidence"),
            reason_codes=("visual_comparison", "decision_required"),
            provisional=False,
            should_continue=False,
            delivery="local_html",
            publish_policy="never",
        )

        html = render_components(
            plan,
            title="Hook案の比較",
            content={
                "overview": "3案を比較して選びます。",
                "walkthrough": "まず違いを図で見て、その後に1案を選びます。",
                "visual": "現在 → 改良案",
                "decision": ["案A", "案B", "案C"],
                "evidence": "確認済みfixtureに基づきます。",
            },
        )

        self.assertIn('data-component="visual"', html)
        self.assertIn('data-component="decision"', html)
        self.assertIn('type="radio"', html)
        self.assertIn('<pre id="decision-prompt"', html)
        self.assertIn('id="copy-decision"', html)
        self.assertIn("--ink", html)
        self.assertNotIn("https://", html)
        self.assertNotIn("fetch(", html)

    def test_inline_rich_text_escapes_html_and_tooltips_known_code_identifiers(self):
        plan = ExplanationPlan(
            audience="project_novice",
            depth="deep",
            components=("overview",),
            reason_codes=(),
            provisional=False,
            should_continue=False,
            delivery="local_html",
            publish_policy="never",
        )
        entries = {
            "KnownId": GlossaryEntry("KnownId", "既知の識別子", "project"),
        }

        html = render_components(
            plan,
            title="安全な本文",
            content={
                "overview": (
                    "**太字** `KnownId` `<img src=x onerror=alert(1)>` "
                    "<em>raw</em>"
                )
            },
            glossary_entries=entries,
        )

        self.assertIn("<strong>太字</strong>", html)
        self.assertIn('<code><span class="t"', html)
        self.assertIn(">KnownId</span></code>", html)
        self.assertIn("&lt;img src=x onerror=alert(1)&gt;", html)
        self.assertIn("&lt;em&gt;raw&lt;/em&gt;", html)
        self.assertNotIn("<img src=x", html)
        self.assertNotIn("<em>raw</em>", html)

    def test_each_known_code_identifier_occurrence_keeps_its_glossary_wrapper(self):
        plan = ExplanationPlan(
            audience="project_novice",
            depth="deep",
            components=("overview",),
            reason_codes=(),
            provisional=False,
            should_continue=False,
            delivery="local_html",
            publish_policy="never",
        )
        entries = {
            "KnownId": GlossaryEntry("KnownId", "既知の識別子", "project"),
        }

        html = render_components(
            plan,
            title="繰り返し",
            content={"overview": "`KnownId` を確認し、もう一度 `KnownId` を確認します。"},
            glossary_entries=entries,
        )

        self.assertEqual(html.count('<span class="t"'), 2)

    def test_evidence_supports_structured_entries_source_column_and_numeric_cells(self):
        plan = ExplanationPlan(
            audience="project_novice",
            depth="deep",
            components=("evidence",),
            reason_codes=(),
            provisional=False,
            should_continue=False,
            delivery="local_html",
            publish_policy="never",
        )

        html = render_components(
            plan,
            title="根拠",
            content={
                "evidence": [
                    {"type": "実測", "content": 51, "source": "scripts/check.py"},
                    {
                        "type": "推奨",
                        "content": "次は実物を確認する",
                        "source": "docs/plan.md",
                    },
                ]
            },
        )

        self.assertEqual(html.count("<th>"), 3)
        self.assertIn("<th>どこで確かめたか</th>", html)
        self.assertIn('<td data-label="内容" class="num">51</td>', html)
        self.assertIn("<code>scripts/check.py</code>", html)
        self.assertIn("<code>docs/plan.md</code>", html)

    def test_evidence_marks_missing_source_as_unpresented(self):
        plan = ExplanationPlan(
            audience="project_novice",
            depth="deep",
            components=("evidence",),
            reason_codes=(),
            provisional=False,
            should_continue=False,
            delivery="local_html",
            publish_policy="never",
        )

        html = render_components(
            plan,
            title="根拠",
            content={
                "evidence": [{"type": "未検証", "content": "要確認"}],
            },
        )

        self.assertIn('data-missing-source="true"', html)
        self.assertIn("未提示", html)

    def test_evidence_rows_expose_source_markers_for_artifact_inspection(self):
        plan = ExplanationPlan(
            audience="project_novice",
            depth="deep",
            components=("evidence",),
            reason_codes=(),
            provisional=False,
            should_continue=False,
            delivery="local_html",
            publish_policy="never",
        )

        html = render_components(
            plan,
            title="検査可能な根拠",
            content={
                "evidence": [
                    {"type": "実測", "content": "Claim", "source": "docs/fixture.md"},
                ]
            },
        )

        self.assertIn('data-evidence="evidence-1"', html)
        self.assertIn('class="source"', html)
        self.assertIn('data-source="docs/fixture.md"', html)

    def test_manual_theme_overrides_include_light_dark_and_automatic_dark(self):
        plan = ExplanationPlan(
            audience="project_novice",
            depth="deep",
            components=("overview",),
            reason_codes=(),
            provisional=False,
            should_continue=False,
            delivery="local_html",
            publish_policy="never",
        )

        html = render_components(plan, title="テーマ", content={"overview": "説明"})

        self.assertIn(':root[data-theme="light"]', html)
        self.assertIn(':root[data-theme="dark"]', html)
        self.assertIn("@media(prefers-color-scheme:dark)", html)

    def test_overview_and_summary_are_emitted_only_when_planned(self):
        evidence_only = ExplanationPlan(
            audience="project_novice",
            depth="deep",
            components=("evidence",),
            reason_codes=(),
            provisional=False,
            should_continue=False,
            delivery="local_html",
            publish_policy="never",
        )
        hidden = render_components(
            evidence_only,
            title="非表示",
            content={"overview": "隠す", "summary": "Goal：隠す", "evidence": "実測：残す"},
        )

        self.assertNotIn('data-component="overview"', hidden)
        self.assertNotIn('data-component="summary"', hidden)
        self.assertNotIn("隠す", hidden)

        planned = ExplanationPlan(
            audience="project_novice",
            depth="deep",
            components=("overview", "summary"),
            reason_codes=(),
            provisional=False,
            should_continue=False,
            delivery="local_html",
            publish_policy="never",
        )
        shown = render_components(
            planned,
            title="表示",
            content={
                "overview": "案内",
                "summary": "Goal：目的。\nNow：現在。\nRisk：注意。\nDecision：判断。",
            },
        )

        self.assertIn('<header data-component="overview">', shown)
        self.assertIn('<section data-component="summary" id=', shown)
        self.assertIn('class="note summary-note"', shown)
        self.assertIn("<h3>3行でいうと</h3>", shown)

    def test_provenance_footer_displays_mapping_and_falls_back_to_safe_metadata(self):
        plan = ExplanationPlan(
            audience="project_novice",
            depth="deep",
            components=("overview",),
            reason_codes=(),
            provisional=False,
            should_continue=False,
            delivery="local_html",
            publish_policy="never",
        )

        provided = render_components(
            plan,
            title="証跡",
            content={
                "overview": "本文",
                "provenance": {"source": "docs/record.md", "owner": "local"},
            },
        )
        fallback = render_components(
            plan,
            title="証跡なし",
            content={"overview": "本文"},
        )

        self.assertIn('<footer data-component="provenance">', provided)
        self.assertIn("<code>docs/record.md</code>", provided)
        self.assertIn("証跡なし", fallback)
        self.assertIn("project_novice", fallback)
        self.assertIn("never", fallback)

    def test_decision_mapping_adds_recommendation_and_freeform_objection(self):
        plan = ExplanationPlan(
            audience="project_novice",
            depth="deep",
            components=("decision",),
            reason_codes=(),
            provisional=False,
            should_continue=False,
            delivery="local_html",
            publish_policy="never",
        )

        html = render_components(
            plan,
            title="判断",
            content={
                "decision": {
                    "options": [
                        "案A",
                        {"label": "案B", "recommended": True},
                    ],
                }
            },
        )

        self.assertIn("案A", html)
        self.assertIn("案B", html)
        # 2026-08-29：推奨の印は参照頁と同じバッジ姿にした。目印の recommendation は残す
        self.assertIn('recommendation">推奨</span>', html)
        self.assertIn("推奨", html)
        self.assertIn('id="decision-objection"', html)
        self.assertIn("これは違う／追加条件", html)
        self.assertIn("objection.value", html)
        self.assertIn("addEventListener('input',build)", html)

    def test_example_labels_restore_warning_bad_and_good_tones(self):
        plan = ExplanationPlan(
            audience="project_novice",
            depth="deep",
            components=("examples",),
            reason_codes=(),
            provisional=False,
            should_continue=False,
            delivery="local_html",
            publish_policy="never",
        )

        html = render_components(
            plan,
            title="例",
            content={
                "examples": "注意：確認が必要。\n反例：これは違う。\n確認済み：成功。",
            },
        )

        self.assertIn('class="note warn"', html)
        self.assertIn('class="note bad"', html)
        self.assertIn('class="note good"', html)

    def test_p3_styles_and_caption_content_are_renderable(self):
        plan = ExplanationPlan(
            audience="project_novice",
            depth="deep",
            components=("caption", "evidence"),
            reason_codes=(),
            provisional=False,
            should_continue=False,
            delivery="local_html",
            publish_policy="never",
        )

        html = render_components(
            plan,
            title="補足",
            content={
                "caption": "図の読み方です。",
                "evidence": [{"type": "実測", "content": 3, "source": "run.log"}],
            },
        )

        self.assertIn('<section data-component="caption" id=', html)
        self.assertIn('class="cap"', html)
        self.assertIn(".cap{", html)
        self.assertIn(".num", html)
        self.assertIn("td.ok", html)
        self.assertIn("td.ng", html)
        self.assertIn("h3{", html)
        self.assertIn("footer{", html)
        self.assertIn("code{", html)

    def test_evidence_caption_is_reachable_from_normal_evidence_component(self):
        plan = ExplanationPlan(
            audience="project_novice",
            depth="deep",
            components=("evidence",),
            reason_codes=(),
            provisional=False,
            should_continue=False,
            delivery="local_html",
            publish_policy="never",
        )

        html = render_components(
            plan,
            title="Evidence caption",
            content={
                "evidence": {
                    "entries": [
                        {"type": "実測", "content": "1件", "source": "tests/test.py"}
                    ],
                    "caption": "分母は全1件。",
                }
            },
        )

        self.assertIn('<p class="cap">分母は全1件。</p>', html)

    def test_mobile_evidence_rows_and_objection_textarea_are_readable(self):
        plan = ExplanationPlan(
            audience="project_novice",
            depth="deep",
            components=("decision", "evidence"),
            reason_codes=(),
            provisional=False,
            should_continue=False,
            delivery="local_html",
            publish_policy="never",
        )

        html = render_components(
            plan,
            title="Mobile readability",
            content={
                "decision": {"options": [{"label": "採用", "recommended": True}]},
                "evidence": [
                    {"type": "実測", "content": "1件", "source": "docs/long/path.md"}
                ],
            },
        )

        self.assertIn('data-label="種類"', html)
        self.assertIn('data-label="内容"', html)
        self.assertIn('data-label="どこで確かめたか"', html)
        self.assertIn('section[data-component="evidence"] .scroll{border:0', html)
        self.assertIn('.objection-freeform+textarea{display:block;width:100%', html)
        self.assertIn('.recommendation{', html)

    def test_reduced_motion_disables_transitions_and_animations_for_pseudo_elements(self):
        plan = ExplanationPlan(
            audience="project_novice",
            depth="deep",
            components=("overview",),
            reason_codes=(),
            provisional=False,
            should_continue=False,
            delivery="local_html",
            publish_policy="never",
        )

        html = render_components(plan, title="動き", content={"overview": "説明"})

        self.assertIn(
            "@media(prefers-reduced-motion:reduce){*,*::before,*::after{",
            html,
        )
        self.assertIn("transition:none", html)
        self.assertIn("animation:none", html)


if __name__ == "__main__":
    unittest.main()

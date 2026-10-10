from __future__ import annotations

import sys
import unittest

sys.dont_write_bytecode = True

from pathlib import Path

HOOKS_DIR = Path(__file__).resolve().parents[1]
if str(HOOKS_DIR) not in sys.path:
    sys.path.insert(0, str(HOOKS_DIR))

from visual.artifact_inspection import inspect_artifact_html
from visual.glossary import GlossaryEntry
from visual.render_components import DECISION_SCRIPT


class ArtifactInspectionTests(unittest.TestCase):
    def test_provenance_footer_is_a_valid_optional_component(self):
        html = """
<header data-component="overview">概要</header>
<footer data-component="provenance">local / project_novice</footer>
"""

        result = inspect_artifact_html(
            html,
            required_components=("overview",),
            glossary_entries={},
        )

        self.assertTrue(result.ok)
        self.assertIn("provenance", result.present_components)

    def test_identifier_definition_term_is_not_reported_as_unwrapped(self):
        html = """
<header data-component="overview">概要</header>
<section data-component="glossary"><dl><dt>knownCamel</dt><dd>この場で定義する</dd></dl></section>
"""

        result = inspect_artifact_html(
            html,
            required_components=("overview", "glossary"),
            glossary_entries={
                "knownCamel": GlossaryEntry("knownCamel", "既知の識別子", "project")
            },
        )

        self.assertTrue(result.ok)
        self.assertEqual(result.unwrapped_identifiers, ())

    def test_one_wrapped_identifier_allows_later_plain_repetitions(self):
        html = """
<header data-component="overview">
  <p><span class="t" tabindex="0" data-d="既知の識別子">knownCamel</span></p>
  <p>knownCamel をもう一度使う。</p>
</header>
"""

        result = inspect_artifact_html(
            html,
            required_components=("overview",),
            glossary_entries={
                "knownCamel": GlossaryEntry("knownCamel", "既知の識別子", "project")
            },
        )

        self.assertTrue(result.ok)
        self.assertEqual(result.unwrapped_identifiers, ())

    def setUp(self) -> None:
        self.entries = {
            "ArtifactReceipt": GlossaryEntry(
                "ArtifactReceipt", "検査済みHTMLの証拠", "project"
            ),
            "goalLadder": GlossaryEntry(
                "goalLadder", "目標を段階に分けた一覧", "project"
            ),
            "link_audit": GlossaryEntry(
                "link_audit", "リンクを1本ずつ確認した記録", "project"
            ),
            "nestedName": GlossaryEntry(
                "nestedName", "入れ子の例で使う識別子", "project"
            ),
            "knownCamel": GlossaryEntry(
                "knownCamel", "既知のcamelCase識別子", "project"
            ),
            "known_snake": GlossaryEntry(
                "known_snake", "既知のsnake_case識別子", "project"
            ),
            "ALL_CAPS": GlossaryEntry(
                "ALL_CAPS", "既知の大文字識別子", "project"
            ),
            "`backtickName`": GlossaryEntry(
                "`backtickName`", "バッククォート付きの既知識別子", "project"
            ),
        }

    def test_complete_artifact_is_ok_and_reports_structural_components(self):
        html = """
<!doctype html>
<html><body>
<header data-component="overview">
  <h1>Overview</h1>
  <code><span class="t" data-d="検査済みHTMLの証拠" tabindex="0">ArtifactReceipt</span></code>
</header>
<section data-component="summary"><div class="note">Summary</div></section>
<section data-component="decision">
  <label><input type="radio" name="decision" value="A">A</label>
  <pre id="decision-prompt">選択してください。</pre>
  <button id="copy-decision" type="button">コピー</button>
  <button data-role="select-all" type="button">全部選ぶ</button>
  <label><input type="checkbox" name="objection" value="wrong">これは違う</label>
</section>
<section data-component="evidence">
  <table><thead><tr><th>種類</th><th>内容</th><th>Source</th></tr></thead>
    <tbody><tr data-evidence="claim-1"><td>実測</td><td>Claim</td><td class="source" data-source="tests/fixture.py">tests/fixture.py</td></tr></tbody>
  </table>
</section>
</body></html>
"""

        result = inspect_artifact_html(
            html,
            required_components=("overview", "summary", "decision", "evidence"),
            glossary_entries=self.entries,
        )

        self.assertTrue(result.ok)
        self.assertEqual(
            result.present_components,
            ("overview", "summary", "decision", "evidence"),
        )
        self.assertEqual(result.missing_components, ())
        self.assertEqual(result.missing_decision_parts, ())
        self.assertEqual(result.unwrapped_identifiers, ())
        self.assertEqual(result.unknown_identifiers, ())
        self.assertEqual(result.missing_evidence_sources, ())
        self.assertEqual(result.errors, ())

    def test_missing_components_and_decision_parts_are_enumerated(self):
        html = """
<header data-component="overview">Overview</header>
<section data-component="summary"><div class="note">Summary</div></section>
<section data-component="decision"><input type="text" name="freeform"></section>
<section data-component="evidence">
  <table><tbody><tr data-evidence="claim-without-source"><td>Claim</td></tr></tbody></table>
</section>
"""

        result = inspect_artifact_html(
            html,
            required_components=("overview", "summary", "decision", "evidence", "visual"),
            glossary_entries=self.entries,
        )

        self.assertFalse(result.ok)
        self.assertEqual(result.missing_components, ("visual",))
        self.assertEqual(
            set(result.missing_decision_parts),
            {"choice_control", "pre", "copy_button", "select_all", "objection"},
        )
        self.assertIn("claim-without-source", result.missing_evidence_sources)

    def test_decision_controls_outside_decision_section_do_not_count(self):
        html = """
<section data-component="decision"></section>
<div>
  <input type="radio" name="decision" value="A">
  <pre>outside</pre>
  <button id="copy-decision">copy</button>
  <button data-role="select-all">select</button>
  <textarea name="objection">outside</textarea>
</div>
"""

        result = inspect_artifact_html(
            html,
            required_components=("decision",),
            glossary_entries={},
        )

        self.assertFalse(result.ok)
        self.assertEqual(
            set(result.missing_decision_parts),
            {"choice_control", "pre", "copy_button", "select_all", "objection"},
        )

    def test_overview_requires_header_and_summary_requires_explicit_section_or_note(self):
        html = """
<div data-component="overview">not a header</div>
<div data-component="summary">not a section or note</div>
"""

        result = inspect_artifact_html(
            html,
            required_components=("overview", "summary"),
            glossary_entries={},
        )

        self.assertFalse(result.ok)
        self.assertEqual(result.missing_components, ("overview", "summary"))
        self.assertTrue(any("overview" in error for error in result.errors))
        self.assertTrue(any("summary" in error for error in result.errors))

    def test_identifier_candidates_exclude_paths_commands_urls_and_whitespace(self):
        html = """
<section data-component="overview">
  <code>goalLadder</code>
  <code><span class="t" data-d="リンクを1本ずつ確認した記録" tabindex="0">link_audit</span></code>
  <code><span><span class="t" data-d="入れ子の例で使う識別子" tabindex="0">nestedName</span></span></code>
  <code>UnknownThing</code>
  <code>C:/repo/file.py:12</code>
  <code>git status</code>
  <code>https://example.test/path</code>
  <code>text with spaces</code>
</section>
"""

        result = inspect_artifact_html(
            html,
            required_components=("overview",),
            glossary_entries=self.entries,
        )

        self.assertFalse(result.ok)
        # ⚠️2026-09-01の裁定で方針が反転した＝**コード書きの中は包装を求めない**
        #   （本文だけ包む）。∴未包装は0件になる。以前はここに2件出るのが正しかった。
        self.assertEqual(result.unwrapped_identifiers, ())
        # 「用語集に無い識別子」の報告だけは残す＝ここを弱めると別の役目が消える。
        self.assertEqual(result.unknown_identifiers, ("UnknownThing",))

    def test_evidence_source_is_checked_for_each_evidence_row(self):
        html = """
<section data-component="evidence">
  <table>
    <tbody>
      <tr data-evidence="has-source"><td>実測</td><td>Claim A</td><td class="source" data-source="docs/fixture.md">docs/fixture.md</td></tr>
      <tr data-evidence="missing-source"><td>実測</td><td>Claim B</td><td class="source" data-source=""></td></tr>
    </tbody>
  </table>
</section>
"""

        result = inspect_artifact_html(
            html,
            required_components=("evidence",),
            glossary_entries={},
        )

        self.assertFalse(result.ok)
        self.assertEqual(result.missing_evidence_sources, ("missing-source",))

    def test_missing_source_placeholder_is_not_accepted_as_evidence(self):
        variants = (
            ("missing-marker", "", "未提示", ' data-missing-source="true"'),
            ("n-a-visible", "tests/a.py", "N/A", ""),
            ("tbd-visible", "tests/a.py", "TBD", ""),
            ("n-a-attr", "N/A", "tests/a.py", ""),
            ("tbd-attr", "TBD", "tests/a.py", ""),
        )
        for name, source_attr, visible_text, missing_attr in variants:
            with self.subTest(name=name):
                html = (
                    '<section data-component="evidence"><table><tbody>'
                    f'<tr data-evidence="{name}"><td>実測</td><td>Claim</td>'
                    f'<td class="source" data-source="{source_attr}"{missing_attr}>'
                    f'{visible_text}</td></tr></tbody></table></section>'
                )
                result = inspect_artifact_html(
                    html,
                    required_components=("evidence",),
                    glossary_entries={},
                )

                self.assertFalse(result.ok)
                self.assertEqual(result.missing_evidence_sources, (name,))

    def test_every_evidence_body_row_is_checked_without_marker(self):
        html = """
<section data-component="evidence">
  <table><tbody>
    <tr data-evidence="marked"><td>実測</td><td>A</td><td class="source" data-source="tests/a.py">tests/a.py</td></tr>
    <tr><td>実測</td><td>B without source</td><td></td></tr>
  </tbody></table>
</section>
"""

        result = inspect_artifact_html(
            html,
            required_components=("evidence",),
            glossary_entries={},
        )

        self.assertFalse(result.ok)
        self.assertIn("row-2", result.missing_evidence_sources)

    def test_evidence_requires_exactly_three_cells_and_visible_source_cell(self):
        html = """
<section data-component="evidence">
  <table><tbody><tr data-evidence="one-cell" data-source="tests/a.py">
    <td>Claim only</td>
  </tr></tbody></table>
</section>
"""

        result = inspect_artifact_html(
            html,
            required_components=("evidence",),
            glossary_entries={},
        )

        self.assertFalse(result.ok)
        self.assertIn("one-cell", result.missing_evidence_sources)
        self.assertTrue(any("exactly 3 cells" in error for error in result.errors))

    def test_evidence_source_must_be_the_third_cell(self):
        html = """
<section data-component="evidence">
  <table><tbody><tr data-evidence="wrong-column">
    <td class="source" data-source="tests/a.py">tests/a.py</td>
    <td>Claim</td><td>not source</td>
  </tr></tbody></table>
</section>
"""

        result = inspect_artifact_html(
            html,
            required_components=("evidence",),
            glossary_entries={},
        )

        self.assertFalse(result.ok)
        self.assertIn("wrong-column", result.missing_evidence_sources)

    def test_hidden_evidence_source_is_not_visible_evidence(self):
        variants = (
            ('hidden', '<td class="source" data-source="tests/a.py" hidden>tests/a.py</td>'),
            (
                'aria-hidden',
                '<td class="source" data-source="tests/a.py" aria-hidden="true">tests/a.py</td>',
            ),
            (
                'display-none',
                '<td class="source" data-source="tests/a.py" style="display:none">tests/a.py</td>',
            ),
            (
                'hidden-child',
                '<td class="source" data-source="tests/a.py"><span hidden>tests/a.py</span></td>',
            ),
        )
        for name, source_cell in variants:
            with self.subTest(name=name):
                html = (
                    '<section data-component="evidence"><table><tbody>'
                    f'<tr data-evidence="{name}"><td>実測</td><td>Claim</td>{source_cell}</tr>'
                    '</tbody></table></section>'
                )
                result = inspect_artifact_html(
                    html,
                    required_components=("evidence",),
                    glossary_entries={},
                )

                self.assertFalse(result.ok)
                self.assertIn(name, result.missing_evidence_sources)

    def test_sparse_evidence_section_without_rows_fails(self):
        result = inspect_artifact_html(
            '<section data-component="evidence"><p>実測です。</p></section>',
            required_components=("evidence",),
            glossary_entries={},
        )

        self.assertFalse(result.ok)
        self.assertEqual(result.missing_evidence_sources, ("evidence-table",))

    def test_known_identifiers_in_plain_visible_text_are_required_to_be_wrapped(self):
        html = """
<section data-component="overview">
  <h2>knownCamel</h2>
  <table><thead><tr><th>known_snake</th></tr></thead><tbody><tr><td>value</td></tr></tbody></table>
  <script>const ALL_CAPS = 1;</script>
  <style>.known_snake { color: red; }</style>
  <p>knownCamel known_snake ALL_CAPS backtickName</p>
</section>
"""

        result = inspect_artifact_html(
            html,
            required_components=("overview",),
            glossary_entries=self.entries,
        )

        self.assertFalse(result.ok)
        self.assertEqual(
            set(result.unwrapped_identifiers),
            {"knownCamel", "known_snake", "ALL_CAPS", "backtickName"},
        )
        self.assertEqual(result.unknown_identifiers, ())

    def test_identifier_must_be_wrapped_at_first_occurrence(self):
        html = """
<section data-component="overview">
  <p>knownCamel appears plain first.</p>
  <p><span class="t" tabindex="0" data-d="既知のキャメルケース識別子">knownCamel</span></p>
</section>
"""

        result = inspect_artifact_html(
            html,
            required_components=("overview",),
            glossary_entries=self.entries,
        )

        self.assertFalse(result.ok)
        self.assertEqual(result.unwrapped_identifiers, ("knownCamel",))

    def test_code_element_can_itself_be_the_tooltip_wrapper(self):
        html = """
<header data-component="overview">
  <code class="t" tabindex="0" data-d="既知のキャメルケース識別子">knownCamel</code>
</header>
"""

        result = inspect_artifact_html(
            html,
            required_components=("overview",),
            glossary_entries=self.entries,
        )

        self.assertTrue(result.ok)
        self.assertEqual(result.unwrapped_identifiers, ())

    def test_active_event_handler_and_javascript_url_are_errors(self):
        html = """
<section data-component="overview">
  <img src="x" onerror="alert(1)">
  <a href="javascript:alert(2)">click</a>
</section>
"""

        result = inspect_artifact_html(
            html,
            required_components=("overview",),
            glossary_entries={},
        )

        self.assertFalse(result.ok)
        self.assertTrue(any("active event handler" in error for error in result.errors))
        self.assertTrue(any("javascript URL" in error for error in result.errors))

    def test_only_canonical_decision_script_is_allowed(self):
        safe = (
            '<header data-component="overview">safe</header>'
            f"<script>{DECISION_SCRIPT}</script>"
        )
        unsafe = (
            '<header data-component="overview">unsafe</header>'
            '<script>alert(1)</script>'
        )

        safe_result = inspect_artifact_html(
            safe,
            required_components=("overview",),
            glossary_entries={},
        )
        unsafe_result = inspect_artifact_html(
            unsafe,
            required_components=("overview",),
            glossary_entries={},
        )

        self.assertTrue(safe_result.ok)
        self.assertFalse(unsafe_result.ok)
        self.assertTrue(
            any("unapproved inline script" in error for error in unsafe_result.errors)
        )

    def test_malformed_and_unresolved_html_are_errors(self):
        html = """
<section data-component="overview">
  <span aria-describedby="missing-description">Overview
"""

        result = inspect_artifact_html(
            html,
            required_components=("overview",),
            glossary_entries={},
        )

        self.assertFalse(result.ok)
        self.assertTrue(any("unclosed" in error or "mismatched" in error for error in result.errors))
        self.assertTrue(any("missing-description" in error for error in result.errors))


class RawProseAndScriptRolesTests(unittest.TestCase):
    """原稿の節（data-prose="raw"）と、判断欄・指摘・添削の3本の script（2026-10-09）。詳しくは test_review_gate.py。"""

    def test_raw_prose_inside_the_manuscript_section_is_not_asked_to_wrap_known_terms(self):
        html = (
            '<header data-component="overview">概要</header>'
            '<section data-component="manuscript"><article data-prose="raw">'
            "<p>knownCamel を原稿に書いた。</p></article></section>"
        )

        result = inspect_artifact_html(
            html,
            required_components=("overview", "manuscript"),
            glossary_entries={"knownCamel": GlossaryEntry("knownCamel", "既知の識別子", "project")},
        )

        self.assertTrue(result.ok, result.errors)
        self.assertEqual(result.unwrapped_identifiers, ())

    def test_raw_prose_outside_the_manuscript_section_is_an_error(self):
        html = (
            '<header data-component="overview">概要</header>'
            '<section data-component="walkthrough"><article data-prose="raw"><p>x</p></article></section>'
        )

        result = inspect_artifact_html(html, required_components=("overview",), glossary_entries={})

        self.assertIn("raw prose is only allowed inside the manuscript section", result.errors)

    def test_two_decision_scripts_are_a_duplicate_not_a_third_role(self):
        html = (
            '<header data-component="overview">概要</header>'
            f"<script>{DECISION_SCRIPT}</script><script>{DECISION_SCRIPT}</script>"
        )

        result = inspect_artifact_html(html, required_components=("overview",), glossary_entries={})

        self.assertFalse(result.ok)
        self.assertIn("duplicate inline script: decision", result.errors)


if __name__ == "__main__":
    unittest.main()

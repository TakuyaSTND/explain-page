"""検品の Gate（artifact_inspection）の試験（2026-10-09・指摘と添削の作り込み）。

何を守るか＝
  ①頁に載せてよい script は3本（判断欄・指摘・添削）の部分集合だけ。各1本・判断欄が先頭・並びは
    ROLE_ORDER の順。重複・承認していない本文・JSON の script・順序違い・3本超は落とす。
    既存の文言（multiple inline scripts are not allowed／unapproved inline script is not allowed）は残す。
  ②原稿の節の中身（data-prose="raw"）は、用語の包装もコード書きの語の検査も求めない。
    ただし raw は原稿の節（section[data-component="manuscript"]）の中だけ。外にあれば errors。

指摘・添削の script の正本（visual/review_scripts.py）が無い環境でも走るよう、役割の検査は
APPROVED_SCRIPTS を試験用の短い本文に差し替えて行う。本物の script での合格は、取り込めたときだけ別に確かめる。
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.dont_write_bytecode = True

HOOKS_DIR = Path(__file__).resolve().parents[1]
if str(HOOKS_DIR) not in sys.path:
    sys.path.insert(0, str(HOOKS_DIR))

from visual import artifact_inspection as ai  # noqa: E402
from visual.artifact_inspection import inspect_artifact_html  # noqa: E402
from visual.glossary import GlossaryEntry  # noqa: E402
from visual.render_components import DECISION_SCRIPT  # noqa: E402

SHITEKI_FAKE = "const shitekiRole = 1;"
TENSAKU_FAKE = "const tensakuRole = 2;"
FAKE_APPROVED = (
    ("decision", DECISION_SCRIPT),
    ("shiteki", SHITEKI_FAKE),
    ("tensaku", TENSAKU_FAKE),
)
HEADER = '<header data-component="overview">概要</header>'


def _page(*scripts, body=""):
    return HEADER + body + "".join("<script>%s</script>" % text for text in scripts)


def _inspect(html, entries=None):
    return inspect_artifact_html(html, required_components=("overview",), glossary_entries=entries or {})


def _errors(html, entries=None):
    return list(_inspect(html, entries).errors)


class ScriptRoleTests(unittest.TestCase):
    def setUp(self):
        patcher = patch.object(ai, "APPROVED_SCRIPTS", FAKE_APPROVED)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_every_subset_with_decision_first_in_order_passes(self):
        for scripts in (
            (DECISION_SCRIPT,),
            (DECISION_SCRIPT, SHITEKI_FAKE),
            (DECISION_SCRIPT, TENSAKU_FAKE),
            (DECISION_SCRIPT, SHITEKI_FAKE, TENSAKU_FAKE),
        ):
            with self.subTest(count=len(scripts), last=scripts[-1][:12]):
                self.assertTrue(_inspect(_page(*scripts)).ok, _errors(_page(*scripts)))

    def test_no_script_at_all_passes(self):
        self.assertTrue(_inspect(_page()).ok)

    def test_a_duplicate_role_is_named(self):
        errors = _errors(_page(DECISION_SCRIPT, DECISION_SCRIPT))
        self.assertIn("duplicate inline script: decision", errors)

        errors = _errors(_page(DECISION_SCRIPT, SHITEKI_FAKE, SHITEKI_FAKE))
        self.assertIn("duplicate inline script: shiteki", errors)

    def test_an_unapproved_text_is_refused_even_next_to_approved_ones(self):
        errors = _errors(_page(DECISION_SCRIPT, SHITEKI_FAKE + " // changed"))

        self.assertIn("unapproved inline script is not allowed", errors)

    def test_one_character_off_the_approved_text_is_refused(self):
        self.assertIn(
            "unapproved inline script is not allowed", _errors(_page(DECISION_SCRIPT + ";"))
        )

    def test_a_json_data_script_is_refused_as_unapproved(self):
        html = HEADER + "<script>%s</script>" % DECISION_SCRIPT + '<script type="application/json">{"a":1}</script>'

        self.assertIn("unapproved inline script is not allowed", _errors(html))

    def test_a_json_data_script_alone_is_refused_too(self):
        html = HEADER + '<script type="application/json">{"a":1}</script>'

        self.assertIn("unapproved inline script is not allowed", _errors(html))

    def test_the_order_must_follow_the_role_order_with_decision_first(self):
        for scripts in (
            (SHITEKI_FAKE, DECISION_SCRIPT),
            (DECISION_SCRIPT, TENSAKU_FAKE, SHITEKI_FAKE),
            (TENSAKU_FAKE, DECISION_SCRIPT, SHITEKI_FAKE),
        ):
            with self.subTest(first=scripts[0][:10]):
                self.assertIn("decision script must come first", _errors(_page(*scripts)))

    def test_a_role_without_the_decision_script_is_refused(self):
        self.assertIn("decision script must come first", _errors(_page(SHITEKI_FAKE)))
        self.assertIn("decision script must come first", _errors(_page(TENSAKU_FAKE)))

    def test_more_than_three_scripts_keeps_the_old_wording(self):
        errors = _errors(_page(DECISION_SCRIPT, SHITEKI_FAKE, TENSAKU_FAKE, "alert(1)"))

        self.assertIn("multiple inline scripts are not allowed", errors)
        self.assertIn("unapproved inline script is not allowed", errors)

    def test_a_script_with_an_external_source_is_still_refused(self):
        html = HEADER + '<script src="x.js"></script>'

        self.assertIn("external script source is not allowed", _errors(html))


class ScriptRoleWithoutTheReviewModuleTests(unittest.TestCase):
    """指摘・添削の script の正本が無い環境＝判断欄だけを認める（今までと同じ動き）。"""

    def test_only_the_decision_script_is_approved_then(self):
        with patch.object(ai, "APPROVED_SCRIPTS", (("decision", DECISION_SCRIPT),)):
            self.assertTrue(_inspect(_page(DECISION_SCRIPT)).ok)
            self.assertIn(
                "unapproved inline script is not allowed", _errors(_page(DECISION_SCRIPT, SHITEKI_FAKE))
            )
            self.assertIn("multiple inline scripts are not allowed", _errors(_page(DECISION_SCRIPT, SHITEKI_FAKE)))


class RealReviewScriptsTests(unittest.TestCase):
    """指摘・添削の script の正本が取り込めたときだけ、本物で確かめる。"""

    def setUp(self):
        if not (ai.SHITEKI_SCRIPT and ai.TENSAKU_SCRIPT):
            self.skipTest("review_scripts がまだ無い")

    def test_the_approved_list_has_three_distinct_roles_in_order(self):
        self.assertEqual([role for role, _ in ai.APPROVED_SCRIPTS], ["decision", "shiteki", "tensaku"])
        self.assertEqual(len({text for _role, text in ai.APPROVED_SCRIPTS}), 3)

    def test_the_real_scripts_pass_in_every_subset(self):
        shiteki, tensaku = ai.SHITEKI_SCRIPT, ai.TENSAKU_SCRIPT
        for scripts in (
            (DECISION_SCRIPT, shiteki),
            (DECISION_SCRIPT, tensaku),
            (DECISION_SCRIPT, shiteki, tensaku),
        ):
            with self.subTest(count=len(scripts)):
                self.assertTrue(_inspect(_page(*scripts)).ok, _errors(_page(*scripts)))

    def test_the_real_scripts_in_the_wrong_order_are_refused(self):
        self.assertIn(
            "decision script must come first",
            _errors(_page(DECISION_SCRIPT, ai.TENSAKU_SCRIPT, ai.SHITEKI_SCRIPT)),
        )

    def test_the_module_roles_match_the_gate_order(self):
        from visual import review_scripts

        self.assertEqual(tuple(review_scripts.ROLE_ORDER), tuple(role for role, _ in ai.APPROVED_SCRIPTS))


RAW_ENTRIES = {
    "knownCamel": GlossaryEntry("knownCamel", "既知の識別子", "project"),
    "link_audit": GlossaryEntry("link_audit", "リンクを1本ずつ確認した記録", "project"),
}


def _manuscript(inner, section_attrs=""):
    return (
        '<section data-component="manuscript"%s><h2>原稿</h2>'
        '<article class="ms" data-prose="raw">%s</article></section>' % (section_attrs, inner)
    )


class RawProseTests(unittest.TestCase):
    def test_raw_prose_is_not_asked_to_wrap_known_terms(self):
        body = _manuscript('<div class="ms-blk"><p>knownCamel と link_audit を原稿に書いた。</p></div>')

        result = _inspect(_page(body=body), RAW_ENTRIES)

        self.assertEqual(result.unwrapped_identifiers, ())
        self.assertTrue(result.ok, result.errors)

    def test_the_same_text_outside_raw_is_still_asked_to_wrap(self):
        body = '<section data-component="walkthrough"><p>knownCamel と link_audit を本文に書いた。</p></section>'

        result = _inspect(_page(body=body), RAW_ENTRIES)

        self.assertIn("knownCamel", result.unwrapped_identifiers)
        self.assertFalse(result.ok)

    def test_a_code_span_with_an_unknown_identifier_is_fine_inside_raw_only(self):
        inside = _manuscript('<div class="ms-blk"><p><code>unknown_ident</code> と <code>CamelCaseName</code></p></div>')
        outside = '<section data-component="walkthrough"><p><code>unknown_ident</code></p></section>'

        self.assertEqual(_inspect(_page(body=inside)).unknown_identifiers, ())
        self.assertTrue(_inspect(_page(body=inside)).ok)
        self.assertIn("unknown_ident", _inspect(_page(body=outside)).unknown_identifiers)

    def test_raw_prose_outside_the_manuscript_section_is_an_error(self):
        body = '<section data-component="walkthrough"><article data-prose="raw"><p>x</p></article></section>'

        self.assertIn("raw prose is only allowed inside the manuscript section", _errors(_page(body=body)))

    def test_raw_prose_with_no_section_at_all_is_an_error(self):
        body = '<div data-prose="raw"><p>x</p></div>'

        self.assertIn("raw prose is only allowed inside the manuscript section", _errors(_page(body=body)))

    def test_raw_on_the_manuscript_section_itself_is_an_error(self):
        body = '<section data-component="manuscript" data-prose="raw"><p>x</p></section>'

        self.assertIn("raw prose is only allowed inside the manuscript section", _errors(_page(body=body)))

    def test_a_manuscript_section_that_is_not_a_section_element_does_not_count(self):
        body = '<div data-component="manuscript"><article data-prose="raw"><p>x</p></article></div>'

        errors = _errors(_page(body=body))

        self.assertIn("raw prose is only allowed inside the manuscript section", errors)
        self.assertIn("manuscript must be represented by a section", errors)

    def test_other_data_prose_values_are_ignored(self):
        body = '<section data-component="walkthrough"><p data-prose="rich">x</p></section>'

        self.assertEqual(_errors(_page(body=body)), [])

    def test_raw_inside_the_manuscript_section_is_not_an_error_and_the_component_is_present(self):
        body = _manuscript('<div class="ms-blk"><p>本文</p></div>')

        result = inspect_artifact_html(
            _page(body=body), required_components=("overview", "manuscript"), glossary_entries={}
        )

        self.assertEqual(result.errors, ())
        self.assertIn("manuscript", result.present_components)
        self.assertTrue(result.ok)

    def test_text_after_the_manuscript_section_is_checked_again(self):
        body = _manuscript("<p>knownCamel</p>") + '<section data-component="walkthrough"><p>knownCamel を本文に書いた。</p></section>'

        result = _inspect(_page(body=body), RAW_ENTRIES)

        self.assertIn("knownCamel", result.unwrapped_identifiers)

    def test_a_hidden_textarea_with_the_source_does_not_disturb_the_inspection(self):
        source = (
            '<textarea id="ms-source" class="ms-source" hidden readonly aria-hidden="true">\n'
            "&lt;b&gt;x&lt;/b&gt; knownCamel &lt;/section&gt;</textarea>"
        )
        body = _manuscript('<div class="ms-blk"><p>本文</p></div>' + source)

        result = _inspect(_page(body=body), RAW_ENTRIES)

        self.assertTrue(result.ok, result.errors)


if __name__ == "__main__":
    unittest.main()

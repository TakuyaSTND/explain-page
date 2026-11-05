"""用語の規則表（glossary-context.json）＝普通の言葉としても使う語の吹き出しを止める（2026-10-18）。

実例＝裁定シートの文「判決確定後の被害者向け」「民法の予告期間」「保管期限を決める主体」の確定・
予告・主体に、用語集の意味（応答の最後に決めた計画 など）の吹き出しが付いた。置き場の頁196本の
吹き出し1,359件を1件ずつ読むと、普通の用法が179件（今の規則でも付くのは141件・86頁）だった。
語の境目の規則（term_boundary.py）は文字の並びだけを見るので、同じ字で意味が違う語は止められない。

規則＝語ごとの「手がかりの語」（GlossaryEntry.cues）。None＝規則なし（今までどおり）／
()＝自動では包まない／非空＝手がかりが前後20字にあるときだけ包む。レンダラーと検品器が
同じ find_term を読む。
⚠️吹き出しが付いた語は、規則を通さず「初出は済んだ」と検品器に記録する。試作で、規則を通すと、
  吹き出しの中の文字だけを見て手がかりが無いと判断し、後ろの手がかり付きの同じ語を検品器が
  未包装と責める1頁があった（pushdoc-fb）。
⚠️公開版にも写る試験＝公開版には規則表の実物が無いので、実物を読む試験は無ければ飛ばす。
"""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

HOOKS_DIR = Path(__file__).resolve().parents[1]
if str(HOOKS_DIR) not in sys.path:
    sys.path.insert(0, str(HOOKS_DIR))

from visual.artifact_inspection import inspect_artifact_html
from visual.contracts import ExplanationPlan
from visual.glossary import GlossaryEntry, load_context_rules, load_glossary_snapshot
from visual.render_components import render_components
from visual.term_boundary import CUE_WINDOW, contains_term, find_term

CLAUDE_DIR = Path(__file__).resolve().parents[2]
SHIPPED_CONTEXT = CLAUDE_DIR / "glossary-context.json"

KAKUTEI = "応答の最後に決めた計画。"
RONTEN = "詰められたら困る弱点。"
CHIMEISHO = "崩壊しかねない重大な瑕疵。"


def _entry(term: str, description: str, cues=None) -> GlossaryEntry:
    return GlossaryEntry(term=term, description=description, provenance="test", cues=cues)


ENTRIES = {
    "確定": _entry("確定", KAKUTEI, ()),
    "論点": _entry("論点", RONTEN, ("致命傷", "細部")),
    "致命傷": _entry("致命傷", CHIMEISHO),
    "正本": _entry("正本", "唯一の正しい版。"),
}


def _plan(*components: str) -> ExplanationPlan:
    return ExplanationPlan(
        audience="project_novice",
        depth="deep",
        components=tuple(components),
        reason_codes=(),
        provisional=False,
        should_continue=False,
        delivery="local_html",
        publish_policy="never",
    )


def _render(components, content, entries=ENTRIES):
    return render_components(
        _plan(*components), title="題", content=content, glossary_entries=entries
    )


def _inspect(html, components, entries=ENTRIES):
    return inspect_artifact_html(
        html, required_components=tuple(components), glossary_entries=entries
    )


class FindTermCuesTests(unittest.TestCase):
    """find_term の手がかり（cues）＝None は規則なし・() は自動では包まない・非空は手がかり付き。"""

    def test_no_rule_keeps_the_old_behaviour(self):
        self.assertEqual(find_term("判決確定後の被害者向け", "確定"), 2)
        self.assertEqual(find_term("判決確定後の被害者向け", "確定", 0, None), 2)
        self.assertTrue(contains_term("判決確定後", "確定"))

    def test_empty_cues_never_match_in_prose(self):
        self.assertEqual(find_term("判決確定後の被害者向け", "確定", 0, ()), -1)
        self.assertFalse(contains_term("判決確定後", "確定", ()))

    def test_a_cue_before_the_term_matches(self):
        self.assertEqual(find_term("致命傷・論点・細部の3層", "論点", 0, ("致命傷",)), 4)

    def test_a_cue_after_the_term_matches(self):
        self.assertEqual(find_term("主体の断絶が起きる", "主体", 0, ("断絶",)), 0)

    def test_the_window_is_twenty_characters_on_each_side(self):
        self.assertEqual(CUE_WINDOW, 20)
        # 手がかりの全体が、語の直前20字（直後20字）に収まるときだけ付く。
        before_near = "致命傷" + "あ" * 17 + "論点"
        before_far = "致命傷" + "あ" * 18 + "論点"
        after_near = "論点" + "あ" * 15 + "断絶"
        after_far = "論点" + "あ" * 19 + "断絶"
        self.assertEqual(find_term(before_near, "論点", 0, ("致命傷",)), len(before_near) - 2)
        self.assertEqual(find_term(before_far, "論点", 0, ("致命傷",)), -1)
        self.assertEqual(find_term(after_near, "論点", 0, ("断絶",)), 0)
        self.assertEqual(find_term(after_far, "論点", 0, ("断絶",)), -1)

    def test_the_term_itself_is_not_a_cue(self):
        self.assertEqual(find_term("論点", "論点", 0, ("論点",)), -1)

    def test_the_word_boundary_rules_still_apply(self):
        # 目盛りの中の盛りは、手がかりが近くにあっても別の語（語の境目の規則）。
        self.assertEqual(find_term("目盛りの数字", "盛り", 0, ("数字",)), -1)

    def test_the_first_qualifying_occurrence_is_returned(self):
        text = "論点は" + "あ" * 30 + "致命傷・論点・細部"
        self.assertEqual(find_term(text, "論点", 0, ("致命傷", "細部")), text.rindex("論点"))

    def test_text_before_start_still_gives_the_cue(self):
        text = "致命傷・論点"
        self.assertEqual(find_term(text, "論点", 4, ("致命傷",)), 4)


class ContextRulesLoadTests(unittest.TestCase):
    """規則表の読み込み＝壊れていても例外を投げない（頁を組む仕組み・フックを止めない）。"""

    SHARED = "| 用語 | 説明 |\n|---|---|\n| 金庫 | Obsidianのノートの入れ物。 |\n"
    PROJECT = (
        "| 用語 | 説明 |\n|---|---|\n"
        "| 確定 | 応答の最後に決めた計画。 |\n"
        "| 論点 | 詰められたら困る弱点。 |\n"
        "| 主体 | その段を動かす人。 |\n"
        "| 正本 | 唯一の正しい版。 |\n"
    )

    def _load(self, context=None):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / ".claude").mkdir()
            home = root / "home.md"
            mirror = root / "mirror.md"
            project = root / ".claude" / "glossary.md"
            home.write_text(self.SHARED, encoding="utf-8")
            mirror.write_text(self.SHARED, encoding="utf-8")
            project.write_text(self.PROJECT, encoding="utf-8")
            if context is not None:
                (root / ".claude" / "glossary-context.json").write_text(context, encoding="utf-8")
            return load_glossary_snapshot(home, mirror, project)

    def test_without_a_file_nothing_changes(self):
        snapshot, entries = self._load()

        self.assertEqual(snapshot.context_count, 0)
        self.assertEqual(snapshot.context_problems, ())
        self.assertEqual(snapshot.context_sha256, "")
        self.assertTrue(all(entry.cues is None for entry in entries.values()))

    def test_an_empty_file_gives_the_same_hash_as_no_file(self):
        # ⚠️規則表が無い（または空の）プロジェクトは、用語集のハッシュが1バイトも変わらない
        #   ＝既存の検品証が無効にならない。
        without, _ = self._load()
        empty, _ = self._load("{}")

        self.assertEqual(without.effective_sha256, empty.effective_sha256)

    def test_rules_are_attached_to_the_entries(self):
        context = json.dumps(
            {
                "_comment": "説明",
                "確定": {"cues": [], "note": "普通の用法が大半"},
                "論点": {"cues": ["致命傷", "細部"]},
            },
            ensure_ascii=False,
        )
        snapshot, entries = self._load(context)

        self.assertEqual(entries["確定"].cues, ())
        self.assertEqual(entries["論点"].cues, ("致命傷", "細部"))
        self.assertIsNone(entries["正本"].cues)
        self.assertEqual(snapshot.context_count, 2)
        self.assertEqual(snapshot.context_problems, ())
        self.assertTrue(snapshot.context_path.endswith("glossary-context.json"))
        self.assertEqual(len(snapshot.context_sha256), 64)

    def test_a_bare_list_means_the_cues(self):
        _, entries = self._load(json.dumps({"論点": ["致命傷"]}, ensure_ascii=False))

        self.assertEqual(entries["論点"].cues, ("致命傷",))

    def test_a_rule_can_name_a_term_that_only_the_shared_glossary_has(self):
        _, entries = self._load(json.dumps({"金庫": {"cues": []}}, ensure_ascii=False))

        self.assertEqual(entries["金庫"].cues, ())
        self.assertEqual(entries["金庫"].provenance, "shared")

    def test_a_term_missing_from_the_glossary_is_reported_not_applied(self):
        snapshot, entries = self._load(json.dumps({"未登録の語": {"cues": []}}, ensure_ascii=False))

        self.assertNotIn("未登録の語", entries)
        self.assertEqual(snapshot.context_count, 0)
        self.assertEqual(len(snapshot.context_problems), 1)
        self.assertIn("未登録の語", snapshot.context_problems[0])

    def test_broken_files_never_raise(self):
        for broken in ("{ not json", "[1, 2]", '"text"', ""):
            snapshot, entries = self._load(broken)

            self.assertTrue(snapshot.context_problems, broken)
            self.assertEqual(snapshot.context_count, 0)
            self.assertTrue(all(entry.cues is None for entry in entries.values()))

    def test_bad_shapes_are_skipped_one_by_one(self):
        context = json.dumps(
            {"確定": 5, "論点": {"cues": "致命傷"}, "主体": {"cues": ["断絶"]}},
            ensure_ascii=False,
        )
        snapshot, entries = self._load(context)

        self.assertEqual(entries["主体"].cues, ("断絶",))
        self.assertIsNone(entries["確定"].cues)
        self.assertIsNone(entries["論点"].cues)
        self.assertEqual(snapshot.context_count, 1)
        self.assertEqual(len(snapshot.context_problems), 2)

    def test_cues_are_stripped_and_deduplicated(self):
        rules, problems, _ = self._rules({"論点": {"cues": [" 致命傷 ", "", "致命傷", "細部", 3]}})

        self.assertEqual(rules["論点"], ("致命傷", "細部"))
        self.assertEqual(len(problems), 1)

    def test_the_effective_hash_follows_the_rules(self):
        base, _ = self._load()
        one, _ = self._load(json.dumps({"論点": {"cues": ["致命傷"]}}, ensure_ascii=False))
        other, _ = self._load(json.dumps({"論点": {"cues": ["細部"]}}, ensure_ascii=False))

        self.assertNotEqual(base.effective_sha256, one.effective_sha256)
        self.assertNotEqual(one.effective_sha256, other.effective_sha256)

    def _rules(self, data):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "glossary-context.json"
            path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
            return load_context_rules(path)

    def test_a_missing_file_is_an_empty_rule_set(self):
        rules, problems, digest = load_context_rules(Path("no-such-dir") / "glossary-context.json")

        self.assertEqual((rules, problems, digest), ({}, (), ""))


class RenderedPageRuleTests(unittest.TestCase):
    """レンダラーと検品器が、同じ規則で吹き出しを付ける・求める。"""

    COMPONENTS = ("walkthrough",)

    def test_a_manual_term_gets_no_tooltip_in_ordinary_prose(self):
        html = _render(self.COMPONENTS, {"walkthrough": "判決確定後の被害者向けで、民法の予告期間にかかる。"})

        self.assertIn("判決確定後の被害者向け", html)
        self.assertNotIn(KAKUTEI, html)
        self.assertNotIn('>確定</span>', html)

    def test_the_code_span_still_wraps_a_manual_term(self):
        # 説明を付けたいときの手段＝規則に関係なく付く（コード書きの丸ごと一致）。
        html = _render(self.COMPONENTS, {"walkthrough": "手順は `確定` を突き合わせる。"})

        self.assertIn('<code><span class="t"', html)
        self.assertIn(KAKUTEI, html)
        self.assertEqual(_inspect(html, self.COMPONENTS).unwrapped_identifiers, ())

    def test_a_cued_term_is_wrapped_only_where_its_cue_is_near(self):
        html = _render(
            self.COMPONENTS,
            {"walkthrough": "この案は論点が整理されている。\n審査は致命傷・論点・細部の3層で返す。"},
        )

        self.assertEqual(html.count('>論点</span>'), 1)
        self.assertEqual(html.count('>致命傷</span>'), 1)
        self.assertGreater(html.index('>論点</span>'), html.index("整理されている"))

    def test_a_cue_across_inline_markup_is_not_seen(self):
        # 太字をはさむと、レンダラーは別の文字列として探す。検品器も同じ切れ目で見る。
        html = _render(self.COMPONENTS, {"walkthrough": "審査は致命傷・**論点**・細部の3層で返す。"})

        self.assertEqual(html.count('>論点</span>'), 0)
        self.assertEqual(_inspect(html, self.COMPONENTS).unwrapped_identifiers, ())

    def test_the_inspector_agrees_with_the_renderer_on_many_shapes(self):
        shapes = (
            "判決確定後の被害者向け。",
            "この案は論点が整理されている。",
            "審査は致命傷・論点・細部の3層で返す。",
            "致命傷は1件で、論点は後で整理する。",
            "（重い指摘・論点・細部）を読む。",
            "手順は `確定` と `論点` を書く。",
            "正本を直し、確定させる。",
        )
        for text in shapes:
            html = _render(self.COMPONENTS, {"walkthrough": text})
            inspection = _inspect(html, self.COMPONENTS)

            self.assertEqual(inspection.unwrapped_identifiers, (), text)

    def test_the_inspector_demands_a_term_whose_cue_is_near(self):
        html = (
            '<!doctype html><html><body><section data-component="walkthrough">'
            "<p>致命傷・論点・細部の3層で返す。</p></section></body></html>"
        )
        inspection = _inspect(html, self.COMPONENTS)

        self.assertIn("論点", inspection.unwrapped_identifiers)
        self.assertIn("致命傷", inspection.unwrapped_identifiers)

    def test_the_inspector_does_not_demand_a_manual_term_or_a_cued_term_without_its_cue(self):
        html = (
            '<!doctype html><html><body><section data-component="walkthrough">'
            "<p>判決確定後の被害者向け。この案は論点が整理されている。</p></section></body></html>"
        )
        inspection = _inspect(html, self.COMPONENTS)

        self.assertEqual(inspection.unwrapped_identifiers, ())

    def test_a_wrapped_term_counts_as_seen_without_asking_the_rule(self):
        # 試作で見つけた落とし穴（pushdoc-fb）。吹き出しの中の文字は「論点」だけで、手がかりは
        # 外側の文字にある。ここへ規則を掛けると「初出は済んでいない」と数え、後ろの
        # 手がかり付きの同じ語を未包装と責める。
        entries = {"論点": _entry("論点", RONTEN, ("重い指摘",))}
        html = (
            '<!doctype html><html><body><section data-component="walkthrough">'
            '<p>重い指摘1と<span class="t" tabindex="0" data-d="詰められたら困る弱点。" '
            'aria-label="論点：詰められたら困る弱点。">論点</span>1を確かめます。</p>'
            "<p>これは重い指摘2と論点3の延長です。</p></section></body></html>"
        )

        self.assertEqual(_inspect(html, self.COMPONENTS, entries).unwrapped_identifiers, ())

    def test_the_renderer_wraps_once_and_the_inspector_accepts_the_page(self):
        entries = {"論点": _entry("論点", RONTEN, ("重い指摘",))}
        html = _render(
            self.COMPONENTS,
            {"walkthrough": "重い指摘1と論点1を確かめます。\nこれは重い指摘2と論点3の延長です。"},
            entries,
        )

        self.assertEqual(html.count('>論点</span>'), 1)
        self.assertEqual(_inspect(html, self.COMPONENTS, entries).unwrapped_identifiers, ())

    def test_a_diagram_box_hover_follows_the_rule(self):
        diagram = {"nodes": [{"id": "a", "label": "確定した計画", "col": 0, "row": 0}], "edges": []}
        with_rule = _render(("diagram",), {"diagram": diagram})
        no_rule = _render(
            ("diagram",), {"diagram": diagram}, {"確定": _entry("確定", KAKUTEI)}
        )

        self.assertNotIn(KAKUTEI, with_rule)
        self.assertIn(KAKUTEI, no_rule)


@unittest.skipUnless(SHIPPED_CONTEXT.is_file(), "公開版には規則表の実物が無い")
class ShippedContextTests(unittest.TestCase):
    """このリポジトリの規則表（.claude/glossary-context.json）の実物。"""

    MANUAL = ("確定", "予告", "感度", "波", "実時間", "基準線", "成功条件", "越境", "金庫")
    CUED = ("論点", "主体")

    def _snapshot(self):
        shared = CLAUDE_DIR / "glossary-shared.md"
        return load_glossary_snapshot(shared, shared, CLAUDE_DIR / "glossary.md")

    def test_the_file_loads_without_problems(self):
        rules, problems, digest = load_context_rules(SHIPPED_CONTEXT)

        self.assertEqual(problems, ())
        self.assertEqual(len(digest), 64)
        for term in self.MANUAL:
            self.assertEqual(rules[term], (), term)
        for term in self.CUED:
            self.assertTrue(rules[term], term)

    def test_every_rule_names_a_term_in_the_glossary(self):
        snapshot, entries = self._snapshot()
        rules, _, _ = load_context_rules(SHIPPED_CONTEXT)

        self.assertEqual(snapshot.context_problems, ())
        self.assertEqual(snapshot.context_count, len(rules))
        for term in rules:
            self.assertIn(term, entries)

    def test_no_cue_contains_its_own_term(self):
        rules, _, _ = load_context_rules(SHIPPED_CONTEXT)

        for term, cues in rules.items():
            for cue in cues:
                self.assertNotIn(term, cue, (term, cue))

    def test_the_reported_sentences_get_no_wrong_tooltip(self):
        _, entries = self._snapshot()
        sentences = (
            "候補の通知は判決確定後の被害者向けで、民法の予告期間にかかる。",
            "採取した証拠の保管期限を決める主体は誰か。",
            "この案は論点が整理されている。",
        )
        for text in sentences:
            html = _render(("walkthrough",), {"walkthrough": text}, entries)

            for term in ("確定", "予告", "主体", "論点"):
                self.assertNotIn(">%s</span>" % term, html, (text, term))

    def test_the_review_tiers_still_get_the_glossary_meaning(self):
        _, entries = self._snapshot()
        html = _render(("walkthrough",), {"walkthrough": "審査は致命傷・論点・細部の3層で返す。"}, entries)

        self.assertIn(">論点</span>", html)
        self.assertIn(">致命傷</span>", html)
        self.assertEqual(_inspect(html, ("walkthrough",), entries).unwrapped_identifiers, ())


if __name__ == "__main__":
    unittest.main()

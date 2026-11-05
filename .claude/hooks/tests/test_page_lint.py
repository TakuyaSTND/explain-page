"""案のカードからの選択肢の補い（H2）・機械の点検（H3）・仕組みの版の印字（H5）の試験（2026-10-19・利用者が選んだ3案）。

何を守るか＝
  H2：案のカード（proposals）の番号で始まる判断欄の選択肢へ、絵・利点・代償・推奨を補う。書いてあれば上書きしない。
      元の定義は変えない（写しを返す）。カードが無い・番号が合わない選択肢は、そのまま。
  H3：数の出所・略した単位・絵が一部だけ・英字の語の点検は、全部「止めはしない」の警告で、出所の表に数があれば黙る。
  H5：頁の末尾の出所に「仕組みの版」（本線・作業場・公開版・プラグイン＋コミット番号）を足す。個人のパスは出さない。
"""
from __future__ import annotations

import copy
import sys
import unittest
from pathlib import Path

HOOKS_DIR = Path(__file__).resolve().parents[1]
if str(HOOKS_DIR) not in sys.path:
    sys.path.insert(0, str(HOOKS_DIR))

from visual import page_lint as pl  # noqa: E402


def _content(options, cards=None, extra=None):
    cards = cards if cards is not None else [
        {"no": "H2", "title": "案のカードを選択肢にする", "exhibit": {"kind": "gold"}, "recommended": True, "pros": "二重に書かない", "cons": "縦に長い"},
        {"no": "H3", "title": "機械の点検", "exhibit": "<svg viewBox=\"0 0 10 10\"><rect x=\"1\" y=\"1\" width=\"5\" height=\"5\"/></svg>", "pros": "試問が減る"},
    ]
    content = {
        "sections": [
            {"component": "examples", "label": "案", "content": [{"proposals": cards}]},
            {"component": "decision", "label": "判断", "content": {"groups": [{"legend": "どれを作るか", "kind": "checkbox", "options": options}]}},
        ]
    }
    if extra:
        content.update(extra)
    return content


def _options(content):
    return content["sections"][1]["content"]["groups"][0]["options"]


class LinkProposalsTests(unittest.TestCase):
    def test_fills_thumb_pros_cons_and_recommended_from_the_card(self):
        new, notes = pl.link_proposals(_content([{"label": "H2"}, {"label": "H3 機械の点検を先に走らせる"}]))
        first, second = _options(new)
        self.assertEqual(first["label"], "H2 案のカードを選択肢にする")
        self.assertTrue(first["thumb"]["svg"].startswith("<svg"))
        self.assertEqual((first["pros"], first["cons"], first["recommended"]), ("二重に書かない", "縦に長い", True))
        self.assertTrue(second["thumb"]["svg"].startswith("<svg"), "svg の文字列の図も絵になる")
        self.assertEqual(second["pros"], "試問が減る")
        self.assertNotIn("cons", second, "カードに無い項目は作らない")
        self.assertNotIn("recommended", second)
        self.assertEqual(len(notes), 2)
        self.assertTrue(all("案のカードから選択肢を補った" in n for n in notes))

    def test_a_plain_string_option_becomes_a_dict(self):
        new, _ = pl.link_proposals(_content(["H2 カード"]))
        self.assertIsInstance(_options(new)[0], dict)
        self.assertEqual(_options(new)[0]["label"], "H2 カード")

    def test_does_not_overwrite_what_the_writer_wrote(self):
        mine = {"label": "H2", "thumb": {"svg": "<svg/>"}, "pros": "私の利点", "cons": "私の代償", "recommended": False}
        new, notes = pl.link_proposals(_content([mine]))
        self.assertEqual(_options(new)[0]["thumb"], {"svg": "<svg/>"})
        self.assertEqual((_options(new)[0]["pros"], _options(new)[0]["cons"], _options(new)[0]["recommended"]), ("私の利点", "私の代償", False))
        # 書いてあるものは補わない。新しく付くのは、カードの「これを選ぶ」枠（2026-10-19）の知らせだけ。
        self.assertEqual([line for line in notes if "これを選ぶ" not in line], [])
        self.assertEqual(_options(new)[0]["pick_id"], "pk-H2")

    def test_does_not_change_the_input_and_is_idempotent(self):
        content = _content([{"label": "H2"}])
        before = copy.deepcopy(content)
        new, _ = pl.link_proposals(content)
        self.assertEqual(content, before)
        again, notes = pl.link_proposals(new)
        self.assertEqual(again, new)
        self.assertEqual(notes, [])

    def test_unmatched_labels_stay_and_a_hint_is_given_when_nothing_matches(self):
        new, notes = pl.link_proposals(_content([{"label": "案Aだけ"}, {"label": "X9 知らない番号"}]))
        self.assertEqual(_options(new), [{"label": "案Aだけ"}, {"label": "X9 知らない番号"}])
        self.assertEqual(len(notes), 1)
        self.assertIn("案の番号で始める", notes[0])

    def test_no_cards_means_no_change_and_no_note(self):
        content = {"decision": {"groups": [{"legend": "q", "kind": "radio", "options": [{"label": "A"}]}]}}
        new, notes = pl.link_proposals(content)
        self.assertIs(new, content)
        self.assertEqual(notes, [])

    def test_free_and_scale_groups_are_ignored(self):
        content = _content([{"label": "H2"}])
        content["sections"][1]["content"]["groups"].append({"legend": "自由記述", "kind": "free", "placeholder": "x"})
        new, _ = pl.link_proposals(content)
        self.assertEqual(new["sections"][1]["content"]["groups"][1], {"legend": "自由記述", "kind": "free", "placeholder": "x"})

    def test_unknown_exhibit_kind_gives_no_thumb_but_still_fills_text(self):
        cards = [{"no": "H9", "title": "t", "exhibit": "nothing_like_this", "pros": "利点"}]
        new, _ = pl.link_proposals(_content([{"label": "H9"}], cards=cards))
        self.assertNotIn("thumb", _options(new)[0])
        self.assertEqual(_options(new)[0]["pros"], "利点")


class NumberSourceTests(unittest.TestCase):
    def test_number_in_prose_without_a_source_is_warned(self):
        content = {"headline": "費用は 3,370,134 トークン", "sections": [{"component": "evidence", "content": [{"type": "実測", "content": "別の数 12", "source": "x"}]}]}
        lines = pl.number_source_warnings(content)
        self.assertEqual(len(lines), 1)
        self.assertIn("3370134", lines[0])

    def test_number_found_in_evidence_table_or_stats_is_quiet(self):
        content = {
            "headline": "費用は 3,370,134 トークン・差は 28%・比は 0.93",
            "sections": [
                {"component": "evidence", "content": [{"type": "実測", "content": "合計 3370134", "source": "res.json"}]},
                {"component": "visual", "content": [{"table": {"head": ["a"], "rows": [["0.93", "28"]]}}]},
            ],
        }
        self.assertEqual(pl.number_source_warnings(content), [])

    def test_small_numbers_years_and_plain_integers_are_ignored(self):
        content = {"headline": "2026年の 12 件と 3 つ、番号 9999 は桁だけ", "sections": []}
        lines = pl.number_source_warnings(content)
        self.assertEqual(len(lines), 1)
        self.assertIn("9999", lines[0])
        self.assertNotIn("2026", lines[0])
        self.assertNotIn("（headline）・12", lines[0])

    def test_percent_and_decimal_count_even_when_short(self):
        lines = pl.number_source_warnings({"overview": "減りは 28% で比は 0.93", "sections": []})
        self.assertIn("28", lines[0])
        self.assertIn("0.93", lines[0])

    def test_many_missing_numbers_are_capped(self):
        text = " ".join("数%d は %d 件" % (i, 10000 + i) for i in range(12))
        line = pl.number_source_warnings({"overview": text, "sections": []}, limit=3)[0]
        self.assertIn("ほか9件", line)


class AbbreviatedUnitTests(unittest.TestCase):
    def test_warns_on_M_and_k_but_not_on_KB_or_words(self):
        lines = pl.abbreviated_unit_warnings({"overview": "約4.7M と 110k、ただし 12KB と 3Mbps は別、AIM は語", "sections": []})
        self.assertEqual(len(lines), 1)
        self.assertIn("4.7M", lines[0])
        self.assertIn("110k", lines[0])
        self.assertNotIn("12KB", lines[0])

    def test_quiet_when_written_in_japanese_units(self):
        self.assertEqual(pl.abbreviated_unit_warnings({"overview": "約470万トークンと1,000件", "sections": []}), [])


class MixedThumbTests(unittest.TestCase):
    def test_some_but_not_all_options_with_a_thumb_is_warned(self):
        content = _content([{"label": "a", "thumb": {"svg": "<svg/>"}}, {"label": "b"}], cards=[])
        lines = pl.mixed_thumb_warnings(content)
        self.assertEqual(len(lines), 1)
        self.assertIn("Q1", lines[0])
        self.assertIn("2個中1個", lines[0])

    def test_all_or_none_is_quiet_and_withdrawn_is_not_counted(self):
        self.assertEqual(pl.mixed_thumb_warnings(_content([{"label": "a"}, {"label": "b"}], cards=[])), [])
        self.assertEqual(pl.mixed_thumb_warnings(_content([{"label": "a", "thumb": {"svg": "<svg/>"}}, {"label": "b", "thumb": {"svg": "<svg/>"}}], cards=[])), [])
        mixed = _content([{"label": "a", "thumb": {"svg": "<svg/>"}}, {"label": "b", "withdrawn": "取り下げ"}], cards=[])
        self.assertEqual(pl.mixed_thumb_warnings(mixed), [])


class UnexplainedAsciiTests(unittest.TestCase):
    PAGE = (
        "<html><head><title>x</title></head><body><header><p class=\"eyebrow\">UNDERSTANDING COMPOSER</p></header>"
        "<section data-component=\"examples\"><p>push と Artifact を使い、<span class=\"t\" data-d=\"d\">master</span> と <code>origin</code> は別。"
        "ファイル docs/readme.md と explain-page は道具。Codex と Claude は毎回出る。</p><ul><li>staging を使う</li></ul></section>"
        "<section data-component=\"glossary\"><p>Artifact：公開の箱</p></section></body></html>"
    )

    def test_flags_unexplained_words_only(self):
        line = pl.unexplained_ascii_warnings(self.PAGE)[0]
        self.assertIn("push", line)
        self.assertIn("staging", line)
        for quiet in ("Artifact", "master", "origin", "docs", "explain", "UNDERSTANDING", "Codex", "Claude"):
            self.assertNotIn(quiet, line, quiet)

    def test_no_words_no_warning(self):
        self.assertEqual(pl.unexplained_ascii_warnings("<body><section><p>日本語だけ</p></section></body>"), [])


class ToolVersionTests(unittest.TestCase):
    def test_classify_location_never_returns_a_path(self):
        self.assertEqual(pl.classify_location("D:/work/repo/.claude/worktrees/nice-abc/.claude/scripts"), ("作業場", "nice-abc"))
        self.assertEqual(pl.classify_location("D:/work/explain-page/.claude/scripts"), ("公開版", ""))
        self.assertEqual(pl.classify_location("D:/work/.claude/plugins/cache/foo/scripts"), ("プラグイン", ""))
        self.assertEqual(pl.classify_location("D:/work/repo/.claude/scripts"), ("本線", ""))

    def test_version_is_kind_plus_hash_for_a_real_repo(self):
        text = pl.tool_version(str(HOOKS_DIR.parent / "scripts"))
        self.assertRegex(text, r"^(本線|作業場 \S+|公開版|プラグイン)( [0-9a-f]{7,12})?")
        self.assertNotIn("Users", text)

    def test_without_git_it_says_no_record(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            self.assertIn("版の記録なし", pl.tool_version(tmp))

    def test_stamp_adds_to_provenance_once_and_keeps_other_items(self):
        content = {"provenance": {"source": "a", "owner": "b"}}
        with unittest.mock.patch.object(pl, "tool_version", return_value="本線 abc1234"):
            stamped = pl.stamp_version(content, "x")
            self.assertEqual(stamped["provenance"], {"source": "a", "owner": "b", "仕組みの版": "本線 abc1234"})
            self.assertEqual(content["provenance"], {"source": "a", "owner": "b"}, "元は変えない")
            self.assertIs(pl.stamp_version(stamped, "x"), stamped, "2回目は何もしない")
            self.assertEqual(pl.stamp_version({}, "x")["provenance"], {"仕組みの版": "本線 abc1234"})
            self.assertEqual(pl.stamp_version({"provenance": "文字"}, "x")["provenance"], {"出所": "文字", "仕組みの版": "本線 abc1234"})


import unittest.mock  # noqa: E402

if __name__ == "__main__":
    unittest.main()

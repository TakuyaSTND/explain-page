"""読みやすさ関門（使ってはいけない言い回し・否定側）のテスト。

出所＝mathbullet/skills（MIT）ja-text-communication B2・B4。正本＝
`.claude/readability-rules.md`。判定ロジック＝`visual/readability.py`。
関門の状態は既定 shadow（数えて知らせるだけ・block しない）。
"""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

HOOKS_DIR = Path(__file__).resolve().parents[1]
CLAUDE_DIR = HOOKS_DIR.parent
if str(HOOKS_DIR) not in sys.path:
    sys.path.insert(0, str(HOOKS_DIR))

from visual.entrypoint import handle_event
from visual.policy import load_policy
from visual.readability import Rules, WordRule, check_text, load_rules, strip_code
from visual.state import StateStore

RULES_PATH = CLAUDE_DIR / "readability-rules.md"
CWD = "C:/repo"
SESSION = "session"


def _user_record(text: str, session: str = SESSION) -> dict:
    return {
        "type": "user",
        "sessionId": session,
        "cwd": CWD,
        "message": {"role": "user", "content": [{"type": "text", "text": text}]},
    }


def _assistant_record(blocks: list, session: str = SESSION) -> dict:
    return {
        "type": "assistant",
        "sessionId": session,
        "cwd": CWD,
        "message": {"role": "assistant", "content": blocks},
    }


def _tool_result_record(session: str = SESSION) -> dict:
    return {
        "type": "user",
        "sessionId": session,
        "cwd": CWD,
        "message": {
            "role": "user",
            "content": [{"type": "tool_result", "tool_use_id": "t1", "content": "ok"}],
        },
    }


def _write_transcript(directory: Path, records: list) -> str:
    path = directory / "transcript.jsonl"
    payload = "\n".join(json.dumps(r, ensure_ascii=False) for r in records) + "\n"
    path.write_text(payload, encoding="utf-8", newline="\n")
    return str(path)


class B2MachineRuleHitTests(unittest.TestCase):
    """B2＝英単語に日本語助詞・活用を直結しない、を機械で拾う側（当たる例）。"""

    def test_generic_na_is_a_hit(self):
        hits = check_text("この設計は generic な発想です。", Rules())
        self.assertTrue(any(hit.rule == "b2_particle_on_english_word" for hit in hits))
        self.assertTrue(any("generic" in hit.matched for hit in hits))

    def test_retrieve_shita_is_a_hit(self):
        hits = check_text("その値は retrieve した。", Rules())
        self.assertTrue(any("retrieve" in hit.matched for hit in hits))


class B2MachineRuleNonHitTests(unittest.TestCase):
    """B2非該当＝略語・助詞「を」・英文の途中で誤爆しないことの確認。"""

    def test_all_caps_abbreviation_is_not_a_hit(self):
        hits = check_text("この判断はAIに任せます。", Rules())
        self.assertEqual(hits, [])

    def test_object_particle_wo_is_not_a_hit(self):
        hits = check_text("Workflow を実行します。", Rules())
        self.assertEqual(hits, [])

    def test_english_sentence_the_is_not_a_hit(self):
        # 許容語（for/the/and/is/at 等）は語尾が続く形でも英文の一部として除外する。
        # 「な」が続く形になっていても（本来ならb2型に見える形）許容語なので当たらない。
        hits = check_text("note: the な continues", Rules())
        self.assertEqual(hits, [])

    def test_word_alone_without_suffix_is_not_a_hit(self):
        hits = check_text("data はここにあります。", Rules())
        self.assertEqual(hits, [])

    def test_technical_noun_with_locative_ni_is_not_a_hit(self):
        # 2026-09-08較正＝実頁171枚に掛けたところ、格助詞「に」を語尾候補に含めると
        # gitに／jsonに／pythonに等の普通の名詞用法が319件も当たった。「Workflow を」
        # と同じ理由（助詞としての普通の用法）で「に」は対象から外した。
        hits = check_text("設定ファイルはgitに追加した。", Rules())
        self.assertEqual(hits, [])

    def test_nado_is_not_mistaken_for_na_adjective(self):
        # 較正で implementation-result-deep.html の「decisionなど」を誤って
        # 拾った実例が見つかったため、「な」の続きが「など」等になる場合は除外する。
        hits = check_text("overview、examples、decisionなど。", Rules())
        self.assertEqual(hits, [])


class WordListRuleTests(unittest.TestCase):
    def test_word_list_hit_from_project_rules(self):
        rules = load_rules(RULES_PATH)
        self.assertTrue(rules.word_list, "readability-rules.md の語リストが読めていない")
        hits = check_text("この処理を流すと壊れます。", rules)
        self.assertTrue(any(hit.rule == "word_list:を流す" for hit in hits))

    def test_word_list_rule_directly(self):
        rules = Rules(word_list=(WordRule(term="白箱", kind="AI由来の造語", alternative="中身が見える仕組み"),))
        hits = check_text("これは白箱という考え方です。", rules)
        self.assertEqual(len(hits), 1)
        self.assertEqual(hits[0].matched, "白箱")


class CodeStripTests(unittest.TestCase):
    def test_code_block_contents_are_ignored(self):
        html = "<p>説明</p><code>generic な設定</code><pre>retrieve した値</pre>"
        hits = check_text(strip_code(html), Rules())
        self.assertEqual(hits, [])

    def test_inline_backtick_is_ignored(self):
        text = "設定は `generic な` を使う。"
        hits = check_text(strip_code(text), Rules())
        self.assertEqual(hits, [])


class PolicyDefaultTests(unittest.TestCase):
    def test_default_readability_mode_is_shadow(self):
        policy = load_policy(path=None, env={})
        self.assertEqual(policy.readability, "shadow")

    def test_policy_json_can_set_enforce(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "policy.json"
            path.write_text(json.dumps({"readability": "enforce"}), encoding="utf-8")
            policy = load_policy(path)
        self.assertEqual(policy.readability, "enforce")


class EntrypointShadowDoesNotBlockTests(unittest.TestCase):
    """shadowは数えて知らせるだけ＝読みやすさの当たりだけで新たにblockを起こさない。"""

    def test_shadow_mode_stays_noop_even_with_a_readability_hit(self):
        with tempfile.TemporaryDirectory() as td:
            transcript = _write_transcript(
                Path(td),
                [
                    _user_record("調べて"),
                    _assistant_record(
                        [
                            {"type": "text", "text": "調べます"},
                            {"type": "tool_use", "id": "t1", "name": "Bash", "input": {}},
                        ]
                    ),
                    _tool_result_record(),
                    _assistant_record(
                        [{"type": "text", "text": "調べました。generic な内容でした。"}]
                    ),
                ],
            )
            policy = load_policy(path=None, env={})
            self.assertEqual(policy.readability, "shadow")
            state = StateStore(Path(td) / "state.db")
            common = {"cwd": CWD, "session_id": SESSION, "prompt_id": "turn"}
            handle_event(
                {**common, "hook_event_name": "UserPromptSubmit", "prompt": "調べて"},
                runtime="claude",
                project_root=CWD,
                policy=policy,
                html_output_path=CLAUDE_DIR / "html-output.md",
                state_store=state,
                readability_rules_path=RULES_PATH,
            )
            result = handle_event(
                {
                    **common,
                    "hook_event_name": "Stop",
                    "transcript_path": transcript,
                    "stop_hook_active": False,
                },
                runtime="claude",
                project_root=CWD,
                policy=policy,
                html_output_path=CLAUDE_DIR / "html-output.md",
                state_store=state,
                readability_rules_path=RULES_PATH,
            )
        self.assertEqual(result, {})



class AttributeStrippingTests(unittest.TestCase):
    def test_attribute_copies_are_not_checked(self):
        # コピー釦の複製本文・表の見出し複製・読み上げ用ラベルは本文の複製＝当たりにしない。
        from visual.readability import strip_code
        html = ('<button data-copy="cloneした別環境">コピー</button>'
                '<td data-label="cloneした">値</td>'
                '<span aria-label="語：genericな説明">語</span>'
                '<pre class="log">genericな</pre><p>普通の文。</p>')
        stripped = strip_code(html)
        self.assertNotIn("cloneした", stripped)
        self.assertNotIn("genericな", stripped)
        self.assertIn("普通の文", stripped)

    def test_body_text_still_checked_after_attribute_stripping(self):
        from visual.readability import strip_code
        html = '<p class="x" data-label="a">retrieveした結果</p>'
        self.assertIn("retrieveした結果", strip_code(html))


class SectionScopedRulesTests(unittest.TestCase):
    def test_tables_outside_word_list_section_are_ignored(self):
        import tempfile
        from pathlib import Path
        from visual.readability import load_rules
        lines = [
            "# 正本", "", "## 語リスト", "",
            "| 語 | 型 | 代わりの言い方 |", "|---|---|---|", "| に落とす | 俗語 | 〜で作る |", "",
            "## 較正の記録", "",
            "| 種別 | 件数 | 中身 |", "|---|---|---|", "| 自己言及 | 18 | 例文 |",
        ]
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "rules.md"
            path.write_text(chr(10).join(lines), encoding="utf-8")
            rules = load_rules(path)
        terms = [rule.term for rule in rules.word_list]
        self.assertIn("に落とす", terms)
        self.assertNotIn("自己言及", terms)
        self.assertNotIn("種別", terms)


if __name__ == "__main__":
    unittest.main()

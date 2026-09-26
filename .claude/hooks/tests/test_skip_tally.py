"""検品証を作れなかった回数を、期限なしで数える検査（2026-08-31 実害から）。

⚠️**なぜ要るか＝この件で丸一日を使った。**
   別セッションが「公開したのに警告が1件も残っていない」と報告し、双方で合計5つの
   誤った読みを重ねた末に、原因は単純だった＝警告の保存期間は**24時間**で、問題の公開は
   3日前だったので**証拠が原理的に消えていた**。∴「起きなかった」と「記録が消えた」を
   区別できなかった。

∴中身（どのpathか・理由）は今までどおり24時間で消し、**回数だけを期限なしで残す**。
   ⚠️保存期間そのものを延ばすと台帳が膨らみ、古い記録が判断に混ざる危険が増える。
"""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

HOOKS_DIR = Path(__file__).resolve().parents[1]
if str(HOOKS_DIR) not in sys.path:
    sys.path.insert(0, str(HOOKS_DIR))

from visual.state import StateStore

DAY = 86400.0
def _day(at: float) -> str:
    """その時刻の日付（世界標準時）。⚠️固定文字列で書くと年を間違える（実際に間違えた）。"""
    import time
    return time.strftime("%Y-%m-%d", time.gmtime(at))

# 固定の時刻。⚠️`time.time()` を使うと日付の境目で揺れるので固定する。
# ⚠️この値は **2025-08-24 01:46:40 UTC**＝**いまより約1年前**である（意図した「だいたい現在」
#   より1年古い値をこちらが書いた）。検査の中身には影響しないが、出てくる日付が2025年に
#   なるので、読む人が「年が違う」と混乱しないようここに明記する。
BASE = 1_756_000_000.0


def _store(td):
    return StateStore(Path(td) / "state.db")


def _save(store, *, at, path="C:/tmp/x.html", session="s1"):
    store.save_receipt_skip(
        runtime="claude",
        project_hash="ph",
        session_id=session,
        turn_id="t1",
        path=path,
        reason="[検品証なし] 承認済みの置き場の外",
        ttl_seconds=int(DAY),
        now=at,
    )


class TallySurvivesTheCleanupTests(unittest.TestCase):
    """⚠️これが今回の実害の核心＝中身が消えても回数は残る。"""

    def test_the_detail_expires_but_the_count_remains(self):
        with tempfile.TemporaryDirectory() as td:
            store = _store(td)
            _save(store, at=BASE)

            # 3日後に別の1件を保存する＝そのとき古い中身は掃除される。
            _save(store, at=BASE + 3 * DAY, path="C:/tmp/y.html")

            details = store.load_receipt_skips(project_hash="ph", now=BASE + 3 * DAY)
            tally = store.load_receipt_skip_tally(project_hash="ph")

        # 中身は新しい1件だけ（3日前の分は消えている）
        self.assertEqual(len(details), 1)
        self.assertIn("y.html", details[0][0])
        # ⚠️回数は両方の日が残る＝「起きなかった」と「消えた」を区別できる
        self.assertEqual(len(tally), 2)
        self.assertEqual({day for day, _ in tally}, {_day(BASE), _day(BASE + 3 * DAY)})
        self.assertEqual({count for _, count in tally}, {1})

    def test_repeats_in_one_day_are_counted_up(self):
        with tempfile.TemporaryDirectory() as td:
            store = _store(td)
            for offset in (0.0, 60.0, 120.0, 180.0):
                _save(store, at=BASE + offset)
            tally = store.load_receipt_skip_tally(project_hash="ph")

        self.assertEqual(len(tally), 1)
        self.assertEqual(tally[0][1], 4)

    def test_the_newest_day_comes_first(self):
        with tempfile.TemporaryDirectory() as td:
            store = _store(td)
            _save(store, at=BASE)
            _save(store, at=BASE + DAY)
            _save(store, at=BASE + 2 * DAY)
            tally = store.load_receipt_skip_tally(project_hash="ph")

        self.assertEqual(
            [day for day, _ in tally],
            [_day(BASE + 2 * DAY), _day(BASE + DAY), _day(BASE)],
        )

    def test_other_projects_are_not_mixed_in(self):
        with tempfile.TemporaryDirectory() as td:
            store = _store(td)
            _save(store, at=BASE)
            store.save_receipt_skip(
                runtime="claude", project_hash="other", session_id="s2", turn_id="t2",
                path="C:/tmp/z.html", reason="別のプロジェクト",
                ttl_seconds=int(DAY), now=BASE,
            )
            mine = store.load_receipt_skip_tally(project_hash="ph")
            theirs = store.load_receipt_skip_tally(project_hash="other")

        self.assertEqual(mine[0][1], 1)
        self.assertEqual(theirs[0][1], 1)

    def test_nothing_recorded_means_an_empty_list(self):
        # ⚠️「0件」と「表が無い」を混ぜない＝呼んでも落ちないこと。
        with tempfile.TemporaryDirectory() as td:
            self.assertEqual(_store(td).load_receipt_skip_tally(project_hash="ph"), ())

    def test_the_days_limit_is_respected(self):
        with tempfile.TemporaryDirectory() as td:
            store = _store(td)
            for n in range(5):
                _save(store, at=BASE + n * DAY)
            tally = store.load_receipt_skip_tally(project_hash="ph", days=2)

        self.assertEqual(len(tally), 2)


class TheTallyHasNoExpiryTests(unittest.TestCase):
    def test_the_table_carries_no_expiry_column(self):
        # ⚠️期限の列を足すと掃除の対象になり、この検査の意味が消える。
        source = (HOOKS_DIR / "visual" / "state.py").read_text(encoding="utf-8")
        start = source.index("CREATE TABLE IF NOT EXISTS receipt_skip_tally")
        ddl = source[start: source.index(")", source.index("PRIMARY KEY", start))]

        self.assertNotIn("expires_at", ddl)
        self.assertIn("count INTEGER NOT NULL", ddl)


if __name__ == "__main__":
    unittest.main()

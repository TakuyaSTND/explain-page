"""組み上がった頁の濃さを道具が報告する検査（2026-09-01 ユーザー指摘）。

⚠️**指示文に書いただけでは効かなかった**＝実測。
   09-01 00:33 に指示文へ密度の部品を列挙したのに、10:13 に別セッションが組んだ頁は
   図解0・タイル0・段組み0・色札4・目次0 だった。その頁は道具で組まれ検品も通っている
   ＝**道具は使えているが密度だけ伝わっていない**。∴伝える場所を、その人が走らせる道具の
   出力に移した。

⚠️止めはしない（助言だけ）＝密度の正しさは中身次第で、機械には決められない。
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parents[2] / "scripts"
HOOKS_DIR = Path(__file__).resolve().parents[1]
for entry in (str(HOOKS_DIR), str(SCRIPTS_DIR)):
    if entry not in sys.path:
        sys.path.insert(0, entry)

import render_page as rp

BIG = 20_000


def _page(**parts):
    """濃さの目印だけを並べた最小のHTML。⚠️`<body>` 以降しか数えないので必ず付ける。"""
    marks = {
        "図解": '<div class="dia-wrap"></div>',
        "カード": '<div class="card-stack"></div>',
        "段組み": '<div class="cols" data-cols="2"></div>',
        "タイル": '<div class="tiles"></div>',
        "色札": '<span class="badge b-good">x</span>',
        "表": "<table></table>",
        "目次": '<nav class="toc"></nav>',
    }
    body = "".join(marks[name] * count for name, count in parts.items())
    return "<html><body>" + body + "</body></html>"


class CountingTests(unittest.TestCase):
    def test_only_the_body_is_counted(self):
        # ⚠️CSSの定義に同じ語が出る＝頭を数えると常に「濃い」と誤判定する。
        html = '<html><style>.dia-wrap{}</style><body><span class="badge b-good">x</span></body></html>'
        got = dict(rp.density(html))

        self.assertEqual(got["図解"], 0)
        self.assertEqual(got["色札"], 1)

    def test_every_part_is_counted(self):
        got = dict(rp.density(_page(図解=1, カード=2, 段組み=1, タイル=3, 色札=12, 表=4, 目次=1)))

        self.assertEqual(got["図解"], 1)
        self.assertEqual(got["カード"], 2)
        self.assertEqual(got["タイル"], 3)
        self.assertEqual(got["色札"], 12)
        self.assertEqual(got["目次"], 1)


class AdviceTests(unittest.TestCase):
    """⚠️空振りでないこと＝薄い頁で本当に出て、濃い頁では出ないこと。"""

    def test_a_prose_only_page_gets_advice(self):
        advice = rp.advise_density(rp.density(_page()), BIG)

        self.assertTrue(advice)
        self.assertTrue(any("図解が0" in line for line in advice))
        self.assertTrue(any("色札が0個" in line for line in advice))
        self.assertTrue(any("カード・タイル・段組みが全部0" in line for line in advice))

    def test_a_dense_page_gets_no_advice(self):
        dense = _page(図解=1, 段組み=1, タイル=1, 色札=34, 表=7, 目次=1)

        self.assertEqual(rp.advise_density(rp.density(dense), BIG), [])

    def test_a_short_page_is_left_alone(self):
        # ⚠️短い頁に濃さを求めない＝空振りで作業を止めないため。
        self.assertEqual(rp.advise_density(rp.density(_page()), 3000), [])

    def test_the_thresholds_match_what_was_measured(self):
        """⚠️目安は実測から取った＝濃い頁は色札25〜45、薄い頁は色札4〜8だった。"""
        thin = rp.advise_density(rp.density(_page(色札=8, 図解=1, 表=3, カード=1)), BIG)
        thick = rp.advise_density(rp.density(_page(色札=25, 図解=1, 表=3, カード=1, 目次=1)), BIG)

        self.assertTrue(any("色札が8個" in line for line in thin))
        self.assertEqual(thick, [])

    def test_advice_names_the_key_to_write(self):
        """助言は「何を書けばよいか」まで言う＝言われても直せない形にしない。"""
        advice = rp.advise_density(rp.density(_page()), BIG)
        joined = " ".join(advice)

        for key in ("diagram", "cards", "tiles", "columns", "toc"):
            self.assertIn(key, joined)


if __name__ == "__main__":
    unittest.main()

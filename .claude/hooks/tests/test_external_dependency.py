"""検品の「外部の依存」の判定の試験（2026-09-26 新設）。

実害＝報告の頁の記録の欄に「git fetch」と書いただけで、公開時（PostToolUse の Artifact）に
「HTMLが外部URLを読み込んでいる」と判定され、検品の記録が作られなかった。原因は
`receipts.NETWORK_CODE` が頁の全文に当たり、エスケープされた地の文の単語 fetch にも
一致していたこと。いっぽう頁を組む道具（render_page.py）は同じ頁を合格と出していた。

ここで確かめること＝①地の文の単語（git fetch・fetch the data・@import・url()）は通る
②script の中の fetch・on で始まる属性・javascript: の値・外部の src・相対の src・
CSS の @import と url() は引き続き止まる ③レンダラーが組んだ本物の頁で、検品の記録が
作れ、頁を組む道具の判定も同じになる。
"""
from __future__ import annotations

import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch

HOOKS_DIR = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = HOOKS_DIR.parent / "scripts"
for _entry in (str(HOOKS_DIR), str(SCRIPTS_DIR)):
    if _entry not in sys.path:
        sys.path.insert(0, _entry)

from visual.contracts import ExplanationPlan, GlossarySnapshot, HookEnvelope  # noqa: E402
from visual.receipts import (  # noqa: E402
    _has_external_dependency,
    build_receipt,
    external_dependency_reason,
)
from visual.render_components import render_components  # noqa: E402

import render_page as rp  # noqa: E402

PROSE = "送る前＝git fetch のあと origin との差を見た。次に fetch the data の手順を読む。"


def _envelope() -> HookEnvelope:
    return HookEnvelope(
        1, "claude", "", "PostToolUse", "C:/repo", "",
        "session", "turn", "", "", "", "", "", (), False, 0,
        frozenset({"can_receipt"}), True,
    )


def _glossary() -> GlossarySnapshot:
    return GlossarySnapshot(
        "home", "shared.md", "shared", "shared", "project",
        "effective", 1, 0, 1, (), (), True,
    )


def _rendered_page(text: str) -> str:
    plan = ExplanationPlan(
        audience="project_novice",
        depth="deep",
        components=("overview", "details"),
        reason_codes=(),
        provisional=False,
        should_continue=False,
        delivery="local_html",
        publish_policy="never",
    )
    return render_components(
        plan,
        title="検品の記録の試験",
        content={
            "overview": text,
            "sections": [
                {"component": "details", "num": "壱", "label": "記録", "content": [{"log": text}]}
            ],
        },
    )


class ProseWordsAreNotNetworkCodeTests(unittest.TestCase):
    def test_prose_fetch_passes(self):
        html = "<p>git fetch のあと</p><p>fetch the data</p><pre>git fetch origin</pre>"
        self.assertIsNone(external_dependency_reason(html))

    def test_prose_css_words_pass(self):
        html = "<p>@import と書いた</p><p>url(a.png) と書いた</p><p>src=&quot;x.png&quot;</p>"
        self.assertIsNone(external_dependency_reason(html))

    def test_rendered_page_with_fetch_in_prose_builds_a_receipt(self):
        html = _rendered_page(PROSE)
        self.assertIn("git fetch", html)
        self.assertFalse(_has_external_dependency(html))
        with tempfile.TemporaryDirectory() as td:
            page = Path(td) / "prose-fetch.html"
            page.write_text(html, encoding="utf-8")
            receipt = build_receipt(
                page,
                envelope=_envelope(),
                glossary=_glossary(),
                glossary_entries={},
                local_root=td,
                previewed=True,
                required_components=("overview",),
                visual_smoke_status="pass",
            )
        self.assertEqual(receipt.visibility, "local")


class ActiveCodeIsStillBlockedTests(unittest.TestCase):
    def test_script_fetch_call_is_blocked(self):
        self.assertIsNotNone(external_dependency_reason("<p>x</p><script>fetch('/x')</script>"))

    def test_script_fetch_reference_without_call_is_blocked(self):
        # script の中では呼び出しの形でなくても止める（関数を別名で持つだけで通信できる）
        self.assertIsNotNone(external_dependency_reason("<script>const f = window.fetch;</script>"))

    def test_other_network_apis_in_script_are_blocked(self):
        for code in ("new WebSocket('x')", "new XMLHttpRequest()", "new EventSource('x')",
                     "navigator.sendBeacon('x')"):
            with self.subTest(code=code):
                self.assertIsNotNone(external_dependency_reason("<script>%s</script>" % code))

    def test_event_attribute_and_javascript_url_are_blocked(self):
        self.assertIsNotNone(external_dependency_reason('<button onclick="fetch(1)">x</button>'))
        self.assertIsNotNone(external_dependency_reason('<a href="javascript:fetch(1)">x</a>'))

    def test_external_and_relative_sources_are_blocked(self):
        self.assertIsNotNone(external_dependency_reason('<img src="https://example.com/a.png">'))
        self.assertIsNotNone(external_dependency_reason('<img src="./a.png">'))
        self.assertIsNotNone(external_dependency_reason('<script src="app.js"></script>'))

    def test_css_import_and_url_are_blocked(self):
        self.assertIsNotNone(external_dependency_reason("<style>@import 'x.css';</style>"))
        self.assertIsNotNone(external_dependency_reason("<style>body{background:url(a.png)}</style>"))
        self.assertIsNotNone(external_dependency_reason('<div style="background:url(a.png)"></div>'))

    def test_data_uri_and_fragment_references_pass(self):
        self.assertIsNone(external_dependency_reason('<img src="data:image/png;base64,AA==">'))
        self.assertIsNone(external_dependency_reason('<svg><rect fill="url(#g)"></rect></svg>'))

    def test_external_url_in_prose_is_still_blocked(self):
        # 外部のURLは従来どおり全文で止める（今回の直しの範囲外＝緩めない）
        self.assertIsNotNone(external_dependency_reason("<p>https://example.com を見る</p>"))

    def test_script_fetch_blocks_a_receipt(self):
        with tempfile.TemporaryDirectory() as td:
            page = Path(td) / "script-fetch.html"
            page.write_text("<header data-component=\"overview\"></header><script>fetch('/x')</script>",
                            encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "external dependency"):
                build_receipt(page, envelope=_envelope(), glossary=_glossary(),
                              glossary_entries={}, local_root=td)


class RenderPageAgreesWithTheReceiptTests(unittest.TestCase):
    """頁を組む道具の合否と、公開時の検品の記録の判定がそろっている。"""

    def _check(self, html: str) -> dict:
        passing_smoke = types.SimpleNamespace(status="pass", errors=())
        with tempfile.TemporaryDirectory() as td:
            page = Path(td) / "page.html"
            page.write_text(html, encoding="utf-8")
            with patch.object(rp, "run_visual_smoke", return_value=passing_smoke):
                return rp.check(str(page), ["overview"])

    def test_prose_fetch_page_is_not_flagged(self):
        result = self._check(_rendered_page(PROSE))
        self.assertEqual(result["external_dependency"], [])

    def test_script_fetch_page_fails_with_the_reason(self):
        html = _rendered_page("本文。").replace("</body>", "<script>fetch('/x')</script></body>")
        result = self._check(html)
        self.assertFalse(result["ok"])
        self.assertEqual(len(result["external_dependency"]), 1)
        self.assertIn("通信のコード", result["external_dependency"][0])


if __name__ == "__main__":
    unittest.main()

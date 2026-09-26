#!/usr/bin/env python3
"""大きい頁で表示検査が持つかを測る道具（2026-08-30 ユーザー選択）。

なぜ要るか＝手で作る報告の頁は5万バイト級だが、**手書きの参照頁は106KB**で桁が1つ違う。
「この大きさでも表示検査が通るか」を測っていなかったので、合成の頁で測れるようにした。

⚠️合成である＝中身は同じ形の節を繰り返して膨らませただけで、読み物としての意味は無い。
   測っているのは**表示と検査の持ち**だけ（横溢れ・JSエラー・押せるか・所要時間）。

使い方:
  PYTHONUTF8=1 python .claude/scripts/stress_page.py [目標バイト数]

既定は 110000 バイト（参照頁の106KBを少し超える）。
"""
import io
import json
import os
import sys
import time

NL = chr(10)
HERE = os.path.dirname(os.path.abspath(__file__))
CLAUDE_DIR = os.path.dirname(HERE)
HOOKS_DIR = os.path.join(CLAUDE_DIR, "hooks")
if HOOKS_DIR not in sys.path:
    sys.path.insert(0, HOOKS_DIR)
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import render_page as rp  # noqa: E402
from visual.contracts import ExplanationPlan  # noqa: E402
from visual.render_components import render_components  # noqa: E402

FILLER = (
    "測定のために置いた文である。読み物としての意味は無く、頁を大きくするためだけにある。"
    "ここで見ているのは表示の持ちであって、書かれている内容ではない。"
)


def _one_table(index):
    return {
        "head": ["項目", "値", "備考"],
        "widths": ["150px", "90px", ""],
        "rows": [[f"項目{index}-{row}", str(index * 100 + row), FILLER[:40]] for row in range(6)],
    }


def _section(index):
    """1節ぶんの中身を作る。⚠️見出しは重複させない（見出し検査に引っかかる）。"""
    kind = index % 4
    if kind == 0:
        return "table", {"heading": f"測定用の並び {index}", "caption": "合成の中身",
                         **_one_table(index)}
    if kind == 1:
        return "examples", [{
            "heading": f"測定用の札 {index}",
            "text": FILLER,
            "cards": [
                {"badge": f"札 {index}-{n}", "tone": ["good", "warn", "bad", "new"][n % 4],
                 "title": f"見出し {index}-{n}", "text": FILLER,
                 "objection": f"測定用の判定 {index}-{n}"}
                for n in range(3)
            ],
        }]
    if kind == 2:
        return "walkthrough", [{
            "heading": f"測定用の説明 {index}",
            "text": FILLER,
            "items": [f"箇条書き {index}-{n}：{FILLER[:30]}" for n in range(5)],
            "note": "⚠️" + FILLER[:60],
        }]
    return "log", NL.join(f"行 {index}-{n}：{FILLER[:50]}" for n in range(8))


def build_spec(count):
    """節を count 個ぶら下げた合成の頁の定義を作る。"""
    sections = []
    content = {}
    for index in range(count):
        component, value = _section(index)
        key = f"測定{index}"
        content[key] = value
        sections.append({
            "component": component,
            "num": str(index + 1),
            "label": f"測定用の節 {index + 1}",
            "content": value,
        })
    content.update({
        "provenance": {"source": ".claude/scripts/stress_page.py", "owner": "local"},
        "overview": "大きい頁で表示検査が持つかを測るための合成の頁である。" + FILLER,
        "summary": (
            "Goal：大きい頁で表示検査が持つかを測る。" + NL
            + "Now：合成の節を並べて目標のバイト数まで膨らませた。" + NL
            + "Risk：中身は合成なので、読み物としての質は測っていない。"
        ),
        "progress": "完了：合成の頁の組み立て。" + NL + "人待ち：無し。",
        "visual": "小さい頁｜大きい頁" + NL + "5万バイト級｜10万バイト級",
        "decision": {"options": ["この大きさで十分", "もっと大きくして測る"],
                     "judgments": ["この頁は合成であり、読み物としての質は測っていない"]},
        "evidence": "実測：合成の頁で表示検査を通した｜`.claude/scripts/stress_page.py`",
        "glossary": "表示検査：本物のブラウザで頁を開き、横に溢れていないか・押せるかを機械で確かめること。",
        "details": [{"summary": "この頁の作り方", "text": "同じ形の節を繰り返して膨らませただけである。"}],
        # ⚠️側柱と目次も一緒に積む＝節が数十個あるときに目次が画面を突き抜けないかを見る。
        "rail": [{"heading": "目次", "toc": True},
                 {"heading": "この頁について", "text": "合成の頁である。"}],
    })
    ordered = ["overview", "summary", "walkthrough", "examples", "progress", "visual",
               "table", "log", "decision", "evidence", "glossary", "details"]
    sections.extend([
        {"component": name, "num": "終" + str(n + 1), "label": f"締めの節 {n + 1}"}
        for n, name in enumerate(("progress", "visual", "decision", "evidence",
                                  "glossary", "details"))
    ])
    content["sections"] = sections
    return {
        "name": "renderer-stress",
        "title": "表示検査の耐荷重（合成の頁）",
        "components": ordered,
        "reasons": ["project_novice_default", "explicit_page_request"],
        "publish": "never",
        "content": content,
    }


def _size_of(spec):
    plan = ExplanationPlan(
        audience="project_novice",
        depth="deep",
        components=tuple(spec["components"]),
        reason_codes=tuple(spec["reasons"]),
        provisional=False,
        should_continue=False,
        delivery="local_html",
        publish_policy=spec["publish"],
    )
    _, entries = rp._glossary()
    html = render_components(
        plan, title=spec["title"], content=spec["content"], glossary_entries=entries
    )
    return len(html.encode("utf-8"))


def main(argv):
    target = int(argv[1]) if len(argv) > 1 else 110000
    count = 8
    spec = build_spec(count)
    # ⚠️1節ぶんの大きさから逆算せず、実際に組んで測って増やす（部品ごとに嵩が違う）。
    while _size_of(spec) < target and count < 400:
        count += 4
        spec = build_spec(count)
    size = _size_of(spec)
    path = os.path.join(rp.APPROVED_ROOT, "stress-spec.json")
    os.makedirs(rp.APPROVED_ROOT, exist_ok=True)
    io.open(path, "w", encoding="utf-8", newline=NL).write(
        json.dumps(spec, ensure_ascii=False, indent=1)
    )
    print("合成の頁：節 %d 個 / %d バイト" % (count, size))
    print("定義: " + path)

    started = time.perf_counter()
    code = rp.main([argv[0], path])
    print("組み立てから検査までの所要: %.1f 秒" % (time.perf_counter() - started))
    return code


if __name__ == "__main__":
    if sys.platform == "win32":
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass
    raise SystemExit(main(sys.argv))

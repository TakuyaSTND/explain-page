"""描き終えた箱と矢印の図を、ブラウザの実寸で点検する（2026-11-04・利用者が選んだ A3）。

なぜ要るか＝配置の計算（diagram_layout.py）は描く前の見積もりで、箱と線の衝突は避けるが、
辺のラベルが「別の線」や「別のラベル」と重なるか、線どうしが同じ縦線・横線の上で重なるかは
見ていなかった。実測（2026-11-04）＝既存の図165個の見積もりで、別の線が通るラベル19本・
ラベル同士4組・重なる直線15組。撮影した3枚のうち2枚で崩れを目で確かめ、1枚は見積もりの誤検出
だった＝見積もりでなく、描いた後の実寸（getBBox・getPointAtLength）で測る。

使い方＝`DIAGRAM_CHECK_JS` は「引数なしの関数」の JavaScript の式。Playwright の
`page.evaluate('(' + DIAGRAM_CHECK_JS + ')()')` で頁の中で動かすと、見つけたものの一覧
（`{fig, title, kind, text}` の辞書の配列・最大40件）を返す。`describe()` がそれを人に見せる1行にする。
表示検査（visual_smoke.py・頁を組むたび）と撮影の道具（page_check.py）が同じものを使う
（利用者の回答 Q6 A＝両方で同じ結果）。

⚠️警告だけ（利用者の回答 Q3 A＝較正が済むまで）。表示検査の合否（errors）には入れない。
⚠️対象は箱と矢印の図（`svg.dia`）だけ（Q7 A）＝ラベル（縁取り付きの text）と矢印（fill="none" の
  path）を道具の出力の形で見分けられるので、誤検出が少ない。数値の図・年表などは見ない。
⚠️ラベルと矢印の結び付きは `data-r`（render_components.py が付ける経路の番号）で取る。
  古い頁で `data-r` が無いときは、ラベルの中心にいちばん近い線を「自分の線」とみなす。
"""

from __future__ import annotations

from typing import Any, Iterable

# 見つけたものの種類 → 人に見せる言い方。
KIND_TEXT = {
    "label-crossed": "ラベル「%s」に別の線が通る",
    "label-overlap": "ラベル「%s」が別のラベルと重なる",
    "text-clipped": "文字「%s」が図の枠の外で切れる",
    "box-text-overflow": "箱の文字「%s」が箱からはみ出す",
    "routes-stacked": "2本の線が同じ縦線・横線の上で重なる（%s）",
}

DIAGRAM_CHECK_JS = r"""() => {
  const out = [];
  const push = (f) => { if (out.length < 40) out.push(f); };
  const figs = Array.from(document.querySelectorAll('svg.dia'));
  figs.forEach((svg, fi) => {
    try {
      const title = (svg.getAttribute('aria-label') || '').slice(0, 40);
      const vb = svg.viewBox && svg.viewBox.baseVal;
      const W = vb && vb.width ? vb.width : 0;
      const H = vb && vb.height ? vb.height : 0;
      const kids = Array.from(svg.children);
      const routes = kids.filter((el) => el.tagName === 'path' && el.getAttribute('fill') === 'none');
      const labels = kids.filter((el) => el.tagName === 'text' && el.getAttribute('paint-order') === 'stroke');
      const samples = routes.map((p) => {
        const pts = [];
        let len = 0;
        try { len = p.getTotalLength(); } catch (e) { len = 0; }
        for (let d = 0; d <= len; d += 2) { const q = p.getPointAtLength(d); pts.push([q.x, q.y]); }
        return pts;
      });
      const inside = (pt, b, m) => pt[0] > b.x + m && pt[0] < b.x + b.width - m && pt[1] > b.y + m && pt[1] < b.y + b.height - m;
      const ownOf = (t, b) => {
        const r = t.getAttribute('data-r');
        if (r !== null) return routes.findIndex((p) => p.getAttribute('data-r') === r);
        const cx = b.x + b.width / 2, cy = b.y + b.height / 2;
        let best = -1, bestD = Infinity;
        samples.forEach((pts, ri) => pts.forEach((pt) => {
          const d = Math.hypot(pt[0] - cx, pt[1] - cy);
          if (d < bestD) { bestD = d; best = ri; }
        }));
        return best;
      };
      const boxes = labels.map((t) => t.getBBox());
      labels.forEach((t, li) => {
        const b = boxes[li];
        const own = ownOf(t, b);
        const hit = samples.some((pts, ri) => ri !== own && pts.some((pt) => inside(pt, b, 1)));
        if (hit) push({ fig: fi + 1, title, kind: 'label-crossed', text: t.textContent.slice(0, 30) });
      });
      for (let i = 0; i < labels.length; i++) {
        for (let j = i + 1; j < labels.length; j++) {
          const a = boxes[i], c = boxes[j];
          const w = Math.min(a.x + a.width, c.x + c.width) - Math.max(a.x, c.x);
          const h = Math.min(a.y + a.height, c.y + c.height) - Math.max(a.y, c.y);
          if (w > 2 && h > 2) push({ fig: fi + 1, title, kind: 'label-overlap', text: labels[i].textContent.slice(0, 30) });
        }
      }
      if (W && H) {
        Array.from(svg.querySelectorAll('text')).forEach((t) => {
          const b = t.getBBox();
          if (!b.width) return;
          if (b.x < -1 || b.y < -1 || b.x + b.width > W + 1 || b.y + b.height > H + 1) {
            push({ fig: fi + 1, title, kind: 'text-clipped', text: t.textContent.slice(0, 30) });
          }
        });
      }
      kids.filter((el) => el.tagName === 'g').forEach((g) => {
        const rect = g.querySelector(':scope > rect');
        if (!rect) return;
        const rx = rect.x.baseVal.value, ry = rect.y.baseVal.value;
        const rw = rect.width.baseVal.value, rh = rect.height.baseVal.value;
        Array.from(g.querySelectorAll(':scope > text')).forEach((t) => {
          const b = t.getBBox();
          if (!b.width) return;
          if (b.x < rx - 1 || b.x + b.width > rx + rw + 1 || b.y + b.height > ry + rh + 1) {
            push({ fig: fi + 1, title, kind: 'box-text-overflow', text: t.textContent.slice(0, 30) });
          }
        });
      });
      for (let i = 0; i < samples.length; i++) {
        for (let j = i + 1; j < samples.length; j++) {
          let n = 0;
          samples[i].forEach((p) => {
            if (samples[j].some((q) => Math.abs(p[0] - q[0]) < 1.5 && Math.abs(p[1] - q[1]) < 1.5)) n += 1;
          });
          if (n * 2 > 8) push({ fig: fi + 1, title, kind: 'routes-stacked', text: Math.round(n * 2) + 'px' });
        }
      }
    } catch (e) {
      push({ fig: fi + 1, title: '', kind: 'check-failed', text: String(e).slice(0, 60) });
    }
  });
  return out;
}"""


def describe(findings: Iterable[Any]) -> list[str]:
    """見つけたものの一覧を、人に見せる1行ずつにする（同じ行は1回だけ）。"""
    lines: list[str] = []
    for item in findings or []:
        if not isinstance(item, dict):
            continue
        kind = str(item.get("kind") or "")
        text = str(item.get("text") or "")
        title = str(item.get("title") or "").strip()
        head = "図%s" % item.get("fig", "?") + ("（%s）" % title if title else "")
        if kind in KIND_TEXT:
            body = KIND_TEXT[kind] % text
        elif kind == "check-failed":
            body = "点検が走らなかった（%s）" % text
        else:
            continue
        line = "%s：%s" % (head, body)
        if line not in lines:
            lines.append(line)
    return lines

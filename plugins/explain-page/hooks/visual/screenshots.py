"""画面を撮って頁に貼るための撮影係（2026-10-01・ユーザー承認の P2）。

なぜ要るか
----------
頁を組む道具（render_page.py）は、ファイルになった画像なら `image` で貼れる。けれど
「いま直した画面を見せる」には、エージェントが自分でブラウザを動かして撮り、ファイルに
してから渡す必要があった。この係は、組む途中で手元の頁や開発中の localhost の頁を撮り、
その PNG を返す。貼る処理（縮小・圧縮・出所の行）は `images.embed_image` に任せる。

安全の決まり
------------
撮ってよいのは「手元のファイル」と「開発用の名前（localhost・127.0.0.1・[::1]・
*.localhost・*.test）」の http(s) だけ。ほかの頁は撮らない＝組む道具が外の頁を開いて
中身を頁に写すと、情報の持ち出しやログイン中の画面の写り込みが起きるため。

撮影には表示検査（visual_smoke.py）と同じ Playwright を使う（同じ探し方）。
"""
from __future__ import annotations

import json
import os
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, Optional
from urllib.parse import urlparse

from .visual_smoke import _resolve_playwright

LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1"}
LOCAL_SUFFIXES = (".localhost", ".test")

# ⚠️バックスラッシュを書かない（CLAUDE.md の決まり）＝引数は JSON で渡す。
NODE_SHOT_SCRIPT = r"""
const playwrightPath = process.argv[1];
const target = process.argv[2];
const outPath = process.argv[3];
const opts = JSON.parse(process.argv[4]);
const pw = require(playwrightPath);
(async () => {
  const browser = await pw.chromium.launch();
  try {
    const page = await browser.newPage({
      viewport: { width: opts.width, height: opts.height },
      deviceScaleFactor: opts.scale,
    });
    await page.goto(target, { waitUntil: "load", timeout: opts.timeout_ms });
    if (opts.wait_ms > 0) { await page.waitForTimeout(opts.wait_ms); }
    if (opts.selector) {
      const el = await page.$(opts.selector);
      if (!el) { console.log(JSON.stringify({ ok: false, error: "selector not found" })); return; }
      await el.screenshot({ path: outPath });
    } else {
      await page.screenshot({ path: outPath, fullPage: !!opts.full_page });
    }
    console.log(JSON.stringify({ ok: true }));
  } finally {
    await browser.close();
  }
})().catch((e) => {
  console.log(JSON.stringify({ ok: false, error: String((e && e.message) || e).slice(0, 200) }));
});
"""


@dataclass
class ShotResult:
    png: Optional[bytes]
    target: str
    label: str
    warnings: list = field(default_factory=list)
    # 根拠欄に書く撮った先＝手元のファイルは場所そのもの、URL は「http://」を外した形。
    # ⚠️頁の文字に http:// や file:// が入ると、検品が外部の読み込みとみなして落とす（receipts.py）。
    place: str = ""


def _int(value: Any, default: int, lo: int, hi: int) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return default
    return max(lo, min(hi, number))


def schemeless(text: str) -> str:
    """頁に出す文字から http:// https:// file:// を外す（検品の外部 URL の判定に当たらないように）。"""
    out = str(text or "")
    for prefix in ("https://", "http://", "file:///", "file://"):
        if out.lower().startswith(prefix):
            return out[len(prefix):]
    return out

def resolve_target(raw: Any) -> tuple[Optional[str], str]:
    """撮る先を、ブラウザに渡す URL に直す。返るもの＝(URL か None, 理由か表示名)。

    手元のファイルは file:// に直す。http(s) は開発用の名前だけ通す。
    """
    text = str(raw or "").strip()
    if not text:
        return None, "撮る先（target）が空"
    parsed = urlparse(text)
    if parsed.scheme in ("http", "https"):
        host = (parsed.hostname or "").lower()
        if host in LOCAL_HOSTS or host.endswith(LOCAL_SUFFIXES):
            return text, schemeless(text)
        return None, "外部の頁は撮らない（手元のファイルと localhost などの開発用の頁だけ）：" + schemeless(text)
    if parsed.scheme == "file":
        return text, schemeless(text)
    if parsed.scheme and len(parsed.scheme) > 1:
        return None, "撮れない種類の場所：" + schemeless(text)
    path = Path(text)
    if not path.is_file():
        return None, "ファイルが見つからない：" + text
    # 図の説明に出す名前はファイル名だけ（機械の中の長い場所は根拠欄の1行にだけ残す）。
    return path.resolve().as_uri(), path.name


def capture(spec: Mapping[str, Any], *, timeout_seconds: int = 25) -> ShotResult:
    """`spec` の先を撮って PNG のバイト列を返す。失敗しても例外は投げない。

    入れるもの＝`{"target"|"url"|"file", "viewport": [幅, 高さ], "selector", "full_page",
    "wait_ms", "scale"}`。⚠️`width` は貼るときの表示の上限（image と同じ）なので、
    撮る大きさは `viewport` で渡す（既定 1280×800）。
    返るもの＝ShotResult（png が None なら warnings に理由）。
    """
    raw = spec.get("target") or spec.get("url") or spec.get("file") or spec.get("path")
    url, label = resolve_target(raw)
    if url is None:
        return ShotResult(None, str(raw or ""), label, [label])
    viewport = spec.get("viewport")
    if isinstance(viewport, Mapping):
        vw, vh = viewport.get("width"), viewport.get("height")
    elif isinstance(viewport, (list, tuple)) and len(viewport) >= 2:
        vw, vh = viewport[0], viewport[1]
    else:
        vw, vh = None, None
    width = _int(vw, 1280, 320, 2560)
    height = _int(vh, 800, 240, 4000)
    scale = _int(spec.get("scale", 1), 1, 1, 2)
    wait_ms = _int(spec.get("wait_ms", 300), 300, 0, 10000)
    selector = str(spec.get("selector") or "").strip()
    full_page = bool(spec.get("full_page"))
    playwright_path, error = _resolve_playwright()
    if not playwright_path:
        return ShotResult(None, url, label, [error or "Playwright unavailable"])
    handle, out_path = tempfile.mkstemp(prefix="shot-", suffix=".png")
    os.close(handle)
    opts = {
        "width": width,
        "height": height,
        "scale": scale,
        "wait_ms": wait_ms,
        "selector": selector,
        "full_page": full_page,
        "timeout_ms": max(1000, (timeout_seconds - 3) * 1000),
    }
    try:
        completed = subprocess.run(
            ["node", "-e", NODE_SHOT_SCRIPT, playwright_path, url, out_path, json.dumps(opts)],
            text=True,
            encoding="utf-8",
            capture_output=True,
            timeout=max(5, int(timeout_seconds)),
            check=False,
            shell=False,
        )
        payload: dict = {}
        for line in reversed((completed.stdout or "").strip().splitlines()):
            try:
                payload = json.loads(line)
                break
            except json.JSONDecodeError:
                continue
        if not payload.get("ok"):
            reason = payload.get("error") or "撮影に失敗した（終了値 %s）" % completed.returncode
            return ShotResult(None, url, label, [str(reason)])
        data = Path(out_path).read_bytes()
        if not data:
            return ShotResult(None, url, label, ["撮影したファイルが空"])
        detail = "幅%dpx" % width + ("・%s" % selector if selector else "") + ("・頁全体" if full_page else "")
        place = str(Path(str(raw)).resolve()) if not urlparse(str(raw)).scheme or len(urlparse(str(raw)).scheme) == 1 else schemeless(url)
        return ShotResult(data, url, label + "（" + detail + "）", [], place)
    except subprocess.TimeoutExpired:
        return ShotResult(None, url, label, ["撮影が時間切れ"])
    except OSError as exc:
        return ShotResult(None, url, label, ["撮影の道具を起動できない：%s" % exc])
    finally:
        try:
            os.remove(out_path)
        except OSError:
            pass

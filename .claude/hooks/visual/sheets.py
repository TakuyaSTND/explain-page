"""回答集めのシート（赤ペン akapen・尋問 grilling-viz）の見分けと、回の中での探索。

2026-10-08 ユーザー裁定＝2026-09-01 の裁定（尋問の回答集めだけの回でも報告の頁を要求する）を
**反転した**。シートだけの回は、Stop で差し戻さない。
⚠️理由＝シートは「人に答えてもらうための入力票」で、部品の目印（data-component）を持たない
  のが正しい形。それを検品に掛けても落ちるだけで、報告の頁を足す動機にならなかった
  （実測：赤ペンの標準シートを置き場の中に Write すると、外部のURLの判定で検品証が作れず、
  どの回も [receipt_missing] で差し戻されていた）。

このモジュールの役目は2つだけ。
  1. HTMLの文字列／ファイルが回答集めのシートか見分ける（answer_sheet_kind*）
  2. 回の開始時刻より後に承認済みの置き場へ書かれたシートを探す（sheets_written_since）
     ＝シェルで書いたシートは PostToolUse が見ない（matcher に Bash が無い）ので、
       停止の時点でファイルの側から探す。

⚠️判定は「印がある」かつ「レンダラーの印（data-component）が無い」。印は部分文字列の
  一致だけで見る（正規表現は使わない）。取りこぼしは「免除しない」側に倒れるだけで、
  従来どおり差し戻す（fail-closed）。
⚠️例外は外へ投げない。読めない・探せないときは None／空タプル＝免除しない。
"""
from __future__ import annotations

import os
import time
from pathlib import Path

# 赤ペン（akapen）の3モードの印。標準＝先頭の版コメント／3モード共通の回答文の頭／指摘＝body の属性。
AKAPEN_MARKERS = ("<!-- akapen-format: v3 -->", "【赤ペン回答】", "<body data-shiteki=")
# 尋問の回答集め（grilling-viz）の印。⚠️両方が要る（片方だけなら別の頁の引用かもしれない）。
GV_MARKERS = ('<body class="gv"', 'id="gv-data"')
# レンダラーの頁には必ずある印。これがある頁はシート扱いしない（報告の頁として検品を受ける）。
RENDERER_MARK = 'data-component="'

KIND_AKAPEN = "akapen"
KIND_GRILLING_VIZ = "grilling-viz"

# 探索で降りないフォルダ。承認済みの置き場の中の、回の印と作業用の入れ物。
_SKIP_DIRS = frozenset({"current-turn", "__pycache__", "node_modules", ".git"})


def answer_sheet_kind(text: str) -> str | None:
    """HTMLの文字列が回答集めのシートなら "akapen" か "grilling-viz"、そうでなければ None。

    入れるもの＝HTMLの全文。返るもの＝種類か None。
    ⚠️レンダラーの印（data-component）があれば、印があっても None
      ＝赤ペンの回答文を本文に引用した報告の頁を、シートと取り違えない。
    """
    if not isinstance(text, str) or not text:
        return None
    if RENDERER_MARK in text:
        return None
    for marker in AKAPEN_MARKERS:
        if marker in text:
            return KIND_AKAPEN
    if all(marker in text for marker in GV_MARKERS):
        return KIND_GRILLING_VIZ
    return None


def _read_for_classification(path: Path, max_bytes: int) -> str | None:
    """先頭と（大きいときは）末尾だけを読んで文字列にする。読めなければ None。

    ⚠️添削モードのシートは記事の全文を抱えるので、回答文の印が後ろにあることがある。
      先頭だけでは見逃す＝大きいファイルは末尾も読む。中ほどだけにある印は見ない
      （見逃しは免除しない側に倒れる）。
    """
    try:
        size = path.stat().st_size
        with open(path, "rb") as handle:
            head = handle.read(max_bytes)
            tail = b""
            if size > max_bytes:
                handle.seek(max(max_bytes, size - max_bytes))
                tail = handle.read(max_bytes)
    except (OSError, ValueError):
        return None
    return (head + b"\n" + tail).decode("utf-8", errors="replace")


def answer_sheet_kind_of_path(path: object, *, max_bytes: int = 400_000) -> str | None:
    """ファイルが回答集めのシートなら種類、そうでなければ（読めない場合も）None。"""
    try:
        candidate = Path(str(path))
        if candidate.suffix.lower() != ".html" or not candidate.is_file():
            return None
    except (OSError, ValueError, TypeError):
        return None
    text = _read_for_classification(candidate, max(1, int(max_bytes)))
    if text is None:
        return None
    return answer_sheet_kind(text)


def is_under(path: object, root: object) -> bool:
    """path が root の中（root 自身を含む）にあるか。実在の別名（symlink・大文字小文字）を畳んで比べる。"""
    try:
        target = os.path.normcase(os.path.realpath(os.path.abspath(str(path))))
        base = os.path.normcase(os.path.realpath(os.path.abspath(str(root))))
        return os.path.commonpath((target, base)) == base
    except (OSError, ValueError, TypeError):
        return False


def sheets_written_since(
    root: object,
    since: float,
    *,
    tolerance: float = 2.0,
    max_depth: int = 3,
    max_bytes: int = 400_000,
    max_files: int = 200,
    budget_seconds: float = 3.0,
) -> tuple[tuple[str, str], ...]:
    """root の下で since（回の開始時刻）より後に書かれた回答集めのシートを (path, kind) で返す。新しい順。

    入れるもの＝承認済みの置き場・回の開始時刻（epoch 秒）。返るもの＝見つかったシートの並び（無ければ空）。
    探索＝os.scandir で .html だけ。更新時刻が since - tolerance 以上のものだけ読む
    （tolerance は時計とファイルシステムの粒度のずれの余裕）。降りる深さは max_depth まで、
    current-turn などの入れ物は飛ばす。読む件数と時間に上限を置く（停止フックの待ち時間は15秒）。
    ⚠️例外は外へ投げない。途中で諦めた分は「見つからなかった」と同じ＝免除しない側に倒れる。
    """
    try:
        threshold = float(since) - float(tolerance)
        base = str(root)
    except (TypeError, ValueError):
        return ()
    deadline = time.monotonic() + float(budget_seconds)
    found: list[tuple[float, str, str]] = []
    state = {"read": 0}

    def walk(directory: str, depth: int) -> None:
        try:
            with os.scandir(directory) as iterator:
                entries = list(iterator)
        except OSError:
            return
        for entry in entries:
            if time.monotonic() > deadline or state["read"] >= max_files:
                return
            try:
                if entry.is_dir(follow_symlinks=False):
                    if depth < max_depth and entry.name not in _SKIP_DIRS:
                        walk(entry.path, depth + 1)
                    continue
                if not entry.name.lower().endswith(".html"):
                    continue
                modified = entry.stat().st_mtime
                if modified < threshold:
                    continue
            except OSError:
                continue
            state["read"] += 1
            kind = answer_sheet_kind_of_path(entry.path, max_bytes=max_bytes)
            if kind:
                found.append((modified, entry.path, kind))

    try:
        walk(base, 0)
    except Exception:  # 探索の失敗で停止フックを落とさない
        return ()
    found.sort(key=lambda item: item[0], reverse=True)
    return tuple((path, kind) for _, path, kind in found)

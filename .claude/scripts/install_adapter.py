#!/usr/bin/env python3
"""explain-page を Codex／Hermes（どちらも試験的）へ配線する道具。

正本は開発元リポジトリの `.claude/public/install_adapter.py`。
書き出し先では `.claude/scripts/install_adapter.py` として配る。

やること＝ `.claude/hooks/adapters/` にある雛形（`{{EXPLAIN_PAGE_ROOT}}` /
`{{PROJECT_ROOT}}` / `{{PYTHON}}` というプレースホルダを含む）を、この道具が
走っている場所（explain-page 自身の置き場）と、指定したプロジェクトの根で
埋める。

使い方:
  python .claude/scripts/install_adapter.py --runtime codex  --project-root P [--write]
  python .claude/scripts/install_adapter.py --runtime hermes --project-root P

  --runtime codex  … `<P>/.codex/hooks.json` に書く配線。既定（--write を
                     付けない）ではプレビューを標準出力に出すだけで書かない。
                     `--write` を付けると書き込む。ただし `<P>/.codex/hooks.json`
                     が既にあり中身が違えば、**上書きせず**差分を出して止める
                     （終了値1）。中身が同じなら何もせず終了値0。
  --runtime hermes … 埋めた YAML を標準出力に出すだけ（Hermesの設定は
                     `%LOCALAPPDATA%/Hermes/config.yaml` 等、環境ごとに置き場が
                     違うため、この道具はファイルを書かない）。貼る先を
                     案内する1行を添える。

プレースホルダの埋め方:
  {{EXPLAIN_PAGE_ROOT}} … この道具の置き場（explain-page の根。python
                          スクリプト自身の場所から2つ上の親で決める）。
  {{PROJECT_ROOT}}      … `--project-root` で渡した値（説明の対象にするプロジェクト）。
  {{PYTHON}}            … `sys.executable`（python/python3 の揺れを避けるため、
                          呼び出し時のインタプリタの絶対pathをそのまま埋める）。
  どれも Windows でも `/` 区切りにする（シェルの引用・バックスラッシュの
  食い違いを避けるため）。
"""
from __future__ import annotations

import argparse
import io
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
CLAUDE_DIR = os.path.dirname(HERE)
EXPLAIN_PAGE_ROOT = os.path.dirname(CLAUDE_DIR)
ADAPTERS_DIR = os.path.join(CLAUDE_DIR, "hooks", "adapters")

CODEX_FRAGMENT = os.path.join(ADAPTERS_DIR, "codex-hooks.fragment.json")
HERMES_FRAGMENT = os.path.join(ADAPTERS_DIR, "hermes-hooks.fragment.yaml")


def _to_slash(path: str) -> str:
    return path.replace("\\", "/")


def _read_text(path: str) -> str:
    handle = io.open(path, encoding="utf-8")
    try:
        return handle.read()
    finally:
        handle.close()


def _write_text(path: str, text: str) -> None:
    parent = os.path.dirname(path)
    if parent and not os.path.isdir(parent):
        os.makedirs(parent)
    # このリポジトリの決まり＝ソースの書き戻しはバイナリ・改行はNL固定。
    handle = io.open(path, "wb")
    try:
        handle.write(text.encode("utf-8"))
    finally:
        handle.close()


def fill_template(text: str, project_root: str) -> str:
    """雛形の3つのプレースホルダを埋める。"""
    filled = text.replace("{{EXPLAIN_PAGE_ROOT}}", _to_slash(EXPLAIN_PAGE_ROOT))
    filled = filled.replace("{{PROJECT_ROOT}}", _to_slash(os.path.abspath(project_root)))
    filled = filled.replace("{{PYTHON}}", _to_slash(sys.executable))
    return filled


def _install_codex(project_root: str, write: bool) -> int:
    if not os.path.isfile(CODEX_FRAGMENT):
        print("雛形が無い: " + CODEX_FRAGMENT)
        return 1
    filled = fill_template(_read_text(CODEX_FRAGMENT), project_root)
    dest = os.path.join(os.path.abspath(project_root), ".codex", "hooks.json")
    if not write:
        print(filled)
        print("")
        print("ⓘ プレビューのみ（--write を付けると書く先）: " + dest)
        return 0
    if os.path.isfile(dest):
        existing = _read_text(dest)
        if existing == filled:
            print("一致: 既にこの内容で書かれている: " + dest)
            return 0
        print("ずれている＝上書きしない: " + dest)
        print("--- 既存 ---")
        print(existing)
        print("--- 新しい内容 ---")
        print(filled)
        return 1
    _write_text(dest, filled)
    print("書いた: " + dest)
    return 0


def _install_hermes(project_root: str) -> int:
    if not os.path.isfile(HERMES_FRAGMENT):
        print("雛形が無い: " + HERMES_FRAGMENT)
        return 1
    filled = fill_template(_read_text(HERMES_FRAGMENT), project_root)
    print(filled)
    print("")
    print("ⓘ Hermesの設定ファイル（例：%LOCALAPPDATA%/Hermes/config.yaml の")
    print("  skills.hooks 相当）へ、上の内容を貼ってください。この道具は")
    print("  Hermesの設定ファイルの置き場を決め打ちしないため、書き込みません。")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runtime", choices=("codex", "hermes"), required=True)
    parser.add_argument("--project-root", required=True)
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args(argv)
    if args.runtime == "codex":
        return _install_codex(args.project_root, args.write)
    return _install_hermes(args.project_root)


if __name__ == "__main__":
    if sys.platform == "win32":
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass
    raise SystemExit(main(sys.argv[1:]))

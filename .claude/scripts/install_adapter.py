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

利用者単位の配線（2026-09-28）:
  python .claude/scripts/install_adapter.py --runtime claude --scope user [--write | --remove]
  python .claude/scripts/install_adapter.py --runtime codex  --scope user [--write | --remove]
  python .claude/scripts/install_adapter.py --enable-project P [--mode auto|always] [--write]

  --scope user … その機械の利用者のすべての会話に効く設定へ、この置き場のフックを
                 `--shared` 付きで呼ぶ行を足す（Claude＝`~/.claude/settings.json` の
                 hooks、Codex＝`~/.codex/hooks.json`）。フックは会話の場所から上へ
                 `.claude/visual-hook-policy.json`（有効にする印）を探し、無ければ
                 何もしない。直接の配線があるリポジトリでも何もしない（二重を防ぐ）。
                 既定はプレビューだけ。`--write` で書く（元のファイルは
                 `<名前>.bak-explain-page` に控える）。既にこの置き場の行があれば何もしない。
                 `--remove` はこの道具が足した行だけを取り除く（控えを取ってから）。
  --enable-project P … P の `.claude/` に有効にする印（この置き場の印を写し、
                 explain_mode を `--mode` の値＝既定 auto にしたもの）と、用語集の雛形を
                 置く。既にあるファイルは上書きしない。既定はプレビューだけ。
  {{BASH}} … Windows の Codex が使う Git Bash の場所（見つからなければ `bash`）。
"""
from __future__ import annotations

import argparse
import copy
import io
import json
import os
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
CLAUDE_DIR = os.path.dirname(HERE)
EXPLAIN_PAGE_ROOT = os.path.dirname(CLAUDE_DIR)
ADAPTERS_DIR = os.path.join(CLAUDE_DIR, "hooks", "adapters")

CODEX_FRAGMENT = os.path.join(ADAPTERS_DIR, "codex-hooks.fragment.json")
HERMES_FRAGMENT = os.path.join(ADAPTERS_DIR, "hermes-hooks.fragment.yaml")
CLAUDE_USER_FRAGMENT = os.path.join(ADAPTERS_DIR, "claude-user-settings.fragment.json")
CODEX_USER_FRAGMENT = os.path.join(ADAPTERS_DIR, "codex-user-hooks.fragment.json")
BACKUP_SUFFIX = ".bak-explain-page"
GIT_BASH_CANDIDATES = (
    "C:/Program Files/Git/bin/bash.exe",
    "C:/Program Files (x86)/Git/bin/bash.exe",
)


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


def _bash_path() -> str:
    for candidate in GIT_BASH_CANDIDATES:
        if os.path.isfile(candidate):
            return candidate
    found = shutil.which("bash")
    return _to_slash(found) if found else "bash"


def fill_user_template(text: str) -> str:
    """利用者単位の雛形のプレースホルダ（プロジェクトの根は無い）を埋める。"""
    filled = text.replace("{{EXPLAIN_PAGE_ROOT}}", _to_slash(EXPLAIN_PAGE_ROOT))
    filled = filled.replace("{{PYTHON}}", _to_slash(sys.executable))
    filled = filled.replace("{{BASH}}", _bash_path())
    return filled


def _composer_path() -> str:
    return _to_slash(EXPLAIN_PAGE_ROOT) + "/.claude/hooks/understanding-composer.py"


def _is_ours(group: object) -> bool:
    """このフック群が、この置き場のフックを --shared で呼ぶ行か。"""
    text = json.dumps(group, ensure_ascii=False)
    return _composer_path() in text and "--shared" in text


def merge_user_hooks(existing: dict, fragment: dict) -> tuple[dict, list[str]]:
    """既存の設定に雛形のフックを足した設定と、足した出来事の名前を返す。

    既にこの置き場の行がある出来事には足さない（何度走らせても同じ結果になる）。
    ほかの設定（hooks 以外の欄・ほかのフック）には触らない。
    """
    merged = copy.deepcopy(existing)
    hooks = merged.get("hooks")
    if hooks is None or hooks == []:
        hooks = {}
        merged["hooks"] = hooks
    if not isinstance(hooks, dict):
        raise ValueError("hooks is not an object")
    added = []
    for event, groups in fragment.get("hooks", {}).items():
        current = hooks.get(event)
        if current is None:
            current = []
            hooks[event] = current
        if not isinstance(current, list):
            raise ValueError("hooks." + event + " is not a list")
        if any(_is_ours(group) for group in current):
            continue
        current.extend(copy.deepcopy(groups))
        added.append(event)
    return merged, added


def remove_user_hooks(existing: dict) -> tuple[dict, list[str]]:
    """この道具が足した行だけを取り除いた設定と、取り除いた出来事の名前を返す。"""
    merged = copy.deepcopy(existing)
    hooks = merged.get("hooks")
    removed = []
    if not isinstance(hooks, dict):
        return merged, removed
    for event in list(hooks.keys()):
        current = hooks[event]
        if not isinstance(current, list):
            continue
        kept = [group for group in current if not _is_ours(group)]
        if len(kept) != len(current):
            removed.append(event)
            if kept:
                hooks[event] = kept
            else:
                del hooks[event]
    return merged, removed


def _user_dest(runtime: str, home: str) -> str:
    if runtime == "claude":
        return os.path.join(home, ".claude", "settings.json")
    return os.path.join(home, ".codex", "hooks.json")


def _dump_json(data: dict) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2) + "\n"


def _backup(dest: str) -> str:
    backup = dest + BACKUP_SUFFIX
    number = 2
    while os.path.exists(backup):
        backup = dest + BACKUP_SUFFIX + "-" + str(number)
        number += 1
    shutil.copyfile(dest, backup)
    return backup


def _install_user(runtime: str, home: str, write: bool, remove: bool) -> int:
    fragment_path = CLAUDE_USER_FRAGMENT if runtime == "claude" else CODEX_USER_FRAGMENT
    if not os.path.isfile(fragment_path):
        print("雛形が無い: " + fragment_path)
        return 1
    dest = _user_dest(runtime, home)
    existing: dict = {}
    if os.path.isfile(dest):
        try:
            loaded = json.loads(_read_text(dest) or "{}")
        except ValueError as exc:
            print("読めない（JSON ではない）＝書かない: " + dest + " (" + str(exc) + ")")
            return 1
        if not isinstance(loaded, dict):
            print("形が違う（JSON の物ではない）＝書かない: " + dest)
            return 1
        existing = loaded
    if remove:
        merged, changed = remove_user_hooks(existing)
        verb = "取り除く"
    else:
        fragment = json.loads(fill_user_template(_read_text(fragment_path)))
        try:
            merged, changed = merge_user_hooks(existing, fragment)
        except ValueError as exc:
            print("既存の hooks の形が想定と違う＝書かない: " + dest + " (" + str(exc) + ")")
            return 1
        verb = "足す"
    if not changed:
        print("変更なし（" + verb + "ものが無い）: " + dest)
        return 0
    print(_dump_json(merged), end="")
    print("")
    print("ⓘ " + verb + "出来事: " + ", ".join(changed))
    if not write:
        print("ⓘ プレビューのみ（--write を付けると書く先）: " + dest)
        if os.path.isfile(dest):
            print("ⓘ 書くときは元のファイルを控える: " + dest + BACKUP_SUFFIX)
        return 0
    if os.path.isfile(dest):
        print("控えた: " + _backup(dest))
    _write_text(dest, _dump_json(merged))
    print("書いた: " + dest)
    return 0


def _enable_project(project_root: str, mode: str, write: bool) -> int:
    base_policy = os.path.join(CLAUDE_DIR, "visual-hook-policy.json")
    if not os.path.isfile(base_policy):
        print("元にする印が無い: " + base_policy)
        return 1
    policy = json.loads(_read_text(base_policy))
    policy["explain_mode"] = mode
    claude_dir = os.path.join(os.path.abspath(project_root), ".claude")
    plan = (
        (os.path.join(claude_dir, "visual-hook-policy.json"), _dump_json(policy)),
    )
    glossary_src = os.path.join(CLAUDE_DIR, "glossary.md")
    if os.path.isfile(glossary_src):
        plan = plan + ((os.path.join(claude_dir, "glossary.md"), _read_text(glossary_src)),)
    for dest, text in plan:
        if os.path.isfile(dest):
            print("既にある（変更しない）: " + dest)
            continue
        if not write:
            print("書く予定: " + dest)
            continue
        _write_text(dest, text)
        print("書いた: " + dest)
    if not write:
        print("ⓘ プレビューのみ（--write を付けると書く）。explain_mode=" + mode)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runtime", choices=("codex", "hermes", "claude"))
    parser.add_argument("--scope", choices=("project", "user"), default="project")
    parser.add_argument("--project-root")
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--remove", action="store_true")
    parser.add_argument("--home", default=os.path.expanduser("~"))
    parser.add_argument("--enable-project")
    parser.add_argument("--mode", choices=("auto", "always"), default="auto")
    args = parser.parse_args(argv)
    if args.enable_project:
        return _enable_project(args.enable_project, args.mode, args.write)
    if not args.runtime:
        parser.error("--runtime or --enable-project is required")
    if args.scope == "user":
        if args.runtime == "hermes":
            parser.error("--scope user supports claude and codex only")
        return _install_user(args.runtime, args.home, args.write, args.remove)
    if args.runtime == "claude":
        parser.error("--runtime claude needs --scope user")
    if not args.project_root:
        parser.error("--project-root is required for --scope project")
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

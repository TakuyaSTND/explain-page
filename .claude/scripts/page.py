#!/usr/bin/env python3
"""頁の仕組みを、どのエージェント（Claude Code・Codex・Hermes）からも同じ形で使う共通の命令。

標準ライブラリだけで動く。結果は表で出し、成否を終了値でも返す（0＝成功・1＝失敗・2＝使い方の誤り）。

使い方:
  python page.py status [--project-root P]
      いまのリポジトリで頁の仕組みが効くか（有効にする印・配線・モード）を表で答える。何も書かない。
  python page.py check <頁.html> [--components a,b,...] [--project-root P]
      頁を検査する（部品・用語・根拠の出所・実ブラウザでの表示）。表示検査は Playwright が要る。
  python page.py enable [P] [--mode auto|always] [--write]
      リポジトリ P（省くと今の場所）に「有効にする印」を置く。既定は内容を見せるだけで、--write で書く。
  python page.py install [--write] [--home H]
      利用者単位に、スキル explain-page（Claude Code と Codex）と、Claude の近道コマンド
      （page-status・page-check・page-enable）を置く。既定は内容を見せるだけ。

頁を組む命令は render_page.py（雛形は --scaffold）。この命令は判定の基準を持たず、既存の道具を呼ぶだけ。
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
CLAUDE_DIR = os.path.dirname(HERE)
NL = chr(10)
POLICY_REL = os.path.join(".claude", "visual-hook-policy.json")
HOOK_MARK = "understanding-composer"


def _utf8_out():
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except Exception:
            pass


def _read(path):
    try:
        return io.open(path, encoding="utf-8", errors="replace").read()
    except OSError:
        return ""


def _find_project_root(start=None):
    """今の場所から上へ、有効にする印（visual-hook-policy.json）を探す。無ければ None。"""
    env_root = os.environ.get("CLAUDE_PROJECT_DIR")
    if not start and env_root and os.path.isfile(os.path.join(env_root, POLICY_REL)):
        return os.path.abspath(env_root)
    current = os.path.abspath(start or os.getcwd())
    while True:
        if os.path.isfile(os.path.join(current, POLICY_REL)):
            return current
        parent = os.path.dirname(current)
        if parent == current:
            return None
        current = parent


def _runtime_guess():
    if os.environ.get("CODEX_SESSION_ID") or os.environ.get("CODEX_THREAD_ID"):
        return "codex"
    if os.environ.get("CLAUDECODE") or os.environ.get("CLAUDE_PROJECT_DIR"):
        return "claude"
    return "不明（端末から直接）"


def _table(rows, head=("項目", "状態")):
    width = max([len(head[0])] + [len(str(r[0])) for r in rows])
    lines = ["%s  %s" % (head[0].ljust(width), head[1]), "%s  %s" % ("-" * width, "-" * 20)]
    for key, value in rows:
        lines.append("%s  %s" % (str(key).ljust(width), value))
    return NL.join(lines)


def _wired(path):
    return HOOK_MARK in _read(path)


def cmd_status(args):
    start = args.project_root
    root = _find_project_root(start)
    user_claude = _wired(os.path.join(os.path.expanduser("~"), ".claude", "settings.json"))
    user_codex = _wired(os.path.join(os.path.expanduser("~"), ".codex", "hooks.json"))
    rows = [("この道具の置き場", CLAUDE_DIR.replace(os.sep, "/")), ("いまのエージェント", _runtime_guess())]
    effective = False
    if root is None:
        rows.append(("有効にする印", "無い（上のフォルダにも無い）＝頁の仕組みは動かない"))
        rows.append(("有効にするには", "python %s enable <リポジトリ> --write" % os.path.join(HERE, "page.py").replace(os.sep, "/")))
    else:
        try:
            policy = json.loads(_read(os.path.join(root, POLICY_REL)) or "{}")
        except ValueError:
            policy = {}
        mode = policy.get("explain_mode", "（不明）")
        rows.append(("有効にする印", "ある＝%s" % root.replace(os.sep, "/")))
        rows.append(("モード", "%s（always＝毎回頁を要求・auto＝頁が要る場面だけ）／公開 %s／読み手 %s／深さ %s" % (
            mode, policy.get("publish", "?"), policy.get("default_audience", "?"), policy.get("default_depth", "?"))))
        direct_claude = _wired(os.path.join(root, ".claude", "settings.json")) or _wired(os.path.join(root, ".claude", "settings.local.json"))
        direct_codex = _wired(os.path.join(root, ".codex", "hooks.json"))
        rows.append(("このリポジトリの直接の配線", "Claude %s／Codex %s" % ("あり" if direct_claude else "なし", "あり" if direct_codex else "なし")))
        effective = direct_claude or direct_codex or user_claude or user_codex
    rows.append(("利用者単位の配線", "Claude %s／Codex %s" % ("あり" if user_claude else "なし", "あり" if user_codex else "なし")))
    if root is not None:
        rows.append(("結論", "頁の仕組みは効く" if effective else "印はあるが配線が無い＝動かない"))
    print(_table(rows))
    return 0


def cmd_check(args):
    path = os.path.abspath(args.html)
    if not os.path.isfile(path):
        print("頁が見つからない: %s" % path, file=sys.stderr)
        return 2
    if HERE not in sys.path:
        sys.path.insert(0, HERE)
    try:
        import render_page as rp
    except Exception as error:  # noqa: BLE001
        print("render_page.py を読み込めない: %s" % error, file=sys.stderr)
        return 2
    components = [c for c in (args.components or "").split(",") if c] or list(rp.ALL_COMPONENTS)
    root = args.project_root or _find_project_root() or None
    result = rp.check(path, components, root)
    gloss = os.path.join(HERE, "check_gloss.py")
    gloss_code = "（check_gloss.py が無い）"
    if os.path.isfile(gloss):
        run = subprocess.run([sys.executable, gloss, path, "--strict"], capture_output=True, text=True, encoding="utf-8", errors="replace")
        gloss_code = "合格" if run.returncode == 0 else "不一致あり（終了値 %d）" % run.returncode
    ok = bool(result.get("ok"))
    rows = [
        ("頁", path.replace(os.sep, "/")),
        ("大きさ", "%d バイト" % result.get("bytes", 0)),
        ("総合", "合格" if ok else "不合格"),
        ("部品・用語・根拠の検査", "合格" if result.get("inspection_ok") else "不合格"),
        ("足りない部品", ",".join(result.get("missing_components") or []) or "なし"),
        ("未包装の識別子", ",".join(result.get("unwrapped") or []) or "なし"),
        ("出所の無い根拠", ",".join(map(str, result.get("missing_sources") or [])) or "なし"),
        ("表示検査", result.get("smoke", "?")),
        ("外部の依存", ",".join(result.get("external_dependency") or []) or "なし"),
        ("用語集との一致", gloss_code),
        ("頁の高さ", "%s px" % result.get("page_height", "?")),
    ]
    print(_table(rows, ("検査", "結果")))
    for message in (result.get("smoke_errors") or []) + (result.get("errors") or []):
        print("  - %s" % message)
    if result.get("smoke") != "pass":
        print("表示検査が通らない。Playwright が無い環境では、次で入れる: npx -y playwright install chromium")
    return 0 if ok and gloss_code == "合格" else 1


def _adapter_path():
    for candidate in (os.path.join(HERE, "install_adapter.py"), os.path.join(CLAUDE_DIR, "public", "install_adapter.py")):
        if os.path.isfile(candidate):
            return candidate
    return None


def cmd_enable(args):
    adapter = _adapter_path()
    if adapter is None:
        print("install_adapter.py が見つからない", file=sys.stderr)
        return 2
    target = os.path.abspath(args.project or os.getcwd())
    command = [sys.executable, adapter, "--enable-project", target, "--mode", args.mode]
    if args.write:
        command.append("--write")
    else:
        print("（書き込まずに内容だけ見せる。書くには --write）")
    return subprocess.run(command).returncode


SKILL_TEXT = """---
name: explain-page
description: 説明・報告・判断の HTML 頁の仕組み（explain-page）を、いまのリポジトリで使えるか確かめる、頁を検査する、リポジトリで有効にする。「頁の仕組みは効いているか」「この頁を点検して」「このリポジトリで頁を有効にして」と頼まれたときに使う。
---

# explain-page

頁の仕組みの道具は、端末から打つ共通の命令 `page.py` に集めてある。このスキルは呼び方だけを書き、判定の基準は持たない。

命令の場所: `{PAGE_PY}`
Python: `{PYTHON}`

## 呼び方

- 効いているか確かめる: `{PYTHON} {PAGE_PY} status`
- 頁を検査する: `{PYTHON} {PAGE_PY} check <頁.html>`（表示検査は Playwright が要る）
- リポジトリで有効にする: まず `{PYTHON} {PAGE_PY} enable <リポジトリ>` で内容を見せ、利用者の了承を得てから `--write` を付ける。他のリポジトリの設定ファイルを書き換えるので、了承なしに `--write` を付けない。

## 決まり

- 結果の表をそのまま利用者に見せる。表に無いことを断定しない。
- 頁を組むのは `render_page.py`（`{PAGE_DIR}`）。頁は手書きしない。
- 終了値 0 は成功、1 は失敗、2 は使い方の誤り。
"""

COMMAND_TEXT = {
    "page-status": ("頁の仕組みがいまのリポジトリで効くかを表で見る", "", "status"),
    "page-check": ("頁を検査する（部品・用語・根拠・実ブラウザの表示）", "<頁.html>", "check"),
    "page-enable": ("リポジトリで頁の仕組みを有効にする（内容を見せてから、了承を得て書く）", "[リポジトリ] [--mode auto|always]", "enable"),
}


def _command_body(name):
    desc, hint, sub = COMMAND_TEXT[name]
    lines = ["---", "description: %s" % desc]
    if hint:
        lines.append("argument-hint: %s" % hint)
    lines += ["---", "",
              "次を端末で走らせ、結果の表をそのまま見せる。引数＝ $ARGUMENTS", "",
              "```", "{PYTHON} {PAGE_PY} %s $ARGUMENTS" % sub, "```", ""]
    if sub == "enable":
        lines.append("最初は `--write` を付けずに走らせ、内容を見せて了承を得てから `--write` を付けて走らせ直す。")
    lines.append("判定の基準はこの文書に書かない（道具が持つ）。")
    return NL.join(lines) + NL


def _fill(text):
    return (text.replace("{PYTHON}", sys.executable.replace(os.sep, "/"))
            .replace("{PAGE_PY}", os.path.join(HERE, "page.py").replace(os.sep, "/"))
            .replace("{PAGE_DIR}", HERE.replace(os.sep, "/")))


def _targets(home):
    items = [
        (os.path.join(home, ".claude", "skills", "explain-page", "SKILL.md"), _fill(SKILL_TEXT)),
        (os.path.join(home, ".agents", "skills", "explain-page", "SKILL.md"), _fill(SKILL_TEXT)),
    ]
    for name in COMMAND_TEXT:
        items.append((os.path.join(home, ".claude", "commands", name + ".md"), _fill(_command_body(name))))
    return items


def cmd_install(args):
    home = os.path.abspath(args.home or os.path.expanduser("~"))
    if not args.write:
        print("（書き込まずに内容だけ見せる。書くには --write）")
    changed = 0
    for path, text in _targets(home):
        old = _read(path) if os.path.isfile(path) else None
        shown = path.replace(os.sep, "/")
        if old == text:
            print("同じ内容なので何もしない: %s" % shown)
            continue
        verb = "新しく書く" if old is None else "書き換える（元は .bak-explain-page に控える）"
        print("%s: %s" % (verb, shown))
        changed += 1
        if not args.write:
            continue
        os.makedirs(os.path.dirname(path), exist_ok=True)
        if old is not None:
            io.open(path + ".bak-explain-page", "w", encoding="utf-8", newline=NL).write(old)
        io.open(path, "w", encoding="utf-8", newline=NL).write(text)
    print("変更 %d 件%s" % (changed, "（書いた）" if args.write else "（まだ書いていない）"))
    return 0


def main(argv=None):
    _utf8_out()
    parser = argparse.ArgumentParser(prog="page.py", description="頁の仕組みの共通の命令")
    sub = parser.add_subparsers(dest="command")
    p = sub.add_parser("status")
    p.add_argument("--project-root")
    p.set_defaults(func=cmd_status)
    p = sub.add_parser("check")
    p.add_argument("html")
    p.add_argument("--components")
    p.add_argument("--project-root")
    p.set_defaults(func=cmd_check)
    p = sub.add_parser("enable")
    p.add_argument("project", nargs="?")
    p.add_argument("--mode", choices=("auto", "always"), default="auto")
    p.add_argument("--write", action="store_true")
    p.set_defaults(func=cmd_enable)
    p = sub.add_parser("install")
    p.add_argument("--write", action="store_true")
    p.add_argument("--home")
    p.set_defaults(func=cmd_install)
    args = parser.parse_args(argv)
    if not getattr(args, "func", None):
        parser.print_help()
        return 2
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""このプロジェクトで explain-page プラグインを有効にする（生成物・2026-09-25）。

やること＝プラグイン同梱の雛形（templates/）を、このプロジェクトの `.claude/` へ写す。
既にあるファイルは上書きしない（プロジェクト固有の中身を壊さないため）。

使い方:
  python init_project.py [プロジェクトの根（既定＝今の作業フォルダ）]

写すもの:
  templates/visual-hook-policy.json -> <project>/.claude/visual-hook-policy.json
  templates/glossary.md             -> <project>/.claude/glossary.md
  templates/readability-rules.md    -> <project>/.claude/readability-rules.md

この道具を走らせただけでは効かない＝プラグインを有効にしても、そのプロジェクトの
`.claude/visual-hook-policy.json` が無い間は understanding-composer.py が
何もせず終了する（安全の掟）。この道具はその設定ファイルを置くためだけの道具である。
"""
import io
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PLUGIN_ROOT = os.path.dirname(HERE)
TEMPLATES = os.path.join(PLUGIN_ROOT, "templates")

FILES = (
    "visual-hook-policy.json",
    "glossary.md",
    "readability-rules.md",
)


def _copy_if_absent(name, claude_dir):
    src = os.path.join(TEMPLATES, name)
    dest = os.path.join(claude_dir, name)
    if os.path.isfile(dest):
        return "既にある（変更しない）: " + dest
    if not os.path.isfile(src):
        return "雛形が無い（見送り）: " + src
    handle_in = io.open(src, "rb")
    data = handle_in.read()
    handle_in.close()
    handle_out = io.open(dest, "wb")
    handle_out.write(data)
    handle_out.close()
    return "書いた: " + dest


def main(argv):
    project_root = argv[1] if len(argv) > 1 else os.getcwd()
    claude_dir = os.path.join(os.path.abspath(project_root), ".claude")
    if not os.path.isdir(claude_dir):
        os.makedirs(claude_dir)
    lines = []
    for name in FILES:
        lines.append(_copy_if_absent(name, claude_dir))
    print(os.linesep.join(lines))
    return 0


if __name__ == "__main__":
    if sys.platform == "win32":
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass
    raise SystemExit(main(sys.argv))


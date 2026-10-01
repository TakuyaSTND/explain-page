#!/usr/bin/env python3
"""説明の頁の仕組み（フック一式）を、Claude Codeのプラグインとして組み立てる道具
（2026-09-25 新設）。

なぜ要るか＝このリポジトリの `.claude/` にある仕組み（フック・レンダラー・用語集）を、
他のリポジトリでもそのまま使えるようにしたい。プラグインという配布の形にすれば、
`/plugin marketplace add` と `/plugin install` だけで他のリポジトリへ持ち出せる。

正本は `.claude/` のまま＝このスクリプトは正本から `plugins/<配布の名前>/` を
生成するだけで、同じ中身を手で二重に持たない。生成物がずれたら、まずこの道具を
もう一度走らせる（手で直さない）。配布の名前・作者・説明文などの固有の値は
`hooks/visual/branding.py` に集めてあり、このスクリプトはそこを参照するだけ
（2026-09-25）＝公開版の書き出しでは branding.py だけを差し替えれば済む。

使い方:
  PYTHONUTF8=1 python .claude/scripts/build_plugin.py           … 生成する
  PYTHONUTF8=1 python .claude/scripts/build_plugin.py --check   … 一致だけ検査する
                                                                  （終了値0=一致、
                                                                  1=ずれ。ずれた
                                                                  ファイル名を1行ずつ出す）
  PYTHONUTF8=1 python .claude/scripts/build_plugin.py --out DIR         … DIR を
      プラグインの根として、そこへだけ書き出す（marketplace.json には触れない。
      試験が一時フォルダへ生成するときに使う）
  PYTHONUTF8=1 python .claude/scripts/build_plugin.py --check --out DIR … DIR だけを
      正本と比べる

書いてよい場所＝ `<repo>/plugins/<配布の名前>/` と `<repo>/.claude-plugin/marketplace.json`
だけ（`--out` を指定した時は指定先）。正本の `.claude/` は読むだけで、書き換えない。
"""
import io
import json
import os
import shutil
import sys

NL = chr(10)
HERE = os.path.dirname(os.path.abspath(__file__))
CLAUDE_DIR = os.path.dirname(HERE)
REPO_ROOT = os.path.dirname(CLAUDE_DIR)

HOOKS_DIR = os.path.join(CLAUDE_DIR, "hooks")
if HOOKS_DIR not in sys.path:
    sys.path.insert(0, HOOKS_DIR)
from visual import branding  # noqa: E402

PLUGIN_REL = "plugins/" + branding.PRODUCT_NAME
PLUGIN_ROOT = os.path.join(REPO_ROOT, "plugins", branding.PRODUCT_NAME)
MARKETPLACE_REL = ".claude-plugin/marketplace.json"

PLUGIN_NAME = branding.PRODUCT_NAME
PLUGIN_DESCRIPTION = branding.PLUGIN_DESCRIPTION
MARKETPLACE_NAME = branding.MARKETPLACE_NAME
MARKETPLACE_OWNER = branding.AUTHOR_NAME

# 2026-09-25：入口は run-python.sh 経由（Macは python3、Windowsは python。
# PYTHONUTF8=1 は run-python.sh の中で付ける＝ここに複製しない）。
HOOK_COMMAND = (
    'sh "${CLAUDE_PLUGIN_ROOT}/hooks/run-python.sh"'
    ' "${CLAUDE_PLUGIN_ROOT}/hooks/understanding-composer.py"'
    ' --runtime claude --plugin --project-root "${CLAUDE_PROJECT_DIR}"'
)

# 正本からそのまま写す物（正本の相対path → プラグイン内の相対path）。
# ⚠️gloss_shared.py は入れない＝render_page.py が使っていない道具なので同梱しない。
COPY_FILES = (
    ("hooks/understanding-composer.py", "hooks/understanding-composer.py"),
    ("hooks/run-python.sh", "hooks/run-python.sh"),
    ("scripts/render_page.py", "scripts/render_page.py"),
    ("scripts/check_gloss.py", "scripts/check_gloss.py"),
    ("glossary-shared.md", "glossary-shared.md"),
    ("html-output.md", "html-output.md"),
    ("visual-hook-policy.json", "templates/visual-hook-policy.json"),
    ("readability-rules.md", "templates/readability-rules.md"),
)


def _visual_py_files():
    """`hooks/visual/` 直下の *.py を並べて返す（tests・__pycache__ は除外）。"""
    visual_dir = os.path.join(CLAUDE_DIR, "hooks", "visual")
    names = []
    for name in sorted(os.listdir(visual_dir)):
        full = os.path.join(visual_dir, name)
        if os.path.isfile(full) and name.endswith(".py"):
            names.append(name)
    return names


def _read_bytes(path):
    handle = io.open(path, "rb")
    try:
        return handle.read()
    finally:
        handle.close()


def _write_bytes(path, data):
    parent = os.path.dirname(path)
    if parent and not os.path.isdir(parent):
        os.makedirs(parent)
    handle = io.open(path, "wb")
    try:
        handle.write(data)
    finally:
        handle.close()


# ⚠️生成する文字列は1行ずつ NL.join で組む（この repo の決まり＝行またぎの文字列を
#   生成コードに書かない。書き戻しは open(path, 'wb') のバイナリ＝改行はNL固定）。
GLOSSARY_TEMPLATE_LINES = (
    "# 用語集（ホバー説明の言い回しの正本・プラグインの雛形）",
    "",
    "書式：`| 用語 | 平易な説明（1〜2文・専門語で説明しない） |`",
    "",
    "**ここに無い語を使ったら1行足す。** 足せば次回から自動で説明が付く。",
    "",
    "## このプロジェクト固有の用語",
    "",
    "| 用語 | 説明 |",
    "|---|---|",
    "",
)

INIT_PROJECT_PY_LINES = (
    "#!/usr/bin/env python3",
    '"""このプロジェクトで ' + PLUGIN_NAME + ' プラグインを有効にする（生成物・2026-09-25）。',
    "",
    "やること＝プラグイン同梱の雛形（templates/）を、このプロジェクトの `.claude/` へ写す。",
    "既にあるファイルは上書きしない（プロジェクト固有の中身を壊さないため）。",
    "",
    "使い方:",
    "  python init_project.py [プロジェクトの根（既定＝今の作業フォルダ）]",
    "",
    "写すもの:",
    "  templates/visual-hook-policy.json -> <project>/.claude/visual-hook-policy.json",
    "  templates/glossary.md             -> <project>/.claude/glossary.md",
    "  templates/readability-rules.md    -> <project>/.claude/readability-rules.md",
    "",
    "この道具を走らせただけでは効かない＝プラグインを有効にしても、そのプロジェクトの",
    "`.claude/visual-hook-policy.json` が無い間は understanding-composer.py が",
    "何もせず終了する（安全の掟）。この道具はその設定ファイルを置くためだけの道具である。",
    '"""',
    "import io",
    "import os",
    "import sys",
    "",
    "HERE = os.path.dirname(os.path.abspath(__file__))",
    "PLUGIN_ROOT = os.path.dirname(HERE)",
    'TEMPLATES = os.path.join(PLUGIN_ROOT, "templates")',
    "",
    "FILES = (",
    '    "visual-hook-policy.json",',
    '    "glossary.md",',
    '    "readability-rules.md",',
    ")",
    "",
    "",
    "def _copy_if_absent(name, claude_dir):",
    "    src = os.path.join(TEMPLATES, name)",
    "    dest = os.path.join(claude_dir, name)",
    "    if os.path.isfile(dest):",
    '        return "既にある（変更しない）: " + dest',
    "    if not os.path.isfile(src):",
    '        return "雛形が無い（見送り）: " + src',
    '    handle_in = io.open(src, "rb")',
    "    data = handle_in.read()",
    "    handle_in.close()",
    '    handle_out = io.open(dest, "wb")',
    "    handle_out.write(data)",
    "    handle_out.close()",
    '    return "書いた: " + dest',
    "",
    "",
    "def main(argv):",
    "    project_root = argv[1] if len(argv) > 1 else os.getcwd()",
    '    claude_dir = os.path.join(os.path.abspath(project_root), ".claude")',
    "    if not os.path.isdir(claude_dir):",
    "        os.makedirs(claude_dir)",
    "    lines = []",
    "    for name in FILES:",
    "        lines.append(_copy_if_absent(name, claude_dir))",
    "    print(os.linesep.join(lines))",
    "    return 0",
    "",
    "",
    'if __name__ == "__main__":',
    '    if sys.platform == "win32":',
    "        try:",
    "            sys.stdout.reconfigure(encoding=\"utf-8\")",
    "        except Exception:",
    "            pass",
    "    raise SystemExit(main(sys.argv))",
    "",
)

README_LINES = (
    "# " + PLUGIN_NAME,
    "",
    "人に見せる頁（説明・報告・判断のHTML）を、正規レンダラーで組んで検品まで通す",
    "フック一式のプラグイン版。正本は `" + branding.REPO_SLUG + "` リポジトリの `.claude/`",
    "（このプラグインは `.claude/scripts/build_plugin.py` がそこから生成した写し）。",
    "",
    "## 入れ方",
    "",
    "1. `/plugin marketplace add <このリポジトリのpathまたはURL>`",
    "2. `/plugin install " + PLUGIN_NAME + "@" + MARKETPLACE_NAME + "`",
    "",
    "## 有効にする",
    "",
    "プラグインを入れただけでは何も起きない（安全の掟①）。使いたいプロジェクトの根で",
    "次を走らせ、そのプロジェクトの `.claude/` へ設定と雛形を置く。",
    "",
    "```",
    "python <プラグインの場所>/scripts/init_project.py <プロジェクトの根>",
    "```",
    "",
    "既にあるファイルは上書きしない。`.claude/visual-hook-policy.json` が置かれた",
    "プロジェクトでだけ、このプラグインのフックが動き出す。",
    "",
    "## 安全の掟",
    "",
    "- そのプロジェクトに `.claude/visual-hook-policy.json` が無ければ、フックは",
    "  何もせず終了する（関係ないリポジトリに影響しない）。",
    "- そのプロジェクトの `.claude/settings.json` か `.claude/settings.local.json` に",
    "  この仕組みを直接呼ぶ配線が既にあれば、プラグイン側は何もせず終了する",
    "  （プラグインのフックと直接書いたフックは両方走るため、二重発火を防ぐ）。",
    "- 共通の用語集（`glossary-shared.md`）と読みやすさ規則（`readability-rules.md`）は、",
    "  プロジェクト側に無ければプラグイン同梱の控え・雛形を使う。",
    "",
    "## Codexについて",
    "",
    "このプラグインは Claude Code 専用。Codex では対象外＝`codex-build/` 側の",
    "雛形（overlay等）を使うこと。",
    "",
)


def _generated_plugin_files():
    """返すもの＝{プラグイン内の相対path: bytes}（コピー＋生成の両方）。"""
    files = {}
    for src_rel, dest_rel in COPY_FILES:
        src_path = os.path.join(CLAUDE_DIR, *src_rel.split("/"))
        files[dest_rel] = _read_bytes(src_path)
    for name in _visual_py_files():
        src_path = os.path.join(CLAUDE_DIR, "hooks", "visual", name)
        files["hooks/visual/" + name] = _read_bytes(src_path)
    files["templates/glossary.md"] = (NL.join(GLOSSARY_TEMPLATE_LINES) + NL).encode("utf-8")
    files["scripts/init_project.py"] = (NL.join(INIT_PROJECT_PY_LINES) + NL).encode("utf-8")
    files["hooks/hooks.json"] = _hooks_json_bytes()
    files[".claude-plugin/plugin.json"] = _plugin_json_bytes()
    files["README.md"] = (NL.join(README_LINES) + NL).encode("utf-8")
    return files


def _hook_entry(status_message, timeout=15, matcher=None):
    entry = {}
    if matcher is not None:
        entry["matcher"] = matcher
    entry["hooks"] = [
        {
            "type": "command",
            "command": HOOK_COMMAND,
            "timeout": timeout,
            "statusMessage": status_message,
        }
    ]
    return entry


def _hooks_json_bytes():
    data = {
        "hooks": {
            "UserPromptSubmit": [_hook_entry("初心者向けの説明構成を準備する")],
            "PostToolUse": [
                _hook_entry(
                    "local HTMLの検品証を記録する",
                    matcher="Write|Edit|Artifact|open_preview",
                )
            ],
            "SubagentStop": [_hook_entry("subagent結果を親向けに集約する")],
            "Stop": [_hook_entry("説明componentの不足を確認する")],
            "StopFailure": [
                _hook_entry(
                    "APIエラーの診断を表示する",
                    matcher=(
                        "rate_limit|overloaded|authentication_failed|"
                        "oauth_org_not_allowed|billing_error|invalid_request|"
                        "model_not_found|server_error|max_output_tokens|unknown"
                    ),
                )
            ],
        }
    }
    text = json.dumps(data, ensure_ascii=False, indent=2) + NL
    return text.encode("utf-8")


def _plugin_json_bytes():
    # 2026-10-01（利用者の選択）：version を書かない。Claude Code は版の番号で更新を見分け、
    #   manifest に番号があると、作者が変えるまで利用者はその写しのまま（公式の plugins/loading
    #   「Versions and updates」）。番号が無ければ Git の置き場ではコミットの番号が版になり、
    #   書き出して送るたびに届く＝番号の上げ忘れで黙って届かない事故が起きない。
    #   ⚠️`claude plugin validate` は番号が無いと警告を出す（失敗ではない）。
    data = {
        "name": PLUGIN_NAME,
        "description": PLUGIN_DESCRIPTION,
        "author": {"name": MARKETPLACE_OWNER},
    }
    text = json.dumps(data, ensure_ascii=False, indent=2) + NL
    return text.encode("utf-8")


def _marketplace_json_bytes():
    data = {
        "name": MARKETPLACE_NAME,
        "owner": {"name": MARKETPLACE_OWNER},
        "metadata": {
            "description": branding.MARKETPLACE_DESCRIPTION
        },
        "plugins": [
            {
                "name": PLUGIN_NAME,
                "source": "./" + PLUGIN_REL,
                "description": PLUGIN_DESCRIPTION,
            }
        ],
    }
    text = json.dumps(data, ensure_ascii=False, indent=2) + NL
    return text.encode("utf-8")


def _existing_plugin_files(plugin_root):
    """指定した場所（プラグインの根）に今あるファイルを読む。"""
    out = {}
    if os.path.isdir(plugin_root):
        for dirpath, dirnames, filenames in os.walk(plugin_root):
            dirnames[:] = [d for d in dirnames if d != "__pycache__"]
            for name in filenames:
                full = os.path.join(dirpath, name)
                rel = os.path.relpath(full, plugin_root).replace(os.sep, "/")
                out[rel] = _read_bytes(full)
    return out


def _diff(expected, existing):
    """返すもの＝(missing, extra, differing) の3つ（どれもソート済みの名前の並び）。"""
    missing = sorted(set(expected) - set(existing))
    extra = sorted(set(existing) - set(expected))
    differing = sorted(
        name
        for name in (set(expected) & set(existing))
        if expected[name] != existing[name]
    )
    return missing, extra, differing


def _print_diff(missing, extra, differing):
    print("ずれている:")
    for name in missing:
        print("  無い（正本にはある）: " + name)
    for name in extra:
        print("  余分（正本には無い）: " + name)
    for name in differing:
        print("  中身が違う: " + name)


def check(out_dir=None):
    """生成物が正本と一致するかを検査する。

    `out_dir` を渡すと、そこ（プラグインの根そのもの＝下に hooks/scripts/…
    が直接ある場所）だけを検査し、`.claude-plugin/marketplace.json` は見ない
    （試験など、一時フォルダだけを見たい時に使う）。省くと従来どおり、実際の
    `PLUGIN_ROOT`（`plugins/<配布の名前>/`）と repo根の marketplace.json の両方を見る。
    """
    plugin_root = out_dir if out_dir else PLUGIN_ROOT
    expected = _generated_plugin_files()
    existing = _existing_plugin_files(plugin_root)
    missing, extra, differing = _diff(expected, existing)
    total = len(expected)
    if out_dir is None:
        marketplace_path = os.path.join(REPO_ROOT, *MARKETPLACE_REL.split("/"))
        expected_mkt = {MARKETPLACE_REL: _marketplace_json_bytes()}
        existing_mkt = {}
        if os.path.isfile(marketplace_path):
            existing_mkt[MARKETPLACE_REL] = _read_bytes(marketplace_path)
        m_missing, m_extra, m_differing = _diff(expected_mkt, existing_mkt)
        missing = missing + m_missing
        extra = extra + m_extra
        differing = differing + m_differing
        total += 1
    if not missing and not extra and not differing:
        print("一致: 生成物は正本と同じ（%d ファイル）" % total)
        return 0
    _print_diff(missing, extra, differing)
    return 1


def build(out_dir=None):
    """正本から生成する。`out_dir` を渡すと、そこへ直接プラグインの根を書き出し、
    repo根の marketplace.json には触れない（試験用の一時フォルダ生成に使う）。
    省くと従来どおり、実際の `PLUGIN_ROOT`（`plugins/<配布の名前>/`）と
    marketplace.json の両方を書き直す。
    """
    plugin_root = out_dir if out_dir else PLUGIN_ROOT
    expected = _generated_plugin_files()
    # 生成物は正本ではない＝作り直す前に消してよい（ずれの原因になる残骸を残さない）。
    if os.path.isdir(plugin_root):
        shutil.rmtree(plugin_root)
    for rel, data in expected.items():
        dest = os.path.join(plugin_root, *rel.split("/"))
        _write_bytes(dest, data)
    total = len(expected)
    if out_dir is None:
        marketplace_path = os.path.join(REPO_ROOT, *MARKETPLACE_REL.split("/"))
        _write_bytes(marketplace_path, _marketplace_json_bytes())
        total += 1
        print("生成した: %s + %s（%d ファイル）" % (plugin_root, MARKETPLACE_REL, total))
    else:
        print("生成した: %s（%d ファイル）" % (plugin_root, total))
    return 0


def _parse_argv(argv):
    check_only = False
    out_dir = None
    index = 1
    while index < len(argv):
        token = argv[index]
        if token == "--check":
            check_only = True
        elif token == "--out" and index + 1 < len(argv):
            index += 1
            out_dir = argv[index]
        index += 1
    return check_only, out_dir


def main(argv):
    check_only, out_dir = _parse_argv(argv)
    if check_only:
        return check(out_dir)
    return build(out_dir)


if __name__ == "__main__":
    if sys.platform == "win32":
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass
    raise SystemExit(main(sys.argv))

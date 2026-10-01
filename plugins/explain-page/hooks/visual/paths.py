from __future__ import annotations

"""用語集3つ・読みやすさ規則・頁を組む道具の場所を、直置き（.claude）でも
Claude Codeのプラグインでも同じ規則で決める（2026-09-25 新設）。

なぜ1か所にまとめるか
----------------------
検品の照合は「頁を組む道具（render_page.py）が使った用語集」と「台本（フックの
指示文）が使った用語集」が**同じ中身か**を見る。この2つがそれぞれ別の規則で
パスを決めると、プラグイン化のときにズレて記録が無効になる。
∴composer 側（understanding-composer.py → visual/entrypoint.py）と
render_page.py の両方が、ここの関数だけを呼ぶ。

「台本の根」とは
----------------
hooks フォルダ（このファイルが入っている `visual/` の親）の、そのまた親のこと。
  直置き   … `<project>/.claude/hooks` の親 ＝ `<project>/.claude`
  プラグイン … `<plugin>/hooks` の親 ＝ プラグインの根
どちらも呼び出し側が `Path(__file__).resolve().parent.parent`（understanding-composer.py
の HOOKS_DIR.parent）や、render_page.py の CLAUDE_DIR と同じ考え方で求められるので、
直置きかプラグインかを呼び出し側が意識しなくても、ここへ渡す値は自動的に正しい場所になる。
"""

import os
import re
import tempfile
from pathlib import Path

from . import branding

# LLMに見せる文字列にだけ使うトークン（Claude Codeがhookコマンドの中で実行時に展開する
# 環境変数）。ファイルシステムの探索には使わない＝実ファイルの有無は判定できないので。
PLUGIN_ROOT_TOKEN = "${CLAUDE_PLUGIN_ROOT}"
PROJECT_DIR_TOKEN = "${CLAUDE_PROJECT_DIR}"

# 直置き（プラグインを使わない）ときに指示文へ出す、頁を組む道具の相対パス。
# ⚠️このリポジトリでの実際の運用と同じ文字列＝ここを変えると「1バイトも変えない」が破れる。
DIRECT_RENDER_PAGE_PATH = ".claude/scripts/render_page.py"


def glossary_paths(
    project_root: str | Path, script_root: str | Path
) -> tuple[Path, Path, Path]:
    """用語集3つ（共通の正本・控え・固有）のpathを返す。

    入れるもの＝プロジェクトの根・台本の根。返るもの＝(home_shared, mirror, project)。

    - 共通の正本＝常に `~/.claude/glossary-shared.md`（直置き・プラグインで変わらない）。
    - 控え（mirror）＝プロジェクトの `<project>/.claude/glossary-shared.md` があればそれ、
      無ければ台本の根の `glossary-shared.md`（プラグイン同梱の控え）。
      ⚠️直置きでは「台本の根」がそのままプロジェクトの `.claude` なので、この2つは
      同じpathになり、既存の挙動と1バイトも変わらない。
    - 固有＝常にプロジェクトの `<project>/.claude/glossary.md`。
    """
    claude_dir = Path(project_root) / ".claude"
    home_shared = Path.home() / ".claude" / "glossary-shared.md"
    project_mirror = claude_dir / "glossary-shared.md"
    bundled_mirror = Path(script_root) / "glossary-shared.md"
    mirror = project_mirror if project_mirror.is_file() else bundled_mirror
    project_specific = claude_dir / "glossary.md"
    return home_shared, mirror, project_specific


def readability_rules_path(project_root: str | Path, script_root: str | Path) -> Path:
    """読みやすさ規則（否定側の言い回し）のpathを返す。

    プロジェクトの `<project>/.claude/readability-rules.md` があればそれ、
    無ければ台本の根の `templates/readability-rules.md`（プラグイン同梱の雛形）。
    ⚠️直置きでは通常プロジェクト側に正本があるので、この分岐に入らない。
    """
    claude_dir = Path(project_root) / ".claude"
    project_rules = claude_dir / "readability-rules.md"
    if project_rules.is_file():
        return project_rules
    # 2026-09-28：利用者単位の配線（--shared）では台本の根が別のリポジトリの `.claude`
    # なので、正本はその直下にある。プラグインの根には無いので、プラグインでは従来どおり雛形へ。
    shared_rules = Path(script_root) / "readability-rules.md"
    if shared_rules.is_file():
        return shared_rules
    return Path(script_root) / "templates" / "readability-rules.md"


def html_output_path(project_root: str | Path, script_root: str | Path) -> Path:
    """部品ごとの説明文（html-output.md）のpathを返す。

    プロジェクトの `<project>/.claude/html-output.md` があればそれ、無ければ台本の根の
    `html-output.md`（プラグイン同梱の版）。⚠️2026-09-25：同梱の一覧から漏れていて、
    プラグインで有効にしたプロジェクトでは部品ごとの指示（初心者として扱う等）が出ていなかった。
    """
    project_file = Path(project_root) / ".claude" / "html-output.md"
    if project_file.is_file():
        return project_file
    return Path(script_root) / "html-output.md"


# %TEMP%（大小無視）だけは正規表現で拾う＝Windowsの環境変数記法は大文字小文字を
# 区別しないので "%Temp%" 等の書きぶり違いも受ける。$TMPDIR・${TMPDIR}・$TEMP は
# Unix系の書き方で、大文字小文字を区別する通常の環境変数名なのでそのまま文字列一致。
_PERCENT_TEMP_PATTERN = re.compile(r"%TEMP%", re.IGNORECASE)
_DOLLAR_TEMP_TOKENS = ("${TMPDIR}", "$TMPDIR", "$TEMP")


def artifact_root(value: str | None) -> Path:
    """置き場の文字列（policyの `local_artifact_root`）を実際のPathへ展開する
    （2026-09-25 新設）。

    入れるもの＝`local_artifact_root` の値（無い・空文字なら None扱い）。
    返すもの＝展開ずみのPath。

    - None・空文字なら既定＝`"%TEMP%/" + branding.ARTIFACT_DIR_NAME`。
    - `%TEMP%`（大小無視）・`$TMPDIR`・`${TMPDIR}`・`$TEMP` は
      `tempfile.gettempdir()` に置き換える（Windowsは`%TEMP%`、Mac/Linuxは
      `$TMPDIR`が典型だが、OSを問わずどちらの書き方も受ける）。
    - 残りは `os.path.expandvars`・`os.path.expanduser` で展開する
      （他の環境変数や `~` を使いたい場合のため）。

    ⚠️このリポジトリの `.claude/visual-hook-policy.json` は `local_artifact_root` に
      既定と同じ値（`"%TEMP%/" + branding.ARTIFACT_DIR_NAME`）を明示しているので、
      結果はこのリポジトリでの従来どおりの場所と1バイトも変わらない
      （試験 `test_branding_portability.py` で確かめる）。
    """
    text = value if isinstance(value, str) and value.strip() else None
    if text is None:
        text = "%TEMP%/" + branding.ARTIFACT_DIR_NAME
    tmp_dir = tempfile.gettempdir()
    text = _PERCENT_TEMP_PATTERN.sub(lambda _match: tmp_dir, text)
    for token in _DOLLAR_TEMP_TOKENS:
        text = text.replace(token, tmp_dir)
    text = os.path.expandvars(text)
    text = os.path.expanduser(text)
    return Path(text)


def render_page_tool_location(
    *,
    plugin: bool,
    script_root: str | Path | None = None,
    project_root: str | Path | None = None,
) -> str:
    """指示文で示す『頁を組む道具』の場所（LLMに見せる文字列）を返す。

    直置き（plugin=False）＝プロジェクト相対 `.claude/scripts/render_page.py`
      （このリポジトリでは今と同じ文字列＝挙動を変えない）。
    プラグイン（plugin=True）＝実ファイルパスではなく、実行時に展開される環境変数の
      トークンをそのまま埋め込む（`${CLAUDE_PLUGIN_ROOT}/scripts/render_page.py`）。
      ⚠️ここで実在のパスへ解決してしまうと、他人の機械では存在しないパスになる。
    道具の置き場とプロジェクトが違う（2026-09-28）＝台本の根（script_root）の親が
      プロジェクトの根と別の場所なら、道具の絶対の場所（`/` 区切り）を返す。
      利用者単位の配線（--shared）や、別のリポジトリへ書いた Codex の配線では、
      相対の場所はそのプロジェクトに存在しないので、LLM が道具を見つけられなくなる。
      ⚠️両方を渡さない呼び出し・同じ場所のときは従来どおり（このリポジトリでは1バイトも変わらない）。
    """
    if plugin:
        return PLUGIN_ROOT_TOKEN + "/scripts/render_page.py"
    if script_root is not None and project_root is not None:
        tool_repo = os.path.normcase(os.path.abspath(str(Path(script_root).parent)))
        project = os.path.normcase(os.path.abspath(str(project_root)))
        if tool_repo != project:
            return (Path(os.path.abspath(str(script_root))) / "scripts" / "render_page.py").as_posix()
    return DIRECT_RENDER_PAGE_PATH

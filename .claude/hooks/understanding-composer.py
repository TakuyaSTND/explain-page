from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

HOOKS_DIR = Path(__file__).resolve().parent
if str(HOOKS_DIR) not in sys.path:
    sys.path.insert(0, str(HOOKS_DIR))

from visual.entrypoint import handle_event
from visual.policy import load_policy
from visual.state import StateStore
from visual import paths as visual_paths


def _has_direct_wiring(claude_dir: Path) -> bool:
    """そのプロジェクトの settings.json / settings.local.json に、この道具（
    understanding-composer.py）を直接呼ぶ配線が**既にある**かを見る。

    ⚠️`--plugin` の安全の掟②＝プラグインのフックとプロジェクトに直接書いたフックは
      **両方走る**。このリポジトリのように直接の配線が既にある所でプラグインも入れると
      二重に走ってしまうので、直接の配線があるプロジェクトでは `--plugin` 側を黙って
      引っ込める。判定は構造ではなく単純な文字列一致＝settings.json の形がどうであれ、
      その中に "understanding-composer.py" という文字列があれば「配線あり」とみなす
      （fail-safeに倒す＝見逃すと二重発火、誤検知しても実害は「プラグインが働かない」
      だけ）。
    読めない・壊れている設定ファイルは「配線なし」として扱う（既存の他コードと同じ
      fail-open の考え方＝設定ファイルの読み取り失敗で本体処理を止めない）。
    """
    for name in ("settings.json", "settings.local.json"):
        candidate = claude_dir / name
        if not candidate.is_file():
            continue
        try:
            text = candidate.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if "understanding-composer.py" in text:
            return True
    return False


def _has_direct_codex_wiring(root: Path) -> bool:
    """そのプロジェクトの `.codex/hooks.json` / `.codex/config.toml` に、この道具を
    直接呼ぶ配線が既にあるかを見る（2026-09-28・`--shared` の安全の掟②の Codex 版）。

    ⚠️Codex は利用者単位（~/.codex/hooks.json）とリポジトリ単位（.codex/hooks.json）の
      フックを**重ねて全部走らせる**（Codex の公式の説明 learn.chatgpt.com/docs/hooks）。
      このリポジトリのように直接の配線がある所で利用者単位の配線も走ると二重になるので、
      `_has_direct_wiring` と同じ単純な文字列一致で引っ込める。
    """
    for name in ("hooks.json", "config.toml"):
        candidate = root / ".codex" / name
        if not candidate.is_file():
            continue
        try:
            text = candidate.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if "understanding-composer.py" in text:
            return True
    return False


def _shared_start_dir(payload: dict, runtime: str) -> Path:
    """`--shared` で印を探し始める場所（2026-09-28）。

    Claude は CLAUDE_PROJECT_DIR（会話の根＝`cd` しても動かない）を先に使う。
    無ければ入力の cwd（Claude・Codex とも入力に入る）、それも無ければ今の作業フォルダ
    （Codex はフックを会話の cwd で走らせる）。
    """
    if runtime == "claude":
        env_root = os.environ.get("CLAUDE_PROJECT_DIR")
        if env_root and os.path.isdir(env_root):
            return Path(env_root)
    cwd = payload.get("cwd")
    if isinstance(cwd, str) and cwd and os.path.isdir(cwd):
        return Path(cwd)
    return Path(os.getcwd())


def _find_enabled_root(start: Path) -> Path | None:
    """start から上へ辿って `.claude/visual-hook-policy.json`（有効にする印）がある
    フォルダを返す。どこにも無ければ None（`--shared` の安全の掟①＝何もしない）。
    """
    current = start.resolve()
    while True:
        if (current / ".claude" / "visual-hook-policy.json").is_file():
            return current
        if current.parent == current:
            return None
        current = current.parent


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runtime", choices=("claude", "codex", "hermes"), required=True)
    parser.add_argument("--project-root")
    parser.add_argument("--state-path")
    # 2026-09-25：Claude Codeのプラグインから呼ばれた時だけ付く印。
    # ⚠️このフラグが無い時の挙動は今と1バイトも変えない（下のif文の外は全部従来どおり）。
    parser.add_argument("--plugin", action="store_true")
    # 2026-09-28：利用者単位の配線（~/.claude/settings.json・~/.codex/hooks.json）から
    # 呼ばれた時だけ付く印。プロジェクトの根は固定で渡さず、会話の場所から印を探して決める。
    parser.add_argument("--shared", action="store_true")
    args = parser.parse_args(argv)
    if not args.shared and not args.project_root:
        parser.error("--project-root is required unless --shared is given")
    try:
        payload = json.loads(sys.stdin.read() or "{}")
    except json.JSONDecodeError:
        return 0
    if not isinstance(payload, dict):
        return 0
    if args.shared:
        # 安全の掟①：会話の場所から上へ辿っても印が無ければ何もしない
        # （利用者単位の配線はどのリポジトリの会話でも走るので、使うと決めた所だけで動かす）。
        found = _find_enabled_root(_shared_start_dir(payload, args.runtime))
        if found is None:
            return 0
        root = found
        # 安全の掟②：そのプロジェクトに直接の配線が既にあれば何もしない
        # （このリポジトリのように直接の配線がある所で二重に走るのを防ぐ）。
        if args.runtime == "claude" and _has_direct_wiring(root / ".claude"):
            return 0
        if args.runtime == "codex" and _has_direct_codex_wiring(root):
            return 0
    else:
        root = Path(args.project_root).resolve()
    claude_dir = root / ".claude"
    policy_path = claude_dir / "visual-hook-policy.json"

    if args.plugin:
        # 安全の掟①：そのプロジェクトが仕組みを有効にしていなければ何もしない
        # （プラグインを入れても関係ないリポジトリには効かせない）。
        if not policy_path.is_file():
            return 0
        # 安全の掟②：そのプロジェクトに直接の配線が既にあれば何もしない
        # （このリポジトリのように直接の配線がある所で二重に走るのを防ぐ）。
        if _has_direct_wiring(claude_dir):
            return 0

    policy = load_policy(policy_path)
    if not policy.enabled:
        return 0
    # 2026-09-25：置き場は policy の local_artifact_root（無ければ既定）を
    # visual/paths.py の artifact_root() で展開した場所を使う（composerとrender_page.py
    # の両方がここを通るので、承認済みの置き場がずれない）。
    resolved_artifact_root = visual_paths.artifact_root(policy.local_artifact_root)
    state_path = (
        Path(args.state_path)
        if args.state_path
        else resolved_artifact_root / "state.db"
    )
    state_store = StateStore(state_path)

    # 「台本の根」＝hooksフォルダの親。直置きなら`<project>/.claude`、プラグインなら
    # プラグインの根＝どちらも HOOKS_DIR.parent で自動的に正しい場所になる
    # （visual/paths.py のdocstring参照）。
    script_root = HOOKS_DIR.parent
    glossary_paths_value = visual_paths.glossary_paths(root, script_root)
    readability_rules_value = visual_paths.readability_rules_path(root, script_root)
    render_page_path = visual_paths.render_page_tool_location(
        plugin=args.plugin, script_root=script_root, project_root=root
    )

    result = handle_event(
        payload,
        runtime=args.runtime,
        project_root=str(root),
        policy=policy,
        html_output_path=visual_paths.html_output_path(root, script_root),
        state_store=state_store,
        glossary_paths=glossary_paths_value,
        local_artifact_root=resolved_artifact_root,
        # 2026-08-28：読みやすさの否定規則（shadow既定）。正本が無ければ entrypoint 側で空規則になる
        readability_rules_path=readability_rules_value,
        render_page_path=render_page_path,
    )
    if result:
        sys.stdout.write(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    if sys.platform == "win32":
        try:
            sys.stdout.reconfigure(encoding="utf-8")
            sys.stderr.reconfigure(encoding="utf-8")
        except Exception:
            pass
    raise SystemExit(main())

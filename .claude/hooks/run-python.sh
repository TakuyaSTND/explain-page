#!/bin/sh
# 実行の入口（POSIX sh・2026-09-25 新設）。
#
# なぜ要るか＝Macには「python」が無いことが普通で「python3」を使う。Windowsは逆に
# 「python」が使え、しかも「python3」が Microsoft Store の偽物（起動するだけで
# 何もしない）のことがあるので、Windowsではpython3を探さない。
#
# 使い方＝ sh run-python.sh <このあとにpythonへ渡す引数>
#   例＝ sh "${CLAUDE_PLUGIN_ROOT}/hooks/run-python.sh" "${CLAUDE_PLUGIN_ROOT}/hooks/understanding-composer.py" --runtime claude --plugin --project-root "${CLAUDE_PROJECT_DIR}"

PYTHONUTF8=1
export PYTHONUTF8

if [ "$OS" = "Windows_NT" ]; then
  PY=python
elif command -v python3 >/dev/null 2>&1; then
  PY=python3
else
  PY=python
fi

exec "$PY" "$@"

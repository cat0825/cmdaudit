#!/usr/bin/env bash
# 用 pyproject 里 pin 的版本跑 CI 的三步检查。
#
# 直接用系统 ruff/mypy/pytest 会因版本漂移出现「本地过、CI 挂」：
# 实测本地 ruff 0.15 放过的 UP038，CI 的 0.9.2 会报错。
set -euo pipefail

cd "$(dirname "$0")/.."
VENV=".venv-ci"

if [[ ! -x "$VENV/bin/python" ]]; then
  echo "==> 创建 $VENV"
  python3 -m venv "$VENV"
fi

echo "==> 同步 pin 的依赖"
"$VENV/bin/pip" install -q -e '.[dev]'

echo "==> ruff $("$VENV/bin/ruff" --version)"
"$VENV/bin/ruff" check src tests

echo "==> mypy $("$VENV/bin/mypy" --version)"
"$VENV/bin/mypy"

echo "==> pytest $("$VENV/bin/pytest" --version 2>&1 | head -1)"
"$VENV/bin/pytest" -q

echo "==> 全部通过"

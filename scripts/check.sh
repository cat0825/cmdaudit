#!/usr/bin/env bash
# 用 pin 的版本跑 CI 的检查，并覆盖前端构建图。
#
# 直接用系统 ruff/mypy/pytest 会因版本漂移出现「本地过、CI 挂」：
# 实测本地 ruff 0.15 放过的 UP038，CI 的 0.9.2 会报错。
# 前端也按同一张图校验：`web/dist/index.html` 必须与提交进包的
# `src/cmdaudit/viz/shell.html` 一致，否则前端改了、产物没同步的 PR
# 会在这一步失败。
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

if ! command -v npm >/dev/null 2>&1; then
  echo "错误：找不到 npm，无法校验前端构建图。请先安装 Node 22+。"
  exit 1
fi

echo "==> 前端 typecheck"
(cd web && npm ci && npm run typecheck)

echo "==> 前端 build + shell.html 同步校验"
(cd web && npm run build)
if ! cmp -s web/dist/index.html src/cmdaudit/viz/shell.html; then
  echo "错误：web/dist/index.html 与 src/cmdaudit/viz/shell.html 不一致。"
  echo "      前端改动后必须先重建外壳：运行 scripts/sync-shell.sh 并提交新的 shell.html。"
  exit 1
fi

echo "==> 全部通过"

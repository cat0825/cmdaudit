#!/usr/bin/env bash
# 重建工作台外壳并落盘到 src/cmdaudit/viz/shell.html。
#
# 这是 `web/dist/index.html` → `src/cmdaudit/viz/shell.html` 的**唯一**复制通道。
# `scripts/check.sh` 与 CI 都按同一张构建图做确定性同步校验：构建产物与
# 提交进包的外壳不一致就失败，并提示运行本脚本。
set -euo pipefail
cd "$(dirname "$0")/.."

echo "==> 前端依赖（lockfile 确定性安装）"
(cd web && npm ci)

echo "==> 前端 typecheck + build"
(cd web && npm run build)

echo "==> 落盘 shell.html"
cp web/dist/index.html src/cmdaudit/viz/shell.html
echo "   src/cmdaudit/viz/shell.html ($(wc -c < src/cmdaudit/viz/shell.html) bytes)"

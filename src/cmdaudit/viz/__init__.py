"""离线单文件可视化。

`cmdaudit viz` 直接读 `commands.duckdb`（不经 summary.json），
因此页面能拿到 Markdown 报告里没有的命令原文样本。
"""

from __future__ import annotations

from cmdaudit.viz.build import build_viz

__all__ = ["build_viz"]

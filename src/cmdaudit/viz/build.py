"""生成入口：DuckDB → Payload → 单文件 HTML。"""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

from cmdaudit.db import open_commands_db
from cmdaudit.viz.collect import collect_payload
from cmdaudit.viz.render_html import render_html
from cmdaudit.viz.serialize import payload_to_dict


def build_viz(
    commands_db: Path,
    out_html: Path,
    *,
    candidates_path: Path | None = None,
    generated_at: dt.datetime | None = None,
    fixture_path: Path | None = None,
) -> Path:
    """生成离线工作台页并返回写入路径。

    `fixture_path` 给定时额外导出一份未转义的 payload JSON。它只服务于
    `web/` 前端开发（`npm run dev` 会读它），产物页面本身不依赖该文件。
    """
    stamp = (generated_at or dt.datetime.now(dt.UTC)).strftime("%Y-%m-%d %H:%M UTC")
    # open_commands_db 自带存在性检查与只读约束：可视化不得改动抽取结果。
    conn = open_commands_db(commands_db)
    try:
        payload = collect_payload(
            conn,
            source_db=str(commands_db),
            generated_at=stamp,
            candidates_path=candidates_path,
        )
    finally:
        conn.close()

    out_html.parent.mkdir(parents=True, exist_ok=True)
    out_html.write_text(render_html(payload), encoding="utf-8")

    if fixture_path is not None:
        fixture_path.parent.mkdir(parents=True, exist_ok=True)
        fixture_path.write_text(
            json.dumps(payload_to_dict(payload), ensure_ascii=False, indent=1),
            encoding="utf-8",
        )
    return out_html

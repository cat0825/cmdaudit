"""把 Table 渲染成 Markdown 与 JSON。

每张表都要打印自己的口径声明与可复现 SQL。
报告里不允许出现「不知道来自哪个口径」的数字。
"""

from __future__ import annotations

import datetime as dt
import json
from typing import Any

from cmdaudit.report.queries import Table

_MAX_CELL = 88


def _cell(value: Any) -> str:
    if value is None:
        return "—"
    text = str(value).replace("\n", " ").replace("\r", " ").replace("|", "\\|")
    text = " ".join(text.split())
    if len(text) > _MAX_CELL:
        text = text[: _MAX_CELL - 1] + "…"
    return text


def render_table(table: Table) -> str:
    lines = [f"### {table.title}", ""]
    lines.append(f"口径 `{table.scope.name}`：{table.scope.caveat}")
    lines.append("")
    if table.note:
        lines.append(table.note)
        lines.append("")
    if not table.rows:
        lines.append("_无数据_")
        lines.append("")
    else:
        lines.append("| " + " | ".join(table.columns) + " |")
        lines.append("|" + "|".join(["---"] * len(table.columns)) + "|")
        for row in table.rows:
            lines.append("| " + " | ".join(_cell(value) for value in row) + " |")
        lines.append("")
    lines.append("<details><summary>复现这张表的 SQL</summary>")
    lines.append("")
    lines.append("```sql")
    lines.append(table.sql)
    lines.append("```")
    lines.append("")
    lines.append("</details>")
    lines.append("")
    return "\n".join(lines)


def render_markdown(
    *,
    tables: list[Table],
    coverage: dict[str, Any],
    source_db: str,
    generated_at: dt.datetime | None = None,
) -> str:
    stamp = (generated_at or dt.datetime.now(dt.UTC)).strftime("%Y-%m-%d %H:%M UTC")
    lines = [
        "# 命令审计报告",
        "",
        f"生成时间：{stamp}",
        f"数据源：`{source_db}`",
        "",
        "## 读这份报告之前",
        "",
        "耗时与失败是两套独立的证据，覆盖范围不同，**不要跨表相加**：",
        "",
        "- **失败分析**不依赖耗时证据，覆盖全部 agent。",
        "- **耗时分析**只在有进程自报墙钟的记录上成立。本机数据里这部分几乎全部"
        "来自 codex，所以耗时结论不可外推到其他 agent。",
        "",
        "三类记录被排除在耗时统计之外，原因各不相同：",
        "",
        "| 排除项 | 原因 |",
        "|---|---|",
        "| `duration_source = 'batch_shared'` | 并发批次共享一个总墙钟，均摊会让每条数据都失真 |",
        "| `duration_source = 'unknown'` | 没有任何耗时证据 |",
        "| `duration_truncated = true` | 命令未跑完就被工具让出，记录到的是下界不是耗时 |",
        "",
        "## 数据覆盖",
        "",
    ]
    lines.append("| 项 | 值 |")
    lines.append("|---|---|")
    for key, value in coverage.items():
        lines.append(f"| {key} | {value} |")
    lines.append("")

    grouped: dict[str, list[Table]] = {}
    for table in tables:
        grouped.setdefault(table.scope.name, []).append(table)

    section_titles = {
        "status_only": "## 失败分析（全 agent 覆盖）",
        "exact": "## 耗时分析（仅进程自报墙钟）",
        "upper_bound": "## 耗时上界参考（含模型思考时间）",
    }
    for scope_name in ("status_only", "exact", "upper_bound"):
        scope_tables = grouped.get(scope_name)
        if not scope_tables:
            continue
        lines.append(section_titles[scope_name])
        lines.append("")
        for table in scope_tables:
            lines.append(render_table(table))

    return "\n".join(lines).rstrip() + "\n"


def render_json(
    *,
    tables: list[Table],
    coverage: dict[str, Any],
    source_db: str,
    generated_at: dt.datetime | None = None,
) -> str:
    stamp = (generated_at or dt.datetime.now(dt.UTC)).isoformat()
    payload = {
        "generated_at": stamp,
        "source_db": source_db,
        "coverage": coverage,
        "tables": [
            {
                "key": table.key,
                "title": table.title,
                "scope": {
                    "name": table.scope.name,
                    "sources": list(table.scope.sources),
                    "caveat": table.scope.caveat,
                },
                "columns": list(table.columns),
                "rows": [list(row) for row in table.rows],
                "sql": table.sql,
                "note": table.note,
            }
            for table in tables
        ],
    }
    return json.dumps(payload, indent=2, ensure_ascii=False) + "\n"

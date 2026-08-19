"""组装报告：覆盖度统计 + 四类表。"""

from __future__ import annotations

from typing import Any

import duckdb

from cmdaudit.report import queries as Q
from cmdaudit.report.queries import Table
from cmdaudit.report.scope import DURATION_GUARD, EXACT, STATUS_ONLY


def collect_coverage(conn: duckdb.DuckDBPyConnection) -> dict[str, Any]:
    """报告开头的覆盖度表。每个排除项都要能解释去向。"""

    def scalar(sql: str) -> Any:
        row = conn.execute(sql).fetchone()
        return row[0] if row else None

    total = scalar("SELECT count(*) FROM commands")
    coverage: dict[str, Any] = {
        "命令总数": total,
        "agent 数": scalar("SELECT count(DISTINCT agent) FROM commands"),
        "项目数": scalar("SELECT count(DISTINCT project) FROM commands"),
        "模板数": scalar("SELECT count(DISTINCT template_id) FROM commands"),
        "判定为失败": scalar("SELECT count(*) FROM commands WHERE status = 'failed'"),
        "判定为成功": scalar("SELECT count(*) FROM commands WHERE status = 'ok'"),
        "查无结果（非失败）": scalar("SELECT count(*) FROM commands WHERE status = 'no_match'"),
        "无状态证据": scalar("SELECT count(*) FROM commands WHERE status = 'unknown'"),
        "可用于耗时统计": scalar(f"SELECT count(*) FROM commands WHERE {DURATION_GUARD}"),
        "耗时被工具让出截断": scalar("SELECT count(*) FROM commands WHERE duration_truncated"),
        "批次共享耗时": scalar(
            "SELECT count(*) FROM commands WHERE duration_source = 'batch_shared'"
        ),
        "无耗时证据": scalar("SELECT count(*) FROM commands WHERE duration_source = 'unknown'"),
    }
    exact_total = scalar(
        f"SELECT round(sum(duration_s), 1) FROM commands WHERE {DURATION_GUARD}"
    )
    coverage["可信耗时合计（秒）"] = exact_total
    if isinstance(exact_total, int | float):
        coverage["可信耗时合计（小时）"] = round(exact_total / 3600, 2)
    return coverage


def build_tables(conn: duckdb.DuckDBPyConnection) -> list[Table]:
    return [
        # 失败线：全 agent 覆盖，是主线。
        Q.failure_by_kind_and_program(conn, STATUS_ONLY),
        Q.failure_rate_by_program(conn, STATUS_ONLY),
        Q.timeout_and_network(conn, STATUS_ONLY),
        # 耗时线：仅自报墙钟。
        Q.duration_by_template(conn, EXACT),
        Q.by_group(conn, EXACT),
        Q.by_program(conn, EXACT),
        Q.by_agent(conn, EXACT),
        Q.by_project(conn, EXACT),
    ]

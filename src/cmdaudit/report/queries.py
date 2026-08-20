"""聚合查询。

每个查询都返回它自己的 SQL 原文，报告里逐表打印，
这样任何数字都能被独立复现（docs/plan.md §4 验收标准）。

分位数一律用 `quantile_cont`，并且只在排除了 `batch_shared` / `unknown`
的行集上计算：`batch_shared` 是并发批次共享的总墙钟，
均摊或直接入统计都会让每条数据失真。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Final

import duckdb

from cmdaudit.report.scope import DURATION_GUARD, Scope

#: 耗时统计的过滤条件，见 scope.DURATION_GUARD。
_PERCENTILE_GUARD: Final[str] = DURATION_GUARD


@dataclass(frozen=True, slots=True)
class Table:
    """一张报告表：标题、口径、列名、数据行、可复现的 SQL。"""

    key: str
    title: str
    scope: Scope
    columns: tuple[str, ...]
    rows: tuple[tuple[Any, ...], ...]
    sql: str
    note: str = ""


def _run(conn: duckdb.DuckDBPyConnection, sql: str) -> tuple[tuple[Any, ...], ...]:
    return tuple(tuple(row) for row in conn.execute(sql).fetchall())


def failure_by_kind_and_program(
    conn: duckdb.DuckDBPyConnection, scope: Scope, *, limit: int = 25
) -> Table:
    """失败榜：主表。不依赖耗时，覆盖全部 agent。"""
    sql = f"""
SELECT failure_kind,
       program,
       count(*)                        AS failures,
       count(DISTINCT agent)           AS agents,
       count(DISTINCT project)         AS projects,
       any_value(error_snippet)         AS sample
FROM commands
WHERE status = 'failed'
GROUP BY failure_kind, program
ORDER BY failures DESC
LIMIT {limit}
""".strip()
    return Table(
        key="failure_by_kind_and_program",
        title="失败榜：失败类型 × 程序",
        scope=scope,
        columns=("failure_kind", "program", "failures", "agents", "projects", "sample"),
        rows=_run(conn, sql),
        sql=sql,
        note=(
            "按可落地规则排序的主表：同一 program 反复以同一 failure_kind 失败，"
            "才值得写进 AGENTS.md。"
        ),
    )


def failure_rate_by_program(
    conn: duckdb.DuckDBPyConnection, scope: Scope, *, min_runs: int = 30, limit: int = 25
) -> Table:
    """失败率榜。只看有足够样本的程序，避免小样本噪声。

    分母只含 `ok` 与 `failed`：
    - `unknown` 是没有状态证据，不是成功；
    - `no_match` 是 `rg` / `find` 这类查无结果，是成功的空查询而非失败，
      算进分母会稀释真实失败率。
    """
    sql = f"""
SELECT program,
       count(*)                                              AS decided_runs,
       sum(CASE WHEN status = 'failed' THEN 1 ELSE 0 END)     AS failures,
       round(
           100.0 * sum(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) / count(*), 1
       )                                                      AS failure_pct
FROM commands
WHERE status IN ('ok', 'failed')
GROUP BY program
HAVING count(*) >= {min_runs}
ORDER BY failure_pct DESC, failures DESC
LIMIT {limit}
""".strip()
    return Table(
        key="failure_rate_by_program",
        title=f"失败率榜（仅统计已判定 ≥ {min_runs} 次的程序）",
        scope=scope,
        columns=("program", "decided_runs", "failures", "failure_pct"),
        rows=_run(conn, sql),
        sql=sql,
        note=(
            "分母只含 `ok` 与 `failed`。`unknown`（无状态证据）与 "
            "`no_match`（`rg`/`find` 查无结果）都不进分母。"
        ),
    )


def duration_by_template(
    conn: duckdb.DuckDBPyConnection, scope: Scope, *, limit: int = 30
) -> Table:
    """耗时榜：按 `canonical` 聚合。

    不用 Drain3 的 `template`：它把 `npm run build`（732 秒 / 152 次）、
    `npm run typecheck`（311 秒 / 106 次）、`npm run test:e2e`（490 秒 / 30 次）
    聚成同一个 `npm run <*>` 桶。那个粒度下「哪一类命令吃掉我最多时间」
    这个问题的答案是「npm run 什么东西」，没有可操作性。
    """
    sql = f"""
SELECT canonical,
       program,
       count(*)                                    AS runs,
       round(sum(duration_s), 1)                   AS total_s,
       round(quantile_cont(duration_s, 0.5), 3)    AS p50_s,
       round(quantile_cont(duration_s, 0.9), 2)    AS p90_s,
       round(max(duration_s), 1)                   AS max_s
FROM commands
WHERE {scope.sql_filter}
  AND {_PERCENTILE_GUARD}
GROUP BY canonical, program
ORDER BY total_s DESC
LIMIT {limit}
""".strip()
    return Table(
        key="duration_by_command_shape",
        title="耗时榜：按命令形状聚合",
        scope=scope,
        columns=("canonical", "program", "runs", "total_s", "p50_s", "p90_s", "max_s"),
        rows=_run(conn, sql),
        sql=sql,
        note=(
            "回答「哪一类命令吃掉我最多时间」。默认按总耗时降序。"
            "形状用确定性占位符替换（保留 script 名），不用 Drain3 聚类 —— "
            "后者会把 `npm run build` 与 `npm run typecheck` 合成一桶。"
        ),
    )


def timeout_and_network(
    conn: duckdb.DuckDBPyConnection, scope: Scope, *, limit: int = 25
) -> Table:
    """超时与网络专项：这是最初的诉求。"""
    sql = f"""
SELECT failure_kind,
       program,
       count(*)                                        AS failures,
       round(sum(COALESCE(duration_s, 0)), 1)          AS observed_s,
       any_value(error_snippet)                        AS sample
FROM commands
WHERE status = 'failed'
  AND failure_kind IN ('timeout', 'network')
GROUP BY failure_kind, program
ORDER BY failures DESC
LIMIT {limit}
""".strip()
    return Table(
        key="timeout_and_network",
        title="超时与网络专项",
        scope=scope,
        columns=("failure_kind", "program", "failures", "observed_s", "sample"),
        rows=_run(conn, sql),
        sql=sql,
        note=(
            "observed_s 是这些失败已记录到的耗时之和，混合了多种 duration_source，"
            "只用于粗略量级判断，不可当精确损耗引用。"
        ),
    )


def _dimension(
    conn: duckdb.DuckDBPyConnection,
    scope: Scope,
    *,
    key: str,
    column: str,
    title: str,
    limit: int,
) -> Table:
    sql = f"""
SELECT {column}                                        AS bucket,
       count(*)                                        AS runs,
       round(sum(duration_s), 1)                       AS total_s,
       round(quantile_cont(duration_s, 0.5), 3)        AS p50_s,
       round(quantile_cont(duration_s, 0.9), 2)        AS p90_s,
       sum(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) AS failures
FROM commands
WHERE {scope.sql_filter}
  AND {_PERCENTILE_GUARD}
GROUP BY {column}
ORDER BY total_s DESC
LIMIT {limit}
""".strip()
    return Table(
        key=key,
        title=title,
        scope=scope,
        columns=("bucket", "runs", "total_s", "p50_s", "p90_s", "failures"),
        rows=_run(conn, sql),
        sql=sql,
    )


def by_group(conn: duckdb.DuckDBPyConnection, scope: Scope, *, limit: int = 20) -> Table:
    return _dimension(
        conn, scope, key="by_group", column="command_group", title="维度：命令分组", limit=limit
    )


def by_program(conn: duckdb.DuckDBPyConnection, scope: Scope, *, limit: int = 25) -> Table:
    return _dimension(
        conn, scope, key="by_program", column="program", title="维度：程序", limit=limit
    )


def by_agent(conn: duckdb.DuckDBPyConnection, scope: Scope, *, limit: int = 20) -> Table:
    return _dimension(
        conn, scope, key="by_agent", column="agent", title="维度：agent", limit=limit
    )


def by_project(conn: duckdb.DuckDBPyConnection, scope: Scope, *, limit: int = 20) -> Table:
    return _dimension(
        conn, scope, key="by_project", column="project", title="维度：项目", limit=limit
    )

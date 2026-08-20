"""报告层：口径隔离、SQL 可复现、渲染不泄漏。"""

from __future__ import annotations

import json
from pathlib import Path

import duckdb
import pytest

from cmdaudit.models import RawCall
from cmdaudit.pipeline import build_records
from cmdaudit.report import queries as Q
from cmdaudit.report.build import build_tables, collect_coverage
from cmdaudit.report.render import render_json, render_markdown, render_table
from cmdaudit.report.scope import DURATION_GUARD, EXACT, STATUS_ONLY, UPPER_BOUND
from cmdaudit.store import write_commands

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def commands_db(tmp_path: Path) -> duckdb.DuckDBPyConnection:
    payload = json.loads((FIXTURES / "raw_calls.json").read_text(encoding="utf-8"))
    records = list(build_records(RawCall(**item) for item in payload))
    db_path = tmp_path / "commands.duckdb"
    write_commands(db_path, records)
    conn = duckdb.connect(str(db_path), read_only=True)
    yield conn
    conn.close()


def test_scope_filters_are_distinct() -> None:
    assert EXACT.sources == ("self_reported",)
    assert "turn_delta" in UPPER_BOUND.sources
    assert STATUS_ONLY.sql_filter == "TRUE"
    # 精确口径绝不含时间戳差值。
    assert "turn_delta" not in EXACT.sql_filter


def test_duration_guard_excludes_all_three_unusable_kinds() -> None:
    """batch_shared / unknown / truncated 三类都不得进耗时统计。"""
    assert "batch_shared" in DURATION_GUARD
    assert "unknown" in DURATION_GUARD
    assert "NOT duration_truncated" in DURATION_GUARD
    assert "duration_s IS NOT NULL" in DURATION_GUARD


def test_every_table_declares_its_scope(commands_db: duckdb.DuckDBPyConnection) -> None:
    for table in build_tables(commands_db):
        assert table.scope.name in {"exact", "upper_bound", "status_only"}
        assert table.scope.caveat
        assert table.sql.strip()
        assert table.columns


def test_duration_tables_never_use_status_only_scope(
    commands_db: duckdb.DuckDBPyConnection,
) -> None:
    """耗时表必须声明耗时口径，否则读者无法判断数字可信度。"""
    for table in build_tables(commands_db):
        if "total_s" in table.columns or "p50_s" in table.columns:
            assert table.scope.name != "status_only"
            assert table.scope.sources


def test_duration_queries_carry_the_guard(commands_db: duckdb.DuckDBPyConnection) -> None:
    for table in build_tables(commands_db):
        if "p50_s" in table.columns:
            assert "NOT duration_truncated" in table.sql


def test_table_sql_is_reproducible(commands_db: duckdb.DuckDBPyConnection) -> None:
    """报告里附的 SQL 必须真能跑出同样的行数。"""
    for table in build_tables(commands_db):
        rerun = commands_db.execute(table.sql).fetchall()
        assert len(rerun) == len(table.rows)


def test_coverage_accounts_for_every_status(commands_db: duckdb.DuckDBPyConnection) -> None:
    coverage = collect_coverage(commands_db)
    total = coverage["命令总数"]
    parts = (
        coverage["判定为成功"]
        + coverage["判定为失败"]
        + coverage["查无结果（非失败）"]
        + coverage["无状态证据"]
    )
    assert parts == total


def test_failure_rate_denominator_excludes_unknown_and_no_match(
    commands_db: duckdb.DuckDBPyConnection,
) -> None:
    table = Q.failure_rate_by_program(commands_db, STATUS_ONLY, min_runs=1)
    assert "status IN ('ok', 'failed')" in table.sql
    assert "no_match" not in table.sql.split("HAVING")[0].replace("status IN ('ok', 'failed')", "")


def test_render_table_includes_scope_and_sql(commands_db: duckdb.DuckDBPyConnection) -> None:
    table = Q.failure_by_kind_and_program(commands_db, STATUS_ONLY)
    rendered = render_table(table)
    assert table.scope.caveat in rendered
    assert "```sql" in rendered
    assert table.sql in rendered


def test_render_escapes_pipes_and_newlines(commands_db: duckdb.DuckDBPyConnection) -> None:
    """错误片段含换行与竖线会破坏 Markdown 表格。"""
    table = Q.failure_by_kind_and_program(commands_db, STATUS_ONLY)
    rendered = render_table(table)
    for line in rendered.splitlines():
        if line.startswith("|") and "---" not in line:
            assert "\n" not in line


def test_markdown_report_warns_against_cross_scope_addition(
    commands_db: duckdb.DuckDBPyConnection,
) -> None:
    markdown = render_markdown(
        tables=build_tables(commands_db),
        coverage=collect_coverage(commands_db),
        source_db="test.duckdb",
    )
    assert "不要跨表相加" in markdown
    assert "duration_truncated" in markdown
    # 三个口径各自成节，不混排。
    assert "## 失败分析" in markdown
    assert "## 耗时分析" in markdown


def test_json_report_is_machine_readable(commands_db: duckdb.DuckDBPyConnection) -> None:
    payload = json.loads(
        render_json(
            tables=build_tables(commands_db),
            coverage=collect_coverage(commands_db),
            source_db="test.duckdb",
        )
    )
    assert payload["source_db"] == "test.duckdb"
    assert payload["coverage"]["命令总数"] >= 1
    for table in payload["tables"]:
        assert table["scope"]["name"]
        assert table["scope"]["caveat"]
        assert table["sql"]


def test_report_never_leaks_credentials(commands_db: duckdb.DuckDBPyConnection) -> None:
    markdown = render_markdown(
        tables=build_tables(commands_db),
        coverage=collect_coverage(commands_db),
        source_db="test.duckdb",
    )
    assert "sk-ant-abcdefghij1234567890" not in markdown


def test_duration_table_uses_canonical_not_drain3_template(
    commands_db: duckdb.DuckDBPyConnection,
) -> None:
    """耗时榜必须能区分 `npm run build` 与 `npm run typecheck`。

    Drain3 把两者聚成 `npm run <*>`，那个粒度下答案没有可操作性。
    """
    table = Q.duration_by_template(commands_db, EXACT)
    assert "canonical" in table.columns
    assert "GROUP BY canonical" in table.sql
    assert "GROUP BY template" not in table.sql

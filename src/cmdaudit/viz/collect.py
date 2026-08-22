"""把 DuckDB 与 candidates.json 组装成 Payload。

聚合数字**完全复用** `report.queries`，不另写一套 SQL：Markdown 报告与页面
必须逐格一致，否则两份产物会给出不同的结论。可视化在此之上只加一件事 ——
每个聚合行预挂命令原文样本，让「这一行是哪些命令」可以当场回答。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Final

import duckdb

from cmdaudit.report import queries as Q
from cmdaudit.report.build import collect_coverage
from cmdaudit.report.queries import Table
from cmdaudit.report.scope import DURATION_GUARD, EXACT, STATUS_ONLY
from cmdaudit.viz.model import (
    Candidate,
    Dashboard,
    DurationProfile,
    Finding,
    FindingSignal,
    HeatCell,
    HistogramBin,
    Payload,
    Row,
    Sample,
    Section,
    SectionKind,
    TimelinePoint,
    Track,
)

#: 每个聚合行下钻展示的样本条数。再多会让页面体积失控且无助于判断。
SAMPLES_PER_ROW: Final[int] = 5

#: 候选队列展示上限。候选是假设不是结论，全量堆上来只会稀释注意力。
MAX_CANDIDATES: Final[int] = 24

#: 失败模式队列上限。本机数据里 1573 个 (template_id, failure_kind) 组合中
#: 1422 个只出现过一次，全量渲染只会把单次噪声和复发问题混在一起。
MAX_FINDINGS: Final[int] = 120

#: 进入队列的最低复发次数。1 次失败不足以称为「模式」。
MIN_FINDING_FAILURES: Final[int] = 2

#: 队列行内 sparkline 的回溯天数。
FINDING_SIGNAL_DAYS: Final[int] = 21

#: 耗时直方图的桶边界（秒）。边界按对数量级选取，覆盖亚秒到分钟级。
#: 最后一段为开区间，避免长尾把整张图压平。
_HISTOGRAM_EDGES: Final[tuple[float, ...]] = (
    0.0, 0.1, 0.25, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0, 60.0, 120.0,
)

#: 热力图回溯天数与 agent 上限。
HEATMAP_DAYS: Final[int] = 30
HEATMAP_AGENTS: Final[int] = 8

#: 样本里 error_snippet 的截断长度，避免单条日志撑爆页面。
_SNIPPET_CHARS: Final[int] = 240

_SAMPLE_COLUMNS: Final[str] = f"""
    command,
    agent,
    project,
    status,
    exit_code,
    duration_s,
    duration_source,
    failure_kind,
    substr(COALESCE(error_snippet, ''), 1, {_SNIPPET_CHARS}) AS snippet
""".strip()


class UnknownColumn(ValueError):
    """下钻列名不在 commands 表里。属于编程错误，不是用户输入问题。"""


def _table_columns(conn: duckdb.DuckDBPyConnection) -> frozenset[str]:
    return frozenset(str(row[0]) for row in conn.execute("DESCRIBE commands").fetchall())


def _sql_literal(value: Any) -> str:
    """只用于**展示**的字面量渲染。实际执行一律走参数绑定。"""
    if value is None:
        return "NULL"
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    if isinstance(value, int | float):
        return str(value)
    return "'" + str(value).replace("'", "''") + "'"


def _fetch_samples(
    conn: duckdb.DuckDBPyConnection,
    *,
    base_filter: str,
    keys: tuple[str, ...],
    values: tuple[Any, ...],
    order_by: str,
    known_columns: frozenset[str],
) -> tuple[tuple[Sample, ...], str]:
    """取一个聚合行对应的命令原文样本。

    列名来自本模块的封闭配置并对照 `DESCRIBE commands` 校验，值一律参数绑定，
    因此没有注入面。同一条命令原文只保留一次 —— 重复原文对判断没有增量。
    """
    conditions = [base_filter]
    params: list[Any] = []
    for key, value in zip(keys, values, strict=True):
        if key not in known_columns:
            raise UnknownColumn(key)
        if value is None:
            conditions.append(f"{key} IS NULL")
        else:
            conditions.append(f"{key} = ?")
            params.append(value)
    where = "\n  AND ".join(conditions)
    sql = f"""
SELECT {_SAMPLE_COLUMNS}
FROM commands
WHERE {where}
ORDER BY {order_by}
LIMIT {SAMPLES_PER_ROW * 6}
""".strip()

    rows = conn.execute(sql, params).fetchall()
    seen: set[str] = set()
    samples: list[Sample] = []
    for row in rows:
        command = str(row[0])
        if command in seen:
            continue
        seen.add(command)
        samples.append(
            Sample(
                command=command,
                agent=str(row[1]),
                project=str(row[2]),
                status=str(row[3]),
                exit_code=int(row[4]) if row[4] is not None else None,
                duration_s=float(row[5]) if row[5] is not None else None,
                duration_source=str(row[6]),
                failure_kind=str(row[7]) if row[7] is not None else None,
                error_snippet=str(row[8]).strip() or None,
            )
        )
        if len(samples) == SAMPLES_PER_ROW:
            break

    display_conditions = [base_filter]
    for key, value in zip(keys, values, strict=True):
        display_conditions.append(
            f"{key} IS NULL" if value is None else f"{key} = {_sql_literal(value)}"
        )
    display_sql = (
        f"SELECT {_SAMPLE_COLUMNS}\nFROM commands\nWHERE "
        + "\n  AND ".join(display_conditions)
        + f"\nORDER BY {order_by}\nLIMIT {SAMPLES_PER_ROW}"
    )
    return tuple(samples), display_sql


def _build_section(
    conn: duckdb.DuckDBPyConnection,
    table: Table,
    *,
    kind: SectionKind,
    bar_column: str | None,
    drill_keys: tuple[str, ...],
    base_filter: str,
    order_by: str,
    known_columns: frozenset[str],
) -> Section:
    index = {name: pos for pos, name in enumerate(table.columns)}
    bar_pos = index[bar_column] if bar_column else None

    magnitudes: list[float] = []
    if bar_pos is not None:
        for row in table.rows:
            value = row[bar_pos]
            magnitudes.append(float(value) if isinstance(value, int | float) else 0.0)
    peak = max(magnitudes, default=0.0)

    rows: list[Row] = []
    for position, raw in enumerate(table.rows):
        ratio = 0.0
        if bar_pos is not None and peak > 0:
            ratio = max(0.0, min(1.0, magnitudes[position] / peak))
        samples, drill_sql = _fetch_samples(
            conn,
            base_filter=base_filter,
            keys=drill_keys,
            values=tuple(raw[index[key]] for key in drill_keys),
            order_by=order_by,
            known_columns=known_columns,
        )
        rows.append(Row(cells=tuple(raw), bar_ratio=ratio, samples=samples, drill_sql=drill_sql))

    return Section(
        key=table.key,
        title=table.title,
        note=table.note,
        kind=kind,
        columns=table.columns,
        bar_column=bar_column,
        rows=tuple(rows),
        sql=table.sql,
    )


#: 失败线的下钻：按时间倒序，先看最近一次是什么样子。
_FAILURE_ORDER: Final[str] = "started_at DESC NULLS LAST"
#: 耗时线的下钻：按耗时倒序，先看最贵的那一次。
_DURATION_ORDER: Final[str] = "duration_s DESC NULLS LAST"
_FAILED_ONLY: Final[str] = "status = 'failed'"


def _failure_track(conn: duckdb.DuckDBPyConnection, known: frozenset[str]) -> Track:
    sections = (
        _build_section(
            conn,
            Q.failure_by_kind_and_program(conn, STATUS_ONLY),
            kind="bar",
            bar_column="failures",
            drill_keys=("failure_kind", "program"),
            base_filter=_FAILED_ONLY,
            order_by=_FAILURE_ORDER,
            known_columns=known,
        ),
        _build_section(
            conn,
            Q.failure_rate_by_program(conn, STATUS_ONLY),
            kind="bar",
            bar_column="failure_pct",
            drill_keys=("program",),
            base_filter=_FAILED_ONLY,
            order_by=_FAILURE_ORDER,
            known_columns=known,
        ),
        _build_section(
            conn,
            Q.timeout_and_network(conn, STATUS_ONLY),
            kind="bar",
            bar_column="failures",
            drill_keys=("failure_kind", "program"),
            base_filter=_FAILED_ONLY,
            order_by=_FAILURE_ORDER,
            known_columns=known,
        ),
    )
    return Track(
        key="failure",
        title="失败线",
        tone="failure",
        scope_name=STATUS_ONLY.name,
        caveat=STATUS_ONLY.caveat,
        lead=(
            "不依赖耗时证据，覆盖全部 agent，是主线。"
            "同一 program 反复以同一 failure_kind 失败，才值得写进 AGENTS.md。"
        ),
        sections=sections,
    )


def _duration_track(conn: duckdb.DuckDBPyConnection, known: frozenset[str]) -> Track:
    guard = f"{DURATION_GUARD.lstrip()} AND {EXACT.sql_filter}"
    dimension_specs = (
        (Q.by_group(conn, EXACT), "command_group"),
        (Q.by_program(conn, EXACT), "program"),
        (Q.by_agent(conn, EXACT), "agent"),
        (Q.by_project(conn, EXACT), "project"),
    )
    sections = [
        _build_section(
            conn,
            Q.duration_by_template(conn, EXACT),
            kind="bar",
            bar_column="total_s",
            drill_keys=("canonical",),
            base_filter=guard,
            order_by=_DURATION_ORDER,
            known_columns=known,
        )
    ]
    for table, column in dimension_specs:
        # 维度表的分组列在 SELECT 里统一别名成 bucket，下钻要还原成真实列名。
        sections.append(_rebind_bucket(conn, table, column, guard, known))
    return Track(
        key="duration",
        title="耗时线",
        tone="duration",
        scope_name=EXACT.name,
        caveat=EXACT.caveat,
        lead=(
            "只在进程自报墙钟上成立。本机这部分几乎全部来自 codex，"
            "结论不可外推到其他 agent，也不能与失败线的数字相加。"
        ),
        sections=tuple(sections),
    )


def _rebind_bucket(
    conn: duckdb.DuckDBPyConnection,
    table: Table,
    real_column: str,
    guard: str,
    known: frozenset[str],
) -> Section:
    """维度表把分组列统一别名成 `bucket`，下钻时要换回真实列名。"""
    renamed = Table(
        key=table.key,
        title=table.title,
        scope=table.scope,
        columns=(real_column,) + table.columns[1:],
        rows=table.rows,
        sql=table.sql,
        note=table.note,
    )
    return _build_section(
        conn,
        renamed,
        kind="bar",
        bar_column="total_s",
        drill_keys=(real_column,),
        base_filter=guard,
        order_by=_DURATION_ORDER,
        known_columns=known,
    )


def _load_candidates(path: Path | None) -> tuple[tuple[Candidate, ...], str, tuple[str, ...]]:
    if path is None or not path.is_file():
        return (), "", (
            "未找到 candidates.json，待验证队列为空。运行 `cmdaudit screen` 后重新生成。",
        )
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return (), "", (f"candidates.json 读取失败：{exc}",)

    entries = raw.get("candidates") if isinstance(raw, dict) else None
    if not isinstance(entries, list):
        return (), "", ("candidates.json 结构异常：缺少 candidates 数组。",)

    contract = raw.get("contract") if isinstance(raw, dict) else None
    note = ""
    if isinstance(contract, dict):
        parts = [str(value) for value in contract.values() if isinstance(value, str)]
        note = " ".join(parts)

    candidates: list[Candidate] = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        verification = entry.get("verification")
        design = ""
        if isinstance(verification, dict):
            design = str(verification.get("design", ""))
        observed = entry.get("observed")
        caveats = entry.get("caveats")
        priority = entry.get("priority")
        candidates.append(
            Candidate(
                candidate_id=str(entry.get("candidate_id", "")),
                source_rule=str(entry.get("source_rule", "")),
                command_shape=str(entry.get("command_shape", "")),
                priority=float(priority) if isinstance(priority, int | float) else 0.0,
                hypothesis=str(entry.get("hypothesis", "")),
                design=design,
                observed=observed if isinstance(observed, dict) else {},
                caveats=tuple(str(item) for item in caveats) if isinstance(caveats, list) else (),
            )
        )
    candidates.sort(key=lambda item: item.priority, reverse=True)
    return tuple(candidates[:MAX_CANDIDATES]), note, ()


def _heatmap(
    conn: duckdb.DuckDBPyConnection,
) -> tuple[tuple[HeatCell, ...], tuple[str, ...], tuple[str, ...]]:
    """agent × 自然日 的运行/失败矩阵。

    只返回**真实存在**的格子；agent 在某天没跑过命令时不产出 0 值格子，
    渲染层据此区分「跑了但没失败」与「压根没跑」—— 补零会把后者伪装成前者。
    """
    agents = tuple(
        str(row[0])
        for row in conn.execute(
            f"""SELECT agent, count(*) AS runs FROM commands
                WHERE try_cast(started_at AS TIMESTAMP) IS NOT NULL
                GROUP BY 1 ORDER BY 2 DESC, 1 LIMIT {HEATMAP_AGENTS}"""
        ).fetchall()
    )
    if not agents:
        return (), (), ()

    days = tuple(
        str(row[0])
        for row in conn.execute(
            f"""SELECT strftime(try_cast(started_at AS TIMESTAMP), '%Y-%m-%d') AS day
                FROM commands
                WHERE try_cast(started_at AS TIMESTAMP) IS NOT NULL
                GROUP BY 1 ORDER BY 1 DESC LIMIT {HEATMAP_DAYS}"""
        ).fetchall()
    )[::-1]
    if not days:
        return (), (), ()

    placeholders = ", ".join("?" for _ in agents)
    rows = conn.execute(
        f"""
        SELECT agent,
               strftime(try_cast(started_at AS TIMESTAMP), '%Y-%m-%d') AS day,
               count(*) AS runs,
               sum(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) AS failures
        FROM commands
        WHERE try_cast(started_at AS TIMESTAMP) IS NOT NULL
          AND agent IN ({placeholders})
          AND strftime(try_cast(started_at AS TIMESTAMP), '%Y-%m-%d') >= ?
        GROUP BY 1, 2
        ORDER BY 1, 2
        """,
        [*agents, days[0]],
    ).fetchall()
    cells = tuple(
        HeatCell(agent=str(a), day=str(d), runs=int(r), failures=int(f)) for a, d, r, f in rows
    )
    return cells, agents, days


def _duration_profile(conn: duckdb.DuckDBPyConnection) -> DurationProfile:
    """耗时分布 + 分位数。口径与报告分位数完全一致（DURATION_GUARD）。"""
    edges = _HISTOGRAM_EDGES
    cases = "\n               ".join(
        f"WHEN duration_s < {hi} THEN {pos}" for pos, hi in enumerate(edges[1:])
    )
    rows = conn.execute(
        f"""
        SELECT bucket, count(*) AS n FROM (
            SELECT CASE
               {cases}
               ELSE {len(edges) - 1}
            END AS bucket
            FROM commands
            WHERE {DURATION_GUARD}
        )
        GROUP BY 1 ORDER BY 1
        """
    ).fetchall()
    counts = dict((int(bucket), int(n)) for bucket, n in rows)
    bins = tuple(
        HistogramBin(
            lo=edges[pos],
            hi=edges[pos + 1] if pos + 1 < len(edges) else None,
            count=counts.get(pos, 0),
        )
        for pos in range(len(edges))
    )
    stats = conn.execute(
        f"""
        SELECT round(quantile_cont(duration_s, 0.50), 3),
               round(quantile_cont(duration_s, 0.90), 3),
               round(quantile_cont(duration_s, 0.99), 3),
               round(max(duration_s), 3),
               count(*)
        FROM commands WHERE {DURATION_GUARD}
        """
    ).fetchone()
    p50, p90, p99, max_s, size = stats if stats else (None, None, None, None, 0)
    return DurationProfile(
        bins=bins,
        p50=float(p50) if p50 is not None else None,
        p90=float(p90) if p90 is not None else None,
        p99=float(p99) if p99 is not None else None,
        max_s=float(max_s) if max_s is not None else None,
        sample_size=int(size or 0),
    )


def _findings_total(conn: duckdb.DuckDBPyConnection) -> int:
    """未截断的 finding 条数（与 `_findings` 同口径，去掉 LIMIT）。

    KPI 必须用它而不是 `len(findings)`：MAX_FINDINGS 截断时后者会静默少报。
    """
    row = conn.execute(
        f"""
        SELECT count(*) FROM (
            SELECT template_id, COALESCE(failure_kind, 'unknown') AS failure_kind
            FROM commands
            WHERE status = 'failed'
            GROUP BY 1, 2
            HAVING count(*) >= {MIN_FINDING_FAILURES}
        )
        """
    ).fetchone()
    return int(row[0]) if row else 0


def _findings(
    conn: duckdb.DuckDBPyConnection, known: frozenset[str]
) -> tuple[Finding, ...]:
    """失败模式队列：template_id × failure_kind。

    这是工作台的核心工作对象。只收录复发 >= MIN_FINDING_FAILURES 的组合 ——
    单次失败是事件不是模式，混进队列会让「待处理」永远清不完。
    `runs` 是该模板的**全部**执行次数（含成功），用于算失败率。
    """
    rows = conn.execute(
        f"""
        WITH failed AS (
            SELECT template_id,
                   COALESCE(failure_kind, 'unknown') AS failure_kind,
                   count(*) AS failures,
                   min(started_at) AS first_seen,
                   max(started_at) AS last_seen,
                   -- 每个 (template_id, failure_kind) 组取一条确定性代表行，
                   -- 它的 template/program 就是这个 finding 的展示值。
                   -- any_value 从哪一行取值不定，同批数据重复查询可能给不同模板。
                   first(template ORDER BY started_at NULLS LAST, call_id) AS template,
                   first(program  ORDER BY started_at NULLS LAST, call_id) AS program
            FROM commands
            WHERE status = 'failed'
            GROUP BY 1, 2
            HAVING count(*) >= {MIN_FINDING_FAILURES}
        ),
        totals AS (
            SELECT template_id, count(*) AS runs FROM commands GROUP BY 1
        )
        SELECT f.template_id, f.failure_kind, f.failures, f.template, f.program,
               f.first_seen, f.last_seen, COALESCE(t.runs, f.failures) AS runs
        FROM failed f LEFT JOIN totals t USING (template_id)
        ORDER BY f.failures DESC, f.template_id, f.failure_kind
        LIMIT {MAX_FINDINGS}
        """
    ).fetchall()

    findings: list[Finding] = []
    for tid, kind, failures, template, program, first_seen, last_seen, runs in rows:
        keys = ("template_id", "failure_kind")
        values: tuple[Any, ...] = (tid, kind if kind != "unknown" else None)
        samples, drill_sql = _fetch_samples(
            conn,
            base_filter="status = 'failed'",
            keys=keys,
            values=values,
            order_by="started_at DESC",
            known_columns=known,
        )
        kind_filter = (
            "failure_kind IS NULL" if kind == "unknown" else "failure_kind = ?"
        )
        params: list[Any] = [tid] if kind == "unknown" else [tid, kind]
        dims = conn.execute(
            f"""SELECT agent, project FROM commands
                WHERE status = 'failed' AND template_id = ? AND {kind_filter}
                GROUP BY 1, 2""",
            params,
        ).fetchall()
        signal_rows = conn.execute(
            f"""SELECT strftime(try_cast(started_at AS TIMESTAMP), '%Y-%m-%d') AS day,
                       count(*) AS failures
                FROM commands
                WHERE status = 'failed' AND template_id = ? AND {kind_filter}
                  AND try_cast(started_at AS TIMESTAMP) IS NOT NULL
                GROUP BY 1 ORDER BY 1 DESC LIMIT {FINDING_SIGNAL_DAYS}""",
            params,
        ).fetchall()
        findings.append(
            Finding(
                finding_id=f"{tid}:{kind}",
                template_id=str(tid),
                template=str(template or ""),
                failure_kind=str(kind),
                program=str(program or ""),
                failures=int(failures),
                runs=int(runs),
                agents=tuple(sorted({str(a) for a, _ in dims})),
                projects=tuple(sorted({str(pr) for _, pr in dims})),
                first_seen=str(first_seen) if first_seen else None,
                last_seen=str(last_seen) if last_seen else None,
                signal=tuple(
                    FindingSignal(day=str(day), failures=int(n))
                    for day, n in reversed(signal_rows)
                ),
                samples=samples,
                drill_sql=drill_sql,
            )
        )
    return tuple(findings)


def _dashboard(conn: duckdb.DuckDBPyConnection) -> Dashboard:
    """收集工作台概览；所有信号均由 commands 表实时聚合，不填充虚构时间点。"""
    timeline_rows = conn.execute(
        """
        SELECT strftime(try_cast(started_at AS TIMESTAMP), '%Y-%m-%d') AS day,
               count(*) AS runs,
               sum(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) AS failures,
               round(sum(CASE WHEN duration_source = 'self_reported'
                              AND duration_truncated = FALSE
                         THEN COALESCE(duration_s, 0) ELSE 0 END), 1) AS duration_s
        FROM commands
        WHERE try_cast(started_at AS TIMESTAMP) IS NOT NULL
        GROUP BY 1
        ORDER BY 1 DESC
        LIMIT 21
        """
    ).fetchall()
    timeline = tuple(
        TimelinePoint(
            day=str(day),
            runs=int(runs),
            failures=int(failures),
            duration_s=float(duration),
        )
        for day, runs, failures, duration in reversed(timeline_rows)
    )
    kinds = tuple(
        (str(kind) if kind is not None else 'unknown', int(count))
        for kind, count in conn.execute(
            """SELECT failure_kind, count(*) FROM commands WHERE status = 'failed'
               GROUP BY 1 ORDER BY 2 DESC, 1"""
        ).fetchall()
    )
    agents = tuple(
        (str(agent), int(count))
        for agent, count in conn.execute(
            "SELECT agent, count(*) FROM commands GROUP BY 1 ORDER BY 2 DESC, 1 LIMIT 6"
        ).fetchall()
    )
    # 空表时 fetchone() 可能返回 None，不能直接下标。
    latest_row = conn.execute("SELECT max(started_at) FROM commands").fetchone()
    latest = latest_row[0] if latest_row else None
    cells, heat_agents, heat_days = _heatmap(conn)
    return Dashboard(
        timeline=timeline,
        failures_by_kind=kinds,
        runs_by_agent=agents,
        latest_event_at=str(latest) if latest else None,
        heatmap=cells,
        heatmap_agents=heat_agents,
        heatmap_days=heat_days,
        duration_profile=_duration_profile(conn),
    )


def collect_payload(
    conn: duckdb.DuckDBPyConnection,
    *,
    source_db: str,
    generated_at: str,
    candidates_path: Path | None = None,
) -> Payload:
    known = _table_columns(conn)
    candidates, candidate_note, warnings = _load_candidates(candidates_path)
    return Payload(
        generated_at=generated_at,
        source_db=source_db,
        coverage=collect_coverage(conn),
        dashboard=_dashboard(conn),
        findings_total=_findings_total(conn),
        findings=_findings(conn, known),
        tracks=(_failure_track(conn, known), _duration_track(conn, known)),
        candidates=candidates,
        candidate_note=candidate_note,
        warnings=warnings,
    )

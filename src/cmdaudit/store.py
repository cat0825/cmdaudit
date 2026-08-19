"""DuckDB 落库。

只写 `--out-dir` 下的文件，不碰源库。
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator
from pathlib import Path
from typing import Any, Final

import duckdb

from cmdaudit.models import CommandRecord

SCHEMA: Final[str] = """
CREATE TABLE IF NOT EXISTS commands (
    session_id      VARCHAR NOT NULL,
    agent           VARCHAR NOT NULL,
    project         VARCHAR NOT NULL,
    call_id         BIGINT  NOT NULL,
    slot            INTEGER NOT NULL,
    started_at      VARCHAR,
    tool_name       VARCHAR NOT NULL,
    command         VARCHAR NOT NULL,
    workdir         VARCHAR,
    input_kind      VARCHAR NOT NULL,
    duration_s      DOUBLE,
    duration_source VARCHAR NOT NULL,
    -- 命令未跑完就被工具让出：耗时是下界，不得进耗时排名与分位数。
    duration_truncated BOOLEAN NOT NULL,
    exit_code       BIGINT,   -- Windows 会给出 0xC0000409 这类超出 INT32 的退出码
    status          VARCHAR NOT NULL,
    status_source   VARCHAR NOT NULL,
    failure_kind    VARCHAR,
    error_snippet   VARCHAR,
    program         VARCHAR NOT NULL,
    programs        VARCHAR NOT NULL,
    subcommand      VARCHAR,
    command_group   VARCHAR NOT NULL,
    parse_ok        BOOLEAN NOT NULL,
    template        VARCHAR NOT NULL,
    template_id     VARCHAR NOT NULL,
    redacted        BOOLEAN NOT NULL,
    PRIMARY KEY (call_id, slot)
);

CREATE TABLE IF NOT EXISTS extract_stats (
    key   VARCHAR PRIMARY KEY,
    value BIGINT NOT NULL
);
"""

_INSERT: Final[str] = """
INSERT OR REPLACE INTO commands VALUES (
    ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
)
"""

_BATCH: Final[int] = 2000


def _row(record: CommandRecord) -> tuple[Any, ...]:
    return (
        record.session_id,
        record.agent,
        record.project,
        record.call_id,
        record.slot,
        record.started_at,
        record.tool_name,
        record.command,
        record.workdir,
        record.input_kind,
        record.duration_s,
        record.duration_source,
        record.duration_truncated,
        record.exit_code,
        record.status,
        record.status_source,
        record.failure_kind,
        record.error_snippet,
        record.program,
        ",".join(record.programs),
        record.subcommand,
        record.command_group,
        record.parse_ok,
        record.template,
        record.template_id,
        record.redacted,
    )


def _chunks(items: Iterable[CommandRecord], size: int) -> Iterator[list[CommandRecord]]:
    batch: list[CommandRecord] = []
    for item in items:
        batch.append(item)
        if len(batch) >= size:
            yield batch
            batch = []
    if batch:
        yield batch


def write_commands(
    db_path: Path, records: Iterable[CommandRecord], *, reset: bool = True
) -> int:
    """落库并返回写入条数。"""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = duckdb.connect(str(db_path))
    try:
        conn.execute(SCHEMA)
        if reset:
            conn.execute("DELETE FROM commands")
        total = 0
        for batch in _chunks(records, _BATCH):
            conn.executemany(_INSERT, [_row(record) for record in batch])
            total += len(batch)
        return total
    finally:
        conn.close()


def write_stats(db_path: Path, stats: dict[str, int]) -> None:
    conn = duckdb.connect(str(db_path))
    try:
        conn.execute(SCHEMA)
        conn.execute("DELETE FROM extract_stats")
        conn.executemany(
            "INSERT INTO extract_stats VALUES (?, ?)", [(k, v) for k, v in stats.items()]
        )
    finally:
        conn.close()

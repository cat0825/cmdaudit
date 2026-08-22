"""agentsview 的 SQLite 会话库读取（只读）。

硬约束（docs/plan.md §0）：
- 以 `mode=ro` 打开，那是 agentsview 的生产库且有 daemon 在写；
- 启动时校验依赖的列是否存在，缺列直接报错而不是静默出错数；
- 不碰 agentsview 的 daemon、配置、进程。

`turn_delta` 的取法：同一 session 内 tool_call 所属 message 的时间戳，
与其后第一个有时间戳的 message 之差。同一 message 承载多条并发调用时，
这个差值是它们共享的，故只用于降级场景。
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from pathlib import Path
from typing import Final

from cmdaudit.models import RawCall

DEFAULT_DB_PATH: Final[Path] = Path.home() / ".agentsview" / "sessions.db"

#: 依赖的最小列集合，缺任何一列即报错。
_REQUIRED_COLUMNS: Final[dict[str, frozenset[str]]] = {
    "tool_calls": frozenset(
        {
            "id",
            "message_id",
            "session_id",
            "tool_name",
            "category",
            "tool_use_id",
            "input_json",
            "result_content",
            "call_index",
        }
    ),
    "messages": frozenset({"id", "session_id", "ordinal", "timestamp"}),
    "sessions": frozenset({"id", "agent", "project"}),
    "tool_result_events": frozenset({"session_id", "tool_use_id", "status"}),
}

#: 同一个 tool_use_id 可能有多条 result event（重试/续传），状态要按失败优先聚合。
#: `min(status)` 按字典序会让 `min('completed','errored') == 'completed'`，
#: 歧义事件偏成功。这里显式映射成整数优先级再取最高：
#: errored/failed/error/failure > interrupted/aborted > completed/success/ok > 未知。
#: 未知值保留原字符串给下游单独可观测，不静默归成功。
_STATUS_PRIORITY: Final[str] = """
CASE
    WHEN lower(status) IN ('errored', 'error', 'failed', 'failure') THEN 3
    WHEN lower(status) IN ('interrupted', 'aborted') THEN 2
    WHEN lower(status) IN ('completed', 'success', 'ok') THEN 1
    ELSE 0
END
"""

_QUERY: Final[str] = """
WITH turn AS (
    SELECT
        m.id        AS message_id,
        m.ordinal   AS ordinal,
        m.timestamp AS started_at,
        LEAD(m.timestamp) OVER (
            PARTITION BY m.session_id ORDER BY m.ordinal
        )           AS ended_at
    FROM messages AS m
),
res AS (
    SELECT tool_use_id, status
    FROM (
        SELECT tool_use_id, status,
               ROW_NUMBER() OVER (
                   PARTITION BY tool_use_id
                   ORDER BY """ + _STATUS_PRIORITY + """ DESC, rowid DESC
               ) AS rn
        FROM tool_result_events
        WHERE tool_use_id IS NOT NULL
          AND status IS NOT NULL
          AND status != ''
    )
    WHERE rn = 1
)
SELECT
    tc.id,
    tc.session_id,
    COALESCE(s.agent, '')      AS agent,
    COALESCE(s.project, '')    AS project,
    COALESCE(turn.ordinal, -1) AS ordinal,
    COALESCE(tc.call_index, 0) AS call_index,
    tc.tool_name,
    tc.tool_use_id,
    tc.input_json,
    tc.result_content,
    res.status                 AS result_status,
    turn.started_at,
    turn.ended_at
FROM tool_calls AS tc
LEFT JOIN turn ON turn.message_id = tc.message_id
LEFT JOIN res  ON res.tool_use_id = tc.tool_use_id
LEFT JOIN sessions AS s ON s.id = tc.session_id
WHERE tc.category = 'Bash'
ORDER BY tc.id
"""


class SchemaMismatch(RuntimeError):
    """源库缺少必需列。不静默降级，避免出错数。"""


def _table_columns(conn: sqlite3.Connection, table: str) -> frozenset[str]:
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return frozenset(str(row[1]) for row in rows)


def open_readonly(db_path: Path = DEFAULT_DB_PATH) -> sqlite3.Connection:
    """只读打开并校验 schema。"""
    if not db_path.exists():
        raise FileNotFoundError(f"找不到会话库：{db_path}")
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    for table, required in _REQUIRED_COLUMNS.items():
        present = _table_columns(conn, table)
        if not present:
            conn.close()
            raise SchemaMismatch(f"源库缺少表 {table}")
        missing = required - present
        if missing:
            conn.close()
            raise SchemaMismatch(f"源库表 {table} 缺少列：{sorted(missing)}")
    return conn


def count_bash_calls(conn: sqlite3.Connection) -> int:
    row = conn.execute("SELECT count(*) FROM tool_calls WHERE category = 'Bash'").fetchone()
    return int(row[0])


def iter_raw_calls(conn: sqlite3.Connection, *, limit: int | None = None) -> Iterator[RawCall]:
    """按 tool_call id 升序流式读出候选调用。"""
    cursor = conn.execute(_QUERY)
    for emitted, row in enumerate(cursor, start=1):
        yield RawCall(
            call_id=int(row["id"]),
            session_id=str(row["session_id"]),
            agent=str(row["agent"]),
            project=str(row["project"]),
            message_ordinal=int(row["ordinal"]),
            call_index=int(row["call_index"]),
            tool_name=str(row["tool_name"]),
            tool_use_id=row["tool_use_id"],
            input_json=row["input_json"],
            result_content=row["result_content"],
            result_status=row["result_status"],
            started_at=row["started_at"],
            ended_at=row["ended_at"],
        )
        if limit is not None and emitted >= limit:
            return

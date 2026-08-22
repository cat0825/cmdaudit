"""源库读取：只读约束与 schema 校验。

用临时 SQLite 构造最小 schema，不碰真实的 ~/.agentsview/sessions.db。
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from cmdaudit.sources.agentsview import (
    SchemaMismatch,
    count_bash_calls,
    iter_raw_calls,
    open_readonly,
)

_MINIMAL_SCHEMA = """
CREATE TABLE sessions (
    id TEXT PRIMARY KEY, project TEXT NOT NULL, agent TEXT NOT NULL
);
CREATE TABLE messages (
    id INTEGER PRIMARY KEY, session_id TEXT NOT NULL, ordinal INTEGER NOT NULL,
    timestamp TEXT, has_tool_use INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE tool_calls (
    id INTEGER PRIMARY KEY, message_id INTEGER NOT NULL, session_id TEXT NOT NULL,
    tool_name TEXT NOT NULL, category TEXT NOT NULL, tool_use_id TEXT,
    input_json TEXT, result_content TEXT, call_index INTEGER
);
CREATE TABLE tool_result_events (
    id INTEGER PRIMARY KEY, session_id TEXT NOT NULL, tool_use_id TEXT, status TEXT NOT NULL
);
"""


def _build_db(path: Path) -> None:
    conn = sqlite3.connect(path)
    try:
        conn.executescript(_MINIMAL_SCHEMA)
        conn.execute("INSERT INTO sessions VALUES ('s1', 'demo', 'codex')")
        conn.executemany(
            "INSERT INTO messages VALUES (?, ?, ?, ?, ?)",
            [
                (1, "s1", 10, "2026-08-19T10:00:00Z", 1),
                (2, "s1", 11, "2026-08-19T10:00:05Z", 1),
                (3, "s1", 12, "2026-08-19T10:00:09Z", 0),
            ],
        )
        conn.executemany(
            "INSERT INTO tool_calls VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                (1, 1, "s1", "exec_command", "Bash", "t1", '{"cmd":"pwd"}', "ok", 0),
                (2, 2, "s1", "Bash", "Bash", "t2", '{"command":"ls"}', "ok", 0),
                (3, 2, "s1", "Read", "File", "t3", '{"file_path":"/a"}', "ok", 1),
            ],
        )
        conn.execute("INSERT INTO tool_result_events VALUES (1, 's1', 't2', 'completed')")
        conn.commit()
    finally:
        conn.close()


def test_missing_file_raises(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        open_readonly(tmp_path / "absent.db")


def test_missing_column_raises_instead_of_silently_degrading(tmp_path: Path) -> None:
    path = tmp_path / "broken.db"
    conn = sqlite3.connect(path)
    try:
        conn.executescript(_MINIMAL_SCHEMA.replace(", result_content TEXT", ""))
        conn.commit()
    finally:
        conn.close()
    with pytest.raises(SchemaMismatch, match="result_content"):
        open_readonly(path)


def test_reads_only_bash_calls_with_turn_timestamps(tmp_path: Path) -> None:
    path = tmp_path / "sessions.db"
    _build_db(path)
    conn = open_readonly(path)
    try:
        assert count_bash_calls(conn) == 2
        calls = list(iter_raw_calls(conn))
    finally:
        conn.close()

    assert [call.call_id for call in calls] == [1, 2]
    assert calls[0].agent == "codex"
    assert calls[0].project == "demo"
    # LEAD 窗口给出同 session 的下一个时间戳。
    assert calls[0].started_at == "2026-08-19T10:00:00Z"
    assert calls[0].ended_at == "2026-08-19T10:00:05Z"
    # 预聚合的 result event 状态。
    assert calls[1].result_status == "completed"
    assert calls[0].result_status is None


def test_limit_stops_early(tmp_path: Path) -> None:
    path = tmp_path / "sessions.db"
    _build_db(path)
    conn = open_readonly(path)
    try:
        assert len(list(iter_raw_calls(conn, limit=1))) == 1
    finally:
        conn.close()


def test_status_aggregation_is_failure_biased(tmp_path: Path) -> None:
    """同一个 tool_use_id 的多条 result event 按失败优先聚合，不再 min(status)。

    `min(status)` 按字典序会让 `min('completed','errored') == 'completed'`，
    歧义事件偏成功。这里必须偏失败。
    """
    path = tmp_path / "sessions.db"
    _build_db(path)
    conn = sqlite3.connect(path)
    try:
        # 三个事件都挂 t1：completed < interrupted < errored，应取 errored。
        conn.executemany(
            "INSERT INTO tool_result_events VALUES (?, 's1', 't1', ?)",
            [(2, "completed"), (3, "interrupted"), (4, "errored")],
        )
        # success + failed 应取 failed。
        conn.executemany(
            "INSERT INTO tool_result_events VALUES (?, 's1', 't2', ?)",
            [(5, "success"), (6, "failed")],
        )
        # 空状态事件不产生证据，聚合结果应为 NULL，不得被当成成功。
        conn.execute("INSERT INTO tool_result_events VALUES (7, 's1', 't4', '')")
        conn.execute(
            "INSERT INTO tool_calls VALUES (4, 3, 's1', 'Bash', 'Bash', 't4', "
            "'{\"command\":\"ls\"}', 'ok', 0)"
        )
        conn.commit()
    finally:
        conn.close()

    conn = open_readonly(path)
    try:
        calls = list(iter_raw_calls(conn))
    finally:
        conn.close()

    by_id = {call.call_id: call for call in calls}
    assert by_id[1].result_status == "errored"
    assert by_id[2].result_status == "failed"
    assert by_id[4].result_status is None

def test_connection_is_read_only(tmp_path: Path) -> None:
    path = tmp_path / "sessions.db"
    _build_db(path)
    conn = open_readonly(path)
    try:
        with pytest.raises(sqlite3.OperationalError):
            conn.execute("DELETE FROM tool_calls")
    finally:
        conn.close()

"""commands.duckdb 的只读打开。

report 与 screen 共用，避免两处各写一份。
"""

from __future__ import annotations

from pathlib import Path

import duckdb


def open_commands_db(db_path: Path) -> duckdb.DuckDBPyConnection:
    """只读打开抽取结果。缺文件时给出可执行的下一步而不是栈回溯。"""
    if not db_path.exists():
        raise FileNotFoundError(f"找不到 {db_path}，先跑 `cmdaudit extract`")
    return duckdb.connect(str(db_path), read_only=True)

"""端到端组装：RawCall → CommandRecord，含落库回归。"""

from __future__ import annotations

import json
from pathlib import Path

import duckdb
import pytest

from cmdaudit.models import RawCall
from cmdaudit.pipeline import ExtractStats, build_records, turn_delta_seconds
from cmdaudit.store import write_commands, write_stats

FIXTURES = Path(__file__).parent / "fixtures"


def load_fixture(name: str) -> list[RawCall]:
    payload = json.loads((FIXTURES / name).read_text(encoding="utf-8"))
    return [RawCall(**item) for item in payload]


def test_turn_delta_seconds() -> None:
    delta = turn_delta_seconds("2026-07-07T03:51:32.729784Z", "2026-07-07T03:51:35.333745Z")
    assert delta == pytest.approx(2.603961)
    assert turn_delta_seconds(None, "2026-07-07T03:51:35Z") is None
    assert turn_delta_seconds("2026-07-07T03:51:35Z", None) is None
    # 负差值不可信。
    assert turn_delta_seconds("2026-07-07T03:51:35Z", "2026-07-07T03:51:30Z") is None
    assert turn_delta_seconds("garbage", "also garbage") is None


def test_records_from_fixture() -> None:
    stats = ExtractStats()
    records = list(build_records(load_fixture("raw_calls.json"), stats=stats))

    by_command = {record.command: record for record in records}

    ok = by_command["pwd"]
    assert ok.status == "ok"
    assert ok.duration_source == "self_reported"
    assert ok.command_group == "shell_noop"

    failed = by_command["git push origin main"]
    assert failed.status == "failed"
    assert failed.exit_code == 128
    assert failed.failure_kind == "network"
    assert failed.command_group == "vcs"

    waited = by_command["sleep 180; tail -5 /tmp/task.log"]
    assert waited.command_group == "wait"
    assert waited.program == "sleep"

    # 排除项都记了数，能在报告里解释去向。
    assert stats.excluded_tool == 1
    assert stats.no_command_key == 1
    assert stats.commands == len(records)


def test_batch_script_yields_per_slot_records() -> None:
    records = list(build_records(load_fixture("raw_calls.json")))
    batch = sorted(
        (record for record in records if record.input_kind == "js_script"),
        key=lambda record: record.slot,
    )
    assert [record.command for record in batch] == ["echo one", "echo two"]
    assert [record.slot for record in batch] == [0, 1]
    assert {record.duration_source for record in batch} == {"self_reported"}


def test_secrets_never_reach_records() -> None:
    records = list(build_records(load_fixture("raw_calls.json")))
    leaked = [record for record in records if "sk-ant-" in record.command]
    assert leaked == []
    redacted = [record for record in records if record.redacted]
    assert redacted
    assert all("REDACTED" in record.command for record in redacted)


def test_no_record_violates_the_exit_code_invariant() -> None:
    records = list(build_records(load_fixture("raw_calls.json")))
    assert [r for r in records if r.exit_code == 0 and r.status == "failed"] == []
    assert all(r.duration_source for r in records)
    assert all(r.program for r in records)


def test_roundtrip_through_duckdb(tmp_path: Path) -> None:
    db_path = tmp_path / "commands.duckdb"
    records = list(build_records(load_fixture("raw_calls.json")))
    written = write_commands(db_path, records)
    assert written == len(records)

    conn = duckdb.connect(str(db_path), read_only=True)
    try:
        total = conn.execute("SELECT count(*) FROM commands").fetchone()
        assert total is not None
        assert total[0] == len(records)
        violations = conn.execute(
            "SELECT count(*) FROM commands WHERE exit_code = 0 AND status = 'failed'"
        ).fetchone()
        assert violations is not None
        assert violations[0] == 0
    finally:
        conn.close()


def test_windows_exit_code_does_not_overflow(tmp_path: Path) -> None:
    """0xC0000409 超出 INT32，列类型必须是 BIGINT。"""
    db_path = tmp_path / "wide.duckdb"
    call = RawCall(
        call_id=1,
        session_id="s",
        agent="codex",
        project="p",
        message_ordinal=1,
        call_index=0,
        tool_name="run_command",
        tool_use_id="t1",
        input_json='{"CommandLine":"node crash.js"}',
        result_content="Process exited with code 3221226505",
        result_status=None,
        started_at=None,
        ended_at=None,
    )
    records = list(build_records([call]))
    assert records[0].exit_code == 3221226505
    assert write_commands(db_path, records) == 1


def test_stats_are_persisted(tmp_path: Path) -> None:
    db_path = tmp_path / "stats.duckdb"
    write_commands(db_path, [])
    write_stats(db_path, {"raw_calls": 7, "commands": 3})
    conn = duckdb.connect(str(db_path), read_only=True)
    try:
        rows = dict(conn.execute("SELECT key, value FROM extract_stats").fetchall())
    finally:
        conn.close()
    assert rows == {"raw_calls": 7, "commands": 3}

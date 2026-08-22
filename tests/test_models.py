"""CommandRecord 构造期不变量。

与 Duration / Outcome 同一套写法：非法状态不可表达。每条非法组合
都在构造时抛 ValueError，而不是落库后才发现。
"""

from __future__ import annotations

import pytest

from cmdaudit.models import CommandRecord


def _record(**overrides: object) -> CommandRecord:
    payload: dict[str, object] = {
        "session_id": "s",
        "agent": "codex",
        "project": "p",
        "call_id": 1,
        "slot": 0,
        "started_at": None,
        "tool_name": "exec_command",
        "command": "pwd",
        "workdir": None,
        "input_kind": "cmd",
        "duration_s": None,
        "duration_source": "unknown",
        "duration_truncated": False,
        "exit_code": None,
        "status": "unknown",
        "status_source": "none",
        "failure_kind": None,
        "error_snippet": None,
        "program": "pwd",
        "programs": ("pwd",),
        "subcommand": None,
        "command_group": "shell_noop",
        "parse_ok": True,
    }
    payload.update(overrides)
    return CommandRecord(**payload)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("overrides", "match"),
    [
        ({"status": "bogus"}, "未知 status"),
        ({"duration_source": "bogus"}, "未知 duration_source"),
        ({"status_source": "bogus"}, "未知 status_source"),
        ({"failure_kind": "bogus", "status": "failed"}, "未知 failure_kind"),
        # duration_s 与 duration_source 必须配对。
        ({"duration_s": 1.0, "duration_source": "unknown"}, "不能为 unknown"),
        ({"duration_s": None, "duration_source": "self_reported"}, "必须为 unknown"),
        ({"duration_s": -1.0, "duration_source": "self_reported"}, "不能为负"),
        # status 与 failure_kind 必须配对。
        ({"status": "ok", "failure_kind": "timeout"}, "只有 failed"),
        ({"status": "failed", "failure_kind": None}, "必须带 failure_kind"),
        # 红线：exit_code=0 只能是 ok。
        ({"exit_code": 0, "status": "failed", "failure_kind": "network"}, "exit_code=0"),
        ({"exit_code": 0, "status": "no_match"}, "exit_code=0"),
        ({"slot": -1}, "slot 不能为负"),
    ],
)
def test_invalid_command_records_raise(overrides: dict[str, object], match: str) -> None:
    with pytest.raises(ValueError, match=match):
        _record(**overrides)


def test_valid_records_construct() -> None:
    ok = _record(exit_code=0, status="ok", status_source="exit_code")
    assert ok.status == "ok"
    failed = _record(
        duration_s=3.2,
        duration_source="self_reported",
        exit_code=128,
        status="failed",
        status_source="exit_code",
        failure_kind="network",
    )
    assert failed.failure_kind == "network"


def test_tags_field_has_been_removed() -> None:
    """tags 是死字段（pipeline 不传、store/schema 不写），构造期就该没有它。"""
    record = _record()
    assert not hasattr(record, "tags")

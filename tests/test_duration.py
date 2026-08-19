"""耗时四级降级，含两个实测踩出来的解析陷阱。"""

from __future__ import annotations

from cmdaudit.extract.duration import (
    TURN_DELTA_CEILING_S,
    parse_inner_wall_times,
    parse_outer_wall_time,
    resolve_durations,
)

# 新格式：有冒号。
NEW_FORMAT = "Chunk ID: a40592\nWall time: 0.0516 seconds\nProcess exited with code 0\n"
# 旧格式：无冒号，且内层 JSON 是转义的。
OLD_FORMAT = (
    '[{"type":"input_text","text":"Script completed\\nWall time 1.2 seconds\\nOutput:\\n"},'
    '{"text":"{\\"chunk_id\\":\\"ed69ad\\",\\"wall_time_seconds\\":1.002315041,\\"exit_code\\":0}"},'
    '{"text":"{\\"chunk_id\\":\\"57f7bd\\",\\"wall_time_seconds\\":0.19,\\"exit_code\\":0}"}]'
)


def test_outer_wall_time_accepts_both_formats() -> None:
    assert parse_outer_wall_time(NEW_FORMAT) == 0.0516
    assert parse_outer_wall_time(OLD_FORMAT) == 1.2


def test_wall_time_without_colon_is_matched() -> None:
    assert parse_outer_wall_time("Wall time 12.5 seconds") == 12.5


def test_inner_wall_times_survive_json_escaping() -> None:
    assert parse_inner_wall_times(OLD_FORMAT) == [1.002315041, 0.19]


def test_inner_wall_times_handle_scientific_notation() -> None:
    assert parse_inner_wall_times('\\"wall_time_seconds\\":1.3e-05') == [1.3e-05]


def test_single_command_prefers_self_reported() -> None:
    [duration] = resolve_durations(NEW_FORMAT, 1, 99.0)
    assert duration.source == "self_reported"
    assert duration.seconds == 0.0516


def test_batch_with_matching_inner_count_is_exact() -> None:
    durations = resolve_durations(OLD_FORMAT, 2, None)
    assert [d.source for d in durations] == ["self_reported", "self_reported"]
    assert [d.seconds for d in durations] == [1.002315041, 0.19]


def test_batch_with_mismatched_count_falls_back_to_shared() -> None:
    durations = resolve_durations(OLD_FORMAT, 3, None)
    assert {d.source for d in durations} == {"batch_shared"}
    # 共享总墙钟，不均摊：均摊会让每条数据都是错的。
    assert [d.seconds for d in durations] == [1.2, 1.2, 1.2]


def test_batch_without_any_wall_time_is_unknown() -> None:
    durations = resolve_durations("no timing here", 2, None)
    assert {d.source for d in durations} == {"unknown"}
    assert all(d.seconds is None for d in durations)


def test_turn_delta_is_used_when_no_self_report() -> None:
    [duration] = resolve_durations("no timing", 1, 12.5)
    assert duration.source == "turn_delta"
    assert duration.seconds == 12.5


def test_turn_delta_beyond_ceiling_is_rejected() -> None:
    """时间戳差值含模型思考与用户离开的时间，超限的不是命令耗时。"""
    [duration] = resolve_durations("no timing", 1, TURN_DELTA_CEILING_S + 1)
    assert duration.source == "unknown"
    assert duration.seconds is None


def test_no_evidence_yields_unknown() -> None:
    [duration] = resolve_durations(None, 1, None)
    assert duration.source == "unknown"


def test_zero_slots_returns_empty() -> None:
    assert resolve_durations(NEW_FORMAT, 0, None) == []

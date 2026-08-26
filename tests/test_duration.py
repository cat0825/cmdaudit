"""耗时四级降级，含两个实测踩出来的解析陷阱。"""

from __future__ import annotations

from cmdaudit.extract.duration import (
    TURN_DELTA_CEILING_S,
    UNKNOWN,
    YIELD_CEILING_S,
    TruncationPolicy,
    looks_truncated,
    parse_inner_wall_times,
    parse_outer_wall_time,
    resolve_durations,
)
from cmdaudit.models import Duration

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


def test_background_session_marker_counts_as_truncated() -> None:
    """`gh pr checks --watch` 被挂到后台会话时输出以 SESSION_ID= 结尾。

    工具侧会把这次调用标记为 completed，但命令并没有退出，
    自报的 30 秒只是让出时刻。不标记会让耗时榜把它当真实耗时。
    """
    text = "quality\tpending\t0\thttps://example.test/job/1\nSESSION_ID=91282"
    assert looks_truncated(text, None) is True


def test_exit_code_wins_over_session_marker() -> None:
    """有退出码就说明命令确实结束了，即使输出里提到 session。"""
    assert looks_truncated("SESSION_ID=1\nProcess exited with code 0", 0) is False


def test_normal_completion_is_not_truncated() -> None:
    assert looks_truncated("Wall time: 1.0 seconds\nProcess exited with code 0", 0) is False


def test_duration_at_yield_ceiling_without_exit_code_is_truncated() -> None:
    """贴着让出上限又没有退出码：命令没退出，30 秒只是让出时刻。

    阈值有数据支撑：无退出码的自报耗时里 >=29.9s 有 632 条，
    而 20-29.9s 只有 69 条。这个断崖说明 30 秒是上限不是真实分布。
    """
    assert looks_truncated("some output", None, YIELD_CEILING_S) is True
    assert looks_truncated("some output", None, 30.2) is True


def test_duration_at_ceiling_with_exit_code_is_trusted() -> None:
    """有退出码就是真跑完了，哪怕耗时正好贴着上限。"""
    assert looks_truncated("Process exited with code 0", 0, 30.0) is False


def test_duration_below_ceiling_without_exit_code_is_not_truncated() -> None:
    """没到上限就没有截断的理由，不能只因为缺退出码就判截断。"""
    assert looks_truncated("some output", None, 5.0) is False


def test_mark_truncated_preserves_unknown_durations() -> None:
    from cmdaudit.extract.duration import mark_truncated

    durations = [Duration(1.0, "self_reported"), UNKNOWN]
    marked = mark_truncated(durations, truncated=True)
    assert marked[0].truncated is True
    assert marked[1].source == "unknown"
    assert marked[1].truncated is False


def test_mark_truncated_is_a_noop_when_not_truncated() -> None:
    from cmdaudit.extract.duration import mark_truncated

    durations = [Duration(1.0, "self_reported")]
    assert mark_truncated(durations, truncated=False) == durations


# --- issue #30: 让出上限可配置，直接证据优先 ---


def test_ceiling_is_configurable() -> None:
    """10s / 60s 配置下阈值跟着变，不再写死 29.9。"""
    ten = TruncationPolicy(yield_ceiling_s=10.0)
    sixty = TruncationPolicy(yield_ceiling_s=60.0)
    assert looks_truncated("some output", None, 12.0, policy=ten) is True
    assert looks_truncated("some output", None, 12.0, policy=sixty) is False
    assert looks_truncated("some output", None, 61.0, policy=sixty) is True


def test_ceiling_can_be_disabled() -> None:
    """关掉纯耗时兜底后只认直接证据。换 agent 时这是最安全的配置。"""
    off = TruncationPolicy(yield_ceiling_s=None)
    assert looks_truncated("some output", None, 3600.0, policy=off) is False
    assert looks_truncated("still running", None, 1.0, policy=off) is True


def test_direct_evidence_beats_ceiling() -> None:
    """直接证据不依赖阈值：耗时远低于上限也照样标截断。"""
    assert looks_truncated("SESSION_ID=abc", None, 0.5) is True


def test_explicit_exit_wins_over_everything() -> None:
    """长命令已明确退出：既不看直接证据也不看阈值。"""
    assert looks_truncated("still running", 0, 120.0) is False
    assert looks_truncated("still running", 1, 120.0) is False


def test_policy_is_recorded_for_artifacts() -> None:
    """产物必须能说出自己是按什么策略标的。"""
    assert TruncationPolicy().as_dict() == {
        "truncation_strategy": "direct_evidence_then_ceiling",
        "yield_ceiling_s": YIELD_CEILING_S,
    }
    assert TruncationPolicy(yield_ceiling_s=None).as_dict() == {
        "truncation_strategy": "direct_evidence_only",
        "yield_ceiling_s": None,
    }

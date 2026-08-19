"""耗时四级降级（docs/plan.md §3.2）。

两个实测踩出来的陷阱，写在正则里：

1. 外层墙钟有两种格式：新格式 `Wall time: 0.05 seconds`（有冒号），
   旧格式 `Wall time 1.2 seconds`（无冒号）。正则里冒号必须是可选的。
2. 旧格式 JS 脚本的 `result_content` 里嵌的是转义 JSON，
   键名实际长这样 `\\"wall_time_seconds\\":1.002`，
   直接匹配 `"wall_time_seconds"` 会全部漏掉。
"""

from __future__ import annotations

import re
from typing import Final

from cmdaudit.models import Duration

#: 外层自报墙钟，冒号可选。
RE_WALL_TIME: Final[re.Pattern[str]] = re.compile(
    r"Wall time:?\s*([0-9]+(?:\.[0-9]+)?)\s*seconds", re.IGNORECASE
)

#: 内层逐条墙钟，允许键名两侧有任意个反斜杠或引号。
RE_INNER_WALL: Final[re.Pattern[str]] = re.compile(
    r"wall_time_seconds[\\\"']*\s*:\s*([0-9]+(?:\.[0-9]+)?(?:e-?[0-9]+)?)", re.IGNORECASE
)

UNKNOWN: Final[Duration] = Duration(seconds=None, source="unknown")

#: `turn_delta` 的可信上限（秒）。时间戳差值包含模型思考与用户离开的时间，
#: 不等于命令耗时。实测最大值 39087s（约 10.9 小时）显然是会话空闲，
#: 超过这个阈值的差值不可信，降级为 unknown 而不是当成命令耗时。
#: 阈值取 300s：自报耗时的 p99 是 30s、最大值 43s，300s 已经宽出一个数量级。
TURN_DELTA_CEILING_S: Final[float] = 300.0


def parse_outer_wall_time(result_content: str | None) -> float | None:
    """外层总墙钟。一个 result 里可能出现多次，取第一个。"""
    if not result_content:
        return None
    m = RE_WALL_TIME.search(result_content)
    return float(m.group(1)) if m else None


def parse_inner_wall_times(result_content: str | None) -> list[float]:
    """内层逐条墙钟，按出现顺序。"""
    if not result_content:
        return []
    return [float(m.group(1)) for m in RE_INNER_WALL.finditer(result_content)]


def _trusted_delta(turn_delta_s: float | None) -> float | None:
    """时间戳差值只在可信区间内使用。"""
    if turn_delta_s is None or turn_delta_s > TURN_DELTA_CEILING_S:
        return None
    return turn_delta_s


def resolve_durations(
    result_content: str | None,
    slot_count: int,
    turn_delta_s: float | None,
) -> list[Duration]:
    """为同一个 tool_call 里的 slot_count 条命令各定一个耗时。

    判定顺序：
    1. 单条命令且有外层墙钟 → `self_reported`；
    2. 多条命令且内层墙钟数量恰好等于命令数 → 逐条 `self_reported`；
    3. 多条命令但数量不匹配/缺失 → 全部 `batch_shared`（共享外层总墙钟）；
    4. 无自报值但有可信的 turn 时间戳差值 → `turn_delta`
       （超过 TURN_DELTA_CEILING_S 的差值视为会话空闲，不采用）；
    5. 都没有 → `unknown`。

    `batch_shared` 的值故意保留为总墙钟而不均摊：均摊会让每条数据都是错的，
    报告层按 `duration_source` 把它排除出分位数统计。
    """
    if slot_count <= 0:
        return []

    inner = parse_inner_wall_times(result_content)
    outer = parse_outer_wall_time(result_content)
    delta = _trusted_delta(turn_delta_s)

    if slot_count == 1:
        if inner and len(inner) == 1:
            return [Duration(inner[0], "self_reported")]
        if outer is not None:
            return [Duration(outer, "self_reported")]
        if delta is not None:
            return [Duration(delta, "turn_delta")]
        return [UNKNOWN]

    if len(inner) == slot_count:
        return [Duration(v, "self_reported") for v in inner]

    shared = outer if outer is not None else delta
    if shared is None:
        return [UNKNOWN] * slot_count
    return [Duration(shared, "batch_shared")] * slot_count

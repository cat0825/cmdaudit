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
from dataclasses import dataclass
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

#: 进程未退出的标记。工具的 `yield_time_ms` 到点会让出，命令仍在后台跑，
#: 此时自报墙钟只记到让出那一刻，是耗时的下界而非耗时。
#: 实测 612 条自报耗时聚集在 30.0-30.5s（工具默认让出上限），
#: 其中 473 条没有退出码 —— 命令确实没跑完。不标记会系统性低估长命令。
RE_STILL_RUNNING: Final[re.Pattern[str]] = re.compile(
    r"(?:still running|process (?:is )?running|"
    r"session id|SESSION_ID\s*=|timed out waiting|use write_stdin)",
    re.IGNORECASE,
)

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


#: 工具默认让出上限（秒）。贴着这个值又拿不到退出码的记录，耗时是让出时刻。
#:
#: 阈值有数据支撑而不是猜的：无退出码的自报耗时里 `>=29.9s` 有 632 条，
#: 而 `20-29.9s` 只有 69 条 —— 这个断崖说明 30 秒是让出上限不是真实分布。
#: 有退出码的对照组里 `>=29.9s` 只有 15 条。
#:
#: 但它只是**本机 Codex 的默认值**，不是跨环境常量（issue #30）。换成 10s / 60s
#: 配置后纯耗时阈值会漏标或误标，所以它现在是 `TruncationPolicy` 的默认值而非
#: 判定逻辑里的硬编码，且随产物一起记录。
YIELD_CEILING_S: Final[float] = 29.9


@dataclass(frozen=True, slots=True)
class TruncationPolicy:
    """截断判定策略。随产物记录，让旧数据能解释自己是按什么口径标的。

    `yield_ceiling_s` 是采集环境的属性（工具的 `yield_time_ms` 配置），
    不是本库的常量。给 `None` 表示不启用纯耗时兜底，只认直接证据 ——
    换 agent 或改配置时这是最安全的选择。
    """

    yield_ceiling_s: float | None = YIELD_CEILING_S

    def as_dict(self) -> dict[str, object]:
        return {
            "truncation_strategy": "direct_evidence_then_ceiling"
            if self.yield_ceiling_s is not None
            else "direct_evidence_only",
            "yield_ceiling_s": self.yield_ceiling_s,
        }


DEFAULT_TRUNCATION_POLICY: Final[TruncationPolicy] = TruncationPolicy()


def looks_truncated(
    result_content: str | None,
    exit_code: int | None,
    duration_s: float | None = None,
    *,
    policy: TruncationPolicy = DEFAULT_TRUNCATION_POLICY,
) -> bool:
    """判断这条记录的耗时是否被工具让出截断。

    判据是「没有退出码」而不是「耗时接近 30 秒」：
    真正跑了 30 秒又正常退出的命令是有效数据，不该被排除。

    注意不能用 `result_status == 'completed'` 反证命令跑完了：
    那个字段说的是「工具调用完成」，不是「命令退出」。
    实测 `gh pr checks --watch` 被挂到后台会话（输出以 `SESSION_ID=` 结尾），
    工具侧标记为 completed，但命令仍在跑，30 秒只是让出时刻。

    证据优先级（issue #30）：**先看直接证据，再看纯耗时阈值**。
    `still running` / `SESSION_ID=` 这类文本是命令没退出的直接证据，与采集环境的
    让出配置无关，换 agent 也成立。纯耗时阈值只是兜底，它依赖 `yield_ceiling_s`
    是否与实际配置一致，所以放在后面，且可以关掉。
    """
    if exit_code is not None:
        # 有退出码就是真的跑完了，哪怕耗时正好贴着上限。
        return False
    # 直接证据：命令自己说了还在跑。不依赖任何阈值。
    if result_content and RE_STILL_RUNNING.search(result_content):
        return True
    # 兜底：贴着让出上限又没有退出码。仅在策略启用了阈值时生效。
    ceiling = policy.yield_ceiling_s
    return ceiling is not None and duration_s is not None and duration_s >= ceiling


def mark_truncated(durations: list[Duration], *, truncated: bool) -> list[Duration]:
    """按最终耗时值重新判定截断标记。"""
    if not truncated:
        return durations
    return [
        Duration(item.seconds, item.source, truncated=True) if item.seconds is not None else item
        for item in durations
    ]


def resolve_durations(
    result_content: str | None,
    slot_count: int,
    turn_delta_s: float | None,
    *,
    truncated: bool = False,
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
            return [Duration(inner[0], "self_reported", truncated=truncated)]
        if outer is not None:
            return [Duration(outer, "self_reported", truncated=truncated)]
        if delta is not None:
            return [Duration(delta, "turn_delta", truncated=truncated)]
        return [UNKNOWN]

    if len(inner) == slot_count:
        return [Duration(v, "self_reported", truncated=truncated) for v in inner]

    shared = outer if outer is not None else delta
    if shared is None:
        return [UNKNOWN] * slot_count
    return [Duration(shared, "batch_shared", truncated=truncated)] * slot_count

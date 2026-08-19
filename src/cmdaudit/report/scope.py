"""耗时口径（scope）。

M1 跑完全量后发现一件事，它决定了 M2 的结构：
`self_reported` 的 35058 条里 100% 是 codex，非 codex 的 14345 条命令里
只有 7 条有自报耗时。

所以「精确耗时」和「跨 agent 覆盖」是互斥的，不能用一个数字同时满足：

- 只用 `self_reported`：耗时精确，但等于只分析 codex 一个 agent；
- 混入 `turn_delta`：覆盖 8 个 agent，但那个值含模型思考时间，是上界不是耗时。

结论是不选口径，而是让每张表显式声明自己用的是哪个口径。
混口径的汇总数字一律视为缺陷。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final, Literal

ScopeName = Literal["exact", "upper_bound", "status_only"]

#: 精确口径：进程自报墙钟。可用于分位数与耗时排名。
EXACT_SOURCES: Final[tuple[str, ...]] = ("self_reported",)

#: 上界口径：叠加时间戳差值。差值含模型思考与用户离开的时间。
UPPER_BOUND_SOURCES: Final[tuple[str, ...]] = ("self_reported", "turn_delta")


@dataclass(frozen=True, slots=True)
class Scope:
    """一张表的数据口径声明。渲染时必须原样打印，不允许省略。"""

    name: ScopeName
    sources: tuple[str, ...]
    caveat: str

    @property
    def sql_filter(self) -> str:
        """可直接拼进 WHERE 的过滤片段。取值来自封闭枚举，无注入面。"""
        if not self.sources:
            return "TRUE"
        quoted = ", ".join(f"'{source}'" for source in self.sources)
        return f"duration_source IN ({quoted})"


EXACT: Final[Scope] = Scope(
    name="exact",
    sources=EXACT_SOURCES,
    caveat=(
        "仅含进程自报墙钟。本机数据里这部分 100% 来自 codex，"
        "因此耗时结论不可外推到其他 agent。"
    ),
)

UPPER_BOUND: Final[Scope] = Scope(
    name="upper_bound",
    sources=UPPER_BOUND_SOURCES,
    caveat=(
        "叠加了相邻消息时间戳差值。差值含模型思考与用户离开的时间，"
        "是命令耗时的上界而非耗时本身，不可用于「这条命令花了多久」这类断言。"
    ),
)

STATUS_ONLY: Final[Scope] = Scope(
    name="status_only",
    sources=(),
    caveat="不依赖耗时证据，覆盖全部 agent。失败判定来自退出码与结果事件。",
)

#: `batch_shared` 是批次共享的总墙钟，任何口径都不得进入分位数统计。
EXCLUDED_FROM_PERCENTILES: Final[tuple[str, ...]] = ("batch_shared", "unknown")

#: 耗时统计的完整前置条件：排除批次共享值、无耗时记录，以及被工具让出截断的记录。
#: 截断记录实测 612 条聚集在 30 秒（工具让出上限），把它们计入会低估长命令。
DURATION_GUARD: Final[str] = (
    " AND ".join(f"duration_source != '{source}'" for source in EXCLUDED_FROM_PERCENTILES)
    + " AND duration_s IS NOT NULL"
    + " AND NOT duration_truncated"
)

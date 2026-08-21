"""可视化的数据模型。

只描述「页面需要什么」，不含任何 HTML。渲染层只读这些 dataclass，
因此换渲染目标（HTML / 静态图 / 其他）不必改查询。

与 Markdown 报告的关键差异：这里每个聚合行都预挂若干条**命令原文样本**。
报告的读者要的是数字，可视化的读者要的是「这一行到底是哪些命令」。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

#: 轨道的语义色。失败与耗时是两套口径不同的证据，
#: 颜色在轨道级别固定，行内不再混色，避免读者把两条线并起来看。
TrackTone = Literal["failure", "duration", "exploratory"]

#: 区块的呈现形态。bar 会在指定列上叠加横条，plain 只出表格。
SectionKind = Literal["bar", "plain"]


@dataclass(frozen=True, slots=True)
class Sample:
    """一条命令原文样本，用于下钻。

    `error_snippet` 已在查询侧截断；这里不再做长度处理，
    渲染层只负责转义。
    """

    command: str
    agent: str
    project: str
    status: str
    exit_code: int | None
    duration_s: float | None
    duration_source: str
    failure_kind: str | None
    error_snippet: str | None


@dataclass(frozen=True, slots=True)
class Row:
    """一个聚合行。

    `cells` 与所属 Section 的 `columns` 一一对应。
    `bar_ratio` 是相对本区块最大值的比例（0..1），已由构造侧算好，
    渲染层不做数值运算。
    """

    cells: tuple[Any, ...]
    bar_ratio: float
    samples: tuple[Sample, ...] = ()
    drill_sql: str = ""


@dataclass(frozen=True, slots=True)
class Section:
    """一个可视区块，对应报告里的一张表。"""

    key: str
    title: str
    note: str
    kind: SectionKind
    columns: tuple[str, ...]
    bar_column: str | None
    rows: tuple[Row, ...]
    sql: str


@dataclass(frozen=True, slots=True)
class Track:
    """一条证据轨道。同一轨道内的数字才允许互相比较。"""

    key: str
    title: str
    tone: TrackTone
    scope_name: str
    caveat: str
    lead: str
    sections: tuple[Section, ...]


@dataclass(frozen=True, slots=True)
class Candidate:
    """待验证候选。evidence_class 恒为 exploratory，页面必须显式标注。"""

    candidate_id: str
    source_rule: str
    command_shape: str
    priority: float
    hypothesis: str
    design: str
    observed: dict[str, Any]
    caveats: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class TimelinePoint:
    """按自然日聚合的真实审计事件，用于工作台趋势图。"""

    day: str
    runs: int
    failures: int
    duration_s: float


@dataclass(frozen=True, slots=True)
class HeatCell:
    """agent × 自然日 的一格。缺席的格子不出现，渲染层按缺失处理，不补零冒充。"""

    agent: str
    day: str
    runs: int
    failures: int


@dataclass(frozen=True, slots=True)
class HistogramBin:
    """耗时直方图的一个桶。区间为 [lo, hi)，最后一桶的 hi 为 None 表示开区间。"""

    lo: float
    hi: float | None
    count: int


@dataclass(frozen=True, slots=True)
class DurationProfile:
    """耗时分布画像。口径固定为 DURATION_GUARD，与报告分位数同源。"""

    bins: tuple[HistogramBin, ...]
    p50: float | None
    p90: float | None
    p99: float | None
    max_s: float | None
    sample_size: int


@dataclass(frozen=True, slots=True)
class FindingSignal:
    """失败模式的近期日频信号，用于队列行内 sparkline。"""

    day: str
    failures: int


@dataclass(frozen=True, slots=True)
class Finding:
    """一个可处理的失败模式：template_id × failure_kind。

    这是工作台的核心工作对象。所有字段都来自 commands 聚合，
    `status` / `owner` / `note` 等流转字段不在此处 —— 它们属于本地状态层，
    由前端持久化，绝不混进证据。
    """

    finding_id: str
    template_id: str
    template: str
    failure_kind: str
    program: str
    failures: int
    runs: int
    agents: tuple[str, ...]
    projects: tuple[str, ...]
    first_seen: str | None
    last_seen: str | None
    signal: tuple[FindingSignal, ...]
    samples: tuple[Sample, ...]
    drill_sql: str


@dataclass(frozen=True, slots=True)
class Dashboard:
    """工作台概览所需的轻量聚合，独立于报告表的下钻结构。"""

    timeline: tuple[TimelinePoint, ...]
    failures_by_kind: tuple[tuple[str, int], ...]
    runs_by_agent: tuple[tuple[str, int], ...]
    latest_event_at: str | None
    heatmap: tuple[HeatCell, ...] = ()
    heatmap_agents: tuple[str, ...] = ()
    heatmap_days: tuple[str, ...] = ()
    duration_profile: DurationProfile | None = None


@dataclass(frozen=True, slots=True)
class Payload:
    """整页数据。"""

    generated_at: str
    source_db: str
    coverage: dict[str, Any]
    tracks: tuple[Track, ...]
    dashboard: Dashboard = field(default_factory=lambda: Dashboard((), (), (), None))
    findings: tuple[Finding, ...] = ()
    candidates: tuple[Candidate, ...] = ()
    candidate_note: str = ""
    warnings: tuple[str, ...] = field(default_factory=tuple)

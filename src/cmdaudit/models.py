"""落库记录的数据契约。

设计原则：非法状态不可表达。`duration_source` 与 `status` 都是封闭取值，
构造时校验；`duration_s` 为 None 时 `duration_source` 必须是 `unknown`。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, get_args

DurationSource = Literal["self_reported", "turn_delta", "batch_shared", "unknown"]
#: `no_match` 是独立状态：`rg` / `grep` / `find` 退出码 1 表示「查无结果」，
#: 那是一次成功的查询得到空结果，不是命令失败。混进 failed 会虚高失败率，
#: 并让「哪个程序最容易出错」这个榜单失去意义。
Status = Literal["ok", "failed", "no_match", "unknown"]
FailureKind = Literal[
    "timeout",
    "network",
    "not_found",
    "permission",
    "build",
    "test",
    "interrupted",
    "other",
]
StatusSource = Literal["exit_code", "result_event", "text_heuristic", "none"]

DURATION_SOURCES: frozenset[str] = frozenset(get_args(DurationSource))
STATUSES: frozenset[str] = frozenset(get_args(Status))
FAILURE_KINDS: frozenset[str] = frozenset(get_args(FailureKind))
STATUS_SOURCES: frozenset[str] = frozenset(get_args(StatusSource))


@dataclass(frozen=True, slots=True)
class RawCall:
    """从 agentsview 读出的一行 tool_call，未解析。"""

    call_id: int
    session_id: str
    agent: str
    project: str
    message_ordinal: int
    call_index: int
    tool_name: str
    tool_use_id: str | None
    input_json: str | None
    result_content: str | None
    result_status: str | None
    started_at: str | None
    ended_at: str | None


@dataclass(frozen=True, slots=True)
class ExtractedCommand:
    """一条被抽出的 shell 命令原文及其在源调用里的位置。"""

    command: str
    workdir: str | None
    # 同一个 tool_call 里的第几条命令（旧格式 JS 脚本可含多条）。
    slot: int
    slot_count: int
    input_kind: str  # cmd / command / CommandLine / js_script


@dataclass(frozen=True, slots=True)
class Duration:
    seconds: float | None
    source: DurationSource
    #: 命令未跑完就被工具让出（yield_time_ms 到点），耗时是被截断的下界。
    #: 这类记录不得进入耗时排名与分位数，否则会系统性低估长命令。
    truncated: bool = False

    def __post_init__(self) -> None:
        if self.source not in DURATION_SOURCES:
            raise ValueError(f"未知 duration_source: {self.source}")
        if self.seconds is None and self.source != "unknown":
            raise ValueError(f"耗时缺失时 source 必须为 unknown，收到 {self.source}")
        if self.seconds is not None:
            if self.source == "unknown":
                raise ValueError("耗时存在时 source 不能为 unknown")
            if self.seconds < 0:
                raise ValueError(f"耗时不能为负: {self.seconds}")


@dataclass(frozen=True, slots=True)
class Outcome:
    status: Status
    status_source: StatusSource
    exit_code: int | None
    failure_kind: FailureKind | None
    error_snippet: str | None

    def __post_init__(self) -> None:
        if self.status not in STATUSES:
            raise ValueError(f"未知 status: {self.status}")
        if self.status_source not in STATUS_SOURCES:
            raise ValueError(f"未知 status_source: {self.status_source}")
        # plan.md §3.3 的红线：exit_code=0 绝不判失败。
        if self.exit_code == 0 and self.status == "failed":
            raise ValueError("exit_code=0 不得判为 failed")
        if self.exit_code == 0 and self.status == "no_match":
            raise ValueError("exit_code=0 不是 no_match")
        if self.status != "failed" and self.failure_kind is not None:
            raise ValueError("只有 failed 才允许带 failure_kind")
        if self.status == "failed" and self.failure_kind is None:
            raise ValueError("failed 必须带 failure_kind")


@dataclass(frozen=True, slots=True)
class CommandRecord:
    """落库的一行。

    构造期做跨字段校验，和 `Duration` / `Outcome` 同一套写法：
    非法状态不可表达，而不是落库后才发现。
    """

    session_id: str
    agent: str
    project: str
    call_id: int
    slot: int
    started_at: str | None
    tool_name: str
    command: str
    workdir: str | None
    input_kind: str
    duration_s: float | None
    duration_source: DurationSource
    duration_truncated: bool
    exit_code: int | None
    status: Status
    status_source: StatusSource
    failure_kind: FailureKind | None
    error_snippet: str | None
    program: str
    programs: tuple[str, ...]
    subcommand: str | None
    command_group: str
    parse_ok: bool
    #: 确定性占位符替换的结果。比 Drain3 的 template 细：
    #: Drain3 会把 `npm run build` 与 `npm run typecheck` 聚成 `npm run <*>`，
    #: 而这两者耗时差一倍以上，候选筛选需要能区分它们。
    canonical: str = ""
    template: str = ""
    template_id: str = ""
    redacted: bool = False

    def __post_init__(self) -> None:
        if self.duration_source not in DURATION_SOURCES:
            raise ValueError(f"未知 duration_source: {self.duration_source}")
        if self.status not in STATUSES:
            raise ValueError(f"未知 status: {self.status}")
        if self.status_source not in STATUS_SOURCES:
            raise ValueError(f"未知 status_source: {self.status_source}")
        if self.failure_kind is not None and self.failure_kind not in FAILURE_KINDS:
            raise ValueError(f"未知 failure_kind: {self.failure_kind}")
        if self.duration_s is None and self.duration_source != "unknown":
            raise ValueError(
                f"耗时缺失时 duration_source 必须为 unknown，收到 {self.duration_source}"
            )
        if self.duration_s is not None:
            if self.duration_source == "unknown":
                raise ValueError("耗时存在时 duration_source 不能为 unknown")
            if self.duration_s < 0:
                raise ValueError(f"耗时不能为负: {self.duration_s}")
        if self.status != "failed" and self.failure_kind is not None:
            raise ValueError("只有 failed 才允许带 failure_kind")
        if self.status == "failed" and self.failure_kind is None:
            raise ValueError("failed 必须带 failure_kind")
        # plan.md §3.3 的红线：exit_code=0 绝不判失败，也不可能是 no_match。
        if self.exit_code == 0 and self.status != "ok":
            raise ValueError(f"exit_code=0 必须 status=ok，收到 {self.status}")
        if self.slot < 0:
            raise ValueError(f"slot 不能为负: {self.slot}")

"""把 RawCall 组装成 CommandRecord。

纯逻辑层：不碰 IO，便于用 fixture 测试。
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Iterable, Iterator
from dataclasses import dataclass

from cmdaudit.extract.command import extract_commands
from cmdaudit.extract.duration import looks_truncated, mark_truncated, resolve_durations
from cmdaudit.extract.shellparse import parse_programs
from cmdaudit.extract.status import decide_outcome
from cmdaudit.models import CommandRecord, RawCall
from cmdaudit.normalize.group import classify_group
from cmdaudit.normalize.redact import redact
from cmdaudit.normalize.template import TemplateEngine, canonicalize, template_id


@dataclass(slots=True)
class ExtractStats:
    """抽取过程的可核对计数。报告里要能解释每一条被排除的记录。"""

    raw_calls: int = 0
    excluded_tool: int = 0
    no_command_key: int = 0
    commands: int = 0
    parse_failed: int = 0
    redacted: int = 0
    duration_truncated: int = 0
    no_match: int = 0

    def as_dict(self) -> dict[str, int]:
        return {
            "raw_calls": self.raw_calls,
            "excluded_tool": self.excluded_tool,
            "no_command_key": self.no_command_key,
            "commands": self.commands,
            "parse_failed": self.parse_failed,
            "redacted": self.redacted,
            "duration_truncated": self.duration_truncated,
            "no_match": self.no_match,
        }


def _parse_ts(value: str | None) -> dt.datetime | None:
    if not value:
        return None
    try:
        return dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def turn_delta_seconds(started_at: str | None, ended_at: str | None) -> float | None:
    start, end = _parse_ts(started_at), _parse_ts(ended_at)
    if start is None or end is None:
        return None
    delta = (end - start).total_seconds()
    return delta if delta >= 0 else None


def build_records(
    calls: Iterable[RawCall],
    *,
    engine: TemplateEngine | None = None,
    stats: ExtractStats | None = None,
) -> Iterator[CommandRecord]:
    template_engine = engine if engine is not None else TemplateEngine()
    counters = stats if stats is not None else ExtractStats()

    for call in calls:
        counters.raw_calls += 1
        extracted = extract_commands(call.tool_name, call.input_json)
        if not extracted:
            from cmdaudit.extract.command import EXCLUDED_TOOLS

            if call.tool_name in EXCLUDED_TOOLS:
                counters.excluded_tool += 1
            else:
                counters.no_command_key += 1
            continue

        delta = turn_delta_seconds(call.started_at, call.ended_at)
        # 先用不带 program 的判定拿到 exit_code，用于 truncated 检测；
        # 每条命令的最终状态在下面按它自己的 program 重新判（no_match 依赖 program）。
        probe = decide_outcome(call.result_content, call.result_status)
        durations = resolve_durations(call.result_content, len(extracted), delta)
        # 截断判定要看最终耗时值（贴着让出上限且无退出码即为截断），
        # 所以先算耗时再标记。
        longest = max((d.seconds for d in durations if d.seconds is not None), default=None)
        truncated = looks_truncated(call.result_content, probe.exit_code, longest)
        durations = mark_truncated(durations, truncated=truncated)
        if truncated:
            counters.duration_truncated += 1

        for item, duration in zip(extracted, durations, strict=True):
            safe_command, was_redacted = redact(item.command)
            if was_redacted:
                counters.redacted += 1
            programs, primary, subcommand, parse_ok = parse_programs(safe_command)
            if not parse_ok:
                counters.parse_failed += 1
            outcome = decide_outcome(
                call.result_content, call.result_status, primary, command=safe_command
            )
            if outcome.status == "no_match":
                counters.no_match += 1
            canonical = canonicalize(safe_command)
            template = template_engine.fit(safe_command)
            counters.commands += 1
            yield CommandRecord(
                session_id=call.session_id,
                agent=call.agent,
                project=call.project,
                call_id=call.call_id,
                slot=item.slot,
                started_at=call.started_at,
                tool_name=call.tool_name,
                command=safe_command,
                workdir=item.workdir,
                input_kind=item.input_kind,
                duration_s=duration.seconds,
                duration_source=duration.source,
                duration_truncated=duration.truncated,
                exit_code=outcome.exit_code,
                status=outcome.status,
                status_source=outcome.status_source,
                failure_kind=outcome.failure_kind,
                error_snippet=outcome.error_snippet,
                program=primary,
                programs=programs,
                subcommand=subcommand,
                command_group=classify_group(primary, programs, subcommand),
                parse_ok=parse_ok,
                canonical=canonical,
                template=template,
                template_id=template_id(primary, subcommand, template),
                redacted=was_redacted,
            )

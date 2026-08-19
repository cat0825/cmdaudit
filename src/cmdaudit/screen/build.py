"""组装候选清单：跑规则、去重、排序、渲染。

排序键是「潜在节省 × 出现频率」的规则化近似，各规则的 priority 量纲不同，
所以先按规则内排序取头部，再全局按 priority 排。
这不是精确的收益预估 —— 精确收益只能由反事实实验给出。
"""

from __future__ import annotations

import datetime as dt
import json
from typing import Any

import duckdb

from cmdaudit.screen.contract import Candidate
from cmdaudit.screen.rules import ALL_RULES


def collect_candidates(
    conn: duckdb.DuckDBPyConnection, *, per_rule_limit: int = 15
) -> list[Candidate]:
    """跑全部规则并按同一形状归并。

    同一 `command_shape` 可能被多条规则命中（例如既反复失败又超时聚集）。
    这种情况保留优先级最高的那条，并把其他规则名记进 `caveats`，
    避免同一个形状在清单里出现多次占掉名额。
    """
    collected: list[Candidate] = []
    for rule in ALL_RULES:
        collected.extend(rule.builder(conn, per_rule_limit))

    best: dict[tuple[str, str], Candidate] = {}
    also_hit: dict[tuple[str, str], list[str]] = {}
    for candidate in collected:
        key = (candidate.program, candidate.command_shape)
        existing = best.get(key)
        if existing is None:
            best[key] = candidate
            continue
        wins = candidate.priority > existing.priority
        also_hit.setdefault(key, []).append(
            existing.source_rule if wins else candidate.source_rule
        )
        if wins:
            best[key] = candidate

    merged: list[Candidate] = []
    for key, candidate in best.items():
        extra = sorted(set(also_hit.get(key, [])) - {candidate.source_rule})
        if extra:
            note = "同一形状也被这些规则命中：" + "、".join(extra)
            candidate = Candidate(
                candidate_id=candidate.candidate_id,
                source_rule=candidate.source_rule,
                command_shape=candidate.command_shape,
                program=candidate.program,
                observed=candidate.observed,
                hypothesis=candidate.hypothesis,
                verification=candidate.verification,
                priority=candidate.priority,
                caveats=(*candidate.caveats, note),
            )
        merged.append(candidate)

    merged.sort(key=lambda item: item.priority, reverse=True)
    return merged


def render_json(candidates: list[Candidate], *, generated_at: dt.datetime | None = None) -> str:
    stamp = (generated_at or dt.datetime.now(dt.UTC)).isoformat()
    payload: dict[str, Any] = {
        "generated_at": stamp,
        "tool": "cmdaudit screen",
        "contract": {
            "evidence_class": "exploratory",
            "status": "unverified",
            "statement": (
                "本文件只包含待验证假设。cmdaudit 不判定某条命令是否必要 —— "
                "那需要反事实实验：删掉它之后故障是否漏掉。"
                "任何条目都不得计入质量声明或进入 benchmark cohort。"
            ),
        },
        "rules": [{"name": rule.name, "description": rule.description} for rule in ALL_RULES],
        "candidates": [candidate.as_dict() for candidate in candidates],
    }
    return json.dumps(payload, indent=2, ensure_ascii=False) + "\n"


def render_markdown(
    candidates: list[Candidate], *, generated_at: dt.datetime | None = None, top: int = 20
) -> str:
    stamp = (generated_at or dt.datetime.now(dt.UTC)).strftime("%Y-%m-%d %H:%M UTC")
    lines = [
        "# 待验证候选清单",
        "",
        f"生成时间：{stamp}",
        "",
        "## 这份清单是什么，不是什么",
        "",
        "**是**：值得做反事实实验的命令形状，按规则从观测数据里筛出。",
        "",
        "**不是**：关于「这条命令该不该跑」的结论。",
        "那个问题只能由「删掉它之后故障是否漏掉」来回答，"
        "cmdaudit 没有跑过那个实验。",
        "",
        "每条候选的 `evidence_class` 恒为 `exploratory`、`status` 恒为 `unverified`。",
        "**不得计入任何质量声明，也不得进入 benchmark cohort。**",
        "",
        f"候选总数 {len(candidates)}，以下列出优先级最高的 {min(top, len(candidates))} 条。",
        "优先级是规则化的粗排，不是收益预估。",
        "",
    ]
    for index, candidate in enumerate(candidates[:top], start=1):
        lines.append(f"## {index}. `{candidate.command_shape}`")
        lines.append("")
        lines.append(f"- 候选 id：`{candidate.candidate_id}`")
        lines.append(f"- 命中规则：`{candidate.source_rule}`")
        lines.append(f"- 主程序：`{candidate.program}`")
        lines.append(f"- 优先级：{candidate.priority:.1f}")
        lines.append(f"- 状态：`{candidate.status}` / 证据等级 `{candidate.evidence_class}`")
        lines.append("")
        lines.append(f"**假设**：{candidate.hypothesis}")
        lines.append("")
        lines.append("**观测依据**：")
        lines.append("")
        for key, value in candidate.observed.items():
            shown = str(value).replace("\n", " ") if value is not None else "—"
            if len(shown) > 160:
                shown = shown[:159] + "…"
            lines.append(f"- `{key}`：{shown}")
        lines.append("")
        lines.append(f"**验证方式**（`{candidate.verification.method}`）：")
        lines.append("")
        lines.append(candidate.verification.design)
        lines.append("")
        lines.append(f"独立判定：`{candidate.verification.oracle}`")
        lines.append("")
        if candidate.caveats:
            lines.append("**这条候选的边界**：")
            lines.append("")
            for caveat in candidate.caveats:
                lines.append(f"- {caveat}")
            lines.append("")
    return "\n".join(lines).rstrip() + "\n"

"""候选筛选规则。

全部是确定性 SQL 规则，不用模型。模型判定没有 ground truth，
而这些规则的每一条输出都能由一句 SQL 复现。

候选键用 `canonical` 而不是 Drain3 的 `template`：后者会把
`npm run build`（732 秒 / 152 次）与 `npm run typecheck`（311 秒 / 106 次）
聚成同一个 `npm run <*>` 桶，那个粒度下没法定位该验证哪个 script。
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Final

import duckdb

from cmdaudit.report.scope import DURATION_GUARD
from cmdaudit.screen.contract import Candidate, Verification

#: 规则的最小样本量。低于此值的模式当噪声处理，不产出候选。
MIN_RUNS: Final[int] = 5

#: 高失败率阈值。
HIGH_FAILURE_RATE: Final[float] = 0.4

#: 每个分组取一条确定性代表行：优先失败行、再按 `started_at, call_id`。
#: `any_value` 从哪一行取值不定，同批数据重复查询可能给出不同样本；
#: 代表行只是抽样展示，候选里的 count/rate 才是可复现的聚合数字。
_DETERMINISTIC_KIND: Final[str] = (
    "first(failure_kind ORDER BY (status = 'failed') DESC, started_at NULLS LAST, call_id)"
)
_DETERMINISTIC_SAMPLE: Final[str] = (
    "first(error_snippet ORDER BY (status = 'failed') DESC, started_at NULLS LAST, call_id)"
)


@dataclass(frozen=True, slots=True)
class Rule:
    """一条候选规则。"""

    name: str
    description: str
    builder: Callable[[duckdb.DuckDBPyConnection, int], list[Candidate]]


def _rows(conn: duckdb.DuckDBPyConnection, sql: str) -> list[tuple[Any, ...]]:
    return [tuple(row) for row in conn.execute(sql).fetchall()]


def _candidate_id(rule: str, shape: str) -> str:
    import hashlib

    digest = hashlib.blake2b(f"{rule}\x1f{shape}".encode(), digest_size=5).hexdigest()
    return f"cand_{digest}"


def repeated_failures(conn: duckdb.DuckDBPyConnection, limit: int) -> list[Candidate]:
    """同一命令形状反复失败：最可能产出可写进 AGENTS.md 的规则。"""
    sql = f"""
SELECT canonical,
       program,
       count(*)                                            AS decided_runs,
       sum(CASE WHEN status = 'failed' THEN 1 ELSE 0 END)   AS failures,
       count(DISTINCT project)                             AS projects,
       {_DETERMINISTIC_KIND}                               AS kind,
       {_DETERMINISTIC_SAMPLE}                             AS sample
FROM commands
WHERE status IN ('ok', 'failed')
GROUP BY canonical, program
HAVING count(*) >= {MIN_RUNS}
   AND sum(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) * 1.0 / count(*) >= {HIGH_FAILURE_RATE}
ORDER BY failures DESC
LIMIT {limit}
""".strip()
    candidates: list[Candidate] = []
    for shape, program, runs, failures, projects, kind, sample in _rows(conn, sql):
        rate = failures / runs if runs else 0.0
        candidates.append(
            Candidate(
                candidate_id=_candidate_id("repeated_failures", str(shape)),
                source_rule="repeated_failures",
                command_shape=str(shape),
                program=str(program),
                observed={
                    "decided_runs": runs,
                    "failures": failures,
                    "failure_rate": round(rate, 3),
                    "projects": projects,
                    "dominant_failure_kind": kind,
                    "error_sample": (str(sample)[:200] if sample else None),
                },
                hypothesis=(
                    f"`{program}` 的这个调用形状在 {runs} 次里失败 {failures} 次，"
                    f"疑似存在可预防的用法问题（观测到的主要失败类型：{kind}），"
                    "待验证是否能用前置检查消除"
                ),
                verification=Verification(
                    method="counterfactual_run",
                    design=(
                        "在隔离工作区复现该命令形状，先按原样执行记录失败；"
                        "再加入候选前置检查后执行同一任务，"
                        "比较失败次数与任务最终结果是否一致。"
                        "前置检查不得改变任务语义。"
                    ),
                    oracle="independent_oracle",
                ),
                priority=float(failures) * rate,
                caveats=(
                    "失败归因来自规则匹配，可能把复合命令里其他程序的失败算给主程序。",
                ),
            )
        )
    return candidates


def timeout_and_network_clusters(
    conn: duckdb.DuckDBPyConnection, limit: int
) -> list[Candidate]:
    """超时与网络失败聚集：最初的诉求。"""
    sql = f"""
SELECT canonical,
       program,
       failure_kind,
       count(*)                               AS failures,
       count(DISTINCT project)                AS projects,
       {_DETERMINISTIC_SAMPLE}                AS sample
FROM commands
WHERE status = 'failed'
  AND failure_kind IN ('timeout', 'network')
GROUP BY canonical, program, failure_kind
HAVING count(*) >= 3
ORDER BY failures DESC
LIMIT {limit}
""".strip()
    candidates: list[Candidate] = []
    for shape, program, kind, failures, projects, sample in _rows(conn, sql):
        candidates.append(
            Candidate(
                candidate_id=_candidate_id(f"network_cluster:{kind}", str(shape)),
                source_rule="timeout_and_network_clusters",
                command_shape=str(shape),
                program=str(program),
                observed={
                    "failures": failures,
                    "failure_kind": kind,
                    "projects": projects,
                    "error_sample": (str(sample)[:200] if sample else None),
                },
                hypothesis=(
                    f"`{program}` 的这个形状出现 {failures} 次 {kind} 失败，"
                    "疑似可通过重试策略、超时上调或改用轮询以外的等待方式改善，"
                    "待验证"
                ),
                verification=Verification(
                    method="counterfactual_run",
                    design=(
                        "同一任务跑两个 run：一个按原样，一个应用候选的等待/重试策略。"
                        "比较总耗时与任务最终结果，"
                        "并确认新策略没有把真实故障掩盖成一次成功重试。"
                    ),
                    oracle="independent_oracle",
                ),
                priority=float(failures) * 1.5,
                caveats=(
                    "网络与超时受外部环境影响，同一命令在不同网络下结果不同，"
                    "验证时需固定网络条件或多次重复。",
                ),
            )
        )
    return candidates


def duration_hotspots(conn: duckdb.DuckDBPyConnection, limit: int) -> list[Candidate]:
    """耗时头部：只在精确口径上成立，因此候选自带覆盖范围声明。"""
    sql = f"""
SELECT canonical,
       program,
       count(*)                                    AS runs,
       round(sum(duration_s), 1)                   AS total_s,
       round(quantile_cont(duration_s, 0.5), 3)    AS p50_s,
       round(max(duration_s), 1)                   AS max_s,
       count(DISTINCT agent)                       AS agents
FROM commands
WHERE duration_source = 'self_reported'
  AND {DURATION_GUARD}
GROUP BY canonical, program
HAVING count(*) >= {MIN_RUNS}
ORDER BY total_s DESC
LIMIT {limit}
""".strip()
    candidates: list[Candidate] = []
    for shape, program, runs, total_s, p50_s, max_s, agents in _rows(conn, sql):
        candidates.append(
            Candidate(
                candidate_id=_candidate_id("duration_hotspots", str(shape)),
                source_rule="duration_hotspots",
                command_shape=str(shape),
                program=str(program),
                observed={
                    "runs": runs,
                    "total_s": total_s,
                    "p50_s": p50_s,
                    "max_s": max_s,
                    "agents": agents,
                },
                hypothesis=(
                    f"这个形状累计占用 {total_s} 秒（{runs} 次，p50 {p50_s} 秒），"
                    "疑似存在缓存、增量执行或按影响面裁剪的空间，待验证"
                ),
                verification=Verification(
                    method="counterfactual_run",
                    design=(
                        "构造隔离工作区，baseline 按原样执行该命令，"
                        "candidate 应用候选优化（缓存或裁剪范围）。"
                        "用独立 oracle 确认两者的任务结果一致、"
                        "且 candidate 没有漏掉 baseline 能发现的故障。"
                    ),
                    oracle="independent_oracle",
                ),
                priority=float(total_s) / 60.0,
                caveats=(
                    "耗时仅统计有进程自报墙钟的记录，本机数据里这部分几乎全部来自 "
                    "codex，不可外推到其他 agent。",
                    "已排除批次共享耗时与被工具让出截断的记录。",
                ),
            )
        )
    return candidates


def wait_polling(conn: duckdb.DuckDBPyConnection, limit: int) -> list[Candidate]:
    """等待轮询：命令组为 wait 的形状。

    单独成一条规则而不是并进耗时榜，因为等待的改进方向完全不同
    —— 不是让命令更快，而是换一种等待机制。
    """
    sql = f"""
SELECT canonical,
       program,
       count(*)                                    AS runs,
       round(sum(COALESCE(duration_s, 0)), 1)      AS observed_s,
       round(max(COALESCE(duration_s, 0)), 1)      AS max_s,
       count(DISTINCT duration_source)             AS source_kinds
FROM commands
WHERE command_group = 'wait'
GROUP BY canonical, program
HAVING count(*) >= 3
ORDER BY observed_s DESC
LIMIT {limit}
""".strip()
    candidates: list[Candidate] = []
    for shape, program, runs, observed_s, max_s, source_kinds in _rows(conn, sql):
        candidates.append(
            Candidate(
                candidate_id=_candidate_id("wait_polling", str(shape)),
                source_rule="wait_polling",
                command_shape=str(shape),
                program=str(program),
                observed={
                    "runs": runs,
                    "observed_s": observed_s,
                    "max_s": max_s,
                    "duration_source_kinds": source_kinds,
                },
                hypothesis=(
                    f"这个等待形状出现 {runs} 次、已记录 {observed_s} 秒，"
                    "疑似可用事件通知或阻塞式等待替代固定间隔轮询，待验证"
                ),
                verification=Verification(
                    method="counterfactual_run",
                    design=(
                        "同一后台任务跑两个 run：一个用固定 sleep 轮询，"
                        "一个用事件回调或阻塞等待。比较总等待时间，"
                        "并确认新方式不会在任务尚未完成时提前返回。"
                    ),
                    oracle="independent_oracle",
                ),
                priority=float(observed_s) / 60.0,
                caveats=(
                    "等待时间混合了多种 duration_source，只作量级参考，"
                    "不可当精确损耗引用。",
                ),
            )
        )
    return candidates


#: 「命令根本没跑起来」的三类判据。
#:
#: 与其他规则的区别在验证成本：这三类的失败信号是 shell/OS 在执行**之前**
#: 给出的，命令没有产生任何副作用。所以「有没有跑起来」是客观事实，
#: 不需要 baseline/candidate 双跑，`manual_inspection` 足够。
#:
#: 判据全部落在 `error_snippet` 的固定串上，不做模糊匹配 ——
#: 宁可漏掉一批，也不要把「跑起来但失败了」误判成「没跑起来」。
PREVENTABLE_KINDS: Final[tuple[tuple[str, str, str, str], ...]] = (
    (
        "zsh_glob_unquoted",
        "error_snippet LIKE '%no matches found%'",
        "路径含 zsh 的 glob 元字符（`[` `]` `*` `?`）且未加引号，shell 在展开阶段就拒绝执行",
        "把路径参数用单引号包起来，或对元字符转义",
    ),
    (
        "command_not_found",
        "(error_snippet LIKE '%command not found%'"
        " OR error_snippet LIKE '%: not found%')",
        "目标程序在当前 PATH 里不存在，命令未进入执行阶段",
        "调用前用 `command -v` 探测，或改用项目内已声明的等价工具",
    ),
    (
        "not_a_git_repo",
        "error_snippet LIKE '%not a git repository%'",
        "在非 git 工作目录里执行 git 子命令，git 未做任何操作即退出",
        "先确认 cwd 在仓库内，或给 git 显式传 `-C <repo>`",
    ),
)


def preventable_errors(conn: duckdb.DuckDBPyConnection, limit: int) -> list[Candidate]:
    """命令根本没跑起来的失败：shell/OS 在执行前就拒绝了。

    这条规则和其他四条的性质不同。`repeated_failures` 等规则筛出的是
    「跑了但失败」，要判断该不该改必须做反事实实验；这里筛出的是
    「压根没跑」—— 加引号、探测 PATH、确认 cwd 都不改变任务语义，
    没有 trade-off 需要权衡，所以验证方式是 `manual_inspection`。

    仍然输出待验证假设而非结论：规则只能证明这批调用没跑起来，
    不能证明补上前置处理后 agent 的整体行为一定更好。
    """
    candidates: list[Candidate] = []
    for kind, predicate, mechanism, remedy in PREVENTABLE_KINDS:
        where = f"status = 'failed' AND error_snippet IS NOT NULL AND {predicate}"
        # 先取该类的全库总量。`limit` 会截掉长尾形状，不报总数会让读者
        # 把候选覆盖的次数当成该类的全部发生次数。
        totals = conn.execute(
            f"SELECT count(*), count(DISTINCT canonical) FROM commands WHERE {where}"
        ).fetchone()
        kind_total, kind_shapes = (int(totals[0]), int(totals[1])) if totals else (0, 0)
        sql = f"""
SELECT canonical,
       program,
       count(*)                    AS occurrences,
       count(DISTINCT project)     AS projects,
       count(DISTINCT agent)       AS agents,
       {_DETERMINISTIC_SAMPLE}     AS sample
FROM commands
WHERE {where}
GROUP BY canonical, program
ORDER BY occurrences DESC, canonical
LIMIT {limit}
""".strip()
        for shape, program, occurrences, projects, agents, sample in _rows(conn, sql):
            candidates.append(
                Candidate(
                    candidate_id=_candidate_id(f"preventable:{kind}", str(shape)),
                    source_rule="preventable_errors",
                    command_shape=str(shape),
                    program=str(program),
                    observed={
                        "preventable_kind": kind,
                        "occurrences": occurrences,
                        "projects": projects,
                        "agents": agents,
                        "kind_total_occurrences": kind_total,
                        "kind_total_shapes": kind_shapes,
                        "mechanism": mechanism,
                        "error_sample": (str(sample)[:200] if sample else None),
                    },
                    hypothesis=(
                        f"`{program}` 的这个形状有 {occurrences} 次因 {kind} 未能进入执行阶段"
                        f"（{mechanism}）。疑似可由一条 AGENTS.md 约定消除："
                        f"{remedy}。待验证该约定是否覆盖全部命中样本"
                    ),
                    verification=Verification(
                        method="manual_inspection",
                        design=(
                            "逐条读命中样本的命令原文与错误输出，确认失败确实发生在"
                            "执行之前（无部分副作用）；再确认候选约定套用到该原文上"
                            "能让命令进入执行阶段，且不改变命令语义。"
                            "两条都成立才算这条候选被证实。"
                        ),
                        oracle="manual_reading",
                    ),
                    priority=float(occurrences) * 0.5,
                    caveats=(
                        "判据是 error_snippet 固定串匹配，只召回明确报出该错误的记录，"
                        "真实发生次数可能更高。",
                        "「未进入执行阶段」由错误类型推断；复合命令里前半段"
                        "可能已经执行，需按样本逐条确认。",
                        f"该类全库共 {kind_total} 次命中 / {kind_shapes} 个形状，"
                        f"本清单按 per_rule_limit 只列出头部，长尾未展开。",
                    ),
                )
            )
    return candidates


ALL_RULES: Final[tuple[Rule, ...]] = (
    Rule("repeated_failures", "同一命令形状反复失败", repeated_failures),
    Rule("timeout_and_network_clusters", "超时与网络失败聚集", timeout_and_network_clusters),
    Rule("duration_hotspots", "耗时头部形状", duration_hotspots),
    Rule("wait_polling", "固定间隔轮询等待", wait_polling),
    Rule("preventable_errors", "命令未进入执行阶段的可预防错误", preventable_errors),
)

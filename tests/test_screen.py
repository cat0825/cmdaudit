"""候选筛选：契约不变量与输出约束。

这些测试守的是同一件事 —— cmdaudit 只输出待验证假设。
一旦有人把结论塞进候选，这里必须失败。
"""

from __future__ import annotations

import json
from pathlib import Path

import duckdb
import pytest

from cmdaudit.models import CommandRecord, RawCall
from cmdaudit.pipeline import build_records
from cmdaudit.screen.build import collect_candidates, render_json, render_markdown
from cmdaudit.screen.contract import (
    FORBIDDEN_EVIDENCE_CLASSES,
    Candidate,
    ContractViolation,
    Verification,
)
from cmdaudit.screen.rules import ALL_RULES
from cmdaudit.store import write_commands

FIXTURES = Path(__file__).parent / "fixtures"


def _verification() -> Verification:
    return Verification(
        method="counterfactual_run",
        design="跑 baseline 与 candidate 两个 run，用独立 oracle 比较故障召回",
        oracle="independent_oracle",
    )


def _candidate(**overrides: object) -> Candidate:
    payload: dict[str, object] = {
        "candidate_id": "cand_test",
        "source_rule": "unit_test",
        "command_shape": "npm run build",
        "program": "npm",
        "observed": {"runs": 10},
        "hypothesis": "疑似存在缓存空间，待验证",
        "verification": _verification(),
        "priority": 1.0,
    }
    payload.update(overrides)
    return Candidate(**payload)  # type: ignore[arg-type]


@pytest.fixture
def commands_db(tmp_path: Path) -> duckdb.DuckDBPyConnection:
    payload = json.loads((FIXTURES / "raw_calls.json").read_text(encoding="utf-8"))
    records = list(build_records(RawCall(**item) for item in payload))
    db_path = tmp_path / "commands.duckdb"
    write_commands(db_path, records)
    conn = duckdb.connect(str(db_path), read_only=True)
    yield conn
    conn.close()


def test_valid_candidate_is_constructible() -> None:
    candidate = _candidate()
    assert candidate.evidence_class == "exploratory"
    assert candidate.status == "unverified"


@pytest.mark.parametrize("forbidden", sorted(FORBIDDEN_EVIDENCE_CLASSES))
def test_forbidden_evidence_classes_are_rejected(forbidden: str) -> None:
    """observed_benchmark 等等级会让候选被下游当成已验证证据。"""
    with pytest.raises(ContractViolation, match="evidence_class"):
        _candidate(evidence_class=forbidden)


def test_status_cannot_be_preset_to_verified() -> None:
    with pytest.raises(ContractViolation, match="status"):
        _candidate(status="verified")


@pytest.mark.parametrize(
    "hypothesis",
    [
        "这条命令不必要",
        "应该删除这条命令",
        "该命令是冗余的",
        "已验证为无用，待验证",
        "This command is unnecessary 待验证",
        "This is redundant 待验证",
        "可以安全删除，待验证",
    ],
)
def test_verdict_wording_is_rejected(hypothesis: str) -> None:
    with pytest.raises(ContractViolation):
        _candidate(hypothesis=hypothesis)


def test_hypothesis_must_be_hedged() -> None:
    """没有限定词的陈述会被读成结论。"""
    with pytest.raises(ContractViolation, match="限定词"):
        _candidate(hypothesis="这个形状累计占用 700 秒")


def test_verification_design_is_required() -> None:
    with pytest.raises(ContractViolation, match="design"):
        Verification(method="counterfactual_run", design="   ", oracle="independent_oracle")


def test_verification_design_cannot_contain_verdict() -> None:
    with pytest.raises(ContractViolation):
        Verification(
            method="counterfactual_run",
            design="确认它是冗余的",
            oracle="independent_oracle",
        )


def test_observed_evidence_is_required() -> None:
    with pytest.raises(ContractViolation, match="observed"):
        _candidate(observed={})


def test_every_rule_produces_contract_compliant_candidates(
    commands_db: duckdb.DuckDBPyConnection,
) -> None:
    for rule in ALL_RULES:
        for candidate in rule.builder(commands_db, 5):
            assert candidate.evidence_class == "exploratory"
            assert candidate.status == "unverified"
            assert candidate.verification.design.strip()
            assert candidate.observed


def test_candidates_are_sorted_and_deduplicated(
    commands_db: duckdb.DuckDBPyConnection,
) -> None:
    candidates = collect_candidates(commands_db, per_rule_limit=10)
    priorities = [candidate.priority for candidate in candidates]
    assert priorities == sorted(priorities, reverse=True)
    keys = [(candidate.program, candidate.command_shape) for candidate in candidates]
    assert len(keys) == len(set(keys))


def test_json_output_declares_the_contract(commands_db: duckdb.DuckDBPyConnection) -> None:
    payload = json.loads(render_json(collect_candidates(commands_db)))
    assert payload["contract"]["evidence_class"] == "exploratory"
    assert payload["contract"]["status"] == "unverified"
    for entry in payload["candidates"]:
        assert entry["evidence_class"] == "exploratory"
        assert entry["status"] == "unverified"
        assert entry["verification"]["design"]


def test_json_output_never_contains_forbidden_classes(
    commands_db: duckdb.DuckDBPyConnection,
) -> None:
    """整份文件的文本里都不该出现 observed_benchmark。"""
    text = render_json(collect_candidates(commands_db))
    assert "observed_benchmark" not in text


def test_markdown_states_what_it_is_not(commands_db: duckdb.DuckDBPyConnection) -> None:
    markdown = render_markdown(collect_candidates(commands_db))
    assert "不是" in markdown
    assert "unverified" in markdown
    assert "不得计入任何质量声明" in markdown


def test_markdown_never_leaks_credentials(commands_db: duckdb.DuckDBPyConnection) -> None:
    markdown = render_markdown(collect_candidates(commands_db))
    assert "sk-ant-abcdefghij1234567890" not in markdown


def test_empty_database_yields_no_candidates(tmp_path: Path) -> None:
    db_path = tmp_path / "empty.duckdb"
    write_commands(db_path, [])
    conn = duckdb.connect(str(db_path), read_only=True)
    try:
        assert collect_candidates(conn) == []
        payload = json.loads(render_json([]))
        assert payload["candidates"] == []
    finally:
        conn.close()


def test_repeated_failures_kind_and_sample_are_deterministic(tmp_path: Path) -> None:
    """同一命令形状的 kind/sample 不受插入顺序影响。

    `any_value` 从哪一行取值不定，重复查询可能给出不同 dominant_failure_kind。
    """
    from cmdaudit.models import CommandRecord
    from cmdaudit.screen.rules import repeated_failures

    def record(call_id: int, started_at: str, kind: str, snippet: str) -> CommandRecord:
        return CommandRecord(
            session_id="s",
            agent="codex",
            project="p",
            call_id=call_id,
            slot=0,
            started_at=started_at,
            tool_name="exec_command",
            command="git pull",
            workdir=None,
            input_kind="cmd",
            duration_s=None,
            duration_source="unknown",
            duration_truncated=False,
            exit_code=1 if kind == "other" else 128,
            status="failed",
            status_source="exit_code",
            failure_kind=kind,
            error_snippet=snippet,
            program="git",
            programs=("git",),
            subcommand="pull",
            command_group="vcs",
            parse_ok=True,
            canonical="git pull",
            template="git pull",
            template_id="t1",
            redacted=False,
        )

    rows = [
        record(1, "2026-08-01", "network", "snippet-a"),
        record(2, "2026-08-02", "timeout", "snippet-b"),
        record(3, "2026-08-03", "network", "snippet-c"),
        record(4, "2026-08-04", "network", "snippet-d"),
        record(5, "2026-08-05", "timeout", "snippet-e"),
        record(6, "2026-08-06", "network", "snippet-f"),
    ]
    forward = tmp_path / "forward.duckdb"
    reversed_path = tmp_path / "reversed.duckdb"
    write_commands(forward, rows)
    write_commands(reversed_path, list(reversed(rows)))

    def observed(db: Path) -> list[tuple[str, str]]:
        conn = duckdb.connect(str(db), read_only=True)
        try:
            candidates = repeated_failures(conn, 10)
        finally:
            conn.close()
        assert candidates
        return [
            (str(item.observed["dominant_failure_kind"]), str(item.observed["error_sample"]))
            for item in candidates
        ]

    # 换输入顺序结果一致，且代表行是失败行里最早的一条。
    first = observed(forward)
    assert observed(forward) == first
    assert observed(reversed_path) == first
    assert first[0] == ("network", "snippet-a")


def _preventable_record(
    call_id: int, command: str, canonical: str, program: str, snippet: str
) -> CommandRecord:
    return CommandRecord(
        session_id="s",
        agent="codex",
        project="p",
        call_id=call_id,
        slot=0,
        started_at=f"2026-08-{call_id:02d}",
        tool_name="exec_command",
        command=command,
        workdir=None,
        input_kind="cmd",
        duration_s=None,
        duration_source="unknown",
        duration_truncated=False,
        exit_code=1,
        status="failed",
        status_source="exit_code",
        failure_kind="other",
        error_snippet=snippet,
        program=program,
        programs=(program,),
        subcommand=None,
        command_group="other",
        parse_ok=True,
        canonical=canonical,
        template=canonical,
        template_id="t1",
        redacted=False,
    )


def test_preventable_errors_detects_each_kind(tmp_path: Path) -> None:
    """三类判据各自能召回，且 kind 标注正确。"""
    from cmdaudit.screen.rules import preventable_errors

    rows = [
        _preventable_record(
            1, "sed -n '1,20p' src/[id]/route.ts", "sed -n '<n>,20p' <path>", "sed",
            "zsh:1: no matches found: src/[id]/route.ts",
        ),
        _preventable_record(
            2, "bun run x", "bun run x", "bun", "zsh: command not found: bun",
        ),
        _preventable_record(
            3, "git status", "git status", "git",
            "fatal: not a git repository (or any of the parent directories): .git",
        ),
    ]
    db = tmp_path / "prev.duckdb"
    write_commands(db, rows)
    conn = duckdb.connect(str(db), read_only=True)
    try:
        candidates = preventable_errors(conn, 10)
    finally:
        conn.close()

    kinds = {str(item.observed["preventable_kind"]) for item in candidates}
    assert kinds == {"zsh_glob_unquoted", "command_not_found", "not_a_git_repo"}
    # 契约仍然守住：这条规则输出的也是待验证假设。
    for item in candidates:
        assert item.evidence_class == "exploratory"
        assert item.status == "unverified"
        assert item.verification.method == "manual_inspection"


def test_preventable_errors_reports_kind_total_when_truncated(tmp_path: Path) -> None:
    """`limit` 截掉长尾时，全库总数必须仍然可见（不做静默截断）。"""
    from cmdaudit.screen.rules import preventable_errors

    rows = [
        _preventable_record(
            i, f"bun run task{i}", f"bun run task{i}", "bun",
            f"zsh: command not found: bun{i}",
        )
        for i in range(1, 6)
    ]
    db = tmp_path / "trunc.duckdb"
    write_commands(db, rows)
    conn = duckdb.connect(str(db), read_only=True)
    try:
        candidates = preventable_errors(conn, 2)
    finally:
        conn.close()

    assert len(candidates) == 2, "limit 应当生效"
    for item in candidates:
        assert item.observed["kind_total_occurrences"] == 5
        assert item.observed["kind_total_shapes"] == 5
        assert any("长尾未展开" in caveat for caveat in item.caveats)


def test_preventable_errors_ignores_ordinary_failures(tmp_path: Path) -> None:
    """跑起来但失败的命令不得被召回：判据只认执行前的拒绝。"""
    from cmdaudit.screen.rules import preventable_errors

    rows = [
        _preventable_record(
            i, "pytest", "pytest", "pytest", "2 failed, 3 passed in 4.2s"
        )
        for i in range(1, 8)
    ]
    db = tmp_path / "ordinary.duckdb"
    write_commands(db, rows)
    conn = duckdb.connect(str(db), read_only=True)
    try:
        assert preventable_errors(conn, 10) == []
    finally:
        conn.close()

"""可视化层：口径分轨不可混、下钻样本与聚合行同源、渲染完全离线且不泄漏。

这层的风险点和报告层不同：报告层只输出数字，页面还要内联命令原文。
因此测试重点是「转义唯一出口」「样本不越过口径」「零外部依赖」。
"""

from __future__ import annotations

import json
from pathlib import Path

import duckdb
import pytest

from cmdaudit.models import RawCall
from cmdaudit.pipeline import build_records
from cmdaudit.report.scope import EXACT, STATUS_ONLY
from cmdaudit.store import write_commands
from cmdaudit.viz.build import build_viz
from cmdaudit.viz.collect import (
    MAX_CANDIDATES,
    SAMPLES_PER_ROW,
    UnknownColumn,
    _fetch_samples,
    _load_candidates,
    _table_columns,
    collect_payload,
)
from cmdaudit.viz.model import Payload, Row, Sample, Section, Track
from cmdaudit.viz.render_html import _esc, load_shell, render_html

FIXTURES = Path(__file__).parent / "fixtures"


def _write_db(tmp_path: Path) -> Path:
    payload = json.loads((FIXTURES / "raw_calls.json").read_text(encoding="utf-8"))
    records = list(build_records(RawCall(**item) for item in payload))
    db_path = tmp_path / "commands.duckdb"
    write_commands(db_path, records)
    return db_path


@pytest.fixture
def commands_db(tmp_path: Path) -> duckdb.DuckDBPyConnection:
    conn = duckdb.connect(str(_write_db(tmp_path)), read_only=True)
    yield conn
    conn.close()


@pytest.fixture
def payload(commands_db: duckdb.DuckDBPyConnection) -> Payload:
    return collect_payload(
        commands_db,
        source_db="out/commands.duckdb",
        generated_at="2026-08-21 00:00 UTC",
    )


# --- 口径 ---------------------------------------------------------------


def test_tracks_keep_the_two_scopes_physically_separate(payload: Payload) -> None:
    """失败线与耗时线必须是两条独立轨道，且各自打印自己的口径与 caveat。"""
    scopes = {track.key: track.scope_name for track in payload.tracks}
    assert scopes == {"failure": STATUS_ONLY.name, "duration": EXACT.name}
    for track in payload.tracks:
        assert track.caveat
        assert track.lead
        assert track.sections


def test_duration_samples_never_include_unusable_evidence(payload: Payload) -> None:
    """耗时线的下钻样本只能是 self_reported 且未被截断，否则数字口径就串了。"""
    duration = next(track for track in payload.tracks if track.key == "duration")
    seen = 0
    for section in duration.sections:
        for row in section.rows:
            for sample in row.samples:
                seen += 1
                assert sample.duration_source == "self_reported"
                assert sample.duration_s is not None
    assert seen > 0


def test_failure_samples_are_all_failed(payload: Payload) -> None:
    failure = next(track for track in payload.tracks if track.key == "failure")
    seen = 0
    for section in failure.sections:
        for row in section.rows:
            for sample in row.samples:
                seen += 1
                assert sample.status == "failed"
    assert seen > 0


def test_sample_count_is_capped(payload: Payload) -> None:
    for track in payload.tracks:
        for section in track.sections:
            for row in section.rows:
                assert len(row.samples) <= SAMPLES_PER_ROW


# --- 下钻与聚合同源 -----------------------------------------------------


def test_drill_sql_is_reproducible(
    commands_db: duckdb.DuckDBPyConnection, payload: Payload
) -> None:
    """页面上贴出的下钻 SQL 必须真能跑，且有样本的行至少跑出一条。"""
    checked = 0
    for track in payload.tracks:
        for section in track.sections:
            for row in section.rows:
                assert row.drill_sql
                rerun = commands_db.execute(row.drill_sql).fetchall()
                if row.samples:
                    assert rerun
                    checked += 1
    assert checked > 0


def test_samples_match_their_aggregate_row(payload: Payload) -> None:
    """failure_kind × program 的行，样本必须落在同一格里，否则下钻是错的。"""
    failure = next(track for track in payload.tracks if track.key == "failure")
    section = next(s for s in failure.sections if s.key == "failure_by_kind_and_program")
    kind_index = section.columns.index("failure_kind")
    program_index = section.columns.index("program")
    checked = 0
    for row in section.rows:
        for sample in row.samples:
            checked += 1
            assert sample.failure_kind == row.cells[kind_index]
            assert sample.command.split()[0] == row.cells[program_index]
    assert checked > 0


def test_unknown_drill_column_is_rejected(commands_db: duckdb.DuckDBPyConnection) -> None:
    """下钻列名来自封闭配置；写错列名要在构造期炸掉，不能拼进 SQL。"""
    with pytest.raises(UnknownColumn):
        _fetch_samples(
            commands_db,
            base_filter="TRUE",
            keys=("program; DROP TABLE commands",),
            values=("git",),
            order_by="started_at DESC",
            known_columns=_table_columns(commands_db),
        )


def test_bar_ratio_is_normalized(payload: Payload) -> None:
    for track in payload.tracks:
        for section in track.sections:
            if section.bar_column is None or not section.rows:
                continue
            ratios = [row.bar_ratio for row in section.rows]
            assert all(0.0 <= value <= 1.0 for value in ratios)
            assert max(ratios) == pytest.approx(1.0)


# --- 候选队列 -----------------------------------------------------------


def test_missing_candidates_file_degrades_to_a_warning(tmp_path: Path) -> None:
    candidates, note, warnings = _load_candidates(tmp_path / "nope.json")
    assert candidates == ()
    assert note == ""
    assert warnings and "candidates.json" in warnings[0]


def test_broken_candidates_file_does_not_raise(tmp_path: Path) -> None:
    path = tmp_path / "candidates.json"
    path.write_text("{ not json", encoding="utf-8")
    candidates, _, warnings = _load_candidates(path)
    assert candidates == ()
    assert warnings


def test_candidates_are_sorted_and_capped(tmp_path: Path) -> None:
    entries = [
        {
            "candidate_id": f"c{index}",
            "source_rule": "rule",
            "command_shape": "npm install",
            "priority": index,
            "hypothesis": "假设",
            "verification": {"design": "设计"},
            "observed": {"failures": index},
            "caveats": ["探索性"],
        }
        for index in range(MAX_CANDIDATES + 5)
    ]
    path = tmp_path / "candidates.json"
    path.write_text(json.dumps({"candidates": entries}), encoding="utf-8")
    candidates, _, warnings = _load_candidates(path)
    assert warnings == ()
    assert len(candidates) == MAX_CANDIDATES
    priorities = [item.priority for item in candidates]
    assert priorities == sorted(priorities, reverse=True)


# --- 渲染 ---------------------------------------------------------------


def test_esc_is_the_only_text_exit() -> None:
    assert _esc("</script><img onerror=x>") == (
        "&lt;/script&gt;&lt;img onerror=x&gt;"
    )
    assert _esc('a "b" & c') == "a &quot;b&quot; &amp; c"
    assert _esc(None) == "—"


def test_rendered_page_has_no_external_resource(payload: Payload) -> None:
    """必须 file:// 双击可用：不引 CDN、外部字体、埋点、任何 src。"""
    html = render_html(payload)
    forbidden_markers = (
        "<link", "<img", "<iframe", " src=", "@import", "url(http", "fonts.googleapis",
    )
    for forbidden in forbidden_markers:
        assert forbidden not in html


def test_rendered_page_escapes_hostile_command_text() -> None:
    """命令原文是外部数据。带尖括号的命令必须以转义形式落地，不能提前闭合标签。"""
    hostile = '</script><img src=x onerror=alert(1)> "quoted"'
    sample = Sample(
        command=hostile,
        agent="codex",
        project="demo",
        status="failed",
        exit_code=1,
        duration_s=1.0,
        duration_source="self_reported",
        failure_kind="network",
        error_snippet=hostile,
    )
    section = Section(
        key="s",
        title=hostile,
        note=hostile,
        kind="bar",
        columns=("program", "failures"),
        bar_column="failures",
        rows=(Row(cells=(hostile, 1), bar_ratio=1.0, samples=(sample,), drill_sql=hostile),),
        sql=hostile,
    )
    track = Track(
        key="failure",
        title="失败线",
        tone="failure",
        scope_name=STATUS_ONLY.name,
        caveat=hostile,
        lead=hostile,
        sections=(section,),
    )
    html = render_html(
        Payload(
            generated_at=hostile,
            source_db=hostile,
            coverage={hostile: hostile},
            tracks=(track,),
            warnings=(hostile,),
        )
    )
    # 外部数据走 payload_to_json，落地形态是 \uXXXX，不是 HTML 实体。
    assert hostile not in html
    assert "\\u003c/script\\u003e" in html
    assert "onerror=alert(1)\\u003e" in html
    # 注入不能凭空多出标签：script 数量与空外壳一致。
    assert html.count("<script") == load_shell().count("<script")
    assert html.count("</script>") == load_shell().count("</script>")


def test_rendered_page_shows_the_real_command_text(payload: Payload) -> None:
    """下钻区要能看到命令原文本身，否则「这一行是哪些命令」答不上来。"""
    html = render_html(payload)
    assert "git push origin main" in html


def test_payload_dashboard_uses_real_aggregations(payload: Payload) -> None:
    """工作台图表必须来自 commands 聚合，不能拿硬编码装饰数据冒充趋势。"""
    assert payload.dashboard.timeline
    assert all(point.day for point in payload.dashboard.timeline)
    assert all(point.runs >= point.failures >= 0 for point in payload.dashboard.timeline)
    assert payload.dashboard.failures_by_kind


def test_findings_template_and_program_are_deterministic(tmp_path: Path) -> None:
    """finding 的 template/program 必须是确定性的代表行，不随查询漂移。"""
    from cmdaudit.store import SCHEMA

    db_path = tmp_path / "commands.duckdb"
    conn = duckdb.connect(str(db_path))
    insert = (
        "INSERT INTO commands VALUES ("
        + ", ".join("?" for _ in range(27))
        + ")"
    )

    def row(call_id: int, started_at: str, command: str, snippet: str, program: str) -> tuple:
        return (
            "s", "codex", "p", call_id, 0, started_at, "exec_command", command, None,
            "cmd", None, "unknown", False, 1, "failed", "exit_code", "network", snippet,
            program, program, None, "test", True, command, command, "tid-shared", False,
        )

    try:
        conn.execute(SCHEMA)
        conn.execute("DELETE FROM commands")
        conn.executemany(
            insert,
            [
                # 同一 template_id 组内三行，template/program 不同：
                # any_value 会漂，first(... ORDER BY started_at, call_id) 不会。
                row(1, "2026-08-01", "npm run build", "a", "npm"),
                row(2, "2026-08-02", "npm run build 2", "b", "npm2"),
                row(3, "2026-08-03", "npm run build 2", "c", "npm2"),
            ],
        )
    finally:
        conn.close()

    conn = duckdb.connect(str(db_path), read_only=True)
    try:
        first = collect_payload(conn, source_db=str(db_path), generated_at="t1").findings
        second = collect_payload(conn, source_db=str(db_path), generated_at="t2").findings
    finally:
        conn.close()

    assert first == second
    # 代表行是组内最早的一条：template/program 取 call_id=1 那行。
    finding = first[0]
    assert finding.finding_id.startswith("tid-shared")
    assert finding.template == "npm run build"
    assert finding.program == "npm"


def test_rendered_workbench_contains_product_controls(payload: Payload) -> None:
    """交互面在编译外壳里，标签文本可断言；缺了说明外壳没重新构建。"""
    html = render_html(payload)
    assert '<div id="root"></div>' in html
    assert 'id="cmdaudit-payload"' in html
    for marker in ("命令面板", "失败模式详情", "运行信号", "失败类型构成"):
        assert marker in html, marker


def test_rendered_page_prints_both_scopes_and_caveats(payload: Payload) -> None:
    """口径不能只存在于 payload：外壳必须有打印它的模板和不可相加的告示。"""
    html = render_html(payload)
    # 数据侧：两条轨道各带自己的口径名与 caveat。
    assert '"scope_name":"status_only"' in html
    assert '"scope_name":"exact"' in html
    for track in payload.tracks:
        assert track.caveat
    # 模板侧：口径徽标与跨轨道告示都在外壳里。
    assert "口径 " in html
    assert "跨轨道数字口径不同" in html


def test_rendered_page_marks_candidates_as_exploratory(tmp_path: Path) -> None:
    """候选是假设不是结论，页面必须显式标注 exploratory。"""
    path = tmp_path / "candidates.json"
    path.write_text(
        json.dumps(
            {
                "contract": {"evidence_class": "exploratory"},
                "candidates": [
                    {
                        "candidate_id": "c1",
                        "source_rule": "repeat_failure",
                        "command_shape": "npm install",
                        "priority": 1.0,
                        "hypothesis": "假设",
                        "verification": {"design": "设计"},
                        "observed": {"failures": 3},
                        "caveats": ["样本量小"],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    candidates, note, _ = _load_candidates(path)
    assert len(candidates) == 1
    assert "exploratory" in note


def test_build_viz_writes_a_self_contained_file(tmp_path: Path) -> None:
    db_path = _write_db(tmp_path)
    out = tmp_path / "report.html"
    written = build_viz(db_path, out)
    assert written == out
    text = out.read_text(encoding="utf-8")
    assert text.lower().startswith("<!doctype html>")
    assert text.rstrip().endswith("</html>")
    assert "<style" in text  # CSS 内联（Vite 产物带属性，不是裸 <style>）
    assert "__CMDAUDIT_PAYLOAD__" not in text  # 占位符已被替换

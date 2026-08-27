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
    MAX_FINDINGS,
    MAX_RETRY_LOOPS,
    MIN_GROUP_RUNS,
    MIN_RETRY_TRIES,
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


def test_rendered_shell_uses_chinese_nav_labels(payload: Payload) -> None:
    """窄屏导航必须渲染中文 label（可访问名称），不能是内部路由 id。

    可访问名称来自 `web/src/lib/views.ts` 的 VIEWS，编译进外壳后应可断言。
    aria-current="page" 是当前视图按钮的选中态标注。
    """
    html = render_html(payload)
    for label in ("总览", "失败模式", "处理看板", "耗时分析", "验证队列", "证据与口径"):
        assert label in html, label
    assert "aria-current" in html


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


def test_wheel_ships_the_compiled_shell(tmp_path: Path) -> None:
    """wheel 必须包含编译好的 shell.html，否则装包后 `cmdaudit viz` 不可用。

    用 `--no-build-isolation` 走当前环境的 setuptools（dev 依赖里已声明），
    离线即可构建，不依赖 PyPI。
    """
    import subprocess
    import sys
    import zipfile

    repo_root = Path(__file__).resolve().parents[1]
    wheel_dir = tmp_path / "wheel"
    wheel_dir.mkdir()
    subprocess.run(
        [
            sys.executable, "-m", "pip", "wheel", ".",
            "--no-deps", "--no-build-isolation", "-w", str(wheel_dir),
        ],
        check=True,
        capture_output=True,
        cwd=repo_root,
    )
    wheels = list(wheel_dir.glob("*.whl"))
    assert len(wheels) == 1
    with zipfile.ZipFile(wheels[0]) as archive:
        names = set(archive.namelist())
        assert "cmdaudit/viz/shell.html" in names
        shell = archive.read("cmdaudit/viz/shell.html").decode("utf-8")
    # 外壳里必须有 payload 占位符，Python 侧注入才有落点。
    assert "__CMDAUDIT_PAYLOAD__" in shell


def test_findings_total_and_kinds_are_not_truncated(tmp_path: Path) -> None:
    """>MAX_FINDINGS 条 finding 时 KPI 用未截断总数，失败构成返回全部类型。"""
    from cmdaudit.store import SCHEMA

    kinds = (
        "timeout",
        "network",
        "not_found",
        "permission",
        "build",
        "test",
        "interrupted",
        "other",
    )
    db_path = tmp_path / "commands.duckdb"
    conn = duckdb.connect(str(db_path))
    try:
        conn.execute(SCHEMA)
        conn.execute("DELETE FROM commands")
        rows: list[tuple] = []
        for group in range(MAX_FINDINGS + 10):
            kind = kinds[group % len(kinds)]
            for slot in (0, 1):
                call_id = group * 2 + slot
                command = f"npm run build-{group}"
                rows.append(
                    (
                        "s", "codex", "p", call_id, 0, "2026-08-01", "exec_command",
                        command, None, "cmd", None, "unknown", False, 1, "failed",
                        "exit_code", kind, f"snippet-{group}", "npm", "npm", "run",
                        "test", True, command, command, f"tid-{group}", False,
                    )
                )
        conn.executemany(
            "INSERT INTO commands VALUES (" + ", ".join("?" for _ in range(27)) + ")",
            rows,
        )
    finally:
        conn.close()

    conn = duckdb.connect(str(db_path), read_only=True)
    try:
        payload = collect_payload(conn, source_db=str(db_path), generated_at="t")
    finally:
        conn.close()

    # KPI 数字用未截断总数；列表仍受 MAX_FINDINGS 约束。
    assert payload.findings_total == MAX_FINDINGS + 10
    assert len(payload.findings) == MAX_FINDINGS
    # 失败构成返回全部 8 类（不能 LIMIT 6 静默截断），百分比合计才是 100%。
    by_kind = dict(payload.dashboard.failures_by_kind)
    assert set(by_kind) == set(kinds)
    assert sum(by_kind.values()) == 2 * (MAX_FINDINGS + 10)


def _seed(db_path: Path, rows: list[tuple]) -> None:
    """把整批行写进一个干净的 commands 表。"""
    from cmdaudit.store import SCHEMA

    conn = duckdb.connect(str(db_path))
    try:
        conn.execute(SCHEMA)
        conn.execute("DELETE FROM commands")
        conn.executemany(
            "INSERT INTO commands VALUES (" + ", ".join("?" for _ in range(27)) + ")",
            rows,
        )
    finally:
        conn.close()


def _cmd_row(
    *,
    call_id: int,
    session: str,
    command: str,
    template_id: str,
    status: str,
    group: str = "pkg",
    duration: float | None = None,
    source: str = "self_reported",
) -> tuple:
    return (
        session, "codex", "p", call_id, 0, f"2026-08-{(call_id % 27) + 1:02d}",
        "exec_command", command, None, "cmd", duration, source, False,
        1 if status == "failed" else 0, status, "exit_code",
        "build" if status == "failed" else None, "snippet", "npm", "npm", "run",
        group, True, command, command, template_id, False,
    )


def test_retry_loop_samples_keep_duplicate_command_text(tmp_path: Path) -> None:
    """重试链的样本**不能**按原文去重。

    去重是其它聚合行的正确行为，但重试链的定义就是「同一条命令重复执行」——
    去重会把 6 次尝试压成 1 行，整个视图的证据随之消失。
    """
    db_path = tmp_path / "commands.duckdb"
    _seed(
        db_path,
        [
            _cmd_row(
                call_id=i,
                session="sess-a",
                command="npm run build",
                template_id="tid-loop",
                status="failed",
            )
            for i in range(6)
        ],
    )

    conn = duckdb.connect(str(db_path), read_only=True)
    try:
        payload = collect_payload(conn, source_db=str(db_path), generated_at="t")
    finally:
        conn.close()

    assert len(payload.retry_loops) == 1
    loop = payload.retry_loops[0]
    assert loop.tries == 6
    assert loop.failures == 6
    # 6 次同样的原文必须全部留在样本里（受 SAMPLES_PER_ROW 上限约束）。
    assert len(loop.samples) == SAMPLES_PER_ROW
    assert {sample.command for sample in loop.samples} == {"npm run build"}


def test_retry_loops_do_not_span_sessions(tmp_path: Path) -> None:
    """重试链按 session 切分：跨会话重跑同一命令不是一次卡死。"""
    db_path = tmp_path / "commands.duckdb"
    rows = [
        _cmd_row(
            call_id=i,
            session=f"sess-{i % 2}",
            command="npm run build",
            template_id="tid-loop",
            status="failed",
        )
        for i in range(8)
    ]
    _seed(db_path, rows)

    conn = duckdb.connect(str(db_path), read_only=True)
    try:
        payload = collect_payload(conn, source_db=str(db_path), generated_at="t")
    finally:
        conn.close()

    # 8 次分摊到两个会话 → 两条各 4 次的链，而不是一条 8 次的。
    assert len(payload.retry_loops) == 2
    assert {loop.tries for loop in payload.retry_loops} == {4}
    assert {loop.session_id for loop in payload.retry_loops} == {"sess-0", "sess-1"}


def test_retry_loops_total_is_not_truncated(tmp_path: Path) -> None:
    """>MAX_RETRY_LOOPS 条链时 KPI 用未截断总数，否则页面静默少报。"""
    db_path = tmp_path / "commands.duckdb"
    rows: list[tuple] = []
    count = MAX_RETRY_LOOPS + 5
    for chain in range(count):
        for attempt in range(MIN_RETRY_TRIES):
            rows.append(
                _cmd_row(
                    call_id=chain * MIN_RETRY_TRIES + attempt,
                    session=f"sess-{chain}",
                    command=f"npm run build-{chain}",
                    template_id=f"tid-{chain}",
                    status="failed",
                )
            )
    _seed(db_path, rows)

    conn = duckdb.connect(str(db_path), read_only=True)
    try:
        payload = collect_payload(conn, source_db=str(db_path), generated_at="t")
    finally:
        conn.close()

    assert payload.retry_loops_total == count
    assert len(payload.retry_loops) == MAX_RETRY_LOOPS


def test_retry_loops_need_a_minimum_number_of_tries(tmp_path: Path) -> None:
    """低于 MIN_RETRY_TRIES 的重复不算链：两次重跑是事件，不是循环。"""
    db_path = tmp_path / "commands.duckdb"
    _seed(
        db_path,
        [
            _cmd_row(
                call_id=i,
                session="sess-a",
                command="npm run build",
                template_id="tid-short",
                status="failed",
            )
            for i in range(MIN_RETRY_TRIES - 1)
        ],
    )

    conn = duckdb.connect(str(db_path), read_only=True)
    try:
        payload = collect_payload(conn, source_db=str(db_path), generated_at="t")
    finally:
        conn.close()

    assert payload.retry_loops == ()
    assert payload.retry_loops_total == 0


def test_retry_loop_wasted_time_only_counts_trusted_duration(tmp_path: Path) -> None:
    """`wasted_s` 只累加 DURATION_GUARD 口径内的耗时，是下界不是估算。"""
    db_path = tmp_path / "commands.duckdb"
    rows = [
        # 可信：self_reported 且未截断。
        _cmd_row(
            call_id=i,
            session="sess-a",
            command="npm run build",
            template_id="tid-loop",
            status="failed",
            duration=2.0,
            source="self_reported",
        )
        for i in range(4)
    ]
    # 不可信来源的耗时必须被排除，否则 wasted_s 会把推测值当事实。
    rows.append(
        _cmd_row(
            call_id=99,
            session="sess-a",
            command="npm run build",
            template_id="tid-loop",
            status="failed",
            duration=500.0,
            source="inferred",
        )
    )
    _seed(db_path, rows)

    conn = duckdb.connect(str(db_path), read_only=True)
    try:
        payload = collect_payload(conn, source_db=str(db_path), generated_at="t")
    finally:
        conn.close()

    loop = payload.retry_loops[0]
    assert loop.tries == 5
    # 4 × 2.0 秒；那条 500 秒的 inferred 不进账。
    assert loop.wasted_s == pytest.approx(8.0)


def test_group_profiles_drop_small_samples(tmp_path: Path) -> None:
    """低于 MIN_GROUP_RUNS 的类别不出现：小样本失败率是噪声不是信号。"""
    db_path = tmp_path / "commands.duckdb"
    rows: list[tuple] = []
    # 达标类别：MIN_GROUP_RUNS 条，其中四分之一失败。
    for i in range(MIN_GROUP_RUNS):
        rows.append(
            _cmd_row(
                call_id=i,
                session="sess-a",
                command=f"npm run x-{i}",
                template_id=f"tid-{i}",
                status="failed" if i % 4 == 0 else "ok",
                group="pkg",
            )
        )
    # 不达标类别：一条全失败，失败率 100% —— 正是必须被门槛挡掉的假信号。
    rows.append(
        _cmd_row(
            call_id=9000,
            session="sess-a",
            command="cmake --build .",
            template_id="tid-tiny",
            status="failed",
            group="build",
        )
    )
    _seed(db_path, rows)

    conn = duckdb.connect(str(db_path), read_only=True)
    try:
        payload = collect_payload(conn, source_db=str(db_path), generated_at="t")
    finally:
        conn.close()

    groups = {profile.group: profile for profile in payload.group_profiles}
    assert "build" not in groups
    assert groups["pkg"].runs == MIN_GROUP_RUNS
    assert groups["pkg"].failure_pct == pytest.approx(25.0)


def test_group_profiles_are_sorted_by_failure_rate(tmp_path: Path) -> None:
    """按失败率降序：本视图的存在意义就是让小体量高失败率的类别不被体量淹没。"""
    db_path = tmp_path / "commands.duckdb"
    rows: list[tuple] = []
    # 大体量低失败率。
    for i in range(4 * MIN_GROUP_RUNS):
        rows.append(
            _cmd_row(
                call_id=i,
                session="sess-a",
                command=f"rg pattern-{i}",
                template_id=f"tid-read-{i}",
                status="failed" if i % 4 == 0 else "ok",
                group="search_read",
            )
        )
    # 小体量高失败率:绝对失败数远少于上面(50 < 100),但失败率高一倍(50% > 25%)。
    for i in range(MIN_GROUP_RUNS):
        rows.append(
            _cmd_row(
                call_id=10_000 + i,
                session="sess-a",
                command=f"cmake --build {i}",
                template_id=f"tid-build-{i}",
                status="failed" if i % 2 == 0 else "ok",
                group="build",
            )
        )
    _seed(db_path, rows)

    conn = duckdb.connect(str(db_path), read_only=True)
    try:
        payload = collect_payload(conn, source_db=str(db_path), generated_at="t")
    finally:
        conn.close()

    ordered = [profile.group for profile in payload.group_profiles]
    assert ordered[0] == "build", ordered
    rates = [profile.failure_pct for profile in payload.group_profiles]
    assert rates == sorted(rates, reverse=True)
    # 绝对失败数是反向的 —— 这正是不能只按失败数排序的证据。
    by_group = {profile.group: profile for profile in payload.group_profiles}
    assert by_group["search_read"].failures > by_group["build"].failures

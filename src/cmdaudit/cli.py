"""命令行入口。

M1 只提供 `extract`；`report` / `screen` 在 M2 / M3 加，`viz` 在 M5 加。
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import webbrowser
from pathlib import Path

from cmdaudit.db import open_commands_db
from cmdaudit.extract.duration import YIELD_CEILING_S, TruncationPolicy
from cmdaudit.pipeline import ExtractStats, build_records
from cmdaudit.report.build import build_tables, collect_coverage
from cmdaudit.report.render import render_json, render_markdown
from cmdaudit.screen.build import collect_candidates
from cmdaudit.screen.build import render_json as render_candidates_json
from cmdaudit.screen.build import render_markdown as render_candidates_markdown
from cmdaudit.sources.agentsview import (
    DEFAULT_DB_PATH,
    SchemaMismatch,
    count_bash_calls,
    iter_raw_calls,
    open_readonly,
)
from cmdaudit.store import write_commands, write_stats
from cmdaudit.viz.build import build_viz

DEFAULT_OUT_DIR = Path("out")


def _cmd_extract(args: argparse.Namespace) -> int:
    out_dir: Path = args.out_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    db_out = out_dir / "commands.duckdb"

    try:
        conn = open_readonly(args.db)
    except (FileNotFoundError, SchemaMismatch) as exc:
        print(f"错误：{exc}", file=sys.stderr)
        return 2

    # issue #30：让出上限是采集环境的属性，随产物记录，不当跨环境常量。
    # 传 0（或负值）表示关掉纯耗时兜底，只认 still-running 这类直接证据。
    ceiling = args.yield_ceiling if args.yield_ceiling > 0 else None
    truncation = TruncationPolicy(yield_ceiling_s=ceiling)

    started = time.monotonic()
    stats = ExtractStats()
    try:
        bash_total = count_bash_calls(conn)
        calls = iter_raw_calls(conn, limit=args.limit)
        written = write_commands(
            db_out, build_records(calls, stats=stats, truncation=truncation)
        )
    finally:
        conn.close()

    elapsed = time.monotonic() - started
    payload = {
        "source_db": str(args.db),
        "bash_tool_calls": bash_total,
        "commands_written": written,
        "elapsed_s": round(elapsed, 2),
        **stats.as_dict(),
        **truncation.as_dict(),
    }
    write_stats(db_out, {k: v for k, v in payload.items() if isinstance(v, int)})
    (out_dir / "extract-stats.json").write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )

    print(f"源库 Bash tool_calls：{bash_total}")
    print(f"排除（非命令工具）：{stats.excluded_tool}")
    print(f"排除（无命令键）：{stats.no_command_key}")
    print(f"抽出命令：{written}（解析降级 {stats.parse_failed}，脱敏 {stats.redacted}）")
    print(f"耗时：{elapsed:.1f}s")
    print(f"输出：{db_out}")
    return 0


def _cmd_report(args: argparse.Namespace) -> int:
    out_dir: Path = args.out_dir
    db_path: Path = args.commands_db or (out_dir / "commands.duckdb")
    try:
        conn = open_commands_db(db_path)
    except FileNotFoundError as exc:
        print(f"错误：{exc}", file=sys.stderr)
        return 2

    try:
        coverage = collect_coverage(conn)
        tables = build_tables(conn)
    finally:
        conn.close()

    out_dir.mkdir(parents=True, exist_ok=True)
    markdown = render_markdown(tables=tables, coverage=coverage, source_db=str(db_path))
    payload = render_json(tables=tables, coverage=coverage, source_db=str(db_path))
    (out_dir / "report.md").write_text(markdown, encoding="utf-8")
    (out_dir / "summary.json").write_text(payload, encoding="utf-8")

    print(f"命令总数：{coverage['命令总数']}")
    print(f"可用于耗时统计：{coverage['可用于耗时统计']}")
    print(f"判定为失败：{coverage['判定为失败']}")
    print(f"表数量：{len(tables)}")
    print(f"输出：{out_dir / 'report.md'}")
    print(f"输出：{out_dir / 'summary.json'}")
    return 0


def _cmd_screen(args: argparse.Namespace) -> int:
    out_dir: Path = args.out_dir
    db_path: Path = args.commands_db or (out_dir / "commands.duckdb")
    try:
        conn = open_commands_db(db_path)
    except FileNotFoundError as exc:
        print(f"错误：{exc}", file=sys.stderr)
        return 2

    try:
        candidates = collect_candidates(conn, per_rule_limit=args.per_rule)
    finally:
        conn.close()

    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "candidates.json").write_text(
        render_candidates_json(candidates), encoding="utf-8"
    )
    (out_dir / "candidates.md").write_text(
        render_candidates_markdown(candidates, top=args.top), encoding="utf-8"
    )

    by_rule: dict[str, int] = {}
    for candidate in candidates:
        by_rule[candidate.source_rule] = by_rule.get(candidate.source_rule, 0) + 1
    print(f"候选总数：{len(candidates)}")
    for rule_name, count in sorted(by_rule.items(), key=lambda item: -item[1]):
        print(f"  {rule_name}: {count}")
    print("证据等级：exploratory（全部 unverified，不得计入质量声明）")
    print(f"输出：{out_dir / 'candidates.md'}")
    print(f"输出：{out_dir / 'candidates.json'}")
    return 0


def _cmd_viz(args: argparse.Namespace) -> int:
    out_dir: Path = args.out_dir
    db_path: Path = args.commands_db or (out_dir / "commands.duckdb")
    out_html: Path = args.out or (out_dir / "report.html")

    # 候选文件缺失不是错误：页面会显式说明队列为空并给出补齐命令。
    candidates = args.candidates or (out_dir / "candidates.json")

    try:
        written = build_viz(
            db_path, out_html, candidates_path=candidates, fixture_path=args.emit_fixture
        )
    except FileNotFoundError as exc:
        print(f"错误：{exc}", file=sys.stderr)
        return 2
    except RuntimeError as exc:
        # 外壳缺失/损坏属于打包问题，直接把修复命令打出来，不留下半成品页面。
        print(f"错误：{exc}", file=sys.stderr)
        return 3

    size_kb = written.stat().st_size / 1024
    print(f"输出：{written}（{size_kb:.0f} KB，离线单文件）")
    if args.open and not webbrowser.open(written.resolve().as_uri()):
        print("警告：未找到可用浏览器，请手动打开该文件", file=sys.stderr)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cmdaudit",
        description="统计 AI coding agent 会话里每条命令的耗时、退出码与失败原因",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    extract = sub.add_parser("extract", help="从 agentsview 会话库抽取命令（只读）")
    extract.add_argument("--db", type=Path, default=DEFAULT_DB_PATH, help="agentsview sessions.db")
    extract.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR, help="输出目录")
    extract.add_argument(
        "--yield-ceiling",
        type=float,
        default=YIELD_CEILING_S,
        help=(
            f"工具让出上限（秒），默认 {YIELD_CEILING_S}（本机 Codex）。"
            "换 agent 或改了 yield_time_ms 时要跟着改；传 0 表示只认直接证据、"
            "不用纯耗时兜底"
        ),
    )
    extract.add_argument(
        "--limit", type=int, default=None, help="只处理前 N 个 tool_call（调试用）"
    )
    extract.set_defaults(func=_cmd_extract)

    report = sub.add_parser("report", help="从 commands 表生成报告")
    report.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR, help="输出目录")
    report.add_argument(
        "--commands-db", type=Path, default=None, help="commands.duckdb 路径，默认取 out-dir 下的"
    )
    report.set_defaults(func=_cmd_report)

    screen = sub.add_parser("screen", help="筛出值得做反事实实验的候选（输出假设，非结论）")
    screen.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR, help="输出目录")
    screen.add_argument(
        "--commands-db", type=Path, default=None, help="commands.duckdb 路径，默认取 out-dir 下的"
    )
    screen.add_argument("--per-rule", type=int, default=15, help="每条规则最多产出多少候选")
    screen.add_argument("--top", type=int, default=20, help="Markdown 里展开前 N 条")
    screen.set_defaults(func=_cmd_screen)

    viz = sub.add_parser("viz", help="生成离线单文件 HTML 报告页（可下钻到命令原文）")
    viz.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR, help="输出目录")
    viz.add_argument(
        "--commands-db", type=Path, default=None, help="commands.duckdb 路径，默认取 out-dir 下的"
    )
    viz.add_argument(
        "--out", type=Path, default=None, help="HTML 输出路径，默认 out-dir/report.html"
    )
    viz.add_argument(
        "--candidates", type=Path, default=None, help="candidates.json 路径，默认取 out-dir 下的"
    )
    viz.add_argument(
        "--emit-fixture",
        type=Path,
        default=None,
        help="额外导出 payload JSON（供 web/ 前端开发用，产物页面不依赖它）",
    )
    viz.add_argument("--open", action="store_true", help="生成后用默认浏览器打开")
    viz.set_defaults(func=_cmd_viz)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    result: int = args.func(args)
    return result


if __name__ == "__main__":
    raise SystemExit(main())

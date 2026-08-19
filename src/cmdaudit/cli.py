"""命令行入口。

M1 只提供 `extract`；`report` / `screen` 在 M2 / M3 加。
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

from cmdaudit.pipeline import ExtractStats, build_records
from cmdaudit.report.build import build_tables, collect_coverage, open_commands_db
from cmdaudit.report.render import render_json, render_markdown
from cmdaudit.sources.agentsview import (
    DEFAULT_DB_PATH,
    SchemaMismatch,
    count_bash_calls,
    iter_raw_calls,
    open_readonly,
)
from cmdaudit.store import write_commands, write_stats

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

    started = time.monotonic()
    stats = ExtractStats()
    try:
        bash_total = count_bash_calls(conn)
        calls = iter_raw_calls(conn, limit=args.limit)
        written = write_commands(db_out, build_records(calls, stats=stats))
    finally:
        conn.close()

    elapsed = time.monotonic() - started
    payload = {
        "source_db": str(args.db),
        "bash_tool_calls": bash_total,
        "commands_written": written,
        "elapsed_s": round(elapsed, 2),
        **stats.as_dict(),
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
        "--limit", type=int, default=None, help="只处理前 N 个 tool_call（调试用）"
    )
    extract.set_defaults(func=_cmd_extract)

    report = sub.add_parser("report", help="从 commands 表生成报告")
    report.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR, help="输出目录")
    report.add_argument(
        "--commands-db", type=Path, default=None, help="commands.duckdb 路径，默认取 out-dir 下的"
    )
    report.set_defaults(func=_cmd_report)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    result: int = args.func(args)
    return result


if __name__ == "__main__":
    raise SystemExit(main())

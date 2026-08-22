"""tree-sitter-bash 解析。每个用例都是原型 shlex 版本的误判样本。"""

from __future__ import annotations

import pytest

from cmdaudit.extract.shellparse import parse_programs


def test_compound_command_extracts_all_programs() -> None:
    programs, primary, sub, ok = parse_programs(
        "cd /x && git log | head -3; VAR=1 npm run build 2>&1 || echo fail"
    )
    assert ok
    assert programs == ("cd", "git", "head", "npm", "echo")
    # cd 是目录切换，不代表这条命令在做什么。
    assert (primary, sub) == ("git", "log")


@pytest.mark.parametrize(
    ("command", "expected_primary"),
    [
        # 原型把 -v 当成程序名。
        ("command -v codex", "codex"),
        # 原型把 +%s%N) 当成程序名。
        ("echo $(date +%s%N)", "echo"),
        # 包装器后的真实程序。
        ("sudo -E env FOO=1 npm ci", "npm"),
        ("timeout 30 pytest -q", "pytest"),
        # 裸包装器本身就是命令。
        ("env", "env"),
        # 绝对路径要取 basename。
        ("/usr/local/bin/rg --files", "rg"),
        # 命令替换里的命令是参数求值，不是主体。
        ("for i in $(seq 1 3); do curl -s http://x; done", "curl"),
        # 只有 cd 时它就是主体。
        ("cd /repo", "cd"),
    ],
)
def test_primary_program(command: str, expected_primary: str) -> None:
    _, primary, _, _ = parse_programs(command)
    assert primary == expected_primary


@pytest.mark.parametrize(
    ("command", "expected"),
    [
        ("git log --oneline -12", ("git", "log")),
        ("gh pr view 118 -R o/r --json x", ("gh", "pr")),
        # npm run <script>：script 名才是语义粒度，分得清 typecheck 与 build。
        ("npm run typecheck", ("npm", "typecheck")),
        ("npm run test:e2e", ("npm", "test:e2e")),
        ("cargo build --release", ("cargo", "build")),
        # python -m 的模块是 subcommand。
        ("python -m pytest", ("python", "pytest")),
        # npx 是运行器，它后面跟的测试框架是 subcommand。
        ("npx jest --ci", ("npx", "jest")),
        # 裸 python script.py 的 script 不是 subcommand。
        ("python scripts/build.py", ("python", None)),
        # 非子命令程序不该编造 subcommand。
        ("rg -n foo src", ("rg", None)),
    ],
)
def test_subcommand(command: str, expected: tuple[str, str | None]) -> None:
    _, primary, sub, _ = parse_programs(command)
    assert (primary, sub) == expected


@pytest.mark.parametrize(
    ("command", "expected"),
    [
        # sudo -u 会吃掉下一个参数：postgres 是用户名，不是主程序。
        ("sudo -u postgres psql -c select", ("psql", None)),
        # kubectl -n 会吃掉 default：get 才是 subcommand。
        ("kubectl -n default get pods", ("kubectl", "get")),
        # git -C 会吃掉 /repo：status 才是 subcommand。
        ("git -C /repo status", ("git", "status")),
        # --namespace=value 自带值，不额外吃参数。
        ("kubectl --namespace=prod get svc", ("kubectl", "get")),
    ],
)
def test_option_arity_eats_next_argument(command: str, expected: tuple[str, str | None]) -> None:
    """带参数的选项（sudo -u / kubectl -n / git -C）不能把参数当程序名或 subcommand。"""
    programs, primary, sub, _ = parse_programs(command)
    assert (primary, sub) == expected
    assert expected[0] in programs


def test_heredoc_body_is_not_parsed_as_commands() -> None:
    programs, primary, _, _ = parse_programs("python3 - <<'PY'\n# comment\nprint(1)\nPY")
    assert primary == "python3"
    assert "#" not in programs


def test_redaction_placeholder_does_not_break_parsing() -> None:
    """`<redacted>` 里的 `<` 是重定向符，会让整条命令解析失败。"""
    programs, primary, _, ok = parse_programs("mkdir -p REDACTED && curl -L -o a.pdf https://x/1")
    assert ok
    assert primary == "mkdir"
    assert "curl" in programs


def test_empty_command_reports_failure() -> None:
    assert parse_programs("") == ((), "", None, False)


def test_unparseable_command_degrades_instead_of_dropping() -> None:
    """解析失败要降级取第一个 token，不能丢记录。"""
    programs, primary, _, ok = parse_programs("git commit -m 'unclosed")
    assert primary == "git"
    assert programs
    assert ok is False

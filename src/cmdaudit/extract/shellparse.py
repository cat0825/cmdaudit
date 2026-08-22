"""tree-sitter-bash 封装：提取命令里出现的程序名与子命令。

替代原型里的 shlex 切分。原型的误判样本（写在测试里防回归）：
`command -v codex` 把 `-v` 当程序名、heredoc 里的注释行被当成命令、
`$(date +%s%N)` 里的 `+%s%N)` 被当成程序名。
"""

from __future__ import annotations

import re
from functools import lru_cache
from typing import Final

import tree_sitter_bash
from tree_sitter import Language, Node, Parser

#: 这些包装器带一个位置参数，之后才是真正的程序（`timeout 30 pytest`）。
_WRAPPERS_WITH_ARG: Final[frozenset[str]] = frozenset({"timeout", "nice", "stdbuf"})

#: 这些是 shell 内建/包装器，真正的程序在其后。
_WRAPPERS: Final[frozenset[str]] = frozenset(
    {
        "sudo",
        "command",
        "env",
        "time",
        "nohup",
        "exec",
        "xargs",
        "nice",
        "timeout",
        "builtin",
        "stdbuf",
        "unbuffer",
        "doas",
    }
)

#: 带子命令的程序，取其第一个非选项参数作为 subcommand。
_SUBCOMMAND_PROGRAMS: Final[frozenset[str]] = frozenset(
    {
        "git",
        "gh",
        "npm",
        "pnpm",
        "yarn",
        "cargo",
        "go",
        "docker",
        "kubectl",
        "pip",
        "pip3",
        "uv",
        "brew",
        "apt",
        "apt-get",
        "systemctl",
        "glab",
        "aws",
        "gcloud",
        "terraform",
        "poetry",
        "bundle",
        "dotnet",
        "swift",
        "conda",
        "make",
        "npx",
    }
)

#: 用 `run <script>` 执行 npm script 的包管理器。script 名才是语义粒度：
#: 只抽到 run 分不清 `npm run build` 与 `npm run typecheck`（耗时差一倍以上）。
_RUN_SCRIPT_PROGRAMS: Final[frozenset[str]] = frozenset({"npm", "pnpm", "yarn", "bun"})

#: `python -m <module>` 的模块名是测试入口判定要用的 subcommand。
_PYTHON_PROGRAMS: Final[frozenset[str]] = frozenset({"python", "python3"})

#: npm script 名允许 `:`（test:e2e）、`@`（scope）等字符，比程序名宽。
_RE_SCRIPT_NAME: Final[re.Pattern[str]] = re.compile(r"^[A-Za-z0-9_@][A-Za-z0-9_@:./+\-]*$")

#: 会吃掉下一个参数的选项集。`--opt=value` 自带值不在此列，
#: 解析时先按 `=` 短路。未知选项保守降级：宁可 subcommand 取 None，
#: 也不能把 option 的参数当程序名（`sudo -u postgres psql` 的 postgres 是 sudo 的用户名）。
_OPTION_ARITY: Final[dict[str, frozenset[str]]] = {
    "sudo": frozenset({"-u", "--user", "-g", "--group", "-h", "--host"}),
    "git": frozenset({"-C", "-c"}),
    "kubectl": frozenset({"-n", "--namespace", "--context"}),
}

#: 目录切换与环境设置类内建：有其他程序时不当主程序，但仍记进 programs。
_TRANSPARENT: Final[frozenset[str]] = frozenset(
    {"cd", "pushd", "popd", "export", "set", "unset", "source", "alias", "shift"}
)

_RE_PLAUSIBLE_PROGRAM: Final[re.Pattern[str]] = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_.+\-]*$")


@lru_cache(maxsize=1)
def _parser() -> Parser:
    return Parser(Language(tree_sitter_bash.language()))


def _node_text(node: Node, src: bytes) -> str:
    return src[node.start_byte : node.end_byte].decode("utf-8", "replace")


def _basename(token: str) -> str:
    """`/usr/bin/git` → `git`；剥掉引号。"""
    token = token.strip().strip("\"'")
    if "/" in token:
        token = token.rsplit("/", 1)[-1]
    return token


def _is_program(token: str) -> bool:
    return bool(token) and bool(_RE_PLAUSIBLE_PROGRAM.match(token))


def _command_words(node: Node, src: bytes) -> list[str]:
    """一个 command 节点里的实义词（跳过赋值前缀与重定向）。"""
    words: list[str] = []
    for child in node.named_children:
        if child.type in {"variable_assignment", "file_redirect", "herestring_redirect"}:
            continue
        if child.type == "command_name":
            inner = child.named_children[0] if child.named_children else child
            words.append(_node_text(inner, src))
        elif child.type in {"word", "string", "raw_string", "concatenation", "number"}:
            words.append(_node_text(child, src))
    return words


def _skip_options(words: list[str], index: int, arity: frozenset[str]) -> int:
    """从 index 起跳过选项；arity 里的选项连它的参数一起跳过。

    `--opt=value` 自带值，不额外吃参数。KEY=VALUE 前缀（变量赋值）也要跳过，
    树解析可能把它们留在实义词序列里。
    """
    while index < len(words):
        token = words[index]
        if token.startswith("--") and "=" in token:
            index += 1
            continue
        if token in arity:
            index += 2
            continue
        if token.startswith("-") or re.match(r"^[A-Za-z_][A-Za-z0-9_]*=", token) is not None:
            index += 1
            continue
        break
    return index


def _resolve(words: list[str]) -> tuple[str, str | None]:
    """从实义词序列解析 (program, subcommand)，跳过包装器与其选项。

    包装器后面没有真实程序时（例如裸 `env` 用于打印环境变量），
    包装器自己就是这条命令要执行的程序。
    """
    wrapper_seen = ""
    index = 0
    while index < len(words):
        candidate = _basename(words[index])
        if not _is_program(candidate):
            index += 1
            continue
        if candidate in _WRAPPERS:
            if not wrapper_seen:
                wrapper_seen = candidate
            index += 1
            # 跳过包装器自己的选项（含会吃参数的选项）。
            index = _skip_options(words, index, _OPTION_ARITY.get(candidate, frozenset()))
            # `timeout 30 pytest` 这类：跳过包装器的位置参数。
            if (
                candidate in _WRAPPERS_WITH_ARG
                and index < len(words)
                and re.match(r"^[0-9]+(?:\.[0-9]+)?[smhd]?$", words[index])
            ):
                index += 1
            continue
        sub: str | None = None
        if candidate in _SUBCOMMAND_PROGRAMS:
            # 选项（及其参数）不能当 subcommand：`git -C /repo status` 的 /repo
            # 是 -C 的路径，`kubectl -n default get pods` 的 default 是 namespace。
            i = _skip_options(words, index + 1, _OPTION_ARITY.get(candidate, frozenset()))
            if i < len(words):
                cleaned = words[i].strip().strip("\"'")
                if _RE_PLAUSIBLE_PROGRAM.match(cleaned):
                    sub = cleaned
                    # `npm run <script>`：script 名才是语义粒度，用来判定测试入口。
                    if candidate in _RUN_SCRIPT_PROGRAMS and cleaned == "run":
                        j = _skip_options(words, i + 1, frozenset())
                        if j < len(words):
                            script = words[j].strip().strip("\"'")
                            if _RE_SCRIPT_NAME.match(script):
                                sub = script
        elif candidate in _PYTHON_PROGRAMS:
            # `python -m pytest`：-m 后的模块是测试入口判定要用的 subcommand；
            # 裸 `python script.py` 里的 script 不是 subcommand，保持 None。
            for k in range(index + 1, len(words)):
                if words[k] == "-m" and k + 1 < len(words):
                    module = words[k + 1].strip().strip("\"'")
                    if module and not module.startswith("-"):
                        sub = module
                    break
        return candidate, sub
    return wrapper_seen, None


_NESTING_TYPES: Final[frozenset[str]] = frozenset(
    {"command_substitution", "process_substitution", "arithmetic_expansion"}
)


def _collect_commands(root: Node) -> list[tuple[Node, bool]]:
    """按源码顺序收集 command 节点，并标记它是否位于命令替换内部。"""
    found: list[tuple[Node, bool]] = []
    stack: list[tuple[Node, bool]] = [(root, False)]
    while stack:
        node, nested = stack.pop()
        if node.type == "command":
            found.append((node, nested))
        child_nested = nested or node.type in _NESTING_TYPES
        stack.extend((child, child_nested) for child in reversed(node.named_children))
    found.sort(key=lambda pair: pair[0].start_byte)
    return found


def parse_programs(command: str) -> tuple[tuple[str, ...], str, str | None, bool]:
    """返回 (全部程序名, 主程序, 主程序子命令, 解析是否成功)。

    解析失败时降级为「取第一个像程序名的 token」，不丢弃记录。
    """
    text = command.strip()
    if not text:
        return (), "", None, False

    src = text.encode("utf-8")
    tree = _parser().parse(src)
    programs: list[str] = []
    primary = ""
    primary_sub: str | None = None

    ordered = _collect_commands(tree.root_node)
    fallback: tuple[str, str | None] | None = None

    for node, nested in ordered:
        program, sub = _resolve(_command_words(node, src))
        if not program:
            continue
        if program not in programs:
            programs.append(program)
        if primary:
            continue
        # 命令替换/进程替换里的命令是参数求值，不是这条命令的主体。
        # 目录切换类内建也不代表这条命令在做什么。
        if nested or program in _TRANSPARENT:
            if fallback is None:
                fallback = (program, sub)
            continue
        primary, primary_sub = program, sub

    if not primary and fallback is not None:
        primary, primary_sub = fallback

    if primary:
        return tuple(programs), primary, primary_sub, not tree.root_node.has_error

    # 降级：取第一个像程序名的 token。
    for token in re.split(r"[\s|;&()]+", text):
        candidate = _basename(token)
        if _is_program(candidate) and candidate not in _WRAPPERS:
            return (candidate,), candidate, None, False
    return (), "", None, False

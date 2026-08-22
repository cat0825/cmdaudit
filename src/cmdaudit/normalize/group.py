"""程序 → 命令分组表。

`wait` 是独立分组，不并入 `proc_sys`：等待外部系统既不是有效工作也不是
进程管理，混在一起会掩盖信号。原型实测纯等待占全部 shell 时间 14.4%，
比整个 test 分组（8.8%）还大。
"""

from __future__ import annotations

import re
from typing import Final

CommandGroup = str

#: 会跑测试的包管理器/运行器。`npx jest` 的 jest、`npm test` 的 test 都是测试入口。
_PKG_RUNNERS: Final[frozenset[str]] = frozenset(
    {"npm", "pnpm", "yarn", "bun", "npx", "cargo", "go", "python", "python3"}
)

#: 直接以运行器身份出现的测试框架。
_TEST_RUNNERS: Final[frozenset[str]] = frozenset(
    {"jest", "vitest", "playwright", "pytest", "unittest"}
)

#: npm script 的测试命名习惯：test / test:unit / test:e2e。typecheck 不算测试。
_RE_TEST_SCRIPT: Final[re.Pattern[str]] = re.compile(r"^test(?:[:_-].*)?$", re.IGNORECASE)

_GROUPS: Final[dict[str, tuple[str, ...]]] = {
    "wait": ("sleep", "wait", "watch"),
    "vcs": ("git", "gh", "glab", "hg", "svn", "jj", "git-lfs", "cr"),
    "build": ("make", "cmake", "ninja", "gcc", "g++", "clang", "clang++", "cargo", "go",
              "tsc", "swift", "javac", "gradle", "mvn", "bazel", "xcodebuild", "dotnet",
              "rustc", "esbuild", "vite", "webpack", "meson"),
    "test": ("pytest", "jest", "vitest", "mocha", "ctest", "gtest", "tox", "nose",
             "phpunit", "rspec", "junit", "playwright", "cypress", "nyc"),
    "pkg": ("npm", "pnpm", "yarn", "bun", "pip", "pip3", "uv", "poetry", "pipx",
            "brew", "apt", "apt-get", "conda", "bundle", "gem", "composer", "nix"),
    "net": ("curl", "wget", "ssh", "scp", "rsync", "nc", "ping", "dig", "nslookup",
            "http", "httpie", "telnet", "sftp", "aws", "gcloud", "az", "wrangler"),
    "search_read": ("rg", "grep", "ag", "ack", "find", "fd", "cat", "head", "tail",
                    "less", "more", "nl", "wc", "sort", "uniq", "cut", "tr", "jq",
                    "yq", "diff", "column", "fzf", "tree", "ls", "stat", "file",
                    "strings", "xxd", "od", "basename", "dirname", "readlink"),
    "fs_mutate": ("cp", "mv", "rm", "mkdir", "rmdir", "touch", "ln", "chmod", "chown",
                  "tar", "zip", "unzip", "gzip", "gunzip", "dd", "install", "truncate",
                  "sed", "awk", "tee", "patch"),
    "lint_fmt": ("ruff", "eslint", "prettier", "black", "isort", "mypy", "flake8",
                 "pylint", "clang-format", "clang-tidy", "gofmt", "rustfmt",
                 "shellcheck", "biome", "stylelint", "markdownlint"),
    "runtime": ("python", "python3", "node", "deno", "ruby", "perl", "php", "java",
                "bash", "sh", "zsh", "osascript", "Rscript", "julia", "lua"),
    "container": ("docker", "podman", "kubectl", "helm", "docker-compose", "colima",
                  "minikube", "k9s", "nerdctl"),
    "db": ("sqlite3", "psql", "mysql", "redis-cli", "mongosh", "duckdb", "pg_dump",
           "clickhouse-client"),
    "proc_sys": ("ps", "kill", "pkill", "killall", "top", "htop", "lsof", "df", "du",
                 "uname", "sysctl", "launchctl", "systemctl", "service", "nproc",
                 "uptime", "whoami", "id", "date", "env", "printenv", "ulimit",
                 "defaults", "open", "pbcopy", "pbpaste", "mdfind", "codesign", "otool"),
    "shell_noop": ("echo", "printf", "true", "false", "cd", "pushd", "popd", "export",
                   "set", "unset", "source", "alias", "which", "type", "pwd", "clear",
                   "seq", "sleepless", "exit", "return", "read", "eval", "test", "["),
}

_PROGRAM_TO_GROUP: Final[dict[str, str]] = {
    program: group for group, programs in _GROUPS.items() for program in programs
}

GROUP_NAMES: Final[tuple[str, ...]] = (*_GROUPS.keys(), "other")


def classify_group(
    program: str, programs: tuple[str, ...] = (), subcommand: str | None = None
) -> CommandGroup:
    """主程序优先；主程序未知时看复合命令里是否有已知程序。

    测试入口优先于分组表：`npm test` / `cargo test` / `python -m pytest`
    这类命令要落到 `test` 组，否则测试时间会被摊进 pkg/build/runtime。
    非测试子命令保持原分组（`npm install` 还是 pkg，`cargo build` 还是 build）。
    等待类特殊处理：只要主程序是 sleep 就归 wait，因为
    `sleep 180; tail -5 out.txt` 的实际成本全在等待上。
    """
    if (
        subcommand
        and program in _PKG_RUNNERS
        and (_RE_TEST_SCRIPT.match(subcommand) or subcommand in _TEST_RUNNERS)
    ):
        return "test"
    direct = _PROGRAM_TO_GROUP.get(program)
    if direct is not None:
        return direct
    for candidate in programs:
        group = _PROGRAM_TO_GROUP.get(candidate)
        if group is not None:
            return group
    return "other"

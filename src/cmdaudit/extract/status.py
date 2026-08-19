"""状态判定与失败归因（docs/plan.md §3.3）。

判定优先级，高位命中即停：

1. 退出码 —— `exit_code == 0` 时直接判 ok，**绝不再看输出文本**；
2. `tool_result_events.status` —— 非空即用；
3. 文本启发式 —— 只在前两级都拿不到时使用。

第 1 条是原型踩坑换来的红线：初版扫全量输出，报错率虚高到 20.3%，
改成退出码优先后降到 15.6%。那 4.7 个百分点全是读日志时
输出里出现 `error:` 造成的假阳性。
"""

from __future__ import annotations

import re
from typing import Final

from cmdaudit.models import FailureKind, Outcome

#: 两种退出码格式，实测 `Process exited with code N` 27135 条、`Exit code: N` 402 条。
RE_EXIT_CODE: Final[re.Pattern[str]] = re.compile(
    r"(?:Process exited with code|Exit code:?)\s*(-?[0-9]+)", re.IGNORECASE
)

RE_INTERRUPTED: Final[re.Pattern[str]] = re.compile(
    r"(?:turn[_ ]aborted|user (?:interrupted|aborted)|KeyboardInterrupt|SIGINT)",
    re.IGNORECASE,
)

#: 失败归因规则，按顺序匹配，先命中先归类。规则判定优先于任何模型判定。
_FAILURE_RULES: Final[tuple[tuple[FailureKind, re.Pattern[str]], ...]] = (
    (
        "timeout",
        re.compile(
            r"(?:timed?\s*out|timeout|deadline exceeded|ETIMEDOUT|"
            r"operation (?:has )?timed out|still running)",
            re.IGNORECASE,
        ),
    ),
    (
        "network",
        re.compile(
            r"(?:ECONNREFUSED|ECONNRESET|ENOTFOUND|EAI_AGAIN|ENETUNREACH|"
            r"could not resolve host|connection (?:refused|reset|closed)|"
            r"network is unreachable|ssl\s*(?:error|handshake)|"
            r"tls handshake|proxy|remote end hung up|"
            r"failed to connect|HTTP 5[0-9][0-9]|502 Bad Gateway|"
            r"curl:\s*\([0-9]+\)|"
            # Python/Node 的网络异常类名。
            r"ConnectionError|ConnectionRefused|ConnectionReset|"
            r"NewConnectionError|MaxRetryError|ReadTimeout|ConnectTimeout|"
            r"URLError|SSLError|socket\.timeout|getaddrinfo failed|"
            r"fetch failed|ERR_NETWORK|ERR_INTERNET_DISCONNECTED)",
            re.IGNORECASE,
        ),
    ),
    (
        "permission",
        re.compile(
            r"(?:permission denied|EACCES|EPERM|operation not permitted|"
            r"not authorized|401 unauthorized|403 forbidden|"
            r"authentication failed|sandbox denied|read-only file system)",
            re.IGNORECASE,
        ),
    ),
    (
        "not_found",
        re.compile(
            r"(?:command not found|no such file or directory|ENOENT|"
            r"not a git repository|unknown (?:command|option)|"
            r"cannot find module|module not found|404 not found|"
            r"no matches found|did not match any files)",
            re.IGNORECASE,
        ),
    ),
    (
        "test",
        re.compile(
            r"(?:\d+ (?:tests? )?fail(?:ed|ing)|assertion(?:error| failed)|"
            r"tests? failed|FAIL\s|✗|✖|expected .* (?:but|to) )",
            re.IGNORECASE,
        ),
    ),
    (
        "build",
        re.compile(
            r"(?:compilation (?:failed|error|terminated)|build failed|"
            r"linker command failed|undefined reference|"
            r"error TS[0-9]+|error\[E[0-9]+\]|syntax error|"
            r"fatal error:|ld: symbol|cannot compile)",
            re.IGNORECASE,
        ),
    ),
)

#: 只在没有退出码也没有 result event 时使用；刻意保守，宁漏不误报。
_TEXT_FAILURE: Final[re.Pattern[str]] = re.compile(
    r"(?:^|\n)\s*(?:error|fatal|traceback \(most recent call last\)|"
    r"panic:|abort(?:ed|ing)?):",
    re.IGNORECASE,
)

_SNIPPET_LIMIT: Final[int] = 400

#: 这些程序用退出码 1 表示「查无结果」，不是错误。
#: 实测 rg 95 次、find 36 次、grep 8 次被误判为失败，
#: 这些误判会让 rg 出现在「最容易失败的程序」榜单前列。
_NO_MATCH_PROGRAMS: Final[frozenset[str]] = frozenset(
    {
        # 搜索类：退出码 1 = 没找到匹配。
        "rg", "grep", "egrep", "fgrep", "ag", "ack", "fd", "find",
        # 比较类：退出码 1 = 有差异，这是它的正常答案。
        "diff", "cmp", "test",
        # 探测类：退出码 1 = 未安装。`which pandoc` 返回 1 是一次成功的探测
        # 得到否定答案，不是这条命令出错。
        "which", "type", "hash", "command",
    }
)

#: 只有退出码恰好是 1 才算查无结果；其他非零码是真错误
#: （例如 rg 的 2 表示用法错误）。
_NO_MATCH_EXIT_CODE: Final[int] = 1


def parse_exit_code(result_content: str | None) -> int | None:
    if not result_content:
        return None
    m = RE_EXIT_CODE.search(result_content)
    return int(m.group(1)) if m else None


def classify_failure(text: str | None, exit_code: int | None) -> FailureKind:
    """给已判定为失败的记录归因。规则判定，不用模型。"""
    if text:
        if RE_INTERRUPTED.search(text):
            return "interrupted"
        for kind, pattern in _FAILURE_RULES:
            if pattern.search(text):
                return kind
    if exit_code in (124, 137, 143):  # timeout(1)/SIGKILL/SIGTERM
        return "timeout"
    if exit_code == 126:
        return "permission"
    if exit_code == 127:
        return "not_found"
    if exit_code == 130:
        return "interrupted"
    return "other"


#: 工具自己加的包装行，不是命令输出。片段要跳过它们，否则人工核对时
#: 看到的全是 `Wall time` / `Chunk ID` 而不是真正的报错。
_WRAPPER_LINE: Final[re.Pattern[str]] = re.compile(
    r"^\s*(?:Chunk ID|Wall time|Process exited|Exit code|Original token count|"
    r"Total output lines|Output|Command|Script completed|Process running)\b",
    re.IGNORECASE,
)


def _payload_lines(text: str) -> list[str]:
    """剥掉工具包装行，只留命令自己的输出。"""
    return [
        line
        for line in text.splitlines()
        if line.strip() and not _WRAPPER_LINE.match(line)
    ]


def _snippet(text: str | None) -> str | None:
    """截一段最像错误的片段，供人工核对。

    先剥掉工具包装行再匹配，并且从匹配所在行的行首开始截，
    这样片段总是从一个完整的输出行开始，而不是从半个单词开始。
    """
    if not text:
        return None
    lines = _payload_lines(text)
    if not lines:
        return None
    body = "\n".join(lines)

    for pattern in (_TEXT_FAILURE, RE_INTERRUPTED, *(p for _, p in _FAILURE_RULES)):
        m = pattern.search(body)
        if m:
            # `_TEXT_FAILURE` 用 `(?:^|\n)` 起头，m.start() 会落在换行符上，
            # 直接 rfind 会退回上一行。改用匹配文本里第一个非换行字符定位。
            offset = m.start() + len(m.group(0)) - len(m.group(0).lstrip("\r\n"))
            line_start = body.rfind("\n", 0, offset) + 1
            return body[line_start : line_start + _SNIPPET_LIMIT].strip() or None
    # 没匹配到已知错误模式时，取末尾若干行：报错通常在最后。
    return body[-_SNIPPET_LIMIT:].strip() or None


def is_no_match(program: str, exit_code: int | None, text: str | None) -> bool:
    """判断这是不是「查无结果」而非失败。

    要求同时满足：程序属于搜索类、退出码恰好为 1、且输出里没有该程序自己的
    错误行（`rg: ...` 这类）。第三条排除了「用法写错」被当成查无结果的情况。
    """
    if program not in _NO_MATCH_PROGRAMS or exit_code != _NO_MATCH_EXIT_CODE:
        return False
    own_error = re.search(rf"^\s*{re.escape(program)}:\s", text, re.MULTILINE) if text else None
    return own_error is None


def decide_outcome(
    result_content: str | None, result_status: str | None, program: str = ""
) -> Outcome:
    """三级判定。返回值的不变量由 Outcome 自身守住。"""
    exit_code = parse_exit_code(result_content)

    if exit_code is not None:
        if exit_code == 0:
            # 红线：退出码为 0 时不看文本，哪怕输出里全是 "error:"。
            return Outcome("ok", "exit_code", 0, None, None)
        if is_no_match(program, exit_code, result_content):
            return Outcome("no_match", "exit_code", exit_code, None, None)
        return Outcome(
            "failed",
            "exit_code",
            exit_code,
            classify_failure(result_content, exit_code),
            _snippet(result_content),
        )

    normalized = (result_status or "").strip().lower()
    if normalized:
        if normalized in {"completed", "success", "ok"}:
            return Outcome("ok", "result_event", None, None, None)
        if normalized in {"errored", "error", "failed", "failure"}:
            return Outcome(
                "failed",
                "result_event",
                None,
                classify_failure(result_content, None),
                _snippet(result_content),
            )

    if result_content and _TEXT_FAILURE.search(result_content):
        return Outcome(
            "failed",
            "text_heuristic",
            None,
            classify_failure(result_content, None),
            _snippet(result_content),
        )
    if result_content and RE_INTERRUPTED.search(result_content):
        return Outcome("failed", "text_heuristic", None, "interrupted", _snippet(result_content))

    return Outcome("unknown", "none", None, None, None)

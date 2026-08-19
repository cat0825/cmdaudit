"""落库前脱敏。

模板化天然去掉字面量，但原始 `command` 列仍要保留可读性，
所以这里只打掉明确的凭据模式，不做整体混淆。
"""

from __future__ import annotations

import re
from typing import Final

#: 占位符必须是 shell 安全的裸词：`<redacted>` 里的 `<` 会被 bash 当重定向符，
#: 导致后续 tree-sitter 解析整条命令失败（实测让 294 条 mkdir 全部降级）。
_PLACEHOLDER: Final[str] = "REDACTED"

_PATTERNS: Final[tuple[re.Pattern[str], ...]] = (
    re.compile(r"(?i)(authorization\s*:\s*(?:bearer|basic|token)?\s*)[^\"'\s]+"),
    re.compile(r"(?i)\b(x-api-key\s*:\s*)[^\"'\s]+"),
    re.compile(r"(?i)\b((?:api[_-]?key|access[_-]?token|secret|password|passwd|pwd|token)\s*[=:]\s*)[^\"'\s&]+"),
    # `-p` 只在数据库客户端语境下当密码：否则 `mkdir -p /some/path` 会被误伤，
    # 而误伤会连带破坏后续的程序名解析。
    re.compile(
        r"(?i)\b((?:mysql|mysqldump|psql|mongo|mongosh|smbclient)\b[^\n]*?"
        r"\s-p\s*)(?!-)(?!\d+\b)[^\s]{4,}"
    ),
    re.compile(r"\b(gh[pousr]_)[A-Za-z0-9]{16,}"),
    re.compile(r"\b(sk-(?:proj-|ant-)?)[A-Za-z0-9_\-]{16,}"),
    re.compile(r"\b(AKIA)[0-9A-Z]{12,}"),
    re.compile(r"(?i)(://[^/\s:@]+:)[^@/\s]+(@)"),
    re.compile(r"(?i)\b(aws_secret_access_key\s*=\s*)\S+"),
)


def redact(command: str) -> tuple[str, bool]:
    """返回 (脱敏后命令, 是否发生替换)。"""
    out = command
    for pattern in _PATTERNS:
        if pattern.groups >= 2:
            out = pattern.sub(lambda m: m.group(1) + _PLACEHOLDER + (m.group(2) or ""), out)
        else:
            out = pattern.sub(lambda m: m.group(1) + _PLACEHOLDER, out)
    return out, out != command

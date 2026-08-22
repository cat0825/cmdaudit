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
    # 赋值形式的凭据。左锚点不能是 `\b`：`_` 也是词字符，`GITHUB_TOKEN=` 里
    # TOKEN 前面没有词边界，`\b(api_key|token|...)` 会整条漏过。
    # 改成「任意非词字符或行首 + 可选的变量名前缀」，覆盖 `*_TOKEN` / `*_API_KEY` / `*_SECRET`；
    # 尾部 `[_-](key|secret|token)` 覆盖 `STRIPE_SECRET_KEY=` 这类复合名。
    re.compile(
        r"(?i)((?:^|[^A-Za-z0-9_])[A-Za-z0-9_]*"
        r"(?:api[_-]?key|access[_-]?token|secret|password|passwd|pwd|token)"
        r"(?:[_-](?:key|secret|token))?[ \t]*[=:][ \t]*)[^\"'\s&]+"
    ),
    # 选项形式：`--token=value` 与 `--token value`。`[=\s]` 必须吃掉一个分隔符，
    # 否则 `--token` 后面跟的是下一个选项时会把它当值误吞。
    # 刻意只收 token / api-key 两种明确凭据词，不收 `--secret`/`--password`：
    # `docker service create --secret <名字>` 是引用名字不是凭据本身。
    re.compile(
        r"(?i)((?:^|[\s;&|(])--[A-Za-z0-9_-]*"
        r"(?:token|api[_-]?key)(?:[=\s]+))[^\"'\s&]+"
    ),
    # `-p` 只在数据库客户端语境下当密码：否则 `mkdir -p /some/path` 会被误伤，
    # 而误伤会连带破坏后续的程序名解析。
    re.compile(
        r"(?i)\b((?:mysql|mysqldump|psql|mongo|mongosh|smbclient)\b[^\n]*?"
        r"\s-p\s*)(?!-)(?!\d+\b)[^\s]{4,}"
    ),
    re.compile(r"\b(gh[pousr]_)[A-Za-z0-9]{16,}"),
    # Slack / npm / HuggingFace 的令牌前缀。`{10,}` 防止 `npm_install` 这类
    # 普通词被误伤，这些平台的令牌本体都显著长于 10 个字符。
    re.compile(r"\b((?:xox[abprs]-|npm_|hf_))[A-Za-z0-9_\-]{10,}"),
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
